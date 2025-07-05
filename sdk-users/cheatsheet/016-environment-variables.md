# Environment Variables - Configuration Management

## AI/LLM Providers
```python
import os

# OpenAI
os.environ["OPENAI_API_KEY"] = "sk-..."
os.environ["OPENAI_ORG_ID"] = "org-..."

# Anthropic
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-..."

# Ollama (local)
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
os.environ["OLLAMA_TIMEOUT"] = "120"

# Azure OpenAI
os.environ["AZURE_OPENAI_API_KEY"] = "..."
os.environ["AZURE_OPENAI_ENDPOINT"] = "https://..."
os.environ["AZURE_OPENAI_VERSION"] = "2024-02-15-preview"

```

## Authentication & Security
```python
# SharePoint/Microsoft
os.environ["SHAREPOINT_TENANT_ID"] = "..."
os.environ["SHAREPOINT_CLIENT_ID"] = "..."
os.environ["SHAREPOINT_CLIENT_SECRET"] = "..."
os.environ["SHAREPOINT_SITE_URL"] = "https://..."

# OAuth2/Generic API
os.environ["API_CLIENT_ID"] = "..."
os.environ["API_CLIENT_SECRET"] = "..."
os.environ["API_REDIRECT_URI"] = "http://localhost:8000/callback"

# Security
os.environ["KAILASH_SECRET_KEY"] = "..."
os.environ["KAILASH_ENCRYPTION_KEY"] = "..."

```

## Database Configuration
```python
# PostgreSQL
os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost/db"
os.environ["DB_POOL_SIZE"] = "20"
os.environ["DB_MAX_OVERFLOW"] = "10"

# Redis (caching)
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ["REDIS_TTL"] = "3600"

# MongoDB
os.environ["MONGODB_URI"] = "mongodb://localhost:27017/kailash"

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
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Auto-loaded from environment
workflow = Workflow("example", name="Example")
workflow.add_node("llm", LLMAgentNode(),
    provider="openai",  # Uses OPENAI_API_KEY automatically
    model="gpt-4"
)

# Explicit reference
workflow = Workflow("example", name="Example")
workflow.add_node("api", HTTPRequestNode(),
    url="${API_BASE_URL}/endpoint",
    headers={"Authorization": "Bearer ${API_TOKEN}"}
)

# Runtime configuration
runtime = LocalRuntime(
    max_workers=int(os.getenv("KAILASH_MAX_WORKERS", "4")),
    enable_monitoring=os.getenv("KAILASH_ENABLE_MONITORING") == "true"
)

```

## Best Practices
```python
# Use .env file for local development
from dotenv import load_dotenv
load_dotenv()

# Validate required variables
required = ["OPENAI_API_KEY", "DATABASE_URL"]
missing = [var for var in required if not os.getenv(var)]
if missing:
    raise ValueError(f"Missing required env vars: {missing}")

# Never commit secrets
# Add .env to .gitignore

```

## Next Steps
- [Security Config](008-security-configuration.md) - Security setup
- [Production Guide](../../developer/04-production.md) - Deployment
- [Quick Tips](017-quick-tips.md) - Environment tips
