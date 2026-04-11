"""
Unit tests for CARE-004: Maximum Delegation Depth Enforcement.

Tests cover:
- DelegationLimits configuration validation
- Depth enforcement in DELEGATE operation configuration
- Configurable max depth parameter on TrustOperations
"""

import pytest
from kailash.trust.signing.crypto import NACL_AVAILABLE

# Skip crypto tests if PyNaCl not available
pytestmark = pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not installed")


class TestDelegationLimits:
    """Tests for DelegationLimits dataclass validation."""

    def test_default_values(self):
        """Default values should be reasonable."""
        from kailash.trust.chain import DelegationLimits

        limits = DelegationLimits()
        assert limits.max_depth == 10
        assert limits.max_chain_length == 50
        assert limits.require_expiry is True
        assert limits.default_expiry_hours == 24

    def test_custom_values(self):
        """Custom values should be accepted."""
        from kailash.trust.chain import DelegationLimits

        limits = DelegationLimits(
            max_depth=5,
            max_chain_length=20,
            require_expiry=False,
            default_expiry_hours=48,
        )
        assert limits.max_depth == 5
        assert limits.max_chain_length == 20
        assert limits.require_expiry is False
        assert limits.default_expiry_hours == 48

    def test_max_depth_must_be_at_least_one(self):
        """max_depth < 1 should raise ValueError."""
        from kailash.trust.chain import DelegationLimits

        with pytest.raises(ValueError, match="max_depth must be at least 1"):
            DelegationLimits(max_depth=0)

    def test_max_depth_negative_raises(self):
        """Negative max_depth should raise ValueError."""
        from kailash.trust.chain import DelegationLimits

        with pytest.raises(ValueError, match="max_depth must be at least 1"):
            DelegationLimits(max_depth=-1)

    def test_max_chain_length_must_be_ge_max_depth(self):
        """max_chain_length < max_depth should raise ValueError."""
        from kailash.trust.chain import DelegationLimits

        with pytest.raises(ValueError, match="max_chain_length must be >= max_depth"):
            DelegationLimits(max_depth=10, max_chain_length=5)

    def test_max_chain_length_equals_max_depth(self):
        """max_chain_length == max_depth should be valid."""
        from kailash.trust.chain import DelegationLimits

        limits = DelegationLimits(max_depth=10, max_chain_length=10)
        assert limits.max_chain_length == 10


class TestMaxDelegationDepthConstant:
    """Tests for MAX_DELEGATION_DEPTH constant."""

    def test_constant_exists(self):
        """MAX_DELEGATION_DEPTH must be defined in operations module."""
        from kailash.trust.operations import MAX_DELEGATION_DEPTH

        assert isinstance(MAX_DELEGATION_DEPTH, int)
        assert MAX_DELEGATION_DEPTH > 0

    def test_default_value_is_10(self):
        """Default MAX_DELEGATION_DEPTH should be 10."""
        from kailash.trust.operations import MAX_DELEGATION_DEPTH

        assert MAX_DELEGATION_DEPTH == 10


class TestTrustOperationsDepthConfig:
    """Tests for max_delegation_depth parameter on TrustOperations."""

    def test_max_delegation_depth_attribute_exists(self):
        """TrustOperations must have max_delegation_depth attribute."""
        # Check the __init__ signature accepts max_delegation_depth
        import inspect

        from kailash.trust.operations import TrustOperations

        sig = inspect.signature(TrustOperations.__init__)
        assert "max_delegation_depth" in sig.parameters

    def test_calculate_delegation_depth_method_exists(self):
        """TrustOperations must have _calculate_delegation_depth method."""
        from kailash.trust.operations import TrustOperations

        assert hasattr(TrustOperations, "_calculate_delegation_depth")

    def test_max_delegation_depth_default_value(self):
        """TrustOperations should use MAX_DELEGATION_DEPTH as default."""
        from unittest.mock import MagicMock

        from kailash.trust.operations import (
            MAX_DELEGATION_DEPTH,
            TrustKeyManager,
            TrustOperations,
        )

        authority_registry = MagicMock()
        key_manager = TrustKeyManager()
        trust_store = MagicMock()

        trust_ops = TrustOperations(authority_registry, key_manager, trust_store)
        assert trust_ops.max_delegation_depth == MAX_DELEGATION_DEPTH

    def test_max_delegation_depth_custom_value(self):
        """TrustOperations should accept custom max_delegation_depth."""
        from unittest.mock import MagicMock

        from kailash.trust.operations import TrustKeyManager, TrustOperations

        authority_registry = MagicMock()
        key_manager = TrustKeyManager()
        trust_store = MagicMock()

        trust_ops = TrustOperations(
            authority_registry, key_manager, trust_store, max_delegation_depth=5
        )
        assert trust_ops.max_delegation_depth == 5


