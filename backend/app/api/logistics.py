"""Excursion relocation routing (ML-assisted, decision support). See services/route_optimizer.py."""
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.ml.eta_model import EtaModel
from app.models import Batch, Incident, RoutePlan
from app.models.enums import ACTIVE_INCIDENT_STATUSES, BatchStatus, IncidentType, RoutePlanStatus
from app.schemas.logistics import RoutePlanDecision, RoutePlanRequest
from app.services.access import AccessScope
from app.services.route_optimizer import Params, RoutePlanService

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
                    vehicles=body.vehicles, depart_at=body.depart_at or datetime.now(timezone.utc))
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

