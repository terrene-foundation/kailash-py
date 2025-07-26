# Security Patterns

Patterns for building secure workflows with authentication, authorization, data protection, and compliance.

## 1. Secure File Processing Pattern

**Purpose**: Safely process files with path validation, size limits, and sanitization

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.security import SecurityConfig, set_security_config
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime
import os

# Configure global security policy
security_config = SecurityConfig(
    allowed_directories=[
        "/app/data/input",
        "/app/data/output",
        "/tmp/kailash"
    ],
    blocked_paths=[
        "/etc",
        "/root",
        "/home",
        "*.key",
        "*.pem"
    ],
    max_file_size=100 * 1024 * 1024,  # 100MB
    allowed_extensions=[".csv", ".json", ".txt", ".xml"],
    execution_timeout=300.0,  # 5 minutes
    enable_audit_logging=True,
    audit_log_path="/var/log/kailash/security.log"
)

set_security_config(security_config)

# Create secure workflow
workflow = WorkflowBuilder()

# Secure file reader with validation
workflow.add_node("PythonCodeNode", "validator", {}),
    code="""
import os
import hashlib
from pathlib import Path

# Validate file path
file_path = Path(input_path)
if not file_path.is_absolute():
    file_path = file_path.resolve()

# Check if file exists and is readable
if not file_path.exists():
    raise FileNotFoundError(f"File not found: {file_path}")

if not os.access(file_path, os.R_OK):
    raise PermissionError(f"Cannot read file: {file_path}")

# Calculate file hash for integrity
hasher = hashlib.sha256()
with open(file_path, 'rb') as f:
    for chunk in iter(lambda: f.read(4096), b""):
        hasher.update(chunk)

file_hash = hasher.hexdigest()
file_size = file_path.stat().st_size

# Log file access
audit_log = {
    'action': 'file_read',
    'file': str(file_path),
    'size': file_size,
    'hash': file_hash,
    'timestamp': datetime.now().isoformat(),
    'user': os.getenv('USER', 'unknown')
}

print(f"Security audit: {json.dumps(audit_log)}")

result = {
    'validated_path': str(file_path),
    'file_hash': file_hash,
    'file_size': file_size
}
""",
    imports=["os", "hashlib", "from pathlib import Path", "from datetime import datetime", "json"]
)

# Secure CSV reader - automatically validates paths
workflow.add_node("CSVReaderNode", "reader", {}))

# Data processor with sanitization
workflow.add_node("PythonCodeNode", "processor", {}),
    code="""
import re
import html

def sanitize_string(value):
    '''Remove potentially dangerous content'''
    if not isinstance(value, str):
        return value

    # Remove script tags and javascript
    value = re.sub(r'<script[^>]*>.*?</script>', '', value, flags=re.IGNORECASE)
    value = re.sub(r'javascript:', '', value, flags=re.IGNORECASE)

    # HTML escape
    value = html.escape(value)

    # Remove SQL injection attempts
    sql_keywords = ['DROP', 'DELETE', 'INSERT', 'UPDATE', 'EXEC', 'UNION']
    for keyword in sql_keywords:
        value = re.sub(rf'\\b{keyword}\\b', '', value, flags=re.IGNORECASE)

    return value.strip()

# Sanitize all string fields
sanitized_data = []
for record in data:
    sanitized_record = {}
    for key, value in record.items():
        if isinstance(value, str):
            sanitized_record[key] = sanitize_string(value)
        else:
            sanitized_record[key] = value
    sanitized_data.append(sanitized_record)

result = sanitized_data
""",
    imports=["re", "html"]
)

# Secure writer with path validation
workflow.add_node("CSVWriterNode", "writer", {}))

# Connect workflow
workflow.add_connection("validator", "reader", "result.validated_path", "file_path")
workflow.add_connection("reader", "processor", "data", "data")
workflow.add_connection("processor", "writer", "result", "data")

# Execute with sandboxing
runtime = LocalRuntime(security_config=security_config)
results, run_id = runtime.execute(workflow, parameters={
    "validator": {"input_path": "/app/data/input/customers.csv"},
    "writer": {"file_path": "/app/data/output/sanitized_customers.csv"}
})

