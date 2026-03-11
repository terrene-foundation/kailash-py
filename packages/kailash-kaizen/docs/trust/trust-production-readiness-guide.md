# Trust System Production Readiness Guide

This guide covers the Phase 5 P1 production readiness features for the EATP (Enterprise Agent Trust Protocol) trust system. These security hardening features are essential for production deployment.

## Overview

The Phase 5 P1 features provide enterprise-grade security and reliability:

| Feature                  | CARE ID  | Purpose                        |
| ------------------------ | -------- | ------------------------------ |
| Key Management           | CARE-005 | Pluggable HSM/KMS key backends |
| Linked State Hashing     | CARE-006 | Tamper-evident hash chains     |
| Revocation Broadcasting  | CARE-007 | Real-time cascade revocation   |
| Transactional Re-signing | CARE-008 | Atomic key rotation            |
| Constraint Inheritance   | CARE-009 | Widening attack prevention     |
| Append-Only Audit        | CARE-010 | Immutable audit trails         |

---

## Key Management (CARE-005)

Provides an abstracted `KeyManagerInterface` supporting pluggable backends for development, testing, and production environments.

### Why Pluggable Backends Matter

Production environments require hardware security modules (HSM) or cloud key management services (KMS) for cryptographic operations. The `KeyManagerInterface` provides a unified API that works with:

- **InMemoryKeyManager**: Development and testing
- **AWSKMSKeyManager**: Production AWS deployments (stub for roadmap)

### KeyManagerInterface

All key managers implement this async interface:

```python
from kaizen.trust.key_manager import KeyManagerInterface, KeyMetadata

class KeyManagerInterface(ABC):
    async def generate_keypair(self, key_id: str) -> Tuple[str, str]:
        """Generate Ed25519 keypair. Returns (private_ref, public_key)."""

    async def sign(self, payload: str, key_id: str) -> str:
        """Sign payload with specified key."""

    async def verify(self, payload: str, signature: str, public_key: str) -> bool:
        """Verify signature against payload."""

    async def rotate_key(self, key_id: str) -> Tuple[str, str]:
        """Rotate key, returns new (private_ref, public_key)."""

    async def revoke_key(self, key_id: str) -> None:
        """Revoke key, preventing signing operations."""

    async def get_key_metadata(self, key_id: str) -> Optional[KeyMetadata]:
        """Get key metadata."""

    async def list_keys(self, active_only: bool = True) -> List[KeyMetadata]:
        """List managed keys."""
```

### InMemoryKeyManager

For development and testing:

```python
from kaizen.trust.key_manager import InMemoryKeyManager, KeyMetadata

# Create key manager
key_manager = InMemoryKeyManager()

# Generate a keypair
private_ref, public_key = await key_manager.generate_keypair("agent-001")

# Sign a payload
signature = await key_manager.sign("important data", "agent-001")

# Verify signature
is_valid = await key_manager.verify("important data", signature, public_key)
assert is_valid

# Check key status
metadata = await key_manager.get_key_metadata("agent-001")
print(f"Key active: {metadata.is_active()}")
print(f"Created: {metadata.created_at}")
print(f"Algorithm: {metadata.algorithm}")  # "Ed25519"

# Key rotation (generates new keypair, old key kept for verification grace period)
new_private_ref, new_public_key = await key_manager.rotate_key("agent-001")

# Key revocation (prevents signing, allows verification of historical signatures)
await key_manager.revoke_key("agent-001")
```

### KeyMetadata

Track key lifecycle information:

```python
from kaizen.trust.key_manager import KeyMetadata

@dataclass
class KeyMetadata:
    key_id: str
    algorithm: str = "Ed25519"
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_hardware_backed: bool = False
    hsm_slot: Optional[str] = None
    is_revoked: bool = False
    revoked_at: Optional[datetime] = None
    rotated_from: Optional[str] = None

    def is_active(self) -> bool:
        """Check if key is currently active (not expired and not revoked)."""
```

### Backward Compatibility

The `InMemoryKeyManager` provides helper methods for backward compatibility with `TrustKeyManager`:

```python
# Register an existing private key
key_manager.register_key("legacy-key", private_key_base64)

# Get private key directly
private_key = key_manager.get_key("legacy-key")

# Get public key
public_key = key_manager.get_public_key("agent-001")
```

