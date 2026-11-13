"""Demo dataset (CLEARLY SIMULATED). Builds regions, facilities, equipment, 5-role users,
24 h of simulated telemetry, and incidents/work orders at different lifecycle stages by
driving the real services, so every record is internally consistent.

All sensors are flagged `is_simulated`, all readings `is_simulated=true`. Names of places
are used only as plausible labels for fictional facilities.
"""
from __future__ import annotations

import logging
import uuid
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import (Batch, MonitoringPolicy, Product, Region, Facility, Sensor, StorageUnit, SystemConfiguration,
                        TemperatureReading, User, UserRoleAssignment)
from app.models.enums import (CalibrationResult, MaintenancePriority, MaintenanceType, Role, SensorStatus,
                              ViolationSeverity)
from app.security.auth import get_password_hash
from app.simulation.scenarios import generate

log = logging.getLogger(__name__)
DEMO_PASSWORD = "ColdGuard#2026"  # local demonstration only — documented in README

USERS = [
    # email, name, role, title
    ("admin@coldguard.local", "Asha Raman", Role.ADMIN, "Platform Administrator"),
    ("operator.blr@coldguard.local", "Ravi Kumar", Role.OPERATOR, "Cold Chain Handler — Bengaluru"),
    ("operator.mys@coldguard.local", "Meena Gowda", Role.OPERATOR, "Cold Chain Handler — Mysuru"),
    ("supervisor@coldguard.local", "Dr. Kiran Shetty", Role.SUPERVISOR, "District Immunisation Officer"),
    ("supervisor.south@coldguard.local", "Dr. Farah Ali", Role.SUPERVISOR, "Regional Cold Chain Officer"),
    ("technician@coldguard.local", "Suresh Naik", Role.TECHNICIAN, "Refrigeration Technician"),
    ("technician.mys@coldguard.local", "Arun Prakash", Role.TECHNICIAN, "Refrigeration Technician"),
    ("auditor@coldguard.local", "Lakshmi Iyer", Role.AUDITOR, "Quality & Compliance Auditor"),
]

REGIONS = [
    ("BLR", "Bengaluru Urban", [
        ("BLR-DVS", "District Vaccine Store, Bengaluru Urban", "District Vaccine Store", 12.9716, 77.5946),
        ("BLR-JAY", "Urban PHC Jayanagar", "Primary Health Centre", 12.9250, 77.5938),
        ("BLR-HEB", "Urban PHC Hebbal", "Primary Health Centre", 13.0358, 77.5970),
        ("BLR-ANK", "CHC Anekal", "Community Health Centre", 12.7111, 77.6956),
    ]),
    ("MYS", "Mysuru", [
        ("MYS-DVS", "District Vaccine Store, Mysuru", "District Vaccine Store", 12.2958, 76.6394),
        ("MYS-NJN", "CHC Nanjangud", "Community Health Centre", 12.1200, 76.6800),
    ]),
    ("BGM", "Belagavi", [
        ("BGM-DVS", "District Vaccine Store, Belagavi", "District Vaccine Store", 15.8497, 74.4977),
        ("BGM-GKK", "PHC Gokak", "Primary Health Centre", 16.1667, 74.8333),
    ]),
]

PRODUCTS = [
    ("Pentavalent (DTwP-HepB-Hib)", "Routine", 2, 8, "Serum Institute (demo)", "10-dose vial", 10),
    ("Measles-Rubella (MR)", "Routine", 2, 8, "Serum Institute (demo)", "5-dose vial", 5),
    ("bOPV", "Routine", -25, 8, "Bharat Biotech (demo)", "20-dose vial", 20),
    ("BCG", "Routine", 2, 8, "Green Signal (demo)", "10-dose ampoule", 10),
    ("Rotavirus (RVV)", "Routine", 2, 8, "Bharat Biotech (demo)", "5-dose vial", 5),
    ("PCV", "Routine", 2, 8, "Pneumosil (demo)", "4-dose vial", 4),
    ("Td", "Routine", 2, 8, "Biological E (demo)", "10-dose vial", 10),
    ("mRNA vaccine (ultra-cold)", "Campaign", -80, -60, "Generic mRNA (demo)", "6-dose vial", 6),
]


def wipe(db: Session):
    """DEMO ONLY: remove all rows (bypasses ORM immutability guards by design).

    On PostgreSQL this is ONE `TRUNCATE ... CASCADE` statement: it locks every table at once, so
    a separate worker process (e.g. the simulator in its own pod) cannot insert readings between
    per-table deletes and break foreign keys half-way through the wipe."""
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy import text
        names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        db.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))
    else:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
    db.commit()


