#!/bin/bash
# Double-click this file in Finder to open the app (macOS).
cd "$(dirname "$0")"
bash "./code/launch.sh"
STATUS=$?
if [[ ${STATUS} -ne 0 ]]; then
  echo ""
  read -r -p "Press Enter to close… " _
fi
