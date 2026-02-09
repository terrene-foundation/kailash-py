# Trust Testing Strategy

## Overview

This document defines the 3-tier testing strategy for CARE/EATP trust features. The strategy enforces real infrastructure usage in integration and E2E tests (NO MOCKING) to ensure cryptographic operations and distributed trust propagation work correctly in production-like environments.

## Testing Principles

### NO MOCKING Policy (Tiers 2-3)

**CRITICAL**: Integration and E2E tests MUST use real infrastructure.

| Tier           | Mocking       | Infrastructure         | Timeout |
| -------------- | ------------- | ---------------------- | ------- |
| 1: Unit        | Allowed       | In-memory only         | <1s     |
| 2: Integration | **FORBIDDEN** | Real PostgreSQL, Redis | <5s     |
| 3: E2E         | **FORBIDDEN** | Full Docker stack      | <10s    |

### What IS Allowed in All Tiers

- `freeze_time()` for deterministic time-based testing
- `random.seed()` for deterministic cryptographic test vectors
- `patch.dict(os.environ)` for environment configuration
- In-memory implementations (e.g., `InMemoryTrustStore`) that execute real logic

### What IS Forbidden in Tiers 2-3

- `@patch()` or `MagicMock()` for SDK components
- Stubbed database responses
- Fake cryptographic operations
- Mocked signature verification

---

## Tier 1: Unit Tests

### Purpose

Test individual components in isolation with fast execution.

### Location

```
apps/kailash-kaizen/tests/unit/trust/
```

### Coverage Areas

| Component                   | Test File                      | Coverage Target |
| --------------------------- | ------------------------------ | --------------- |
| Crypto primitives           | `test_crypto.py`               | 100%            |
| Trust chain data structures | `test_chain.py`                | 100%            |
| Constraint validation logic | `test_constraint_validator.py` | 100%            |
| Posture mapping             | `test_postures.py`             | 100%            |
| Exception handling          | `test_exceptions.py`           | 100%            |

### Unit Test Examples

```python
# tests/unit/trust/test_crypto.py
"""
Unit tests for cryptographic primitives.

These tests verify Ed25519 operations work correctly.
Real crypto operations - no mocking needed.
"""

import pytest
from kaizen.trust.crypto import (
    generate_keypair,
    sign,
    verify_signature,
    hash_chain,
    serialize_for_signing,
)


class TestKeypairGeneration:
    """Test Ed25519 keypair generation."""

    def test_generate_keypair_returns_valid_keys(self):
        """Generated keys should be valid Ed25519 keys."""
        private_key, public_key = generate_keypair()

        # Keys should be base64-encoded strings
        assert isinstance(private_key, str)
        assert isinstance(public_key, str)

        # Private key is 64 bytes (512 bits), public key is 32 bytes
        import base64
        priv_bytes = base64.b64decode(private_key)
        pub_bytes = base64.b64decode(public_key)

        assert len(priv_bytes) == 64  # Ed25519 private key
        assert len(pub_bytes) == 32   # Ed25519 public key

    def test_keypairs_are_unique(self):
        """Each keypair generation should produce unique keys."""
        key1 = generate_keypair()
        key2 = generate_keypair()

        assert key1[0] != key2[0]  # Private keys differ
        assert key1[1] != key2[1]  # Public keys differ


class TestSignatureOperations:
    """Test Ed25519 signature creation and verification."""

    def test_sign_and_verify_succeeds(self):
        """Signature should verify with correct key."""
        private_key, public_key = generate_keypair()
        message = {"agent_id": "test-001", "action": "analyze"}

        signature = sign(message, private_key)
        is_valid = verify_signature(message, signature, public_key)

        assert is_valid is True

    def test_verify_fails_with_wrong_key(self):
        """Signature should fail with different key."""
        priv1, pub1 = generate_keypair()
        priv2, pub2 = generate_keypair()

        message = {"agent_id": "test-001"}
        signature = sign(message, priv1)

        # Verify with wrong public key
        is_valid = verify_signature(message, signature, pub2)

        assert is_valid is False

    def test_verify_fails_with_tampered_message(self):
        """Signature should fail if message is tampered."""
        private_key, public_key = generate_keypair()
        original = {"agent_id": "test-001", "action": "analyze"}
        tampered = {"agent_id": "test-001", "action": "delete"}

        signature = sign(original, private_key)

        is_valid = verify_signature(tampered, signature, public_key)

        assert is_valid is False

    def test_signature_is_deterministic_for_same_input(self):
        """Same input should produce same signature."""
        import random
        random.seed(42)  # Deterministic randomness

        private_key, public_key = generate_keypair()
        message = {"agent_id": "test-001"}

        sig1 = sign(message, private_key)
        sig2 = sign(message, private_key)

        # Ed25519 is deterministic
        assert sig1 == sig2


class TestHashChain:
    """Test hash chain computation for trust chains."""

    def test_hash_chain_is_deterministic(self):
        """Same chain state should produce same hash."""
        chain_state = {
            "genesis_id": "gen-001",
            "agent_id": "agent-001",
            "capabilities": ["read", "analyze"],
        }

        hash1 = hash_chain(chain_state)
        hash2 = hash_chain(chain_state)

        assert hash1 == hash2

    def test_hash_chain_changes_with_state(self):
        """Different chain state should produce different hash."""
        state1 = {"genesis_id": "gen-001", "capabilities": ["read"]}
        state2 = {"genesis_id": "gen-001", "capabilities": ["read", "write"]}

        hash1 = hash_chain(state1)
        hash2 = hash_chain(state2)

        assert hash1 != hash2


class TestSerializeForSigning:
    """Test deterministic serialization for signatures."""

    def test_serialize_is_deterministic(self):
        """Serialization should be deterministic regardless of dict order."""
        data1 = {"b": 2, "a": 1, "c": 3}
        data2 = {"a": 1, "c": 3, "b": 2}

        ser1 = serialize_for_signing(data1)
        ser2 = serialize_for_signing(data2)

        assert ser1 == ser2

    def test_serialize_handles_nested_dicts(self):
        """Nested dictionaries should serialize deterministically."""
        data = {
            "outer": {"inner_b": 2, "inner_a": 1},
            "simple": "value",
        }

        serialized = serialize_for_signing(data)

        # Should be valid JSON bytes
        import json
        parsed = json.loads(serialized)
        assert parsed["outer"]["inner_a"] == 1
```

