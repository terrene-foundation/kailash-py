# EATP Security Hardening (Week 11)

**Status**: ✅ Complete
**Version**: 1.0.0
**Last Updated**: 2025-12-15

## Overview

Security Hardening provides comprehensive security features for the Enterprise Agent Trust Protocol (EATP), including input validation, encrypted key storage, rate limiting, and security audit logging.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Security Hardening Layer                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────┐  ┌──────────────────────┐        │
│  │ TrustSecurityValidator│  │  SecureKeyStorage   │        │
│  │                      │  │                      │        │
│  │ - validate_agent_id  │  │ - store_key          │        │
│  │ - validate_authority │  │ - retrieve_key       │        │
│  │ - validate_uri       │  │ - delete_key         │        │
│  │ - sanitize_metadata  │  │ (Fernet Encryption)  │        │
│  └──────────────────────┘  └──────────────────────┘        │
│                                                              │
│  ┌──────────────────────┐  ┌──────────────────────┐        │
│  │  TrustRateLimiter    │  │ SecurityAuditLogger  │        │
│  │                      │  │                      │        │
│  │ - check_rate         │  │ - log_security_event │        │
│  │ - record_operation   │  │ - get_recent_events  │        │
│  │ (Per-Authority)      │  │ (Event Tracking)     │        │
│  └──────────────────────┘  └──────────────────────┘        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. TrustSecurityValidator

Validates input to prevent injection attacks and ensure data integrity.

**Key Features**:
- Agent ID validation (UUID format)
- Authority ID validation (alphanumeric with hyphens)
- Capability URI validation (valid URI format)
- Metadata sanitization (removes script tags, event handlers, etc.)

**Example**:
```python
from kaizen.trust.security import TrustSecurityValidator

validator = TrustSecurityValidator()

# Validate agent ID (UUID format)
is_valid = validator.validate_agent_id("550e8400-e29b-41d4-a716-446655440000")
# True

# Validate authority ID
is_valid = validator.validate_authority_id("org-acme-corp")
# True

# Validate capability URI
is_valid = validator.validate_capability_uri("urn:capability:read:data")
# True

# Sanitize metadata (removes unsafe content)
unsafe_metadata = {
    "name": "Agent<script>alert(1)</script>",
    "description": "Safe content"
}
safe_metadata = validator.sanitize_metadata(unsafe_metadata)
# {"name": "Agent", "description": "Safe content"}
```

**Validation Rules**:
- **Agent ID**: Must be valid UUID (8-4-4-4-12 hex format)
- **Authority ID**: 1-64 characters, alphanumeric + hyphens/underscores, must start with alphanumeric
- **Capability URI**: Valid URI with safe scheme (no javascript:, data:, vbscript:)
- **Metadata**: Removes `<script>` tags, event handlers (`onclick`, etc.), data URIs

### 2. SecureKeyStorage

Encrypted storage for cryptographic keys using Fernet symmetric encryption.

**Key Features**:
- Keys encrypted at rest using Fernet (AES-128 in CBC mode)
- Master key derived from environment variable using PBKDF2
- Secure deletion support
- In-memory storage (can be extended to persistent storage)

**Example**:
```python
import os
from kaizen.trust.security import SecureKeyStorage

# Set master key (in production, use secure secret management)
os.environ['KAIZEN_TRUST_ENCRYPTION_KEY'] = 'your-secure-master-key'

storage = SecureKeyStorage()

# Store a key
storage.store_key("agent-001", b"private_key_bytes")

# Retrieve a key
private_key = storage.retrieve_key("agent-001")

# Delete a key
storage.delete_key("agent-001")
```

**Security Properties**:
- **Encryption**: AES-128-CBC via Fernet
- **Key Derivation**: PBKDF2-HMAC-SHA256, 100,000 iterations
- **Salt**: Static salt for deterministic key derivation
- **Storage**: In-memory (extend for persistent storage)

### 3. TrustRateLimiter

