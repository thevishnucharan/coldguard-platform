"""Standalone background worker: MQTT ingestion, connectivity sweep, escalation,
maintenance rules, expiry and retention. Exposes Prometheus metrics on WORKER_METRICS_PORT.

    python -m app.worker
"""
import logging
import signal

from prometheus_client import start_http_server

from app.core.config import settings
from app.core.logging import setup_logging


def main():
    setup_logging()
    log = logging.getLogger("coldguard.worker")
    from app.core.azure_monitor import configure_azure_monitor
    configure_azure_monitor("coldguard-worker")   # optional Application Insights, alongside Prometheus
    from app.services.realtime import hub  # noqa: F401  (Redis publisher initialised lazily)
    from app.services.rbac import sync_rbac
    from app.db.session import SessionLocal
    from app.workers.runner import runner

    db = SessionLocal()
    try:
        sync_rbac(db)
    finally:
        db.close()
    start_http_server(settings.WORKER_METRICS_PORT)
    log.info("Worker metrics on :%s/metrics", settings.WORKER_METRICS_PORT)
    signal.signal(signal.SIGTERM, lambda *_: runner.stop())
    signal.signal(signal.SIGINT, lambda *_: runner.stop())
    runner.start()
    runner.join()
    log.info("Worker stopped")


if __name__ == "__main__":
    main()
