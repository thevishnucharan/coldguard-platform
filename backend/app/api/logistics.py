"""Excursion relocation routing (ML-assisted, decision support). See services/route_optimizer.py."""
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission, user_from_token
from app.core.config import settings
from app.core.permissions import permissions_for_role
from app.ml.eta_model import EtaModel
from app.models import Batch, Incident, RoutePlan, Shipment, TransitAlert
from app.models.enums import (ACTIVE_INCIDENT_STATUSES, BatchStatus, IncidentType, RoutePlanStatus, ShipmentStatus,
                              TransitAlertStatus)
from app.schemas.logistics import (DispatchRequest, DivertRequest, NoteRequest, RoutePlanDecision, RoutePlanRequest,
                                   TransitReading)
from app.services.access import AccessScope, resolve_scope
from app.services.route_optimizer import Params, RoutePlanService
from app.services.transit import TransitService, alert_dict, shipment_dict

router = APIRouter()


def _summary(p: RoutePlan) -> dict:
    return {
        "id": str(p.id), "plan_number": p.plan_number, "status": p.status.value,
        "incident_id": str(p.incident_id) if p.incident_id else None,
        "incident_number": p.incident.incident_number if p.incident else None,
        "source_storage_unit_id": str(p.source_storage_unit_id), "unit_code": p.source_storage_unit.unit_code,
        "facility_id": str(p.facility_id) if p.facility_id else None,
        "facility_name": p.facility.name if p.facility else None,
        "model_version": p.model_version, "total_doses": p.total_doses, "unassigned_doses": p.unassigned_doses,
        "trip_count": p.trip_count, "exposure_dose_minutes": p.exposure_dose_minutes,
        "baseline_exposure_dose_minutes": p.baseline_exposure_dose_minutes, "improvement_pct": p.improvement_pct,
        "created_by_name": p.created_by_name, "created_at": p.created_at,
        "decided_by_name": p.decided_by_name, "decided_at": p.decided_at, "decision_note": p.decision_note,
    }


def _load(db: Session, plan_id: uuid.UUID, scope: AccessScope) -> RoutePlan:
    p = db.get(RoutePlan, plan_id)
    if not p:
        raise HTTPException(404, "Route plan not found")
    scope.ensure(p.facility_id, not_found="Route plan not found")
    return p


@router.get("/model")
def model_info(_: AccessScope = Depends(require_permission("logistics.view"))) -> Any:
    return EtaModel.info()


@router.get("/excursions")
def active_excursions(db: Session = Depends(get_db),
                      scope: AccessScope = Depends(require_permission("logistics.view"))) -> List[dict]:
    """Active excursion incidents in scope with the stock still inside the affected unit."""
    incs = (scope.apply(db.query(Incident), Incident.facility_id)
            .filter(Incident.incident_type == IncidentType.TEMPERATURE_EXCURSION,
                    Incident.status.in_(ACTIVE_INCIDENT_STATUSES), Incident.storage_unit_id.isnot(None))
            .order_by(Incident.created_at.desc()).all())
    out = []
    for inc in incs:
        batches, doses = (db.query(func.count(Batch.id), func.coalesce(func.sum(Batch.current_quantity), 0))
                          .filter(Batch.storage_unit_id == inc.storage_unit_id, Batch.current_quantity > 0,
                                  Batch.status.in_((BatchStatus.ACTIVE, BatchStatus.QUARANTINED))).one())
        latest = (db.query(RoutePlan).filter(RoutePlan.incident_id == inc.id)
                  .order_by(RoutePlan.created_at.desc()).first())
        out.append({
            "incident_id": str(inc.id), "incident_number": inc.incident_number, "title": inc.title,
            "severity": inc.severity.value, "status": inc.status.value, "created_at": inc.created_at,
            "storage_unit_id": str(inc.storage_unit_id), "unit_code": inc.storage_unit.unit_code if inc.storage_unit else None,
            "facility_id": str(inc.facility_id) if inc.facility_id else None,
            "facility_name": inc.facility.name if inc.facility else None, "is_simulated": inc.is_simulated,
            "batches_at_risk": int(batches), "doses_at_risk": int(doses),
            "latest_plan": ({"id": str(latest.id), "plan_number": latest.plan_number, "status": latest.status.value}
                            if latest else None),
        })
    return out


