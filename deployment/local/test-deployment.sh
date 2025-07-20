#!/bin/bash
# Test Enterprise Deployment Configurations Locally
# Uses Docker Compose to validate configurations without Kubernetes

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
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.test.yml"
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

# Initialize test environment
init_test_env() {
    log_info "Initializing test environment..."
    
    # Create results directory
    mkdir -p "$RESULTS_DIR"
    
    # Create test report file
    cat > "$RESULTS_DIR/test-report-$TIMESTAMP.txt" << EOF
Enterprise Deployment Test Report
=================================
Test Date: $(date)
Test Type: Local Docker Validation

Test Summary:
EOF
    
    log_success "Test environment initialized"
}

# Test Docker Compose configuration
test_docker_compose() {
    log_info "Testing Docker Compose configuration..."
    
    if docker-compose -f "$COMPOSE_FILE" config &> /dev/null; then
        log_success "Docker Compose configuration is valid"
        echo "- Docker Compose: PASS" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    else
        log_error "Docker Compose configuration is invalid"
        echo "- Docker Compose: FAIL" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
        return 1
    fi
}

# Start test services
start_services() {
    log_info "Starting test services..."
    
    # Start services
    if docker-compose -f "$COMPOSE_FILE" up -d; then
        log_success "Test services started"
        
        # Wait for services to be healthy
        log_info "Waiting for services to be healthy..."
        local max_wait=60
        local wait_time=0
        
        while [[ $wait_time -lt $max_wait ]]; do
            if docker-compose -f "$COMPOSE_FILE" ps | grep -q "unhealthy"; then
                sleep 5
                wait_time=$((wait_time + 5))
                log_info "Waiting for services... ($wait_time/$max_wait seconds)"
            else
                break
            fi
        done
        
        # Show service status
        docker-compose -f "$COMPOSE_FILE" ps
        
        echo "- Services startup: PASS" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    else
        log_error "Failed to start test services"
        echo "- Services startup: FAIL" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
        return 1
    fi
}

# Test PostgreSQL security
test_postgres_security() {
    log_info "Testing PostgreSQL security configuration..."
    
    # Test SSL connection
    if docker exec kailash-test-postgres psql -U kailash_user -d kailash_test -c "SHOW ssl;" | grep -q "on"; then
        log_success "PostgreSQL SSL is enabled"
        echo "- PostgreSQL SSL: PASS" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    else
        log_error "PostgreSQL SSL is not enabled"
        echo "- PostgreSQL SSL: FAIL" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    fi
    
    # Test connection limits
    if docker exec kailash-test-postgres psql -U kailash_user -d kailash_test -c "SHOW max_connections;" | grep -q "100"; then
        log_success "PostgreSQL connection limit is set"
        echo "- PostgreSQL max_connections: PASS" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    else
        log_warning "PostgreSQL connection limit not as expected"
        echo "- PostgreSQL max_connections: WARN" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    fi
}

# Test Redis security
test_redis_security() {
    log_info "Testing Redis security configuration..."
    
    # Test authentication requirement
    if docker exec kailash-test-redis redis-cli ping 2>&1 | grep -q "NOAUTH"; then
        log_success "Redis requires authentication"
        echo "- Redis authentication: PASS" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    else
        log_error "Redis does not require authentication"
        echo "- Redis authentication: FAIL" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    fi
    
    # Test authenticated connection
    if docker exec kailash-test-redis redis-cli -a secure_redis_password ping | grep -q "PONG"; then
        log_success "Redis authenticated connection works"
        echo "- Redis auth connection: PASS" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    else
        log_error "Redis authenticated connection failed"
        echo "- Redis auth connection: FAIL" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    fi
}

# Test Vault
test_vault() {
    log_info "Testing Vault configuration..."
    
    # Test Vault status
    if docker exec kailash-test-vault vault status | grep -q "Initialized.*true"; then
        log_success "Vault is initialized"
        echo "- Vault initialized: PASS" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    else
        log_error "Vault is not initialized"
        echo "- Vault initialized: FAIL" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    fi
    
    # Test Vault unsealed
    if docker exec kailash-test-vault vault status | grep -q "Sealed.*false"; then
        log_success "Vault is unsealed"
        echo "- Vault unsealed: PASS" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    else
        log_error "Vault is sealed"
        echo "- Vault unsealed: FAIL" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    fi
    
    # Create test secret in Vault
    if docker exec kailash-test-vault vault kv put secret/test-secret value=test-value; then
        log_success "Can write secrets to Vault"
        echo "- Vault write secret: PASS" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    else
        log_error "Cannot write secrets to Vault"
        echo "- Vault write secret: FAIL" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    fi
}

