"""Structured JSON logging with sensitive-value masking.

v1 bug fixed: the formatter looked for `record.extra`, but `logger.info(..., extra={...})`
sets attributes directly on the record, so structured fields were never emitted.
"""
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict

SENSITIVE_KEYS = {"password", "token", "secret", "api_key", "authorization", "access_token", "refresh_token",
                  "device_key", "email"}
_STD = set(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {"message", "asctime", "taskName"}
_PATTERN = re.compile(r"(password|token|secret|api_key|authorization)([=:\s]+)[^\s,\]}]+", re.IGNORECASE)


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _PATTERN.sub(r"\1\2***MASKED***", record.msg)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: Dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _STD or key.startswith("_"):
                continue
            out[key] = "***MASKED***" if key.lower() in SENSITIVE_KEYS else value
        if record.exc_info:
            out["exception"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def setup_logging():
    root = logging.getLogger()
    if getattr(root, "_coldguard_configured", False):
        return
    for h in root.handlers[:]:
        root.removeHandler(h)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SensitiveDataFilter())
    root.addHandler(handler)
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = [handler]
        logging.getLogger(name).propagate = False
    logging.getLogger("uvicorn.access").disabled = True  # replaced by ObservabilityMiddleware
    root._coldguard_configured = True
