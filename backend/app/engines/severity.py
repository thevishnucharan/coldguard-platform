from app.models.enums import ViolationSeverity
from typing import Optional
from sqlalchemy.orm import Session

class SeverityEngine:
    # Default fallback thresholds (used if database configuration is not provided)
    WARNING_MAX_DEV = 2.0
    WARNING_MAX_DUR = 15.0

    HIGH_MAX_DEV = 5.0
    HIGH_MAX_DUR = 60.0

    @classmethod
    def evaluate(cls, deviation: float, duration_mins: float, db: Optional[Session] = None) -> ViolationSeverity:
        """
        Determines the severity of a violation based on its max deviation and total duration.
        Uses database configuration when a session is supplied.
        """
        warn_dev = cls.WARNING_MAX_DEV
        warn_dur = cls.WARNING_MAX_DUR
        high_dev = cls.HIGH_MAX_DEV
        high_dur = cls.HIGH_MAX_DUR

        if db is not None:
            try:
                from app.services.configuration import ConfigurationService
                rules = ConfigurationService.get_severity_rules(db)
                warn_dev = rules.warning_max_dev
                warn_dur = rules.warning_max_dur_mins
                high_dev = rules.high_max_dev
                high_dur = rules.high_max_dur_mins
            except Exception:
                # Fallback to class defaults if any lookup error occurs
                pass

        if deviation >= high_dev or duration_mins >= high_dur:
            return ViolationSeverity.CRITICAL
            
        if deviation >= warn_dev or duration_mins >= warn_dur:
            return ViolationSeverity.HIGH
            
        return ViolationSeverity.WARNING
