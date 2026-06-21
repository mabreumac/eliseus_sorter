#!/bin/bash
# Double-click to install Eliseus Sorter.app to ~/Applications.
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

clear
print_banner "Install Eliseus Sorter"
echo "  Installs to ~/Applications"
echo "  First launch installs Python libraries (~10–15 min, one time)"
echo "  Photos stay on your Mac — nothing is uploaded"
echo ""

bash "${ROOT}/code/build_mac_app.sh"
APP_DEST="${HOME}/Applications/${APP_NAME}.app"

# shellcheck source=code/paths.sh
source "${ROOT}/code/paths.sh"
register_repo_root "${ROOT}"
echo "  Logs: ${LOG_DIR}"

if [[ ! -d "${APP_DEST}" ]]; then
  echo "Build failed — app not found in Applications." >&2
  read -r -p "Press Enter to close… " _
  exit 1
fi

if [[ -d "${ROOT}/dist" ]]; then
  rm -rf "${ROOT}/dist"
fi

echo ""
echo "Done."
echo ""
echo "  Open from Spotlight or Finder → Applications"
echo "  First launch: click Install when prompted"
echo ""
echo "  If macOS blocks the app: right-click → Open → Open"
echo ""
read -r -p "Press Enter to close… " _
