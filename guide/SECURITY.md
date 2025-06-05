# Kailash Python SDK - Security Documentation

## Overview

This document provides comprehensive security information for the Kailash Python SDK, including security features, potential vulnerabilities, best practices, and guidelines for secure deployment.

## Table of Contents

1. [Security Architecture](#security-architecture)
2. [Security Features](#security-features)
3. [Vulnerability Assessment](#vulnerability-assessment)
4. [Best Practices](#best-practices)
5. [Secure Configuration](#secure-configuration)
6. [Security Testing](#security-testing)
7. [Incident Response](#incident-response)
8. [Security Updates](#security-updates)

## Security Architecture

### Security-First Design Principles

The Kailash SDK implements security through defense-in-depth:

1. **Input Validation**: All user inputs are validated and sanitized
2. **Path Restrictions**: File operations are restricted to allowed directories
3. **Code Sandboxing**: Python code execution is sandboxed with limits
4. **Authentication Security**: Secure credential management and API authentication
5. **Audit Logging**: Comprehensive security event logging
6. **Resource Limits**: Memory and execution time limits prevent DoS

### Security Components

```
┌─────────────────────┐
│   Security Module   │  ← Central security controls
├─────────────────────┤
│ - Path Validation   │
│ - Input Sanitization│
│ - Command Validation│
│ - Execution Limits  │
│ - Audit Logging     │
└─────────────────────┘
          │
┌─────────┴─────────┐
│    Node Mixins    │  ← Security for individual nodes
├───────────────────┤
│ - SecurityMixin   │
│ - ValidationMixin │
│ - LoggingMixin    │
└───────────────────┘
          │
┌─────────┴─────────┐
│   Security Tests  │  ← Automated security validation
├───────────────────┤
│ - Path Traversal  │
│ - Code Injection  │
│ - Auth Security   │
│ - Input Validation│
└───────────────────┘
```

## Security Features

### 1. Path Traversal Prevention

**Implementation**: `src/kailash/security.py`

```python
from kailash.security import validate_file_path, safe_open

# Safe file operations
validated_path = validate_file_path("/path/to/file.txt")
with safe_open(validated_path, "r") as f:
    content = f.read()
```

**Features**:
- Blocks `../` path traversal attempts
- Restricts access to system directories (`/etc`, `/var`, `/usr`)
- Enforces directory allowlists
- Validates file extensions
- Comprehensive audit logging

### 2. Code Execution Security

**Implementation**: `src/kailash/nodes/code/python.py`

```python
# Secure Python code execution
executor = CodeExecutor(security_config=config)
result = executor.execute_code(user_code, inputs)
```

**Features**:
- AST-based code safety validation
- Module import restrictions
- Execution timeouts (default: 5 minutes)
- Memory limits (default: 512MB)
- Restricted builtin functions
- Input sanitization

### 3. Input Sanitization

**Implementation**: `src/kailash/security.py`

```python
from kailash.security import sanitize_input, validate_node_parameters

# Sanitize user inputs
clean_input = sanitize_input(user_input)
clean_params = validate_node_parameters(node_params)
```

**Features**:
- Removes dangerous characters (`<>;&|`\`$()`)
- Script tag removal
- Length validation
- Type validation
- Recursive sanitization for nested data

### 4. Authentication Security

**Implementation**: `src/kailash/nodes/api/auth.py`

```python
# Secure authentication
oauth_node = OAuth2Node(
    client_id_env="OAUTH_CLIENT_ID",
    client_secret_env="OAUTH_CLIENT_SECRET"
)
```

**Features**:
- Multiple authentication methods (OAuth2, API Key, Basic Auth)
- Environment variable integration
- Token encryption and secure storage
- Automatic token refresh
- Rate limiting protection

## Vulnerability Assessment

### Critical Vulnerabilities Identified

#### 1. Docker Runtime Command Injection
**Location**: `src/kailash/runtime/docker.py`
**Risk**: HIGH
**Status**: ⚠️ NEEDS ATTENTION

```python
# VULNERABLE CODE
cmd.extend(["--name", container_name])  # User input not validated

# SECURE IMPLEMENTATION
def validate_container_name(name: str) -> str:
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]*$', name):
        raise SecurityError("Invalid container name")
    return name
```

#### 2. Python Code Execution Sandbox Bypass
**Location**: `src/kailash/nodes/code/python.py`
**Risk**: HIGH
**Status**: ✅ PARTIALLY MITIGATED

**Current Protections**:
- AST-based validation
- Module whitelist
- Execution timeouts
- Memory limits

**Remaining Risks**:
- Advanced sandbox escape techniques
- Import system exploitation

#### 3. Template Injection
**Location**: `src/kailash/utils/export.py`
**Risk**: MEDIUM
**Status**: ⚠️ NEEDS ATTENTION

```python
# VULNERABLE CODE
content = template.format(**user_data)

# SECURE IMPLEMENTATION
from string import Template
safe_template = Template(template_string)
content = safe_template.safe_substitute(**sanitized_data)
```

### Authentication Vulnerabilities

#### 1. Credential Exposure in Logs
**Risk**: HIGH
**Mitigation**: Implement credential masking

```python
def mask_credentials(log_message: str) -> str:
    patterns = [
        (r'(password["\']?\s*:\s*["\']?)([^"\']+)', r'\1***'),
        (r'(Authorization:\s*Bearer\s+)([A-Za-z0-9+/=]+)', r'\1***'),
        (r'(api_key["\']?\s*:\s*["\']?)([^"\']+)', r'\1***'),
    ]
    for pattern, replacement in patterns:
        log_message = re.sub(pattern, replacement, log_message, flags=re.IGNORECASE)
    return log_message
```

#### 2. Plain Text Credential Storage
**Risk**: HIGH
**Mitigation**: Implement encrypted storage

```python
class SecureCredentialStore:
    def store_credential(self, key: str, value: str) -> None:
        encrypted_value = self._encrypt(value)
        self._storage.set(key, encrypted_value)

    def get_credential(self, key: str) -> str:
        encrypted_value = self._storage.get(key)
        return self._decrypt(encrypted_value)
```

## Best Practices

### 1. Secure Development Guidelines

#### Input Validation
```python
# ALWAYS validate inputs at node boundaries
def run(self, **kwargs) -> Dict[str, Any]:
    validated_params = self.validate_and_sanitize_inputs(kwargs)
    return self.process_safely(validated_params)
```

#### Credential Management
```python
# Use environment variables, never hardcode credentials
oauth_node = OAuth2Node(
    client_id_env="OAUTH_CLIENT_ID",
    client_secret_env="OAUTH_CLIENT_SECRET",
    scope="read:data"
)
```

#### Error Handling
```python
# Never expose sensitive information in errors
try:
    authenticate(credentials)
except AuthenticationError:
    # Don't reveal why authentication failed
    raise NodeExecutionError("Authentication failed")
```

### 2. Secure Configuration

#### Security Configuration
```python
from kailash.security import SecurityConfig, set_security_config

# Production security configuration
security_config = SecurityConfig(
    allowed_directories=["/app/data", "/tmp/kailash"],
    max_file_size=50 * 1024 * 1024,  # 50MB
    execution_timeout=60.0,  # 1 minute
    memory_limit=256 * 1024 * 1024,  # 256MB
    allowed_file_extensions=['.txt', '.csv', '.json', '.yaml'],
    enable_audit_logging=True,
    enable_path_validation=True,
    enable_command_validation=True
)

set_security_config(security_config)
```

#### Environment Variables
```bash
# Required security environment variables
export OAUTH_CLIENT_ID="your_client_id"
export OAUTH_CLIENT_SECRET="your_client_secret"
export API_KEY="your_api_key"
export KAILASH_LOG_LEVEL="INFO"
export KAILASH_SECURITY_MODE="strict"
```

### 3. Network Security

#### HTTPS Enforcement
```python
# Always use HTTPS for API calls
rest_client = RESTClientNode(
    base_url="https://api.example.com",
    verify_ssl=True,
    timeout=30
)
```

#### Certificate Validation
```python
# Use certificate pinning for critical APIs
rest_client = RESTClientNode(
    base_url="https://api.example.com",
    cert_path="/path/to/client.crt",
    key_path="/path/to/client.key",
    ca_path="/path/to/ca.crt"
)
```

## Security Testing

### Automated Security Tests

The SDK includes comprehensive security tests:

```bash
# Run security test suite
python -m pytest tests/test_security/ -v

# Run specific security categories
python -m pytest tests/test_security/test_security_suite.py::TestPathTraversalPrevention -v
python -m pytest tests/test_security/test_security_suite.py::TestPythonCodeNodeSecurity -v
python -m pytest tests/test_security/test_security_suite.py::TestCommandInjectionPrevention -v
```

### Manual Security Testing

#### Path Traversal Testing
```python
# Test path traversal prevention
try:
    validate_file_path("../../../etc/passwd")
    assert False, "Should have blocked path traversal"
except PathTraversalError:
    pass  # Expected
```

#### Code Injection Testing
```python
# Test code injection prevention
malicious_code = """
import os
os.system('rm -rf /')
"""

try:
    executor.execute_code(malicious_code, {})
    assert False, "Should have blocked malicious code"
except SecurityError:
    pass  # Expected
```

### Security Monitoring

#### Audit Log Monitoring
```python
# Monitor security events
import logging

security_logger = logging.getLogger('kailash.security')
security_logger.addHandler(SecurityAuditHandler())
```

#### Performance Monitoring
```python
# Monitor for security-related performance issues
from kailash.nodes.mixins import PerformanceMixin

class MonitoredNode(SecurityMixin, PerformanceMixin, Node):
    def run(self, **kwargs):
        with self.track_performance(self.secure_process):
            return self.secure_process(kwargs)
```

## Secure Deployment

### Production Deployment Checklist

- [ ] **Environment Variables**: All credentials stored in environment variables
- [ ] **Security Configuration**: Production security config applied
- [ ] **HTTPS**: All API communication over HTTPS
- [ ] **Logging**: Security audit logging enabled
- [ ] **Monitoring**: Security event monitoring in place
- [ ] **Updates**: Latest security patches applied
- [ ] **Testing**: Security tests passing
- [ ] **Documentation**: Security procedures documented

### Docker Security

```dockerfile
# Secure Docker deployment
FROM python:3.12-slim

# Create non-root user
RUN groupadd -r kailash && useradd -r -g kailash kailash

# Set security-focused environment
ENV PYTHONPATH=/app
ENV KAILASH_SECURITY_MODE=strict

# Copy application
COPY --chown=kailash:kailash . /app
WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Switch to non-root user
USER kailash

# Run with security limits
CMD ["python", "-m", "kailash", "--security-mode", "strict"]
```

### Kubernetes Security

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: kailash-app
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 1000
  containers:
  - name: kailash
    image: kailash:latest
    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities:
        drop:
        - ALL
    resources:
      limits:
        memory: "512Mi"
        cpu: "500m"
      requests:
        memory: "256Mi"
        cpu: "250m"
```

## Incident Response

### Security Incident Procedure

1. **Immediate Response**
   - Isolate affected systems
   - Preserve logs and evidence
   - Notify security team

2. **Assessment**
   - Determine scope of impact
   - Identify attack vectors
   - Assess data exposure

3. **Containment**
   - Apply emergency patches
   - Update security configurations
   - Revoke compromised credentials

4. **Recovery**
   - Restore from clean backups
   - Verify system integrity
   - Update security measures

### Security Contact

For security issues, contact:
- **Email**: security@kailash.ai (if applicable)
- **Response Time**: 24 hours for critical issues

## Security Updates

### Version Security Status

| Version | Security Status | Notes |
|---------|----------------|-------|
| 0.1.4   | ⚠️ Has known vulnerabilities | Docker runtime, template injection |
| 0.1.5   | 🚧 In development | Security hardening in progress |

### Known Vulnerabilities

| CVE ID | Severity | Component | Status | Fix Version |
|--------|----------|-----------|--------|-------------|
| PENDING | HIGH | Docker Runtime | Open | 0.1.5 |
| PENDING | MEDIUM | Template System | Open | 0.1.5 |
| PENDING | HIGH | Auth Credential Exposure | Open | 0.1.5 |

### Security Roadmap

#### Version 0.1.5 (In Progress)
- [ ] Docker command injection fixes
- [ ] Enhanced code sandboxing
- [ ] Credential masking implementation
- [ ] Template injection prevention

#### Version 0.2.0 (Planned)
- [ ] Hardware security module (HSM) support
- [ ] Advanced container isolation
- [ ] Automated vulnerability scanning
- [ ] Security policy enforcement

---

**Last Updated**: 2025-06-05
**Next Review**: 2025-07-05
**Document Version**: 1.0
