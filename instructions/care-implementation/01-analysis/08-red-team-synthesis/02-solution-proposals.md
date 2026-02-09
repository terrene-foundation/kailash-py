# CARE/EATP Trust Framework - Solution Proposals

## Executive Summary

This document proposes concrete solutions for all CRITICAL and HIGH priority threats identified in the Consolidated Threat Register. Each solution specifies placement (SDK vs Platform), effort estimate, dependencies, and implementation details.

**Total Remediation Effort**: 60-80 person-weeks across 4 phases (realistic: 4-6 months including security testing)
**First-Mover Window**: Solutions must be deployed within 6-9 months to maintain competitive advantage

---

## Section 1: P0 Solutions (Immediate - Week 1-2)

### SOL-CRIT-001: Dynamic Salt with Per-Deployment Uniqueness

**Addresses**: CRIT-001 (Static Salt in Key Derivation)

**Placement**: SDK (Kaizen Trust Module)

**Solution Description**:
Replace the hardcoded salt with a cryptographically secure, per-deployment unique salt generated during initialization and stored securely.

**Implementation**:

```python
# NEW: crypto.py modifications

import os
from pathlib import Path

class SaltManager:
    """Manages per-deployment salt for key derivation."""

    SALT_FILE = ".eatp-salt"
    SALT_LENGTH = 32  # 256 bits

    @classmethod
    def get_or_create_salt(cls, deployment_id: str = None) -> bytes:
        """Get existing salt or create new one for this deployment."""
        salt_path = Path(os.environ.get("EATP_SALT_PATH", cls.SALT_FILE))

        if salt_path.exists():
            with open(salt_path, "rb") as f:
                return f.read()

        # Generate new salt
        salt = os.urandom(cls.SALT_LENGTH)

        # Optionally incorporate deployment_id
        if deployment_id:
            import hashlib
            salt = hashlib.sha256(salt + deployment_id.encode()).digest()

        # Store securely (owner read-only)
        salt_path.touch(mode=0o600)
        with open(salt_path, "wb") as f:
            f.write(salt)

        return salt

def derive_key(password: str, purpose: str) -> bytes:
    """Derive key with per-deployment salt."""
    import hashlib
    salt = SaltManager.get_or_create_salt()
    # Add purpose to prevent cross-use
    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode(),
        salt + purpose.encode(),
        iterations=100000,
        dklen=32
    )
```

**Effort**: 0.5 person-weeks
**Dependencies**: None
**Risk Mitigation**: Existing deployments need migration procedure

**Migration Procedure**:

1. Generate new salt for deployment
2. Re-derive all keys using new salt
3. Re-sign all trust records with new keys
4. Verify chain integrity
5. Remove old salt

### Cloud and Container Salt Hardening (Second-Pass)

```python
class CloudSaltManager(SaltManager):
    """Production-grade salt management with cloud, env, and file fallback.

    Priority order:
    1. Cloud KMS (EATP_KMS_SALT_ARN environment variable)
    2. Environment variable (EATP_SALT_B64, base64-encoded)
    3. File-based with atomic creation (O_EXCL flag)
    """

    def _generate_or_load_salt(self) -> bytes:
        # Priority 1: Cloud KMS
        kms_arn = os.environ.get("EATP_KMS_SALT_ARN")
        if kms_arn:
            return self._load_from_kms(kms_arn)

        # Priority 2: Environment variable
        salt_b64 = os.environ.get("EATP_SALT_B64")
        if salt_b64:
            return base64.b64decode(salt_b64)

        # Priority 3: File-based with atomic creation
        salt_path = Path(os.environ.get("EATP_SALT_PATH", ".eatp-salt"))
        if salt_path.exists():
            return salt_path.read_bytes()

        # Generate new salt with atomic file creation (O_EXCL prevents race)
        salt = os.urandom(32)
        fd = os.open(str(salt_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, salt)
        finally:
            os.close(fd)

        # Store integrity hash separately
        hash_path = salt_path.with_suffix(".sha256")
        hash_path.write_text(hashlib.sha256(salt).hexdigest())

        return salt
```

> **Backup exclusion**: The `.eatp-salt` file MUST be excluded from filesystem backups. Add to `.gitignore`, backup exclusion lists, and container image `.dockerignore`.

---

### SOL-CRIT-002: Enable Delegation Signature Verification

**Addresses**: CRIT-002 (Delegation Signature Verification Disabled)

**Placement**: SDK (Kaizen Trust Module)

**Solution Description**:
Implement complete delegation signature verification using per-agent signing keys derived from their trust chain.

**Implementation**:

```python
# operations.py modifications

async def _verify_delegation_signature(
    self,
    delegation: DelegationRecord,
    delegator_chain: TrustLineageChain,
) -> bool:
    """Verify a delegation record's signature."""
    # Get delegator's signing key
    # For agents, derive from their trust chain
    delegator_key_id = f"agent:{delegation.delegator_id}"

    # Look up delegator's public key from their chain
    # In production, each agent should have their own key pair
    delegator_public_key = await self._get_agent_public_key(
        delegation.delegator_id,
        delegator_chain
    )

    if not delegator_public_key:
        logger.warning(
            f"No public key found for delegator {delegation.delegator_id}"
        )
        return False

    # Verify signature
    payload = serialize_for_signing(delegation.to_signing_payload())
    return await self.key_manager.verify(
        payload,
        delegation.signature,
        delegator_public_key
    )

async def _verify_signatures(
    self,
    chain: TrustLineageChain,
) -> VerificationResult:
    """Verify all signatures in a trust chain - INCLUDING DELEGATIONS."""
    # ... existing genesis and capability verification ...

    # NEW: Verify delegation signatures
    for delegation in chain.delegations:
        try:
            delegator_chain = await self.trust_store.get_chain(
                delegation.delegator_id
            )
            if not await self._verify_delegation_signature(
                delegation, delegator_chain
            ):
                return VerificationResult(
                    valid=False,
                    reason=f"Invalid delegation signature: {delegation.id}",
                    level=VerificationLevel.FULL,
                )
        except TrustChainNotFoundError:
            return VerificationResult(
                valid=False,
                reason=f"Delegator chain not found: {delegation.delegator_id}",
                level=VerificationLevel.FULL,
            )

    return VerificationResult(valid=True, level=VerificationLevel.FULL)
```

**Effort**: 1 person-week
**Dependencies**: Agent key pair generation (see SOL-CRIT-004)
**Risk Mitigation**: Must handle legacy delegations without signatures

### Migration Procedure (Second-Pass)

