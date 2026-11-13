"""Excursion relocation route optimisation — DECISION SUPPORT ONLY.

When a storage unit is in a temperature excursion, the stock inside it should be moved to
safe, compatible storage as fast as possible. This module proposes *where* each batch
should go and *in which order* a cold-box vehicle should visit the receiving facilities.

Pipeline
  1. Cargo        ACTIVE / QUARANTINED batches with stock in the source unit.
  2. Candidates   other ACTIVE units in scope at active facilities with coordinates, no
                  active excursion / equipment / connectivity incident, compatible approved
                  range and free capacity.
  3. ETA matrix   ML quantile model (`app.ml.eta_model`): p50 = routing cost, p90 = the
                  conservative bound checked against the cold-box hold time.
  4. Assignment   batches in priority order (doses x heat-sensitivity) go to the feasible
                  unit with the lowest p50 from the source; opening an extra stop costs
                  `STOP_PENALTY_MINUTES` so loads consolidate.
  5. Routing      stops are packed into trips (vehicle capacity + p90 hold time), each trip
                  is ordered to minimise dose-weighted arrival time (exact permutation search
                  up to `EXACT_MAX_STOPS` stops, 2-opt beyond), and trips are scheduled on the
                  vehicle that frees up first.
  6. Baseline     the same cargo routed the way a planner without the tool would: nearest
                  compatible facility by straight-line distance, radial visiting order, one
                  vehicle — evaluated with the SAME ETA matrix so only plan quality differs.

The core (`optimise`) is pure and DB-free; `RoutePlanService` adapts it to the ORM.
"""
from __future__ import annotations

import itertools
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.base import as_utc
from app.ml.eta_model import EtaModel, haversine_km
from app.models import Batch, Facility, Incident, RoutePlan, StorageUnit, User
from app.models.enums import (ACTIVE_INCIDENT_STATUSES, BatchStatus, IncidentType, Role, RoutePlanStatus,
                              StorageUnitStatus)

DOSE_VOLUME_LITRES = 0.0035        # packed volume per dose (≈3.5 cm³, WHO typical for multi-dose vials)
DEFAULT_UNIT_CAPACITY_LITRES = 100.0
UNIT_FILL_LIMIT = 0.9               # never plan a unit beyond 90 % of its net storage volume
UNLOAD_MINUTES = 10.0               # per stop: unload, put away, sign the transfer note
STOP_PENALTY_MINUTES = 15.0         # discourages opening one more stop for a small load
EXACT_MAX_STOPS = 7
BLOCKING_INCIDENTS = (IncidentType.TEMPERATURE_EXCURSION, IncidentType.EQUIPMENT_FAILURE,
                      IncidentType.SENSOR_OFFLINE, IncidentType.SENSOR_FAULT)


# ----------------------------------------------------------------------------- data model
@dataclass
class Site:
    key: str
    code: str
    name: str
    lat: float
    lon: float
    region_id: Optional[str] = None

    def as_dict(self) -> dict:
        return {"key": self.key, "code": self.code, "name": self.name, "lat": self.lat, "lon": self.lon,
                "region_id": self.region_id}


@dataclass
class Cargo:
    batch_id: str
    batch_number: str
    product: str
    doses: int
    min_temp: float
    max_temp: float
    status: str = "ACTIVE"
    expiry: Optional[str] = None

    @property
    def volume(self) -> float:
        return self.doses * DOSE_VOLUME_LITRES

    @property
    def priority(self) -> float:
        # narrower approved range => more heat/freeze sensitive => move first
        return self.doses * (1.0 + 4.0 / (max(self.max_temp - self.min_temp, 0.0) + 1.0))


@dataclass
class Destination:
    unit_id: str
    unit_code: str
    site: Site
    eff_min: float
    eff_max: float
    free_litres: float

    def compatible(self, c: Cargo) -> bool:
        # product's labelled range must contain the unit's approved operating range
        return c.min_temp <= self.eff_min and c.max_temp >= self.eff_max


