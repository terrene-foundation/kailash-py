#!/bin/bash
# CIS Kubernetes Benchmark Testing Script
# Tests and validates CIS benchmark implementations

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
RESULTS_DIR="$SCRIPT_DIR/results"
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

# Initialize results directory
init_results() {
    mkdir -p "$RESULTS_DIR"
    echo "CIS Kubernetes Benchmark Test Results - $(date)" > "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
}

# Check if kubectl is available and cluster is accessible
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl not found. Please install kubectl."
        exit 1
    fi
    
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster. Please check kubeconfig."
        exit 1
    fi
    
    log_success "Prerequisites satisfied"
}

# Test CIS 1.2.1 - API Server Anonymous Auth
test_anonymous_auth() {
    log_info "Testing CIS 1.2.1 - API Server Anonymous Authentication"
    
    # Check if anonymous auth is disabled in API server
    local result=$(kubectl get pods -n kube-system -l component=kube-apiserver -o yaml | grep -o "anonymous-auth=false" || echo "not_found")
    
    if [[ "$result" == "anonymous-auth=false" ]]; then
        log_success "CIS 1.2.1 - Anonymous authentication is disabled"
        echo "PASS: CIS 1.2.1" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
        return 0
    else
        log_error "CIS 1.2.1 - Anonymous authentication is not properly disabled"
        echo "FAIL: CIS 1.2.1" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
        return 1
    fi
}

# Test CIS 1.2.12 - Encryption at Rest
test_encryption_at_rest() {
    log_info "Testing CIS 1.2.12 - Encryption at Rest"
    
    # Check if encryption provider config is set
    local result=$(kubectl get pods -n kube-system -l component=kube-apiserver -o yaml | grep -o "encryption-provider-config" || echo "not_found")
    
    if [[ "$result" == "encryption-provider-config" ]]; then
        log_success "CIS 1.2.12 - Encryption at rest is configured"
        echo "PASS: CIS 1.2.12" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
        return 0
    else
        log_error "CIS 1.2.12 - Encryption at rest is not configured"
        echo "FAIL: CIS 1.2.12" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
        return 1
    fi
}

# Test CIS 1.2.29 - Audit Logging
test_audit_logging() {
    log_info "Testing CIS 1.2.29 - Audit Logging"
    
    # Check if audit logging is enabled
    local result=$(kubectl get pods -n kube-system -l component=kube-apiserver -o yaml | grep -o "audit-log-path" || echo "not_found")
    
    if [[ "$result" == "audit-log-path" ]]; then
        log_success "CIS 1.2.29 - Audit logging is enabled"
        echo "PASS: CIS 1.2.29" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
        return 0
    else
        log_error "CIS 1.2.29 - Audit logging is not enabled"
        echo "FAIL: CIS 1.2.29" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
        return 1
    fi
}

# Test CIS 4.2.1 - Kubelet Anonymous Auth
test_kubelet_anonymous_auth() {
    log_info "Testing CIS 4.2.1 - Kubelet Anonymous Authentication"
    
    # Check kubelet configuration on nodes
    local nodes=$(kubectl get nodes -o name | head -1)
    if [[ -n "$nodes" ]]; then
        # This is a simplified check - in practice, you'd need to access node filesystem
        log_warning "CIS 4.2.1 - Manual verification required for kubelet anonymous auth"
        echo "MANUAL: CIS 4.2.1" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
        return 0
    else
        log_error "CIS 4.2.1 - No nodes found for testing"
        echo "FAIL: CIS 4.2.1" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
        return 1
    fi
}

# Test Pod Security Standards
test_pod_security_standards() {
    log_info "Testing Pod Security Standards"
    
    # Check if PSS is enabled
    local pss_enabled=$(kubectl api-resources | grep -c "podsecuritypolicy" || echo "0")
    
    if [[ "$pss_enabled" -gt 0 ]]; then
        log_success "Pod Security Policies are available"
        echo "PASS: Pod Security Standards" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
        return 0
    else
        log_warning "Pod Security Policies not found - checking for PSS"
        echo "MANUAL: Pod Security Standards" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
        return 0
    fi
}

# Test RBAC Configuration
test_rbac_configuration() {
    log_info "Testing RBAC Configuration"
    
    # Check if RBAC is enabled
    local rbac_enabled=$(kubectl auth can-i --list --as=system:anonymous 2>/dev/null | grep -c "No resources found" || echo "0")
    
    if [[ "$rbac_enabled" -gt 0 ]]; then
        log_success "RBAC is properly configured (anonymous access denied)"
        echo "PASS: RBAC Configuration" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
        return 0
    else
        log_error "RBAC configuration needs review"
        echo "FAIL: RBAC Configuration" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
        return 1
    fi
}

# Install and run kube-bench if available
run_kube_bench() {
    log_info "Running kube-bench for comprehensive CIS assessment"
    
    if command -v kube-bench &> /dev/null; then
        log_info "kube-bench found, running comprehensive scan..."
        kube-bench run --targets=master,node,etcd,policies > "$RESULTS_DIR/kube-bench-$TIMESTAMP.txt" 2>&1
        log_success "kube-bench scan completed - check $RESULTS_DIR/kube-bench-$TIMESTAMP.txt"
    else
        log_warning "kube-bench not found. Installing..."
        
        # Download and install kube-bench
        local os=$(uname -s | tr '[:upper:]' '[:lower:]')
        local arch=$(uname -m)
        [[ "$arch" == "x86_64" ]] && arch="amd64"
        [[ "$arch" == "aarch64" ]] && arch="arm64"
        
        local download_url="https://github.com/aquasecurity/kube-bench/releases/latest/download/kube-bench_${os}_${arch}.tar.gz"
        
        if curl -L "$download_url" | tar xz -C /tmp/; then
            sudo mv /tmp/kube-bench /usr/local/bin/
            log_success "kube-bench installed successfully"
            
            # Run the scan
            kube-bench run --targets=master,node,etcd,policies > "$RESULTS_DIR/kube-bench-$TIMESTAMP.txt" 2>&1
            log_success "kube-bench scan completed"
        else
            log_error "Failed to install kube-bench"
            return 1
        fi
    fi
}

