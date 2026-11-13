from datetime import datetime, timezone, timedelta
from typing import Tuple
from sqlalchemy.orm import Session
from app.models import TemperatureReading
import uuid

class QualityStatus:
    VALID = "valid"
    SUSPICIOUS = "suspicious"
    INVALID = "invalid"

class DataQualityEngine:
    MAX_TEMP = 100.0
    MIN_TEMP = -100.0
    MAX_JUMP_DEG_PER_MIN = 10.0 # max degrees change per minute
    
    @classmethod
    def evaluate(cls, db: Session, sensor_id: uuid.UUID, temperature: float, timestamp: datetime) -> Tuple[str, str]:
        """
        Evaluates a temperature reading and returns (status, reason).
        """
        now = datetime.now(timezone.utc)
        
        # Normalize timestamp to UTC for comparison
        ts_eval = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)

        # 1. Impossible values
        if temperature > cls.MAX_TEMP or temperature < cls.MIN_TEMP:
            return QualityStatus.INVALID, f"Impossible temperature value: {temperature}°C"
            
        # 2. Future timestamps
        if ts_eval > now + timedelta(minutes=1): # 1 min leniency for clock drift
            return QualityStatus.INVALID, "Timestamp is in the future"
            
        # 3. Stale timestamps
        if ts_eval < now - timedelta(hours=24):
            return QualityStatus.SUSPICIOUS, "Reading is more than 24 hours old"
            
        # 4. Duplicate reading
        duplicate = db.query(TemperatureReading).filter(
            TemperatureReading.sensor_id == sensor_id,
            TemperatureReading.timestamp == timestamp
        ).first()
        if duplicate:
            return QualityStatus.INVALID, "Duplicate reading timestamp for this sensor"
            
        # 5. Sudden unrealistic jumps
        last_reading = db.query(TemperatureReading).filter(
            TemperatureReading.sensor_id == sensor_id,
            TemperatureReading.timestamp < timestamp
        ).order_by(TemperatureReading.timestamp.desc()).first()
        
        if last_reading:
            last_ts = last_reading.timestamp if last_reading.timestamp.tzinfo else last_reading.timestamp.replace(tzinfo=timezone.utc)
            time_diff_min = (ts_eval - last_ts).total_seconds() / 60.0
            if time_diff_min > 0:
                temp_diff = abs(temperature - last_reading.temperature)
                if (temp_diff / time_diff_min) > cls.MAX_JUMP_DEG_PER_MIN:
                    return QualityStatus.SUSPICIOUS, f"Unrealistic temperature jump of {temp_diff:.2f}°C in {time_diff_min:.2f} mins"

        return QualityStatus.VALID, "Passed all quality checks"
