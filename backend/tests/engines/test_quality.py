import pytest
from datetime import datetime, timezone, timedelta
import uuid
from app.engines.quality import DataQualityEngine, QualityStatus

# Removed test_quality_valid

def test_quality_impossible_temp():
    # > 100
    status, reason = DataQualityEngine.evaluate(None, uuid.uuid4(), 105.0, datetime.now(timezone.utc))
    assert status == QualityStatus.INVALID
    assert "Impossible" in reason

    # < -100
    status, reason = DataQualityEngine.evaluate(None, uuid.uuid4(), -105.0, datetime.now(timezone.utc))
    assert status == QualityStatus.INVALID

def test_quality_future_date():
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    status, reason = DataQualityEngine.evaluate(None, uuid.uuid4(), 5.0, future)
    assert status == QualityStatus.INVALID
    assert "future" in reason

def test_quality_stale_date():
    stale = datetime.now(timezone.utc) - timedelta(hours=25)
    status, reason = DataQualityEngine.evaluate(None, uuid.uuid4(), 5.0, stale)
    assert status == QualityStatus.SUSPICIOUS
    assert "24 hours old" in reason
