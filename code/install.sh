#!/usr/bin/env bash
# One-time setup: Homebrew (if needed), Python 3.10+, venv, and all pip packages.
set -euo pipefail

unset ELISEUS_SORTER_APP ELISEUS_PROJECT_ROOT || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=paths.sh
source "${SCRIPT_DIR}/paths.sh"
LOG_FILE="${INSTALL_LOG}"
PYTHON="${PYTHON:-}"
VERIFY_SCRIPT="${SCRIPT_DIR}/verify_install.py"

mkdir -p "${LOG_DIR}"
register_repo_root "${REPO_ROOT}"

info()  { printf '\n\033[1;34m▸ %s\033[0m\n' "$1"; }
ok()    { printf '  \033[1;32m✓ %s\033[0m\n' "$1"; }
warn()  { printf '  \033[1;33m! %s\033[0m\n' "$1"; }
fail()  { printf '\n\033[1;31m✗ %s\033[0m\n' "$1" >&2; exit 1; }

exec > >(tee -a "${LOG_FILE}") 2>&1

cd "${REPO_ROOT}"

# shellcheck source=../macos/branding.sh
source "${REPO_ROOT}/macos/branding.sh"
# shellcheck source=../macos/install_banner.sh
source "${REPO_ROOT}/macos/install_banner.sh"

python_version_ok() {
  local exe="$1"
  command -v "${exe}" >/dev/null 2>&1 || return 1
  "${exe}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null
}

python_version_label() {
  local exe="$1"
  "${exe}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
}

ensure_homebrew() {
  brew_shellenv
  if command -v brew >/dev/null 2>&1; then
    ok "Homebrew ready"
    return 0
  fi

  info "Installing Homebrew"
  echo "  Your Mac may ask for your password once (required by Homebrew)."
  echo "  This can take a few minutes."
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  brew_shellenv

  if ! command -v brew >/dev/null 2>&1; then
    fail "Homebrew installation did not finish. Run installer.command again after installing Homebrew from https://brew.sh"
  fi
  ok "Homebrew installed"
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
    /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12
    /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11
    /Library/Frameworks/Python.framework/Versions/3.10/bin/python3.10
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
  ensure_homebrew

  info "Installing Python 3.12 and Tkinter with Homebrew"
  echo "  macOS system Python is too old for this app."
  brew install python@3.12 python-tk@3.12

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

  warn "Python 3.10+ not found — installing with Homebrew."
  if found="$(install_python_with_homebrew)"; then
    echo "${found}"
    return 0
  fi

  local system_version="unknown"
  if command -v python3 >/dev/null 2>&1; then
    system_version="$(python_version_label python3)"
  fi

  fail "Could not install Python 3.10+ (system python3 is ${system_version}).

Try running installer.command again, or install Python 3.12 from:
  https://www.python.org/downloads/macos/

Then run: bash installer.command"
}

info "${APP_NAME} — full setup"
print_banner "Setup"
echo "  Project folder: ${REPO_ROOT}"
echo "  Log file:       ${LOG_FILE}"
echo "  Python env:     ${VENV_DIR}"

ensure_homebrew

if ! xcode-select -p >/dev/null 2>&1; then
  warn "Xcode Command Line Tools are required."
  echo "  Click Install in the macOS dialog, wait for it to finish,"
  echo "  then run installer.command again."
  xcode-select --install 2>/dev/null || true
  fail "Install Command Line Tools, then re-run installer.command."
fi
ok "Xcode Command Line Tools"

PYTHON="$(resolve_python)"
PY_VERSION="$(python_version_label "${PYTHON}")"
ok "Python ${PY_VERSION} (${PYTHON})"

if [[ "${REPO_ROOT}" == *"CloudStorage"* ]] || [[ "${REPO_ROOT}" == *"Google Drive"* ]]; then
  warn "Project is on Google Drive — Python packages stay in Application Support."
  if [[ -d "${REPO_ROOT}/.venv" ]]; then
    warn "Removing old .venv inside Google Drive."
    rm -rf "${REPO_ROOT}/.venv"
  fi
fi

info "Creating virtual environment"
if [[ -d "${VENV_DIR}" ]]; then
  if ! "${VENV_DIR}/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    warn "Removing old venv (Python < 3.10)"
    rm -rf "${VENV_DIR}"
  fi
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  "${PYTHON}" -m venv --copies "${VENV_DIR}"
  ok "Created venv with Python ${PY_VERSION}"
else
  ok "Using existing venv"
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

  warn "Tkinter missing — installing via Homebrew."
  local py_mm
  py_mm="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

  ensure_homebrew
  brew install "python-tk@${py_mm}" || true
  if python -c "import tkinter" 2>/dev/null; then
    ok "Tkinter installed"
    return 0
  fi

  fail "Tkinter is not available for Python ${py_mm}.

Re-run installer.command, or install Python from https://www.python.org/downloads/macos/ (includes Tk)."
}

ensure_tkinter

info "Installing Python packages (numpy, opencv, insightface, GUI…)"
if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
  fail "requirements.txt not found at ${REQUIREMENTS_FILE}"
fi
python -m pip install -r "${REQUIREMENTS_FILE}"
ok "Python packages installed"

info "Verifying installation"
if ! python "${VERIFY_SCRIPT}"; then
  fail "Verification failed. See ${LOG_FILE}"
fi
ok "Verification passed"

cat <<EOF

$(printf '\033[1;32mSetup complete!\033[0m')

Python environment: ${VENV_DIR}
Log saved to: ${LOG_FILE}

EOF
