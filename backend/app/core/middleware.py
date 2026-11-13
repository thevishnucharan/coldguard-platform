import logging
import threading
import time
import uuid
from collections import defaultdict
from typing import Dict, List, Tuple

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.metrics import HTTP_ERRORS, HTTP_LATENCY, HTTP_REQUESTS

logger = logging.getLogger("coldguard.http")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """OWASP security headers (preserved from v1)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        h = response.headers
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "strict-origin-when-cross-origin"
        h["Permissions-Policy"] = "geolocation=(), camera=(), microphone=(), payment=()"
        if settings.ENVIRONMENT.lower() in ("production", "prod", "staging"):
            h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path in ("/docs", "/redoc", "/openapi.json"):
            h["Content-Security-Policy"] = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                                            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                                            "img-src 'self' data: https://fastapi.tiangolo.com; frame-ancestors 'none';")
        else:
            h["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none';"
        return response


class InMemoryRateLimiter:
    """Sliding-window limiter per key (per-process; put a shared limiter at the ingress for
    multi-replica deployments — see docs/SECURITY.md)."""

    def __init__(self):
        self._requests: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_rate_limited(self, key: str, max_requests: int, window_seconds: int = 60) -> Tuple[bool, int]:
        now = time.time()
        with self._lock:
            recent = [t for t in self._requests[key] if t > now - window_seconds]
            self._requests[key] = recent
            if len(recent) >= max_requests:
                return True, max(1, int(window_seconds - (now - recent[0])))
            recent.append(now)
            return False, 0

    def reset(self):
        with self._lock:
            self._requests.clear()


class RedisRateLimiter:
    """Fixed-window limiter shared by all API processes/replicas (used when REDIS_URL is set).
    Falls back to the in-memory limiter if Redis is unreachable (fail-open on the shared
    store, never fail-closed for the whole API)."""

    def __init__(self, url: str, fallback: InMemoryRateLimiter):
        import redis
        self.client = redis.Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)
        self.fallback = fallback

    def is_rate_limited(self, key: str, max_requests: int, window_seconds: int = 60) -> Tuple[bool, int]:
        window = int(time.time() // window_seconds)
        rkey = f"coldguard:rl:{key}:{window}"
        try:
            pipe = self.client.pipeline()
            pipe.incr(rkey)
            pipe.expire(rkey, window_seconds + 1)
            count = pipe.execute()[0]
        except Exception:
            return self.fallback.is_rate_limited(key, max_requests, window_seconds)
        if count > max_requests:
            return True, max(1, window_seconds - int(time.time() % window_seconds))
        return False, 0

    def reset(self):
        self.fallback.reset()


limiter = InMemoryRateLimiter()
if settings.REDIS_URL:
    try:
        limiter = RedisRateLimiter(settings.REDIS_URL, InMemoryRateLimiter())
    except Exception as _exc:  # redis package missing / bad URL
        logger.warning("Redis rate limiter unavailable (%s); using in-memory limiter", _exc)


class RateLimitingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limiter_instance: InMemoryRateLimiter = limiter):
        super().__init__(app)
        self.limiter = limiter_instance

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)
        path = request.url.path
        if path in ("/health", "/api/v1/health", "/metrics", "/ready"):
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        if ip == "testclient" and not request.headers.get("X-Test-Rate-Limit"):
            return await call_next(request)
        # Strict bucket only for password login (brute-force target). Refresh tokens are 384-bit
        # random values and are refreshed on every page load, so they use the general bucket.
        if path.startswith("/api/v1/auth/login"):
            key, limit = f"auth:{ip}", settings.RATE_LIMIT_AUTH_PER_MINUTE
        else:
            key, limit = f"api:{ip}", settings.RATE_LIMIT_DEFAULT_PER_MINUTE
        limited, retry = self.limiter.is_rate_limited(key, limit)
        if limited:
            logger.warning("Rate limit exceeded", extra={"client_ip": ip, "http_path": path})
            return JSONResponse(status_code=429, content={"detail": "Too many requests. Please try again later."},
                                headers={"Retry-After": str(retry)})
        return await call_next(request)


def _route_template(request: Request) -> str:
    """Bounded-cardinality label: the request path with path-parameter values replaced by
    their names (e.g. /api/v1/incidents/{incident_id}); 'unmatched' for 404s."""
    if request.scope.get("route") is None:
        return "unmatched"
    path = request.url.path
    for name, value in (request.path_params or {}).items():
        path = path.replace(str(value), "{" + name + "}")
    return path


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Structured access log + Prometheus RED metrics (route template, not raw path, to keep
    label cardinality bounded and avoid leaking IDs)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            elapsed = time.perf_counter() - start
            template = _route_template(request)
            if template != "/metrics":
                HTTP_REQUESTS.labels(request.method, template, str(status)).inc()
                HTTP_LATENCY.labels(request.method, template).observe(elapsed)
                if status >= 500:
                    HTTP_ERRORS.labels(template).inc()
                logger.info("request", extra={"request_id": request_id, "http_method": request.method,
                                              "http_route": template, "http_status": status,
                                              "duration_ms": round(elapsed * 1000, 1)})
