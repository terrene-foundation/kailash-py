# Runtime Secret Management - Enterprise Security

## Overview
Runtime secret management eliminates security anti-patterns by injecting secrets at execution time rather than embedding them in code or environment variables.

## Core Concepts

### SecretProvider Interface
```python
from kailash.runtime.secret_provider import SecretProvider, SecretRequirement

class SecretProvider(ABC):
    def get_secret(self, name: str, version: Optional[str] = None) -> str:
        """Fetch a secret by name and optional version."""
        pass

    def list_secrets(self) -> List[str]:
        """List available secrets."""
        pass

    def get_secrets(self, requirements: List[SecretRequirement]) -> Dict[str, str]:
        """Fetch multiple secrets based on requirements."""
        pass
```

### Secret Requirements
```python
from kailash.runtime.secret_provider import SecretRequirement

# Declare what secrets your node needs
class APINode(Node):
    @classmethod
    def get_secret_requirements(cls):
        return [
            SecretRequirement("jwt-signing-key", "secret_key"),
            SecretRequirement("api-token", "auth_token", optional=True)
        ]
```

## Built-in Secret Providers

### Environment Provider
```python
from kailash.runtime.secret_provider import EnvironmentSecretProvider

# Default prefix: KAILASH_SECRET_
provider = EnvironmentSecretProvider()

# Custom prefix
provider = EnvironmentSecretProvider(prefix="MYAPP_SECRET_")

# Environment variables:
# KAILASH_SECRET_JWT_SIGNING_KEY=your_secret_here
# KAILASH_SECRET_API_TOKEN=your_token_here
```

### HashiCorp Vault Provider
```python
from kailash.runtime.secret_provider import VaultSecretProvider

# Connect to Vault
provider = VaultSecretProvider(
    vault_url="https://vault.company.com:8200",
    vault_token="hvs.token_here",
    mount_path="secret"  # KV mount path
)

# Supports both KV v1 and v2
secret = provider.get_secret("jwt-signing-key")
```

### AWS Secrets Manager Provider
```python
from kailash.runtime.secret_provider import AWSSecretProvider

# AWS Secrets Manager
provider = AWSSecretProvider(region_name="us-east-1")

# Uses AWS credentials from:
# - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
# - IAM roles
# - AWS credentials file
```

## Runtime Integration

### LocalRuntime with Secret Provider
```python
from kailash.runtime.local import LocalRuntime
from kailash.runtime.secret_provider import EnvironmentSecretProvider

# Create runtime with secret provider
secret_provider = EnvironmentSecretProvider()
runtime = LocalRuntime(secret_provider=secret_provider)

# Secrets are automatically injected during workflow execution
results, run_id = runtime.execute(workflow.build())
```

### Workflow Secret Declaration
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.secret_provider import SecretRequirement

# Create workflow without secrets in parameters
workflow = WorkflowBuilder()
workflow.add_node("TokenGeneratorNode", "token_gen", {
    "user_id": "user123"
    # Note: No secret_key provided - injected at runtime!
})

# Node declares its secret requirements
class TokenGeneratorNode(Node):
    @classmethod
    def get_secret_requirements(cls):
        return [
            SecretRequirement("jwt-signing-key", "secret_key")
        ]

    def run(self, secret_key, user_id, **kwargs):
        # Secret is automatically injected here
        token = generate_jwt(secret_key, user_id)
        return {"token": token}
```

## Security Benefits

### ✅ Secure Patterns
```python
# ✅ Runtime secret injection
runtime = LocalRuntime(secret_provider=provider)
workflow.add_node("HTTPRequestNode", "api", {
    "url": "https://api.example.com",
    "headers": {"Authorization": "Bearer {injected_token}"}
})

# ✅ Declarative secret requirements
class APINode(Node):
    @classmethod
    def get_secret_requirements(cls):
        return [SecretRequirement("api-token", "auth_token")]

# ✅ Multiple provider support
providers = {
    "vault": VaultSecretProvider("https://vault.com", "token"),
    "aws": AWSSecretProvider("us-east-1"),
    "env": EnvironmentSecretProvider()
}
```

### ❌ Anti-Patterns to Avoid
```python
# ❌ Hardcoded secrets
workflow.add_node("HTTPRequestNode", "api", {
    "headers": {"Authorization": "Bearer sk-abc123"}  # NEVER DO THIS
})