### Unit Test: Constraint Validation

```python
# tests/unit/trust/test_constraint_validator.py
"""
Unit tests for constraint validation logic.

Tests constraint evaluation without database access.
"""

import pytest
from datetime import datetime, timezone
from freezegun import freeze_time
from kaizen.trust import (
    ConstraintValidator,
    ConstraintViolation,
    ValidationResult,
    Constraint,
    ConstraintType,
)


class TestResourceLimitConstraints:
    """Test resource limit constraint validation."""

    def test_api_call_limit_not_exceeded(self):
        """API calls within limit should pass."""
        validator = ConstraintValidator()

        constraint = Constraint(
            id="resource-001",
            constraint_type=ConstraintType.RESOURCE_LIMIT,
            parameters={"max_api_calls": 100},
            enforced_by="runtime",
        )

        result = validator.validate(
            constraint=constraint,
            context={"current_api_calls": 50},
        )

        assert result.valid is True
        assert len(result.violations) == 0

    def test_api_call_limit_exceeded(self):
        """API calls exceeding limit should fail."""
        validator = ConstraintValidator()

        constraint = Constraint(
            id="resource-001",
            constraint_type=ConstraintType.RESOURCE_LIMIT,
            parameters={"max_api_calls": 100},
            enforced_by="runtime",
        )

        result = validator.validate(
            constraint=constraint,
            context={"current_api_calls": 150},
        )

        assert result.valid is False
        assert len(result.violations) == 1
        assert result.violations[0].constraint_id == "resource-001"


class TestTimeWindowConstraints:
    """Test time-based constraint validation."""

    @freeze_time("2025-02-07 14:00:00", tz_offset=0)
    def test_within_business_hours(self):
        """Actions during business hours should pass."""
        validator = ConstraintValidator()

        constraint = Constraint(
            id="time-001",
            constraint_type=ConstraintType.TIME_WINDOW,
            parameters={
                "start_hour": 9,
                "end_hour": 17,
                "timezone": "UTC",
            },
            enforced_by="runtime",
        )

        result = validator.validate(constraint=constraint, context={})

        assert result.valid is True

    @freeze_time("2025-02-07 22:00:00", tz_offset=0)
    def test_outside_business_hours(self):
        """Actions outside business hours should fail."""
        validator = ConstraintValidator()

        constraint = Constraint(
            id="time-001",
            constraint_type=ConstraintType.TIME_WINDOW,
            parameters={
                "start_hour": 9,
                "end_hour": 17,
                "timezone": "UTC",
            },
            enforced_by="runtime",
        )

        result = validator.validate(constraint=constraint, context={})

        assert result.valid is False
        assert "time_window" in result.violations[0].reason.lower()


class TestDataScopeConstraints:
    """Test data scope constraint validation."""

    def test_allowed_table_access(self):
        """Access to allowed tables should pass."""
        validator = ConstraintValidator()

        constraint = Constraint(
            id="data-001",
            constraint_type=ConstraintType.DATA_SCOPE,
            parameters={
                "allowed_tables": ["transactions", "users"],
                "denied_columns": ["ssn", "password"],
            },
            enforced_by="dataflow",
        )

        result = validator.validate(
            constraint=constraint,
            context={
                "requested_table": "transactions",
                "requested_columns": ["id", "amount", "date"],
            },
        )

        assert result.valid is True

    def test_denied_column_access(self):
        """Access to denied columns should fail."""
        validator = ConstraintValidator()

        constraint = Constraint(
            id="data-001",
            constraint_type=ConstraintType.DATA_SCOPE,
            parameters={
                "allowed_tables": ["users"],
                "denied_columns": ["ssn", "password"],
            },
            enforced_by="dataflow",
        )

        result = validator.validate(
            constraint=constraint,
            context={
                "requested_table": "users",
                "requested_columns": ["id", "name", "ssn"],  # ssn is denied
            },
        )

        assert result.valid is False
        assert "ssn" in str(result.violations[0])
```

