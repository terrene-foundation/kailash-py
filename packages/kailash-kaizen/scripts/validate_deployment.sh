#!/bin/bash

# Deployment Validation Script
# Validates deployment health, endpoints, and performs smoke tests

set -e  # Exit on error
set -o pipefail  # Exit on pipe failure

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ENVIRONMENT="${ENVIRONMENT:-dev}"
DEPLOYMENT_URL="${DEPLOYMENT_URL:-http://localhost:8000}"
TIMEOUT=30
MAX_RETRIES=5
RETRY_DELAY=5

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
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# Print validation header
print_header() {
    echo ""
    echo "=========================================="
    echo "  🔍 Deployment Validation"
    echo "=========================================="
    echo "Environment: ${ENVIRONMENT}"
    echo "URL: ${DEPLOYMENT_URL}"
    echo "Timeout: ${TIMEOUT}s"
    echo "=========================================="
    echo ""
}

# Check if required tools are available
check_requirements() {
    log_info "Checking requirements..."

    if ! command -v curl &> /dev/null; then
        log_error "curl is required but not installed"
        exit 1
    fi

    if ! command -v jq &> /dev/null; then
        log_warning "jq is not installed - JSON validation will be limited"
    fi

    log_success "All required tools are available"
}

# Health check validation
validate_health_check() {
    log_info "Validating health check endpoint..."

    local health_url="${DEPLOYMENT_URL}/health"
    local retry_count=0

    while [ $retry_count -lt $MAX_RETRIES ]; do
        log_info "Attempt $((retry_count + 1))/${MAX_RETRIES}..."

        # Make health check request
        response=$(curl -s -w "\n%{http_code}" --connect-timeout $TIMEOUT --max-time $TIMEOUT "${health_url}" 2>/dev/null || echo "000")

        # Extract status code (last line)
        status_code=$(echo "$response" | tail -n 1)
        body=$(echo "$response" | head -n -1)

        if [ "$status_code" = "200" ]; then
            log_success "Health check passed (HTTP 200)"
            log_info "Response: ${body}"
            return 0
        elif [ "$status_code" = "000" ]; then
            log_warning "Connection failed - service may not be ready yet"
        else
            log_warning "Health check returned HTTP ${status_code}"
        fi

        retry_count=$((retry_count + 1))
        if [ $retry_count -lt $MAX_RETRIES ]; then
            log_info "Retrying in ${RETRY_DELAY}s..."
            sleep $RETRY_DELAY
        fi
    done

    log_error "Health check failed after ${MAX_RETRIES} attempts"
    return 1
}

# Validate API endpoints
validate_api_endpoints() {
    log_info "Validating API endpoints..."

    # Test root endpoint
    log_info "Testing root endpoint..."
    response=$(curl -s -w "\n%{http_code}" --connect-timeout $TIMEOUT --max-time $TIMEOUT "${DEPLOYMENT_URL}/" 2>/dev/null || echo "000")
    status_code=$(echo "$response" | tail -n 1)

    if [ "$status_code" = "200" ] || [ "$status_code" = "404" ]; then
        log_success "Root endpoint accessible (HTTP ${status_code})"
    else
        log_error "Root endpoint failed (HTTP ${status_code})"
        return 1
    fi

    # Test metrics endpoint (if available)
    log_info "Testing metrics endpoint..."
    response=$(curl -s -w "\n%{http_code}" --connect-timeout $TIMEOUT --max-time $TIMEOUT "${DEPLOYMENT_URL}/metrics" 2>/dev/null || echo "000")
    status_code=$(echo "$response" | tail -n 1)

    if [ "$status_code" = "200" ]; then
        log_success "Metrics endpoint accessible (HTTP 200)"
    elif [ "$status_code" = "404" ]; then
        log_warning "Metrics endpoint not found (HTTP 404) - may not be enabled"
    else
        log_warning "Metrics endpoint returned HTTP ${status_code}"
    fi

    log_success "API endpoint validation completed"
    return 0
}

