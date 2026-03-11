"""
Unit tests for CARE-002: Delegation Signature Verification.

Tests cover:
- Single delegation signature verification
- Full delegation chain verification
- Tampered delegation detection
- Missing delegator chain handling
- Signature replay attack prevention
- Signing payload correctness

These tests use REAL Ed25519 cryptography from kaizen.trust.crypto.
NO MOCKING of cryptographic operations.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from kaizen.trust.authority import (
    AuthorityPermission,
    AuthorityType,
    OrganizationalAuthority,
    OrganizationalAuthorityRegistry,
)
from kaizen.trust.chain import (
    CapabilityAttestation,
    CapabilityType,
    ConstraintEnvelope,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
    VerificationLevel,
    VerificationResult,
)
from kaizen.trust.crypto import (
    NACL_AVAILABLE,
    generate_keypair,
    serialize_for_signing,
    sign,
    verify_signature,
)
from kaizen.trust.exceptions import TrustChainNotFoundError
from kaizen.trust.operations import TrustKeyManager, TrustOperations
from kaizen.trust.store import PostgresTrustStore

# Skip tests if PyNaCl not available
pytestmark = pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not installed")


class TestDelegationSigningPayload:
    """Tests for DelegationRecord.to_signing_payload()."""

    def test_to_signing_payload_excludes_signature(self):
        """The signing payload must NOT include the signature field."""
        delegation = DelegationRecord(
            id="del-001",
            delegator_id="agent-A",
            delegatee_id="agent-B",
            task_id="task-001",
            capabilities_delegated=["analyze_data"],
            constraint_subset=["read_only"],
            delegated_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            expires_at=datetime(2025, 1, 16, 10, 0, 0, tzinfo=timezone.utc),
            signature="this-should-not-appear-in-payload",
            parent_delegation_id="del-000",
        )

        payload = delegation.to_signing_payload()

        # Signature must NOT be in payload (would cause circular verification)
        assert "signature" not in payload

        # All other signable fields must be present
        assert payload["id"] == "del-001"
        assert payload["delegator_id"] == "agent-A"
        assert payload["delegatee_id"] == "agent-B"
        assert payload["task_id"] == "task-001"
        assert payload["capabilities_delegated"] == ["analyze_data"]
        assert payload["constraint_subset"] == ["read_only"]
        assert payload["parent_delegation_id"] == "del-000"

    def test_to_signing_payload_deterministic(self):
        """Signing payload must be deterministic for the same data."""
        delegation = DelegationRecord(
            id="del-001",
            delegator_id="agent-A",
            delegatee_id="agent-B",
            task_id="task-001",
            capabilities_delegated=["cap-b", "cap-a"],  # Unsorted
            constraint_subset=["con-z", "con-a"],  # Unsorted
            delegated_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            signature="sig",
        )

        # Call multiple times
        payload1 = delegation.to_signing_payload()
        payload2 = delegation.to_signing_payload()

        # Serialize both
        serialized1 = serialize_for_signing(payload1)
        serialized2 = serialize_for_signing(payload2)

        assert serialized1 == serialized2

    def test_to_signing_payload_sorts_lists(self):
        """Signing payload must sort lists for deterministic signing."""
        delegation = DelegationRecord(
            id="del-001",
            delegator_id="agent-A",
            delegatee_id="agent-B",
            task_id="task-001",
            capabilities_delegated=["cap-z", "cap-a", "cap-m"],
            constraint_subset=["con-z", "con-a"],
            delegated_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            signature="sig",
        )

        payload = delegation.to_signing_payload()

        # Lists should be sorted for deterministic serialization
        assert payload["capabilities_delegated"] == ["cap-a", "cap-m", "cap-z"]
        assert payload["constraint_subset"] == ["con-a", "con-z"]


class TestVerifyDelegationSignature:
    """Tests for _verify_delegation_signature() method."""

    @pytest.fixture
    def keypair(self):
        """Generate a keypair for tests."""
        return generate_keypair()

    @pytest.fixture
    def authority(self, keypair):
        """Create an authority with the test keypair."""
        private_key, public_key = keypair
        return OrganizationalAuthority(
            id="org-test",
            name="Test Organization",
            public_key=public_key,
            signing_key_id="key-test",
            authority_type=AuthorityType.ORGANIZATION,
            permissions=[
                AuthorityPermission.CREATE_AGENTS,
                AuthorityPermission.DELEGATE_TRUST,
            ],
        )

    @pytest.fixture
    def key_manager(self, keypair):
        """Create a key manager with the test keypair."""
        private_key, public_key = keypair
        km = TrustKeyManager()
        km.register_key("key-test", private_key)
        return km

    @pytest.fixture
    def trust_store(self):
        """Create a mock trust store."""
        return AsyncMock(spec=PostgresTrustStore)

    @pytest.fixture
    def authority_registry(self, authority):
        """Create a mock authority registry."""
        registry = AsyncMock(spec=OrganizationalAuthorityRegistry)
        registry.get_authority = AsyncMock(return_value=authority)
        return registry

    @pytest.fixture
    def trust_ops(self, authority_registry, key_manager, trust_store):
        """Create TrustOperations with test fixtures."""
        return TrustOperations(authority_registry, key_manager, trust_store)

    def _create_delegator_chain(
        self, authority_id: str, agent_id: str
    ) -> TrustLineageChain:
        """Helper to create a delegator's trust chain."""
        genesis = GenesisRecord(
            id=f"gen-{uuid4()}",
            agent_id=agent_id,
            authority_id=authority_id,
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature="genesis-sig",
        )
        return TrustLineageChain(genesis=genesis, capabilities=[], delegations=[])

    @pytest.mark.asyncio
    async def test_verify_valid_delegation_signature(
        self, trust_ops, keypair, authority
    ):
        """Valid delegation signature passes verification."""
        private_key, public_key = keypair

        # Create a delegation and sign it with real crypto
        delegation = DelegationRecord(
            id="del-001",
            delegator_id="agent-A",
            delegatee_id="agent-B",
            task_id="task-001",
            capabilities_delegated=["analyze_data"],
            constraint_subset=["read_only"],
            delegated_at=datetime.now(timezone.utc),
            signature="",  # Will be signed
        )

        # Sign the delegation with real Ed25519
        payload = serialize_for_signing(delegation.to_signing_payload())
        delegation.signature = sign(payload, private_key)

        # Create delegator chain
        delegator_chain = self._create_delegator_chain("org-test", "agent-A")

        # Verify
        result = await trust_ops._verify_delegation_signature(
            delegation, delegator_chain
        )

        assert result.valid is True
        assert result.level == VerificationLevel.FULL

    @pytest.mark.asyncio
    async def test_tampered_delegation_rejected(self, trust_ops, keypair, authority):
        """Tampered delegation fails signature verification."""
        private_key, public_key = keypair

        # Create and sign a delegation
        delegation = DelegationRecord(
            id="del-001",
            delegator_id="agent-A",
            delegatee_id="agent-B",
            task_id="task-001",
            capabilities_delegated=["analyze_data"],
            constraint_subset=["read_only"],
            delegated_at=datetime.now(timezone.utc),
            signature="",
        )

        # Sign the original delegation
        payload = serialize_for_signing(delegation.to_signing_payload())
        delegation.signature = sign(payload, private_key)

        # TAMPER: Modify the delegation AFTER signing
        delegation.capabilities_delegated = ["analyze_data", "delete_everything"]

        # Create delegator chain
        delegator_chain = self._create_delegator_chain("org-test", "agent-A")

        # Verify - should FAIL due to tampering
        result = await trust_ops._verify_delegation_signature(
            delegation, delegator_chain
        )

        assert result.valid is False
        assert "Invalid delegation signature" in result.reason

    @pytest.mark.asyncio
    async def test_wrong_key_delegation_rejected(self, trust_ops, keypair, authority):
        """Delegation signed with wrong key fails verification."""
        private_key, public_key = keypair

        # Generate a DIFFERENT keypair for signing
        wrong_private_key, wrong_public_key = generate_keypair()

        # Create delegation and sign with WRONG key
        delegation = DelegationRecord(
            id="del-001",
            delegator_id="agent-A",
            delegatee_id="agent-B",
            task_id="task-001",
            capabilities_delegated=["analyze_data"],
            constraint_subset=["read_only"],
            delegated_at=datetime.now(timezone.utc),
            signature="",
        )

        # Sign with wrong key
        payload = serialize_for_signing(delegation.to_signing_payload())
        delegation.signature = sign(payload, wrong_private_key)

        # Create delegator chain
        delegator_chain = self._create_delegator_chain("org-test", "agent-A")

        # Verify - should FAIL because wrong key was used
        result = await trust_ops._verify_delegation_signature(
            delegation, delegator_chain
        )

        assert result.valid is False
        assert "Invalid delegation signature" in result.reason


