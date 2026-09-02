# Self-host (HTTP + Tailscale Serve)

How to run this server on a machine you control, over streamable HTTP, without
putting hostnames, Linux usernames, or race calendars in git.

Transport flags and the generic security model live in
[remote-deployment.md](remote-deployment.md). This page is the opinionated
layout for a **coaching / management** instance.

## What this server is

| | |
| --- | --- |
| Source of truth for | Race calendar (A/B/C events), planned workouts, wellness, CTL/ATL/form, power/HR/pace curves |
| Not | Goals, racing identity, constraints — keep those in a separate knowledge store if you use one |
| Transport | Streamable HTTP, bind `127.0.0.1`, path `/mcp` |
| Front door (tailnet) | Tailscale **Serve** HTTPS **8443** → localhost 8788 |
| Front door (Claude.ai / iOS) | **Funnel 443** (path `/intervals-icu` if `/` is taken) plus a [link token](identities.md). Anthropic does not dial `:8443`. Do not Funnel with HTTP auth off. |
| Writes | Straight to Intervals.icu. Review planned workouts in the Intervals calendar UI. |

If a change would not make sense to a client that only has this MCP, it does not
belong in this repository. Coaching turn order and `INTERVALS_*` env live here.
Do not store Intervals API keys, athlete ids, or CTL numbers in a knowledge
store. A **link token** may live there as a personal secret — it selects an
identity on this server; it is not the Intervals API key. See
[identities.md](identities.md) and [claude-connector.md](claude-connector.md).

## Locked process settings (recommended)

```
bind:              127.0.0.1
port:              8788          # not 8000 (FastMCP default); pick any free localhost port
Tailscale Serve:   --bg --https=8443 http://127.0.0.1:8788
Tailscale Funnel:  --bg --https=443 --set-path=/intervals-icu http://127.0.0.1:8788
Claude MCP URL:    https://<magicdns-host>/intervals-icu/mcp   (port 443 only)
Cursor (optional): Funnel/Serve 8443 → same localhost port
INTERVALS_ICU_DELETE_MODE: safe
INTERVALS_ICU_TOOL_PROFILE: coaching
INTERVALS_ICU_HTTP_AUTH: auto
```

`--host` and `--port` are CLI flags, not env vars. Credentials stay in `.env`
on the host (`chmod 600`), never in git.

Auth is Intervals.icu personal API: HTTP Basic username `API_KEY`, password =
the key. Get both at https://intervals.icu/settings → Developer.

## Files in this repo vs on the host

Committed (generic):

- `.env.example`
- `deploy/intervals-icu.service.example`
- `scripts/host-pull.sh`
- this document

Host-only (gitignored overlay):

- `.env`
- `deploy/host.local/intervals-icu.service` — copy of the example with real User/paths
- any notes you drop in `deploy/host.local/` (Tailscale hostname, client URL, race seed list)

See `deploy/host.local/README.md`.

## Install (once)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone <this-repo> ~/intervals-icu-mcp
cd ~/intervals-icu-mcp
uv sync
cp .env.example .env
chmod 600 .env
# fill INTERVALS_ICU_API_KEY and INTERVALS_ICU_ATHLETE_ID

cp deploy/intervals-icu.service.example deploy/host.local/intervals-icu.service
# edit User, Group, WorkingDirectory, EnvironmentFile, ExecStart (`which uv`)

sudo cp deploy/host.local/intervals-icu.service /etc/systemd/system/intervals-icu.service
sudo systemctl daemon-reload
sudo systemctl enable --now intervals-icu.service

# Tailnet-only (Cursor on the same tailnet):
sudo tailscale serve --bg --https=8443 http://127.0.0.1:8788
# Claude.ai / iOS — Funnel 443 (path if another MCP already owns /). Not :8443.
sudo tailscale funnel --bg --https=443 --set-path=/intervals-icu http://127.0.0.1:8788
sudo tailscale funnel status
# Funnel only after INTERVALS_ICU_LINK_TOKEN is set — see docs/claude-connector.md
```

After later pushes, run `scripts/host-pull.sh` on the host. Do not hook that
script from another project's pull helper.

## Client config

Env vars stay on the **server**. Tailnet clients need the HTTPS URL. If a link
token is configured, they must send it (see [identities.md](identities.md)).

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

Claude.ai / iOS cannot use Serve or Funnel `:8443`. Funnel **443** + connector
header: [claude-connector.md](claude-connector.md).

## Seed races in the Intervals UI

Create typed events. `event_type` is required (Ride or Run). Priority is the
`category`: `RACE_A`, `RACE_B`, or `RACE_C` (see `intervals-icu://event-categories`).

Dates live here. Why a race matters belongs in a goals store, if you have one.

## Checklist

- [ ] `.env` on the host, mode 600, not in git
- [ ] `deploy/host.local/intervals-icu.service` filled in
- [ ] `systemctl enable --now intervals-icu`
- [ ] `tailscale serve` to localhost:8788
- [ ] Link token set before Funnel; Funnel 443 for Claude (path if `/` is taken)
- [ ] Client `mcp.json` / Claude connector sends `Authorization: Bearer`
- [ ] Seed A/B/C races in the Intervals calendar UI
