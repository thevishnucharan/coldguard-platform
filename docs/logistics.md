# Excursion relocation routing

When a storage unit is in a **temperature excursion**, the stock inside should be moved to safe,
compatible storage quickly. The logistics module proposes **where** each batch should go and **in
which order** a cold-box vehicle should visit the receiving facilities.

It is **decision support only**: generating or approving a plan never moves stock. Each move is
still recorded as an inventory transfer by someone with `inventory.manage` and scope over the
receiving facility.

## Where to find it

*Admin → Platform → Excursion routing* (`/admin/logistics`)

1. Pick an active excursion (incidents of type `TEMPERATURE_EXCURSION` whose unit still holds stock).
2. Set the constraints: cold-box hold time, vehicle cold-box volume, number of vehicles.
3. **Optimise relocation route** → map, trips, ETAs (p50 and p90), comparison with the baseline.
4. **Approve & notify** (operators and supervisors of the source facility, operators of the
   receiving facilities) or **Cancel** (a reason is required). Every step is audited (`LOGISTICS`).

| Permission | Roles |
|---|---|
| `logistics.plan` (generate / approve / cancel) | ADMIN |
| `logistics.view` | ADMIN, SUPERVISOR, OPERATOR, AUDITOR (facility scope applies) |

## How a plan is computed (`backend/app/services/route_optimizer.py`)

| Step | Rule |
|---|---|
| Cargo | ACTIVE and QUARANTINED batches with stock in the source unit (quarantined stock is flagged *keep segregated*) |
| Candidates | ACTIVE units in scope at active facilities with coordinates; none with an active excursion, equipment, sensor-offline or sensor-fault incident |
| Compatibility | the product's labelled range must contain the unit's approved range |
| Capacity | `capacity_litres` (default 100 L) × 90 % fill limit, minus stock already there; 0.0035 L per dose |
| ETA | ML matrix: **p50** is the routing cost, **p90** is checked against the hold time |
| Assignment | batches in priority order (doses × heat sensitivity) go to the feasible unit with the lowest p50; opening another stop costs 15 min, so loads consolidate |
| Trips | packed by vehicle volume and p90 hold time; stops ordered to minimise dose-weighted arrival time (exact search up to 7 stops, 2-opt beyond); scheduled on the vehicle that is free first |
| Baseline | nearest compatible unit by straight-line distance, radial visiting order, one vehicle, scored with the **same** ETA matrix |

**Exposure** = Σ doses × minutes until they reach safe storage. The improvement figure compares
the optimised plan's exposure with the baseline's.

## ML model (`backend/app/ml/eta_model.py`)

Two `GradientBoostingRegressor` quantile models (α = 0.5 and 0.9) predict road minutes from:
distance, log distance, time of day (sin/cos), peak hour, weekend and same-region.

```bash
cd backend
python ml/train_routing.py   # -> ml/models/route_eta_gbr.joblib, ml/reports/routing_evaluation.json
```

Training data is **simulated** (`ml/routing_dataset.py`), not field GPS data. Held-out results
for `route-eta-gbr-v1-sim-2026.11`:

| Metric | Value |
|---|---|
| p50 MAE | 6.45 min |
| Constant-speed baseline MAE | 16.24 min (−60.3 %) |
| p90 coverage | 89.4 % |

If the model file is missing or unreadable, the API falls back to the physical baseline
(1.3 road factor, 40 km/h, 8 min handling) and reports `available: false`.

## API (`/api/v1/logistics`)

| Method | Path | Permission |
|---|---|---|
| GET | `/model` | `logistics.view` |
| GET | `/excursions` | `logistics.view` |
| POST | `/route-plans` `{incident_id \| storage_unit_id, max_trip_minutes, vehicle_capacity_litres, vehicles, depart_at?, persist?}` | `logistics.plan` |
| GET | `/route-plans?status=&incident_id=` · `/route-plans/{id}` | `logistics.view` |
| POST | `/route-plans/{id}/approve` · `/route-plans/{id}/cancel` `{note}` | `logistics.plan` |

