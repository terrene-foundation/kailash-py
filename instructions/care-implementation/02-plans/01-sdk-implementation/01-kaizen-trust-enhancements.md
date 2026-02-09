# Kaizen Trust Module Enhancements Plan

## Overview

This document details the implementation plan for P0/P1/P2 fixes to the Kaizen trust module, addressing critical security vulnerabilities, production readiness requirements, and enterprise features for the CARE/EATP trust framework.

**Target Module**: `apps/kailash-kaizen/src/kaizen/trust/`
**Priority Levels**: P0 (Critical Security), P1 (Production Readiness), P2 (Enterprise Features)

---

## P0 Critical Fixes (Immediate - Security Vulnerabilities)

### P0-1: Fix Static Salt in Key Derivation

**Current Issue**: Two related salt vulnerabilities exist:

1. `security.py:427` uses a hardcoded static salt `b"kaizen-trust-security-salt"` in PBKDF2 key derivation
2. `crypto.py:30-58` `generate_keypair()` uses `SigningKey.generate()` without any salt-based derivation

**Files**:

- `apps/kailash-kaizen/src/kaizen/trust/security.py` (static salt — CRIT-001)
- `apps/kailash-kaizen/src/kaizen/trust/crypto.py` (no salt in key generation)

**Current Code Analysis**:

```python
# security.py:427 - Static salt in PBKDF2:
salt = b"kaizen-trust-security-salt"  # VULNERABILITY: Same across all deployments

# crypto.py:30-58 - generate_keypair() uses SigningKey.generate() without salt
# hash_trust_chain_state() does not include salt
```

**Required Changes**:

1. Add salt generation and storage functions:

```python
# New file: apps/kailash-kaizen/src/kaizen/trust/crypto.py
# Add after line 28

import os
import secrets
from typing import Optional

# Salt length for key derivation (RFC 8018 recommends at least 8 bytes)
SALT_LENGTH = 32  # 256 bits for high security

def generate_salt() -> bytes:
    """
    Generate a cryptographically secure random salt.

    Returns:
        32 bytes of random data for use as salt

    Security:
        Uses secrets.token_bytes() which is suitable for cryptographic use.
    """
    return secrets.token_bytes(SALT_LENGTH)


def derive_key_with_salt(
    master_key: bytes,
    salt: bytes,
    key_length: int = 32,
    iterations: int = 100000,
) -> Tuple[bytes, bytes]:
    """
    Derive a key from master key using PBKDF2-HMAC-SHA256.

    Args:
        master_key: The master key material
        salt: Random salt (should be generated per-key)
        key_length: Length of derived key in bytes
        iterations: PBKDF2 iteration count

    Returns:
        Tuple of (derived_key, salt_used)

    Security:
        - Uses per-key random salt
        - 100k iterations provides ~50ms derivation time
        - Salt is stored alongside derived key for verification
    """
    import hashlib

    derived = hashlib.pbkdf2_hmac(
        'sha256',
        master_key,
        salt,
        iterations,
        dklen=key_length
    )
    return derived, salt


def hash_trust_chain_state_with_salt(
    genesis_id: str,
    capability_ids: list,
    delegation_ids: list,
    constraint_hash: str,
    previous_state_hash: Optional[str] = None,
    salt: Optional[bytes] = None,
) -> Tuple[str, str]:
    """
    Compute salted hash of current trust chain state.

    Args:
        genesis_id: ID of the genesis record
        capability_ids: List of capability attestation IDs
        delegation_ids: List of delegation record IDs
        constraint_hash: Hash of constraint envelope
        previous_state_hash: Hash of previous state (for linked hashing)
        salt: Optional salt (generated if not provided)

    Returns:
        Tuple of (hash_hex, salt_base64)

    Security:
        - Per-computation random salt prevents rainbow table attacks
        - Linked hashing enables tamper detection
    """
    if salt is None:
        salt = generate_salt()

    state = {
        "genesis_id": genesis_id,
        "capability_ids": sorted(capability_ids),
        "delegation_ids": sorted(delegation_ids),
        "constraint_hash": constraint_hash,
        "previous_state_hash": previous_state_hash,
        "salt": base64.b64encode(salt).decode("utf-8"),
    }

    hash_result = hash_chain(state)
    return hash_result, base64.b64encode(salt).decode("utf-8")
```

2. Update `TrustLineageChain.hash()` to use salted hashing:

```python
# File: apps/kailash-kaizen/src/kaizen/trust/chain.py
# Update the hash() method in TrustLineageChain class (line 540-556)

def hash(self, previous_hash: Optional[str] = None) -> str:
    """
    Compute hash of current trust state with linked hashing.

    Args:
        previous_hash: Hash of previous state for chain linking

    Returns:
        Hex-encoded hash with linked state
    """
    from kaizen.trust.crypto import hash_trust_chain_state_with_salt

    hash_result, salt = hash_trust_chain_state_with_salt(
        genesis_id=self.genesis.id,
        capability_ids=[c.id for c in self.capabilities],
        delegation_ids=[d.id for d in self.delegations],
        constraint_hash=(
            self.constraint_envelope.constraint_hash
            if self.constraint_envelope
            else ""
        ),
        previous_state_hash=previous_hash,
    )
    # Store salt in chain metadata for verification
    if hasattr(self, '_last_hash_salt'):
        self._last_hash_salt = salt
    return hash_result
```