def seed(db: Session, history_hours: int = 48, step_minutes: int = 5, with_scenarios: bool = True,
         history_days: int = 14) -> dict:
    from app.services.rbac import sync_rbac
    from app.services.configuration import ConfigurationService
    rnd = random.Random(42)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    # Pause background sweeps in ALL worker processes while the dataset is half-built.
    db.merge(SystemConfiguration(key="demo.seeding", value={"started": now.isoformat()},
                                 description="Demo seed in progress — worker jobs paused"))
    db.commit()
    sync_rbac(db)
    ConfigurationService.ensure_defaults(db)

    # ---- policies
    std = MonitoringPolicy(name="Vaccine refrigerator 2–8 °C", description="Standard ILR / walk-in cooler policy",
                           min_temperature=2.0, max_temperature=8.0, warning_margin=0.5, critical_after_minutes=30,
                           critical_deviation=3.0, expected_interval_seconds=15, missing_telemetry_minutes=3,
                           offline_minutes=8, approved_by="Regional Cold Chain Officer (demo)",
                           reference="DEMO-POL-001 (connectivity windows shortened for demonstration)")
    frz = MonitoringPolicy(name="Vaccine freezer −25 to −15 °C", description="Deep freezer policy",
                           min_temperature=-25.0, max_temperature=-15.0, warning_margin=1.0, critical_after_minutes=45,
                           critical_deviation=4.0, expected_interval_seconds=15, missing_telemetry_minutes=3,
                           offline_minutes=8, approved_by="Regional Cold Chain Officer (demo)", reference="DEMO-POL-002")
    ult = MonitoringPolicy(name="Ultra-low −80 to −60 °C", description="ULT freezer policy",
                           min_temperature=-80.0, max_temperature=-60.0, warning_margin=2.0, critical_after_minutes=20,
                           critical_deviation=5.0, expected_interval_seconds=15, missing_telemetry_minutes=3,
                           offline_minutes=8, approved_by="Regional Cold Chain Officer (demo)", reference="DEMO-POL-003")
    db.add_all([std, frz, ult])
    db.flush()

    # ---- org + equipment
    facilities, units, sensors = {}, [], []
    for rcode, rname, facs in REGIONS:
        region = Region(code=rcode, name=rname, description=f"{rname} district (demo)")
        db.add(region)
        db.flush()
        for fcode, fname, ftype, lat, lng in facs:
            f = Facility(code=fcode, name=fname, facility_type=ftype, region_id=region.id, latitude=lat, longitude=lng,
                         address=f"{fname}, {rname}", contact_name="Facility in-charge (demo)",
                         contact_phone="+91-00000-00000")
            db.add(f)
            db.flush()
            facilities[fcode] = f
            layout = [("ILR-1", "Ice-lined refrigerator 1", "ILR", std), ("DF-1", "Deep freezer 1", "Deep Freezer", frz)]
            if ftype == "District Vaccine Store":
                layout = [("WIC-1", "Walk-in cooler", "Walk-in Cold Room", std),
                          ("ILR-1", "Ice-lined refrigerator 1", "ILR", std),
                          ("WIF-1", "Walk-in freezer", "Walk-in Freezer", frz)]
                if rcode == "BLR":
                    layout.append(("ULT-1", "Ultra-low freezer", "ULT Freezer", ult))
            elif fcode in ("BLR-JAY", "BLR-HEB"):
                layout.append(("ILR-2", "Ice-lined refrigerator 2", "ILR", std))
            for ucode, uname, utype, pol in layout:
                u = StorageUnit(unit_code=f"{fcode}-{ucode}", name=uname, location=f"{fname} — cold room",
                                unit_type=utype, min_temperature=pol.min_temperature, max_temperature=pol.max_temperature,
                                facility_id=f.id, policy_id=pol.id, manufacturer=rnd.choice(["Vestfrost", "Haier", "B Medical"]),
                                model=rnd.choice(["MK 304", "HBC-260", "TCW 3000", "VLS 300"]),
                                serial_number=f"SN-{rnd.randint(100000, 999999)}",
                                capacity_litres=rnd.choice([100, 200, 240, 300]),
                                installed_at=now - timedelta(days=rnd.randint(300, 1500)),
                                last_service_at=now - timedelta(days=rnd.randint(30, 170)),
                                next_service_due=now + timedelta(days=rnd.randint(-3, 120)))
                db.add(u)
                db.flush()
                u.policy = pol
                units.append(u)
                s = Sensor(sensor_code=f"S-{fcode}-{ucode}", storage_unit_id=u.id, sensor_type="Temperature (PT100)",
                           status=SensorStatus.ONLINE, serial_number=f"TS-{rnd.randint(10000, 99999)}",
                           manufacturer="DemoSense", firmware_version=rnd.choice(["2.3.1", "2.4.0"]),
                           battery_level=round(rnd.uniform(55, 100), 1), provisioned_at=now - timedelta(days=200),
                           last_reading_at=now, is_simulated=True)  # avoid false 'offline' while seeding
                db.add(s)
                db.flush()
                sensors.append(s)
    db.commit()

    # ---- users & scope
    users = {}
    for email, name, role, title in USERS:
        u = User(email=email, name=name, role=role, title=title, password_hash=get_password_hash(DEMO_PASSWORD))
        db.add(u)
        db.flush()
        users[email] = u
    regions = {r.code: r for r in db.query(Region).all()}
    a = lambda user, **kw: db.add(UserRoleAssignment(user_id=user.id, role=user.role, **kw))  # noqa: E731
    for fc in ("BLR-JAY", "BLR-HEB", "BLR-DVS"):
        a(users["operator.blr@coldguard.local"], facility_id=facilities[fc].id)
    for fc in ("MYS-DVS", "MYS-NJN"):
        a(users["operator.mys@coldguard.local"], facility_id=facilities[fc].id)
    a(users["supervisor@coldguard.local"], region_id=regions["BLR"].id)
    a(users["supervisor.south@coldguard.local"], region_id=regions["MYS"].id)
    a(users["supervisor.south@coldguard.local"], region_id=regions["BGM"].id)
    for fc in ("BLR-JAY", "BLR-HEB", "BLR-DVS", "BLR-ANK"):
        a(users["technician@coldguard.local"], facility_id=facilities[fc].id)
    for fc in ("MYS-DVS", "MYS-NJN", "BGM-DVS", "BGM-GKK"):
        a(users["technician.mys@coldguard.local"], facility_id=facilities[fc].id)
    db.commit()

    # ---- products & batches (through the inventory ledger)
    from app.services.inventory import InventoryService
    products = []
    for name, cat, lo, hi, mfr, pres, doses in PRODUCTS:
        p = Product(name=name, category=cat, min_temperature=lo, max_temperature=hi, manufacturer=mfr,
                    presentation=pres, doses_per_vial=doses, description=f"{name} — demo catalogue entry")
        db.add(p)
        products.append(p)
    db.commit()
    op_blr, op_mys = users["operator.blr@coldguard.local"], users["operator.mys@coldguard.local"]
    n = 0
    for u in units:
        fac_code = u.unit_code.rsplit("-", 2)[0]
        actor = op_mys if fac_code.startswith(("MYS", "BGM")) else op_blr
        compatible = [p for p in products if p.min_temperature <= u.effective_max and p.max_temperature >= u.effective_min]
        for p in rnd.sample(compatible, k=min(len(compatible), 3 if u.unit_type != "ULT Freezer" else 1)):
            n += 1
            days = rnd.choice([12, 25, 45, 80, 160, 240, 400])
            InventoryService.receive(
                db, actor, batch_number=f"{p.name.split()[0][:4].upper()}-{now:%y}{n:04d}", product_id=p.id,
                storage_unit_id=u.id, quantity=rnd.choice([200, 400, 500, 800, 1000]),
                expiry_date=now + timedelta(days=days), manufacturing_date=now - timedelta(days=300),
                supplier="State Vaccine Store (demo)", reference=f"GRN-{n:05d}")
    # some issues so movement history isn't trivial
    for b in db.query(Batch).limit(10).all():
        try:
            InventoryService.issue(db, b, op_blr, quantity=rnd.choice([20, 40, 60]), reason="Session issue (demo)",
                                   enforce_fefo=False)
        except Exception:
            db.rollback()
    for b in db.query(Batch).all():  # backdate receipts so batches overlap historical telemetry
        b.start_time = now - timedelta(days=rnd.randint(3, 40))
    db.commit()

    # ---- calibration history
    from app.services.maintenance import CalibrationService, MaintenanceService
    tech_blr, tech_mys = users["technician@coldguard.local"], users["technician.mys@coldguard.local"]
    for i, s in enumerate(sensors):
        tech = tech_mys if s.sensor_code.startswith(("S-MYS", "S-BGM")) else tech_blr
        days_ago = 355 + (i % 4) * 4 if i % 6 == 0 else rnd.randint(30, 300)  # a few due within 14 days / overdue
        CalibrationService.record(db, tech, sensor=s, calibrated_at=now - timedelta(days=days_ago),
                                  result=CalibrationResult.PASS, reference_temperature=5.0,
                                  measured_temperature=round(5.0 + rnd.uniform(-0.2, 0.2), 2),
                                  certificate_reference=f"CAL-CERT-{rnd.randint(1000, 9999)} (demo)")

    # ---- simulated baseline telemetry (bulk insert): `history_days` back; the most recent 48 h at
    # `step_minutes` resolution (like-for-like day-over-day comparisons), older days every 30 min.
    rows = []
    recent_steps = int(min(history_hours, 48) * 60 / step_minutes)
    for s in sensors:
        u = s.storage_unit
        rng = random.Random(s.sensor_code)
        offsets = [m for m in range(history_days * 24 * 60, recent_steps * step_minutes, -30)] if history_days > 2 else []
        offsets += [k * step_minutes for k in range(recent_steps, 6, -1)]  # stop 30 min ago; the live pipeline fills the rest
        for off in offsets:
            ts = now - timedelta(minutes=off)
            t = generate("normal", off * 60, u.effective_min, u.effective_max, rng)
            rows.append(TemperatureReading(storage_unit_id=u.id, sensor_id=s.id, temperature=t, timestamp=ts,
                                           source="simulator", quality_status="valid", is_simulated=True,
                                           message_id=f"seed-{s.sensor_code}-{int(ts.timestamp())}"))
        s.last_reading_at = rows[-1].timestamp
        s.last_temperature = rows[-1].temperature
    db.add_all(rows)
    db.commit()

    summary = {"regions": len(REGIONS), "facilities": len(facilities), "storage_units": len(units),
               "sensors": len(sensors), "users": len(users), "baseline_readings": len(rows)}
    if with_scenarios:
        summary.update(_live_scenarios(db, now, sensors, users, facilities))
    db.merge(SystemConfiguration(key="demo.seeded_at", value={"at": now.isoformat(), "password_hint": "see README"},
                                 description="Demo dataset marker"))
    seeding = db.get(SystemConfiguration, "demo.seeding")
    if seeding:
        db.delete(seeding)
    db.commit()
    return summary


