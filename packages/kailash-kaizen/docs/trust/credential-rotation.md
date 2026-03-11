# Credential Rotation for EATP

## Quick Start

Credential rotation enables automated key rotation for organizational authorities with grace periods, audit logging, and automatic trust chain re-signing.

### Basic Usage

```python
from kaizen.trust import (
    CredentialRotationManager,
    TrustKeyManager,
    PostgresTrustStore,
    OrganizationalAuthorityRegistry,
)

# Initialize components
key_manager = TrustKeyManager()
trust_store = PostgresTrustStore()
authority_registry = OrganizationalAuthorityRegistry()

# Create rotation manager
rotation_mgr = CredentialRotationManager(
    key_manager=key_manager,
    trust_store=trust_store,
    authority_registry=authority_registry,
    rotation_period_days=90,      # Default rotation period
    grace_period_hours=24,         # Default grace period
)
await rotation_mgr.initialize()

# Rotate a key
result = await rotation_mgr.rotate_key("org-acme")
print(f"Rotated {result.chains_updated} chains")
print(f"Old key: {result.old_key_id}")
print(f"New key: {result.new_key_id}")
print(f"Grace period ends: {result.grace_period_end}")
```

## Core Operations

### 1. Rotate Key

Rotate the signing key for an authority with automatic trust chain re-signing.

```python
result = await rotation_mgr.rotate_key(
    authority_id="org-acme",
    grace_period_hours=48,  # Optional: override default grace period
)

# Result contains:
# - rotation_id: Unique identifier
# - new_key_id: Newly generated key
# - old_key_id: Rotated key
# - chains_updated: Number of chains re-signed
# - started_at, completed_at: Timing
# - grace_period_end: When old key expires
```

### 2. Schedule Rotation

Schedule a future key rotation.

```python
from datetime import datetime, timedelta

# Schedule rotation 90 days from now
future_time = datetime.utcnow() + timedelta(days=90)
rotation_id = await rotation_mgr.schedule_rotation(
    authority_id="org-acme",
    at=future_time,
)

# Process scheduled rotations (e.g., via cron)
results = await rotation_mgr.process_scheduled_rotations()
```

### 3. Check Rotation Status

Get current rotation status for an authority.

```python
status = await rotation_mgr.get_rotation_status("org-acme")

print(f"Current key: {status.current_key_id}")
print(f"Last rotation: {status.last_rotation}")
print(f"Next scheduled: {status.next_scheduled}")
print(f"Status: {status.status.value}")
print(f"Keys in grace period: {len(status.grace_period_keys)}")
print(f"Pending revocations: {len(status.pending_revocations)}")
```

### 4. Revoke Old Key

Revoke an old key after grace period expires.

```python
# Only succeeds if grace period has elapsed
await rotation_mgr.revoke_old_key(
    authority_id="org-acme",
    key_id="key-old-001",
)
```

## Data Classes

### RotationResult

Result of a key rotation operation.

```python
@dataclass
class RotationResult:
    rotation_id: str          # Unique rotation identifier
    new_key_id: str           # Newly generated key
    old_key_id: str           # Rotated key
    chains_updated: int       # Number of chains re-signed
    started_at: datetime      # Rotation start time
    completed_at: datetime    # Rotation completion time
    grace_period_end: Optional[datetime]  # When old key expires
```

### RotationStatusInfo

Current rotation status for an authority.

```python
@dataclass
class RotationStatusInfo:
    last_rotation: Optional[datetime]     # Last rotation timestamp
    next_scheduled: Optional[datetime]    # Next scheduled rotation
    current_key_id: str                   # Active key ID
    pending_revocations: List[str]        # Keys past grace period
    rotation_period_days: int             # Configured rotation period
    status: RotationStatus                # Current status
    grace_period_keys: Dict[str, datetime]  # Keys in grace period
```

### RotationStatus

Status enum for rotation operations.

```python
class RotationStatus(str, Enum):
    PENDING = "pending"           # Scheduled, not yet started
    IN_PROGRESS = "in_progress"   # Currently rotating
    COMPLETED = "completed"       # Rotation finished
    FAILED = "failed"             # Rotation failed
    GRACE_PERIOD = "grace_period" # Keys in grace period
```

