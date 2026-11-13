"""Reproducible evaluation of the anomaly detectors on a held-out SIMULATED dataset.

    python ml/evaluate.py    # prints a table, writes ml/reports/evaluation.json

Scores are point-wise precision/recall/F1 against INJECTED anomaly labels (see
ml/dataset.py for limitations). They are not field-accuracy figures.
"""
import json
import os
import statistics
import sys
from datetime import datetime, timezone

import joblib
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.ml.anomaly_service import MIN_HISTORY, STD_FLOOR, ZSCORE_THRESHOLD, ZSCORE_WINDOW  # noqa: E402
from app.ml.features import FEATURE_COLUMNS, add_features  # noqa: E402
from ml.dataset import make_series  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL_SEEDS = [9001, 9002, 9003]


def prf(y, p):
    tp = int(((y == 1) & (p == 1)).sum()); fp = int(((y == 0) & (p == 1)).sum()); fn = int(((y == 1) & (p == 0)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3), "tp": tp, "fp": fp, "fn": fn,
            "false_positive_rate": round(fp / max(1, int((y == 0).sum())), 4)}


def zscore_flags(temps):
    out = np.zeros(len(temps), dtype=int)
    for i in range(MIN_HISTORY, len(temps)):
        hist = temps[max(0, i - ZSCORE_WINDOW):i]
        std = max(statistics.pstdev(hist), STD_FLOOR)
        out[i] = int(abs((temps[i] - statistics.fmean(hist)) / std) >= ZSCORE_THRESHOLD)
    return out


def main():
    models = {}
    for name in ("isolation_forest.joblib", "isolation_forest_v2.joblib"):
        p = os.path.join(HERE, "models", name)
        if os.path.exists(p):
            obj = joblib.load(p)
            if isinstance(obj, dict):
                models[obj["version"]] = (obj["model"], obj.get("score_threshold"))
            else:
                models["iforest-prototype-v1"] = (obj, None)
    ys, preds = [], {k: [] for k in list(models) + ["rolling_zscore"]}
    combos = {f"{k}+zscore(AND)": [] for k in models}
    for seed in EVAL_SEEDS:
        df = add_features(make_series(3000, seed, anomaly_rate=0.03))
        y = df["label"].to_numpy().copy()
        y[:MIN_HISTORY] = 0
        ys.append(y)
        z = zscore_flags(df["temperature"].to_numpy())
        preds["rolling_zscore"].append(z)
        for k, (m, thr) in models.items():
            x = df[FEATURE_COLUMNS]
            p = ((m.score_samples(x) < thr) if thr is not None else (m.predict(x) == -1)).astype(int)
            p[:MIN_HISTORY] = 0
            preds[k].append(p)
            combos[f"{k}+zscore(AND)"].append(p & z)
    y = np.concatenate(ys)
    results = {k: prf(y, np.concatenate(v)) for k, v in {**preds, **combos}.items()}
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "dataset": "SIMULATED (ml/dataset.py)",
              "eval_seeds": EVAL_SEEDS, "points": int(len(y)), "anomaly_points": int(y.sum()),
              "caveat": "Point-wise metrics vs injected labels on synthetic data; not field accuracy.",
              "results": results}
    os.makedirs(os.path.join(HERE, "reports"), exist_ok=True)
    with open(os.path.join(HERE, "reports", "evaluation.json"), "w") as f:
        json.dump(report, f, indent=2)
    print(f"{'detector':40s} {'prec':>6s} {'recall':>6s} {'f1':>6s} {'FPR':>7s}")
    for k, r in results.items():
        print(f"{k:40s} {r['precision']:6.3f} {r['recall']:6.3f} {r['f1']:6.3f} {r['false_positive_rate']:7.4f}")


if __name__ == "__main__":
    main()