def _feed(db, sensor, scenario, start, end, step_s=60):
    """Push scenario readings through the REAL ingestion pipeline (creates violations,
    incidents, anomalies exactly as live telemetry would)."""
    from app.services import telemetry
    rng = random.Random(sensor.sensor_code + scenario)
    t = start
    while t <= end:
        u = sensor.storage_unit
        temp = generate(scenario, (t - start).total_seconds(), u.effective_min, u.effective_max, rng)
        if temp is not None:
            telemetry.ingest(db, {"sensor_code": sensor.sensor_code, "temperature": temp, "timestamp": t.isoformat(),
                                  "simulated": True, "message_id": f"seed-{sensor.sensor_code}-{int(t.timestamp())}",
                                  "source": "simulator"}, channel="simulator")
        t += timedelta(seconds=step_s)


def _live_scenarios(db, now, sensors, users, facilities):
    from app.models import Incident
    from app.models.enums import IncidentType
    from app.services.incident import IncidentService
    from app.services.maintenance import MaintenanceService
    from app.services.sensor_health import SensorHealthService
    from app.services.simulation import save_state

    by_code = {s.sensor_code: s for s in sensors}
    start = now - timedelta(minutes=30)
    special = {
        "S-BLR-JAY-ILR-1": "excursion",     # critical excursion, left OPEN (unacknowledged)
        "S-BLR-HEB-ILR-1": "excursion",     # -> corrective action awaiting supervisor approval
        "S-BLR-DVS-WIC-1": "fluctuation",   # repeated swings -> anomalies / pattern
        "S-MYS-NJN-ILR-1": "excursion",     # -> under supervisor review
        "S-MYS-DVS-ILR-1": "disconnect",    # offline sensor
        "S-BGM-GKK-ILR-1": "missing",       # intermittent telemetry
    }
    for s in sensors:
        scen = special.get(s.sensor_code, "normal")
        _feed(db, s, scen, start + timedelta(minutes=2) if scen == "excursion" else start, now - timedelta(seconds=30))

    op_blr, op_mys = users["operator.blr@coldguard.local"], users["operator.mys@coldguard.local"]
    sup, sup_s = users["supervisor@coldguard.local"], users["supervisor.south@coldguard.local"]
    tech = users["technician@coldguard.local"]

    class A:  # simple action payload
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def inc_for(code):
        s = by_code[code]
        return (db.query(Incident).filter(Incident.storage_unit_id == s.storage_unit_id,
                                          Incident.incident_type == IncidentType.TEMPERATURE_EXCURSION)
                .order_by(Incident.created_at).first())

    heb = inc_for("S-BLR-HEB-ILR-1")
    if heb:
        IncidentService.acknowledge(db, heb.id, op_blr, A(notes="Alarm acknowledged at facility; checking unit."))
        IncidentService.investigate(db, heb.id, op_blr, A(notes="Door found ajar after evening session; seal worn."))
        IncidentService.propose_corrective_action(
            db, heb.id, op_blr, description="Replace door gasket; add door-closure check to session-end checklist.",
            root_cause="Worn door gasket allowed warm air ingress", action_type="EQUIPMENT")
        MaintenanceService.create(db, op_blr, facility_id=heb.facility_id, storage_unit_id=heb.storage_unit_id,
                                  incident_id=heb.id, title="Replace worn door gasket on ILR-1",
                                  description="Gasket worn; door does not seal fully.",
                                  priority=MaintenancePriority.HIGH)
    njn = inc_for("S-MYS-NJN-ILR-1")
    if njn:
        IncidentService.acknowledge(db, njn.id, op_mys, A(notes="Acknowledged."))
        IncidentService.investigate(db, njn.id, op_mys, A(notes="Power cut 40 min; generator delayed."))
        ca = IncidentService.propose_corrective_action(
            db, njn.id, op_mys, description="Generator auto-start relay serviced; vaccine kept closed during outage.",
            root_cause="Grid power outage with delayed generator start", action_type="POWER")
        IncidentService.review_corrective_action(db, njn.id, ca.id, sup_s, "approve", "Approved; confirm relay test.")
        IncidentService.implement_corrective_action(db, njn.id, ca.id, op_mys, "Relay replaced and tested 3x.")
        try:
            IncidentService.verify_recovery(db, njn.id, op_mys, "Unit stable within 2–8 °C for 20 min.")
        except Exception:
            db.rollback()

    # a historical CLOSED incident for the audit trail
    anomaly_sensor = by_code["S-BLR-ANK-ILR-1"]
    hist, _ = IncidentService.open_incident(
        db, incident_type=IncidentType.EQUIPMENT_FAILURE, severity=ViolationSeverity.HIGH,
        facility_id=anomaly_sensor.storage_unit.facility_id, storage_unit_id=anomaly_sensor.storage_unit_id,
        sensor_id=anomaly_sensor.id, title="Compressor tripped (historical)", is_simulated=True,
        description="Unit alarm; compressor thermal cut-out. (demo history)", dedup_key=None)
    IncidentService.acknowledge(db, hist.id, op_blr, A(notes="Moved stock to ILR backup."))
    IncidentService.investigate(db, hist.id, op_blr, A(notes="Thermal cut-out due to blocked condenser."))
    ca = IncidentService.propose_corrective_action(db, hist.id, op_blr, description="Clean condenser; quarterly PM.",
                                                   root_cause="Dust-blocked condenser")
    IncidentService.review_corrective_action(db, hist.id, ca.id, sup, "approve", "OK")
    IncidentService.implement_corrective_action(db, hist.id, ca.id, op_blr, "Condenser cleaned.")
    IncidentService.verify_recovery(db, hist.id, op_blr, "Stable for 24 h.")
    IncidentService.review(db, hist.id, sup, "resolve", "Root cause addressed.")
    IncidentService.close(db, hist.id, sup, A(closure_evidence="PM record attached (demo)",
                                              vaccine_disposition="No stock exposed — stock was relocated before excursion.",
                                              false_alarm=False))

    # work orders at different stages
    jay_unit = by_code["S-BLR-JAY-ILR-2"].storage_unit
    t1 = MaintenanceService.create(db, op_blr, facility_id=jay_unit.facility_id, storage_unit_id=jay_unit.id,
                                   title="Thermostat display flickering", description="Display intermittently blank.",
                                   priority=MaintenancePriority.MEDIUM)
    MaintenanceService.assign(db, t1, sup, tech.id)
    MaintenanceService.start(db, t1, tech)
    MaintenanceService.add_note(db, t1, tech, "Loose ribbon cable on display board.", "INSPECTION")
    dvs_unit = by_code["S-BLR-DVS-ILR-1"].storage_unit
    t2 = MaintenanceService.create(db, op_blr, facility_id=dvs_unit.facility_id, storage_unit_id=dvs_unit.id,
                                   title="Noisy compressor fan", description="Rattling noise during cycling.",
                                   priority=MaintenancePriority.LOW, maintenance_type=MaintenanceType.INSPECTION)
    MaintenanceService.accept(db, t2, tech)
    MaintenanceService.start(db, t2, tech)
    MaintenanceService.resolve(db, t2, tech, "Fan blade re-seated, mounting screws tightened.",
                               now + timedelta(days=90))

    # connectivity sweep (on the seed's own timeline) + rule-based tickets
    SensorHealthService.check_offline_sensors(db, now=now)
    from app.services.maintenance import MaintenanceRules
    MaintenanceRules.run(db)
    save_state(db, {"running": True, "interval_seconds": 15, "scenarios": {
        str(by_code[c].id): {"scenario": sc, "started_at": (now - timedelta(minutes=40)).isoformat()}
        for c, sc in special.items() if sc in ("disconnect", "missing", "fluctuation")}})
    # Seeding can take minutes on slow hosts: emit one real (simulated) reading per sensor at the
    # CURRENT time so sweeps that resume afterwards don't see the whole fleet as stale.
    from app.services.simulation import SimulationEngine
    SimulationEngine().tick(now=datetime.now(timezone.utc), ignore_pause=True)
    logistics = _logistics_scenarios(db, users, inc_for("S-BLR-JAY-ILR-1"), inc_for("S-BLR-HEB-ILR-1"))
    return {"incidents": db.query(Incident).count(), **logistics}