## Features

### Grace Period Support

Old keys remain valid during a grace period after rotation:

```python
# Default 24-hour grace period
result = await rotation_mgr.rotate_key("org-acme")

# Custom grace period
result = await rotation_mgr.rotate_key("org-acme", grace_period_hours=48)

# Grace period allows time for:
# - Key propagation to dependent systems
# - Cache invalidation
# - Service restarts
```

### Automatic Trust Chain Re-signing

All trust chains are automatically re-signed after rotation:

```python
# Before rotation: chains signed with old key
# After rotation: chains re-signed with new key
# All signatures updated:
# - Genesis records
# - Capability attestations
# - Delegation records (where authority is delegator)
```

### Concurrent Rotation Prevention

Only one rotation per authority can run at a time:

```python
# First rotation starts
task1 = rotation_mgr.rotate_key("org-acme")

# Second rotation is blocked
try:
    task2 = rotation_mgr.rotate_key("org-acme")
except RotationError as e:
    print("Another rotation is in progress")
```

### Audit Logging

All rotation events are logged for compliance:

```python
# Event types logged:
# - rotation_completed: Successful rotation
# - rotation_failed: Failed rotation
# - rotation_scheduled: Future rotation scheduled
# - key_revoked: Old key revoked

# Each event includes:
# - timestamp
# - authority_id
# - rotation_id
# - event-specific details
```

## Error Handling

### RotationError

Raised when rotation operations fail.

```python
try:
    result = await rotation_mgr.rotate_key("org-missing")
except RotationError as e:
    print(f"Rotation failed: {e.message}")
    print(f"Authority: {e.authority_id}")
    print(f"Rotation: {e.rotation_id}")
    print(f"Reason: {e.reason}")
```

Common error reasons:
- `concurrent_rotation`: Another rotation in progress
- `rotation_failed`: Rotation operation failed
- `invalid_schedule_time`: Scheduled time in past
- `grace_period_not_expired`: Key revocation too early
- `key_not_in_grace_period`: Key not found

## Production Deployment

### Scheduled Rotation

Use cron or orchestration system to process scheduled rotations:

```python
# In a scheduled job (e.g., runs every hour)
async def process_rotations():
    rotation_mgr = CredentialRotationManager(...)
    await rotation_mgr.initialize()

    # Process any due rotations
    results = await rotation_mgr.process_scheduled_rotations()

    for result in results:
        print(f"Rotated {result.authority_id}: {result.rotation_id}")

    await rotation_mgr.close()
```

### Key Revocation

Periodically revoke expired keys:

```python
async def revoke_expired_keys():
    rotation_mgr = CredentialRotationManager(...)
    await rotation_mgr.initialize()

    # Get all authorities
    authorities = await authority_registry.list_authorities()

    for authority in authorities:
        status = await rotation_mgr.get_rotation_status(authority.id)

        # Revoke expired keys
        for key_id in status.pending_revocations:
            await rotation_mgr.revoke_old_key(authority.id, key_id)
            print(f"Revoked key {key_id} for {authority.id}")

    await rotation_mgr.close()
```

### Monitoring

Monitor rotation operations:

```python
async def check_rotation_health():
    rotation_mgr = CredentialRotationManager(...)
    await rotation_mgr.initialize()

    authorities = await authority_registry.list_authorities()

    for authority in authorities:
        status = await rotation_mgr.get_rotation_status(authority.id)

        # Alert if no recent rotation
        if status.last_rotation:
            days_since = (datetime.utcnow() - status.last_rotation).days
            if days_since > 90:
                alert(f"Authority {authority.id} overdue for rotation")

        # Alert if rotation in progress too long
        if status.status == RotationStatus.IN_PROGRESS:
            alert(f"Authority {authority.id} rotation stuck")

    await rotation_mgr.close()
```

## Best Practices

### 1. Regular Rotation Schedule

Rotate keys on a regular schedule (e.g., every 90 days):

