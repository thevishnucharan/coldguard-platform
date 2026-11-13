"""SIMULATED labelled dataset for training/evaluating the anomaly detectors.

LIMITATIONS (read before quoting any number):
* Entirely synthetic. Generated from app/simulation/scenarios.py plus injected spikes,
  drops, drifts and stuck/noisy segments. It does not capture real compressor physics,
  door-opening behaviour, defrost cycles, sensor placement or seasonal load.
* Labels mark *injected* anomalies only. Metrics computed on this data measure how well
  detectors recover the injected patterns — NOT field accuracy.
* Real deployments must re-evaluate on facility data with human-labelled events.
"""
import os
import random
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.simulation.scenarios import generate  # noqa: E402


def make_series(n: int, seed: int, lo=2.0, hi=8.0, anomaly_rate=0.03, start="2026-01-01") -> pd.DataFrame:
    rng = random.Random(seed)
    nprng = np.random.default_rng(seed)
    ts = pd.date_range(start=start, periods=n, freq="min", tz="UTC")
    temps = np.array([generate("normal", i * 60, lo, hi, rng) for i in range(n)], dtype=float)
    labels = np.zeros(n, dtype=int)
    i = 20
    while i < n - 20:
        if nprng.random() < anomaly_rate:
            kind = nprng.choice(["spike", "drop", "drift", "noise"])
            if kind == "spike":
                temps[i] += nprng.uniform(4, 10); labels[i] = 1; i += 1
            elif kind == "drop":
                temps[i] -= nprng.uniform(4, 8); labels[i] = 1; i += 1
            elif kind == "drift":
                L = int(nprng.integers(5, 12))
                temps[i:i + L] += np.linspace(1.5, 7, L); labels[i:i + L] = 1; i += L
            else:
                L = int(nprng.integers(5, 10))
                temps[i:i + L] += nprng.normal(0, 2.5, L); labels[i:i + L] = 1; i += L
        i += 1
    return pd.DataFrame({"timestamp": ts, "temperature": temps.round(2), "label": labels})


if __name__ == "__main__":
    df = make_series(5000, 7)
    print(df.label.mean(), df.describe())
