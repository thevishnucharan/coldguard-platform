"""Role dashboards and analytics. Each dashboard requires an ACTION permission characteristic
of that role (e.g. incidents.review for the supervisor view), so dashboards are not shared
across roles; all data inside is additionally facility-scoped."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.services import analytics
from app.services.access import AccessScope

router = APIRouter()      # /dashboards
analytics_router = APIRouter()  # /analytics


@router.get("/admin")
def admin(db: Session = Depends(get_db), scope: AccessScope = Depends(require_permission("platform.view", "users.view"))):
    return analytics.admin_overview(db, scope)


@router.get("/operator")
def operator(facility_id: Optional[uuid.UUID] = None, db: Session = Depends(get_db),
             scope: AccessScope = Depends(require_permission("monitoring.view", "incidents.acknowledge"))):
    scope.ensure_requested(facility_id)
    return analytics.operator_dashboard(db, scope, facility_id)


@router.get("/supervisor")
def supervisor(db: Session = Depends(get_db),
               scope: AccessScope = Depends(require_permission("incidents.review", "reports.view"))):
    return analytics.supervisor_dashboard(db, scope)


@router.get("/technician")
def technician(db: Session = Depends(get_db),
               scope: AccessScope = Depends(require_permission("maintenance.update", "calibration.view"))):
    return analytics.technician_dashboard(db, scope, scope.user)


@router.get("/auditor")
def auditor(db: Session = Depends(get_db),
            scope: AccessScope = Depends(require_permission("audit.view", "reports.view"))):
    return analytics.auditor_home(db, scope)


@analytics_router.get("/compliance-trend")
def compliance_trend(days: int = Query(14, ge=1, le=90), facility_id: Optional[uuid.UUID] = None,
                     db: Session = Depends(get_db), scope: AccessScope = Depends(require_permission("reports.view"))):
    scope.ensure_requested(facility_id)
    return analytics.compliance_trend(db, scope, days, facility_id)


@analytics_router.get("/facility-comparison")
def facility_comparison(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db),
                        scope: AccessScope = Depends(require_permission("reports.view", "incidents.view"))):
    return analytics.facility_comparison(db, scope, days)


@analytics_router.get("/incidents-per-day")
def incidents_per_day(days: int = Query(14, ge=1, le=90), db: Session = Depends(get_db),
                      scope: AccessScope = Depends(require_permission("incidents.view"))):
    return analytics.incidents_per_day(db, scope, days)


@analytics_router.get("/device-reliability")
def device_reliability(hours: int = Query(24, ge=1, le=24 * 30), db: Session = Depends(get_db),
                       scope: AccessScope = Depends(require_permission("devices.view"))):
    return analytics.device_reliability(db, scope, hours)


@analytics_router.get("/ingestion")
def ingestion(hours: int = Query(24, ge=1, le=168), db: Session = Depends(get_db),
              scope: AccessScope = Depends(require_permission("monitoring.view"))):
    return analytics.hourly_ingestion(db, scope, hours)
