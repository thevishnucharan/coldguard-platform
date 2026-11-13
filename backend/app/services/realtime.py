"""Real-time event fan-out.

Producers (ingestion pipeline, incident service, worker jobs — often running in threads)
call `publish(event_type, data, facility_id)`. Events reach WebSocket clients through:

  * in-process hub (single-process / embedded-worker mode), and
  * Redis pub/sub channel `coldguard:events` when REDIS_URL is set (worker -> API replicas).

The WebSocket layer filters each event against the connected user's facility scope, so a
client never receives data for facilities it cannot access.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from app.core.config import settings

logger = logging.getLogger(__name__)
CHANNEL = "coldguard:events"


def _default(o):
    if isinstance(o, uuid.UUID):
        return str(o)
    if isinstance(o, datetime):
        return o.isoformat()
    if hasattr(o, "value"):
        return o.value
    return str(o)


class _Subscriber:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=500)

    def push(self, event: dict):
        def _put():
            if self.queue.full():  # drop oldest — clients re-sync via REST on reconnect
                try:
                    self.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            self.queue.put_nowait(event)
        try:
            self.loop.call_soon_threadsafe(_put)
        except RuntimeError:
            pass  # loop closed


class RealtimeHub:
    def __init__(self):
        self._subs: Set[_Subscriber] = set()
        self._lock = threading.Lock()
        self._redis = None
        self._redis_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.origin = uuid.uuid4().hex  # identifies this process to ignore its own Redis echoes

    # ---- subscriptions (API side)
    def subscribe(self, loop: asyncio.AbstractEventLoop) -> _Subscriber:
        sub = _Subscriber(loop)
        with self._lock:
            self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: _Subscriber):
        with self._lock:
            self._subs.discard(sub)

    def _dispatch_local(self, event: dict):
        with self._lock:
            subs = list(self._subs)
        for s in subs:
            s.push(event)

    # ---- publishing (any thread)
    def publish(self, event_type: str, data: Dict[str, Any], facility_id: Optional[uuid.UUID] = None,
                user_ids: Optional[list] = None):
        event = {
            "type": event_type,
            "data": json.loads(json.dumps(data, default=_default)),
            "facility_id": str(facility_id) if facility_id else None,
            "user_ids": [str(u) for u in user_ids] if user_ids else None,
            "ts": datetime.now(timezone.utc).isoformat(),
            "origin": self.origin,
        }
        self._dispatch_local(event)
        client = self._get_redis()
        if client is not None:
            try:
                client.publish(CHANNEL, json.dumps(event))
            except Exception as exc:  # pragma: no cover - network
                logger.warning("Redis publish failed: %s", exc)

    # ---- redis bridge
    def _get_redis(self):
        if not settings.REDIS_URL:
            return None
        if self._redis is None:
            try:
                import redis
                self._redis = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=2, socket_connect_timeout=2)
            except Exception as exc:  # pragma: no cover
                logger.warning("Redis unavailable: %s", exc)
                return None
        return self._redis

    def redis_ok(self) -> Optional[bool]:
        client = self._get_redis()
        if client is None:
            return None
        try:
            return bool(client.ping())
        except Exception:
            return False

    def start_redis_listener(self):
        if not settings.REDIS_URL or self._redis_thread:
            return
        self._stop.clear()
        self._redis_thread = threading.Thread(target=self._listen, name="redis-events", daemon=True)
        self._redis_thread.start()

    def stop(self):
        self._stop.set()

    def _listen(self):  # pragma: no cover - requires redis
        import time
        import redis
        while not self._stop.is_set():
            try:
                client = redis.Redis.from_url(settings.REDIS_URL)
                pubsub = client.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(CHANNEL)
                logger.info("Subscribed to Redis channel %s", CHANNEL)
                while not self._stop.is_set():
                    msg = pubsub.get_message(timeout=1.0)
                    if msg and msg.get("type") == "message":
                        event = json.loads(msg["data"])
                        if event.get("origin") != self.origin:
                            self._dispatch_local(event)
            except Exception as exc:
                logger.warning("Redis listener error (%s); retrying in 3s", exc)
                time.sleep(3)


hub = RealtimeHub()


def publish(event_type: str, data: Dict[str, Any], facility_id=None, user_ids=None):
    try:
        hub.publish(event_type, data, facility_id, user_ids)
    except Exception as exc:  # realtime must never break business transactions
        logger.warning("Realtime publish failed: %s", exc)
