#!/bin/bash
# macOS app entry point (no Terminal window when launched from Applications).
set -euo pipefail

CONTENTS="$(cd "$(dirname "$0")/.." && pwd)"
RESOURCES="${CONTENTS}/Resources"
SUPPORT="${HOME}/Library/Application Support/Eliseus Sorter"
VENV="${SUPPORT}/venv"
LOG_DIR="${SUPPORT}/logs"
INSTALL_LOG="${LOG_DIR}/install.log"
APP_LOG="${LOG_DIR}/app.log"

export ELISEUS_SORTER_APP=1
export ELISEUS_RESOURCES="${RESOURCES}"
export ELISEUS_VENV_DIR="${VENV}"
export ELISEUS_PROJECT_ROOT="${RESOURCES}"

mkdir -p "${LOG_DIR}"

if [[ ! -x "${VENV}/bin/python" ]]; then
  /usr/bin/osascript -e 'display dialog "Eliseus Sorter needs a one-time setup (about 10–15 minutes, requires internet). Your photos stay on this Mac." buttons {"Cancel", "Install"} default button "Install" with title "First Launch"' || exit 1
  /bin/bash "${RESOURCES}/code/install.sh" >> "${INSTALL_LOG}" 2>&1 || {
    /usr/bin/osascript -e "display alert \"Installation failed\" message \"Open ${INSTALL_LOG} for details.\" as critical"
    exit 1
  }
fi

if ! "${VENV}/bin/python" "${RESOURCES}/code/verify_install.py" >> "${APP_LOG}" 2>&1; then
  /usr/bin/osascript -e "display alert \"Eliseus Sorter is not ready\" message \"Run Install from the project folder, or delete ${VENV} and open the app again.\" as critical"
  exit 1
fi

cd "${RESOURCES}/code"
exec "${VENV}/bin/python" gui_app.py >> "${APP_LOG}" 2>&1
