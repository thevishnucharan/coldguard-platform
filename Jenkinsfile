// ==============================================================================
// ColdGuard CI/CD Pipeline
// ==============================================================================
//
// Stages:
//   1.  Checkout
//   2.  Backend: Install Dependencies
//   3.  Backend: Lint
//   4.  Backend: Tests  (JUnit XML + coverage)
//   5.  Frontend: Install Dependencies
//   6.  Frontend: Tests (Vitest)
//   7.  Frontend: Build (production bundle)
//   8.  Docker: Build images
//   9.  Docker Compose: Smoke test
//   10. [OPTIONAL] Push to Azure Container Registry
//       Runs only when AZURE_ACR_ENABLED == "true"
//
// LOCAL MODE (default):
//   - All stages run without any cloud credentials.
//   - Stage 10 is skipped.
//
// AZURE MODE:
//   Configure the following Jenkins Credentials and env vars:
//   - Credentials ID "coldguard-acr-credentials" (Username/Password)
//     Username = ACR login server (e.g. coldguardacr.azurecr.io)
//     Password = ACR access token (use Service Principal or Admin password)
//   - Environment variable AZURE_ACR_ENABLED = "true"  (in Jenkins or branch config)
//   - Environment variable AZURE_ACR_REGISTRY (ACR login server, same as above)
//
// Usage:
//   - Set up a Jenkins Pipeline job pointing to this Jenkinsfile.
//   - See docs/jenkins_setup.md for full setup instructions.
// ==============================================================================