```python
# Schedule rotation for all authorities
for authority in authorities:
    next_rotation = datetime.utcnow() + timedelta(days=90)
    await rotation_mgr.schedule_rotation(authority.id, at=next_rotation)
```

### 2. Grace Period Configuration

Choose grace period based on system architecture:

- **Microservices**: 24-48 hours (time for pod restarts)
- **Monoliths**: 12-24 hours (faster propagation)
- **Legacy Systems**: 48-72 hours (manual intervention may be needed)

### 3. Key Storage

In production, replace in-memory TrustKeyManager with secure key storage:

- **HSM**: Hardware Security Modules for maximum security
- **KMS**: Cloud key management services (AWS KMS, Azure Key Vault)
- **Vault**: HashiCorp Vault for secrets management

### 4. Audit Logging

Integrate rotation events with enterprise audit systems:

```python
class ProductionRotationManager(CredentialRotationManager):
    async def _log_rotation_event(self, authority_id, rotation_id, event_type, details):
        # Send to SIEM
        await siem_client.log_event({
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": f"trust.rotation.{event_type}",
            "authority_id": authority_id,
            "rotation_id": rotation_id,
            "details": details,
        })

        # Send metrics
        metrics_client.increment(f"rotation.{event_type}")
```

### 5. Testing

Test rotation in staging before production:

```python
# In test environment
async def test_rotation():
    # Rotate with short grace period
    result = await rotation_mgr.rotate_key(
        "org-test",
        grace_period_hours=1,
    )

    # Verify chains still valid
    for agent_id in test_agents:
        chain = await trust_store.get_chain(agent_id)
        assert chain.verify_basic().valid

    # Test key revocation
    await asyncio.sleep(3600)  # Wait 1 hour
    await rotation_mgr.revoke_old_key("org-test", result.old_key_id)
```

## Examples

See `examples/trust/credential_rotation_example.py` for a comprehensive example demonstrating:
- Basic rotation
- Scheduled rotation
- Status checking
- Key revocation
- Grace period handling
- Trust chain verification

## API Reference

### CredentialRotationManager

```python
class CredentialRotationManager:
    def __init__(
        self,
        key_manager: TrustKeyManager,
        trust_store: PostgresTrustStore,
        authority_registry: OrganizationalAuthorityRegistry,
        rotation_period_days: int = 90,
        grace_period_hours: int = 24,
    )

    async def initialize() -> None
    async def rotate_key(authority_id: str, grace_period_hours: Optional[int] = None) -> RotationResult
    async def schedule_rotation(authority_id: str, at: datetime) -> str
    async def get_rotation_status(authority_id: str) -> RotationStatusInfo
    async def revoke_old_key(authority_id: str, key_id: str) -> None
    async def process_scheduled_rotations() -> List[RotationResult]
    async def close() -> None
```

## Troubleshooting

### Rotation Hanging

If rotation appears stuck:

```python
status = await rotation_mgr.get_rotation_status("org-acme")
if status.status == RotationStatus.IN_PROGRESS:
    # Check active rotations
    if "org-acme" in rotation_mgr._active_rotations:
        # Remove stuck rotation
        rotation_mgr._active_rotations.discard("org-acme")
```

### Chain Re-signing Failures

If chains fail to re-sign:

```python
# Check chain count
chains = await trust_store.list_chains(authority_id="org-acme")
print(f"Found {len(chains)} chains to re-sign")

# Verify chain signatures manually
for chain in chains:
    result = chain.verify_basic()
    if not result.valid:
        print(f"Chain {chain.genesis.agent_id} invalid: {result.reason}")
```

### Grace Period Issues

If key revocation fails:

```python
status = await rotation_mgr.get_rotation_status("org-acme")

# Check grace period keys
for key_id, expiry in status.grace_period_keys.items():
    remaining = expiry - datetime.utcnow()
    print(f"Key {key_id}: {remaining.total_seconds() / 3600:.1f} hours remaining")

# Force revocation (dangerous!)
rotation_mgr._grace_period_keys["org-acme"][key_id] = datetime.utcnow() - timedelta(hours=1)
await rotation_mgr.revoke_old_key("org-acme", key_id)
```