@dataclass
class Params:
    max_trip_minutes: float = 240.0       # validated cold-box hold time
    vehicle_capacity_litres: float = 60.0
    vehicles: int = 1
    depart_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


EtaFn = Callable[[Sequence[dict], datetime], Dict[Tuple[str, str], Tuple[float, float, float]]]


# ----------------------------------------------------------------------------- routing helpers
def _arrivals(order: Sequence[str], src: str, mx, idx: int) -> List[float]:
    """Cumulative arrival minutes (from trip start) at each stop. idx 1 = p50, 2 = p90."""
    t, prev, out = 0.0, src, []
    for k in order:
        t += mx[(prev, k)][idx]
        out.append(t)
        t += UNLOAD_MINUTES
        prev = k
    return out


def _weighted_cost(order, src, mx, doses: Dict[str, int]) -> float:
    return sum(doses[k] * a for k, a in zip(order, _arrivals(order, src, mx, 1)))


def _best_order(stops: List[str], src: str, mx, doses: Dict[str, int]) -> List[str]:
    if len(stops) <= 1:
        return list(stops)
    if len(stops) <= EXACT_MAX_STOPS:
        return list(min(itertools.permutations(stops), key=lambda o: _weighted_cost(o, src, mx, doses)))
    order = sorted(stops, key=lambda k: mx[(src, k)][1])
    best, improved = _weighted_cost(order, src, mx, doses), True
    while improved:
        improved = False
        for i in range(len(order) - 1):
            for j in range(i + 1, len(order)):
                cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                c = _weighted_cost(cand, src, mx, doses)
                if c < best - 1e-9:
                    order, best, improved = cand, c, True
    return order


def _pack_trips(stops: List[str], src: str, mx, loads: Dict[str, float], doses: Dict[str, int],
                p: Params) -> List[List[str]]:
    """Greedy packing in descending urgency; a stop joins the first trip where the re-optimised
    order still respects vehicle capacity and the p90 hold time."""
    trips: List[List[str]] = []
    for k in sorted(stops, key=lambda s: (-doses[s], mx[(src, s)][1])):
        placed = False
        for i, t in enumerate(trips):
            if sum(loads[s] for s in t) + loads[k] > p.vehicle_capacity_litres + 1e-9:
                continue
            cand = _best_order(t + [k], src, mx, doses)
            if _arrivals(cand, src, mx, 2)[-1] <= p.max_trip_minutes:
                trips[i], placed = cand, True
                break
        if not placed:
            trips.append([k])
    return trips


def _schedule(trips: List[List[str]], src: str, mx, p: Params, doses: Dict[str, int]):
    """Assign trips (most urgent first) to the vehicle that becomes free earliest."""
    free = [0.0] * max(1, p.vehicles)
    plan = []
    for order in sorted(trips, key=lambda t: -_weighted_cost(t, src, mx, doses) / max(1, sum(doses[s] for s in t))):
        v = min(range(len(free)), key=lambda i: free[i])
        start = free[v]
        arr50, arr90 = _arrivals(order, src, mx, 1), _arrivals(order, src, mx, 2)
        back = mx[(order[-1], src)][1] if order else 0.0
        end = start + (arr50[-1] + UNLOAD_MINUTES + back if order else 0.0)
        free[v] = end
        plan.append({"vehicle": v + 1, "start": start, "order": order, "arr50": arr50, "arr90": arr90,
                     "return_minutes": back, "end": end})
    return plan


def _exposure(schedule, doses: Dict[str, int]) -> float:
    return sum(doses[k] * (t["start"] + a) for t in schedule for k, a in zip(t["order"], t["arr50"]))


