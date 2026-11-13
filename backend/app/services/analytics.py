"""Aggregations for role dashboards and analytics. Every function takes an AccessScope and
only aggregates facilities inside it."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import fmean
from typing import Dict, List, Optional

from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session

from app.db.base import as_utc
from app.models import (Anomaly, AuditLog, Batch, CalibrationRecord, CorrectiveAction, Facility, Incident,
                        InventoryMovement, MaintenanceTicket, MonitoringPolicy, Product, Region, Sensor, StorageUnit,
                        SystemConfiguration, TelemetryQuarantine, TemperatureReading, User, Violation)
from app.models.enums import (ACTIVE_INCIDENT_STATUSES, ACTIVE_MAINTENANCE_STATUSES, BatchStatus,
                              CorrectiveActionStatus, IncidentStatus, MaintenanceStatus, MaintenanceTrigger,
                              MaintenanceType, SensorStatus, StorageUnitStatus, ViolationSeverity)
from app.services.monitoring import live_units, worst


def _now():
    return datetime.now(timezone.utc)


def _scoped_facilities(db: Session, scope):
    return scope.apply(db.query(Facility), Facility.id).all()


def compliance_by_unit(db: Session, scope, days: int = 7, facility_id=None) -> Dict:
    """% of valid readings within approved limits, per storage unit."""
    since = _now() - timedelta(days=days)
    lo = func.coalesce(MonitoringPolicy.min_temperature, StorageUnit.min_temperature)
    hi = func.coalesce(MonitoringPolicy.max_temperature, StorageUnit.max_temperature)
    q = (db.query(StorageUnit.id, StorageUnit.facility_id, func.count(TemperatureReading.id),
                  func.sum(case((and_(TemperatureReading.temperature >= lo, TemperatureReading.temperature <= hi), 1),
                                else_=0)))
         .join(TemperatureReading, TemperatureReading.storage_unit_id == StorageUnit.id)
         .outerjoin(MonitoringPolicy, MonitoringPolicy.id == StorageUnit.policy_id)
         .filter(TemperatureReading.timestamp >= since, TemperatureReading.quality_status != "invalid"))
    q = scope.apply(q, StorageUnit.facility_id)
    if facility_id:
        q = q.filter(StorageUnit.facility_id == facility_id)
    return {uid: {"facility_id": fid, "total": tot, "in_range": int(ok or 0)}
            for uid, fid, tot, ok in q.group_by(StorageUnit.id, StorageUnit.facility_id).all()}


def compliance_trend(db: Session, scope, days: int = 14, facility_id=None) -> List[dict]:
    since = (_now() - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    lo = func.coalesce(MonitoringPolicy.min_temperature, StorageUnit.min_temperature)
    hi = func.coalesce(MonitoringPolicy.max_temperature, StorageUnit.max_temperature)
    rows = (scope.apply(
        db.query(TemperatureReading.timestamp,
                 case((and_(TemperatureReading.temperature >= lo, TemperatureReading.temperature <= hi), 1), else_=0))
        .join(StorageUnit, StorageUnit.id == TemperatureReading.storage_unit_id)
        .outerjoin(MonitoringPolicy, MonitoringPolicy.id == StorageUnit.policy_id)
        .filter(TemperatureReading.timestamp >= since), StorageUnit.facility_id))
    if facility_id:
        rows = rows.filter(StorageUnit.facility_id == facility_id)
    agg = defaultdict(lambda: [0, 0])
    for ts, ok in rows.all():
        d = as_utc(ts).date().isoformat()
        agg[d][0] += 1
        agg[d][1] += ok
    out = []
    for i in range(days):
        d = (since + timedelta(days=i)).date().isoformat()
        tot, ok = agg.get(d, [0, 0])
        out.append({"date": d, "readings": tot, "compliance": round(100 * ok / tot, 2) if tot else None})
    return out


def incident_stats(incidents: List[Incident]) -> dict:
    ack = [(as_utc(i.acknowledged_at) - as_utc(i.created_at)).total_seconds() / 60 for i in incidents if i.acknowledged_at]
    res = [(as_utc(i.resolved_at) - as_utc(i.created_at)).total_seconds() / 3600 for i in incidents if i.resolved_at]
    return {"count": len(incidents),
            "mean_time_to_acknowledge_min": round(fmean(ack), 1) if ack else None,
            "mean_time_to_resolve_h": round(fmean(res), 2) if res else None}


def facility_summaries(db: Session, scope, units: Optional[List[dict]] = None) -> List[dict]:
    facilities = _scoped_facilities(db, scope)
    units = units if units is not None else live_units(db, scope, include_sparkline=False)
    by_fac = defaultdict(list)
    for u in units:
        by_fac[u["facility_id"]].append(u)
    inc = defaultdict(lambda: [0, 0])
    for fid, sev in (scope.apply(db.query(Incident.facility_id, Incident.severity)
                                 .filter(Incident.status.in_(ACTIVE_INCIDENT_STATUSES)), Incident.facility_id).all()):
        inc[fid][0] += 1
        inc[fid][1] += int(sev == ViolationSeverity.CRITICAL)
    regions = {r.id: r.name for r in db.query(Region).all()}
    out = []
    for f in facilities:
        us = by_fac.get(f.id, [])
        sensors = [s for u in us for s in u["sensors"]]
        health = worst([u["health"] for u in us]) if us else "NO_DATA"
        if inc[f.id][1]:
            health = "CRITICAL"
        out.append({"id": f.id, "code": f.code, "name": f.name, "facility_type": f.facility_type,
                    "region_id": f.region_id, "region_name": regions.get(f.region_id), "latitude": f.latitude,
                    "longitude": f.longitude, "is_active": f.is_active, "address": f.address,
                    "contact_name": f.contact_name, "contact_phone": f.contact_phone, "created_at": f.created_at,
                    "storage_units": len(us), "sensors_total": len(sensors),
                    "sensors_online": sum(1 for s in sensors if s["status"] == "ONLINE"),
                    "active_incidents": inc[f.id][0], "critical_incidents": inc[f.id][1], "health": health,
                    "unit_health": {h: sum(1 for u in us if u["health"] == h) for h in {u["health"] for u in us}}})
    return out


def hourly_ingestion(db: Session, scope, hours: int = 24) -> List[dict]:
    since = (_now() - timedelta(hours=hours - 1)).replace(minute=0, second=0, microsecond=0)
    q = scope.apply(db.query(TemperatureReading.timestamp, TemperatureReading.is_simulated)
                    .join(StorageUnit, StorageUnit.id == TemperatureReading.storage_unit_id)
                    .filter(TemperatureReading.timestamp >= since), StorageUnit.facility_id)
    agg = defaultdict(lambda: [0, 0])
    for ts, sim in q.all():
        k = as_utc(ts).replace(minute=0, second=0, microsecond=0)
        agg[k][1 if sim else 0] += 1
    return [{"hour": (since + timedelta(hours=i)).isoformat(),
             "device": agg[since + timedelta(hours=i)][0], "simulated": agg[since + timedelta(hours=i)][1]}
            for i in range(hours)]


def incidents_per_day(db: Session, scope, days: int = 14) -> List[dict]:
    since = (_now() - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = scope.apply(db.query(Incident.created_at, Incident.severity).filter(Incident.created_at >= since),
                       Incident.facility_id).all()
    agg = defaultdict(lambda: defaultdict(int))
    for ts, sev in rows:
        agg[as_utc(ts).date().isoformat()][sev.value] += 1
    out = []
    for i in range(days):
        d = (since + timedelta(days=i)).date().isoformat()
        out.append({"date": d, "WARNING": agg[d]["WARNING"], "HIGH": agg[d]["HIGH"], "CRITICAL": agg[d]["CRITICAL"]})
    return out


def device_reliability(db: Session, scope, hours: int = 24) -> List[dict]:
    since = _now() - timedelta(hours=hours)
    counts = dict(scope.apply(db.query(TemperatureReading.sensor_id, func.count(TemperatureReading.id))
                              .join(StorageUnit, StorageUnit.id == TemperatureReading.storage_unit_id)
                              .filter(TemperatureReading.timestamp >= since), StorageUnit.facility_id)
                  .group_by(TemperatureReading.sensor_id).all())
    sensors = scope.apply(db.query(Sensor).join(StorageUnit, StorageUnit.id == Sensor.storage_unit_id)
                          .filter(Sensor.status != SensorStatus.DECOMMISSIONED), StorageUnit.facility_id).all()
    out = []
    for s in sensors:
        interval = s.storage_unit.policy.expected_interval_seconds if s.storage_unit.policy else 60
        expected = hours * 3600 / interval
        got = counts.get(s.id, 0)
        out.append({"sensor_id": s.id, "sensor_code": s.sensor_code, "storage_unit_code": s.storage_unit.unit_code,
                    "facility_id": s.storage_unit.facility_id, "status": s.status.value, "readings": got,
                    "expected": int(expected), "availability": round(min(100.0, 100 * got / expected), 1) if expected else None,
                    "battery_level": s.battery_level, "is_simulated": s.is_simulated})
    return sorted(out, key=lambda r: r["availability"] if r["availability"] is not None else 0)


def system_status(db: Session) -> dict:
    from app.services.realtime import hub
    from sqlalchemy import text
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    hb = db.get(SystemConfiguration, "worker.heartbeat")
    hb_at = datetime.fromisoformat(hb.value["at"]) if hb and isinstance(hb.value, dict) and hb.value.get("at") else None
    worker_ok = hb_at is not None and (_now() - hb_at).total_seconds() < 180
    from app.core.config import settings
    mqtt = None
    if settings.MQTT_ENABLED:
        from app.workers.mqtt_ingestor import ingestor
        mqtt = ingestor.connected if settings.RUN_EMBEDDED_WORKER else (hb.value.get("mqtt") if hb else None)
    last_hour = db.query(func.count(TemperatureReading.id)).filter(
        TemperatureReading.created_at >= _now() - timedelta(hours=1)).scalar()
    return {"api": "ok", "database": "ok" if db_ok else "down",
            "worker": "ok" if worker_ok else "stale", "worker_heartbeat": hb_at,
            "mqtt": "disabled" if not settings.MQTT_ENABLED else ("connected" if mqtt else "disconnected"),
            "redis": {None: "disabled", True: "ok", False: "down"}[hub.redis_ok()],
            "ingested_last_hour": last_hour,
            "quarantined_last_24h": db.query(func.count(TelemetryQuarantine.id)).filter(
                TelemetryQuarantine.received_at >= _now() - timedelta(hours=24)).scalar(),
            "environment": settings.ENVIRONMENT, "demo_mode": settings.DEMO_MODE, "version": settings.VERSION}


def _pct_change(cur, prev):
    if cur is None or prev in (None, 0):
        return None
    return round(100.0 * (cur - prev) / prev, 1)


def period_deltas(db: Session, scope, facility_id=None) -> dict:
    """Period-over-period figures for KPI delta chips (current vs previous equal period)."""
    now = _now()
    def inc_count(a, b):
        q = scope.apply(db.query(func.count(Incident.id)).filter(Incident.created_at >= a, Incident.created_at < b), Incident.facility_id)
        if facility_id:
            q = q.filter(Incident.facility_id == facility_id)
        return q.scalar() or 0
    inc_cur, inc_prev = inc_count(now - timedelta(days=7), now), inc_count(now - timedelta(days=14), now - timedelta(days=7))
    trend = compliance_trend(db, scope, 14, facility_id)

    def wavg(rows):
        tot = sum(r["readings"] for r in rows if r["compliance"] is not None)
        return round(sum(r["compliance"] * r["readings"] for r in rows if r["compliance"] is not None) / tot, 2) if tot else None
    comp_prev, comp_cur = wavg(trend[:7]), wavg(trend[7:])

    def readings(a, b):
        q = scope.apply(db.query(func.count(TemperatureReading.id)).join(StorageUnit, StorageUnit.id == TemperatureReading.storage_unit_id)
                        .filter(TemperatureReading.timestamp >= a, TemperatureReading.timestamp < b), StorageUnit.facility_id)
        return q.scalar() or 0
    r_cur, r_prev = readings(now - timedelta(hours=24), now), readings(now - timedelta(hours=48), now - timedelta(hours=24))
    return {
        "incidents_7d": inc_cur, "incidents_prev_7d": inc_prev, "incidents_change_pct": _pct_change(inc_cur, inc_prev),
        "compliance_7d": comp_cur, "compliance_prev_7d": comp_prev,
        "compliance_change_pts": round(comp_cur - comp_prev, 2) if comp_cur is not None and comp_prev is not None else None,
        "readings_24h": r_cur, "readings_prev_24h": r_prev, "readings_change_pct": _pct_change(r_cur, r_prev),
    }


# --------------------------------------------------------------------------- role dashboards
def admin_overview(db: Session, scope) -> dict:
    sensors = db.query(Sensor.status, func.count(Sensor.id)).group_by(Sensor.status).all()
    by_status = {s.value: n for s, n in sensors}
    users = db.query(User.role, User.is_active, func.count(User.id)).group_by(User.role, User.is_active).all()
    active_inc = db.query(Incident.severity, func.count(Incident.id)).filter(
        Incident.status.in_(ACTIVE_INCIDENT_STATUSES)).group_by(Incident.severity).all()
    facs = facility_summaries(db, scope)
    return {
        "kpis": {
            "facilities": len(facs), "facilities_active": sum(1 for f in facs if f["is_active"]),
            "storage_units": db.query(func.count(StorageUnit.id)).filter(StorageUnit.status != StorageUnitStatus.INACTIVE).scalar(),
            "sensors_total": sum(n for s, n in by_status.items() if s != "DECOMMISSIONED"),
            "sensors_online": by_status.get("ONLINE", 0),
            "sensors_offline": by_status.get("OFFLINE", 0) + by_status.get("ERROR", 0),
            "users_total": sum(n for _, _, n in users), "users_active": sum(n for _, a, n in users if a),
            "active_incidents": sum(n for _, n in active_inc),
            "critical_incidents": sum(n for s, n in active_inc if s == ViolationSeverity.CRITICAL),
        },
        "sensors_by_status": by_status,
        "users_by_role": {r.value: sum(n for rr, _, n in users if rr == r) for r in {u[0] for u in users}},
        "incidents_by_severity": {s.value: n for s, n in active_inc},
        "system": system_status(db),
        "ingestion": hourly_ingestion(db, scope),
        "incidents_per_day": incidents_per_day(db, scope),
        "facilities": facs,
        "device_reliability": device_reliability(db, scope)[:8],
        "deltas": period_deltas(db, scope),
        "recent_security_events": [
            {"action": a.action, "actor": a.actor_name, "outcome": a.outcome, "timestamp": a.timestamp}
            for a in db.query(AuditLog).filter(AuditLog.category.in_(["SECURITY", "CONFIG"]))
            .order_by(AuditLog.timestamp.desc()).limit(8)],
    }


def pending_actions(db: Session, scope, facility_id=None) -> List[dict]:
    items = []
    q = scope.apply(db.query(Incident).filter(Incident.status.in_([IncidentStatus.OPEN, IncidentStatus.DETECTED])),
                    Incident.facility_id)
    if facility_id:
        q = q.filter(Incident.facility_id == facility_id)
    for i in q.order_by(Incident.created_at).limit(20):
        items.append({"kind": "ACKNOWLEDGE_INCIDENT", "title": f"Acknowledge {i.incident_number}",
                      "detail": i.title, "severity": i.severity.value, "link": f"/incidents/{i.id}", "at": i.created_at})
    q = (scope.apply(db.query(CorrectiveAction).join(Incident), Incident.facility_id)
         .filter(CorrectiveAction.status == CorrectiveActionStatus.APPROVED))
    if facility_id:
        q = q.filter(Incident.facility_id == facility_id)
    for ca in q.limit(20):
        items.append({"kind": "IMPLEMENT_CORRECTIVE_ACTION", "title": f"Implement action for {ca.incident.incident_number}",
                      "detail": ca.description, "severity": ca.incident.severity.value,
                      "link": f"/incidents/{ca.incident_id}", "at": ca.reviewed_at})
    q = scope.apply(db.query(Incident).filter(Incident.status == IncidentStatus.INVESTIGATING,
                                              Incident.review_decision == "MORE_INVESTIGATION"), Incident.facility_id)
    for i in q.limit(10):
        items.append({"kind": "FURTHER_INVESTIGATION", "title": f"Supervisor requested more on {i.incident_number}",
                      "detail": i.title, "severity": i.severity.value, "link": f"/incidents/{i.id}", "at": i.reviewed_at})
    q = scope.apply(db.query(MaintenanceTicket).filter(MaintenanceTicket.status == MaintenanceStatus.RESOLVED),
                    MaintenanceTicket.facility_id)
    if facility_id:
        q = q.filter(MaintenanceTicket.facility_id == facility_id)
    for t in q.limit(20):
        items.append({"kind": "VERIFY_REPAIR", "title": f"Verify repair {t.ticket_number}", "detail": t.title,
                      "severity": "INFO", "link": f"/maintenance/{t.id}", "at": t.resolved_at})
    return items


def stock_overview(db: Session, scope, facility_id=None) -> dict:
    q = scope.apply(db.query(Batch), Batch.facility_id)
    if facility_id:
        q = q.filter(Batch.facility_id == facility_id)
    batches = q.all()
    now = _now()
    by_product = defaultdict(int)
    for b in batches:
        if b.status == BatchStatus.ACTIVE:
            by_product[b.product.name] += b.current_quantity
    return {
        "batches_active": sum(1 for b in batches if b.status == BatchStatus.ACTIVE),
        "batches_quarantined": sum(1 for b in batches if b.status == BatchStatus.QUARANTINED),
        "batches_expired": sum(1 for b in batches if b.status == BatchStatus.EXPIRED),
        "doses_available": sum(b.current_quantity for b in batches if b.status == BatchStatus.ACTIVE),
        "expiring_30d": sum(1 for b in batches if b.status == BatchStatus.ACTIVE
                            and as_utc(b.expiry_date) <= now + timedelta(days=30)),
        "by_product": [{"product": k, "doses": v} for k, v in sorted(by_product.items(), key=lambda x: -x[1])],
    }


def operator_dashboard(db: Session, scope, facility_id=None) -> dict:
    units = live_units(db, scope, facility_id)
    counts = defaultdict(int)
    for u in units:
        counts[u["health"]] += 1
    q = scope.apply(db.query(Incident).filter(Incident.status.in_(ACTIVE_INCIDENT_STATUSES)), Incident.facility_id)
    if facility_id:
        q = q.filter(Incident.facility_id == facility_id)
    active = q.order_by(Incident.created_at.desc()).all()
    return {
        "facility_health": worst([u["health"] for u in units]) if units else "NO_DATA",
        "unit_counts": {"total": len(units), **counts},
        "units": units,
        "active_incidents": [_inc_brief(i) for i in active[:15]],
        "active_incident_count": len(active),
        "pending_actions": pending_actions(db, scope, facility_id),
        "stock": stock_overview(db, scope, facility_id),
        "facilities": [{"id": f.id, "name": f.name, "code": f.code} for f in _scoped_facilities(db, scope)],
        "deltas": period_deltas(db, scope, facility_id),
    }


def _inc_brief(i: Incident) -> dict:
    return {"id": i.id, "incident_number": i.incident_number, "incident_type": i.incident_type.value,
            "severity": i.severity.value, "status": i.status.value, "title": i.title, "created_at": i.created_at,
            "facility_id": i.facility_id, "storage_unit_id": i.storage_unit_id, "escalation_level": i.escalation_level,
            "is_simulated": i.is_simulated, "unit_code": i.storage_unit.unit_code if i.storage_unit else None,
            "facility_name": i.facility.name if i.facility else None}


def facility_comparison(db: Session, scope, days: int = 30) -> List[dict]:
    since = _now() - timedelta(days=days)
    comp = compliance_by_unit(db, scope, days=min(days, 14))
    by_fac = defaultdict(lambda: [0, 0])
    for v in comp.values():
        by_fac[v["facility_id"]][0] += v["total"]
        by_fac[v["facility_id"]][1] += v["in_range"]
    incs = scope.apply(db.query(Incident).filter(Incident.created_at >= since), Incident.facility_id).all()
    inc_by = defaultdict(list)
    for i in incs:
        inc_by[i.facility_id].append(i)
    exc = dict(scope.apply(db.query(StorageUnit.facility_id, func.count(Violation.id))
                           .join(Violation, Violation.storage_unit_id == StorageUnit.id)
                           .filter(Violation.start_time >= since), StorageUnit.facility_id)
               .group_by(StorageUnit.facility_id).all())
    maint = dict(scope.apply(db.query(MaintenanceTicket.facility_id, func.count(MaintenanceTicket.id))
                             .filter(MaintenanceTicket.created_at >= since,
                                     MaintenanceTicket.maintenance_type.in_([MaintenanceType.CORRECTIVE, MaintenanceType.INSPECTION])),
                             MaintenanceTicket.facility_id).group_by(MaintenanceTicket.facility_id).all())
    out = []
    for f in _scoped_facilities(db, scope):
        tot, ok = by_fac.get(f.id, [0, 0])
        st = incident_stats(inc_by.get(f.id, []))
        out.append({"facility_id": f.id, "facility_name": f.name, "code": f.code, "region_id": f.region_id,
                    "compliance": round(100 * ok / tot, 2) if tot else None, "readings": tot,
                    "excursions": exc.get(f.id, 0), "incidents": st["count"],
                    "mtta_min": st["mean_time_to_acknowledge_min"], "mttr_h": st["mean_time_to_resolve_h"],
                    "equipment_failures": maint.get(f.id, 0)})
    return sorted(out, key=lambda r: (r["compliance"] is None, r["compliance"] or 0))


def supervisor_insights(db: Session, scope, facs: List[dict]) -> dict:
    """Three compact trend insights with the most-affected facility and period change."""
    now = _now()
    names = {f["id"]: f["name"] for f in facs}
    since = (now - timedelta(days=13)).replace(hour=0, minute=0, second=0, microsecond=0)
    vrows = scope.apply(db.query(Violation.start_time, StorageUnit.facility_id).join(StorageUnit, StorageUnit.id == Violation.storage_unit_id)
                        .filter(Violation.start_time >= since), StorageUnit.facility_id).all()
    per_day, per_fac = defaultdict(int), defaultdict(int)
    for ts, fid in vrows:
        per_day[as_utc(ts).date().isoformat()] += 1
        per_fac[fid] += 1
    days = [(since + timedelta(days=i)).date().isoformat() for i in range(14)]
    exc_series = [{"x": d[5:], "v": per_day.get(d, 0)} for d in days]
    cur, prev = sum(r["v"] for r in exc_series[7:]), sum(r["v"] for r in exc_series[:7])
    top_fac = max(per_fac, key=per_fac.get) if per_fac else None

    rel = device_reliability(db, scope, 24)
    by_fac = defaultdict(list)
    for r in rel:
        if r["availability"] is not None:
            by_fac[r["facility_id"]].append(r["availability"])
    fac_avail = {fid: sum(v) / len(v) for fid, v in by_fac.items()}
    worst_fac = min(fac_avail, key=fac_avail.get) if fac_avail else None
    ing = hourly_ingestion(db, scope, 24)
    ing_series = [{"x": r["hour"][11:13] + "h", "v": r["device"] + r["simulated"]} for r in ing]
    first, last = sum(r["v"] for r in ing_series[:12]), sum(r["v"] for r in ing_series[12:])

    sensors = scope.apply(db.query(Sensor.calibration_due_at, StorageUnit.facility_id).join(StorageUnit, StorageUnit.id == Sensor.storage_unit_id)
                          .filter(Sensor.status != SensorStatus.DECOMMISSIONED), StorageUnit.facility_id).all()
    weeks = []
    for w in range(8):
        end = now + timedelta(weeks=w + 1)
        weeks.append({"x": f"W{w + 1}", "v": sum(1 for d, _ in sensors if d and as_utc(d) <= end)})
    due_fac = defaultdict(int)
    for d, fid in sensors:
        if d and as_utc(d) <= now + timedelta(weeks=8):
            due_fac[fid] += 1
    cal_top = max(due_fac, key=due_fac.get) if due_fac else None
    total_readings = sum(r["v"] for r in ing_series)
    return {
        "excursions": {"series": exc_series, "facility": names.get(top_fac, "—"), "change_pct": _pct_change(cur, prev),
                       "current": cur, "confidence": "High" if total_readings > 2000 else "Medium" if total_readings > 200 else "Low"},
        "availability": {"series": ing_series, "facility": names.get(worst_fac, "—"),
                         "facility_availability": round(fac_avail[worst_fac], 1) if worst_fac else None,
                         "change_pct": _pct_change(last, first), "confidence": "High" if len(rel) >= 10 else "Medium"},
        "calibration": {"series": weeks, "facility": names.get(cal_top, "—"), "due_8w": weeks[-1]["v"] if weeks else 0,
                        "overdue": sum(1 for d, _ in sensors if d and as_utc(d) < now), "confidence": "High"},
    }


def supervisor_dashboard(db: Session, scope) -> dict:
    units = live_units(db, scope, include_sparkline=False)
    facs = facility_summaries(db, scope, units)
    healthy = sum(1 for f in facs if f["health"] in ("NORMAL",))
    warning = sum(1 for f in facs if f["health"] in ("WARNING", "MISSING_TELEMETRY", "OFFLINE", "NO_DATA"))
    critical = sum(1 for f in facs if f["health"] == "CRITICAL")
    active = scope.apply(db.query(Incident).filter(Incident.status.in_(ACTIVE_INCIDENT_STATUSES)), Incident.facility_id).all()
    approvals = (scope.apply(db.query(CorrectiveAction).join(Incident), Incident.facility_id)
                 .filter(CorrectiveAction.status == CorrectiveActionStatus.PROPOSED).all())
    reviews = [i for i in active if i.status == IncidentStatus.UNDER_REVIEW]
    quarantined = scope.apply(db.query(Batch).filter(Batch.status == BatchStatus.QUARANTINED), Batch.facility_id).all()
    comp = compliance_by_unit(db, scope, days=7)
    tot = sum(v["total"] for v in comp.values())
    ok = sum(v["in_range"] for v in comp.values())
    overdue_ca = [ca for ca in (scope.apply(db.query(CorrectiveAction).join(Incident), Incident.facility_id)
                                .filter(CorrectiveAction.status == CorrectiveActionStatus.APPROVED).all())
                  if ca.due_date and as_utc(ca.due_date) < _now()]
    return {
        "kpis": {"facilities": len(facs), "healthy": healthy, "warning": warning, "critical": critical,
                 "unresolved_incidents": len(active), "escalated": sum(1 for i in active if i.escalation_level > 0),
                 "compliance_7d": round(100 * ok / tot, 2) if tot else None,
                 "approvals_pending": len(approvals) + len(reviews), "quarantined_batches": len(quarantined),
                 "overdue_corrective_actions": len(overdue_ca)},
        "facilities": facs,
        "deltas": period_deltas(db, scope),
        "insights": supervisor_insights(db, scope, facs),
        "regions": [{"id": r.id, "name": r.name, "code": r.code} for r in db.query(Region).all()
                    if scope.is_global or r.id in scope.region_ids or any(f["region_id"] == r.id for f in facs)],
        "approval_queue": [
            *[{"kind": "CORRECTIVE_ACTION", "incident_id": ca.incident_id, "incident_number": ca.incident.incident_number,
               "facility_name": ca.incident.facility.name if ca.incident.facility else None, "title": ca.description,
               "proposed_by": ca.proposer.name, "severity": ca.incident.severity.value, "at": ca.created_at,
               "corrective_action_id": ca.id} for ca in approvals],
            *[{"kind": "INCIDENT_REVIEW", "incident_id": i.id, "incident_number": i.incident_number,
               "facility_name": i.facility.name if i.facility else None, "title": i.title, "proposed_by": None,
               "severity": i.severity.value, "at": i.recovery_verified_at} for i in reviews]],
        "escalated_incidents": [_inc_brief(i) for i in sorted(active, key=lambda x: -x.escalation_level)
                                if i.escalation_level > 0 or i.severity == ViolationSeverity.CRITICAL][:10],
        "compliance_trend": compliance_trend(db, scope, 14),
        "incidents_per_day": incidents_per_day(db, scope, 14),
        "facility_comparison": facility_comparison(db, scope, 30),
        "quarantined_batches": [{"id": b.id, "batch_number": b.batch_number, "product": b.product.name,
                                 "facility_id": b.facility_id, "quantity": b.current_quantity,
                                 "reason": b.quarantine_reason} for b in quarantined],
    }


def technician_dashboard(db: Session, scope, user: User) -> dict:
    now = _now()
    tq = scope.apply(db.query(MaintenanceTicket), MaintenanceTicket.facility_id)
    tickets = tq.all()
    mine = [t for t in tickets if t.assigned_to == user.id]
    active = [t for t in tickets if t.status in ACTIVE_MAINTENANCE_STATUSES]
    overdue = [t for t in active if t.due_date and as_utc(t.due_date) < now]
    weeks = []
    start = (now - timedelta(weeks=11)).replace(hour=0, minute=0, second=0, microsecond=0)
    for w in range(12):
        a, b = start + timedelta(weeks=w), start + timedelta(weeks=w + 1)
        created = [t for t in tickets if a <= as_utc(t.created_at) < b]
        weeks.append({"week": a.date().isoformat(),
                      "preventive": sum(1 for t in created if t.maintenance_type in (MaintenanceType.PREVENTIVE, MaintenanceType.CALIBRATION)),
                      "corrective": sum(1 for t in created if t.maintenance_type not in (MaintenanceType.PREVENTIVE, MaintenanceType.CALIBRATION)),
                      "completed": sum(1 for t in tickets if t.resolved_at and a <= as_utc(t.resolved_at) < b)})
    by_type = defaultdict(int)
    for t in active:
        by_type[t.maintenance_type.value] += 1
    by_trigger = defaultdict(int)
    for t in active:
        by_trigger[t.trigger.value] += 1
    sensors = scope.apply(db.query(Sensor).join(StorageUnit, StorageUnit.id == Sensor.storage_unit_id)
                          .filter(Sensor.status != SensorStatus.DECOMMISSIONED), StorageUnit.facility_id).all()
    return {
        "kpis": {"open_requests": sum(1 for t in tickets if t.status == MaintenanceStatus.OPEN),
                 "my_assigned": sum(1 for t in mine if t.status == MaintenanceStatus.ASSIGNED),
                 "in_progress": sum(1 for t in mine if t.status == MaintenanceStatus.IN_PROGRESS),
                 "completed_30d": sum(1 for t in mine if t.resolved_at and as_utc(t.resolved_at) >= now - timedelta(days=30)),
                 "overdue": len(overdue),
                 "pm_due_30d": sum(1 for t in active if t.maintenance_type in (MaintenanceType.PREVENTIVE, MaintenanceType.CALIBRATION)),
                 "calibration_due_30d": sum(1 for s in sensors if s.calibration_due_at and as_utc(s.calibration_due_at) <= now + timedelta(days=30)),
                 "sensors_offline": sum(1 for s in sensors if s.status in (SensorStatus.OFFLINE, SensorStatus.ERROR)),
                 "low_battery": sum(1 for s in sensors if s.battery_level is not None and s.battery_level < 20)},
        "overdue_gauge": {"overdue": len(overdue), "active": len(active)},
        "deltas": {"completed_30d": sum(1 for t in mine if t.resolved_at and as_utc(t.resolved_at) >= now - timedelta(days=30)),
                   "completed_prev_30d": sum(1 for t in mine if t.resolved_at and now - timedelta(days=60) <= as_utc(t.resolved_at) < now - timedelta(days=30)),
                   "created_30d": sum(1 for t in tickets if as_utc(t.created_at) >= now - timedelta(days=30)),
                   "created_prev_30d": sum(1 for t in tickets if now - timedelta(days=60) <= as_utc(t.created_at) < now - timedelta(days=30))},
        "work_orders_over_time": weeks,
        "active_by_type": [{"type": k, "count": v} for k, v in by_type.items()],
        "active_by_trigger": [{"trigger": k, "count": v} for k, v in by_trigger.items()],
        "my_work_orders": [_ticket_brief(t) for t in sorted(mine, key=lambda t: as_utc(t.due_date) or now)
                           if t.status not in (MaintenanceStatus.CLOSED,)][:20],
        "unassigned": [_ticket_brief(t) for t in active if t.status == MaintenanceStatus.OPEN][:20],
        "equipment": [{"sensor_id": s.id, "sensor_code": s.sensor_code, "unit_code": s.storage_unit.unit_code,
                       "facility_id": s.storage_unit.facility_id, "status": s.status.value,
                       "battery_level": s.battery_level, "last_reading_at": s.last_reading_at,
                       "calibration_due_at": s.calibration_due_at, "firmware_version": s.firmware_version,
                       "is_simulated": s.is_simulated} for s in sensors],
    }


def _ticket_brief(t: MaintenanceTicket) -> dict:
    return {"id": t.id, "ticket_number": t.ticket_number, "title": t.title, "status": t.status.value,
            "priority": t.priority.value, "maintenance_type": t.maintenance_type.value, "trigger": t.trigger.value,
            "due_date": t.due_date, "facility_id": t.facility_id,
            "facility_name": t.facility.name if t.facility else None,
            "unit_code": t.storage_unit.unit_code if t.storage_unit else None,
            "is_overdue": bool(t.due_date and as_utc(t.due_date) < _now()
                               and t.status in ACTIVE_MAINTENANCE_STATUSES)}


def auditor_home(db: Session, scope) -> dict:
    since = _now() - timedelta(days=30)
    cats = db.query(AuditLog.category, func.count(AuditLog.id)).filter(AuditLog.timestamp >= since).group_by(AuditLog.category).all()
    return {
        "kpis": {"audit_events_30d": sum(n for _, n in cats),
                 "security_events_30d": sum(n for c, n in cats if c == "SECURITY"),
                 "incidents_closed_30d": db.query(func.count(Incident.id)).filter(Incident.closed_at >= since).scalar(),
                 "dispositions_30d": db.query(func.count(AuditLog.id)).filter(AuditLog.category == "DISPOSITION",
                                                                             AuditLog.timestamp >= since).scalar(),
                 "movements_30d": db.query(func.count(InventoryMovement.id)).filter(InventoryMovement.created_at >= since).scalar(),
                 "calibrations_30d": db.query(func.count(CalibrationRecord.id)).filter(CalibrationRecord.calibrated_at >= since).scalar(),
                 "quarantined_telemetry_30d": db.query(func.count(TelemetryQuarantine.id)).filter(TelemetryQuarantine.received_at >= since).scalar(),
                 "anomalies_30d": db.query(func.count(Anomaly.id)).filter(Anomaly.detected_at >= since).scalar()},
        "events_by_category": {c: n for c, n in cats},
        "deltas": period_deltas(db, scope),
        "compliance_trend": compliance_trend(db, scope, 14),
        "recent_audit": [{"id": a.id, "action": a.action, "actor": a.actor_name, "role": a.actor_role,
                          "entity_type": a.entity_type, "category": a.category, "outcome": a.outcome,
                          "timestamp": a.timestamp} for a in db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(15)],
        "facility_comparison": facility_comparison(db, scope, 30),
    }


_ = (Product, MaintenanceTrigger)
