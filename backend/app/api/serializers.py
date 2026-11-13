"""Model -> response dict helpers (adds display names; keeps routers thin)."""
from datetime import datetime, timezone

from app.db.base import as_utc
from app.models import Batch, CorrectiveAction, Incident, MaintenanceTicket
from app.models.enums import ACTIVE_MAINTENANCE_STATUSES, CorrectiveActionStatus, IncidentStatus
from app.services.incident import IncidentService
from app.services.inventory import InventoryService


def _base(obj, fields):
    return {f: getattr(obj, f) for f in fields}


INCIDENT_FIELDS = ["id", "incident_number", "incident_type", "severity", "status", "title", "description", "source",
                   "is_simulated", "facility_id", "storage_unit_id", "sensor_id", "violation_id", "assigned_to",
                   "root_cause", "corrective_action", "investigation_notes", "ai_summary", "escalation_level",
                   "escalated_at", "escalation_reason", "review_decision", "reviewed_at", "review_notes",
                   "closure_evidence", "vaccine_disposition", "recovery_verified_at", "peak_temperature",
                   "excursion_start", "excursion_end", "created_at", "acknowledged_at", "resolved_at", "closed_at"]


def incident(i: Incident) -> dict:
    d = _base(i, INCIDENT_FIELDS)
    d["facility_name"] = i.facility.name if i.facility else None
    d["storage_unit_code"] = i.storage_unit.unit_code if i.storage_unit else None
    d["sensor_code"] = i.sensor.sensor_code if i.sensor else None
    d["assignee_name"] = i.assignee.name if i.assignee else None
    d["duration_seconds"] = IncidentService.duration_seconds(i)
    if i.violation:
        d["limit_min"], d["limit_max"] = i.violation.allowed_minimum, i.violation.allowed_maximum
    elif i.storage_unit:
        d["limit_min"], d["limit_max"] = i.storage_unit.effective_min, i.storage_unit.effective_max
    return d


def corrective_action(c: CorrectiveAction) -> dict:
    d = _base(c, ["id", "incident_id", "action_type", "description", "root_cause", "status", "proposed_by",
                  "reviewed_by", "review_comment", "reviewed_at", "due_date", "implemented_at", "implementation_notes",
                  "maintenance_ticket_id", "created_at"])
    d["proposer_name"] = c.proposer.name if c.proposer else None
    d["reviewer_name"] = c.reviewer.name if c.reviewer else None
    return d


def available_incident_actions(i: Incident, scope) -> list:
    """What the CURRENT user may do next — drives action buttons; the API re-checks everything."""
    S = IncidentStatus
    acts = []
    has = scope.has
    if i.status in (S.OPEN, S.DETECTED) and has("incidents.acknowledge"):
        acts.append("acknowledge")
    if i.status == S.ACKNOWLEDGED and has("incidents.investigate"):
        acts.append("investigate")
    if i.status not in (S.RESOLVED, S.CLOSED):
        if has("incidents.investigate"):
            acts.append("add_note")
        if has("incidents.escalate"):
            acts.append("escalate")
    if i.status == S.INVESTIGATING and has("corrective_actions.submit"):
        acts.append("propose_corrective_action")
    pending = [c for c in i.corrective_actions if c.status == CorrectiveActionStatus.PROPOSED]
    approved = [c for c in i.corrective_actions if c.status == CorrectiveActionStatus.APPROVED]
    implemented = [c for c in i.corrective_actions if c.status == CorrectiveActionStatus.IMPLEMENTED]
    if pending and has("corrective_actions.approve"):
        acts.append("review_corrective_action")
    if approved and has("corrective_actions.submit"):
        acts.append("implement_corrective_action")
    if i.status == S.CORRECTIVE_ACTION_PENDING and implemented and not pending and has("corrective_actions.submit"):
        acts.append("verify_recovery")
    if i.status == S.UNDER_REVIEW and has("incidents.review"):
        acts.append("review")
    if i.status == S.RESOLVED and has("incidents.review"):
        acts.append("close")
    if i.status not in (S.RESOLVED, S.CLOSED) and has("incidents.review"):
        acts.append("close_false_alarm")
    if has("incidents.assign") and i.status not in (S.RESOLVED, S.CLOSED):
        acts.append("assign")
    if has("maintenance.create") and i.status != S.CLOSED:
        acts.append("create_work_order")
    return acts


def batch(b: Batch) -> dict:
    d = _base(b, ["id", "batch_number", "product_id", "storage_unit_id", "facility_id", "status", "manufacturer",
                  "manufacturing_date", "expiry_date", "receipt_date", "supplier", "quantity_received",
                  "current_quantity", "unit_of_measure", "quarantine_reason", "start_time", "end_time"])
    d["product_name"] = b.product.name if b.product else None
    d["storage_unit_code"] = b.storage_unit.unit_code if b.storage_unit else None
    d["facility_name"] = b.facility.name if b.facility else None
    d["expiry_bucket"] = InventoryService.expiry_bucket(b)
    d["days_to_expiry"] = (as_utc(b.expiry_date) - datetime.now(timezone.utc)).days
    d["excursion_count"] = len(b.incident_associations)
    return d


def ticket(t: MaintenanceTicket) -> dict:
    d = _base(t, ["id", "ticket_number", "facility_id", "storage_unit_id", "sensor_id", "incident_id", "title",
                  "description", "maintenance_type", "priority", "status", "trigger", "trigger_rule", "assigned_to",
                  "requested_by", "due_date", "inspection_results", "repair_notes", "next_maintenance_due",
                  "created_at", "assigned_at", "started_at", "resolved_at", "verified_at", "closed_at"])
    d["facility_name"] = t.facility.name if t.facility else None
    d["storage_unit_code"] = t.storage_unit.unit_code if t.storage_unit else None
    d["sensor_code"] = t.sensor.sensor_code if t.sensor else None
    d["assignee_name"] = t.assignee.name if t.assignee else None
    d["is_overdue"] = bool(t.due_date and as_utc(t.due_date) < datetime.now(timezone.utc)
                           and t.status in ACTIVE_MAINTENANCE_STATUSES)
    return d
