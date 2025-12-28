#!/bin/bash
# Automated Security Scanning Script for Kaizen AI Framework
# Usage: ./run_security_scan.sh [--full] [--report-dir DIR]
#
# This script orchestrates multiple security scanning tools to provide
# comprehensive security validation for the Kaizen AI Framework.
#
# Scan Types:
#   1. Dependency Scanning (safety, pip-audit)
#   2. Secret Scanning (truffleHog, detect-secrets)
#   3. Static Analysis (bandit, semgrep)
#   4. Container Scanning (trivy)
#   5. License Compliance (pip-licenses)
#
# Requirements:
#   - Python 3.9+
#   - pip, pipx, or uv package manager
#   - Docker (for container scanning)
#   - Internet connection (for vulnerability database updates)
#
# Exit Codes:
#   0 - No vulnerabilities found
#   1 - Critical vulnerabilities found
#   2 - High severity vulnerabilities found
#   3 - Medium severity vulnerabilities found
#   4 - Script execution error

set -euo pipefail  # Exit on error, undefined variable, or pipe failure

# Color codes for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPORT_DIR="${PROJECT_ROOT}/security_scan_results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FULL_SCAN=false
EXIT_CODE=0

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --full)
            FULL_SCAN=true
            shift
            ;;
        --report-dir)
            REPORT_DIR="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [--full] [--report-dir DIR]"
            echo ""
            echo "Options:"
            echo "  --full          Run comprehensive scan (slower, more thorough)"
            echo "  --report-dir    Directory for scan reports (default: ./security_scan_results)"
            echo "  --help          Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Run '$0 --help' for usage information"
            exit 4
            ;;
    esac
done

