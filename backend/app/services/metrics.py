from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from typing import Dict, Any, Optional

from app.models.storage import StorageUnit, Sensor
from app.models.monitoring import TemperatureReading
from app.models.incident import Incident, Violation
from app.models.enums import ViolationStatus, IncidentStatus, ViolationSeverity, ACTIVE_INCIDENT_STATUSES

class MetricsService:
    @classmethod
    def get_dashboard_metrics(
        cls, 
        db: Session, 
        start_date: Optional[datetime] = None, 
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Aggregates system metrics.
        - total storage units
        - active sensors
        - total readings
        - total violations
        - open incidents
        - resolved incidents
        - critical incidents
        - average excursion duration
        - maximum temperature
        - minimum temperature
        """
        
        # Base queries
        q_units = db.query(func.count(StorageUnit.id))
        q_sensors = db.query(func.count(Sensor.id)).filter(Sensor.status == 'ONLINE')
        
        q_readings = db.query(func.count(TemperatureReading.id))
        q_max_temp = db.query(func.max(TemperatureReading.temperature))
        q_min_temp = db.query(func.min(TemperatureReading.temperature))
        
        q_violations = db.query(func.count(Violation.id))
        q_avg_excursion = db.query(func.avg(Violation.duration_seconds))
        
        q_incidents_open = db.query(func.count(Incident.id)).filter(Incident.status.in_(ACTIVE_INCIDENT_STATUSES))
        q_incidents_resolved = db.query(func.count(Incident.id)).filter(Incident.status.in_([IncidentStatus.RESOLVED, IncidentStatus.CLOSED]))
        q_incidents_critical = db.query(func.count(Incident.id)).filter(Incident.severity == ViolationSeverity.CRITICAL)
        
        # Apply date filters to time-series data
        if start_date:
            q_readings = q_readings.filter(TemperatureReading.timestamp >= start_date)
            q_max_temp = q_max_temp.filter(TemperatureReading.timestamp >= start_date)
            q_min_temp = q_min_temp.filter(TemperatureReading.timestamp >= start_date)
            
            q_violations = q_violations.filter(Violation.start_time >= start_date)
            q_avg_excursion = q_avg_excursion.filter(Violation.start_time >= start_date)
            
            q_incidents_open = q_incidents_open.filter(Incident.created_at >= start_date)
            q_incidents_resolved = q_incidents_resolved.filter(Incident.created_at >= start_date)
            q_incidents_critical = q_incidents_critical.filter(Incident.created_at >= start_date)
            
        if end_date:
            q_readings = q_readings.filter(TemperatureReading.timestamp <= end_date)
            q_max_temp = q_max_temp.filter(TemperatureReading.timestamp <= end_date)
            q_min_temp = q_min_temp.filter(TemperatureReading.timestamp <= end_date)
            
            q_violations = q_violations.filter(Violation.start_time <= end_date)
            q_avg_excursion = q_avg_excursion.filter(Violation.start_time <= end_date)
            
            q_incidents_open = q_incidents_open.filter(Incident.created_at <= end_date)
            q_incidents_resolved = q_incidents_resolved.filter(Incident.created_at <= end_date)
            q_incidents_critical = q_incidents_critical.filter(Incident.created_at <= end_date)
            
        avg_duration = q_avg_excursion.scalar()
        
        return {
            "total_storage_units": q_units.scalar() or 0,
            "active_sensors": q_sensors.scalar() or 0,
            "total_readings": q_readings.scalar() or 0,
            "total_violations": q_violations.scalar() or 0,
            "open_incidents": q_incidents_open.scalar() or 0,
            "resolved_incidents": q_incidents_resolved.scalar() or 0,
            "critical_incidents": q_incidents_critical.scalar() or 0,
            "average_excursion_duration_seconds": float(avg_duration) if avg_duration else 0.0,
            "maximum_temperature": float(q_max_temp.scalar() or 0.0),
            "minimum_temperature": float(q_min_temp.scalar() or 0.0)
        }
