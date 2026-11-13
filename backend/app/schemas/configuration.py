from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Any, Dict, List, Optional
from datetime import datetime

class TemperatureThresholdsConfig(BaseModel):
    default_min_temp: float = Field(2.0, description="Minimum allowable temperature in °C")
    default_max_temp: float = Field(8.0, description="Maximum allowable temperature in °C")
    unit: str = Field("°C", description="Temperature measurement unit")
    warning_tolerance: float = Field(0.5, ge=0.0, description="Tolerance before triggering warning (°C)")
    critical_tolerance: float = Field(2.0, ge=0.0, description="Tolerance before critical violation (°C)")

    @model_validator(mode="after")
    def validate_range(self) -> "TemperatureThresholdsConfig":
        if self.default_min_temp >= self.default_max_temp:
            raise ValueError("default_min_temp must be less than default_max_temp")
        return self

class SeverityRulesConfig(BaseModel):
    warning_max_dev: float = Field(2.0, gt=0.0, description="Maximum deviation limit for WARNING severity (°C)")
    warning_max_dur_mins: float = Field(15.0, gt=0.0, description="Maximum duration limit for WARNING severity (minutes)")
    high_max_dev: float = Field(5.0, gt=0.0, description="Maximum deviation limit for HIGH severity (°C)")
    high_max_dur_mins: float = Field(60.0, gt=0.0, description="Maximum duration limit for HIGH severity (minutes)")

    @model_validator(mode="after")
    def validate_severity_thresholds(self) -> "SeverityRulesConfig":
        if self.warning_max_dev >= self.high_max_dev:
            raise ValueError("warning_max_dev must be less than high_max_dev")
        if self.warning_max_dur_mins >= self.high_max_dur_mins:
            raise ValueError("warning_max_dur_mins must be less than high_max_dur_mins")
        return self

class NotificationRulesConfig(BaseModel):
    rules: Dict[str, List[str]] = Field(
        default_factory=lambda: {
            "WARNING": ["DASHBOARD"],
            "HIGH": ["DASHBOARD", "EMAIL"],
            "CRITICAL": ["DASHBOARD", "EMAIL"],
        },
        description="Map of ViolationSeverity to list of alert notification channels (DASHBOARD, EMAIL)",
    )
    default_alert_email: str = Field("alerts@coldguard.local", description="Primary alert recipient email")
    default_admin_email: str = Field("admin@coldguard.local", description="Admin contact email")
    enable_email_alerts: bool = Field(True, description="Enable email alert dispatching")
    enable_dashboard_alerts: bool = Field(True, description="Enable live dashboard notifications")
    escalation_time_mins: int = Field(30, ge=1, description="Escalation threshold if unacknowledged (minutes)")

class SystemConfigurationUpdate(BaseModel):
    value: Any = Field(..., description="Configuration value object or primitive")
    description: Optional[str] = Field(None, description="Optional description of the configuration key")

class SystemConfigurationResponse(BaseModel):
    key: str
    value: Any
    description: Optional[str] = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
