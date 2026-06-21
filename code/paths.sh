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
INSTALL_LOG="${LOG_DIR}/install.log"
APP_LOG="${LOG_DIR}/app.log"

register_repo_root() {
  local root="$1"
  mkdir -p "${APP_SUPPORT}"
  printf '%s\n' "${root}" > "${APP_SUPPORT}/repo_root"
  mkdir -p "${root}/logs"
}