```python
class DelegationMigrator:
    """Handles unsigned-to-signed delegation migration."""

    async def migrate_all(self, batch_size: int = 100) -> MigrationReport:
        """Batch-sign all existing unsigned delegations."""
        unsigned = await self.store.list_unsigned_delegations()
        report = MigrationReport(total=len(unsigned))

        for batch in chunks(unsigned, batch_size):
            for delegation in batch:
                try:
                    # Sign with delegator's current key
                    signed = await self._sign_delegation(delegation)
                    # Add monotonic counter for replay prevention
                    signed.counter = await self._next_counter(delegation.delegator_id)
                    await self.store.update_delegation(signed)
                    report.signed += 1
                except KeyNotFoundError:
                    # Delegator no longer available - use org admin key
                    signed = await self._admin_sign_delegation(delegation)
                    signed.counter = await self._next_counter("admin")
                    await self.store.update_delegation(signed)
                    report.admin_signed += 1

        return report

    async def _next_counter(self, delegator_id: str) -> int:
        """Atomic counter increment with distributed synchronization.

        Uses a database-level atomic increment (UPDATE ... RETURNING) to
        guarantee uniqueness across all nodes in the cluster. No two
        delegations from the same delegator can share a counter value.

        This is NOT an in-memory counter — it uses the centralized trust
        store with serializable isolation to prevent counter collisions
        across distributed nodes.
        """
        # Atomic increment in the trust store (single source of truth)
        return await self.store.atomic_increment_counter(
            delegator_id,
            # Serializable isolation prevents concurrent increments
            isolation_level="serializable",
        )

class VersionNegotiatingVerifier:
    """Verifies delegations with version-aware protocol."""

    async def verify(self, delegation: Delegation) -> VerificationResult:
        # Check monotonic counter (prevents replay) — uses centralized store
        if delegation.counter is not None:
            last_seen = await self._get_last_counter(delegation.delegator_id)
            if delegation.counter <= last_seen:
                return VerificationResult(valid=False, reason="Replay detected")

        # Version-aware verification
        if delegation.protocol_version >= 2:
            # v2: Full signature verification required
            return await self._verify_signature(delegation)
        elif self.config.strict_mode:
            # v1 in strict mode: reject unsigned
            return VerificationResult(valid=False, reason="Unsigned delegation rejected in strict mode")
        else:
            # v1 in compatibility mode: warn and accept (migration window only)
            logger.warning(f"Accepting unsigned delegation {delegation.id} during migration")
            return VerificationResult(valid=True, warning="Unsigned - migrate ASAP")
```

---

### SOL-CRIT-003: Delegation Cycle Detection

**Addresses**: CRIT-003 (No Cycle Detection in Delegation Chains)

**Placement**: SDK (Kaizen Trust Module)

**Solution Description**:
Implement graph-based cycle detection before accepting any delegation, preventing privilege escalation loops.

**Implementation**:

```python
# NEW: delegation_validator.py

from typing import Dict, Set, List
from collections import defaultdict

class DelegationGraphValidator:
    """Validates delegation graphs for cycles and depth limits."""

    MAX_DELEGATION_DEPTH = 10  # Configurable

    def __init__(self, trust_store):
        self.trust_store = trust_store
        self._graph: Dict[str, Set[str]] = defaultdict(set)
        self._reverse_graph: Dict[str, Set[str]] = defaultdict(set)

    async def load_graph(self) -> None:
        """Load current delegation graph from store."""
        chains = await self.trust_store.list_chains()
        self._graph.clear()
        self._reverse_graph.clear()

        for chain in chains:
            for delegation in chain.delegations:
                self._graph[delegation.delegator_id].add(delegation.delegatee_id)
                self._reverse_graph[delegation.delegatee_id].add(delegation.delegator_id)

    def would_create_cycle(
        self,
        delegator_id: str,
        delegatee_id: str
    ) -> bool:
        """Check if adding this delegation would create a cycle."""
        # If delegatee can reach delegator through existing paths,
        # adding delegator -> delegatee creates a cycle
        visited = set()
        stack = [delegatee_id]

        while stack:
            current = stack.pop()
            if current == delegator_id:
                return True  # Cycle would be created
            if current in visited:
                continue
            visited.add(current)
            stack.extend(self._graph.get(current, set()))

        return False

    def get_chain_depth(self, agent_id: str) -> int:
        """Get the delegation depth from nearest genesis."""
        visited = set()
        depth = 0
        current_level = {agent_id}

        while current_level:
            next_level = set()
            for agent in current_level:
                if agent in visited:
                    continue
                visited.add(agent)
                parents = self._reverse_graph.get(agent, set())
                if not parents:
                    # This agent is a genesis (no delegator)
                    return depth
                next_level.update(parents)
            current_level = next_level
            depth += 1

        return depth

    def validate_delegation(
        self,
        delegator_id: str,
        delegatee_id: str
    ) -> tuple[bool, str]:
        """Validate if a delegation can be safely created."""
        # Check for cycles
        if self.would_create_cycle(delegator_id, delegatee_id):
            return False, f"Delegation would create cycle: {delegator_id} -> {delegatee_id}"

        # Check depth limit
        current_depth = self.get_chain_depth(delegator_id)
        if current_depth >= self.MAX_DELEGATION_DEPTH:
            return False, f"Maximum delegation depth ({self.MAX_DELEGATION_DEPTH}) exceeded"

        return True, "Delegation is valid"

# Integration in operations.py
async def delegate(self, ...):
    """DELEGATE operation with cycle detection."""
    # NEW: Validate delegation graph
    validator = DelegationGraphValidator(self.trust_store)
    await validator.load_graph()

    is_valid, reason = validator.validate_delegation(delegator_id, delegatee_id)
    if not is_valid:
        raise DelegationError(
            reason,
            delegator_id=delegator_id,
            delegatee_id=delegatee_id,
        )

    # ... rest of delegation logic ...
```

**Effort**: 1 person-week
**Dependencies**: None
**Risk Mitigation**: Must handle existing cycles gracefully (flag for review)

---

### SOL-CRIT-005: Active Cache Invalidation via Pub/Sub

**Addresses**: CRIT-005 (Cache Invalidation is No-Op)

**Placement**: SDK (Kaizen Trust Module) + Platform (if distributed)

**Solution Description**:
Implement active cache invalidation using a pub/sub pattern. When trust is modified or revoked, publish invalidation event to all cache holders.

**Implementation**:

```python
# NEW: cache_invalidation.py

import asyncio
from typing import Callable, Set
from abc import ABC, abstractmethod

class CacheInvalidationChannel(ABC):
    """Abstract channel for cache invalidation."""

    @abstractmethod
    async def publish(self, agent_id: str, event_type: str) -> None:
        """Publish invalidation event."""
        pass

    @abstractmethod
    async def subscribe(
        self,
        callback: Callable[[str, str], None]
    ) -> None:
        """Subscribe to invalidation events."""
        pass

class RedisCacheInvalidation(CacheInvalidationChannel):
    """Redis-based cache invalidation for distributed deployments."""

    CHANNEL = "eatp:cache:invalidate"

    def __init__(self, redis_url: str):
        import aioredis
        self.redis = aioredis.from_url(redis_url)
        self.pubsub = None

    async def publish(self, agent_id: str, event_type: str) -> None:
        message = f"{event_type}:{agent_id}"
        await self.redis.publish(self.CHANNEL, message)

    async def subscribe(
        self,
        callback: Callable[[str, str], None]
    ) -> None:
        self.pubsub = self.redis.pubsub()
        await self.pubsub.subscribe(self.CHANNEL)

        async for message in self.pubsub.listen():
            if message["type"] == "message":
                data = message["data"].decode()
                event_type, agent_id = data.split(":", 1)
                await callback(agent_id, event_type)

class InMemoryCacheInvalidation(CacheInvalidationChannel):
    """In-memory cache invalidation for single-node deployments."""

    def __init__(self):
        self._subscribers: Set[Callable] = set()

    async def publish(self, agent_id: str, event_type: str) -> None:
        for callback in self._subscribers:
            await callback(agent_id, event_type)

    async def subscribe(
        self,
        callback: Callable[[str, str], None]
    ) -> None:
        self._subscribers.add(callback)

# Modified store.py
class PostgresTrustStore:
    def __init__(
        self,
        database_url: str = None,
        enable_cache: bool = True,
        cache_ttl_seconds: int = 300,
        invalidation_channel: CacheInvalidationChannel = None,
    ):
        # ... existing init ...
        self._invalidation = invalidation_channel or InMemoryCacheInvalidation()
        self._local_cache: Dict[str, tuple[TrustLineageChain, datetime]] = {}

    async def initialize(self) -> None:
        """Initialize with cache subscription."""
        await super().initialize()
        await self._invalidation.subscribe(self._on_cache_invalidate)

    async def _on_cache_invalidate(self, agent_id: str, event_type: str) -> None:
        """Handle cache invalidation event."""
        if agent_id in self._local_cache:
            del self._local_cache[agent_id]
            logger.info(f"Cache invalidated for {agent_id} ({event_type})")

    async def _invalidate_cache(self, agent_id: str) -> None:
        """Invalidate cache across all nodes."""
        # Local invalidation
        if agent_id in self._local_cache:
            del self._local_cache[agent_id]

        # Distributed invalidation
        await self._invalidation.publish(agent_id, "invalidate")
```

**Effort**: 1 person-week
**Dependencies**: Redis (optional, for distributed deployments)
**Risk Mitigation**: Fallback to short TTL if pub/sub fails

---

## Section 2: P1 Solutions (Phase 1 - Week 3-6)

### SOL-CRIT-004: HSM/KMS Integration for Key Storage

**Addresses**: CRIT-004 (In-Memory Key Storage)

**Placement**: SDK (Kaizen Trust Module) with Platform configuration

**Solution Description**:
Replace in-memory key storage with pluggable backend supporting HSM (HashiCorp Vault, AWS CloudHSM) and KMS (AWS KMS, Azure Key Vault, GCP KMS).

**Implementation**:

```python
# NEW: key_backends.py

from abc import ABC, abstractmethod
from typing import Optional

class KeyBackend(ABC):
    """Abstract key storage backend."""

    @abstractmethod
    async def store_key(self, key_id: str, private_key: bytes) -> None:
        """Store a private key securely."""
        pass

    @abstractmethod
    async def get_key(self, key_id: str) -> Optional[bytes]:
        """Retrieve a private key."""
        pass

    @abstractmethod
    async def sign(self, key_id: str, payload: bytes) -> bytes:
        """Sign payload using key in backend (key never leaves backend)."""
        pass

    @abstractmethod
    async def delete_key(self, key_id: str) -> None:
        """Delete a key."""
        pass

class AWSKMSBackend(KeyBackend):
    """AWS KMS backend - keys never leave AWS."""

    def __init__(self, region: str = None):
        import boto3
        self.kms = boto3.client('kms', region_name=region)
        self._key_aliases: Dict[str, str] = {}  # key_id -> KMS key ARN

    async def store_key(self, key_id: str, private_key: bytes) -> None:
        """Create new KMS key (private key bytes ignored - KMS generates)."""
        response = self.kms.create_key(
            Description=f"EATP key: {key_id}",
            KeyUsage='SIGN_VERIFY',
            KeySpec='ECC_NIST_P256',
            Tags=[{'TagKey': 'eatp_key_id', 'TagValue': key_id}]
        )
        self._key_aliases[key_id] = response['KeyMetadata']['Arn']

    async def sign(self, key_id: str, payload: bytes) -> bytes:
        """Sign using KMS - private key never exposed."""
        key_arn = self._key_aliases.get(key_id)
        if not key_arn:
            raise ValueError(f"Key not found: {key_id}")

        response = self.kms.sign(
            KeyId=key_arn,
            Message=payload,
            MessageType='RAW',
            SigningAlgorithm='ECDSA_SHA_256'
        )
        return response['Signature']

class HashiCorpVaultBackend(KeyBackend):
    """HashiCorp Vault backend with Transit secrets engine."""

    def __init__(self, vault_addr: str, vault_token: str):
        import hvac
        self.client = hvac.Client(url=vault_addr, token=vault_token)

    async def store_key(self, key_id: str, private_key: bytes) -> None:
        """Create key in Vault Transit engine."""
        self.client.secrets.transit.create_key(
            name=key_id,
            key_type='ed25519'
        )

    async def sign(self, key_id: str, payload: bytes) -> bytes:
        """Sign using Vault - private key never exposed."""
        import base64
        response = self.client.secrets.transit.sign_data(
            name=key_id,
            hash_input=base64.b64encode(payload).decode(),
            hash_algorithm='sha2-256'
        )
        signature = response['data']['signature']
        # Vault returns vault:v1:base64signature format
        return base64.b64decode(signature.split(':')[-1])

class SecureTrustKeyManager:
    """Key manager with pluggable secure backends."""

    def __init__(self, backend: KeyBackend):
        self._backend = backend

    async def sign(self, payload: str, key_id: str) -> str:
        """Sign using backend - key never in memory."""
        import base64
        signature = await self._backend.sign(key_id, payload.encode())
        return base64.b64encode(signature).decode()
```

**Effort**: 2 person-weeks
**Dependencies**: Cloud provider SDK or Vault client
**Risk Mitigation**: Include fallback to encrypted file-based storage

### Tiered Security Guidance (Second-Pass)

| Tier               | Key Storage                            | Cost       | Who Should Use           | Trade-offs                                         |
| ------------------ | -------------------------------------- | ---------- | ------------------------ | -------------------------------------------------- |
| **Minimum Viable** | Encrypted file + per-deployment salt   | Free       | All users, dev, startups | Keys extractable with local access                 |
| **Production**     | Cloud KMS (Vault, AWS Secrets Manager) | $5-50/mo   | Production deployments   | Requires cloud vendor; Ed25519 via custom wrapping |
| **Enterprise**     | Hardware HSM (CloudHSM, on-prem)       | $1K-20K/mo | Regulated industries     | High cost; Ed25519 support varies                  |