Only one plan per source unit can be APPROVED at a time. Migration: `0003_route_plans`.
`allow_on_site: false` is for facility-wide problems (power outage, fire): only *other*
facilities may receive stock.

## In-transit monitoring (`backend/app/services/transit.py`)

An APPROVED plan is **dispatched** as one shipment per vehicle trip (`POST /route-plans/{id}/dispatch
{vehicle_code, sensor_code?, trips?}`). Each vehicle's data logger reports position and cargo
temperature (`POST /shipments/{id}/telemetry {lat, lon, temperature, sensor_status?}`, via the
`X-Ingest-Key` gateway or a JWT with `logistics.operate`).

| Failure | Detected when | Severity / incident |
|---|---|---|
| `SENSOR_FAULT` | logger reports FAULT/ERROR, sends no value, or a physically implausible value (< −90 °C or > 70 °C) | HIGH · `TRANSIT_SENSOR_FAILURE` |
| `SENSOR_OFFLINE` | no reading for `TRANSIT_OFFLINE_MINUTES` (5); worker job `transit` | HIGH · `TRANSIT_SENSOR_FAILURE` |
| `TEMPERATURE_EXCURSION` | valid reading outside the strictest product range on board | CRITICAL · `TRANSIT_EXCURSION` |

For every alert, the **nearest compatible cold-chain stores** are ranked from the vehicle's last
known position using the ML ETA model:
* units must be active, hold no active excursion, equipment or connectivity incident, have an
  approved range that suits every product on board, and have room for the load;
* a store is *reachable* when its p90 ETA fits in the hold time left;
* the top `TRANSIT_NEARBY_LIMIT` (3) stores are kept, reachable ones first.

Who is alerted (in-app notification and realtime event):
* the **vehicle's operator** (the person who dispatched it) and the source facility's operators
  and supervisors, with the recommended store, ETA and hold time left;
* **operators of each nearby store**: "prepare unit X to receive diverted stock"; the
  recommended one is marked.

One active alert is kept per failure mode, with its position and ranking refreshed. When valid
readings return, logger alerts resolve automatically. People then **acknowledge**, **divert**
(`/shipments/{id}/divert {facility_id}`, which notifies the receiving store) or **deliver**.
Nothing is diverted automatically. UI: *Admin → Excursion routing* (dispatch and monitor) and
*In-transit vehicles* for admins, operators and supervisors.

The demo seed creates this scenario: a facility-wide plan for the open Jayanagar excursion, the
vehicle `KA01CC1001` in transit whose logger fails half-way (alert, incident and nearby stores
alerted), plus a delivered shipment. Migration: `0004_shipments`.

## Tests

* `backend/tests/unit/test_eta_model.py`: model metadata, beats the baseline on unseen trips, p90 calibration, physical sanity, fallback.
* `backend/tests/services/test_route_optimizer.py`: compatibility, capacity, hold time, trip splitting, ordering, consolidation, fleet size, exact search vs. 2-opt.
* `backend/tests/api/test_logistics.py`: real excursion pipeline, exclusions, RBAC and scope, approval workflow, notifications, audit, execution through the inventory ledger.
* `frontend/src/test/logistics.test.tsx`: page flow, approval, read-only mode, navigation.
* `backend/tests/api/test_transit.py` (15): dispatch rules and RBAC; logger fault, implausible value, cargo excursion and silent logger; ML-ranked nearby stores (excluding failing, incompatible, full or unreachable ones); alerts to the dispatcher, source facility and nearby stores; incidents; dedup and auto-resolve; divert, deliver, acknowledge; telemetry authentication.
* `backend/tests/scenarios/test_demo_seed.py`: the seeded supply-chain scenario (plans, in-transit failure, delivered shipment).
* `frontend/src/test/transit.test.tsx`: transit monitor (alert, hold-time bar, recommended store, divert, acknowledge, demo failure, read-only), role sidebar and home banner, login demo cards.
