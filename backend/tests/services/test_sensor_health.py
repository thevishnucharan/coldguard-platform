import pytest
from datetime import datetime, timedelta, timezone
import uuid

from app.models.enums import SensorStatus, SensorHealthState
from app.models.storage import StorageUnit, Sensor
from app.models.monitoring import TemperatureReading, SensorHealthEvent
from app.services.sensor_health import SensorHealthService

@pytest.fixture
def test_storage(db):
    storage = StorageUnit(unit_code=f"SU-{uuid.uuid4().hex[:6]}", name="Test", location="A", unit_type="B", min_temperature=2, max_temperature=8, status="ACTIVE")
    db.add(storage)
    db.commit()
    db.refresh(storage)
    return storage

@pytest.fixture
def test_sensor(db, test_storage):
    sensor = Sensor(sensor_code=f"SENS-{uuid.uuid4().hex[:6]}", storage_unit_id=test_storage.id, sensor_type="B", status=SensorStatus.ONLINE)
    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    return sensor

def _add_reading(db, sensor_id, temp, ts):
    r = TemperatureReading(
        sensor_id=sensor_id,
        storage_unit_id=uuid.uuid4(), # doesn't matter for this test
        temperature=temp,
        timestamp=ts,
        source="TEST",
        quality_status="VALID"
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r

def test_invalid_temperature(db, test_sensor):
    r = _add_reading(db, test_sensor.id, 500.0, datetime.now(timezone.utc))
    SensorHealthService.evaluate_reading(db, r)
    
    events = db.query(SensorHealthEvent).filter(SensorHealthEvent.sensor_id == test_sensor.id).all()
    assert len(events) == 1
    assert events[0].event_type == "INVALID_TEMPERATURE"
    assert events[0].health_state == SensorHealthState.CRITICAL

def test_unrealistic_jump(db, test_sensor):
    now = datetime.now(timezone.utc)
    # First reading is 5.0
    r1 = _add_reading(db, test_sensor.id, 5.0, now - timedelta(minutes=5))
    SensorHealthService.evaluate_reading(db, r1)
    
    # Second reading is 25.0 (jump of 20)
    r2 = _add_reading(db, test_sensor.id, 25.0, now)
    SensorHealthService.evaluate_reading(db, r2)
    
    events = db.query(SensorHealthEvent).filter(SensorHealthEvent.sensor_id == test_sensor.id).all()
    assert len(events) == 1
    assert events[0].event_type == "UNREALISTIC_JUMP"

def test_stuck_sensor(db, test_sensor):
    now = datetime.now(timezone.utc)
    for i in range(SensorHealthService.CONSTANT_TEMP_COUNT + 1):
        r = _add_reading(db, test_sensor.id, 5.1, now + timedelta(minutes=i))
        SensorHealthService.evaluate_reading(db, r)
        
    events = db.query(SensorHealthEvent).filter(SensorHealthEvent.sensor_id == test_sensor.id).all()
    # It will trigger on the CONSTANT_TEMP_COUNT+1 reading
    assert len(events) == 1
    assert events[0].event_type == "POSSIBLE_STUCK_SENSOR"
    assert events[0].health_state == SensorHealthState.WARNING

def test_check_offline_sensors(db, test_sensor):
    # Manually set last_reading_at to 1 hour ago
    test_sensor.last_reading_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.add(test_sensor)
    db.commit()
    
    SensorHealthService.check_offline_sensors(db)
    
    db.refresh(test_sensor)
    assert test_sensor.status == SensorStatus.OFFLINE
    
    events = db.query(SensorHealthEvent).filter(SensorHealthEvent.sensor_id == test_sensor.id).all()
    assert len(events) == 1
    assert events[0].event_type == "SENSOR_OFFLINE"
    assert events[0].health_state == SensorHealthState.OFFLINE