---

## Linked State Hashing (CARE-006)

Creates tamper-evident hash chains by linking each state hash to its predecessor, enabling detection of tampering or missing entries.

### Why Linked Hashes Matter

Without linked hashing, an attacker could modify historical trust chain states without detection. Linked hashing creates a blockchain-like chain where:

- Any modification to historical entries breaks the chain
- Missing intermediate entries are detectable
- Full chain integrity can be verified in O(n) time

### TrustLineageChain.hash() with Linking

The `TrustLineageChain.hash()` method supports linked hashing:

```python
from kaizen.trust.chain import TrustLineageChain

# Create trust chain for an agent
chain = TrustLineageChain(genesis=genesis_record)

# Original hash (backward compatible, no linking)
original_hash = chain.hash()

# Linked hash (includes previous state)
previous_hash = "abc123..."  # Hash from previous chain state
linked_hash = chain.hash(previous_hash=previous_hash)

# The linked hash is different and includes the previous state
assert linked_hash != original_hash
```

### LinkedHashChain

Maintain a chain of linked hashes across multiple agents:

```python
from kaizen.trust.chain import LinkedHashChain, LinkedHashEntry

# Create a linked hash chain
chain = LinkedHashChain()

# Add hashes for agents (each links to previous)
hash1 = chain.add_hash("agent-001", "state_hash_abc123")
hash2 = chain.add_hash("agent-002", "state_hash_def456")
hash3 = chain.add_hash("agent-003", "state_hash_ghi789")

# Verify chain integrity
valid, break_index = chain.verify_integrity()
assert valid is True
assert break_index is None

# Detect tampering
is_tampered = chain.detect_tampering("agent-002", "wrong_hash")
assert is_tampered is True

# Get specific entry
entry = chain.get_entry("agent-002")
print(f"Hash: {entry.hash}")
print(f"Timestamp: {entry.timestamp}")

# Get previous hash for an entry
prev = chain.get_previous_hash("agent-002")
assert prev == hash1

# Chain length
print(f"Chain has {len(chain)} entries")
```

### Full Verification with Original Hashes

For complete verification, provide the original (unlinked) hashes:

```python
# Store original hashes during creation
original_hashes = ["state_hash_abc123", "state_hash_def456", "state_hash_ghi789"]

# Later, verify with originals
valid, break_index = chain.verify_chain_linkage(original_hashes)
if not valid:
    print(f"Chain broken at index {break_index}")
```

### Serialization

Persist and restore the linked hash chain:

```python
# Serialize to dictionary
chain_data = chain.to_dict()
# {
#   "entries": [...],
#   "version": "1.0",
#   "chain_type": "linked_hash_chain"
# }

# Restore from dictionary
restored = LinkedHashChain.from_dict(chain_data)
```

---

## Revocation Broadcasting (CARE-007)

Implements a pub/sub system for broadcasting revocation events across the trust system. When an agent is revoked, all delegates in the delegation tree receive immediate notification.

### RevocationType and RevocationEvent

```python
from kaizen.trust.revocation.broadcaster import (
    RevocationType,
    RevocationEvent,
)
from datetime import datetime, timezone

# Available revocation types
RevocationType.AGENT_REVOKED          # Agent's trust completely revoked
RevocationType.DELEGATION_REVOKED     # Specific delegation revoked
RevocationType.HUMAN_SESSION_REVOKED  # Human session revoked
RevocationType.KEY_REVOKED            # Cryptographic key revoked
RevocationType.CASCADE_REVOCATION     # Automatic from parent revocation

# Create a revocation event
event = RevocationEvent(
    event_id="rev-001",
    revocation_type=RevocationType.AGENT_REVOKED,
    target_id="agent-001",
    revoked_by="admin",
    reason="Security policy violation",
    affected_agents=["agent-002", "agent-003"],  # Delegates
    timestamp=datetime.now(timezone.utc),
    cascade_from=None,  # Set for CASCADE_REVOCATION
)

# Serialize for storage/transmission
event_dict = event.to_dict()

# Deserialize
restored_event = RevocationEvent.from_dict(event_dict)
```

### InMemoryRevocationBroadcaster

For development and single-process deployments:

