#!/bin/bash
# Secrets Management Testing Script
# Tests Vault and External Secrets integration

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_NAMESPACE="vault-system"
ESO_NAMESPACE="external-secrets-system"
APP_NAMESPACE="default"
ERRORS=0

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
    ((ERRORS++))
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
    
    log_success "Prerequisites satisfied"
}

# Test Vault connectivity
test_vault_connectivity() {
    log_info "Testing Vault connectivity..."
    
    # Check if Vault pods are running
    if kubectl get pods -n "$VAULT_NAMESPACE" -l app.kubernetes.io/name=vault | grep -q "Running"; then
        log_success "Vault pods are running"
    else
        log_error "Vault pods are not running"
        return 1
    fi
    
    # Test Vault status
    if kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault status &> /dev/null; then
        local vault_status=$(kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault status -format=json | jq -r '.sealed')
        
        if [[ "$vault_status" == "false" ]]; then
            log_success "Vault is unsealed and accessible"
        else
            log_error "Vault is sealed"
            return 1
        fi
    else
        log_error "Cannot connect to Vault"
        return 1
    fi
}

# Test Vault authentication
test_vault_authentication() {
    log_info "Testing Vault authentication..."
    
    # Test root token access (if available)
    if kubectl get secret vault-init -n "$VAULT_NAMESPACE" &> /dev/null; then
        local root_token
        root_token=$(kubectl get secret vault-init -n "$VAULT_NAMESPACE" -o jsonpath='{.data.root-token}' | base64 -d)
        
        if kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault auth -method=token token="$root_token" &> /dev/null; then
            log_success "Root token authentication works"
        else
            log_error "Root token authentication failed"
        fi
    else
        log_warning "Vault init secret not found - cannot test root token"
    fi
    
    # Test Kubernetes auth method
    if kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault auth list | grep -q "kubernetes/"; then
        log_success "Kubernetes auth method is enabled"
    else
        log_error "Kubernetes auth method is not enabled"
    fi
}

# Test secret engines
test_secret_engines() {
    log_info "Testing Vault secret engines..."
    
    # Test KV v2 engine
    if kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault secrets list | grep -q "kv/"; then
        log_success "KV v2 secret engine is enabled"
        
        # Test reading a secret
        if kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault kv get kv/database/postgres &> /dev/null; then
            log_success "Can read secrets from KV engine"
        else
            log_warning "Cannot read sample secrets (may not exist yet)"
        fi
    else
        log_error "KV v2 secret engine is not enabled"
    fi
}

# Test External Secrets Operator
test_external_secrets_operator() {
    log_info "Testing External Secrets Operator..."
    
    # Check if ESO is deployed
    if kubectl get deployment external-secrets -n "$ESO_NAMESPACE" &> /dev/null; then
        if kubectl get pods -n "$ESO_NAMESPACE" -l app.kubernetes.io/name=external-secrets | grep -q "Running"; then
            log_success "External Secrets Operator is running"
        else
            log_error "External Secrets Operator pods are not running"
            return 1
        fi
    else
        log_error "External Secrets Operator is not deployed"
        return 1
    fi
    
    # Check webhook
    if kubectl get deployment external-secrets-webhook -n "$ESO_NAMESPACE" &> /dev/null; then
        if kubectl get pods -n "$ESO_NAMESPACE" -l app.kubernetes.io/name=external-secrets-webhook | grep -q "Running"; then
            log_success "External Secrets webhook is running"
        else
            log_error "External Secrets webhook is not running"
        fi
    else
        log_warning "External Secrets webhook is not deployed"
    fi
}

# Test secret stores
test_secret_stores() {
    log_info "Testing secret stores..."
    
    # Check cluster secret store
    if kubectl get clustersecretstore vault-backend &> /dev/null; then
        log_success "Vault cluster secret store exists"
        
        # Check store status
        local store_status
        store_status=$(kubectl get clustersecretstore vault-backend -o jsonpath='{.status.conditions[0].status}' 2>/dev/null || echo "Unknown")
        
        if [[ "$store_status" == "True" ]]; then
            log_success "Vault cluster secret store is ready"
        else
            log_warning "Vault cluster secret store status: $store_status"
        fi
    else
        log_error "Vault cluster secret store not found"
    fi
    
    # Check service account
    if kubectl get serviceaccount external-secrets-vault -n "$ESO_NAMESPACE" &> /dev/null; then
        log_success "External Secrets service account exists"
    else
        log_warning "External Secrets service account not found"
    fi
}

