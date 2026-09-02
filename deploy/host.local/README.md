# Host-local overlay (gitignored)

Copy `../intervals-icu.service.example` to `intervals-icu.service` here and fill
in `User`, `WorkingDirectory`, `EnvironmentFile`, and the `uv` path from `which uv`.

Put Tailscale hostnames, MCP client URLs, and race-seed notes in a file in this
directory if you want them next to the unit — nothing in `host.local/` is
committed except this README.

`scripts/host-pull.sh` prefers `deploy/host.local/intervals-icu.service` when
that file exists.