# ----------------------------------------------------------------------------- core optimiser
def optimise(source: Site, cargo: List[Cargo], destinations: List[Destination], params: Params,
             eta: EtaFn = EtaModel.matrix) -> dict:
    sites = {source.key: source}
    for d in destinations:
        sites.setdefault(d.site.key, d.site)
    mx = eta([s.as_dict() for s in sites.values()], params.depart_at)

    free = {d.unit_id: d.free_litres for d in destinations}
    by_unit = {d.unit_id: d for d in destinations}
    assigned: Dict[str, List[Cargo]] = {}
    unassigned: List[dict] = []
    open_sites: set = set()

    for c in sorted(cargo, key=lambda c: -c.priority):
        best, best_cost, reason = None, math.inf, "No compatible storage unit in scope"
        for d in destinations:
            if not d.compatible(c):
                continue
            if free[d.unit_id] + 1e-9 < c.volume:
                reason = "Compatible units lack free capacity"
                continue
            on_site = d.site.key == source.key
            if not on_site and c.volume > params.vehicle_capacity_litres:
                reason = "Batch volume exceeds vehicle cold-box capacity"
                continue
            p90 = mx[(source.key, d.site.key)][2]
            if not on_site and p90 > params.max_trip_minutes:
                reason = "Compatible units are beyond the cold-box hold time (p90 ETA)"
                continue
            cost = mx[(source.key, d.site.key)][1] + (0 if d.site.key in open_sites or on_site else STOP_PENALTY_MINUTES)
            if cost < best_cost - 1e-9 or (abs(cost - best_cost) < 1e-9 and best and free[d.unit_id] > free[best.unit_id]):
                best, best_cost = d, cost
        if best is None:
            unassigned.append({"batch_id": c.batch_id, "batch_number": c.batch_number, "product": c.product,
                               "doses": c.doses, "reason": reason})
            continue
        free[best.unit_id] -= c.volume
        assigned.setdefault(best.unit_id, []).append(c)
        open_sites.add(best.site.key)

    # stops = receiving sites (off-site); on-site moves need no vehicle
    site_units: Dict[str, List[str]] = {}
    for uid in assigned:
        site_units.setdefault(by_unit[uid].site.key, []).append(uid)
    loads = {k: sum(c.volume for u in us for c in assigned[u]) for k, us in site_units.items()}
    doses = {k: sum(c.doses for u in us for c in assigned[u]) for k, us in site_units.items()}
    off = [k for k in site_units if k != source.key]
    schedule = _schedule(_pack_trips(off, source.key, mx, loads, doses, params), source.key, mx, params, doses)

    depart = as_utc(params.depart_at)
    trips = []
    for n, t in enumerate(schedule, start=1):
        prev, stops = source.key, []
        for k, a50, a90 in zip(t["order"], t["arr50"], t["arr90"]):
            s = sites[k]
            dist, leg50, leg90 = mx[(prev, k)]
            stops.append({
                "facility_key": k, "facility_code": s.code, "facility_name": s.name, "lat": s.lat, "lon": s.lon,
                "leg_distance_km": round(dist, 2), "leg_eta_minutes": round(leg50, 1), "leg_eta_p90_minutes": round(leg90, 1),
                "arrival_offset_minutes": round(t["start"] + a50, 1), "arrival_p90_offset_minutes": round(t["start"] + a90, 1),
                "eta": (depart + timedelta(minutes=t["start"] + a50)).isoformat(),
                "load_litres": round(loads[k], 3), "doses": doses[k],
                "deliveries": [_delivery(by_unit[u], assigned[u]) for u in site_units[k]],
            })
            prev = k
        trips.append({
            "trip": n, "vehicle": t["vehicle"], "start_offset_minutes": round(t["start"], 1),
            "duration_minutes": round(t["end"] - t["start"], 1), "cold_chain_minutes_p90": round(t["arr90"][-1], 1),
            "distance_km": round(sum(st["leg_distance_km"] for st in stops) + mx[(prev, source.key)][0], 2),
            "load_litres": round(sum(st["load_litres"] for st in stops), 3), "doses": sum(st["doses"] for st in stops),
            "stops": stops,
        })
    on_site = [_delivery(by_unit[u], assigned[u]) for u in site_units.get(source.key, [])]
    on_site_doses = sum(c.doses for u in site_units.get(source.key, []) for c in assigned[u])

    exposure = _exposure(schedule, doses) + on_site_doses * mx[(source.key, source.key)][1]
    baseline = _baseline(source, cargo, destinations, params, mx)
    improvement = (round(100 * (baseline - exposure) / baseline, 1) if baseline else None)
    total = sum(c.doses for c in cargo)
    moved = total - sum(u["doses"] for u in unassigned)
    return {
        "source": source.as_dict(), "trips": trips, "on_site_moves": on_site, "unassigned": unassigned,
        "summary": {
            "batches": len(cargo), "total_doses": total, "relocated_doses": moved,
            "unassigned_doses": total - moved, "trip_count": len(trips),
            "vehicle_minutes": round(sum(t["duration_minutes"] for t in trips), 1),
            "distance_km": round(sum(t["distance_km"] for t in trips), 2),
            "completion_minutes": round(max([t["start_offset_minutes"] + t["duration_minutes"] for t in trips] or [0]), 1),
            "exposure_dose_minutes": round(exposure, 1),
            "baseline_exposure_dose_minutes": round(baseline, 1) if baseline is not None else None,
            "improvement_pct": improvement,
        },
    }


