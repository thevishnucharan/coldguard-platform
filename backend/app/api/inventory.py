import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.api.deps import get_db, require_permission
from app.models import Batch, Incident, IncidentBatch, InventoryMovement, Product
from app.models.enums import BatchStatus, MovementType
from app.schemas.common import Page, paginate
from app.schemas.inventory import (AdjustIn, BatchDetail, BatchOut, DispositionIn, FefoIssueIn, MovementOut, ProductIn,
                                   ProductOut, QuantityIn, ReceiveIn, ReconcileIn, TransferIn)
from app.services.access import AccessScope
from app.services.audit import log_audit
from app.services.inventory import InventoryService

products = APIRouter()
batches = APIRouter()
inventory = APIRouter()


# ------------------------------------------------------------------ products
@products.get("", response_model=List[ProductOut])
def list_products(db: Session = Depends(get_db), _: AccessScope = Depends(require_permission("inventory.view"))):
    return db.query(Product).order_by(Product.name).all()


@products.post("", response_model=ProductOut, status_code=201)
def create_product(body: ProductIn, request: Request, db: Session = Depends(get_db),
                   scope: AccessScope = Depends(require_permission("products.manage"))):
    p = Product(**body.model_dump())
    db.add(p)
    db.flush()
    log_audit(db, scope.user, "PRODUCT_CREATED", "Product", p.id, body.model_dump(), category="CONFIG",
              request=request, commit=False)
    db.commit()
    return p


@products.put("/{product_id}", response_model=ProductOut)
def update_product(product_id: uuid.UUID, body: ProductIn, request: Request, db: Session = Depends(get_db),
                   scope: AccessScope = Depends(require_permission("products.manage"))):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    log_audit(db, scope.user, "PRODUCT_UPDATED", "Product", p.id, body.model_dump(), category="CONFIG",
              request=request, commit=False)
    db.commit()
    return p


# ------------------------------------------------------------------ batches
def _batch(db, batch_id, scope) -> Batch:
    b = db.get(Batch, batch_id)
    if not b:
        raise HTTPException(404, "Batch not found")
    scope.ensure(b.facility_id, not_found="Batch not found")
    return b


@batches.get("", response_model=Page[BatchOut])
def list_batches(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
                 status: Optional[List[BatchStatus]] = Query(None), facility_id: Optional[uuid.UUID] = None,
                 product_id: Optional[uuid.UUID] = None, storage_unit_id: Optional[uuid.UUID] = None,
                 expiring_within_days: Optional[int] = Query(None, ge=0, le=3650),
                 search: Optional[str] = Query(None, max_length=100),
                 sort: str = Query("expiry_date", pattern="^-?(expiry_date|batch_number|current_quantity|receipt_date)$"),
                 db: Session = Depends(get_db), scope: AccessScope = Depends(require_permission("inventory.view"))) -> Any:
    scope.ensure_requested(facility_id)
    q = scope.apply(db.query(Batch), Batch.facility_id)
    if status:
        q = q.filter(Batch.status.in_(status))
    if facility_id:
        q = q.filter(Batch.facility_id == facility_id)
    if product_id:
        q = q.filter(Batch.product_id == product_id)
    if storage_unit_id:
        q = q.filter(Batch.storage_unit_id == storage_unit_id)
    if expiring_within_days is not None:
        q = q.filter(Batch.expiry_date <= datetime.now(timezone.utc) + timedelta(days=expiring_within_days))
    if search:
        like = f"%{search.strip()}%"
        q = q.join(Product).filter(or_(Batch.batch_number.ilike(like), Product.name.ilike(like)))
    col = getattr(Batch, sort.lstrip("-"))
    q = q.order_by(col.desc() if sort.startswith("-") else col.asc())
    items, total = paginate(q, page, page_size)
    return {"items": [ser.batch(b) for b in items], "total": total, "page": page, "page_size": page_size}


@batches.post("/receive", response_model=BatchOut, status_code=201)
def receive(body: ReceiveIn, db: Session = Depends(get_db),
            scope: AccessScope = Depends(require_permission("inventory.manage"))):
    b = InventoryService.receive(db, scope.user, scope=scope, **body.model_dump())
    return ser.batch(b)


@batches.get("/{batch_id}", response_model=BatchDetail)
def get_batch(batch_id: uuid.UUID, db: Session = Depends(get_db),
              scope: AccessScope = Depends(require_permission("inventory.view"))):
    b = _batch(db, batch_id, scope)
    d = ser.batch(b)
    d["movements"] = [{**MovementOut.model_validate(m).model_dump(), "batch_number": b.batch_number} for m in b.movements]
    incs = (db.query(Incident).join(IncidentBatch, IncidentBatch.incident_id == Incident.id)
            .filter(IncidentBatch.batch_id == b.id).order_by(Incident.created_at).all())
    d["incidents"] = [{"id": i.id, "incident_number": i.incident_number, "severity": i.severity.value,
                       "status": i.status.value, "title": i.title, "peak_temperature": i.peak_temperature,
                       "excursion_start": i.excursion_start, "excursion_end": i.excursion_end,
                       "vaccine_disposition": i.vaccine_disposition} for i in incs]
    return d


def _done(b):
    return ser.batch(b)