---

## Tier 2: Integration Tests

### Purpose

Test component interactions with real infrastructure. NO MOCKING.

### Location

```
apps/kailash-kaizen/tests/integration/trust/
```

### Infrastructure Requirements

```bash
# Start Docker services before running integration tests
./tests/utils/test-env up

# Services required:
# - PostgreSQL: localhost:5434
# - Redis: localhost:6380
```

### Coverage Areas

| Component Integration       | Test File                          | Requirements        |
| --------------------------- | ---------------------------------- | ------------------- |
| Trust store + PostgreSQL    | `test_postgres_store.py`           | Real PostgreSQL     |
| Trust operations end-to-end | `test_trust_chain_verification.py` | Real crypto + store |
| Secure messaging            | `test_secure_messaging.py`         | Real Ed25519        |
| Health monitoring           | `test_health_monitoring.py`        | Real registry       |
| Cache + store               | `test_cache_integration.py`        | Real Redis          |

### Integration Test Examples

```python
# tests/integration/trust/test_trust_operations.py
"""
Integration tests for TrustOperations with real PostgreSQL.

NO MOCKING - all operations use real database and crypto.
"""

import pytest
from datetime import datetime, timedelta
from kaizen.trust import (
    TrustOperations,
    PostgresTrustStore,
    OrganizationalAuthorityRegistry,
    TrustKeyManager,
    CapabilityRequest,
    CapabilityType,
    VerificationLevel,
    generate_keypair,
)


@pytest.fixture
async def postgres_store():
    """
    Real PostgreSQL trust store.

    NO MOCKING - connects to real Docker PostgreSQL.
    """
    store = PostgresTrustStore(
        connection_string="postgresql://test_user:test_password@localhost:5434/kailash_test"
    )
    await store.initialize()

    yield store

    # Cleanup test data
    await store.close()


@pytest.fixture
async def trust_operations(postgres_store):
    """
    Fully configured TrustOperations with real store.
    """
    registry = OrganizationalAuthorityRegistry()
    key_manager = TrustKeyManager()

    ops = TrustOperations(
        authority_registry=registry,
        key_manager=key_manager,
        trust_store=postgres_store,
    )
    await ops.initialize()

    return ops


class TestTrustEstablishment:
    """
    Integration tests for ESTABLISH operation.

    Tests real database writes and cryptographic signing.
    """

    @pytest.mark.integration
    @pytest.mark.requires_docker
    async def test_establish_creates_trust_chain(self, trust_operations):
        """
        ESTABLISH should create trust chain in database.
        """
        # Establish trust for new agent
        chain = await trust_operations.establish(
            agent_id=f"test-agent-{datetime.utcnow().timestamp()}",
            authority_id="test-org-001",
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACCESS,
                ),
            ],
        )

        # Verify chain was created
        assert chain is not None
        assert chain.genesis is not None
        assert chain.genesis.signature != ""  # Real signature

        # Verify chain is in database
        retrieved = await trust_operations.get_chain(chain.genesis.agent_id)
        assert retrieved is not None
        assert retrieved.genesis.id == chain.genesis.id

    @pytest.mark.integration
    @pytest.mark.requires_docker
    async def test_establish_with_constraints(self, trust_operations):
        """
        ESTABLISH with constraints should store them correctly.
        """
        chain = await trust_operations.establish(
            agent_id=f"test-constrained-{datetime.utcnow().timestamp()}",
            authority_id="test-org-001",
            capabilities=[
                CapabilityRequest(
                    capability="read_data",
                    capability_type=CapabilityType.ACCESS,
                    constraints=["read_only", "no_pii"],
                ),
            ],
        )

        assert len(chain.capabilities) == 1
        assert "read_only" in chain.capabilities[0].constraints
        assert "no_pii" in chain.capabilities[0].constraints


class TestTrustVerification:
    """
    Integration tests for VERIFY operation.

    Tests real signature verification and constraint checking.
    """

    @pytest.mark.integration
    @pytest.mark.requires_docker
    async def test_verify_valid_action(self, trust_operations):
        """
        VERIFY should succeed for valid action with capability.
        """
        agent_id = f"test-verify-{datetime.utcnow().timestamp()}"

        # First establish
        await trust_operations.establish(
            agent_id=agent_id,
            authority_id="test-org-001",
            capabilities=[
                CapabilityRequest(capability="analyze_data"),
            ],
        )

        # Then verify
        result = await trust_operations.verify(
            agent_id=agent_id,
            action="analyze_data",
        )

        assert result.valid is True
        assert result.level in [
            VerificationLevel.QUICK,
            VerificationLevel.STANDARD,
            VerificationLevel.FULL,
        ]

    @pytest.mark.integration
    @pytest.mark.requires_docker
    async def test_verify_denied_action(self, trust_operations):
        """
        VERIFY should fail for action without capability.
        """
        agent_id = f"test-deny-{datetime.utcnow().timestamp()}"

        # Establish with limited capabilities
        await trust_operations.establish(
            agent_id=agent_id,
            authority_id="test-org-001",
            capabilities=[
                CapabilityRequest(capability="read_data"),
            ],
        )

        # Try to verify action not in capabilities
        result = await trust_operations.verify(
            agent_id=agent_id,
            action="delete_data",  # Not granted
        )

        assert result.valid is False
        assert "capability" in result.reason.lower()

    @pytest.mark.integration
    @pytest.mark.requires_docker
    async def test_verify_expired_chain(self, trust_operations):
        """
        VERIFY should fail for expired trust chain.
        """
        agent_id = f"test-expired-{datetime.utcnow().timestamp()}"

        # Establish with past expiration
        chain = await trust_operations.establish(
            agent_id=agent_id,
            authority_id="test-org-001",
            capabilities=[
                CapabilityRequest(capability="analyze_data"),
            ],
            expires_at=datetime.utcnow() - timedelta(hours=1),  # Already expired
        )

        result = await trust_operations.verify(
            agent_id=agent_id,
            action="analyze_data",
        )

        assert result.valid is False
        assert "expired" in result.reason.lower()


class TestTrustDelegation:
    """
    Integration tests for DELEGATE operation.

    Tests real delegation chain creation.
    """

    @pytest.mark.integration
    @pytest.mark.requires_docker
    async def test_delegate_to_child_agent(self, trust_operations):
        """
        DELEGATE should create valid delegation record.
        """
        parent_id = f"parent-{datetime.utcnow().timestamp()}"
        child_id = f"child-{datetime.utcnow().timestamp()}"

        # Establish parent with delegation capability
        await trust_operations.establish(
            agent_id=parent_id,
            authority_id="test-org-001",
            capabilities=[
                CapabilityRequest(capability="analyze_data"),
                CapabilityRequest(
                    capability="delegate",
                    capability_type=CapabilityType.DELEGATION,
                ),
            ],
        )

        # Delegate to child
        delegation = await trust_operations.delegate(
            from_agent_id=parent_id,
            to_agent_id=child_id,
            capabilities=["analyze_data"],
            constraints={"max_records": 1000},
        )

        assert delegation is not None
        assert delegation.from_agent_id == parent_id
        assert delegation.to_agent_id == child_id

        # Child should now be verifiable
        result = await trust_operations.verify(
            agent_id=child_id,
            action="analyze_data",
        )

        assert result.valid is True

    @pytest.mark.integration
    @pytest.mark.requires_docker
    async def test_delegate_cannot_exceed_parent_capabilities(self, trust_operations):
        """
        DELEGATE should fail if delegating more than parent has.
        """
        parent_id = f"parent-limited-{datetime.utcnow().timestamp()}"
        child_id = f"child-limited-{datetime.utcnow().timestamp()}"

        # Parent has limited capabilities
        await trust_operations.establish(
            agent_id=parent_id,
            authority_id="test-org-001",
            capabilities=[
                CapabilityRequest(capability="read_data"),
            ],
        )

        # Try to delegate capability parent doesn't have
        with pytest.raises(Exception) as exc_info:
            await trust_operations.delegate(
                from_agent_id=parent_id,
                to_agent_id=child_id,
                capabilities=["delete_data"],  # Parent doesn't have this
            )

        assert "capability" in str(exc_info.value).lower()
```

