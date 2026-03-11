#!/bin/bash
# ============================================================================
# Production Deployment Verification Script
# ============================================================================
#
# This script tests the production observability stack deployment to verify
# that all security hardening measures are in place and functioning correctly.
#
# Usage:
#   ./scripts/test-production-deployment.sh
#
# Requirements:
#   - Docker and Docker Compose running
#   - Production stack deployed with docker-compose up -d
#   - curl installed

set -e  # Exit on error

# ============================================================================
# Configuration
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GRAFANA_DIR="${SCRIPT_DIR}/.."

# Service endpoints
GRAFANA_URL="${GRAFANA_URL:-https://localhost:3000}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"
JAEGER_URL="${JAEGER_URL:-http://localhost:16686}"
ELASTICSEARCH_URL="${ELASTICSEARCH_URL:-http://localhost:9200}"

# Load environment variables
if [ -f "${GRAFANA_DIR}/.env.production" ]; then
    source "${GRAFANA_DIR}/.env.production"
else
    echo "⚠️  Warning: .env.production not found. Using defaults."
fi

# Test counters
TESTS_TOTAL=0
TESTS_PASSED=0
TESTS_FAILED=0

# ============================================================================
# Functions
# ============================================================================

print_header() {
    echo ""
    echo "============================================================================"
    echo "$1"
    echo "============================================================================"
    echo ""
}

print_test() {
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    echo ""
    echo "[$TESTS_TOTAL] Testing: $1"
}

print_pass() {
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo "✅ PASS: $1"
}

print_fail() {
    TESTS_FAILED=$((TESTS_FAILED + 1))
    echo "❌ FAIL: $1"
}

print_info() {
    echo "ℹ️  $1"
}

print_warn() {
    echo "⚠️  WARNING: $1"
}

test_docker_container() {
    local container_name=$1
    if docker ps --format '{{.Names}}' | grep -q "^${container_name}$"; then
        print_pass "Container '${container_name}' is running"
        return 0
    else
        print_fail "Container '${container_name}' is NOT running"
        return 1
    fi
}

test_http_response() {
    local url=$1
    local expected_code=$2
    local description=$3

    local actual_code=$(curl -k -s -o /dev/null -w "%{http_code}" "${url}" 2>/dev/null || echo "000")

    if [ "${actual_code}" = "${expected_code}" ]; then
        print_pass "${description} (HTTP ${actual_code})"
        return 0
    else
        print_fail "${description} (Expected ${expected_code}, got ${actual_code})"
        return 1
    fi
}

test_file_exists() {
    local file_path=$1
    local description=$2

    if [ -f "${file_path}" ]; then
        print_pass "${description}: ${file_path}"
        return 0
    else
        print_fail "${description}: ${file_path} NOT FOUND"
        return 1
    fi
}

test_env_var() {
    local var_name=$1
    local expected_value=$2
    local description=$3

    local actual_value="${!var_name}"

    if [ "${actual_value}" = "${expected_value}" ]; then
        print_pass "${description}: ${var_name}=${expected_value}"
        return 0
    else
        print_fail "${description}: ${var_name}=${actual_value} (expected ${expected_value})"
        return 1
    fi
}

test_env_var_not_default() {
    local var_name=$1
    local default_value=$2
    local description=$3

    local actual_value="${!var_name}"

    if [ -z "${actual_value}" ]; then
        print_fail "${description}: ${var_name} is EMPTY"
        return 1
    elif [ "${actual_value}" = "${default_value}" ]; then
        print_fail "${description}: ${var_name} is still DEFAULT VALUE (${default_value})"
        return 1
    else
        print_pass "${description}: ${var_name} is configured (not default)"
        return 0
    fi
}

# ============================================================================
# Tests
# ============================================================================

print_header "Production Deployment Security Verification"

echo "Testing deployment at:"
echo "  Grafana:        ${GRAFANA_URL}"
echo "  Prometheus:     ${PROMETHEUS_URL}"
echo "  Jaeger:         ${JAEGER_URL}"
echo "  Elasticsearch:  ${ELASTICSEARCH_URL}"
echo ""

# Test 1: Docker Containers
print_header "Test Suite 1: Docker Containers"

print_test "Grafana container is running"
test_docker_container "kaizen-grafana"

print_test "Prometheus container is running"
test_docker_container "kaizen-prometheus"

print_test "Jaeger container is running"
test_docker_container "kaizen-jaeger"

