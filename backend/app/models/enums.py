import enum


class Role(str, enum.Enum):
    ADMIN = "ADMIN"            # System Administrator
    OPERATOR = "OPERATOR"      # Facility Operator
    SUPERVISOR = "SUPERVISOR"  # District / Regional Supervisor
    TECHNICIAN = "TECHNICIAN"  # Maintenance Technician
    AUDITOR = "AUDITOR"        # Auditor / Compliance Officer


class StorageUnitStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    MAINTENANCE = "MAINTENANCE"
    INACTIVE = "INACTIVE"


class SensorStatus(str, enum.Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    CALIBRATING = "CALIBRATING"
    ERROR = "ERROR"
    DECOMMISSIONED = "DECOMMISSIONED"
    PROVISIONED = "PROVISIONED"  # registered, never reported


class BatchStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    QUARANTINED = "QUARANTINED"
    EXPIRED = "EXPIRED"
    DEPLETED = "DEPLETED"
    DISCARDED = "DISCARDED"
    COMPLETED = "COMPLETED"  # legacy value from original schema (== DEPLETED)


class ViolationSeverity(str, enum.Enum):
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ViolationStatus(str, enum.Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class IncidentStatus(str, enum.Enum):
    DETECTED = "DETECTED"
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    CORRECTIVE_ACTION_PENDING = "CORRECTIVE_ACTION_PENDING"
    UNDER_REVIEW = "UNDER_REVIEW"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


ACTIVE_INCIDENT_STATUSES = (
    IncidentStatus.DETECTED,
    IncidentStatus.OPEN,
    IncidentStatus.ACKNOWLEDGED,
    IncidentStatus.INVESTIGATING,
    IncidentStatus.CORRECTIVE_ACTION_PENDING,
    IncidentStatus.UNDER_REVIEW,
)


class IncidentType(str, enum.Enum):
    TEMPERATURE_EXCURSION = "TEMPERATURE_EXCURSION"
    SENSOR_OFFLINE = "SENSOR_OFFLINE"
    MISSING_TELEMETRY = "MISSING_TELEMETRY"
    ABNORMAL_PATTERN = "ABNORMAL_PATTERN"   # ML / statistical decision-support signal
    EQUIPMENT_FAILURE = "EQUIPMENT_FAILURE"
    SENSOR_FAULT = "SENSOR_FAULT"


class CorrectiveActionStatus(str, enum.Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVISION_REQUESTED = "REVISION_REQUESTED"
    IMPLEMENTED = "IMPLEMENTED"
    VERIFIED = "VERIFIED"


class AlertStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class AnomalySeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SensorHealthState(str, enum.Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    OFFLINE = "OFFLINE"


class MovementType(str, enum.Enum):
    RECEIPT = "RECEIPT"
    ISSUE = "ISSUE"
    ADJUSTMENT = "ADJUSTMENT"
    TRANSFER_OUT = "TRANSFER_OUT"
    TRANSFER_IN = "TRANSFER_IN"
    QUARANTINE = "QUARANTINE"
    RELEASE = "RELEASE"
    DISPOSAL = "DISPOSAL"
    EXPIRY = "EXPIRY"
    RECONCILIATION = "RECONCILIATION"


class MaintenanceStatus(str, enum.Enum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    VERIFIED = "VERIFIED"
    CLOSED = "CLOSED"


ACTIVE_MAINTENANCE_STATUSES = (
    MaintenanceStatus.OPEN,
    MaintenanceStatus.ASSIGNED,
    MaintenanceStatus.IN_PROGRESS,
)


class MaintenancePriority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class MaintenanceTrigger(str, enum.Enum):
    MANUAL = "MANUAL"          # raised by a person
    RULE = "RULE"              # rule-based trigger (thresholds / counts) — NOT predictive
    ML = "ML"                  # model-based signal (decision support)
    PREVENTIVE = "PREVENTIVE"  # scheduled preventive maintenance


class MaintenanceType(str, enum.Enum):
    CORRECTIVE = "CORRECTIVE"
    PREVENTIVE = "PREVENTIVE"
    CALIBRATION = "CALIBRATION"
    INSPECTION = "INSPECTION"
    REPLACEMENT = "REPLACEMENT"


class CalibrationResult(str, enum.Enum):
    PASS = "PASS"
    ADJUSTED = "ADJUSTED"
    FAIL = "FAIL"


class NotificationLevel(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class UnitHealth(str, enum.Enum):
    """Computed (not stored) operational state of a storage unit."""
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    OFFLINE = "OFFLINE"
    MISSING_TELEMETRY = "MISSING_TELEMETRY"
    NO_DATA = "NO_DATA"
    INACTIVE = "INACTIVE"


class RoutePlanStatus(str, enum.Enum):
    PROPOSED = "PROPOSED"      # generated, awaiting an authorised decision
    APPROVED = "APPROVED"      # decision recorded; facilities notified to execute transfers
    CANCELLED = "CANCELLED"    # rejected or superseded
