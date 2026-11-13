"""In-transit cold-chain monitoring for relocation vehicles — DECISION SUPPORT.

An APPROVED route plan is dispatched as one Shipment per vehicle trip. The vehicle's data
logger reports position and cargo temperature (`record_reading`). Three failure modes raise a
TransitAlert:

  SENSOR_FAULT           logger reports a fault, no temperature, or a physically implausible value
  SENSOR_OFFLINE         no reading for TRANSIT_OFFLINE_MINUTES (worker sweep `check_offline`)
  TEMPERATURE_EXCURSION  cargo temperature outside the strictest product range on board

For every alert, the nearest compatible cold-chain stores are ranked from the vehicle's last
known position with the ML ETA model (`nearby_storage`). Candidates must be active, hold no
active excursion / equipment / connectivity incident, have an approved range that suits every
product on board, and have room for the load. A store is "reachable" when its p90 ETA fits in
the hold time left. Then:

  * an incident (TRANSIT_SENSOR_FAILURE / TRANSIT_EXCURSION) is opened for the source facility;
  * the dispatcher (the vehicle's operator) and the source facility's operators/supervisors are
    notified with the recommended store and ETA;
  * operators of the nearby stores are alerted to prepare to receive the diverted stock.

Nothing is diverted automatically: a person diverts or confirms delivery.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import as_utc
from app.ml.eta_model import EtaModel
from app.models import Facility, Incident, RoutePlan, Shipment, StorageUnit, TransitAlert, User
from app.models.enums import (ACTIVE_INCIDENT_STATUSES, IncidentType, NotificationLevel, Role, RoutePlanStatus,
                              ShipmentStatus, StorageUnitStatus, TransitAlertStatus, TransitAlertType,
                              TransitSensorState, ViolationSeverity)
from app.services.audit import log_audit
from app.services.notification import notify, notify_facility
from app.services.route_optimizer import (BLOCKING_INCIDENTS, DEFAULT_UNIT_CAPACITY_LITRES, UNIT_FILL_LIMIT,
                                          _used_litres)

PLAUSIBLE_MIN, PLAUSIBLE_MAX = -90.0, 70.0      # outside this a logger reading is a fault, not a temperature
FAULT_STATUSES = {"FAULT", "ERROR", "SENSOR_ERROR", "LOW_BATTERY_SHUTDOWN"}
_SEVERITY = {TransitAlertType.TEMPERATURE_EXCURSION: ViolationSeverity.CRITICAL,
             TransitAlertType.SENSOR_FAULT: ViolationSeverity.HIGH,
             TransitAlertType.SENSOR_OFFLINE: ViolationSeverity.HIGH}
_INCIDENT_TYPE = {TransitAlertType.TEMPERATURE_EXCURSION: IncidentType.TRANSIT_EXCURSION,
                  TransitAlertType.SENSOR_FAULT: IncidentType.TRANSIT_SENSOR_FAILURE,
                  TransitAlertType.SENSOR_OFFLINE: IncidentType.TRANSIT_SENSOR_FAILURE}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cargo_range(trip: dict, db: Session) -> tuple[float, float]:
    """Strictest range across the batches on board (every product must stay in range)."""
    from app.models import Batch
    ids = [b["batch_id"] for st in trip.get("stops", []) for d in st["deliveries"] for b in d["batches"]]
    lo, hi = -1e9, 1e9
    for b in db.query(Batch).filter(Batch.id.in_([uuid.UUID(i) for i in ids])).all() if ids else []:
        lo, hi = max(lo, b.product.min_temperature), min(hi, b.product.max_temperature)
    if lo == -1e9:  # no batches resolved: fall back to the destinations' approved ranges
        ranges = [d["approved_range"] for st in trip.get("stops", []) for d in st["deliveries"]]
        lo, hi = max(r[0] for r in ranges), min(r[1] for r in ranges)
    return lo, hi


def minutes_in_transit(s: Shipment, at: Optional[datetime] = None) -> float:
    return max(0.0, ((at or _now()) - as_utc(s.dispatched_at)).total_seconds() / 60.0)


class TransitService:
    # ------------------------------------------------------------------ dispatch
    @staticmethod
    def dispatch(db: Session, plan: RoutePlan, user: User, vehicle_code: str, sensor_code: Optional[str] = None,
                 trips: Optional[List[int]] = None, is_simulated: bool = False) -> List[Shipment]:
        if plan.status != RoutePlanStatus.APPROVED:
            raise HTTPException(409, f"Plan is {plan.status.value}; only APPROVED plans can be dispatched")
        plan_trips = plan.plan.get("trips", [])
        if not plan_trips:
            raise HTTPException(409, "This plan has no vehicle trips (on-site moves only)")
        wanted = set(trips or [t["trip"] for t in plan_trips])
        unknown = wanted - {t["trip"] for t in plan_trips}
        if unknown:
            raise HTTPException(422, f"Unknown trip number(s): {sorted(unknown)}")
        done = {s.trip_no for s in db.query(Shipment).filter(Shipment.route_plan_id == plan.id)}
        if wanted & done:
            raise HTTPException(409, f"Trip(s) {sorted(wanted & done)} already dispatched")
        src = plan.plan.get("source", {})
        hold = float(plan.parameters.get("max_trip_minutes", 240))
        out = []
        for t in sorted((t for t in plan_trips if t["trip"] in wanted), key=lambda t: t["trip"]):
            lo, hi = _cargo_range(t, db)
            suffix = f"-{t['trip']}" if len(wanted) > 1 else ""   # one vehicle per trip
            s = Shipment(
                shipment_number=f"SH-{plan.plan_number.removeprefix('RP-')}-{t['trip']}",
                route_plan_id=plan.id, trip_no=t["trip"], facility_id=plan.facility_id,
                vehicle_code=vehicle_code.strip().upper() + suffix, cargo=t,
                sensor_code=(sensor_code or f"VDL-{vehicle_code}").strip().upper() + suffix,
                total_doses=t["doses"], load_litres=t["load_litres"], min_temperature=lo, max_temperature=hi,
                hold_minutes=hold, last_lat=src.get("lat"), last_lon=src.get("lon"), last_reading_at=_now(),
                dispatched_by=user.id, dispatched_by_name=user.name, is_simulated=is_simulated)
            db.add(s)
            out.append(s)
        db.flush()
        log_audit(db, user, "SHIPMENT_DISPATCHED", "RoutePlan", plan.id,
                  {"plan_number": plan.plan_number, "shipments": [s.shipment_number for s in out],
                   "vehicle": vehicle_code}, category="LOGISTICS", facility_id=plan.facility_id, commit=False)
        db.commit()
        return out

    # ------------------------------------------------------------------ telemetry
    @classmethod
    def record_reading(cls, db: Session, s: Shipment, *, lat: float, lon: float, temperature: Optional[float],
                       sensor_status: Optional[str] = None, timestamp: Optional[datetime] = None) -> dict:
        if s.status != ShipmentStatus.IN_TRANSIT:
            raise HTTPException(409, f"Shipment is {s.status.value}; telemetry is only accepted in transit")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise HTTPException(422, "Invalid coordinates")
        ts = as_utc(timestamp) if timestamp else _now()
        s.last_lat, s.last_lon, s.last_reading_at = lat, lon, max(ts, as_utc(s.last_reading_at) or ts)
        status = (sensor_status or "OK").upper()
        fault_reason = None
        if status in FAULT_STATUSES:
            fault_reason = f"Data logger reported {status}"
        elif temperature is None:
            fault_reason = "Data logger sent no temperature value"
        elif not (PLAUSIBLE_MIN <= temperature <= PLAUSIBLE_MAX):
            fault_reason = f"Implausible logger value {temperature:.1f} °C (sensor failure)"

        alert = None
        if fault_reason:
            s.sensor_state = TransitSensorState.FAULT
            alert = cls.raise_alert(db, s, TransitAlertType.SENSOR_FAULT, fault_reason, temperature=None)
        else:
            s.last_temperature = temperature
            s.sensor_state = TransitSensorState.OK
            cls._resolve(db, s, (TransitAlertType.SENSOR_OFFLINE, TransitAlertType.SENSOR_FAULT),
                         "Logger reporting valid readings again")
            if not (s.min_temperature <= temperature <= s.max_temperature):
                limit = s.max_temperature if temperature > s.max_temperature else s.min_temperature
                alert = cls.raise_alert(
                    db, s, TransitAlertType.TEMPERATURE_EXCURSION,
                    f"Cargo at {temperature:.1f} °C, outside {s.min_temperature:g}–{s.max_temperature:g} °C "
                    f"({temperature - limit:+.1f} °C)", temperature=temperature)
        db.commit()
        return {"shipment": s.shipment_number, "sensor_state": s.sensor_state.value,
                "alert": alert_dict(alert) if alert else None}

    # ------------------------------------------------------------------ nearby stores (ML ETA)
    @staticmethod
    def nearby_storage(db: Session, s: Shipment, lat: float, lon: float, limit: Optional[int] = None,
                       at: Optional[datetime] = None) -> List[dict]:
        limit = limit or settings.TRANSIT_NEARBY_LIMIT
        remaining = s.hold_minutes - minutes_in_transit(s, at)
        blocked = {u for (u,) in db.query(Incident.storage_unit_id).filter(
            Incident.incident_type.in_(BLOCKING_INCIDENTS), Incident.status.in_(ACTIVE_INCIDENT_STATUSES),
            Incident.storage_unit_id.isnot(None))}
        source_unit = s.route_plan.source_storage_unit_id if s.route_plan else None
        by_fac: dict = {}
        q = (db.query(StorageUnit).join(Facility, StorageUnit.facility_id == Facility.id)
             .filter(StorageUnit.status == StorageUnitStatus.ACTIVE, Facility.is_active.is_(True),
                     Facility.latitude.isnot(None), Facility.longitude.isnot(None)))
        for u in q.all():
            if u.id in blocked or u.id == source_unit:
                continue
            # the unit's approved range must lie inside the cargo's tolerated range
            if not (s.min_temperature <= u.effective_min and s.max_temperature >= u.effective_max):
                continue
            free = (u.capacity_litres or DEFAULT_UNIT_CAPACITY_LITRES) * UNIT_FILL_LIMIT - _used_litres(db, u.id)
            if free + 1e-9 < s.load_litres:
                continue
            by_fac.setdefault(u.facility, []).append({"storage_unit_id": str(u.id), "unit_code": u.unit_code,
                                                      "free_litres": round(free, 2),
                                                      "approved_range": [u.effective_min, u.effective_max]})
        if not by_fac:
            return []
        sites = [{"key": "vehicle", "lat": lat, "lon": lon, "region_id": None}]
        sites += [{"key": str(f.id), "lat": f.latitude, "lon": f.longitude, "region_id": str(f.region_id)} for f in by_fac]
        mx = EtaModel.matrix(sites, at or _now())
        out = []
        for f, units in by_fac.items():
            d, p50, p90 = mx[("vehicle", str(f.id))]
            out.append({"facility_id": str(f.id), "facility_code": f.code, "facility_name": f.name,
                        "lat": f.latitude, "lon": f.longitude, "distance_km": round(d, 2),
                        "eta_minutes": round(p50, 1), "eta_p90_minutes": round(p90, 1),
                        "reachable_within_hold": p90 <= remaining, "units": sorted(units, key=lambda x: -x["free_litres"])})
        out.sort(key=lambda x: (not x["reachable_within_hold"], x["eta_minutes"]))
        return out[:limit]

    # ------------------------------------------------------------------ alerts
    @classmethod
    def raise_alert(cls, db: Session, s: Shipment, kind: TransitAlertType, reason: str,
                    temperature: Optional[float] = None, at: Optional[datetime] = None) -> TransitAlert:
        open_alert = (db.query(TransitAlert).filter(TransitAlert.shipment_id == s.id, TransitAlert.alert_type == kind,
                                                    TransitAlert.status != TransitAlertStatus.RESOLVED).first())
        if open_alert:  # dedup: keep one active alert per failure mode, refresh position/ranking
            open_alert.lat, open_alert.lon = s.last_lat, s.last_lon
            if temperature is not None:
                open_alert.temperature = temperature
            open_alert.nearby = cls.nearby_storage(db, s, s.last_lat, s.last_lon, at=at)
            return open_alert
        mins = minutes_in_transit(s, at)
        nearby = cls.nearby_storage(db, s, s.last_lat, s.last_lon, at=at) if s.last_lat is not None else []
        best = next((n for n in nearby if n["reachable_within_hold"]), None)
        remaining = s.hold_minutes - mins
        if best:
            advice = (f"Nearest compatible store: {best['facility_name']} ({best['distance_km']:.0f} km, "
                      f"ETA ~{best['eta_minutes']:.0f} min, p90 {best['eta_p90_minutes']:.0f} min). "
                      f"Hold time left ~{max(remaining, 0):.0f} min.")
        elif nearby:
            advice = (f"No compatible store reachable within the remaining hold time (~{max(remaining, 0):.0f} min); "
                      f"closest is {nearby[0]['facility_name']} (ETA ~{nearby[0]['eta_minutes']:.0f} min).")
        else:
            advice = "No compatible store with free capacity found — contact the supervisor."
        sev = _SEVERITY[kind]
        title = f"{s.vehicle_code}: {kind.value.replace('_', ' ').lower()} in transit"
        msg = f"{reason}. Shipment {s.shipment_number}, {s.total_doses} doses, {mins:.0f} min in transit. {advice}"
        alert = TransitAlert(shipment_id=s.id, alert_type=kind, severity=sev.value, message=msg, lat=s.last_lat,
                             lon=s.last_lon, temperature=temperature, minutes_in_transit=round(mins, 1),
                             nearby=nearby, created_at=at or _now())
        db.add(alert)
        db.flush()
        from app.services.incident import IncidentService
        inc, _ = IncidentService.open_incident(
            db, incident_type=_INCIDENT_TYPE[kind], severity=sev, facility_id=s.facility_id, title=title,
            description=msg, source="RULE", dedup_key=f"TRANSIT:{s.id}:{_INCIDENT_TYPE[kind].value}",
            is_simulated=s.is_simulated, data={"shipment": s.shipment_number, "alert_type": kind.value,
                                               "lat": s.last_lat, "lon": s.last_lon})
        alert.incident_id = inc.id
        alert.notified_users = cls._notify(db, s, alert, title, msg, nearby, best)
        log_audit(db, None, "TRANSIT_ALERT_RAISED", "Shipment", s.id,
                  {"shipment": s.shipment_number, "alert_type": kind.value, "nearby": [n["facility_code"] for n in nearby]},
                  category="LOGISTICS", facility_id=s.facility_id, commit=False)
        from app.services import realtime
        realtime.publish("transit.alert", {"shipment_id": str(s.id), "alert_type": kind.value, "severity": sev.value},
                         facility_id=s.facility_id)
        return alert

    @staticmethod
    def _notify(db: Session, s: Shipment, alert: TransitAlert, title: str, msg: str, nearby: List[dict],
                best: Optional[dict]) -> int:
        level = NotificationLevel.CRITICAL if alert.severity == ViolationSeverity.CRITICAL.value else NotificationLevel.WARNING
        link = "/admin/logistics"
        kw = dict(level=level, category="LOGISTICS", link=link, entity_type="Shipment", entity_id=s.id, commit=False)
        sent = set()
        # the vehicle's operator: whoever dispatched it
        if s.dispatched_by:
            u = db.get(User, s.dispatched_by)
            if u and u.is_active:
                sent |= {n.user_id for n in notify(db, [u], title, msg, facility_id=s.facility_id, **kw)}
        if s.facility_id:
            sent |= {n.user_id for n in notify_facility(db, s.facility_id, [Role.OPERATOR, Role.SUPERVISOR], title, msg, **kw)}
        # nearby cold-chain stores: prepare to receive the load
        for n in nearby:
            unit = n["units"][0]["unit_code"] if n["units"] else "a compatible unit"
            ask = (f"{s.vehicle_code} ({s.shipment_number}) has an in-transit {alert.alert_type.value.replace('_', ' ').lower()} "
                   f"{n['distance_km']:.0f} km away (ETA ~{n['eta_minutes']:.0f} min) carrying {s.total_doses} doses "
                   f"({s.min_temperature:g}–{s.max_temperature:g} °C). Prepare {unit} to receive diverted stock"
                   f"{' — recommended destination' if best and n['facility_id'] == best['facility_id'] else ''}.")
            sent |= {x.user_id for x in notify_facility(db, uuid.UUID(n["facility_id"]), [Role.OPERATOR],
                                                        f"Incoming diversion possible: {s.vehicle_code}", ask, **kw)}
        return len(sent)

    @staticmethod
    def _resolve(db: Session, s: Shipment, kinds, note: str):
        for a in db.query(TransitAlert).filter(TransitAlert.shipment_id == s.id, TransitAlert.alert_type.in_(kinds),
                                               TransitAlert.status != TransitAlertStatus.RESOLVED):
            a.status, a.resolved_at = TransitAlertStatus.RESOLVED, _now()
            a.message = f"{a.message} [Resolved: {note}]"

    # ------------------------------------------------------------------ worker sweep
    @classmethod
    def check_offline(cls, db: Session, now: Optional[datetime] = None) -> dict:
        now = now or _now()
        cutoff = now - timedelta(minutes=settings.TRANSIT_OFFLINE_MINUTES)
        raised = 0
        for s in db.query(Shipment).filter(Shipment.status == ShipmentStatus.IN_TRANSIT,
                                           Shipment.last_reading_at < cutoff).all():
            silent = (now - as_utc(s.last_reading_at)).total_seconds() / 60
            s.sensor_state = TransitSensorState.OFFLINE
            existing = db.query(TransitAlert).filter(TransitAlert.shipment_id == s.id,
                                                     TransitAlert.alert_type == TransitAlertType.SENSOR_OFFLINE,
                                                     TransitAlert.status != TransitAlertStatus.RESOLVED).first()
            if not existing:
                cls.raise_alert(db, s, TransitAlertType.SENSOR_OFFLINE,
                                f"No data-logger reading for {silent:.0f} min (last known position used)", at=now)
                raised += 1
        db.commit()
        return {"transit_offline_alerts": raised}

    # ------------------------------------------------------------------ human actions
    @staticmethod
    def acknowledge(db: Session, alert: TransitAlert, user: User) -> TransitAlert:
        if alert.status != TransitAlertStatus.OPEN:
            raise HTTPException(409, f"Alert is {alert.status.value}")
        alert.status, alert.acknowledged_by_name, alert.acknowledged_at = TransitAlertStatus.ACKNOWLEDGED, user.name, _now()
        log_audit(db, user, "TRANSIT_ALERT_ACKNOWLEDGED", "TransitAlert", alert.id,
                  {"shipment": alert.shipment.shipment_number}, category="LOGISTICS",
                  facility_id=alert.shipment.facility_id, commit=False)
        db.commit()
        return alert

    @classmethod
    def divert(cls, db: Session, s: Shipment, facility_id, user: User, note: Optional[str]) -> Shipment:
        if s.status != ShipmentStatus.IN_TRANSIT:
            raise HTTPException(409, f"Shipment is {s.status.value}")
        f = db.get(Facility, facility_id)
        if not f or not f.is_active:
            raise HTTPException(404, "Facility not found")
        s.status, s.diverted_to_facility_id, s.closed_at = ShipmentStatus.DIVERTED, f.id, _now()
        cls._resolve(db, s, tuple(TransitAlertType), f"diverted to {f.name}")
        msg = (f"{s.vehicle_code} ({s.shipment_number}, {s.total_doses} doses) is diverting to {f.name}. "
               "Receive into a compatible unit and record the inventory transfer.")
        notify_facility(db, f.id, [Role.OPERATOR, Role.SUPERVISOR], f"Diverted shipment arriving: {s.vehicle_code}", msg,
                        level=NotificationLevel.WARNING, category="LOGISTICS", link="/admin/logistics",
                        entity_type="Shipment", entity_id=s.id, commit=False)
        log_audit(db, user, "SHIPMENT_DIVERTED", "Shipment", s.id,
                  {"shipment": s.shipment_number, "to": f.code, "note": note}, category="LOGISTICS",
                  facility_id=s.facility_id, commit=False)
        db.commit()
        return s

    @classmethod
    def deliver(cls, db: Session, s: Shipment, user: User, note: Optional[str]) -> Shipment:
        if s.status != ShipmentStatus.IN_TRANSIT:
            raise HTTPException(409, f"Shipment is {s.status.value}")
        s.status, s.closed_at = ShipmentStatus.DELIVERED, _now()
        cls._resolve(db, s, tuple(TransitAlertType), "delivered")
        log_audit(db, user, "SHIPMENT_DELIVERED", "Shipment", s.id, {"shipment": s.shipment_number, "note": note},
                  category="LOGISTICS", facility_id=s.facility_id, commit=False)
        db.commit()
        return s


# ---------------------------------------------------------------------- serialisation
def alert_dict(a: TransitAlert) -> dict:
    return {"id": str(a.id), "shipment_id": str(a.shipment_id), "alert_type": a.alert_type.value,
            "status": a.status.value, "severity": a.severity, "message": a.message, "lat": a.lat, "lon": a.lon,
            "temperature": a.temperature, "minutes_in_transit": a.minutes_in_transit, "nearby": a.nearby,
            "incident_id": str(a.incident_id) if a.incident_id else None,
            "incident_number": a.incident.incident_number if a.incident else None,
            "notified_users": a.notified_users, "created_at": a.created_at,
            "acknowledged_by_name": a.acknowledged_by_name, "acknowledged_at": a.acknowledged_at,
            "resolved_at": a.resolved_at}


def shipment_dict(s: Shipment, with_alerts: bool = True) -> dict:
    d = {"id": str(s.id), "shipment_number": s.shipment_number, "route_plan_id": str(s.route_plan_id),
         "plan_number": s.route_plan.plan_number if s.route_plan else None, "trip_no": s.trip_no,
         "status": s.status.value, "vehicle_code": s.vehicle_code, "sensor_code": s.sensor_code,
         "sensor_state": s.sensor_state.value, "facility_id": str(s.facility_id) if s.facility_id else None,
         "facility_name": s.facility.name if s.facility else None, "total_doses": s.total_doses,
         "load_litres": s.load_litres, "temperature_range": [s.min_temperature, s.max_temperature],
         "hold_minutes": s.hold_minutes, "minutes_in_transit": round(minutes_in_transit(s), 1),
         "last_lat": s.last_lat, "last_lon": s.last_lon, "last_temperature": s.last_temperature,
         "last_reading_at": s.last_reading_at, "dispatched_by_name": s.dispatched_by_name,
         "dispatched_at": s.dispatched_at, "closed_at": s.closed_at,
         "diverted_to": s.diverted_to.name if s.diverted_to else None, "is_simulated": s.is_simulated,
         "stops": [{"facility_code": st["facility_code"], "facility_name": st["facility_name"], "lat": st["lat"],
                    "lon": st["lon"], "doses": st["doses"]} for st in s.cargo.get("stops", [])],
         "open_alerts": sum(1 for a in s.alerts if a.status != TransitAlertStatus.RESOLVED)}
    if with_alerts:
        d["alerts"] = [alert_dict(a) for a in reversed(s.alerts)]
    return d

