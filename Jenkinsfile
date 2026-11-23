pipeline {
    agent { label 'rootless-docker' }
    options {
        disableConcurrentBuilds()
        timeout(time: 30, unit: 'MINUTES')
    }
    triggers { pollSCM('H/5 * * * *') }

    stages {
        stage('Test') {
            steps {
                sh '''
                    set -eu
                    NET="statlab-test-$BUILD_NUMBER"
                    DB="statlab-test-db-$BUILD_NUMBER"
                    cleanup() {
                        docker rm -f -v "$DB" >/dev/null 2>&1 || true
                        docker network rm "$NET" >/dev/null 2>&1 || true
                    }
                    trap cleanup EXIT

                    docker network create "$NET"
                    docker run -d --name "$DB" --network "$NET" \
                        -e POSTGRES_DB=statlab -e POSTGRES_USER=statlab \
                        -e POSTGRES_PASSWORD=test-only postgres:16

                    for i in $(seq 1 30); do
                        docker exec "$DB" pg_isready -h 127.0.0.1 -U statlab -d statlab && break
                        sleep 2
                    done
                    docker exec "$DB" pg_isready -h 127.0.0.1 -U statlab -d statlab

                    docker run --rm --network "$NET" \
                        -e DATABASE_URL="postgresql://statlab:test-only@$DB:5432/statlab" \
                        -v "$WORKSPACE":/src:ro python:3.13-slim sh -ec '
                            cp -r /src /tmp/app
                            cd /tmp/app
                            pip install -q -r requirements-dev.txt
                            python -m ruff check .
                            python -m unittest discover -v
                        '
                '''
            }
        }
        stage('Build and Deploy') {
            steps {
                sh 'python3 scripts/prepare_ubuntu.py'
                withCredentials([file(credentialsId: 'statlab-env', variable: 'ENV_FILE')]) {
                    dir('ubuntu-deploy') {
                        sh '''
                            docker compose --env-file "$ENV_FILE" build
                            docker compose --env-file "$ENV_FILE" up -d --wait --wait-timeout 300
                            docker compose --env-file "$ENV_FILE" restart frontend
                            docker compose --env-file "$ENV_FILE" ps
                        '''
                    }
                }
            }
        }
        stage('Health Check') {
            steps {
                sh 'curl --fail --retry 10 --retry-delay 2 --retry-all-errors http://10.50.80.96:8080/api/health'
            }
        }
    }
    post {
        success { echo 'StatLab deployed: http://10.50.80.96:8080' }
        failure { echo 'Pipeline failed. Check Console Output.' }
    }
}
