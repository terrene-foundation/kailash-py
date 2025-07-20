#!/bin/bash
# Vault Setup and Configuration Script
# Automates Vault deployment and initial configuration

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT_DIR="$(cd "$SCRIPT_DIR/../../../" && pwd)"
VAULT_NAMESPACE="vault-system"
VAULT_RELEASE="vault"
VAULT_CHART_VERSION="0.27.0"

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
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    local required_tools=("kubectl" "helm")
    
    for tool in "${required_tools[@]}"; do
        if command -v "$tool" &> /dev/null; then
            log_success "Required tool found: $tool"
        else
            log_error "Required tool missing: $tool"
            exit 1
        fi
    done
    
    # Check cluster connectivity
    if kubectl cluster-info &> /dev/null; then
        local cluster_name=$(kubectl config current-context)
        log_success "Connected to cluster: $cluster_name"
    else
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
}

# Create namespace
create_namespace() {
    log_info "Creating Vault namespace..."
    
    if kubectl get namespace "$VAULT_NAMESPACE" &> /dev/null; then
        log_warning "Namespace $VAULT_NAMESPACE already exists"
    else
        kubectl create namespace "$VAULT_NAMESPACE"
        log_success "Created namespace: $VAULT_NAMESPACE"
    fi
    
    # Label namespace for network policies
    kubectl label namespace "$VAULT_NAMESPACE" name="$VAULT_NAMESPACE" --overwrite
}

# Generate TLS certificates
generate_tls_certs() {
    log_info "Generating TLS certificates for Vault..."
    
    local cert_dir="/tmp/vault-certs"
    mkdir -p "$cert_dir"
    
    # Generate CA private key
    openssl genrsa -out "$cert_dir/ca.key" 4096
    
    # Generate CA certificate
    openssl req -new -x509 -days 365 -key "$cert_dir/ca.key" -out "$cert_dir/ca.crt" -subj "/CN=vault-ca"
    
    # Generate server private key
    openssl genrsa -out "$cert_dir/tls.key" 4096
    
    # Generate certificate signing request
    cat > "$cert_dir/csr.conf" << EOF
[req]
default_bits = 4096
prompt = no
encrypt_key = no
distinguished_name = dn
req_extensions = v3_req

[dn]
CN = vault

[v3_req]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
subjectAltName = @alt_names

[alt_names]
DNS.1 = vault
DNS.2 = vault.vault-system
DNS.3 = vault.vault-system.svc
DNS.4 = vault.vault-system.svc.cluster.local
DNS.5 = vault-0.vault-internal
DNS.6 = vault-1.vault-internal
DNS.7 = vault-2.vault-internal
IP.1 = 127.0.0.1
EOF
    
    # Generate certificate signing request
    openssl req -new -key "$cert_dir/tls.key" -out "$cert_dir/tls.csr" -config "$cert_dir/csr.conf"
    
    # Generate server certificate
    openssl x509 -req -in "$cert_dir/tls.csr" -CA "$cert_dir/ca.crt" -CAkey "$cert_dir/ca.key" -CAcreateserial -out "$cert_dir/tls.crt" -days 365 -extensions v3_req -extfile "$cert_dir/csr.conf"
    
    # Create Kubernetes secret
    kubectl create secret generic vault-tls \
        --from-file="$cert_dir/ca.crt" \
        --from-file="$cert_dir/tls.crt" \
        --from-file="$cert_dir/tls.key" \
        -n "$VAULT_NAMESPACE" \
        --dry-run=client -o yaml | kubectl apply -f -
    
    log_success "TLS certificates generated and stored in secret: vault-tls"
    
    # Cleanup
    rm -rf "$cert_dir"
}

# Add Helm repository
add_helm_repo() {
    log_info "Adding HashiCorp Helm repository..."
    
    helm repo add hashicorp https://helm.releases.hashicorp.com
    helm repo update
    
    log_success "HashiCorp Helm repository added"
}

# Deploy Vault
deploy_vault() {
    log_info "Deploying Vault with Helm..."
    
    local values_file="$DEPLOYMENT_DIR/security/secrets-management/vault/helm-values.yaml"
    
    if [[ ! -f "$values_file" ]]; then
        log_error "Vault values file not found: $values_file"
        exit 1
    fi
    
    # Deploy Vault
    helm upgrade --install "$VAULT_RELEASE" hashicorp/vault \
        --namespace "$VAULT_NAMESPACE" \
        --version "$VAULT_CHART_VERSION" \
        --values "$values_file" \
        --wait \
        --timeout 600s
    
    log_success "Vault deployed successfully"
}

