"""Scheduled escalation rules (run by the background worker, never inside API requests).

Rules (thresholds configurable via system configuration key `escalation_rules`):
  UNACK_CRITICAL       CRITICAL incident not acknowledged within N minutes
  LONG_RUNNING         any incident active for more than N hours
  OVERDUE_CORRECTIVE   approved corrective action not implemented by its due date,
                       or proposal waiting for supervisor review > N hours
  REPEATED_EXCURSIONS  incident received >= N repeated excursion signals
Each rule escalates an incident at most once per level (tracked through incident events).
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import as_utc
from app.models import CorrectiveAction, Incident, IncidentEvent, SystemConfiguration
from app.models.enums import ACTIVE_INCIDENT_STATUSES, CorrectiveActionStatus, IncidentStatus, ViolationSeverity
from app.services.incident import IncidentService

logger = logging.getLogger(__name__)

DEFAULT_RULES = {
    "unack_critical_minutes": settings.ESCALATE_UNACK_CRITICAL_MINUTES,
    "long_running_hours": settings.ESCALATE_LONG_RUNNING_HOURS,
    "overdue_review_hours": settings.ESCALATE_OVERDUE_CA_HOURS,
    "repeated_excursion_signals": 3,
    "max_level": 3,
}


def rules(db: Session) -> dict:
    row = db.get(SystemConfiguration, "escalation_rules")
    merged = dict(DEFAULT_RULES)
    if row and isinstance(row.value, dict):
        merged.update({k: v for k, v in row.value.items() if k in DEFAULT_RULES})
    return merged


def _already(db: Session, inc: Incident, rule: str) -> bool:
    return db.query(IncidentEvent).filter(IncidentEvent.incident_id == inc.id, IncidentEvent.event_type == "ESCALATED",
                                          IncidentEvent.data.isnot(None)).filter(
        IncidentEvent.note.like(f"[{rule}]%")).first() is not None


def run_escalations(db: Session, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    r = rules(db)
    done = {"UNACK_CRITICAL": 0, "LONG_RUNNING": 0, "OVERDUE_CORRECTIVE": 0, "REPEATED_EXCURSIONS": 0}
    active = db.query(Incident).filter(Incident.status.in_(ACTIVE_INCIDENT_STATUSES)).all()

    def esc(inc, rule, reason):
        if inc.escalation_level >= r["max_level"] or _already(db, inc, rule):
            return
        IncidentService.escalate(db, inc.id, None, f"[{rule}] {reason}", rule=rule)
        done[rule] += 1

    for inc in active:
        age_min = (now - as_utc(inc.created_at)).total_seconds() / 60
        if (inc.severity == ViolationSeverity.CRITICAL and inc.status in (IncidentStatus.DETECTED, IncidentStatus.OPEN)
                and age_min >= r["unack_critical_minutes"]):
            esc(inc, "UNACK_CRITICAL", f"Critical incident unacknowledged for {age_min:.0f} min")
        if age_min >= r["long_running_hours"] * 60:
            esc(inc, "LONG_RUNNING", f"Incident active for {age_min / 60:.1f} h")
        repeats = db.query(IncidentEvent).filter(IncidentEvent.incident_id == inc.id,
                                                 IncidentEvent.event_type == "REPEATED_SIGNAL").count()
        if repeats >= r["repeated_excursion_signals"]:
            esc(inc, "REPEATED_EXCURSIONS", f"{repeats} repeated signals while incident open")

    for ca in db.query(CorrectiveAction).join(Incident).filter(Incident.status.in_(ACTIVE_INCIDENT_STATUSES)).all():
        if ca.status == CorrectiveActionStatus.APPROVED and ca.due_date and as_utc(ca.due_date) < now:
            esc(ca.incident, "OVERDUE_CORRECTIVE", "Approved corrective action past its due date")
        elif (ca.status == CorrectiveActionStatus.PROPOSED
              and (now - as_utc(ca.created_at)).total_seconds() / 3600 >= r["overdue_review_hours"]):
            esc(ca.incident, "OVERDUE_CORRECTIVE", "Corrective action proposal awaiting supervisor review")
    return done
