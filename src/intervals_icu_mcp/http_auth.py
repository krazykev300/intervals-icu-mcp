"""ASGI gate: Funnel-safe HTTP requires a link token that selects an Intervals identity."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qsl, urlencode

from starlette.middleware import Middleware
from starlette.types import ASGIApp, Receive, Scope, Send

from .identity import (
    config_for_identity,
    extract_link_token,
    http_auth_required,
    lookup_identity,
    reset_http_config,
    set_http_config,
)

_UNAUTHORIZED = json.dumps(
    {
        "error": {
            "message": (
                "Send Authorization: Bearer <link_token>, X-Intervals-Link, "
                "or ?link=<link_token> on the URL."
            ),
            "type": "auth_error",
        }
    }
).encode()


_PUBLIC_PATH_PREFIXES = ("/.well-known/",)
_PUBLIC_PATHS = frozenset({"/register", "/.well-known/oauth-protected-resource"})


def _is_auth_exempt(path: str) -> bool:
    """Claude custom connectors probe OAuth metadata before sending the Bearer header.

    401 on those URLs looks like a dead server. Let FastMCP 404 them instead.
    `/mcp` still requires a link token.
    """
    if path in _PUBLIC_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in _PUBLIC_PATH_PREFIXES)


class LinkTokenMiddleware:
    """Pure ASGI middleware so request-scoped identity uses contextvars correctly."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Always strip ?link= so the secret never reaches logs, even when auth is off.
        query_token = _pop_query_token(scope)
        if not http_auth_required():
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        if _is_auth_exempt(path):
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])
        }
        token = extract_link_token(
            headers.get("authorization", ""), headers.get("x-intervals-link", ""), query_token
        )
        identity = lookup_identity(token)
        if identity is None:
            await _send_unauthorized(send)
            return

        reset_token = set_http_config(config_for_identity(identity))
        try:
            await self.app(scope, receive, send)
        finally:
            reset_http_config(reset_token)


_QUERY_PARAM = "link"


def _pop_query_token(scope: Scope) -> str:
    """Take `link` out of the query string and return its value.

    The scope is mutated in place so uvicorn's access log (which reads the same
    dict) and everything downstream never see the secret.
    """
    raw = scope.get("query_string") or b""
    if not raw:
        return ""
    pairs = parse_qsl(raw.decode("latin-1"), keep_blank_values=True)
    token = ""
    kept: list[tuple[str, str]] = []
    for key, value in pairs:
        if key == _QUERY_PARAM:
            token = token or value
        else:
            kept.append((key, value))
    if len(kept) != len(pairs):
        scope["query_string"] = urlencode(kept).encode("latin-1")
    return token


def starlette_middleware() -> list[Any]:
    """Always installed; no-ops when no link tokens are configured (HTTP_AUTH=auto)."""
    return [Middleware(LinkTokenMiddleware)]


async def _send_unauthorized(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b'Bearer realm="intervals-icu-mcp"'),
                (b"content-length", str(len(_UNAUTHORIZED)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": _UNAUTHORIZED})
