# Credential Management Guide

*Added in Session 067 for enterprise-grade security*

## Overview

The `CredentialManagerNode` provides centralized credential management with support for multiple sources, validation, and automatic masking. Never hardcode credentials or expose them in logs.

## Key Features

- **Multi-source support**: Environment variables, files, vaults
- **Built-in validation**: Ensures credentials meet security requirements
- **Automatic masking**: Credentials never exposed in logs
- **Caching**: Reduce vault API calls with configurable TTL
- **Type-aware**: Different handling for API keys, OAuth2, databases, etc.

## Basic Usage

```python
from kailash.nodes.security import CredentialManagerNode
from kailash.workflow import Workflow

workflow = Workflow(workflow_id="secure_pipeline", name="Secure Pipeline")

# Add credential manager
workflow.add_node(
    "get_api_key",
    CredentialManagerNode,
    credential_name="openai",
    credential_type="api_key",
    validate_on_fetch=True
)

# Use credentials in another node
workflow.add_node(
    "llm_call",
    LLMAgentNode,
    prompt="Analyze this data"
)

# Connect - credentials are passed securely
workflow.connect("get_api_key", "llm_call", {"credentials.api_key": "api_key"})
```

## Credential Sources

### 1. Environment Variables (Default)

```python
# Set environment variables
export OPENAI_API_KEY=sk-...
export DB_HOST=localhost
export DB_USER=admin
export DB_PASSWORD=secret

# Node will automatically find them
node = CredentialManagerNode(
    credential_name="openai",
    credential_type="api_key"
)
```

### 2. JSON Files

```python
# Create .credentials/api_service.json
{
    "api_key": "your-api-key",
    "endpoint": "https://api.example.com"
}

# Configure node to use files
node = CredentialManagerNode(
    credential_name="api_service",
    credential_type="api_key",
    credential_sources=["file", "env"]  # Try file first
)
```

### 3. Vault Integration

```python
# AWS Secrets Manager
node = CredentialManagerNode(
    credential_name="production_db",
    credential_type="database",
    credential_sources=["aws_secrets", "env"]
)

# Azure Key Vault
node = CredentialManagerNode(
    credential_name="api_keys",
    credential_type="api_key",
    credential_sources=["azure_keyvault"]
)

# HashiCorp Vault
node = CredentialManagerNode(
    credential_name="app_secrets",
    credential_type="custom",
    credential_sources=["vault"]
)
```

## Credential Types

### API Key
```python
node = CredentialManagerNode(
    credential_name="service_api",
    credential_type="api_key",
    validate_on_fetch=True  # Validates format
)
# Output: {"api_key": "sk-..."}
```

### OAuth2
```python
node = CredentialManagerNode(
    credential_name="oauth_service",
    credential_type="oauth2"
)
# Output: {"client_id": "...", "client_secret": "...", "token_url": "..."}
```

### Database
```python
node = CredentialManagerNode(
    credential_name="postgres",
    credential_type="database"
)
# Output: {"host": "...", "port": "...", "username": "...", "password": "...", "database": "..."}
```

### Certificate
```python
node = CredentialManagerNode(
    credential_name="client_cert",
    credential_type="certificate"
)
# Output: {"cert_path": "...", "key_path": "...", "passphrase": "..."}
```

### Basic Auth
```python
node = CredentialManagerNode(
    credential_name="http_auth",
    credential_type="basic_auth"
)
# Output: {"username": "...", "password": "..."}
```

## Advanced Features

### Caching

Reduce API calls to vaults:

```python
node = CredentialManagerNode(
    credential_name="expensive_secret",
    credential_type="api_key",
    credential_sources=["vault"],
    cache_duration_seconds=3600  # Cache for 1 hour
)
```

### Validation

Built-in validation for credential formats:

```python
# This will validate the API key format
node = CredentialManagerNode(
    credential_name="openai",
    credential_type="api_key",
    validate_on_fetch=True  # Ensures proper format
)
```

### Masking

Credentials are automatically masked in logs:

