import uuid
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.incident import Incident
from app.adapters.ai import MockAIProvider
from app.services.incident import IncidentService
from app.models.monitoring import SensorHealthEvent
from sqlalchemy import desc

class AIAssistantService:
    @classmethod
    def get_provider(cls):
        # In a real environment, this might check env vars to load AzureOpenAIProvider
        return MockAIProvider()

    @classmethod
    def generate_summary(cls, db: Session, incident_id: uuid.UUID) -> str:
        incident = db.get(Incident, incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
            
        violation = incident.violation
        if not violation:
            raise HTTPException(status_code=400, detail="Incident has no associated violation data")
            
        # Gather affected batches
        affected_batches = IncidentService.identify_affected_batches(db, incident_id)
        
        # Gather sensor health
        sensor = violation.sensor if hasattr(violation, 'sensor') else None
        sensor_code = "Unknown"
        sensor_health = "Unknown"
        if hasattr(violation.storage_unit, 'sensors') and violation.storage_unit.sensors:
            # Assuming the first sensor of the unit for simplicity in this context
            sensor_obj = violation.storage_unit.sensors[0]
            sensor_code = sensor_obj.sensor_code
            # Get latest health
            latest_health = db.query(SensorHealthEvent).filter(
                SensorHealthEvent.sensor_id == sensor_obj.id
            ).order_by(desc(SensorHealthEvent.detected_at)).first()
            if latest_health:
                sensor_health = latest_health.health_state.value
                
        # Build Context Dictionary
        context = {
            "incident_number": incident.incident_number,
            "peak_temperature": violation.peak_temperature,
            "duration_seconds": violation.duration_seconds,
            "storage_unit": violation.storage_unit.unit_code,
            "sensor": sensor_code,
            "sensor_health": sensor_health,
            "batches": affected_batches,
            "investigation_notes": incident.investigation_notes
        }
        
        provider = cls.get_provider()
        summary = provider.generate_summary(context)
        
        # Persist summary
        incident.ai_summary = summary
        db.add(incident)
        db.commit()
        
        return summary