**Testing Requirements**:

```python
# File: tests/unit/trust/test_crypto_salt.py

import pytest
from kaizen.trust.crypto import (
    generate_salt,
    derive_key_with_salt,
    hash_trust_chain_state_with_salt,
)

def test_salt_uniqueness():
    """Each salt generation must be unique."""
    salts = [generate_salt() for _ in range(1000)]
    assert len(set(salts)) == 1000, "Salt collision detected"

def test_derived_keys_differ_with_different_salts():
    """Same master key with different salts produces different keys."""
    master = b"test_master_key"
    salt1 = generate_salt()
    salt2 = generate_salt()

    key1, _ = derive_key_with_salt(master, salt1)
    key2, _ = derive_key_with_salt(master, salt2)

    assert key1 != key2

def test_hash_reproducible_with_same_salt():
    """Same inputs with same salt produce same hash."""
    salt = generate_salt()
    hash1, _ = hash_trust_chain_state_with_salt(
        "gen-1", ["cap-1"], ["del-1"], "abc", salt=salt
    )
    hash2, _ = hash_trust_chain_state_with_salt(
        "gen-1", ["cap-1"], ["del-1"], "abc", salt=salt
    )
    assert hash1 == hash2
```

**Migration Plan**:

- Add salt field to stored trust chains
- Existing chains without salt treated as legacy (warning logged)
- New chains require salt
- Migration script to re-hash existing chains with salt

---

### P0-2: Enable Delegation Signature Verification

**Current Issue**: Delegation signature verification is skipped in `operations.py` lines 832-854.

**File**: `apps/kailash-kaizen/src/kaizen/trust/operations.py`

**Current Code** (lines 832-854):

```python
# Verify delegation signatures (if any)
for delegation in chain.delegations:
    # For delegations, we need the delegator's public key
    # This requires looking up the delegator's chain
    try:
        delegator_chain = await self.trust_store.get_chain(
            delegation.delegator_id
        )
        # Use authority's key for now (simplified - production would use agent keys)
        del_payload = serialize_for_signing(delegation.to_signing_payload())
        # Note: In production, each agent would have their own key
        # For Phase 1, we skip delegation signature verification
    except TrustChainNotFoundError:
        return VerificationResult(
            valid=False,
            reason=f"Delegator chain not found: {delegation.delegator_id}",
            level=VerificationLevel.FULL,
        )
```

**Required Changes**:

```python
# File: apps/kailash-kaizen/src/kaizen/trust/operations.py
# Replace lines 832-854 with:

async def _verify_delegation_signature(
    self,
    delegation: DelegationRecord,
    delegator_chain: TrustLineageChain,
) -> VerificationResult:
    """
    Verify a single delegation signature.

    Args:
        delegation: The delegation record to verify
        delegator_chain: The delegator's trust chain

    Returns:
        VerificationResult indicating if signature is valid
    """
    # Get the authority that established the delegator
    authority = await self.authority_registry.get_authority(
        delegator_chain.genesis.authority_id,
        include_inactive=True,  # Allow historical verification
    )

    # Build signing payload
    del_payload = serialize_for_signing(delegation.to_signing_payload())

    # Verify signature using authority's key
    # In production with agent keys, would use delegator's key instead
    if not await self.key_manager.verify(
        del_payload,
        delegation.signature,
        authority.public_key,
    ):
        return VerificationResult(
            valid=False,
            reason=f"Invalid delegation signature: {delegation.id}",
            level=VerificationLevel.FULL,
        )

    return VerificationResult(valid=True, level=VerificationLevel.FULL)


# Update _verify_signatures method:
async def _verify_signatures(
    self,
    chain: TrustLineageChain,
) -> VerificationResult:
    """
    Verify all signatures in a trust chain.

    Args:
        chain: Trust chain to verify

    Returns:
        VerificationResult
    """
    # ... existing genesis and capability verification ...

    # Verify delegation signatures (ENABLED)
    for delegation in chain.delegations:
        try:
            delegator_chain = await self.trust_store.get_chain(
                delegation.delegator_id
            )

            result = await self._verify_delegation_signature(
                delegation, delegator_chain
            )

            if not result.valid:
                return result

        except TrustChainNotFoundError:
            return VerificationResult(
                valid=False,
                reason=f"Delegator chain not found: {delegation.delegator_id}",
                level=VerificationLevel.FULL,
            )

    return VerificationResult(
        valid=True,
        level=VerificationLevel.FULL,
    )
```

**Testing Requirements**:

```python
# File: tests/unit/trust/test_delegation_signatures.py

import pytest
from kaizen.trust.crypto import generate_keypair, sign

@pytest.mark.asyncio
async def test_delegation_signature_verified(trust_ops_fixture):
    """Delegation signatures must be cryptographically verified."""
    # Create delegator with valid signature
    delegator = await trust_ops_fixture.establish(...)

    # Delegate with valid signature
    delegation = await trust_ops_fixture.delegate(...)

    # Verify should pass
    result = await trust_ops_fixture.verify(
        agent_id=delegation.delegatee_id,
        action="test_action",
        level=VerificationLevel.FULL,
    )
    assert result.valid

@pytest.mark.asyncio
async def test_tampered_delegation_rejected(trust_ops_fixture):
    """Tampered delegation signatures must be rejected."""
    delegation = await trust_ops_fixture.delegate(...)

    # Tamper with the delegation
    chain = await trust_ops_fixture.trust_store.get_chain(delegation.delegatee_id)
    chain.delegations[0].signature = "tampered_signature"
    await trust_ops_fixture.trust_store.update_chain(chain)

    # Verify should fail
    result = await trust_ops_fixture.verify(
        agent_id=delegation.delegatee_id,
        action="test_action",
        level=VerificationLevel.FULL,
    )
    assert not result.valid
    assert "Invalid delegation signature" in result.reason
```

