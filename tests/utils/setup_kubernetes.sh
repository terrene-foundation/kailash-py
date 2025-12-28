#!/bin/bash
# Kubernetes Test Environment Setup Script
# Sets up kind cluster for Kailash SDK testing

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${YELLOW}→${NC} $1"
}

# Check if kubectl is installed
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        print_error "kubectl is not installed. Please install kubectl first."
        echo "Installation guide: https://kubernetes.io/docs/tasks/tools/"
        exit 1
    fi
    print_success "kubectl is available"
}

# Check if kind is installed
check_kind() {
    if ! command -v kind &> /dev/null; then
        print_error "kind is not installed. Please install kind first."
        echo "Installation guide: https://kind.sigs.k8s.io/docs/user/quick-start/#installation"
        exit 1
    fi
    print_success "kind is available"
}

# Check if Docker is running
check_docker() {
    if ! docker info &> /dev/null; then
        print_error "Docker is not running. Please start Docker first."
        exit 1
    fi
    print_success "Docker is running"
}

# Create kind cluster configuration
create_kind_config() {
    cat > /tmp/kailash-kind-config.yaml << EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: kailash-test
nodes:
- role: control-plane
  image: kindest/node:v1.29.0
  kubeadmConfigPatches:
  - |
    kind: InitConfiguration
    nodeRegistration:
      kubeletExtraArgs:
        node-labels: "ingress-ready=true"
  extraPortMappings:
  - containerPort: 80
    hostPort: 30080
    protocol: TCP
  - containerPort: 443
    hostPort: 30443
    protocol: TCP
  - containerPort: 6443
    hostPort: 6443
    protocol: TCP
EOF
    print_success "Kind cluster configuration created"
}

# Create kind cluster
create_cluster() {
    print_info "Creating kind cluster 'kailash-test'..."

    # Delete existing cluster if it exists
    if kind get clusters | grep -q "kailash-test"; then
        print_info "Deleting existing cluster..."
        kind delete cluster --name kailash-test
    fi

    # Create new cluster
    kind create cluster --config /tmp/kailash-kind-config.yaml

    # Wait for cluster to be ready
    print_info "Waiting for cluster to be ready..."
    kubectl wait --for=condition=Ready nodes --all --timeout=120s

    print_success "Kind cluster 'kailash-test' created and ready"
}

# Setup test namespace
setup_namespace() {
    print_info "Setting up test namespace..."

    kubectl create namespace kailash-test --dry-run=client -o yaml | kubectl apply -f -
    kubectl config set-context --current --namespace=kailash-test

    print_success "Test namespace 'kailash-test' created and set as default"
}

# Install NGINX Ingress Controller
install_ingress() {
    print_info "Installing NGINX Ingress Controller..."

    kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml

    # Wait for ingress controller to be ready
    kubectl wait --namespace ingress-nginx \
        --for=condition=ready pod \
        --selector=app.kubernetes.io/component=controller \
        --timeout=120s

    print_success "NGINX Ingress Controller installed"
}

# Create test resources for validation
create_test_resources() {
    print_info "Creating test resources..."

    # Create a simple test deployment
    cat << EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-nginx
  namespace: kailash-test
  labels:
    app: test-nginx
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test-nginx
  template:
    metadata:
      labels:
        app: test-nginx
    spec:
      containers:
      - name: nginx
        image: nginx:alpine
        ports:
        - containerPort: 80
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
  name: test-nginx-service
  namespace: kailash-test
spec:
  selector:
    app: test-nginx
  ports:
  - port: 80
    targetPort: 80
  type: ClusterIP
EOF

    # Wait for deployment to be ready
    kubectl wait --for=condition=available --timeout=60s deployment/test-nginx -n kailash-test

    print_success "Test resources created and ready"
}

# Verify cluster setup
verify_setup() {
    print_info "Verifying cluster setup..."

    # Check cluster info
    kubectl cluster-info

    # Check nodes
    kubectl get nodes

    # Check test resources
    kubectl get pods,services -n kailash-test

    print_success "Cluster verification complete"
}

# Export kubeconfig for tests
export_kubeconfig() {
    print_info "Exporting kubeconfig for tests..."

    # Get kubeconfig path
    KUBECONFIG_PATH=$(kind get kubeconfig-path --name kailash-test 2>/dev/null || echo "$HOME/.kube/config")

    echo "export KUBECONFIG=$KUBECONFIG_PATH" > /tmp/kailash-k8s-env
    echo "export KUBERNETES_HOST=localhost" >> /tmp/kailash-k8s-env
    echo "export KUBERNETES_PORT=6443" >> /tmp/kailash-k8s-env
    echo "export KUBERNETES_API_SERVER=https://localhost:6443" >> /tmp/kailash-k8s-env
    echo "export KUBERNETES_NAMESPACE=kailash-test" >> /tmp/kailash-k8s-env

    print_success "Environment variables exported to /tmp/kailash-k8s-env"
    print_info "Run: source /tmp/kailash-k8s-env"
}

# Main setup function
main() {
    print_info "Setting up Kubernetes test environment for Kailash SDK"

    check_kubectl
    check_kind
    check_docker

    create_kind_config
    create_cluster
    setup_namespace
    install_ingress
    create_test_resources
    verify_setup
    export_kubeconfig

    print_success "Kubernetes test environment setup complete!"
    echo ""
    print_info "Next steps:"
    echo "  1. Source environment: source /tmp/kailash-k8s-env"
    echo "  2. Run tests: pytest tests/test_phase4_integration_testing.py::TestPhase4ExecutionTests::test_kubernetes_node_execution -v"
    echo "  3. Clean up when done: kind delete cluster --name kailash-test"
}

# Cleanup function
cleanup() {
    print_info "Cleaning up Kubernetes test environment..."

    if kind get clusters | grep -q "kailash-test"; then
        kind delete cluster --name kailash-test
        print_success "Cluster deleted"
    else
        print_info "No cluster to delete"
    fi

    # Clean up temporary files
    rm -f /tmp/kailash-kind-config.yaml
    rm -f /tmp/kailash-k8s-env

    print_success "Cleanup complete"
}

# Handle script arguments
case "${1:-setup}" in
    setup)
        main
        ;;
    cleanup)
        cleanup
        ;;
    verify)
        verify_setup
        ;;
    *)
        echo "Usage: $0 {setup|cleanup|verify}"
        echo "  setup   - Create and configure kind cluster"
        echo "  cleanup - Delete kind cluster and clean up"
        echo "  verify  - Verify existing cluster setup"
        exit 1
        ;;
esac
