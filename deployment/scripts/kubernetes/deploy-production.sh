#!/bin/bash
set -euo pipefail

# Kailash User Management - Production Kubernetes Deployment Script
# This script deploys the User Management System to production Kubernetes environment

# Configuration
NAMESPACE="kailash-user-management"
APP_NAME="kailash-user-management"
MANIFESTS_DIR="../../k8s"
ENVIRONMENT="production"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed or not in PATH"
        exit 1
    fi
    
    # Check cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    # Check if manifests directory exists
    if [[ ! -d "$MANIFESTS_DIR" ]]; then
        log_error "Manifests directory not found: $MANIFESTS_DIR"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Create namespace if it doesn't exist
create_namespace() {
    log_info "Creating/updating namespace..."
    
    if kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_info "Namespace $NAMESPACE already exists"
    else
        kubectl apply -f "$MANIFESTS_DIR/namespace.yaml"
        log_success "Namespace $NAMESPACE created"
    fi
}

# Deploy secrets
deploy_secrets() {
    log_info "Deploying secrets..."
    
    # Check if secrets already exist
    if kubectl get secret user-management-secrets -n "$NAMESPACE" &> /dev/null; then
        log_warning "Secrets already exist, skipping creation"
        read -p "Do you want to update secrets? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            kubectl apply -f "$MANIFESTS_DIR/secrets.yaml"
            log_success "Secrets updated"
        fi
    else
        kubectl apply -f "$MANIFESTS_DIR/secrets.yaml"
        log_success "Secrets created"
    fi
}

# Deploy ConfigMaps
deploy_configmaps() {
    log_info "Deploying ConfigMaps..."
    kubectl apply -f "$MANIFESTS_DIR/configmap.yaml"
    log_success "ConfigMaps deployed"
}

# Deploy RBAC
deploy_rbac() {
    log_info "Deploying RBAC configuration..."
    kubectl apply -f "$MANIFESTS_DIR/rbac.yaml"
    log_success "RBAC configuration deployed"
}

# Deploy storage
deploy_storage() {
    log_info "Deploying persistent storage..."
    kubectl apply -f "$MANIFESTS_DIR/pvc.yaml"
    
    # Wait for PVCs to be bound
    log_info "Waiting for PVCs to be bound..."
    kubectl wait --for=condition=Bound pvc/user-management-data -n "$NAMESPACE" --timeout=300s
    kubectl wait --for=condition=Bound pvc/postgresql-data -n "$NAMESPACE" --timeout=300s
    kubectl wait --for=condition=Bound pvc/redis-data -n "$NAMESPACE" --timeout=300s
    
    log_success "Persistent storage deployed and bound"
}

# Deploy applications
deploy_applications() {
    log_info "Deploying applications..."
    kubectl apply -f "$MANIFESTS_DIR/deployment.yaml"
    
    # Wait for deployments to be ready
    log_info "Waiting for deployments to be ready..."
    kubectl wait --for=condition=Available deployment/user-management-app -n "$NAMESPACE" --timeout=600s
    kubectl wait --for=condition=Available deployment/postgresql -n "$NAMESPACE" --timeout=300s
    kubectl wait --for=condition=Available deployment/redis -n "$NAMESPACE" --timeout=300s
    
    log_success "Applications deployed successfully"
}

# Deploy services
deploy_services() {
    log_info "Deploying services..."
    kubectl apply -f "$MANIFESTS_DIR/service.yaml"
    log_success "Services deployed"
}

# Deploy ingress
deploy_ingress() {
    log_info "Deploying ingress..."
    kubectl apply -f "$MANIFESTS_DIR/ingress.yaml"
    log_success "Ingress deployed"
}

# Deploy autoscaling
deploy_autoscaling() {
    log_info "Deploying horizontal pod autoscaler..."
    kubectl apply -f "$MANIFESTS_DIR/hpa.yaml"
    log_success "Autoscaling configured"
}

