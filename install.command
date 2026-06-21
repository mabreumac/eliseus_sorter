#!/bin/bash
# Double-click this file in Finder to install (macOS).
cd "$(dirname "$0")"
# Remove quarantine flag so macOS allows running (no admin needed).
xattr -cr "$(pwd)" 2>/dev/null || true
clear
echo "=============================================="
echo "  Eliseus Sorter — Install"
echo "=============================================="
echo ""
bash "./code/install.sh"
STATUS=$?
echo ""
if [[ ${STATUS} -eq 0 ]]; then
  echo "You can close this window."
else
  echo "Installation did not finish."
  echo ""
  echo "If Python 3.9 was the problem, install Homebrew (https://brew.sh)"
  echo "or Python 3.12 from https://www.python.org/downloads/macos/"
  echo "then run Install again."
  echo ""
  echo "Full details: install.log"
fi
echo ""
read -r -p "Press Enter to close… " _
