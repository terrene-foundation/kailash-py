# Enterprise Secrets Management

## 🔐 Overview

Enterprise-grade secrets management using HashiCorp Vault and External Secrets Operator for secure, auditable, and automated secret lifecycle management in Kubernetes.

## 🏗️ Architecture

### Components
- **HashiCorp Vault**: Central secret storage and management
- **External Secrets Operator (ESO)**: Kubernetes-native secret synchronization
- **Vault Agent Injector**: Sidecar-based secret injection
- **AWS Secrets Manager**: Cloud-native secret storage (alternative)
- **Cert-Manager**: Automated certificate management

### Security Features
- **Zero-trust secret access**: All secrets require authentication
- **Audit logging**: Complete audit trail of secret access
- **Secret rotation**: Automated secret rotation capabilities
- **Encryption**: Secrets encrypted at rest and in transit
- **RBAC integration**: Fine-grained access control
- **Key management**: Integrated with cloud KMS services

## 📁 Directory Structure

```
secrets-management/
├── vault/
│   ├── helm-values.yaml          # Vault Helm configuration
│   ├── policies/                 # Vault policies
│   ├── auth-methods/            # Authentication methods
│   └── secret-engines/          # Secret engine configurations
├── external-secrets/
│   ├── operator.yaml            # ESO deployment
│   ├── cluster-secret-store.yaml # Global secret store
│   ├── secret-stores/           # Environment-specific stores
│   └── external-secrets/        # Secret definitions
├── cert-manager/
│   ├── issuer.yaml              # Certificate issuers
│   └── certificates.yaml       # Certificate definitions
├── aws-secrets-manager/
│   ├── secret-store.yaml        # AWS Secrets Manager store
│   └── iam-policy.json          # Required IAM policies
└── scripts/
    ├── setup-vault.sh           # Vault setup automation
    ├── configure-auth.sh        # Authentication setup
    └── test-secrets.sh          # Secret access testing
```

## 🚀 Quick Start

### 1. Deploy Vault
```bash
# Add Vault Helm repository
helm repo add hashicorp https://helm.releases.hashicorp.com
helm repo update

# Deploy Vault
helm install vault hashicorp/vault \
  -f deployment/security/secrets-management/vault/helm-values.yaml \
  --namespace vault-system \
  --create-namespace

# Initialize and unseal Vault
kubectl exec -n vault-system vault-0 -- vault operator init
kubectl exec -n vault-system vault-0 -- vault operator unseal <key1>
kubectl exec -n vault-system vault-0 -- vault operator unseal <key2>
kubectl exec -n vault-system vault-0 -- vault operator unseal <key3>
```

### 2. Deploy External Secrets Operator
```bash
# Deploy ESO
kubectl apply -f deployment/security/secrets-management/external-secrets/operator.yaml

# Configure secret stores
kubectl apply -f deployment/security/secrets-management/external-secrets/cluster-secret-store.yaml
```

### 3. Configure Authentication
```bash
# Setup Kubernetes authentication
./deployment/security/secrets-management/scripts/configure-auth.sh

# Test secret access
./deployment/security/secrets-management/scripts/test-secrets.sh
```

## ⚙️ Configuration

### Vault High Availability
```yaml
# vault/helm-values.yaml
ha:
  enabled: true
  replicas: 3
  raft:
    enabled: true
    setNodeId: true
    config: |
      cluster_name = "vault-integrated-storage"
      storage "raft" {
        path = "/vault/data"
        retry_join {
          leader_api_addr = "http://vault-0.vault-internal:8200"
        }
        retry_join {
          leader_api_addr = "http://vault-1.vault-internal:8200"
        }
        retry_join {
          leader_api_addr = "http://vault-2.vault-internal:8200"
        }
      }
```

### External Secrets Configuration
```yaml
# external-secrets/cluster-secret-store.yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: vault-backend
spec:
  provider:
    vault:
      server: "http://vault.vault-system:8200"
      path: "kv"
      version: "v2"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "external-secrets"
```

## 🔑 Secret Types & Usage

### Database Credentials
```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: postgres-credentials
  namespace: default
spec:
  refreshInterval: 15s
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: postgres-secret
    creationPolicy: Owner
  data:
  - secretKey: username
    remoteRef:
      key: database/postgres
      property: username
  - secretKey: password
    remoteRef:
      key: database/postgres
      property: password
```

### API Keys
```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: api-keys
  namespace: kailash-system
spec:
  refreshInterval: 30s
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: application-secrets
  data:
  - secretKey: nexus-api-key
    remoteRef:
      key: application/api-keys
      property: nexus
  - secretKey: encryption-key
    remoteRef:
      key: application/encryption
      property: key
```