# Test security configurations
test_security_configs() {
    log_info "Testing security configurations..."
    
    # Run validation scripts
    "$PROJECT_ROOT/deployment/security/scripts/validate-configs.sh" > "$RESULTS_DIR/cis-validation-$TIMESTAMP.txt" 2>&1
    
    if grep -q "All validations passed" "$RESULTS_DIR/cis-validation-$TIMESTAMP.txt"; then
        log_success "CIS benchmark configurations are valid"
        echo "- CIS configurations: PASS" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    else
        log_error "CIS benchmark configurations have issues"
        echo "- CIS configurations: FAIL" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    fi
}

# Test container security scanning
test_container_scanning() {
    log_info "Testing container security scanning..."
    
    # Wait for Trivy scan to complete
    sleep 10
    
    if [[ -f "$SCRIPT_DIR/scan-results/scan-report.json" ]]; then
        log_success "Container scan completed"
        echo "- Container scanning: PASS" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
        
        # Check for vulnerabilities
        local vuln_count=$(jq '.Results[0].Vulnerabilities | length' "$SCRIPT_DIR/scan-results/scan-report.json" 2>/dev/null || echo "0")
        log_info "Found $vuln_count vulnerabilities in test image"
    else
        log_warning "Container scan report not found"
        echo "- Container scanning: WARN" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    fi
}

# Test network connectivity
test_network_connectivity() {
    log_info "Testing network connectivity between services..."
    
    # Test app to postgres connectivity
    if docker exec kailash-test-app nc -zv postgres 5432 2>&1 | grep -q "succeeded"; then
        log_success "App can connect to PostgreSQL"
        echo "- App->PostgreSQL connectivity: PASS" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    else
        log_error "App cannot connect to PostgreSQL"
        echo "- App->PostgreSQL connectivity: FAIL" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    fi
    
    # Test app to redis connectivity
    if docker exec kailash-test-app nc -zv redis 6379 2>&1 | grep -q "succeeded"; then
        log_success "App can connect to Redis"
        echo "- App->Redis connectivity: PASS" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    else
        log_error "App cannot connect to Redis"
        echo "- App->Redis connectivity: FAIL" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    fi
    
    # Test app to vault connectivity
    if docker exec kailash-test-app nc -zv vault 8200 2>&1 | grep -q "succeeded"; then
        log_success "App can connect to Vault"
        echo "- App->Vault connectivity: PASS" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    else
        log_error "App cannot connect to Vault"
        echo "- App->Vault connectivity: FAIL" >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
    fi
}

# Generate final report
generate_report() {
    log_info "Generating final test report..."
    
    # Add summary to report
    cat >> "$RESULTS_DIR/test-report-$TIMESTAMP.txt" << EOF

Test Details:
- PostgreSQL security features tested
- Redis authentication tested
- Vault initialization and secret management tested
- CIS benchmark configurations validated
- Container security scanning performed
- Network connectivity verified

Recommendations:
1. Review any failed tests and fix configurations
2. Ensure all security features are enabled in production
3. Set strong passwords for all services
4. Enable encryption at rest and in transit
5. Implement regular security scanning

Test artifacts saved in: $RESULTS_DIR
EOF
    
    # Display report
    log_success "Test report generated:"
    cat "$RESULTS_DIR/test-report-$TIMESTAMP.txt"
}

# Cleanup test environment
cleanup() {
    log_info "Cleaning up test environment..."
    
    # Stop and remove containers
    docker-compose -f "$COMPOSE_FILE" down -v
    
    # Remove test artifacts
    rm -rf "$SCRIPT_DIR/scan-results"
    
    log_success "Cleanup completed"
}

# Main execution
main() {
    log_info "Starting enterprise deployment testing"
    echo "========================================"
    
    init_test_env
    test_docker_compose
    start_services
    
    # Run tests
    test_postgres_security
    test_redis_security
    test_vault
    test_security_configs
    test_container_scanning
    test_network_connectivity
    
    generate_report
    
    echo "========================================"
    log_success "Testing completed!"
}

# Show help
show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Test enterprise deployment configurations locally using Docker

Options:
    -h, --help      Show this help message
    -c, --cleanup   Cleanup test environment only
    -k, --keep      Keep services running after tests

Examples:
    $0              # Run all tests and cleanup
    $0 --keep       # Run tests but keep services running
    $0 --cleanup    # Cleanup only

EOF
}

# Parse command line arguments
CLEANUP_ONLY="false"
KEEP_SERVICES="false"

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -c|--cleanup)
            CLEANUP_ONLY="true"
            shift
            ;;
        -k|--keep)
            KEEP_SERVICES="true"
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Execute based on options
if [[ "$CLEANUP_ONLY" == "true" ]]; then
    cleanup
    exit 0
fi

# Set trap for cleanup (unless --keep is specified)
if [[ "$KEEP_SERVICES" != "true" ]]; then
    trap cleanup EXIT
fi

# Run main function
main "$@"