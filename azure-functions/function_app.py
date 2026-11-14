
import json
import logging

import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

MIN_TEMPERATURE = 2.0
MAX_TEMPERATURE = 8.0


# ---------------------------------------------------------
# HTTP TRIGGER: Manual telemetry processing
# ---------------------------------------------------------

@app.route(
    route="telemetry/process",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION
)
def process_telemetry(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("ColdGuard telemetry processor invoked.")

    try:
        payload = req.get_json()

        if not isinstance(payload, dict):
            return func.HttpResponse(
                json.dumps({"error": "JSON payload must be an object"}),
                status_code=400,
                mimetype="application/json"
            )

        sensor_id = payload.get("sensor_id")
        unit_code = payload.get("unit_code")
        temperature = payload.get("temperature")
        humidity = payload.get("humidity")

        if not sensor_id or not unit_code:
            return func.HttpResponse(
                json.dumps({
                    "error": "sensor_id and unit_code are required"
                }),
                status_code=400,
                mimetype="application/json"
            )

        if isinstance(temperature, bool) or not isinstance(
            temperature, (int, float)
        ):
            return func.HttpResponse(
                json.dumps({"error": "temperature must be numeric"}),
                status_code=400,
                mimetype="application/json"
            )

        temperature = float(temperature)

        if not -100 <= temperature <= 100:
            return func.HttpResponse(
                json.dumps({
                    "error": "temperature is outside valid bounds"
                }),
                status_code=400,
                mimetype="application/json"
            )

        if temperature < MIN_TEMPERATURE:
            status = "LOW"
            alert = "Temperature below 2°C"
        elif temperature > MAX_TEMPERATURE:
            status = "HIGH"
            alert = "Temperature exceeds 8°C"
        else:
            status = "NORMAL"
            alert = None

        result = {
            "sensor_id": sensor_id,
            "unit_code": unit_code,
            "temperature": temperature,
            "humidity": humidity,
            "status": status,
            "threshold_exceeded": status != "NORMAL",
            "alert": alert,
            "processor": "ColdGuardTelemetryProcessor"
        }

        logging.info(
            "Processed sensor=%s temperature=%.2f status=%s",
            sensor_id,
            temperature,
            status
        )

        return func.HttpResponse(
            json.dumps(result),
            status_code=200,
            mimetype="application/json"
        )

    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON payload"}),
            status_code=400,
            mimetype="application/json"
        )

    except Exception:
        logging.exception("Unexpected telemetry processing error.")

        return func.HttpResponse(
            json.dumps({"error": "Internal processing error"}),
            status_code=500,
            mimetype="application/json"
        )


# ---------------------------------------------------------
# EVENT HUB TRIGGER: Azure IoT Hub telemetry processing
# ---------------------------------------------------------

def extract_sensor_id(payload: dict):
    """
    Extract a sensor identifier from supported payload fields.
    """

    possible_fields = [
        "sensor_id",
        "deviceId",
        "sensor_code",
        "sensorCode",
        "sensorId",
        "device_id"
    ]

    for field in possible_fields:
        value = payload.get(field)

        if value:
            return value

    # Check common nested payload structures.
    for nested_field in ["data", "telemetry", "payload"]:
        nested = payload.get(nested_field)

        if isinstance(nested, dict):
            sensor_id = extract_sensor_id(nested)

            if sensor_id:
                return sensor_id

    return None


@app.function_name(name="process_iothub_telemetry")
@app.event_hub_message_trigger(
    arg_name="event",
    event_hub_name="iothub-ehub-coldguard-56257692-3d2577ae14",
    connection="IOTHUB_EVENTHUB_CONNECTION",
    consumer_group="$Default"
)
def process_iothub_telemetry(event: func.EventHubEvent):
    """
    Consume telemetry forwarded to the Azure IoT Hub built-in
    Events endpoint.

    This stage validates and classifies incoming messages.
    It does not modify PostgreSQL or send notifications.
    """

    try:
        body = event.get_body().decode("utf-8")
        payload = json.loads(body)

        if not isinstance(payload, dict):
            logging.warning(
                "Ignoring IoT Hub event: JSON payload is not an object."
            )
            return

        # Diagnostic logging: log field names, not sensor values.
        logging.info(
            "IoT Hub payload field names: %s",
            sorted(payload.keys())
        )

        sensor_id = extract_sensor_id(payload)

        temperature = payload.get("temperature")

        # Also check common nested telemetry structures.
        if temperature is None:
            for nested_field in ["data", "telemetry", "payload"]:
                nested = payload.get(nested_field)

                if isinstance(nested, dict):
                    temperature = nested.get("temperature")

                    if temperature is not None:
                        break

        if not sensor_id:
            logging.warning(
                "Ignoring telemetry event: sensor identifier is missing."
            )
            return

        if isinstance(temperature, bool) or not isinstance(
            temperature, (int, float)
        ):
            logging.warning(
                "Ignoring telemetry event for sensor=%s: "
                "temperature is invalid.",
                sensor_id
            )
            return

        temperature = float(temperature)

        if not -100 <= temperature <= 100:
            logging.warning(
                "Ignoring telemetry event for sensor=%s: "
                "temperature is outside valid bounds.",
                sensor_id
            )
            return

        # Classify temperature against vaccine cold-chain thresholds.
        if temperature < MIN_TEMPERATURE:
            status = "LOW"
        elif temperature > MAX_TEMPERATURE:
            status = "HIGH"
        else:
            status = "NORMAL"

        logging.info(
            "IoT Hub telemetry processed: "
            "sensor=%s temperature=%.2f status=%s",
            sensor_id,
            temperature,
            status
        )

    except (UnicodeDecodeError, json.JSONDecodeError):
        logging.warning(
            "Ignoring IoT Hub event: message is not valid UTF-8 JSON."
        )

    except Exception:
        logging.exception(
            "Unexpected IoT Hub telemetry processing error."
        )
        raise
