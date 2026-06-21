#!/usr/bin/env bash
# One-time setup: virtual environment + Python dependencies (macOS).
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"
PYTHON="${PYTHON:-python3}"

info()  { printf '\n\033[1;34m▸ %s\033[0m\n' "$1"; }
ok()    { printf '  \033[1;32m✓ %s\033[0m\n' "$1"; }
warn()  { printf '  \033[1;33m! %s\033[0m\n' "$1"; }
fail()  { printf '\n\033[1;31m✗ %s\033[0m\n' "$1" >&2; exit 1; }

cd "${PROJECT_ROOT}"

info "Eliseus Sorter — installation"
echo "  Project folder: ${PROJECT_ROOT}"

if ! command -v "${PYTHON}" >/dev/null 2>&1; then
  fail "Python 3 was not found.

Install it using one of these options:
  • macOS will offer Command Line Tools when needed — accept that dialog.
  • Or install from https://www.python.org/downloads/macos/
  • Or run: xcode-select --install"
fi

PY_VERSION="$("${PYTHON}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_MAJOR="${PY_VERSION%%.*}"
PY_MINOR="${PY_VERSION#*.}"
if [[ "${PY_MAJOR}" -lt 3 ]] || [[ "${PY_MAJOR}" -eq 3 && "${PY_MINOR}" -lt 10 ]]; then
  fail "Python 3.10 or newer is required (found ${PY_VERSION})."
fi
ok "Python ${PY_VERSION}"

if ! xcode-select -p >/dev/null 2>&1; then
  warn "Xcode Command Line Tools are not installed yet."
  echo "  A system dialog may appear — click Install and wait for it to finish."
  echo "  Then run this installer again."
  xcode-select --install 2>/dev/null || true
  fail "Please install Command Line Tools, then re-run Install."
fi
ok "Xcode Command Line Tools"

info "Creating virtual environment"
if [[ ! -d "${VENV_DIR}" ]]; then
  "${PYTHON}" -m venv "${VENV_DIR}"
  ok "Created .venv"
else
  ok "Using existing .venv"
fi

# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip setuptools wheel >/dev/null
ok "pip ready"

install_dlib() {
  info "Installing face recognition libraries (this may take several minutes)"
  if python -m pip install dlib; then
    ok "dlib installed"
    return 0
  fi

  warn "dlib did not install on the first try."

  if command -v brew >/dev/null 2>&1; then
    echo "  Trying Homebrew cmake helper…"
    brew install cmake
    python -m pip install dlib
    ok "dlib installed (with Homebrew cmake)"
    return 0
  fi

  fail "Could not install dlib automatically.

Try installing Homebrew (https://brew.sh), then run Install again:
  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"

Or ask for help and mention your macOS version and Python version (${PY_VERSION})."
}

install_dlib

info "Installing remaining packages"
python -m pip install -r "${PROJECT_ROOT}/requirements.txt"
ok "All packages installed"

info "Verifying installation"
python "${PROJECT_ROOT}/scripts/verify_install.py"
ok "Verification passed"

cat <<EOF

$(printf '\033[1;32mInstallation complete!\033[0m')

Next step:
  Double-click  \033[1mEliseus Sorter.command\033[0m  in this folder.

Put your photos here:
  data/ground_truth/<student_name>/*.jpg
  data/test_subset/*.jpg

EOF
