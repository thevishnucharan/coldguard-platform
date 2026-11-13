"""In-app demo simulation engine.

Desired state lives in the DB (system_configurations key `simulation.state`) so the admin
UI (API process) can control an engine running in the separate worker process.
Readings go through the SAME ingestion pipeline as real devices with channel "simulator"
and `simulated=true`, so they are labelled in the database and UI.
"""
import logging
import random
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Dict

from sqlalchemy.orm import Session

from app.db.base import as_utc
from app.db.session import SessionLocal
from app.models import Sensor, SystemConfiguration
from app.models.enums import SensorStatus
from app.simulation.scenarios import SCENARIOS, generate

logger = logging.getLogger(__name__)
KEY = "simulation.state"
DEFAULT_STATE = {"running": False, "interval_seconds": 15, "scenarios": {}}


def get_state(db: Session) -> dict:
    row = db.get(SystemConfiguration, KEY)
    state = dict(DEFAULT_STATE)
    if row and isinstance(row.value, dict):
        state.update(row.value)
    return state


def save_state(db: Session, state: dict):
    row = db.get(SystemConfiguration, KEY)
    if row:
        row.value = dict(state)
    else:
        db.add(SystemConfiguration(key=KEY, value=dict(state), description="Demo simulation control (simulated data)"))
    db.commit()


def set_scenario(db: Session, sensor_id: uuid.UUID, scenario: str) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {SCENARIOS}")
    state = get_state(db)
    scen = dict(state.get("scenarios", {}))
    scen[str(sensor_id)] = {"scenario": scenario, "started_at": datetime.now(timezone.utc).isoformat()}
    state["scenarios"] = scen
    save_state(db, state)
    return state


class SimulationEngine:
    def __init__(self):
        self._thread = None
        self._stop = threading.Event()
        self._rng: Dict[str, random.Random] = {}

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="simulation", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            interval = 15
            try:
                interval = self.tick()
            except Exception as exc:
                logger.error("Simulation tick failed: %s", exc, exc_info=True)
            self._stop.wait(max(3, interval))

    def tick(self, now: datetime | None = None, ignore_pause: bool = False) -> int:
        from app.services import telemetry
        from app.workers.jobs import PAUSED, seeding_in_progress
        if not ignore_pause and (PAUSED.is_set() or seeding_in_progress()):
            return 5
        db = SessionLocal()
        try:
            state = get_state(db)
            if not state.get("running"):
                return 5
            now = now or datetime.now(timezone.utc)
            sensors = db.query(Sensor).filter(Sensor.is_simulated.is_(True), Sensor.storage_unit_id.isnot(None),
                                              Sensor.status != SensorStatus.DECOMMISSIONED).all()
            for s in sensors:
                cfg = state["scenarios"].get(str(s.id), {"scenario": "normal", "started_at": None})
                started = as_utc(datetime.fromisoformat(cfg["started_at"])) if cfg.get("started_at") else now
                rng = self._rng.setdefault(str(s.id), random.Random(hash(s.sensor_code) & 0xFFFF))
                unit = s.storage_unit
                temp = generate(cfg["scenario"], (now - started).total_seconds(), unit.effective_min,
                                unit.effective_max, rng)
                if temp is None:
                    continue
                battery = s.battery_level if s.battery_level is not None else 100.0
                telemetry.ingest(db, {
                    "sensor_code": s.sensor_code, "temperature": temp, "timestamp": now.isoformat(),
                    "battery": max(0.0, round(battery - 0.002, 3)), "simulated": True,
                    "message_id": f"sim-{s.sensor_code}-{int(now.timestamp())}", "source": "simulator",
                }, channel="simulator")
            return int(state.get("interval_seconds", 15))
        finally:
            db.close()


engine = SimulationEngine()
_ = time
