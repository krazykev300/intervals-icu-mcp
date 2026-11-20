"""In-process MCP smoke test: real server, middleware and schemas; stubbed Intervals HTTP.

Drives the coaching-profile server through a FastMCP client the way a chat host
would (list tools, call them with JSON args) and checks what reaches the API.
Never touches intervals.icu: every request goes to a respx stub, and the
credentials are fake. Run with `make smoke`; exits non-zero on any failure.
Extend `main()` when a tool's write path changes.
"""

import asyncio
import json
import os
import sys
from typing import Any

os.environ.update(
    INTERVALS_ICU_API_KEY="fake",
    INTERVALS_ICU_ATHLETE_ID="i1",
    INTERVALS_ICU_TOOL_PROFILE="coaching",
    INTERVALS_ICU_DELETE_MODE="safe",
)
import respx
from fastmcp import Client
from httpx import Response
from mcp.types import TextContent

from intervals_icu_mcp.server import mcp
from intervals_icu_mcp.tool_profile import COACHING_PROMPTS, coaching_tools_for_delete_mode

B = "https://intervals.icu/api/v1"
sent = {}


def echo(key, eid=1):
    def f(req):
        body = json.loads(req.content) if req.content else {}
        sent[key] = body
        if isinstance(body, list):
            return Response(
                200,
                json=[
                    {"id": i, "start_date_local": "2026-12-01T00:00:00", **e}
                    for i, e in enumerate(body)
                ],
            )
        return Response(200, json={"id": eid, "start_date_local": "2026-12-01T00:00:00", **body})

    return f


ACT = {
    "id": "i9",
    "start_date_local": "2026-11-17T18:00:00",
    "name": "Gym",
    "type": "WeightTraining",
    "paired_event_id": 77,
    "icu_training_load": None,
}
ok: list[bool] = []


def _text(result: Any) -> str:
    block = result.content[0]
    assert isinstance(block, TextContent)
    return block.text


def check(name, cond):
    ok.append(cond)
    print(("PASS " if cond else "FAIL ") + name)