```

## 2. Secure Code Execution Pattern

**Purpose**: Execute user-provided code with sandboxing and resource limits

```python
from kailash.security import CodeSandbox, ResourceLimits
from kailash.nodes.code import SecurePythonCodeNode

# Create sandboxed code execution node
class SandboxedCodeNode(SecurePythonCodeNode):
    """Execute untrusted code safely"""

    def __init__(self, **config):
        super().__init__(**config)

        # Configure sandbox
        self.sandbox = CodeSandbox(
            allowed_imports=[
                'math', 'statistics', 'json', 'csv',
                'datetime', 'collections', 'itertools'
            ],
            blocked_builtins=[
                'eval', 'exec', 'compile', '__import__',
                'open', 'input', 'help', 'globals', 'locals'
            ],
            resource_limits=ResourceLimits(
                cpu_time=30.0,  # seconds
                memory=256 * 1024 * 1024,  # 256MB
                output_size=10 * 1024 * 1024,  # 10MB
                max_processes=1,
                max_files=0  # No file access
            )
        )

    def run(self, **kwargs):
        code = kwargs.get('code', self.config.get('code', ''))

        # Validate code before execution
        validation = self.sandbox.validate_code(code)
        if not validation.is_safe:
            raise SecurityError(f"Code validation failed: {validation.errors}")

        # Execute in sandbox
        try:
            result = self.sandbox.execute(
                code,
                context=kwargs,
                timeout=self.config.get('timeout', 30)
            )

            # Log execution
            self.log_security_event({
                'action': 'code_execution',
                'status': 'success',
                'resource_usage': result.resource_usage
            })

            return result.output

        except Exception as e:
            self.log_security_event({
                'action': 'code_execution',
                'status': 'failed',
                'error': str(e)
            })
            raise

# Use sandboxed execution
workflow = WorkflowBuilder()

workflow.add_node("SandboxedCodeNode", "sandbox", {}),
    timeout=10,
    allowed_variables=['data', 'config'],
    max_iterations=1000
)

# User-provided code (potentially untrusted)
user_code = """
# Calculate statistics
import statistics

values = [item['value'] for item in data]
result = {
    'mean': statistics.mean(values),
    'median': statistics.median(values),
    'stdev': statistics.stdev(values) if len(values) > 1 else 0,
    'count': len(values)
}
"""

# Execute safely
results, run_id = runtime.execute(workflow, parameters={
    "sandbox": {
        "code": user_code,
        "data": [{"value": i} for i in range(100)]
    }
})

```

## 3. Authentication and Authorization Pattern

**Purpose**: Implement secure authentication and fine-grained authorization

```python
from kailash.security import AuthManager, Permission, Role
from kailash.nodes.base import SecureNode
import jwt
from datetime import datetime, timedelta

class AuthenticationNode(SecureNode):
    """Handle user authentication"""

    def __init__(self, **config):
        super().__init__(**config)
        self.auth_manager = AuthManager(
            jwt_secret=os.getenv('JWT_SECRET'),
            token_expiry=timedelta(hours=1)
        )

    def run(self, **kwargs):
        auth_method = kwargs.get('auth_method', 'jwt')

        if auth_method == 'jwt':
            return self._authenticate_jwt(kwargs)
        elif auth_method == 'api_key':
            return self._authenticate_api_key(kwargs)
        elif auth_method == 'oauth':
            return self._authenticate_oauth(kwargs)
        else:
            raise ValueError(f"Unsupported auth method: {auth_method}")

    def _authenticate_jwt(self, kwargs):
        token = kwargs.get('token')
        if not token:
            raise AuthenticationError("No token provided")

        try:
            # Verify and decode token
            payload = jwt.decode(
                token,
                self.auth_manager.jwt_secret,
                algorithms=['HS256']
            )

            # Check expiration
            if datetime.fromtimestamp(payload['exp']) < datetime.now():
                raise AuthenticationError("Token expired")

            # Get user permissions
            user_id = payload['user_id']
            permissions = self.auth_manager.get_user_permissions(user_id)

            return {
                'authenticated': True,
                'user_id': user_id,
                'permissions': permissions,
                'token_valid_until': payload['exp']
            }

        except jwt.InvalidTokenError as e:
            raise AuthenticationError(f"Invalid token: {e}")

