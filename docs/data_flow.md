# ColdGuard Data Flow Architecture

ColdGuard is designed to operate locally without external cloud dependencies during development, while remaining fully "Azure-ready" for production deployments. We achieve this using the **Adapter Pattern**.

## The Ingestion Pipeline

### 1. TemperatureEventSource (Abstract Base Class)
The core of our ingestion pipeline is the `TemperatureEventSource` interface (`backend/app/adapters/event_source.py`). It defines a contract that any event provider must fulfill (`ingest`, `ingest_bulk`).

### 2. Local Mode (Current Implementation)
In Local Mode, the Simulator bypasses heavy message brokers and talks directly to the FastAPI Backend.

**Flow:**
`Simulator Script` ➔ `POST /api/v1/temperature/readings` ➔ `LocalEventSource` ➔ `DataQualityEngine` ➔ `PostgreSQL Database`

- The `LocalEventSource` adapter intercepts the HTTP payload and passes it to the `DataQualityEngine`.
- If the quality engine rejects the payload (e.g., impossible temperature > 100°C), the adapter raises a `400 Bad Request` back to the Simulator.

### 3. Azure IoT Hub / Event Hubs Mode (Future Implementation)
In the future production environment, the Simulator (acting as IoT devices) will stream millions of events per second directly to an Azure Event Hub, bypassing the FastAPI REST endpoints entirely.

**Flow:**
`Physical Sensors` ➔ `Azure IoT Hub` ➔ `Azure Event Hub` ➔ `FutureAzureEventHubSource` (Daemon) ➔ `DataQualityEngine` ➔ `PostgreSQL Database`

- The `FutureAzureEventHubSource` is already stubbed out. It will run as a continuous background daemon listening to an Event Hub partition.
- It shares the **exact same** `DataQualityEngine` as the local API, ensuring identical validation rules apply whether data comes from HTTP or Event Hubs.

## The Data Quality Engine

Regardless of the source adapter, all readings pass through `DataQualityEngine.evaluate()`. It strictly categorizes data as:
- **VALID**: Standard readings.
- **SUSPICIOUS**: Retained but flagged (e.g., > 24 hours stale, or a sudden jump > 10°C/min).
- **INVALID**: Dropped/Rejected (e.g., future timestamps, duplicates, physical impossibilities).
