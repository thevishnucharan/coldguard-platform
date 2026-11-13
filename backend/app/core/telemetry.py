"""Legacy (v1) metric helper, kept for compatibility. Counts are also logged as
structured JSON. New code should use app.core.metrics (Prometheus)."""
import logging
import threading
from typing import Any, Dict

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_metrics_store: Dict[str, float] = {}

_SENSITIVE = ("secret", "token", "password", "email")


def track_metric(name: str, value: float = 1.0, properties: Dict[str, Any] = None):
    with _lock:
        _metrics_store[name] = _metrics_store.get(name, 0.0) + value
    extra = {"metric_name": name, "metric_value": value}
    if properties:
        extra["metric_properties"] = {k: v for k, v in properties.items() if not any(s in k.lower() for s in _SENSITIVE)}
    logger.debug("metric %s=%s", name, value, extra=extra)


def get_metrics() -> Dict[str, float]:
    with _lock:
        return dict(_metrics_store)


def reset_metrics():
    with _lock:
        _metrics_store.clear()
