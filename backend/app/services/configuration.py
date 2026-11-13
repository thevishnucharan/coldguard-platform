from sqlalchemy.orm import Session
from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional
from fastapi import HTTPException

from app.models.configuration import SystemConfiguration
from app.models.user import User
from app.services.audit import log_audit
from app.schemas.configuration import (
    TemperatureThresholdsConfig,
    SeverityRulesConfig,
    NotificationRulesConfig,
)

DEFAULT_CONFIGS: Dict[str, Dict[str, Any]] = {
    "temperature_thresholds": {
        "value": TemperatureThresholdsConfig().model_dump(),
        "description": "Standard cold-chain storage threshold parameters (Min: 2°C, Max: 8°C)",
    },
    "severity_rules": {
        "value": SeverityRulesConfig().model_dump(),
        "description": "Violation excursion limits for warning, high, and critical classifications",
    },
    "notification_rules": {
        "value": NotificationRulesConfig().model_dump(),
        "description": "Notification dispatch rules and recipient configuration per severity level",
    },
}

class ConfigurationService:
    @classmethod
    def ensure_defaults(cls, db: Session) -> None:
        """Seed default configuration values into the database if missing."""
        seeded = False
        for key, config_meta in DEFAULT_CONFIGS.items():
            existing = db.query(SystemConfiguration).filter(SystemConfiguration.key == key).first()
            if not existing:
                record = SystemConfiguration(
                    key=key,
                    value=config_meta["value"],
                    description=config_meta["description"],
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(record)
                seeded = True
        if seeded:
            db.commit()

    @classmethod
    def get_all(cls, db: Session) -> List[SystemConfiguration]:
        cls.ensure_defaults(db)
        return db.query(SystemConfiguration).order_by(SystemConfiguration.key).all()

    @classmethod
    def get(cls, db: Session, key: str) -> Optional[SystemConfiguration]:
        cls.ensure_defaults(db)
        return db.query(SystemConfiguration).filter(SystemConfiguration.key == key).first()

    @classmethod
    def get_temperature_thresholds(cls, db: Session) -> TemperatureThresholdsConfig:
        config = cls.get(db, "temperature_thresholds")
        if config and isinstance(config.value, dict):
            try:
                return TemperatureThresholdsConfig(**config.value)
            except Exception:
                pass
        return TemperatureThresholdsConfig()

    @classmethod
    def get_severity_rules(cls, db: Session) -> SeverityRulesConfig:
        config = cls.get(db, "severity_rules")
        if config and isinstance(config.value, dict):
            try:
                return SeverityRulesConfig(**config.value)
            except Exception:
                pass
        return SeverityRulesConfig()

    @classmethod
    def get_notification_rules(cls, db: Session) -> NotificationRulesConfig:
        config = cls.get(db, "notification_rules")
        if config and isinstance(config.value, dict):
            try:
                return NotificationRulesConfig(**config.value)
            except Exception:
                pass
        return NotificationRulesConfig()

    @classmethod
    def update(
        cls,
        db: Session,
        key: str,
        value: Any,
        current_user: User,
        description: Optional[str] = None,
    ) -> SystemConfiguration:
        cls.ensure_defaults(db)

        # Validate typed config if known
        validated_value = value
        if key == "temperature_thresholds":
            if isinstance(value, dict):
                try:
                    validated_value = TemperatureThresholdsConfig(**value).model_dump()
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Invalid temperature threshold configuration: {str(e)}")
            else:
                raise HTTPException(status_code=400, detail="Temperature thresholds must be a dictionary object")
        elif key == "severity_rules":
            if isinstance(value, dict):
                try:
                    validated_value = SeverityRulesConfig(**value).model_dump()
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Invalid severity rule configuration: {str(e)}")
            else:
                raise HTTPException(status_code=400, detail="Severity rules must be a dictionary object")
        elif key == "notification_rules":
            if isinstance(value, dict):
                try:
                    validated_value = NotificationRulesConfig(**value).model_dump()
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Invalid notification rule configuration: {str(e)}")
            else:
                raise HTTPException(status_code=400, detail="Notification rules must be a dictionary object")

        config = db.query(SystemConfiguration).filter(SystemConfiguration.key == key).first()
        prev_value = None

        if config:
            prev_value = config.value
            config.value = validated_value
            if description is not None:
                config.description = description
            config.updated_at = datetime.now(timezone.utc)
        else:
            config = SystemConfiguration(
                key=key,
                value=validated_value,
                description=description or DEFAULT_CONFIGS.get(key, {}).get("description"),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(config)

        db.commit()
        db.refresh(config)

        # Generate deterministic UUID for audit log entity_id
        entity_id = uuid.uuid5(uuid.NAMESPACE_OID, f"sys_config_{key}")
        log_audit(
            db=db,
            user=current_user,
            action="UPDATE",
            entity_type="SystemConfiguration",
            entity_id=entity_id,
            details={
                "key": key,
                "previous_value": prev_value,
                "new_value": validated_value,
                "description": config.description,
            },
        )

        return config
