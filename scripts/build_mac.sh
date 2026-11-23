#!/bin/bash
# Builds "dist/TidyDrop.app" on a Mac.
# Needs Python 3.12+ (python.org installer or `brew install python`).
# Run in Terminal:   bash scripts/build_mac.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then
  echo "Python 3.12 or newer is needed. Install it from python.org (recommended) and run again."
  exit 1
fi
if ! "$PYTHON" -c 'import tkinter' 2>/dev/null; then
  echo "This Python has no Tk (needed for the Settings window)."
  echo "Use the python.org installer, or with Homebrew run:  brew install python-tk"
  exit 1
fi
if [ ! -d .venv-mac ]; then "$PYTHON" -m venv .venv-mac; fi
source .venv-mac/bin/activate
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements-dev.txt --quiet
python tools/make_icons.py
python -m pytest -q

python -m PyInstaller --noconfirm --clean --windowed \
  --name "TidyDrop" \
  --icon assets/icon.icns \
  --osx-bundle-identifier com.tidydrop.app \
  --hidden-import pystray._darwin \
  run.pyw

APP="dist/TidyDrop.app"
# Menu-bar only app: no Dock icon.
plutil -insert LSUIElement -bool true "$APP/Contents/Info.plist" 2>/dev/null \
  || plutil -replace LSUIElement -bool true "$APP/Contents/Info.plist"
# Re-sign after editing Info.plist (ad-hoc signature, fine for your own Mac).
codesign --force --deep --sign - "$APP"

# Standard Mac installer: a disk image with the app and an Applications shortcut to drag it onto.
DMG="dist/TidyDrop.dmg"
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
hdiutil create -volname "TidyDrop" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGE"

echo ""
echo "Built: $DMG"
echo "Open it, drag TidyDrop onto Applications, then open the app once with right-click > Open."
