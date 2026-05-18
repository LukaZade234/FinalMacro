#!/usr/bin/env bash
# One-time setup: create venv and install dependencies.
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d .venv ]]; then
  echo "Creating .venv …"
  python3 -m venv .venv
fi

echo "Installing requirements …"
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt

echo ""
echo "Done. Start the app with:"
echo "  source .venv/bin/activate && python run.py"
echo "or:"
echo "  .venv/bin/python run.py"
