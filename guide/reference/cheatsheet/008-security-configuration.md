# Security Configuration

## Basic Security Setup
```python
from kailash.security import SecurityConfig, set_security_config

# Production security configuration
config = SecurityConfig(
    allowed_directories=["/app/data", "/tmp/kailash"],
    max_file_size=50 * 1024 * 1024,  # 50MB
    execution_timeout=60.0,  # 1 minute
    memory_limit=256 * 1024 * 1024,  # 256MB
    enable_audit_logging=True
)
set_security_config(config)
```

## Safe File Operations
```python
from kailash.security import safe_open, validate_file_path

# Validate file path before use
safe_path = validate_file_path("/app/data/file.txt")

# Safe file opening with automatic validation
with safe_open("data/file.txt", "r") as f:
    content = f.read()
```

## Secure Node Development
```python
from kailash.nodes.mixins import SecurityMixin
from kailash.nodes.base import Node

class MySecureNode(SecurityMixin, Node):
    def run(self, **kwargs):
        # Input is automatically sanitized
        safe_params = self.validate_and_sanitize_inputs(kwargs)
        return self.process_safely(safe_params)
```