```python
from kaizen.trust.revocation.broadcaster import (
    InMemoryRevocationBroadcaster,
    RevocationType,
    RevocationEvent,
)

# Create broadcaster
broadcaster = InMemoryRevocationBroadcaster()

# Subscribe to all revocation events
def on_any_revocation(event: RevocationEvent):
    print(f"Agent {event.target_id} was revoked: {event.reason}")

sub_id = broadcaster.subscribe(on_any_revocation)

# Subscribe to specific event types only
def on_agent_revoked(event: RevocationEvent):
    print(f"Agent revoked: {event.target_id}")

filtered_sub_id = broadcaster.subscribe(
    on_agent_revoked,
    filter_types=[RevocationType.AGENT_REVOKED],
)

# Async callbacks are also supported
async def on_revocation_async(event: RevocationEvent):
    await notify_external_system(event)

async_sub_id = broadcaster.subscribe(on_revocation_async)

# Broadcast an event
event = RevocationEvent(
    event_id="rev-001",
    revocation_type=RevocationType.AGENT_REVOKED,
    target_id="agent-001",
    revoked_by="admin",
    reason="Security violation",
)
broadcaster.broadcast(event)

# Get event history
history = broadcaster.get_history()

# Unsubscribe when done
broadcaster.unsubscribe(sub_id)
```

### CascadeRevocationManager

Automatically revoke all delegates when a parent is revoked:

```python
from kaizen.trust.revocation.broadcaster import (
    InMemoryRevocationBroadcaster,
    InMemoryDelegationRegistry,
    CascadeRevocationManager,
)

# Set up delegation relationships
registry = InMemoryDelegationRegistry()
registry.register_delegation("agent-A", "agent-B")  # A delegated to B
registry.register_delegation("agent-A", "agent-C")  # A delegated to C
registry.register_delegation("agent-B", "agent-D")  # B delegated to D

# Create cascade manager
broadcaster = InMemoryRevocationBroadcaster()
manager = CascadeRevocationManager(broadcaster, registry)

# Revoke agent-A - cascades to B, C, and D
events = manager.cascade_revoke(
    target_id="agent-A",
    revoked_by="admin",
    reason="Security violation",
)

# events contains:
# 1. AGENT_REVOKED for agent-A (with affected_agents: [B, C, D])
# 2. CASCADE_REVOCATION for agent-B (cascade_from: event 1)
# 3. CASCADE_REVOCATION for agent-C (cascade_from: event 1)
# 4. CASCADE_REVOCATION for agent-D (cascade_from: event for B)

print(f"Total revocations: {len(events)}")

# Circular delegation detection prevents infinite loops
# Dead-letter queue tracks failed broadcasts
failed = manager.get_dead_letters()
```

### TrustRevocationList

Real-time tracking of revoked agents for access control:

```python
from kaizen.trust.revocation.broadcaster import (
    InMemoryRevocationBroadcaster,
    TrustRevocationList,
)

broadcaster = InMemoryRevocationBroadcaster()
trl = TrustRevocationList(broadcaster)

# Start listening for revocations
trl.initialize()

# ... after some revocations ...

# Fast lookup for access control
if trl.is_revoked("agent-001"):
    raise PermissionError("Agent is revoked")

# Get the revocation event details
event = trl.get_revocation_event("agent-001")
if event:
    print(f"Revoked at: {event.timestamp}")
    print(f"Reason: {event.reason}")

# Get all revoked agents
all_revoked = trl.get_all_revoked()

# Clean up
trl.close()
```

### Dead-Letter Queue

Failed broadcast attempts are tracked for debugging and retry:

```python
from kaizen.trust.revocation.broadcaster import DeadLetterEntry

# Get failed broadcasts
dead_letters = broadcaster.get_dead_letters()
for entry in dead_letters:
    print(f"Event {entry.event.event_id} failed for {entry.subscription_id}")
    print(f"Error: {entry.error}")
    print(f"Timestamp: {entry.timestamp}")

# Clear after handling
broadcaster.clear_dead_letters()
```

---

## Transactional Re-signing (CARE-008)

Provides atomic re-signing of trust chains during key rotation. Either all chains are re-signed or none are, with automatic rollback on failure.

### Why Atomic Re-signing Matters

