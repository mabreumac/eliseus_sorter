# Shared paths for install and launch scripts.

if [[ -n "${ELISEUS_PROJECT_ROOT:-}" ]]; then
  PROJECT_ROOT="${ELISEUS_PROJECT_ROOT}"
else
  PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

VENV_DIR="${ELISEUS_VENV_DIR:-${HOME}/.eliseus_sorter/venv}"