Per-authority rate limiting using sliding window algorithm.

**Key Features**:
- Configurable limits per operation type
- Per-authority isolation (one authority can't exhaust another's quota)
- Async-first API
- Sliding window algorithm (1-minute window)

**Example**:
```python
from kaizen.trust.security import TrustRateLimiter, RateLimitExceededError

limiter = TrustRateLimiter(
    establish_per_minute=100,
    verify_per_minute=1000
)

# Check if operation is within limits
can_proceed = await limiter.check_rate("establish", "org-acme")

# Record an operation (raises RateLimitExceededError if exceeded)
try:
    await limiter.record_operation("establish", "org-acme")
except RateLimitExceededError as e:
    print(f"Rate limit exceeded: {e.limit} ops/minute")
```

**Configuration**:
- `establish_per_minute`: Max establish operations per authority (default: 100)
- `verify_per_minute`: Max verify operations per authority (default: 1000)
- Custom operations default to 100/minute

### 4. SecurityAuditLogger

Security event logging with severity levels and filtering.

**Key Features**:
- Event type categorization (authentication, authorization, rate limiting, etc.)
- Severity levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Filtering by event type, authority, and severity
- Automatic cleanup of old events

**Example**:
```python
from kaizen.trust.security import (
    SecurityAuditLogger,
    SecurityEventType,
    SecurityEventSeverity
)

logger = SecurityAuditLogger(max_events=10000)

# Log a security event
logger.log_security_event(
    event_type=SecurityEventType.ESTABLISH_TRUST,
    details={"agent_id": "agent-001", "capability": "read"},
    authority_id="org-acme",
    agent_id="agent-001",
    severity=SecurityEventSeverity.INFO
)

# Query recent events
recent_events = logger.get_recent_events(count=100)

# Filter by severity
critical_events = logger.get_recent_events(
    count=50,
    severity=SecurityEventSeverity.CRITICAL
)

# Filter by event type
rate_limit_events = logger.get_recent_events(
    count=50,
    event_type=SecurityEventType.RATE_LIMIT_EXCEEDED
)
```

**Event Types**:
- **Authentication**: `AUTHENTICATION_SUCCESS`, `AUTHENTICATION_FAILURE`
- **Authorization**: `AUTHORIZATION_SUCCESS`, `AUTHORIZATION_FAILURE`
- **Trust Operations**: `ESTABLISH_TRUST`, `VERIFY_TRUST`, `DELEGATE_CAPABILITY`, `REVOKE_DELEGATION`
- **Validation**: `VALIDATION_SUCCESS`, `VALIDATION_FAILURE`
- **Key Management**: `KEY_STORED`, `KEY_RETRIEVED`, `KEY_DELETED`
- **Rate Limiting**: `RATE_LIMIT_EXCEEDED`, `RATE_LIMIT_WARNING`
- **Attack Detection**: `INJECTION_ATTEMPT`, `REPLAY_ATTACK`, `SUSPICIOUS_ACTIVITY`

**Severity Levels**:
- `DEBUG`: Detailed diagnostic information
- `INFO`: Normal operations
- `WARNING`: Potential issues or policy violations
- `ERROR`: Error conditions
- `CRITICAL`: Security incidents requiring immediate attention

## Integration with EATP

### With TrustOperations