@router.post("/route-plans", status_code=201)
def create_plan(body: RoutePlanRequest, db: Session = Depends(get_db),
                scope: AccessScope = Depends(require_permission("logistics.plan"))) -> Any:
    params = Params(max_trip_minutes=body.max_trip_minutes, vehicle_capacity_litres=body.vehicle_capacity_litres,
                    vehicles=body.vehicles, depart_at=body.depart_at or datetime.now(timezone.utc),
                    allow_on_site=body.allow_on_site)
    return RoutePlanService.generate(db, scope, incident_id=body.incident_id, storage_unit_id=body.storage_unit_id,
                                     params=params, persist=body.persist)


@router.get("/route-plans")
def list_plans(status: Optional[RoutePlanStatus] = None, incident_id: Optional[uuid.UUID] = None,
               limit: int = 50, db: Session = Depends(get_db),
               scope: AccessScope = Depends(require_permission("logistics.view"))) -> List[dict]:
    q = scope.apply(db.query(RoutePlan), RoutePlan.facility_id)
    if status:
        q = q.filter(RoutePlan.status == status)
    if incident_id:
        q = q.filter(RoutePlan.incident_id == incident_id)
    return [_summary(p) for p in q.order_by(RoutePlan.created_at.desc()).limit(max(1, min(limit, 200))).all()]


@router.get("/route-plans/{plan_id}")
def get_plan(plan_id: uuid.UUID, db: Session = Depends(get_db),
             scope: AccessScope = Depends(require_permission("logistics.view"))) -> Any:
    p = _load(db, plan_id, scope)
    return {**_summary(p), "parameters": p.parameters, "plan": p.plan}


@router.post("/route-plans/{plan_id}/approve")
def approve_plan(plan_id: uuid.UUID, body: RoutePlanDecision, db: Session = Depends(get_db),
                 scope: AccessScope = Depends(require_permission("logistics.plan"))) -> Any:
    p = RoutePlanService.decide(db, _load(db, plan_id, scope), scope.user, True, body.note)
    return _summary(p)


@router.post("/route-plans/{plan_id}/cancel")
def cancel_plan(plan_id: uuid.UUID, body: RoutePlanDecision, db: Session = Depends(get_db),
                scope: AccessScope = Depends(require_permission("logistics.plan"))) -> Any:
    p = RoutePlanService.decide(db, _load(db, plan_id, scope), scope.user, False, body.note)
    return _summary(p)



# ====================================================================== in-transit monitoring
def _shipment(db: Session, shipment_id: uuid.UUID, scope: AccessScope) -> Shipment:
    s = db.get(Shipment, shipment_id)
    if not s:
        raise HTTPException(404, "Shipment not found")
    scope.ensure(s.facility_id, not_found="Shipment not found")
    return s


def _vehicle_auth(request: Request, db: Session = Depends(get_db), x_ingest_key: Optional[str] = Header(None),
                  authorization: Optional[str] = Header(None)) -> Optional[AccessScope]:
    """Vehicle gateways authenticate with X-Ingest-Key (no user); people with a JWT that holds
    logistics.operate (the facility scope check then applies)."""
    if x_ingest_key:
        if settings.INGEST_API_KEY and hmac.compare_digest(x_ingest_key, settings.INGEST_API_KEY):
            return None
        raise HTTPException(401, "Invalid ingest key")
    if authorization and authorization.lower().startswith("bearer "):
        user = user_from_token(db, authorization.split(" ", 1)[1])
        if "logistics.operate" not in permissions_for_role(user.role):
            raise HTTPException(403, "Operation not permitted")
        return resolve_scope(db, user)
    raise HTTPException(401, "Missing credentials", headers={"WWW-Authenticate": "Bearer"})


@router.post("/route-plans/{plan_id}/dispatch", status_code=201)
def dispatch_plan(plan_id: uuid.UUID, body: DispatchRequest, db: Session = Depends(get_db),
                  scope: AccessScope = Depends(require_permission("logistics.operate"))) -> List[dict]:
    plan = _load(db, plan_id, scope)
    sim = bool(plan.incident and plan.incident.is_simulated)
    out = TransitService.dispatch(db, plan, scope.user, body.vehicle_code, body.sensor_code, body.trips,
                                  is_simulated=sim)
    return [shipment_dict(s) for s in out]


