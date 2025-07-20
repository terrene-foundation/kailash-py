#!/bin/bash

# Multi-App Deployment Script for Kailash Platform
# Supports both Docker and Kubernetes deployments with dynamic app discovery

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOYMENT_DIR="$PROJECT_ROOT/deployment"

# Default values
MODE="docker"
ENVIRONMENT="development"
DRY_RUN=false
FORCE=false
APPS=""

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}==== $1 ====${NC}"
}

# Function to show usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Deploy multi-app Kailash platform with dynamic app discovery

OPTIONS:
    -m, --mode          Deployment mode: docker, kubernetes, both (default: docker)
    -e, --environment   Environment: development, staging, production (default: development)
    -a, --apps          Comma-separated list of specific apps to deploy (default: all)
    -d, --dry-run       Generate configurations without deploying
    -f, --force         Force deployment even if services are running
    -h, --help          Show this help message

EXAMPLES:
    $0                                      # Deploy all apps with Docker (development)
    $0 -m kubernetes -e production          # Deploy to Kubernetes (production)
    $0 -a user-management,analytics         # Deploy specific apps only
    $0 -d                                   # Dry run (generate configs only)
    $0 -m both -f                          # Deploy with both Docker and Kubernetes, force

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -m|--mode)
            MODE="$2"
            shift 2
            ;;
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -a|--apps)
            APPS="$2"
            shift 2
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Validate mode
case $MODE in
    docker|kubernetes|both)
        ;;
    *)
        print_error "Invalid mode: $MODE. Must be docker, kubernetes, or both"
        exit 1
        ;;
esac

# Function to check prerequisites
check_prerequisites() {
    print_header "Checking Prerequisites"
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is required but not installed"
        exit 1
    fi
    
    # Check Docker if needed
    if [[ "$MODE" == "docker" || "$MODE" == "both" ]]; then
        if ! command -v docker &> /dev/null; then
            print_error "Docker is required but not installed"
            exit 1
        fi
        
        if ! command -v docker-compose &> /dev/null; then
            print_error "Docker Compose is required but not installed"
            exit 1
        fi
        
        # Check if Docker is running
        if ! docker info &> /dev/null; then
            print_error "Docker is not running"
            exit 1
        fi
    fi
    
    # Check Kubernetes if needed
    if [[ "$MODE" == "kubernetes" || "$MODE" == "both" ]]; then
        if ! command -v kubectl &> /dev/null; then
            print_error "kubectl is required but not installed"
            exit 1
        fi
        
        # Check if kubectl can connect to cluster
        if ! kubectl cluster-info &> /dev/null; then
            print_error "Cannot connect to Kubernetes cluster"
            exit 1
        fi
    fi
    
    print_status "Prerequisites check passed"
}

