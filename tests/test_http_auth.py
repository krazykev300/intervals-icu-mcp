"""Link-token HTTP identity tests."""

import json
from pathlib import Path

import httpx
import pytest
from asgi_lifespan import LifespanManager
from pydantic import ValidationError

from intervals_icu_mcp.auth import ICUConfig
from intervals_icu_mcp.http_auth import starlette_middleware
from intervals_icu_mcp.identity import (
    config_for_identity,
    extract_link_token,
    http_auth_required,
    list_identities,
    lookup_identity,
)
from intervals_icu_mcp.server import mcp


def _cfg(**kwargs: object) -> ICUConfig:
    defaults: dict[str, object] = {
        "intervals_icu_api_key": "k",
        "intervals_icu_athlete_id": "i1",
    }
    defaults.update(kwargs)
    return ICUConfig.model_validate(defaults)


class TestHttpAuthConfig:
    def test_default_is_auto(self, monkeypatch):
        monkeypatch.delenv("INTERVALS_ICU_HTTP_AUTH", raising=False)
        cfg = _cfg()
        assert cfg.intervals_icu_http_auth == "auto"

    def test_rejects_invalid(self):
        with pytest.raises(ValidationError, match="INTERVALS_ICU_HTTP_AUTH"):
            _cfg(intervals_icu_http_auth="banana")


class TestIdentities:
    def test_auto_off_when_no_tokens(self):
        cfg = _cfg(intervals_icu_link_token="")
        assert http_auth_required(cfg) is False
        assert list_identities(cfg) == []

    def test_auto_on_when_env_token_present(self):
        cfg = _cfg(intervals_icu_link_token="secret-token")
        assert http_auth_required(cfg) is True
        assert lookup_identity("secret-token", cfg) is not None
        assert lookup_identity("wrong", cfg) is None

    def test_off_mode_ignores_tokens(self):
        cfg = _cfg(intervals_icu_http_auth="off", intervals_icu_link_token="secret-token")
        assert http_auth_required(cfg) is False

    def test_link_token_mode_requires_even_without_identities(self):
        cfg = _cfg(intervals_icu_http_auth="link_token", intervals_icu_link_token="")
        assert http_auth_required(cfg) is True
        assert lookup_identity("anything", cfg) is None

    def test_identities_file(self, tmp_path: Path):
        path = tmp_path / "identities.json"
        path.write_text(
            json.dumps(
                {
                    "identities": [
                        {
                            "name": "other",
                            "link_token": "tok-b",
                            "intervals_icu_api_key": "key-b",
                            "intervals_icu_athlete_id": "i2",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        cfg = _cfg(
            intervals_icu_link_token="tok-a",
            intervals_icu_identities_file=str(path),
        )
        names = {row.name: row for row in list_identities(cfg)}
        assert set(names) == {"env", "other"}
        ident = lookup_identity("tok-b", cfg)
        assert ident is not None
        bound = config_for_identity(ident, cfg)
        assert bound.intervals_icu_api_key == "key-b"
        assert bound.intervals_icu_athlete_id == "i2"

    def test_extract_bearer_and_extra_header(self):
        assert extract_link_token("Bearer abc", "") == "abc"
        assert extract_link_token("bearer abc", "") == "abc"
        assert extract_link_token("", "xyz") == "xyz"
        assert extract_link_token("", "") == ""


class TestHttpLinkTokenGate:
    async def test_401_without_token(self, monkeypatch):
        monkeypatch.setenv("INTERVALS_ICU_HTTP_AUTH", "link_token")
        monkeypatch.setenv("INTERVALS_ICU_LINK_TOKEN", "gate-token")
        monkeypatch.setenv("INTERVALS_ICU_API_KEY", "k")
        monkeypatch.setenv("INTERVALS_ICU_ATHLETE_ID", "i1")

        app = mcp.http_app(middleware=starlette_middleware())
        async with LifespanManager(app) as manager:
            transport = httpx.ASGITransport(app=manager.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/mcp",
                    json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
                    headers={"Accept": "application/json, text/event-stream"},
                )
        assert resp.status_code == 401
        assert resp.json()["error"]["type"] == "auth_error"

    async def test_200_with_bearer(self, monkeypatch):
        monkeypatch.setenv("INTERVALS_ICU_HTTP_AUTH", "link_token")
        monkeypatch.setenv("INTERVALS_ICU_LINK_TOKEN", "gate-token")
        monkeypatch.setenv("INTERVALS_ICU_API_KEY", "k")
        monkeypatch.setenv("INTERVALS_ICU_ATHLETE_ID", "i1")

        app = mcp.http_app(middleware=starlette_middleware())
        async with LifespanManager(app) as manager:
            transport = httpx.ASGITransport(app=manager.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/mcp",
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
                    headers={
                        "Accept": "application/json, text/event-stream",
                        "Authorization": "Bearer gate-token",
                    },
                )
        assert resp.status_code == 200
        assert "intervals_icu_mcp" in resp.text

    async def test_well_known_oauth_probe_is_not_401(self, monkeypatch):
        monkeypatch.setenv("INTERVALS_ICU_HTTP_AUTH", "link_token")
        monkeypatch.setenv("INTERVALS_ICU_LINK_TOKEN", "gate-token")
        monkeypatch.setenv("INTERVALS_ICU_API_KEY", "k")
        monkeypatch.setenv("INTERVALS_ICU_ATHLETE_ID", "i1")

        app = mcp.http_app(middleware=starlette_middleware())
        async with LifespanManager(app) as manager:
            transport = httpx.ASGITransport(app=manager.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/.well-known/oauth-protected-resource")
        assert resp.status_code != 401
