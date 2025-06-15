# SharePoint Multi-Authentication Guide

*Added in Session 067 for enterprise SharePoint integrations*

## Overview

The `SharePointGraphReaderEnhanced` extends the standard SharePoint reader with multiple authentication methods, making it suitable for various enterprise scenarios.

## Authentication Methods

### 1. Certificate-Based Authentication (Most Secure)

Best for production environments:

```python
from kailash.nodes.data import SharePointGraphReaderEnhanced

node = SharePointGraphReaderEnhanced()
result = await node.execute(
    auth_method="certificate",
    tenant_id="your-tenant-id",
    client_id="your-app-client-id",
    certificate_path="/secure/certs/sharepoint.pem",
    site_url="https://company.sharepoint.com/sites/project",
    operation="list_files",
    library_name="Documents"
)
```

With encrypted certificate:

```python
result = await node.execute(
    auth_method="certificate",
    tenant_id="your-tenant-id",
    client_id="your-app-client-id",
    certificate_path="/secure/certs/sharepoint.pfx",
    certificate_password="cert-password",
    site_url="https://company.sharepoint.com/sites/project",
    operation="download_file",
    file_name="report.pdf"
)
```

### 2. Managed Identity (Azure-Hosted Apps)

No credentials needed when running in Azure:

```python
# System-assigned managed identity
node = SharePointGraphReaderEnhanced()
result = await node.execute(
    auth_method="managed_identity",
    use_system_identity=True,
    site_url="https://company.sharepoint.com/sites/project",
    operation="list_files"
)

# User-assigned managed identity
result = await node.execute(
    auth_method="managed_identity",
    use_system_identity=False,
    managed_identity_client_id="identity-client-id",
    site_url="https://company.sharepoint.com/sites/project",
    operation="list_files"
)
```

### 3. Username/Password (Legacy Support)

For older systems or interactive scenarios:

```python
node = SharePointGraphReaderEnhanced()
result = await node.execute(
    auth_method="username_password",
    tenant_id="your-tenant-id",
    client_id="your-app-client-id",
    username="user@company.com",
    password="user-password",
    site_url="https://company.sharepoint.com/sites/project",
    operation="search_files",
    search_query="quarterly report"
)
```

### 4. Device Code Flow (CLI Tools)

Perfect for command-line applications:

```python
def display_device_code(flow_info):
    print(f"Please visit: {flow_info['verification_uri']}")
    print(f"Enter code: {flow_info['user_code']}")

node = SharePointGraphReaderEnhanced()
result = await node.execute(
    auth_method="device_code",
    tenant_id="your-tenant-id",
    client_id="your-app-client-id",
    device_code_callback=display_device_code.__name__,
    site_url="https://company.sharepoint.com/sites/project",
    operation="list_libraries"
)
```

### 5. Client Credentials (Backward Compatible)

Original authentication method still supported:

```python
# Works with both SharePointGraphReader and Enhanced version
result = await node.execute(
    auth_method="client_credentials",  # Or omit for default
    tenant_id="your-tenant-id",
    client_id="your-app-client-id",
    client_secret="your-client-secret",
    site_url="https://company.sharepoint.com/sites/project",
    operation="list_files"
)
```

## Complete Workflow Example

```python
from kailash.workflow import Workflow
from kailash.nodes.data import SharePointGraphReaderEnhanced
from kailash.nodes.security import CredentialManagerNode

workflow = Workflow(workflow_id="sharepoint_sync", name="SharePoint Sync")

# Get credentials securely
workflow.add_node(
    "get_sp_cert",
    CredentialManagerNode,
    credential_name="sharepoint_cert",
    credential_type="certificate",
    credential_sources=["vault", "file"]
)

# Read from SharePoint with certificate auth
workflow.add_node(
    "read_sharepoint",
    SharePointGraphReaderEnhanced,
    auth_method="certificate",
    site_url="https://company.sharepoint.com/sites/hr",
    operation="download_file",
    library_name="Policies",
    file_name="employee_handbook.pdf",
    local_path="/tmp/handbook.pdf"
)

# Connect credential manager to SharePoint
workflow.connect("get_sp_cert", "read_sharepoint", {
    "credentials.cert_path": "certificate_path",
    "credentials.tenant_id": "tenant_id",
    "credentials.client_id": "client_id"
})

result = await workflow.execute()
```

## Multi-Tenant Scenarios

```python
from kailash.workflow import Workflow

workflow = Workflow(workflow_id="multi_tenant", name="Multi-Tenant SharePoint")

tenants = [
    {
        "name": "tenant1",
        "auth_method": "certificate",
        "tenant_id": "tenant1-id",
        "client_id": "app1-id",
        "certificate_thumbprint": "ABCD1234"
    },
    {
        "name": "tenant2",
        "auth_method": "managed_identity",
        "site_url": "https://tenant2.sharepoint.com/sites/data"
    },
    {
        "name": "tenant3",
        "auth_method": "client_credentials",
        "tenant_id": "tenant3-id",
        "client_id": "app3-id",
        "client_secret": "${TENANT3_SECRET}"
    }
]

# Add node for each tenant
for tenant in tenants:
    workflow.add_node(
        f"sp_{tenant['name']}",
        SharePointGraphReaderEnhanced,
        **tenant,
        operation="list_files",
        library_name="Shared Documents"
    )
```

