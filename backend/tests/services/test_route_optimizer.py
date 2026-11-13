"""Pure optimiser behaviour with a deterministic ETA (1 km = 1 min, p90 = 1.2 x p50) so every
expectation can be checked by hand. The real ML matrix is exercised in tests/api/test_logistics.py."""
import itertools
from datetime import datetime, timezone

import pytest

from app.ml.eta_model import haversine_km
from app.services import route_optimizer as ro
from app.services.route_optimizer import Cargo, Destination, Params, Site, optimise

KM_PER_DEG = 111.2


def flat_eta(sites, _depart):
    out = {}
    for a in sites:
        for b in sites:
            if a["key"] == b["key"]:
                out[(a["key"], b["key"])] = (0.0, 5.0, 5.0)
            else:
                d = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
                out[(a["key"], b["key"])] = (d, d, d * 1.2)
    return out


SRC = Site("src", "SRC", "Source", 12.0, 77.0, "r1")


def site(key, km_north=0.0, km_east=0.0, region="r1"):
    return Site(key, key.upper(), key, 12.0 + km_north / KM_PER_DEG, 77.0 + km_east / (KM_PER_DEG * 0.978), region)


def dest(uid, s, lo=2.0, hi=8.0, free=50.0):
    return Destination(uid, uid.upper(), s, lo, hi, free)


def penta(bid, doses):
    return Cargo(bid, bid.upper(), "Penta", doses, 2.0, 8.0)


def run(cargo, dests, **kw):
    p = Params(depart_at=datetime(2026, 11, 11, 13, tzinfo=timezone.utc), **kw)
    return optimise(SRC, cargo, dests, p, eta=flat_eta)


def _units(plan):
    return {b["batch_number"]: d["unit_code"]
            for t in plan["trips"] for st in t["stops"] for d in st["deliveries"] for b in d["batches"]}


def test_routes_to_nearest_compatible_unit():
    near, far = site("near", 10), site("far", 40)
    plan = run([penta("b1", 1000)], [dest("u_far", far), dest("u_near", near)])
    assert _units(plan) == {"B1": "U_NEAR"}
    assert plan["summary"]["trip_count"] == 1 and plan["summary"]["unassigned_doses"] == 0
    stop = plan["trips"][0]["stops"][0]
    assert stop["leg_eta_minutes"] == pytest.approx(10, abs=0.1)
    assert stop["arrival_p90_offset_minutes"] == pytest.approx(12, abs=0.1)


def test_temperature_compatibility_is_enforced():
    freezer, fridge = site("frz", 5), site("fr", 30)
    opv = Cargo("o1", "O1", "OPV", 500, -25.0, 8.0)    # tolerates freezer and fridge
    hep = Cargo("h1", "H1", "HepB", 500, 2.0, 8.0)     # must never freeze
    plan = run([opv, hep], [dest("u_frz", freezer, -25, -15), dest("u_fr", fridge)])
    assert _units(plan) == {"O1": "U_FRZ", "H1": "U_FR"}
    plan = run([hep], [dest("u_frz", freezer, -25, -15)])
    assert plan["unassigned"][0]["reason"] == "No compatible storage unit in scope"


def test_unit_capacity_is_respected_and_overflow_goes_elsewhere():
    a, b = site("a", 5), site("b", 40)
    # 10 000 doses * 0.0035 L = 35 L; unit A has 20 L free. B is far enough that the small batch
    # is better off opening a stop at A (5 + 15 penalty) than riding along to B (40).
    plan = run([penta("big", 10_000), penta("small", 2_000)], [dest("ua", a, free=20), dest("ub", b, free=100)],
               vehicle_capacity_litres=100)
    units = _units(plan)
    assert units["BIG"] == "UB" and units["SMALL"] == "UA"
    plan = run([penta("big", 10_000)], [dest("ua", a, free=20)])
    assert plan["unassigned"][0]["reason"] == "Compatible units lack free capacity"


def test_hold_time_uses_p90_and_excludes_unreachable_units():
    far = site("far", 100)  # p50 = 100 min, p90 = 120 min
    plan = run([penta("b1", 100)], [dest("uf", far)], max_trip_minutes=110)
    assert plan["unassigned"][0]["reason"].startswith("Compatible units are beyond the cold-box hold time")
    assert run([penta("b1", 100)], [dest("uf", far)], max_trip_minutes=130)["summary"]["unassigned_doses"] == 0


