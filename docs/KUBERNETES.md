# Kubernetes deployment

Kustomize manifests live in `infrastructure/k8s`. Both Docker Compose and Kubernetes are kept in
sync and tested by CI (`scripts/ci/config-check.sh`, `compose-smoke.sh`, `k8s-deploy.sh`,
`k8s-smoke.sh`).

```
infrastructure/k8s/
  base/                     everything an environment needs, no secrets
    namespace.yaml          namespace coldguard
    data.yaml               PostgreSQL StatefulSet + PVC, Redis + PVC, Mosquitto + PVC
    app.yaml                migrate Job, API Deployment + HPA + PDB, worker, frontend + HPA + PDB, Ingress
    monitoring.yaml         Prometheus (+PVC, RBAC), Grafana (+PVC), kube-state-metrics, postgres/redis exporters
    network-policies.yaml   default-deny ingress + explicit allow rules
    config/                 ConfigMap sources (Prometheus, alerts, Grafana, Mosquitto)
  overlays/local/           kind/minikube: demo mode, 1 replica, local images, secrets.env (git-ignored)
  overlays/production/      registry images, TLS ingress, production config, secrets from an external store
  kind/kind-config.yaml     single-node kind cluster, host port 8088 -> ingress controller :80
  kind/traefik.yaml         fallback ingress controller for kind when registry.k8s.io is unreachable
```

## What runs where

| Component | Kind | Replicas / scaling | Probes | Storage |
|---|---|---|---|---|
| frontend (nginx + SPA) | Deployment, Service :80 | HPA 2–4 (CPU 75 %), PDB | liveness + readiness `/healthz`, preStop drain | — |
| backend (FastAPI) | Deployment, Service :8000 | HPA 2–6 (CPU 70 %), PDB, spread across nodes | startup/liveness `/health`, readiness `/ready` (DB check), preStop drain | — |
| worker (MQTT ingest, schedules, simulation) | Deployment (Recreate), Service :9101 | exactly 1 | liveness + readiness `/metrics` | — |
| coldguard-migrate | Job (backoffLimit 6) | runs migrations + demo seed | — | — |
| PostgreSQL 16 | StatefulSet, headless Service | 1 | `pg_isready` | `volumeClaimTemplates` 5 Gi (1 Gi local, 20 Gi prod) |
| Redis 7 (pub/sub, rate limits) | Deployment | 1 | `redis-cli ping` / TCP | PVC 1 Gi (AOF) |
| Mosquitto 2 (MQTT) | Deployment (Recreate) | 1 | TCP 1883 | PVC 256 Mi (persistence) |
| Prometheus 3 | Deployment (Recreate) | 1 | `/-/ready`, `/-/healthy` | PVC 5 Gi, 7 d retention |
| Grafana 11 | Deployment (Recreate) | 1 | `/api/health` | PVC 1 Gi |
| kube-state-metrics, postgres/redis exporters | Deployment | 1 | HTTP | — |

**ML:** the anomaly detector (IsolationForest) and the route ETA model (gradient boosting) are
small `joblib` files inside the backend image. They run in the API/worker processes, so there is
no separate ML service to deploy or scale; they scale with the backend HPA.

* **Resources:** every container has requests and limits.
* **Restart handling:** liveness probes restart hung containers; `restartPolicy: Always`; Job
  `backoffLimit`; PDBs keep at least one API/UI pod during node drains. API and worker init
  containers wait for the migration Job, so a fresh rollout never serves an old schema.
* **Rolling updates:** API/UI use `maxUnavailable: 0, maxSurge: 1` plus a `preStop` sleep, so
  endpoints stop routing before shutdown. Singletons that own a volume or the MQTT session use
  `Recreate`. `revisionHistoryLimit: 5` allows `kubectl rollout undo`.
* **Service discovery:** cluster DNS names (`postgres`, `redis`, `mosquitto`, `backend`) come from
  the `coldguard-config` ConfigMap and nginx `proxy_pass http://backend:8000`. Prometheus discovers
  API/worker **pods** individually, because scraping a load-balanced Service would mix counters
  from different replicas.
* **Autoscaling:** HPAs scale on sustained CPU (60 s scale-up window, at most +2 pods/min, 5 min
  scale-down window), so a new pod's start-up burst does not trigger scale-out. The local overlay
  caps them at 2 replicas, which is what a single-node laptop cluster can hold.
* **Pod Security:** the namespace **enforces** the `restricted` Pod Security Standard. Every
  workload, including Postgres (uid 70), Mosquitto (uid 1883), Redis and the migration Job, runs
  non-root with RuntimeDefault seccomp, no privilege escalation and all capabilities dropped.
* **Isolation:** default-deny ingress. Only the frontend and MQTT accept external traffic. The
  backend accepts traffic from the frontend and Prometheus. The data tier accepts the app tier,
  the migration Job and monitoring. Only Prometheus and kube-state-metrics mount a
  service-account token. All app pods run as non-root, drop all capabilities, use
  `RuntimeDefault` seccomp and disallow privilege escalation.
