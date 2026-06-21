#!/usr/bin/env bash
# Launch the desktop app (macOS).
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"
APP_PY="${PROJECT_ROOT}/code/gui_app.py"

cd "${PROJECT_ROOT}"

if [[ ! -d "${VENV_DIR}" ]]; then
  echo ""
  echo "This app is not installed yet."
  echo "Please double-click  Install.command  first."
  echo ""
  exit 1
fi

# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"

if ! python "${PROJECT_ROOT}/scripts/verify_install.py" >/dev/null 2>&1; then
  echo ""
  echo "Something is wrong with the installation."
  echo "Please run  Install.command  again."
  echo ""
  exit 1
fi

exec python "${APP_PY}"
