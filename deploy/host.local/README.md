# Host-local overlay (gitignored)

Copy `../intervals-icu.service.example` to `intervals-icu.service` here and fill
in `User`, `WorkingDirectory`, `EnvironmentFile`, and the `uv` path from `which uv`.

Put Tailscale hostnames, MCP client URLs, race-seed notes, and
`identities.json` (link tokens → Intervals API keys) in this directory if you
want them next to the unit — nothing in `host.local/` is committed except this
README. Copy `../identities.json.example` as a starting point.

`scripts/host-pull.sh` prefers `deploy/host.local/intervals-icu.service` when
that file exists. Optional GitHub Actions: `docs/self-host.md` (self-hosted
runner lives outside this clone). Funnel and Claude.ai:
`docs/claude-connector.md` and `docs/identities.md`.