class TestVerifyDelegationChain:
    """Tests for verify_delegation_chain() method."""

    @pytest.fixture
    def keypair(self):
        """Generate a keypair for tests."""
        return generate_keypair()

    @pytest.fixture
    def authority(self, keypair):
        """Create an authority with the test keypair."""
        private_key, public_key = keypair
        return OrganizationalAuthority(
            id="org-test",
            name="Test Organization",
            public_key=public_key,
            signing_key_id="key-test",
            authority_type=AuthorityType.ORGANIZATION,
            permissions=[
                AuthorityPermission.CREATE_AGENTS,
                AuthorityPermission.DELEGATE_TRUST,
            ],
        )

    @pytest.fixture
    def key_manager(self, keypair):
        """Create a key manager with the test keypair."""
        private_key, public_key = keypair
        km = TrustKeyManager()
        km.register_key("key-test", private_key)
        return km

    @pytest.fixture
    def trust_store(self):
        """Create a mock trust store."""
        return AsyncMock(spec=PostgresTrustStore)

    @pytest.fixture
    def authority_registry(self, authority):
        """Create a mock authority registry."""
        registry = AsyncMock(spec=OrganizationalAuthorityRegistry)
        registry.get_authority = AsyncMock(return_value=authority)
        return registry

    @pytest.fixture
    def trust_ops(self, authority_registry, key_manager, trust_store):
        """Create TrustOperations with test fixtures."""
        return TrustOperations(authority_registry, key_manager, trust_store)

    def _create_signed_delegation(
        self, private_key: str, delegator_id: str, delegatee_id: str, del_id: str
    ) -> DelegationRecord:
        """Helper to create a properly signed delegation."""
        delegation = DelegationRecord(
            id=del_id,
            delegator_id=delegator_id,
            delegatee_id=delegatee_id,
            task_id=f"task-{uuid4()}",
            capabilities_delegated=["analyze_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="",
        )
        payload = serialize_for_signing(delegation.to_signing_payload())
        delegation.signature = sign(payload, private_key)
        return delegation

    def _create_chain_with_delegations(
        self, agent_id: str, authority_id: str, delegations: list
    ) -> TrustLineageChain:
        """Helper to create a chain with delegations."""
        genesis = GenesisRecord(
            id=f"gen-{uuid4()}",
            agent_id=agent_id,
            authority_id=authority_id,
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature="genesis-sig",
        )
        return TrustLineageChain(
            genesis=genesis,
            capabilities=[],
            delegations=delegations,
        )

    @pytest.mark.asyncio
    async def test_verify_delegation_chain_all_valid(
        self, trust_ops, trust_store, keypair
    ):
        """Multi-level chain A->B->C with all valid signatures passes."""
        private_key, public_key = keypair

        # Create chain: Human -> Agent-A -> Agent-B -> Agent-C
        # We're verifying Agent-C's chain

        # Create delegation A -> B
        del_a_to_b = self._create_signed_delegation(
            private_key, "agent-A", "agent-B", "del-001"
        )

        # Create delegation B -> C
        del_b_to_c = self._create_signed_delegation(
            private_key, "agent-B", "agent-C", "del-002"
        )

        # Create chains for each agent
        chain_a = self._create_chain_with_delegations("agent-A", "org-test", [])
        chain_b = self._create_chain_with_delegations(
            "agent-B", "org-test", [del_a_to_b]
        )
        chain_c = self._create_chain_with_delegations(
            "agent-C", "org-test", [del_a_to_b, del_b_to_c]
        )

        # Setup trust store to return appropriate chains
        async def mock_get_chain(agent_id):
            if agent_id == "agent-A":
                return chain_a
            elif agent_id == "agent-B":
                return chain_b
            elif agent_id == "agent-C":
                return chain_c
            raise TrustChainNotFoundError(agent_id)

        trust_store.get_chain = AsyncMock(side_effect=mock_get_chain)

        # Verify the entire chain for agent-C
        result = await trust_ops.verify_delegation_chain("agent-C")

        assert result.valid is True
        assert result.level == VerificationLevel.FULL

    @pytest.mark.asyncio
    async def test_verify_delegation_chain_broken_signature(
        self, trust_ops, trust_store, keypair
    ):
        """Chain with one tampered signature fails verification."""
        private_key, public_key = keypair

        # Create valid delegation A -> B
        del_a_to_b = self._create_signed_delegation(
            private_key, "agent-A", "agent-B", "del-001"
        )

        # Create delegation B -> C and TAMPER with it after signing
        del_b_to_c = self._create_signed_delegation(
            private_key, "agent-B", "agent-C", "del-002"
        )
        # TAMPER: Add unauthorized capability
        del_b_to_c.capabilities_delegated = ["analyze_data", "admin_access"]

        # Create chains
        chain_a = self._create_chain_with_delegations("agent-A", "org-test", [])
        chain_b = self._create_chain_with_delegations(
            "agent-B", "org-test", [del_a_to_b]
        )
        chain_c = self._create_chain_with_delegations(
            "agent-C", "org-test", [del_a_to_b, del_b_to_c]
        )

        async def mock_get_chain(agent_id):
            if agent_id == "agent-A":
                return chain_a
            elif agent_id == "agent-B":
                return chain_b
            elif agent_id == "agent-C":
                return chain_c
            raise TrustChainNotFoundError(agent_id)

        trust_store.get_chain = AsyncMock(side_effect=mock_get_chain)

        # Verify - should FAIL at the tampered delegation
        result = await trust_ops.verify_delegation_chain("agent-C")

        assert result.valid is False
        assert "Invalid delegation signature" in result.reason

    @pytest.mark.asyncio
    async def test_verify_chain_missing_delegator(
        self, trust_ops, trust_store, keypair
    ):
        """Missing delegator chain returns invalid result."""
        private_key, public_key = keypair

        # Create delegation from non-existent agent
        del_ghost_to_c = self._create_signed_delegation(
            private_key, "ghost-agent", "agent-C", "del-001"
        )

        chain_c = self._create_chain_with_delegations(
            "agent-C", "org-test", [del_ghost_to_c]
        )

        async def mock_get_chain(agent_id):
            if agent_id == "agent-C":
                return chain_c
            # ghost-agent doesn't exist
            raise TrustChainNotFoundError(agent_id)

        trust_store.get_chain = AsyncMock(side_effect=mock_get_chain)

        # Verify - should FAIL because delegator chain not found
        result = await trust_ops.verify_delegation_chain("agent-C")

        assert result.valid is False
        assert "Delegator chain not found" in result.reason
        assert "ghost-agent" in result.reason

    @pytest.mark.asyncio
    async def test_verify_chain_empty_delegations(self, trust_ops, trust_store):
        """Agent with no delegations passes chain verification."""
        # Agent directly established, no delegations
        chain = self._create_chain_with_delegations("agent-A", "org-test", [])

        trust_store.get_chain = AsyncMock(return_value=chain)

        result = await trust_ops.verify_delegation_chain("agent-A")

        assert result.valid is True
        assert result.level == VerificationLevel.FULL


class TestSignatureReplayAttacks:
    """Tests for signature replay attack prevention."""

    @pytest.fixture
    def keypair(self):
        """Generate a keypair for tests."""
        return generate_keypair()

    @pytest.fixture
    def authority(self, keypair):
        """Create an authority with the test keypair."""
        private_key, public_key = keypair
        return OrganizationalAuthority(
            id="org-test",
            name="Test Organization",
            public_key=public_key,
            signing_key_id="key-test",
            authority_type=AuthorityType.ORGANIZATION,
            permissions=[
                AuthorityPermission.CREATE_AGENTS,
                AuthorityPermission.DELEGATE_TRUST,
            ],
        )

    @pytest.fixture
    def key_manager(self, keypair):
        """Create a key manager with the test keypair."""
        private_key, public_key = keypair
        km = TrustKeyManager()
        km.register_key("key-test", private_key)
        return km

    @pytest.fixture
    def trust_store(self):
        """Create a mock trust store."""
        return AsyncMock(spec=PostgresTrustStore)

    @pytest.fixture
    def authority_registry(self, authority):
        """Create a mock authority registry."""
        registry = AsyncMock(spec=OrganizationalAuthorityRegistry)
        registry.get_authority = AsyncMock(return_value=authority)
        return registry

    @pytest.fixture
    def trust_ops(self, authority_registry, key_manager, trust_store):
        """Create TrustOperations with test fixtures."""
        return TrustOperations(authority_registry, key_manager, trust_store)

    @pytest.mark.asyncio
    async def test_signature_replay_attack_prevented(self, trust_ops, keypair):
        """Signature from one delegation cannot be used on another."""
        private_key, public_key = keypair

        # Create original delegation A -> B
        original_delegation = DelegationRecord(
            id="del-001",
            delegator_id="agent-A",
            delegatee_id="agent-B",
            task_id="task-001",
            capabilities_delegated=["read_data"],  # Limited capability
            constraint_subset=["read_only"],
            delegated_at=datetime.now(timezone.utc),
            signature="",
        )

        # Sign the original delegation
        payload = serialize_for_signing(original_delegation.to_signing_payload())
        original_delegation.signature = sign(payload, private_key)

        # Attacker creates a NEW delegation with DIFFERENT (elevated) capabilities
        # but tries to REUSE the signature from the original delegation
        malicious_delegation = DelegationRecord(
            id="del-002",  # Different ID
            delegator_id="agent-A",
            delegatee_id="agent-ATTACKER",  # Different target
            task_id="task-evil",
            capabilities_delegated=["admin_access", "delete_all"],  # Elevated
            constraint_subset=[],  # No constraints
            delegated_at=datetime.now(timezone.utc),
            signature=original_delegation.signature,  # REPLAY: stolen signature
        )

        # Create delegator chain
        genesis = GenesisRecord(
            id="gen-001",
            agent_id="agent-A",
            authority_id="org-test",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature="genesis-sig",
        )
        delegator_chain = TrustLineageChain(
            genesis=genesis, capabilities=[], delegations=[]
        )

        # Verify the malicious delegation - should FAIL
        result = await trust_ops._verify_delegation_signature(
            malicious_delegation, delegator_chain
        )

        assert result.valid is False
        assert "Invalid delegation signature" in result.reason

    @pytest.mark.asyncio
    async def test_signature_id_bound(self, trust_ops, keypair):
        """Signature is bound to delegation ID - cannot reuse for same content different ID."""
        private_key, public_key = keypair

        # Create original delegation
        original = DelegationRecord(
            id="del-001",
            delegator_id="agent-A",
            delegatee_id="agent-B",
            task_id="task-001",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            signature="",
        )

        payload = serialize_for_signing(original.to_signing_payload())
        original.signature = sign(payload, private_key)

        # Create IDENTICAL delegation but with different ID
        clone = DelegationRecord(
            id="del-999",  # Different ID
            delegator_id="agent-A",
            delegatee_id="agent-B",
            task_id="task-001",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            signature=original.signature,  # Reuse signature
        )

        # Create delegator chain
        genesis = GenesisRecord(
            id="gen-001",
            agent_id="agent-A",
            authority_id="org-test",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature="genesis-sig",
        )
        delegator_chain = TrustLineageChain(
            genesis=genesis, capabilities=[], delegations=[]
        )

        # Verify clone - should FAIL because ID is part of signed payload
        result = await trust_ops._verify_delegation_signature(clone, delegator_chain)

        assert result.valid is False
        assert "Invalid delegation signature" in result.reason


class TestIntegrationWithExistingVerify:
    """Tests verifying integration with existing _verify_signatures method."""

    @pytest.fixture
    def keypair(self):
        """Generate a keypair for tests."""
        return generate_keypair()

    @pytest.fixture
    def authority(self, keypair):
        """Create an authority with the test keypair."""
        private_key, public_key = keypair
        return OrganizationalAuthority(
            id="org-test",
            name="Test Organization",
            public_key=public_key,
            signing_key_id="key-test",
            authority_type=AuthorityType.ORGANIZATION,
            permissions=[
                AuthorityPermission.CREATE_AGENTS,
                AuthorityPermission.DELEGATE_TRUST,
            ],
        )

    @pytest.fixture
    def key_manager(self, keypair):
        """Create a key manager with the test keypair."""
        private_key, public_key = keypair
        km = TrustKeyManager()
        km.register_key("key-test", private_key)
        return km

    @pytest.fixture
    def trust_store(self):
        """Create a mock trust store."""
        return AsyncMock(spec=PostgresTrustStore)

    @pytest.fixture
    def authority_registry(self, authority):
        """Create a mock authority registry."""
        registry = AsyncMock(spec=OrganizationalAuthorityRegistry)
        registry.get_authority = AsyncMock(return_value=authority)
        return registry

    @pytest.fixture
    def trust_ops(self, authority_registry, key_manager, trust_store):
        """Create TrustOperations with test fixtures."""
        return TrustOperations(authority_registry, key_manager, trust_store)

    @pytest.mark.asyncio
    async def test_verify_signatures_validates_delegations(
        self, trust_ops, trust_store, keypair, authority
    ):
        """_verify_signatures now validates delegation signatures."""
        private_key, public_key = keypair

        # Create a properly signed genesis
        genesis = GenesisRecord(
            id="gen-001",
            agent_id="agent-A",
            authority_id="org-test",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature="",
        )
        genesis_payload = serialize_for_signing(genesis.to_signing_payload())
        genesis.signature = sign(genesis_payload, private_key)

        # Create a properly signed capability
        capability = CapabilityAttestation(
            id="cap-001",
            capability="analyze_data",
            capability_type=CapabilityType.ACCESS,
            constraints=[],
            attester_id="org-test",
            attested_at=datetime.now(timezone.utc),
            signature="",
        )
        cap_payload = serialize_for_signing(capability.to_signing_payload())
        capability.signature = sign(cap_payload, private_key)

        # Create a properly signed delegation
        delegation = DelegationRecord(
            id="del-001",
            delegator_id="origin-agent",
            delegatee_id="agent-A",
            task_id="task-001",
            capabilities_delegated=["analyze_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="",
        )
        del_payload = serialize_for_signing(delegation.to_signing_payload())
        delegation.signature = sign(del_payload, private_key)

        # Create chain with all properly signed elements
        chain = TrustLineageChain(
            genesis=genesis,
            capabilities=[capability],
            delegations=[delegation],
        )

        # Create origin chain for delegator lookup
        origin_chain = TrustLineageChain(
            genesis=GenesisRecord(
                id="gen-000",
                agent_id="origin-agent",
                authority_id="org-test",
                authority_type=AuthorityType.ORGANIZATION,
                created_at=datetime.now(timezone.utc),
                signature="origin-sig",
            ),
            capabilities=[],
            delegations=[],
        )

        async def mock_get_chain(agent_id):
            if agent_id == "origin-agent":
                return origin_chain
            raise TrustChainNotFoundError(agent_id)

        trust_store.get_chain = AsyncMock(side_effect=mock_get_chain)

        # Verify signatures - should now validate delegation signatures
        result = await trust_ops._verify_signatures(chain)

        assert result.valid is True
        assert result.level == VerificationLevel.FULL