async def main():
    async with Client(mcp) as c:
        tools = {t.name: t for t in await c.list_tools()}
        expected = len(coaching_tools_for_delete_mode("safe"))
        check(f"coaching registers {expected} tools ({len(tools)})", len(tools) == expected)
        check("icu_log_session registered", "icu_log_session" in tools)
        props = tools["icu_create_event"].inputSchema["properties"]
        for p in [
            "purpose",
            "fallback",
            "carbs_per_hour",
            "role",
            "tags",
            "indoor",
            "external_id",
            "max_training_seconds",
            "can_train_sports",
        ]:
            check(f"create_event schema has {p}", p in props)
        check("tags schema is array", "array" in json.dumps(props["tags"]))
        with respx.mock(base_url=B, assert_all_called=False) as m:
            m.post("/athlete/i1/events").mock(side_effect=echo("create"))
            m.put("/athlete/i1/events/5").mock(side_effect=echo("update", 5))
            m.post("/athlete/i1/events/bulk").mock(side_effect=echo("bulk"))
            m.post("/athlete/i1/activities/manual").mock(
                side_effect=lambda r: Response(
                    200,
                    json={
                        **ACT,
                        **json.loads(r.content),
                        "paired_event_id": None,
                        "icu_training_load": 38,
                    },
                )
            )
            m.post("/athlete/i1/events/77/mark-done").mock(return_value=Response(200, json=ACT))
            m.get("/athlete/i1/events/77").mock(
                return_value=Response(
                    200,
                    json={
                        "id": 77,
                        "start_date_local": "2026-11-17T00:00:00",
                        "name": "Strength A3",
                        "category": "WORKOUT",
                        "type": "WeightTraining",
                    },
                )
            )
            day_acts: list[dict] = []
            m.get("/athlete/i1/activities").mock(side_effect=lambda r: Response(200, json=day_acts))
            strava = {
                "id": "2104",
                "start_date_local": "2026-11-17T16:15:28",
                "name": "Untitled",
                "type": None,
                "source": "STRAVA",
            }
            m.put("/activity/2104").mock(
                side_effect=lambda r: (
                    sent.__setitem__("strava_put", json.loads(r.content)),
                    Response(200, json={**strava, **json.loads(r.content)}),
                )[1]
            )
            m.put("/activity/i9").mock(
                side_effect=lambda r: (
                    sent.__setitem__("act_put", json.loads(r.content)),
                    Response(200, json={**ACT, **json.loads(r.content)}),
                )[1]
            )

            desc = "Warmup\n- 10m 60%\n\nMain 3x\n- 10m 95%\n- 5m 55%\n\nCooldown\n- 10m 50%"
            r = await c.call_tool(
                "icu_create_event",
                {
                    "start_date": "2026-12-01",
                    "name": "Threshold 3x10",
                    "category": "WORKOUT",
                    "event_type": "Ride",
                    "description": desc,
                    "purpose": "Threshold: raise the power you can hold for an hour",
                    "fallback": "If legs are flat after the first interval, switch to 90 minutes easy.",
                    "carbs_per_hour": 70,
                    "role": "key",
                    "tags": ["threshold"],
                    "indoor": True,
                },
            )
            d = json.loads(_text(r))
            s = sent["create"]
            print("--- composed description ---\n" + s["description"] + "\n---")
            check("create ok", "error" not in d)
            check(
                "layout order",
                s["description"].index("Threshold:")
                < s["description"].index("Warmup")
                < s["description"].index("Fuel:")
                < s["description"].index("Fallback:"),
            )
            check(
                "role tag + color + external_id",
                s["tags"] == ["threshold", "role:key"]
                and s["color"] == "#d32f2f"
                and s["external_id"].startswith("coach-"),
            )
            # composed description still lints/parses
            r = await c.call_tool("icu_preview_workout", {"description": s["description"]})
            pv = json.loads(_text(r))
            check(
                f"composed text previews, 3x repeat kept ({pv['data'].get('total_duration_seconds')}s)",
                pv["data"].get("total_duration_seconds") == 3900 and not pv["data"].get("warnings"),
            )

            r = await c.call_tool("icu_update_event", {"event_id": 5, "purpose": "x"})
            check("update purpose w/o description refused", "full description" in _text(r))
            await c.call_tool(
                "icu_update_event",
                {
                    "event_id": 5,
                    "description": s["description"],
                    "purpose": "Threshold: raise the power you can hold for an hour",
                    "carbs_per_hour": 90,
                    "fallback": "Easy 90.",
                },
            )
            u = sent["update"]["description"]
            check(
                "recompose idempotent",
                u.count("Threshold:") == 1
                and u.count("Fuel:") == 1
                and "90 g" in u
                and u.count("Fallback:") == 1,
            )

            r = await c.call_tool(
                "icu_create_event",
                {
                    "start_date": "2026-12-03",
                    "end_date": "2026-12-06",
                    "name": "Travel – hotel gym",
                    "category": "HOLIDAY",
                    "training_availability": "limited",
                    "max_training_seconds": 2700,
                    "can_train_sports": ["weighttraining"],
                },
            )
            s = sent["create"]
            d = json.loads(_text(r))["data"]
            check(
                "availability sent",
                s["training_availability"] == "LIMITED"
                and s["max_training_time"] == 2700
                and s["can_train_sports"] == ["WeightTraining"],
            )
            check(
                "availability echoed",
                d.get("max_training_seconds") == 2700
                and d.get("can_train_sports") == ["WeightTraining"],
            )
            r = await c.call_tool(
                "icu_create_event",
                {
                    "start_date": "2026-12-03",
                    "name": "x",
                    "category": "HOLIDAY",
                    "can_train_sports": ["Gym"],
                },
            )
            check("bad sport rejected", "Unknown sport" in _text(r))

            r = await c.call_tool(
                "icu_bulk_create_events",
                {
                    "events": json.dumps(
                        [
                            {
                                "start_date_local": "2026-12-01",
                                "name": "VO2",
                                "category": "WORKOUT",
                                "event_type": "Ride",
                                "description": desc,
                                "purpose": "VO2",
                                "role": "key",
                                "carbs_per_hour": 60,
                                "indoor": True,
                            },
                            {
                                "start_date_local": "2026-12-02",
                                "name": "Gym",
                                "category": "WORKOUT",
                                "event_type": "WeightTraining",
                                "description": "3x5 squat",
                                "role": "strength",
                            },
                        ]
                    )
                },
            )
            b = sent["bulk"]
            check(
                "bulk ok, friendly keys stripped",
                "error" not in _text(r)
                and not any(k in b[0] for k in ("purpose", "role", "fallback"))
                and b[0]["carbs_per_hour"] == 60,
            )
            check(
                "bulk strength colour",
                b[1]["color"] == "#7b1fa2" and b[1]["tags"] == ["role:strength"],
            )

            r = await c.call_tool(
                "icu_log_session",
                {"start_date": "2026-11-17", "duration_seconds": 3000, "rpe": 7, "kg_lifted": 4200},
            )
            d = json.loads(_text(r))["data"]
            check(
                "log manual", d["rpe"] == 7 and d["kg_lifted"] == 4200 and d["training_load"] == 38
            )
            r = await c.call_tool(
                "icu_log_session", {"event_id": 77, "duration_seconds": 3000, "rpe": 7}
            )
            d = json.loads(_text(r))["data"]
            check(
                "log paired via mark-done + PUT",
                d["paired_event_id"] == 77
                and sent["act_put"] == {"moving_time": 3000, "elapsed_time": 3000, "icu_rpe": 7}
                and "training_load_hint" in d,
            )
            r = await c.call_tool("icu_log_session", {"rpe": 7})
            check("log needs date+duration", "start_date and duration_seconds" in _text(r))
            day_acts.append(strava)
            r = await c.call_tool(
                "icu_log_session", {"event_id": 77, "duration_seconds": 3000, "rpe": 6}
            )
            d = json.loads(_text(r))["data"]
            check(
                "log lands on the Strava recording, paired",
                d["activity_id"] == "2104"
                and sent["strava_put"]
                == {"name": "Strength A3", "icu_rpe": 6, "paired_event_id": 77},
            )

            # Illness protocol (playbook section 7): the two writes it prescribes.
            r = await c.call_tool(
                "icu_create_event",
                {
                    "start_date": "2026-12-01",
                    "end_date": "2026-12-03",
                    "name": "Head cold",
                    "category": "SICK",
                    "training_availability": "LIMITED",
                    "max_training_seconds": 2700,
                    "description": "Above the neck only. Removed: Threshold 3x10.",
                },
            )
            s = sent["create"]
            check(
                "protocol: SICK window with limits",
                "error" not in json.loads(_text(r))
                and s["category"] == "SICK"
                and s["training_availability"] == "LIMITED"
                and s["max_training_time"] == 2700
                and s["end_date_local"].startswith("2026-12-03"),
            )
            r = await c.call_tool(
                "icu_update_event", {"event_id": 5, "category": "NOTE", "name": "Rest"}
            )
            check(
                "protocol: today's session becomes a rest note",
                sent["update"] == {"name": "Rest", "category": "NOTE"},
            )

        prompts = {p.name for p in await c.list_prompts()}
        check(f"coaching lists {len(COACHING_PROMPTS)} prompts", prompts == set(COACHING_PROMPTS))
        sick = await c.get_prompt("im_sick", {"what": "head cold"})
        body = sick.messages[0].content
        assert isinstance(body, TextContent)
        check(
            "im_sick prompt: state, guide, protocol",
            "icu_get_athlete_state" in body.text
            and "icu_get_coaching_guide" in body.text
            and "7. Illness and injury protocol" in body.text
            and "head cold" in body.text,
        )
        short = await c.get_prompt("i_have_45_minutes", {"minutes": "30"})
        body = short.messages[0].content
        assert isinstance(body, TextContent)
        check("i_have_45_minutes prompt takes minutes", "30 minutes" in body.text)

        res = await c.call_tool("icu_get_coaching_guide", {})
        check(
            "guide carries session layout + log_session",
            "Session layout" in _text(res) and "icu_log_session" in _text(res),
        )
        check(
            "guide carries illness protocol + return rule",
            "## 7. Illness and injury protocol" in _text(res)
            and "## Return from a break" in _text(res),
        )
    print(f"\n{sum(ok)}/{len(ok)} passed")
    return all(ok)


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
