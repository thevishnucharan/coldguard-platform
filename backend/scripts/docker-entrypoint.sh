#!/bin/sh
# ColdGuard container entrypoint.
#   api      -> run migrations (if MIGRATE_ON_START=true), optional demo seed, start uvicorn
#   worker   -> background worker (MQTT ingestion, sweeps, escalation, simulation)
#   migrate  -> run migrations only (Kubernetes Job / init container)
#   seed     -> demo seed only
set -e
cmd="${1:-api}"

migrate() {
  echo "[coldguard] applying database migrations"
  python scripts/migrate.py
}

case "$cmd" in
  api)
    if [ "${MIGRATE_ON_START:-true}" = "true" ]; then migrate; fi
    if [ "${UVICORN_WORKERS:-1}" -gt 1 ]; then
      # aggregate Prometheus metrics across uvicorn worker processes (stale files from a
      # previous container start would double-count, so start clean)
      export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus-multiproc}"
      rm -rf "$PROMETHEUS_MULTIPROC_DIR" && mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
    fi
    if [ "${SEED_DEMO_ON_START:-false}" = "true" ]; then python scripts/seed.py; fi
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips="*" \
         --workers "${UVICORN_WORKERS:-1}"
    ;;
  worker)  exec python -m app.worker ;;
  migrate) migrate ;;
  seed)    exec python scripts/seed.py ;;
  *)       exec "$@" ;;
esac
