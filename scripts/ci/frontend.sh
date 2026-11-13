#!/usr/bin/env bash
# Phase: frontend install, lint, type-check, unit tests (JUnit) and production build.
source "$(dirname "$0")/lib.sh"
cd "$ROOT/frontend"
# Windows (Git Bash): vitest fails to locate its runner when the drive letter is lowercase,
# because module ids are then compared case-sensitively. Use the canonical C:/... spelling.
if command -v cygpath >/dev/null 2>&1; then
  win=$(cygpath -m "$PWD")
  cd "$(printf '%s' "${win:0:1}" | tr '[:lower:]' '[:upper:]')${win:1}"
fi

if [ "${CI:-}" = "true" ] || [ ! -d node_modules ]; then
  log "npm ci"
  npm ci --no-audit --no-fund
fi
log "lint (oxlint)";   npm run lint --silent
log "unit tests";      npm test -- --reporter=default --reporter=junit --outputFile.junit="$REPORTS/frontend-tests.xml"
log "build";           npm run build --silent
ok "frontend built ($(du -sh dist | cut -f1))"
