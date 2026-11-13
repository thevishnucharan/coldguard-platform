"""Train IsolationForest v2 on SIMULATED normal-operation data.

    python ml/train.py            # writes ml/models/isolation_forest_v2.joblib

The v1 prototype model (ml/models/isolation_forest.joblib, trained by train_prototype.py on
a 2–8 °C sine wave with 5 % injected anomalies) is kept unchanged for comparison.
v2 differences: trained on the same scenario generator the platform simulates, with a
mostly-clean training set and an explicit contamination prior; stored with metadata.
"""
import os
import sys
from datetime import datetime, timezone

import joblib
from sklearn.ensemble import IsolationForest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.ml.features import FEATURE_COLUMNS, add_features  # noqa: E402
from ml.dataset import make_series  # noqa: E402

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
VERSION = "iforest-v2-sim-2026.11"
SEED = 1234


def main():
    frames = [make_series(4000, SEED + k, anomaly_rate=0.005) for k in range(6)]
    X = [add_features(f)[FEATURE_COLUMNS] for f in frames]
    import pandas as pd
    X = pd.concat(X, ignore_index=True)
    model = IsolationForest(n_estimators=200, contamination=0.01, random_state=SEED)
    model.fit(X)
    import numpy as np
    scores = model.score_samples(X)
    # Decision threshold calibrated on (simulated) normal operation: flag only scores below
    # the 0.1th percentile of training scores (~0.1 % expected false-positive rate).
    threshold = float(np.quantile(scores, 0.001))
    os.makedirs(MODEL_DIR, exist_ok=True)
    path = os.path.join(MODEL_DIR, "isolation_forest_v2.joblib")
    joblib.dump({"model": model, "version": VERSION, "features": FEATURE_COLUMNS,
                 "trained_at": datetime.now(timezone.utc).isoformat(), "training_rows": len(X),
                 "data": "SIMULATED (ml/dataset.py) — not field data", "seed": SEED,
                 "score_threshold": threshold}, path)
    print(f"Saved {path} ({VERSION}, {len(X)} rows, score_threshold={threshold:.4f})")


if __name__ == "__main__":
    main()
