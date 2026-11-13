# Azure Architecture Mapping

ColdGuard is built locally to facilitate an easy transition to Microsoft Azure.

## Component Mapping

| Local Development Component | Future Azure Production Service | Purpose |
|---|---|---|
| PostgreSQL Container | Azure Database for PostgreSQL Flexible Server | Relational storage, relational models, audit logs. |
| React/Vite Frontend Container | Azure Static Web Apps | Hosts the compiled SPA dashboard. |
| FastAPI Backend Container | Azure Kubernetes Service (AKS) | Scalable hosting for the core domain engines. |
| Local File System | Azure Blob Storage | Stores generated PDF and CSV compliance reports. |
| `.env` Files | Azure Key Vault + Workload Identity | Production secret and configuration management. |
| Console Logs / Local Metrics | Azure Monitor / Application Insights | Distributed tracing, log aggregation, custom metric alerts. |
| Local AI Mock | Azure OpenAI | Generates the intelligent incident summaries. |
| REST IoT Ingestion | Azure Event Hubs / IoT Hub | High-throughput streaming ingestion of telemetry data. |

*Note: Azure deployment is NOT currently completed. This mapping represents the intended architectural evolution.*
