from typing import Annotated, ClassVar, List, Optional, Union

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_INSECURE_DEFAULT_SECRET = "dev-only-insecure-secret-change-me-0123456789abcdef"


class Settings(BaseSettings):
    PROJECT_NAME: ClassVar[str] = "ColdGuard API"
    VERSION: ClassVar[str] = "2.0.0"  # build constant — not overridable from .env
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"  # development | test | staging | production

    # Database
    DATABASE_URL: str = "sqlite:///./coldguard.db"

    # Auth & Security
    SECRET_KEY: str = _INSECURE_DEFAULT_SECRET
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    MAX_FAILED_LOGINS: int = 5
    LOCKOUT_MINUTES: int = 15
    # Gateway key for REST telemetry ingestion (header X-Ingest-Key). Empty = disabled.
    INGEST_API_KEY: str = ""

    # NoDecode: accept both 'a,b' and '["a","b"]' (pydantic-settings would JSON-decode first)
    BACKEND_CORS_ORIGINS: Annotated[List[str], NoDecode] = [
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:8080", "http://127.0.0.1:8080",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json
                return [str(i).strip() for i in json.loads(v)]
            return [i.strip() for i in v.split(",") if i.strip()]
        if isinstance(v, list):
            return v
        raise ValueError(v)

    # Rate limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_AUTH_PER_MINUTE: int = 20
    RATE_LIMIT_DEFAULT_PER_MINUTE: int = 600

    # Notifications
    SMTP_PASSWORD: Optional[str] = None
    ALERT_FROM_EMAIL: str = "alerts@coldguard.local"

    # Event backends (preserved from v1)
    EVENT_BACKEND: str = "local"
    AZURE_EVENT_HUB_CONNECTION_STRING: Optional[str] = None
    AZURE_EVENT_HUB_NAME: Optional[str] = None
    AZURE_EVENT_HUB_CONSUMER_GROUP: Optional[str] = "$Default"
    AI_PROVIDER: str = "mock"
    STORAGE_BACKEND: str = "local"
    NOTIFICATION_BACKEND: str = "console"

    # MQTT
    MQTT_ENABLED: bool = False
    MQTT_HOST: str = "localhost"
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""
    MQTT_TOPIC: str = "coldguard/telemetry/#"
    MQTT_CLIENT_ID: str = "coldguard-ingestor"

    # Redis (real-time fan-out between worker and API replicas). Empty = in-process bus.
    REDIS_URL: str = ""

    # Worker
    # When true the API process also runs the scheduler + MQTT ingestor (single-process dev).
    RUN_EMBEDDED_WORKER: bool = True
    WORKER_TICK_SECONDS: int = 30
    WORKER_METRICS_PORT: int = 9101

    # Escalation (defaults; overridable at runtime via system configuration)
    ESCALATE_UNACK_CRITICAL_MINUTES: int = 15
    ESCALATE_LONG_RUNNING_HOURS: int = 24
    ESCALATE_OVERDUE_CA_HOURS: int = 48

    # Telemetry retention
    TELEMETRY_RETENTION_DAYS: int = 365
    RETENTION_PURGE_ENABLED: bool = False

    # ML
    ML_ENABLED: bool = True
    ML_PATTERN_WINDOW_MINUTES: int = 30
    ML_PATTERN_MIN_ANOMALIES: int = 3

    # Demo mode
    DEMO_MODE: bool = True
    SIMULATION_ENABLED: bool = True

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def _refuse_insecure_production(self):
        if self.ENVIRONMENT.lower() in ("production", "prod", "staging"):
            if self.SECRET_KEY == _INSECURE_DEFAULT_SECRET or len(self.SECRET_KEY) < 32:
                raise ValueError("SECRET_KEY must be set to a strong value (>=32 chars) outside development")
            if self.DEMO_MODE:
                raise ValueError("DEMO_MODE must be false in staging/production")
            insecure = [o for o in self.BACKEND_CORS_ORIGINS
                        if not o.startswith("https://") and "localhost" not in o and "127.0.0.1" not in o]
            if insecure:
                raise ValueError(f"BACKEND_CORS_ORIGINS must use https outside development: {insecure}")
        if "*" in self.BACKEND_CORS_ORIGINS:
            # credentials are allowed, so a wildcard origin would let any site act as the user
            raise ValueError("BACKEND_CORS_ORIGINS must list explicit origins; '*' is not allowed")
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


settings = Settings()
