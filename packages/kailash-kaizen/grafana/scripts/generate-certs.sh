#!/bin/bash
# ============================================================================
# SSL Certificate Generation Script for Grafana Production Deployment
# ============================================================================
#
# This script generates self-signed SSL certificates for development/staging.
# For production, replace with certificates from Let's Encrypt or your CA.
#
# Usage:
#   ./scripts/generate-certs.sh [domain] [days]
#
# Examples:
#   ./scripts/generate-certs.sh                    # localhost, 365 days
#   ./scripts/generate-certs.sh grafana.local      # custom domain
#   ./scripts/generate-certs.sh grafana.local 730  # 2 years validity
#
# Requirements:
#   - OpenSSL installed

set -e  # Exit on error
set -u  # Exit on undefined variable

# ============================================================================
# Configuration
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="${SCRIPT_DIR}/../ssl"
DOMAIN="${1:-localhost}"
DAYS_VALID="${2:-365}"

# Certificate file paths
PRIVATE_KEY="${CERT_DIR}/grafana.key"
CSR_FILE="${CERT_DIR}/grafana.csr"
CERTIFICATE="${CERT_DIR}/grafana.crt"

# Certificate details
COUNTRY="US"
STATE="State"
CITY="City"
ORGANIZATION="Kaizen Observability"
OU="DevOps"

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

print_warning() {
    echo "⚠️  $1"
}

print_error() {
    echo "❌ $1"
}

check_openssl() {
    if ! command -v openssl &> /dev/null; then
        print_error "OpenSSL is not installed"
        echo ""
        echo "Install OpenSSL:"
        echo "  Ubuntu/Debian: sudo apt-get install openssl"
        echo "  macOS:         brew install openssl"
        echo "  RHEL/CentOS:   sudo yum install openssl"
        exit 1
    fi
    print_success "OpenSSL found: $(openssl version)"
}

# ============================================================================
# Main Script
# ============================================================================

print_header "Grafana SSL Certificate Generator"

# Check prerequisites
check_openssl

# Display configuration
print_info "Configuration:"
echo "  Domain:       ${DOMAIN}"
echo "  Validity:     ${DAYS_VALID} days"
echo "  Output dir:   ${CERT_DIR}"
echo ""

# Create SSL directory
print_info "Creating SSL directory..."
mkdir -p "${CERT_DIR}"
print_success "Directory created: ${CERT_DIR}"

# Generate private key
print_header "Step 1: Generate Private Key"
print_info "Generating 2048-bit RSA private key..."
openssl genrsa -out "${PRIVATE_KEY}" 2048
chmod 600 "${PRIVATE_KEY}"  # Secure private key permissions
print_success "Private key generated: ${PRIVATE_KEY}"

# Generate certificate signing request
print_header "Step 2: Generate Certificate Signing Request (CSR)"
print_info "Creating CSR with subject: CN=${DOMAIN}"
openssl req -new \
    -key "${PRIVATE_KEY}" \
    -out "${CSR_FILE}" \
    -subj "/C=${COUNTRY}/ST=${STATE}/L=${CITY}/O=${ORGANIZATION}/OU=${OU}/CN=${DOMAIN}"
print_success "CSR generated: ${CSR_FILE}"

# Generate self-signed certificate
print_header "Step 3: Generate Self-Signed Certificate"
print_info "Creating self-signed certificate (valid for ${DAYS_VALID} days)..."
openssl x509 -req \
    -days "${DAYS_VALID}" \
    -in "${CSR_FILE}" \
    -signkey "${PRIVATE_KEY}" \
    -out "${CERTIFICATE}"
chmod 644 "${CERTIFICATE}"  # Public certificate can be readable
print_success "Certificate generated: ${CERTIFICATE}"

# Display certificate information
print_header "Certificate Information"
openssl x509 -in "${CERTIFICATE}" -text -noout | grep -E "Subject:|Issuer:|Not Before|Not After"

# Final summary
print_header "Summary"
print_success "SSL certificates generated successfully!"
echo ""
echo "Files created:"
echo "  Private Key:  ${PRIVATE_KEY}"
echo "  CSR:          ${CSR_FILE}"
echo "  Certificate:  ${CERTIFICATE}"
echo ""

print_warning "IMPORTANT: These are SELF-SIGNED certificates for development/staging only!"
echo ""
echo "For production deployment:"
echo ""
echo "1. Option A: Let's Encrypt (FREE, automated renewal)"
echo "   Install certbot:"
echo "     Ubuntu/Debian: sudo apt-get install certbot"
echo "     macOS:         brew install certbot"
echo ""
echo "   Generate certificate:"
echo "     sudo certbot certonly --standalone -d ${DOMAIN}"
echo ""
echo "   Certificates will be in: /etc/letsencrypt/live/${DOMAIN}/"
echo "   Update .env.production:"
echo "     GRAFANA_SERVER_CERT_FILE=/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
echo "     GRAFANA_SERVER_KEY_FILE=/etc/letsencrypt/live/${DOMAIN}/privkey.pem"
echo ""

echo "2. Option B: Organization CA"
echo "   - Request certificate from your organization's Certificate Authority"
echo "   - Provide CSR file: ${CSR_FILE}"
echo "   - Save signed certificate as: ${CERTIFICATE}"
echo "   - Update .env.production with certificate paths"
echo ""

echo "3. Option C: Cloud Provider Certificates"
echo "   - AWS Certificate Manager (ACM)"
echo "   - Google Cloud Certificate Manager"
echo "   - Azure Key Vault Certificates"
echo "   - Use with Application Load Balancer / Ingress"
echo ""

print_header "Next Steps"
echo "1. Copy .env.production.example to .env.production"
echo "   cp .env.production.example .env.production"
echo ""
echo "2. Update .env.production with your configuration:"
echo "   - GRAFANA_ADMIN_PASSWORD (strong password)"
echo "   - GRAFANA_SERVER_DOMAIN (${DOMAIN})"
echo "   - GRAFANA_SERVER_PROTOCOL (https)"
echo "   - Other security settings"
echo ""
echo "3. Start the stack:"
echo "   docker-compose --env-file .env.production up -d"
echo ""
echo "4. Access Grafana:"
echo "   https://${DOMAIN}:3000"
echo "   (Accept self-signed certificate warning in browser)"
echo ""
echo "5. For production, replace with real certificates (see above)"
echo ""

print_success "Done!"
