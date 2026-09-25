#!/bin/sh
# Adds Lectern to your desktop's application menu (Linux).
# Run from the project folder after setting up .venv, or pass the path to a built dist/Lectern/Lectern.
set -e
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
EXEC="${1:-$HERE/.venv/bin/python -m lectern}"
mkdir -p "$HOME/.local/share/applications" "$HOME/.local/share/icons/hicolor/scalable/apps"
cp "$HERE/lectern/resources/icon.svg" "$HOME/.local/share/icons/hicolor/scalable/apps/lectern.svg"
cat > "$HOME/.local/share/applications/lectern.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Lectern
GenericName=Bible Reader
Comment=RSV-2CE Bible and Coverdale Psalter
Exec=sh -c 'cd "$HERE" && $EXEC'
Icon=lectern
Categories=Education;Literature;
Terminal=false
DESK
echo "Installed: $HOME/.local/share/applications/lectern.desktop"
