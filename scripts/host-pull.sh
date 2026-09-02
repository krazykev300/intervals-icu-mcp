#!/usr/bin/env bash
set -euo pipefail
# Run on the host after a git push to this repo. Does not belong in any other
# project's pull script — this unit is independent.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

git pull --ff-only
uv sync

UNIT_SRC="$ROOT/deploy/host.local/intervals-icu.service"
if [[ ! -f "$UNIT_SRC" ]]; then
  UNIT_SRC="$ROOT/deploy/intervals-icu.service.example"
  echo "No deploy/host.local/intervals-icu.service — copying the example unit." >&2
  echo "Edit User/WorkingDirectory/ExecStart on the host before relying on this." >&2
fi

sudo cp "$UNIT_SRC" /etc/systemd/system/intervals-icu.service
sudo systemctl daemon-reload
sudo systemctl enable intervals-icu.service
sudo systemctl restart intervals-icu.service
sudo systemctl --no-pager --full status intervals-icu.service | head -20