class AuthorizationNode(SecureNode):
    """Check user permissions for operations"""

    def run(self, **kwargs):
        user_permissions = kwargs.get('permissions', [])
        required_permission = kwargs.get('required_permission')
        resource = kwargs.get('resource')

        # Check permission
        has_permission = self._check_permission(
            user_permissions,
            required_permission,
            resource
        )

        if not has_permission:
            self.log_security_event({
                'action': 'authorization_denied',
                'user': kwargs.get('user_id'),
                'permission': required_permission,
                'resource': resource
            })
            raise AuthorizationError(
                f"Permission denied: {required_permission} on {resource}"
            )

        return {
            'authorized': True,
            'permission': required_permission,
            'resource': resource
        }

    def _check_permission(self, user_permissions, required, resource):
        # Check exact permission
        if required in user_permissions:
            return True

        # Check wildcard permissions
        resource_type = resource.split(':')[0]
        if f"{resource_type}:*" in user_permissions:
            return True

        # Check admin permission
        if "admin:*" in user_permissions:
            return True

        return False

# Create secure workflow with auth
secure_workflow = WorkflowBuilder()

# Add auth nodes
secure_workflow.add_node("AuthenticationNode", "authenticate", {}))
secure_workflow.add_node("AuthorizationNode", "authorize", {}))

# Protected operation
secure_workflow.add_node("PythonCodeNode", "protected_operation", {}),
    code="""
# This operation requires authentication and authorization
result = {
    'data': sensitive_data,
    'accessed_by': user_id,
    'accessed_at': datetime.now().isoformat()
}
"""
)

# Connect with auth flow
secure_workflow.add_connection("authenticate", "authorize", "result", "auth_context")
secure_workflow.add_connection("authorize", "protected_operation", "auth_context.user_id", "user_id")

```

## 4. Data Encryption Pattern

**Purpose**: Encrypt sensitive data at rest and in transit

```python
from kailash.security import EncryptionManager, EncryptedField
from cryptography.fernet import Fernet
import base64

class EncryptionNode(SecureNode):
    """Encrypt/decrypt sensitive data"""

    def __init__(self, **config):
        super().__init__(**config)

        # Initialize encryption
        self.encryption_manager = EncryptionManager(
            master_key=os.getenv('MASTER_ENCRYPTION_KEY'),
            key_rotation_days=90
        )

    def run(self, **kwargs):
        operation = kwargs.get('operation', 'encrypt')
        data = kwargs.get('data')
        fields_to_encrypt = kwargs.get('encrypt_fields', [])

        if operation == 'encrypt':
            return self._encrypt_data(data, fields_to_encrypt)
        elif operation == 'decrypt':
            return self._decrypt_data(data, fields_to_encrypt)
        else:
            raise ValueError(f"Unknown operation: {operation}")

    def _encrypt_data(self, data, fields):
        encrypted_data = []

        for record in data:
            encrypted_record = record.copy()

            for field in fields:
                if field in record:
                    # Encrypt field value
                    value = str(record[field])
                    encrypted_value = self.encryption_manager.encrypt(value)
                    encrypted_record[field] = encrypted_value

                    # Add encryption metadata
                    encrypted_record[f"{field}_encrypted"] = True
                    encrypted_record[f"{field}_algorithm"] = "AES-256"

            encrypted_data.append(encrypted_record)

        return {'data': encrypted_data, 'encrypted_fields': fields}

    def _decrypt_data(self, data, fields):
        decrypted_data = []

        for record in data:
            decrypted_record = record.copy()

            for field in fields:
                if f"{field}_encrypted" in record and record[f"{field}_encrypted"]:
                    # Decrypt field value
                    encrypted_value = record[field]
                    decrypted_value = self.encryption_manager.decrypt(encrypted_value)
                    decrypted_record[field] = decrypted_value

                    # Remove encryption metadata
                    del decrypted_record[f"{field}_encrypted"]
                    del decrypted_record[f"{field}_algorithm"]

            decrypted_data.append(decrypted_record)

        return {'data': decrypted_data}

# Workflow with encryption
encryption_workflow = WorkflowBuilder()

