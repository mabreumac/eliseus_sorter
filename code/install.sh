#!/usr/bin/env bash
# One-time setup: virtual environment + Python dependencies (macOS).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=paths.sh
source "${SCRIPT_DIR}/paths.sh"
LOG_FILE="${PROJECT_ROOT}/install.log"
PYTHON="${PYTHON:-}"

info()  { printf '\n\033[1;34m▸ %s\033[0m\n' "$1"; }
ok()    { printf '  \033[1;32m✓ %s\033[0m\n' "$1"; }
warn()  { printf '  \033[1;33m! %s\033[0m\n' "$1"; }
fail()  { printf '\n\033[1;31m✗ %s\033[0m\n' "$1" >&2; exit 1; }

exec > >(tee -a "${LOG_FILE}") 2>&1

cd "${PROJECT_ROOT}"

# shellcheck source=../macos/branding.sh
source "${PROJECT_ROOT}/macos/branding.sh"
# shellcheck source=../macos/install_banner.sh
source "${PROJECT_ROOT}/macos/install_banner.sh"

python_version_ok() {
  local exe="$1"
  command -v "${exe}" >/dev/null 2>&1 || return 1
  "${exe}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null
}

python_version_label() {
  local exe="$1"
  "${exe}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
}

find_suitable_python() {
  local candidate

  if [[ -n "${PYTHON}" ]]; then
    if python_version_ok "${PYTHON}"; then
      echo "${PYTHON}"
      return 0
    fi
    warn "PYTHON=${PYTHON} is set but is older than 3.10 — searching for another…"
  fi

  local -a candidates=(
    python3.12 python3.11 python3.10
    /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 /opt/homebrew/bin/python3.10
    /usr/local/bin/python3.12 /usr/local/bin/python3.11 /usr/local/bin/python3.10
    python3
  )

  for candidate in "${candidates[@]}"; do
    if python_version_ok "${candidate}"; then
      echo "${candidate}"
      return 0
    fi
  done

  return 1
}

install_python_with_homebrew() {
  if ! command -v brew >/dev/null 2>&1; then
    return 1
  fi

  info "Installing Python 3.12 with Homebrew (one-time)"
  echo "  macOS ships with Python 3.9, which is too old for this app."
  echo "  This step downloads a newer Python — it may take a few minutes."
  brew install python@3.12

  local brew_python
  brew_python="$(brew --prefix python@3.12)/bin/python3.12"
  if python_version_ok "${brew_python}"; then
    echo "${brew_python}"
    return 0
  fi
  return 1
}

resolve_python() {
  local found

  if found="$(find_suitable_python)"; then
    echo "${found}"
    return 0
  fi

  warn "Python 3.10+ not found on this Mac."
  if found="$(install_python_with_homebrew)"; then
    echo "${found}"
    return 0
  fi

  local system_version="unknown"
  if command -v python3 >/dev/null 2>&1; then
    system_version="$(python_version_label python3)"
  fi

  fail "Python 3.10 or newer is required (your python3 is ${system_version}).

Easiest fix — install Homebrew, then run Install again:
  https://brew.sh

Or install Python manually:
  1. Open https://www.python.org/downloads/macos/
  2. Download Python 3.12 (or newer)
  3. Run the installer
  4. Run  bash code/install.sh  again

Advanced (if Homebrew is already installed):
  brew install python@3.12
  bash code/install.sh"
}

info "${APP_NAME} — one-time setup"
print_banner "Setup"
echo "  Project folder: ${PROJECT_ROOT}"
echo "  Log file:       ${LOG_FILE}"

PYTHON="$(resolve_python)"
PY_VERSION="$(python_version_label "${PYTHON}")"
ok "Python ${PY_VERSION} (${PYTHON})"

if ! xcode-select -p >/dev/null 2>&1; then
  warn "Xcode Command Line Tools are not installed yet."
  echo "  A system dialog may appear — click Install and wait for it to finish."
  echo "  Then run this installer again."
  xcode-select --install 2>/dev/null || true
  fail "Please install Command Line Tools, then re-run Install."
fi
ok "Xcode Command Line Tools"

if [[ "${PROJECT_ROOT}" == *"CloudStorage"* ]] || [[ "${PROJECT_ROOT}" == *"Google Drive"* ]]; then
  warn "Project is on Google Drive."
  echo "  Python packages will be stored locally at: ${VENV_DIR}"
  if [[ -d "${PROJECT_ROOT}/.venv" ]]; then
    warn "Removing old .venv inside Google Drive (causes install errors)."
    rm -rf "${PROJECT_ROOT}/.venv"
  fi
fi

info "Creating virtual environment"
if [[ -d "${VENV_DIR}" ]]; then
  if ! "${VENV_DIR}/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    warn "Removing old .venv (built with Python < 3.10)"
    rm -rf "${VENV_DIR}"
  fi
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  "${PYTHON}" -m venv --copies "${VENV_DIR}"
  ok "Created .venv with Python ${PY_VERSION}"
else
  ok "Using existing .venv"
fi

# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip setuptools wheel
ok "pip ready"

ensure_tkinter() {
  if python -c "import tkinter" 2>/dev/null; then
    ok "Tkinter (GUI) ready"
    return 0
  fi

  warn "Tkinter is missing — required for the desktop window."
  local py_mm
  py_mm="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

  if command -v brew >/dev/null 2>&1; then
    echo "  Installing python-tk@${py_mm} via Homebrew…"
    if brew install "python-tk@${py_mm}"; then
      if python -c "import tkinter" 2>/dev/null; then
        ok "Tkinter installed"
        return 0
      fi
    fi
  fi

  fail "Tkinter is not available for Python ${py_mm}.

Homebrew Python needs a separate Tk package. In Terminal, run:
  brew install python-tk@${py_mm}

Then run: bash code/install.sh

Or install Python from https://www.python.org/downloads/macos/ (includes Tk)
and run  bash code/install.sh  again."
}

ensure_tkinter

install_insightface() {
  info "Installing InsightFace stack (ONNX models download on first run)"

  if python -c "import insightface, onnxruntime, cv2" 2>/dev/null; then
    ok "InsightFace packages present"
  fi
}

install_insightface

info "Installing remaining packages"
python -m pip install -r "${PROJECT_ROOT}/requirements.txt"
ok "Python packages installed"

info "Verifying installation"
if ! python "${PROJECT_ROOT}/code/verify_install.py"; then
  fail "Installation verification failed. See messages above and install.log"
fi
ok "Verification passed"

cat <<EOF

$(printf '\033[1;32mInstallation complete!\033[0m')

Python environment: ${VENV_DIR}
Log saved to: ${LOG_FILE}

EOF
