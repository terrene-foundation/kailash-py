#!/bin/bash
# Network Policy Testing Script
# Tests connectivity and validates network security policies

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT_DIR="$(cd "$SCRIPT_DIR/../../" && pwd)"
TEST_NAMESPACE="netpol-test"
RESULTS_DIR="$SCRIPT_DIR/test-results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl not found"
        exit 1
    fi
    
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    # Check if CNI supports network policies
    local cni_check=$(kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.containerRuntimeVersion}' | grep -o '^[^:]*' || echo "unknown")
    log_info "Container runtime: $cni_check"
    
    log_success "Prerequisites satisfied"
}

# Create test namespace and pods
setup_test_environment() {
    log_info "Setting up test environment..."
    
    # Create test namespace
    kubectl create namespace "$TEST_NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
    
    # Create test pods
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: test-client
  namespace: $TEST_NAMESPACE
  labels:
    app: test-client
    role: client
spec:
  containers:
  - name: client
    image: busybox:1.35
    command: ["sleep", "3600"]
    resources:
      requests:
        memory: "64Mi"
        cpu: "100m"
      limits:
        memory: "128Mi"
        cpu: "200m"
---
apiVersion: v1
kind: Pod
metadata:
  name: test-server
  namespace: $TEST_NAMESPACE
  labels:
    app: test-server
    role: server
spec:
  containers:
  - name: server
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
  name: test-server-service
  namespace: $TEST_NAMESPACE
spec:
  selector:
    app: test-server
  ports:
  - port: 80
    targetPort: 80
EOF
    
    # Wait for pods to be ready
    log_info "Waiting for test pods to be ready..."
    kubectl wait --for=condition=Ready pod/test-client -n "$TEST_NAMESPACE" --timeout=60s
    kubectl wait --for=condition=Ready pod/test-server -n "$TEST_NAMESPACE" --timeout=60s
    
    log_success "Test environment setup complete"
}

# Test connectivity before network policies
test_connectivity_without_policies() {
    log_info "Testing connectivity without network policies..."
    
    local test_result
    
    # Test HTTP connectivity
    if kubectl exec -n "$TEST_NAMESPACE" test-client -- wget -qO- --timeout=10 test-server-service &> /dev/null; then
        log_success "HTTP connectivity test passed (expected before policies)"
        test_result="PASS"
    else
        log_warning "HTTP connectivity test failed (unexpected)"
        test_result="FAIL"
    fi
    
    echo "BEFORE_POLICIES: HTTP connectivity: $test_result" >> "$RESULTS_DIR/connectivity-test-$TIMESTAMP.txt"
}

# Apply network policies
apply_network_policies() {
    log_info "Applying network policies..."
    
    # Apply default deny to test namespace
    cat <<EOF | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: $TEST_NAMESPACE
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
EOF
    
    # Wait for policies to take effect
    sleep 5
    
    log_success "Network policies applied"
}

# Test connectivity after network policies (should fail)
test_connectivity_with_deny_all() {
    log_info "Testing connectivity with deny-all policy..."
    
    local test_result
    
    # Test HTTP connectivity (should fail)
    if kubectl exec -n "$TEST_NAMESPACE" test-client -- timeout 10 wget -qO- test-server-service &> /dev/null; then
        log_error "HTTP connectivity test passed (unexpected with deny-all policy)"
        test_result="FAIL"
    else
        log_success "HTTP connectivity test blocked (expected with deny-all policy)"
        test_result="PASS"
    fi
    
    echo "WITH_DENY_ALL: HTTP connectivity: $test_result" >> "$RESULTS_DIR/connectivity-test-$TIMESTAMP.txt"
}

# Apply selective allow policy
apply_selective_allow_policy() {
    log_info "Applying selective allow policy..."
    
    cat <<EOF | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-client-to-server
  namespace: $TEST_NAMESPACE
spec:
  podSelector:
    matchLabels:
      app: test-server
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: test-client
    ports:
    - protocol: TCP
      port: 80
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-client-egress
  namespace: $TEST_NAMESPACE
spec:
  podSelector:
    matchLabels:
      app: test-client
  policyTypes:
  - Egress
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: test-server
    ports:
    - protocol: TCP
      port: 80
EOF
    
    # Wait for policies to take effect
    sleep 5
    
    log_success "Selective allow policy applied"
}

# Test connectivity with selective allow (should pass)
test_connectivity_with_selective_allow() {
    log_info "Testing connectivity with selective allow policy..."
    
    local test_result
    
    # Test HTTP connectivity (should pass)
    if kubectl exec -n "$TEST_NAMESPACE" test-client -- timeout 10 wget -qO- test-server-service &> /dev/null; then
        log_success "HTTP connectivity test passed (expected with selective allow)"
        test_result="PASS"
    else
        log_error "HTTP connectivity test failed (unexpected with selective allow)"
        test_result="FAIL"
    fi
    
    echo "WITH_SELECTIVE_ALLOW: HTTP connectivity: $test_result" >> "$RESULTS_DIR/connectivity-test-$TIMESTAMP.txt"
}

