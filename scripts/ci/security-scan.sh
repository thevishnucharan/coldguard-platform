#!/usr/bin/env bash
# Phase: secrets hygiene + dependency audit.
#  * no env/secret files or private keys are tracked by git
#  * the production frontend bundle contains no backend secrets or credential names
#  * dependency audits (reported; gating only with STRICT_AUDIT=1)
source "$(dirname "$0")/lib.sh"
cd "$ROOT"

log "tracked files: no secret files"
bad=$(git ls-files | grep -E '(^|/)(\.env|secrets\.env|.*\.pem|.*\.key|id_rsa.*)$' || true)
[ -z "$bad" ] || fail "secret-bearing files are tracked: $bad"
ok "no .env / secrets.env / key files tracked"

log "tracked files: no private keys or cloud credentials"
hits=$(git grep -nIE -e '-----BEGIN ([A-Z]+ )?PRIVATE KEY-----' -e 'AKIA[0-9A-Z]{16}' -e 'xox[baprs]-[0-9A-Za-z-]{10,}' \
       -e 'ghp_[0-9A-Za-z]{36}' -- . ':!scripts/ci/security-scan.sh' || true)
[ -z "$hits" ] || fail "possible credentials committed:\n$hits"
ok "no private keys / cloud tokens in tracked files"

log "kubernetes manifests: secrets only via secretKeyRef / generator"
if grep -rnE '^\s*kind:\s*Secret\b' infrastructure/k8s --include=*.yaml; then fail "literal Secret manifest found"; fi
if grep -rnE '(PASSWORD|SECRET_KEY|API_KEY)\s*[:=]\s*["'"'"']?[A-Za-z0-9]{8,}' infrastructure/k8s --include=*.yaml; then
  fail "credential-like literal in a manifest"
fi
ok "no literal secrets in manifests"

if [ -d frontend/dist ]; then
  log "frontend bundle: no backend secrets"
  if grep -rlE 'SECRET_KEY|POSTGRES_PASSWORD|DATABASE_URL|INGEST_API_KEY|MQTT_(INGESTOR|DEVICE)_PASSWORD|GRAFANA_ADMIN_PASSWORD' frontend/dist; then
    fail "frontend bundle references backend secret names"
  fi
  if [ -f .env ]; then
    while IFS='=' read -r k v; do
      case "$k" in SECRET_KEY|POSTGRES_PASSWORD|INGEST_API_KEY|MQTT_INGESTOR_PASSWORD|MQTT_DEVICE_PASSWORD|GRAFANA_ADMIN_PASSWORD) ;;
        *) continue ;; esac
      v=${v%$'\r'}
      [ ${#v} -ge 8 ] && grep -rqF -- "$v" frontend/dist && fail "value of $k found in frontend bundle"
    done < .env
  fi
  ok "frontend bundle clean"
fi

log "dependency audit"
rc=0
(cd frontend && npm audit --omit=dev --audit-level=high) || rc=$?
if [ -n "${PYTHON_BIN:-}" ] && "$PYTHON_BIN" -m pip_audit --version >/dev/null 2>&1; then
  "$PYTHON_BIN" -m pip_audit -r backend/requirements.txt || rc=$?
else
  echo "pip-audit not installed — skipped (pip install pip-audit)"
fi
if [ "$rc" -ne 0 ]; then
  [ "${STRICT_AUDIT:-0}" = "1" ] && fail "dependency audit reported vulnerabilities"
  echo "dependency audit reported findings (non-gating; set STRICT_AUDIT=1 to gate)"
fi
ok "security scan complete"
