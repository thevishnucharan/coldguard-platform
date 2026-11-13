# Jenkins CI/CD

The pipeline is in `Jenkinsfile`. Every stage is a thin call to a script in `scripts/ci/`, so the
exact same phases run locally:

```bash
scripts/ci/run-all.sh                                   # all phases, in pipeline order
PHASES="backend frontend config security" scripts/ci/run-all.sh
PYTHON_BIN=backend/venv/Scripts/python.exe scripts/ci/run-all.sh   # reuse a local venv (Windows)
```

| # | Stage | Script | Gate |
|---|---|---|---|
| 1 | Checkout | — | — |
| 2 | Build & test (parallel) | `backend.sh` (ruff report, pytest → JUnit/coverage) · `frontend.sh` (oxlint, vitest → JUnit, build) | tests |
| 3 | Config consistency | `config-check.sh`: Compose↔k8s shared files identical, scrape jobs present, Compose dev+prod render, prod CORS is https, kustomize overlays render, kubeconform (k8s 1.32) | yes |
| 4 | Security scan | `security-scan.sh`: no tracked secret files / private keys / cloud tokens, no literal secrets in manifests, no backend secrets in the frontend bundle, `npm audit` / `pip-audit` (gating with `STRICT_AUDIT=1`) | yes |
| 5 | Docker images | `build-images.sh`: `coldguard-{backend,frontend,simulator}` tagged `2.0.0` (used by Compose/k8s) and the git sha | yes |
| 6 | Compose smoke test | `compose-smoke.sh`: full stack with throw-away secrets; probes, auth/RBAC, REST + MQTT ingestion, Prometheus targets and signals, Grafana provisioning, restart policy, Postgres persistence | `RUN_COMPOSE_SMOKE` |
| 7 | Kubernetes deploy (kind) | `k8s-deploy.sh`: creates `kind-coldguard` (ingress-nginx, metrics-server) if needed, loads images, applies `overlays/local` | `DEPLOY_LOCAL_K8S` |
| 8 | Kubernetes smoke test | `k8s-smoke.sh`: the shared checks via the ingress, plus HPA metrics, NetworkPolicy isolation, zero-downtime rolling update, self-healing, PVC persistence | `DEPLOY_LOCAL_K8S` |
| 9 | Push images | `k8s-release.sh push` | `PUSH_IMAGES` + `REGISTRY` |
| 10 | Deploy production | `k8s-release.sh deploy` after manual approval | `DEPLOY_PRODUCTION` + `PROD_CONTEXT` |

JUnit results (`reports/*.xml`) are published, and `reports/` plus `frontend/dist` are archived.

## Agent requirements

`bash`, `git`, `python3` (3.11+, with `venv`), Node.js 20+, Docker with the Compose v2 plugin
(the Jenkins user in the `docker` group), `kubectl`, and `kind` ≥ 0.27 for stages 7–8. On a
Windows agent, `sh` steps need Git for Windows' `bin` directory on the PATH.

Stages 1–8 need no credentials. Throw-away secrets are generated per run and deleted afterwards.
The Compose UI uses port `18080` because Jenkins usually owns `8080`. Compose also binds 8001,
3000, 9090 and 1883 on the agent, so builds are serialised (`disableConcurrentBuilds`).

`k8s-deploy.sh` / `k8s-smoke.sh` refuse non-local kube contexts unless `ALLOW_REMOTE_CONTEXT=1`.
A kubeconfig on the agent that points at a real cluster is never touched by stages 7–8.

## Job setup

1. *New Item → Pipeline* (or *Multibranch Pipeline*), *Pipeline script from SCM*, Git URL of this
   repository, *Script Path* `Jenkinsfile`.
2. Required plugins: Pipeline, Git, JUnit, Credentials Binding, Timestamper (all in the
   suggested-plugins set).
3. Build with parameters. The defaults run stages 1–8.

## Credentials (only for stages 9–10)

| ID | Type | Used for |
|---|---|---|
| `coldguard-registry` | Username with password | `docker login` to the registry host in `REGISTRY` (Azure ACR: service principal id / secret) |
| `coldguard-prod-kubeconfig` | Secret file | kubeconfig for the production cluster; `PROD_CONTEXT` selects the context |

The production `coldguard-secrets` Secret must already exist in the cluster (External Secrets /
Sealed Secrets / vault). The pipeline never creates or prints application secrets.