```python
from kaizen.trust import TrustOperations
from kaizen.trust.security import (
    TrustSecurityValidator,
    TrustRateLimiter,
    SecurityAuditLogger,
    SecurityEventType,
    SecurityEventSeverity,
    RateLimitExceededError
)

# Initialize security components
validator = TrustSecurityValidator()
limiter = TrustRateLimiter(establish_per_minute=100)
audit_logger = SecurityAuditLogger()

# Initialize trust operations
trust_ops = TrustOperations(registry, key_manager, store)
await trust_ops.initialize()

async def secure_establish(agent_id: str, authority_id: str, capabilities: list):
    """Establish trust with security hardening."""

    # 1. Validate inputs
    if not validator.validate_agent_id(agent_id):
        audit_logger.log_security_event(
            event_type=SecurityEventType.VALIDATION_FAILURE,
            details={"reason": "Invalid agent ID", "input": agent_id},
            authority_id=authority_id,
            severity=SecurityEventSeverity.WARNING
        )
        raise ValueError("Invalid agent ID format")

    if not validator.validate_authority_id(authority_id):
        audit_logger.log_security_event(
            event_type=SecurityEventType.VALIDATION_FAILURE,
            details={"reason": "Invalid authority ID", "input": authority_id},
            authority_id=authority_id,
            severity=SecurityEventSeverity.WARNING
        )
        raise ValueError("Invalid authority ID format")

    # 2. Check rate limit
    try:
        await limiter.record_operation("establish", authority_id)
    except RateLimitExceededError as e:
        audit_logger.log_security_event(
            event_type=SecurityEventType.RATE_LIMIT_EXCEEDED,
            details={"operation": "establish", "limit": e.limit},
            authority_id=authority_id,
            agent_id=agent_id,
            severity=SecurityEventSeverity.WARNING
        )
        raise

    # 3. Establish trust
    try:
        chain = await trust_ops.establish(
            agent_id=agent_id,
            authority_id=authority_id,
            capabilities=capabilities
        )

        # 4. Log success
        audit_logger.log_security_event(
            event_type=SecurityEventType.ESTABLISH_TRUST,
            details={"capabilities": [c.capability for c in capabilities]},
            authority_id=authority_id,
            agent_id=agent_id,
            severity=SecurityEventSeverity.INFO
        )

        return chain

    except Exception as e:
        # Log failure
        audit_logger.log_security_event(
            event_type=SecurityEventType.AUTHORIZATION_FAILURE,
            details={"error": str(e)},
            authority_id=authority_id,
            agent_id=agent_id,
            severity=SecurityEventSeverity.ERROR
        )
        raise
```

### With TrustedAgent

```python
from kaizen.trust import TrustedAgent, TrustedAgentConfig
from kaizen.trust.security import (
    TrustSecurityValidator,
    SecurityAuditLogger,
    SecurityEventType
)

validator = TrustSecurityValidator()
audit_logger = SecurityAuditLogger()

class SecureAgent(TrustedAgent):
    """TrustedAgent with security hardening."""

    async def execute(self, input_data: dict) -> dict:
        """Execute with input validation and audit logging."""

        # Validate and sanitize input
        safe_input = validator.sanitize_metadata(input_data)

        # Log execution
        audit_logger.log_security_event(
            event_type=SecurityEventType.AUTHORIZATION_SUCCESS,
            details={"action": "execute", "input_keys": list(safe_input.keys())},
            authority_id=self.authority_id,
            agent_id=self.agent_id
        )

        # Execute with safe input
        return await super().execute(safe_input)
```

## Configuration

### Environment Variables

```bash
# Master key for encryption (required for SecureKeyStorage)
export KAIZEN_TRUST_ENCRYPTION_KEY="your-secure-master-key-here"

# In production, use secret management (AWS Secrets Manager, HashiCorp Vault, etc.)
# DO NOT hardcode in source code or commit to version control
```

### Rate Limit Tuning

```python
# Development/Testing
limiter = TrustRateLimiter(
    establish_per_minute=10,   # Low limit for testing
    verify_per_minute=100
)

# Production (Light Load)
limiter = TrustRateLimiter(
    establish_per_minute=100,
    verify_per_minute=1000
)

# Production (Heavy Load)
limiter = TrustRateLimiter(
    establish_per_minute=500,
    verify_per_minute=5000
)
```

### Audit Logger Configuration

```python
# Small deployment
logger = SecurityAuditLogger(max_events=1000)

# Medium deployment
logger = SecurityAuditLogger(max_events=10000)

# Large deployment (use persistent storage)
logger = SecurityAuditLogger(max_events=100000)
```