---

### P0-3: Add Cycle Detection to Delegation Chain

**Current Issue**: The `get_delegation_chain()` method in `chain.py` (lines 660-691) does not detect cycles, which could lead to infinite loops.

**File**: `apps/kailash-kaizen/src/kaizen/trust/chain.py`

**Required Changes**:

```python
# File: apps/kailash-kaizen/src/kaizen/trust/chain.py
# Add new exception class after line 11

class DelegationCycleError(Exception):
    """Raised when a cycle is detected in the delegation chain."""

    def __init__(self, cycle_path: List[str]):
        self.cycle_path = cycle_path
        super().__init__(
            f"Delegation cycle detected: {' -> '.join(cycle_path)}"
        )


# Replace get_delegation_chain() method (lines 660-691):

def get_delegation_chain(self, max_depth: int = 100) -> List[DelegationRecord]:
    """
    Get delegation chain in order from root to leaf.

    Follows parent_delegation_id links to build ordered chain.
    Includes cycle detection to prevent infinite loops.

    Args:
        max_depth: Maximum chain depth allowed (default: 100)

    Returns:
        Ordered list of delegation records from root to leaf

    Raises:
        DelegationCycleError: If a cycle is detected in the chain
        ValueError: If chain exceeds max_depth
    """
    if not self.delegations:
        return []

    # Build delegation map
    delegation_map = {d.id: d for d in self.delegations}

    # Find leaf delegations (no other delegation references them as parent)
    parent_ids = {
        d.parent_delegation_id for d in self.delegations if d.parent_delegation_id
    }
    leaves = [d for d in self.delegations if d.id not in parent_ids]

    if not leaves:
        return list(self.delegations)

    # Build chain from most recent leaf with cycle detection
    chain = []
    visited: Set[str] = set()
    current = leaves[0]

    while current:
        # Cycle detection
        if current.id in visited:
            cycle_path = [d.id for d in chain] + [current.id]
            raise DelegationCycleError(cycle_path)

        # Depth limit check
        if len(chain) >= max_depth:
            raise ValueError(
                f"Delegation chain exceeds maximum depth of {max_depth}"
            )

        visited.add(current.id)
        chain.append(current)

        if current.parent_delegation_id:
            current = delegation_map.get(current.parent_delegation_id)
        else:
            current = None

    return list(reversed(chain))
```

**Testing Requirements**:

```python
# File: tests/unit/trust/test_delegation_cycles.py

import pytest
from kaizen.trust.chain import TrustLineageChain, DelegationCycleError

def test_cycle_detection_raises_error():
    """Delegation cycles must raise DelegationCycleError."""
    # Create chain with circular delegation
    chain = create_chain_with_cycle()

    with pytest.raises(DelegationCycleError) as exc:
        chain.get_delegation_chain()

    assert len(exc.value.cycle_path) > 0

def test_max_depth_enforced():
    """Chain depth limits must be enforced."""
    chain = create_deep_chain(depth=150)

    with pytest.raises(ValueError) as exc:
        chain.get_delegation_chain(max_depth=100)

    assert "exceeds maximum depth" in str(exc.value)
```

---

### P0-4: Add Maximum Delegation Depth Enforcement

**Current Issue**: No maximum delegation depth is enforced, allowing unbounded delegation chains.

**Files to Modify**:

- `apps/kailash-kaizen/src/kaizen/trust/operations.py`
- `apps/kailash-kaizen/src/kaizen/trust/chain.py`

**Required Changes**:

```python
# File: apps/kailash-kaizen/src/kaizen/trust/operations.py
# Add constant after imports (around line 68)

# Maximum allowed delegation depth from human origin
MAX_DELEGATION_DEPTH = 10

# Add to TrustOperations.__init__:
def __init__(
    self,
    authority_registry: OrganizationalAuthorityRegistry,
    key_manager: TrustKeyManager,
    trust_store: PostgresTrustStore,
    max_delegation_depth: int = MAX_DELEGATION_DEPTH,
):
    # ... existing code ...
    self.max_delegation_depth = max_delegation_depth


# Update delegate() method (around line 937):
async def delegate(
    self,
    delegator_id: str,
    delegatee_id: str,
    task_id: str,
    capabilities: List[str],
    additional_constraints: Optional[List[str]] = None,
    expires_at: Optional[datetime] = None,
    metadata: Optional[Dict[str, Any]] = None,
    context: Optional[ExecutionContext] = None,
) -> DelegationRecord:
    """DELEGATE: Transfer trust from one agent to another."""
    # ... existing validation ...

    # Check delegation depth limit
    if ctx:
        new_depth = ctx.delegation_depth + 1
        if new_depth > self.max_delegation_depth:
            raise DelegationError(
                f"Delegation depth {new_depth} exceeds maximum allowed "
                f"({self.max_delegation_depth}). Cannot delegate from "
                f"{delegator_id} to {delegatee_id}.",
                delegator_id=delegator_id,
                delegatee_id=delegatee_id,
            )

    # ... rest of method ...
```

