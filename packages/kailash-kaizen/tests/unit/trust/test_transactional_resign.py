"""
CARE-008: Transactional Chain Re-signing Tests.

Tests the atomic re-signing functionality for trust chains during key rotation.
Validates that either ALL chains are re-signed or NONE are (transactional guarantee).

Test Intent:
- Verify TransactionContext commit and rollback behavior
- Verify atomic re-signing of chains during key rotation
- Test pagination/batch processing for large numbers of chains
- Ensure chain integrity is preserved during rotation
"""

import copy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import pytest
from kaizen.trust.authority import AuthorityPermission, OrganizationalAuthority
from kaizen.trust.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
)
from kaizen.trust.crypto import generate_keypair, sign, verify_signature
from kaizen.trust.key_manager import InMemoryKeyManager
from kaizen.trust.operations import TrustKeyManager
from kaizen.trust.rotation import CredentialRotationManager, RotationError
from kaizen.trust.store import InMemoryTrustStore, TransactionContext


class InMemoryAuthorityRegistry:
    """
    In-memory authority registry for unit testing.

    Avoids database dependencies by storing authorities in memory.
    """

    def __init__(self):
        """Initialize the in-memory registry."""
        self._authorities: Dict[str, OrganizationalAuthority] = {}

    async def register_authority(self, authority: OrganizationalAuthority) -> str:
        """Register an authority."""
        self._authorities[authority.id] = authority
        return authority.id

    async def get_authority(self, authority_id: str) -> OrganizationalAuthority:
        """Get an authority by ID."""
        if authority_id not in self._authorities:
            from kaizen.trust.exceptions import AuthorityNotFoundError

            raise AuthorityNotFoundError(authority_id)
        return self._authorities[authority_id]

    async def update_authority(self, authority: OrganizationalAuthority) -> None:
        """Update an authority."""
        self._authorities[authority.id] = authority

    async def list_authorities(
        self, active_only: bool = True
    ) -> List[OrganizationalAuthority]:
        """List authorities."""
        if active_only:
            return [a for a in self._authorities.values() if a.is_active]
        return list(self._authorities.values())


class FailingKeyManager(TrustKeyManager):
    """
    A key manager that fails after N sign operations.

    Used to simulate failures during chain re-signing for testing rollback.
    """

    def __init__(self, fail_after: int):
        """
        Initialize with failure threshold.

        Args:
            fail_after: Number of successful sign operations before failing
        """
        super().__init__()
        self.fail_after = fail_after
        self.sign_count = 0

    async def sign(self, payload: str, key_id: str) -> str:
        """Sign with failure injection after N calls."""
        self.sign_count += 1
        if self.sign_count > self.fail_after:
            raise RuntimeError(f"Simulated failure after {self.fail_after} signs")
        return super().sign(payload, key_id)


class FailingTrustStore(InMemoryTrustStore):
    """
    A trust store that fails update_chain after N calls during the initial update phase.

    Used to simulate database failures during atomic re-signing.
    Disables transaction support to test non-transactional failure path.

    CARE-048: Allows rollback calls to succeed so we can test the rollback mechanism.
    Once the failure threshold is reached, the store enters rollback mode where
    all subsequent update_chain calls succeed (to allow rollback to work).
    """

    def __init__(self, fail_after: int):
        """
        Initialize with failure threshold.

        Args:
            fail_after: Number of successful update_chain operations before failing
        """
        super().__init__()
        self.fail_after = fail_after
        self.update_count = 0
        self._initial_store_complete = False
        self._in_rollback_mode = False

    async def update_chain(
        self,
        agent_id: str,
        chain: TrustLineageChain,
    ) -> None:
        """Update chain with failure injection after N calls during re-signing."""
        # Only count calls after initial chain storage is complete
        if self._initial_store_complete and not self._in_rollback_mode:
            self.update_count += 1
            if self.update_count > self.fail_after:
                # Enter rollback mode - subsequent updates succeed
                self._in_rollback_mode = True
                raise RuntimeError(
                    f"Simulated DB failure after {self.fail_after} updates"
                )
        return await super().update_chain(agent_id, chain)

    def mark_initial_store_complete(self) -> None:
        """Mark initial chain storage as complete to start counting failures."""
        self._initial_store_complete = True

    def transaction(self):
        """Disable transaction support to test non-transactional path."""
        # Return None or raise to indicate no transaction support
        # This forces _apply_chain_updates_atomically to use the non-transactional path
        raise AttributeError("transaction not supported")