# ❌ Environment variables in code
import os
secret = os.getenv("API_KEY")  # Avoid this pattern

# ❌ Template substitution
workflow.add_node("HTTPRequestNode", "api", {
    "headers": {"Authorization": "Bearer ${API_TOKEN}"}  # Legacy pattern
})
```

## Enterprise Patterns

### Multi-Environment Configuration
```python
# Production
vault_provider = VaultSecretProvider(
    vault_url="https://vault.prod.company.com",
    vault_token=os.getenv("VAULT_TOKEN"),
    mount_path="production"
)

# Development
env_provider = EnvironmentSecretProvider(prefix="DEV_SECRET_")

# Runtime selection
provider = vault_provider if is_production else env_provider
runtime = LocalRuntime(secret_provider=provider)
```

### Secret Rotation Support
```python
# Versioned secrets
secret = provider.get_secret("api-key", version="v2")

# Automatic rotation detection
requirements = [
    SecretRequirement("api-key", "current_key"),
    SecretRequirement("api-key", "previous_key", version="v1", optional=True)
]
```

### Multi-Tenant Secret Management
```python
class TenantSecretProvider(SecretProvider):
    def __init__(self, base_provider: SecretProvider, tenant_id: str):
        self.base_provider = base_provider
        self.tenant_id = tenant_id

    def get_secret(self, name: str, version: Optional[str] = None) -> str:
        # Prefix with tenant ID
        tenant_secret_name = f"{self.tenant_id}/{name}"
        return self.base_provider.get_secret(tenant_secret_name, version)
```

## Error Handling

### Secret Not Found
```python
from kailash.runtime.secret_provider import SecretNotFoundError

try:
    secret = provider.get_secret("nonexistent-secret")
except SecretNotFoundError as e:
    logger.error(f"Secret not found: {e}")
    # Handle gracefully
```

### Optional Secrets
```python
requirements = [
    SecretRequirement("required-key", "required_param"),
    SecretRequirement("optional-key", "optional_param", optional=True)
]

# Runtime will not fail if optional secrets are missing
secrets = provider.get_secrets(requirements)
```

## Migration Guide

### From Environment Variables
```python
# Before (insecure)
import os
api_key = os.getenv("API_KEY")
workflow.add_node("HTTPRequestNode", "api", {}), {
    "headers": {"Authorization": f"Bearer {api_key}"}
})

# After (secure)
secret_provider = EnvironmentSecretProvider()
runtime = LocalRuntime(secret_provider=secret_provider)
workflow.add_node("HTTPRequestNode", "api", {}), {
    "headers": {"Authorization": "Bearer {api_key}"}  # Injected at runtime
})
```

### From Static Credentials
```python
# Before (static)
from kailash.security import CredentialManager
creds = CredentialManager()
api_key = creds.get_secret("api_key")

# After (runtime)
from kailash.runtime.secret_provider import VaultSecretProvider
provider = VaultSecretProvider("https://vault.com", "token")
runtime = LocalRuntime(secret_provider=provider)
```

## Best Practices

1. **Use Runtime Injection**: Never hardcode secrets in workflow parameters
2. **Declare Requirements**: Use `get_secret_requirements()` for clear documentation
3. **Choose Right Provider**: Environment for dev, Vault/AWS for production
4. **Handle Errors**: Gracefully handle missing optional secrets
5. **Rotate Regularly**: Use versioned secrets for rotation support
6. **Audit Access**: Monitor secret access patterns
7. **Principle of Least Privilege**: Only request secrets your node needs

## Production Deployment

```python
# production.py
from kailash.runtime.local import LocalRuntime
from kailash.runtime.secret_provider import VaultSecretProvider

# Production-ready configuration
def create_production_runtime():
    provider = VaultSecretProvider(
        vault_url=os.getenv("VAULT_URL"),
        vault_token=os.getenv("VAULT_TOKEN"),
        mount_path="production"
    )

    return LocalRuntime(
        secret_provider=provider,
        enable_audit_logging=True,
        max_execution_time=300
    )

# Usage
runtime = create_production_runtime()
results, run_id = runtime.execute(workflow.build())
```

## Next Steps
- [Security Configuration](008-security-configuration.md) - Complete security setup
- [Production Guide](../developer/04-production.md) - Production deployment
- [Enterprise Patterns](../enterprise/security-patterns.md) - Advanced security patterns