**Add DelegationDepthConfig dataclass**:

```python
# File: apps/kailash-kaizen/src/kaizen/trust/chain.py
# Add after DelegationRecord class

@dataclass
class DelegationLimits:
    """
    Configuration for delegation chain limits.

    Attributes:
        max_depth: Maximum delegation chain depth from human origin
        max_chain_length: Maximum number of delegations in a chain
        require_expiry: Whether delegations must have expiry
        default_expiry_hours: Default expiry for delegations without explicit expiry
    """
    max_depth: int = 10
    max_chain_length: int = 50
    require_expiry: bool = True
    default_expiry_hours: int = 24
```

**Testing Requirements**:

```python
# File: tests/unit/trust/test_delegation_depth.py

import pytest
from kaizen.trust.operations import TrustOperations, MAX_DELEGATION_DEPTH
from kaizen.trust.exceptions import DelegationError

@pytest.mark.asyncio
async def test_delegation_depth_limit_enforced(trust_ops_fixture):
    """Delegation depth must be enforced."""
    # Create a chain at max depth
    ctx = create_context_at_depth(MAX_DELEGATION_DEPTH)

    # Attempting to delegate should fail
    with pytest.raises(DelegationError) as exc:
        await trust_ops_fixture.delegate(
            delegator_id="agent-at-max-depth",
            delegatee_id="new-agent",
            task_id="task-1",
            capabilities=["read"],
            context=ctx,
        )

    assert "exceeds maximum allowed" in str(exc.value)

@pytest.mark.asyncio
async def test_configurable_depth_limit(trust_ops_fixture_custom_depth):
    """Depth limit should be configurable."""
    # Configure with lower limit
    trust_ops = TrustOperations(
        ...,
        max_delegation_depth=5,
    )

    ctx = create_context_at_depth(5)

    with pytest.raises(DelegationError):
        await trust_ops.delegate(...)
```

---

## P1 Production Readiness

### P1-1: HSM/KMS Integration for Genesis Keys

**File**: `apps/kailash-kaizen/src/kaizen/trust/operations.py`

**Add KeyManagerInterface abstraction**:

```python
# File: apps/kailash-kaizen/src/kaizen/trust/key_manager.py (NEW)

from abc import ABC, abstractmethod
from typing import Optional, Tuple
from dataclasses import dataclass

@dataclass
class KeyMetadata:
    """Metadata about a managed key."""
    key_id: str
    algorithm: str = "Ed25519"
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_hardware_backed: bool = False
    hsm_slot: Optional[str] = None


class KeyManagerInterface(ABC):
    """
    Abstract interface for cryptographic key management.

    Implementations:
    - InMemoryKeyManager: Development/testing
    - AWSKMSKeyManager: AWS Key Management Service
    - AzureKeyVaultManager: Azure Key Vault
    - HSMKeyManager: Hardware Security Module (PKCS#11)
    """

    @abstractmethod
    async def generate_keypair(self, key_id: str) -> Tuple[str, str]:
        """
        Generate a new keypair.

        Args:
            key_id: Unique identifier for the key

        Returns:
            Tuple of (private_key_ref, public_key)

        Note:
            private_key_ref may be a reference (HSM/KMS) or actual key (in-memory)
        """
        pass

    @abstractmethod
    async def sign(self, payload: str, key_id: str) -> str:
        """Sign payload with specified key."""
        pass

    @abstractmethod
    async def verify(
        self, payload: str, signature: str, public_key: str
    ) -> bool:
        """Verify signature."""
        pass

    @abstractmethod
    async def rotate_key(self, key_id: str) -> Tuple[str, str]:
        """Rotate a key, returning new key info."""
        pass

    @abstractmethod
    async def revoke_key(self, key_id: str) -> None:
        """Revoke/delete a key."""
        pass

    @abstractmethod
    async def get_key_metadata(self, key_id: str) -> Optional[KeyMetadata]:
        """Get metadata about a key."""
        pass


class InMemoryKeyManager(KeyManagerInterface):
    """In-memory key manager for development/testing."""

    def __init__(self):
        self._keys: Dict[str, str] = {}
        self._metadata: Dict[str, KeyMetadata] = {}

    async def generate_keypair(self, key_id: str) -> Tuple[str, str]:
        from kaizen.trust.crypto import generate_keypair
        private_key, public_key = generate_keypair()
        self._keys[key_id] = private_key
        self._metadata[key_id] = KeyMetadata(
            key_id=key_id,
            created_at=datetime.now(timezone.utc),
            is_hardware_backed=False,
        )
        return private_key, public_key

    # ... implement other methods ...


class AWSKMSKeyManager(KeyManagerInterface):
    """AWS KMS integration for production key management."""

    def __init__(self, kms_client, key_alias_prefix: str = "eatp/"):
        self._kms = kms_client
        self._prefix = key_alias_prefix

    async def sign(self, payload: str, key_id: str) -> str:
        """Sign using AWS KMS."""
        import base64

        response = await self._kms.sign(
            KeyId=f"alias/{self._prefix}{key_id}",
            Message=payload.encode('utf-8'),
            SigningAlgorithm='ECDSA_SHA_256',
        )
        return base64.b64encode(response['Signature']).decode('utf-8')

    # ... implement other methods ...
```

