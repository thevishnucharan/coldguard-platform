# ColdGuard Security

## Implemented controls
| Area | Control | Where |
|---|---|---|
| Passwords | bcrypt (passlib); strength policy (≥10 chars, letters + digits); never logged or returned | `security/auth.py`, `schemas/user.py` |
| Login | Constant-time behaviour for unknown e-mails, lockout after 5 failures (15 min), every failure audited (`LOGIN_FAILED`, `LOGIN_BLOCKED`) | `api/auth.py` |
| Tokens | JWT access token (30 min, HS256, `sub` = user id only — role never trusted from the client); opaque refresh tokens stored as SHA-256, rotated on every use, reuse of a rotated token revokes the whole family | `api/auth.py`, `models/user.py` |
| Browser storage | Access token in memory only; refresh token in `sessionStorage` (cleared when the tab closes) | `frontend/src/store/authStore.ts` |
| Authorization | Central permission matrix; `require_permission()` on every protected endpoint; facility/region data scope applied to every query; out-of-scope resources return 404 (no ID enumeration); denials audited (`PERMISSION_DENIED`) | `core/permissions.py`, `services/access.py`, `api/deps.py` |
| Separation of duties | No self-approval of corrective actions; technicians cannot verify their own repairs; admins have no stock / disposition / incident-acknowledgement rights | `services/incident.py`, `services/maintenance.py` |
| Audit | Append-only `audit_logs`, `incident_events`, `inventory_movements` (ORM blocks update/delete); actor, role, IP, outcome, facility; secrets scrubbed from details | `services/audit.py`, `db/immutability.py` |
| Input validation | Pydantic schemas with bounds; telemetry validated + quarantined; CSV formula-injection escaping; report download path-traversal removed (exports are streamed) | `schemas/*`, `services/telemetry.py`, `services/reporting.py` |
| Devices | Sensor identity checked against registry; decommissioned devices rejected; MQTT topic/payload identity must match; per-device keys stored as hashes, shown once, rotatable; MQTT broker requires auth with topic ACLs | `services/telemetry.py`, `workers/mqtt_ingestor.py`, `infrastructure/mosquitto/` |
| REST gateway | `X-Ingest-Key` compared in constant time, or JWT with `telemetry.ingest` | `api/monitoring.py` |
| Rate limiting | Strict bucket for `/auth/login`; general bucket otherwise; shared via Redis when configured | `core/middleware.py` |
| Transport / headers | CSP, X-Frame-Options DENY, nosniff, Referrer-Policy, HSTS in staging/production; restrictive CORS (explicit origins, methods, headers) | `core/middleware.py`, `main.py`, `frontend/nginx.conf` |
| Errors | Generic 500 body; stack traces only in server logs | `main.py` |
| Logs | Structured JSON; passwords/tokens/secrets/e-mail masked | `core/logging.py` |
| Config | App refuses to start in staging/production with the default `SECRET_KEY` or `DEMO_MODE=true` | `core/config.py` |
| Secrets | No credentials in source: Compose reads `.env` (git-ignored; `.env.example` has placeholders); Kubernetes generates `coldguard-secrets` from a git-ignored `secrets.env` | `docker-compose.yml`, `infrastructure/k8s/` |
| Containers | Non-root users (API uid 10001, nginx-unprivileged, simulator uid 10002), `no-new-privileges`, dropped capabilities, seccomp RuntimeDefault, resource limits; NetworkPolicies default-deny | Dockerfiles, `infrastructure/k8s/base` |

## Production checklist
1. Set `ENVIRONMENT=production`, a 64-character random `SECRET_KEY`, `DEMO_MODE=false`.
2. Bootstrap the first admin: `BOOTSTRAP_ADMIN_PASSWORD=… python scripts/seed.py --bootstrap-admin you@org`.
3. Terminate TLS at the ingress / load balancer; enable the Mosquitto TLS listener (8883) and per-device credentials.
4. Use a managed PostgreSQL with TLS; grant the application role no `UPDATE`/`DELETE` on `audit_logs`, `incident_events`, `inventory_movements` (DB-level immutability on top of the ORM guard).
5. Move secrets to a secret manager (External Secrets / Azure Key Vault) instead of `secrets.env`.
6. Consider httpOnly, SameSite=strict cookies for the refresh token if the SPA and API share a domain.

## Known limitations
* The demo accounts and password are public by design (local demonstration only); `DEMO_MODE=false` disables seeding, the simulator and the login-page demo buttons.
* The ML and AI-assistant outputs are decision support only and are labelled as such.
