"""Reports. Exports are streamed directly to the requester (v1 stored files under guessable
names that any authenticated user could download; that flow was removed)."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.services import reporting
from app.services.access import AccessScope
from app.services.audit import log_audit
from app.services.metrics import MetricsService

router = APIRouter()


@router.get("/types")
def report_types(scope: AccessScope = Depends(require_permission("reports.view"))):
    return {"reports": reporting.available_reports(scope), "can_export": scope.has("reports.export")}


@router.get("/export")
def export(request: Request, type: str = Query(..., alias="type"), format: str = Query("csv", pattern="^(csv|pdf)$"),
           start: Optional[datetime] = None, end: Optional[datetime] = None, days: Optional[int] = Query(None, ge=1, le=3650),
           facility_id: Optional[uuid.UUID] = None, db: Session = Depends(get_db),
           scope: AccessScope = Depends(require_permission("reports.view", "reports.export"))):
    spec = reporting.REPORTS.get(type)
    if spec is None:
        raise HTTPException(404, "Unknown report type")
    if not scope.has(spec["permission"]):
        raise HTTPException(403, "Operation not permitted")
    scope.ensure_requested(facility_id)
    if days and not start:
        start = datetime.now(timezone.utc) - timedelta(days=days)
    if start and end and start > end:
        raise HTTPException(400, "start must be before end")
    filename, content, media = reporting.build(db, scope, type, format, start, end, facility_id)
    log_audit(db, scope.user, "REPORT_EXPORTED", "Report", None,
              {"type": type, "format": format, "facility_id": str(facility_id) if facility_id else None,
               "start": start.isoformat() if start else None, "end": end.isoformat() if end else None,
               "bytes": len(content)}, category="DATA", request=request)
    return Response(content=content, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "Cache-Control": "no-store"})


@router.get("/dashboard")
def legacy_dashboard_metrics(date_filter: str = Query("all"), db: Session = Depends(get_db),
                             scope: AccessScope = Depends(require_permission("platform.view"))):
    """Preserved v1 platform metrics (global; admin/auditor)."""
    now = datetime.now(timezone.utc)
    start = {"today": now.replace(hour=0, minute=0, second=0, microsecond=0), "last_7_days": now - timedelta(days=7),
             "last_30_days": now - timedelta(days=30)}.get(date_filter)
    return MetricsService.get_dashboard_metrics(db, start, now if start else None)