```python
class ProductionWarningKeyManager(InMemoryKeyManager):
    """Wraps InMemoryKeyManager with loud production warnings."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if os.environ.get("ENVIRONMENT", "").lower() in ("production", "prod", "staging"):
            import logging
            logging.critical(
                "SECURITY WARNING: InMemoryKeyManager is being used in a production "
                "environment. Private keys are stored in process memory and will be "
                "lost on restart. Configure EATP_KEY_BACKEND=kms or EATP_KEY_BACKEND=hsm "
                "for production deployments. See: docs/security/key-management.md"
            )
```

---

### SOL-CRIT-006 & SOL-CRIT-007: Core SDK and DataFlow Trust Integration

**Addresses**: CRIT-006 (No SDK Trust), CRIT-007 (No DataFlow Trust)

**Placement**: SDK (Core, DataFlow, Nexus)

**Solution Description**:
Add TrustContext parameter threading through Core SDK, DataFlow, and Nexus with automatic trust verification and audit trail.

**Implementation**:

```python
# Core SDK: runtime_trust.py (NEW)

from dataclasses import dataclass
from typing import Optional, Any, Dict
from kailash.runtime import LocalRuntime, AsyncLocalRuntime

@dataclass
class TrustContext:
    """Trust context for runtime execution."""
    agent_id: str
    human_origin: str
    delegation_chain: list[str]
    constraints: list[str]
    trace_id: str

    @classmethod
    def from_kaizen(cls, kaizen_context) -> "TrustContext":
        """Create from Kaizen ExecutionContext."""
        return cls(
            agent_id=kaizen_context.agent_id if hasattr(kaizen_context, 'agent_id') else 'unknown',
            human_origin=kaizen_context.human_origin.human_id,
            delegation_chain=kaizen_context.delegation_chain,
            constraints=list(kaizen_context.effective_constraints.keys()),
            trace_id=kaizen_context.trace_id,
        )

class TrustAwareRuntime(AsyncLocalRuntime):
    """Runtime with integrated trust verification."""

    def __init__(
        self,
        trust_operations=None,  # Kaizen TrustOperations
        require_trust: bool = True,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._trust_ops = trust_operations
        self._require_trust = require_trust

    async def execute_workflow_async(
        self,
        workflow,
        inputs: Dict[str, Any] = None,
        trust_context: TrustContext = None,
    ):
        """Execute workflow with trust verification."""
        if self._require_trust and not trust_context:
            raise RuntimeError(
                "TrustContext required. Either provide trust_context or "
                "set require_trust=False for untrusted execution."
            )

        if trust_context and self._trust_ops:
            # Verify trust before execution
            from kaizen.trust.chain import VerificationLevel
            result = await self._trust_ops.verify(
                agent_id=trust_context.agent_id,
                action="execute_workflow",
                level=VerificationLevel.STANDARD,
                context={"workflow_id": workflow.id if hasattr(workflow, 'id') else 'anonymous'}
            )
            if not result.valid:
                raise PermissionError(f"Trust verification failed: {result.reason}")

        # Execute with context tracking
        results, run_id = await super().execute_workflow_async(workflow, inputs or {})

        # Record audit
        if trust_context and self._trust_ops:
            from kaizen.trust.chain import ActionResult
            await self._trust_ops.audit(
                agent_id=trust_context.agent_id,
                action="execute_workflow",
                result=ActionResult.SUCCESS,
                context_data={"run_id": run_id, "workflow_nodes": len(workflow.nodes)},
            )

        return results, run_id

# DataFlow integration: dataflow_trust.py (NEW)

class TrustAwareDataFlow:
    """DataFlow wrapper with EATP trust integration."""

    def __init__(
        self,
        database_url: str,
        trust_operations=None,
        require_trust: bool = True,
        **kwargs
    ):
        from dataflow import DataFlow
        self._db = DataFlow(database_url, **kwargs)
        self._trust_ops = trust_operations
        self._require_trust = require_trust

    async def execute(
        self,
        node_type: str,
        params: dict,
        trust_context: TrustContext = None,
    ):
        """Execute DataFlow operation with trust."""
        if self._require_trust and not trust_context:
            raise RuntimeError("TrustContext required for DataFlow operations")

        # Map operation to action
        action = f"dataflow:{node_type.lower()}"

        if trust_context and self._trust_ops:
            # Verify trust
            result = await self._trust_ops.verify(
                agent_id=trust_context.agent_id,
                action=action,
                level=VerificationLevel.STANDARD,
            )
            if not result.valid:
                raise PermissionError(f"DataFlow operation denied: {result.reason}")

        # Execute operation
        from kailash.workflow.builder import WorkflowBuilder
        workflow = WorkflowBuilder()
        workflow.add_node(node_type, "operation", params)

        from kailash.runtime import AsyncLocalRuntime
        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute_workflow_async(workflow.build(), {})

        # Audit
        if trust_context and self._trust_ops:
            await self._trust_ops.audit(
                agent_id=trust_context.agent_id,
                action=action,
                resource=params.get("table", "unknown"),
                result=ActionResult.SUCCESS,
                context_data={"node_type": node_type, "run_id": run_id},
            )

        return results
```

**Effort**: 4 person-weeks (2 for Core SDK, 2 for DataFlow)
**Dependencies**: SOL-CRIT-002 (delegation verification)
**Risk Mitigation**: Maintain backward compatibility with opt-in trust

---

### SOL-CRIT-008: Trust Posture Alignment

**Addresses**: CRIT-008 (Posture Mismatch)

**Placement**: SDK (Kaizen) + Platform (Enterprise-App)

**Solution Description**:
Define canonical 5-posture model with formal mapping, state machine, and transition guards.

**Implementation**:

