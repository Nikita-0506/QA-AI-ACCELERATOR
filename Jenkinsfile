pipeline {
    agent any
    stages {
        stage('Install dependencies') {
            steps {
                bat 'pip install -r requirements.txt'
            }
        }
        stage('Run tests') {
            steps {
                bat 'pytest --maxfail=1 --disable-warnings --junitxml=reports\\results.xml'
            }
        }
        stage('Archive reports') {
            steps {
                junit 'reports/results.xml'
                archiveArtifacts artifacts: 'reports/results.xml', allowEmptyArchive: true
            }
        }
    }
}