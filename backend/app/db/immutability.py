"""ORM-level guards making ledger tables append-only.

AuditLog, IncidentEvent and InventoryMovement rows can be inserted but never updated or
deleted through the application. (Database-level enforcement — revoking UPDATE/DELETE
from the app role — is documented in docs/SECURITY.md for production.)
"""
from sqlalchemy import event

from app.models.audit import AuditLog
from app.models.incident import IncidentEvent
from app.models.product import InventoryMovement


class ImmutableRecordError(RuntimeError):
    pass


def _block(kind: str):
    def _guard(mapper, connection, target):
        raise ImmutableRecordError(f"{type(target).__name__} records are immutable ({kind} blocked)")
    return _guard


for _model in (AuditLog, IncidentEvent, InventoryMovement):
    event.listen(_model, "before_update", _block("update"))
    event.listen(_model, "before_delete", _block("delete"))