# Create report directory
mkdir -p "$REPORT_DIR"

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Install missing tools
install_tools() {
    log "Checking required security tools..."

    local missing_tools=()

    # Check Python tools
    if ! command_exists safety; then
        missing_tools+=("safety")
    fi

    if ! command_exists bandit; then
        missing_tools+=("bandit")
    fi

    if ! command_exists pip-audit; then
        missing_tools+=("pip-audit")
    fi

    if ! command_exists detect-secrets; then
        missing_tools+=("detect-secrets")
    fi

    if ! command_exists semgrep; then
        missing_tools+=("semgrep")
    fi

    if ! command_exists trivy; then
        log_warning "trivy not found (container scanning will be skipped)"
        log_warning "Install: https://aquasecurity.github.io/trivy/latest/getting-started/installation/"
    fi

    # Install missing Python tools
    if [ ${#missing_tools[@]} -gt 0 ]; then
        log "Installing missing tools: ${missing_tools[*]}"
        pip install --quiet "${missing_tools[@]}"
        log_success "Tools installed successfully"
    else
        log_success "All required tools are installed"
    fi
}

# 1. Dependency Scanning
scan_dependencies() {
    log "Running dependency vulnerability scanning..."

    cd "$PROJECT_ROOT"

    # safety check
    log "  → Running safety (PyPI vulnerability database)..."
    if safety check --json --output "$REPORT_DIR/safety_report_${TIMESTAMP}.json" 2>/dev/null; then
        log_success "safety: No known vulnerabilities found"
    else
        local vuln_count=$(jq '.vulnerabilities | length' "$REPORT_DIR/safety_report_${TIMESTAMP}.json" 2>/dev/null || echo "0")
        log_error "safety: Found $vuln_count vulnerabilities"
        EXIT_CODE=2
    fi

    # pip-audit (more comprehensive)
    log "  → Running pip-audit (OSV database)..."
    if pip-audit --format json --output "$REPORT_DIR/pip_audit_report_${TIMESTAMP}.json" 2>/dev/null; then
        log_success "pip-audit: No known vulnerabilities found"
    else
        log_error "pip-audit: Found vulnerabilities (see report)"
        EXIT_CODE=2
    fi

    # Generate human-readable summary
    log "  → Generating dependency scan summary..."
    cat > "$REPORT_DIR/dependency_summary_${TIMESTAMP}.txt" <<EOF
Dependency Vulnerability Scan - $(date)
========================================

Safety Report:
$(safety check --output text 2>/dev/null || echo "See JSON report for details")

pip-audit Report:
$(pip-audit --format text 2>/dev/null || echo "See JSON report for details")

Full reports:
- safety: $REPORT_DIR/safety_report_${TIMESTAMP}.json
- pip-audit: $REPORT_DIR/pip_audit_report_${TIMESTAMP}.json
EOF

    log_success "Dependency scanning complete"
}

# 2. Secret Scanning
scan_secrets() {
    log "Running secret scanning..."

    cd "$PROJECT_ROOT"

    # detect-secrets (baseline approach)
    log "  → Running detect-secrets..."
    if [ ! -f ".secrets.baseline" ]; then
        detect-secrets scan --baseline .secrets.baseline
        log_warning "Created baseline file: .secrets.baseline"
    fi

    if detect-secrets scan --baseline .secrets.baseline 2>/dev/null; then
        log_success "detect-secrets: No new secrets detected"
    else
        log_error "detect-secrets: Found potential secrets"
        detect-secrets scan > "$REPORT_DIR/secrets_scan_${TIMESTAMP}.json"
        EXIT_CODE=1  # Critical - secrets found
    fi

    # Check for common secret patterns manually
    log "  → Checking for common secret patterns..."
    local secret_patterns=(
        "password\s*=\s*['\"][^'\"]+['\"]"
        "api[_-]?key\s*=\s*['\"][^'\"]+['\"]"
        "secret[_-]?key\s*=\s*['\"][^'\"]+['\"]"
        "token\s*=\s*['\"][^'\"]+['\"]"
        "AWS_ACCESS_KEY"
        "AWS_SECRET"
        "OPENAI_API_KEY"
        "ANTHROPIC_API_KEY"
    )

    local found_patterns=0
    for pattern in "${secret_patterns[@]}"; do
        if grep -rn -E "$pattern" --include="*.py" --include="*.yaml" --include="*.yml" --include="*.json" \
            --exclude-dir=".venv" --exclude-dir="venv" --exclude-dir=".git" \
            --exclude-dir="__pycache__" --exclude-dir="node_modules" \
            "$PROJECT_ROOT" > "$REPORT_DIR/grep_secrets_${TIMESTAMP}.txt" 2>/dev/null; then
            ((found_patterns++))
        fi
    done

    if [ $found_patterns -eq 0 ]; then
        log_success "Pattern matching: No hardcoded secrets found"
    else
        log_warning "Pattern matching: Found $found_patterns potential secret patterns (review manually)"
    fi

    log_success "Secret scanning complete"
}

# 3. Static Analysis
scan_static() {
    log "Running static analysis..."

    cd "$PROJECT_ROOT"

    # bandit (Python security linter)
    log "  → Running bandit (Python security issues)..."
    if bandit -r src/kaizen -f json -o "$REPORT_DIR/bandit_report_${TIMESTAMP}.json" -ll 2>/dev/null; then
        log_success "bandit: No security issues found"
    else
        local issue_count=$(jq '.metrics._totals.SEVERITY | to_entries | map(.value) | add' "$REPORT_DIR/bandit_report_${TIMESTAMP}.json" 2>/dev/null || echo "0")
        log_warning "bandit: Found $issue_count potential security issues (review required)"

        # Generate text summary
        bandit -r src/kaizen -f txt -o "$REPORT_DIR/bandit_summary_${TIMESTAMP}.txt" -ll 2>/dev/null || true
        EXIT_CODE=3
    fi

    # semgrep (advanced static analysis)
    if command_exists semgrep; then
        log "  → Running semgrep (SAST)..."
        if $FULL_SCAN; then
            # Full scan with all rulesets
            semgrep --config=auto --json --output="$REPORT_DIR/semgrep_report_${TIMESTAMP}.json" src/kaizen 2>/dev/null || true
        else
            # Quick scan with critical rules only
            semgrep --config="p/security-audit" --config="p/owasp-top-ten" \
                --json --output="$REPORT_DIR/semgrep_report_${TIMESTAMP}.json" src/kaizen 2>/dev/null || true
        fi

        local semgrep_findings=$(jq '.results | length' "$REPORT_DIR/semgrep_report_${TIMESTAMP}.json" 2>/dev/null || echo "0")
        if [ "$semgrep_findings" -eq 0 ]; then
            log_success "semgrep: No findings"
        else
            log_warning "semgrep: Found $semgrep_findings findings (review required)"
        fi
    else
        log_warning "semgrep not installed (skipping advanced SAST)"
    fi

    log_success "Static analysis complete"
}

# 4. Container Scanning
scan_containers() {
    log "Running container security scanning..."

    if ! command_exists trivy; then
        log_warning "trivy not installed - skipping container scanning"
        return
    fi

    cd "$PROJECT_ROOT"

    # Scan Dockerfile if exists
    if [ -f "Dockerfile" ]; then
        log "  → Scanning Dockerfile with trivy..."
        trivy config --format json --output "$REPORT_DIR/trivy_dockerfile_${TIMESTAMP}.json" Dockerfile 2>/dev/null || true

        local dockerfile_vulns=$(jq '.Results[0].Misconfigurations | length' "$REPORT_DIR/trivy_dockerfile_${TIMESTAMP}.json" 2>/dev/null || echo "0")
        if [ "$dockerfile_vulns" -eq 0 ]; then
            log_success "trivy: No Dockerfile misconfigurations found"
        else
            log_warning "trivy: Found $dockerfile_vulns Dockerfile issues"
        fi
    fi

    # Scan filesystem for vulnerabilities
    log "  → Scanning filesystem with trivy..."
    trivy fs --format json --output "$REPORT_DIR/trivy_fs_${TIMESTAMP}.json" . 2>/dev/null || true

    log_success "Container scanning complete"
}

# 5. License Compliance
scan_licenses() {
    log "Running license compliance check..."

    cd "$PROJECT_ROOT"

    # Check for incompatible licenses
    log "  → Checking dependency licenses..."
    pip-licenses --format=json --output-file="$REPORT_DIR/licenses_${TIMESTAMP}.json" 2>/dev/null || true

    # Generate human-readable summary
    pip-licenses --format=plain-vertical > "$REPORT_DIR/licenses_summary_${TIMESTAMP}.txt" 2>/dev/null || true

    # Flag GPL licenses (potential compliance issues for proprietary software)
    local gpl_count=$(grep -c "GPL" "$REPORT_DIR/licenses_summary_${TIMESTAMP}.txt" 2>/dev/null || echo "0")
    if [ "$gpl_count" -gt 0 ]; then
        log_warning "Found $gpl_count GPL-licensed dependencies (review for compliance)"
    else
        log_success "No GPL license conflicts detected"
    fi

    log_success "License compliance check complete"
}

# Generate consolidated report
generate_report() {
    log "Generating consolidated security report..."

    local report_file="$REPORT_DIR/SECURITY_SCAN_REPORT_${TIMESTAMP}.md"

    cat > "$report_file" <<EOF
# Security Scan Report
**Date**: $(date)
**Project**: Kaizen AI Framework
**Scan Type**: $([ "$FULL_SCAN" = true ] && echo "Full" || echo "Quick")

## Executive Summary

### Scan Results
| Category | Status | Findings |
|----------|--------|----------|
| Dependencies | $([ $EXIT_CODE -ge 2 ] && echo "⚠️ ISSUES FOUND" || echo "✅ PASSED") | See dependency reports |
| Secrets | $([ $EXIT_CODE -eq 1 ] && echo "❌ CRITICAL" || echo "✅ PASSED") | See secret scan reports |
| Static Analysis | $([ $EXIT_CODE -eq 3 ] && echo "⚠️ REVIEW NEEDED" || echo "✅ PASSED") | See static analysis reports |
| Containers | ℹ️ INFO | See container scan reports |
| Licenses | ℹ️ INFO | See license compliance reports |

### Overall Risk Assessment
$(if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ **LOW RISK** - No critical vulnerabilities detected"
elif [ $EXIT_CODE -eq 1 ]; then
    echo "❌ **CRITICAL RISK** - Secrets detected in codebase"
elif [ $EXIT_CODE -eq 2 ]; then
    echo "⚠️ **HIGH RISK** - Known vulnerabilities in dependencies"
elif [ $EXIT_CODE -eq 3 ]; then
    echo "⚠️ **MEDIUM RISK** - Potential security issues found"
else
    echo "❓ **UNKNOWN** - Scan incomplete"
fi)

## Detailed Reports

### 1. Dependency Vulnerabilities
- **Safety Report**: \`safety_report_${TIMESTAMP}.json\`
- **pip-audit Report**: \`pip_audit_report_${TIMESTAMP}.json\`
- **Summary**: \`dependency_summary_${TIMESTAMP}.txt\`

### 2. Secret Scanning
- **detect-secrets Report**: \`.secrets.baseline\`
- **Pattern Matching**: \`grep_secrets_${TIMESTAMP}.txt\`

### 3. Static Analysis
- **Bandit Report**: \`bandit_report_${TIMESTAMP}.json\`
- **Bandit Summary**: \`bandit_summary_${TIMESTAMP}.txt\`
- **Semgrep Report**: \`semgrep_report_${TIMESTAMP}.json\`

### 4. Container Security
- **Trivy Dockerfile**: \`trivy_dockerfile_${TIMESTAMP}.json\`
- **Trivy Filesystem**: \`trivy_fs_${TIMESTAMP}.json\`

### 5. License Compliance
- **Licenses JSON**: \`licenses_${TIMESTAMP}.json\`
- **Licenses Summary**: \`licenses_summary_${TIMESTAMP}.txt\`

## Remediation Priorities

### Critical (0-24 hours)
$(if [ $EXIT_CODE -eq 1 ]; then
    echo "- Remove hardcoded secrets from codebase"
    echo "- Rotate exposed credentials immediately"
    echo "- Implement secret management solution (AWS Secrets Manager, HashiCorp Vault)"
else
    echo "None"
fi)

### High (7 days)
$(if [ $EXIT_CODE -eq 2 ]; then
    echo "- Update vulnerable dependencies to patched versions"
    echo "- Review CVE severity and exploitability"
    echo "- Implement dependency pinning"
else
    echo "None"
fi)

### Medium (30 days)
$(if [ $EXIT_CODE -eq 3 ]; then
    echo "- Review and fix static analysis findings"
    echo "- Implement recommended security best practices"
    echo "- Add security-focused linting to CI/CD"
else
    echo "None"
fi)

## Next Steps

1. **Review this report** and all detailed scan outputs
2. **Triage findings** by severity and exploitability
3. **Create remediation tasks** in GitHub Issues
4. **Fix critical issues** within 24 hours
5. **Schedule quarterly pentests** per compliance requirements

## Compliance Mapping

- **PCI DSS 4.0**: Requirement 11.4 (Penetration testing)
- **HIPAA**: § 164.308(a)(8) (Periodic evaluation)
- **GDPR**: Article 32 (Security measures testing)
- **SOC 2**: CC6.1 (Logical and physical access controls)
- **ISO 27001**: Control A.18.2.3 (Technical compliance)

---

**Report Generated By**: Automated Security Scanning Script
**Script Version**: 1.0.0
**Report Location**: \`$report_file\`
EOF

    log_success "Consolidated report generated: $report_file"

    # Print report to console
    cat "$report_file"
}

# Main execution
main() {
    log "Starting automated security scan..."
    log "Project: $PROJECT_ROOT"
    log "Report directory: $REPORT_DIR"
    log "Scan type: $([ "$FULL_SCAN" = true ] && echo "Full" || echo "Quick")"
    echo ""

    # Install tools if needed
    install_tools
    echo ""

    # Run scans
    scan_dependencies
    echo ""

    scan_secrets
    echo ""

    scan_static
    echo ""

    scan_containers
    echo ""

    scan_licenses
    echo ""

    # Generate report
    generate_report
    echo ""

    # Final summary
    if [ $EXIT_CODE -eq 0 ]; then
        log_success "Security scan completed successfully - No critical issues found"
    elif [ $EXIT_CODE -eq 1 ]; then
        log_error "Security scan completed - CRITICAL: Secrets detected"
    elif [ $EXIT_CODE -eq 2 ]; then
        log_error "Security scan completed - HIGH: Vulnerabilities in dependencies"
    elif [ $EXIT_CODE -eq 3 ]; then
        log_warning "Security scan completed - MEDIUM: Review static analysis findings"
    fi

    log "All reports saved to: $REPORT_DIR"

    exit $EXIT_CODE
}

# Execute main function
main "$@"
