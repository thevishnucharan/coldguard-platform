"""Telemetry ingestion -> validation -> storage -> thresholds -> incidents."""
import json
from datetime import datetime, timedelta, timezone

from app.models import Incident, IncidentEvent, Notification, TelemetryQuarantine, TemperatureReading, Violation
from app.models.enums import IncidentStatus, IncidentType, SensorStatus, ViolationSeverity, ViolationStatus
from app.services import telemetry
from app.services.monitoring import live_units
from app.services.access import resolve_scope
from app.services.sensor_health import SensorHealthService
from app.workers.mqtt_ingestor import handle_message
from app.db.session import SessionLocal
from tests.conftest import feed, reading


def test_valid_reading_is_stored_with_metadata(db, org):
    r = telemetry.ingest(db, reading("S-U1", 5.0, simulated=True, battery=77), channel="mqtt")
    assert r.status == "accepted"
    row = db.get(TemperatureReading, r.reading_id)
    assert row.temperature == 5.0 and row.is_simulated is True and row.battery_level == 77
    db.refresh(org.sensors.u1)
    assert org.sensors.u1.last_temperature == 5.0 and org.sensors.u1.status == SensorStatus.ONLINE


def test_malformed_payloads_are_quarantined_not_dropped(db, org):
    for bad in ({"sensor_code": "S-U1"}, {"sensor_code": "S-U1", "temperature": "hot", "timestamp": "x"},
                b"{not json", {"temperature": 4, "timestamp": datetime.now(timezone.utc).isoformat()}):
        assert telemetry.ingest(db, bad, channel="mqtt").status == "rejected"
    assert db.query(TelemetryQuarantine).count() == 4
    assert db.query(TemperatureReading).count() == 0


def test_identity_validation(db, org):
    assert telemetry.ingest(db, reading("S-UNKNOWN", 4)).reason == "unknown sensor"
    org.sensors.u2.status = SensorStatus.DECOMMISSIONED
    db.commit()
    assert telemetry.ingest(db, reading("S-U2", 4)).reason == "sensor decommissioned"
    bad_unit = reading("S-U1", 4, storage_unit_id=str(org.units.u3.id))
    assert telemetry.ingest(db, bad_unit).reason == "storage unit mismatch"
    reasons = {q.reason.split(":")[0] for q in db.query(TelemetryQuarantine)}
    assert reasons == {"identity"}


def test_timestamp_and_value_validation(db, org):
    future = {"sensor_code": "S-U1", "temperature": 4,
              "timestamp": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()}
    assert telemetry.ingest(db, future).status == "rejected"
    assert telemetry.ingest(db, reading("S-U1", 250)).status == "rejected"  # physically impossible


def test_idempotency_by_message_id_and_timestamp(db, org):
    msg = reading("S-U1", 5.0, message_id="m-1")
    assert telemetry.ingest(db, msg).status == "accepted"
    assert telemetry.ingest(db, msg).status == "duplicate"
    same_ts = dict(msg, message_id="m-2")
    assert telemetry.ingest(db, same_ts).status == "duplicate"
    assert db.query(TemperatureReading).count() == 1


def test_calibration_offset_applied(db, org):
    org.sensors.u1.calibration_offset = -0.4
    db.commit()
    r = telemetry.ingest(db, reading("S-U1", 5.0))
    assert db.get(TemperatureReading, r.reading_id).temperature == 4.6


def test_excursion_opens_single_incident_and_escalates_severity(db, org):
    feed(db, "S-U1", [5, 5, 9.0, 9.2, 9.4], start_minutes_ago=40, step_minutes=1)
    incs = db.query(Incident).all()
    assert len(incs) == 1  # dedup: one incident for the ongoing excursion
    inc = incs[0]
    assert inc.incident_type == IncidentType.TEMPERATURE_EXCURSION and inc.status == IncidentStatus.OPEN
    assert inc.severity == ViolationSeverity.WARNING
    # sustained beyond policy.critical_after_minutes (30) -> CRITICAL
    feed(db, "S-U1", [9.3, 9.5], start_minutes_ago=2, step_minutes=1)
    db.refresh(inc)
    assert inc.severity == ViolationSeverity.CRITICAL
    assert db.query(IncidentEvent).filter_by(incident_id=inc.id, event_type="SEVERITY_RAISED").count() >= 1
    # notifications reached facility operators (and supervisor on CRITICAL)
    assert db.query(Notification).filter(Notification.user_id == org.users.op1.id).count() >= 1
    assert db.query(Notification).filter(Notification.user_id == org.users.sup1.id).count() >= 1
    assert db.query(Notification).filter(Notification.user_id == org.users.op3.id).count() == 0


def test_large_deviation_is_immediately_critical(db, org):
    feed(db, "S-U1", [5, 12.5], start_minutes_ago=3)
    assert db.query(Incident).one().severity == ViolationSeverity.CRITICAL


def test_recovery_closes_violation_but_not_incident(db, org):
    feed(db, "S-U1", [5, 9.5, 9.6, 5.0], start_minutes_ago=6)
    v = db.query(Violation).one()
    assert v.status == ViolationStatus.RESOLVED
    inc = db.query(Incident).one()
    assert inc.status == IncidentStatus.OPEN  # human investigation still required
    assert db.query(IncidentEvent).filter_by(incident_id=inc.id, event_type="TEMPERATURE_RECOVERED").count() == 1


