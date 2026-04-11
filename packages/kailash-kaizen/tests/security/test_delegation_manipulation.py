"""
CARE-040 Part 2: Delegation Chain Manipulation Tests.

Security tests that verify the trust framework properly rejects various
manipulation attempts on delegation chains.

These are Tier 1 (unit) tests - mocking is allowed for database access
(uses InMemoryTrustStore), but cryptographic operations use REAL Ed25519
signatures and keys (NO MOCKING of crypto).

Test Categories:
1. Capability ownership validation - Cannot delegate what you don't own
2. Constraint tightening enforcement - Cannot weaken inherited constraints
3. Expiration boundary enforcement - Cannot extend expiration beyond parent
4. Signature integrity verification - Tampered signatures are rejected
5. Delegation injection prevention - Fake delegations are rejected
6. Hash chain integrity verification - Modifications to chain are detected

All tests follow the pattern:
1. Create a VALID trust chain using the actual API
2. Attempt the manipulation
3. Verify it's BLOCKED with the appropriate error

Author: Kaizen Framework Team
Created: 2026-02-09
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from kailash.trust.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    ConstraintEnvelope,
    DelegationRecord,
    GenesisRecord,
    LinkedHashChain,
    TrustLineageChain,
    VerificationLevel,
)
from kailash.trust.constraint_validator import ConstraintValidator, ConstraintViolation
from kailash.trust.exceptions import (
    CapabilityNotFoundError,
    ConstraintViolationError,
    DelegationError,
    TrustChainNotFoundError,
)
from kailash.trust.operations import TrustKeyManager, TrustOperations
from kailash.trust.signing.crypto import (
    NACL_AVAILABLE,
    generate_keypair,
    serialize_for_signing,
    sign,
    verify_signature,
)

from kaizen.trust.authority import (
    AuthorityPermission,
    OrganizationalAuthority,
    OrganizationalAuthorityRegistry,
)
from kaizen.trust.store import InMemoryTrustStore

# Skip all tests if PyNaCl is not available
pytestmark = pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not installed")


class TestCannotDelegateUnownedCapability:
    """
    Test 1: Agent tries to delegate a capability it doesn't own.

    EATP Security Property: An agent can only delegate capabilities that
    have been explicitly granted to it via its trust chain.
    """

    @pytest.fixture
    def keypair(self):
        """Generate real Ed25519 keypair for signing."""
        return generate_keypair()

    @pytest.fixture
    def authority(self, keypair):
        """Create an organizational authority with the test keypair."""
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
        """Create key manager with the test keypair."""
        private_key, public_key = keypair
        km = TrustKeyManager()
        km.register_key("key-test", private_key)
        return km

    @pytest.fixture
    def trust_store(self):
        """Use real InMemoryTrustStore instead of mocking."""
        return InMemoryTrustStore()

    @pytest.fixture
    def authority_registry(self, authority):
        """Create mock authority registry returning our test authority."""
        registry = AsyncMock(spec=OrganizationalAuthorityRegistry)
        registry.get_authority = AsyncMock(return_value=authority)
        registry.initialize = AsyncMock()
        return registry

    @pytest.fixture
    def trust_ops(self, authority_registry, key_manager, trust_store):
        """Create TrustOperations with test fixtures."""
        return TrustOperations(authority_registry, key_manager, trust_store)

    def _create_signed_genesis(
        self, private_key: str, agent_id: str, authority_id: str
    ) -> GenesisRecord:
        """Helper to create a properly signed genesis record."""
        genesis = GenesisRecord(
            id=f"gen-{uuid4()}",
            agent_id=agent_id,
            authority_id=authority_id,
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            signature="",
        )
        payload = serialize_for_signing(genesis.to_signing_payload())
        genesis.signature = sign(payload, private_key)
        return genesis

    def _create_signed_capability(
        self,
        private_key: str,
        capability_name: str,
        attester_id: str,
        constraints: Optional[List[str]] = None,
    ) -> CapabilityAttestation:
        """Helper to create a properly signed capability attestation."""
        capability = CapabilityAttestation(
            id=f"cap-{uuid4()}",
            capability=capability_name,
            capability_type=CapabilityType.ACCESS,
            constraints=constraints or [],
            attester_id=attester_id,
            attested_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            signature="",
        )
        payload = serialize_for_signing(capability.to_signing_payload())
        capability.signature = sign(payload, private_key)
        return capability

    @pytest.mark.asyncio
    async def test_cannot_delegate_unowned_capability(
        self, trust_ops, trust_store, keypair
    ):
        """
        Agent-A has 'analyze_data' capability.
        Agent-A tries to delegate 'admin_access' which it does NOT have.
        Delegation MUST be rejected.
        """
        private_key, public_key = keypair

        # Step 1: Create Agent-A with ONLY 'analyze_data' capability
        genesis_a = self._create_signed_genesis(private_key, "agent-A", "org-test")
        cap_analyze = self._create_signed_capability(
            private_key, "analyze_data", "org-test"
        )

        chain_a = TrustLineageChain(
            genesis=genesis_a,
            capabilities=[cap_analyze],  # ONLY analyze_data
            delegations=[],
        )

        await trust_store.initialize()
        await trust_store.store_chain(chain_a)
        await trust_ops.initialize()

        # Step 2: Agent-A tries to delegate 'admin_access' (NOT owned)
        with pytest.raises(CapabilityNotFoundError) as exc_info:
            await trust_ops.delegate(
                delegator_id="agent-A",
                delegatee_id="agent-B",
                task_id="task-001",
                capabilities=["admin_access"],  # Agent-A does NOT have this
            )

        # Step 3: Verify the error contains appropriate information
        assert "admin_access" in str(exc_info.value)
        assert (
            "agent-A" in str(exc_info.value)
            or exc_info.value.agent_id == "admin_access"
        )

    @pytest.mark.asyncio
    async def test_cannot_delegate_multiple_unowned_capabilities(
        self, trust_ops, trust_store, keypair
    ):
        """
        Agent-A has ['analyze_data', 'read_logs'].
        Agent-A tries to delegate ['analyze_data', 'delete_all', 'admin'].
        Delegation MUST fail because 'delete_all' and 'admin' are not owned.
        """
        private_key, public_key = keypair

        # Step 1: Create Agent-A with limited capabilities
        genesis_a = self._create_signed_genesis(private_key, "agent-A", "org-test")
        cap_analyze = self._create_signed_capability(
            private_key, "analyze_data", "org-test"
        )
        cap_logs = self._create_signed_capability(private_key, "read_logs", "org-test")

        chain_a = TrustLineageChain(
            genesis=genesis_a,
            capabilities=[cap_analyze, cap_logs],
            delegations=[],
        )

        await trust_store.initialize()
        await trust_store.store_chain(chain_a)
        await trust_ops.initialize()

        # Step 2: Try to delegate mix of owned and unowned capabilities
        with pytest.raises(CapabilityNotFoundError) as exc_info:
            await trust_ops.delegate(
                delegator_id="agent-A",
                delegatee_id="agent-B",
                task_id="task-002",
                capabilities=["analyze_data", "delete_all", "admin"],
            )

        # The first unowned capability should trigger the error
        error_msg = str(exc_info.value)
        assert "delete_all" in error_msg or "admin" in error_msg


class TestCannotWeakenInheritedConstraints:
    """
    Test 2: Agent tries to weaken constraints during delegation.

    EATP Security Property (CARE-009): Constraints can only be TIGHTENED
    during delegation, never loosened. This prevents "widening attacks"
    where a malicious agent tries to grant more permissions than it has.
    """

    @pytest.fixture
    def validator(self):
        """Create ConstraintValidator for testing."""
        return ConstraintValidator()

    def test_cannot_weaken_cost_limit_constraint(self, validator):
        """
        Parent has cost_limit=1000.
        Child tries to set cost_limit=10000.
        MUST be rejected (widening attack).
        """
        # Step 1: Define parent constraints
        parent_constraints = {
            "cost_limit": 1000,
            "rate_limit": 100,
        }

        # Step 2: Child attempts to WEAKEN cost_limit
        child_constraints = {
            "cost_limit": 10000,  # WIDENED - should fail
            "rate_limit": 50,  # Tightened - OK
        }

        # Step 3: Validate - should FAIL
        result = validator.validate_inheritance(parent_constraints, child_constraints)

        assert result.valid is False
        assert ConstraintViolation.COST_LOOSENED in result.violations
        assert "cost_limit" in result.details

    def test_cannot_expand_allowed_actions(self, validator):
        """
        Parent allows ['read', 'write'].
        Child tries to allow ['read', 'write', 'admin', 'delete'].
        MUST be rejected (adding unauthorized actions).
        """
        parent_constraints = {
            "allowed_actions": ["read", "write"],
        }

        child_constraints = {
            "allowed_actions": ["read", "write", "admin", "delete"],  # EXPANDED
        }

        result = validator.validate_inheritance(parent_constraints, child_constraints)

        assert result.valid is False
        assert ConstraintViolation.ACTION_RESTRICTION_REMOVED in result.violations
        # Check that the expanded actions are mentioned in details
        assert (
            "admin" in result.details["allowed_actions"]
            or "delete" in result.details["allowed_actions"]
        )

    def test_cannot_remove_forbidden_actions(self, validator):
        """
        Parent forbids ['delete', 'admin'].
        Child tries to forbid only ['delete'].
        MUST be rejected (removing a restriction).
        """
        parent_constraints = {
            "forbidden_actions": ["delete", "admin"],
        }

        child_constraints = {
            "forbidden_actions": ["delete"],  # 'admin' restriction removed!
        }

        result = validator.validate_inheritance(parent_constraints, child_constraints)

        assert result.valid is False
        assert ConstraintViolation.FORBIDDEN_ACTION_REMOVED in result.violations
        assert "admin" in result.details["forbidden_actions"]

    def test_cannot_expand_time_window(self, validator):
        """
        Parent allows 09:00-17:00 (business hours).
        Child tries to allow 08:00-20:00 (extended hours).
        MUST be rejected.
        """
        parent_constraints = {
            "time_window": "09:00-17:00",
        }

        child_constraints = {
            "time_window": "08:00-20:00",  # EXPANDED
        }

        result = validator.validate_inheritance(parent_constraints, child_constraints)

        assert result.valid is False
        assert ConstraintViolation.TIME_WINDOW_EXPANDED in result.violations

    def test_cannot_expand_resource_scope(self, validator):
        """
        Parent allows ['data/users/*'].
        Child tries to allow ['data/*'] (broader scope).
        MUST be rejected.
        """
        parent_constraints = {
            "resources": ["data/users/*"],
        }

        child_constraints = {
            "resources": ["data/*"],  # EXPANDED scope
        }

        result = validator.validate_inheritance(parent_constraints, child_constraints)

        assert result.valid is False
        assert ConstraintViolation.RESOURCES_EXPANDED in result.violations

    def test_multiple_weakening_attempts_all_detected(self, validator):
        """
        Child attempts multiple constraint weakenings simultaneously.
        ALL violations MUST be detected and reported.
        """
        parent_constraints = {
            "cost_limit": 1000,
            "rate_limit": 50,
            "allowed_actions": ["read"],
            "forbidden_actions": ["delete", "admin"],
            "time_window": "09:00-17:00",
        }

        child_constraints = {
            "cost_limit": 5000,  # Widened
            "rate_limit": 100,  # Widened
            "allowed_actions": ["read", "write"],  # Expanded
            "forbidden_actions": ["delete"],  # Removed 'admin'
            "time_window": "08:00-18:00",  # Expanded
        }

        result = validator.validate_inheritance(parent_constraints, child_constraints)

        assert result.valid is False
        # All violation types should be present
        assert ConstraintViolation.COST_LOOSENED in result.violations
        assert ConstraintViolation.RATE_LIMIT_INCREASED in result.violations
        assert ConstraintViolation.ACTION_RESTRICTION_REMOVED in result.violations
        assert ConstraintViolation.FORBIDDEN_ACTION_REMOVED in result.violations
        assert ConstraintViolation.TIME_WINDOW_EXPANDED in result.violations
        assert len(result.violations) >= 5


class TestCannotExtendExpirationBeyondParent:
    """
    Test 3: Agent tries to set longer expiration than parent.

    EATP Security Property: Delegated trust CANNOT outlive the delegator's
    trust. If parent's trust expires at T, child's trust MUST expire at or
    before T.
    """

    @pytest.fixture
    def keypair(self):
        """Generate real Ed25519 keypair for signing."""
        return generate_keypair()

    @pytest.fixture
    def authority(self, keypair):
        """Create an organizational authority."""
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
        """Create key manager with the test keypair."""
        private_key, public_key = keypair
        km = TrustKeyManager()
        km.register_key("key-test", private_key)
        return km

    @pytest.fixture
    def trust_store(self):
        """Use real InMemoryTrustStore."""
        return InMemoryTrustStore()

    @pytest.fixture
    def authority_registry(self, authority):
        """Create mock authority registry."""
        registry = AsyncMock(spec=OrganizationalAuthorityRegistry)
        registry.get_authority = AsyncMock(return_value=authority)
        registry.initialize = AsyncMock()
        return registry

    @pytest.fixture
    def trust_ops(self, authority_registry, key_manager, trust_store):
        """Create TrustOperations with test fixtures."""
        return TrustOperations(authority_registry, key_manager, trust_store)

    def _create_signed_genesis(
        self,
        private_key: str,
        agent_id: str,
        authority_id: str,
        expires_at: Optional[datetime] = None,
    ) -> GenesisRecord:
        """Helper to create a signed genesis with specific expiration."""
        genesis = GenesisRecord(
            id=f"gen-{uuid4()}",
            agent_id=agent_id,
            authority_id=authority_id,
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            signature="",
        )
        payload = serialize_for_signing(genesis.to_signing_payload())
        genesis.signature = sign(payload, private_key)
        return genesis

    def _create_signed_capability(
        self, private_key: str, capability_name: str, attester_id: str
    ) -> CapabilityAttestation:
        """Helper to create a signed capability."""
        capability = CapabilityAttestation(
            id=f"cap-{uuid4()}",
            capability=capability_name,
            capability_type=CapabilityType.ACCESS,
            constraints=[],
            attester_id=attester_id,
            attested_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            signature="",
        )
        payload = serialize_for_signing(capability.to_signing_payload())
        capability.signature = sign(payload, private_key)
        return capability

    @pytest.mark.asyncio
    async def test_delegation_expiry_capped_to_parent(
        self, trust_ops, trust_store, keypair
    ):
        """
        Parent trust expires in 7 days.
        Child requests delegation expiring in 30 days.
        Delegation expiry MUST be capped to 7 days (parent's expiry).
        """
        private_key, public_key = keypair

        # Step 1: Create parent with 7-day expiry
        parent_expires = datetime.now(timezone.utc) + timedelta(days=7)
        genesis_a = self._create_signed_genesis(
            private_key, "agent-A", "org-test", expires_at=parent_expires
        )
        cap_analyze = self._create_signed_capability(
            private_key, "analyze_data", "org-test"
        )

        chain_a = TrustLineageChain(
            genesis=genesis_a,
            capabilities=[cap_analyze],
            delegations=[],
        )

        await trust_store.initialize()
        await trust_store.store_chain(chain_a)
        await trust_ops.initialize()

        # Step 2: Request delegation with 30-day expiry
        requested_expiry = datetime.now(timezone.utc) + timedelta(days=30)

        delegation = await trust_ops.delegate(
            delegator_id="agent-A",
            delegatee_id="agent-B",
            task_id="task-001",
            capabilities=["analyze_data"],
            expires_at=requested_expiry,
        )

        # Step 3: Verify delegation expiry was CAPPED to parent's expiry
        # The delegation's expires_at should be <= parent_expires
        assert delegation.expires_at is not None
        assert delegation.expires_at <= parent_expires

        # Verify it's not the requested 30 days
        assert delegation.expires_at < requested_expiry

    @pytest.mark.asyncio
    async def test_delegation_without_explicit_expiry_uses_parent(
        self, trust_ops, trust_store, keypair
    ):
        """
        Parent trust expires in 7 days.
        Child requests delegation without specifying expiry.
        Delegation MUST inherit parent's expiry.
        """
        private_key, public_key = keypair

        parent_expires = datetime.now(timezone.utc) + timedelta(days=7)
        genesis_a = self._create_signed_genesis(
            private_key, "agent-A", "org-test", expires_at=parent_expires
        )
        cap_analyze = self._create_signed_capability(
            private_key, "analyze_data", "org-test"
        )

        chain_a = TrustLineageChain(
            genesis=genesis_a,
            capabilities=[cap_analyze],
            delegations=[],
        )

        await trust_store.initialize()
        await trust_store.store_chain(chain_a)
        await trust_ops.initialize()

        # No expires_at specified
        delegation = await trust_ops.delegate(
            delegator_id="agent-A",
            delegatee_id="agent-B",
            task_id="task-002",
            capabilities=["analyze_data"],
        )

        # Should use parent's expiry
        assert delegation.expires_at is not None
        assert delegation.expires_at == parent_expires


class TestTamperedGenesisSignatureRejected:
    """
    Test 4: Modify genesis signature, verify chain validation fails.

    EATP Security Property: All chain components are cryptographically
    signed. Any modification to signed data MUST be detected and rejected.
    """

    @pytest.fixture
    def keypair(self):
        """Generate real Ed25519 keypair for signing."""
        return generate_keypair()

    @pytest.fixture
    def authority(self, keypair):
        """Create an organizational authority."""
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
        """Create key manager with the test keypair."""
        private_key, public_key = keypair
        km = TrustKeyManager()
        km.register_key("key-test", private_key)
        return km

    @pytest.fixture
    def trust_store(self):
        """Use real InMemoryTrustStore."""
        return InMemoryTrustStore()

    @pytest.fixture
    def authority_registry(self, authority):
        """Create mock authority registry."""
        registry = AsyncMock(spec=OrganizationalAuthorityRegistry)
        registry.get_authority = AsyncMock(return_value=authority)
        registry.initialize = AsyncMock()
        return registry

    @pytest.fixture
    def trust_ops(self, authority_registry, key_manager, trust_store):
        """Create TrustOperations with test fixtures."""
        return TrustOperations(authority_registry, key_manager, trust_store)

    def test_tampered_genesis_signature_detected(self, keypair):
        """
        Create valid genesis, then modify authority_id after signing.
        Signature verification MUST fail.
        """
        private_key, public_key = keypair

        # Step 1: Create and sign a valid genesis
        genesis = GenesisRecord(
            id="gen-001",
            agent_id="agent-A",
            authority_id="org-test",  # Original authority
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            signature="",
        )

        # Sign with real Ed25519
        payload = serialize_for_signing(genesis.to_signing_payload())
        genesis.signature = sign(payload, private_key)

        # Step 2: Verify signature is valid before tampering
        valid_before = verify_signature(payload, genesis.signature, public_key)
        assert valid_before is True

        # Step 3: TAMPER - Modify the authority_id AFTER signing
        genesis.authority_id = "org-attacker"  # Changed!

        # Step 4: Verify signature is now INVALID
        tampered_payload = serialize_for_signing(genesis.to_signing_payload())
        valid_after = verify_signature(tampered_payload, genesis.signature, public_key)

        assert valid_after is False

    def test_tampered_genesis_agent_id_detected(self, keypair):
        """
        Create valid genesis, then modify agent_id after signing.
        Signature verification MUST fail.
        """
        private_key, public_key = keypair

        genesis = GenesisRecord(
            id="gen-001",
            agent_id="agent-A",
            authority_id="org-test",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            signature="",
        )

        payload = serialize_for_signing(genesis.to_signing_payload())
        genesis.signature = sign(payload, private_key)

        # Tamper: Change agent_id
        genesis.agent_id = "agent-ATTACKER"

        tampered_payload = serialize_for_signing(genesis.to_signing_payload())
        valid = verify_signature(tampered_payload, genesis.signature, public_key)

        assert valid is False

    def test_tampered_genesis_expiry_detected(self, keypair):
        """
        Create valid genesis with 30-day expiry, then extend to 365 days.
        Signature verification MUST fail.
        """
        private_key, public_key = keypair

        original_expiry = datetime.now(timezone.utc) + timedelta(days=30)
        genesis = GenesisRecord(
            id="gen-001",
            agent_id="agent-A",
            authority_id="org-test",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            expires_at=original_expiry,
            signature="",
        )

        payload = serialize_for_signing(genesis.to_signing_payload())
        genesis.signature = sign(payload, private_key)

        # Tamper: Extend expiry to 365 days
        genesis.expires_at = datetime.now(timezone.utc) + timedelta(days=365)

        tampered_payload = serialize_for_signing(genesis.to_signing_payload())
        valid = verify_signature(tampered_payload, genesis.signature, public_key)

        assert valid is False


class TestInjectedDelegationRejected:
    """
    Test 5: Inject fake delegation into chain, verify rejection.

    EATP Security Property: All delegations MUST be cryptographically
    signed by an authorized party. An attacker cannot inject fake
    delegations into a chain.
    """

    @pytest.fixture
    def keypair(self):
        """Generate real Ed25519 keypair for signing (authorized)."""
        return generate_keypair()

    @pytest.fixture
    def attacker_keypair(self):
        """Generate a DIFFERENT keypair for the attacker."""
        return generate_keypair()

    @pytest.fixture
    def authority(self, keypair):
        """Create authority with the authorized keypair."""
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
        """Create key manager with the authorized keypair."""
        private_key, public_key = keypair
        km = TrustKeyManager()
        km.register_key("key-test", private_key)
        return km

    @pytest.fixture
    def trust_store(self):
        """Use real InMemoryTrustStore."""
        return InMemoryTrustStore()

    @pytest.fixture
    def authority_registry(self, authority):
        """Create mock authority registry."""
        registry = AsyncMock(spec=OrganizationalAuthorityRegistry)
        registry.get_authority = AsyncMock(return_value=authority)
        registry.initialize = AsyncMock()
        return registry

    @pytest.fixture
    def trust_ops(self, authority_registry, key_manager, trust_store):
        """Create TrustOperations with test fixtures."""
        return TrustOperations(authority_registry, key_manager, trust_store)

    def _create_signed_genesis(
        self, private_key: str, agent_id: str, authority_id: str
    ) -> GenesisRecord:
        """Helper to create a signed genesis."""
        genesis = GenesisRecord(
            id=f"gen-{uuid4()}",
            agent_id=agent_id,
            authority_id=authority_id,
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            signature="",
        )
        payload = serialize_for_signing(genesis.to_signing_payload())
        genesis.signature = sign(payload, private_key)
        return genesis

    @pytest.mark.asyncio
    async def test_injected_delegation_with_wrong_key_rejected(
        self, trust_ops, trust_store, keypair, attacker_keypair
    ):
        """
        Create a valid chain for Agent-A.
        Attacker creates a fake delegation (signed with wrong key).
        Signature verification MUST fail.
        """
        private_key, public_key = keypair
        attacker_private, attacker_public = attacker_keypair

        # Step 1: Create valid chain for Agent-A
        genesis_a = self._create_signed_genesis(private_key, "agent-A", "org-test")
        chain_a = TrustLineageChain(
            genesis=genesis_a,
            capabilities=[],
            delegations=[],
        )

        # Step 2: Attacker creates a FAKE delegation using their own key
        fake_delegation = DelegationRecord(
            id="del-fake",
            delegator_id="agent-A",
            delegatee_id="agent-ATTACKER",
            task_id="task-evil",
            capabilities_delegated=["admin_access", "delete_all"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="",
        )

        # Attacker signs with THEIR key (not the authorized key)
        fake_payload = serialize_for_signing(fake_delegation.to_signing_payload())
        fake_delegation.signature = sign(fake_payload, attacker_private)

        # Step 3: Add fake delegation to chain
        chain_a.delegations.append(fake_delegation)

        await trust_store.initialize()
        await trust_store.store_chain(chain_a)
        await trust_ops.initialize()

        # Step 4: Verify delegation signature - should FAIL
        result = await trust_ops._verify_delegation_signature(fake_delegation, chain_a)

        assert result.valid is False
        assert "Invalid delegation signature" in result.reason

    def test_delegation_with_forged_signature_detected(self, keypair, attacker_keypair):
        """
        Attacker creates delegation and forges signature.
        Verification with correct public key MUST fail.
        """
        private_key, public_key = keypair
        attacker_private, attacker_public = attacker_keypair

        # Create delegation
        delegation = DelegationRecord(
            id="del-001",
            delegator_id="agent-A",
            delegatee_id="agent-ATTACKER",
            task_id="task-evil",
            capabilities_delegated=["admin_access"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="",
        )

        # Attacker signs with their key
        payload = serialize_for_signing(delegation.to_signing_payload())
        delegation.signature = sign(payload, attacker_private)

        # Verify with the CORRECT public key (authority's key)
        valid = verify_signature(payload, delegation.signature, public_key)

        # Should FAIL because it was signed with wrong key
        assert valid is False

    def test_delegation_with_random_signature_detected(self, keypair):
        """
        Attacker creates delegation with random/garbage signature.
        Verification MUST fail.
        """
        private_key, public_key = keypair

        delegation = DelegationRecord(
            id="del-001",
            delegator_id="agent-A",
            delegatee_id="agent-ATTACKER",
            task_id="task-evil",
            capabilities_delegated=["admin_access"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="totally_fake_signature_base64_garbage_data_here",  # Garbage
        )

        payload = serialize_for_signing(delegation.to_signing_payload())

        # Verification should fail (invalid base64 or wrong signature)
        try:
            valid = verify_signature(payload, delegation.signature, public_key)
            assert valid is False
        except Exception:
            # Any exception during verification is also acceptable
            # (e.g., base64 decode error)
            pass


class TestHashChainIntegrityVerified:
    """
    Test 6: Verify hash chain detects any modification to chain entries.

    EATP Security Property (CARE-006): The linked hash chain creates
    a tamper-evident blockchain-like structure. Any modification to
    any entry breaks the chain and is detectable.
    """

    def test_hash_chain_detects_modified_entry(self):
        """
        Create a valid hash chain with 3 entries.
        Modify one entry's hash.
        Chain integrity verification MUST detect the tampering.
        """
        # Step 1: Create a valid linked hash chain
        chain = LinkedHashChain()
        original_hashes = ["hash_a", "hash_b", "hash_c"]

        for i, h in enumerate(original_hashes):
            chain.add_hash(f"agent-{i + 1}", h)

        # Step 2: Verify chain is valid before tampering
        valid_before, break_index = chain.verify_chain_linkage(original_hashes)
        assert valid_before is True
        assert break_index is None

        # Step 3: Tamper - provide wrong original hash for verification
        tampered_hashes = ["hash_a", "hash_TAMPERED", "hash_c"]
        valid_after, break_index = chain.verify_chain_linkage(tampered_hashes)

        # Step 4: Chain verification MUST fail at the tampered position
        assert valid_after is False
        assert break_index == 1  # Tampering detected at index 1

    def test_hash_chain_detects_missing_entry(self):
        """
        Create a valid hash chain with 3 entries.
        Verify with only 2 original hashes.
        Chain verification MUST detect the gap.
        """
        chain = LinkedHashChain()
        chain.add_hash("agent-1", "hash_a")
        chain.add_hash("agent-2", "hash_b")
        chain.add_hash("agent-3", "hash_c")

        # Try to verify with missing middle entry
        missing_hashes = ["hash_a", "hash_c"]  # hash_b missing
        valid, break_index = chain.verify_chain_linkage(missing_hashes)

        assert valid is False
        # Break detected due to length mismatch or hash mismatch
        assert break_index is not None

    def test_hash_chain_detects_reordered_entries(self):
        """
        Create a valid hash chain with 3 entries.
        Verify with hashes in wrong order.
        Chain verification MUST detect the reordering.
        """
        chain = LinkedHashChain()
        chain.add_hash("agent-1", "hash_a")
        chain.add_hash("agent-2", "hash_b")
        chain.add_hash("agent-3", "hash_c")

        # Wrong order
        reordered_hashes = ["hash_c", "hash_b", "hash_a"]
        valid, break_index = chain.verify_chain_linkage(reordered_hashes)

        assert valid is False
        assert break_index == 0  # First entry doesn't match

    def test_hash_chain_detects_additional_entries(self):
        """
        Create a valid hash chain with 2 entries.
        Verify with 4 hashes (attacker trying to inject history).
        Chain verification MUST detect the mismatch.
        """
        chain = LinkedHashChain()
        chain.add_hash("agent-1", "hash_a")
        chain.add_hash("agent-2", "hash_b")

        # Attacker tries to claim there were more entries
        extra_hashes = ["hash_x", "hash_y", "hash_a", "hash_b"]
        valid, break_index = chain.verify_chain_linkage(extra_hashes)

        assert valid is False

    def test_trust_chain_hash_changes_on_capability_added(self):
        """
        Create a TrustLineageChain.
        Compute hash.
        Add a new capability.
        Hash MUST change (capability ID list changed).
        """
        genesis = GenesisRecord(
            id="gen-001",
            agent_id="agent-A",
            authority_id="org-test",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature="sig",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )

        cap1 = CapabilityAttestation(
            id="cap-001",
            capability="analyze_data",
            capability_type=CapabilityType.ACCESS,
            constraints=["read_only"],
            attester_id="org-test",
            attested_at=datetime.now(timezone.utc),
            signature="cap-sig",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )

        chain = TrustLineageChain(genesis=genesis, capabilities=[cap1])

        # Compute original hash
        original_hash = chain.hash()

        # Add a new capability (changes capability ID list)
        cap2 = CapabilityAttestation(
            id="cap-002",
            capability="admin_access",
            capability_type=CapabilityType.ACCESS,
            constraints=[],
            attester_id="org-test",
            attested_at=datetime.now(timezone.utc),
            signature="cap-sig-2",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        chain.capabilities.append(cap2)

        # Hash MUST change because capability ID list changed
        modified_hash = chain.hash()

        assert original_hash != modified_hash

    def test_trust_chain_hash_changes_on_delegation_added(self):
        """
        Create a TrustLineageChain.
        Compute hash.
        Add a delegation.
        Hash MUST change (delegation ID list changed).
        """
        genesis = GenesisRecord(
            id="gen-001",
            agent_id="agent-A",
            authority_id="org-test",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature="sig",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )

        chain = TrustLineageChain(genesis=genesis, capabilities=[], delegations=[])

        # Compute original hash
        original_hash = chain.hash()

        # Add a delegation (changes delegation ID list)
        delegation = DelegationRecord(
            id="del-001",
            delegator_id="agent-A",
            delegatee_id="agent-B",
            task_id="task-001",
            capabilities_delegated=["analyze_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature="del-sig",
        )
        chain.delegations.append(delegation)

        # Hash MUST change because delegation ID list changed
        modified_hash = chain.hash()

        assert original_hash != modified_hash

    def test_linked_hash_detects_tampering_via_detect_method(self):
        """
        Use detect_tampering() method to identify hash mismatches.
        """
        chain = LinkedHashChain()
        linked_hash = chain.add_hash("agent-001", "original_hash")

        # No tampering - detect_tampering returns False
        assert chain.detect_tampering("agent-001", linked_hash) is False

        # Tampered hash - detect_tampering returns True
        assert chain.detect_tampering("agent-001", "tampered_hash") is True

        # Non-existent agent - also returns True (suspicious)
        assert chain.detect_tampering("agent-999", "any_hash") is True
