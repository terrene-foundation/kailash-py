# Security Configuration - Production Safety

## Core Security Setup
```python
from kailash.security import SecurityConfig, set_security_config

# Configure security constraints
config = SecurityConfig(
    allowed_directories=["/app/data", "/tmp/kailash"],
    max_file_size=50 * 1024 * 1024,  # 50MB
    execution_timeout=60.0,           # 1 minute
    memory_limit=256 * 1024 * 1024,   # 256MB
    enable_audit_logging=True
)
set_security_config(config)

```

## Access Control Runtime
```python
from kailash.runtime.access_controlled import AccessControlledRuntime
from kailash.access_control import UserContext, PermissionRule

# Create user context
user = UserContext(
    user_id="user123",
    roles=["analyst", "reader"],
    attributes={"department": "finance", "level": "senior"}
)

# Use access-controlled runtime
runtime = AccessControlledRuntime(user_context=user)
results, run_id = runtime.execute(workflow.build())

```

## Security Nodes
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

# Authentication
workflow = WorkflowBuilder()
workflow.add_node("MultiFactorAuthNode", "auth", {}),
    auth_methods=["password", "totp"],
    session_timeout=3600
)

# OAuth2 Integration with Runtime Secret Management
workflow = WorkflowBuilder()
workflow.add_node("oauth", OAuth2Node(),
    provider="azure",
    client_id="azure_client_id",  # Secret name, not value
    client_secret="azure_client_secret",  # Secret name, not value
    scope="read write"
)

# Secrets are automatically injected at runtime by SecretProvider

# Threat Detection
workflow = WorkflowBuilder()
workflow.add_node("ThreatDetectionNode", "security", {}),
    detection_rules=["sql_injection", "xss", "path_traversal"],
    action="block_and_alert"
)

```

## Safe File Operations
```python
from kailash.security import safe_open, validate_file_path

# Validate paths
safe_path = validate_file_path("/app/data/file.txt")

# Safe file I/O with validation
with safe_open("data/file.txt", "r") as f:
    content = f.read()

# Secure node with path validation
workflow.add_node("CSVReaderNode", "reader", {}),
    file_path=safe_path,
    validate_path=True  # Auto-validate
)

```

## Runtime Secret Management
```python
# ✅ NEW: Runtime secret injection (v0.8.1+)
from kailash.runtime.local import LocalRuntime
from kailash.runtime.secret_provider import EnvironmentSecretProvider

# Create runtime with secret provider
secret_provider = EnvironmentSecretProvider()
runtime = LocalRuntime(secret_provider=secret_provider)

# Secrets are injected at runtime - NO hardcoding needed!
workflow.add_node("HTTPRequestNode", "api", {}),
    url="https://api.example.com",
    headers={"Authorization": "Bearer {secret_will_be_injected}"}
)

# Node declares its secret requirements
class APINode(Node):
    @classmethod
    def get_secret_requirements(cls):
        return [SecretRequirement("api-token", "auth_token")]

# Multiple secret providers supported
from kailash.runtime.secret_provider import VaultSecretProvider, AWSSecretProvider

# HashiCorp Vault
vault_provider = VaultSecretProvider('https://vault.company.com', 'token')
runtime = LocalRuntime(secret_provider=vault_provider)

# AWS Secrets Manager
aws_provider = AWSSecretProvider('us-east-1')
runtime = LocalRuntime(secret_provider=aws_provider)

```

## Legacy Credential Management
```python
# ❌ DEPRECATED: Static credential management
from kailash.security import CredentialManager
creds = CredentialManager()
api_key = creds.get_secret("api_key")

# ⚠️ ANTI-PATTERN: Environment variables for secrets
import os
api_key = os.getenv("API_KEY")  # Avoid this pattern

```

## Common Security Patterns
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

# Input sanitization in PythonCodeNode
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "sanitize", {})
result = {'sanitized': safe_input}
''',
    input_types={"user_input": str}
))

# Rate limiting
workflow = WorkflowBuilder()
workflow.add_node("RateLimiterNode", "limiter", {}),
    max_requests=100,
    window_seconds=60,
    key_field="user_id"
)

```

## Next Steps
- [Access Control](014-access-control-multi-tenancy.md) - RBAC/ABAC
- [Production Guide](../../developer/04-production.md) - Security best practices
- [Runtime Secret Management](052-runtime-secret-management.md) - Complete secret management guide
- [Environment Variables](016-environment-variables.md) - Legacy patterns (avoid for secrets)