### Integration Test: Secure Messaging

```python
# tests/integration/trust/test_secure_messaging.py
"""
Integration tests for secure agent-to-agent messaging.

NO MOCKING - real Ed25519 signatures and verification.
"""

import pytest
from datetime import datetime
from kaizen.trust import (
    SecureChannel,
    MessageSigner,
    MessageVerifier,
    InMemoryReplayProtection,
    generate_keypair,
)


@pytest.fixture
def agent_keypairs():
    """Generate real keypairs for test agents."""
    return {
        "agent-a": generate_keypair(),
        "agent-b": generate_keypair(),
        "agent-c": generate_keypair(),
    }


@pytest.fixture
def public_key_registry(agent_keypairs):
    """Registry of public keys for verification."""
    return {
        agent_id: keys[1]  # Public key
        for agent_id, keys in agent_keypairs.items()
    }


class TestSecureChannelMessaging:
    """
    Integration tests for SecureChannel.

    Tests real cryptographic operations.
    """

    @pytest.mark.integration
    async def test_send_and_receive_message(
        self,
        agent_keypairs,
        public_key_registry,
    ):
        """
        Messages should be signed and verified correctly.
        """
        # Create channels for two agents
        priv_a, pub_a = agent_keypairs["agent-a"]
        priv_b, pub_b = agent_keypairs["agent-b"]

        channel_a = SecureChannel(
            agent_id="agent-a",
            private_key=priv_a,
            public_key_lookup=lambda aid: public_key_registry.get(aid),
            replay_protection=InMemoryReplayProtection(),
        )

        channel_b = SecureChannel(
            agent_id="agent-b",
            private_key=priv_b,
            public_key_lookup=lambda aid: public_key_registry.get(aid),
            replay_protection=InMemoryReplayProtection(),
        )

        # Agent A sends message to Agent B
        envelope = await channel_a.create_message(
            to_agent="agent-b",
            payload={"task": "analyze", "data_id": "123"},
        )

        # Agent B receives and verifies
        verified_payload = await channel_b.receive_message(envelope)

        assert verified_payload["task"] == "analyze"
        assert verified_payload["data_id"] == "123"

    @pytest.mark.integration
    async def test_tampered_message_rejected(
        self,
        agent_keypairs,
        public_key_registry,
    ):
        """
        Tampered messages should be rejected.
        """
        priv_a, _ = agent_keypairs["agent-a"]
        priv_b, _ = agent_keypairs["agent-b"]

        channel_a = SecureChannel(
            agent_id="agent-a",
            private_key=priv_a,
            public_key_lookup=lambda aid: public_key_registry.get(aid),
            replay_protection=InMemoryReplayProtection(),
        )

        channel_b = SecureChannel(
            agent_id="agent-b",
            private_key=priv_b,
            public_key_lookup=lambda aid: public_key_registry.get(aid),
            replay_protection=InMemoryReplayProtection(),
        )

        # Create valid message
        envelope = await channel_a.create_message(
            to_agent="agent-b",
            payload={"amount": 100},
        )

        # Tamper with payload
        envelope.payload["amount"] = 1000000

        # Verification should fail
        with pytest.raises(Exception) as exc_info:
            await channel_b.receive_message(envelope)

        assert "signature" in str(exc_info.value).lower()

    @pytest.mark.integration
    async def test_replay_attack_prevented(
        self,
        agent_keypairs,
        public_key_registry,
    ):
        """
        Replayed messages should be rejected.
        """
        priv_a, _ = agent_keypairs["agent-a"]
        priv_b, _ = agent_keypairs["agent-b"]

        replay_protection = InMemoryReplayProtection()

        channel_a = SecureChannel(
            agent_id="agent-a",
            private_key=priv_a,
            public_key_lookup=lambda aid: public_key_registry.get(aid),
            replay_protection=replay_protection,
        )

        channel_b = SecureChannel(
            agent_id="agent-b",
            private_key=priv_b,
            public_key_lookup=lambda aid: public_key_registry.get(aid),
            replay_protection=replay_protection,
        )

        # Create and receive message
        envelope = await channel_a.create_message(
            to_agent="agent-b",
            payload={"action": "transfer"},
        )

        await channel_b.receive_message(envelope)

        # Try to replay same message
        with pytest.raises(Exception) as exc_info:
            await channel_b.receive_message(envelope)

        assert "replay" in str(exc_info.value).lower()
```

