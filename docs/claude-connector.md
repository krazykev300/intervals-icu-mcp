# Claude.ai and Claude iOS (custom connector)

How to put this MCP on **claude.ai** and the **Claude iOS app**. Those clients
call the server from **Anthropic’s cloud**, not from your phone or laptop.
A URL that only works on your Tailscale network will fail there even when
Cursor on the same tailnet is fine.

Claude Desktop and local Claude Code use **stdio** — skip this page and use
the README client snippets.

## Serve vs Funnel

| | Tailscale **Serve** | Tailscale **Funnel** |
| --- | --- | --- |
| Who can reach it | Devices on your tailnet | The public internet (Anthropic, ChatGPT, anyone with the URL) |
| Typical clients | Cursor, Claude Code on a tailnet node | claude.ai, Claude iOS |
| Status line | `(tailnet only)` | `(Funnel on)` |

Funnel ports are **443**, **8443**, and **10000**. **Claude.ai / iOS only
dial 443.** Anthropic’s backend never opens `:8443` or `:10000` (confirmed
in [claude-ai-mcp#125](https://github.com/anthropics/claude-ai-mcp/issues/125)).
A Funnel on 8443 can look healthy (`Funnel on`, curl from your tailnet
works) while Claude shows “Couldn’t reach … MCP” and your process logs stay
empty of Anthropic IPs.

If Funnel **443 `/`** is already another MCP, add a **path** on 443. Do not
replace `/`. Do not `funnel reset`.

Do **not** Funnel with `INTERVALS_ICU_HTTP_AUTH=off` and no [link
token](identities.md). MCP has no protocol login; the bearer header *is* the
login. Read identities.md before you publish.

## One-time on the host

Assume the process binds `127.0.0.1:8788` (see [self-host.md](self-host.md)).
Substitute your localhost port, MagicDNS name, and path.

1. Put a link token in `.env` (`openssl rand -hex 32` → `INTERVALS_ICU_LINK_TOKEN`).
2. Confirm the unit still binds `127.0.0.1` (not `0.0.0.0`).
3. Restart the unit so it picks up `.env`.
4. Funnel **443** for Claude. Tailscale **1.52+**: `funnel` takes a **target**,
   not `on`.

**This is the only MCP on Funnel 443:**

```bash
sudo tailscale funnel --bg --https=443 http://127.0.0.1:8788
```

Connector URL: `https://<magicdns>.ts.net/mcp`

**Another MCP already owns 443 `/`:** add a path (keeps `/` unchanged):

```bash
sudo tailscale funnel --bg --https=443 --set-path=/intervals-icu http://127.0.0.1:8788
sudo tailscale funnel status
```

Expect:

```text
https://<magicdns>.ts.net (Funnel on)
|-- / proxy http://127.0.0.1:<other-mcp>
|-- /intervals-icu proxy http://127.0.0.1:8788
```

Connector URL: `https://<magicdns>.ts.net/intervals-icu/mcp`

Optional Funnel **8443** is for Cursor/tailnet clients only — not Claude.ai.

Do **not** run `tailscale funnel reset` unless you intend to drop **every**
Funnel on that node.

5. Probe the **Claude** URL **without** a token (must be **401** once a link
   token is set):

```bash
curl -sS -o /dev/null -w "%{http_code}\n" \
  -X POST https://<magicdns>.ts.net/intervals-icu/mcp \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
```

### Wrong Funnel command (Tailscale 1.52+)

This used to mean “enable Funnel on 8443.” Current CLIs treat `on` as the
backend URL (`http://on`):

```bash
# WRONG — error: non-localhost target "http://on" must include a scheme
sudo tailscale funnel --https=8443 on
```

Use `--bg --https=443 http://127.0.0.1:<port>` (and `--set-path=` if needed).

## Add the connector in Claude

Works on the website and the iOS app for the **same** Anthropic account.

1. **Customize → Connectors → Add custom connector** (Team/Enterprise: an
   owner adds it under organization connectors first).
2. URL: `https://<magicdns-host>/mcp` (or `/intervals-icu/mcp` if you
   Funneled a path — **no `:8443`**)
3. Authentication: **None**
4. Request headers: `Authorization` = `Bearer <link_token>`  
   (`Bearer`, a space, then the token — no quotes.)
5. Add, then **enable the connector in that chat’s tools menu**. Adding it
   under Connectors is not enough; the chat must have it turned on.

Anthropic probes `/.well-known/oauth-protected-resource` **without** the
Bearer header. This server lets those requests through (typically **404** =
no OAuth). `/mcp` still requires the header. If discovery returns **401**,
Claude reports “Couldn’t connect” even when Funnel is on.

Free plans allow one custom connector; Pro/Max more. Another Funnel MCP
already occupies a slot if you connected it the same way.

## Troubleshooting

| What you see | Likely cause | What to do |
| --- | --- | --- |
| “Couldn’t reach … MCP” / “Check that the URL points to a valid MCP server” | URL has `:8443` / `:10000`; Anthropic never leaves their network | Use Funnel **443** (path if `/` is taken). Logs on this MCP stay empty until then |
| Same error on a `:443` URL | Funnel not on; still `(tailnet only)`; or OAuth probe 401 | `funnel --bg --https=443 …`. URL must end in `/mcp`. Exempt `/.well-known/` from the link-token gate |
| Cursor works, Claude.ai/iOS does not | Serve, or Funnel on a non-443 port | Serve is enough for the tailnet. Claude.ai needs Funnel **on 443** |
| 401 on `POST /mcp` from `curl` without `Authorization` | Expected once a link token is configured | Add the Bearer header on the connector |
| 401 on `POST /mcp` **with** the header | Wrong token or extra whitespace/quotes | `Bearer` + space + the same value as `INTERVALS_ICU_LINK_TOKEN` |
| Tools missing in a chat | Connector added but not enabled for that conversation | Enable it in the chat tools menu (website **and** iOS) |

## Generate and write workouts

Phone coaching is an MCP skill (server instructions +
`intervals-icu://coaching-playbook` + prompt `coach_with_goals`). Human
walkthrough: [claude-ios-coaching.md](claude-ios-coaching.md).

After the connector is on, ask for coaching in plain language. The model
should propose sessions, then write them with `icu_create_event`. Review in
the Intervals.icu calendar UI before you ride.

A Strava MCP is a **separate** process (own port, own Funnel path or 10000,
own link token). This repo does not vendor Strava.

## Isolation

If a change would not make sense to a client that only has this MCP, it does
not belong here. Do not store Intervals API keys in a goals/knowledge MCP.
The link token may be stored there as a personal secret so you remember which
Claude connector is which identity — see [identities.md](identities.md).
