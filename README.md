# FinalMacro

Desktop GUI for automating Mudae rolls, kakera reactions, `$us` batches, and related minigames on Discord.

Built with **PySide6** (QML) and **discord.py-self**.

## Requirements

- Linux (primary; may work on macOS/Windows with manual setup)
- Python 3.10+
- A Discord **user** token (configure inside the app — never commit it)

## Install

From the project folder:

```bash
./install.sh
```

This creates `.venv` and installs dependencies from `requirements.txt`.

## Run

**Terminal:**

```bash
.venv/bin/python run.py
```

or:

```bash
./launch.sh
```

**App launcher (Alt+Space, rofi, GNOME overview, etc.):**

```bash
./install-desktop.sh
```

That installs a user-level entry at `~/.local/share/applications/finalmacro.desktop` and an icon so you can start FinalMacro with a click or by searching “FinalMacro” or “Mudae”.

Re-run `./install-desktop.sh` if you move the project to a different folder (the launcher stores the absolute path to `launch.sh`).

## First-time setup

1. **Accounts** — add your Discord account token.
2. **Servers** — add the Mudae channel; fetch `$settings` / `$bonus` when prompted.
3. **Presets** — configure roll rules, kakera colors, `$us` behavior, etc.
4. **Run** — pick account, channel, and preset, then connect and start.

Settings are saved to `data/settings.json` (gitignored). That single file holds accounts, macro presets, Mudae settings presets, server/channel profiles (including fetched `$settings` / `$bonus`), and run targets. Session logs go under `data/session_logs/`.

## Sharing with friends

Share the repo or a zip **without** your `data/` folder (tokens and logs stay local). Friends run `./install.sh`, then `./install-desktop.sh`, and set up their own account, channel, and preset.

## Docs

| File | What it is |
|------|------------|
| [`docs/MUDAE_LOGIC.md`](docs/MUDAE_LOGIC.md) | How Mudae works, and how the macro uses each mechanic |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | File map, runtime flow, stores, Phase D |
| [`docs/TODO.md`](docs/TODO.md) | Open work |
| [`docs/archive/`](docs/archive/) | Reference mocks and superseded docs ([README](docs/archive/README.md)) |

## Project layout

| Path | Purpose |
|------|---------|
| `run.py` | Entry point |
| `launch.sh` | Wrapper for venv + desktop launcher |
| `gui/` | PySide6 / QML interface |
| `macro/` | Roll cycle, kakera, minigames |
| `mudae/` | Discord reader, parsers, logs |
| `docs/` | Game logic, architecture, TODO, [archive](docs/archive/) |
| `data/` | Local settings and logs (not in git) |

## Disclaimer

This app automates a Discord **user** account. That violates [Discord’s Terms of Service](https://discord.com/terms) and can lead to warnings or account action. Use at your own risk, only on accounts you accept may be restricted.