def test_repeated_excursion_folds_into_active_incident(db, org):
    feed(db, "S-U1", [5, 9.5, 5.0, 9.4, 5.0], start_minutes_ago=6)
    assert db.query(Violation).count() == 2
    assert db.query(Incident).count() == 1
    inc = db.query(Incident).one()
    assert db.query(IncidentEvent).filter_by(incident_id=inc.id, event_type="REPEATED_SIGNAL").count() == 1


def test_policy_limits_are_per_unit_not_hardcoded(db, org):
    feed(db, "S-FZ1", [-20, -18, -16], start_minutes_ago=4)   # within freezer policy
    assert db.query(Incident).count() == 0
    feed(db, "S-FZ1", [-12], start_minutes_ago=0.5)            # above -15
    assert db.query(Incident).count() == 1
    feed(db, "S-U1", [-20], start_minutes_ago=0.2)             # same value in a 2-8 unit -> excursion
    assert db.query(Incident).count() == 2


def test_missing_then_offline_escalates_one_incident_and_recovers(db, org):
    now = datetime.now(timezone.utc)
    feed(db, "S-U1", [5], start_minutes_ago=7)
    s = SensorHealthService.check_offline_sensors(db, now=now)
    assert s["missing"] >= 1
    inc = db.query(Incident).filter(Incident.sensor_id == org.sensors.u1.id).one()
    assert inc.incident_type == IncidentType.MISSING_TELEMETRY and inc.severity == ViolationSeverity.WARNING
    SensorHealthService.check_offline_sensors(db, now=now + timedelta(minutes=10))
    db.refresh(inc)
    db.refresh(org.sensors.u1)
    assert inc.incident_type == IncidentType.SENSOR_OFFLINE and inc.severity == ViolationSeverity.HIGH
    assert org.sensors.u1.status == SensorStatus.OFFLINE
    assert db.query(Incident).filter(Incident.sensor_id == org.sensors.u1.id).count() == 1
    # repeated sweeps do not create more incidents
    SensorHealthService.check_offline_sensors(db, now=now + timedelta(minutes=12))
    assert db.query(Incident).filter(Incident.sensor_id == org.sensors.u1.id).count() == 1
    # telemetry resumes -> sensor online, event recorded, incident still needs human closure
    feed(db, "S-U1", [5.1], start_minutes_ago=0)
    db.refresh(org.sensors.u1)
    assert org.sensors.u1.status == SensorStatus.ONLINE
    assert db.query(IncidentEvent).filter_by(incident_id=inc.id, event_type="TELEMETRY_RESTORED").count() == 1


def test_live_view_never_presents_stale_reading_as_current(db, org):
    feed(db, "S-U1", [5], start_minutes_ago=10)
    feed(db, "S-U2", [5], start_minutes_ago=0.1)
    feed(db, "S-U3", [7.8], start_minutes_ago=0.1)
    units = {u["unit_code"]: u for u in live_units(db, resolve_scope(db, org.users.admin))}
    assert units["U1"]["stale"] is True and units["U1"]["health"] == "MISSING_TELEMETRY"
    assert units["U2"]["health"] == "NORMAL" and units["U2"]["stale"] is False
    assert units["U3"]["health"] == "WARNING"   # inside limits but within warning margin
    assert units["FZ1"]["health"] == "NO_DATA"


def test_mqtt_handler_end_to_end_and_topic_spoofing(db, org):
    payload = json.dumps({"temperature": 4.4, "timestamp": datetime.now(timezone.utc).isoformat(),
                          "message_id": "mq-1"}).encode()
    assert handle_message("coldguard/telemetry/F1/S-U1", payload, db_factory=SessionLocal).status == "accepted"
    spoof = json.dumps({"sensor_code": "S-U3", "temperature": 4.4,
                        "timestamp": datetime.now(timezone.utc).isoformat()}).encode()
    assert handle_message("coldguard/telemetry/F1/S-U1", spoof, db_factory=SessionLocal).status == "rejected"
    assert handle_message("coldguard/telemetry/F1/S-U1", b"\x00garbage", db_factory=SessionLocal).status == "rejected"
    assert db.query(TemperatureReading).count() == 1


def test_rest_gateway_authentication(client, org, auth):
    body = reading("S-U1", 5.0)
    assert client.post("/api/v1/temperature/readings", json=body).status_code == 401
    assert client.post("/api/v1/temperature/readings", json=body, headers={"X-Ingest-Key": "wrong"}).status_code == 401
    assert client.post("/api/v1/temperature/readings", json=body, headers=auth(org.users.op1)).status_code == 403
    r = client.post("/api/v1/temperature/readings", json=body, headers={"X-Ingest-Key": "test-ingest-key-0123456789"})
    assert r.status_code == 202 and r.json()["status"] == "accepted"
    bulk = {"readings": [reading("S-U2", 5.0), reading("S-NOPE", 4.0), {"bad": 1}]}
    r = client.post("/api/v1/temperature/readings/bulk", json=bulk, headers=auth(org.users.admin))
    assert r.json() == {"ingested": 1, "duplicates": 0, "rejected": 2}
