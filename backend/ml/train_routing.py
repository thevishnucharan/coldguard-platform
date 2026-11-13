"""Train the route ETA quantile models on SIMULATED trips.

    python ml/train_routing.py      # writes ml/models/route_eta_gbr.joblib
                                    # and   ml/reports/routing_evaluation.json

Held-out evaluation compares the learned p50 against the constant-speed physical baseline
and checks p90 calibration (share of real trips that finish within the p90 estimate).
"""
import json
import os
import sys
from datetime import datetime, timezone

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.ml.eta_model import FEATURES, MODEL_FILE, baseline_minutes  # noqa: E402
from ml.routing_dataset import make_trips  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(HERE, "models")
REPORT_DIR = os.path.join(HERE, "reports")
VERSION = "route-eta-gbr-v1-sim-2026.11"
SEED = 2026


def _gbr(alpha: float) -> GradientBoostingRegressor:
    return GradientBoostingRegressor(loss="quantile", alpha=alpha, n_estimators=250, max_depth=3,
                                     learning_rate=0.06, subsample=0.8, min_samples_leaf=20, random_state=SEED)


def evaluate(p50_model, p90_model, test) -> dict:
    X, y = test[FEATURES].values, test["minutes"].values
    p50, p90 = p50_model.predict(X), np.maximum(p90_model.predict(X), p50_model.predict(X))
    base = np.array([baseline_minutes(d) for d in test["distance_km"].values])
    mae = float(np.mean(np.abs(p50 - y)))
    base_mae = float(np.mean(np.abs(base - y)))
    return {
        "test_rows": int(len(y)),
        "p50_mae_minutes": round(mae, 2),
        "baseline_mae_minutes": round(base_mae, 2),
        "mae_improvement_pct": round(100 * (base_mae - mae) / base_mae, 1),
        "p50_mape_pct": round(float(np.mean(np.abs(p50 - y) / y)) * 100, 1),
        "p90_coverage": round(float(np.mean(y <= p90)), 3),
    }


def main():
    train, test = make_trips(16000, SEED), make_trips(4000, SEED + 1)
    X, y = train[FEATURES].values, train["minutes"].values
    p50, p90 = _gbr(0.5).fit(X, y), _gbr(0.9).fit(X, y)
    metrics = evaluate(p50, p90, test)
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(REPORT_DIR, exist_ok=True)
    bundle = {"p50": p50, "p90": p90, "version": VERSION, "features": FEATURES,
              "trained_at": datetime.now(timezone.utc).isoformat(), "training_rows": len(train),
              "data": "SIMULATED trips (ml/routing_dataset.py) — not field GPS data", "seed": SEED,
              "metrics": metrics}
    path = os.path.join(MODEL_DIR, MODEL_FILE)
    joblib.dump(bundle, path, compress=3)
    with open(os.path.join(REPORT_DIR, "routing_evaluation.json"), "w") as fh:
        json.dump({"version": VERSION, **metrics}, fh, indent=2)
    print(f"Saved {path} ({VERSION}) -> {json.dumps(metrics)}")


if __name__ == "__main__":
    main()
