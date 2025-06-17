# Security Architecture Patterns

*Security patterns and best practices for Kailash applications*

## 🔒 Security Layers

### 1. **Authentication Layer**

```python
from kailash.security import AuthenticationManager
from kailash.nodes.security import MultiFactorAuthNode, OAuth2Node

# Multi-factor authentication
workflow.add_node("mfa", MultiFactorAuthNode(
    auth_methods=["password", "totp", "biometric"],
    session_timeout=3600,
    max_attempts=3,
    lockout_duration=900  # 15 minutes
))

# OAuth2 integration
workflow.add_node("oauth", OAuth2Node(
    provider="azure",
    client_id="${OAUTH_CLIENT_ID}",
    client_secret="${OAUTH_CLIENT_SECRET}",
    redirect_uri="https://app.com/callback",
    scope="read write profile",
    pkce_enabled=True  # Proof Key for Code Exchange
))

# JWT token management
workflow.add_node("jwt_handler", JWTHandlerNode(
    secret_key="${JWT_SECRET}",
    algorithm="RS256",
    expiration=3600,
    refresh_enabled=True,
    refresh_expiration=86400
))

```

### 2. **Authorization Layer**

```python
from kailash.runtime.access_controlled import AccessControlledRuntime
from kailash.access_control import AccessControlManager, UserContext

# User context with attributes
user_context = UserContext(
    user_id="user123",
    roles=["analyst", "viewer"],
    attributes={
        "department": "finance",
        "clearance_level": "confidential",
        "region": "US",
        "ip_address": request.client.host
    }
)

# Hybrid access control (RBAC + ABAC)
access_manager = AccessControlManager(
    strategy="hybrid",
    rbac_rules={
        "analyst": ["read", "analyze", "export"],
        "viewer": ["read"]
    },
    abac_policies=[
        {
            "effect": "allow",
            "action": "export",
            "condition": "user.clearance_level >= 'confidential'"
        },
        {
            "effect": "deny",
            "action": "delete",
            "condition": "user.department != 'admin'"
        }
    ]
)

# Secure runtime
runtime = AccessControlledRuntime(
    user_context=user_context,
    access_manager=access_manager,
    audit_enabled=True
)

```

### 3. **Data Protection Layer**

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Encryption at rest
workflow = Workflow("example", name="Example")
workflow.  # Method signature)

# Decryption with key rotation
workflow = Workflow("example", name="Example")
workflow.  # Method signature)

# Data masking
workflow = Workflow("example", name="Example")
workflow.  # Method signature)

# Field-level encryption
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("field_encryptor", FieldEncryptionNode(
    fields=["ssn", "credit_card", "medical_record"],
    algorithm="AES-256-CBC",
    preserve_format=True  # Format-preserving encryption
))

```

## 🛡️ Security Patterns

### 1. **Zero Trust Architecture**

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Every request is verified
workflow = Workflow("zero-trust", name="Zero Trust Pipeline")

# Identity verification
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("verify_identity", IdentityVerificationNode(
    methods=["certificate", "token", "biometric"],
    trust_score_threshold=0.8
))

# Device verification
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("verify_device", DeviceVerificationNode(
    check_compliance=True,
    allowed_platforms=["windows", "macos", "linux"],
    require_encryption=True
))

# Context verification
workflow = Workflow("example", name="Example")
workflow.  # Method signature)

# Risk assessment
workflow = Workflow("example", name="Example")
workflow.  # Method signature)

# Connect verification pipeline
workflow = Workflow("example", name="Example")
workflow.workflow.connect("verify_identity", "verify_device")
workflow = Workflow("example", name="Example")
workflow.workflow.connect("verify_device", "verify_context")
workflow = Workflow("example", name="Example")
workflow.workflow.connect("verify_context", "risk_scorer")

```

### 2. **API Security Pattern**

```python
# Secure API gateway
from kailash.api.gateway import create_gateway

gateway = create_gateway(
    workflows=workflows,
    config={
        # Authentication
        "enable_auth": True,
        "auth_providers": ["jwt", "api_key", "oauth2"],

        # Rate limiting
        "rate_limiting": {
            "enabled": True,
            "default_limit": 100,
            "window": 60,
            "by_user": {
                "premium": 1000,
                "standard": 100,
                "trial": 10
            }
        },

        # Security headers
        "security_headers": {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000",
            "Content-Security-Policy": "default-src 'self'"
        },

        # Input validation
        "input_validation": {
            "max_body_size": "10MB",
            "allowed_content_types": ["application/json"],
            "schema_validation": True
        },

        # CORS configuration
        "cors": {
            "allowed_origins": ["https://app.company.com"],
            "allowed_methods": ["GET", "POST"],
            "allowed_headers": ["Content-Type", "Authorization"],
            "max_age": 3600
        }
    }
)

```