def _delivery(d: Destination, items: List[Cargo]) -> dict:
    return {"storage_unit_id": d.unit_id, "unit_code": d.unit_code, "approved_range": [d.eff_min, d.eff_max],
            "batches": [{"batch_id": c.batch_id, "batch_number": c.batch_number, "product": c.product,
                         "doses": c.doses, "status": c.status,
                         "segregate": c.status == BatchStatus.QUARANTINED.value} for c in items]}


def _baseline(source: Site, cargo: List[Cargo], destinations: List[Destination], p: Params, mx) -> Optional[float]:
    """Nearest compatible unit by straight-line distance, radial visiting order, one vehicle,
    no hold-time trip splitting. Evaluated with the same ETA matrix as the optimised plan."""
    free = {d.unit_id: d.free_litres for d in destinations}
    sites_doses: Dict[str, int] = {}
    on_site = 0
    for c in cargo:
        options = [d for d in destinations if d.compatible(c) and free[d.unit_id] + 1e-9 >= c.volume]
        if not options:
            continue
        d = min(options, key=lambda d: haversine_km(source.lat, source.lon, d.site.lat, d.site.lon))
        free[d.unit_id] -= c.volume
        if d.site.key == source.key:
            on_site += c.doses
        else:
            sites_doses[d.site.key] = sites_doses.get(d.site.key, 0) + c.doses
    if not sites_doses and not on_site:
        return None
    order = sorted(sites_doses, key=lambda k: mx[(source.key, k)][0])
    arr = _arrivals(order, source.key, mx, 1)
    return sum(sites_doses[k] * a for k, a in zip(order, arr)) + on_site * mx[(source.key, source.key)][1]


# ----------------------------------------------------------------------------- ORM adapter
def _site(f: Facility) -> Site:
    return Site(key=str(f.id), code=f.code, name=f.name, lat=f.latitude, lon=f.longitude, region_id=str(f.region_id))


def _used_litres(db: Session, unit_id) -> float:
    qty = sum(b.current_quantity for b in db.query(Batch).filter(
        Batch.storage_unit_id == unit_id, Batch.status.in_((BatchStatus.ACTIVE, BatchStatus.QUARANTINED))))
    return qty * DOSE_VOLUME_LITRES