def test_vehicle_capacity_splits_trips():
    stops = [site(f"s{i}", 5 + i, (-1) ** i * 3) for i in range(4)]
    cargo = [penta(f"b{i}", 4000) for i in range(4)]        # 14 L each
    dests = [dest(f"u{i}", s, free=15) for i, s in enumerate(stops)]  # one batch per unit
    plan = run(cargo, dests, vehicle_capacity_litres=30)
    assert plan["summary"]["trip_count"] == 2
    for t in plan["trips"]:
        assert t["load_litres"] <= 30
        assert t["cold_chain_minutes_p90"] <= 240
    assert plan["summary"]["relocated_doses"] == 16_000


def test_hold_time_splits_multi_stop_trips():
    a, b = site("a", 60), site("b", -60)  # opposite directions, 120 km apart
    plan = run([penta("x", 100), penta("y", 100)], [dest("ua", a, free=0.4), dest("ub", b, free=0.4)],
               max_trip_minutes=150)  # each unit fits exactly one 0.35 L batch
    assert plan["summary"]["trip_count"] == 2  # visiting both in one trip would exceed the hold time


def test_orders_stops_to_minimise_dose_weighted_arrival():
    small, big = site("small", 5), site("big", -8)   # big load is slightly further away, opposite side
    cargo = [penta("tiny", 100), penta("huge", 5000)]
    dests = [dest("u_small", small, free=0.5), dest("u_big", big, free=17.6)]  # each fits only its own batch
    plan = run(cargo, dests)
    order = [st["facility_code"] for st in plan["trips"][0]["stops"]]
    assert order == ["BIG", "SMALL"]
    s = plan["summary"]
    assert s["exposure_dose_minutes"] < s["baseline_exposure_dose_minutes"]
    assert s["improvement_pct"] > 0


def test_consolidation_penalty_avoids_extra_stop_for_marginal_gain():
    a, b = site("a", 10), site("b", 12)
    plan = run([penta("b1", 1000), penta("b2", 1000)], [dest("ua", a, free=50), dest("ub", b, free=50)])
    assert set(_units(plan).values()) == {"UA"}
    assert len(plan["trips"][0]["stops"]) == 1


def test_on_site_move_needs_no_vehicle_and_quarantine_is_segregated():
    same = Site("src", "SRC", "Source", 12.0, 77.0, "r1")
    q = Cargo("q1", "Q1", "Penta", 300, 2.0, 8.0, status="QUARANTINED")
    plan = run([q], [dest("u_same", same), dest("u_far", site("far", 30))])
    assert plan["trips"] == []
    move = plan["on_site_moves"][0]
    assert move["unit_code"] == "U_SAME" and move["batches"][0]["segregate"] is True


def test_more_vehicles_finish_sooner():
    stops = [site(f"s{i}", 20, i * 15 - 30) for i in range(5)]
    cargo = [penta(f"b{i}", 4000) for i in range(5)]
    dests = [dest(f"u{i}", s, free=15) for i, s in enumerate(stops)]
    one = run(cargo, dests, vehicle_capacity_litres=15, vehicles=1)["summary"]
    three = run(cargo, dests, vehicle_capacity_litres=15, vehicles=3)["summary"]
    assert three["completion_minutes"] < one["completion_minutes"]
    assert three["exposure_dose_minutes"] < one["exposure_dose_minutes"]


def test_exact_search_matches_brute_force_and_2opt_is_no_worse_than_radial():
    sites = [{"key": "src", "lat": 12.0, "lon": 77.0}]
    keys = []
    for i in range(9):
        k = f"k{i}"
        keys.append(k)
        sites.append({"key": k, "lat": 12.0 + ((i * 37) % 11 - 5) / 50, "lon": 77.0 + ((i * 53) % 13 - 6) / 50})
    mx = flat_eta(sites, None)
    doses = {k: 100 * (i + 1) for i, k in enumerate(keys)}
    six = keys[:6]
    best = min(itertools.permutations(six), key=lambda o: ro._weighted_cost(o, "src", mx, doses))
    assert ro._best_order(six, "src", mx, doses) == list(best)
    radial = sorted(keys, key=lambda k: mx[("src", k)][1])
    assert (ro._weighted_cost(ro._best_order(keys, "src", mx, doses), "src", mx, doses)
            <= ro._weighted_cost(radial, "src", mx, doses))


def test_priority_prefers_heat_sensitive_and_large_batches():
    narrow = Cargo("a", "A", "mRNA", 100, 2.0, 3.0)
    wide = Cargo("b", "B", "OPV", 100, -25.0, 8.0)
    assert narrow.priority > wide.priority
    assert penta("x", 1000).priority > penta("y", 10).priority


def test_empty_destinations_reports_everything_unassigned():
    plan = run([penta("b1", 100)], [])
    s = plan["summary"]
    assert s["unassigned_doses"] == 100 and s["trip_count"] == 0 and s["baseline_exposure_dose_minutes"] is None