During key rotation, all trust chains signed with the old key must be re-signed with the new key. Without transactions:

- Partial failures leave the system in an inconsistent state
- Some chains have old signatures, some have new
- Recovery requires manual intervention

With CARE-008:

- All updates are staged before committing
- On failure, all changes are rolled back
- System remains consistent

### TransactionContext

The `InMemoryTrustStore` provides transaction support:

```python
from kaizen.trust.store import InMemoryTrustStore, TransactionContext

store = InMemoryTrustStore()
await store.initialize()

# Store some initial chains
await store.store_chain(chain1)
await store.store_chain(chain2)
await store.store_chain(chain3)

# Atomic update using transaction context
async with store.transaction() as tx:
    # Queue updates (not applied yet)
    await tx.update_chain("agent-1", updated_chain1)
    await tx.update_chain("agent-2", updated_chain2)
    await tx.update_chain("agent-3", updated_chain3)

    # Check pending count
    print(f"Pending updates: {tx.pending_count}")

    # Commit - applies all updates atomically
    await tx.commit()

# If an exception occurs before commit(), all changes are rolled back
try:
    async with store.transaction() as tx:
        await tx.update_chain("agent-1", bad_chain)
        raise ValueError("Something went wrong")
        await tx.commit()  # Never reached
except ValueError:
    # All changes are automatically rolled back
    # agent-1 still has its original data
    pass
```

### Credential Rotation with Transactional Re-signing

The `CredentialRotationManager` uses transactions for atomic key rotation:

```python
from kaizen.trust.rotation import CredentialRotationManager
from kaizen.trust.operations import TrustKeyManager
from kaizen.trust.authority import OrganizationalAuthorityRegistry
from kaizen.trust.store import InMemoryTrustStore

# Set up components
key_manager = TrustKeyManager()
trust_store = InMemoryTrustStore()
await trust_store.initialize()
authority_registry = OrganizationalAuthorityRegistry()

# Create rotation manager
rotation_mgr = CredentialRotationManager(
    key_manager=key_manager,
    trust_store=trust_store,
    authority_registry=authority_registry,
    rotation_period_days=90,
    grace_period_hours=24,
)
await rotation_mgr.initialize()

# Rotate key - all chains re-signed atomically
result = await rotation_mgr.rotate_key("org-acme")
print(f"Rotation ID: {result.rotation_id}")
print(f"Old key: {result.old_key_id}")
print(f"New key: {result.new_key_id}")
print(f"Chains updated: {result.chains_updated}")
print(f"Grace period ends: {result.grace_period_end}")

# Check rotation status
status = await rotation_mgr.get_rotation_status("org-acme")
print(f"Current key: {status.current_key_id}")
print(f"Status: {status.status}")  # COMPLETED, GRACE_PERIOD, etc.
print(f"Grace period keys: {status.grace_period_keys}")
```

### Batch Processing with Pagination

For large numbers of chains, re-signing uses pagination:

```python
# The _resign_chains method handles pagination internally
# Default batch_size is 100 chains per batch
chains_updated = await rotation_mgr._resign_chains(
    authority_id="org-acme",
    old_key_id="old-key",
    new_key_id="new-key",
    batch_size=50,  # Process 50 chains at a time
)
```

### Rollback on Failure

If any chain fails to re-sign, the entire batch is rolled back:

```python
from kaizen.trust.rotation import RotationError

try:
    result = await rotation_mgr.rotate_key("org-acme")
except RotationError as e:
    print(f"Rotation failed: {e.message}")
    print(f"Authority: {e.authority_id}")
    print(f"Reason: {e.reason}")
    # All chains remain with their original signatures
```

---

## Constraint Inheritance Validation (CARE-009)

Ensures delegations can only TIGHTEN constraints, never loosen them. This prevents widening attacks where a delegatee attempts to gain more permissions than their delegator.

### The Tightening-Only Rule

A fundamental security property of EATP: trust can only be reduced as it flows through the delegation chain.

**Allowed (tightening):**

- Reduce cost limits: parent=10000, child=5000
- Narrow time windows: parent="09:00-17:00", child="10:00-16:00"
- Restrict resources: parent="invoices/_", child="invoices/small/_"
- Add forbidden actions: parent forbids X, child also forbids X

