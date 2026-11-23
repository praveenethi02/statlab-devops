pipeline {
    agent { label 'statlab-linux' }
    options {
        disableConcurrentBuilds()
        timestamps()
    }
    parameters {
        booleanParam(name: 'DEPLOY_AZURE', defaultValue: false, description: 'Release main to the configured Azure environment')
    }
    stages {
        stage('Test') {
            steps {
                sh '''
                    set -eu
                    python3 -m venv .venv
                    .venv/bin/pip install -r requirements-dev.txt
                    export POSTGRES_PASSWORD=$(openssl rand -hex 32)
                    db_container=statlab-test-db-$BUILD_NUMBER
                    docker run --rm --detach --name "$db_container" \
                        --health-cmd 'pg_isready -U statlab -d statlab' \
                        --health-interval 2s --health-timeout 3s --health-retries 30 \
                        --env POSTGRES_USER=statlab --env POSTGRES_PASSWORD \
                        --env POSTGRES_DB=statlab --publish 127.0.0.1::5432 postgres:16
                    trap 'docker stop "$db_container" >/dev/null 2>&1 || true' EXIT
                    for attempt in $(seq 1 60); do
                        status=$(docker inspect --format='{{.State.Health.Status}}' "$db_container")
                        if [ "$status" = healthy ]; then break; fi
                        if [ "$status" = unhealthy ]; then
                            docker logs "$db_container"
                            exit 1
                        fi
                        sleep 2
                    done
                    if [ "$status" != healthy ]; then
                        docker logs "$db_container"
                        exit 1
                    fi
                    mapped_port=$(docker port "$db_container" 5432/tcp)
                    mapped_port=${mapped_port##*:}
                    export DATABASE_URL="postgresql://statlab:$POSTGRES_PASSWORD@127.0.0.1:$mapped_port/statlab"
                    .venv/bin/python -m unittest discover -v
                    mkdir -p .runtime
                    .venv/bin/python scripts/browser_test.py
                    npm run check
                    terraform -chdir=infra/terraform init -backend=false -input=false
                    terraform -chdir=infra/terraform validate
                    ansible-playbook -i localhost, infra/ansible/deploy.yml --syntax-check
                '''
            }
        }
        stage('Build and verify three tiers') {
            steps {
                script {
                    env.RELEASE_TAG = sh(script: 'git rev-parse HEAD', returnStdout: true).trim() + "-" + env.BUILD_NUMBER
                    env.COMPOSE_PROJECT_NAME = "statlab-ci-" + sh(script: 'printf %s "$BUILD_TAG" | sha256sum | cut -c1-12', returnStdout: true).trim()
                }
                sh '''
                    set -eu
                    python3 scripts/prepare_ubuntu.py
                    export COMPOSE_FILE=ubuntu-deploy/compose.yaml
                    export STATLAB_BACKEND_IMAGE=statlab-backend:$RELEASE_TAG STATLAB_FRONTEND_IMAGE=statlab-frontend:$RELEASE_TAG
                    export APP_SECRET=$(openssl rand -hex 32) POSTGRES_PASSWORD=$(openssl rand -hex 32)
                    export BIND_ADDRESS=127.0.0.1 HTTP_PORT=0
                    trap 'docker compose down --volumes' EXIT
                    docker compose build
                    docker compose up -d --wait --wait-timeout 180
                    endpoint=http://$(docker compose port frontend 80)
                    curl -fsS "$endpoint/" >/dev/null
                    python3 scripts/check_stack.py "$endpoint"
                '''
            }
        }
        stage('Release to Azure') {
            when { allOf { branch 'main'; expression { params.DEPLOY_AZURE } } }
            steps {
                withCredentials([string(credentialsId: 'statlab-db-password', variable: 'TF_VAR_database_password'),
                                 string(credentialsId: 'statlab-app-secret', variable: 'TF_VAR_app_secret')]) {
                    sh '''
                        set -eu
                        export AZURE_CONFIG_DIR=$(mktemp -d) DOCKER_CONFIG=$(mktemp -d)
                        plan_dir=$(mktemp -d)
                        trap 'rm -rf "$AZURE_CONFIG_DIR" "$DOCKER_CONFIG" "$plan_dir"' EXIT
                        az login --identity --output none
                        az account set --subscription "$ARM_SUBSCRIPTION_ID"
                        export ARM_USE_MSI=true ARM_USE_AZUREAD=true TF_VAR_image_tag=$RELEASE_TAG
                        REGISTRY_HOST=$(az acr show -n "$TF_VAR_registry_name" -g "$TF_VAR_registry_resource_group" --query loginServer -o tsv)
                        export REGISTRY_HOST
                        az acr login --name "$TF_VAR_registry_name"
                        for tier in backend frontend; do
                            docker tag "statlab-$tier:$RELEASE_TAG" "$REGISTRY_HOST/statlab-$tier:$RELEASE_TAG"
                            docker push "$REGISTRY_HOST/statlab-$tier:$RELEASE_TAG"
                        done
                        terraform -chdir=infra/terraform init -reconfigure -input=false \
                            -backend-config="resource_group_name=$STATE_RESOURCE_GROUP" \
                            -backend-config="storage_account_name=$STATE_STORAGE_ACCOUNT" \
                            -backend-config="container_name=$STATE_CONTAINER" \
                            -backend-config="key=$TF_VAR_prefix.tfstate"
                        terraform -chdir=infra/terraform plan -input=false -out="$plan_dir/release.tfplan"
                        terraform -chdir=infra/terraform apply -input=false "$plan_dir/release.tfplan"
                        STATLAB_RESOURCE_GROUP=$(terraform -chdir=infra/terraform output -raw resource_group)
                        STATLAB_URL=$(terraform -chdir=infra/terraform output -raw frontend_url)
                        export STATLAB_RESOURCE_GROUP STATLAB_URL
                        ansible-playbook -i localhost, infra/ansible/deploy.yml
                    '''
                }
            }
        }
    }
}
