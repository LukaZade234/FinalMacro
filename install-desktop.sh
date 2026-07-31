#!/usr/bin/env bash
# Install a user-level .desktop entry so FinalMacro appears in app launchers.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"
DESKTOP_FILE="$APPS_DIR/finalmacro.desktop"
ICON_SRC="$ROOT/assets/app-icon.png"
LAUNCHER="$ROOT/launch.sh"

if [[ ! -f "$ICON_SRC" ]]; then
  echo "Missing icon: $ICON_SRC" >&2
  exit 1
fi
if [[ ! -x "$LAUNCHER" ]]; then
  chmod +x "$LAUNCHER"
fi

mkdir -p "$APPS_DIR" "$ICONS_DIR"
cp "$ICON_SRC" "$ICONS_DIR/finalmacro.png"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=FinalMacro
GenericName=Mudae Macro
Comment=Automated Mudae rolling and kakera macro
Exec=$LAUNCHER
Icon=finalmacro
Terminal=false
StartupNotify=true
Categories=Game;Utility;
Keywords=mudae;discord;macro;roll;kakera;
EOF

chmod +x "$DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPS_DIR" 2>/dev/null || true
fi

echo "Installed desktop entry:"
echo "  $DESKTOP_FILE"
echo ""
echo "FinalMacro should appear in your app launcher (Alt+Space, rofi, GNOME overview, etc.)."
echo "If it does not show up immediately, log out and back in or restart the launcher."