* **Configuration per environment:** `coldguard-config` is merged per overlay (ENVIRONMENT,
  DEMO_MODE, CORS, LOG_LEVEL). The backend refuses to start in staging/production with a weak
  `SECRET_KEY`, demo mode, or non-https CORS origins.

## Secrets

No secret values are in YAML. `coldguard-secrets` is referenced through `secretKeyRef` / `envFrom`.

* **local:** `secretGenerator` reads `overlays/local/secrets.env`. It is git-ignored; generate it
  with random values using `bash scripts/k8s/gen-secrets.sh`.
* **production:** create the Secret from your secret store (External Secrets Operator, Sealed
  Secrets, or CI from a vault), e.g. `kubectl -n coldguard create secret generic coldguard-secrets --from-env-file=…`.
  The keys are the same as `secrets.env.example`.

`scripts/ci/security-scan.sh` fails the build if a `kind: Secret` or a credential-like literal
appears in the manifests, or if a secrets file is tracked by git.

## Local cluster (kind), tested

Prerequisites: Docker, `kubectl`, [kind](https://kind.sigs.k8s.io) ≥ 0.27.

```bash
bash scripts/ci/build-images.sh      # coldguard-backend:2.0.0, coldguard-frontend:2.0.0, ...
bash scripts/ci/k8s-deploy.sh        # creates kind-coldguard (ingress-nginx, metrics-server), loads images,
                                     # generates secrets.env, applies overlays/local, waits for every rollout
bash scripts/ci/k8s-smoke.sh         # end-to-end checks (see below)
```

**Ingress controller:** ingress-nginx by default. If your network cannot pull from
`registry.k8s.io` (TLS timeouts were seen while testing), use `INGRESS_CONTROLLER=traefik bash
scripts/ci/k8s-deploy.sh`: Traefik comes from Docker Hub and the script re-points the local
Ingress to it. Third-party images are pulled on the host with retries and side-loaded into kind
as single-platform archives (this also works around Docker Desktop's containerd image store).

`k8s-deploy.sh` only deploys to a local context (`kind-*`, `minikube`, `docker-desktop`, …) unless
`ALLOW_REMOTE_CONTEXT=1` is set. **Always pass `--context`** when you run kubectl by hand:

```bash
kubectl --context kind-coldguard -n coldguard get pods,pvc,hpa
# UI      http://coldguard.localhost:8088          (ingress; *.localhost resolves to 127.0.0.1)
kubectl --context kind-coldguard -n coldguard port-forward svc/grafana 3000:3000      # admin / GRAFANA_ADMIN_PASSWORD
kubectl --context kind-coldguard -n coldguard port-forward svc/prometheus 9090:9090
kubectl --context kind-coldguard -n coldguard port-forward svc/backend 8000:8000      # /docs
kind delete cluster --name coldguard                                                  # tear down
```

**Minikube:** `minikube addons enable ingress metrics-server`, `minikube image load coldguard-backend:2.0.0 coldguard-frontend:2.0.0`,
then `KUBE_CONTEXT=minikube bash scripts/ci/k8s-deploy.sh` (the kind steps are skipped for non-kind contexts).

### What `k8s-smoke.sh` verifies

* ingress → frontend → backend service discovery, API probes
* JWT login, forged-token rejection, RBAC denials, ingest-key enforcement
* REST and MQTT telemetry ingestion, and the ML routing model loaded in the pod
* every Prometheus target up; MQTT connected, worker heartbeat, `pg_up`, `redis_up`, container
  CPU/memory (kubelet cAdvisor) and readiness (kube-state-metrics)
* 4 Grafana dashboards and the datasource provisioned; anonymous access denied
* HPA receives CPU metrics
* NetworkPolicy: an unlabeled pod cannot reach Postgres/Redis, an app-tier pod can
* the namespace enforces `restricted` Pod Security and no running pod violates it
* rolling restart of backend + frontend under continuous traffic with **0 failed requests**
* a deleted worker pod is replaced; data survives deleting `postgres-0` (PVC)

## Production

```bash
REGISTRY=registry.example.com/coldguard IMAGE_TAG=$(git rev-parse --short HEAD) \
KUBE_CONTEXT=prod ALLOW_REMOTE_CONTEXT=1 bash scripts/ci/k8s-release.sh all
```

The release script pins the built tag on top of `overlays/production`. It refuses to deploy if
`coldguard-secrets` is missing, re-runs the migration Job and waits for the rollouts. In Jenkins
this is the gated *Deploy production* stage (manual approval).

**External database:** to use managed PostgreSQL, remove `data.yaml`'s Postgres StatefulSet and
Service in an overlay, and set `DATABASE_URL` / `EXPORTER_DSN` in the Secret to the managed
instance (`sslmode=require`). Nothing else changes.