# Test external secrets
test_external_secrets() {
    log_info "Testing external secrets..."
    
    local external_secrets=(
        "postgres-credentials"
        "redis-credentials"
        "application-secrets"
    )
    
    for external_secret in "${external_secrets[@]}"; do
        if kubectl get externalsecret "$external_secret" -n "$APP_NAMESPACE" &> /dev/null; then
            log_success "External secret exists: $external_secret"
            
            # Check external secret status
            local status
            status=$(kubectl get externalsecret "$external_secret" -n "$APP_NAMESPACE" -o jsonpath='{.status.conditions[0].status}' 2>/dev/null || echo "Unknown")
            
            if [[ "$status" == "True" ]]; then
                log_success "External secret is synced: $external_secret"
            else
                log_warning "External secret status: $external_secret = $status"
            fi
            
            # Check if target secret was created
            local target_secret
            target_secret=$(kubectl get externalsecret "$external_secret" -n "$APP_NAMESPACE" -o jsonpath='{.spec.target.name}' 2>/dev/null || echo "")
            
            if [[ -n "$target_secret" ]] && kubectl get secret "$target_secret" -n "$APP_NAMESPACE" &> /dev/null; then
                log_success "Target secret created: $target_secret"
                
                # Check secret data
                local secret_keys
                secret_keys=$(kubectl get secret "$target_secret" -n "$APP_NAMESPACE" -o jsonpath='{.data}' | jq -r 'keys[]' 2>/dev/null | wc -l || echo "0")
                
                if [[ "$secret_keys" -gt 0 ]]; then
                    log_success "Target secret has $secret_keys keys: $target_secret"
                else
                    log_warning "Target secret has no data: $target_secret"
                fi
            else
                log_error "Target secret not created for: $external_secret"
            fi
        else
            log_warning "External secret not found: $external_secret"
        fi
    done
}

# Test secret access from application
test_secret_access() {
    log_info "Testing secret access from application..."
    
    # Create a test pod that uses secrets
    local test_pod_name="secret-test-pod"
    
    # Clean up any existing test pod
    kubectl delete pod "$test_pod_name" -n "$APP_NAMESPACE" --ignore-not-found=true
    
    # Create test pod
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: $test_pod_name
  namespace: $APP_NAMESPACE
  labels:
    app: secret-test
spec:
  restartPolicy: Never
  containers:
  - name: test
    image: busybox:1.35
    command: ["sleep", "300"]
    env:
    - name: DATABASE_URL
      valueFrom:
        secretKeyRef:
          name: postgres-secret
          key: connection-string
          optional: true
    - name: REDIS_URL
      valueFrom:
        secretKeyRef:
          name: redis-secret
          key: connection-string
          optional: true
    - name: APP_SECRET_KEY
      valueFrom:
        secretKeyRef:
          name: kailash-app-secrets
          key: secret-key
          optional: true
EOF
    
    # Wait for pod to be ready
    if kubectl wait --for=condition=Ready pod "$test_pod_name" -n "$APP_NAMESPACE" --timeout=60s &> /dev/null; then
        log_success "Test pod is ready"
        
        # Test environment variables
        local env_vars
        env_vars=$(kubectl exec "$test_pod_name" -n "$APP_NAMESPACE" -- env | grep -E "(DATABASE_URL|REDIS_URL|APP_SECRET_KEY)" | wc -l)
        
        if [[ "$env_vars" -gt 0 ]]; then
            log_success "Application can access $env_vars secret environment variables"
        else
            log_warning "Application cannot access secret environment variables"
        fi
        
        # Test specific secrets
        if kubectl exec "$test_pod_name" -n "$APP_NAMESPACE" -- sh -c 'test -n "$DATABASE_URL"' &> /dev/null; then
            log_success "Database connection string is available"
        else
            log_warning "Database connection string is not available"
        fi
        
        if kubectl exec "$test_pod_name" -n "$APP_NAMESPACE" -- sh -c 'test -n "$REDIS_URL"' &> /dev/null; then
            log_success "Redis connection string is available"
        else
            log_warning "Redis connection string is not available"
        fi
    else
        log_error "Test pod failed to start"
    fi
    
    # Cleanup test pod
    kubectl delete pod "$test_pod_name" -n "$APP_NAMESPACE" --ignore-not-found=true
}

# Test secret rotation
test_secret_rotation() {
    log_info "Testing secret rotation..."
    
    # Check refresh intervals
    local refresh_intervals
    refresh_intervals=$(kubectl get externalsecrets -n "$APP_NAMESPACE" -o jsonpath='{.items[*].spec.refreshInterval}' | tr ' ' '\n' | sort -u)
    
    if [[ -n "$refresh_intervals" ]]; then
        log_success "External secrets have refresh intervals configured:"
        echo "$refresh_intervals" | while read -r interval; do
            log_info "  - $interval"
        done
    else
        log_warning "No refresh intervals found on external secrets"
    fi
    
    # Check for dynamic credentials (short refresh intervals)
    local dynamic_secrets
    dynamic_secrets=$(kubectl get externalsecrets -n "$APP_NAMESPACE" -o json | jq -r '.items[] | select(.spec.refreshInterval | contains("300s") or contains("5m")) | .metadata.name' 2>/dev/null || echo "")
    
    if [[ -n "$dynamic_secrets" ]]; then
        log_success "Dynamic secrets found (5min refresh):"
        echo "$dynamic_secrets" | while read -r secret; do
            log_info "  - $secret"
        done
    else
        log_info "No dynamic secrets found (this is normal for static secrets)"
    fi
}

