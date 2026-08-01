#!/usr/bin/env bash
# Install a user-level .desktop entry so FinalMacro appears in app launchers.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_THEME="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
DESKTOP_FILE="$APPS_DIR/finalmacro.desktop"
ICON_SRC="$ROOT/assets/app-icon.png"
LAUNCHER="$ROOT/launch.sh"
ICON_NAME="finalmacro"

if [[ ! -f "$ICON_SRC" ]]; then
  echo "Missing icon: $ICON_SRC" >&2
  exit 1
fi
if [[ ! -x "$LAUNCHER" ]]; then
  chmod +x "$LAUNCHER"
fi

mkdir -p "$APPS_DIR"
for size in 32 48 64 128 256; do
  dir="$ICON_THEME/${size}x${size}/apps"
  mkdir -p "$dir"
  cp "$ICON_SRC" "$dir/${ICON_NAME}.png"
done

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=FinalMacro
GenericName=Mudae Macro
Comment=Automated Mudae rolling and kakera macro
Exec=$LAUNCHER
Icon=$ICON_SRC
StartupWMClass=FinalMacro
Terminal=false
StartupNotify=true
Categories=Game;Utility;
Keywords=mudae;discord;macro;roll;kakera;
EOF

chmod +x "$DESKTOP_FILE"

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t "$ICON_THEME" 2>/dev/null || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPS_DIR" 2>/dev/null || true
fi
if command -v kbuildsycoca6 >/dev/null 2>&1; then
  kbuildsycoca6 --noincremental 2>/dev/null || true
elif command -v kbuildsycoca5 >/dev/null 2>&1; then
  kbuildsycoca5 --noincremental 2>/dev/null || true
fi

echo "Installed desktop entry:"
echo "  $DESKTOP_FILE"
echo ""
echo "FinalMacro should appear in your app launcher (Alt+Space, rofi, GNOME overview, etc.)."
echo "If the icon still looks old, restart KRunner/Plasma or log out and back in."
