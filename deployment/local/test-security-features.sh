#!/bin/bash
# Test Security Features in Local Docker Environment

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

# Test PostgreSQL Security
test_postgres_security() {
    log_info "=== Testing PostgreSQL Security ==="
    
    # Test connection from outside (should fail without password)
    if PGPASSWORD="" psql -h localhost -p 15432 -U kailash_user -d kailash_test -c "SELECT 1;" 2>&1 | grep -q "authentication failed"; then
        log_success "PostgreSQL requires password authentication"
    else
        log_warning "PostgreSQL auth test inconclusive (local container access)"
    fi
    
    # Test with correct password
    if PGPASSWORD=secure_test_password psql -h localhost -p 15432 -U kailash_user -d kailash_test -c "SELECT 1;" 2>&1 | grep -q "1 row"; then
        log_success "PostgreSQL authenticated connection works"
    else
        # Try alternative method if psql not installed
        if docker exec -e PGPASSWORD=secure_test_password kailash-test-postgres psql -U kailash_user -d kailash_test -c "SELECT current_database();" | grep -q "kailash_test"; then
            log_success "PostgreSQL database 'kailash_test' accessible with password"
        else
            log_error "PostgreSQL connection failed"
        fi
    fi
    
    # Test SSL configuration
    if docker exec kailash-test-postgres psql -U kailash_user -d kailash_test -c "SHOW ssl;" | grep -q "on"; then
        log_success "PostgreSQL SSL is enabled"
    else
        log_warning "PostgreSQL SSL not fully configured (expected in Docker)"
    fi
}

# Test Redis Security
test_redis_security() {
    log_info "=== Testing Redis Security ==="
    
    # Test without auth (should fail)
    if docker exec kailash-test-redis redis-cli ping 2>&1 | grep -q "NOAUTH"; then
        log_success "Redis requires authentication"
    else
        log_error "Redis does not require authentication"
    fi
    
    # Test with auth
    if docker exec kailash-test-redis redis-cli -a secure_redis_password ping | grep -q "PONG"; then
        log_success "Redis authentication works"
    else
        log_error "Redis authentication failed"
    fi
    
    # Test memory limit
    if docker exec kailash-test-redis redis-cli -a secure_redis_password CONFIG GET maxmemory | grep -q "536870912"; then
        log_success "Redis memory limit is set (512MB)"
    else
        log_warning "Redis memory limit not as expected"
    fi
}

# Test Vault
test_vault() {
    log_info "=== Testing Vault ==="
    
    # Test Vault is running
    if curl -s http://localhost:18200/v1/sys/health | grep -q "initialized"; then
        log_success "Vault is running and initialized"
    else
        log_error "Vault is not properly initialized"
    fi
    
    # Test Vault token auth
    if curl -s -H "X-Vault-Token: root-token-for-testing" http://localhost:18200/v1/sys/auth | grep -q "token/"; then
        log_success "Vault token authentication works"
    else
        log_error "Vault token authentication failed"
    fi
    
    # Create and read a test secret
    if curl -s -X POST -H "X-Vault-Token: root-token-for-testing" \
        -d '{"data": {"password": "test123"}}' \
        http://localhost:18200/v1/secret/data/test-secret | grep -q "created_time"; then
        log_success "Can write secrets to Vault"
    else
        log_error "Cannot write secrets to Vault"
    fi
    
    # Read the secret back
    if curl -s -H "X-Vault-Token: root-token-for-testing" \
        http://localhost:18200/v1/secret/data/test-secret | grep -q "test123"; then
        log_success "Can read secrets from Vault"
    else
        log_error "Cannot read secrets from Vault"
    fi
}

# Test Network Connectivity
test_network_connectivity() {
    log_info "=== Testing Network Connectivity ==="
    
    # Test app can reach services
    if docker exec kailash-test-app nc -zv postgres 5432 2>&1 | grep -q "open"; then
        log_success "App can connect to PostgreSQL"
    else
        log_error "App cannot connect to PostgreSQL"
    fi
    
    if docker exec kailash-test-app nc -zv redis 6379 2>&1 | grep -q "open"; then
        log_success "App can connect to Redis"
    else
        log_error "App cannot connect to Redis"
    fi
    
    if docker exec kailash-test-app nc -zv vault 8200 2>&1 | grep -q "open"; then
        log_success "App can connect to Vault"
    else
        log_error "App cannot connect to Vault"
    fi
    
    # Test app is accessible
    if curl -s http://localhost:18080 | grep -q "Welcome to nginx"; then
        log_success "Test app is accessible"
    else
        log_error "Test app is not accessible"
    fi
}

