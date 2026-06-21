#!/bin/bash
# macOS app entry point (no Terminal window when launched from Applications).
set -euo pipefail

CONTENTS="$(cd "$(dirname "$0")/.." && pwd)"
RESOURCES="${CONTENTS}/Resources"
SUPPORT="${HOME}/Library/Application Support/Eliseus Sorter"
VENV="${SUPPORT}/venv"

export ELISEUS_SORTER_APP=1
export ELISEUS_RESOURCES="${RESOURCES}"
export ELISEUS_VENV_DIR="${VENV}"
export ELISEUS_PROJECT_ROOT="${RESOURCES}"

# shellcheck source=../code/paths.sh
source "${RESOURCES}/code/paths.sh"

mkdir -p "${LOG_DIR}"

show_failure() {
  local title="$1"
  local message="$2"
  /usr/bin/osascript -e "display alert \"${title}\" message \"${message}\" as critical" || true
}

if [[ ! -x "${VENV}/bin/python" ]]; then
  /usr/bin/osascript -e 'display dialog "Eliseus Sorter needs a one-time setup (about 10–15 minutes, internet required). Photos stay on this Mac." buttons {"Cancel", "Install"} default button "Install" with title "Eliseus Sorter — Setup"' || exit 1
  /bin/bash "${RESOURCES}/code/install.sh" >> "${INSTALL_LOG}" 2>&1 || {
    show_failure "Eliseus Sorter — setup failed" "See logs/install.log in the project folder (${REPO_ROOT})."
    exit 1
  }
fi

if ! "${VENV}/bin/python" "${RESOURCES}/code/verify_runtime.py" >> "${APP_LOG}" 2>&1; then
  show_failure "Eliseus Sorter is not ready" "See logs/app.log in the project folder (${REPO_ROOT}). Delete the venv in Application Support and open the app again to re-run setup."
  exit 1
fi

cd "${RESOURCES}/code"
if ! "${VENV}/bin/python" gui_app.py >> "${APP_LOG}" 2>&1; then
  show_failure "Eliseus Sorter quit unexpectedly" "See logs/app.log in the project folder (${REPO_ROOT})."
  exit 1
fi
