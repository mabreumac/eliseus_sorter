#!/usr/bin/env bash
# Launch the desktop app (macOS).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=paths.sh
source "${SCRIPT_DIR}/paths.sh"
cd "${SCRIPT_DIR}"

if [[ ! -d "${VENV_DIR}" ]]; then
  echo ""
  echo "This app is not installed yet."
  echo "Please double-click  Install.command  first."
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
  echo "Then double-click  Install.command  again."
  echo ""
  exit 1
fi

if ! python "${SCRIPT_DIR}/verify_install.py"; then
  echo ""
  echo "Installation verification failed."
  echo "Please run  Install.command  again."
  echo "Details: install.log"
  echo ""
  exit 1
fi

exec python gui_app.py