---

### P1-2: Linked State Hashing

**File**: `apps/kailash-kaizen/src/kaizen/trust/crypto.py`

**Already included in P0-1 salt fix.** The `hash_trust_chain_state_with_salt` function includes `previous_state_hash` parameter.

**Additional Store Changes**:

```python
# File: apps/kailash-kaizen/src/kaizen/trust/store.py
# Add to TrustChain model (around line 117)

previous_chain_hash: Optional[str] = None  # Hash of previous state for linking


# Update store_chain method:
async def store_chain(
    self,
    chain: TrustLineageChain,
    expires_at: Optional[datetime] = None,
) -> str:
    # ... existing code ...

    # Get previous hash for linking
    previous_hash = None
    try:
        existing = await self.get_chain(chain.genesis.agent_id)
        previous_hash = existing.hash()
    except TrustChainNotFoundError:
        pass

    # Compute new hash with linking
    current_hash = chain.hash(previous_hash=previous_hash)

    # Store with linked hash
    # ... rest of method ...
```

---

### P1-3: Revocation Event Broadcasting

**File**: `apps/kailash-kaizen/src/kaizen/trust/revocation.py` (NEW)

```python
# File: apps/kailash-kaizen/src/kaizen/trust/revocation.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional
from enum import Enum
import asyncio
import logging

logger = logging.getLogger(__name__)


class RevocationType(str, Enum):
    """Types of revocation events."""
    AGENT_REVOKED = "agent_revoked"
    DELEGATION_REVOKED = "delegation_revoked"
    HUMAN_SESSION_REVOKED = "human_session_revoked"
    KEY_REVOKED = "key_revoked"
    CASCADE_REVOCATION = "cascade_revocation"


@dataclass
class RevocationEvent:
    """
    A revocation event for broadcasting.

    Attributes:
        event_id: Unique event identifier
        revocation_type: Type of revocation
        target_id: ID of revoked entity
        revoked_by: ID of revoking authority
        reason: Reason for revocation
        affected_agents: List of agents affected by this revocation
        timestamp: When revocation occurred
        cascade_from: Parent revocation event (for cascades)
    """
    event_id: str
    revocation_type: RevocationType
    target_id: str
    revoked_by: str
    reason: str
    affected_agents: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cascade_from: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "event_id": self.event_id,
            "revocation_type": self.revocation_type.value,
            "target_id": self.target_id,
            "revoked_by": self.revoked_by,
            "reason": self.reason,
            "affected_agents": self.affected_agents,
            "timestamp": self.timestamp.isoformat(),
            "cascade_from": self.cascade_from,
        }


class RevocationBroadcaster(ABC):
    """
    Abstract interface for broadcasting revocation events.

    Implementations can use different backends:
    - InMemoryBroadcaster: For testing
    - RedisBroadcaster: For distributed systems
    - KafkaBroadcaster: For event-sourced architectures
    - WebhookBroadcaster: For external integrations
    """

    @abstractmethod
    async def broadcast(self, event: RevocationEvent) -> None:
        """Broadcast a revocation event to all subscribers."""
        pass

    @abstractmethod
    async def subscribe(
        self,
        callback: Callable[[RevocationEvent], None],
        filter_types: Optional[List[RevocationType]] = None,
    ) -> str:
        """
        Subscribe to revocation events.

        Returns subscription ID for unsubscribing.
        """
        pass

    @abstractmethod
    async def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe from revocation events."""
        pass


class InMemoryRevocationBroadcaster(RevocationBroadcaster):
    """In-memory broadcaster for development and testing."""

    def __init__(self):
        self._subscribers: Dict[str, Callable] = {}
        self._filters: Dict[str, Optional[List[RevocationType]]] = {}
        self._history: List[RevocationEvent] = []

    async def broadcast(self, event: RevocationEvent) -> None:
        """Broadcast to all subscribers."""
        self._history.append(event)

        for sub_id, callback in self._subscribers.items():
            filter_types = self._filters.get(sub_id)

            # Apply filter
            if filter_types and event.revocation_type not in filter_types:
                continue

            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"Subscriber {sub_id} error: {e}")

    async def subscribe(
        self,
        callback: Callable[[RevocationEvent], None],
        filter_types: Optional[List[RevocationType]] = None,
    ) -> str:
        from uuid import uuid4
        sub_id = f"sub-{uuid4().hex[:8]}"
        self._subscribers[sub_id] = callback
        self._filters[sub_id] = filter_types
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> None:
        self._subscribers.pop(subscription_id, None)
        self._filters.pop(subscription_id, None)


class TrustRevocationList:
    """
    Certificate Revocation List (CRL) for trust chains.

    Maintains a list of revoked trust chains for quick lookup.
    """

    def __init__(self, broadcaster: RevocationBroadcaster):
        self._broadcaster = broadcaster
        self._revoked: Dict[str, RevocationEvent] = {}
        self._subscription_id: Optional[str] = None

    async def initialize(self) -> None:
        """Initialize and subscribe to revocation events."""
        self._subscription_id = await self._broadcaster.subscribe(
            self._on_revocation_event
        )

    async def _on_revocation_event(self, event: RevocationEvent) -> None:
        """Handle incoming revocation events."""
        self._revoked[event.target_id] = event
        for agent_id in event.affected_agents:
            self._revoked[agent_id] = event

    def is_revoked(self, agent_id: str) -> bool:
        """Check if an agent is revoked."""
        return agent_id in self._revoked

    def get_revocation_event(self, agent_id: str) -> Optional[RevocationEvent]:
        """Get the revocation event for an agent."""
        return self._revoked.get(agent_id)

    async def close(self) -> None:
        if self._subscription_id:
            await self._broadcaster.unsubscribe(self._subscription_id)
```