# Validate configuration files
validate_configs() {
    log_info "Validating CIS configuration files"
    
    local config_files=(
        "$DEPLOYMENT_DIR/security/cis-benchmarks/api-server/kube-apiserver.yaml"
        "$DEPLOYMENT_DIR/security/cis-benchmarks/api-server/audit-policy.yaml"
        "$DEPLOYMENT_DIR/security/cis-benchmarks/api-server/encryption-config.yaml"
        "$DEPLOYMENT_DIR/security/cis-benchmarks/api-server/admission-config.yaml"
    )
    
    local valid_count=0
    local total_count=${#config_files[@]}
    
    for config_file in "${config_files[@]}"; do
        if [[ -f "$config_file" ]]; then
            if kubectl apply --dry-run=client -f "$config_file" &> /dev/null; then
                log_success "Configuration valid: $(basename "$config_file")"
                ((valid_count++))
            else
                log_error "Configuration invalid: $(basename "$config_file")"
            fi
        else
            log_error "Configuration file not found: $(basename "$config_file")"
        fi
    done
    
    echo "CONFIG VALIDATION: $valid_count/$total_count files valid" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    
    if [[ "$valid_count" -eq "$total_count" ]]; then
        log_success "All configuration files are valid"
        return 0
    else
        log_error "Some configuration files are invalid"
        return 1
    fi
}

# Generate summary report
generate_summary() {
    log_info "Generating summary report"
    
    local report_file="$RESULTS_DIR/cis-summary-$TIMESTAMP.txt"
    
    cat > "$report_file" << EOF
CIS Kubernetes Benchmark Test Summary
=====================================
Test Date: $(date)
Cluster: $(kubectl config current-context)

Test Results:
EOF
    
    # Count pass/fail from detailed report
    local pass_count=$(grep -c "PASS:" "$RESULTS_DIR/test-report-$TIMESTAMP.txt" || echo "0")
    local fail_count=$(grep -c "FAIL:" "$RESULTS_DIR/test-report-$TIMESTAMP.txt" || echo "0")
    local manual_count=$(grep -c "MANUAL:" "$RESULTS_DIR/test-report-$TIMESTAMP.txt" || echo "0")
    local total_count=$((pass_count + fail_count + manual_count))
    
    cat >> "$report_file" << EOF
- Total Tests: $total_count
- Passed: $pass_count
- Failed: $fail_count
- Manual Review Required: $manual_count

Score: $pass_count/$total_count ($(( pass_count * 100 / total_count ))%)

Files Generated:
- Detailed Report: test-report-$TIMESTAMP.txt
- kube-bench Output: kube-bench-$TIMESTAMP.txt (if available)
- Summary Report: cis-summary-$TIMESTAMP.txt

Recommendations:
- Review failed tests and apply necessary configurations
- Schedule regular CIS benchmark assessments
- Implement continuous monitoring for compliance drift
EOF
    
    log_success "Summary report generated: $report_file"
    cat "$report_file"
}

# Main test execution
main() {
    log_info "Starting CIS Kubernetes Benchmark Tests"
    
    init_results
    check_prerequisites
    
    # Run individual tests
    local test_results=()
    
    test_anonymous_auth && test_results+=("PASS") || test_results+=("FAIL")
    test_encryption_at_rest && test_results+=("PASS") || test_results+=("FAIL")
    test_audit_logging && test_results+=("PASS") || test_results+=("FAIL")
    test_kubelet_anonymous_auth && test_results+=("PASS") || test_results+=("FAIL")
    test_pod_security_standards && test_results+=("PASS") || test_results+=("FAIL")
    test_rbac_configuration && test_results+=("PASS") || test_results+=("FAIL")
    
    # Validate configuration files
    validate_configs && test_results+=("PASS") || test_results+=("FAIL")
    
    # Run comprehensive kube-bench scan
    run_kube_bench && test_results+=("PASS") || test_results+=("FAIL")
    
    # Generate final report
    generate_summary
    
    # Count failures
    local failures=$(printf '%s\n' "${test_results[@]}" | grep -c "FAIL" || echo "0")
    
    if [[ "$failures" -eq 0 ]]; then
        log_success "All CIS benchmark tests passed!"
        exit 0
    else
        log_error "$failures test(s) failed. Review the detailed report for remediation steps."
        exit 1
    fi
}

# Show help
show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

CIS Kubernetes Benchmark Testing Script

Options:
    -h, --help              Show this help message
    -v, --verbose           Enable verbose output
    -o, --output DIR        Specify output directory (default: ./results)

Examples:
    $0                      # Run all CIS benchmark tests
    $0 -v                   # Run with verbose output
    $0 -o /tmp/cis-results  # Save results to custom directory

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -v|--verbose)
            set -x
            shift
            ;;
        -o|--output)
            RESULTS_DIR="$2"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Run main function
main "$@"