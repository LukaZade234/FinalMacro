#!/usr/bin/env bash
# Setup: create .venv and install dependencies. Safe to run again.
#
# The venv is built on a Python that only changes when you change it:
# uv's own managed CPython (PYTHON_VERSION below). A venv on the system
# python3 breaks when a distro update moves it to a new minor version — the
# packages stay behind under the old version's folder and nothing imports
# (Fedora 45 moved 3.14 → 3.15, and discord.py-self's dependencies had no
# 3.15 builds yet).
#
# Without uv it falls back to pythonX.Y if installed, then python3, with a
# warning. A venv that exists but can no longer import its packages is
# rebuilt.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_VERSION="3.14"

venv_works() {
  [[ -x .venv/bin/python ]] && .venv/bin/python -c "import PySide6, discord" >/dev/null 2>&1
}

if [[ -d .venv ]] && ! venv_works; then
  stamp="$(date +%Y%m%d-%H%M%S)"
  echo "The existing .venv can't import its packages (its Python probably changed)."
  echo "Moving it aside to .venv-broken-$stamp and rebuilding …"
  mv .venv ".venv-broken-$stamp"
fi

UV="$(command -v uv || true)"
if [[ -z "$UV" && -x "$HOME/.local/bin/uv" ]]; then
  UV="$HOME/.local/bin/uv"
fi

if [[ ! -d .venv ]]; then
  if [[ -n "$UV" ]]; then
    echo "Creating .venv on uv-managed Python $PYTHON_VERSION …"
    "$UV" venv --python "$PYTHON_VERSION" --python-preference only-managed .venv
  elif command -v "python$PYTHON_VERSION" >/dev/null 2>&1; then
    echo "uv not found — creating .venv with python$PYTHON_VERSION."
    echo "  (It will break if that Python is removed; installing uv avoids this:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh)"
    "python$PYTHON_VERSION" -m venv .venv
  else
    echo "uv and python$PYTHON_VERSION not found — falling back to python3 ($(python3 --version 2>&1))."
    echo "  This venv breaks when a system update changes python3's version."
    echo "  Installing uv avoids that: curl -LsSf https://astral.sh/uv/install.sh | sh"
    python3 -m venv .venv
  fi
fi

echo "Installing requirements …"
if [[ -n "$UV" ]]; then
  "$UV" pip install --python .venv/bin/python -r requirements.txt pytest
else
  .venv/bin/python -m pip install -U pip
  .venv/bin/python -m pip install -r requirements.txt pytest
fi

if ! venv_works; then
  echo "" >&2
  echo "Install finished, but .venv still can't import PySide6 / discord — see the errors above." >&2
  exit 1
fi

echo ""
echo "Done ($(.venv/bin/python --version)). Start the app with:"
echo "  source .venv/bin/activate && python run.py"
echo "or:"
echo "  ./launch.sh"
echo ""
echo "Optional — add to your app launcher (Alt+Space, rofi, etc.):"
echo "  ./install-desktop.sh"
