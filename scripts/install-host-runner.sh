#!/usr/bin/env bash
set -euo pipefail
# One-time on the host. Registers a runner labeled intervals-icu-host.
# Usage: RUNNER_TOKEN=... scripts/install-host-runner.sh https://github.com/you/intervals-icu-mcp

REPO_URL="${1:?usage: RUNNER_TOKEN=... $0 https://github.com/<owner>/<repo>}"
TOKEN="${RUNNER_TOKEN:?set RUNNER_TOKEN to a registration token from Settings → Actions → Runners}"
DEST="${RUNNER_DIR:-$HOME/actions-runner}"
LABELS="${RUNNER_LABELS:-intervals-icu-host}"
NAME="${RUNNER_NAME:-intervals-icu-host}"

mkdir -p "$DEST"
cd "$DEST"

if [[ ! -f ./config.sh ]]; then
  version="$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest \
    | sed -n 's/.*"tag_name": "v\([^"]*\)".*/\1/p' | head -1)"
  if [[ -z "$version" ]]; then
    echo "Could not resolve the latest actions/runner version." >&2
    exit 1
  fi
  tarball="actions-runner-linux-x64-${version}.tar.gz"
  curl -fsSL -o "$tarball" \
    "https://github.com/actions/runner/releases/download/v${version}/${tarball}"
  tar xzf "$tarball"
  rm -f "$tarball"
fi

if [[ ! -f .runner ]]; then
  ./config.sh --url "$REPO_URL" --token "$TOKEN" \
    --labels "$LABELS" --unattended --name "$NAME"
fi

echo "Runner configured in $DEST."
echo "Install the service (needs sudo):"
echo "  cd $DEST && sudo ./svc.sh install && sudo ./svc.sh start"
