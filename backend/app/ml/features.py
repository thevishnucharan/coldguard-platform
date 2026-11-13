"""Feature engineering shared by training, evaluation and online inference (preserved v1)."""
from typing import List

import pandas as pd

FEATURE_COLUMNS = ["current_temp", "rolling_mean", "rolling_std", "deviation_from_mean", "rate_of_change", "temp_range"]


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(by="timestamp").reset_index(drop=True)
    df["current_temp"] = df["temperature"]
    rolling = df["temperature"].rolling(window=10, min_periods=1)
    df["rolling_mean"] = rolling.mean()
    df["rolling_std"] = rolling.std().fillna(0)
    df["deviation_from_mean"] = df["temperature"] - df["rolling_mean"]
    df["rate_of_change"] = df["temperature"].diff().fillna(0)
    df["temp_range"] = rolling.max() - rolling.min()
    return df


def build_features_dataframe(readings: List) -> pd.DataFrame:
    if not readings:
        return pd.DataFrame()
    df = pd.DataFrame([{"timestamp": r.timestamp, "temperature": r.temperature, "id": r.id} for r in readings])
    # SQLite returns naive datetimes while live readings are tz-aware: normalise to UTC
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return add_features(df)
