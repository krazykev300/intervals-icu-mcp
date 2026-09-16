# Identities and link tokens

How this server binds an HTTP client to an Intervals.icu account **without**
baking that account into the process, and without putting Intervals API keys in
a knowledge store.

## The problem

Funnel (public HTTPS) is required for Claude.ai / Claude iOS: Anthropic’s cloud
calls the MCP URL, not your phone. MCP has no protocol login. If the process
always uses `INTERVALS_ICU_API_KEY` from `.env`, two bad outcomes follow:

1. Anyone who finds the Funnel URL is you, on Intervals.icu.
2. The daemon is permanently one Intervals.icu account, not a gateway that can
   select an identity per client.

A knowledge store holding the Intervals API key would violate isolation (goals
and racing identity live there; API secrets and CTL numbers do not).

## What a link token is

A **link token** is a long random secret that means “use *this* Intervals.icu
identity on *this* MCP.” It is **not** the Intervals Developer API key.

| Secret | Where it lives | Who sees it |
| --- | --- | --- |
| Intervals.icu API key + athlete id | Host `.env` and/or `identities.json` (mode 600, never git) | This process only |
| Link token | Same host files **and optionally** a knowledge store as a personal secret | HTTP client (Claude connector header) and, if you choose, that store |

Rotate the link token without rotating the Intervals API key. Revoke one
identity without taking the process down.

## How HTTP selects an account

When HTTP auth is active, every request must send:

```
Authorization: Bearer <link_token>
```

or `X-Intervals-Link: <link_token>`.

The ASGI gate (`http_auth.py`) maps the token to credentials **before** MCP
runs. Wrong or missing token → **401**. Tool handlers then use that identity’s
API key (`identity.py` + `ConfigMiddleware`).

stdio (local Cursor `uvx`) never uses this gate. It keeps using `.env`.

### `INTERVALS_ICU_HTTP_AUTH`

| Value | Behavior |
| --- | --- |
| `auto` (default) | Require a bearer **only if** at least one link token is configured |
| `link_token` | Always require a bearer on HTTP (even if you forgot to configure tokens — every call 401s) |
| `off` | Never require a bearer. Tailnet Serve is then the only gate. Do not Funnel. |

### Single identity (typical)

In host `.env`:

```
INTERVALS_ICU_API_KEY=...
INTERVALS_ICU_ATHLETE_ID=i...
INTERVALS_ICU_LINK_TOKEN=<openssl rand -hex 32>
INTERVALS_ICU_HTTP_AUTH=auto
```

That token maps to the `.env` API key.

### Several identities

`INTERVALS_ICU_IDENTITIES_FILE=/home/you/intervals-icu-mcp/deploy/host.local/identities.json`

```json
{
  "identities": [
    {
      "name": "personal",
      "link_token": "long-random-a",
      "intervals_icu_api_key": "...",
      "intervals_icu_athlete_id": "i111"
    },
    {
      "name": "coached-athlete",
      "link_token": "long-random-b",
      "intervals_icu_api_key": "...",
      "intervals_icu_athlete_id": "i222"
    }
  ]
}
```

Each Claude (or Cursor) connector is configured with **one** bearer, so it is
one Intervals account. The process is shared.

See `deploy/identities.json.example`.

## Why another MCP cannot “log you in” at request time

Claude.ai (and the iOS app) open **two separate HTTPS connections** from
Anthropic’s cloud: one to each custom connector. The model can *read* a
link token from another MCP. It **cannot** attach that value as an HTTP header
on the Intervals connector. Connector headers are static in Claude’s UI.

So the working design is:

1. Generate a link token on the Intervals host.
2. Paste it into the Claude custom connector as `Authorization: Bearer …`
   (auth = None; the header *is* the login).
3. Optionally store **the same link token** (not the API key) in a knowledge
   store as a personal secret so you remember which identity that Claude
   account uses.

Do **not** add an `icu_bind_session(token)` tool. That would put the secret in
the model’s tool arguments every turn (logs, prompt injection, leakage).

## What not to put in a knowledge store

Never: `INTERVALS_ICU_API_KEY`, athlete id as a credential, CTL/ATL numbers,
race dates as facts (dates are Intervals events).

Allowed: the link token, and racing *why* (intent, limiter, identity).

## Cursor on the tailnet

If a link token is configured, Serve clients must send it too:

```json
{
  "mcpServers": {
    "intervals-icu": {
      "url": "https://<magicdns-host>:8443/mcp",
      "headers": {
        "Authorization": "Bearer <link_token>"
      }
    }
  }
}
```

If you have **no** `INTERVALS_ICU_LINK_TOKEN` and no identities file, HTTP stays
open (`auto`). That is the Serve-only setup.

## Resource caveat

The `intervals-icu://athlete/profile` resource does not see HTTP headers; it
still reflects process `.env`. Tools use the bearer identity. Prefer tools for
phone/Claude.ai coaching turns.
