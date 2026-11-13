// ==============================================================================
// ColdGuard CI/CD pipeline
// ==============================================================================
// Every stage is a thin wrapper around scripts/ci/*.sh, so the pipeline can be reproduced
// locally with `scripts/ci/run-all.sh` (see docs/jenkins_setup.md).
//
//   1. Checkout
//   2. Build & test (parallel)      backend lint + pytest | frontend lint + vitest + build
//   3. Config consistency           compose <-> k8s copies, compose render, kustomize + kubeconform
//   4. Security scan                tracked secrets, literal secrets in manifests, bundle, deps
//   5. Docker images                coldguard-{backend,frontend,simulator}:{2.0.0,<git-sha>}
//   6. Compose smoke test           full stack, throw-away secrets, end-to-end checks
//   7. Kubernetes deploy (kind)     local cluster: ingress-nginx, metrics-server, kustomize overlay
//   8. Kubernetes smoke test        ingress, RBAC, MQTT, Prometheus/Grafana, HPA, NetworkPolicy,
//                                   zero-downtime rollout, self-healing, persistence
//   9. Push images                  [PUSH_IMAGES]        registry credentials from Jenkins
//  10. Deploy production            [DEPLOY_PRODUCTION]  manual approval + kubeconfig credential
//
// Agent requirements: bash, git, python3, node 20+, docker (with compose v2), kubectl, kind.
// No credentials are needed for stages 1-8; they never leave the agent.
// ==============================================================================

pipeline {
    agent any

    parameters {
        booleanParam(name: 'RUN_COMPOSE_SMOKE', defaultValue: true,  description: 'Bring up the full Docker Compose stack and run end-to-end checks')
        booleanParam(name: 'DEPLOY_LOCAL_K8S',  defaultValue: true,  description: 'Deploy to a local kind cluster and run the Kubernetes smoke test')
        booleanParam(name: 'TEARDOWN_KIND',     defaultValue: false, description: 'Delete the kind cluster after the Kubernetes smoke test')
        booleanParam(name: 'PUSH_IMAGES',       defaultValue: false, description: 'Push images to REGISTRY (credentials: coldguard-registry)')
        booleanParam(name: 'DEPLOY_PRODUCTION', defaultValue: false, description: 'Deploy the production overlay (credentials: coldguard-prod-kubeconfig)')
        choice(name: 'INGRESS_CONTROLLER', choices: ['nginx', 'traefik'], description: 'Ingress controller for the kind cluster (traefik if registry.k8s.io is unreachable)')
        string(name: 'REGISTRY',     defaultValue: '', description: 'e.g. coldguardacr.azurecr.io/coldguard')
        string(name: 'PROD_CONTEXT', defaultValue: '', description: 'kube context name inside the production kubeconfig')
    }

    environment {
        APP_VERSION  = '2.0.0'
        CI           = 'true'
        REPORTS_DIR  = "${WORKSPACE}/reports"
        KUBE_CONTEXT = 'kind-coldguard'
        SMOKE_PROJECT = "cg-smoke-${BUILD_NUMBER}"
        UI_PORT      = '18080'           // Jenkins itself usually owns 8080
    }

    options {
        timeout(time: 90, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
        disableConcurrentBuilds()        // compose host ports and the kind cluster are shared
        timestamps()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                script {
                    env.IMAGE_TAG = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()
                }
                echo "==> ${env.BRANCH_NAME ?: 'detached'} @ ${env.IMAGE_TAG}"
            }
        }

        stage('Build & test') {
            parallel {
                stage('Backend') {
                    steps { sh 'bash scripts/ci/backend.sh' }
                    post { always { junit allowEmptyResults: true, testResults: 'reports/backend-tests.xml' } }
                }
                stage('Frontend') {
                    steps { sh 'bash scripts/ci/frontend.sh' }
                    post {
                        always  { junit allowEmptyResults: true, testResults: 'reports/frontend-tests.xml' }
                        success { archiveArtifacts artifacts: 'frontend/dist/**', fingerprint: true, allowEmptyArchive: true }
                    }
                }
            }
        }

        stage('Config consistency') {
            steps { sh 'bash scripts/ci/config-check.sh' }
        }

        stage('Security scan') {
            steps { sh 'bash scripts/ci/security-scan.sh' }
        }

        stage('Docker images') {
            steps { sh 'bash scripts/ci/build-images.sh' }
        }

        stage('Compose smoke test') {
            when { expression { params.RUN_COMPOSE_SMOKE } }
            steps { sh 'NO_BUILD=1 bash scripts/ci/compose-smoke.sh' }
        }

        stage('Kubernetes deploy (kind)') {
            when { expression { params.DEPLOY_LOCAL_K8S } }
            steps { sh "INGRESS_CONTROLLER=${params.INGRESS_CONTROLLER} bash scripts/ci/k8s-deploy.sh" }
        }

        stage('Kubernetes smoke test') {
            when { expression { params.DEPLOY_LOCAL_K8S } }
            steps { sh 'bash scripts/ci/k8s-smoke.sh' }
            post {
                failure {
                    sh '''
                        kubectl --context "$KUBE_CONTEXT" -n coldguard get pods -o wide || true
                        kubectl --context "$KUBE_CONTEXT" -n coldguard get events --sort-by=.lastTimestamp | tail -n 40 || true
                        kubectl --context "$KUBE_CONTEXT" -n coldguard logs deploy/backend --tail=80 || true
                    '''
                }
                always {
                    script {
                        if (params.TEARDOWN_KIND) { sh 'kind delete cluster --name coldguard || true' }
                    }
                }
            }
        }

        stage('Push images') {
            when { expression { params.PUSH_IMAGES && params.REGISTRY?.trim() } }
            steps {
                withCredentials([usernamePassword(credentialsId: 'coldguard-registry',
                                                  usernameVariable: 'REG_USER', passwordVariable: 'REG_PASS')]) {
                    sh '''
                        echo "$REG_PASS" | docker login "${REGISTRY%%/*}" -u "$REG_USER" --password-stdin
                        REGISTRY="$REGISTRY" bash scripts/ci/k8s-release.sh push
                        docker logout "${REGISTRY%%/*}"
                    '''
                }
            }
        }

        stage('Deploy production') {
            when { expression { params.DEPLOY_PRODUCTION && params.REGISTRY?.trim() && params.PROD_CONTEXT?.trim() } }
            steps {
                input message: "Deploy ${env.IMAGE_TAG} to production?", ok: 'Deploy'
                withCredentials([file(credentialsId: 'coldguard-prod-kubeconfig', variable: 'KUBECONFIG')]) {
                    sh 'REGISTRY="$REGISTRY" KUBE_CONTEXT="$PROD_CONTEXT" ALLOW_REMOTE_CONTEXT=1 bash scripts/ci/k8s-release.sh deploy'
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true
            sh 'docker image prune -f --filter "until=24h" >/dev/null 2>&1 || true'
        }
        success { echo "==> BUILD SUCCESS — coldguard ${env.IMAGE_TAG}" }
        failure { echo '==> BUILD FAILED — see the stage logs and archived reports/' }
    }
}
