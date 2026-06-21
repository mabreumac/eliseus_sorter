#!/bin/bash
# Double-click to install Eliseus Sorter — one step: dependencies + app.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "${ROOT}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Eliseus Sorter requires macOS." >&2
  exit 1
fi

xattr -cr "${ROOT}" 2>/dev/null || true

# shellcheck source=macos/branding.sh
source "${ROOT}/macos/branding.sh"
# shellcheck source=macos/install_banner.sh
source "${ROOT}/macos/install_banner.sh"
# shellcheck source=code/paths.sh
source "${ROOT}/code/paths.sh"

clear
print_banner "Install Eliseus Sorter"
echo "  One step: Python libraries + app to ~/Applications"
echo "  Takes about 10–15 minutes (internet required)"
echo "  Photos stay on your Mac — nothing is uploaded"
echo "  Logs: ${LOG_DIR}/install.log"
echo ""

if ! /usr/bin/osascript -e 'display dialog "Install Eliseus Sorter now?\n\nThis will install Homebrew and Python if needed, then all libraries and the app (~10–15 min, internet required)." buttons {"Cancel", "Install"} default button "Install" with title "Eliseus Sorter"' >/dev/null 2>&1; then
  echo "Installation cancelled."
  exit 1
fi

register_repo_root "${ROOT}"
mkdir -p "${LOG_DIR}"

echo ""
echo "▸ Step 1/2 — Python environment and libraries"
echo ""
bash "${ROOT}/code/install.sh"

echo ""
echo "▸ Step 2/2 — Building Eliseus Sorter.app"
echo ""
bash "${ROOT}/code/build_mac_app.sh"

APP_DEST="${HOME}/Applications/${APP_NAME}.app"

if [[ ! -d "${APP_DEST}" ]]; then
  echo "Build failed — app not found in Applications." >&2
  read -r -p "Press Enter to close… " _
  exit 1
fi

if [[ -d "${ROOT}/dist" ]]; then
  rm -rf "${ROOT}/dist"
fi

echo ""
echo "Done — everything is installed."
echo ""
echo "  Open Eliseus Sorter from Spotlight or Applications"
echo "  No extra setup on first launch"
echo ""
echo "  If macOS blocks the app: right-click → Open → Open"
echo "  Logs: ${LOG_DIR}/"
echo ""
read -r -p "Press Enter to close… " _