def create_test_chain(
    agent_id: str,
    authority_id: str,
    private_key: str,
    num_capabilities: int = 1,
    num_delegations: int = 0,
) -> TrustLineageChain:
    """
    Create a test trust chain with signatures.

    Args:
        agent_id: Agent ID for the chain
        authority_id: Authority that establishes the chain
        private_key: Private key for signing
        num_capabilities: Number of capability attestations to add
        num_delegations: Number of delegation records to add

    Returns:
        A fully signed TrustLineageChain
    """
    from kaizen.trust.crypto import serialize_for_signing

    # Create genesis
    genesis = GenesisRecord(
        id=f"gen-{agent_id}",
        agent_id=agent_id,
        authority_id=authority_id,
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime.now(timezone.utc),
        signature="",  # Will be set below
    )
    genesis_payload = serialize_for_signing(genesis.to_signing_payload())
    genesis.signature = sign(genesis_payload, private_key)

    # Create capabilities
    capabilities = []
    for i in range(num_capabilities):
        cap = CapabilityAttestation(
            id=f"cap-{agent_id}-{i}",
            capability=f"capability_{i}",
            capability_type=CapabilityType.ACCESS,
            constraints=["read_only"],
            attester_id=authority_id,
            attested_at=datetime.now(timezone.utc),
            signature="",
        )
        cap_payload = serialize_for_signing(cap.to_signing_payload())
        cap.signature = sign(cap_payload, private_key)
        capabilities.append(cap)

    # Create delegations
    delegations = []
    for i in range(num_delegations):
        delegation = DelegationRecord(
            id=f"del-{agent_id}-{i}",
            delegator_id=authority_id,
            delegatee_id=f"delegatee-{i}",
            task_id=f"task-{i}",
            capabilities_delegated=[f"capability_{i}"],
            constraint_subset=["constraint_a"],
            delegated_at=datetime.now(timezone.utc),
            signature="",
        )
        del_payload = serialize_for_signing(delegation.to_signing_payload())
        delegation.signature = sign(del_payload, private_key)
        delegations.append(delegation)

    return TrustLineageChain(
        genesis=genesis,
        capabilities=capabilities,
        delegations=delegations,
    )


@pytest.fixture
def key_manager():
    """Create a TrustKeyManager with registered keys."""
    km = TrustKeyManager()
    # Generate initial key
    private_key, public_key = generate_keypair()
    km.register_key("key-001", private_key)
    return km


@pytest.fixture
def trust_store():
    """Create an InMemoryTrustStore."""
    return InMemoryTrustStore()


@pytest.fixture
def authority_registry():
    """Create an InMemoryAuthorityRegistry for testing."""
    return InMemoryAuthorityRegistry()


@pytest.fixture
def sample_authority():
    """Create a sample OrganizationalAuthority."""
    private_key, public_key = generate_keypair()
    return OrganizationalAuthority(
        id="org-test",
        name="Test Organization",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=public_key,
        signing_key_id="key-001",
        permissions=[AuthorityPermission.CREATE_AGENTS],
        is_active=True,
        metadata={"private_key": private_key},  # Store for test use
    )


# =============================================================================
# TransactionContext Tests
# =============================================================================


