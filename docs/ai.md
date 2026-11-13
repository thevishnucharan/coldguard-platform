# AI Incident Assistant

To aid Quality Assurance personnel, ColdGuard features an AI-assisted Incident Summary generator.

## Purpose
When an incident is complex, spans a long duration, or affects multiple batches, human operators must synthesize the timeline, peak deviations, and affected products into a cohesive QA report. The AI Assistant automates this synthesis.

## Integration Point
Located in the Incident Details view, operators can click "Generate Summary". The backend packages the incident metadata, telemetry peaks, and affected batches into a prompt and requests a natural language summary.

## Current Implementation
Currently implemented locally using a Mock Provider (`AI_PROVIDER=mock`). It returns a pre-formatted, static summary to validate the frontend/backend contract and loading states.

## Future Azure Integration
Designed to integrate directly with **Azure OpenAI**. When `AI_PROVIDER=azure` is set and credentials are provided, the payload will be sent to a deployed GPT-4 model to generate genuine, context-aware operational summaries.
