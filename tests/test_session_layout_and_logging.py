"""Backlog 1.1 (session layout), 1.6 (availability), 1.9 (logging a session)."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import Response

from intervals_icu_mcp.tools.event_management import (
    _compose_session_description,
    bulk_create_events,
    create_event,
    log_session,
    update_event,
)

STEPS = "Warmup\n- 10m 60%\n\nMain 3x\n- 10m 95%\n- 5m 55%\n\nCooldown\n- 10m 50%"


@pytest.fixture
def ctx(mock_config):
    mock_ctx = MagicMock()
    mock_ctx.get_state = AsyncMock(return_value=mock_config)
    return mock_ctx


def _echo(request, event_id: int = 1):
    body = json.loads(request.content)
    return Response(200, json={"id": event_id, **body})


class TestComposeDescription:
    def test_layout_order(self):
        out = _compose_session_description(STEPS, "Threshold: hold power", 60, "Go easy")
        assert out == (
            "Threshold: hold power\n\n"
            + STEPS
            + "\n\nFuel: 60 g carbs per hour.\nFallback: Go easy"
        )

    def test_recompose_is_idempotent(self):
        once = _compose_session_description(STEPS, "Purpose", 60, "Fallback text")
        twice = _compose_session_description(once, "Purpose", 80, "Fallback text")
        assert twice is not None
        assert twice.count("Purpose") == 1
        assert twice.count("Fuel:") == 1
        assert "80 g" in twice
        assert twice.count("Fallback:") == 1

    def test_no_layout_fields_is_passthrough(self):
        assert _compose_session_description(STEPS, None, None, None) == STEPS


class TestSessionLayoutCreate:
    async def test_create_sends_layout_fields(self, ctx, respx_mock):
        route = respx_mock.post("/athlete/i123456/events").mock(side_effect=_echo)
        result = await create_event(
            start_date="2026-12-01",
            name="Threshold 3x10",
            category="WORKOUT",
            event_type="Ride",
            description=STEPS,
            purpose="Threshold: raise the power you can hold for an hour",
            fallback="If legs are flat after the first interval, switch to 90 minutes easy.",
            carbs_per_hour=70,
            role="key",
            tags=["threshold"],
            indoor=True,
            ctx=ctx,
        )
        sent = json.loads(route.calls.last.request.content)
        assert sent["description"].startswith("Threshold: raise")
        assert "Fuel: 70 g carbs per hour." in sent["description"]
        assert sent["description"].endswith("switch to 90 minutes easy.")
        assert sent["carbs_per_hour"] == 70
        assert sent["tags"] == ["threshold", "role:key"]
        assert sent["color"] == "#d32f2f"
        assert sent["indoor"] is True
        assert sent["external_id"].startswith("coach-")
        data = json.loads(result)["data"]
        assert data["tags"] == ["threshold", "role:key"]
        assert data["indoor"] is True
        assert data["carbs_per_hour"] == 70
        assert data["workout_parsed"] is False  # echo has no workout_doc

    async def test_explicit_color_and_external_id_win(self, ctx, respx_mock):
        route = respx_mock.post("/athlete/i123456/events").mock(side_effect=_echo)
        await create_event(
            start_date="2026-12-01",
            name="Easy",
            category="WORKOUT",
            role="easy",
            color="#000000",
            external_id="mine-1",
            ctx=ctx,
        )
        sent = json.loads(route.calls.last.request.content)
        assert sent["color"] == "#000000"
        assert sent["external_id"] == "mine-1"

    async def test_no_role_no_external_id(self, ctx, respx_mock):
        route = respx_mock.post("/athlete/i123456/events").mock(side_effect=_echo)
        await create_event(start_date="2026-12-01", name="Note", category="NOTE", ctx=ctx)
        sent = json.loads(route.calls.last.request.content)
        assert "external_id" not in sent
        assert "tags" not in sent

    async def test_invalid_role(self, ctx):
        result = await create_event(
            start_date="2026-12-01", name="X", category="WORKOUT", role="hero", ctx=ctx
        )
        assert "Invalid role" in json.loads(result)["error"]["message"]

    async def test_carbs_out_of_range(self, ctx):
        result = await create_event(
            start_date="2026-12-01", name="X", category="WORKOUT", carbs_per_hour=500, ctx=ctx
        )
        assert "carbs_per_hour" in json.loads(result)["error"]["message"]


class TestSessionLayoutUpdate:
    async def test_purpose_without_description_is_refused(self, ctx):
        result = await update_event(event_id=5, purpose="New purpose", ctx=ctx)
        assert "full description" in json.loads(result)["error"]["message"]

    async def test_carbs_alone_sets_field_only(self, ctx, respx_mock):
        route = respx_mock.put("/athlete/i123456/events/5").mock(
            side_effect=lambda r: _echo(r, 5)
        )
        await update_event(event_id=5, carbs_per_hour=90, ctx=ctx)
        sent = json.loads(route.calls.last.request.content)
        assert sent == {"carbs_per_hour": 90}

    async def test_role_on_update_does_not_mint_external_id(self, ctx, respx_mock):
        route = respx_mock.put("/athlete/i123456/events/5").mock(
            side_effect=lambda r: _echo(r, 5)
        )
        await update_event(event_id=5, role="support", ctx=ctx)
        sent = json.loads(route.calls.last.request.content)
        assert sent == {"tags": ["role:support"], "color": "#1976d2"}


class TestAvailability:
    async def test_holiday_with_limits(self, ctx, respx_mock):
        route = respx_mock.post("/athlete/i123456/events").mock(side_effect=_echo)
        result = await create_event(
            start_date="2026-12-03",
            end_date="2026-12-06",
            name="Travel",
            category="HOLIDAY",
            training_availability="limited",
            max_training_seconds=2700,
            can_train_sports=["weighttraining", "Run"],
            ctx=ctx,
        )
        sent = json.loads(route.calls.last.request.content)
        assert sent["training_availability"] == "LIMITED"
        assert sent["max_training_time"] == 2700
        assert sent["can_train_sports"] == ["WeightTraining", "Run"]
        data = json.loads(result)["data"]
        assert data["max_training_seconds"] == 2700
        assert data["can_train_sports"] == ["WeightTraining", "Run"]

    async def test_unknown_sport_rejected(self, ctx):
        result = await create_event(
            start_date="2026-12-03",
            name="Travel",
            category="HOLIDAY",
            can_train_sports=["Gym"],
            ctx=ctx,
        )
        assert "Unknown sport" in json.loads(result)["error"]["message"]

    async def test_update_availability(self, ctx, respx_mock):
        route = respx_mock.put("/athlete/i123456/events/9").mock(
            side_effect=lambda r: _echo(r, 9)
        )
        await update_event(event_id=9, max_training_seconds=3600, ctx=ctx)
        assert json.loads(route.calls.last.request.content) == {"max_training_time": 3600}


class TestBulkLayoutAndAvailability:
    async def test_bulk_translates_friendly_fields(self, ctx, respx_mock):
        def echo_bulk(request):
            body = json.loads(request.content)
            return Response(200, json=[{"id": i + 1, **e} for i, e in enumerate(body)])

        route = respx_mock.post("/athlete/i123456/events/bulk").mock(side_effect=echo_bulk)
        events = [
            {
                "start_date_local": "2026-12-01",
                "name": "Threshold",
                "category": "WORKOUT",
                "event_type": "Ride",
                "description": STEPS,
                "purpose": "Threshold",
                "fallback": "Easy instead",
                "carbs_per_hour": 60,
                "role": "key",
            },
            {
                "start_date_local": "2026-12-03",
                "end_date_local": "2026-12-06",
                "name": "Travel",
                "category": "HOLIDAY",
                "training_availability": "LIMITED",
                "max_training_seconds": 1800,
                "can_train_sports": ["WeightTraining"],
            },
        ]
        result = await bulk_create_events(events=json.dumps(events), ctx=ctx)
        sent = json.loads(route.calls.last.request.content)
        assert "purpose" not in sent[0] and "role" not in sent[0] and "fallback" not in sent[0]
        assert sent[0]["description"].startswith("Threshold\n\nWarmup")
        assert sent[0]["tags"] == ["role:key"]
        assert sent[0]["external_id"].startswith("coach-")
        assert sent[1]["max_training_time"] == 1800
        assert "max_training_seconds" not in sent[1]
        assert "error" not in json.loads(result)

    async def test_bulk_bad_role(self, ctx):
        events = [{"start_date_local": "2026-12-01", "name": "X", "category": "WORKOUT", "role": "x"}]
        result = await bulk_create_events(events=json.dumps(events), ctx=ctx)
        assert "Event 0: Invalid role" in json.loads(result)["error"]["message"]


ACTIVITY = {
    "id": "i9001",
    "start_date_local": "2026-11-17T00:00:00",
    "name": "Strength",
    "type": "WeightTraining",
}


class TestLogSession:
    async def test_manual_activity_without_event(self, ctx, respx_mock):
        def echo(request):
            body = json.loads(request.content)
            return Response(200, json={**ACTIVITY, **body, "icu_training_load": 40})

        route = respx_mock.post("/athlete/i123456/activities/manual").mock(side_effect=echo)
        result = await log_session(
            start_date="2026-11-17", duration_seconds=3000, rpe=7, kg_lifted=4200.0, ctx=ctx
        )
        sent = json.loads(route.calls.last.request.content)
        assert sent["type"] == "WeightTraining"
        assert sent["name"] == "Strength"
        assert sent["moving_time"] == 3000
        assert sent["icu_rpe"] == 7
        assert sent["kg_lifted"] == 4200.0
        data = json.loads(result)["data"]
        assert data["rpe"] == 7
        assert data["training_load"] == 40
        assert "training_load_hint" not in data

    async def test_pairs_with_event_then_updates(self, ctx, respx_mock):
        respx_mock.post("/athlete/i123456/events/77/mark-done").mock(
            return_value=Response(200, json={**ACTIVITY, "paired_event_id": 77})
        )
        put = respx_mock.put("/activity/i9001").mock(
            return_value=Response(
                200, json={**ACTIVITY, "moving_time": 3000, "icu_rpe": 7, "paired_event_id": 77}
            )
        )
        result = await log_session(event_id=77, duration_seconds=3000, rpe=7, ctx=ctx)
        sent = json.loads(put.calls.last.request.content)
        assert sent == {"moving_time": 3000, "elapsed_time": 3000, "icu_rpe": 7}
        data = json.loads(result)["data"]
        assert data["paired_event_id"] == 77
        assert "training_load_hint" in data

    async def test_event_only_skips_update(self, ctx, respx_mock):
        respx_mock.post("/athlete/i123456/events/77/mark-done").mock(
            return_value=Response(200, json=ACTIVITY)
        )
        put = respx_mock.put("/activity/i9001")
        result = await log_session(event_id=77, ctx=ctx)
        assert not put.called
        assert json.loads(result)["data"]["paired_event_id"] == 77

    async def test_requires_date_and_duration_without_event(self, ctx):
        result = await log_session(rpe=7, ctx=ctx)
        assert "start_date and duration_seconds" in json.loads(result)["error"]["message"]

    async def test_rpe_range(self, ctx):
        result = await log_session(event_id=1, rpe=11, ctx=ctx)
        assert "rpe" in json.loads(result)["error"]["message"]
