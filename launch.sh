#!/usr/bin/env bash
# Launch FinalMacro from the project venv (used by the .desktop entry).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  msg="FinalMacro: run ./install.sh in $ROOT first."
  if command -v notify-send >/dev/null 2>&1; then
    notify-send "FinalMacro" "$msg"
  fi
  echo "$msg" >&2
  exit 1
fi

exec "$PYTHON" "$ROOT/run.py" "$@"
