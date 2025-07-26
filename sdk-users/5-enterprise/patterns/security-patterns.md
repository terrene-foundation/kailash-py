# Security Architecture Patterns

*Security patterns and best practices for Kailash applications*

## 🔒 Security Layers

### 1. **Authentication Layer**

```python
from kailash.security import AuthenticationManager
from kailash.nodes.security import MultiFactorAuthNode, OAuth2Node

# Multi-factor authentication
workflow.add_node("MultiFactorAuthNode", "mfa", {}))

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
workflow.add_node("JWTHandlerNode", "jwt_handler", {}))

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
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Encryption at rest
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

# Decryption with key rotation
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

# Data masking
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

# Field-level encryption
workflow = WorkflowBuilder()
workflow.add_node("FieldEncryptionNode", "field_encryptor", {}))

```

## 🛡️ Security Patterns

### 1. **Zero Trust Architecture**

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Every request is verified
workflow = WorkflowBuilder()

# Identity verification
workflow = WorkflowBuilder()
workflow.add_node("IdentityVerificationNode", "verify_identity", {}))

# Device verification
workflow = WorkflowBuilder()
workflow.add_node("DeviceVerificationNode", "verify_device", {}))

# Context verification
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

# Risk assessment
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

# Connect verification pipeline
workflow = WorkflowBuilder()
workflow.add_connection("verify_identity", "result", "verify_device", "input")
workflow = WorkflowBuilder()
workflow.add_connection("verify_device", "result", "verify_context", "input")
workflow = WorkflowBuilder()
workflow.add_connection("verify_context", "result", "risk_scorer", "input")

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
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Centralized secrets management
workflow = WorkflowBuilder()
workflow.add_node("SecretsManagerNode", "secrets_manager", {}))

# Dynamic secret retrieval
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

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
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

```

### 4. **Input Validation Pattern**

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Comprehensive input validation
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

# Custom validation logic
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "custom_validator", {}):
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
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Comprehensive audit logging
workflow = WorkflowBuilder()
workflow.add_node("AuditLoggerNode", "audit_logger", {}))

# Compliance reporting
workflow = WorkflowBuilder()
workflow.add_node("ComplianceReporterNode", "compliance_reporter", {}))

```

## 🔐 Security Best Practices

### 1. **Secure Coding**

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# SQL injection prevention
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

# XSS prevention
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "xss_prevention", {})

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
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# TLS configuration
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "tls_client", {}),
    ca_bundle="/path/to/ca-bundle.crt"
))

# Network isolation
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

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
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Anomaly detection
workflow = WorkflowBuilder()
workflow.add_node("AnomalyDetectionNode", "anomaly_detector", {}))

# Threat intelligence
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

# Intrusion detection
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

```

## 🔗 Next Steps

- [Performance Patterns](performance-patterns.md) - Performance optimization
- [Security Guide](../developer/04-production.md#security) - Implementation details
- [Monitoring Guide](../monitoring/) - Security monitoring
