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
                    docker run --rm -v "$WORKSPACE":/src:ro python:3.13-slim sh -ec '
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
