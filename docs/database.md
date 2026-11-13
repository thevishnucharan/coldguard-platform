# Database Schema

ColdGuard uses a highly relational PostgreSQL schema optimized for both telemetry tracking and audit compliance.

## Core Entities
- **StorageUnit**: Physical containers (Freezers, Refrigerators). Defines acceptable temperature bounds.
- **Sensor**: IoT hardware linked to a Storage Unit.
- **Product & Batch**: Inventory currently residing inside Storage Units.
- **TemperatureReading**: High-frequency telemetry.
- **Violation**: A tracked deviation from acceptable limits. Maintains state (peak, duration).
- **Incident**: The workflow wrapper around a Violation.
- **IncidentBatch**: Association table linking an Incident to potentially affected Batches.
- **Alert**: Notification records.
- **AuditLog**: Immutable ledger for 21 CFR Part 11 style tracking.

## Telemetry Optimization
In the local implementation, `TemperatureReading` is a standard table.
*Future Azure Integration Note: When migrating to Azure, this table is designed to map to TimescaleDB or Azure Data Explorer (ADX) for high-scale time-series ingestion.*
