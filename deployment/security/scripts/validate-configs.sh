#!/bin/bash
# Local Configuration Validation Script
# Tests configuration files without requiring a Kubernetes cluster

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

# Validate YAML syntax
validate_yaml_syntax() {
    local file="$1"
    local filename=$(basename "$file")
    
    if ! command -v yq &> /dev/null && ! python3 -c "import yaml" &> /dev/null; then
        log_warning "Neither yq nor python3+yaml available, skipping YAML validation for $filename"
        return 0
    fi
    
    if command -v yq &> /dev/null; then
        if yq eval '.' "$file" &> /dev/null; then
            log_success "YAML syntax valid: $filename"
            return 0
        else
            log_error "YAML syntax invalid: $filename"
            return 1
        fi
    else
        if python3 -c "import yaml; yaml.safe_load(open('$file'))" &> /dev/null; then
            log_success "YAML syntax valid: $filename"
            return 0
        else
            log_error "YAML syntax invalid: $filename"
            return 1
        fi
    fi
}

# Validate Kubernetes manifest structure
validate_k8s_manifest() {
    local file="$1"
    local filename=$(basename "$file")
    
    # Check for required fields
    local required_fields=("apiVersion" "kind" "metadata")
    
    for field in "${required_fields[@]}"; do
        if grep -q "^$field:" "$file"; then
            continue
        else
            log_error "Missing required field '$field' in $filename"
            return 1
        fi
    done
    
    log_success "Kubernetes manifest structure valid: $filename"
    return 0
}

# Validate API server configuration
validate_api_server_config() {
    log_info "Validating API Server configuration..."
    
    local config_file="$DEPLOYMENT_DIR/security/cis-benchmarks/api-server/kube-apiserver.yaml"
    
    if [[ ! -f "$config_file" ]]; then
        log_error "API Server config not found: $config_file"
        return 1
    fi
    
    # Check for critical CIS controls
    local cis_controls=(
        "anonymous-auth=false"
        "authorization-mode=Node,RBAC"
        "encryption-provider-config"
        "audit-log-path"
        "tls-min-version=VersionTLS12"
    )
    
    local found_controls=0
    
    for control in "${cis_controls[@]}"; do
        if grep -q "$control" "$config_file"; then
            log_success "Found CIS control: $control"
            ((found_controls++))
        else
            log_error "Missing CIS control: $control"
        fi
    done
    
    if [[ "$found_controls" -eq "${#cis_controls[@]}" ]]; then
        log_success "API Server CIS controls validation passed"
        return 0
    else
        log_error "API Server CIS controls validation failed ($found_controls/${#cis_controls[@]})"
        return 1
    fi
}

# Validate audit policy
validate_audit_policy() {
    log_info "Validating Audit Policy..."
    
    local policy_file="$DEPLOYMENT_DIR/security/cis-benchmarks/api-server/audit-policy.yaml"
    
    if [[ ! -f "$policy_file" ]]; then
        log_error "Audit policy not found: $policy_file"
        return 1
    fi
    
    # Check for required audit levels
    local audit_levels=("RequestResponse" "Request" "Metadata")
    local found_levels=0
    
    for level in "${audit_levels[@]}"; do
        if grep -q "level: $level" "$policy_file"; then
            log_success "Found audit level: $level"
            ((found_levels++))
        else
            log_warning "Audit level not found: $level"
        fi
    done
    
    # Check for sensitive resource auditing
    local sensitive_resources=("secrets" "configmaps" "rbac")
    local found_resources=0
    
    for resource in "${sensitive_resources[@]}"; do
        if grep -q "$resource" "$policy_file"; then
            log_success "Auditing sensitive resource: $resource"
            ((found_resources++))
        else
            log_warning "Not auditing sensitive resource: $resource"
        fi
    done
    
    if [[ "$found_levels" -ge 2 && "$found_resources" -ge 2 ]]; then
        log_success "Audit policy validation passed"
        return 0
    else
        log_error "Audit policy validation failed"
        return 1
    fi
}

# Validate encryption configuration
validate_encryption_config() {
    log_info "Validating Encryption Configuration..."
    
    local encryption_file="$DEPLOYMENT_DIR/security/cis-benchmarks/api-server/encryption-config.yaml"
    
    if [[ ! -f "$encryption_file" ]]; then
        log_error "Encryption config not found: $encryption_file"
        return 1
    fi
    
    # Check for encryption providers
    if grep -q "aescbc:" "$encryption_file"; then
        log_success "Found AES-CBC encryption provider"
    else
        log_error "AES-CBC encryption provider not found"
        return 1
    fi
    
    # Check for encrypted resources
    local encrypted_resources=("secrets" "configmaps")
    local found_encrypted=0
    
    for resource in "${encrypted_resources[@]}"; do
        if grep -q "$resource" "$encryption_file"; then
            log_success "Encryption configured for: $resource"
            ((found_encrypted++))
        else
            log_error "Encryption not configured for: $resource"
        fi
    done
    
    if [[ "$found_encrypted" -eq "${#encrypted_resources[@]}" ]]; then
        log_success "Encryption configuration validation passed"
        return 0
    else
        log_error "Encryption configuration validation failed"
        return 1
    fi
}

