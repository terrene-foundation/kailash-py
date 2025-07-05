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
results, run_id = runtime.execute(workflow)

```

## Security Nodes
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

# Authentication
workflow = Workflow("example", name="Example")
workflow.add_node("auth", MultiFactorAuthNode(),
    auth_methods=["password", "totp"],
    session_timeout=3600
)

# OAuth2 Integration
workflow = Workflow("example", name="Example")
workflow.add_node("oauth", OAuth2Node(),
    provider="azure",
    client_id="${AZURE_CLIENT_ID}",
    client_secret="${AZURE_CLIENT_SECRET}",
    scope="read write"
)

# Threat Detection
workflow = Workflow("example", name="Example")
workflow.add_node("security", ThreatDetectionNode(),
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
workflow.add_node("reader", CSVReaderNode(),
    file_path=safe_path,
    validate_path=True  # Auto-validate
)

```

## Environment Security
```python
# Never hardcode secrets
workflow.add_node("api", HTTPRequestNode(),
    url="https://api.example.com",
    headers={"Authorization": f"Bearer ${API_TOKEN}"}
)

# Use credential management
from kailash.security import CredentialManager
creds = CredentialManager()
api_key = creds.get_secret("api_key")

```

## Common Security Patterns
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

# Input sanitization in PythonCodeNode
workflow = Workflow("example", name="Example")
workflow.add_node("sanitize", PythonCodeNode(
    name="sanitize",
    code='''
import re
# Remove dangerous characters
safe_input = re.sub(r'[<>&"\'`;]', '', user_input)
result = {'sanitized': safe_input}
''',
    input_types={"user_input": str}
))

# Rate limiting
workflow = Workflow("example", name="Example")
workflow.add_node("limiter", RateLimiterNode(),
    max_requests=100,
    window_seconds=60,
    key_field="user_id"
)

```

## Next Steps
- [Access Control](014-access-control-multi-tenancy.md) - RBAC/ABAC
- [Production Guide](../../developer/04-production.md) - Security best practices
- [Environment Variables](016-environment-variables.md) - Secret management