### 3. **Secrets Management Pattern**

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Centralized secrets management
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("secrets_manager", SecretsManagerNode(
    provider="vault",
    vault_url="${VAULT_URL}",
    namespace="production",
    auth_method="kubernetes"
))

# Dynamic secret retrieval
workflow = Workflow("example", name="Example")
workflow.  # Method signature

    # Secrets have TTL
    if secret_data['ttl'] < 300:  # 5 minutes
        # Rotate secret before expiry
        new_secret = secrets_manager.rotate(secret_path)
        secret_data = new_secret

    result = {
        "secret": secret_data['value'],
        "expires_at": secret_data['expires_at']
    }
except Exception as e:
    result = {"error": "Failed to retrieve secret", "details": str(e)}
''',
    input_types={"environment": str, "service": str}
))

# Environment variable injection
workflow = Workflow("example", name="Example")
workflow.  # Method signature)

```

### 4. **Input Validation Pattern**

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Comprehensive input validation
workflow = Workflow("example", name="Example")
workflow.  # Method signature)

# Custom validation logic
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("custom_validator", PythonCodeNode(
    name="custom_validator",
    code='''
import re
from urllib.parse import urlparse

def validate_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def validate_credit_card(number):
    # Luhn algorithm
    digits = [int(d) for d in str(number) if d.isdigit()]
    checksum = sum(digits[-1::-2]) + sum(sum(divmod(d*2, 10)) for d in digits[-2::-2])
    return checksum % 10 == 0

errors = []
if not validate_url(data.get('website', '')):
    errors.append("Invalid website URL")

if not validate_credit_card(data.get('card_number', '')):
    errors.append("Invalid credit card number")

result = {
    "valid": len(errors) == 0,
    "errors": errors,
    "data": data if not errors else None
}
''',
    input_types={"data": dict}
))

```

### 5. **Audit Trail Pattern**

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Comprehensive audit logging
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("audit_logger", AuditLoggerNode(
    log_level="info",
    destinations=["database", "siem", "file"],
    include_fields=[
        "user_id", "action", "resource",
        "timestamp", "ip_address", "user_agent"
    ],
    exclude_fields=["password", "secret", "token"],
    retention_days=2555  # 7 years for compliance
))

# Compliance reporting
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("compliance_reporter", ComplianceReporterNode(
    standards=["SOC2", "HIPAA", "GDPR"],
    report_frequency="daily",
    include_metrics=[
        "access_attempts",
        "data_exports",
        "permission_changes",
        "security_incidents"
    ]
))

```

## 🔐 Security Best Practices

### 1. **Secure Coding**

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# SQL injection prevention
workflow = Workflow("example", name="Example")
workflow.  # Method signature)

# XSS prevention
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("xss_prevention", PythonCodeNode(
    name="xss_prevention",
    code='''
import html
from markupsafe import Markup, escape

# Escape user input
safe_input = html.escape(user_input)

# Use template with auto-escaping
template = '''
<div>
    <h1>{{ title }}</h1>
    <p>{{ content }}</p>
</div>
'''

result = {
    "safe_html": Markup(template).format(
        title=escape(title),
        content=escape(content)
    )
}
''',
    input_types={"user_input": str, "title": str, "content": str}
))

```

### 2. **Network Security**

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# TLS configuration
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("tls_client", HTTPRequestNode(
    verify_ssl=True,
    ssl_version="TLSv1.3",
    cipher_suites=[
        "TLS_AES_256_GCM_SHA384",
        "TLS_CHACHA20_POLY1305_SHA256"
    ],
    client_cert=("client.crt", "client.key"),
    ca_bundle="/path/to/ca-bundle.crt"
))

# Network isolation
workflow = Workflow("example", name="Example")
workflow.  # Method signature)

```

### 3. **Container Security**

```dockerfile
# Secure Dockerfile
FROM python:3.11-slim-bullseye

# Run as non-root user
RUN useradd -m -u 1000 appuser

# Security updates
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY --chown=appuser:appuser requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY --chown=appuser:appuser . /app
WORKDIR /app

# Security hardening
RUN chmod -R 550 /app && \
    find /app -type f -name "*.py" -exec chmod 440 {} \;

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Run with security options
ENTRYPOINT ["python", "-u"]
CMD ["main.py"]
```

## 🚨 Threat Detection

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Anomaly detection
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("anomaly_detector", AnomalyDetectionNode(
    models=["isolation_forest", "one_class_svm"],
    sensitivity=0.95,
    training_data="historical_patterns.pkl"
))

# Threat intelligence
workflow = Workflow("example", name="Example")
workflow.  # Method signature)

# Intrusion detection
workflow = Workflow("example", name="Example")
workflow.  # Method signature)

```

## 🔗 Next Steps

- [Performance Patterns](performance-patterns.md) - Performance optimization
- [Security Guide](../developer/04-production.md#security) - Implementation details
- [Monitoring Guide](../monitoring/) - Security monitoring