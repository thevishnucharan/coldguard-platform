#!/usr/bin/env python3
"""ColdGuard device simulator — DEMONSTRATION ONLY.

Publishes simulated temperature telemetry for one or more sensors over MQTT (default) or
the REST gateway. Every message carries `"simulated": true`, so the platform labels the
data as simulated in the database and UI.

Scenario maths is shared with the in-app engine: backend/app/simulation/scenarios.py.

Examples
  # discover simulated sensors from the API and publish 'normal' for all of them
  python simulator.py --discover --api http://localhost:8000/api/v1

  # explicit sensors (code:facility:min:max:scenario)
  python simulator.py --sensor S-BLR-JAY-ILR-1:BLR-JAY:2:8:excursion --sensor S-MYS-DVS-ILR-1:MYS-DVS:2:8:disconnect

  # REST gateway instead of MQTT
  python simulator.py --transport http --ingest-key $INGEST_API_KEY --sensor ...

Note: the API's in-app simulation (Admin -> Demo simulation) drives the same sensors; stop it
before running this simulator against them to avoid two data sources per sensor.
"""
import argparse
import json
import os
import random
import signal
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

try:  # inside the container scenarios.py sits next to this file
    from scenarios import SCENARIOS, generate
except ImportError:  # running from the repository
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from app.simulation.scenarios import SCENARIOS, generate

RUNNING = True


@dataclass
class SimSensor:
    code: str
    facility: str
    lo: float
    hi: float
    scenario: str
    started: float
    battery: float = 100.0


def parse_sensor(spec: str) -> SimSensor:
    parts = spec.split(":")
    if len(parts) != 5 or parts[4] not in SCENARIOS:
        raise argparse.ArgumentTypeError(f"--sensor CODE:FACILITY:MIN:MAX:SCENARIO (scenario in {SCENARIOS})")
    return SimSensor(parts[0], parts[1], float(parts[2]), float(parts[3]), parts[4], time.time())


def discover(api: str, email: str, password: str, scenario: str) -> list[SimSensor]:
    import requests
    s = requests.Session()
    r = s.post(f"{api}/auth/login", data={"username": email, "password": password}, timeout=10)
    r.raise_for_status()
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    units = s.get(f"{api}/monitoring/live", timeout=20).json()["units"]
    facilities = {f["id"]: f["code"] for f in s.get(f"{api}/facilities", timeout=20).json()}
    out = []
    for u in units:
        for sen in u["sensors"]:
            if sen["is_simulated"]:
                out.append(SimSensor(sen["sensor_code"], facilities.get(u["facility_id"], "UNKNOWN"),
                                     u["min_temperature"], u["max_temperature"], scenario, time.time()))
    return out


def message(s: SimSensor, rng: random.Random) -> dict | None:
    temp = generate(s.scenario, time.time() - s.started, s.lo, s.hi, rng)
    if temp is None:
        return None
    s.battery = max(0.0, s.battery - 0.01)
    return {"sensor_code": s.code, "temperature": temp, "timestamp": datetime.now(timezone.utc).isoformat(),
            "battery": round(s.battery, 2), "message_id": uuid.uuid4().hex, "simulated": True, "source": "mqtt-simulator"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--transport", choices=["mqtt", "http"], default=os.getenv("SIM_TRANSPORT", "mqtt"))
    ap.add_argument("--mqtt-host", default=os.getenv("MQTT_HOST", "localhost"))
    ap.add_argument("--mqtt-port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    ap.add_argument("--mqtt-username", default=os.getenv("MQTT_USERNAME", ""))
    ap.add_argument("--mqtt-password", default=os.getenv("MQTT_PASSWORD", ""))
    ap.add_argument("--api", default=os.getenv("API_URL", "http://localhost:8000/api/v1"))
    ap.add_argument("--ingest-key", default=os.getenv("INGEST_API_KEY", ""))
    ap.add_argument("--discover", action="store_true", default=os.getenv("SIM_DISCOVER", "false") == "true")
    ap.add_argument("--discover-email", default=os.getenv("SIM_API_EMAIL", ""))
    ap.add_argument("--discover-password", default=os.getenv("SIM_API_PASSWORD", ""))
    ap.add_argument("--scenario", default=os.getenv("SIM_SCENARIO", "normal"), choices=SCENARIOS)
    ap.add_argument("--sensor", action="append", type=parse_sensor, default=[])
    ap.add_argument("--interval", type=float, default=float(os.getenv("SIM_INTERVAL", "15")))
    ap.add_argument("--duration", type=float, default=float(os.getenv("SIM_DURATION", "0")), help="seconds, 0 = forever")
    args = ap.parse_args()

    sensors = list(args.sensor)
    if args.discover:
        for attempt in range(30):
            try:
                sensors += discover(args.api, args.discover_email, args.discover_password, args.scenario)
                break
            except Exception as exc:  # API may still be starting
                print(f"[sim] discovery failed ({exc}); retrying in 5 s", flush=True)
                time.sleep(5)
    if not sensors:
        sys.exit("No sensors to simulate (use --sensor or --discover)")
    print(f"[sim] simulating {len(sensors)} sensor(s) via {args.transport} every {args.interval}s — SIMULATED DATA", flush=True)

    client = None
    if args.transport == "mqtt":
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"coldguard-sim-{uuid.uuid4().hex[:6]}")
        if args.mqtt_username:
            client.username_pw_set(args.mqtt_username, args.mqtt_password)
        client.reconnect_delay_set(1, 30)
        client.connect_async(args.mqtt_host, args.mqtt_port, keepalive=30)
        client.loop_start()
    else:
        import requests
        http = requests.Session()
        http.headers["X-Ingest-Key"] = args.ingest_key

    signal.signal(signal.SIGTERM, lambda *_: globals().__setitem__("RUNNING", False))
    signal.signal(signal.SIGINT, lambda *_: globals().__setitem__("RUNNING", False))
    rngs = {s.code: random.Random(s.code) for s in sensors}
    t0 = time.time()
    while RUNNING and (args.duration <= 0 or time.time() - t0 < args.duration):
        for s in sensors:
            msg = message(s, rngs[s.code])
            if msg is None:
                continue
            if client is not None:
                client.publish(f"coldguard/telemetry/{s.facility}/{s.code}", json.dumps(msg), qos=1)
            else:
                try:
                    r = http.post(f"{args.api}/temperature/readings", json=msg, timeout=10)
                    if r.status_code >= 400:
                        print(f"[sim] {s.code}: HTTP {r.status_code} {r.text[:120]}", flush=True)
                except Exception as exc:
                    print(f"[sim] {s.code}: {exc}", flush=True)
        time.sleep(args.interval)
    if client is not None:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