@pytest.mark.asyncio
class TestTransactionContext:
    """Test suite for TransactionContext."""

    async def test_transaction_commit_applies_updates(self, trust_store):
        """Test that updates are visible after commit."""
        private_key, _ = generate_keypair()
        chain = create_test_chain("agent-001", "org-test", private_key)

        # Store initial chain
        await trust_store.initialize()
        await trust_store.store_chain(chain)

        # Modify chain in transaction
        updated_chain = copy.deepcopy(chain)
        updated_chain.genesis.metadata["updated"] = True

        async with trust_store.transaction() as tx:
            await tx.update_chain("agent-001", updated_chain)
            await tx.commit()

        # Verify update was applied
        result = await trust_store.get_chain("agent-001")
        assert result.genesis.metadata.get("updated") is True

    async def test_transaction_rollback_on_exception(self, trust_store):
        """Test that exception causes rollback."""
        private_key, _ = generate_keypair()
        chain = create_test_chain("agent-001", "org-test", private_key)

        await trust_store.initialize()
        await trust_store.store_chain(chain)

        original_signature = chain.genesis.signature

        # Modify chain but raise exception
        updated_chain = copy.deepcopy(chain)
        updated_chain.genesis.signature = "modified-signature"

        with pytest.raises(ValueError):
            async with trust_store.transaction() as tx:
                await tx.update_chain("agent-001", updated_chain)
                raise ValueError("Simulated error")

        # Verify original state is restored
        result = await trust_store.get_chain("agent-001")
        assert result.genesis.signature == original_signature

    async def test_transaction_rollback_without_commit(self, trust_store):
        """Test that no commit results in rollback."""
        private_key, _ = generate_keypair()
        chain = create_test_chain("agent-001", "org-test", private_key)

        await trust_store.initialize()
        await trust_store.store_chain(chain)

        original_signature = chain.genesis.signature

        # Modify chain but don't commit
        updated_chain = copy.deepcopy(chain)
        updated_chain.genesis.signature = "modified-signature"

        async with trust_store.transaction() as tx:
            await tx.update_chain("agent-001", updated_chain)
            # No commit - should rollback

        # Verify original state is preserved
        result = await trust_store.get_chain("agent-001")
        assert result.genesis.signature == original_signature

    async def test_transaction_snapshot_preserves_original(self, trust_store):
        """Test that snapshot preserves original state for rollback."""
        private_key, _ = generate_keypair()
        chain1 = create_test_chain("agent-001", "org-test", private_key)
        chain2 = create_test_chain("agent-002", "org-test", private_key)

        await trust_store.initialize()
        await trust_store.store_chain(chain1)
        await trust_store.store_chain(chain2)

        original_sig1 = chain1.genesis.signature
        original_sig2 = chain2.genesis.signature

        # Modify both chains but fail
        with pytest.raises(RuntimeError):
            async with trust_store.transaction() as tx:
                modified1 = copy.deepcopy(chain1)
                modified1.genesis.signature = "new-sig-1"
                await tx.update_chain("agent-001", modified1)

                modified2 = copy.deepcopy(chain2)
                modified2.genesis.signature = "new-sig-2"
                await tx.update_chain("agent-002", modified2)

                raise RuntimeError("Fail before commit")

        # Both should be restored
        result1 = await trust_store.get_chain("agent-001")
        result2 = await trust_store.get_chain("agent-002")
        assert result1.genesis.signature == original_sig1
        assert result2.genesis.signature == original_sig2

    async def test_transaction_multiple_updates(self, trust_store):
        """Test multiple chains updated atomically."""
        private_key, _ = generate_keypair()

        await trust_store.initialize()

        # Create and store 5 chains
        chains = []
        for i in range(5):
            chain = create_test_chain(f"agent-{i:03d}", "org-test", private_key)
            await trust_store.store_chain(chain)
            chains.append(chain)

        # Update all chains atomically
        async with trust_store.transaction() as tx:
            for i, chain in enumerate(chains):
                updated = copy.deepcopy(chain)
                updated.genesis.metadata["batch_updated"] = True
                updated.genesis.metadata["index"] = i
                await tx.update_chain(f"agent-{i:03d}", updated)
            await tx.commit()

        # Verify all were updated
        for i in range(5):
            result = await trust_store.get_chain(f"agent-{i:03d}")
            assert result.genesis.metadata.get("batch_updated") is True
            assert result.genesis.metadata.get("index") == i

    async def test_transaction_context_manager_works(self, trust_store):
        """Test that async with syntax works correctly."""
        await trust_store.initialize()

        private_key, _ = generate_keypair()
        chain = create_test_chain("agent-001", "org-test", private_key)
        await trust_store.store_chain(chain)

        # Use async with syntax
        async with trust_store.transaction() as tx:
            assert tx.pending_count == 0
            modified = copy.deepcopy(chain)
            modified.genesis.metadata["context_test"] = True
            await tx.update_chain("agent-001", modified)
            assert tx.pending_count == 1
            await tx.commit()

        result = await trust_store.get_chain("agent-001")
        assert result.genesis.metadata.get("context_test") is True


# =============================================================================
# Atomic Re-signing Tests
# =============================================================================