# Test monitoring and metrics
test_monitoring() {
    log_info "Testing monitoring and metrics..."
    
    # Check if metrics services exist
    if kubectl get service external-secrets-metrics -n "$ESO_NAMESPACE" &> /dev/null; then
        log_success "External Secrets metrics service exists"
    else
        log_warning "External Secrets metrics service not found"
    fi
    
    # Check for Vault metrics
    if kubectl get service vault -n "$VAULT_NAMESPACE" &> /dev/null; then
        log_success "Vault service exists"
        
        # Test metrics endpoint (if accessible)
        if kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- wget -q -O - http://localhost:8200/v1/sys/metrics?format=prometheus 2>/dev/null | head -1 | grep -q "vault_"; then
            log_success "Vault metrics endpoint is accessible"
        else
            log_warning "Vault metrics endpoint is not accessible"
        fi
    else
        log_error "Vault service not found"
    fi
}

# Generate test report
generate_report() {
    log_info "Generating test report..."
    
    local report_file="/tmp/secrets-test-report-$(date +%Y%m%d_%H%M%S).txt"
    
    cat > "$report_file" << EOF
Secrets Management Test Report
=============================
Test Date: $(date)
Cluster: $(kubectl config current-context)

Summary:
- Total Errors: $ERRORS
- Status: $([ $ERRORS -eq 0 ] && echo "PASS" || echo "FAIL")

Components Tested:
- Vault connectivity and status
- Vault authentication methods
- Vault secret engines
- External Secrets Operator
- Secret stores configuration
- External secrets synchronization
- Application secret access
- Secret rotation capabilities
- Monitoring and metrics

$([ $ERRORS -eq 0 ] && echo "✅ All tests passed successfully!" || echo "❌ $ERRORS test(s) failed. Review the output above.")

Recommendations:
- Ensure regular backup of Vault data
- Monitor secret refresh rates and failures
- Set up alerting for Vault seal events
- Implement secret rotation policies
- Review and audit secret access regularly
EOF
    
    log_success "Test report generated: $report_file"
    cat "$report_file"
}

# Display status
show_status() {
    log_info "Current secrets management status:"
    
    echo
    log_info "Vault Pods:"
    kubectl get pods -n "$VAULT_NAMESPACE" -l app.kubernetes.io/name=vault 2>/dev/null || log_warning "Vault not deployed"
    
    echo
    log_info "External Secrets Operator:"
    kubectl get pods -n "$ESO_NAMESPACE" 2>/dev/null || log_warning "External Secrets Operator not deployed"
    
    echo
    log_info "Secret Stores:"
    kubectl get clustersecretstores,secretstores --all-namespaces 2>/dev/null || log_warning "No secret stores found"
    
    echo
    log_info "External Secrets:"
    kubectl get externalsecrets --all-namespaces 2>/dev/null || log_warning "No external secrets found"
    
    echo
    log_info "Generated Secrets:"
    kubectl get secrets --all-namespaces | grep -E "(postgres-secret|redis-secret|kailash-app-secrets)" || log_warning "No generated secrets found"
}

# Main testing function
main() {
    log_info "Starting secrets management testing"
    echo "========================================"
    
    check_prerequisites
    test_vault_connectivity
    test_vault_authentication
    test_secret_engines
    test_external_secrets_operator
    test_secret_stores
    test_external_secrets
    test_secret_access
    test_secret_rotation
    test_monitoring
    
    show_status
    generate_report
    
    echo "========================================"
    if [[ $ERRORS -eq 0 ]]; then
        log_success "All secrets management tests passed!"
        exit 0
    else
        log_error "$ERRORS test(s) failed. Please review and fix the issues."
        exit 1
    fi
}

# Show help
show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Test Vault and External Secrets integration

Options:
    -h, --help              Show this help message
    -v, --verbose           Enable verbose output
    --vault-ns NAMESPACE    Vault namespace (default: vault-system)
    --eso-ns NAMESPACE      External Secrets namespace (default: external-secrets-system)
    --app-ns NAMESPACE      Application namespace (default: default)

Examples:
    $0                      # Run all tests
    $0 -v                   # Run with verbose output
    $0 --vault-ns vault     # Use custom Vault namespace

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
        --vault-ns)
            VAULT_NAMESPACE="$2"
            shift 2
            ;;
        --eso-ns)
            ESO_NAMESPACE="$2"
            shift 2
            ;;
        --app-ns)
            APP_NAMESPACE="$2"
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