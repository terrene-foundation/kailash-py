# EATP Security Best Practices

Enterprise security guidelines for deploying EATP (Enterprise Agent Trust Protocol) in production environments.

## Overview

EATP provides cryptographic trust chains for AI agents. This guide covers:

1. Key management and rotation
2. Authority configuration
3. Constraint design
4. Audit and compliance
5. Network security
6. Operational security

## 1. Key Management

### Use Hardware Security Modules (HSMs)

For production environments, store authority keys in HSMs:

```python
from kaizen.trust import SecureKeyStorage

# Production: Use HSM or KMS
key_storage = SecureKeyStorage(
    backend="aws_kms",  # or "azure_keyvault", "hashicorp_vault"
    key_id="arn:aws:kms:us-east-1:123456789:key/abc123",
)

# Development only: In-memory storage
# key_storage = SecureKeyStorage()  # NOT for production
```

### Implement Key Rotation

Rotate authority keys regularly:

```python
from kaizen.trust import CredentialRotationManager

rotation_manager = CredentialRotationManager(
    key_manager=key_manager,
    trust_store=trust_store,
    authority_registry=authority_registry,
    rotation_period_days=90,  # Rotate every 90 days
    grace_period_hours=24,    # 24-hour grace period
)

# Schedule automatic rotation
await rotation_manager.schedule_rotation(
    authority_id="org-production",
    at=datetime.utcnow() + timedelta(days=90),
)

# Monitor rotation status
status = await rotation_manager.get_rotation_status("org-production")
print(f"Last rotation: {status.last_rotation}")
print(f"Next scheduled: {status.next_scheduled}")
```

### Key Storage Security

```python
from kaizen.trust import SecureKeyStorage

# Use encrypted storage
storage = SecureKeyStorage(
    encryption_key=os.getenv("EATP_ENCRYPTION_KEY"),  # 32-byte key
)

# Store key encrypted at rest
storage.store_key("key-prod-001", private_key)

# Retrieve key (decrypted in memory)
key = storage.get_key("key-prod-001")
```

**Key Storage Checklist:**
- [ ] Keys encrypted at rest
- [ ] Keys never logged
- [ ] Keys not in source control
- [ ] Keys rotated regularly
- [ ] Old keys securely deleted

## 2. Authority Configuration

### Principle of Least Privilege

Grant minimum necessary permissions:

```python
from kaizen.trust import (
    OrganizationalAuthority,
    AuthorityPermission,
)

# Root authority (minimal permissions)
root_authority = OrganizationalAuthority(
    id="org-root",
    permissions=[
        AuthorityPermission.CREATE_SUB_AUTHORITIES,  # Only creates sub-authorities
    ],
)

# Team authority (agent-focused)
team_authority = OrganizationalAuthority(
    id="org-team-analytics",
    permissions=[
        AuthorityPermission.CREATE_AGENTS,      # Can create agents
        AuthorityPermission.GRANT_CAPABILITIES, # Can grant capabilities
        # NO AuthorityPermission.REVOKE_CAPABILITIES - escalate to admin
    ],
)
```

### Authority Hierarchy

```
                    org-root
                       │
         ┌─────────────┼─────────────┐
         │             │             │
    org-prod      org-staging    org-dev
         │             │             │
    ┌────┴────┐   ┌────┴────┐   ┌────┴────┐
  team-a   team-b  team-a   team-b  team-all
```

### Separate Environments

```python
# Production authority (strict)
prod_authority = OrganizationalAuthority(
    id="org-production",
    metadata={
        "environment": "production",
        "approval_required": True,
        "audit_level": "full",
    },
)

# Development authority (relaxed)
dev_authority = OrganizationalAuthority(
    id="org-development",
    metadata={
        "environment": "development",
        "approval_required": False,
        "audit_level": "standard",
    },
)
```

## 3. Constraint Design

### Defense in Depth

Apply multiple constraint types:

```python
from kaizen.trust import Constraint, ConstraintType

# Layer 1: Resource limits
resource_constraints = [
    Constraint(
        constraint_type=ConstraintType.RESOURCE_LIMIT,
        name="max_api_calls_per_hour",
        value=1000,
    ),
    Constraint(
        constraint_type=ConstraintType.RESOURCE_LIMIT,
        name="max_tokens_per_request",
        value=4000,
    ),
]

# Layer 2: Time restrictions
time_constraints = [
    Constraint(
        constraint_type=ConstraintType.TIME_WINDOW,
        name="business_hours",
        value={"start": "09:00", "end": "18:00", "timezone": "UTC"},
    ),
    Constraint(
        constraint_type=ConstraintType.TIME_WINDOW,
        name="expiration",
        value={"expires_at": "2025-12-31T23:59:59Z"},
    ),
]

# Layer 3: Data scope
scope_constraints = [
    Constraint(
        constraint_type=ConstraintType.DATA_SCOPE,
        name="allowed_databases",
        value=["analytics_db"],
        metadata={"deny_list": ["hr_db", "finance_db", "audit_db"]},
    ),
]

# Layer 4: Action restrictions
action_constraints = [
    Constraint(
        constraint_type=ConstraintType.ACTION_RESTRICTION,
        name="no_destructive_ops",
        value={"deny": ["DELETE", "DROP", "TRUNCATE"]},
    ),
]

# Layer 5: Audit requirements
audit_constraints = [
    Constraint(
        constraint_type=ConstraintType.AUDIT_REQUIREMENT,
        name="mandatory_logging",
        value=True,
        metadata={"retention_days": 365},
    ),
]

# Combine all layers
all_constraints = (
    resource_constraints +
    time_constraints +
    scope_constraints +
    action_constraints +
    audit_constraints
)
```

### Constraint Inheritance Rules

Remember: Constraints can only be TIGHTENED during delegation:

```python
# Parent agent: max_records=10000
# Worker MUST have max_records <= 10000

# VALID: Tighter constraint
delegation = await trust_ops.delegate(
    delegator_agent_id="supervisor",
    delegatee_agent_id="worker",
    constraints=[
        Constraint(
            constraint_type=ConstraintType.RESOURCE_LIMIT,
            name="max_records",
            value=5000,  # Tighter than 10000
        ),
    ],
)

# INVALID: Looser constraint (raises ConstraintViolationError)
# value=20000 would fail
```

## 4. Audit and Compliance

### Enable Comprehensive Logging

```python
from kaizen.trust import (
    SecurityAuditLogger,
    SecurityEventType,
    SecurityEventSeverity,
)

# Initialize audit logger
audit_logger = SecurityAuditLogger(
    log_level=SecurityEventSeverity.INFO,
    include_metadata=True,
)

# Log security events
audit_logger.log_security_event(
    event_type=SecurityEventType.TRUST_VERIFICATION_FAILED,
    details={
        "agent_id": agent_id,
        "action": action,
        "reason": "capability_not_found",
    },
    severity=SecurityEventSeverity.WARNING,
)
```

### Audit Retention

Configure appropriate retention:

```python
# Compliance requirements
AUDIT_RETENTION = {
    "financial_services": 365 * 7,  # 7 years
    "healthcare": 365 * 6,          # 6 years
    "general": 365,                 # 1 year
}

audit_store = PostgresAuditStore(
    database_url=os.getenv("POSTGRES_URL"),
    retention_days=AUDIT_RETENTION["financial_services"],
    enable_compression=True,  # Compress old records
)
```

### Compliance Reports

Generate periodic compliance reports:

```python
from kaizen.trust import AuditQueryService

audit_service = AuditQueryService(audit_store=audit_store)

# Weekly compliance report
report = await audit_service.generate_compliance_report(
    authority_id="org-production",
    start_time=datetime.utcnow() - timedelta(days=7),
    end_time=datetime.utcnow(),
)

# Check for anomalies
if report.denied_actions > report.total_actions * 0.1:
    alert_security_team(
        "High denial rate detected",
        report=report,
    )
```

## 5. Network Security

### TLS for All Connections

```python
# Database with TLS
trust_store = PostgresTrustStore(
    database_url="postgresql://user:pass@host:5432/db?sslmode=require",
)

# A2A service with TLS
from kaizen.trust.a2a import A2AService

a2a = A2AService(
    trust_operations=trust_ops,
    tls_cert_path="/path/to/cert.pem",
    tls_key_path="/path/to/key.pem",
)
```

### Rate Limiting

```python
from kaizen.trust import TrustRateLimiter

rate_limiter = TrustRateLimiter(
    default_limit=100,      # 100 requests
    window_seconds=60,      # per minute
)

# Check before processing
if not await rate_limiter.check(authority_id):
    raise RateLimitExceededError(
        f"Rate limit exceeded for {authority_id}"
    )
```

### Input Validation

```python
from kaizen.trust import TrustSecurityValidator

validator = TrustSecurityValidator()

# Validate all inputs
if not validator.validate_agent_id(agent_id):
    raise ValidationError("Invalid agent_id format")

if not validator.validate_authority_id(authority_id):
    raise ValidationError("Invalid authority_id format")

if not validator.validate_capability_uri(capability_uri):
    raise ValidationError("Invalid capability_uri")

# Sanitize metadata
safe_metadata = validator.sanitize_metadata(user_metadata)
```

## 6. Operational Security

### Monitoring and Alerting