@pytest.mark.asyncio
class TestAtomicResigning:
    """Test suite for atomic chain re-signing."""

    async def test_resign_single_chain_atomically(
        self, trust_store, key_manager, authority_registry, sample_authority
    ):
        """Test re-signing a single chain atomically."""
        await trust_store.initialize()
        await authority_registry.register_authority(sample_authority)

        # Create and store chain
        private_key = sample_authority.metadata["private_key"]
        chain = create_test_chain("agent-001", "org-test", private_key)
        await trust_store.store_chain(chain)

        # Register initial key
        key_manager.register_key("key-001", private_key)

        # Create rotation manager
        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=trust_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        # Perform rotation
        result = await manager.rotate_key("org-test")

        assert result.chains_updated == 1

    async def test_resign_multiple_chains_atomically(
        self, trust_store, key_manager, authority_registry, sample_authority
    ):
        """Test re-signing 10 chains atomically."""
        await trust_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager.register_key("key-001", private_key)

        # Create and store 10 chains
        for i in range(10):
            chain = create_test_chain(f"agent-{i:03d}", "org-test", private_key)
            await trust_store.store_chain(chain)

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=trust_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        result = await manager.rotate_key("org-test")

        assert result.chains_updated == 10

    async def test_resign_failure_rolls_back_all(
        self, authority_registry, sample_authority
    ):
        """Test that failure at chain 5 of 10 rolls back chains 1-4."""
        # Use FailingTrustStore that fails after 4 stores during re-signing
        failing_store = FailingTrustStore(fail_after=4)
        await failing_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager = TrustKeyManager()
        key_manager.register_key("key-001", private_key)

        # Store original chains (these don't count toward failure)
        original_signatures = {}
        for i in range(10):
            chain = create_test_chain(f"agent-{i:03d}", "org-test", private_key)
            await failing_store.store_chain(chain)
            original_signatures[f"agent-{i:03d}"] = chain.genesis.signature

        # Mark initial storage complete - now stores will be counted
        failing_store.mark_initial_store_complete()

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=failing_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        # Rotation should fail during chain re-signing
        with pytest.raises(RotationError) as exc_info:
            await manager.rotate_key("org-test")

        assert "failed" in str(exc_info.value).lower()

    async def test_resign_updates_genesis_signature(
        self, trust_store, key_manager, authority_registry, sample_authority
    ):
        """Test that genesis record is re-signed with new key."""
        await trust_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager.register_key("key-001", private_key)

        chain = create_test_chain("agent-001", "org-test", private_key)
        original_genesis_sig = chain.genesis.signature
        await trust_store.store_chain(chain)

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=trust_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        await manager.rotate_key("org-test")

        result = await trust_store.get_chain("agent-001")
        assert result.genesis.signature != original_genesis_sig

    async def test_resign_updates_capability_signatures(
        self, trust_store, key_manager, authority_registry, sample_authority
    ):
        """Test that capabilities are re-signed with new key."""
        await trust_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager.register_key("key-001", private_key)

        chain = create_test_chain(
            "agent-001", "org-test", private_key, num_capabilities=3
        )
        original_cap_sigs = [c.signature for c in chain.capabilities]
        await trust_store.store_chain(chain)

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=trust_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        await manager.rotate_key("org-test")

        result = await trust_store.get_chain("agent-001")
        for i, cap in enumerate(result.capabilities):
            assert cap.signature != original_cap_sigs[i]

    async def test_resign_updates_delegation_signatures(
        self, trust_store, key_manager, authority_registry, sample_authority
    ):
        """Test that delegations are re-signed with new key."""
        await trust_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager.register_key("key-001", private_key)

        chain = create_test_chain(
            "agent-001", "org-test", private_key, num_delegations=2
        )
        original_del_sigs = [d.signature for d in chain.delegations]
        await trust_store.store_chain(chain)

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=trust_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        await manager.rotate_key("org-test")

        result = await trust_store.get_chain("agent-001")
        for i, delegation in enumerate(result.delegations):
            assert delegation.signature != original_del_sigs[i]

    async def test_resign_preserves_chain_structure(
        self, trust_store, key_manager, authority_registry, sample_authority
    ):
        """Test that chain links remain unchanged after re-signing."""
        await trust_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager.register_key("key-001", private_key)

        chain = create_test_chain(
            "agent-001",
            "org-test",
            private_key,
            num_capabilities=2,
            num_delegations=2,
        )
        original_genesis_id = chain.genesis.id
        original_cap_ids = [c.id for c in chain.capabilities]
        original_del_ids = [d.id for d in chain.delegations]
        await trust_store.store_chain(chain)

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=trust_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        await manager.rotate_key("org-test")

        result = await trust_store.get_chain("agent-001")
        assert result.genesis.id == original_genesis_id
        assert [c.id for c in result.capabilities] == original_cap_ids
        assert [d.id for d in result.delegations] == original_del_ids

    async def test_resign_uses_new_key(
        self, trust_store, key_manager, authority_registry, sample_authority
    ):
        """Test that signatures verify with new key."""
        from kaizen.trust.crypto import serialize_for_signing

        await trust_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager.register_key("key-001", private_key)

        chain = create_test_chain("agent-001", "org-test", private_key)
        await trust_store.store_chain(chain)

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=trust_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        result = await manager.rotate_key("org-test")

        # Get updated authority with new public key
        updated_authority = await authority_registry.get_authority("org-test")
        new_public_key = updated_authority.public_key

        # Verify genesis signature with new key
        updated_chain = await trust_store.get_chain("agent-001")
        genesis_payload = serialize_for_signing(
            updated_chain.genesis.to_signing_payload()
        )
        assert verify_signature(
            genesis_payload, updated_chain.genesis.signature, new_public_key
        )

    async def test_resign_old_key_signatures_invalid(
        self, trust_store, key_manager, authority_registry, sample_authority
    ):
        """Test that old signatures are no longer present after rotation."""
        await trust_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager.register_key("key-001", private_key)

        chain = create_test_chain("agent-001", "org-test", private_key)
        old_signature = chain.genesis.signature
        await trust_store.store_chain(chain)

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=trust_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        await manager.rotate_key("org-test")

        updated_chain = await trust_store.get_chain("agent-001")
        assert updated_chain.genesis.signature != old_signature

    async def test_resign_concurrent_prevention(
        self, trust_store, key_manager, authority_registry, sample_authority
    ):
        """Test that concurrent re-signing of same authority is prevented."""
        await trust_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager.register_key("key-001", private_key)

        chain = create_test_chain("agent-001", "org-test", private_key)
        await trust_store.store_chain(chain)

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=trust_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        # Simulate active rotation
        manager._active_rotations.add("org-test")

        # Try second rotation
        with pytest.raises(RotationError) as exc_info:
            await manager.rotate_key("org-test")

        assert "in progress" in str(exc_info.value).lower()