## Security Best Practices

### 1. Input Validation

**Always validate user input before processing**:
```python
validator = TrustSecurityValidator()

# Validate before use
if not validator.validate_agent_id(agent_id):
    raise ValueError("Invalid agent ID")

if not validator.validate_authority_id(authority_id):
    raise ValueError("Invalid authority ID")

# Sanitize metadata
safe_metadata = validator.sanitize_metadata(user_metadata)
```

### 2. Key Management

**Use environment variables for master keys**:
```python
# ✅ GOOD: Load from environment
os.environ['KAIZEN_TRUST_ENCRYPTION_KEY'] = get_from_secret_manager()
storage = SecureKeyStorage()

# ❌ BAD: Hardcoded in source
storage = SecureKeyStorage()
storage._master_key = "hardcoded-key"  # NEVER DO THIS
```

**Rotate encryption keys regularly**:
```python
# Re-encrypt keys with new master key
old_storage = SecureKeyStorage("OLD_MASTER_KEY")
new_storage = SecureKeyStorage("NEW_MASTER_KEY")

for key_id in key_ids:
    key_data = old_storage.retrieve_key(key_id)
    new_storage.store_key(key_id, key_data)
    old_storage.delete_key(key_id)
```

### 3. Rate Limiting

**Set appropriate limits based on load**:
```python
# Monitor rate limit events
rate_limit_events = audit_logger.get_recent_events(
    event_type=SecurityEventType.RATE_LIMIT_EXCEEDED
)

# Adjust limits if necessary
if len(rate_limit_events) > threshold:
    # Increase limits or investigate
    pass
```

### 4. Audit Logging

**Monitor critical events**:
```python
# Set up alerting for critical events
critical_events = audit_logger.get_recent_events(
    severity=SecurityEventSeverity.CRITICAL
)

for event in critical_events:
    if event.event_type == SecurityEventType.INJECTION_ATTEMPT:
        send_alert(f"Injection attempt detected: {event.details}")
    elif event.event_type == SecurityEventType.REPLAY_ATTACK:
        send_alert(f"Replay attack detected: {event.details}")
```

**Persist audit logs**:
```python
# Integrate with persistent storage
class PersistentSecurityAuditLogger(SecurityAuditLogger):
    def __init__(self, db_connection):
        super().__init__()
        self.db = db_connection

    def log_security_event(self, event_type, details, **kwargs):
        super().log_security_event(event_type, details, **kwargs)
        # Persist to database
        self.db.insert_event(event_type, details, **kwargs)
```

## Performance Considerations

### Validation Overhead

Input validation adds minimal overhead:
- Agent ID validation: ~1-2 μs
- Authority ID validation: ~1-2 μs
- URI validation: ~5-10 μs
- Metadata sanitization: ~10-50 μs (depends on size)

### Encryption Overhead

Key encryption/decryption:
- Store key: ~0.5-1 ms
- Retrieve key: ~0.5-1 ms
- Delete key: ~1 μs

### Rate Limiting Overhead

Rate limit checks:
- Check rate: ~10-50 μs (async lock + list filtering)
- Record operation: ~10-50 μs

### Audit Logging Overhead

Event logging:
- Log event: ~1-5 μs (in-memory append)
- Query events: ~10-100 μs (depends on filter complexity)

## Testing

Run the example:
```bash
python examples/trust/security_hardening_example.py
```

