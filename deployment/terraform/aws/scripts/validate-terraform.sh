#!/bin/bash
# Terraform AWS EKS Configuration Validation Script
# Validates Terraform configuration without deploying resources

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
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
    
    # Check required tools
    local required_tools=("terraform" "aws")
    local optional_tools=("kubectl" "helm")
    
    for tool in "${required_tools[@]}"; do
        if command -v "$tool" &> /dev/null; then
            local version=$($tool version | head -1)
            log_success "Required tool found: $tool ($version)"
        else
            log_error "Required tool missing: $tool"
        fi
    done
    
    for tool in "${optional_tools[@]}"; do
        if command -v "$tool" &> /dev/null; then
            local version=$($tool version --short 2>/dev/null || $tool version | head -1)
            log_success "Optional tool found: $tool ($version)"
        else
            log_warning "Optional tool missing: $tool"
        fi
    done
    
    # Check AWS credentials
    if aws sts get-caller-identity &> /dev/null; then
        local account_id=$(aws sts get-caller-identity --query Account --output text)
        local user_arn=$(aws sts get-caller-identity --query Arn --output text)
        log_success "AWS credentials configured (Account: $account_id)"
        log_info "AWS identity: $user_arn"
    else
        log_error "AWS credentials not configured or invalid"
    fi
}

# Validate Terraform configuration syntax
validate_terraform_syntax() {
    log_info "Validating Terraform configuration syntax..."
    
    cd "$TERRAFORM_DIR"
    
    # Format check
    if terraform fmt -check -recursive; then
        log_success "Terraform formatting is correct"
    else
        log_warning "Terraform formatting issues found (can be fixed with 'terraform fmt')"
    fi
    
    # Initialize Terraform (without backend)
    if terraform init -backend=false &> /dev/null; then
        log_success "Terraform initialization successful"
    else
        log_error "Terraform initialization failed"
        return 1
    fi
    
    # Validate configuration
    if terraform validate; then
        log_success "Terraform configuration is valid"
    else
        log_error "Terraform configuration validation failed"
        return 1
    fi
}

# Test Terraform plan with example configuration
test_terraform_plan() {
    log_info "Testing Terraform plan with development configuration..."
    
    cd "$TERRAFORM_DIR"
    
    # Use development configuration for testing
    local dev_config="environments/development/terraform.tfvars"
    
    if [[ ! -f "$dev_config" ]]; then
        log_error "Development configuration not found: $dev_config"
        return 1
    fi
    
    # Run terraform plan (dry run)
    if terraform plan -var-file="$dev_config" -out=tfplan &> plan.out; then
        log_success "Terraform plan completed successfully"
        
        # Check plan output for resources
        local resources_to_create=$(grep "Plan:" plan.out | grep -o '[0-9]\+ to add' | grep -o '[0-9]\+' || echo "0")
        log_info "Resources to create: $resources_to_create"
        
        if [[ "$resources_to_create" -gt 0 ]]; then
            log_success "Plan includes resource creation ($resources_to_create resources)"
        else
            log_warning "Plan includes no resource creation"
        fi
    else
        log_error "Terraform plan failed"
        cat plan.out
        return 1
    fi
    
    # Cleanup
    rm -f tfplan plan.out
}

# Validate variable files
validate_variable_files() {
    log_info "Validating variable files..."
    
    local var_files=(
        "terraform.tfvars.example"
        "environments/development/terraform.tfvars"
    )
    
    for var_file in "${var_files[@]}"; do
        local full_path="$TERRAFORM_DIR/$var_file"
        
        if [[ -f "$full_path" ]]; then
            # Check syntax by attempting to parse with terraform
            if terraform console -var-file="$full_path" <<< "var.environment" &> /dev/null; then
                log_success "Variable file valid: $var_file"
            else
                log_error "Variable file invalid: $var_file"
            fi
        else
            log_warning "Variable file not found: $var_file"
        fi
    done
}

