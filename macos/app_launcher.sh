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
  show_failure "Eliseus Sorter — setup required" "Run installer.command from the project folder once (installs everything in a single step). See logs/install.log at: ${REPO_ROOT}"
  exit 1
fi

if ! "${VENV}/bin/python" "${RESOURCES}/code/verify_runtime.py" >> "${APP_LOG}" 2>&1; then
  show_failure "Eliseus Sorter is not ready" "Re-run installer.command from the project folder. Log: ${LOG_DIR}/app.log"
  exit 1
fi

cd "${RESOURCES}/code"
if ! "${VENV}/bin/python" gui_app.py >> "${APP_LOG}" 2>&1; then
  show_failure "Eliseus Sorter quit unexpectedly" "See ${LOG_DIR}/app.log"
  exit 1
fi
