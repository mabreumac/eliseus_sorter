#!/bin/bash
# Double-click this file in Finder to install (macOS).
cd "$(dirname "$0")"
clear
echo "=============================================="
echo "  Eliseus Sorter — Install"
echo "=============================================="
echo ""
bash "./scripts/install.sh"
STATUS=$?
echo ""
if [[ ${STATUS} -eq 0 ]]; then
  echo "You can close this window."
else
  echo "Installation did not finish. Read the messages above."
fi
echo ""
read -r -p "Press Enter to close… " _