# Wait for Vault pods
wait_for_vault() {
    log_info "Waiting for Vault pods to be ready..."
    
    # Wait for pods to be running
    kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=vault -n "$VAULT_NAMESPACE" --timeout=300s
    
    log_success "Vault pods are ready"
}

# Initialize Vault
initialize_vault() {
    log_info "Initializing Vault..."
    
    # Check if Vault is already initialized
    if kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault status | grep -q "Initialized.*true"; then
        log_warning "Vault is already initialized"
        return 0
    fi
    
    # Initialize Vault and capture output
    local init_output
    init_output=$(kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault operator init -key-shares=5 -key-threshold=3 -format=json)
    
    # Extract keys and root token
    local unseal_keys_b64=($(echo "$init_output" | jq -r '.unseal_keys_b64[]'))
    local root_token=$(echo "$init_output" | jq -r '.root_token')
    
    # Store keys and token in Kubernetes secrets
    kubectl create secret generic vault-init \
        --from-literal=root-token="$root_token" \
        --from-literal=unseal-key-1="${unseal_keys_b64[0]}" \
        --from-literal=unseal-key-2="${unseal_keys_b64[1]}" \
        --from-literal=unseal-key-3="${unseal_keys_b64[2]}" \
        --from-literal=unseal-key-4="${unseal_keys_b64[3]}" \
        --from-literal=unseal-key-5="${unseal_keys_b64[4]}" \
        -n "$VAULT_NAMESPACE"
    
    log_success "Vault initialized successfully"
    log_warning "Unseal keys and root token stored in secret: vault-init"
    log_warning "Please backup these credentials securely!"
}

# Unseal Vault
unseal_vault() {
    log_info "Unsealing Vault..."
    
    # Get unseal keys from secret
    local unseal_key_1=$(kubectl get secret vault-init -n "$VAULT_NAMESPACE" -o jsonpath='{.data.unseal-key-1}' | base64 -d)
    local unseal_key_2=$(kubectl get secret vault-init -n "$VAULT_NAMESPACE" -o jsonpath='{.data.unseal-key-2}' | base64 -d)
    local unseal_key_3=$(kubectl get secret vault-init -n "$VAULT_NAMESPACE" -o jsonpath='{.data.unseal-key-3}' | base64 -d)
    
    # Unseal all Vault instances
    for i in 0 1 2; do
        log_info "Unsealing vault-$i..."
        
        kubectl exec -n "$VAULT_NAMESPACE" "vault-$i" -- vault operator unseal "$unseal_key_1" || true
        kubectl exec -n "$VAULT_NAMESPACE" "vault-$i" -- vault operator unseal "$unseal_key_2" || true
        kubectl exec -n "$VAULT_NAMESPACE" "vault-$i" -- vault operator unseal "$unseal_key_3" || true
        
        log_success "vault-$i unsealed"
    done
}

# Configure Vault authentication and policies
configure_vault() {
    log_info "Configuring Vault authentication and policies..."
    
    # Get root token
    local root_token
    root_token=$(kubectl get secret vault-init -n "$VAULT_NAMESPACE" -o jsonpath='{.data.root-token}' | base64 -d)
    
    # Login to Vault
    kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault auth -method=token token="$root_token"
    
    # Enable Kubernetes authentication
    kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault auth enable kubernetes || true
    
    # Configure Kubernetes authentication
    kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault write auth/kubernetes/config \
        token_reviewer_jwt="$(kubectl get secret -n "$VAULT_NAMESPACE" \$(kubectl get sa vault -n "$VAULT_NAMESPACE" -o jsonpath='{.secrets[0].name}') -o jsonpath='{.data.token}' | base64 -d)" \
        kubernetes_host="https://kubernetes.default.svc:443" \
        kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt
    
    # Enable KV v2 secrets engine
    kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault secrets enable -path=kv kv-v2 || true
    
    # Create policies
    create_vault_policies
    
    # Create roles
    create_vault_roles
    
    log_success "Vault configuration completed"
}

