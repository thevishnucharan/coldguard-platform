import pytest
import uuid
from datetime import datetime, timezone, timedelta

from app.models import StorageUnit, Sensor, TemperatureReading
from app.models.enums import SensorStatus
from app.engines.quality import DataQualityEngine, QualityStatus


def _make_sensor_and_storage(db):
    su = StorageUnit(
        unit_code=f"SU-DQ-{uuid.uuid4().hex[:6]}",
        name="DQ Test Unit",
        location="Lab",
        unit_type="Refrigerator",
        min_temperature=2.0,
        max_temperature=8.0,
        status="ACTIVE",
    )
    db.add(su)
    db.flush()
    sensor = Sensor(
        sensor_code=f"SN-DQ-{uuid.uuid4().hex[:6]}",
        storage_unit_id=su.id,
        sensor_type="BLE-TEMP",
        status=SensorStatus.ONLINE,
    )
    db.add(sensor)
    db.commit()
    db.refresh(su)
    db.refresh(sensor)
    return su, sensor


class TestDataQualityEngine:
    def test_valid_reading_passes(self, db):
        _, sensor = _make_sensor_and_storage(db)
        now = datetime.now(timezone.utc)
        status, reason = DataQualityEngine.evaluate(db, sensor.id, 5.0, now)
        assert status == QualityStatus.VALID

    def test_temperature_above_max_invalid(self, db):
        _, sensor = _make_sensor_and_storage(db)
        now = datetime.now(timezone.utc)
        status, reason = DataQualityEngine.evaluate(db, sensor.id, 150.0, now)
        assert status == QualityStatus.INVALID
        assert "Impossible" in reason

    def test_temperature_below_min_invalid(self, db):
        _, sensor = _make_sensor_and_storage(db)
        now = datetime.now(timezone.utc)
        status, reason = DataQualityEngine.evaluate(db, sensor.id, -150.0, now)
        assert status == QualityStatus.INVALID

    def test_future_timestamp_invalid(self, db):
        _, sensor = _make_sensor_and_storage(db)
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        status, reason = DataQualityEngine.evaluate(db, sensor.id, 5.0, future)
        assert status == QualityStatus.INVALID
        assert "future" in reason.lower()

    def test_stale_timestamp_suspicious(self, db):
        _, sensor = _make_sensor_and_storage(db)
        old = datetime.now(timezone.utc) - timedelta(hours=25)
        status, reason = DataQualityEngine.evaluate(db, sensor.id, 5.0, old)
        assert status == QualityStatus.SUSPICIOUS
        assert "24 hours" in reason

    def test_duplicate_timestamp_invalid(self, db):
        _, sensor = _make_sensor_and_storage(db)
        ts = datetime.now(timezone.utc)
        # Insert a reading
        r = TemperatureReading(
            storage_unit_id=sensor.storage_unit_id,
            sensor_id=sensor.id,
            temperature=4.0,
            timestamp=ts,
            source="test",
            quality_status="valid",
        )
        db.add(r)
        db.commit()
        # Evaluate duplicate
        status, reason = DataQualityEngine.evaluate(db, sensor.id, 4.5, ts)
        assert status == QualityStatus.INVALID
        assert "Duplicate" in reason

    def test_unrealistic_jump_suspicious(self, db):
        su, sensor = _make_sensor_and_storage(db)
        t1 = datetime.now(timezone.utc) - timedelta(minutes=2)
        t2 = t1 + timedelta(minutes=2)
        r = TemperatureReading(
            storage_unit_id=su.id,
            sensor_id=sensor.id,
            temperature=4.0,
            timestamp=t1,
            source="test",
            quality_status="valid",
        )
        db.add(r)
        db.commit()
        # Jump of 50°C in 2 minutes = 25 deg/min >> 10 deg/min threshold
        status, reason = DataQualityEngine.evaluate(db, sensor.id, 54.0, t2)
        assert status == QualityStatus.SUSPICIOUS
        assert "Unrealistic" in reason

    def test_realistic_jump_valid(self, db):
        su, sensor = _make_sensor_and_storage(db)
        t1 = datetime.now(timezone.utc) - timedelta(minutes=10)
        t2 = t1 + timedelta(minutes=10)
        r = TemperatureReading(
            storage_unit_id=su.id,
            sensor_id=sensor.id,
            temperature=4.0,
            timestamp=t1,
            source="test",
            quality_status="valid",
        )
        db.add(r)
        db.commit()
        # Jump of 1°C in 10 minutes = 0.1 deg/min — perfectly realistic
        status, reason = DataQualityEngine.evaluate(db, sensor.id, 5.0, t2)
        assert status == QualityStatus.VALID

    def test_boundary_temperature_valid(self, db):
        _, sensor = _make_sensor_and_storage(db)
        now = datetime.now(timezone.utc)
        # Exact boundary values
        s1, _ = DataQualityEngine.evaluate(db, sensor.id, 100.0, now)
        assert s1 == QualityStatus.VALID
        s2, _ = DataQualityEngine.evaluate(db, sensor.id, -100.0, now - timedelta(seconds=1))
        assert s2 == QualityStatus.VALID