class TestCalculateDelegationDepth:
    """Tests for _calculate_delegation_depth method."""

    def test_depth_zero_for_empty_chain(self):
        """Chain with no delegations should have depth 0."""
        from datetime import datetime, timezone
        from unittest.mock import MagicMock

        from kailash.trust.chain import AuthorityType, GenesisRecord, TrustLineageChain
        from kailash.trust.operations import TrustKeyManager, TrustOperations

        authority_registry = MagicMock()
        key_manager = TrustKeyManager()
        trust_store = MagicMock()
        trust_ops = TrustOperations(authority_registry, key_manager, trust_store)

        genesis = GenesisRecord(
            id="gen-001",
            agent_id="agent-001",
            authority_id="org-acme",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature="sig",
        )

        chain = TrustLineageChain(genesis=genesis, delegations=[])
        depth = trust_ops._calculate_delegation_depth(chain)
        assert depth == 0

    def test_depth_counts_delegation_chain(self):
        """Chain with delegations should have correct depth."""
        from datetime import datetime, timezone
        from unittest.mock import MagicMock

        from kailash.trust.chain import (
            AuthorityType,
            DelegationRecord,
            GenesisRecord,
            TrustLineageChain,
        )
        from kailash.trust.operations import TrustKeyManager, TrustOperations

        authority_registry = MagicMock()
        key_manager = TrustKeyManager()
        trust_store = MagicMock()
        trust_ops = TrustOperations(authority_registry, key_manager, trust_store)

        genesis = GenesisRecord(
            id="gen-001",
            agent_id="agent-c",
            authority_id="org-acme",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature="sig",
        )

        # Create a delegation chain: A -> B -> C
        delegation1 = DelegationRecord(
            id="del-001",
            delegator_id="agent-a",
            delegatee_id="agent-b",
            task_id="task-001",
            capabilities_delegated=["analyze_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="sig",
            parent_delegation_id=None,
        )

        delegation2 = DelegationRecord(
            id="del-002",
            delegator_id="agent-b",
            delegatee_id="agent-c",
            task_id="task-002",
            capabilities_delegated=["analyze_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="sig",
            parent_delegation_id="del-001",
        )

        chain = TrustLineageChain(
            genesis=genesis, delegations=[delegation1, delegation2]
        )
        depth = trust_ops._calculate_delegation_depth(chain)
        assert depth == 2  # Two delegations in the chain


class TestDelegationDepthEnforcement:
    """Tests for CARE-004 depth enforcement in delegate() method."""

    @pytest.mark.asyncio
    async def test_delegate_exceeds_max_depth_raises_delegation_error(self):
        """Delegation exceeding max_depth should raise DelegationError."""
        from datetime import datetime, timedelta, timezone
        from unittest.mock import AsyncMock, MagicMock

        from kailash.trust.chain import (
            AuthorityType,
            CapabilityAttestation,
            CapabilityType,
            ConstraintEnvelope,
            DelegationRecord,
            GenesisRecord,
            TrustLineageChain,
        )
        from kailash.trust.exceptions import DelegationError
        from kailash.trust.operations import TrustKeyManager, TrustOperations

        # Setup mocks
        authority_registry = MagicMock()
        key_manager = TrustKeyManager()
        trust_store = MagicMock()

        # Create TrustOperations with max_depth=2
        trust_ops = TrustOperations(
            authority_registry, key_manager, trust_store, max_delegation_depth=2
        )

        # Create delegator chain with depth already at 2 (at the limit)
        genesis = GenesisRecord(
            id="gen-001",
            agent_id="agent-c",
            authority_id="org-acme",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            signature="sig",
        )

        cap = CapabilityAttestation(
            id="cap-001",
            capability="analyze_data",
            capability_type=CapabilityType.ACCESS,
            constraints=[],
            attester_id="org-acme",
            attested_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            signature="sig",
        )

        # Create a delegation chain with depth 2: A -> B -> C
        delegation1 = DelegationRecord(
            id="del-001",
            delegator_id="agent-a",
            delegatee_id="agent-b",
            task_id="task-001",
            capabilities_delegated=["analyze_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="sig",
            parent_delegation_id=None,
        )

        delegation2 = DelegationRecord(
            id="del-002",
            delegator_id="agent-b",
            delegatee_id="agent-c",
            task_id="task-002",
            capabilities_delegated=["analyze_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="sig",
            parent_delegation_id="del-001",
        )

        envelope = ConstraintEnvelope(
            id="env-001",
            agent_id="agent-c",
            active_constraints=[],
        )

        delegator_chain = TrustLineageChain(
            genesis=genesis,
            capabilities=[cap],
            delegations=[delegation1, delegation2],
            constraint_envelope=envelope,
        )

        # Mock trust_store.get_chain to return our chain
        trust_store.get_chain = AsyncMock(return_value=delegator_chain)

        # Attempting to delegate from agent-c (depth 2) to agent-d (depth 3)
        # should fail because max_depth=2
        with pytest.raises(DelegationError) as exc_info:
            await trust_ops.delegate(
                delegator_id="agent-c",
                delegatee_id="agent-d",
                task_id="task-003",
                capabilities=["analyze_data"],
            )

        # Verify error message contains useful information
        assert "exceeding" in str(exc_info.value)
        assert "depth 3" in str(exc_info.value)  # new_depth
        assert "2" in str(exc_info.value)  # max_delegation_depth

    @pytest.mark.asyncio
    async def test_delegate_at_max_depth_succeeds(self):
        """Delegation at exactly max_depth should succeed."""
        from datetime import datetime, timedelta, timezone
        from unittest.mock import AsyncMock, MagicMock

        from kailash.trust.chain import (
            AuthorityType,
            CapabilityAttestation,
            CapabilityType,
            ConstraintEnvelope,
            DelegationRecord,
            GenesisRecord,
            TrustLineageChain,
        )
        from kailash.trust.operations import TrustKeyManager, TrustOperations
        from kailash.trust.signing.crypto import generate_keypair

        # Setup mocks
        authority_registry = MagicMock()
        key_manager = TrustKeyManager()

        # Generate and register a test key
        private_key, public_key = generate_keypair()
        key_manager.register_key("test-key", private_key)

        trust_store = MagicMock()

        # Create TrustOperations with max_depth=2
        trust_ops = TrustOperations(
            authority_registry, key_manager, trust_store, max_delegation_depth=2
        )

        # Create delegator chain with depth 1 (one below limit)
        genesis = GenesisRecord(
            id="gen-001",
            agent_id="agent-b",
            authority_id="org-acme",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            signature="sig",
        )

        cap = CapabilityAttestation(
            id="cap-001",
            capability="analyze_data",
            capability_type=CapabilityType.ACCESS,
            constraints=[],
            attester_id="org-acme",
            attested_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            signature="sig",
        )

        # Create a delegation chain with depth 1: A -> B
        delegation1 = DelegationRecord(
            id="del-001",
            delegator_id="agent-a",
            delegatee_id="agent-b",
            task_id="task-001",
            capabilities_delegated=["analyze_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="sig",
            parent_delegation_id=None,
        )

        envelope = ConstraintEnvelope(
            id="env-001",
            agent_id="agent-b",
            active_constraints=[],
        )

        delegator_chain = TrustLineageChain(
            genesis=genesis,
            capabilities=[cap],
            delegations=[delegation1],
            constraint_envelope=envelope,
        )

        # Mock authority with public_key and signing_key_id
        mock_authority = MagicMock()
        mock_authority.signing_key_id = "test-key"
        mock_authority.public_key = public_key
        authority_registry.get_authority = AsyncMock(return_value=mock_authority)

        # Mock trust_store methods
        trust_store.get_chain = AsyncMock(return_value=delegator_chain)
        trust_store.update_chain = AsyncMock()
        trust_store.store_chain = AsyncMock()

        # Delegating from agent-b (depth 1) to agent-c (depth 2) should succeed
        # because max_depth=2 and new_depth=2
        result = await trust_ops.delegate(
            delegator_id="agent-b",
            delegatee_id="agent-c",
            task_id="task-002",
            capabilities=["analyze_data"],
        )

        # Verify delegation was created
        assert result is not None
        assert result.delegator_id == "agent-b"
        assert result.delegatee_id == "agent-c"