**Blocked (widening):**

- Increase cost limits: parent=1000, child=10000
- Expand time windows: parent="10:00-16:00", child="09:00-17:00"
- Expand resources: parent="invoices/small/_", child="invoices/_"
- Remove forbidden actions: parent forbids X, child doesn't

### validate_inheritance()

```python
from kaizen.trust.constraint_validator import (
    ConstraintValidator,
    ValidationResult,
    ConstraintViolation,
)

validator = ConstraintValidator()

# Valid: child tightens constraints
result = validator.validate_inheritance(
    parent_constraints={
        "cost_limit": 10000,
        "rate_limit": 100,
        "allowed_actions": ["read", "write", "delete"],
        "time_window": "09:00-17:00",
    },
    child_constraints={
        "cost_limit": 5000,        # Lower = tighter
        "rate_limit": 50,          # Lower = tighter
        "allowed_actions": ["read", "write"],  # Fewer = tighter
        "time_window": "10:00-16:00",  # Narrower = tighter
    },
)
assert result.valid is True
assert len(result.violations) == 0

# Invalid: child widens constraints
result = validator.validate_inheritance(
    parent_constraints={"cost_limit": 1000},
    child_constraints={"cost_limit": 10000},  # WIDENING!
)
assert result.valid is False
assert ConstraintViolation.COST_LOOSENED in result.violations
print(f"Details: {result.details}")  # {"cost_limit": "Child 10000 > Parent 1000"}
```

### What Gets Validated

The `validate_inheritance()` method checks all constraint types:

```python
# Numeric limits (child must be <= parent)
validated_fields = [
    "cost_limit",
    "rate_limit",
    "budget_limit",
    "max_delegation_depth",
    "max_api_calls",
]

# Set-based constraints (child must be subset of parent)
validated_sets = [
    "allowed_actions",    # Actions child can perform
    "data_scopes",        # Data child can access
    "communication_targets",  # Agents child can communicate with
    "geo_restrictions",   # Geographic regions allowed
    "resources",          # Resource patterns (glob matching)
]

# Preserved restrictions (child must keep parent's restrictions)
preserved = [
    "forbidden_actions",  # Actions child cannot perform
]

# Window constraints (child must be within parent)
window_fields = [
    "time_window",  # Format: "HH:MM-HH:MM"
]
```

### Violation Types

```python
from kaizen.trust.constraint_validator import ConstraintViolation

# All possible violations
ConstraintViolation.COST_LOOSENED
ConstraintViolation.RATE_LIMIT_INCREASED
ConstraintViolation.BUDGET_LIMIT_INCREASED
ConstraintViolation.MAX_DELEGATION_DEPTH_INCREASED
ConstraintViolation.MAX_API_CALLS_INCREASED
ConstraintViolation.TIME_WINDOW_EXPANDED
ConstraintViolation.RESOURCES_EXPANDED
ConstraintViolation.ACTION_RESTRICTION_REMOVED
ConstraintViolation.FORBIDDEN_ACTION_REMOVED
ConstraintViolation.DATA_SCOPE_EXPANDED
ConstraintViolation.COMMUNICATION_TARGETS_EXPANDED
ConstraintViolation.GEO_RESTRICTION_REMOVED
ConstraintViolation.NESTED_CONSTRAINT_WIDENED
```

### Nested Constraint Validation

Deep constraints are validated recursively:

```python
result = validator.validate_inheritance(
    parent_constraints={
        "api_limits": {
            "max_calls": 100,
            "per_endpoint": {"users": 50, "orders": 30},
        }
    },
    child_constraints={
        "api_limits": {
            "max_calls": 150,  # WIDENING!
            "per_endpoint": {"users": 60},  # WIDENING!
        }
    },
)
assert result.valid is False
assert ConstraintViolation.NESTED_CONSTRAINT_WIDENED in result.violations
```

### Integration with Delegation

Constraint validation is automatically called during delegation (step 4c):

