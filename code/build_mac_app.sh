#!/usr/bin/env bash
# Build Eliseus Sorter.app for macOS (drag to Applications).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
APP_NAME="Eliseus Sorter"
DIST_DIR="${PROJECT_ROOT}/dist"
APP_PATH="${DIST_DIR}/${APP_NAME}.app"

info() { printf '\n▸ %s\n' "$1"; }

info "Building ${APP_NAME}.app"
rm -rf "${APP_PATH}"
mkdir -p "${APP_PATH}/Contents/MacOS"
mkdir -p "${APP_PATH}/Contents/Resources"

cp "${PROJECT_ROOT}/macos/Info.plist" "${APP_PATH}/Contents/Info.plist"
cp "${PROJECT_ROOT}/macos/app_launcher.sh" "${APP_PATH}/Contents/MacOS/eliseus_sorter"
chmod +x "${APP_PATH}/Contents/MacOS/eliseus_sorter"

cp -R "${PROJECT_ROOT}/code" "${APP_PATH}/Contents/Resources/"
cp "${PROJECT_ROOT}/requirements.txt" "${APP_PATH}/Contents/Resources/"

# Placeholder for a custom icon later (optional).
touch "${APP_PATH}/Contents/Resources/.keep"

# Allow opening unsigned/local apps (no admin needed).
xattr -cr "${APP_PATH}" 2>/dev/null || true

info "Created: ${APP_PATH}"
info "Next: double-click 'Install to Applications.command' or drag the app to /Applications"