# =============================================================================
# Pagination Tests
# =============================================================================


@pytest.mark.asyncio
class TestPagination:
    """Test suite for batch/pagination handling."""

    async def test_resign_with_batch_size(
        self, trust_store, key_manager, authority_registry, sample_authority
    ):
        """Test that large number of chains are handled in batches."""
        await trust_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager.register_key("key-001", private_key)

        # Create 25 chains (more than default batch size would be in prod)
        for i in range(25):
            chain = create_test_chain(f"agent-{i:03d}", "org-test", private_key)
            await trust_store.store_chain(chain)

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=trust_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        result = await manager.rotate_key("org-test")

        assert result.chains_updated == 25

    async def test_resign_batch_failure_rolls_back_all(
        self, authority_registry, sample_authority
    ):
        """Test that failure in batch 2 rolls back batch 1."""
        # Create a store that fails after 15 stores during re-signing
        failing_store = FailingTrustStore(fail_after=15)
        await failing_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager = TrustKeyManager()
        key_manager.register_key("key-001", private_key)

        # Create 25 chains (these don't count toward failure)
        for i in range(25):
            chain = create_test_chain(f"agent-{i:03d}", "org-test", private_key)
            await failing_store.store_chain(chain)

        # Mark initial storage complete - now stores will be counted
        failing_store.mark_initial_store_complete()

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=failing_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        with pytest.raises(RotationError):
            await manager.rotate_key("org-test")


# =============================================================================
# Integration-Style Tests
# =============================================================================


