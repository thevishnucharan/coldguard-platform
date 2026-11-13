"""Vaccine inventory & batch traceability.

Invariants
* `Batch.current_quantity` only changes here, and every change writes one immutable
  InventoryMovement row with quantity_change and quantity_after (a running ledger).
* Multi-record changes (transfer, FEFO issue) happen in one DB transaction.
* Quarantined / expired / discarded stock cannot be issued or transferred.
* Release and disposal of quarantined stock require `batches.release` / `batches.dispose`
  (supervisor) — enforced in the router; this module records who decided and why.
* Nothing here is ever triggered automatically by ML.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.base import as_utc
from app.models import Batch, InventoryMovement, Product, StorageUnit, User
from app.models.enums import BatchStatus, MovementType, StorageUnitStatus
from app.services.audit import log_audit

ISSUABLE = (BatchStatus.ACTIVE,)


def _now():
    return datetime.now(timezone.utc)


def _bad(msg, code=400):
    raise HTTPException(status_code=code, detail=msg)


class InventoryService:
    # ------------------------------------------------------------------ ledger primitive
    @staticmethod
    def _move(db: Session, batch: Batch, mtype: MovementType, change: int, user: Optional[User], *,
              reason: Optional[str] = None, reference: Optional[str] = None, from_unit=None, to_unit=None,
              status_after: Optional[BatchStatus] = None, incident_id=None) -> InventoryMovement:
        new_qty = batch.current_quantity + change
        if new_qty < 0:
            _bad(f"Insufficient quantity in batch {batch.batch_number} (available {batch.current_quantity})")
        before = batch.status
        batch.current_quantity = new_qty
        if status_after is not None:
            batch.status = status_after
        elif new_qty == 0 and batch.status == BatchStatus.ACTIVE:
            batch.status = BatchStatus.DEPLETED
            batch.end_time = _now()
        m = InventoryMovement(
            batch_id=batch.id, facility_id=batch.facility_id, movement_type=mtype, quantity_change=change,
            quantity_after=new_qty, from_storage_unit_id=from_unit, to_storage_unit_id=to_unit,
            status_before=before.value, status_after=batch.status.value, reason=reason, reference=reference,
            incident_id=incident_id, performed_by=user.id if user else None,
            performed_by_name=user.name if user else "system")
        db.add(m)
        return m

    @staticmethod
    def _unit(db: Session, unit_id) -> StorageUnit:
        unit = db.get(StorageUnit, unit_id)
        if not unit:
            _bad("Storage unit not found", 404)
        if unit.status != StorageUnitStatus.ACTIVE:
            _bad(f"Storage unit {unit.unit_code} is {unit.status.value}")
        return unit

    # ------------------------------------------------------------------ receipt
    @classmethod
    def receive(cls, db: Session, user: User, *, batch_number: str, product_id, storage_unit_id, quantity: int,
                expiry_date: datetime, manufacturing_date: Optional[datetime] = None, supplier: Optional[str] = None,
                manufacturer: Optional[str] = None, reference: Optional[str] = None, scope=None) -> Batch:
        if quantity <= 0:
            _bad("Quantity received must be positive")
        product = db.get(Product, product_id)
        if not product:
            _bad("Product not found", 404)
        unit = cls._unit(db, storage_unit_id)
        if scope is not None:
            scope.ensure(unit.facility_id, not_found="Storage unit not found")
        if db.query(Batch).filter(Batch.batch_number == batch_number).first():
            _bad("A batch with this batch number already exists", 409)
        expiry = as_utc(expiry_date)
        if expiry <= _now():
            _bad("Cannot receive stock that is already expired")
        if manufacturing_date and as_utc(manufacturing_date) >= expiry:
            _bad("Manufacturing date must be before expiry date")
        # Policy check: product storage range must be compatible with the unit's approved range
        if product.min_temperature > unit.effective_max or product.max_temperature < unit.effective_min:
            _bad(f"Product requires {product.min_temperature}–{product.max_temperature}°C; unit {unit.unit_code} is "
                 f"approved for {unit.effective_min}–{unit.effective_max}°C")
        now = _now()
        batch = Batch(batch_number=batch_number, product_id=product.id, storage_unit_id=unit.id,
                      facility_id=unit.facility_id, start_time=now, expiry_date=expiry, receipt_date=now,
                      manufacturing_date=manufacturing_date, supplier=supplier,
                      manufacturer=manufacturer or product.manufacturer, quantity_received=quantity,
                      current_quantity=0, status=BatchStatus.ACTIVE)
        db.add(batch)
        db.flush()
        cls._move(db, batch, MovementType.RECEIPT, quantity, user, reference=reference, to_unit=unit.id,
                  reason=f"Received from {supplier or 'supplier'}")
        log_audit(db, user, "STOCK_RECEIVED", "Batch", batch.id,
                  {"batch_number": batch_number, "quantity": quantity, "unit": unit.unit_code},
                  facility_id=unit.facility_id, commit=False)
        db.commit()
        return batch

    # ------------------------------------------------------------------ issue / adjust / transfer
    @classmethod
    def issue(cls, db: Session, batch: Batch, user: User, quantity: int, reason: Optional[str], reference=None,
              enforce_fefo: bool = True) -> InventoryMovement:
        if quantity <= 0:
            _bad("Quantity must be positive")
        if batch.status not in ISSUABLE:
            _bad(f"Batch is {batch.status.value} and cannot be issued")
        if as_utc(batch.expiry_date) <= _now():
            _bad("Batch is expired and cannot be issued")
        if enforce_fefo:
            earlier = cls.fefo_queue(db, batch.product_id, batch.facility_id)
            first = next((b for b in earlier if b.current_quantity > 0), None)
            if first is not None and first.id != batch.id and as_utc(first.expiry_date) < as_utc(batch.expiry_date):
                _bad(f"FEFO: batch {first.batch_number} expires earlier ({as_utc(first.expiry_date).date()}) and must "
                     "be issued first. Provide an override reason to bypass.", 409)
        m = cls._move(db, batch, MovementType.ISSUE, -quantity, user, reason=reason, reference=reference,
                      from_unit=batch.storage_unit_id)
        log_audit(db, user, "STOCK_ISSUED", "Batch", batch.id, {"quantity": quantity, "reason": reason},
                  facility_id=batch.facility_id, commit=False)
        db.commit()
        return m

    @classmethod
    def issue_fefo(cls, db: Session, user: User, product_id, facility_id, quantity: int, reason: Optional[str],
                   reference=None) -> List[InventoryMovement]:
        """Allocate across batches earliest-expiry first, atomically."""
        if quantity <= 0:
            _bad("Quantity must be positive")
        queue = [b for b in cls.fefo_queue(db, product_id, facility_id) if b.current_quantity > 0]
        available = sum(b.current_quantity for b in queue)
        if available < quantity:
            _bad(f"Insufficient usable stock: requested {quantity}, available {available}")
        remaining, moves = quantity, []
        try:
            for b in queue:
                if remaining == 0:
                    break
                take = min(b.current_quantity, remaining)
                moves.append(cls._move(db, b, MovementType.ISSUE, -take, user, reason=reason or "FEFO issue",
                                       reference=reference, from_unit=b.storage_unit_id))
                remaining -= take
            log_audit(db, user, "STOCK_ISSUED_FEFO", "Product", product_id,
                      {"quantity": quantity, "batches": [str(m.batch_id) for m in moves]},
                      facility_id=facility_id, commit=False)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return moves

    @classmethod
    def adjust(cls, db: Session, batch: Batch, user: User, change: int, reason: str) -> InventoryMovement:
        if change == 0:
            _bad("Adjustment cannot be zero")
        if not reason or len(reason.strip()) < 3:
            _bad("A reason is required for stock adjustments")
        m = cls._move(db, batch, MovementType.ADJUSTMENT, change, user, reason=reason)
        log_audit(db, user, "STOCK_ADJUSTED", "Batch", batch.id, {"change": change, "reason": reason},
                  facility_id=batch.facility_id, commit=False)
        db.commit()
        return m

    @classmethod
    def reconcile(cls, db: Session, batch: Batch, user: User, counted: int, reason: Optional[str]) -> Optional[InventoryMovement]:
        if counted < 0:
            _bad("Counted quantity cannot be negative")
        diff = counted - batch.current_quantity
        m = cls._move(db, batch, MovementType.RECONCILIATION, diff, user,
                      reason=reason or f"Physical count {counted} (system {batch.current_quantity})")
        log_audit(db, user, "STOCK_RECONCILED", "Batch", batch.id,
                  {"counted": counted, "difference": diff}, facility_id=batch.facility_id, commit=False)
        db.commit()
        return m

    @classmethod
    def transfer(cls, db: Session, batch: Batch, user: User, to_unit_id, reason: Optional[str], scope=None) -> Batch:
        if batch.status != BatchStatus.ACTIVE:
            _bad(f"Batch is {batch.status.value}; only ACTIVE stock can be transferred")
        target = cls._unit(db, to_unit_id)
        if scope is not None:
            scope.ensure(target.facility_id, not_found="Destination storage unit not found")
        if target.id == batch.storage_unit_id:
            _bad("Batch is already in this storage unit")
        product = batch.product
        if product.min_temperature > target.effective_max or product.max_temperature < target.effective_min:
            _bad("Destination unit's approved range is incompatible with this product")
        qty, src = batch.current_quantity, batch.storage_unit_id
        try:
            cls._move(db, batch, MovementType.TRANSFER_OUT, -qty, user, reason=reason, from_unit=src,
                      to_unit=target.id, status_after=BatchStatus.ACTIVE)
            batch.storage_unit_id = target.id
            batch.facility_id = target.facility_id
            batch.start_time = _now()  # residence in the new unit starts now (for excursion overlap)
            cls._move(db, batch, MovementType.TRANSFER_IN, qty, user, reason=reason, from_unit=src,
                      to_unit=target.id, status_after=BatchStatus.ACTIVE)
            log_audit(db, user, "BATCH_TRANSFERRED", "Batch", batch.id,
                      {"from": str(src), "to": str(target.id), "quantity": qty}, facility_id=target.facility_id,
                      commit=False)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return batch

    # ------------------------------------------------------------------ disposition
    @classmethod
    def quarantine(cls, db: Session, batch: Batch, user: User, reason: str, incident_id=None) -> Batch:
        if batch.status != BatchStatus.ACTIVE:
            _bad(f"Batch is {batch.status.value}; only ACTIVE batches can be quarantined")
        if not reason:
            _bad("A quarantine reason is required")
        batch.quarantine_reason = reason
        cls._move(db, batch, MovementType.QUARANTINE, 0, user, reason=reason, incident_id=incident_id,
                  status_after=BatchStatus.QUARANTINED)
        log_audit(db, user, "BATCH_QUARANTINED", "Batch", batch.id, {"reason": reason},
                  facility_id=batch.facility_id, commit=False)
        db.commit()
        return batch

    @classmethod
    def release(cls, db: Session, batch: Batch, user: User, justification: str, incident_id=None) -> Batch:
        if batch.status != BatchStatus.QUARANTINED:
            _bad("Only QUARANTINED batches can be released")
        if not justification or len(justification.strip()) < 10:
            _bad("A documented release justification (min 10 chars) is required")
        if as_utc(batch.expiry_date) <= _now():
            _bad("Expired stock cannot be released")
        cls._move(db, batch, MovementType.RELEASE, 0, user, reason=justification, incident_id=incident_id,
                  status_after=BatchStatus.ACTIVE)
        log_audit(db, user, "BATCH_RELEASED", "Batch", batch.id, {"justification": justification},
                  category="DISPOSITION", facility_id=batch.facility_id, commit=False)
        db.commit()
        return batch

    @classmethod
    def dispose(cls, db: Session, batch: Batch, user: User, justification: str, incident_id=None) -> Batch:
        if batch.status not in (BatchStatus.QUARANTINED, BatchStatus.EXPIRED):
            _bad("Only QUARANTINED or EXPIRED batches can be disposed")
        if not justification or len(justification.strip()) < 10:
            _bad("A documented disposal justification (min 10 chars) is required")
        cls._move(db, batch, MovementType.DISPOSAL, -batch.current_quantity, user, reason=justification,
                  incident_id=incident_id, status_after=BatchStatus.DISCARDED)
        batch.end_time = _now()
        log_audit(db, user, "BATCH_DISPOSED", "Batch", batch.id, {"justification": justification},
                  category="DISPOSITION", facility_id=batch.facility_id, commit=False)
        db.commit()
        return batch

    # ------------------------------------------------------------------ queries
    @staticmethod
    def fefo_queue(db: Session, product_id, facility_id) -> List[Batch]:
        q = db.query(Batch).filter(Batch.product_id == product_id, Batch.status == BatchStatus.ACTIVE,
                                   Batch.expiry_date > _now())
        if facility_id:
            q = q.filter(Batch.facility_id == facility_id)
        return q.order_by(Batch.expiry_date.asc(), Batch.receipt_date.asc()).all()

    @classmethod
    def mark_expired(cls, db: Session) -> int:
        """Worker job: flag expired ACTIVE stock (status change recorded in the ledger)."""
        n = 0
        for b in db.query(Batch).filter(Batch.status == BatchStatus.ACTIVE, Batch.expiry_date <= _now()).all():
            cls._move(db, b, MovementType.EXPIRY, 0, None, reason="Expiry date reached",
                      status_after=BatchStatus.EXPIRED)
            n += 1
        if n:
            db.commit()
        return n

    @staticmethod
    def expiry_bucket(batch: Batch) -> str:
        days = (as_utc(batch.expiry_date) - _now()).days
        if days < 0:
            return "EXPIRED"
        if days <= 30:
            return "EXPIRES_30D"
        if days <= 90:
            return "EXPIRES_90D"
        return "OK"


def expiring_within(db: Session, days: int, scope) -> List[Batch]:
    q = db.query(Batch).filter(Batch.status == BatchStatus.ACTIVE,
                               Batch.expiry_date <= _now() + timedelta(days=days))
    return scope.apply(q, Batch.facility_id).order_by(Batch.expiry_date).all()