# Read sensitive data
encryption_workflow.add_node("CSVReaderNode", "reader", {}),
    file_path="/secure/customer_data.csv"
)

# Encrypt PII fields
encryption_workflow.add_node("EncryptionNode", "encrypt", {}),
    encrypt_fields=["ssn", "credit_card", "email", "phone"]
)

# Process encrypted data
encryption_workflow.add_node("PythonCodeNode", "processor", {}),
    code="""
# Safe to process - PII is encrypted
processed = []
for record in data:
    # Can work with encrypted data
    processed.append({
        'customer_id': record['customer_id'],
        'encrypted_ssn': record['ssn'],  # Still encrypted
        'risk_score': calculate_risk(record)
    })
result = processed
"""
)

# Decrypt for authorized output
encryption_workflow.add_node("EncryptionNode", "decrypt", {}),
    operation="decrypt"
)

# Connect workflow
encryption_workflow.add_connection("reader", "encrypt", "data", "data")
encryption_workflow.add_connection("encrypt", "processor", "result.data", "data")
encryption_workflow.add_connection("processor", "decrypt", "result", "data")

```

## 5. Audit Logging Pattern

**Purpose**: Comprehensive security audit trail for compliance

```python
from kailash.security import AuditLogger, AuditEvent
import json

class AuditedWorkflowRunner:
    """Run workflows with complete audit trails"""

    def __init__(self, audit_config):
        self.audit_logger = AuditLogger(
            log_path=audit_config['log_path'],
            rotation_size=audit_config.get('rotation_size', 100 * 1024 * 1024),
            retention_days=audit_config.get('retention_days', 90),
            encryption_enabled=audit_config.get('encrypt_logs', True)
        )

    def execute_with_audit(self, workflow, parameters, context):
        # Log workflow start
        start_event = AuditEvent(
            event_type="workflow_start",
            workflow_id=workflow.id,
            user_id=context.get('user_id'),
            timestamp=datetime.now(),
            details={
                'workflow_name': workflow.name,
                'parameters': self._sanitize_parameters(parameters),
                'source_ip': context.get('source_ip'),
                'session_id': context.get('session_id')
            }
        )
        self.audit_logger.log(start_event)

        try:
            # Execute workflow with monitoring
            runtime = LocalRuntime()

            # Add audit hooks to each node
            for node_id, node in workflow.nodes.items():
                self._add_audit_hooks(node, node_id)

            # Execute
            results, run_id = runtime.execute(workflow, parameters=parameters)

            # Log success
            success_event = AuditEvent(
                event_type="workflow_complete",
                workflow_id=workflow.id,
                run_id=run_id,
                user_id=context.get('user_id'),
                timestamp=datetime.now(),
                details={
                    'status': 'success',
                    'duration': results.get('execution_time'),
                    'nodes_executed': len(results)
                }
            )
            self.audit_logger.log(success_event)

            return results, run_id

        except Exception as e:
            # Log failure
            failure_event = AuditEvent(
                event_type="workflow_error",
                workflow_id=workflow.id,
                user_id=context.get('user_id'),
                timestamp=datetime.now(),
                details={
                    'status': 'failed',
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'stack_trace': traceback.format_exc()
                }
            )
            self.audit_logger.log(failure_event)
            raise

    def _add_audit_hooks(self, node, node_id):
        """Add audit logging to node execution"""
        original_run = node.run

        def audited_run(**kwargs):
            # Log node start
            self.audit_logger.log(AuditEvent(
                event_type="node_start",
                node_id=node_id,
                node_type=type(node).__name__,
                timestamp=datetime.now()
            ))

            try:
                # Execute original
                result = original_run(**kwargs)

                # Log node success
                self.audit_logger.log(AuditEvent(
                    event_type="node_complete",
                    node_id=node_id,
                    timestamp=datetime.now(),
                    details={'output_size': len(str(result))}
                ))

                return result

            except Exception as e:
                # Log node failure
                self.audit_logger.log(AuditEvent(
                    event_type="node_error",
                    node_id=node_id,
                    timestamp=datetime.now(),
                    details={
                        'error': str(e),
                        'input_keys': list(kwargs.keys())
                    }
                ))
                raise

        node.run = audited_run

    def _sanitize_parameters(self, parameters):
        """Remove sensitive data from parameters for logging"""
        sanitized = {}
        sensitive_keys = ['password', 'secret', 'key', 'token', 'credential']

        for key, value in parameters.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_parameters(value)
            else:
                sanitized[key] = value

        return sanitized

