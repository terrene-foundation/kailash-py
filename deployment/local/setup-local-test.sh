#!/bin/bash
# Local Kubernetes Test Environment Setup
# Creates a Kind cluster and deploys security configurations for testing

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLUSTER_NAME="kailash-test"
KUBECONFIG_PATH="$HOME/.kube/config-$CLUSTER_NAME"

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
    
    local required_tools=("docker" "kubectl")
    local missing_tools=()
    
    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            missing_tools+=("$tool")
        fi
    done
    
    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing_tools[*]}"
        log_error "Please install them first"
        exit 1
    fi
    
    # Check for Kind
    if ! command -v kind &> /dev/null; then
        log_warning "Kind not found. Installing..."
        install_kind
    fi
    
    # Check if Docker is running
    if ! docker info &> /dev/null; then
        log_error "Docker is not running. Please start Docker."
        exit 1
    fi
    
    log_success "All prerequisites satisfied"
}

# Install Kind
install_kind() {
    log_info "Installing Kind..."
    
    local os=$(uname -s | tr '[:upper:]' '[:lower:]')
    local arch=$(uname -m)
    
    # Convert arch names
    case "$arch" in
        x86_64) arch="amd64" ;;
        aarch64|arm64) arch="arm64" ;;
    esac
    
    # Download Kind
    local kind_version="v0.20.0"
    local download_url="https://github.com/kubernetes-sigs/kind/releases/download/${kind_version}/kind-${os}-${arch}"
    
    if curl -Lo /tmp/kind "$download_url" && chmod +x /tmp/kind; then
        sudo mv /tmp/kind /usr/local/bin/kind
        log_success "Kind installed successfully"
    else
        log_error "Failed to install Kind"
        exit 1
    fi
}

# Create Kind cluster
create_kind_cluster() {
    log_info "Creating Kind cluster: $CLUSTER_NAME"
    
    # Check if cluster already exists
    if kind get clusters | grep -q "^$CLUSTER_NAME$"; then
        log_warning "Cluster $CLUSTER_NAME already exists"
        read -p "Delete and recreate? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            kind delete cluster --name "$CLUSTER_NAME"
        else
            log_info "Using existing cluster"
            return
        fi
    fi
    
    # Create cluster with config
    if kind create cluster --config "$PROJECT_ROOT/deployment/local/kind-config.yaml"; then
        log_success "Kind cluster created successfully"
    else
        log_error "Failed to create Kind cluster"
        exit 1
    fi
    
    # Set kubeconfig
    kind get kubeconfig --name "$CLUSTER_NAME" > "$KUBECONFIG_PATH"
    export KUBECONFIG="$KUBECONFIG_PATH"
    
    log_info "Waiting for cluster to be ready..."
    kubectl wait --for=condition=Ready nodes --all --timeout=300s
}

# Install Calico CNI for network policy support
install_calico() {
    log_info "Installing Calico CNI for network policy support..."
    
    # Install Tigera Calico operator
    kubectl create -f https://raw.githubusercontent.com/projectcalico/calico/v3.26.1/manifests/tigera-operator.yaml || true
    
    # Configure Calico
    cat <<EOF | kubectl apply -f -
apiVersion: operator.tigera.io/v1
kind: Installation
metadata:
  name: default
spec:
  calicoNetwork:
    ipPools:
    - blockSize: 26
      cidr: 10.244.0.0/16
      encapsulation: VXLANCrossSubnet
      natOutgoing: Enabled
      nodeSelector: all()
---
apiVersion: operator.tigera.io/v1
kind: APIServer
metadata:
  name: default
spec: {}
EOF
    
    # Wait for Calico to be ready
    log_info "Waiting for Calico to be ready..."
    kubectl wait --for=condition=Ready pods -n calico-system --all --timeout=300s || true
    
    log_success "Calico CNI installed"
}

# Deploy CIS benchmark configurations
deploy_cis_configs() {
    log_info "Deploying CIS benchmark configurations..."
    
    # Create necessary directories in the cluster
    for node in $(kubectl get nodes -o name | cut -d/ -f2); do
        log_info "Configuring node: $node"
        
        # Copy audit policy
        docker cp "$PROJECT_ROOT/deployment/security/cis-benchmarks/api-server/audit-policy.yaml" "$node:/etc/kubernetes/audit/"
        
        # Copy encryption config
        docker cp "$PROJECT_ROOT/deployment/security/cis-benchmarks/api-server/encryption-config.yaml" "$node:/etc/kubernetes/encryption/"
    done
    
    log_success "CIS configurations deployed"
}

# Deploy network policies
deploy_network_policies() {
    log_info "Deploying network policies..."
    
    # Create test namespaces
    kubectl create namespace kailash-system --dry-run=client -o yaml | kubectl apply -f -
    kubectl create namespace kailash-user-management --dry-run=client -o yaml | kubectl apply -f -
    kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
    
    # Label namespaces
    kubectl label namespace kailash-system name=kailash-system --overwrite
    kubectl label namespace kailash-user-management name=kailash-user-management --overwrite
    kubectl label namespace monitoring name=monitoring --overwrite
    kubectl label namespace default name=default --overwrite
    
    # Apply network policies
    kubectl apply -f "$PROJECT_ROOT/deployment/security/network-policies/00-default-deny.yaml"
    kubectl apply -f "$PROJECT_ROOT/deployment/security/network-policies/03-application-policies.yaml"
    kubectl apply -f "$PROJECT_ROOT/deployment/security/network-policies/04-monitoring-policies.yaml"
    
    log_success "Network policies deployed"
}

