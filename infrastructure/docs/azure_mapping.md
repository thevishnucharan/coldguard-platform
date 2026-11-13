# ColdGuard Infrastructure Mapping

This document describes how the local development components map to their respective Azure production services.

| Local Component (Docker Compose) | Azure Production Service | Purpose |
|----------------------------------|--------------------------|---------|
| **Local PostgreSQL** | **Azure Database for PostgreSQL** | Relational database for core application data (Storage Units, Sensors, Users, Incidents, etc.). |
| **Local Event Source / Simulator** | **Azure Event Hubs** | High-throughput ingestion of real-time temperature telemetry data from sensors. |
| **Local File Storage (OS)** | **Azure Blob Storage** | Storing generated PDF and CSV compliance reports, and audit logs. |
| **Mock AI Provider** | **Azure OpenAI Service** | Providing ML Anomaly detection and intelligent summaries for Root Cause Analysis (RCA). |
| **Docker Build Image** | **Azure Container Registry (ACR)** | Storing and managing private Docker container images for Backend, Frontend, and Simulator. |
| **Docker Compose / Local Host** | **Azure Kubernetes Service (AKS)** | Orchestrating and running the containerized microservices (Backend API, Frontend Dashboard). |
| **Console Notifier** | **Azure Communication Services / SendGrid** | Dispatching email/SMS alerts for high and critical temperature excursions. |
| **Local Console Logs** | **Azure Monitor & Application Insights** | Centralized logging, telemetry, performance monitoring, and alerting. |
| **Local `.env` Secrets** | **Azure Key Vault** | Securely storing database connection strings, API keys, and JWT secrets. |
