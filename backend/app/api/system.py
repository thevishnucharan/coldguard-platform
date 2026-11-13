"""System status, configuration, escalation settings and demo/simulation controls."""
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.core.config import settings
from app.ml.anomaly_service import MLAnomalyService
from app.models import Sensor, StorageUnit, SystemConfiguration
from app.services import analytics
from app.services import simulation as sim
from app.services.access import AccessScope
from app.services.audit import log_audit
from app.services.configuration import ConfigurationService
from app.services.escalation import DEFAULT_RULES, rules as escalation_rules
from app.simulation.scenarios import SCENARIOS

router = APIRouter()      # /system
config = APIRouter()      # /configurations (v1 path preserved)
demo = APIRouter()        # /demo

INTERNAL_KEYS = {"worker.heartbeat", "simulation.state", "demo.seeded_at"}


@router.get("/status")
def status(db: Session = Depends(get_db), _: AccessScope = Depends(require_permission("platform.view"))):
    return {**analytics.system_status(db), "ml": MLAnomalyService.model_info(),
            "mqtt_broker": f"{settings.MQTT_HOST}:{settings.MQTT_PORT}" if settings.MQTT_ENABLED else None}


@router.get("/escalation-rules")
def get_escalation(db: Session = Depends(get_db), _: AccessScope = Depends(require_permission("platform.view"))):
    return {"rules": escalation_rules(db), "defaults": DEFAULT_RULES}


@router.put("/escalation-rules")
def put_escalation(request: Request, body: Dict[str, int] = Body(...), db: Session = Depends(get_db),
                   scope: AccessScope = Depends(require_permission("platform.configure"))):
    unknown = set(body) - set(DEFAULT_RULES)
    if unknown:
        raise HTTPException(400, f"Unknown keys: {sorted(unknown)}")
    if any((not isinstance(v, int)) or v < 1 or v > 10000 for v in body.values()):
        raise HTTPException(400, "Values must be integers between 1 and 10000")
    row = db.get(SystemConfiguration, "escalation_rules")
    before = dict(row.value) if row else None
    merged = {**escalation_rules(db), **body}
    if row:
        row.value = merged
    else:
        db.add(SystemConfiguration(key="escalation_rules", value=merged, description="Incident escalation thresholds"))
    log_audit(db, scope.user, "ESCALATION_RULES_UPDATED", "SystemConfiguration", uuid.uuid5(uuid.NAMESPACE_OID, "escalation_rules"),
              {"before": before, "after": merged}, category="CONFIG", request=request, commit=False)
    db.commit()
    return {"rules": merged}


# ------------------------------------------------------------------ v1 configurations (preserved)
@config.get("")
def list_configs(db: Session = Depends(get_db), _: AccessScope = Depends(require_permission("platform.view"))):
    return [{"key": c.key, "value": c.value, "description": c.description, "updated_at": c.updated_at}
            for c in ConfigurationService.get_all(db) if c.key not in INTERNAL_KEYS]


@config.put("/{key}")
def update_config(key: str, request: Request, body: Dict[str, Any] = Body(...), db: Session = Depends(get_db),
                  scope: AccessScope = Depends(require_permission("platform.configure"))):
    if key in INTERNAL_KEYS:
        raise HTTPException(400, "This key is managed by the system")
    c = ConfigurationService.update(db, key, body.get("value"), scope.user, body.get("description"))
    return {"key": c.key, "value": c.value, "description": c.description, "updated_at": c.updated_at}


# ------------------------------------------------------------------ demo / simulation
def _demo_guard():
    if not settings.DEMO_MODE:
        raise HTTPException(404, "Demo mode is disabled")


class ScenarioIn(BaseModel):
    sensor_id: uuid.UUID
    scenario: str = Field(..., pattern="^(" + "|".join(SCENARIOS) + ")$")


@demo.get("/simulation")
def simulation_state(db: Session = Depends(get_db), _: AccessScope = Depends(require_permission("simulation.control"))):
    _demo_guard()
    state = sim.get_state(db)
    sensors = db.query(Sensor).filter(Sensor.is_simulated.is_(True)).order_by(Sensor.sensor_code).all()
    return {**state, "available_scenarios": list(SCENARIOS), "sensors": [
        {"id": s.id, "sensor_code": s.sensor_code, "unit_code": s.storage_unit.unit_code if s.storage_unit else None,
         "status": s.status.value, "last_temperature": s.last_temperature, "last_reading_at": s.last_reading_at,
         "scenario": state["scenarios"].get(str(s.id), {}).get("scenario", "normal")} for s in sensors]}


@demo.post("/simulation/start")
def start_sim(request: Request, interval_seconds: int = Body(15, embed=True, ge=3, le=300), db: Session = Depends(get_db),
              scope: AccessScope = Depends(require_permission("simulation.control"))):
    _demo_guard()
    state = sim.get_state(db)
    state.update(running=True, interval_seconds=interval_seconds)
    sim.save_state(db, state)
    log_audit(db, scope.user, "SIMULATION_STARTED", "Simulation", None, {"interval": interval_seconds},
              category="CONFIG", request=request)
    return state


@demo.post("/simulation/stop")
def stop_sim(request: Request, db: Session = Depends(get_db),
             scope: AccessScope = Depends(require_permission("simulation.control"))):
    _demo_guard()
    state = sim.get_state(db)
    state["running"] = False
    sim.save_state(db, state)
    log_audit(db, scope.user, "SIMULATION_STOPPED", "Simulation", None, {}, category="CONFIG", request=request)
    return state


@demo.post("/simulation/scenario")
def set_scenario(body: ScenarioIn, request: Request, db: Session = Depends(get_db),
                 scope: AccessScope = Depends(require_permission("simulation.control"))):
    _demo_guard()
    s = db.get(Sensor, body.sensor_id)
    if not s or not s.is_simulated:
        raise HTTPException(400, "Scenarios can only be applied to sensors flagged as simulated")
    state = sim.set_scenario(db, s.id, body.scenario)
    log_audit(db, scope.user, "SIMULATION_SCENARIO_SET", "Sensor", s.id, {"scenario": body.scenario},
              category="CONFIG", request=request)
    return state


@demo.post("/reset")
def reset_demo(request: Request, confirm: str = Body(..., embed=True), db: Session = Depends(get_db),
               scope: AccessScope = Depends(require_permission("simulation.control", "platform.configure"))):
    """Wipe ALL data and re-seed the demo dataset. Only available when DEMO_MODE=true."""
    _demo_guard()
    if confirm != "RESET DEMO DATA":
        raise HTTPException(400, 'Type "RESET DEMO DATA" to confirm')
    actor = scope.user.email
    from app.services import demo_seed
    from app.workers.jobs import PAUSED
    PAUSED.set()
    try:
        demo_seed.wipe(db)
        summary = demo_seed.seed(db)
    finally:
        PAUSED.clear()
    from app.models import User
    admin = db.query(User).filter(User.email == actor).first()
    log_audit(db, admin, "DEMO_RESET", "System", None, {"requested_by": actor, **summary}, category="CONFIG",
              request=request)
    return {"message": "Demo data reset", **summary}


_ = (List, StorageUnit)