print_test "Elasticsearch container is running"
test_docker_container "kaizen-elasticsearch"

print_test "Node Exporter container is running"
test_docker_container "kaizen-node-exporter"

# Test 2: Configuration Files
print_header "Test Suite 2: Configuration Files"

print_test ".env.production exists"
test_file_exists "${GRAFANA_DIR}/.env.production" ".env.production file"

print_test "prometheus.yml exists"
test_file_exists "${GRAFANA_DIR}/prometheus.yml" "Prometheus config"

print_test "SSL certificate exists (if HTTPS enabled)"
if [ "${GRAFANA_SERVER_PROTOCOL}" = "https" ]; then
    test_file_exists "${GRAFANA_DIR}/ssl/grafana.crt" "SSL certificate"
    test_file_exists "${GRAFANA_DIR}/ssl/grafana.key" "SSL private key"
else
    print_info "HTTPS not enabled, skipping SSL certificate check"
fi

# Test 3: Environment Variables
print_header "Test Suite 3: Security Configuration"

print_test "Grafana admin password is NOT default"
test_env_var_not_default "GRAFANA_ADMIN_PASSWORD" "admin" "Grafana admin password"

print_test "Prometheus password is configured"
test_env_var_not_default "PROMETHEUS_PASSWORD" "" "Prometheus password"

print_test "Elasticsearch password is configured"
test_env_var_not_default "ES_PASSWORD" "changeme" "Elasticsearch password"

print_test "HTTPS protocol (if configured)"
if [ "${GRAFANA_SERVER_PROTOCOL}" = "https" ]; then
    print_pass "HTTPS enabled (GRAFANA_SERVER_PROTOCOL=https)"
else
    print_warn "HTTP only (GRAFANA_SERVER_PROTOCOL=${GRAFANA_SERVER_PROTOCOL:-http})"
    print_info "For production, enable HTTPS by setting GRAFANA_SERVER_PROTOCOL=https"
fi

print_test "Anonymous access is disabled"
if [ "${GRAFANA_AUTH_ANONYMOUS_ENABLED}" = "false" ]; then
    print_pass "Anonymous access disabled (GRAFANA_AUTH_ANONYMOUS_ENABLED=false)"
else
    print_fail "Anonymous access ENABLED (security risk!)"
fi

print_test "User sign-up is disabled"
if [ "${GRAFANA_USERS_ALLOW_SIGN_UP}" = "false" ]; then
    print_pass "User sign-up disabled (GRAFANA_USERS_ALLOW_SIGN_UP=false)"
else
    print_fail "User sign-up ENABLED (security risk!)"
fi

# Test 4: Service Endpoints
print_header "Test Suite 4: Service Accessibility"

print_test "Grafana is accessible"
if curl -k -s --connect-timeout 5 "${GRAFANA_URL}" >/dev/null 2>&1; then
    print_pass "Grafana is accessible at ${GRAFANA_URL}"
else
    print_fail "Grafana is NOT accessible at ${GRAFANA_URL}"
    print_info "Check if Grafana is running and the URL is correct"
fi

print_test "Prometheus is accessible"
if curl -s --connect-timeout 5 "${PROMETHEUS_URL}" >/dev/null 2>&1; then
    print_pass "Prometheus is accessible at ${PROMETHEUS_URL}"
else
    print_warn "Prometheus may be behind authentication or not accessible"
fi

print_test "Jaeger UI is accessible (internal only recommended)"
if curl -s --connect-timeout 5 "${JAEGER_URL}" >/dev/null 2>&1; then
    print_info "Jaeger UI is accessible at ${JAEGER_URL}"
    print_warn "For production, restrict Jaeger UI to internal network only"
else
    print_info "Jaeger UI is not publicly accessible (good for production)"
fi

# Test 5: Authentication
print_header "Test Suite 5: Authentication & Authorization"

print_test "Grafana requires authentication (default login blocked)"
http_code=$(curl -k -s -o /dev/null -w "%{http_code}" "${GRAFANA_URL}/api/dashboards/home" 2>/dev/null)
if [ "${http_code}" = "401" ] || [ "${http_code}" = "302" ]; then
    print_pass "Grafana requires authentication (HTTP ${http_code})"
else
    print_fail "Grafana does NOT require authentication (HTTP ${http_code})"
fi

print_test "Prometheus htpasswd file exists (if auth enabled)"
if [ -f "${GRAFANA_DIR}/prometheus-htpasswd" ]; then
    print_pass "Prometheus htpasswd file exists"