```python
# NEW: posture_v2.py - Unified posture model

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Set, Dict, Any

class UnifiedTrustPosture(str, Enum):
    """Canonical 5-posture model aligned with CARE framework."""

    # Level 0: No trust established - cannot act
    BLOCKED = "blocked"

    # Level 1: Human initiates, agent responds only
    PSEUDO = "pseudo"

    # Level 2: Agent acts with continuous human oversight
    SUPERVISED = "supervised"

    # Level 3: Agent proposes, human approves (planning level)
    SHARED_PLANNING = "shared_planning"

    # Level 4: Agent acts with periodic insight reporting
    CONTINUOUS_INSIGHT = "continuous_insight"

    # Level 5: Full delegation with outcome-based reporting
    DELEGATED = "delegated"

@dataclass
class PostureTransition:
    """Defines valid posture transitions."""
    from_posture: UnifiedTrustPosture
    to_posture: UnifiedTrustPosture
    required_trust_level: int  # Minimum trust score
    requires_human_approval: bool
    cooldown_seconds: int  # Minimum time between transitions

# State machine definition
VALID_TRANSITIONS: list[PostureTransition] = [
    # Can always block
    PostureTransition(UnifiedTrustPosture.PSEUDO, UnifiedTrustPosture.BLOCKED, 0, False, 0),
    PostureTransition(UnifiedTrustPosture.SUPERVISED, UnifiedTrustPosture.BLOCKED, 0, False, 0),
    # ... (all to BLOCKED)

    # Upgrade paths require trust accumulation
    PostureTransition(UnifiedTrustPosture.PSEUDO, UnifiedTrustPosture.SUPERVISED, 20, True, 3600),
    PostureTransition(UnifiedTrustPosture.SUPERVISED, UnifiedTrustPosture.SHARED_PLANNING, 50, True, 86400),
    PostureTransition(UnifiedTrustPosture.SHARED_PLANNING, UnifiedTrustPosture.CONTINUOUS_INSIGHT, 80, True, 604800),
    PostureTransition(UnifiedTrustPosture.CONTINUOUS_INSIGHT, UnifiedTrustPosture.DELEGATED, 95, True, 2592000),

    # Downgrade paths are immediate
    PostureTransition(UnifiedTrustPosture.DELEGATED, UnifiedTrustPosture.CONTINUOUS_INSIGHT, 0, False, 0),
    PostureTransition(UnifiedTrustPosture.CONTINUOUS_INSIGHT, UnifiedTrustPosture.SHARED_PLANNING, 0, False, 0),
    # ... etc
]

class PostureStateMachine:
    """Formal state machine for trust posture management."""

    def __init__(self, trust_store):
        self.trust_store = trust_store
        self._transitions = {
            (t.from_posture, t.to_posture): t
            for t in VALID_TRANSITIONS
        }

    def can_transition(
        self,
        current: UnifiedTrustPosture,
        target: UnifiedTrustPosture,
        trust_score: int,
        last_transition_time: datetime,
    ) -> tuple[bool, str]:
        """Check if transition is valid."""
        key = (current, target)
        if key not in self._transitions:
            return False, f"Invalid transition: {current.value} -> {target.value}"

        transition = self._transitions[key]

        # Check trust level
        if trust_score < transition.required_trust_level:
            return False, f"Insufficient trust: {trust_score} < {transition.required_trust_level}"

        # Check cooldown
        elapsed = (datetime.now(timezone.utc) - last_transition_time).total_seconds()
        if elapsed < transition.cooldown_seconds:
            remaining = transition.cooldown_seconds - elapsed
            return False, f"Cooldown active: {remaining}s remaining"

        return True, "Transition permitted"

# Mapping from old 4-posture to new 5-posture
LEGACY_POSTURE_MAPPING = {
    "FULL_AUTONOMY": UnifiedTrustPosture.DELEGATED,
    "SUPERVISED": UnifiedTrustPosture.SUPERVISED,
    "HUMAN_DECIDES": UnifiedTrustPosture.SHARED_PLANNING,
    "BLOCKED": UnifiedTrustPosture.BLOCKED,
    # PSEUDO and CONTINUOUS_INSIGHT have no legacy equivalent
}
```

**Effort**: 2 person-weeks
**Dependencies**: Enterprise-App platform alignment
**Risk Mitigation**: Maintain legacy API with deprecation warnings

---

### SOL-HIGH-002: Maximum Delegation Depth Enforcement

**Addresses**: HIGH-002 (No Maximum Delegation Depth)

**Solution**: Included in SOL-CRIT-003 (DelegationGraphValidator)

---

### SOL-HIGH-004: Linked Hash Chain State

