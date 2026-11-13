"""Route ETA model: loads with metadata, beats the constant-speed baseline on unseen simulated
trips, quantiles are ordered and calibrated, and it degrades to the baseline without a model."""
from datetime import datetime

import numpy as np
import pytest

from app.ml import eta_model
from app.ml.eta_model import (FEATURES, SAME_SITE_MINUTES, EtaModel, baseline_minutes, feature_row, haversine_km,
                              is_peak_hour)
from ml.routing_dataset import make_trips


@pytest.fixture(autouse=True)
def _fresh_model():
    EtaModel.reset()
    yield
    EtaModel.reset()


def test_haversine_known_distances():
    assert haversine_km(12.0, 77.0, 12.0, 77.0) == 0
    assert haversine_km(12.0, 77.0, 13.0, 77.0) == pytest.approx(111.2, abs=0.3)  # 1° of latitude
    assert haversine_km(12.97, 77.59, 12.30, 76.64) == pytest.approx(127, abs=5)   # Bengaluru -> Mysuru


def test_feature_row_encodes_time_and_region():
    row = dict(zip(FEATURES, feature_row(10.0, datetime(2026, 11, 14, 8, 30), same_region=False)))  # Saturday
    assert row["distance_km"] == 10 and row["is_peak"] == 1 and row["is_weekend"] == 1 and row["same_region"] == 0
    assert row["hour_sin"] ** 2 + row["hour_cos"] ** 2 == pytest.approx(1)
    assert is_peak_hour(18.5) and not is_peak_hour(13)


def test_model_loads_with_version_and_metrics():
    info = EtaModel.info()
    assert info["available"] is True
    assert info["version"].startswith("route-eta-gbr")
    assert info["features"] == FEATURES
    assert info["metrics"]["mae_improvement_pct"] > 30
    assert "SIMULATED" in info["data"]


def test_model_beats_constant_speed_baseline_on_unseen_trips():
    test = make_trips(1500, seed=9_001)  # seed never used for training
    p50, p90 = EtaModel.predict(test[FEATURES].values)
    y = test["minutes"].values
    base = np.array([baseline_minutes(d) for d in test["distance_km"]])
    mae, base_mae = np.mean(np.abs(p50 - y)), np.mean(np.abs(base - y))
    assert mae < 0.6 * base_mae, (mae, base_mae)
    assert np.all(p90 >= p50)
    assert 0.82 <= np.mean(y <= p90) <= 0.97  # p90 is roughly calibrated, not wildly conservative


def test_predictions_are_physically_sensible():
    depart = datetime(2026, 11, 11, 13, 0)
    near, far = EtaModel.predict([feature_row(5, depart, True), feature_row(120, depart, True)])[0]
    assert far > near > 0
    peak = EtaModel.predict([feature_row(8, datetime(2026, 11, 11, 8, 30), True)])[0][0]
    night = EtaModel.predict([feature_row(8, datetime(2026, 11, 11, 23, 30), True)])[0][0]
    assert peak > night  # urban rush hour is slower than night driving


def test_matrix_same_site_and_symmetry():
    sites = [{"key": "a", "lat": 12.97, "lon": 77.59, "region_id": "r"},
             {"key": "b", "lat": 13.03, "lon": 77.62, "region_id": "r"}]
    mx = EtaModel.matrix(sites, datetime(2026, 11, 11, 13, 0))
    assert mx[("a", "a")] == (0.0, SAME_SITE_MINUTES, SAME_SITE_MINUTES)
    assert mx[("a", "b")][0] == pytest.approx(mx[("b", "a")][0])
    assert mx[("a", "b")][2] >= mx[("a", "b")][1] > 0


def test_falls_back_to_baseline_without_model(monkeypatch, tmp_path):
    monkeypatch.setattr(eta_model, "MODEL_DIR", str(tmp_path))
    EtaModel.reset()
    info = EtaModel.info()
    assert info["available"] is False and info["version"] == "baseline-physical-v1"
    p50, p90 = EtaModel.predict([feature_row(40, datetime(2026, 11, 11, 13), True)])
    assert p50[0] == pytest.approx(baseline_minutes(40)) and p90[0] > p50[0]


def test_corrupt_model_file_falls_back(monkeypatch, tmp_path):
    (tmp_path / eta_model.MODEL_FILE).write_bytes(b"not a joblib file")
    monkeypatch.setattr(eta_model, "MODEL_DIR", str(tmp_path))
    EtaModel.reset()
    assert EtaModel.info()["available"] is False
