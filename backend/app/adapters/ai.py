from typing import Protocol, Any, Dict
import logging

logger = logging.getLogger(__name__)

class AIProvider(Protocol):
    def generate_summary(self, context: Dict[str, Any]) -> str:
        """Generates an operational summary based on the provided context."""
        ...

class MockAIProvider:
    def generate_summary(self, context: Dict[str, Any]) -> str:
        """
        A local, offline mock provider that strictly formats the AI output 
        without making medical safety determinations.
        """
        logger.info("Generating mock AI summary.")
        
        incident_no = context.get('incident_number', 'UNKNOWN')
        peak_temp = context.get('peak_temperature', 'N/A')
        duration = context.get('duration_seconds', 0) // 60
        
        # Build strict structure
        summary = (
            f"**AI-generated operational assistance**\n\n"
            f"### Incident Summary\n"
            f"{incident_no} experienced a temperature excursion peaking at {peak_temp}°C for {duration} minutes.\n\n"
            f"### Observed Facts\n"
            f"- Storage Unit: {context.get('storage_unit', 'Unknown')}\n"
            f"- Sensor: {context.get('sensor', 'Unknown')} (Health: {context.get('sensor_health', 'Unknown')})\n"
            f"- Affected Batches: {len(context.get('batches', []))}\n\n"
            f"### Investigation Checklist\n"
            f"- [ ] Check refrigerator door.\n"
            f"- [ ] Verify power supply.\n"
            f"- [ ] Check cooling system.\n"
            f"- [ ] Verify sensor condition.\n"
            f"- [ ] Review affected batches for potential quarantine.\n\n"
            f"### Suggested Information to Verify\n"
            f"Verify if there was a scheduled maintenance or known power outage during the time window. "
            f"Ensure the physical sensor has not been dislodged."
        )
        return summary

class FutureAzureOpenAIProvider:
    def generate_summary(self, context: Dict[str, Any]) -> str:
        raise NotImplementedError("Azure OpenAI integration requires a valid API Key and endpoint configuration.")
