#!/usr/bin/env bash
# Launch Eliseus Sorter (Applications app by default, or local dev with --local).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=paths.sh
source "${SCRIPT_DIR}/paths.sh"
# shellcheck source=../macos/branding.sh
source "${SCRIPT_DIR}/../macos/branding.sh"

APP_BUNDLE="${HOME}/Applications/${APP_NAME}.app"

if [[ "${1:-}" != "--local" && -d "${APP_BUNDLE}" ]]; then
  exec open "${APP_BUNDLE}"
fi

cd "${SCRIPT_DIR}"

if [[ ! -d "${VENV_DIR}" ]]; then
  echo ""
  echo "Setup is not complete."
  echo "Run installer.command from the project folder (one step — installs everything)."
  echo ""
  exit 1
fi

# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"

if ! python -c "import tkinter" 2>/dev/null; then
  PY_MM="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  echo ""
  echo "Tkinter is not installed for Python ${PY_MM} (the GUI cannot start)."
  echo ""
  echo "Quick fix — run in Terminal:"
  echo "  brew install python-tk@${PY_MM}"
  echo ""
  echo "Then run: bash code/install.sh"
  echo ""
  exit 1
fi

if ! python "${SCRIPT_DIR}/verify_runtime.py"; then
  echo ""
  echo "Installation verification failed."
  echo "Re-run: bash installer.command"
  echo "Details: logs/install.log"
  echo ""
  exit 1
fi

exec python gui_app.py
