#!/usr/bin/env bash
# Launch FinalMacro from the project venv (used by the .desktop entry).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PYTHON="$ROOT/.venv/bin/python"
# A venv whose Python changed under it (a distro update moving python3 to a new
# version) still has an executable python but none of its packages: say so
# instead of exiting silently behind KRunner.
if [[ -x "$PYTHON" ]] && ! "$PYTHON" -c "import PySide6, discord" >/dev/null 2>&1; then
  msg="FinalMacro: the .venv can't load its packages (its Python probably changed). Run ./install.sh in $ROOT to rebuild it."
  if command -v notify-send >/dev/null 2>&1; then
    notify-send "FinalMacro" "$msg"
  fi
  echo "$msg" >&2
  exit 1
fi
if [[ ! -x "$PYTHON" ]]; then
  msg="FinalMacro: run ./install.sh in $ROOT first."
  if command -v notify-send >/dev/null 2>&1; then
    notify-send "FinalMacro" "$msg"
  fi
  echo "$msg" >&2
  exit 1
fi

exec "$PYTHON" "$ROOT/run.py" "$@"
