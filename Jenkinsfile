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
                bat 'pytest --junitxml=html-reports/pytest_report.xml --html=html-reports/report.html'
            }
        }
        stage('Archive reports') {
            steps {
                junit 'html-reports/pytest_report.xml'
                archiveArtifacts artifacts: 'html-reports/pytest_report.xml', allowEmptyArchive: true
            }
        }
    }
    post {
        always {
            // Archive the XML report for reference
            archiveArtifacts artifacts: 'html-reports/pytest_report.xml', allowEmptyArchive: true

            // Publish the HTML report (make sure pytest generates it)
            publishHTML([
                reportDir: 'html-reports',
                reportFiles: 'report.html',
                reportName: 'Test Report',
                keepAll: true,
                alwaysLinkToLastBuild: true,
                allowMissing: true
            ])
        }
    }
}