```python
from kaizen.trust.constraint_validator import DelegationConstraintValidator

delegate_validator = DelegationConstraintValidator()

# Quick check if delegation is valid
can_delegate = delegate_validator.can_delegate(
    delegator_constraints={"cost_limit": 1000},
    delegatee_constraints={"cost_limit": 500},
)
assert can_delegate is True

# Get maximum allowed constraints for a delegatee
max_constraints = delegate_validator.get_max_allowed_constraints(
    {"cost_limit": 1000, "rate_limit": 100}
)
# Returns: {"cost_limit": 1000, "rate_limit": 100}
# Delegatee can only have <= these values
```

---

## Append-Only Audit Store (CARE-010)

Provides immutable audit trail storage with linked hashing for tamper detection. UPDATE and DELETE operations are blocked at the application level.

### Why Immutability Matters

Audit trails must be tamper-evident for:

- Regulatory compliance (SOC2, HIPAA, etc.)
- Forensic analysis after security incidents
- Legal evidence of agent actions
- Trust verification ("who authorized this action?")

### AppendOnlyAuditStore

```python
from kaizen.trust.audit_store import (
    AppendOnlyAuditStore,
    AuditRecord,
    AuditStoreImmutabilityError,
    IntegrityVerificationResult,
)
from kaizen.trust.chain import AuditAnchor, ActionResult
from datetime import datetime, timezone

# Create store
store = AppendOnlyAuditStore()

# Append audit anchors (the ONLY write operation allowed)
anchor = AuditAnchor(
    id="aud-001",
    agent_id="agent-001",
    action="analyze_financial_data",
    timestamp=datetime.now(timezone.utc),
    trust_chain_hash="abc123...",
    result=ActionResult.SUCCESS,
    signature="sig...",
    resource="invoices/2024",
    context={"department": "finance"},
)

record = await store.append(anchor)
print(f"Record ID: {record.record_id}")
print(f"Sequence: {record.sequence_number}")
print(f"Integrity hash: {record.integrity_hash}")
print(f"Previous hash: {record.previous_hash}")  # Links to prior record
```

### AuditRecord

Each stored anchor is wrapped in an `AuditRecord` with additional metadata:

```python
from kaizen.trust.audit_store import AuditRecord

@dataclass
class AuditRecord:
    anchor: AuditAnchor
    record_id: str           # Auto-generated UUID
    stored_at: datetime      # When stored
    integrity_hash: str      # SHA-256 of anchor content
    previous_hash: str       # Hash of previous record (linked chain)
    sequence_number: int     # Monotonically increasing

    def verify_integrity(self) -> bool:
        """Verify integrity hash matches content."""
```

### Blocked Operations

UPDATE and DELETE are explicitly blocked:

```python
from kaizen.trust.audit_store import AuditStoreImmutabilityError

try:
    await store.update(record_id, new_data)
except AuditStoreImmutabilityError as e:
    print(f"Blocked: {e.operation}")  # "update"

try:
    await store.delete(record_id)
except AuditStoreImmutabilityError as e:
    print(f"Blocked: {e.operation}")  # "delete"
```

### Integrity Verification

Verify the entire audit chain for tampering:

```python
result = await store.verify_integrity()

print(f"Valid: {result.valid}")
print(f"Total records: {result.total_records}")
print(f"Verified: {result.verified_records}")

if not result.valid:
    print(f"First invalid at sequence: {result.first_invalid_sequence}")
    for error in result.errors:
        print(f"Error: {error}")
```

Verification checks:

1. Sequence numbers are monotonically increasing with no gaps
2. Linked hashes form a valid chain
3. Each record's integrity hash matches its content

### Querying Records

```python
# Get by record ID
record = await store.get("record-uuid")

# Get by anchor ID
record = await store.get_by_anchor_id("aud-001")

# Get by sequence number
record = await store.get_by_sequence(5)

# List with filtering
records = await store.list_records(
    agent_id="agent-001",
    action="analyze_financial_data",
    limit=100,
    offset=0,
)

# Verify single record
is_valid = await store.verify_record("record-uuid")

# Store statistics
print(f"Record count: {store.count}")
print(f"Last sequence: {store.last_sequence}")
```

### PostgreSQL Trigger for Database-Level Enforcement

For additional security, apply this trigger to your PostgreSQL audit table:

```python
sql = AppendOnlyAuditStore.get_postgres_trigger_sql("my_audit_table")
# Execute this SQL against your database
```

The trigger prevents UPDATE and DELETE at the database level:

