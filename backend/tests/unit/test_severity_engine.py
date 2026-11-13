import pytest
from app.engines.severity import SeverityEngine
from app.models.enums import ViolationSeverity


class TestSeverityEngine:
    """
    Default thresholds (from SeverityEngine class):
      WARNING  : deviation < 2.0  AND duration < 15 min
      HIGH     : deviation < 5.0  AND duration < 60 min
      CRITICAL : deviation >= 5.0 OR  duration >= 60 min
    """

    def test_small_deviation_short_duration_warning(self):
        s = SeverityEngine.evaluate(deviation=1.0, duration_mins=5.0)
        assert s == ViolationSeverity.WARNING

    def test_moderate_deviation_warning(self):
        # 1.9°C deviation, 14 mins — still WARNING
        s = SeverityEngine.evaluate(deviation=1.9, duration_mins=14.0)
        assert s == ViolationSeverity.WARNING

    def test_at_warning_threshold_high(self):
        # Exactly at warning threshold → HIGH
        s = SeverityEngine.evaluate(deviation=2.0, duration_mins=5.0)
        assert s == ViolationSeverity.HIGH

    def test_moderate_deviation_high(self):
        # 3.4°C (like excursion scenario), 30 mins → HIGH
        s = SeverityEngine.evaluate(deviation=3.4, duration_mins=30.0)
        assert s == ViolationSeverity.HIGH

    def test_at_high_threshold_critical(self):
        # Exactly at CRITICAL deviation threshold
        s = SeverityEngine.evaluate(deviation=5.0, duration_mins=10.0)
        assert s == ViolationSeverity.CRITICAL

    def test_long_duration_critical(self):
        # Duration >= 60 min → CRITICAL even with small deviation
        s = SeverityEngine.evaluate(deviation=1.0, duration_mins=60.0)
        assert s == ViolationSeverity.CRITICAL

    def test_very_high_deviation_critical(self):
        s = SeverityEngine.evaluate(deviation=10.0, duration_mins=1.0)
        assert s == ViolationSeverity.CRITICAL

    def test_zero_deviation_zero_duration_warning(self):
        # Degenerate case: deviation=0 is technically in-bounds; engine handles gracefully
        s = SeverityEngine.evaluate(deviation=0.0, duration_mins=0.0)
        assert s == ViolationSeverity.WARNING

    def test_duration_boundary_14_59_high(self):
        # Just under CRITICAL duration threshold
        s = SeverityEngine.evaluate(deviation=1.0, duration_mins=59.9)
        assert s == ViolationSeverity.HIGH

    def test_duration_exactly_60_critical(self):
        s = SeverityEngine.evaluate(deviation=1.0, duration_mins=60.0)
        assert s == ViolationSeverity.CRITICAL

    def test_evaluate_without_db_uses_defaults(self):
        """Ensure engine works without a db session (no config lookup)."""
        s = SeverityEngine.evaluate(deviation=6.0, duration_mins=90.0, db=None)
        assert s == ViolationSeverity.CRITICAL