class RoutePlanService:
    @staticmethod
    def resolve_source(db: Session, scope, incident_id=None, storage_unit_id=None) -> Tuple[StorageUnit, Optional[Incident]]:
        if bool(incident_id) == bool(storage_unit_id):
            raise HTTPException(422, "Provide exactly one of incident_id or storage_unit_id")
        inc = None
        if incident_id:
            inc = db.get(Incident, incident_id)
            if not inc:
                raise HTTPException(404, "Incident not found")
            scope.ensure(inc.facility_id, not_found="Incident not found")
            if inc.incident_type != IncidentType.TEMPERATURE_EXCURSION:
                raise HTTPException(400, "Route plans are generated for TEMPERATURE_EXCURSION incidents")
            if not inc.storage_unit_id:
                raise HTTPException(400, "Incident has no storage unit")
            storage_unit_id = inc.storage_unit_id
        unit = db.get(StorageUnit, storage_unit_id)
        if not unit:
            raise HTTPException(404, "Storage unit not found")
        scope.ensure(unit.facility_id, not_found="Storage unit not found")
        return unit, inc

    @staticmethod
    def cargo(db: Session, unit: StorageUnit) -> List[Cargo]:
        rows = (db.query(Batch).filter(Batch.storage_unit_id == unit.id, Batch.current_quantity > 0,
                                       Batch.status.in_((BatchStatus.ACTIVE, BatchStatus.QUARANTINED)))
                .order_by(Batch.expiry_date).all())
        return [Cargo(batch_id=str(b.id), batch_number=b.batch_number, product=b.product.name, doses=b.current_quantity,
                      min_temp=b.product.min_temperature, max_temp=b.product.max_temperature, status=b.status.value,
                      expiry=as_utc(b.expiry_date).isoformat()) for b in rows]

    @staticmethod
    def destinations(db: Session, scope, source: StorageUnit) -> Tuple[List[Destination], List[dict]]:
        blocked = {u for (u,) in db.query(Incident.storage_unit_id).filter(
            Incident.incident_type.in_(BLOCKING_INCIDENTS), Incident.status.in_(ACTIVE_INCIDENT_STATUSES),
            Incident.storage_unit_id.isnot(None))}
        q = scope.apply(db.query(StorageUnit).join(Facility, StorageUnit.facility_id == Facility.id)
                        .filter(StorageUnit.status == StorageUnitStatus.ACTIVE, Facility.is_active.is_(True),
                                StorageUnit.id != source.id), StorageUnit.facility_id)
        out, excluded = [], []
        for u in q.all():
            f = u.facility
            why = None
            if f.latitude is None or f.longitude is None:
                why = "Facility has no coordinates"
            elif u.id in blocked:
                why = "Unit has an active excursion / equipment / connectivity incident"
            if why:
                excluded.append({"unit_code": u.unit_code, "facility_code": f.code, "reason": why})
                continue
            cap = (u.capacity_litres or DEFAULT_UNIT_CAPACITY_LITRES) * UNIT_FILL_LIMIT
            out.append(Destination(unit_id=str(u.id), unit_code=u.unit_code, site=_site(f), eff_min=u.effective_min,
                                   eff_max=u.effective_max, free_litres=max(0.0, cap - _used_litres(db, u.id))))
        return out, excluded

    @classmethod
    def generate(cls, db: Session, scope, *, incident_id=None, storage_unit_id=None, params: Params,
                 persist: bool = True) -> dict:
        unit, inc = cls.resolve_source(db, scope, incident_id, storage_unit_id)
        f = unit.facility
        if not f or f.latitude is None or f.longitude is None:
            raise HTTPException(400, "Source facility has no coordinates; routing needs facility latitude/longitude")
        cargo = cls.cargo(db, unit)
        if not cargo:
            raise HTTPException(409, "No ACTIVE or QUARANTINED stock in this storage unit to relocate")
        dests, excluded = cls.destinations(db, scope, unit)
        result = optimise(_site(f), cargo, dests, params)
        result["source"].update({"storage_unit_id": str(unit.id), "unit_code": unit.unit_code})
        result["excluded_units"] = excluded
        result["candidate_units"] = len(dests)
        result["model"] = EtaModel.info()
        result["parameters"] = {"max_trip_minutes": params.max_trip_minutes,
                                "vehicle_capacity_litres": params.vehicle_capacity_litres,
                                "vehicles": params.vehicles, "depart_at": as_utc(params.depart_at).isoformat()}
        result["incident_id"] = str(inc.id) if inc else None
        result["note"] = ("Decision support only. Approving a plan does not move stock; transfers are recorded "
                          "through the inventory ledger by authorised staff.")
        if not persist:
            return result
        s = result["summary"]
        plan = RoutePlan(plan_number=_plan_number(), incident_id=inc.id if inc else None, source_storage_unit_id=unit.id,
                         facility_id=unit.facility_id, model_version=result["model"]["version"],
                         total_doses=s["total_doses"], unassigned_doses=s["unassigned_doses"], trip_count=s["trip_count"],
                         exposure_dose_minutes=s["exposure_dose_minutes"],
                         baseline_exposure_dose_minutes=s["baseline_exposure_dose_minutes"],
                         improvement_pct=s["improvement_pct"], parameters=result["parameters"], plan=result,
                         created_by=scope.user.id, created_by_name=scope.user.name)
        db.add(plan)
        db.flush()
        from app.services.audit import log_audit
        log_audit(db, scope.user, "ROUTE_PLAN_CREATED", "RoutePlan", plan.id,
                  {"plan_number": plan.plan_number, "incident_id": result["incident_id"], "trips": s["trip_count"],
                   "doses": s["relocated_doses"], "model_version": plan.model_version},
                  category="LOGISTICS", facility_id=unit.facility_id, commit=False)
        db.commit()
        result["id"] = str(plan.id)
        result["plan_number"] = plan.plan_number
        result["status"] = plan.status.value
        return result

    @staticmethod
    def decide(db: Session, plan: RoutePlan, user: User, approve: bool, note: Optional[str]) -> RoutePlan:
        if plan.status != RoutePlanStatus.PROPOSED:
            raise HTTPException(409, f"Plan is {plan.status.value}; only PROPOSED plans can be decided")
        if not approve and (not note or len(note.strip()) < 5):
            raise HTTPException(400, "A cancellation reason (min 5 chars) is required")
        if approve:
            # only one approved plan per source unit at a time — never supersede silently
            other = db.query(RoutePlan).filter(RoutePlan.source_storage_unit_id == plan.source_storage_unit_id,
                                               RoutePlan.status == RoutePlanStatus.APPROVED,
                                               RoutePlan.id != plan.id).first()
            if other:
                raise HTTPException(409, f"{other.plan_number} is already approved for this unit; cancel it first")
        plan.status = RoutePlanStatus.APPROVED if approve else RoutePlanStatus.CANCELLED
        plan.decided_by, plan.decided_by_name = user.id, user.name
        plan.decided_at = datetime.now(timezone.utc)
        plan.decision_note = note
        from app.services.audit import log_audit
        log_audit(db, user, "ROUTE_PLAN_APPROVED" if approve else "ROUTE_PLAN_CANCELLED", "RoutePlan", plan.id,
                  {"plan_number": plan.plan_number, "note": note}, category="LOGISTICS", facility_id=plan.facility_id,
                  commit=False)
        if approve:
            _notify_facilities(db, plan)
        db.commit()
        return plan


def _notify_facilities(db: Session, plan: RoutePlan):
    from app.services.notification import notify_facility
    receiving = {st["facility_key"] for t in plan.plan.get("trips", []) for st in t["stops"]}
    title = f"Relocation plan {plan.plan_number} approved"
    link = "/inventory"
    if plan.facility_id:
        notify_facility(db, plan.facility_id, [Role.OPERATOR, Role.SUPERVISOR], title,
                        f"Prepare {plan.total_doses - plan.unassigned_doses} doses in {plan.trip_count} trip(s) for "
                        "transfer out of the affected unit. Record each move as an inventory transfer.",
                        category="LOGISTICS", link=link, entity_type="RoutePlan", entity_id=plan.id, commit=False)
    for key in receiving:
        try:
            fid = uuid.UUID(key)
        except ValueError:
            continue
        notify_facility(db, fid, [Role.OPERATOR], title,
                        "Incoming relocated stock expected — see the approved plan for ETA and receiving units.",
                        category="LOGISTICS", link=link, entity_type="RoutePlan", entity_id=plan.id, commit=False)


def _plan_number() -> str:
    return f"RP-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