else
    print_warn "Prometheus htpasswd file not found"
    print_info "Generate with: ./scripts/generate-prometheus-auth.sh"
fi

# Test 6: Elasticsearch Security
print_header "Test Suite 6: Elasticsearch Security"

print_test "Elasticsearch requires authentication"
http_code=$(curl -s -o /dev/null -w "%{http_code}" "${ELASTICSEARCH_URL}" 2>/dev/null)
if [ "${http_code}" = "401" ]; then
    print_pass "Elasticsearch requires authentication (HTTP 401)"
elif [ "${http_code}" = "200" ]; then
    print_fail "Elasticsearch is OPEN without authentication (security risk!)"
else
    print_warn "Elasticsearch returned HTTP ${http_code}"
fi

print_test "Elasticsearch authentication works"
if [ -n "${ES_PASSWORD}" ]; then
    http_code=$(curl -s -o /dev/null -w "%{http_code}" -u "elastic:${ES_PASSWORD}" "${ELASTICSEARCH_URL}" 2>/dev/null)
    if [ "${http_code}" = "200" ]; then
        print_pass "Elasticsearch authentication successful"
    else
        print_fail "Elasticsearch authentication failed (HTTP ${http_code})"
    fi
else
    print_warn "ES_PASSWORD not set, skipping authentication test"
fi

# Test 7: Security Headers
print_header "Test Suite 7: Security Headers"

print_test "HSTS header enabled (if HTTPS)"
if [ "${GRAFANA_SECURITY_STRICT_TRANSPORT_SECURITY}" = "true" ]; then
    print_pass "HSTS enabled (GRAFANA_SECURITY_STRICT_TRANSPORT_SECURITY=true)"
else
    print_warn "HSTS not enabled (recommended for HTTPS)"
fi

print_test "X-Content-Type-Options header enabled"
if [ "${GRAFANA_SECURITY_X_CONTENT_TYPE_OPTIONS}" = "true" ]; then
    print_pass "X-Content-Type-Options enabled"
else
    print_warn "X-Content-Type-Options not enabled"
fi

print_test "X-XSS-Protection header enabled"
if [ "${GRAFANA_SECURITY_X_XSS_PROTECTION}" = "true" ]; then
    print_pass "X-XSS-Protection enabled"
else
    print_warn "X-XSS-Protection not enabled"
fi

# Test 8: Gitignore
print_header "Test Suite 8: Git Security"

print_test ".gitignore exists"
test_file_exists "${GRAFANA_DIR}/.gitignore" ".gitignore file"

print_test ".env.production is in .gitignore"
if grep -q ".env.production" "${GRAFANA_DIR}/.gitignore" 2>/dev/null; then
    print_pass ".env.production is in .gitignore"
else
    print_fail ".env.production is NOT in .gitignore (secrets may be committed!)"
fi

print_test "SSL keys are in .gitignore"
if grep -q "ssl/\*\.key" "${GRAFANA_DIR}/.gitignore" 2>/dev/null; then
    print_pass "SSL keys are in .gitignore"
else
    print_warn "SSL keys may not be in .gitignore"
fi

# ============================================================================
# Summary
# ============================================================================

print_header "Test Summary"

echo "Total tests:  ${TESTS_TOTAL}"
echo "Passed:       ${TESTS_PASSED} ✅"
echo "Failed:       ${TESTS_FAILED} ❌"
echo ""

if [ ${TESTS_FAILED} -eq 0 ]; then
    echo "🎉 All tests passed! Production deployment is secure."
    echo ""
    echo "Next steps:"
    echo "  1. Configure OAuth/LDAP for SSO (recommended)"
    echo "  2. Set up backup schedule (Grafana dashboards, Prometheus data)"
    echo "  3. Configure alerting (security events, certificate expiry)"
    echo "  4. Review firewall rules (restrict public access)"
    echo "  5. Schedule quarterly security audits"
    exit 0
else
    echo "⚠️  Some tests failed. Please review the failures above."
    echo ""
    echo "Common issues:"
    echo "  1. Default passwords still in use → Update .env.production"
    echo "  2. HTTP instead of HTTPS → Generate SSL certs and enable HTTPS"
    echo "  3. Services not running → Check docker-compose logs"
    echo "  4. Authentication not configured → Run ./scripts/generate-prometheus-auth.sh"
    echo ""
    echo "See docs/observability/SECURITY.md for detailed hardening guide."
    exit 1
fi