---

### P1-4: Transactional Chain Re-signing During Key Rotation

**File**: `apps/kailash-kaizen/src/kaizen/trust/rotation.py`

**Required Changes** to `_resign_chains` method:

```python
# Update _resign_chains in rotation.py

async def _resign_chains(
    self,
    authority_id: str,
    old_key_id: str,
    new_key_id: str,
) -> int:
    """
    Re-sign all trust chains for an authority atomically.

    Uses database transactions to ensure all-or-nothing re-signing.

    Args:
        authority_id: Authority whose chains to re-sign
        old_key_id: Old key ID (for reference)
        new_key_id: New key ID to use for signing

    Returns:
        Number of chains updated

    Raises:
        RotationError: If any chain fails to re-sign (all changes rolled back)
    """
    chains = await self.trust_store.list_chains(
        authority_id=authority_id,
        active_only=True,
        limit=10000,
    )

    # Collect all updates before committing
    updates: List[Tuple[str, TrustLineageChain]] = []

    try:
        for chain in chains:
            # Re-sign genesis record
            genesis_payload = serialize_for_signing(chain.genesis.to_signing_payload())
            new_signature = await self.key_manager.sign(genesis_payload, new_key_id)
            chain.genesis.signature = new_signature

            # Re-sign capability attestations
            for capability in chain.capabilities:
                if capability.attester_id == authority_id:
                    cap_payload = serialize_for_signing(capability.to_signing_payload())
                    new_signature = await self.key_manager.sign(cap_payload, new_key_id)
                    capability.signature = new_signature

            # Re-sign delegations
            for delegation in chain.delegations:
                if delegation.delegator_id == authority_id:
                    del_payload = serialize_for_signing(delegation.to_signing_payload())
                    new_signature = await self.key_manager.sign(del_payload, new_key_id)
                    delegation.signature = new_signature

            updates.append((chain.genesis.agent_id, chain))

        # Commit all updates atomically
        # (Requires adding transaction support to trust store)
        async with self.trust_store.transaction():
            for agent_id, chain in updates:
                await self.trust_store.update_chain(agent_id, chain)

        return len(updates)

    except Exception as e:
        raise RotationError(
            f"Failed to re-sign chains for authority {authority_id}: {str(e)}. "
            "All changes have been rolled back.",
            authority_id=authority_id,
            reason="resign_failed",
        ) from e
```

---

### P1-5: Constraint Inheritance Validation

**File**: `apps/kailash-kaizen/src/kaizen/trust/constraint_validator.py`

**Already largely implemented.** Add widening attack prevention:

```python
# Add to ConstraintValidator class

def validate_inheritance(
    self,
    parent_constraints: Dict[str, Any],
    child_constraints: Dict[str, Any],
) -> ValidationResult:
    """
    Validate that child constraints properly inherit and can only tighten.

    Widening Attack Prevention:
    - Child cannot ADD new allowed_actions not in parent
    - Child cannot INCREASE numeric limits
    - Child cannot EXPAND resource scopes
    - Child cannot REMOVE restrictions

    Args:
        parent_constraints: Parent's constraints
        child_constraints: Child's constraints to validate

    Returns:
        ValidationResult with violations if any widening detected
    """
    violations = []
    details = {}

    # Check for widening attempts

    # 1. Numeric limits must be <= parent
    numeric_limits = [
        "cost_limit", "rate_limit", "budget_limit",
        "max_delegation_depth", "max_api_calls"
    ]
    for limit_name in numeric_limits:
        if limit_name in child_constraints:
            parent_val = parent_constraints.get(limit_name, float("inf"))
            child_val = child_constraints[limit_name]
            if child_val > parent_val:
                violations.append(ConstraintViolation.COST_LOOSENED)
                details[limit_name] = f"Widening: child {child_val} > parent {parent_val}"

    # 2. Resource scopes must be subsets
    if "resources" in child_constraints and "resources" in parent_constraints:
        if not self._is_resource_subset(
            parent_constraints["resources"],
            child_constraints["resources"]
        ):
            violations.append(ConstraintViolation.RESOURCES_EXPANDED)
            details["resources"] = "Widening: child resources not subset of parent"

    # 3. Allowed actions must be subsets
    if "allowed_actions" in child_constraints:
        parent_actions = set(parent_constraints.get("allowed_actions", []))
        child_actions = set(child_constraints["allowed_actions"])
        if child_actions and not child_actions.issubset(parent_actions):
            added = child_actions - parent_actions
            violations.append(ConstraintViolation.ACTION_RESTRICTION_REMOVED)
            details["allowed_actions"] = f"Widening: added actions {added}"

    # 4. Forbidden actions must be preserved
    if "forbidden_actions" in parent_constraints:
        parent_forbidden = set(parent_constraints["forbidden_actions"])
        child_forbidden = set(child_constraints.get("forbidden_actions", []))
        removed = parent_forbidden - child_forbidden
        if removed:
            violations.append(ConstraintViolation.ACTION_RESTRICTION_REMOVED)
            details["forbidden_actions"] = f"Widening: removed forbidden {removed}"

    return ValidationResult(
        valid=len(violations) == 0,
        violations=violations,
        details=details,
    )
```