# Run smoke tests
run_smoke_tests() {
    log_info "Running smoke tests..."

    # Test 1: Basic connectivity
    log_info "Smoke test 1: Basic connectivity..."
    if curl -s --connect-timeout 5 --max-time 10 "${DEPLOYMENT_URL}" > /dev/null 2>&1; then
        log_success "✓ Basic connectivity test passed"
    else
        log_error "✗ Basic connectivity test failed"
        return 1
    fi

    # Test 2: Response time check
    log_info "Smoke test 2: Response time check..."
    response_time=$(curl -s -w "%{time_total}" -o /dev/null --connect-timeout $TIMEOUT --max-time $TIMEOUT "${DEPLOYMENT_URL}/health" 2>/dev/null || echo "999")
    response_time_ms=$(echo "$response_time * 1000" | bc 2>/dev/null || echo "999")

    if (( $(echo "$response_time < 5" | bc -l 2>/dev/null || echo "0") )); then
        log_success "✓ Response time acceptable: ${response_time}s"
    else
        log_warning "✓ Response time: ${response_time}s (slower than expected)"
    fi

    # Test 3: Environment variable check
    log_info "Smoke test 3: Environment configuration..."
    if [ -n "$ENVIRONMENT" ]; then
        log_success "✓ Environment configured: ${ENVIRONMENT}"
    else
        log_error "✗ Environment not configured"
        return 1
    fi

    log_success "All smoke tests passed"
    return 0
}

# Validate deployment version (if version info endpoint exists)
validate_version() {
    log_info "Validating deployment version..."

    local version_url="${DEPLOYMENT_URL}/version"
    response=$(curl -s -w "\n%{http_code}" --connect-timeout $TIMEOUT --max-time $TIMEOUT "${version_url}" 2>/dev/null || echo "000")
    status_code=$(echo "$response" | tail -n 1)

    if [ "$status_code" = "200" ]; then
        body=$(echo "$response" | head -n -1)
        log_success "Version info: ${body}"
        return 0
    elif [ "$status_code" = "404" ]; then
        log_warning "Version endpoint not found - skipping version validation"
        return 0
    else
        log_warning "Version endpoint returned HTTP ${status_code}"
        return 0
    fi
}

# Performance validation
validate_performance() {
    log_info "Validating performance metrics..."

    # Run multiple requests to get average response time
    local total_time=0
    local request_count=5

    for i in $(seq 1 $request_count); do
        response_time=$(curl -s -w "%{time_total}" -o /dev/null --connect-timeout $TIMEOUT --max-time $TIMEOUT "${DEPLOYMENT_URL}/health" 2>/dev/null || echo "0")
        total_time=$(echo "$total_time + $response_time" | bc -l 2>/dev/null || echo "0")
    done

    if command -v bc &> /dev/null; then
        avg_time=$(echo "scale=3; $total_time / $request_count" | bc -l)
        log_info "Average response time over ${request_count} requests: ${avg_time}s"

        if (( $(echo "$avg_time < 2" | bc -l) )); then
            log_success "Performance validation passed"
        else
            log_warning "Performance may be degraded (avg response time: ${avg_time}s)"
        fi
    else
        log_warning "bc not available - skipping detailed performance metrics"
    fi

    return 0
}

# Main validation flow
main() {
    print_header

    # Track validation status
    local validation_failed=0

    # Run all validations
    check_requirements || validation_failed=1

    validate_health_check || validation_failed=1

    validate_api_endpoints || validation_failed=1

    run_smoke_tests || validation_failed=1

    validate_version || true  # Don't fail if version endpoint doesn't exist

    validate_performance || true  # Don't fail on performance warnings

    # Print summary
    echo ""
    echo "=========================================="
    echo "  📊 Validation Summary"
    echo "=========================================="

    if [ $validation_failed -eq 0 ]; then
        log_success "✅ All validations passed!"
        log_info "Deployment is healthy and ready to serve traffic"
        echo "=========================================="
        exit 0
    else
        log_error "❌ Validation failed!"
        log_error "Deployment may have issues - check logs above"
        echo "=========================================="
        exit 1
    fi
}

# Run main function
main