```sql
-- CARE-010: Append-Only Audit Trigger
CREATE OR REPLACE FUNCTION prevent_audit_modification()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' OR TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Audit trail is append-only: % not allowed on %',
            TG_OP, TG_TABLE_NAME;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_append_only ON my_audit_table;
CREATE TRIGGER audit_append_only
BEFORE UPDATE OR DELETE ON my_audit_table
FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();
```

---

## Integration Example

This example demonstrates using multiple Phase 5 P1 features together:

```python
import asyncio
from datetime import datetime, timezone, timedelta
from kaizen.trust.key_manager import InMemoryKeyManager
from kaizen.trust.store import InMemoryTrustStore
from kaizen.trust.chain import (
    TrustLineageChain,
    GenesisRecord,
    AuthorityType,
    LinkedHashChain,
    AuditAnchor,
    ActionResult,
)
from kaizen.trust.revocation.broadcaster import (
    InMemoryRevocationBroadcaster,
    InMemoryDelegationRegistry,
    CascadeRevocationManager,
    TrustRevocationList,
    RevocationType,
)
from kaizen.trust.constraint_validator import ConstraintValidator
from kaizen.trust.audit_store import AppendOnlyAuditStore


async def production_readiness_demo():
    # 1. Initialize key manager
    key_manager = InMemoryKeyManager()
    authority_private, authority_public = await key_manager.generate_keypair("org-acme")
    agent_private, agent_public = await key_manager.generate_keypair("agent-001")

    # 2. Create trust chain with linked hashing
    genesis = GenesisRecord(
        id="gen-001",
        agent_id="agent-001",
        authority_id="org-acme",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime.now(timezone.utc),
        signature=await key_manager.sign("genesis payload", "org-acme"),
    )

    chain = TrustLineageChain(genesis=genesis)

    # Initialize linked hash chain
    hash_chain = LinkedHashChain()
    linked_hash = hash_chain.add_hash("agent-001", chain.hash())
    print(f"Initial linked hash: {linked_hash[:32]}...")

    # 3. Set up revocation broadcasting
    broadcaster = InMemoryRevocationBroadcaster()
    delegation_registry = InMemoryDelegationRegistry()
    cascade_manager = CascadeRevocationManager(broadcaster, delegation_registry)
    revocation_list = TrustRevocationList(broadcaster)
    revocation_list.initialize()

    # Register delegations
    delegation_registry.register_delegation("agent-001", "agent-002")
    delegation_registry.register_delegation("agent-002", "agent-003")

    # 4. Validate constraint inheritance before delegation
    validator = ConstraintValidator()
    parent_constraints = {
        "cost_limit": 10000,
        "rate_limit": 100,
        "allowed_actions": ["read", "write"],
        "time_window": "09:00-17:00",
    }
    child_constraints = {
        "cost_limit": 5000,
        "rate_limit": 50,
        "allowed_actions": ["read"],
        "time_window": "10:00-16:00",
    }

    validation = validator.validate_inheritance(parent_constraints, child_constraints)
    if validation.valid:
        print("Delegation constraints are valid (properly tightened)")
    else:
        print(f"Delegation blocked: {validation.violations}")

    # 5. Store trust chain with transaction support
    store = InMemoryTrustStore()
    await store.initialize()
    await store.store_chain(chain)

    # 6. Record actions in append-only audit store
    audit_store = AppendOnlyAuditStore()

    anchor = AuditAnchor(
        id="aud-001",
        agent_id="agent-001",
        action="process_invoice",
        timestamp=datetime.now(timezone.utc),
        trust_chain_hash=chain.hash(),
        result=ActionResult.SUCCESS,
        signature=await key_manager.sign("audit payload", "agent-001"),
        resource="invoices/inv-12345",
    )

    record = await audit_store.append(anchor)
    print(f"Audit record stored: sequence={record.sequence_number}")

    # 7. Simulate key rotation with transactional re-signing
    async with store.transaction() as tx:
        # Re-sign chain with new key
        new_private, new_public = await key_manager.rotate_key("org-acme")
        genesis.signature = await key_manager.sign("genesis payload", "org-acme")
        await tx.update_chain("agent-001", chain)
        await tx.commit()
        print("Key rotated and chains re-signed atomically")

    # Update linked hash after rotation
    new_linked_hash = hash_chain.add_hash("agent-001", chain.hash())
    print(f"Updated linked hash: {new_linked_hash[:32]}...")

    # 8. Verify audit integrity
    integrity = await audit_store.verify_integrity()
    print(f"Audit integrity valid: {integrity.valid}")
    print(f"Records verified: {integrity.verified_records}/{integrity.total_records}")

    # 9. Demonstrate cascade revocation
    if False:  # Uncomment to see cascade revocation in action
        events = cascade_manager.cascade_revoke(
            target_id="agent-001",
            revoked_by="admin",
            reason="Security policy update",
        )
        print(f"Cascade revocation: {len(events)} agents revoked")

        # Check revocation status
        print(f"agent-001 revoked: {revocation_list.is_revoked('agent-001')}")
        print(f"agent-002 revoked: {revocation_list.is_revoked('agent-002')}")
        print(f"agent-003 revoked: {revocation_list.is_revoked('agent-003')}")

    # Cleanup
    revocation_list.close()
    await store.close()

    print("\nPhase 5 P1 Production Readiness Demo Complete!")


if __name__ == "__main__":
    asyncio.run(production_readiness_demo())
```

