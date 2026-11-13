"""Anomaly detection — DECISION SUPPORT ONLY.

Two independent detectors score every valid reading once enough history exists:
  * STATISTICAL  rolling z-score against the sensor's last N readings
  * ML           IsolationForest on rolling-window features (preserved v1 feature pipeline)

Output is an `Anomaly` row (score, method, model version, context, contributing indicators).
An anomaly is NOT an excursion: excursions are decided only by approved threshold rules
(ViolationEngine). When several anomalies cluster on one unit within a window, an
ABNORMAL_PATTERN incident (WARNING, source=ML/STATISTICAL) asks a human to look — it never
quarantines, releases or discards stock.
"""
import logging
import os
import statistics
from datetime import timedelta
from typing import Optional

import joblib
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.metrics import ANOMALIES
from app.db.base import as_utc
from app.ml.features import FEATURE_COLUMNS, build_features_dataframe
from app.models import Anomaly, Incident, StorageUnit, TemperatureReading
from app.models.enums import ACTIVE_INCIDENT_STATUSES, AnomalySeverity, IncidentType, ViolationSeverity

logger = logging.getLogger(__name__)
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ml", "models")
MIN_HISTORY = 10
ZSCORE_WINDOW = 30
ZSCORE_THRESHOLD = 4.0
STD_FLOOR = 0.08  # °C — sensor resolution floor so a perfectly flat signal doesn't explode z


