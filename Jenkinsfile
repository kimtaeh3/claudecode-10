pipeline { 
    environment { 
        //registry = "192.168.101.190:9011" 
    	registry = "" 
        imagePath = "rampraga/q360auto"
        //registryCredential = 'JFrogJenkinsUserCreds'
    	registryCredential = 'JenkinsDockerHubPAT'
        dockerImage = '' 
		dockerImageLatest = '' 
		
    }
    agent any
    stages { 
        stage('Cloning our Git') { 
            steps { 
                script {
					echo BRANCH_NAME
                    def dockerHome = tool 'myDocker'
                    env.PATH = "${dockerHome}/bin:${env.PATH}"
                }
                git credentialsId: 'rampragadeesh-github-pat', url: 'https://github.com/GenesysCloud-Connex/q360auto.git', branch: '$BRANCH_NAME'
            }
        } 
        stage('Building our image and pushing it to container registry') { 
            steps { 
                script { 
                    sh """
                    docker login -u rampraga -p $DOCKER_PAT
                    """
                    dockerImage = docker.build "$imagePath:$BUILD_NUMBER" 
					dockerImageLatest = docker.build "$imagePath:latest" 
					dockerImage.push() 
					dockerImageLatest.push() 
                }
            } 
        }
        stage('Deploy our image') { 
            steps { 
                script { 
                    echo "push to portainer later"
                        
                    
                } 
            }
        } 
        stage('Cleaning up') { 
            steps { 
                sh "docker rmi $imagePath:$BUILD_NUMBER" 
				sh "docker rmi $imagePath:latest" 
            }
        } 
    }
}