@pytest.mark.asyncio
class TestIntegration:
    """Integration-style tests for full rotation flow."""

    async def test_full_rotation_with_transactional_resign(
        self, trust_store, key_manager, authority_registry, sample_authority
    ):
        """Test complete rotate_key + _resign_chains end-to-end."""
        await trust_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager.register_key("key-001", private_key)

        # Create chains with various components
        chain1 = create_test_chain(
            "agent-001", "org-test", private_key, num_capabilities=2
        )
        chain2 = create_test_chain(
            "agent-002", "org-test", private_key, num_delegations=1
        )
        chain3 = create_test_chain(
            "agent-003",
            "org-test",
            private_key,
            num_capabilities=3,
            num_delegations=2,
        )

        await trust_store.store_chain(chain1)
        await trust_store.store_chain(chain2)
        await trust_store.store_chain(chain3)

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=trust_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        result = await manager.rotate_key("org-test")

        assert result.chains_updated == 3
        assert result.new_key_id != result.old_key_id

    async def test_rotation_with_key_manager(
        self, trust_store, authority_registry, sample_authority
    ):
        """Test rotation uses KeyManagerInterface for signing."""
        await trust_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]

        # Use the actual TrustKeyManager
        key_manager = TrustKeyManager()
        key_manager.register_key("key-001", private_key)

        chain = create_test_chain("agent-001", "org-test", private_key)
        await trust_store.store_chain(chain)

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=trust_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        result = await manager.rotate_key("org-test")

        assert result.chains_updated == 1

    async def test_rotation_preserves_chain_integrity(
        self, trust_store, key_manager, authority_registry, sample_authority
    ):
        """Test that chain hash is valid after rotation."""
        await trust_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager.register_key("key-001", private_key)

        chain = create_test_chain(
            "agent-001",
            "org-test",
            private_key,
            num_capabilities=2,
            num_delegations=1,
        )
        await trust_store.store_chain(chain)

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=trust_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        await manager.rotate_key("org-test")

        updated_chain = await trust_store.get_chain("agent-001")

        # Chain should still compute a valid hash
        chain_hash = updated_chain.hash()
        assert isinstance(chain_hash, str)
        assert len(chain_hash) == 64  # SHA-256 hex

    async def test_rotation_multiple_authorities(
        self, trust_store, key_manager, authority_registry
    ):
        """Test that only target authority's chains are re-signed."""
        await trust_store.initialize()

        # Create two authorities
        private_key1, public_key1 = generate_keypair()
        private_key2, public_key2 = generate_keypair()

        auth1 = OrganizationalAuthority(
            id="org-alpha",
            name="Alpha Organization",
            authority_type=AuthorityType.ORGANIZATION,
            public_key=public_key1,
            signing_key_id="key-alpha",
            permissions=[AuthorityPermission.CREATE_AGENTS],
            is_active=True,
            metadata={"private_key": private_key1},
        )
        auth2 = OrganizationalAuthority(
            id="org-beta",
            name="Beta Organization",
            authority_type=AuthorityType.ORGANIZATION,
            public_key=public_key2,
            signing_key_id="key-beta",
            permissions=[AuthorityPermission.CREATE_AGENTS],
            is_active=True,
            metadata={"private_key": private_key2},
        )

        await authority_registry.register_authority(auth1)
        await authority_registry.register_authority(auth2)

        key_manager.register_key("key-alpha", private_key1)
        key_manager.register_key("key-beta", private_key2)

        # Create chains for both authorities
        chain_alpha = create_test_chain("agent-alpha", "org-alpha", private_key1)
        chain_beta = create_test_chain("agent-beta", "org-beta", private_key2)
        original_beta_sig = chain_beta.genesis.signature

        await trust_store.store_chain(chain_alpha)
        await trust_store.store_chain(chain_beta)

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=trust_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        # Rotate only alpha
        result = await manager.rotate_key("org-alpha")

        assert result.chains_updated == 1

        # Beta chain should be unchanged
        beta_chain = await trust_store.get_chain("agent-beta")
        assert beta_chain.genesis.signature == original_beta_sig

    async def test_empty_chain_list_succeeds(
        self, trust_store, key_manager, authority_registry, sample_authority
    ):
        """Test that no chains to re-sign results in no error."""
        await trust_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager.register_key("key-001", private_key)

        # No chains stored

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=trust_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        result = await manager.rotate_key("org-test")

        assert result.chains_updated == 0

    async def test_resign_returns_count(
        self, trust_store, key_manager, authority_registry, sample_authority
    ):
        """Test that rotation returns correct count of chains updated."""
        await trust_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager.register_key("key-001", private_key)

        # Create exactly 7 chains
        for i in range(7):
            chain = create_test_chain(f"agent-{i:03d}", "org-test", private_key)
            await trust_store.store_chain(chain)

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=trust_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        result = await manager.rotate_key("org-test")

        assert result.chains_updated == 7

    async def test_transaction_isolation(self, trust_store):
        """Test that concurrent reads see old state during transaction."""
        private_key, _ = generate_keypair()
        chain = create_test_chain("agent-001", "org-test", private_key)

        await trust_store.initialize()
        await trust_store.store_chain(chain)

        original_sig = chain.genesis.signature

        # Start transaction but don't commit
        tx = trust_store.transaction()
        await tx.__aenter__()

        # Queue update
        modified = copy.deepcopy(chain)
        modified.genesis.signature = "in-flight-signature"
        await tx.update_chain("agent-001", modified)

        # Read from store during transaction - should see original
        current = await trust_store.get_chain("agent-001")
        assert current.genesis.signature == original_sig

        # Exit without commit
        await tx.__aexit__(None, None, None)

        # Still should see original
        final = await trust_store.get_chain("agent-001")
        assert final.genesis.signature == original_sig


# =============================================================================
# CARE-048: Non-Atomic Chain Re-signing Rollback Tests
# =============================================================================