class MLAnomalyService:
    _model = None
    _version: Optional[str] = None
    _threshold: Optional[float] = None
    _loaded = False

    @classmethod
    def load_model(cls):
        if cls._loaded:
            return cls._model
        cls._loaded = True
        for name in ("isolation_forest_v2.joblib", "isolation_forest.joblib"):
            path = os.path.join(MODEL_DIR, name)
            if os.path.exists(path):
                obj = joblib.load(path)
                if isinstance(obj, dict) and "model" in obj:
                    cls._model, cls._version = obj["model"], obj.get("version", name)
                    cls._threshold = obj.get("score_threshold")
                else:
                    cls._model, cls._version = obj, "iforest-prototype-v1"
                logger.info("Loaded anomaly model %s (%s)", name, cls._version)
                return cls._model
        logger.warning("No IsolationForest model found in %s — ML scoring disabled, statistical only", MODEL_DIR)
        return None

    @classmethod
    def model_info(cls) -> dict:
        cls.load_model()
        return {"available": cls._model is not None, "version": cls._version, "score_threshold": cls._threshold,
                "features": FEATURE_COLUMNS, "statistical": {"window": ZSCORE_WINDOW, "threshold": ZSCORE_THRESHOLD}}

    @classmethod
    def score(cls, history: list, current: TemperatureReading) -> dict:
        """Pure scoring (no DB writes). `history` is ascending, excludes `current`."""
        temps = [r.temperature for r in history[-ZSCORE_WINDOW:]]
        mean = statistics.fmean(temps)
        std = max(statistics.pstdev(temps), STD_FLOOR)
        z = (current.temperature - mean) / std
        result = {"z_score": round(z, 3), "rolling_mean": round(mean, 3), "rolling_std": round(std, 3),
                  "stat_flag": abs(z) >= ZSCORE_THRESHOLD, "ml_flag": False, "ml_score": None}
        model = cls.load_model()
        if model is not None:
            df = build_features_dataframe(history[-9:] + [current])
            x = df[FEATURE_COLUMNS].iloc[[-1]]
            score = float(model.score_samples(x)[0])
            result["ml_flag"] = (score < cls._threshold) if cls._threshold is not None else int(model.predict(x)[0]) == -1
            result["ml_score"] = round(score, 4)
            result["ml_threshold"] = cls._threshold
            row = x.iloc[0]
            result["features"] = {k: round(float(row[k]), 3) for k in FEATURE_COLUMNS}
        return result

    @staticmethod
    def explain(s: dict) -> dict:
        indicators = []
        f = s.get("features", {})
        if abs(s["z_score"]) >= ZSCORE_THRESHOLD:
            indicators.append(f"Reading is {abs(s['z_score']):.1f}σ from the recent mean ({s['rolling_mean']}°C)")
        if f and abs(f.get("rate_of_change", 0)) >= 1.0:
            indicators.append(f"Rapid change of {f['rate_of_change']:+.2f}°C since previous reading")
        if f and f.get("rolling_std", 0) >= 1.0:
            indicators.append(f"Elevated short-term variability (σ={f['rolling_std']:.2f}°C)")
        if f and f.get("temp_range", 0) >= 3.0:
            indicators.append(f"Wide 10-reading range ({f['temp_range']:.1f}°C)")
        if not indicators:
            indicators.append("Multivariate pattern unusual relative to training data (no single dominant feature)")
        return {"indicators": indicators,
                "note": "Decision support only. Not a confirmed excursion; thresholds govern excursions."}

    @classmethod
    def evaluate_reading(cls, db: Session, current: TemperatureReading) -> Optional[Anomaly]:
        if not settings.ML_ENABLED or current.quality_status == "invalid":
            return None
        history = (db.query(TemperatureReading)
                   .filter(TemperatureReading.sensor_id == current.sensor_id, TemperatureReading.id != current.id,
                           TemperatureReading.timestamp < current.timestamp)
                   .order_by(desc(TemperatureReading.timestamp)).limit(ZSCORE_WINDOW).all())
        if len(history) < MIN_HISTORY:
            return None  # cold start: not enough context for a meaningful score
        history.reverse()
        s = cls.score(history, current)
        if not (s["stat_flag"] or s["ml_flag"]):
            return None
        if s["stat_flag"] and s["ml_flag"]:
            method, sev = "ISOLATION_FOREST+ROLLING_ZSCORE", AnomalySeverity.HIGH
        elif s["stat_flag"]:
            method, sev = "ROLLING_ZSCORE", AnomalySeverity.MEDIUM
        else:
            method, sev = "ISOLATION_FOREST", AnomalySeverity.LOW
        anomaly = Anomaly(
            sensor_id=current.sensor_id, temperature_reading_id=current.id, storage_unit_id=current.storage_unit_id,
            anomaly_score=s["ml_score"] if s["ml_score"] is not None else -abs(s["z_score"]),
            detection_method=method, severity=sev, temperature=current.temperature,
            model_version=cls._version or "statistical-only", context=s, explanation=cls.explain(s),
            is_simulated=current.is_simulated, detected_at=as_utc(current.timestamp))
        db.add(anomaly)
        db.commit()
        ANOMALIES.labels(method=method).inc()
        cls._check_pattern(db, current)
        return anomaly

    @classmethod
    def _check_pattern(cls, db: Session, current: TemperatureReading):
        since = as_utc(current.timestamp) - timedelta(minutes=settings.ML_PATTERN_WINDOW_MINUTES)
        count = (db.query(Anomaly).filter(Anomaly.storage_unit_id == current.storage_unit_id,
                                          Anomaly.detected_at >= since).count())
        if count < settings.ML_PATTERN_MIN_ANOMALIES:
            return
        unit = db.get(StorageUnit, current.storage_unit_id)
        excursion_active = db.query(Incident).filter(
            Incident.dedup_key == f"EXCURSION:{unit.id}", Incident.status.in_(ACTIVE_INCIDENT_STATUSES)).first()
        if excursion_active:
            return  # the threshold incident already demands attention
        key = f"PATTERN:{unit.id}"
        if db.query(Incident).filter(Incident.dedup_key == key, Incident.status.in_(ACTIVE_INCIDENT_STATUSES)).first():
            return
        from app.services.incident import IncidentService
        inc, _ = IncidentService.open_incident(
            db, incident_type=IncidentType.ABNORMAL_PATTERN, severity=ViolationSeverity.WARNING,
            facility_id=unit.facility_id, storage_unit_id=unit.id, sensor_id=current.sensor_id,
            title=f"Abnormal temperature pattern on {unit.unit_code}",
            description=(f"{count} anomalous readings within {settings.ML_PATTERN_WINDOW_MINUTES} min "
                         "(statistical/ML decision support). Temperature may still be within approved limits; "
                         "please inspect equipment. No stock action is implied."),
            source="ML", dedup_key=key, is_simulated=current.is_simulated)
        db.query(Anomaly).filter(Anomaly.storage_unit_id == unit.id, Anomaly.detected_at >= since,
                                 Anomaly.incident_id.is_(None)).update({"incident_id": inc.id})
        db.commit()
