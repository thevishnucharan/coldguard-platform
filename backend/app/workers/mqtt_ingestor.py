"""MQTT telemetry ingestor.

Subscribes to `coldguard/telemetry/<facility_code>/<sensor_code>` (QoS 1). Each message is
handed to the shared ingestion pipeline. The sensor code in the topic must match the
payload (if the payload carries one) — a device cannot publish on behalf of another.
paho's network loop reconnects automatically with exponential back-off.
"""
import json
import logging
import queue
import threading
from typing import Optional

from app.core.config import settings
from app.core.metrics import MQTT_CONNECTED
from app.db.session import SessionLocal
from app.services import telemetry

logger = logging.getLogger(__name__)


def handle_message(topic: str, payload: bytes, db_factory=SessionLocal) -> telemetry.IngestResult:
    parts = topic.split("/")
    topic_code = parts[-1] if len(parts) >= 4 else None
    db = db_factory()
    try:
        try:
            data = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return telemetry.ingest(db, payload, channel="mqtt")
        if isinstance(data, dict):
            if topic_code and data.get("sensor_code") and data["sensor_code"] != topic_code:
                telemetry._quarantine(db, "mqtt", data, "identity: topic/payload sensor mismatch", topic_code,
                                      bool(data.get("simulated")))
                return telemetry.IngestResult("rejected", "topic/payload mismatch")
            data.setdefault("sensor_code", topic_code)
            data.setdefault("source", "mqtt")
        return telemetry.ingest(db, data, channel="mqtt")
    finally:
        db.close()


class MQTTIngestor:
    def __init__(self):
        self.client = None
        self.connected = False
        self._queue: "queue.Queue[tuple[str, bytes]]" = queue.Queue(maxsize=10000)
        self._worker: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self):
        import paho.mqtt.client as mqtt
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=settings.MQTT_CLIENT_ID,
                                  clean_session=False)
        if settings.MQTT_USERNAME:
            self.client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._worker = threading.Thread(target=self._drain, name="mqtt-ingest", daemon=True)
        self._worker.start()
        self.client.connect_async(settings.MQTT_HOST, settings.MQTT_PORT, keepalive=30)
        self.client.loop_start()
        logger.info("MQTT ingestor connecting to %s:%s", settings.MQTT_HOST, settings.MQTT_PORT)

    def stop(self):
        self._stop.set()
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0 or getattr(reason_code, "value", 1) == 0:
            self.connected = True
            MQTT_CONNECTED.set(1)
            client.subscribe(settings.MQTT_TOPIC, qos=1)
            logger.info("MQTT connected; subscribed to %s", settings.MQTT_TOPIC)
        else:
            logger.error("MQTT connection refused: %s", reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.connected = False
        MQTT_CONNECTED.set(0)
        logger.warning("MQTT disconnected (%s); auto-reconnect active", reason_code)

    def _on_message(self, client, userdata, msg):
        try:
            self._queue.put_nowait((msg.topic, msg.payload))
        except queue.Full:
            logger.error("MQTT ingest queue full; dropping message on %s", msg.topic)

    def _drain(self):
        # Single consumer thread keeps per-sensor ordering and avoids SQLite write contention.
        while not self._stop.is_set():
            try:
                topic, payload = self._queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                handle_message(topic, payload)
            except Exception as exc:
                logger.error("MQTT message handling failed: %s", exc, exc_info=True)


ingestor = MQTTIngestor()
