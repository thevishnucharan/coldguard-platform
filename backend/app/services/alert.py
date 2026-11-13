"""External alert dispatch (console / SMTP) — preserved from v1, now driven by the
incident's own severity so non-excursion incidents (offline, ML pattern) also alert."""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.adapters.notification import ConsoleNotificationProvider, EmailNotificationProvider
from app.config.alerts import ALERT_RULES, DEFAULT_ALERT_EMAIL
from app.core.telemetry import track_metric
from app.models.enums import AlertStatus
from app.models.incident import Alert, Incident

logger = logging.getLogger(__name__)


class AlertService:
    @classmethod
    def get_providers(cls):
        return {"DASHBOARD": ConsoleNotificationProvider(), "EMAIL": EmailNotificationProvider()}

    @classmethod
    def trigger_alerts_for_incident(cls, db: Session, incident: Incident):
        severity = incident.severity
        try:
            from app.services.configuration import ConfigurationService
            cfg = ConfigurationService.get_notification_rules(db)
            alert_types = cfg.rules.get(severity.value, [])
            recipient = cfg.default_alert_email or DEFAULT_ALERT_EMAIL
        except Exception:
            alert_types = ALERT_RULES.get(severity, [])
            recipient = DEFAULT_ALERT_EMAIL

        unit_code = incident.storage_unit.unit_code if incident.storage_unit else "n/a"
        providers = cls.get_providers()
        for alert_type in alert_types:
            provider = providers.get(alert_type)
            if not provider:
                continue
            record = Alert(
                incident_id=incident.id, alert_type=alert_type, recipient=recipient, status=AlertStatus.PENDING,
                message=(f"[{severity.value}] ColdGuard {incident.incident_type.value}: {incident.incident_number} "
                         f"on storage unit {unit_code}. {incident.title or ''}"),
            )
            db.add(record)
            db.commit()
            ok = provider.send(recipient=recipient, subject=f"ColdGuard Alert: {incident.incident_number}",
                               message=record.message)
            record.status = AlertStatus.SENT if ok else AlertStatus.FAILED
            record.sent_at = datetime.now(timezone.utc) if ok else None
            db.commit()
            if not ok:
                logger.error("Failed to send %s alert for %s", alert_type, incident.incident_number)
                track_metric("alert_failures", 1.0, {"alert_type": alert_type})