---

## Tier 3: E2E Tests

### Purpose

Test complete user workflows from genesis to audit. NO MOCKING.

### Location

```
apps/kailash-kaizen/tests/e2e/trust/
```

### Infrastructure Requirements

```bash
# Full Docker stack required
./tests/utils/test-env up

# All services:
# - PostgreSQL: localhost:5434
# - Redis: localhost:6380
# - Ollama: localhost:11435 (for AI-agent tests)
```

### E2E Test Examples

```python
# tests/e2e/trust/test_trust_lifecycle.py
"""
End-to-end tests for complete trust lifecycle.

NO MOCKING - tests full workflow from genesis to audit.
"""

import pytest
from datetime import datetime, timedelta
from kaizen.trust import (
    TrustOperations,
    PostgresTrustStore,
    PostgresAuditStore,
    OrganizationalAuthorityRegistry,
    TrustKeyManager,
    AuditQueryService,
    CapabilityRequest,
    CapabilityType,
    TrustPostureMapper,
    TrustPosture,
)


@pytest.fixture
async def full_trust_infrastructure():
    """
    Complete trust infrastructure with real services.
    """
    # Real PostgreSQL stores
    trust_store = PostgresTrustStore(
        connection_string="postgresql://test_user:test_password@localhost:5434/kailash_test"
    )
    audit_store = PostgresAuditStore(
        connection_string="postgresql://test_user:test_password@localhost:5434/kailash_test"
    )

    await trust_store.initialize()
    await audit_store.initialize()

    registry = OrganizationalAuthorityRegistry()
    key_manager = TrustKeyManager()

    trust_ops = TrustOperations(
        authority_registry=registry,
        key_manager=key_manager,
        trust_store=trust_store,
        audit_store=audit_store,
    )
    await trust_ops.initialize()

    yield {
        "trust_ops": trust_ops,
        "trust_store": trust_store,
        "audit_store": audit_store,
        "audit_service": AuditQueryService(audit_store),
    }

    await trust_store.close()
    await audit_store.close()


class TestFullTrustLifecycle:
    """
    E2E tests for complete trust lifecycle.
    """

    @pytest.mark.e2e
    @pytest.mark.requires_docker
    @pytest.mark.timeout(30)
    async def test_genesis_to_audit_flow(self, full_trust_infrastructure):
        """
        Test complete flow: genesis -> verify -> action -> audit.
        """
        trust_ops = full_trust_infrastructure["trust_ops"]
        audit_service = full_trust_infrastructure["audit_service"]

        unique_id = datetime.utcnow().timestamp()
        agent_id = f"lifecycle-agent-{unique_id}"

        # 1. ESTABLISH (Genesis)
        chain = await trust_ops.establish(
            agent_id=agent_id,
            authority_id="lifecycle-org",
            capabilities=[
                CapabilityRequest(capability="analyze"),
                CapabilityRequest(capability="report"),
            ],
        )

        assert chain.genesis is not None
        assert chain.genesis.signature != ""

        # 2. VERIFY before action
        verify_result = await trust_ops.verify(
            agent_id=agent_id,
            action="analyze",
        )

        assert verify_result.valid is True

        # 3. Execute action with audit
        audit_anchor = await trust_ops.audit(
            agent_id=agent_id,
            action="analyze",
            result="success",
            metadata={"records_analyzed": 1000},
        )

        assert audit_anchor is not None
        assert audit_anchor.action == "analyze"

        # 4. Query audit trail
        audit_records = await audit_service.query(
            agent_id=agent_id,
            start_time=datetime.utcnow() - timedelta(minutes=5),
        )

        assert len(audit_records) >= 1
        assert audit_records[0].action == "analyze"

    @pytest.mark.e2e
    @pytest.mark.requires_docker
    @pytest.mark.timeout(30)
    async def test_delegation_chain_lifecycle(self, full_trust_infrastructure):
        """
        Test delegation: supervisor -> worker -> action.
        """
        trust_ops = full_trust_infrastructure["trust_ops"]

        unique_id = datetime.utcnow().timestamp()
        supervisor_id = f"supervisor-{unique_id}"
        worker_id = f"worker-{unique_id}"

        # 1. Establish supervisor with delegation capability
        await trust_ops.establish(
            agent_id=supervisor_id,
            authority_id="delegation-org",
            capabilities=[
                CapabilityRequest(capability="analyze"),
                CapabilityRequest(capability="delegate", capability_type=CapabilityType.DELEGATION),
            ],
        )

        # 2. Supervisor delegates to worker
        await trust_ops.delegate(
            from_agent_id=supervisor_id,
            to_agent_id=worker_id,
            capabilities=["analyze"],
            constraints={"max_records": 500},
        )

        # 3. Worker verifies action
        result = await trust_ops.verify(
            agent_id=worker_id,
            action="analyze",
        )

        assert result.valid is True

        # 4. Verify constraint is inherited
        assert result.constraints.get("max_records") == 500

    @pytest.mark.e2e
    @pytest.mark.requires_docker
    @pytest.mark.timeout(30)
    async def test_posture_mapping_e2e(self, full_trust_infrastructure):
        """
        Test trust verification maps to correct postures.
        """
        trust_ops = full_trust_infrastructure["trust_ops"]
        mapper = TrustPostureMapper()

        unique_id = datetime.utcnow().timestamp()
        agent_id = f"posture-agent-{unique_id}"

        # Establish with audit requirement
        await trust_ops.establish(
            agent_id=agent_id,
            authority_id="posture-org",
            capabilities=[
                CapabilityRequest(
                    capability="read_data",
                    constraints=["audit_required"],
                ),
            ],
        )

        # Verify action
        result = await trust_ops.verify(
            agent_id=agent_id,
            action="read_data",
        )

        # Map to posture
        posture_result = mapper.map_verification_result(result)

        # With audit requirement, should be SUPERVISED
        assert posture_result.posture in [
            TrustPosture.SUPERVISED,
            TrustPosture.FULL_AUTONOMY,
        ]
        assert posture_result.constraints.audit_required is True
```