# Deploy test applications
deploy_test_apps() {
    log_info "Deploying test applications..."
    
    # Deploy a simple nginx app
    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-app
  namespace: default
  labels:
    app: kailash-template
spec:
  replicas: 2
  selector:
    matchLabels:
      app: kailash-template
  template:
    metadata:
      labels:
        app: kailash-template
    spec:
      containers:
      - name: nginx
        image: nginx:1.25-alpine
        ports:
        - containerPort: 80
        resources:
          requests:
            memory: "64Mi"
            cpu: "100m"
          limits:
            memory: "128Mi"
            cpu: "200m"
---
apiVersion: v1
kind: Service
metadata:
  name: test-app
  namespace: default
spec:
  selector:
    app: kailash-template
  ports:
  - port: 80
    targetPort: 80
EOF
    
    # Deploy PostgreSQL mock
    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: default
  labels:
    app: postgres
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15-alpine
        env:
        - name: POSTGRES_PASSWORD
          value: testpassword
        - name: POSTGRES_DB
          value: kailash
        ports:
        - containerPort: 5432
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: default
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
EOF
    
    # Deploy Redis mock
    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: default
  labels:
    app: redis
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
        resources:
          requests:
            memory: "64Mi"
            cpu: "50m"
          limits:
            memory: "128Mi"
            cpu: "100m"
---
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: default
spec:
  selector:
    app: redis
  ports:
  - port: 6379
    targetPort: 6379
EOF
    
    log_info "Waiting for test applications to be ready..."
    kubectl wait --for=condition=available deployment/test-app --timeout=300s
    kubectl wait --for=condition=available deployment/postgres --timeout=300s
    kubectl wait --for=condition=available deployment/redis --timeout=300s
    
    log_success "Test applications deployed"
}

# Test network policies
test_network_policies() {
    log_info "Testing network policies..."
    
    # Run network policy tests
    "$PROJECT_ROOT/deployment/security/scripts/test-network-policies.sh" || true
    
    log_success "Network policy tests completed"
}

# Deploy Vault in dev mode for testing
deploy_vault_dev() {
    log_info "Deploying Vault in dev mode for testing..."
    
    # Create Vault namespace
    kubectl create namespace vault-system --dry-run=client -o yaml | kubectl apply -f -
    
    # Deploy Vault in dev mode
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Service
metadata:
  name: vault
  namespace: vault-system
spec:
  selector:
    app: vault
  ports:
  - port: 8200
    targetPort: 8200
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vault
  namespace: vault-system
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vault
  template:
    metadata:
      labels:
        app: vault
    spec:
      containers:
      - name: vault
        image: hashicorp/vault:1.15.2
        env:
        - name: VAULT_DEV_ROOT_TOKEN_ID
          value: "root"
        - name: VAULT_DEV_LISTEN_ADDRESS
          value: "0.0.0.0:8200"
        ports:
        - containerPort: 8200
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
EOF
    
    log_info "Waiting for Vault to be ready..."
    kubectl wait --for=condition=available deployment/vault -n vault-system --timeout=300s
    
    # Deploy External Secrets Operator
    kubectl apply -f "$PROJECT_ROOT/deployment/security/secrets-management/external-secrets/operator.yaml"
    
    log_success "Vault and External Secrets Operator deployed"
}

# Run all security tests
run_security_tests() {
    log_info "Running security tests..."
    
    echo
    log_info "=== CIS Benchmark Validation ==="
    "$PROJECT_ROOT/deployment/security/scripts/validate-configs.sh"
    
    echo
    log_info "=== Network Policy Tests ==="
    # Network policy tests already run above
    
    echo
    log_info "=== Secrets Management Tests ==="
    "$PROJECT_ROOT/deployment/security/scripts/test-secrets.sh" || true
    
    log_success "All security tests completed"
}

# Display cluster information
show_cluster_info() {
    log_info "Cluster Information:"
    echo
    
    log_info "Nodes:"
    kubectl get nodes
    echo
    
    log_info "Namespaces:"
    kubectl get namespaces
    echo
    
    log_info "Network Policies:"
    kubectl get networkpolicies --all-namespaces
    echo
    
    log_info "Pods:"
    kubectl get pods --all-namespaces
    echo
    
    log_info "Access the cluster:"
    echo "export KUBECONFIG=$KUBECONFIG_PATH"
    echo "kubectl get nodes"
    echo
    
    log_success "Local test environment is ready!"
}

# Cleanup function
cleanup() {
    log_info "Cleaning up test environment..."
    kind delete cluster --name "$CLUSTER_NAME" || true
    rm -f "$KUBECONFIG_PATH"
    log_success "Cleanup completed"
}

# Main execution
main() {
    log_info "Setting up local Kubernetes test environment"
    echo "============================================="
    
    check_prerequisites
    create_kind_cluster
    install_calico
    deploy_cis_configs
    deploy_network_policies
    deploy_test_apps
    test_network_policies
    deploy_vault_dev
    run_security_tests
    show_cluster_info
    
    echo "============================================="
    log_success "Local test environment setup completed!"
    echo
    echo "To destroy the test cluster, run:"
    echo "kind delete cluster --name $CLUSTER_NAME"
}

# Show help
show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Setup local Kubernetes test environment for security testing

Options:
    -h, --help      Show this help message
    -c, --cleanup   Cleanup test environment
    -k, --keep      Keep cluster after tests

Examples:
    $0              # Setup and run all tests
    $0 --cleanup    # Cleanup test environment
    $0 --keep       # Setup but don't cleanup after

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -c|--cleanup)
            cleanup
            exit 0
            ;;
        -k|--keep)
            KEEP_CLUSTER="true"
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Set trap for cleanup on exit (unless --keep is specified)
if [[ "${KEEP_CLUSTER:-false}" != "true" ]]; then
    trap cleanup EXIT
fi

# Run main function
main "$@"