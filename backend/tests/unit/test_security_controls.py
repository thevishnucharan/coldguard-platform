"""PART 18 / PART 17 controls not covered elsewhere: CORS hardening, configuration refusal outside
development, log masking of personal data and secrets, and metrics aggregation across workers."""
import json
import logging
import os
import subprocess
import sys

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import JsonFormatter, SensitiveDataFilter

BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STRONG = "x" * 48


def _settings(**kw):
    return Settings(_env_file=None, **kw)


def test_wildcard_cors_origin_is_refused_everywhere():
    with pytest.raises(ValidationError, match="explicit origins"):
        _settings(BACKEND_CORS_ORIGINS="*")
    with pytest.raises(ValidationError):
        _settings(BACKEND_CORS_ORIGINS="https://a.example,*", ENVIRONMENT="production", SECRET_KEY=STRONG, DEMO_MODE=False)


def test_production_requires_https_origins_strong_secret_and_no_demo_mode():
    ok = _settings(ENVIRONMENT="production", SECRET_KEY=STRONG, DEMO_MODE=False,
                   BACKEND_CORS_ORIGINS="https://coldguard.example")
    assert ok.BACKEND_CORS_ORIGINS == ["https://coldguard.example"]
    with pytest.raises(ValidationError, match="https"):
        _settings(ENVIRONMENT="production", SECRET_KEY=STRONG, DEMO_MODE=False, BACKEND_CORS_ORIGINS="http://evil.example")
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        _settings(ENVIRONMENT="staging", SECRET_KEY="short", DEMO_MODE=False, BACKEND_CORS_ORIGINS="https://a.example")
    with pytest.raises(ValidationError, match="DEMO_MODE"):
        _settings(ENVIRONMENT="production", SECRET_KEY=STRONG, DEMO_MODE=True, BACKEND_CORS_ORIGINS="https://a.example")
    # development may use plain-http localhost origins
    assert _settings(BACKEND_CORS_ORIGINS="http://localhost:8080").BACKEND_CORS_ORIGINS == ["http://localhost:8080"]


def test_cors_only_reflects_allowed_origins(client):
    allowed = client.options("/api/v1/auth/login", headers={"Origin": "http://localhost:5173",
                                                             "Access-Control-Request-Method": "POST"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    denied = client.options("/api/v1/auth/login", headers={"Origin": "https://evil.example",
                                                            "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in denied.headers


def _render(msg, *args, **extra):
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, msg, args, None)
    for k, v in extra.items():
        setattr(rec, k, v)
    SensitiveDataFilter().filter(rec)
    return json.loads(JsonFormatter().format(rec))


def test_structured_logs_mask_secrets_and_personal_data():
    out = _render("login password=hunter2 token: abc.def", email="nurse@phc.example", access_token="eyJ...",
                  client_ip="10.0.0.1", http_path="/api/v1/auth/login")
    assert "hunter2" not in json.dumps(out) and "abc.def" not in json.dumps(out)
    assert out["email"] == "***MASKED***" and out["access_token"] == "***MASKED***"
    assert out["http_path"] == "/api/v1/auth/login" and out["level"] == "INFO" and "ts" in out


def test_failed_login_log_does_not_contain_email_or_password(client, org, caplog):
    caplog.set_level(logging.INFO)
    client.post("/api/v1/auth/login", data={"username": "op1@t.io", "password": "Wrong-Password-1"})
    text = "\n".join(JsonFormatter().format(r) for r in caplog.records)
    assert "Wrong-Password-1" not in text
    assert "op1@t.io" not in text


_CHILD = """
import os, sys
sys.path.insert(0, {backend!r})
from app.core.metrics import HTTP_REQUESTS, WS_CONNECTIONS
HTTP_REQUESTS.labels(method="GET", route="/x", status="200").inc()
WS_CONNECTIONS.inc()
"""

_PARENT = """
import os, sys
sys.path.insert(0, {backend!r})
from app.core.metrics import metrics_payload
print(metrics_payload().decode())
"""


def test_metrics_aggregate_across_uvicorn_worker_processes(tmp_path):
    env = {**os.environ, "PROMETHEUS_MULTIPROC_DIR": str(tmp_path)}
    for _ in range(2):  # two "uvicorn workers"
        subprocess.run([sys.executable, "-c", _CHILD.format(backend=BACKEND)], env=env, check=True, timeout=60)
    out = subprocess.run([sys.executable, "-c", _PARENT.format(backend=BACKEND)], env=env, check=True,
                         capture_output=True, text=True, timeout=60).stdout
    line = next(x for x in out.splitlines() if x.startswith("coldguard_http_requests_total{"))
    assert line.endswith(" 2.0")