### TLS Certificates
```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: kailash-tls
  namespace: default
spec:
  secretName: kailash-tls-secret
  issuerRef:
    name: vault-issuer
    kind: ClusterIssuer
  commonName: kailash.your-domain.com
  dnsNames:
  - kailash.your-domain.com
  - api.kailash.your-domain.com
```

## 🔧 Vault Configuration

### Authentication Methods
```bash
# Enable Kubernetes authentication
vault auth enable kubernetes

# Configure Kubernetes auth
vault write auth/kubernetes/config \
    token_reviewer_jwt="$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)" \
    kubernetes_host="https://$KUBERNETES_PORT_443_TCP_ADDR:443" \
    kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt

# Create roles for applications
vault write auth/kubernetes/role/kailash-app \
    bound_service_account_names=kailash-app \
    bound_service_account_namespaces=default \
    policies=kailash-app-policy \
    ttl=24h
```

### Secret Engines
```bash
# Enable KV v2 engine
vault secrets enable -path=kv kv-v2

# Enable database engine for dynamic credentials
vault secrets enable database

# Configure PostgreSQL
vault write database/config/postgres \
    plugin_name=postgresql-database-plugin \
    connection_url="postgresql://{{username}}:{{password}}@postgres:5432/kailash?sslmode=require" \
    allowed_roles="readonly","readwrite" \
    username="vault" \
    password="password"
```

### Policies
```hcl
# policies/kailash-app-policy.hcl
path "kv/data/application/*" {
  capabilities = ["read"]
}

path "database/creds/readonly" {
  capabilities = ["read"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}
```

## 🛡️ Security Best Practices

### Vault Security
- Enable audit logging
- Use TLS for all communications
- Implement seal/unseal procedures
- Regular key rotation
- Monitor access patterns

### Kubernetes Integration
- Use dedicated service accounts
- Implement RBAC for secret access
- Network policies for Vault communication
- Pod security standards enforcement

### Secret Lifecycle
- Automated secret rotation
- Secret versioning and rollback
- Regular access reviews
- Compliance reporting

## 📊 Monitoring & Alerting

### Vault Metrics
```yaml
# Prometheus configuration
- job_name: 'vault'
  static_configs:
  - targets: ['vault.vault-system:8200']
  metrics_path: /v1/sys/metrics
  params:
    format: ['prometheus']
```

### Secret Rotation Alerts
```yaml
# AlertManager rules
groups:
- name: secrets
  rules:
  - alert: SecretRotationOverdue
    expr: time() - vault_secret_last_rotation > 86400
    for: 1h
    labels:
      severity: warning
    annotations:
      summary: "Secret rotation overdue"
      description: "Secret {{ $labels.secret }} has not been rotated in 24+ hours"
```

## 🔄 Backup & Disaster Recovery

### Vault Snapshots
```bash
# Create snapshot
vault operator raft snapshot save backup.snap

# Restore from snapshot
vault operator raft snapshot restore backup.snap
```

### Cross-Region Replication
```hcl
# Vault Enterprise feature
storage "raft" {
  path = "/vault/data"
  
  retry_join {
    leader_api_addr = "https://vault-primary.region1.com:8200"
  }
}

replication {
  performance {
    mode = "secondary"
    primary_api_addr = "https://vault-primary.region1.com:8200"
  }
}
```

## 🧪 Testing

### Secret Access Testing
```bash
# Test external secret synchronization
kubectl get externalsecrets -A

# Verify secret creation
kubectl get secrets -A | grep external-secret

# Test application secret access
kubectl exec -it app-pod -- env | grep SECRET
```

### Security Testing
```bash
# Test unauthorized access
kubectl auth can-i get secrets --as=system:anonymous

# Test RBAC policies
kubectl auth can-i create externalsecrets --as=serviceaccount:default:app

# Test network policies
kubectl exec test-pod -- nc -zv vault.vault-system 8200
```

## 📖 Integration Examples

### Application Integration
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kailash-app
spec:
  template:
    spec:
      serviceAccountName: kailash-app
      containers:
      - name: app
        image: kailash-app:latest
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: connection-string
        - name: API_KEY
          valueFrom:
            secretKeyRef:
              name: application-secrets
              key: nexus-api-key
```

### Vault Agent Sidecar
```yaml
spec:
  template:
    metadata:
      annotations:
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "kailash-app"
        vault.hashicorp.com/agent-inject-secret-config: "kv/data/application/config"
    spec:
      serviceAccountName: kailash-app
```

## 🔗 Related Documentation

- [Security Hardening Guide](../README.md)
- [Network Policies](../network-policies/)
- [CIS Benchmarks](../cis-benchmarks/)
- [Compliance Framework](../../compliance/)

---

**🔐 Enterprise secrets management ensures secure, auditable, and automated secret lifecycle**