---

### P1-6: Append-Only Database Constraints for Audit Trail

**File**: `apps/kailash-kaizen/src/kaizen/trust/audit_store.py`

```python
# Add append-only enforcement

class AppendOnlyAuditStore(PostgresAuditStore):
    """
    Audit store with append-only enforcement.

    Security:
    - DELETE operations blocked
    - UPDATE operations blocked
    - Only INSERT allowed
    - Immutability enforced at application and database level
    """

    async def initialize(self) -> None:
        """Initialize with append-only constraints."""
        await super().initialize()

        # Create database trigger to enforce append-only
        # This is PostgreSQL-specific
        await self._create_append_only_trigger()

    async def _create_append_only_trigger(self) -> None:
        """Create PostgreSQL trigger to prevent updates/deletes."""
        trigger_sql = """
        CREATE OR REPLACE FUNCTION prevent_audit_modification()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'UPDATE' OR TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Audit trail is append-only. Modifications not allowed.';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS audit_append_only ON audit_anchors;

        CREATE TRIGGER audit_append_only
        BEFORE UPDATE OR DELETE ON audit_anchors
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();
        """
        # Execute via DataFlow or raw SQL
        # Implementation depends on DataFlow's raw SQL support

    async def append(self, anchor: AuditAnchor) -> None:
        """Append an audit anchor (the only allowed operation)."""
        # Verify anchor has required fields
        if not anchor.signature:
            raise AuditStoreImmutabilityError(
                "Audit anchors must be signed before storage"
            )

        # Insert via parent class
        await super().append(anchor)

    async def update(self, *args, **kwargs) -> None:
        """Updates are not allowed on append-only store."""
        raise AuditStoreImmutabilityError(
            "Audit trail is append-only. Updates not allowed."
        )

    async def delete(self, *args, **kwargs) -> None:
        """Deletes are not allowed on append-only store."""
        raise AuditStoreImmutabilityError(
            "Audit trail is append-only. Deletes not allowed."
        )
```

---

## P2 Enterprise Features

### P2-1: Multi-Signature Genesis Records

**File**: `apps/kailash-kaizen/src/kaizen/trust/multisig.py` (NEW)

```python
# File: apps/kailash-kaizen/src/kaizen/trust/multisig.py

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from datetime import datetime, timezone

@dataclass
class MultiSigPolicy:
    """
    M-of-N multi-signature policy.

    Attributes:
        required_signatures: Number of signatures required (M)
        total_signers: Total number of authorized signers (N)
        signer_public_keys: Map of signer_id -> public_key
        expiry_hours: Hours before pending signatures expire
    """
    required_signatures: int  # M
    total_signers: int  # N
    signer_public_keys: Dict[str, str]  # signer_id -> public_key
    expiry_hours: int = 24

    def __post_init__(self):
        if self.required_signatures > self.total_signers:
            raise ValueError("Required signatures cannot exceed total signers")
        if self.required_signatures < 1:
            raise ValueError("At least one signature required")


@dataclass
class PendingMultiSig:
    """
    A pending multi-signature operation.

    Attributes:
        operation_id: Unique ID for this operation
        payload: The data being signed
        policy: The multi-sig policy
        signatures: Collected signatures (signer_id -> signature)
        created_at: When the operation was created
        expires_at: When pending signatures expire
    """
    operation_id: str
    payload: str
    policy: MultiSigPolicy
    signatures: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None

    def __post_init__(self):
        if self.expires_at is None:
            from datetime import timedelta
            self.expires_at = self.created_at + timedelta(
                hours=self.policy.expiry_hours
            )

    def is_complete(self) -> bool:
        """Check if enough signatures collected."""
        return len(self.signatures) >= self.policy.required_signatures

    def is_expired(self) -> bool:
        """Check if signing window expired."""
        return datetime.now(timezone.utc) > self.expires_at

    def remaining_signatures(self) -> int:
        """Number of signatures still needed."""
        return max(0, self.policy.required_signatures - len(self.signatures))

    def pending_signers(self) -> Set[str]:
        """Signers who haven't signed yet."""
        return set(self.policy.signer_public_keys.keys()) - set(self.signatures.keys())


class MultiSigManager:
    """
    Manages multi-signature operations for genesis records.

    Example:
        >>> policy = MultiSigPolicy(required_signatures=2, total_signers=3, ...)
        >>> manager = MultiSigManager()
        >>>
        >>> # Initiate signing
        >>> pending = await manager.initiate_genesis_signing(genesis, policy)
        >>>
        >>> # Collect signatures from approvers
        >>> await manager.add_signature(pending.operation_id, "signer-1", sig1)
        >>> await manager.add_signature(pending.operation_id, "signer-2", sig2)
        >>>
        >>> # Complete when M signatures collected
        >>> genesis = await manager.complete_genesis_signing(pending.operation_id)
    """

    def __init__(self, key_manager):
        self._key_manager = key_manager
        self._pending: Dict[str, PendingMultiSig] = {}

    async def initiate_genesis_signing(
        self,
        genesis: GenesisRecord,
        policy: MultiSigPolicy,
    ) -> PendingMultiSig:
        """Start a multi-sig genesis signing operation."""
        from uuid import uuid4
        from kaizen.trust.crypto import serialize_for_signing

        payload = serialize_for_signing(genesis.to_signing_payload())
        operation_id = f"msig-{uuid4().hex[:12]}"

        pending = PendingMultiSig(
            operation_id=operation_id,
            payload=payload,
            policy=policy,
        )

        self._pending[operation_id] = pending
        return pending

    async def add_signature(
        self,
        operation_id: str,
        signer_id: str,
        signature: str,
    ) -> PendingMultiSig:
        """Add a signature to a pending operation."""
        pending = self._pending.get(operation_id)
        if not pending:
            raise ValueError(f"Operation not found: {operation_id}")

        if pending.is_expired():
            raise ValueError("Signing window expired")

        if signer_id not in pending.policy.signer_public_keys:
            raise ValueError(f"Signer not authorized: {signer_id}")

        # Verify signature
        public_key = pending.policy.signer_public_keys[signer_id]
        if not await self._key_manager.verify(pending.payload, signature, public_key):
            raise ValueError("Invalid signature")

        pending.signatures[signer_id] = signature
        return pending

    async def complete_genesis_signing(
        self,
        operation_id: str,
    ) -> str:
        """
        Complete a multi-sig operation and return combined signature.

        Returns:
            Combined signature for the genesis record
        """
        pending = self._pending.get(operation_id)
        if not pending:
            raise ValueError(f"Operation not found: {operation_id}")

        if not pending.is_complete():
            raise ValueError(
                f"Insufficient signatures: {len(pending.signatures)}/"
                f"{pending.policy.required_signatures}"
            )

        # Create combined signature (concatenation with metadata)
        # In production, would use proper multi-sig scheme (Schnorr, BLS, etc.)
        combined = {
            "type": "multisig",
            "threshold": f"{pending.policy.required_signatures}/{pending.policy.total_signers}",
            "signatures": pending.signatures,
        }

        import json
        del self._pending[operation_id]
        return json.dumps(combined)
```

