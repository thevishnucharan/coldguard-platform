"""SIMULATED road-trip generator for the route ETA model.

There is no field GPS data in this project, so transit times are synthesised from a
transparent traffic model (documented here so the ML claims stay honest):

  minutes = handling + distance * winding / speed(distance, hour, weekday) + cross_region_delay + noise

  * winding      lognormal around 1.35 (rural roads are not straight lines)
  * speed        rises from ~20 km/h for short urban hops to ~58 km/h on long highway legs
  * peak hours   07-10 and 17-20 slow short (urban) legs by up to 40 %, long legs ~10 %
  * night        22-05 is ~15 % faster
  * weekends     ~10 % faster
  * crossing a district (region) boundary adds a 6-20 min checkpoint/handover delay
  * heavy-tailed noise (gamma) models breakdowns, detours and queues

The physical baseline in `app.ml.eta_model.baseline_minutes` assumes a single constant
speed, so the learned model should beat it clearly on held-out trips.
"""
import math
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.ml.eta_model import FEATURES, HANDLING_MINUTES, feature_row  # noqa: E402


def true_minutes(distance_km: float, hour: float, weekday: int, cross_region: bool, rng: np.random.Generator) -> float:
    winding = rng.lognormal(mean=math.log(1.35), sigma=0.08)
    speed = 20.0 + 38.0 * (1 - math.exp(-distance_km / 25.0))
    urban_share = math.exp(-distance_km / 15.0)
    if 7 <= hour < 10 or 17 <= hour < 20:
        speed *= 1 - (0.10 + 0.30 * urban_share)
    elif hour >= 22 or hour < 5:
        speed *= 1.15
    if weekday >= 5:
        speed *= 1.10
    minutes = HANDLING_MINUTES + distance_km * winding / speed * 60.0
    if cross_region:
        minutes += rng.uniform(6, 20)
    minutes += rng.gamma(shape=1.5, scale=2.0 + 0.04 * distance_km)
    return minutes


def make_trips(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = datetime(2026, 1, 5)
    rows, y = [], []
    for _ in range(n):
        d = float(rng.gamma(shape=2.0, scale=22.0)) + 0.3          # mostly < 100 km, tail to ~250 km
        depart = start + timedelta(days=int(rng.integers(0, 28)), minutes=int(rng.integers(0, 24 * 60)))
        cross = bool(rng.random() < min(0.9, 0.15 + d / 120.0))     # longer trips cross districts more often
        hour = depart.hour + depart.minute / 60.0
        rows.append(feature_row(d, depart, same_region=not cross))
        y.append(true_minutes(d, hour, depart.weekday(), cross, rng))
    df = pd.DataFrame(rows, columns=FEATURES)
    df["minutes"] = y
    return df
