#!/bin/bash

# DataFlow Deployment Script
# Supports Docker Compose and Kubernetes deployments

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
DEPLOYMENT_TYPE="docker"
ENVIRONMENT="production"
NAMESPACE="dataflow"
REGISTRY=""
VERSION="latest"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--type)
            DEPLOYMENT_TYPE="$2"
            shift 2
            ;;
        -e|--env)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -r|--registry)
            REGISTRY="$2"
            shift 2
            ;;
        -v|--version)
            VERSION="$2"
            shift 2
            ;;
        -h|--help)
            echo "DataFlow Deployment Script"
            echo ""
            echo "Usage: ./deploy.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -t, --type       Deployment type (docker|kubernetes) [default: docker]"
            echo "  -e, --env        Environment (development|staging|production) [default: production]"
            echo "  -n, --namespace  Kubernetes namespace [default: dataflow]"
            echo "  -r, --registry   Docker registry URL"
            echo "  -v, --version    Application version [default: latest]"
            echo "  -h, --help       Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Function to check prerequisites
check_prerequisites() {
    echo "Checking prerequisites..."

    if [[ "$DEPLOYMENT_TYPE" == "docker" ]]; then
        if ! command -v docker &> /dev/null; then
            echo -e "${RED}Docker is not installed${NC}"
            exit 1
        fi

        if ! command -v docker-compose &> /dev/null; then
            echo -e "${RED}Docker Compose is not installed${NC}"
            exit 1
        fi
    elif [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        if ! command -v kubectl &> /dev/null; then
            echo -e "${RED}kubectl is not installed${NC}"
            exit 1
        fi

        # Check kubernetes connection
        if ! kubectl cluster-info &> /dev/null; then
            echo -e "${RED}Cannot connect to Kubernetes cluster${NC}"
            exit 1
        fi
    fi

    echo -e "${GREEN}Prerequisites check passed${NC}"
}

# Function to build Docker image
build_docker_image() {
    echo "Building Docker image..."

    IMAGE_NAME="kailash-dataflow"
    if [[ -n "$REGISTRY" ]]; then
        IMAGE_NAME="$REGISTRY/$IMAGE_NAME"
    fi

    docker build -t "$IMAGE_NAME:$VERSION" -f deployment/docker/Dockerfile .

    if [[ -n "$REGISTRY" ]]; then
        echo "Pushing image to registry..."
        docker push "$IMAGE_NAME:$VERSION"
    fi

    echo -e "${GREEN}Docker image built successfully${NC}"
}

# Function to deploy with Docker Compose
deploy_docker() {
    echo "Deploying with Docker Compose..."

    cd deployment/docker

    # Create .env file if it doesn't exist
    if [[ ! -f .env ]]; then
        cat > .env <<EOF
# DataFlow Environment Configuration
ENVIRONMENT=$ENVIRONMENT
SECRET_KEY=$(openssl rand -base64 32)
DATABASE_URL=postgresql://dataflow:dataflow123@postgres:5432/dataflow_db
REDIS_URL=redis://redis:6379/0
EOF
        echo "Created .env file with default configuration"
    fi

    # Stop existing containers if any
    docker-compose down

    # Start services
    docker-compose up -d

    # Wait for services to be healthy
    echo "Waiting for services to be healthy..."
    sleep 10

    # Check service health
    if docker-compose ps | grep -q "unhealthy"; then
        echo -e "${RED}Some services are unhealthy${NC}"
        docker-compose ps
        exit 1
    fi

    echo -e "${GREEN}Docker deployment successful${NC}"
    echo ""
    echo "Services:"
    echo "  - DataFlow API: http://localhost:8000"
    echo "  - PostgreSQL: localhost:5434"
    echo "  - Redis: localhost:6380"
    echo "  - Prometheus: http://localhost:9090"
    echo "  - Grafana: http://localhost:3000 (admin/admin)"
    echo "  - pgAdmin: http://localhost:5050 (admin@dataflow.local/admin123)"
}

# Function to deploy to Kubernetes
deploy_kubernetes() {
    echo "Deploying to Kubernetes..."

    # Create namespace if it doesn't exist
    kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

    # Update image in deployment if registry is specified
    if [[ -n "$REGISTRY" ]]; then
        sed -i "s|image: kailash-dataflow:.*|image: $REGISTRY/kailash-dataflow:$VERSION|g" \
            deployment/kubernetes/dataflow-deployment.yaml
    fi

    # Apply configurations
    echo "Applying Kubernetes configurations..."
    kubectl apply -f deployment/kubernetes/postgres-deployment.yaml -n $NAMESPACE
    kubectl apply -f deployment/kubernetes/redis-deployment.yaml -n $NAMESPACE

    # Wait for database to be ready
    echo "Waiting for database to be ready..."
    kubectl wait --for=condition=ready pod -l app=postgres -n $NAMESPACE --timeout=300s
    kubectl wait --for=condition=ready pod -l app=redis -n $NAMESPACE --timeout=300s

    # Apply application deployment
    kubectl apply -f deployment/kubernetes/dataflow-deployment.yaml -n $NAMESPACE

    # Wait for application to be ready
    echo "Waiting for application to be ready..."
    kubectl wait --for=condition=ready pod -l app=dataflow -n $NAMESPACE --timeout=300s

    echo -e "${GREEN}Kubernetes deployment successful${NC}"
    echo ""
    echo "Deployment status:"
    kubectl get all -n $NAMESPACE
    echo ""
    echo "To access the application:"
    echo "  kubectl port-forward -n $NAMESPACE service/dataflow-service 8000:80"
}

# Function to run database migrations
run_migrations() {
    echo "Running database migrations..."

    if [[ "$DEPLOYMENT_TYPE" == "docker" ]]; then
        docker-compose exec dataflow python -m kailash_dataflow.migrations upgrade head
    elif [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        POD_NAME=$(kubectl get pods -n $NAMESPACE -l app=dataflow -o jsonpath="{.items[0].metadata.name}")
        kubectl exec -n $NAMESPACE $POD_NAME -- python -m kailash_dataflow.migrations upgrade head
    fi

    echo -e "${GREEN}Migrations completed${NC}"
}

# Function to run health checks
health_check() {
    echo "Running health checks..."

    if [[ "$DEPLOYMENT_TYPE" == "docker" ]]; then
        HEALTH_URL="http://localhost:8000/health"
    elif [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        # Use port-forward for health check
        kubectl port-forward -n $NAMESPACE service/dataflow-service 8001:80 &
        PF_PID=$!
        sleep 5
        HEALTH_URL="http://localhost:8001/health"
    fi

    # Check health endpoint
    if curl -f -s "$HEALTH_URL" > /dev/null; then
        echo -e "${GREEN}Health check passed${NC}"
    else
        echo -e "${RED}Health check failed${NC}"

        # Cleanup port-forward if kubernetes
        if [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
            kill $PF_PID 2>/dev/null
        fi

        exit 1
    fi

    # Cleanup port-forward if kubernetes
    if [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        kill $PF_PID 2>/dev/null
    fi
}

# Main deployment flow
main() {
    echo -e "${YELLOW}DataFlow Deployment${NC}"
    echo "===================="
    echo "Type: $DEPLOYMENT_TYPE"
    echo "Environment: $ENVIRONMENT"
    echo "Version: $VERSION"
    echo ""

    # Check prerequisites
    check_prerequisites

    # Build Docker image
    build_docker_image

    # Deploy based on type
    if [[ "$DEPLOYMENT_TYPE" == "docker" ]]; then
        deploy_docker
    elif [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        deploy_kubernetes
    else
        echo -e "${RED}Unknown deployment type: $DEPLOYMENT_TYPE${NC}"
        exit 1
    fi

    # Run migrations
    echo ""
    read -p "Run database migrations? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        run_migrations
    fi

    # Run health check
    echo ""
    health_check

    echo ""
    echo -e "${GREEN}Deployment completed successfully!${NC}"
}

# Run main function
main
