import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.middleware import ObservabilityMiddleware, RateLimitingMiddleware, SecurityHeadersMiddleware
from app.db.immutability import ImmutableRecordError

setup_logging()
logger = logging.getLogger("coldguard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.db.session import SessionLocal
    from app.services.rbac import sync_rbac
    from app.services.realtime import hub
    logger.info("Starting ColdGuard API %s (%s)", settings.VERSION, settings.ENVIRONMENT)
    from app.core.azure_monitor import configure_azure_monitor
    configure_azure_monitor("coldguard-api")   # optional Application Insights, alongside Prometheus
    db = SessionLocal()
    try:
        sync_rbac(db)
    except Exception as exc:  # schema may not be migrated yet in some test setups
        logger.warning("RBAC sync skipped: %s", exc)
    finally:
        db.close()
    hub.start_redis_listener()
    consumer = None
    if settings.EVENT_BACKEND == "azure_event_hub":
        from app.adapters.event_source import process_events
        from app.adapters.events import get_event_consumer
        consumer = get_event_consumer()
        await consumer.start_consuming(process_events)
    runner = None
    if settings.RUN_EMBEDDED_WORKER:
        from app.workers.runner import runner
        runner.start()
    yield
    if runner:
        runner.stop()
    if consumer:
        await consumer.stop()
    hub.stop()
    logger.info("ColdGuard API stopped")


app = FastAPI(
    title="ColdGuard API",
    description=("Intelligent vaccine cold-chain monitoring & management platform. All protected endpoints enforce "
                 "permission + facility-scope checks server-side. See docs/API.md and docs/RBAC.md."),
    version=settings.VERSION,
    lifespan=lifespan,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitingMiddleware)
app.add_middleware(ObservabilityMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.BACKEND_CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                   allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Ingest-Key"],
                   expose_headers=["Content-Disposition", "X-Request-ID"])


@app.exception_handler(StarletteHTTPException)
async def http_exc(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_exc(request: Request, exc: RequestValidationError):
    errors = [{"loc": [str(x) for x in e.get("loc", [])], "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "Validation failed", "errors": errors})


@app.exception_handler(ImmutableRecordError)
async def immutable_exc(request: Request, exc: ImmutableRecordError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "An unexpected internal server error occurred."})


from app.api import (audit, auth, dashboards, incidents, inventory, logistics, maintenance, monitoring,  # noqa: E402
                     notifications, org, reports, sensors, storage, system, users, ws)

P = settings.API_V1_STR
app.include_router(auth.router, prefix=f"{P}/auth", tags=["auth"])
app.include_router(users.router, prefix=f"{P}/users", tags=["users"])
app.include_router(org.regions, prefix=f"{P}/regions", tags=["organisation"])
app.include_router(org.facilities, prefix=f"{P}/facilities", tags=["organisation"])
app.include_router(org.policies, prefix=f"{P}/policies", tags=["monitoring policies"])
app.include_router(storage.router, prefix=f"{P}/storage-units", tags=["storage units"])
app.include_router(sensors.router, prefix=f"{P}/sensors", tags=["device registry"])
app.include_router(monitoring.router, prefix=f"{P}/monitoring", tags=["monitoring"])
app.include_router(monitoring.legacy, prefix=f"{P}/temperature", tags=["telemetry gateway"])
app.include_router(incidents.router, prefix=f"{P}/incidents", tags=["incidents"])
app.include_router(inventory.products, prefix=f"{P}/products", tags=["inventory"])
app.include_router(inventory.batches, prefix=f"{P}/batches", tags=["inventory"])
app.include_router(inventory.inventory, prefix=f"{P}/inventory", tags=["inventory"])
app.include_router(maintenance.router, prefix=f"{P}/maintenance", tags=["maintenance"])
app.include_router(maintenance.calibration, prefix=f"{P}/calibration", tags=["calibration"])
app.include_router(maintenance.equipment, prefix=f"{P}/equipment", tags=["equipment"])
app.include_router(logistics.router, prefix=f"{P}/logistics", tags=["logistics"])
app.include_router(notifications.router, prefix=f"{P}/notifications", tags=["notifications"])
app.include_router(dashboards.router, prefix=f"{P}/dashboards", tags=["dashboards"])
app.include_router(dashboards.analytics_router, prefix=f"{P}/analytics", tags=["analytics"])
app.include_router(reports.router, prefix=f"{P}/reports", tags=["reports"])
app.include_router(audit.router, prefix=f"{P}/audit-logs", tags=["audit"])
app.include_router(system.router, prefix=f"{P}/system", tags=["system"])
app.include_router(system.config, prefix=f"{P}/configurations", tags=["system"])
app.include_router(system.demo, prefix=f"{P}/demo", tags=["demo"])
app.include_router(ws.router, prefix=P, tags=["realtime"])


@app.get("/", include_in_schema=False)
def root():
    return {"service": "ColdGuard API", "version": settings.VERSION, "documentation": "/docs"}


@app.get("/health", tags=["probes"])
def liveness():
    return {"status": "healthy"}


@app.get("/ready", tags=["probes"])
def readiness():
    from sqlalchemy import text
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "database unavailable"})
    finally:
        db.close()


@app.get(f"{P}/health", include_in_schema=False)
def api_health():
    return {"status": "healthy"}


@app.get("/metrics", include_in_schema=False)
def metrics():
    from app.core.metrics import metrics_payload
    return Response(metrics_payload(), media_type=CONTENT_TYPE_LATEST)
