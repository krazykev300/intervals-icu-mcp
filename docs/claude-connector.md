# Claude.ai and Claude iOS (custom connector)

Phone Claude and claude.ai call MCP **from Anthropic’s cloud**, not from the
device. Tailscale Serve (tailnet-only) is invisible to them. Brain already
uses Funnel for that reason. This server can Funnel **port 8443** without
taking Brain’s Funnel on 443.

Read [identities.md](identities.md) before Funneling: a link token in a
request header selects which Intervals.icu account this process uses. Do not
Funnel with `INTERVALS_ICU_HTTP_AUTH=off` and no tokens.

## One-time on the host

1. Put a link token in `.env` (`openssl rand -hex 32` → `INTERVALS_ICU_LINK_TOKEN`).
2. Confirm the unit still binds `127.0.0.1:8788`.
3. Restart the unit so it picks up `.env`.
4. Serve, then Funnel **8443 only**:

```bash
sudo tailscale serve --bg --https=8443 http://127.0.0.1:8788
sudo tailscale funnel --https=8443 on
sudo tailscale serve status
sudo tailscale funnel status
```

Expect:

- Funnel 443 → Brain (`127.0.0.1:8787`) unchanged
- `https://<magicdns>:8443` Funnel → `127.0.0.1:8788` (this server)

5. Probe without a token (must be 401 once the token is configured):

```bash
curl -sS -o /dev/null -w "%{http_code}\n" \
  -X POST https://<magicdns>:8443/mcp \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
```

## Add the connector in Claude

Works on the website and the iOS app for the same account.

1. **Customize → Connectors → Add custom connector** (Team/Enterprise: an
   owner adds it under organization connectors first).
2. URL: `https://<magicdns-host>:8443/mcp`
3. Authentication: **None**
4. Request headers: `Authorization` = `Bearer <link_token>`
5. Add, then enable the connector in the chat’s tools menu.

Anthropic will request `/.well-known/oauth-protected-resource`; **404 is
normal** — this server is not OAuth. The bearer header is the login.

Free plans allow one custom connector; Pro/Max more. Brain already occupies a
slot if you Funnel Brain.

## Generate and write workouts

After the connector is on, ask Claude to draft sessions, then write them with
`icu_create_event` (`category=WORKOUT`, description = Intervals workout
syntax). Review in the Intervals.icu calendar UI before you ride.

A Strava MCP is a **separate** process (own port, own Funnel path or 10000,
own link token). This repo does not vendor Strava.

## Isolation

If a change would not make sense to a client that only has this MCP, it does
not belong here. Do not add Brain `propose_fact` wrappers or store Intervals
API keys in Brain. The link token may be stored in Brain as a personal secret
so you remember which Claude connector is which identity — see
[identities.md](identities.md).