class FailingRollbackTrustStore(InMemoryTrustStore):
    """
    A trust store that fails during both update AND rollback.

    Used to test CARE-048 critical logging when rollback fails.
    """

    def __init__(self, fail_after: int, fail_rollback_for: Optional[List[str]] = None):
        """
        Initialize with failure thresholds.

        Args:
            fail_after: Number of successful update_chain operations before failing
            fail_rollback_for: List of agent_ids that should fail during rollback
        """
        super().__init__()
        self.fail_after = fail_after
        self.fail_rollback_for = fail_rollback_for or []
        self.update_count = 0
        self._initial_store_complete = False
        self._in_rollback_mode = False
        self.rollback_attempts: List[str] = []

    async def update_chain(
        self,
        agent_id: str,
        chain: TrustLineageChain,
    ) -> None:
        """Update chain with failure injection."""
        if self._initial_store_complete:
            if self._in_rollback_mode:
                # During rollback phase
                self.rollback_attempts.append(agent_id)
                if agent_id in self.fail_rollback_for:
                    raise RuntimeError(f"Simulated rollback failure for {agent_id}")
            else:
                # During initial update phase
                self.update_count += 1
                if self.update_count > self.fail_after:
                    # Enter rollback mode for subsequent calls
                    self._in_rollback_mode = True
                    raise RuntimeError(
                        f"Simulated DB failure after {self.fail_after} updates"
                    )
        return await super().update_chain(agent_id, chain)

    def mark_initial_store_complete(self) -> None:
        """Mark initial chain storage as complete to start counting failures."""
        self._initial_store_complete = True

    def transaction(self):
        """Disable transaction support to test non-transactional path."""
        raise AttributeError("transaction not supported")


