# ColdGuard Jenkins CI/CD Setup

The ColdGuard project uses Jenkins for Continuous Integration and Continuous Deployment (CI/CD). The pipeline is defined in the `Jenkinsfile` at the root of the repository.

## Pipeline Overview

The pipeline supports two modes of operation: **Local Mode** (default) and **Azure Mode**.

It executes the following stages:
1. **Checkout**: Pulls the latest code from GitHub.
2. **Backend: Install Dependencies**: Creates a Python virtual environment and installs backend dependencies.
3. **Backend: Lint**: Runs `ruff` to ensure code quality.
4. **Backend: Tests**: Runs pytest with coverage and generates JUnit XML and HTML reports.
5. **Frontend: Install Dependencies**: Runs `npm ci` for the Vite/React app.
6. **Frontend: Tests**: Runs Vitest and generates JUnit XML reports.
7. **Frontend: Build**: Compiles the production bundle and archives it.
8. **Docker: Build**: Builds `backend`, `frontend`, and `simulator` Docker images.
9. **Docker Compose: Smoke Test**: Spins up PostgreSQL and the backend to verify `/health` endpoint accessibility.
10. **ACR: Push Images (Optional)**: Tags and pushes images to Azure Container Registry if Azure mode is enabled.

## Prerequisites

The Jenkins agent running this pipeline requires the following installed on the host:
- `git`
- `python3` and `python3-venv` (Python 3.11+ recommended)
- `node` and `npm` (Node.js 18+ recommended)
- `docker` (with the Jenkins user added to the `docker` group)
- `docker compose` plugin

## Setting Up the Job in Jenkins

1. Create a new **Pipeline** job in Jenkins (e.g., `ColdGuard-CI`).
2. Under the **Pipeline** section, choose **Pipeline script from SCM**.
3. Select **Git** as the SCM.
4. Provide the Repository URL and configure the required credentials to clone the repository.
5. Set the **Script Path** to `Jenkinsfile`.
6. Save and build the job.

By default, the pipeline runs in **Local Mode**. It performs all tests and builds Docker images, but skips pushing to a remote registry, requiring no credentials.

## Enabling Azure ACR Push

To push built images to Azure Container Registry (ACR), you need to configure Jenkins credentials and environment variables.

### 1. Add Jenkins Credentials

1. Go to **Manage Jenkins** -> **Credentials** -> **System** -> **Global credentials**.
2. Click **Add Credentials**.
3. Select **Username with password**.
4. Set **Username** to your ACR login server (e.g., `coldguardacr.azurecr.io` or `00000000-0000-0000-0000-000000000000` if using a Service Principal).
5. Set **Password** to your ACR access token or Service Principal secret.
6. Set **ID** to exactly `coldguard-acr-credentials`.
7. Click **Create**.

### 2. Configure Environment Variables

You can enable Azure mode either globally in Jenkins or at the job level.

To enable at the job level (recommended):
1. Check the box **This project is parameterized** in the job configuration.
2. Add a **Boolean Parameter**:
   - Name: `AZURE_ACR_ENABLED`
   - Default Value: `true` (or leave unchecked to trigger manually)
3. Add a **String Parameter**:
   - Name: `AZURE_ACR_REGISTRY`
   - Default Value: Your ACR login server (e.g., `coldguardacr.azurecr.io`)

Alternatively, configure them globally via **Manage Jenkins** -> **System** -> **Environment variables**.

When `AZURE_ACR_ENABLED` is true, Stage 10 will authenticate with the ACR, tag all built images, and push them.
