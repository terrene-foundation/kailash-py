#!/bin/bash
# ============================================================================
# Prometheus Basic Authentication Setup Script
# ============================================================================
#
# This script generates htpasswd file for Prometheus authentication.
# Prometheus will require username/password for accessing /metrics and /api.
#
# Usage:
#   ./scripts/generate-prometheus-auth.sh [username] [password]
#
# Examples:
#   ./scripts/generate-prometheus-auth.sh                        # Interactive
#   ./scripts/generate-prometheus-auth.sh prometheus mypass123   # Direct
#
# Requirements:
#   - htpasswd (from apache2-utils on Ubuntu, httpd on macOS)

set -e  # Exit on error

# ============================================================================
# Configuration
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HTPASSWD_FILE="${SCRIPT_DIR}/../prometheus-htpasswd"
DEFAULT_USERNAME="prometheus"

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

print_info() {
    echo "ℹ️  $1"
}

print_success() {
    echo "✅ $1"
}

print_error() {
    echo "❌ $1"
}

check_htpasswd() {
    if ! command -v htpasswd &> /dev/null; then
        print_error "htpasswd is not installed"
        echo ""
        echo "Install htpasswd:"
        echo "  Ubuntu/Debian: sudo apt-get install apache2-utils"
        echo "  macOS:         brew install httpd"
        echo "  RHEL/CentOS:   sudo yum install httpd-tools"
        exit 1
    fi
    print_success "htpasswd found"
}

# ============================================================================
# Main Script
# ============================================================================

print_header "Prometheus Basic Authentication Setup"

# Check prerequisites
check_htpasswd

# Get username
if [ -n "${1:-}" ]; then
    USERNAME="$1"
else
    read -p "Enter username [${DEFAULT_USERNAME}]: " USERNAME
    USERNAME="${USERNAME:-${DEFAULT_USERNAME}}"
fi

# Get password
if [ -n "${2:-}" ]; then
    PASSWORD="$2"
else
    echo ""
    print_info "Password requirements:"
    echo "  - Minimum 12 characters"
    echo "  - Mix of uppercase, lowercase, numbers, special characters"
    echo ""
    read -sp "Enter password: " PASSWORD
    echo ""
    read -sp "Confirm password: " PASSWORD_CONFIRM
    echo ""

    if [ "${PASSWORD}" != "${PASSWORD_CONFIRM}" ]; then
        print_error "Passwords do not match"
        exit 1
    fi

    if [ ${#PASSWORD} -lt 12 ]; then
        print_error "Password must be at least 12 characters"
        exit 1
    fi
fi

# Generate htpasswd file
print_info "Generating htpasswd file..."
# Use -B for bcrypt (more secure than MD5)
htpasswd -nB "${USERNAME}" <<< "${PASSWORD}" > "${HTPASSWD_FILE}"
chmod 600 "${HTPASSWD_FILE}"  # Secure permissions
print_success "htpasswd file generated: ${HTPASSWD_FILE}"

# Display file contents (password is hashed)
echo ""
print_info "File contents:"
cat "${HTPASSWD_FILE}"
echo ""

print_header "Next Steps"
echo "1. Update .env.production with Prometheus credentials:"
echo "   PROMETHEUS_USER=${USERNAME}"
echo "   PROMETHEUS_PASSWORD=<your_password>"
echo ""
echo "2. Update prometheus.yml scrape configs with basic_auth:"
echo "   scrape_configs:"
echo "     - job_name: 'kaizen-agents'"
echo "       basic_auth:"
echo "         username: '${USERNAME}'"
echo "         password_file: /etc/prometheus/prometheus-password.txt"
echo ""
echo "3. Restart Prometheus:"
echo "   docker-compose restart prometheus"
echo ""
echo "4. Test authentication:"
echo "   curl -u ${USERNAME}:<password> http://localhost:9090/metrics"
echo ""

print_success "Done!"