# Verify deployment
verify_deployment() {
    log_info "Verifying deployment..."
    
    # Check pod status
    log_info "Checking pod status..."
    kubectl get pods -n "$NAMESPACE" -o wide
    
    # Check service status
    log_info "Checking service status..."
    kubectl get svc -n "$NAMESPACE"
    
    # Check ingress status
    log_info "Checking ingress status..."
    kubectl get ingress -n "$NAMESPACE"
    
    # Check HPA status
    log_info "Checking HPA status..."
    kubectl get hpa -n "$NAMESPACE"
    
    # Health check
    log_info "Performing health check..."
    
    # Wait for service to be ready
    sleep 30
    
    # Try to access health endpoint
    SERVICE_IP=$(kubectl get svc user-management-service -n "$NAMESPACE" -o jsonpath='{.spec.clusterIP}')
    if kubectl run temp-pod --rm -i --restart=Never --image=curlimages/curl -- curl -f "http://$SERVICE_IP:8000/health" &> /dev/null; then
        log_success "Health check passed"
    else
        log_warning "Health check failed - service may still be starting"
    fi
}

# Get access information
get_access_info() {
    log_info "Getting access information..."
    
    # External LoadBalancer IP
    EXTERNAL_IP=$(kubectl get svc user-management-external -n "$NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "Pending")
    
    # Ingress information
    INGRESS_HOST=$(kubectl get ingress user-management-ingress -n "$NAMESPACE" -o jsonpath='{.spec.rules[0].host}' 2>/dev/null || echo "Not configured")
    
    echo
    log_success "=== DEPLOYMENT COMPLETED ==="
    echo "Environment: $ENVIRONMENT"
    echo "Namespace: $NAMESPACE"
    echo "External LoadBalancer IP: $EXTERNAL_IP"
    echo "Ingress Host: $INGRESS_HOST"
    echo
    echo "API Endpoints:"
    echo "  Health Check: https://$INGRESS_HOST/health"
    echo "  API: https://$INGRESS_HOST/api"
    echo "  WebSocket: wss://$INGRESS_HOST/ws"
    echo "  Metrics: https://$INGRESS_HOST/metrics (internal only)"
    echo
    echo "Monitoring:"
    echo "  kubectl get pods -n $NAMESPACE"
    echo "  kubectl logs -f deployment/user-management-app -n $NAMESPACE"
    echo "  kubectl describe hpa user-management-hpa -n $NAMESPACE"
    echo
}

# Cleanup function for failed deployments
cleanup_on_failure() {
    log_error "Deployment failed. Cleaning up..."
    
    # Remove resources in reverse order
    kubectl delete -f "$MANIFESTS_DIR/hpa.yaml" --ignore-not-found=true
    kubectl delete -f "$MANIFESTS_DIR/ingress.yaml" --ignore-not-found=true
    kubectl delete -f "$MANIFESTS_DIR/service.yaml" --ignore-not-found=true
    kubectl delete -f "$MANIFESTS_DIR/deployment.yaml" --ignore-not-found=true
    kubectl delete -f "$MANIFESTS_DIR/pvc.yaml" --ignore-not-found=true
    kubectl delete -f "$MANIFESTS_DIR/rbac.yaml" --ignore-not-found=true
    kubectl delete -f "$MANIFESTS_DIR/configmap.yaml" --ignore-not-found=true
    
    log_info "Cleanup completed"
    exit 1
}

# Main deployment function
main() {
    log_info "Starting production deployment of Kailash User Management System"
    log_info "Environment: $ENVIRONMENT"
    log_info "Namespace: $NAMESPACE"
    
    # Set trap for cleanup on failure
    trap cleanup_on_failure ERR
    
    # Confirmation prompt for production
    echo
    log_warning "You are about to deploy to PRODUCTION environment!"
    read -p "Are you sure you want to continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Deployment cancelled"
        exit 0
    fi
    
    # Run deployment steps
    check_prerequisites
    create_namespace
    deploy_secrets
    deploy_configmaps
    deploy_rbac
    deploy_storage
    deploy_applications
    deploy_services
    deploy_ingress
    deploy_autoscaling
    verify_deployment
    get_access_info
    
    log_success "Production deployment completed successfully!"
}

# Run main function
main "$@"