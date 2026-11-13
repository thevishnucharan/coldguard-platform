"""Periodic background jobs. Each job opens its own session and is isolated: one job's
failure is logged and counted but never stops the others."""
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.core.config import settings
from app.core.metrics import (ACTIVE_INCIDENTS, SENSORS_BY_STATUS, WORKER_HEARTBEAT, WORKER_JOB_DURATION,
                              WORKER_JOB_FAILURES)
from app.db.session import SessionLocal
from app.models import Incident, Sensor, SystemConfiguration, TemperatureReading, TemperatureRollup
from app.models.enums import ACTIVE_INCIDENT_STATUSES

logger = logging.getLogger(__name__)


def job_connectivity(db):
    from app.services.sensor_health import SensorHealthService
    return SensorHealthService.check_offline_sensors(db)


def job_transit(db):
    from app.services.transit import TransitService
    return TransitService.check_offline(db)


def job_escalation(db):
    from app.services.escalation import run_escalations
    return run_escalations(db)


def job_maintenance_rules(db):
    from app.services.maintenance import MaintenanceRules
    return MaintenanceRules.run(db)


def job_expiry(db):
    from app.services.inventory import InventoryService
    return {"expired": InventoryService.mark_expired(db)}


def job_gauges(db):
    for sev, n in db.query(Incident.severity, func.count(Incident.id)).filter(
            Incident.status.in_(ACTIVE_INCIDENT_STATUSES)).group_by(Incident.severity).all():
        ACTIVE_INCIDENTS.labels(severity=sev.value).set(n)
    for st, n in db.query(Sensor.status, func.count(Sensor.id)).group_by(Sensor.status).all():
        SENSORS_BY_STATUS.labels(status=st.value).set(n)
    return {}


def job_retention(db):
    """Roll raw telemetry older than the retention window into hourly aggregates; purge raw
    rows only when RETENTION_PURGE_ENABLED (readings linked to incidents' windows are kept
    because violations/incident events store their own evidence values)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.TELEMETRY_RETENTION_DAYS)
    old = db.query(TemperatureReading).filter(TemperatureReading.timestamp < cutoff).limit(20000).all()
    if not old:
        return {"rolled": 0}
    buckets = {}
    for r in old:
        hour = r.timestamp.replace(minute=0, second=0, microsecond=0)
        buckets.setdefault((r.sensor_id, r.storage_unit_id, hour), []).append(r.temperature)
    for (sid, uid, hour), temps in buckets.items():
        if not db.query(TemperatureRollup).filter_by(sensor_id=sid, hour=hour).first():
            db.add(TemperatureRollup(sensor_id=sid, storage_unit_id=uid, hour=hour, min_temperature=min(temps),
                                     max_temperature=max(temps), avg_temperature=sum(temps) / len(temps),
                                     reading_count=len(temps)))
    if settings.RETENTION_PURGE_ENABLED:
        for r in old:
            if r.anomaly is None:
                db.delete(r)
    db.commit()
    return {"rolled": len(old)}


def heartbeat(db):
    now = datetime.now(timezone.utc)
    row = db.get(SystemConfiguration, "worker.heartbeat")
    mqtt = None
    if settings.MQTT_ENABLED:
        from app.workers.mqtt_ingestor import ingestor
        mqtt = ingestor.connected
    value = {"at": now.isoformat(), "mode": "embedded" if settings.RUN_EMBEDDED_WORKER else "standalone",
             "mqtt": mqtt}
    if row:
        row.value = value
    else:
        db.add(SystemConfiguration(key="worker.heartbeat", value=value, description="Background worker liveness"))
    db.commit()
    WORKER_HEARTBEAT.set(now.timestamp())
    return {}


JOBS = [  # (name, every_n_ticks)
    ("heartbeat", heartbeat, 1),
    ("connectivity", job_connectivity, 1),
    ("transit", job_transit, 1),          # silent vehicle data loggers -> SENSOR_OFFLINE transit alerts
    ("escalation", job_escalation, 2),
    ("gauges", job_gauges, 1),
    ("maintenance_rules", job_maintenance_rules, 10),
    ("expiry", job_expiry, 20),
    ("retention", job_retention, 120),
]


# Set while a demo reset rebuilds the dataset so sweeps don't act on half-seeded data.
import threading as _threading
PAUSED = _threading.Event()


def seeding_in_progress() -> bool:
    """Cross-process pause: set by the demo seed (possibly running in another container)."""
    db = SessionLocal()
    try:
        row = db.get(SystemConfiguration, "demo.seeding")
        if row is None:
            return False
        started = datetime.fromisoformat(row.value.get("started"))
        return datetime.now(timezone.utc) - started < timedelta(minutes=30)  # stale flag (crashed seed) expires
    except Exception:
        return False
    finally:
        db.close()


def run_cycle(tick: int) -> dict:
    results = {}
    if PAUSED.is_set() or seeding_in_progress():
        return results
    for name, fn, every in JOBS:
        if tick % every:
            continue
        started = time.perf_counter()
        db = SessionLocal()
        try:
            results[name] = fn(db)
        except Exception as exc:
            db.rollback()
            WORKER_JOB_FAILURES.labels(job=name).inc()
            logger.error("Worker job %s failed: %s", name, exc, exc_info=True)
        finally:
            db.close()
            WORKER_JOB_DURATION.labels(job=name).observe(time.perf_counter() - started)
    return results