# Use audited execution
audit_config = {
    'log_path': '/var/log/kailash/audit',
    'rotation_size': 50 * 1024 * 1024,  # 50MB
    'retention_days': 365,  # 1 year for compliance
    'encrypt_logs': True
}

audited_runner = AuditedWorkflowRunner(audit_config)

# Execute with full audit trail
results, run_id = audited_runner.execute_with_audit(
    workflow,
    parameters={'data_source': 'customers.csv'},
    context={
        'user_id': 'john.doe@company.com',
        'source_ip': '192.168.1.100',
        'session_id': 'sess_123456'
    }
)

# Query audit logs
audit_events = audited_runner.audit_logger.query(
    start_date=datetime.now() - timedelta(days=7),
    event_types=['workflow_error', 'node_error'],
    user_id='john.doe@company.com'
)

```

## 6. Zero Trust Security Pattern

**Purpose**: Implement zero trust principles with continuous verification

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

class ZeroTrustNode(SecureNode):
    """Base node with zero trust security"""

    def __init__(self, **config):
        super().__init__(**config)
        self.trust_verifier = TrustVerifier()

    def run(self, **kwargs):
        # Verify trust for every execution
        trust_context = kwargs.get('trust_context', {})

        # Multi-factor verification
        trust_score = self.trust_verifier.calculate_trust_score({
            'user_identity': trust_context.get('user_identity'),
            'device_fingerprint': trust_context.get('device_fingerprint'),
            'location': trust_context.get('location'),
            'behavior_profile': trust_context.get('behavior_profile'),
            'time_of_access': datetime.now()
        })

        # Require minimum trust score
        required_trust = self.config.get('required_trust_score', 0.8)
        if trust_score < required_trust:
            self.log_security_event({
                'action': 'trust_verification_failed',
                'trust_score': trust_score,
                'required_score': required_trust
            })
            raise SecurityError(f"Insufficient trust score: {trust_score}")

        # Verify specific permissions for this operation
        self._verify_operation_permissions(trust_context)

        # Execute with least privilege
        with self.least_privilege_context(trust_context):
            result = self._execute_operation(**kwargs)

        # Log successful operation
        self.log_security_event({
            'action': 'operation_complete',
            'trust_score': trust_score,
            'operation': self.__class__.__name__
        })

        return result

    def _verify_operation_permissions(self, trust_context):
        """Verify specific permissions for this operation"""
        required_permissions = self.get_required_permissions()
        user_permissions = trust_context.get('permissions', [])

        for permission in required_permissions:
            if permission not in user_permissions:
                raise AuthorizationError(f"Missing permission: {permission}")

    @contextmanager
    def least_privilege_context(self, trust_context):
        """Execute with minimal required privileges"""
        original_privileges = self.get_current_privileges()

        try:
            # Drop to minimum required privileges
            required_privileges = self.get_required_privileges()
            self.set_privileges(required_privileges)

            yield

        finally:
            # Restore original privileges
            self.set_privileges(original_privileges)

```

## Best Practices

1. **Defense in Depth**:
   - Implement multiple layers of security
   - Don't rely on single security control
   - Validate at every boundary
   - Assume breach and limit damage

2. **Least Privilege**:
   - Grant minimum necessary permissions
   - Use time-limited credentials
   - Separate duties where possible
   - Regular permission audits

3. **Secure by Default**:
   - Enable security features by default
   - Require explicit unsafe operations
   - Fail securely on errors
   - No default passwords or keys

4. **Monitoring and Response**:
   - Log all security events
   - Monitor for anomalies
   - Have incident response plan
   - Regular security reviews

## See Also
- [Error Handling Patterns](05-error-handling-patterns.md) - Secure error handling
- [Deployment Patterns](09-deployment-patterns.md) - Secure deployment practices
- [Best Practices](11-best-practices.md) - General security guidelines
