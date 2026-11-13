"""Regions, facilities and monitoring policies."""
import uuid
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models import Facility, MonitoringPolicy, Region, StorageUnit, User, UserRoleAssignment
from app.schemas.org import FacilityIn, FacilityUpdate, PolicyIn, PolicyOut, RegionIn, RegionOut
from app.services import analytics
from app.services.access import AccessScope
from app.services.audit import log_audit

regions = APIRouter()
facilities = APIRouter()
policies = APIRouter()


# ------------------------------------------------------------------ regions
@regions.get("", response_model=List[RegionOut])
def list_regions(db: Session = Depends(get_db), scope: AccessScope = Depends(require_permission("facilities.view"))):
    q = db.query(Region).order_by(Region.name)
    if not scope.is_global:
        visible = {f.region_id for f in db.query(Facility).filter(Facility.id.in_(scope.facility_ids))}
        q = q.filter(Region.id.in_(visible | scope.region_ids))
    return q.all()


@regions.post("", response_model=RegionOut, status_code=201)
def create_region(body: RegionIn, request: Request, db: Session = Depends(get_db),
                  scope: AccessScope = Depends(require_permission("regions.manage"))):
    if db.query(Region).filter(Region.code == body.code).first():
        raise HTTPException(409, "Region code already exists")
    r = Region(**body.model_dump())
    db.add(r)
    db.flush()
    log_audit(db, scope.user, "REGION_CREATED", "Region", r.id, body.model_dump(), category="CONFIG", request=request,
              commit=False)
    db.commit()
    return r


@regions.put("/{region_id}", response_model=RegionOut)
def update_region(region_id: uuid.UUID, body: RegionIn, request: Request, db: Session = Depends(get_db),
                  scope: AccessScope = Depends(require_permission("regions.manage"))):
    r = db.get(Region, region_id)
    if not r:
        raise HTTPException(404, "Region not found")
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    log_audit(db, scope.user, "REGION_UPDATED", "Region", r.id, body.model_dump(), category="CONFIG", request=request,
              commit=False)
    db.commit()
    return r


# ------------------------------------------------------------------ facilities
@facilities.get("")
def list_facilities(region_id: Optional[uuid.UUID] = None, include_inactive: bool = False,
                    db: Session = Depends(get_db), scope: AccessScope = Depends(require_permission("facilities.view"))):
    """Facilities in scope with live health summary (used by maps and pickers)."""
    rows = analytics.facility_summaries(db, scope)
    if region_id:
        rows = [r for r in rows if r["region_id"] == region_id]
    if not include_inactive:
        rows = [r for r in rows if r["is_active"]]
    return rows


@facilities.post("", status_code=201)
def create_facility(body: FacilityIn, request: Request, db: Session = Depends(get_db),
                    scope: AccessScope = Depends(require_permission("facilities.create"))):
    if not db.get(Region, body.region_id):
        raise HTTPException(400, "Region not found")
    if db.query(Facility).filter(Facility.code == body.code).first():
        raise HTTPException(409, "Facility code already exists")
    f = Facility(**body.model_dump())
    db.add(f)
    db.flush()
    log_audit(db, scope.user, "FACILITY_CREATED", "Facility", f.id, body.model_dump(), category="CONFIG",
              facility_id=f.id, request=request, commit=False)
    db.commit()
    return {"id": f.id, "code": f.code, "name": f.name}


@facilities.get("/{facility_id}")
def get_facility(facility_id: uuid.UUID, db: Session = Depends(get_db),
                 scope: AccessScope = Depends(require_permission("facilities.view"))):
    scope.ensure(facility_id, not_found="Facility not found")
    rows = [r for r in analytics.facility_summaries(db, scope) if r["id"] == facility_id]
    if not rows:
        raise HTTPException(404, "Facility not found")
    f = rows[0]
    staff = (db.query(User).join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
             .filter((UserRoleAssignment.facility_id == facility_id) | (UserRoleAssignment.region_id == f["region_id"]))
             .distinct().all())
    f["staff"] = [{"id": u.id, "name": u.name, "role": u.role.value, "title": u.title, "is_active": u.is_active}
                  for u in staff]
    f["equipment"] = [{"id": u.id, "unit_code": u.unit_code, "name": u.name, "unit_type": u.unit_type,
                       "status": u.status.value, "sensors": len(u.sensors)}
                      for u in db.query(StorageUnit).filter(StorageUnit.facility_id == facility_id)]
    return f


@facilities.put("/{facility_id}")
def update_facility(facility_id: uuid.UUID, body: FacilityUpdate, request: Request, db: Session = Depends(get_db),
                    scope: AccessScope = Depends(require_permission("facilities.update"))):
    f = db.get(Facility, facility_id)
    if not f:
        raise HTTPException(404, "Facility not found")
    data = body.model_dump(exclude_unset=True)
    if "region_id" in data and not db.get(Region, data["region_id"]):
        raise HTTPException(400, "Region not found")
    for k, v in data.items():
        setattr(f, k, v)
    action = "FACILITY_DEACTIVATED" if data.get("is_active") is False else "FACILITY_UPDATED"
    log_audit(db, scope.user, action, "Facility", f.id, {k: str(v) for k, v in data.items()}, category="CONFIG",
              facility_id=f.id, request=request, commit=False)
    db.commit()
    return {"id": f.id, "code": f.code, "name": f.name, "is_active": f.is_active}


# ------------------------------------------------------------------ monitoring policies
@policies.get("", response_model=List[PolicyOut])
def list_policies(db: Session = Depends(get_db), _: AccessScope = Depends(require_permission("monitoring.view"))):
    return db.query(MonitoringPolicy).order_by(MonitoringPolicy.name).all()


@policies.post("", response_model=PolicyOut, status_code=201)
def create_policy(body: PolicyIn, request: Request, db: Session = Depends(get_db),
                  scope: AccessScope = Depends(require_permission("platform.configure"))):
    if db.query(MonitoringPolicy).filter(MonitoringPolicy.name == body.name).first():
        raise HTTPException(409, "Policy name already exists")
    p = MonitoringPolicy(**body.model_dump())
    db.add(p)
    db.flush()
    log_audit(db, scope.user, "POLICY_CREATED", "MonitoringPolicy", p.id, body.model_dump(), category="CONFIG",
              request=request, commit=False)
    db.commit()
    return p


@policies.put("/{policy_id}", response_model=PolicyOut)
def update_policy(policy_id: uuid.UUID, body: PolicyIn, request: Request, db: Session = Depends(get_db),
                  scope: AccessScope = Depends(require_permission("platform.configure"))) -> Any:
    p = db.get(MonitoringPolicy, policy_id)
    if not p:
        raise HTTPException(404, "Policy not found")
    before = PolicyIn.model_validate(p, from_attributes=True).model_dump()
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    log_audit(db, scope.user, "POLICY_UPDATED", "MonitoringPolicy", p.id, {"before": before, "after": body.model_dump()},
              category="CONFIG", request=request, commit=False)
    db.commit()
    return p


_ = Query