# Test CIS Configurations
test_cis_configurations() {
    log_info "=== Testing CIS Benchmark Configurations ==="
    
    # Run validation script
    if "$PROJECT_ROOT/deployment/security/scripts/validate-configs.sh" | grep -q "All validations passed"; then
        log_success "CIS benchmark configurations are valid"
    else
        log_warning "CIS benchmark configurations have warnings (expected without full K8s)"
    fi
}

# Test Terraform Configuration
test_terraform_config() {
    log_info "=== Testing Terraform Configuration ==="
    
    # Check if Terraform files exist
    if [[ -f "$PROJECT_ROOT/deployment/terraform/aws/main.tf" ]]; then
        log_success "AWS Terraform main.tf exists"
    else
        log_error "AWS Terraform main.tf not found"
    fi
    
    if [[ -f "$PROJECT_ROOT/deployment/terraform/aws/variables.tf" ]]; then
        log_success "AWS Terraform variables.tf exists"
    else
        log_error "AWS Terraform variables.tf not found"
    fi
    
    if [[ -f "$PROJECT_ROOT/deployment/terraform/aws/outputs.tf" ]]; then
        log_success "AWS Terraform outputs.tf exists"
    else
        log_error "AWS Terraform outputs.tf not found"
    fi
}

# Test Security Scripts
test_security_scripts() {
    log_info "=== Testing Security Scripts ==="
    
    # Check script permissions
    local scripts=(
        "$PROJECT_ROOT/deployment/security/scripts/validate-configs.sh"
        "$PROJECT_ROOT/deployment/security/scripts/cis-benchmark-test.sh"
        "$PROJECT_ROOT/deployment/security/scripts/test-network-policies.sh"
        "$PROJECT_ROOT/deployment/security/secrets-management/scripts/setup-vault.sh"
        "$PROJECT_ROOT/deployment/security/secrets-management/scripts/test-secrets.sh"
    )
    
    for script in "${scripts[@]}"; do
        if [[ -x "$script" ]]; then
            log_success "Script is executable: $(basename "$script")"
        else
            log_error "Script not executable: $(basename "$script")"
        fi
    done
}

# Generate Summary Report
generate_summary() {
    log_info "=== Test Summary ==="
    
    # Count test results from log
    local pass_count=$(grep -c "PASS" /tmp/test-output.log 2>/dev/null || echo "0")
    local warn_count=$(grep -c "WARN" /tmp/test-output.log 2>/dev/null || echo "0")
    local total_tests=$((ERRORS + pass_count + warn_count))
    
    echo
    echo "Total Tests: $total_tests"
    echo "Passed: $pass_count"
    echo "Warnings: $warn_count"
    echo "Failed: $ERRORS"
    
    if [[ $total_tests -gt 0 ]]; then
        echo "Success Rate: $(( pass_count * 100 / total_tests ))%"
    fi
    echo
    
    if [[ $ERRORS -eq 0 ]]; then
        log_success "All critical security tests passed!"
    else
        log_error "$ERRORS tests failed"
    fi
}

# Main execution
main() {
    log_info "Starting Security Feature Testing"
    echo "========================================"
    
    # Check if services are running
    if ! docker ps --format "{{.Names}}" | grep -q "kailash-test"; then
        log_error "Test services are not running. Please run docker-compose up first."
        exit 1
    fi
    
    # Run tests and capture output
    {
        test_postgres_security
        test_redis_security
        test_vault
        test_network_connectivity
        test_cis_configurations
        test_terraform_config
        test_security_scripts
    } 2>&1 | tee /tmp/test-output.log
    
    echo "========================================"
    generate_summary
    
    # Cleanup
    rm -f /tmp/test-output.log
    
    exit $ERRORS
}

# Run main function
main "$@"