def _logistics_scenarios(db, users, jay, heb):
    """Supply-chain demo (SIMULATED): relocation plans for live excursions, one vehicle in transit
    whose data logger fails half-way (transit alert + incident + nearby stores alerted), and one
    delivered shipment for history."""
    from app.models import Shipment
    from app.services.access import AccessScope
    from app.services.route_optimizer import Params, RoutePlanService
    from app.services.transit import TransitService
    admin, op_blr = users["admin@coldguard.local"], users["operator.blr@coldguard.local"]
    scope = AccessScope(user=admin, is_global=True)
    out = {"route_plans": 0, "shipments": 0, "transit_alerts": 0}
    for inc, vehicle, fail in ((jay, "KA01CC1001", True), (heb, "KA01CC2002", False)):
        if not inc:
            continue
        try:
            # demo story: the whole facility lost power, so stock must leave the site by vehicle
            res = RoutePlanService.generate(db, scope, incident_id=inc.id,
                                            params=Params(vehicles=1, allow_on_site=False))
        except Exception as exc:  # e.g. no stock left in the unit — never break seeding
            db.rollback()
            log.warning("demo logistics plan skipped for %s: %s", inc.incident_number, exc)
            continue
        out["route_plans"] += 1
        from app.models import RoutePlan
        plan = db.get(RoutePlan, uuid.UUID(res["id"]))
        if not res["trips"]:
            continue
        RoutePlanService.decide(db, plan, admin, True, "Demo: approved for relocation")
        s = TransitService.dispatch(db, plan, op_blr, vehicle, trips=[1], is_simulated=True)[0]
        out["shipments"] += 1
        src, stop = res["source"], res["trips"][0]["stops"][0]
        for k, frac in enumerate((0.2, 0.4, 0.55)):          # vehicle moving towards its first stop
            lat = src["lat"] + (stop["lat"] - src["lat"]) * frac
            lon = src["lon"] + (stop["lon"] - src["lon"]) * frac
            if fail and k == 2:
                TransitService.record_reading(db, s, lat=lat, lon=lon, temperature=None, sensor_status="FAULT")
            else:
                TransitService.record_reading(db, s, lat=lat, lon=lon, temperature=round(4.6 + k * 0.3, 1))
        if not fail:
            TransitService.deliver(db, db.get(Shipment, s.id), op_blr, "Demo: received into destination unit")
    from app.models import TransitAlert
    out["transit_alerts"] = db.query(TransitAlert).count()
    return out