pipeline {
    agent any

    // ── Global environment ─────────────────────────────────────────────────────
    environment {
        // Application metadata
        APP_NAME        = 'coldguard'
        IMAGE_BACKEND   = "${APP_NAME}-backend"
        IMAGE_FRONTEND  = "${APP_NAME}-frontend"
        IMAGE_SIMULATOR = "${APP_NAME}-simulator"

        // Python virtualenv path (relative to workspace)
        VENV_DIR = 'backend/.ci-venv'

        // Azure ACR – disabled unless explicitly enabled via Jenkins config
        // Never hard-code registry URLs or credentials here.
        AZURE_ACR_ENABLED  = "${env.AZURE_ACR_ENABLED ?: 'false'}"
        AZURE_ACR_REGISTRY = "${env.AZURE_ACR_REGISTRY ?: ''}"

        // Docker Compose smoke-test container name (unique per build to avoid conflicts)
        SMOKE_PROJECT = "cg_smoke_${env.BUILD_NUMBER}"
    }

    // ── Pipeline-wide options ──────────────────────────────────────────────────
    options {
        timeout(time: 45, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
        disableConcurrentBuilds()
        ansiColor('xterm')
    }

    // ── Stage definitions ──────────────────────────────────────────────────────
    stages {

        // ── Stage 1: Checkout ────────────────────────────────────────────────
        stage('Checkout') {
            steps {
                echo "==> Checking out source: branch=${env.BRANCH_NAME ?: 'unknown'}, commit=${env.GIT_COMMIT?.take(8) ?: 'N/A'}"
                checkout scm
            }
        }

        // ── Stage 2: Backend – Install Dependencies ──────────────────────────
        stage('Backend: Install Dependencies') {
            steps {
                dir('backend') {
                    sh '''
                        echo "==> Creating Python virtual environment..."
                        python3 -m venv ../${VENV_DIR}
                        ../${VENV_DIR}/bin/pip install --upgrade pip --quiet

                        echo "==> Installing backend dependencies..."
                        ../${VENV_DIR}/bin/pip install -r requirements.txt --quiet

                        echo "==> Installing test/lint extras..."
                        ../${VENV_DIR}/bin/pip install \
                            pytest \
                            pytest-cov \
                            pytest-html \
                            ruff \
                            --quiet

                        echo "==> Dependency installation complete."
                        ../${VENV_DIR}/bin/pip list | grep -E "fastapi|sqlalchemy|pytest|ruff|alembic"
                    '''
                }
            }
        }

        // ── Stage 3: Backend – Lint ──────────────────────────────────────────
        stage('Backend: Lint') {
            steps {
                dir('backend') {
                    sh '''
                        echo "==> Running ruff linter on app/ ..."
                        ../${VENV_DIR}/bin/ruff check app/ --output-format=github || {
                            echo "[WARNING] Lint issues found (non-blocking in CI — fix before merging to main)."
                            exit 0
                        }
                        echo "==> Lint passed."
                    '''
                }
            }
        }

        // ── Stage 4: Backend – Tests ─────────────────────────────────────────
        stage('Backend: Tests') {
            steps {
                dir('backend') {
                    sh '''
                        echo "==> Running backend test suite..."
                        ../${VENV_DIR}/bin/pytest tests/ \
                            -v \
                            --tb=short \
                            --junitxml=../reports/backend-tests.xml \
                            --html=../reports/backend-tests.html \
                            --self-contained-html \
                            --cov=app \
                            --cov-report=xml:../reports/backend-coverage.xml \
                            --cov-report=html:../reports/backend-coverage-html \
                            --cov-report=term-missing \
                            -q
                    '''
                }
            }
            post {
                always {
                    // Publish JUnit results
                    junit allowEmptyResults: true,
                          testResults: 'reports/backend-tests.xml'

                    // Publish HTML test report
                    publishHTML(target: [
                        allowMissing:         true,
                        alwaysLinkToLastBuild: true,
                        keepAll:              true,
                        reportDir:            'reports',
                        reportFiles:          'backend-tests.html',
                        reportName:           'Backend Test Report'
                    ])

                    // Publish coverage HTML
                    publishHTML(target: [
                        allowMissing:         true,
                        alwaysLinkToLastBuild: true,
                        keepAll:              true,
                        reportDir:            'reports/backend-coverage-html',
                        reportFiles:          'index.html',
                        reportName:           'Backend Coverage Report'
                    ])
                }
            }
        }

        // ── Stage 5: Frontend – Install Dependencies ─────────────────────────
        stage('Frontend: Install Dependencies') {
            steps {
                dir('frontend') {
                    sh '''
                        echo "==> Installing frontend dependencies..."
                        npm ci --prefer-offline
                        echo "==> Done."
                    '''
                }
            }
        }

        // ── Stage 6: Frontend – Tests ────────────────────────────────────────
        stage('Frontend: Tests') {
            steps {
                dir('frontend') {
                    sh '''
                        echo "==> Running Vitest suite..."
                        npm test -- --reporter=verbose --reporter=junit --outputFile=../reports/frontend-tests.xml
                    '''
                }
            }
            post {
                always {
                    junit allowEmptyResults: true,
                          testResults: 'reports/frontend-tests.xml'
                }
            }
        }

        // ── Stage 7: Frontend – Build ────────────────────────────────────────
        stage('Frontend: Build') {
            steps {
                dir('frontend') {
                    sh '''
                        echo "==> Building production bundle..."
                        npm run build

                        echo "==> Build output:"
                        du -sh dist/
                    '''
                }
            }
            post {
                success {
                    // Archive the production bundle as a build artefact
                    archiveArtifacts artifacts: 'frontend/dist/**',
                                     fingerprint: true,
                                     allowEmptyArchive: true
                }
            }
        }

        // ── Stage 8: Docker – Build Images ───────────────────────────────────
        stage('Docker: Build') {
            steps {
                script {
                    // Compute a unique tag: short git sha  (fallback to build number)
                    def gitSha = sh(
                        script: "git rev-parse --short HEAD 2>/dev/null || echo 'b${BUILD_NUMBER}'",
                        returnStdout: true
                    ).trim()
                    env.GIT_SHA    = gitSha
                    env.IMAGE_TAG  = gitSha
                    env.BUILD_TAG  = "build-${BUILD_NUMBER}"

                    echo "==> Building Docker images (tag: ${env.IMAGE_TAG})"
                }
                sh '''
                    echo "--- Building backend ---"
                    docker build \
                        -t ${IMAGE_BACKEND}:${IMAGE_TAG} \
                        -t ${IMAGE_BACKEND}:latest \
                        ./backend

                    echo "--- Building frontend ---"
                    docker build \
                        -t ${IMAGE_FRONTEND}:${IMAGE_TAG} \
                        -t ${IMAGE_FRONTEND}:latest \
                        ./frontend

                    echo "--- Building simulator ---"
                    docker build \
                        -t ${IMAGE_SIMULATOR}:${IMAGE_TAG} \
                        -t ${IMAGE_SIMULATOR}:latest \
                        ./simulator

                    echo "==> Docker image sizes:"
                    docker images | grep -E "${IMAGE_BACKEND}|${IMAGE_FRONTEND}|${IMAGE_SIMULATOR}"
                '''
            }
        }

        // ── Stage 9: Docker Compose – Smoke Test ─────────────────────────────
        stage('Docker Compose: Smoke Test') {
            steps {
                sh '''
                    echo "==> Starting smoke test stack (project: ${SMOKE_PROJECT})..."
                    docker compose \
                        -p ${SMOKE_PROJECT} \
                        up -d --no-build \
                        postgres backend

                    echo "==> Waiting for backend to become healthy (up to 60 s)..."
                    for i in $(seq 1 12); do
                        STATUS=$(docker inspect --format="{{.State.Health.Status}}" ${SMOKE_PROJECT}-backend-1 2>/dev/null || echo "starting")
                        echo "  attempt ${i}/12 → ${STATUS}"
                        if [ "${STATUS}" = "healthy" ]; then
                            echo "==> Backend is healthy."
                            break
                        fi
                        sleep 5
                    done

                    echo "==> Hitting /health endpoint..."
                    docker run --rm \
                        --network ${SMOKE_PROJECT}_default \
                        curlimages/curl:8.5.0 \
                        curl -sf http://${SMOKE_PROJECT}-backend-1:8000/health

                    echo "==> Smoke test passed."
                '''
            }
            post {
                always {
                    sh '''
                        echo "==> Tearing down smoke test stack..."
                        docker compose -p ${SMOKE_PROJECT} down -v --remove-orphans 2>/dev/null || true
                        echo "==> Cleanup done."
                    '''
                }
            }
        }

        // ── Stage 10: Push to Azure Container Registry (OPTIONAL) ────────────
        // Disabled unless AZURE_ACR_ENABLED == "true"
        // Configure via Jenkins Credentials ID: coldguard-acr-credentials
        //   Username = ACR login server  (e.g. coldguardacr.azurecr.io)
        //   Password = ACR access token or Service Principal secret
        stage('ACR: Push Images') {
            when {
                environment name: 'AZURE_ACR_ENABLED', value: 'true'
            }
            steps {
                withCredentials([
                    usernamePassword(
                        credentialsId: 'coldguard-acr-credentials',
                        usernameVariable: 'ACR_SERVER',
                        passwordVariable: 'ACR_TOKEN'
                    )
                ]) {
                    sh '''
                        echo "==> Logging in to Azure Container Registry: ${ACR_SERVER}"
                        echo "${ACR_TOKEN}" | docker login "${ACR_SERVER}" \
                            --username "00000000-0000-0000-0000-000000000000" \
                            --password-stdin

                        echo "==> Tagging images for ACR..."
                        docker tag ${IMAGE_BACKEND}:${IMAGE_TAG}   ${ACR_SERVER}/${IMAGE_BACKEND}:${IMAGE_TAG}
                        docker tag ${IMAGE_BACKEND}:latest         ${ACR_SERVER}/${IMAGE_BACKEND}:latest
                        docker tag ${IMAGE_FRONTEND}:${IMAGE_TAG}  ${ACR_SERVER}/${IMAGE_FRONTEND}:${IMAGE_TAG}
                        docker tag ${IMAGE_FRONTEND}:latest        ${ACR_SERVER}/${IMAGE_FRONTEND}:latest
                        docker tag ${IMAGE_SIMULATOR}:${IMAGE_TAG} ${ACR_SERVER}/${IMAGE_SIMULATOR}:${IMAGE_TAG}
                        docker tag ${IMAGE_SIMULATOR}:latest       ${ACR_SERVER}/${IMAGE_SIMULATOR}:latest

                        echo "==> Pushing images..."
                        docker push ${ACR_SERVER}/${IMAGE_BACKEND}:${IMAGE_TAG}
                        docker push ${ACR_SERVER}/${IMAGE_BACKEND}:latest
                        docker push ${ACR_SERVER}/${IMAGE_FRONTEND}:${IMAGE_TAG}
                        docker push ${ACR_SERVER}/${IMAGE_FRONTEND}:latest
                        docker push ${ACR_SERVER}/${IMAGE_SIMULATOR}:${IMAGE_TAG}
                        docker push ${ACR_SERVER}/${IMAGE_SIMULATOR}:latest

                        echo "==> All images pushed to ${ACR_SERVER}."
                        docker logout "${ACR_SERVER}"
                    '''
                }
            }
        }
    }

    // ── Post-pipeline actions ──────────────────────────────────────────────────
    post {
        always {
            echo "==> Pipeline complete: ${currentBuild.currentResult}"

            // Clean up dangling Docker images to prevent disk fill-up on agents
            sh '''
                docker image prune -f --filter "until=24h" 2>/dev/null || true
            '''
        }
        success {
            echo "==> BUILD SUCCESS — ${APP_NAME} @ ${env.IMAGE_TAG ?: 'unknown'}"
        }
        failure {
            echo "==> BUILD FAILED — review stage logs above."
        }
        unstable {
            echo "==> BUILD UNSTABLE — some tests may have failed. Check test reports."
        }
    }
}
