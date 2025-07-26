# Environment Variables - Configuration Management

## ⚠️ SECURITY WARNING
**For secrets and credentials, use [Runtime Secret Management](052-runtime-secret-management.md) instead of environment variables.**

Environment variables should be used for:
- ✅ Configuration (timeouts, pool sizes, feature flags)
- ✅ Non-sensitive URLs and endpoints
- ❌ **NOT for secrets, API keys, or passwords**

## AI/LLM Provider Configuration
```python
import os

# ⚠️ DEPRECATED: Direct API key assignment
# os.environ["OPENAI_API_KEY"] = "sk-..."  # Use runtime secret management instead

# ✅ RECOMMENDED: Non-sensitive configuration only
os.environ["OPENAI_ORG_ID"] = "org-..."
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
os.environ["OLLAMA_TIMEOUT"] = "120"
os.environ["AZURE_OPENAI_ENDPOINT"] = "https://..."
os.environ["AZURE_OPENAI_VERSION"] = "2024-02-15-preview"

# ✅ NEW: Use runtime secret management for API keys
from kailash.runtime.secret_provider import EnvironmentSecretProvider
from kailash.runtime.local import LocalRuntime

secret_provider = EnvironmentSecretProvider()
runtime = LocalRuntime(secret_provider=secret_provider)

# Set secrets via environment with proper prefix:
# KAILASH_SECRET_OPENAI_API_KEY=sk-...
# KAILASH_SECRET_ANTHROPIC_API_KEY=sk-ant-...
# KAILASH_SECRET_AZURE_OPENAI_API_KEY=...

```

## Authentication & Security Configuration
```python
# ⚠️ DEPRECATED: Direct secret assignment
# os.environ["SHAREPOINT_CLIENT_SECRET"] = "..."  # Use runtime secret management
# os.environ["API_CLIENT_SECRET"] = "..."         # Use runtime secret management
# os.environ["KAILASH_SECRET_KEY"] = "..."        # Use runtime secret management

# ✅ RECOMMENDED: Non-sensitive configuration only
os.environ["SHAREPOINT_TENANT_ID"] = "..."
os.environ["SHAREPOINT_CLIENT_ID"] = "..."
os.environ["SHAREPOINT_SITE_URL"] = "https://..."
os.environ["API_CLIENT_ID"] = "..."
os.environ["API_REDIRECT_URI"] = "http://localhost:8000/callback"

# ✅ NEW: Use runtime secret management for secrets
# Set secrets via environment with proper prefix:
# KAILASH_SECRET_SHAREPOINT_CLIENT_SECRET=...
# KAILASH_SECRET_API_CLIENT_SECRET=...
# KAILASH_SECRET_KAILASH_SECRET_KEY=...
# KAILASH_SECRET_KAILASH_ENCRYPTION_KEY=...

```

## Database Configuration
```python
# ⚠️ DEPRECATED: Connection strings with embedded passwords
# os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost/db"  # Password visible
# os.environ["REDIS_URL"] = "redis://user:pass@localhost:6379"       # Password visible
# os.environ["MONGODB_URI"] = "mongodb://user:pass@localhost/db"     # Password visible

# ✅ RECOMMENDED: Configuration without secrets
os.environ["DB_HOST"] = "localhost"
os.environ["DB_PORT"] = "5432"
os.environ["DB_NAME"] = "kailash"
os.environ["DB_USER"] = "kailash_user"
os.environ["DB_POOL_SIZE"] = "20"
os.environ["DB_MAX_OVERFLOW"] = "10"

os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "6379"
os.environ["REDIS_TTL"] = "3600"

os.environ["MONGODB_HOST"] = "localhost"
os.environ["MONGODB_PORT"] = "27017"
os.environ["MONGODB_DB"] = "kailash"

# ✅ NEW: Database passwords via runtime secret management
# Set secrets via environment with proper prefix:
# KAILASH_SECRET_DB_PASSWORD=...
# KAILASH_SECRET_REDIS_PASSWORD=...
# KAILASH_SECRET_MONGODB_PASSWORD=...

```

## Runtime & Performance
```python
# Kailash runtime
os.environ["KAILASH_MAX_WORKERS"] = "8"
os.environ["KAILASH_TIMEOUT"] = "300"
os.environ["KAILASH_MEMORY_LIMIT"] = "512M"
os.environ["KAILASH_LOG_LEVEL"] = "INFO"

# Feature flags
os.environ["KAILASH_ENABLE_MONITORING"] = "true"
os.environ["KAILASH_ENABLE_TRACING"] = "true"
os.environ["KAILASH_ENABLE_AUDIT"] = "true"

```

## Usage in Code
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.runtime.secret_provider import EnvironmentSecretProvider
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# ✅ RECOMMENDED: Runtime with secret management
secret_provider = EnvironmentSecretProvider()
runtime = LocalRuntime(secret_provider=secret_provider)

# ✅ NEW: Secrets automatically injected at runtime
workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "llm", {}),
    provider="openai",  # API key injected via secret provider
    model="gpt-4"
)

# ⚠️ DEPRECATED: Template string substitution
# workflow.add_node("HTTPRequestNode", "api", {}),
#     url="${API_BASE_URL}/endpoint",
#     headers={"Authorization": "Bearer ${API_TOKEN}"}
# )

# ✅ RECOMMENDED: Non-sensitive configuration from environment
runtime = LocalRuntime(
    secret_provider=secret_provider,
    max_workers=int(os.getenv("KAILASH_MAX_WORKERS", "4")),
    enable_monitoring=os.getenv("KAILASH_ENABLE_MONITORING") == "true"
)

```

## Best Practices
```python
# ✅ Use .env file for local development (non-sensitive config only)
from dotenv import load_dotenv
load_dotenv()

# ✅ Validate required configuration (not secrets)
required_config = ["DB_HOST", "DB_PORT", "REDIS_HOST"]
missing = [var for var in required_config if not os.getenv(var)]
if missing:
    raise ValueError(f"Missing required config vars: {missing}")

# ✅ Validate secrets are available through secret provider
from kailash.runtime.secret_provider import EnvironmentSecretProvider, SecretNotFoundError
secret_provider = EnvironmentSecretProvider()
required_secrets = ["openai-api-key", "db-password"]
for secret in required_secrets:
    try:
        secret_provider.get_secret(secret)
    except SecretNotFoundError:
        raise ValueError(f"Required secret '{secret}' not found")

# ✅ Security best practices
# - Never commit secrets to version control
# - Use KAILASH_SECRET_ prefix for secret environment variables
# - Add .env to .gitignore
# - Use different .env files for different environments

```

## Next Steps
- [Runtime Secret Management](052-runtime-secret-management.md) - **RECOMMENDED** for all secrets
- [Security Config](008-security-configuration.md) - Security setup
- [Production Guide](../../developer/04-production.md) - Deployment
- [Quick Tips](017-quick-tips.md) - Environment tips
