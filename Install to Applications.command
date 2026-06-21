#!/bin/bash
# Build the .app and install to your Applications folder (no admin password).
cd "$(dirname "$0")"
clear
echo "=============================================="
echo "  Install Eliseus Sorter to Applications"
echo "=============================================="
echo ""

bash "./code/build_mac_app.sh"
APP_SRC="./dist/Eliseus Sorter.app"

if [[ ! -d "$APP_SRC" ]]; then
  echo "Build failed — app bundle not found."
  read -r -p "Press Enter to close… " _
  exit 1
fi

# User-level Applications — no sudo / admin rights required.
APP_DEST="${HOME}/Applications/Eliseus Sorter.app"
mkdir -p "${HOME}/Applications"

echo ""
echo "Installing to: ${APP_DEST}"
rm -rf "${APP_DEST}"
cp -R "${APP_SRC}" "${APP_DEST}"

# Allow opening unsigned/local apps (no admin needed).
xattr -cr "${APP_DEST}" 2>/dev/null || true

echo ""
echo "Done! Open Eliseus Sorter from:"
echo "  Finder → Applications (under your home folder)"
echo "  or Spotlight — search \"Eliseus Sorter\""
echo ""
echo "First launch: click Install in the dialog (one-time, ~10–15 min)."
echo ""
echo "If macOS blocks the app: right-click the app → Open → Open."
echo ""
echo "Settings & logs:"
echo "  ~/Library/Application Support/Eliseus Sorter/"
echo ""
read -r -p "Press Enter to close… " _