```python
result = node.execute()
print(result['masked_display'])
# Output: {"api_key": "sk-pr******************3456"}
```

## Complete Workflow Example

```python
from kailash.workflow import Workflow
from kailash.nodes.security import CredentialManagerNode
from kailash.nodes.data import SQLDatabaseNode
from kailash.nodes.api import HTTPRequestNode

workflow = Workflow(workflow_id="secure_etl", name="Secure ETL Pipeline")

# Get database credentials
workflow.add_node(
    "db_creds",
    CredentialManagerNode,
    credential_name="production_db",
    credential_type="database",
    credential_sources=["vault", "env"],
    cache_duration_seconds=1800
)

# Get API credentials
workflow.add_node(
    "api_creds",
    CredentialManagerNode,
    credential_name="external_api",
    credential_type="oauth2",
    credential_sources=["aws_secrets", "file"]
)

# Database query
workflow.add_node(
    "fetch_data",
    SQLDatabaseNode,
    query="SELECT * FROM customers WHERE active = true"
)

# API call
workflow.add_node(
    "enrich_data",
    HTTPRequestNode,
    url="https://api.external.com/enrich",
    method="POST"
)

# Connect with credential mapping
workflow.connect("db_creds", "fetch_data", {
    "credentials.host": "host",
    "credentials.port": "port",
    "credentials.username": "username",
    "credentials.password": "password",
    "credentials.database": "database"
})

workflow.connect("api_creds", "enrich_data", {
    "credentials.client_id": "oauth_client_id",
    "credentials.client_secret": "oauth_client_secret"
})

workflow.connect("fetch_data", "enrich_data", {"result": "data"})

# Execute
result = await workflow.execute()
```

## Security Best Practices

1. **Never hardcode credentials** - Always use CredentialManagerNode
2. **Use appropriate sources** - Vaults for production, env for development
3. **Enable validation** - Catch invalid credentials early
4. **Set cache appropriately** - Balance security vs performance
5. **Use least privilege** - Request only needed credential types
6. **Rotate regularly** - Update credentials periodically
7. **Monitor access** - Check logs for credential usage

## Environment Variable Patterns

The node searches for credentials using these patterns:

```bash
# API Keys
SERVICENAME_API_KEY
SERVICENAME_KEY
SERVICENAME_TOKEN

# OAuth2
SERVICENAME_CLIENT_ID
SERVICENAME_CLIENT_SECRET
SERVICENAME_TOKEN_URL

# Database
SERVICENAME_DB_HOST or SERVICENAME_HOST
SERVICENAME_DB_PORT or SERVICENAME_PORT
SERVICENAME_DB_USER or SERVICENAME_USER
SERVICENAME_DB_PASSWORD or SERVICENAME_PASSWORD
SERVICENAME_DB_NAME or SERVICENAME_DATABASE

# Basic Auth
SERVICENAME_USERNAME or SERVICENAME_USER
SERVICENAME_PASSWORD or SERVICENAME_PASS
```

## File Storage Patterns

Recommended directory structure:

```
project/
├── .credentials/          # Git-ignored credential files
│   ├── api_service.json
│   ├── oauth_app.json
│   └── database.json
├── .env.json             # All credentials in one file
└── config/
    └── credentials/      # Alternative location
        └── production.json
```

## Troubleshooting

### Credential Not Found
```python
# Check multiple sources
node = CredentialManagerNode(
    credential_name="service",
    credential_sources=["vault", "aws_secrets", "env", "file"]
)
```

### Validation Failures
```python
# Disable validation for custom formats
node = CredentialManagerNode(
    credential_name="legacy_system",
    validate_on_fetch=False
)
```

### Cache Issues
```python
# Disable caching for testing
node = CredentialManagerNode(
    credential_name="test_creds",
    cache_duration_seconds=None  # No caching
)
```

## Related Documentation

- [09-workflow-resilience.md](09-workflow-resilience.md) - Resilient workflows
- [07-troubleshooting.md](07-troubleshooting.md) - Error handling
- [Examples](../../examples/feature_examples/security/) - Working examples
