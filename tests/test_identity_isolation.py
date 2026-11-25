"""One server, several athletes: every Intervals call and cache follows the caller's link token.

A shared HTTP server maps each link token to its own Intervals.icu key. Code that
reads the host `.env` directly (`load_config()`), or a cache keyed only by the
athlete id, hands one athlete's data to another. These tests pin both rules.
"""

import ast
import base64
import json
from pathlib import Path

import httpx
import pytest
from asgi_lifespan import LifespanManager
from httpx import Response

from intervals_icu_mcp.auth import ICUConfig
from intervals_icu_mcp.coaching.athlete_state import _athlete_today, _timezone_cache
from intervals_icu_mcp.http_auth import starlette_middleware
from intervals_icu_mcp.server import mcp

SRC = Path(__file__).resolve().parent.parent / "src" / "intervals_icu_mcp"

# Modules allowed to call load_config(): it defines it, the identity layer wraps it,
# server.py reads process-wide settings (tool profile, delete mode) at import, and
# the auth setup script writes the host .env.
_LOAD_CONFIG_ALLOWED = {
    "auth.py",
    "identity.py",
    "server.py",
    "scripts/setup_auth.py",
}

HOST = {"key": "host-key", "athlete": "i111", "token": "host-token"}
FRIEND = {"key": "friend-key", "athlete": "i222", "token": "friend-token"}


def _basic_key(request: httpx.Request) -> str:
    raw = request.headers["authorization"].split(" ", 1)[1]
    return base64.b64decode(raw).decode().split(":", 1)[1]


class TestNoDirectHostCredentials:
    def test_load_config_only_where_allowed(self):
        offenders: list[str] = []
        for path in SRC.rglob("*.py"):
            rel = path.relative_to(SRC).as_posix()
            if rel in _LOAD_CONFIG_ALLOWED:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    name = getattr(func, "id", None) or getattr(func, "attr", None)
                    if name == "load_config":
                        offenders.append(f"{rel}:{node.lineno}")
        assert not offenders, (
            "load_config() returns the host's own Intervals account. Use "
            "identity.request_config() or the ctx 'config' state instead: " + ", ".join(offenders)
        )

    def test_server_uses_load_config_only_for_process_settings(self):
        """server.py may read the tool profile and delete mode, never call the API with it."""
        text = (SRC / "server.py").read_text(encoding="utf-8")
        assert text.count("load_config()") == 1
        assert "ICUClient(_CONFIG)" not in text


class TestCachesFollowCredentials:
    async def test_timezone_cache_does_not_cross_api_keys(self, respx_mock):
        """Passing another athlete's id must not return their cached profile data."""
        _timezone_cache.clear()
        respx_mock.get(f"/athlete/{HOST['athlete']}").mock(
            side_effect=lambda req: (
                Response(200, json={"timezone": "Pacific/Kiritimati"})
                if _basic_key(req) == HOST["key"]
                else Response(403, json={"error": "forbidden"})
            )
        )
        from intervals_icu_mcp.client import ICUClient

        host_cfg = ICUConfig(
            intervals_icu_api_key=HOST["key"], intervals_icu_athlete_id=HOST["athlete"]
        )
        friend_cfg = ICUConfig(
            intervals_icu_api_key=FRIEND["key"], intervals_icu_athlete_id=FRIEND["athlete"]
        )
        try:
            async with ICUClient(host_cfg) as client:
                _, tz = await _athlete_today(client, HOST["athlete"])
            assert tz == "Pacific/Kiritimati"
            async with ICUClient(friend_cfg) as client:
                _, tz = await _athlete_today(client, HOST["athlete"])
            assert tz is None
        finally:
            _timezone_cache.clear()


def _identities_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "identities.json"
    path.write_text(
        json.dumps(
            {
                "identities": [
                    {
                        "name": who,
                        "link_token": row["token"],
                        "intervals_icu_api_key": row["key"],
                        "intervals_icu_athlete_id": row["athlete"],
                    }
                    for who, row in (("host", HOST), ("friend", FRIEND))
                ]
            }
        ),
        encoding="utf-8",
    )
    # The host .env is the account a leak would fall back to.
    monkeypatch.setenv("INTERVALS_ICU_API_KEY", HOST["key"])
    monkeypatch.setenv("INTERVALS_ICU_ATHLETE_ID", HOST["athlete"])
    monkeypatch.setenv("INTERVALS_ICU_IDENTITIES_FILE", str(path))
    monkeypatch.setenv("INTERVALS_ICU_HTTP_AUTH", "link_token")


def _rpc_result(resp: httpx.Response) -> dict:
    assert resp.status_code == 200, resp.text
    if resp.headers.get("content-type", "").startswith("application/json"):
        return resp.json()
    for line in resp.text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:])
    raise AssertionError(f"no JSON-RPC payload in {resp.text!r}")


async def _call_as(token: str, method: str, params: dict) -> dict:
    app = mcp.http_app(middleware=starlette_middleware())
    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {token}",
    }
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            init = await client.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "pytest", "version": "0"},
                    },
                },
            )
            _rpc_result(init)
            session = init.headers.get("mcp-session-id")
            if session:
                headers["mcp-session-id"] = session
            await client.post(
                "/mcp",
                headers=headers,
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            )
            resp = await client.post(
                "/mcp",
                headers=headers,
                json={"jsonrpc": "2.0", "id": 2, "method": method, "params": params},
            )
            return _rpc_result(resp)


class TestHttpIdentityReachesEveryCall:
    """Each bearer reaches Intervals.icu with its own key and athlete id, not the host .env."""

    @pytest.fixture
    def intervals_api(self, respx_mock):
        seen: list[tuple[str, str]] = []

        def _record(request: httpx.Request) -> Response:
            seen.append((_basic_key(request), request.url.path))
            if request.url.path.endswith("/sport-settings"):
                return Response(200, json=[{"id": 1, "types": ["Ride"], "ftp": 200}])
            return Response(200, json={"id": "x", "name": "Someone", "sportSettings": []})

        respx_mock.route(host="intervals.icu").mock(side_effect=_record)
        return seen

    @pytest.mark.parametrize("who", [HOST, FRIEND], ids=["host", "friend"])
    async def test_sport_settings_tool(self, who, intervals_api, monkeypatch, tmp_path):
        _identities_env(monkeypatch, tmp_path)
        result = await _call_as(
            who["token"], "tools/call", {"name": "icu_get_sport_settings", "arguments": {}}
        )
        assert "error" not in result, result
        assert intervals_api, "no Intervals call was made"
        assert all(key == who["key"] for key, _ in intervals_api), intervals_api
        assert all(f"/athlete/{who['athlete']}/" in path for _, path in intervals_api)

    async def test_profile_resource(self, intervals_api, monkeypatch, tmp_path):
        _identities_env(monkeypatch, tmp_path)
        result = await _call_as(
            FRIEND["token"], "resources/read", {"uri": "intervals-icu://athlete/profile"}
        )
        assert "error" not in result, result
        assert intervals_api, "no Intervals call was made"
        assert all(key == FRIEND["key"] for key, _ in intervals_api), intervals_api