---

## API Reference

### Quick Import Reference

| Component                       | Import Path                           |
| ------------------------------- | ------------------------------------- |
| `KeyManagerInterface`           | `kaizen.trust.key_manager`            |
| `InMemoryKeyManager`            | `kaizen.trust.key_manager`            |
| `AWSKMSKeyManager`              | `kaizen.trust.key_manager`            |
| `KeyMetadata`                   | `kaizen.trust.key_manager`            |
| `KeyManagerError`               | `kaizen.trust.key_manager`            |
| `LinkedHashChain`               | `kaizen.trust.chain`                  |
| `LinkedHashEntry`               | `kaizen.trust.chain`                  |
| `TrustLineageChain.hash()`      | `kaizen.trust.chain`                  |
| `RevocationType`                | `kaizen.trust.revocation.broadcaster` |
| `RevocationEvent`               | `kaizen.trust.revocation.broadcaster` |
| `RevocationBroadcaster`         | `kaizen.trust.revocation.broadcaster` |
| `InMemoryRevocationBroadcaster` | `kaizen.trust.revocation.broadcaster` |
| `InMemoryDelegationRegistry`    | `kaizen.trust.revocation.broadcaster` |
| `CascadeRevocationManager`      | `kaizen.trust.revocation.broadcaster` |
| `TrustRevocationList`           | `kaizen.trust.revocation.broadcaster` |
| `DeadLetterEntry`               | `kaizen.trust.revocation.broadcaster` |
| `TransactionContext`            | `kaizen.trust.store`                  |
| `InMemoryTrustStore`            | `kaizen.trust.store`                  |
| `PostgresTrustStore`            | `kaizen.trust.store`                  |
| `CredentialRotationManager`     | `kaizen.trust.rotation`               |
| `RotationResult`                | `kaizen.trust.rotation`               |
| `RotationStatusInfo`            | `kaizen.trust.rotation`               |
| `RotationError`                 | `kaizen.trust.rotation`               |
| `ConstraintValidator`           | `kaizen.trust.constraint_validator`   |
| `DelegationConstraintValidator` | `kaizen.trust.constraint_validator`   |
| `ValidationResult`              | `kaizen.trust.constraint_validator`   |
| `ConstraintViolation`           | `kaizen.trust.constraint_validator`   |
| `AppendOnlyAuditStore`          | `kaizen.trust.audit_store`            |
| `AuditRecord`                   | `kaizen.trust.audit_store`            |
| `IntegrityVerificationResult`   | `kaizen.trust.audit_store`            |
| `AuditStoreImmutabilityError`   | `kaizen.trust.audit_store`            |
| `PostgresAuditStore`            | `kaizen.trust.audit_store`            |

---

## See Also

- [EATP Architecture](../architecture/eatp-architecture.md) - Full EATP protocol specification
- [Trust System Overview](../trust/README.md) - Trust module documentation
- [Security Best Practices](../guides/eatp-security-best-practices.md) - Security recommendations
- [Migration Guide](../guides/eatp-migration-guide.md) - Upgrading to EATP