---

## Performance Benchmarks

### Latency Requirements

| Operation              | Target | Maximum |
| ---------------------- | ------ | ------- |
| `VERIFY` (QUICK)       | <10ms  | <100ms  |
| `VERIFY` (STANDARD)    | <50ms  | <100ms  |
| `VERIFY` (FULL)        | <100ms | <200ms  |
| `ESTABLISH`            | <200ms | <500ms  |
| `DELEGATE`             | <100ms | <300ms  |
| `AUDIT`                | <50ms  | <200ms  |
| Revocation propagation | <5s    | <10s    |

### Benchmark Tests

```python
# tests/benchmarks/trust/benchmark_trust_operations.py
"""
Performance benchmarks for trust operations.

Run with: pytest tests/benchmarks/trust/ --benchmark-enable
"""

import pytest
from datetime import datetime
from kaizen.trust import (
    TrustOperations,
    PostgresTrustStore,
    CapabilityRequest,
    VerificationLevel,
)


@pytest.fixture
async def benchmark_trust_ops():
    """Trust operations for benchmarking."""
    store = PostgresTrustStore(
        connection_string="postgresql://test_user:test_password@localhost:5434/kailash_test"
    )
    await store.initialize()

    ops = TrustOperations(trust_store=store)
    await ops.initialize()

    yield ops

    await store.close()


class TestVerifyPerformance:
    """Benchmark VERIFY operation."""

    @pytest.mark.benchmark
    async def test_verify_quick_under_100ms(self, benchmark_trust_ops, benchmark):
        """VERIFY QUICK should complete under 100ms."""
        agent_id = f"bench-{datetime.utcnow().timestamp()}"

        await benchmark_trust_ops.establish(
            agent_id=agent_id,
            authority_id="bench-org",
            capabilities=[CapabilityRequest(capability="benchmark")],
        )

        async def verify():
            return await benchmark_trust_ops.verify(
                agent_id=agent_id,
                action="benchmark",
                level=VerificationLevel.QUICK,
            )

        result = benchmark(verify)

        assert benchmark.stats.mean < 0.1  # 100ms
        assert result.valid is True

    @pytest.mark.benchmark
    async def test_verify_full_under_200ms(self, benchmark_trust_ops, benchmark):
        """VERIFY FULL should complete under 200ms."""
        agent_id = f"bench-full-{datetime.utcnow().timestamp()}"

        await benchmark_trust_ops.establish(
            agent_id=agent_id,
            authority_id="bench-org",
            capabilities=[CapabilityRequest(capability="benchmark")],
        )

        async def verify():
            return await benchmark_trust_ops.verify(
                agent_id=agent_id,
                action="benchmark",
                level=VerificationLevel.FULL,
            )

        result = benchmark(verify)

        assert benchmark.stats.mean < 0.2  # 200ms
        assert result.valid is True
```