# Create Vault policies
create_vault_policies() {
    log_info "Creating Vault policies..."
    
    # External Secrets policy
    kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault policy write external-secrets - << EOF
path "kv/data/*" {
  capabilities = ["read"]
}

path "kv/metadata/*" {
  capabilities = ["list", "read"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}
EOF
    
    # Kailash application policy
    kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault policy write kailash-app - << EOF
path "kv/data/application/*" {
  capabilities = ["read"]
}

path "kv/data/database/*" {
  capabilities = ["read"]
}

path "kv/data/cache/*" {
  capabilities = ["read"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}
EOF
    
    log_success "Vault policies created"
}

# Create Vault roles
create_vault_roles() {
    log_info "Creating Vault roles..."
    
    # External Secrets role
    kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault write auth/kubernetes/role/external-secrets \
        bound_service_account_names=external-secrets-vault \
        bound_service_account_namespaces=external-secrets-system \
        policies=external-secrets \
        ttl=24h
    
    # Kailash application role
    kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault write auth/kubernetes/role/kailash-app \
        bound_service_account_names=kailash-app \
        bound_service_account_namespaces=default \
        policies=kailash-app \
        ttl=1h
    
    log_success "Vault roles created"
}

# Create sample secrets
create_sample_secrets() {
    log_info "Creating sample secrets in Vault..."
    
    # Database secrets
    kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault kv put kv/database/postgres \
        username=kailash_user \
        password=secure_password_123 \
        host=postgres.default.svc.cluster.local \
        port=5432 \
        database=kailash
    
    # Cache secrets
    kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault kv put kv/cache/redis \
        host=redis.default.svc.cluster.local \
        port=6379 \
        username=default \
        password=redis_password_456
    
    # Application secrets
    kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault kv put kv/application/core \
        secret_key=super_secret_key_789 \
        encryption_key=encryption_key_abc123 \
        nexus_api_key=nexus_api_key_def456
    
    # AI service secrets
    kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault kv put kv/application/ai-services \
        openai_api_key=sk-openai_key_here \
        anthropic_api_key=ant-anthropic_key_here
    
    log_success "Sample secrets created"
    log_warning "Please update these with your actual secret values!"
}

# Display status
show_status() {
    log_info "Vault deployment status:"
    
    echo
    log_info "Pods:"
    kubectl get pods -n "$VAULT_NAMESPACE" -l app.kubernetes.io/name=vault
    
    echo
    log_info "Services:"
    kubectl get services -n "$VAULT_NAMESPACE"
    
    echo
    log_info "Vault status:"
    kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault status
    
    echo
    log_success "Vault setup completed successfully!"
    
    cat << EOF

Next steps:
1. Deploy External Secrets Operator:
   kubectl apply -f deployment/security/secrets-management/external-secrets/operator.yaml

2. Configure secret stores:
   kubectl apply -f deployment/security/secrets-management/external-secrets/cluster-secret-store.yaml

3. Create external secrets:
   kubectl apply -f deployment/security/secrets-management/external-secrets/kailash-secrets.yaml

4. Test secret synchronization:
   ./deployment/security/secrets-management/scripts/test-secrets.sh

Important:
- Root token and unseal keys are stored in secret 'vault-init' in namespace '$VAULT_NAMESPACE'
- Please backup these credentials securely!
- Update sample secrets with your actual values
- Configure proper backup and disaster recovery procedures
EOF
}

# Cleanup function
cleanup() {
    log_warning "Cleaning up temporary files..."
    rm -rf /tmp/vault-certs
}

# Trap cleanup on exit
trap cleanup EXIT

# Main execution
main() {
    log_info "Starting Vault setup..."
    
    check_prerequisites
    create_namespace
    generate_tls_certs
    add_helm_repo
    deploy_vault
    wait_for_vault
    initialize_vault
    unseal_vault
    configure_vault
    create_sample_secrets
    show_status
}

# Show help
show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Setup and configure HashiCorp Vault for Kailash SDK secrets management

Options:
    -h, --help              Show this help message
    -n, --namespace NAME    Vault namespace (default: vault-system)
    -r, --release NAME      Helm release name (default: vault)
    --skip-init            Skip Vault initialization (if already done)
    --skip-unseal          Skip Vault unsealing (if already done)

Examples:
    $0                      # Full Vault setup
    $0 --skip-init         # Skip initialization
    $0 -n custom-vault     # Use custom namespace

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -n|--namespace)
            VAULT_NAMESPACE="$2"
            shift 2
            ;;
        -r|--release)
            VAULT_RELEASE="$2"
            shift 2
            ;;
        --skip-init)
            SKIP_INIT="true"
            shift
            ;;
        --skip-unseal)
            SKIP_UNSEAL="true"
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Override functions if skip flags are set
if [[ "${SKIP_INIT:-false}" == "true" ]]; then
    initialize_vault() {
        log_info "Skipping Vault initialization (--skip-init)"
    }
fi

if [[ "${SKIP_UNSEAL:-false}" == "true" ]]; then
    unseal_vault() {
        log_info "Skipping Vault unsealing (--skip-unseal)"
    }
fi

# Run main function
main "$@"