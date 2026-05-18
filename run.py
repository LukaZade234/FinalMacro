#!/usr/bin/env python3
"""Launch the Mudae parse lab GUI."""

from __future__ import annotations

import sys


def _check_dependencies() -> None:
    missing: list[str] = []
    try:
        import PySide6  # noqa: F401
    except ImportError:
        missing.append("PySide6")
    try:
        import discord  # noqa: F401
    except ImportError:
        missing.append("discord.py-self")

    if not missing:
        return

    root = __import__("pathlib").Path(__file__).resolve().parent
    venv_python = root / ".venv" / "bin" / "python"
    lines = [
        "Missing Python packages: " + ", ".join(missing),
        "",
        "This project needs a virtual environment with dependencies installed.",
        "From the project folder run:",
        "",
        "  cd ~/Documents/FinalMacro",
        "  python3 -m venv .venv",
        "  source .venv/bin/activate",
        "  pip install -r requirements.txt",
        "  python run.py",
        "",
        f"You ran: {sys.executable}",
    ]
    if venv_python.is_file():
        lines.extend(
            [
                "",
                "A venv already exists — use it instead:",
                f"  {venv_python} {root / 'run.py'}",
            ]
        )
    print("\n".join(lines), file=sys.stderr)
    sys.exit(1)


def main() -> None:
    _check_dependencies()
    from gui.app import main as run_gui

    run_gui()


if __name__ == "__main__":
    main()
