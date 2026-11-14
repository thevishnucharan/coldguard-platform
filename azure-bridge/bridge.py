import json
import logging
import os
import queue
import signal
import threading
import time

import paho.mqtt.client as mqtt
from azure.iot.device import IoTHubDeviceClient, Message

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [azure-bridge] %(message)s",
)
logger = logging.getLogger("azure-bridge")

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "coldguard-ingestor")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "coldguard/telemetry/#")
IOTHUB_CONNECTION_STRING = os.getenv("IOTHUB_DEVICE_CONNECTION_STRING", "")

QUEUE_SIZE = 500
MAX_RETRIES = 5
RETRY_DELAY = 2

if not IOTHUB_CONNECTION_STRING:
    raise RuntimeError("IOTHUB_DEVICE_CONNECTION_STRING is not configured")

message_queue = queue.Queue(maxsize=QUEUE_SIZE)
stop_event = threading.Event()
iot_client = None


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Connected to MQTT broker %s:%s", MQTT_HOST, MQTT_PORT)
        client.subscribe(MQTT_TOPIC, qos=1)
        logger.info("Subscribed to %s", MQTT_TOPIC)
    else:
        logger.error("MQTT connection failed: %s", rc)


def on_disconnect(client, userdata, rc):
    logger.warning("MQTT disconnected: %s", rc)


def on_message(client, userdata, mqtt_message):
    try:
        payload = mqtt_message.payload.decode("utf-8")
        data = json.loads(payload)

        if not isinstance(data, dict):
            logger.warning("Ignoring non-object telemetry")
            return

        data["azure_gateway"] = "coldguard-iothub-2026"

        item = (mqtt_message.topic, data)

        try:
            message_queue.put_nowait(item)
        except queue.Full:
            logger.error(
                "Azure bridge queue full; dropping message from %s",
                mqtt_message.topic,
            )

    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.exception("Invalid JSON telemetry on %s", mqtt_message.topic)
    except Exception:
        logger.exception("Failed to queue telemetry")


def azure_sender():
    while not stop_event.is_set() or not message_queue.empty():
        try:
            item = message_queue.get(timeout=1)
        except queue.Empty:
            continue

        if item is None:
            message_queue.task_done()
            continue

        topic, data = item
        delivered = False

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                outgoing = Message(json.dumps(data))
                outgoing.content_type = "application/json"
                outgoing.content_encoding = "utf-8"
                outgoing.custom_properties["mqtt_topic"] = topic

                iot_client.send_message(outgoing)

                logger.info(
                    "Forwarded sensor=%s topic=%s",
                    data.get("sensor_code", "unknown"),
                    topic,
                )
                delivered = True
                break

            except Exception as exc:
                logger.warning(
                    "Azure delivery attempt %s/%s failed: %s",
                    attempt,
                    MAX_RETRIES,
                    exc,
                )

                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * (2 ** (attempt - 1)))

        if not delivered:
            logger.error(
                "Telemetry delivery abandoned after %s attempts: sensor=%s",
                MAX_RETRIES,
                data.get("sensor_code", "unknown"),
            )

        message_queue.task_done()


def shutdown(signum, frame):
    logger.info("Shutdown signal received")
    stop_event.set()


def main():
    global iot_client

    logger.info("Starting ColdGuard MQTT-to-Azure bridge")

    iot_client = IoTHubDeviceClient.create_from_connection_string(
        IOTHUB_CONNECTION_STRING
    )
    iot_client.connect()
    logger.info("Connected to Azure IoT Hub")

    sender_thread = threading.Thread(
        target=azure_sender,
        name="azure-sender",
        daemon=True,
    )
    sender_thread.start()

    mqtt_client = mqtt.Client(
        client_id="coldguard-azure-bridge"
    )
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_disconnect = on_disconnect
    mqtt_client.on_message = on_message
    mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)

    try:
        mqtt_client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
        mqtt_client.loop_start()

        logger.info("Azure bridge is running")

        while not stop_event.wait(1):
            pass

    finally:
        logger.info("Stopping MQTT receiver")
        mqtt_client.loop_stop()
        mqtt_client.disconnect()

        logger.info("Draining pending Azure telemetry")
        sender_thread.join(timeout=60)

        if sender_thread.is_alive():
            logger.warning("Azure sender still has pending messages")

        logger.info("Disconnecting from Azure IoT Hub")
        iot_client.disconnect()
        logger.info("Azure bridge stopped")


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

if __name__ == "__main__":
    main()