@batches.post("/{batch_id}/issue", response_model=BatchOut)
def issue(batch_id: uuid.UUID, body: QuantityIn, db: Session = Depends(get_db),
          scope: AccessScope = Depends(require_permission("inventory.manage"))):
    b = _batch(db, batch_id, scope)
    override = bool(body.override_fefo_reason)
    reason = body.reason or ""
    if override:
        reason = f"{reason} [FEFO override: {body.override_fefo_reason}]".strip()
    InventoryService.issue(db, b, scope.user, body.quantity, reason or None, body.reference, enforce_fefo=not override)
    return _done(b)


@batches.post("/{batch_id}/adjust", response_model=BatchOut)
def adjust(batch_id: uuid.UUID, body: AdjustIn, db: Session = Depends(get_db),
           scope: AccessScope = Depends(require_permission("inventory.manage"))):
    b = _batch(db, batch_id, scope)
    InventoryService.adjust(db, b, scope.user, body.change, body.reason)
    return _done(b)


@batches.post("/{batch_id}/reconcile", response_model=BatchOut)
def reconcile(batch_id: uuid.UUID, body: ReconcileIn, db: Session = Depends(get_db),
              scope: AccessScope = Depends(require_permission("inventory.manage"))):
    b = _batch(db, batch_id, scope)
    InventoryService.reconcile(db, b, scope.user, body.counted_quantity, body.reason)
    return _done(b)


@batches.post("/{batch_id}/transfer", response_model=BatchOut)
def transfer(batch_id: uuid.UUID, body: TransferIn, db: Session = Depends(get_db),
             scope: AccessScope = Depends(require_permission("inventory.manage"))):
    b = _batch(db, batch_id, scope)
    InventoryService.transfer(db, b, scope.user, body.to_storage_unit_id, body.reason, scope=scope)
    return _done(b)


@batches.post("/{batch_id}/quarantine", response_model=BatchOut)
def quarantine(batch_id: uuid.UUID, body: DispositionIn, db: Session = Depends(get_db),
               scope: AccessScope = Depends(require_permission("batches.quarantine"))):
    b = _batch(db, batch_id, scope)
    InventoryService.quarantine(db, b, scope.user, body.reason, body.incident_id)
    return _done(b)


@batches.post("/{batch_id}/release", response_model=BatchOut)
def release(batch_id: uuid.UUID, body: DispositionIn, db: Session = Depends(get_db),
            scope: AccessScope = Depends(require_permission("batches.release"))):
    b = _batch(db, batch_id, scope)
    InventoryService.release(db, b, scope.user, body.reason, body.incident_id)
    return _done(b)


@batches.post("/{batch_id}/dispose", response_model=BatchOut)
def dispose(batch_id: uuid.UUID, body: DispositionIn, db: Session = Depends(get_db),
            scope: AccessScope = Depends(require_permission("batches.dispose"))):
    b = _batch(db, batch_id, scope)
    InventoryService.dispose(db, b, scope.user, body.reason, body.incident_id)
    return _done(b)


# ------------------------------------------------------------------ inventory-level
@inventory.get("/fefo")
def fefo(product_id: uuid.UUID, facility_id: uuid.UUID, db: Session = Depends(get_db),
         scope: AccessScope = Depends(require_permission("inventory.view"))):
    scope.ensure_requested(facility_id)
    return [ser.batch(b) for b in InventoryService.fefo_queue(db, product_id, facility_id)]


@inventory.post("/issue-fefo", response_model=List[MovementOut])
def issue_fefo(body: FefoIssueIn, db: Session = Depends(get_db),
               scope: AccessScope = Depends(require_permission("inventory.manage"))):
    scope.ensure_requested(body.facility_id)
    moves = InventoryService.issue_fefo(db, scope.user, body.product_id, body.facility_id, body.quantity, body.reason,
                                        body.reference)
    return [{**MovementOut.model_validate(m).model_dump(), "batch_number": m.batch.batch_number} for m in moves]


@inventory.get("/movements", response_model=Page[MovementOut])
def movements(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
              facility_id: Optional[uuid.UUID] = None, batch_id: Optional[uuid.UUID] = None,
              movement_type: Optional[MovementType] = None, days: Optional[int] = Query(None, ge=1, le=3650),
              db: Session = Depends(get_db), scope: AccessScope = Depends(require_permission("inventory.view"))):
    scope.ensure_requested(facility_id)
    q = scope.apply(db.query(InventoryMovement), InventoryMovement.facility_id)
    if facility_id:
        q = q.filter(InventoryMovement.facility_id == facility_id)
    if batch_id:
        q = q.filter(InventoryMovement.batch_id == batch_id)
    if movement_type:
        q = q.filter(InventoryMovement.movement_type == movement_type)
    if days:
        q = q.filter(InventoryMovement.created_at >= datetime.now(timezone.utc) - timedelta(days=days))
    items, total = paginate(q.order_by(InventoryMovement.created_at.desc()), page, page_size)
    return {"items": [{**MovementOut.model_validate(m).model_dump(), "batch_number": m.batch.batch_number}
                      for m in items], "total": total, "page": page, "page_size": page_size}


@inventory.get("/summary")
def summary(facility_id: Optional[uuid.UUID] = None, db: Session = Depends(get_db),
            scope: AccessScope = Depends(require_permission("inventory.view"))):
    scope.ensure_requested(facility_id)
    from app.services.analytics import stock_overview
    return stock_overview(db, scope, facility_id)
