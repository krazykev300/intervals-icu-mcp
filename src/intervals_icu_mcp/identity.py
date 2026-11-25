"""Link tokens: HTTP identity for Funnel without putting Intervals API keys in a knowledge store.

A link token is a capability for *this* MCP process. It is not an Intervals.icu
API key. The process can map several tokens to several Intervals accounts;
stdio and HTTP-without-a-token still use `.env`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from .auth import ICUConfig, load_config

_http_config: ContextVar[ICUConfig | None] = ContextVar("icu_http_config", default=None)


@dataclass(frozen=True)
class Identity:
    """One Intervals.icu account reachable via a link token."""

    name: str
    link_token: str
    api_key: str
    athlete_id: str


def current_http_config() -> ICUConfig | None:
    """Identity selected by the HTTP bearer for this request, if any."""
    return _http_config.get()


def request_config() -> ICUConfig:
    """Intervals credentials for the caller of this request.

    Over HTTP with a link token this is that identity's key and athlete id;
    over stdio (or HTTP with auth off) it is the process `.env`. Anything that
    calls the Intervals API must get its credentials here (or from the
    middleware-injected ctx state, which is set from this), never from
    `load_config()` directly: that always returns the host's own account, so a
    second athlete on a shared server would read or write the host's data.
    """
    return current_http_config() or load_config()


def credential_key(config: ICUConfig) -> str:
    """Short, non-reversible fingerprint of the API key, for keying caches.

    Key every in-process cache by this plus the athlete id. An athlete id alone
    is not a secret: a caller can pass any id as a tool argument, and a cache hit
    would return another account's data before Intervals.icu checks the key.
    """
    digest = hashlib.sha256(config.intervals_icu_api_key.encode("utf-8")).hexdigest()
    return digest[:16]


def set_http_config(config: ICUConfig | None) -> Token[ICUConfig | None]:
    """Bind the request-scoped Intervals identity. Returns a reset token."""
    return _http_config.set(config)


def reset_http_config(token: Token[ICUConfig | None]) -> None:
    _http_config.reset(token)


def extract_link_token(authorization: str, extra_header: str, query_token: str = "") -> str:
    """Read Bearer from Authorization, a raw X-Intervals-Link, or the `?link=` query value.

    Headers win over the query string. The query form exists for Claude custom
    connectors that cannot send request headers.
    """
    auth = authorization.strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return extra_header.strip() or query_token.strip()


def http_auth_required(config: ICUConfig | None = None) -> bool:
    """Whether HTTP requests must present a configured link token."""
    cfg = config or load_config()
    mode = cfg.intervals_icu_http_auth
    if mode == "off":
        return False
    if mode == "link_token":
        return True
    return bool(list_identities(cfg))


def list_identities(config: ICUConfig | None = None) -> list[Identity]:
    """Identities from INTERVALS_ICU_LINK_TOKEN + optional identities JSON file."""
    cfg = config or load_config()
    found: list[Identity] = []
    if cfg.intervals_icu_link_token and cfg.intervals_icu_api_key and cfg.intervals_icu_athlete_id:
        found.append(
            Identity(
                name="env",
                link_token=cfg.intervals_icu_link_token,
                api_key=cfg.intervals_icu_api_key,
                athlete_id=cfg.intervals_icu_athlete_id,
            )
        )
    path = cfg.intervals_icu_identities_file.strip()
    if path:
        found.extend(_identities_from_file(Path(path)))
    return [row for row in found if row.link_token and row.api_key and row.athlete_id]


def lookup_identity(token: str, config: ICUConfig | None = None) -> Identity | None:
    """Constant-time match of `token` against configured identities."""
    if not token:
        return None
    cfg = config or load_config()
    matched: Identity | None = None
    for identity in list_identities(cfg):
        if hmac.compare_digest(identity.link_token, token):
            matched = identity
    return matched


def config_for_identity(identity: Identity, base: ICUConfig | None = None) -> ICUConfig:
    """Process-level delete mode / tool profile, identity-level API credentials."""
    cfg = base or load_config()
    return cfg.model_copy(
        update={
            "intervals_icu_api_key": identity.api_key,
            "intervals_icu_athlete_id": identity.athlete_id,
        }
    )


class _IdentityFileRow(BaseModel):
    name: str = ""
    link_token: str = ""
    intervals_icu_api_key: str = ""
    api_key: str = ""
    intervals_icu_athlete_id: str = ""
    athlete_id: str = ""


def _empty_identity_rows() -> list[_IdentityFileRow]:
    return []


class _IdentityFile(BaseModel):
    identities: list[_IdentityFileRow] = Field(default_factory=_empty_identity_rows)


def _identities_from_file(path: Path) -> list[Identity]:
    if not path.is_file():
        return []
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(parsed, list):
        file = _IdentityFile.model_validate({"identities": parsed})
    else:
        file = _IdentityFile.model_validate(parsed)
    out: list[Identity] = []
    for i, row in enumerate(file.identities):
        out.append(
            Identity(
                name=row.name.strip() or f"file-{i}",
                link_token=row.link_token.strip(),
                api_key=(row.intervals_icu_api_key or row.api_key).strip(),
                athlete_id=(row.intervals_icu_athlete_id or row.athlete_id).strip(),
            )
        )
    return out