# Function to discover apps
discover_apps() {
    print_header "Discovering Applications"
    
    cd "$PROJECT_ROOT"
    
    if [[ -n "$APPS" ]]; then
        print_status "Deploying specific apps: $APPS"
    else
        print_status "Discovering all available apps..."
        
        # Find all app directories with manifest.yaml
        local discovered_apps=""
        for app_dir in apps/*/; do
            if [[ -d "$app_dir" && ! "$app_dir" =~ _template ]]; then
                app_name=$(basename "$app_dir")
                if [[ -f "$app_dir/manifest.yaml" ]]; then
                    discovered_apps="$discovered_apps,$app_name"
                    print_status "Found app: $app_name"
                fi
            fi
        done
        
        APPS="${discovered_apps#,}"  # Remove leading comma
    fi
    
    if [[ -z "$APPS" ]]; then
        print_warning "No deployable apps found"
        return 1
    fi
    
    print_status "Apps to deploy: $APPS"
}

# Function to deploy with Docker
deploy_docker() {
    print_header "Docker Deployment"
    
    cd "$DEPLOYMENT_DIR/docker"
    
    # Generate dynamic configuration
    print_status "Generating Docker configurations..."
    python3 ../scripts/deploy-apps.py --mode docker \
        ${DRY_RUN:+--dry-run} \
        --output-dir "$DEPLOYMENT_DIR"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        print_status "Dry run complete - configurations generated"
        return 0
    fi
    
    # Set environment variables
    export ENVIRONMENT="$ENVIRONMENT"
    export LOG_LEVEL="${LOG_LEVEL:-INFO}"
    
    # Stop existing services if force is enabled
    if [[ "$FORCE" == "true" ]]; then
        print_status "Stopping existing services..."
        docker-compose -f docker-compose.generated.yml down || true
    fi
    
    # Build and start services
    print_status "Building and starting services..."
    docker-compose -f docker-compose.generated.yml up -d --build
    
    # Wait for services to be healthy
    print_status "Waiting for services to be healthy..."
    sleep 10
    
    # Check service status
    print_status "Checking service status..."
    docker-compose -f docker-compose.generated.yml ps
    
    print_status "Docker deployment complete"
}

# Function to deploy with Kubernetes
deploy_kubernetes() {
    print_header "Kubernetes Deployment"
    
    cd "$DEPLOYMENT_DIR"
    
    # Generate dynamic configuration
    print_status "Generating Kubernetes configurations..."
    python3 scripts/deploy-apps.py --mode kubernetes \
        ${DRY_RUN:+--dry-run} \
        --output-dir "$DEPLOYMENT_DIR"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        print_status "Dry run complete - configurations generated"
        return 0
    fi
    
    # Deploy infrastructure first
    print_status "Deploying infrastructure..."
    kubectl apply -f kubernetes/infrastructure/
    
    # Wait for infrastructure to be ready
    print_status "Waiting for infrastructure to be ready..."
    kubectl wait --for=condition=ready pod -l component=database -n kailash-platform --timeout=300s
    kubectl wait --for=condition=ready pod -l component=cache -n kailash-platform --timeout=300s
    
    # Deploy applications
    print_status "Deploying applications..."
    kubectl apply -f kubernetes/apps/ --recursive
    
    # Wait for applications to be ready
    print_status "Waiting for applications to be ready..."
    kubectl wait --for=condition=ready pod -l component=application -n kailash-platform --timeout=300s
    
    # Show deployment status
    print_status "Checking deployment status..."
    kubectl get all -n kailash-platform
    
    print_status "Kubernetes deployment complete"
}

# Function to show deployment status
show_status() {
    print_header "Deployment Status"
    
    if [[ "$MODE" == "docker" || "$MODE" == "both" ]]; then
        print_status "Docker Services:"
        cd "$DEPLOYMENT_DIR/docker"
        if [[ -f "docker-compose.generated.yml" ]]; then
            docker-compose -f docker-compose.generated.yml ps
        else
            print_warning "No Docker deployment found"
        fi
    fi
    
    if [[ "$MODE" == "kubernetes" || "$MODE" == "both" ]]; then
        print_status "Kubernetes Services:"
        if kubectl get namespace kailash-platform &> /dev/null; then
            kubectl get all -n kailash-platform
        else
            print_warning "No Kubernetes deployment found"
        fi
    fi
}

# Function to clean up deployment
cleanup() {
    print_header "Cleaning Up Deployment"
    
    if [[ "$MODE" == "docker" || "$MODE" == "both" ]]; then
        cd "$DEPLOYMENT_DIR/docker"
        if [[ -f "docker-compose.generated.yml" ]]; then
            print_status "Stopping Docker services..."
            docker-compose -f docker-compose.generated.yml down -v
        fi
    fi
    
    if [[ "$MODE" == "kubernetes" || "$MODE" == "both" ]]; then
        if kubectl get namespace kailash-platform &> /dev/null; then
            print_status "Deleting Kubernetes resources..."
            kubectl delete namespace kailash-platform
        fi
    fi
    
    print_status "Cleanup complete"
}

# Main execution
main() {
    print_header "Kailash Platform Multi-App Deployment"
    print_status "Mode: $MODE"
    print_status "Environment: $ENVIRONMENT"
    print_status "Dry Run: $DRY_RUN"
    
    # Check if this is a cleanup request
    if [[ "${1:-}" == "cleanup" ]]; then
        cleanup
        exit 0
    fi
    
    # Check if this is a status request
    if [[ "${1:-}" == "status" ]]; then
        show_status
        exit 0
    fi
    
    check_prerequisites
    discover_apps
    
    case $MODE in
        docker)
            deploy_docker
            ;;
        kubernetes)
            deploy_kubernetes
            ;;
        both)
            deploy_docker
            deploy_kubernetes
            ;;
    esac
    
    if [[ "$DRY_RUN" == "false" ]]; then
        show_status
        
        print_header "Deployment Summary"
        print_status "✅ Deployment completed successfully"
        print_status "📊 Apps deployed: $APPS"
        print_status "🔧 Mode: $MODE"
        print_status "🌍 Environment: $ENVIRONMENT"
        
        if [[ "$MODE" == "docker" || "$MODE" == "both" ]]; then
            print_status "🐳 Docker services are available at:"
            print_status "   - Gateway: http://localhost:8080"
            print_status "   - Prometheus: http://localhost:9090"
            print_status "   - Grafana: http://localhost:3000"
        fi
        
        if [[ "$MODE" == "kubernetes" || "$MODE" == "both" ]]; then
            print_status "☸️  Kubernetes services deployed to 'kailash-platform' namespace"
            print_status "   Run 'kubectl get all -n kailash-platform' to see all resources"
        fi
    fi
}

# Handle interrupts
trap 'print_error "Deployment interrupted"; exit 1' INT TERM

# Run main function
main "$@"