#!/bin/bash
# Build the .app and copy it to /Applications.
cd "$(dirname "$0")"
clear
echo "=============================================="
echo "  Install Eliseus Sorter to Applications"
echo "=============================================="
echo ""

bash "./scripts/build_mac_app.sh"
APP="./dist/Eliseus Sorter.app"

if [[ ! -d "$APP" ]]; then
  echo "Build failed — app bundle not found."
  read -r -p "Press Enter to close… " _
  exit 1
fi

echo ""
echo "Copying to /Applications (macOS may ask for your password)…"
sudo cp -R "$APP" /Applications/

echo ""
echo "Done! Open Eliseus Sorter from Launchpad or Applications."
echo ""
echo "Your data will be stored at:"
echo "  ~/Library/Application Support/Eliseus Sorter/data/"
echo ""
read -r -p "Press Enter to close… " _
