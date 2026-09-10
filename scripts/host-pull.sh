#!/usr/bin/env bash
set -euo pipefail
# Run on the host after a git push to this repo (SSH or .github/workflows/deploy-host.yml).
# Does not belong in any other project's pull script — this unit is independent.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Prompt on a TTY; fail immediately from Actions / pipes (no password hang).
SUDO=(sudo)
if [[ ! -t 0 ]]; then
  SUDO=(sudo -n)
fi

git pull --ff-only
uv sync

UNIT_SRC="$ROOT/deploy/host.local/intervals-icu.service"
if [[ ! -f "$UNIT_SRC" ]]; then
  UNIT_SRC="$ROOT/deploy/intervals-icu.service.example"
  echo "No deploy/host.local/intervals-icu.service — copying the example unit." >&2
  echo "Edit User/WorkingDirectory/ExecStart on the host before relying on this." >&2
fi

"${SUDO[@]}" cp "$UNIT_SRC" /etc/systemd/system/intervals-icu.service
"${SUDO[@]}" systemctl daemon-reload
"${SUDO[@]}" systemctl enable intervals-icu.service
"${SUDO[@]}" systemctl restart intervals-icu.service
"${SUDO[@]}" systemctl --no-pager --full status intervals-icu.service | head -20