# Validate admission configuration
validate_admission_config() {
    log_info "Validating Admission Configuration..."
    
    local admission_file="$DEPLOYMENT_DIR/security/cis-benchmarks/api-server/admission-config.yaml"
    
    if [[ ! -f "$admission_file" ]]; then
        log_error "Admission config not found: $admission_file"
        return 1
    fi
    
    # Check for admission controllers
    local admission_controllers=("EventRateLimit" "ResourceQuota" "PodSecurityPolicy")
    local found_controllers=0
    
    for controller in "${admission_controllers[@]}"; do
        if grep -q "name: $controller" "$admission_file"; then
            log_success "Found admission controller: $controller"
            ((found_controllers++))
        else
            log_warning "Admission controller not found: $controller"
        fi
    done
    
    if [[ "$found_controllers" -ge 2 ]]; then
        log_success "Admission configuration validation passed"
        return 0
    else
        log_error "Admission configuration validation failed"
        return 1
    fi
}

# Test script execution
test_script_execution() {
    log_info "Testing script executability..."
    
    local test_script="$DEPLOYMENT_DIR/security/scripts/cis-benchmark-test.sh"
    
    if [[ -x "$test_script" ]]; then
        log_success "CIS benchmark test script is executable"
        
        # Test help functionality
        if "$test_script" --help &> /dev/null; then
            log_success "CIS benchmark test script help works"
        else
            log_warning "CIS benchmark test script help may have issues"
        fi
    else
        log_error "CIS benchmark test script is not executable"
        return 1
    fi
}

# Check for required tools
check_required_tools() {
    log_info "Checking for required tools..."
    
    local tools=("bash" "grep" "curl")
    local optional_tools=("kubectl" "yq" "python3")
    
    # Required tools
    for tool in "${tools[@]}"; do
        if command -v "$tool" &> /dev/null; then
            log_success "Required tool found: $tool"
        else
            log_error "Required tool missing: $tool"
        fi
    done
    
    # Optional tools
    for tool in "${optional_tools[@]}"; do
        if command -v "$tool" &> /dev/null; then
            log_success "Optional tool found: $tool"
        else
            log_warning "Optional tool missing: $tool"
        fi
    done
}

# Generate validation report
generate_report() {
    log_info "Generating validation report..."
    
    local report_file="$SCRIPT_DIR/validation-report-$(date +%Y%m%d_%H%M%S).txt"
    
    cat > "$report_file" << EOF
CIS Benchmark Configuration Validation Report
============================================
Validation Date: $(date)
Script: $(basename "$0")

Summary:
- Total Errors: $ERRORS
- Status: $([ $ERRORS -eq 0 ] && echo "PASS" || echo "FAIL")

Configuration Files Validated:
- API Server Configuration
- Audit Policy
- Encryption Configuration  
- Admission Configuration

Tools Check:
- Required tools availability
- Script executability

$([ $ERRORS -eq 0 ] && echo "✅ All validations passed successfully!" || echo "❌ $ERRORS validation(s) failed. Review the output above.")
EOF
    
    log_success "Validation report generated: $report_file"
    cat "$report_file"
}

# Main validation function
main() {
    log_info "Starting CIS Benchmark Configuration Validation"
    echo "================================================"
    
    # Check tools first
    check_required_tools
    
    # Validate configuration files
    local config_files=(
        "$DEPLOYMENT_DIR/security/cis-benchmarks/api-server/kube-apiserver.yaml"
        "$DEPLOYMENT_DIR/security/cis-benchmarks/api-server/audit-policy.yaml"
        "$DEPLOYMENT_DIR/security/cis-benchmarks/api-server/encryption-config.yaml"
        "$DEPLOYMENT_DIR/security/cis-benchmarks/api-server/admission-config.yaml"
    )
    
    # Validate YAML syntax for all files
    for config_file in "${config_files[@]}"; do
        if [[ -f "$config_file" ]]; then
            validate_yaml_syntax "$config_file"
            validate_k8s_manifest "$config_file"
        else
            log_error "Configuration file not found: $(basename "$config_file")"
        fi
    done
    
    # Validate specific configurations
    validate_api_server_config
    validate_audit_policy
    validate_encryption_config
    validate_admission_config
    
    # Test script functionality
    test_script_execution
    
    # Generate final report
    generate_report
    
    echo "================================================"
    if [[ $ERRORS -eq 0 ]]; then
        log_success "All validations passed! Configurations are ready for deployment."
        exit 0
    else
        log_error "$ERRORS validation error(s) found. Please fix the issues before deployment."
        exit 1
    fi
}

# Show help
show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Local Configuration Validation Script for CIS Benchmark Implementation

This script validates CIS benchmark configuration files without requiring 
a Kubernetes cluster connection.

Options:
    -h, --help      Show this help message
    -v, --verbose   Enable verbose output

Examples:
    $0              # Run all validations
    $0 -v           # Run with verbose output

Validated Components:
- YAML syntax
- Kubernetes manifest structure
- API Server CIS controls
- Audit policy configuration
- Encryption at rest settings
- Admission controller setup
- Script executability

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
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Run main function
main "$@"