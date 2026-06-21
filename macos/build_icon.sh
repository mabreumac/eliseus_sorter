#!/usr/bin/env bash
# Build AppIcon.icns from a square full-bleed macos/AppIcon.png.
set -euo pipefail

MACOS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="${MACOS_DIR}/AppIcon.png"
ICONSET="${MACOS_DIR}/AppIcon.iconset"
OUTPUT="${MACOS_DIR}/AppIcon.icns"
GENERATE="${MACOS_DIR}/generate_icon.py"

# Regenerate vector-style icon (1024×1024, no side padding).
if [[ -f "${GENERATE}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    python3 "${GENERATE}" 2>/dev/null || true
  fi
fi

if [[ ! -f "${SOURCE}" ]]; then
  echo "Missing ${SOURCE}" >&2
  exit 1
fi

# Enforce square — crop/pad mistakes from old assets.
read -r width height < <(sips -g pixelWidth -g pixelHeight "${SOURCE}" 2>/dev/null | awk '/pixel/{print $2}' | paste - -)
if [[ "${width}" != "${height}" ]]; then
  side=$(( width < height ? width : height ))
  offset_x=$(( (width - side) / 2 ))
  offset_y=$(( (height - side) / 2 ))
  sips -c "${side}" "${side}" "${SOURCE}" --cropOffset "${offset_x}" "${offset_y}" --out "${SOURCE}" >/dev/null
  if [[ "${side}" -ne 1024 ]]; then
    sips -z 1024 1024 "${SOURCE}" --out "${SOURCE}" >/dev/null
  fi
fi

rm -rf "${ICONSET}"
mkdir -p "${ICONSET}"

declare -a SIZES=(16 32 128 256 512)
for size in "${SIZES[@]}"; do
  sips -z "${size}" "${size}" "${SOURCE}" --out "${ICONSET}/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "${double}" "${double}" "${SOURCE}" --out "${ICONSET}/icon_${size}x${size}@2x.png" >/dev/null
done

rm -f "${OUTPUT}"
iconutil -c icns "${ICONSET}" -o "${OUTPUT}"
rm -rf "${ICONSET}"

echo "Built ${OUTPUT}"