Example output:
```
================================================================================
1. INPUT VALIDATION
================================================================================
Valid Inputs:
  Agent ID (UUID): 550e8400-e29b-41d4-a716-446655440000
  Valid: True

Invalid Inputs (Injection Attempts):
  Malicious Agent ID: agent<script>alert(1)</script>
  Valid: False

================================================================================
2. ENCRYPTED KEY STORAGE
================================================================================
Storing Keys:
  Stored encrypted key for: agent-001

Retrieving Keys:
  Retrieved key for agent-001: ✓ matches

================================================================================
3. RATE LIMITING
================================================================================
Establish Operations (limit: 5/minute):
  Operation 1: can_proceed=True
    ✓ Recorded
  Operation 6: can_proceed=False
    ✗ Rate limit would be exceeded

================================================================================
4. SECURITY AUDIT LOGGING
================================================================================
Critical Events Only:
  [2025-12-15T14:21:17.654302+00:00] injection_attempt
    Details: {'input': "'; DROP TABLE users;--"}
```

## Exceptions

### SecurityError
Base exception for all security-related errors.

### ValidationError
Raised when input validation fails.
```python
try:
    validator = TrustSecurityValidator()
    if not validator.validate_agent_id(agent_id):
        raise ValidationError(f"Invalid agent ID: {agent_id}")
except ValidationError as e:
    print(f"Validation failed: {e}")
```

### EncryptionError
Raised when encryption/decryption operations fail.
```python
try:
    storage = SecureKeyStorage()
    storage.store_key(key_id, key_data)
except EncryptionError as e:
    print(f"Encryption failed: {e}")
```

### RateLimitExceededError
Raised when rate limit is exceeded.
```python
try:
    await limiter.record_operation("establish", authority_id)
except RateLimitExceededError as e:
    print(f"Rate limit exceeded: {e.operation} by {e.authority_id}")
    print(f"Limit: {e.limit} ops/minute")
```

## Production Deployment

### 1. Environment Setup

```bash
# Set encryption key from secret manager
export KAIZEN_TRUST_ENCRYPTION_KEY=$(aws secretsmanager get-secret-value --secret-id kaizen-trust-master-key --query SecretString --output text)

# Set rate limits
export KAIZEN_ESTABLISH_RATE_LIMIT=500
export KAIZEN_VERIFY_RATE_LIMIT=5000
```

### 2. Initialize Components

```python
import os
from kaizen.trust.security import (
    TrustSecurityValidator,
    SecureKeyStorage,
    TrustRateLimiter,
    SecurityAuditLogger
)

# Initialize with production settings
validator = TrustSecurityValidator()
storage = SecureKeyStorage()  # Uses KAIZEN_TRUST_ENCRYPTION_KEY
limiter = TrustRateLimiter(
    establish_per_minute=int(os.getenv('KAIZEN_ESTABLISH_RATE_LIMIT', 500)),
    verify_per_minute=int(os.getenv('KAIZEN_VERIFY_RATE_LIMIT', 5000))
)
audit_logger = SecurityAuditLogger(max_events=100000)
```

### 3. Monitoring

```python
# Monitor rate limit usage
async def monitor_rate_limits():
    while True:
        events = audit_logger.get_recent_events(
            count=1000,
            event_type=SecurityEventType.RATE_LIMIT_EXCEEDED
        )

        if len(events) > 100:  # Threshold
            print(f"HIGH RATE LIMIT VIOLATIONS: {len(events)}")
            # Send alert

        await asyncio.sleep(60)  # Check every minute
```

## Future Enhancements

### Planned Features
- [ ] Persistent storage backend for SecureKeyStorage (PostgreSQL, Redis)
- [ ] Distributed rate limiting using Redis
- [ ] Persistent audit log storage with PostgreSQL
- [ ] Advanced threat detection (anomaly detection, ML-based)
- [ ] Integration with SIEM systems (Splunk, ELK)
- [ ] Automated response to security events

### Under Consideration
- Hardware Security Module (HSM) integration
- Multi-factor authentication for sensitive operations
- Geo-based rate limiting and access control
- Real-time security dashboards

## References

- [Fernet Specification](https://github.com/fernet/spec)
- [PBKDF2 Specification](https://tools.ietf.org/html/rfc2898)
- [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html)
- [Rate Limiting Patterns](https://cloud.google.com/architecture/rate-limiting-strategies-techniques)