**Addresses**: HIGH-004 (Hash Chain Doesn't Include Previous)

**Placement**: SDK (Kaizen Trust Module)

**Implementation**:

```python
# Modified crypto.py

def hash_trust_chain_state(
    genesis_id: str,
    capability_ids: list,
    delegation_ids: list,
    constraint_hash: str,
    previous_hash: str = None,  # NEW: Chain linking
) -> str:
    """Compute hash of trust chain state with chain linking."""
    state = {
        "genesis_id": genesis_id,
        "capability_ids": sorted(capability_ids),
        "delegation_ids": sorted(delegation_ids),
        "constraint_hash": constraint_hash,
        "previous_hash": previous_hash or "genesis",  # Link to previous
    }
    return hash_chain(state)

# Modified chain.py

@dataclass
class TrustLineageChain:
    # ... existing fields ...
    state_history: List[str] = field(default_factory=list)  # Hash chain

    def hash(self) -> str:
        """Compute linked hash."""
        previous = self.state_history[-1] if self.state_history else None
        return hash_trust_chain_state(
            genesis_id=self.genesis.id,
            capability_ids=[c.id for c in self.capabilities],
            delegation_ids=[d.id for d in self.delegations],
            constraint_hash=self.constraint_envelope.constraint_hash if self.constraint_envelope else "",
            previous_hash=previous,
        )

    def update_state(self) -> str:
        """Update state and add to history."""
        new_hash = self.hash()
        self.state_history.append(new_hash)
        return new_hash
```

**Effort**: 0.5 person-weeks
**Dependencies**: None
**Risk Mitigation**: Handle legacy chains without history

---

### SOL-HIGH-012 & SOL-HIGH-014: Execution Fencing and Atomic Revocation

**Addresses**: HIGH-012 (Cascade Race), HIGH-014 (No Exec Fencing)

**Placement**: SDK (Kaizen Trust Module)

**Solution Description**:
Implement execution fencing with version tokens to prevent operations during revocation.

**Implementation**:

```python
# NEW: revocation_fence.py

import asyncio
from typing import Dict, Set
from datetime import datetime, timezone, timedelta

class ExecutionFence:
    """Prevents new executions during revocation."""

    def __init__(self):
        self._fenced_agents: Dict[str, datetime] = {}
        self._fence_lock = asyncio.Lock()
        self._fence_ttl = timedelta(minutes=5)

    async def fence_agent(self, agent_id: str) -> str:
        """Fence an agent to prevent new executions."""
        async with self._fence_lock:
            fence_token = f"fence:{agent_id}:{datetime.now(timezone.utc).isoformat()}"
            self._fenced_agents[agent_id] = datetime.now(timezone.utc)
            return fence_token

    async def unfence_agent(self, agent_id: str) -> None:
        """Remove fence after revocation completes."""
        async with self._fence_lock:
            self._fenced_agents.pop(agent_id, None)

    def is_fenced(self, agent_id: str) -> bool:
        """Check if agent is currently fenced."""
        if agent_id not in self._fenced_agents:
            return False

        fence_time = self._fenced_agents[agent_id]
        if datetime.now(timezone.utc) - fence_time > self._fence_ttl:
            # Fence expired
            del self._fenced_agents[agent_id]
            return False

        return True

class AtomicRevocationEngine:
    """Atomic cascade revocation with fencing."""

    def __init__(self, trust_store, fence: ExecutionFence):
        self.trust_store = trust_store
        self.fence = fence

    async def revoke_cascade_atomic(
        self,
        agent_id: str,
        reason: str,
    ) -> list[str]:
        """Atomically revoke agent and all delegatees."""
        # Phase 1: Fence all affected agents
        affected = await self._find_all_delegatees(agent_id)
        all_agents = [agent_id] + affected

        fence_tokens = []
        for aid in all_agents:
            token = await self.fence.fence_agent(aid)
            fence_tokens.append((aid, token))

        try:
            # Phase 2: Wait for in-flight operations
            await asyncio.sleep(0.5)  # Grace period

            # Phase 3: Perform revocations
            revoked = []
            for aid in all_agents:
                try:
                    await self.trust_store.delete_chain(aid, soft_delete=True)
                    revoked.append(aid)
                except Exception as e:
                    logger.error(f"Failed to revoke {aid}: {e}")

            # Phase 4: Invalidate all caches
            for aid in revoked:
                await self.trust_store._invalidate_cache(aid)

            return revoked

        finally:
            # Phase 5: Remove fences
            for aid, _ in fence_tokens:
                await self.fence.unfence_agent(aid)

    async def _find_all_delegatees(self, agent_id: str) -> list[str]:
        """Find all agents that have delegations from this agent."""
        # BFS to find all delegatees
        result = []
        visited = set()
        queue = [agent_id]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            # Find delegatees
            chains = await self.trust_store.list_chains()
            for chain in chains:
                for delegation in chain.delegations:
                    if delegation.delegator_id == current:
                        if delegation.delegatee_id not in visited:
                            queue.append(delegation.delegatee_id)
                            result.append(delegation.delegatee_id)

        return result
```

**Effort**: 2 person-weeks
**Dependencies**: SOL-CRIT-005 (cache invalidation)
**Risk Mitigation**: Fence TTL prevents permanent blocks

### Revocation Latency SLA (Second-Pass)

| Condition                   | Target   | Maximum           | Fallback                               |
| --------------------------- | -------- | ----------------- | -------------------------------------- |
| Normal (push succeeds)      | < 500ms  | 2s                | N/A                                    |
| Push failure, pull fallback | < 30s    | 60s               | Short-lived token expiry               |
| Network partition           | < 5 min  | Token TTL         | Operations blocked after token expires |
| Platform unavailable        | Degraded | Token TTL + grace | Cached trust with 60s reduced TTL      |

---

## Section 3: P2 Solutions (Phase 2 - Week 7-12)

### SOL-HIGH-001: Multi-Signature Genesis Ceremony

**Addresses**: HIGH-001 (No Multi-Sig Genesis)

**Placement**: SDK + Platform

**Solution Description**:
Require m-of-n signatures for genesis record creation with ceremony audit trail.

**Implementation Approach**:

1. Define GenesisCeremonyPolicy (required signers, threshold)
2. Create GenesisProposal that collects signatures
3. Finalize genesis only when threshold reached
4. Store ceremony audit with all signer attestations

**Effort**: 3 person-weeks
**Dependencies**: SOL-CRIT-004 (HSM/KMS for signer keys)

---

### SOL-HIGH-006: Immutable Audit Storage

**Addresses**: HIGH-006 (AUDIT Not Immutable)

**Placement**: SDK (Kaizen) + Platform (anchoring service)

**Solution Description**:
Implement Merkle tree for audit anchors with periodic external anchoring.

**Implementation Approach**:

1. Build Merkle tree of audit anchors
2. Store tree root periodically (hourly) to:
   - Timestamping Authority (TSA)
   - OR: Public blockchain (Ethereum, Polygon)
   - OR: Cloud-native (AWS QLDB, Azure Immutable Blob)
3. Verification queries Merkle proof + external anchor

**Effort**: 4 person-weeks
**Dependencies**: External anchoring service selection

---

### SOL-HIGH-007 & SOL-HIGH-010: Constraint Anomaly Detection

**Addresses**: HIGH-007 (Transaction Splitting), HIGH-010 (Multi-Agent Collusion)

**Placement**: Platform (real-time monitoring service)

**Solution Description**:
Deploy ML-based anomaly detection for constraint gaming patterns.

**Detection Patterns**:

1. Transaction splitting: Aggregate values across time windows
2. Multi-agent collusion: Graph analysis of correlated behavior
3. Temporal gaming: Statistical analysis of execution timing

**Effort**: 4 person-weeks
**Dependencies**: Metrics collection infrastructure

---

## Section 4: Multi-Threat Solutions

### SOL-MULTI-001: Comprehensive Verification Pipeline

**Addresses**: CRIT-002, HIGH-005, HIGH-012

**Description**: Unified verification that always performs full checks for critical operations.

```python
class ComprehensiveVerificationPipeline:
    """Full verification for critical operations."""

    CRITICAL_ACTIONS = {
        "delegate", "revoke", "create_genesis", "modify_constraint",
        "export_data", "delete", "execute_code"
    }

    async def verify(self, agent_id: str, action: str, context: dict) -> VerificationResult:
        """Full verification for critical actions, standard otherwise."""
        level = VerificationLevel.FULL if action in self.CRITICAL_ACTIONS else VerificationLevel.STANDARD

        # Always check fence status
        if self.fence.is_fenced(agent_id):
            return VerificationResult(
                valid=False,
                reason="Agent is fenced for revocation",
                level=level,
            )

        return await self.trust_ops.verify(agent_id, action, level=level, context=context)
```

**Effort**: 1 person-week
**Cross-references**: Integrates with SOL-CRIT-002, SOL-HIGH-014

---

## New Solutions from Second-Pass Review (SOL-RT Series)

### SOL-RT-001: Circuit Breaker Admin Override

```python
class HardenedCircuitBreaker(PostureCircuitBreaker):
    """Circuit breaker with admin override, failure categorization, and jitter."""

    class FailureCategory(Enum):
        SECURITY = "security"          # Counts toward breaker
        LOGIC = "logic"                # Counts toward breaker
        EXTERNAL = "external"          # Does NOT count
        NETWORK = "network"            # Does NOT count

    async def admin_override(self, agent_id: str, admin_id: str, reason: str):
        """Emergency override: force circuit CLOSED. Audit logged."""
        await self._verify_admin_authority(admin_id, "circuit_breaker_override")
        self._state[agent_id] = CircuitState.CLOSED
        self._override_expiry[agent_id] = now() + timedelta(hours=1)
        await self.audit.record("circuit_override", admin_id=admin_id, reason=reason)
```

### SOL-RT-002: Declarative-Only Constraints with Anti-Gaming Measures (v1)

Reference the updated `04-constraint-extensibility-design.md` which now restricts v1 to `DeclarativeConstraintDimension` only. Arbitrary code execution via custom constraint dimensions is deferred to v2 behind a feature flag, ensuring the attack surface remains minimal in initial deployments.

**Transaction Splitting Mitigation**: Declarative constraints support `window` and `aggregate` operators that evaluate constraints across a sliding time window rather than per-transaction:

```python
# Example: Prevent splitting a $10,000 limit into 100 x $100
rules:
  - field: "amount"
    operator: "le"
    threshold: 10000
    result: "hard_limit"
  - field: "amount"
    operator: "aggregate_le"        # Sum over sliding window
    threshold: 10000
    window: "24h"                    # 24-hour rolling window
    aggregate: "sum"                 # Sum all transactions
    group_by: "agent_id"
    result: "hard_limit"
    reason: "Aggregate spend {value} exceeds {threshold} in 24h window"
```

**Sybil Mitigation**: Agent registration requires human-verified identity (via genesis ceremony). Each agent's trust chain must trace back to a verified `HumanOrigin`. The `PseudoAgentFactory` enforces that no single human can register more than `MAX_AGENTS_PER_HUMAN` agents (configurable, default 10). Combined with the existing peer verification attestation requirement, this prevents trivial Sybil attacks.

**Sliding Window Boundary Hardening**: A naive fixed-window aggregate (e.g., "sum over 00:00-23:59 UTC") is vulnerable to boundary attacks where an adversary spends $9,999 at 23:59 and $9,999 at 00:01, effectively spending $19,998 within 2 minutes. The `aggregate_le` operator MUST use a **true sliding window** (not calendar-aligned buckets):

```python
class SlidingWindowAggregator:
    """True sliding window aggregate — immune to boundary attacks."""

    async def aggregate(
        self, agent_id: str, field: str, window: timedelta
    ) -> float:
        """Sum all values for agent_id within [now - window, now]."""
        cutoff = datetime.now(timezone.utc) - window
        # Query: SELECT SUM(amount) FROM actions
        #        WHERE agent_id = ? AND timestamp >= cutoff
        return await self.store.sum_since(agent_id, field, cutoff)
```

Additionally, overlapping windows provide defense-in-depth:

```yaml
rules:
  # Per-transaction limit
  - field: "amount"
    operator: "le"
    threshold: 10000
    result: "hard_limit"
  # 1-hour rolling window (catches rapid burst)
  - field: "amount"
    operator: "aggregate_le"
    threshold: 10000
    window: "1h"
    aggregate: "sum"
    group_by: "agent_id"
    result: "hard_limit"
  # 24-hour rolling window (catches distributed splitting)
  - field: "amount"
    operator: "aggregate_le"
    threshold: 10000
    window: "24h"
    aggregate: "sum"
    group_by: "agent_id"
    result: "hard_limit"
```

The combination of per-transaction limits + short window + long window closes the boundary gaming vector. An adversary cannot split across boundaries because the sliding window moves continuously — there are no fixed boundaries to exploit.

**Acknowledged Limitation**: Constraint gaming mitigations are probabilistic, not absolute. Novel attack sequences will always be possible. The defense-in-depth approach (declarative rules + true sliding windows + overlapping windows + identity binding + anomaly detection in v2) reduces the attack surface iteratively.

### SOL-RT-003: Cross-Org Dispute Resolution

Reference the updated `04-federated-trust-protocol-design.md` which now includes TLA enforcement, escalation ladder, and arbitration mechanisms. Cross-organization trust disputes follow a three-tier resolution process: automated policy resolution, human mediator escalation, and final binding arbitration with cryptographic audit trail.

### SOL-RT-004: Supply Chain Security

Add dependency verification requirements for the trust module's cryptographic dependencies. All cryptographic libraries (PyNaCl, cryptography, python-jose) must be pinned to exact versions with hash verification in requirements files. A quarterly dependency audit process must verify no known CVEs exist in the trust module's dependency tree.

**Enforcement Mechanism** (not just process):

```yaml
# pyproject.toml — enforced via CI pipeline
[tool.supply-chain]
# 1. Exact version pinning with hash verification
trust_dependencies = [
    "PyNaCl==1.5.0 --hash=sha256:8ac7448f09ab85811607bdd21ec2464495ac8b7c66d146bf545b0f08fb9220ba",
    "cryptography==42.0.5 --hash=sha256:...",
    "python-jose==3.3.0 --hash=sha256:...",
]

# 2. SBOM generation (CycloneDX format, runs in CI)
[tool.sbom]
format = "cyclonedx"
output = "trust-module-sbom.json"
include_transitive = true

# 3. Sigstore verification for releases
[tool.sigstore]
verify_on_install = true
transparency_log = "rekor.sigstore.dev"
```

```python
# CI check: verify_supply_chain.py (runs pre-merge)
class SupplyChainVerifier:
    """Automated supply chain verification — runs in CI, blocks merge on failure."""

    def verify_all(self) -> VerificationReport:
        report = VerificationReport()
        # 1. Hash verification (pip install --require-hashes)
        report.hash_check = self._verify_hashes()
        # 2. CVE scan (pip-audit or safety)
        report.cve_scan = self._run_cve_scan()
        # 3. SBOM diff (detect new transitive dependencies)
        report.sbom_diff = self._diff_sbom_against_baseline()
        # 4. License compliance (reject GPL in trust module)
        report.license_check = self._verify_licenses()
        return report
```

**Quarterly audit** produces a signed attestation stored alongside the release. This is enforced by CI (not just documented as a process).

### SOL-RT-005: Multi-Region Trust Replication

Add hub-and-spoke replication model with < 2s lag SLA for trust state. A designated primary region holds the authoritative trust store; secondary regions receive push-based replication via an append-only replication log. If replication lag exceeds 2s, secondary regions fall back to synchronous verification against the primary before accepting trust-dependent operations.

**Write Forwarding Architecture**:

```python
class MultiRegionTrustStore:
    """Hub-and-spoke trust replication with write forwarding."""

    def __init__(self, region: str, primary_region: str):
        self._region = region
        self._primary_region = primary_region
        self._is_primary = (region == primary_region)
        self._replication_log = AppendOnlyReplicationLog()
        self._lag_monitor = ReplicationLagMonitor(threshold_ms=2000)

    async def write_trust_state(self, agent_id: str, state: TrustState):
        """All writes go to primary. Secondary regions forward."""
        if self._is_primary:
            # Primary: write locally, then push to replication log
            await self._local_store.write(agent_id, state)
            await self._replication_log.append(
                TrustStateChange(agent_id=agent_id, state=state, version=state.version)
            )
        else:
            # Secondary: forward write to primary, wait for ack
            await self._forward_to_primary(agent_id, state)

    async def read_trust_state(self, agent_id: str) -> TrustState:
        """Reads from local replica. Falls back to primary if lag > 2s."""
        lag = await self._lag_monitor.current_lag()
        if lag.total_seconds() > 2:
            # Lag exceeds SLA — synchronous read from primary
            return await self._read_from_primary(agent_id)
        if lag.total_seconds() > 10:
            # Circuit breaker: block operations entirely
            raise TrustUnavailableError(
                f"Replication lag {lag}s exceeds circuit breaker threshold (10s). "
                f"Trust operations blocked until replication catches up."
            )
        return await self._local_store.read(agent_id)

    async def _replicate_from_log(self):
        """Background task: consume replication log and apply locally."""
        async for change in self._replication_log.subscribe(self._region):
            await self._local_store.apply_change(change)
            self._lag_monitor.record_applied(change.timestamp)
```

**Lag Behavior Table**:

| Replication Lag  | Behavior           | Read Source        | Write Target       |
| ---------------- | ------------------ | ------------------ | ------------------ |
| 0-2s (normal)    | Full local reads   | Local replica      | Forward to primary |
| 2-10s (degraded) | Synchronous reads  | Primary (direct)   | Forward to primary |
| 10s+ (critical)  | Operations blocked | N/A                | N/A                |
| Primary down     | Promote secondary  | Promoted secondary | Promoted secondary |

**Primary Failover**: If the primary region is unavailable for > 30 seconds, the secondary with the lowest replication lag is promoted via leader election among the region coordinators. All pending replication log entries from the old primary are reconciled after recovery using the same sticky-revocation merge strategy from Section 8 (split-brain resolution).

**Leader Election Implementation**: Rather than implementing Raft consensus from scratch (which would introduce significant complexity and verification burden), the leader election MUST delegate to a battle-tested distributed coordination service:

| Option                 | Protocol        | Recommendation                                                                                   |
| ---------------------- | --------------- | ------------------------------------------------------------------------------------------------ |
| **etcd** (recommended) | Raft consensus  | Native leader election API via `election.Campaign()`. Used by Kubernetes, well-proven at scale.  |
| **HashiCorp Consul**   | Raft consensus  | Session-based leader election via `consul lock`. Integrates with Vault for trust key management. |
| **Apache ZooKeeper**   | ZAB (Raft-like) | Ephemeral sequential znodes for election. Mature but operationally heavier.                      |

```python
class RegionCoordinator:
    """Region failover coordinator backed by etcd leader election."""

    def __init__(self, etcd_endpoints: list[str], region_id: str):
        import etcd3
        self._client = etcd3.client(host=etcd_endpoints[0])
        self._region_id = region_id
        self._election_key = "/eatp/trust-store/leader"

    async def campaign_for_leadership(self) -> bool:
        """Participate in leader election. Returns True if this region wins."""
        election = self._client.election(self._election_key)
        election.campaign(self._region_id.encode())
        # If we reach here, we are the leader
        return True

    async def watch_leader(self) -> str:
        """Watch for leader changes. Returns new leader region ID."""
        election = self._client.election(self._election_key)
        leader = election.leader()
        return leader.value.decode()

    async def resign_leadership(self):
        """Resign leadership (e.g., during graceful shutdown)."""
        election = self._client.election(self._election_key)
        election.resign()
```

The election lease TTL should be set to 10 seconds (3x the 30-second failover detection threshold divided by typical heartbeat intervals), ensuring timely promotion while avoiding false failovers from transient network hiccups.

---

## Section 5: Solution Dependency Graph

```
SOL-CRIT-001 (Salt) ─────────────────────────────────────┐
                                                          │
SOL-CRIT-004 (HSM/KMS) ──┬─────────────────────┐         │
                         │                      │         │
SOL-CRIT-002 (Delegation Sig) ──┐              │         │
                                │              │         ▼
SOL-CRIT-003 (Cycle Detection) ─┼───> SOL-HIGH-001 (Multi-Sig Genesis)
                                │              │
SOL-HIGH-002 (Depth Limit) ─────┘              │
                                               │
SOL-CRIT-005 (Cache Invalidation) ─────────────┼──> SOL-HIGH-012 (Atomic Revoke)
                                               │          │
SOL-HIGH-014 (Exec Fencing) ───────────────────┘          │
                                                          ▼
SOL-CRIT-006 (Core SDK Trust) ──┬──> SOL-HIGH-006 (Immutable Audit)
                                │
SOL-CRIT-007 (DataFlow Trust) ──┤
                                │
SOL-CRIT-008 (Posture Align) ───┘

SOL-HIGH-007 (Splitting Detect) ──┬──> SOL-HIGH-010 (Collusion Detect)
                                  │
SOL-HIGH-008 (Temporal Detect) ───┘
```

---

## Section 6: Implementation Roadmap

### Phase 0: Immediate (Week 1-2)

| Solution                          | Effort     | Owner    |
| --------------------------------- | ---------- | -------- |
| SOL-CRIT-001 (Salt)               | 0.5 wk     | SDK Team |
| SOL-CRIT-002 (Delegation Sig)     | 1 wk       | SDK Team |
| SOL-CRIT-003 (Cycle Detection)    | 1 wk       | SDK Team |
| SOL-CRIT-005 (Cache Invalidation) | 1 wk       | SDK Team |
| **Total**                         | **3.5 wk** |          |

### Phase 1: Foundation (Week 3-6)

| Solution                         | Effort      | Owner          |
| -------------------------------- | ----------- | -------------- |
| SOL-CRIT-004 (HSM/KMS)           | 2 wk        | SDK Team       |
| SOL-CRIT-006 (Core SDK Trust)    | 2 wk        | Core Team      |
| SOL-CRIT-007 (DataFlow Trust)    | 2 wk        | DataFlow Team  |
| SOL-CRIT-008 (Posture Alignment) | 2 wk        | SDK + Platform |
| SOL-HIGH-004 (Linked Hashing)    | 0.5 wk      | SDK Team       |
| SOL-HIGH-012/14 (Atomic Revoke)  | 2 wk        | SDK Team       |
| **Total**                        | **10.5 wk** |                |

### Phase 2: Hardening (Week 7-12)

| Solution                            | Effort    | Owner          |
| ----------------------------------- | --------- | -------------- |
| SOL-HIGH-001 (Multi-Sig Genesis)    | 3 wk      | SDK + Platform |
| SOL-HIGH-006 (Immutable Audit)      | 4 wk      | Platform Team  |
| SOL-HIGH-007/10 (Anomaly Detection) | 4 wk      | Platform Team  |
| **Total**                           | **11 wk** |                |

---

## Document Metadata

| Attribute      | Value                         |
| -------------- | ----------------------------- |
| Version        | 2.0                           |
| Created        | 2026-02-07                    |
| Author         | Deep Analysis Specialist      |
| Classification | Internal - Security Sensitive |
| Review Cycle   | After each phase completion   |