---

## Test Data Management

### Genesis Record Fixtures

```python
# tests/fixtures/trust/genesis_records.py
"""
Test fixtures for genesis records.

Use with `pytest --fixtures`.
"""

from datetime import datetime, timedelta
from kaizen.trust import (
    GenesisRecord,
    AuthorityType,
    generate_keypair,
    sign,
)


def create_test_genesis(
    agent_id: str = "test-agent",
    authority_id: str = "test-org",
    expires_in_days: int = 365,
) -> GenesisRecord:
    """Create a valid genesis record for testing."""
    private_key, public_key = generate_keypair()

    payload = {
        "agent_id": agent_id,
        "authority_id": authority_id,
        "created_at": datetime.utcnow().isoformat(),
    }

    return GenesisRecord(
        id=f"gen-{datetime.utcnow().timestamp()}",
        agent_id=agent_id,
        authority_id=authority_id,
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=expires_in_days),
        signature=sign(payload, private_key),
        metadata={"public_key": public_key},
    )
```

### Delegation Chain Fixtures

```python
# tests/fixtures/trust/delegation_chains.py
"""
Test fixtures for delegation chains.
"""

def create_3_level_delegation_chain():
    """
    Create a 3-level delegation chain for testing.

    Organization -> Supervisor -> Worker
    """
    return {
        "organization": {
            "id": "org-001",
            "capabilities": ["full_access", "delegate"],
        },
        "supervisor": {
            "id": "supervisor-001",
            "delegated_by": "org-001",
            "capabilities": ["analyze", "report", "delegate"],
            "constraints": {"max_records": 10000},
        },
        "worker": {
            "id": "worker-001",
            "delegated_by": "supervisor-001",
            "capabilities": ["analyze"],
            "constraints": {"max_records": 1000},  # More restrictive
        },
    }
```