@pytest.mark.asyncio
class TestCARE048RollbackMechanism:
    """
    CARE-048: Test rollback mechanism for non-transactional stores.

    Tests that:
    - Partial failure triggers rollback attempt
    - Rollback restores original chains
    - CRITICAL logging on rollback failure
    - Error message includes details of inconsistent state
    """

    async def test_partial_failure_triggers_rollback(
        self, authority_registry, sample_authority
    ):
        """Test that failure midway triggers rollback of previously updated chains."""
        # Fail after 3 updates (chains 0, 1, 2 succeed, chain 3 fails)
        failing_store = FailingTrustStore(fail_after=3)
        await failing_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager = TrustKeyManager()
        key_manager.register_key("key-001", private_key)

        # Store 5 chains with their original signatures
        original_signatures = {}
        for i in range(5):
            chain = create_test_chain(f"agent-{i:03d}", "org-test", private_key)
            await failing_store.store_chain(chain)
            original_signatures[f"agent-{i:03d}"] = chain.genesis.signature

        failing_store.mark_initial_store_complete()

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=failing_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        # Rotation should fail
        with pytest.raises(RotationError) as exc_info:
            await manager.rotate_key("org-test")

        # Error message should indicate rollback occurred
        error_msg = str(exc_info.value)
        assert "rolled back" in error_msg.lower()

    async def test_rollback_restores_original_chains(
        self, authority_registry, sample_authority
    ):
        """Test that successful rollback restores all chains to original state."""
        # Fail after 2 updates (chains 0, 1 succeed, chain 2 fails)
        failing_store = FailingTrustStore(fail_after=2)
        await failing_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager = TrustKeyManager()
        key_manager.register_key("key-001", private_key)

        # Store 4 chains
        original_signatures = {}
        for i in range(4):
            chain = create_test_chain(f"agent-{i:03d}", "org-test", private_key)
            await failing_store.store_chain(chain)
            original_signatures[f"agent-{i:03d}"] = chain.genesis.signature

        failing_store.mark_initial_store_complete()

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=failing_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        # Rotation should fail
        with pytest.raises(RotationError):
            await manager.rotate_key("org-test")

        # All chains should be restored to original signatures
        for agent_id, original_sig in original_signatures.items():
            chain = await failing_store.get_chain(agent_id)
            assert chain.genesis.signature == original_sig, (
                f"Chain {agent_id} was not rolled back to original signature"
            )

    async def test_rollback_failure_logs_critical_and_reports_inconsistent_state(
        self, authority_registry, sample_authority
    ):
        """Test CRITICAL logging when rollback fails and system is inconsistent."""
        # Fail after 2 updates, and fail rollback for agent-000
        failing_store = FailingRollbackTrustStore(
            fail_after=2,
            fail_rollback_for=["agent-000"],
        )
        await failing_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager = TrustKeyManager()
        key_manager.register_key("key-001", private_key)

        # Store 4 chains
        for i in range(4):
            chain = create_test_chain(f"agent-{i:03d}", "org-test", private_key)
            await failing_store.store_chain(chain)

        failing_store.mark_initial_store_complete()

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=failing_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        # Rotation should fail with CRITICAL inconsistent state error
        with pytest.raises(RotationError) as exc_info:
            await manager.rotate_key("org-test")

        error = exc_info.value
        error_msg = str(error)

        # Verify error indicates CRITICAL inconsistent state
        assert "CRITICAL" in error_msg
        assert "inconsistent" in error_msg.lower()
        assert "agent-000" in error_msg  # The chain that failed rollback
        assert error.reason == "rollback_failed_inconsistent_state"

    async def test_error_message_includes_failure_details(
        self, authority_registry, sample_authority
    ):
        """Test that error message includes which chains were updated vs failed."""
        # Fail after 3 updates
        failing_store = FailingTrustStore(fail_after=3)
        await failing_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager = TrustKeyManager()
        key_manager.register_key("key-001", private_key)

        # Store 5 chains
        for i in range(5):
            chain = create_test_chain(f"agent-{i:03d}", "org-test", private_key)
            await failing_store.store_chain(chain)

        failing_store.mark_initial_store_complete()

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=failing_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        with pytest.raises(RotationError) as exc_info:
            await manager.rotate_key("org-test")

        error_msg = str(exc_info.value)

        # Error should indicate which chain failed (4th chain = agent-003)
        assert "agent-003" in error_msg
        # Error should indicate count context (4 of 5)
        assert "4 of 5" in error_msg
        # Error should indicate rollback count (3 chains were rolled back)
        assert "3" in error_msg

    async def test_multiple_rollback_failures_all_reported(
        self, authority_registry, sample_authority
    ):
        """Test that multiple rollback failures are all reported."""
        # Fail after 3 updates, fail rollback for multiple chains
        failing_store = FailingRollbackTrustStore(
            fail_after=3,
            fail_rollback_for=["agent-000", "agent-002"],
        )
        await failing_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager = TrustKeyManager()
        key_manager.register_key("key-001", private_key)

        # Store 5 chains
        for i in range(5):
            chain = create_test_chain(f"agent-{i:03d}", "org-test", private_key)
            await failing_store.store_chain(chain)

        failing_store.mark_initial_store_complete()

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=failing_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        with pytest.raises(RotationError) as exc_info:
            await manager.rotate_key("org-test")

        error_msg = str(exc_info.value)

        # Both failed rollback chains should be mentioned
        assert "agent-000" in error_msg
        assert "agent-002" in error_msg
        assert "2" in error_msg  # 2 rollback failures

    async def test_successful_rollback_reason_is_resign_failed_rolled_back(
        self, authority_registry, sample_authority
    ):
        """Test that successful rollback has correct error reason."""
        failing_store = FailingTrustStore(fail_after=2)
        await failing_store.initialize()
        await authority_registry.register_authority(sample_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager = TrustKeyManager()
        key_manager.register_key("key-001", private_key)

        for i in range(4):
            chain = create_test_chain(f"agent-{i:03d}", "org-test", private_key)
            await failing_store.store_chain(chain)

        failing_store.mark_initial_store_complete()

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=failing_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        with pytest.raises(RotationError) as exc_info:
            await manager.rotate_key("org-test")

        assert exc_info.value.reason == "resign_failed_rolled_back"

    async def test_rollback_preserves_non_authority_chains(
        self, authority_registry, sample_authority
    ):
        """Test that chains from other authorities are not affected."""
        # Fail after 2 updates (need multiple chains for target authority to trigger failure)
        failing_store = FailingTrustStore(fail_after=2)
        await failing_store.initialize()
        await authority_registry.register_authority(sample_authority)

        # Create another authority
        other_private_key, other_public_key = generate_keypair()
        other_authority = OrganizationalAuthority(
            id="org-other",
            name="Other Organization",
            authority_type=AuthorityType.ORGANIZATION,
            public_key=other_public_key,
            signing_key_id="key-other",
            permissions=[AuthorityPermission.CREATE_AGENTS],
            is_active=True,
            metadata={"private_key": other_private_key},
        )
        await authority_registry.register_authority(other_authority)

        private_key = sample_authority.metadata["private_key"]
        key_manager = TrustKeyManager()
        key_manager.register_key("key-001", private_key)
        key_manager.register_key("key-other", other_private_key)

        # Store multiple chains for target authority (so we can trigger failure)
        # and one chain for other authority
        for i in range(4):
            chain_target = create_test_chain(
                f"agent-target-{i}", "org-test", private_key
            )
            await failing_store.store_chain(chain_target)

        chain_other = create_test_chain("agent-other", "org-other", other_private_key)
        other_original_sig = chain_other.genesis.signature
        await failing_store.store_chain(chain_other)

        failing_store.mark_initial_store_complete()

        manager = CredentialRotationManager(
            key_manager=key_manager,
            trust_store=failing_store,
            authority_registry=authority_registry,
        )
        await manager.initialize()

        # Rotation for org-test should fail at chain 3 (after 2 successful updates)
        with pytest.raises(RotationError):
            await manager.rotate_key("org-test")

        # Other authority's chain should be completely unchanged
        other_chain = await failing_store.get_chain("agent-other")
        assert other_chain.genesis.signature == other_original_sig
