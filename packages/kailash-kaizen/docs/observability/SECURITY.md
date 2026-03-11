# Observability Infrastructure Security Hardening

**Status**: Production-ready
**Last Updated**: 2025-10-24
**Version**: 1.0.0

---

## Table of Contents

1. [Overview](#overview)
2. [Current Vulnerabilities (Development Mode)](#current-vulnerabilities-development-mode)
3. [Production Deployment Checklist](#production-deployment-checklist)
4. [SSL/TLS Certificate Management](#ssltls-certificate-management)
5. [Grafana Security](#grafana-security)
6. [Prometheus Security](#prometheus-security)
7. [Jaeger Security](#jaeger-security)
8. [Network Isolation](#network-isolation)
9. [Secrets Management](#secrets-management)
10. [Compliance Considerations](#compliance-considerations)
11. [Security Best Practices](#security-best-practices)
12. [Incident Response](#incident-response)

---

## Overview

The Kaizen observability stack (Grafana, Prometheus, Jaeger, Elasticsearch) ships with **development-friendly defaults** that are **NOT suitable for production deployment**. This document provides comprehensive security hardening guidance for production deployments.

### Security Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Reverse Proxy / Load Balancer             │
│                  (nginx/Traefik/ALB + TLS)                  │
└───────────────────┬─────────────────────────────────────────┘
                    │
        ┌───────────┴───────────┬───────────────┐
        │                       │               │
┌───────▼────────┐   ┌──────────▼─────┐  ┌─────▼──────┐
│    Grafana     │   │   Prometheus   │  │   Jaeger   │
│  (HTTPS+Auth)  │   │  (Basic Auth)  │  │  (Private) │
└────────────────┘   └────────────────┘  └────────────┘
        │                       │               │
        └───────────┬───────────┴───────────────┘
                    │
            ┌───────▼────────┐
            │ Elasticsearch  │
            │ (Auth + TLS)   │
            └────────────────┘
```

### Threat Model

| Threat | Impact | Mitigation |
|--------|--------|------------|
| Default credentials | **CRITICAL** - Full system access | Strong passwords, OAuth/LDAP |
| Plaintext traffic | **HIGH** - Password/data leakage | TLS/HTTPS everywhere |
| No authentication | **HIGH** - Unauthorized access | Basic auth, API tokens |
| Secrets in config | **HIGH** - Credential exposure | Environment variables, vaults |
| Public exposure | **MEDIUM** - Attack surface | Network isolation, firewall |

---

## Current Vulnerabilities (Development Mode)

### ❌ Critical Security Issues

1. **Default Password (Grafana)**
   - Username: `admin`
   - Password: `admin`
   - **Risk**: Publicly known, immediately compromised
   - **Impact**: Full dashboard access, data exfiltration

2. **No TLS/HTTPS**
   - All traffic in plaintext (HTTP)
   - **Risk**: Password interception, MITM attacks
   - **Impact**: Credential theft, data tampering

3. **No Authentication (Prometheus, Jaeger)**
   - Metrics and traces accessible without login
   - **Risk**: Sensitive data exposure, configuration changes
   - **Impact**: Data leakage, denial of service

4. **Secrets in Config Files**
   - Passwords in `docker-compose.yml`
   - **Risk**: Git commit exposure, file sharing
   - **Impact**: Credential compromise

5. **No Network Isolation**
   - All ports exposed to 0.0.0.0
   - **Risk**: Internet-wide accessibility
   - **Impact**: Brute force attacks, unauthorized access

---

## Production Deployment Checklist

Use this checklist to verify production readiness:

### Pre-Deployment (Required)

- [ ] **Copy `.env.production.example` to `.env.production`**
- [ ] **Generate strong passwords (min 16 characters)** for:
  - [ ] Grafana admin (`GRAFANA_ADMIN_PASSWORD`)
  - [ ] Prometheus (`PROMETHEUS_PASSWORD`)
  - [ ] Elasticsearch (`ES_PASSWORD`)
- [ ] **Generate SSL/TLS certificates** (see [Certificate Management](#ssltls-certificate-management))
- [ ] **Configure OAuth/LDAP** (recommended for production)
- [ ] **Add `.env.production` to `.gitignore`**
- [ ] **Review firewall rules** (restrict public access)

### Security Configuration (Required)

- [ ] **Enable HTTPS** for Grafana (`GRAFANA_SERVER_PROTOCOL=https`)
- [ ] **Enable Basic Auth** for Prometheus (generate htpasswd)
- [ ] **Enable Elasticsearch authentication** (`xpack.security.enabled=true`)
- [ ] **Disable anonymous access** (`GRAFANA_AUTH_ANONYMOUS_ENABLED=false`)
- [ ] **Enable security headers** (HSTS, CSP, X-Frame-Options)
- [ ] **Configure network policies** (Docker networks, firewall rules)

### Post-Deployment (Recommended)

- [ ] **Test HTTPS access** (verify certificates)
- [ ] **Test authentication** (all services require login)
- [ ] **Review logs** for security events
- [ ] **Configure alerting** (Grafana alerts, PagerDuty)
- [ ] **Set up backup** (persistent volumes, databases)
- [ ] **Document secrets rotation** procedures
- [ ] **Schedule security audits** (quarterly)

---

## SSL/TLS Certificate Management

### Development/Staging: Self-Signed Certificates

**Quick Setup** (5 minutes):

```bash
cd grafana/
./scripts/generate-certs.sh
# Or with custom domain:
./scripts/generate-certs.sh grafana.staging.local 365
```

**What it does**:
- Generates 2048-bit RSA private key
- Creates self-signed certificate (valid 365 days)
- Sets secure file permissions
- Outputs to `grafana/ssl/` directory

**Limitations**:
- ⚠️ Browser warnings ("Not Secure")
- ⚠️ Certificate not trusted by clients
- ⚠️ Manual renewal required

**Use cases**:
- Internal testing environments
- Staging deployments
- Development setups

### Production: Let's Encrypt (Recommended)

**Free, automated, and trusted certificates.**

#### Option A: Standalone (Direct Port 80/443)

```bash
# Install certbot
sudo apt-get install certbot  # Ubuntu
brew install certbot          # macOS

# Generate certificate
sudo certbot certonly --standalone \
  -d grafana.example.com \
  -d prometheus.example.com \
  -d jaeger.example.com

# Certificates saved to:
# /etc/letsencrypt/live/grafana.example.com/fullchain.pem
# /etc/letsencrypt/live/grafana.example.com/privkey.pem
```

#### Option B: DNS Challenge (Recommended for Internal Services)

```bash
# For internal domains or wildcard certificates
sudo certbot certonly --manual \
  --preferred-challenges dns \
  -d '*.observability.example.com'

# Add DNS TXT record as instructed
# Wait for DNS propagation
```

#### Option C: Reverse Proxy (nginx/Traefik)

**Best for production**: Centralized TLS termination

**nginx example**:

```nginx
# /etc/nginx/sites-available/grafana
server {
    listen 443 ssl http2;
    server_name grafana.example.com;

    ssl_certificate /etc/letsencrypt/live/grafana.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/grafana.example.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload";
    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Auto-Renewal

```bash
# Test renewal
sudo certbot renew --dry-run

# Add to crontab for auto-renewal
0 0,12 * * * certbot renew --quiet
```

### Update `.env.production`

```bash
# For Let's Encrypt certificates
GRAFANA_SERVER_PROTOCOL=https
GRAFANA_SERVER_DOMAIN=grafana.example.com
GRAFANA_SERVER_CERT_FILE=/etc/letsencrypt/live/grafana.example.com/fullchain.pem
GRAFANA_SERVER_KEY_FILE=/etc/letsencrypt/live/grafana.example.com/privkey.pem
```

### Cloud Provider Certificates

| Provider | Service | Integration |
|----------|---------|-------------|
| AWS | Certificate Manager (ACM) | ALB/CloudFront |
| GCP | Certificate Manager | Load Balancer |
| Azure | Key Vault Certificates | App Gateway |
| Cloudflare | Origin Certificates | Cloudflare Proxy |

---

## Grafana Security

### Authentication Methods

#### Method 1: Strong Password (Minimum Security)

```bash
# .env.production
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=<generate-strong-password>

# Generate password (16+ characters):
openssl rand -base64 24
```

**Requirements**:
- Minimum 16 characters
- Mix of uppercase, lowercase, numbers, special chars
- No dictionary words
- Unique (not reused)

#### Method 2: OAuth 2.0 (Recommended)

**Supported providers**: Google, GitHub, GitLab, Okta, Azure AD

**Google OAuth Example**:

1. **Create OAuth 2.0 credentials** in Google Cloud Console:
   - Go to: https://console.cloud.google.com/apis/credentials
   - Create OAuth 2.0 Client ID
   - Authorized redirect URIs: `https://grafana.example.com/login/generic_oauth`

2. **Update `.env.production`**:

```bash
# Google OAuth
GRAFANA_AUTH_OAUTH_ENABLED=true
GRAFANA_AUTH_OAUTH_NAME=Google
GRAFANA_AUTH_OAUTH_CLIENT_ID=<your-client-id>.apps.googleusercontent.com
GRAFANA_AUTH_OAUTH_CLIENT_SECRET=<your-client-secret>
GRAFANA_AUTH_OAUTH_SCOPES=openid email profile
GRAFANA_AUTH_OAUTH_AUTH_URL=https://accounts.google.com/o/oauth2/v2/auth
GRAFANA_AUTH_OAUTH_TOKEN_URL=https://oauth2.googleapis.com/token
GRAFANA_AUTH_OAUTH_API_URL=https://openidconnect.googleapis.com/v1/userinfo
GRAFANA_AUTH_OAUTH_ALLOWED_DOMAINS=example.com  # Restrict to domain
```

3. **Disable password login** (optional):

```bash
GRAFANA_AUTH_DISABLE_LOGIN_FORM=true  # OAuth only
```

**GitHub OAuth Example**:

```bash
# GitHub OAuth
GRAFANA_AUTH_OAUTH_ENABLED=true
GRAFANA_AUTH_OAUTH_NAME=GitHub
GRAFANA_AUTH_OAUTH_CLIENT_ID=<github-client-id>
GRAFANA_AUTH_OAUTH_CLIENT_SECRET=<github-client-secret>
GRAFANA_AUTH_OAUTH_SCOPES=user:email read:org
GRAFANA_AUTH_OAUTH_AUTH_URL=https://github.com/login/oauth/authorize
GRAFANA_AUTH_OAUTH_TOKEN_URL=https://github.com/login/oauth/access_token
GRAFANA_AUTH_OAUTH_API_URL=https://api.github.com/user
GRAFANA_AUTH_OAUTH_ALLOWED_ORGANIZATIONS=your-org  # Restrict to org
```

**Okta SAML Example** (Enterprise):

```bash
GRAFANA_AUTH_OAUTH_ENABLED=true
GRAFANA_AUTH_OAUTH_NAME=Okta
GRAFANA_AUTH_OAUTH_CLIENT_ID=<okta-client-id>
GRAFANA_AUTH_OAUTH_CLIENT_SECRET=<okta-client-secret>
GRAFANA_AUTH_OAUTH_SCOPES=openid profile email
GRAFANA_AUTH_OAUTH_AUTH_URL=https://your-domain.okta.com/oauth2/v1/authorize
GRAFANA_AUTH_OAUTH_TOKEN_URL=https://your-domain.okta.com/oauth2/v1/token
GRAFANA_AUTH_OAUTH_API_URL=https://your-domain.okta.com/oauth2/v1/userinfo
```

#### Method 3: LDAP (Enterprise)

1. **Create LDAP config** (`grafana/ldap.toml`):

```toml
[[servers]]
host = "ldap.example.com"
port = 389
use_ssl = false
start_tls = true
bind_dn = "cn=admin,dc=example,dc=com"
bind_password = "admin_password"
search_filter = "(cn=%s)"
search_base_dns = ["dc=example,dc=com"]

[servers.attributes]
name = "givenName"
surname = "sn"
username = "cn"
member_of = "memberOf"
email = "email"

[[servers.group_mappings]]
group_dn = "cn=admins,ou=groups,dc=example,dc=com"
org_role = "Admin"

[[servers.group_mappings]]
group_dn = "cn=users,ou=groups,dc=example,dc=com"
org_role = "Viewer"
```

2. **Enable LDAP**:

```bash
# .env.production
GRAFANA_AUTH_LDAP_ENABLED=true
GRAFANA_AUTH_LDAP_CONFIG_FILE=/etc/grafana/ldap.toml
```

3. **Mount ldap.toml**:

```yaml
# docker-compose.yml
volumes:
  - ./ldap.toml:/etc/grafana/ldap.toml:ro
```

### Security Headers

**Enabled by default in production** (`.env.production`):

```bash
# HTTP Strict Transport Security
GRAFANA_SECURITY_STRICT_TRANSPORT_SECURITY=true
GRAFANA_SECURITY_STRICT_TRANSPORT_SECURITY_MAX_AGE=31536000
GRAFANA_SECURITY_STRICT_TRANSPORT_SECURITY_PRELOAD=true

# Prevent MIME type sniffing
GRAFANA_SECURITY_X_CONTENT_TYPE_OPTIONS=true

# XSS protection
GRAFANA_SECURITY_X_XSS_PROTECTION=true

# Content Security Policy
GRAFANA_SECURITY_CONTENT_SECURITY_POLICY=true

# Secure cookies (HTTPS only)
GRAFANA_SECURITY_COOKIE_SECURE=true

# Disable Gravatar (prevent external leakage)
GRAFANA_SECURITY_DISABLE_GRAVATAR=true
```

### Access Control

```bash
# Disable anonymous access
GRAFANA_AUTH_ANONYMOUS_ENABLED=false

# Disable user sign-up
GRAFANA_USERS_ALLOW_SIGN_UP=false

# Disable guest access
GRAFANA_AUTH_DISABLE_SIGNOUT_MENU=false
```

---

## Prometheus Security

### Basic Authentication

**Setup** (5 minutes):

1. **Generate htpasswd file**:

```bash
cd grafana/
./scripts/generate-prometheus-auth.sh prometheus <strong-password>

# Or interactive:
./scripts/generate-prometheus-auth.sh
```

2. **Update `.env.production`**:

```bash
PROMETHEUS_USER=prometheus
PROMETHEUS_PASSWORD=<your-strong-password>
```

3. **Restart Prometheus**:

```bash
docker-compose restart prometheus
```

4. **Test authentication**:

```bash
# Should fail (401 Unauthorized)
curl http://localhost:9090/metrics

# Should succeed
curl -u prometheus:<password> http://localhost:9090/metrics
```

### Grafana Datasource Configuration

Update `grafana/datasources/prometheus.yml`:

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    basicAuth: true
    basicAuthUser: prometheus
    secureJsonData:
      basicAuthPassword: ${PROMETHEUS_PASSWORD}  # From .env.production
    isDefault: true
    editable: false
```

### Agent Scraping with Authentication

**Option A: Basic Auth** (agents require credentials):

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'kaizen-agents'
    basic_auth:
      username: 'prometheus'
      password_file: /etc/prometheus/prometheus-password.txt
    static_configs:
      - targets: ['agent-1:8000', 'agent-2:8000']
```

**Option B: Bearer Token** (API keys):

```yaml
scrape_configs:
  - job_name: 'kaizen-agents'
    authorization:
      type: Bearer
      credentials_file: /etc/prometheus/token.txt
    static_configs:
      - targets: ['agent-1:8000']
```

### TLS Configuration

For HTTPS agent endpoints:

```yaml
scrape_configs:
  - job_name: 'kaizen-agents'
    scheme: https
    tls_config:
      ca_file: /etc/prometheus/ca.crt
      cert_file: /etc/prometheus/client.crt
      key_file: /etc/prometheus/client.key
      insecure_skip_verify: false  # Verify certificates
```

---

## Jaeger Security

### Elasticsearch Backend (Production)

**Why Elasticsearch?**
- In-memory storage (default) loses data on restart
- Elasticsearch provides persistence, scalability, and security

**Configuration**:

```bash
# .env.production
SPAN_STORAGE_TYPE=elasticsearch
ES_SERVER_URLS=https://elasticsearch:9200
ES_USERNAME=elastic
ES_PASSWORD=<strong-password>
ES_TLS_ENABLED=true
ES_TLS_SKIP_HOST_VERIFY=false  # Verify certificates
```

### Elasticsearch Security

1. **Enable X-Pack Security** (already configured):

```yaml
# docker-compose.yml
elasticsearch:
  environment:
    - xpack.security.enabled=true
    - ELASTIC_PASSWORD=${ES_PASSWORD}
```

2. **Create dedicated Jaeger user** (recommended):

```bash
# Inside Elasticsearch container
docker exec -it kaizen-elasticsearch bash

# Create jaeger user
curl -X POST "localhost:9200/_security/user/jaeger" \
  -u elastic:${ES_PASSWORD} \
  -H "Content-Type: application/json" \
  -d '{
    "password": "<jaeger-strong-password>",
    "roles": ["jaeger_role"]
  }'

# Create jaeger role with minimal permissions
curl -X POST "localhost:9200/_security/role/jaeger_role" \
  -u elastic:${ES_PASSWORD} \
  -H "Content-Type: application/json" \
  -d '{
    "indices": [
      {
        "names": ["jaeger-*"],
        "privileges": ["create_index", "index", "read", "delete"]
      }
    ]
  }'
```

3. **Update Jaeger config**:

```bash
# .env.production
ES_USERNAME=jaeger
ES_PASSWORD=<jaeger-password>
```

### Access Control

**Jaeger UI** should **NOT** be publicly accessible in production.

**Options**:

1. **Reverse Proxy with Authentication** (nginx + basic auth)
2. **VPN/Bastion Host** (SSH tunnel only)
3. **IP Whitelisting** (firewall rules)

**nginx example**:

```nginx
server {
    listen 443 ssl;
    server_name jaeger.example.com;

    ssl_certificate /etc/letsencrypt/live/jaeger.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/jaeger.example.com/privkey.pem;

    # Basic authentication
    auth_basic "Jaeger UI";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://localhost:16686;
    }
}
```

---

## Network Isolation

### Docker Networks (Internal)

**Best practice**: Isolate observability stack on private network.

```yaml
# docker-compose.yml
networks:
  kaizen-observability:
    driver: bridge
    internal: true  # No external access

  kaizen-public:
    driver: bridge

services:
  grafana:
    networks:
      - kaizen-observability
      - kaizen-public  # Only Grafana exposed

  prometheus:
    networks:
      - kaizen-observability  # Private only

  jaeger:
    networks:
      - kaizen-observability  # Private only

  elasticsearch:
    networks:
      - kaizen-observability  # Private only
```

### Firewall Rules (iptables/ufw)

**Ubuntu/Debian** (ufw):

```bash
# Default deny
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (secure remote access)
sudo ufw allow 22/tcp

# Allow HTTPS only (Grafana)
sudo ufw allow 443/tcp

# Deny direct access to Prometheus, Jaeger, Elasticsearch
sudo ufw deny 9090/tcp  # Prometheus
sudo ufw deny 16686/tcp # Jaeger UI
sudo ufw deny 9200/tcp  # Elasticsearch

# Enable firewall
sudo ufw enable
```

**Cloud Security Groups** (AWS example):

```hcl
# Grafana security group (public HTTPS)
resource "aws_security_group" "grafana" {
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]  # Public HTTPS
  }
}

# Observability security group (internal only)
resource "aws_security_group" "observability" {
  ingress {
    from_port       = 0
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.grafana.id]  # Only from Grafana
  }
}
```

### Port Binding (Localhost Only)

**Restrict to localhost** for internal services:

```yaml
# docker-compose.yml
services:
  prometheus:
    ports:
      - "127.0.0.1:9090:9090"  # Localhost only

  jaeger:
    ports:
      - "127.0.0.1:16686:16686"  # Localhost only

  elasticsearch:
    ports:
      - "127.0.0.1:9200:9200"  # Localhost only
```

---

## Secrets Management

### Environment Variables (Minimum)

**Required**: Use `.env.production` instead of hardcoded secrets.

```bash
# .env.production (NOT in git)
GRAFANA_ADMIN_PASSWORD=<secret>
PROMETHEUS_PASSWORD=<secret>
ES_PASSWORD=<secret>
```

**.gitignore**:

```gitignore
# Never commit production secrets
.env.production
grafana/ssl/*.key
grafana/ssl/*.crt
grafana/prometheus-htpasswd
```

### Docker Secrets (Recommended)

**For Docker Swarm / Kubernetes**:

```yaml
# docker-compose.yml (Swarm mode)
version: '3.8'

services:
  grafana:
    secrets:
      - grafana_admin_password
    environment:
      - GF_SECURITY_ADMIN_PASSWORD_FILE=/run/secrets/grafana_admin_password

secrets:
  grafana_admin_password:
    external: true
```

```bash
# Create secret
echo "strong-password" | docker secret create grafana_admin_password -
```

### HashiCorp Vault (Enterprise)

**Production-grade secrets management**:

```bash
# Store secrets in Vault
vault kv put secret/observability/grafana \
  admin_password="strong-password" \
  oauth_client_secret="oauth-secret"

# Retrieve at runtime
GRAFANA_ADMIN_PASSWORD=$(vault kv get -field=admin_password secret/observability/grafana)
```

**Vault Agent** (auto-inject secrets):

```hcl
# vault-agent.hcl
vault {
  address = "https://vault.example.com"
}

auto_auth {
  method {
    type = "kubernetes"
  }
}

template {
  source      = "/etc/vault/templates/grafana.env.tpl"
  destination = "/app/.env.production"
}
```

### AWS Secrets Manager

```bash
# Store secret
aws secretsmanager create-secret \
  --name observability/grafana/admin-password \
  --secret-string "strong-password"

# Retrieve in entrypoint script
GRAFANA_ADMIN_PASSWORD=$(aws secretsmanager get-secret-value \
  --secret-id observability/grafana/admin-password \
  --query SecretString \
  --output text)
```

### Secrets Rotation

**Best practice**: Rotate credentials quarterly.

**Procedure**:

1. **Generate new password**: `openssl rand -base64 24`
2. **Update `.env.production`** with new password
3. **Restart service**: `docker-compose restart grafana`
4. **Update dependent services** (datasources, scrapers)
5. **Verify connectivity**: Test all integrations
6. **Document rotation**: Log in secrets rotation ledger

**Automated rotation** (recommended):

```bash
#!/bin/bash
# rotate-grafana-password.sh

NEW_PASSWORD=$(openssl rand -base64 24)

# Update Vault
vault kv put secret/observability/grafana admin_password="${NEW_PASSWORD}"

# Trigger rolling restart
docker-compose restart grafana

# Send notification
curl -X POST https://slack.com/api/chat.postMessage \
  -H "Authorization: Bearer ${SLACK_TOKEN}" \
  -d "text=Grafana password rotated successfully"
```

---

## Compliance Considerations

### SOC 2 Requirements

| Control | Requirement | Implementation |
|---------|-------------|----------------|
| CC6.1 | Logical access security | OAuth/LDAP, MFA |
| CC6.6 | Encryption in transit | TLS/HTTPS everywhere |
| CC6.7 | Encryption at rest | Encrypted volumes |
| CC7.2 | Audit logging | Grafana audit logs |
| CC7.3 | Access review | Quarterly user audits |

**Evidence collection**:

```bash
# Grafana audit log
docker logs kaizen-grafana | grep "user.login"

# Access review report
docker exec kaizen-grafana grafana-cli admin user-list
```

### GDPR Compliance

**Personal data handling**:

- **Minimize data collection**: Disable unnecessary metrics
- **Data retention**: Configure Prometheus retention (30 days)
- **Right to deletion**: Provide data export/deletion tools
- **Consent tracking**: Log user consent in audit trail

**Prometheus retention**:

```yaml
# prometheus.yml
storage:
  tsdb:
    retention.time: 30d  # GDPR: reasonable retention
```

### HIPAA Compliance

**Additional requirements for healthcare data**:

- **Encryption in transit**: TLS 1.2+ (mandatory)
- **Encryption at rest**: Encrypted volumes (mandatory)
- **Audit trails**: All access logged (mandatory)
- **Access control**: Role-based access (mandatory)
- **PHI handling**: Tag sensitive metrics, restrict access

**Elasticsearch encryption at rest**:

```yaml
elasticsearch:
  volumes:
    - type: volume
      source: elasticsearch-data
      target: /usr/share/elasticsearch/data
      volume:
        driver: local
        driver_opts:
          type: "luks"  # LUKS encryption
```

### PCI-DSS Requirements

**For systems handling payment data**:

- **Requirement 2.1**: Change default passwords (mandatory)
- **Requirement 4.1**: Encrypt transmission (TLS/HTTPS)
- **Requirement 8.2**: Strong authentication (MFA required)
- **Requirement 10.1**: Audit trails (all access logged)

**Compliance checks**:

```bash
# 1. No default passwords
grep -i "admin:admin" .env.production && echo "FAIL" || echo "PASS"

# 2. HTTPS enabled
grep "GRAFANA_SERVER_PROTOCOL=https" .env.production && echo "PASS" || echo "FAIL"

# 3. Strong passwords (12+ chars)
echo $GRAFANA_ADMIN_PASSWORD | awk '{print length($0) >= 12 ? "PASS" : "FAIL"}'
```

---

## Security Best Practices

### 1. Principle of Least Privilege

**Grant minimum necessary permissions**:

- **Grafana**: Viewer role by default, Admin only for ops team
- **Prometheus**: Read-only access for most users
- **Elasticsearch**: Dedicated roles (jaeger_role, readonly_role)

### 2. Defense in Depth

**Multiple layers of security**:

1. **Perimeter**: Firewall, security groups
2. **Network**: TLS, authentication
3. **Application**: OAuth, RBAC
4. **Data**: Encryption at rest
5. **Audit**: Comprehensive logging

### 3. Regular Security Audits

**Quarterly checklist**:

- [ ] Review user accounts (remove unused accounts)
- [ ] Rotate all credentials (passwords, API keys)
- [ ] Update dependencies (Grafana, Prometheus, Jaeger)
- [ ] Review firewall rules (remove unnecessary access)
- [ ] Check SSL certificate expiry (renew if needed)
- [ ] Audit access logs (investigate anomalies)
- [ ] Test disaster recovery (restore from backup)

### 4. Monitoring & Alerting

**Security alerts** (configure in Grafana):

- Failed login attempts (>5 in 5 minutes)
- Password changes (admin accounts)
- Unauthorized API access (401/403 errors)
- Certificate expiry (30 days before)
- Unusual traffic patterns (DDoS detection)

**Example alert**:

```yaml
# grafana/alerts/security.yml
apiVersion: 1
groups:
  - name: Security
    interval: 1m
    rules:
      - alert: HighFailedLoginRate
        expr: rate(grafana_failed_login_total[5m]) > 5
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High failed login rate detected"
          description: "{{ $value }} failed logins per second"
```

### 5. Backup & Disaster Recovery

**What to backup**:

- Grafana dashboards, datasources, users (`/var/lib/grafana`)
- Prometheus data (`/prometheus`)
- Elasticsearch indices (Jaeger traces)
- Configuration files (`.env.production`, `prometheus.yml`)

**Backup script**:

```bash
#!/bin/bash
# backup-observability.sh

BACKUP_DIR="/backups/observability/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# Grafana database
docker exec kaizen-grafana grafana-cli admin export \
  > "$BACKUP_DIR/grafana-export.json"

# Prometheus data (snapshot)
docker exec kaizen-prometheus promtool tsdb snapshot /prometheus \
  --out "$BACKUP_DIR/prometheus-snapshot"

# Elasticsearch snapshot
curl -X PUT "localhost:9200/_snapshot/backup/snapshot_$(date +%Y%m%d)" \
  -u elastic:${ES_PASSWORD}

# Configuration files
tar -czf "$BACKUP_DIR/config.tar.gz" \
  grafana/prometheus.yml \
  grafana/datasources/ \
  grafana/dashboards/

echo "Backup completed: $BACKUP_DIR"
```

**Restore procedure** (document in runbook).

---

## Incident Response

### Security Incident Playbook

#### Phase 1: Detection

**Indicators of compromise**:
- Multiple failed login attempts
- Unexpected configuration changes
- Unusual API traffic patterns
- Data exfiltration (large downloads)

**Detection tools**:
- Grafana audit logs
- Prometheus access logs
- Elasticsearch query logs
- Docker logs

#### Phase 2: Containment

**Immediate actions** (within 1 hour):

1. **Isolate affected services**:
   ```bash
   docker-compose stop grafana  # Stop compromised service
   ```

2. **Reset credentials**:
   ```bash
   ./scripts/rotate-all-passwords.sh
   ```

3. **Block attacker IP**:
   ```bash
   sudo ufw deny from <attacker-ip>
   ```

4. **Review access logs**:
   ```bash
   docker logs kaizen-grafana | grep <attacker-ip>
   ```

#### Phase 3: Eradication

**Root cause analysis**:

- Identify entry point (default password, CVE, misconfiguration)
- Check for backdoors (unauthorized users, API keys)
- Scan for malware (if applicable)

**Remediation**:

- Apply security patches
- Remove unauthorized accounts
- Revoke compromised credentials
- Update firewall rules

#### Phase 4: Recovery

**Restore from backup**:

```bash
# Restore Grafana
docker exec kaizen-grafana grafana-cli admin import \
  /backups/grafana-export.json

# Restart services
docker-compose up -d
```

**Verify integrity**:

- Test authentication
- Check dashboards, datasources
- Verify metrics collection

#### Phase 5: Post-Incident

**Documentation**:

- Timeline of events
- Root cause analysis
- Remediation actions
- Lessons learned

**Improvements**:

- Implement additional controls
- Update incident response plan
- Train team on new procedures

---

## Quick Reference

### Emergency Contacts

| Role | Contact | Escalation |
|------|---------|------------|
| Security Team | security@example.com | Immediate |
| DevOps On-Call | +1-555-0100 | 15 minutes |
| Compliance Officer | compliance@example.com | 24 hours |

### Security Checklist (1-Page)

**Pre-Production**:
- [ ] Strong passwords (16+ chars)
- [ ] SSL/TLS certificates generated
- [ ] OAuth/LDAP configured
- [ ] `.env.production` created (not in git)

**Hardening**:
- [ ] HTTPS enabled (Grafana)
- [ ] Basic auth enabled (Prometheus)
- [ ] Elasticsearch auth enabled
- [ ] Security headers enabled
- [ ] Anonymous access disabled

**Network**:
- [ ] Firewall rules configured
- [ ] Docker networks isolated
- [ ] Reverse proxy (optional)

**Monitoring**:
- [ ] Security alerts configured
- [ ] Audit logging enabled
- [ ] Backup scheduled

**Compliance**:
- [ ] SOC2/GDPR/HIPAA requirements met
- [ ] Quarterly audit scheduled

---

## Resources

### Tools

- **certbot**: Let's Encrypt automation - https://certbot.eff.org/
- **htpasswd**: Basic auth password generator - `apache2-utils`
- **openssl**: Certificate generation, password generation
- **HashiCorp Vault**: Secrets management - https://vaultproject.io/

### Documentation

- **Grafana Security**: https://grafana.com/docs/grafana/latest/setup-grafana/configure-security/
- **Prometheus Security**: https://prometheus.io/docs/operating/security/
- **Jaeger Security**: https://www.jaegertracing.io/docs/latest/security/
- **Elasticsearch Security**: https://www.elastic.co/guide/en/elasticsearch/reference/current/security-settings.html

### Compliance Frameworks

- **SOC 2**: https://www.aicpa.org/soc2
- **GDPR**: https://gdpr.eu/
- **HIPAA**: https://www.hhs.gov/hipaa/
- **PCI-DSS**: https://www.pcisecuritystandards.org/

---

**Last Updated**: 2025-10-24
**Maintained By**: Kaizen DevOps Team
**Review Cycle**: Quarterly

For questions or security concerns, contact: security@example.com
