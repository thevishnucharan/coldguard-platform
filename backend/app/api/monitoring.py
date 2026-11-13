"""Live monitoring, telemetry gateway (REST), quarantine and anomalies."""
import hmac
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission, user_from_token
from app.core.config import settings
from app.core.permissions import permissions_for_role
from app.ml.anomaly_service import MLAnomalyService
from app.models import Anomaly, Sensor, StorageUnit, TelemetryQuarantine, TemperatureReading
from app.schemas.common import paginate
from app.services import monitoring as mon
from app.services import telemetry
from app.services.access import AccessScope

router = APIRouter()       # /monitoring
legacy = APIRouter()       # /temperature (v1 paths preserved)


@router.get("/live")
def live(facility_id: Optional[uuid.UUID] = None, db: Session = Depends(get_db),
         scope: AccessScope = Depends(require_permission("monitoring.view"))):
    scope.ensure_requested(facility_id)
    return {"units": mon.live_units(db, scope, facility_id)}


@router.get("/quarantine")
def quarantine(page: int = Query(1, ge=1), page_size: int = Query(50, le=200), db: Session = Depends(get_db),
               scope: AccessScope = Depends(require_permission("devices.view"))):
    q = db.query(TelemetryQuarantine).order_by(TelemetryQuarantine.received_at.desc())
    if not scope.is_global:  # restrict to sensors in scope
        codes = [c for (c,) in scope.apply(db.query(Sensor.sensor_code).join(StorageUnit, StorageUnit.id == Sensor.storage_unit_id),
                                           StorageUnit.facility_id).all()]
        q = q.filter(TelemetryQuarantine.sensor_code.in_(codes))
    items, total = paginate(q, page, page_size)
    return {"items": [{"id": r.id, "received_at": r.received_at, "channel": r.channel, "sensor_code": r.sensor_code,
                       "reason": r.reason, "raw_payload": r.raw_payload[:500], "is_simulated": r.is_simulated}
                      for r in items], "total": total, "page": page, "page_size": page_size}


@router.get("/anomalies")
def anomalies(storage_unit_id: Optional[uuid.UUID] = None, hours: int = Query(24, ge=1, le=24 * 30),
              limit: int = Query(200, le=1000), db: Session = Depends(get_db),
              scope: AccessScope = Depends(require_permission("monitoring.view"))):
    from datetime import datetime, timedelta, timezone
    q = (db.query(Anomaly).join(StorageUnit, StorageUnit.id == Anomaly.storage_unit_id)
         .filter(Anomaly.detected_at >= datetime.now(timezone.utc) - timedelta(hours=hours)))
    q = scope.apply(q, StorageUnit.facility_id)
    if storage_unit_id:
        q = q.filter(Anomaly.storage_unit_id == storage_unit_id)
    return {"model": MLAnomalyService.model_info(),
            "items": [{"id": a.id, "sensor_id": a.sensor_id, "storage_unit_id": a.storage_unit_id,
                       "detected_at": a.detected_at, "temperature": a.temperature, "anomaly_score": a.anomaly_score,
                       "detection_method": a.detection_method, "severity": a.severity.value,
                       "model_version": a.model_version, "context": a.context, "explanation": a.explanation,
                       "incident_id": a.incident_id, "is_simulated": a.is_simulated}
                      for a in q.order_by(Anomaly.detected_at.desc()).limit(limit)]}


# ------------------------------------------------------------------ REST telemetry gateway
def ingest_auth(request: Request, x_ingest_key: Optional[str] = Header(None), db: Session = Depends(get_db),
                authorization: Optional[str] = Header(None)) -> str:
    """Gateways authenticate with X-Ingest-Key; humans/tools with a JWT holding telemetry.ingest."""
    if x_ingest_key:
        if settings.INGEST_API_KEY and hmac.compare_digest(x_ingest_key, settings.INGEST_API_KEY):
            return "gateway"
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid ingest key")
    if authorization and authorization.lower().startswith("bearer "):
        user = user_from_token(db, authorization.split(" ", 1)[1])
        if "telemetry.ingest" in permissions_for_role(user.role):
            return f"user:{user.id}"
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Operation not permitted")
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing credentials", headers={"WWW-Authenticate": "Bearer"})


@legacy.post("/readings", status_code=202)
def ingest_one(payload: Dict[str, Any], db: Session = Depends(get_db), _: str = Depends(ingest_auth)):
    r = telemetry.ingest(db, payload, channel="rest")
    if r.status == "rejected":
        raise HTTPException(422, f"Reading rejected: {r.reason} (stored in telemetry quarantine)")
    return {"status": r.status, "reading_id": r.reading_id, "quality": r.quality, "message": r.reason}


@legacy.post("/readings/bulk", status_code=202)
def ingest_bulk(body: Dict[str, List[Dict[str, Any]]], db: Session = Depends(get_db), _: str = Depends(ingest_auth)):
    readings = body.get("readings") or []
    if len(readings) > 1000:
        raise HTTPException(400, "Bulk ingestion batch exceeds maximum limit of 1000 readings")
    results = [telemetry.ingest(db, r, channel="rest") for r in readings]  # every reading validated individually
    return {"ingested": sum(r.status == "accepted" for r in results),
            "duplicates": sum(r.status == "duplicate" for r in results),
            "rejected": sum(r.status == "rejected" for r in results)}


@legacy.get("/readings")
def list_readings(sensor_id: Optional[uuid.UUID] = None, storage_unit_id: Optional[uuid.UUID] = None,
                  limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db),
                  scope: AccessScope = Depends(require_permission("monitoring.view"))):
    q = db.query(TemperatureReading).join(StorageUnit, StorageUnit.id == TemperatureReading.storage_unit_id)
    q = scope.apply(q, StorageUnit.facility_id)
    if sensor_id:
        q = q.filter(TemperatureReading.sensor_id == sensor_id)
    if storage_unit_id:
        q = q.filter(TemperatureReading.storage_unit_id == storage_unit_id)
    return [{"id": r.id, "sensor_id": r.sensor_id, "storage_unit_id": r.storage_unit_id, "temperature": r.temperature,
             "timestamp": r.timestamp, "source": r.source, "quality_status": r.quality_status,
             "is_simulated": r.is_simulated}
            for r in q.order_by(TemperatureReading.timestamp.desc()).limit(limit)]