@router.get("/shipments")
def list_shipments(status: Optional[ShipmentStatus] = None, plan_id: Optional[uuid.UUID] = None,
                   db: Session = Depends(get_db),
                   scope: AccessScope = Depends(require_permission("logistics.view"))) -> List[dict]:
    q = scope.apply(db.query(Shipment), Shipment.facility_id)
    if status:
        q = q.filter(Shipment.status == status)
    if plan_id:
        q = q.filter(Shipment.route_plan_id == plan_id)
    return [shipment_dict(s) for s in q.order_by(Shipment.dispatched_at.desc()).limit(100).all()]


@router.get("/shipments/{shipment_id}")
def get_shipment(shipment_id: uuid.UUID, db: Session = Depends(get_db),
                 scope: AccessScope = Depends(require_permission("logistics.view"))) -> dict:
    return shipment_dict(_shipment(db, shipment_id, scope))


@router.get("/shipments/{shipment_id}/nearby")
def shipment_nearby(shipment_id: uuid.UUID, lat: Optional[float] = None, lon: Optional[float] = None,
                    db: Session = Depends(get_db),
                    scope: AccessScope = Depends(require_permission("logistics.view"))) -> List[dict]:
    """Nearest compatible cold-chain stores from the vehicle's (or a given) position."""
    s = _shipment(db, shipment_id, scope)
    lat = s.last_lat if lat is None else lat
    lon = s.last_lon if lon is None else lon
    if lat is None or lon is None:
        raise HTTPException(409, "No known vehicle position")
    return TransitService.nearby_storage(db, s, lat, lon)


@router.post("/shipments/{shipment_id}/telemetry", status_code=202)
def shipment_telemetry(shipment_id: uuid.UUID, body: TransitReading, db: Session = Depends(get_db),
                       scope: Optional[AccessScope] = Depends(_vehicle_auth)) -> dict:
    s = db.get(Shipment, shipment_id)
    if not s:
        raise HTTPException(404, "Shipment not found")
    if scope is not None:
        scope.ensure(s.facility_id, not_found="Shipment not found")
    return TransitService.record_reading(db, s, lat=body.lat, lon=body.lon, temperature=body.temperature,
                                         sensor_status=body.sensor_status, timestamp=body.timestamp)


@router.post("/shipments/{shipment_id}/divert")
def divert_shipment(shipment_id: uuid.UUID, body: DivertRequest, db: Session = Depends(get_db),
                    scope: AccessScope = Depends(require_permission("logistics.operate"))) -> dict:
    s = TransitService.divert(db, _shipment(db, shipment_id, scope), body.facility_id, scope.user, body.note)
    return shipment_dict(s)


@router.post("/shipments/{shipment_id}/deliver")
def deliver_shipment(shipment_id: uuid.UUID, body: NoteRequest, db: Session = Depends(get_db),
                     scope: AccessScope = Depends(require_permission("logistics.operate"))) -> dict:
    return shipment_dict(TransitService.deliver(db, _shipment(db, shipment_id, scope), scope.user, body.note))


@router.get("/transit-alerts")
def list_transit_alerts(active: bool = True, db: Session = Depends(get_db),
                        scope: AccessScope = Depends(require_permission("logistics.view"))) -> List[dict]:
    q = scope.apply(db.query(TransitAlert).join(Shipment, TransitAlert.shipment_id == Shipment.id),
                    Shipment.facility_id)
    if active:
        q = q.filter(TransitAlert.status != TransitAlertStatus.RESOLVED)
    return [{**alert_dict(a), "shipment_number": a.shipment.shipment_number, "vehicle_code": a.shipment.vehicle_code}
            for a in q.order_by(TransitAlert.created_at.desc()).limit(100).all()]


@router.post("/transit-alerts/{alert_id}/acknowledge")
def acknowledge_transit_alert(alert_id: uuid.UUID, db: Session = Depends(get_db),
                              scope: AccessScope = Depends(require_permission("logistics.operate"))) -> dict:
    a = db.get(TransitAlert, alert_id)
    if not a:
        raise HTTPException(404, "Alert not found")
    scope.ensure(a.shipment.facility_id, not_found="Alert not found")
    return alert_dict(TransitService.acknowledge(db, a, scope.user))