# Validate production network policies
validate_production_policies() {
    log_info "Validating production network policies..."
    
    local policy_files=(
        "$DEPLOYMENT_DIR/security/network-policies/00-default-deny.yaml"
        "$DEPLOYMENT_DIR/security/network-policies/03-application-policies.yaml"
        "$DEPLOYMENT_DIR/security/network-policies/04-monitoring-policies.yaml"
    )
    
    local valid_count=0
    local total_count=${#policy_files[@]}
    
    for policy_file in "${policy_files[@]}"; do
        if [[ -f "$policy_file" ]]; then
            if kubectl apply --dry-run=client -f "$policy_file" &> /dev/null; then
                log_success "Policy valid: $(basename "$policy_file")"
                ((valid_count++))
            else
                log_error "Policy invalid: $(basename "$policy_file")"
            fi
        else
            log_error "Policy file not found: $(basename "$policy_file")"
        fi
    done
    
    echo "POLICY_VALIDATION: $valid_count/$total_count policies valid" >> "$RESULTS_DIR/connectivity-test-$TIMESTAMP.txt"
    
    if [[ "$valid_count" -eq "$total_count" ]]; then
        log_success "All production network policies are valid"
        return 0
    else
        log_error "Some production network policies are invalid"
        return 1
    fi
}

# Check existing network policies
check_existing_policies() {
    log_info "Checking existing network policies..."
    
    local policies=$(kubectl get networkpolicies --all-namespaces --no-headers 2>/dev/null | wc -l || echo "0")
    
    if [[ "$policies" -gt 0 ]]; then
        log_info "Found $policies existing network policies:"
        kubectl get networkpolicies --all-namespaces
    else
        log_warning "No existing network policies found"
    fi
    
    echo "EXISTING_POLICIES: $policies policies found" >> "$RESULTS_DIR/connectivity-test-$TIMESTAMP.txt"
}

# Cleanup test environment
cleanup_test_environment() {
    log_info "Cleaning up test environment..."
    
    kubectl delete namespace "$TEST_NAMESPACE" --ignore-not-found=true
    
    log_success "Test environment cleaned up"
}

# Generate test report
generate_test_report() {
    log_info "Generating test report..."
    
    local report_file="$RESULTS_DIR/network-policy-test-report-$TIMESTAMP.txt"
    
    cat > "$report_file" << EOF
Network Policy Testing Report
============================
Test Date: $(date)
Cluster: $(kubectl config current-context)

Test Results:
$(cat "$RESULTS_DIR/connectivity-test-$TIMESTAMP.txt")

Summary:
- Connectivity tests validate that network policies properly block/allow traffic
- Policy validation ensures production policies are syntactically correct
- Existing policies check shows current cluster state

Recommendations:
- Apply default deny policies to all application namespaces
- Implement least-privilege access between services
- Monitor network policy violations using CNI logs
- Regular testing of connectivity requirements

EOF
    
    log_success "Test report generated: $report_file"
    cat "$report_file"
}

# Main test execution
main() {
    log_info "Starting Network Policy Testing"
    
    # Initialize results directory
    mkdir -p "$RESULTS_DIR"
    echo "Network Policy Test Results - $(date)" > "$RESULTS_DIR/connectivity-test-$TIMESTAMP.txt"
    
    check_prerequisites
    check_existing_policies
    validate_production_policies
    
    # Full connectivity testing
    setup_test_environment
    test_connectivity_without_policies
    apply_network_policies
    test_connectivity_with_deny_all
    apply_selective_allow_policy
    test_connectivity_with_selective_allow
    cleanup_test_environment
    
    generate_test_report
    
    log_success "Network policy testing completed successfully!"
}

# Show help
show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Network Policy Testing Script

Options:
    -h, --help              Show this help message
    -n, --namespace NAME    Test namespace (default: netpol-test)
    -k, --keep-env         Keep test environment after testing

Examples:
    $0                      # Run all network policy tests
    $0 -k                   # Run tests and keep test environment
    $0 -n my-test          # Use custom test namespace

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -n|--namespace)
            TEST_NAMESPACE="$2"
            shift 2
            ;;
        -k|--keep-env)
            KEEP_ENV="true"
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Override cleanup if keep environment is requested
if [[ "${KEEP_ENV:-false}" == "true" ]]; then
    cleanup_test_environment() {
        log_info "Keeping test environment as requested (namespace: $TEST_NAMESPACE)"
    }
fi

# Run main function
main "$@"