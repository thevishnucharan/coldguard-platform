import pytest
from sqlalchemy.exc import IntegrityError
from app.models import User, StorageUnit, Sensor, Product, Batch
from app.models.enums import Role, StorageUnitStatus, SensorStatus, BatchStatus
from datetime import datetime, timezone, timedelta

def test_create_user(db):
    user = User(
        name="Alice Admin",
        email="alice@example.com",
        password_hash="hashedpassword",
        role=Role.ADMIN
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    assert user.id is not None
    assert user.email == "alice@example.com"
    assert user.role == Role.ADMIN
    assert user.is_active is True

def test_unique_email_constraint(db):
    user1 = User(name="User1", email="test@example.com", password_hash="hash", role=Role.OPERATOR)
    db.add(user1)
    db.commit()

    user2 = User(name="User2", email="test@example.com", password_hash="hash", role=Role.AUDITOR)
    db.add(user2)
    with pytest.raises(IntegrityError):
        db.commit()

def test_create_storage_and_sensor(db):
    storage = StorageUnit(
        unit_code="SU-001",
        name="Main Freezer",
        location="Warehouse A",
        unit_type="Walk-in Freezer",
        min_temperature=-25.0,
        max_temperature=-15.0,
        status=StorageUnitStatus.ACTIVE
    )
    db.add(storage)
    db.commit()

    sensor = Sensor(
        sensor_code="SENS-101",
        storage_unit_id=storage.id,
        sensor_type="Temperature Probe",
        status=SensorStatus.ONLINE
    )
    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    
    assert sensor.storage_unit_id == storage.id
    assert storage.sensors[0].sensor_code == "SENS-101"

def test_create_product_and_batch(db):
    # Setup Storage
    storage = StorageUnit(
        unit_code="SU-002",
        name="Vaccine Fridge",
        location="Clinic B",
        unit_type="Medical Fridge",
        min_temperature=2.0,
        max_temperature=8.0
    )
    db.add(storage)
    
    # Setup Product
    product = Product(
        name="COVID-19 mRNA Vaccine",
        category="Vaccine",
        min_temperature=2.0,
        max_temperature=8.0
    )
    db.add(product)
    db.commit()
    
    # Setup Batch
    expiry = datetime.now(timezone.utc) + timedelta(days=180)
    batch = Batch(
        batch_number="B-7890",
        product_id=product.id,
        storage_unit_id=storage.id,
        start_time=datetime.now(timezone.utc),
        expiry_date=expiry,
        status=BatchStatus.ACTIVE
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    assert batch.product_id == product.id
    assert batch.product.name == "COVID-19 mRNA Vaccine"
    assert batch.storage_unit.unit_code == "SU-002"
