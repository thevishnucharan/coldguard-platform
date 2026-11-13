"""ML is decision support: anomalies recorded with version/explanation; pattern incidents are
WARNING and never change stock status. Simulation readings are labelled."""
import random
from datetime import datetime, timedelta, timezone

from app.ml.anomaly_service import MLAnomalyService
from app.models import Anomaly, Batch, Incident, TemperatureReading
from app.models.enums import BatchStatus, IncidentType, ViolationSeverity
from app.services import simulation
from app.services.inventory import InventoryService
from app.simulation.scenarios import SCENARIOS, generate
from tests.conftest import feed


def test_model_loads_with_version():
    info = MLAnomalyService.model_info()
    assert info["available"] is True and info["version"]


def test_normal_series_produces_no_anomalies(db, org):
    rng = random.Random(1)
    temps = [round(5 + rng.gauss(0, 0.1), 2) for _ in range(40)]
    feed(db, "S-U1", temps, start_minutes_ago=40)
    assert db.query(Anomaly).count() == 0


def test_spike_within_limits_is_flagged_with_explanation_but_not_an_excursion(db, org):
    rng = random.Random(2)
    temps = [round(4.0 + rng.gauss(0, 0.05), 2) for _ in range(25)] + [7.6]
    feed(db, "S-U1", temps, start_minutes_ago=26)
    a = db.query(Anomaly).one()
    assert a.detection_method.endswith("ROLLING_ZSCORE")
    assert a.model_version and a.explanation["indicators"] and "Decision support" in a.explanation["note"]
    assert a.context["z_score"] > 4
    assert db.query(Incident).filter(Incident.incident_type == IncidentType.TEMPERATURE_EXCURSION).count() == 0


def test_anomaly_cluster_creates_warning_pattern_incident_without_stock_action(db, org):
    b = InventoryService.receive(db, org.users.op1, batch_number="ML-1", product_id=org.product.id,
                                 storage_unit_id=org.units.u1.id, quantity=10,
                                 expiry_date=datetime.now(timezone.utc) + timedelta(days=60))
    rng = random.Random(3)
    temps = []
    for _ in range(4):  # spikes spaced beyond the 30-reading z-score window
        temps += [round(4.0 + rng.gauss(0, 0.03), 2) for _ in range(31)] + [7.5]
    feed(db, "S-U1", temps, start_minutes_ago=len(temps) * 0.2, step_minutes=0.2)
    inc = db.query(Incident).filter(Incident.incident_type == IncidentType.ABNORMAL_PATTERN).one()
    assert inc.severity == ViolationSeverity.WARNING and inc.source == "ML"
    assert db.query(Anomaly).filter(Anomaly.incident_id == inc.id).count() >= 3
    db.refresh(b)
    assert b.status == BatchStatus.ACTIVE  # never auto-quarantined / released / discarded


def test_scenarios_behave_as_documented():
    rng = random.Random(0)
    assert set(SCENARIOS) == {"normal", "drift", "excursion", "fluctuation", "missing", "disconnect"}
    assert generate("disconnect", 60, 2, 8, rng) is None
    assert all(2 <= generate("normal", t * 60, 2, 8, rng) <= 8 for t in range(60))
    assert generate("excursion", 5 * 60, 2, 8, rng) > 8
    assert generate("drift", 60 * 60, 2, 8, rng) > 8
    assert sum(generate("missing", t, 2, 8, rng) is None for t in range(200)) > 80


def test_simulation_engine_tick_labels_readings(db, org):
    for s in (org.sensors.u1, org.sensors.u2):
        s.is_simulated = True
    db.commit()
    simulation.save_state(db, {"running": True, "interval_seconds": 5, "scenarios": {}})
    simulation.set_scenario(db, org.sensors.u2.id, "disconnect")
    simulation.engine.tick()
    rows = db.query(TemperatureReading).all()
    assert len(rows) == 1 and rows[0].is_simulated is True and rows[0].source == "simulator"
    assert rows[0].sensor_id == org.sensors.u1.id


def test_simulation_api_requires_admin_and_demo_mode(client, org, auth, db):
    org.sensors.u1.is_simulated = True
    db.commit()
    assert client.get("/api/v1/demo/simulation", headers=auth(org.users.op1)).status_code == 403
    r = client.post("/api/v1/demo/simulation/scenario", headers=auth(org.users.admin),
                    json={"sensor_id": str(org.sensors.u1.id), "scenario": "excursion"})
    assert r.status_code == 200
    r = client.post("/api/v1/demo/simulation/scenario", headers=auth(org.users.admin),
                    json={"sensor_id": str(org.sensors.u2.id), "scenario": "excursion"})
    assert r.status_code == 400  # real (non-simulated) sensors cannot be driven by the simulator
    assert client.post("/api/v1/demo/reset", headers=auth(org.users.admin), json={"confirm": "yes"}).status_code == 400


_ = Batch