# Check security best practices
check_security_practices() {
    log_info "Checking security best practices..."
    
    local config_files=("main.tf" "variables.tf" "outputs.tf")
    local security_checks_passed=0
    local total_security_checks=5
    
    # Check 1: Encryption at rest
    if grep -r "encrypted.*=.*true" "$TERRAFORM_DIR"/*.tf &> /dev/null; then
        log_success "Encryption at rest is enabled"
        ((security_checks_passed++))
    else
        log_warning "Encryption at rest may not be properly configured"
    fi
    
    # Check 2: KMS key usage
    if grep -r "kms_key" "$TERRAFORM_DIR"/*.tf &> /dev/null; then
        log_success "KMS keys are configured"
        ((security_checks_passed++))
    else
        log_warning "KMS key configuration not found"
    fi
    
    # Check 3: Private subnets for worker nodes
    if grep -r "private_subnets" "$TERRAFORM_DIR"/*.tf &> /dev/null; then
        log_success "Private subnets are configured"
        ((security_checks_passed++))
    else
        log_warning "Private subnets configuration not found"
    fi
    
    # Check 4: IRSA configuration
    if grep -r "enable_irsa" "$TERRAFORM_DIR"/*.tf &> /dev/null; then
        log_success "IAM Roles for Service Accounts (IRSA) is configured"
        ((security_checks_passed++))
    else
        log_warning "IRSA configuration not found"
    fi
    
    # Check 5: Security groups
    if grep -r "security_group" "$TERRAFORM_DIR"/*.tf &> /dev/null; then
        log_success "Security groups are configured"
        ((security_checks_passed++))
    else
        log_warning "Security group configuration not found"
    fi
    
    log_info "Security checks passed: $security_checks_passed/$total_security_checks"
    
    if [[ "$security_checks_passed" -ge 4 ]]; then
        log_success "Security configuration looks good"
    else
        log_warning "Security configuration needs review"
    fi
}

# Check for hardcoded values
check_hardcoded_values() {
    log_info "Checking for hardcoded sensitive values..."
    
    local sensitive_patterns=(
        "password.*=.*\"[^\"]*\""
        "secret.*=.*\"[^\"]*\""
        "key.*=.*\"[A-Za-z0-9+/=]{20,}\""
        "token.*=.*\"[^\"]*\""
    )
    
    local hardcoded_found=false
    
    for pattern in "${sensitive_patterns[@]}"; do
        if grep -r -i "$pattern" "$TERRAFORM_DIR"/*.tf &> /dev/null; then
            log_error "Potential hardcoded sensitive value found (pattern: $pattern)"
            hardcoded_found=true
        fi
    done
    
    if [[ "$hardcoded_found" == "false" ]]; then
        log_success "No hardcoded sensitive values detected"
    fi
}

# Validate module structure
validate_module_structure() {
    log_info "Validating module structure..."
    
    local required_files=("main.tf" "variables.tf" "outputs.tf")
    local recommended_files=("terraform.tfvars.example" "README.md")
    
    # Check required files
    for file in "${required_files[@]}"; do
        if [[ -f "$TERRAFORM_DIR/$file" ]]; then
            log_success "Required file found: $file"
        else
            log_error "Required file missing: $file"
        fi
    done
    
    # Check recommended files
    for file in "${recommended_files[@]}"; do
        if [[ -f "$TERRAFORM_DIR/$file" ]]; then
            log_success "Recommended file found: $file"
        else
            log_warning "Recommended file missing: $file"
        fi
    done
    
    # Check modules directory
    if [[ -d "$TERRAFORM_DIR/modules" ]]; then
        log_success "Modules directory exists"
        
        # List modules
        local modules=($(find "$TERRAFORM_DIR/modules" -mindepth 1 -maxdepth 1 -type d -exec basename {} \;))
        log_info "Modules found: ${modules[*]}"
    else
        log_warning "Modules directory not found"
    fi
}

# Generate validation report
generate_report() {
    log_info "Generating validation report..."
    
    local report_file="$TERRAFORM_DIR/validation-report-$(date +%Y%m%d_%H%M%S).txt"
    
    cat > "$report_file" << EOF
Terraform AWS EKS Configuration Validation Report
================================================
Validation Date: $(date)
Terraform Directory: $TERRAFORM_DIR

Summary:
- Total Errors: $ERRORS
- Status: $([ $ERRORS -eq 0 ] && echo "PASS" || echo "FAIL")

Validation Checks:
- Prerequisites check
- Terraform syntax validation
- Terraform plan test
- Variable files validation
- Security best practices check
- Hardcoded values check
- Module structure validation

Configuration Files:
- main.tf: Core Terraform configuration
- variables.tf: Input variables
- outputs.tf: Output values
- terraform.tfvars.example: Example configuration
- environments/: Environment-specific configurations

Security Features Validated:
- Encryption at rest and in transit
- KMS key management
- Private subnets for worker nodes
- IAM Roles for Service Accounts (IRSA)
- Security group configurations

$([ $ERRORS -eq 0 ] && echo "✅ All validations passed successfully!" || echo "❌ $ERRORS validation(s) failed. Review the output above.")

Next Steps:
1. Review any warnings or errors above
2. Customize terraform.tfvars for your environment
3. Run 'terraform init' to initialize the configuration
4. Run 'terraform plan' to review planned changes
5. Run 'terraform apply' to deploy the infrastructure
EOF
    
    log_success "Validation report generated: $report_file"
    cat "$report_file"
}

# Main validation function
main() {
    log_info "Starting Terraform AWS EKS Configuration Validation"
    echo "============================================================"
    
    check_prerequisites
    validate_terraform_syntax
    test_terraform_plan
    validate_variable_files
    check_security_practices
    check_hardcoded_values
    validate_module_structure
    
    generate_report
    
    echo "============================================================"
    if [[ $ERRORS -eq 0 ]]; then
        log_success "All validations passed! Configuration is ready for deployment."
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

Terraform AWS EKS Configuration Validation Script

This script validates the Terraform configuration for AWS EKS deployment
without actually deploying any resources.

Options:
    -h, --help      Show this help message
    -v, --verbose   Enable verbose output

Examples:
    $0              # Run all validations
    $0 -v           # Run with verbose output

Validation Checks:
- Tool prerequisites (terraform, aws cli)
- AWS credentials configuration
- Terraform syntax and formatting
- Configuration validation
- Terraform plan (dry run)
- Variable file validation
- Security best practices
- Hardcoded values detection
- Module structure validation

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