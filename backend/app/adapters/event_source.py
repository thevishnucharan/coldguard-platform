"""Callback for the (preserved) local / Azure Event Hubs event consumers: every event goes
through the same telemetry ingestion pipeline as MQTT and REST."""
import logging
from typing import Any, Dict, List

from app.db.session import SessionLocal
from app.services import telemetry

logger = logging.getLogger(__name__)


def process_events(events: List[Dict[str, Any]]) -> None:
    if not events:
        return
    db = SessionLocal()
    try:
        for payload in events:
            try:
                telemetry.ingest(db, payload, channel="eventhub")
            except Exception as exc:
                db.rollback()
                logger.error("Event processing failed: %s", exc, exc_info=True)
    finally:
        db.close()