## Authentication Selection Guide

| Scenario | Recommended Auth | Why |
|----------|-----------------|-----|
| Production service | Certificate | Most secure, no passwords |
| Azure-hosted app | Managed Identity | No credentials to manage |
| Desktop app | Device Code | User-friendly, secure |
| Legacy integration | Username/Password | Compatibility |
| Development/Testing | Client Credentials | Simple setup |

## Security Best Practices

### 1. Certificate Management

```python
# Store certificate securely
workflow.add_node(
    "get_cert",
    CredentialManagerNode,
    credential_name="sharepoint_prod_cert",
    credential_type="certificate",
    credential_sources=["azure_keyvault"]
)

# Use certificate for auth
workflow.add_node(
    "sharepoint",
    SharePointGraphReaderEnhanced,
    auth_method="certificate"
)

workflow.connect("get_cert", "sharepoint", {
    "credentials.cert_path": "certificate_path",
    "credentials.passphrase": "certificate_password"
})
```

### 2. Credential Isolation

```python
# Different credentials for different environments
if environment == "production":
    auth_config = {
        "auth_method": "certificate",
        "certificate_thumbprint": os.environ["PROD_CERT_THUMB"]
    }
elif environment == "staging":
    auth_config = {
        "auth_method": "managed_identity",
        "use_system_identity": True
    }
else:
    auth_config = {
        "auth_method": "device_code",
        "client_id": "dev-app-id"
    }

node = SharePointGraphReaderEnhanced()
result = await node.execute(**auth_config, site_url=site_url, operation=operation)
```

### 3. Fallback Authentication

```python
from kailash.workflow import Workflow

workflow = Workflow(workflow_id="sp_resilient", name="Resilient SharePoint")

# Primary: Managed Identity
workflow.add_node(
    "sp_managed",
    SharePointGraphReaderEnhanced,
    auth_method="managed_identity",
    site_url=site_url,
    operation="list_files"
)

# Fallback: Certificate
workflow.add_node(
    "sp_cert",
    SharePointGraphReaderEnhanced,
    auth_method="certificate",
    certificate_path="/backup/cert.pem",
    tenant_id=tenant_id,
    client_id=client_id,
    site_url=site_url,
    operation="list_files"
)

# Configure fallback
workflow.add_fallback("sp_managed", "sp_cert")
```

## Troubleshooting

### Certificate Issues

```python
# Debug certificate loading
try:
    result = await node.execute(
        auth_method="certificate",
        certificate_path="/path/to/cert.pem",
        # ... other params
    )
except Exception as e:
    if "certificate" in str(e).lower():
        # Try PKCS12 format
        result = await node.execute(
            auth_method="certificate",
            certificate_path="/path/to/cert.pfx",
            certificate_password="password",
            # ... other params
        )
```

### Managed Identity Issues

```python
# Check if running in Azure
import os

if "MSI_ENDPOINT" in os.environ or "IDENTITY_ENDPOINT" in os.environ:
    # Use managed identity
    auth_method = "managed_identity"
else:
    # Fall back to certificate or device code
    auth_method = "certificate"
```

### Permission Issues

Different auth methods may have different permissions:

```python
# Check operation permissions by auth method
operations_by_auth = {
    "managed_identity": ["list_files", "download_file"],
    "certificate": ["list_files", "download_file", "upload_file", "delete_file"],
    "username_password": ["list_files", "download_file"],
    "device_code": ["list_files", "download_file", "search_files"]
}
```

## Migration from Standard Reader

```python
# Old code with SharePointGraphReader
from kailash.nodes.data import SharePointGraphReader
node = SharePointGraphReader()
result = await node.execute(
    tenant_id="...",
    client_id="...",
    client_secret="...",
    site_url="...",
    operation="list_files"
)

# New code with Enhanced (backward compatible)
from kailash.nodes.data import SharePointGraphReaderEnhanced
node = SharePointGraphReaderEnhanced()
result = await node.execute(
    # Same parameters work!
    tenant_id="...",
    client_id="...",
    client_secret="...",
    site_url="...",
    operation="list_files"
)

# Or use new auth methods
result = await node.execute(
    auth_method="certificate",  # New!
    certificate_path="/secure/cert.pem",
    tenant_id="...",
    client_id="...",
    site_url="...",
    operation="list_files"
)
```

## Related Documentation

- [10-credential-management.md](10-credential-management.md) - Secure credential handling
- [09-workflow-resilience.md](09-workflow-resilience.md) - Resilient workflows
- [Examples](../../examples/feature_examples/integrations/) - Working examples
