# Shared paths for install and launch scripts.

_CODE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${ELISEUS_SORTER_APP:-}" == "1" && -n "${ELISEUS_PROJECT_ROOT:-}" ]]; then
  PROJECT_ROOT="${ELISEUS_PROJECT_ROOT}"
else
  PROJECT_ROOT="$(cd "${_CODE_DIR}/.." && pwd)"
fi

APP_SUPPORT="${HOME}/Library/Application Support/Eliseus Sorter"
VENV_DIR="${ELISEUS_VENV_DIR:-${APP_SUPPORT}/venv}"

_resolve_repo_root() {
  if [[ -n "${ELISEUS_REPO_ROOT:-}" ]]; then
    printf '%s' "${ELISEUS_REPO_ROOT}"
    return
  fi
  if [[ -f "${APP_SUPPORT}/repo_root" ]]; then
    tr -d '\n' < "${APP_SUPPORT}/repo_root"
    return
  fi
  local candidate
  candidate="$(cd "${_CODE_DIR}/.." && pwd)"
  if [[ -f "${candidate}/installer.command" ]]; then
    printf '%s' "${candidate}"
    return
  fi
  printf '%s' "${candidate}"
}

REPO_ROOT="$(_resolve_repo_root)"
LOG_DIR="${ELISEUS_LOG_DIR:-${REPO_ROOT}/logs}"

if ! mkdir -p "${LOG_DIR}" 2>/dev/null; then
  LOG_DIR="${APP_SUPPORT}/logs"
  mkdir -p "${LOG_DIR}"
fi

INSTALL_LOG="${LOG_DIR}/install.log"
APP_LOG="${LOG_DIR}/app.log"
REQUIREMENTS_FILE="${PROJECT_ROOT}/requirements.txt"
if [[ ! -f "${REQUIREMENTS_FILE}" && -f "${REPO_ROOT}/requirements.txt" ]]; then
  REQUIREMENTS_FILE="${REPO_ROOT}/requirements.txt"
fi

register_repo_root() {
  local root="$1"
  mkdir -p "${APP_SUPPORT}"
  printf '%s\n' "${root}" > "${APP_SUPPORT}/repo_root"
  mkdir -p "${root}/logs" 2>/dev/null || true
}

brew_shellenv() {
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
}
