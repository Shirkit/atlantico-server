#!/usr/bin/env bash
# Starts the Atlantico server from the repository root.
# Ensures the current working directory is the repo root so relative data
# paths (weights/, parse/, metrics/) resolve correctly.

set -euo pipefail

# Resolve script directory and change to repo root (one level up from scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SCRIPT_DIR%/scripts}"
cd "$REPO_ROOT"

# Prefer using .venv if present
if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
  PY="$REPO_ROOT/.venv/bin/python"
else
  PY="$(command -v python3 || command -v python)"
fi

echo "Starting server using Python: $($PY -V 2>&1)" >&2

exec "$PY" -m atlantico_server.tui_runner "$@"
