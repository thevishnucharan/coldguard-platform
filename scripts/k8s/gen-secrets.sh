#!/usr/bin/env bash
# Generate infrastructure/k8s/overlays/local/secrets.env with random values (git-ignored).
#   scripts/k8s/gen-secrets.sh            # only if missing
#   FORCE=1 scripts/k8s/gen-secrets.sh    # overwrite (existing postgres volumes keep the OLD password!)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/infrastructure/k8s/overlays/local/secrets.env"
rand() { head -c 2048 /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9' | cut -c "1-${1:-40}"; }

if [ -f "$OUT" ] && [ "${FORCE:-0}" != "1" ]; then
  echo "secrets.env exists — keeping it ($OUT)"; exit 0
fi
pg=$(rand 24); ing=$(rand 24)
umask 077
cat >"$OUT" <<EOF
# generated $(date -u +%Y-%m-%dT%H:%M:%SZ) by scripts/k8s/gen-secrets.sh — git-ignored, never commit
POSTGRES_USER=coldguard
POSTGRES_PASSWORD=$pg
DATABASE_URL=postgresql://coldguard:$pg@postgres:5432/coldguard
EXPORTER_DSN=postgresql://coldguard:$pg@postgres:5432/coldguard?sslmode=disable
SECRET_KEY=$(rand 64)
INGEST_API_KEY=$(rand 32)
MQTT_PASSWORD=$ing
MQTT_INGESTOR_PASSWORD=$ing
MQTT_DEVICE_PASSWORD=$(rand 24)
GRAFANA_ADMIN_PASSWORD=$(rand 24)
EOF
echo "wrote $OUT"