```python
# Monitor key metrics
metrics = {
    "trust_verification_failures": Counter(),
    "constraint_violations": Counter(),
    "delegation_denials": Counter(),
    "rate_limit_hits": Counter(),
}

# Alert thresholds
ALERT_THRESHOLDS = {
    "verification_failure_rate": 0.05,  # 5%
    "constraint_violation_rate": 0.01,   # 1%
    "delegation_denial_rate": 0.10,      # 10%
}

async def check_security_metrics():
    total = metrics["trust_verification_total"].get()
    failures = metrics["trust_verification_failures"].get()

    if failures / total > ALERT_THRESHOLDS["verification_failure_rate"]:
        alert_security_team("High verification failure rate")
```

### Incident Response

```python
# Security incident handler
async def handle_security_incident(incident_type: str, details: dict):
    # 1. Log incident
    audit_logger.log_security_event(
        event_type=SecurityEventType.SECURITY_INCIDENT,
        details=details,
        severity=SecurityEventSeverity.CRITICAL,
    )

    # 2. Deactivate compromised authority if needed
    if incident_type == "authority_compromise":
        await authority_registry.deactivate_authority(
            details["authority_id"]
        )

    # 3. Revoke affected trust chains
    if incident_type == "agent_compromise":
        await trust_store.revoke_chain(details["agent_id"])

    # 4. Alert security team
    alert_security_team(incident_type, details)
```

### Secure Deployment

```yaml
# Kubernetes security context
apiVersion: v1
kind: Pod
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    readOnlyRootFilesystem: true
  containers:
  - name: kaizen-trust
    securityContext:
      allowPrivilegeEscalation: false
      capabilities:
        drop:
          - ALL
    env:
      - name: POSTGRES_URL
        valueFrom:
          secretKeyRef:
            name: trust-secrets
            key: database-url
      - name: EATP_ENCRYPTION_KEY
        valueFrom:
          secretKeyRef:
            name: trust-secrets
            key: encryption-key
```

## Security Checklist

### Pre-Production

- [ ] HSM or KMS configured for key storage
- [ ] Key rotation schedule established
- [ ] Authority hierarchy designed
- [ ] Least privilege permissions applied
- [ ] Multi-layer constraints configured
- [ ] Audit retention configured
- [ ] TLS enabled for all connections
- [ ] Rate limiting configured
- [ ] Input validation enabled
- [ ] Monitoring dashboards created
- [ ] Alerting rules configured
- [ ] Incident response plan documented

### Post-Production

- [ ] Regular key rotation verified
- [ ] Compliance reports reviewed weekly
- [ ] Security metrics monitored
- [ ] Penetration testing scheduled
- [ ] Security audits scheduled
- [ ] Incident response drills conducted

## Common Vulnerabilities to Avoid

### 1. Key Exposure

❌ **Don't:**
```python
# NEVER log keys
logger.info(f"Using key: {private_key}")

# NEVER commit keys
KEY = "ed25519_sk_..." # In source code
```

✅ **Do:**
```python
# Use environment variables
key = os.getenv("EATP_PRIVATE_KEY")

# Use secrets management
key = vault_client.get_secret("eatp/private-key")
```

### 2. Insufficient Validation

❌ **Don't:**
```python
# Don't trust user input
agent_id = request.json["agent_id"]
await trust_ops.verify(agent_id=agent_id)  # No validation!
```

✅ **Do:**
```python
# Always validate
agent_id = request.json["agent_id"]
if not validator.validate_agent_id(agent_id):
    raise ValidationError("Invalid agent_id")
await trust_ops.verify(agent_id=agent_id)
```

### 3. Missing Audit

❌ **Don't:**
```python
# Don't skip audit
result = await agent.run(task)
# No audit record!
```

✅ **Do:**
```python
# Always audit
result = await agent.run(task)
await trust_ops.audit(
    agent_id=agent.agent_id,
    action_type="task_execution",
    resource_uri=task.resource_uri,
    result=ActionResult.SUCCESS if result else ActionResult.FAILURE,
)
```

### 4. Weak Constraints

❌ **Don't:**
```python
# Don't use overly permissive constraints
constraints=[
    Constraint(
        constraint_type=ConstraintType.RESOURCE_LIMIT,
        name="max_records",
        value=999999999,  # Effectively no limit
    ),
]
```

✅ **Do:**
```python
# Use meaningful limits
constraints=[
    Constraint(
        constraint_type=ConstraintType.RESOURCE_LIMIT,
        name="max_records",
        value=10000,  # Reasonable limit based on use case
    ),
]
```

## References

- [EATP API Reference](../api/trust.md)
- [EATP Migration Guide](./eatp-migration-guide.md)
- [OWASP Security Guidelines](https://owasp.org)
- [NIST Cryptographic Standards](https://csrc.nist.gov)

## Support

For security concerns:
- Security Issues: security@kailash.dev
- GitHub Security Advisories: https://github.com/terrene-foundation/kailash-py/security
