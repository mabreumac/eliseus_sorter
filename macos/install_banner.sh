#!/usr/bin/env bash
# Shared installer banner (source after branding.sh).
print_banner() {
  local title="${1:-${APP_NAME}}"
  printf '\n'
  printf '  ╭──────────────────────────────────────────╮\n'
  printf '  │  %-40s│\n' "${title}"
  if [[ -n "${APP_TAGLINE:-}" ]]; then
    printf '  │  %-40s│\n' "${APP_TAGLINE}"
  fi
  printf '  ╰──────────────────────────────────────────╯\n'
  printf '\n'
}
