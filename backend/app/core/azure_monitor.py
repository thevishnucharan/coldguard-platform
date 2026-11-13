"""Optional Azure Monitor (Application Insights) export via OpenTelemetry.

Runs ALONGSIDE Prometheus/Grafana, never instead of them:
  * no-op unless APPLICATIONINSIGHTS_CONNECTION_STRING is set (Azure overlay: from Key Vault)
  * no-op (with a warning) if the optional package is not installed — build the image with
    `--build-arg INSTALL_AZURE_MONITOR=true` (requirements-azure.txt) to enable it
  * the same SensitiveDataFilter used for stdout masks secrets in exported log messages

Requests, dependencies (SQLAlchemy, Redis, HTTP), exceptions and `coldguard*` logs then appear
in Application Insights; infrastructure metrics come from AKS Container Insights and managed
Prometheus.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)
_configured = False


def configure_azure_monitor(service_name: str = "coldguard-api") -> bool:
    """Returns True when exporting to Application Insights was enabled."""
    global _configured
    if _configured:
        return True
    conn = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
    if not conn:
        return False
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor as _configure
    except ImportError:
        logger.warning("APPLICATIONINSIGHTS_CONNECTION_STRING is set but azure-monitor-opentelemetry is not "
                       "installed; Application Insights export disabled (build with INSTALL_AZURE_MONITOR=true)")
        return False
    os.environ.setdefault("OTEL_SERVICE_NAME", service_name)
    # sampling keeps cost predictable; errors are always kept by the exporter
    _configure(connection_string=conn, logger_name="coldguard",
               sampling_ratio=float(os.environ.get("AZURE_MONITOR_SAMPLING_RATIO", "0.25")))
    from app.core.logging import SensitiveDataFilter
    for h in logging.getLogger("coldguard").handlers:
        h.addFilter(SensitiveDataFilter())
    _configured = True
    logger.info("Azure Monitor (Application Insights) export enabled for %s", service_name)
    return True
