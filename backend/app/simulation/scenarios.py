"""Deterministic-ish temperature scenario generators for DEMONSTRATION ONLY.

Pure functions (no app imports) so the standalone MQTT simulator container can reuse this
exact file. Every generated reading must be flagged `simulated=true` by the caller.

Scenarios
  normal        stable around the midpoint with small noise and compressor cycling
  drift         gradual warming (~0.12 °C/min) until ~4 °C above the upper limit
  excursion     sudden spike above the limit for ~12 min, then recovery
  fluctuation   repeated oscillation across the upper limit (~5 min period)
  missing       intermittent gaps (~65 % of readings dropped)
  disconnect    no readings at all (sensor offline)
"""
import math
import random
from typing import Optional

SCENARIOS = ("normal", "drift", "excursion", "fluctuation", "missing", "disconnect")


def generate(scenario: str, elapsed_s: float, lo: float, hi: float, rng: random.Random) -> Optional[float]:
    """Return a temperature, or None when the scenario emits nothing for this tick."""
    mid = (lo + hi) / 2.0
    span = max(hi - lo, 1.0)
    noise = rng.gauss(0, 0.08)
    cycle = 0.18 * span * math.sin(elapsed_s / 420.0 * 2 * math.pi)  # ~7-minute compressor cycle
    minutes = elapsed_s / 60.0
    if scenario == "disconnect":
        return None
    if scenario == "missing":
        return None if rng.random() < 0.65 else round(mid + cycle + noise, 2)
    if scenario == "drift":
        return round(min(mid + 0.12 * minutes, hi + 4.0) + noise, 2)
    if scenario == "excursion":
        if 1.0 <= minutes < 13.0:
            ramp = min(1.0, (minutes - 1.0) / 1.5)
            return round(mid + cycle + ramp * (hi - mid + 4.5) + noise, 2)
        return round(mid + cycle + noise, 2)
    if scenario == "fluctuation":
        return round(mid + (hi - mid + 1.8) * math.sin(elapsed_s / 300.0 * 2 * math.pi) + noise, 2)
    return round(mid + cycle + noise, 2)  # normal