---

## CI/CD Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/trust-tests.yml
name: Trust Module Tests

on:
  push:
    paths:
      - "apps/kailash-kaizen/src/kaizen/trust/**"
      - "apps/kailash-kaizen/tests/**/trust/**"
  pull_request:
    paths:
      - "apps/kailash-kaizen/src/kaizen/trust/**"

jobs:
  unit-tests:
    name: Tier 1 - Unit Tests
    runs-on: ubuntu-latest
    timeout-minutes: 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install -e ./apps/kailash-kaizen[dev]

      - name: Run unit tests
        run: |
          pytest apps/kailash-kaizen/tests/unit/trust/ \
            --timeout=1 \
            --cov=apps/kailash-kaizen/src/kaizen/trust \
            --cov-report=xml \
            -v

  integration-tests:
    name: Tier 2 - Integration Tests
    runs-on: ubuntu-latest
    timeout-minutes: 15

    services:
      postgres:
        image: pgvector/pgvector:pg15
        env:
          POSTGRES_DB: kailash_test
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_password
        ports:
          - 5434:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        ports:
          - 6380:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install -e ./apps/kailash-kaizen[dev]

      - name: Wait for services
        run: |
          sleep 10

      - name: Run integration tests
        run: |
          pytest apps/kailash-kaizen/tests/integration/trust/ \
            --timeout=5 \
            -v \
            -m "integration"

  e2e-tests:
    name: Tier 3 - E2E Tests
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Start Docker Compose
        run: |
          docker-compose -f tests/utils/docker-compose.test.yml up -d

      - name: Wait for services
        run: |
          sleep 30

      - name: Install dependencies
        run: |
          pip install -e ./apps/kailash-kaizen[dev]

      - name: Run E2E tests
        run: |
          pytest apps/kailash-kaizen/tests/e2e/trust/ \
            --timeout=10 \
            -v \
            -m "e2e"

      - name: Stop Docker Compose
        if: always()
        run: |
          docker-compose -f tests/utils/docker-compose.test.yml down -v

  benchmarks:
    name: Performance Benchmarks
    runs-on: ubuntu-latest
    timeout-minutes: 20
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'

    services:
      postgres:
        image: pgvector/pgvector:pg15
        env:
          POSTGRES_DB: kailash_test
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_password
        ports:
          - 5434:5432

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install -e ./apps/kailash-kaizen[dev]
          pip install pytest-benchmark

      - name: Run benchmarks
        run: |
          pytest apps/kailash-kaizen/tests/benchmarks/trust/ \
            --benchmark-enable \
            --benchmark-json=benchmark-results.json

      - name: Store benchmark results
        uses: actions/upload-artifact@v4
        with:
          name: benchmark-results
          path: benchmark-results.json
```

---

## Test Execution Commands

```bash
# Unit tests (fast, no Docker needed)
pytest apps/kailash-kaizen/tests/unit/trust/ --timeout=1 -v

# Integration tests (requires Docker)
./tests/utils/test-env up
pytest apps/kailash-kaizen/tests/integration/trust/ --timeout=5 -v

# E2E tests (requires full Docker stack)
pytest apps/kailash-kaizen/tests/e2e/trust/ --timeout=10 -v

# All trust tests with coverage
pytest apps/kailash-kaizen/tests/**/trust/ \
  --cov=apps/kailash-kaizen/src/kaizen/trust \
  --cov-report=term-missing \
  --cov-fail-under=80

# Benchmarks
pytest apps/kailash-kaizen/tests/benchmarks/trust/ \
  --benchmark-enable \
  --benchmark-compare
```