---

## Testing Requirements Summary

### Unit Tests Required

1. **P0 Crypto Tests**: `tests/unit/trust/test_crypto_salt.py`
2. **P0 Signature Tests**: `tests/unit/trust/test_delegation_signatures.py`
3. **P0 Cycle Tests**: `tests/unit/trust/test_delegation_cycles.py`
4. **P0 Depth Tests**: `tests/unit/trust/test_delegation_depth.py`
5. **P1 Key Manager Tests**: `tests/unit/trust/test_key_manager.py`
6. **P1 Revocation Tests**: `tests/unit/trust/test_revocation.py`
7. **P1 Rotation Tests**: `tests/unit/trust/test_rotation_transactional.py`
8. **P2 MultiSig Tests**: `tests/unit/trust/test_multisig.py`

### Integration Tests Required

1. **HSM/KMS Integration**: `tests/integration/trust/test_kms_integration.py`
2. **Revocation Broadcasting**: `tests/integration/trust/test_revocation_broadcast.py`
3. **Multi-signature Flow**: `tests/integration/trust/test_multisig_flow.py`

---

## Migration and Backward Compatibility

### Breaking Changes

1. **Salt in hashes**: Existing chains need migration to include salt
2. **Signature verification**: May reject previously accepted unsigned delegations
3. **Depth limits**: May break existing deep delegation chains

### Migration Script

```python
# scripts/migrations/migrate_trust_chains_v2.py

async def migrate_trust_chains_to_v2(trust_store):
    """
    Migrate trust chains to v2 format with:
    - Salted hashes
    - Linked state hashing
    - Delegation depth limits
    """
    chains = await trust_store.list_chains(limit=10000)

    for chain in chains:
        # Add salt to hash
        new_hash = chain.hash(previous_hash=None)

        # Validate delegation depth
        if any(d.delegation_depth > MAX_DELEGATION_DEPTH for d in chain.delegations):
            logger.warning(f"Chain {chain.genesis.agent_id} exceeds depth limit")

        # Update chain
        await trust_store.update_chain(chain.genesis.agent_id, chain)

    logger.info(f"Migrated {len(chains)} trust chains to v2 format")
```

### Feature Flags

```python
# Enable gradual rollout of new features
TRUST_V2_FEATURES = {
    "salted_hashing": True,  # P0-1
    "delegation_signature_verification": True,  # P0-2
    "cycle_detection": True,  # P0-3
    "depth_limits": True,  # P0-4
    "hsm_integration": False,  # P1-1 (opt-in)
    "linked_hashing": False,  # P1-2 (requires migration)
    "revocation_broadcast": False,  # P1-3 (opt-in)
    "multisig_genesis": False,  # P2-1 (opt-in)
}
```

---

## Version History

| Version | Date       | Changes              |
| ------- | ---------- | -------------------- |
| 1.0     | 2026-02-07 | Initial plan created |

## References

- CARE Framework Specification
- EATP Protocol Design (docs/plans/eatp-integration/)
- Kaizen Trust Module (apps/kailash-kaizen/src/kaizen/trust/)
