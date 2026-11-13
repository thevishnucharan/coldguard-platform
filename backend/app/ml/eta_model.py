"""Transit-time (ETA) model for cold-chain relocation routing — DECISION SUPPORT ONLY.

Two GradientBoosting regressors predict road transit minutes between two facilities:
  * p50  (median, `loss="quantile", alpha=0.5`) — used as the routing cost
  * p90  (`alpha=0.9`)                          — conservative bound used to check that a
                                                   trip stays inside the cold-box hold time

Features come only from data the platform already has (facility coordinates, region and
departure time), see `FEATURES`. The model is trained on SIMULATED trips
(`ml/routing_dataset.py`, `ml/train_routing.py`); it is not fitted to field GPS data.

If the model file is missing, `EtaModel` falls back to a documented physical baseline
(road-winding factor 1.3, 40 km/h, fixed handling time) and reports `available: False`.
"""
from __future__ import annotations

import logging
import math
import os
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

import joblib
import numpy as np

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ml", "models")
MODEL_FILE = "route_eta_gbr.joblib"

FEATURES = ["distance_km", "log_distance", "hour_sin", "hour_cos", "is_peak", "is_weekend", "same_region"]

# Physical baseline (also the fallback when no model is available)
BASELINE_ROAD_FACTOR = 1.3
BASELINE_SPEED_KMH = 40.0
HANDLING_MINUTES = 8.0          # loading / paperwork before a vehicle moves
SAME_SITE_MINUTES = 5.0         # moving stock between units inside one facility
P90_BASELINE_FACTOR = 1.35


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def is_peak_hour(hour: float) -> bool:
    return 7 <= hour < 10 or 17 <= hour < 20


def feature_row(distance_km: float, depart: datetime, same_region: bool) -> List[float]:
    hour = depart.hour + depart.minute / 60.0
    ang = 2 * math.pi * hour / 24.0
    return [distance_km, math.log1p(distance_km), math.sin(ang), math.cos(ang),
            1.0 if is_peak_hour(hour) else 0.0, 1.0 if depart.weekday() >= 5 else 0.0, 1.0 if same_region else 0.0]


def baseline_minutes(distance_km: float) -> float:
    """Naive estimate a planner would use without the model."""
    return HANDLING_MINUTES + distance_km * BASELINE_ROAD_FACTOR / BASELINE_SPEED_KMH * 60.0


class EtaModel:
    _bundle: Optional[dict] = None
    _loaded = False

    @classmethod
    def load(cls) -> Optional[dict]:
        if cls._loaded:
            return cls._bundle
        cls._loaded = True
        path = os.path.join(MODEL_DIR, MODEL_FILE)
        if os.path.exists(path):
            try:
                bundle = joblib.load(path)
                if isinstance(bundle, dict) and {"p50", "p90"} <= set(bundle):
                    cls._bundle = bundle
                    logger.info("Loaded route ETA model %s", bundle.get("version"))
            except Exception as exc:  # corrupt / incompatible file -> baseline only
                logger.warning("Route ETA model could not be loaded (%s); using physical baseline", exc)
        else:
            logger.warning("No route ETA model at %s; using physical baseline", path)
        return cls._bundle

    @classmethod
    def reset(cls) -> None:
        cls._bundle, cls._loaded = None, False

    @classmethod
    def info(cls) -> dict:
        b = cls.load()
        if not b:
            return {"available": False, "version": "baseline-physical-v1", "features": FEATURES,
                    "fallback": {"road_factor": BASELINE_ROAD_FACTOR, "speed_kmh": BASELINE_SPEED_KMH,
                                 "handling_minutes": HANDLING_MINUTES}}
        return {"available": True, "version": b.get("version"), "features": b.get("features", FEATURES),
                "trained_at": b.get("trained_at"), "training_rows": b.get("training_rows"), "data": b.get("data"),
                "metrics": b.get("metrics", {}),
                "note": "Decision support only. Predicted transit times are estimates from SIMULATED trips."}

    @classmethod
    def version(cls) -> str:
        return cls.info()["version"]

    @classmethod
    def predict(cls, rows: Sequence[Sequence[float]]) -> Tuple[np.ndarray, np.ndarray]:
        """Vectorised (p50, p90) minutes for feature rows (see `feature_row`)."""
        X = np.asarray(rows, dtype=float).reshape(-1, len(FEATURES))
        b = cls.load()
        if b:
            p50 = b["p50"].predict(X)
            p90 = b["p90"].predict(X)
        else:
            p50 = np.array([baseline_minutes(d) for d in X[:, 0]])
            p90 = p50 * P90_BASELINE_FACTOR
        floor = HANDLING_MINUTES
        p50 = np.maximum(p50, floor)
        p90 = np.maximum(p90, p50)  # quantile models can cross on extrapolation; never let p90 < p50
        return p50, p90

    @classmethod
    def matrix(cls, sites: Sequence[dict], depart: datetime) -> Dict[Tuple[str, str], Tuple[float, float, float]]:
        """{(a, b): (distance_km, p50_min, p90_min)} for every ordered pair of sites.

        `sites` items need `key`, `lat`, `lon`, `region_id`. Same-site pairs get the fixed
        intra-facility handling time; all other pairs are predicted in ONE batched call."""
        out: Dict[Tuple[str, str], Tuple[float, float, float]] = {}
        pairs, rows = [], []
        for a in sites:
            for b in sites:
                if a["key"] == b["key"]:
                    out[(a["key"], b["key"])] = (0.0, SAME_SITE_MINUTES, SAME_SITE_MINUTES)
                    continue
                d = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
                if d < 0.05:  # co-located facilities
                    out[(a["key"], b["key"])] = (d, SAME_SITE_MINUTES, SAME_SITE_MINUTES)
                    continue
                pairs.append((a["key"], b["key"], d))
                rows.append(feature_row(d, depart, a.get("region_id") == b.get("region_id")))
        if rows:
            p50, p90 = cls.predict(rows)
            for (ka, kb, d), m, h in zip(pairs, p50, p90):
                out[(ka, kb)] = (round(d, 3), float(m), float(h))
        return out
