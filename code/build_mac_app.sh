#!/usr/bin/env bash
# Build Eliseus Sorter.app for release (production code only).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MACOS_DIR="${PROJECT_ROOT}/macos"
CODE_DEST=""
# shellcheck source=../macos/branding.sh
source "${MACOS_DIR}/branding.sh"

APP_PATH="${HOME}/Applications/${APP_NAME}.app"

# Dev-only modules — not shipped in the .app
DEV_MODULES=(
  benchmark.py
  benchmark_eval.py
  benchmark_metrics.py
  benchmark_pipeline.py
  benchmark_viz.py
  balance_ground_truth.py
  build_test_subset.py
  copy_data_from_drive.py
  build_reference.py
  database.py
  build_mac_app.sh
  main.py
)

info() { printf '\n▸ %s\n' "$1"; }

info "Building ${APP_NAME}.app (${APP_VERSION})"
bash "${MACOS_DIR}/build_icon.sh"

rm -rf "${APP_PATH}"
mkdir -p "${APP_PATH}/Contents/MacOS"
mkdir -p "${APP_PATH}/Contents/Resources/code"

cp "${MACOS_DIR}/Info.plist" "${APP_PATH}/Contents/Info.plist"
cp "${MACOS_DIR}/app_launcher.sh" "${APP_PATH}/Contents/MacOS/eliseus_sorter"
chmod +x "${APP_PATH}/Contents/MacOS/eliseus_sorter"

cp "${MACOS_DIR}/AppIcon.icns" "${APP_PATH}/Contents/Resources/AppIcon.icns"
mkdir -p "${APP_PATH}/Contents/Resources/macos"
cp "${MACOS_DIR}/branding.sh" "${MACOS_DIR}/install_banner.sh" "${APP_PATH}/Contents/Resources/macos/"
cp "${PROJECT_ROOT}/requirements.txt" "${APP_PATH}/Contents/Resources/"

CODE_DEST="${APP_PATH}/Contents/Resources/code"
rsync -a --exclude '__pycache__' --exclude '*.pyc' "${SCRIPT_DIR}/" "${CODE_DEST}/"

for module in "${DEV_MODULES[@]}"; do
  rm -f "${CODE_DEST}/${module}"
done

xattr -cr "${APP_PATH}" 2>/dev/null || true

VENV="${HOME}/Library/Application Support/Eliseus Sorter/venv"
if [[ -x "${VENV}/bin/python" ]]; then
  info "Checking production imports"
  if ! "${VENV}/bin/python" -c "
import sys
sys.path.insert(0, '${CODE_DEST}')
import gui_app  # noqa: F401
print('OK')
"; then
    echo "Production import check failed — a dev-only module may be imported at startup." >&2
    exit 1
  fi
fi

info "Installed to: ${APP_PATH}"
info "Open from Spotlight or Finder → Applications"
