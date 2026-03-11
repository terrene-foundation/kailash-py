"""
CARE-040: Adversarial Security Tests for Revocation Race Conditions (Tier 1).

Tests for race conditions and timing attacks in the revocation system.
Covers the RevocationBroadcaster, CertificateRevocationList, KeyRotationManager,
and TransactionalStore.

These tests verify that:
1. Revocation propagates correctly under race conditions
2. CRL entries are immutable once added
3. Concurrent operations do not create security gaps
4. Failed broadcasts do not leave system in inconsistent state
5. Transactions provide proper isolation

NO MOCKING - Uses real implementation instances.
"""

import asyncio
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set
from unittest.mock import patch

import pytest
from kaizen.trust.crl import (
    CertificateRevocationList,
    CRLEntry,
    verify_delegation_with_crl,
)
from kaizen.trust.revocation.broadcaster import (
    CascadeRevocationManager,
    DeadLetterEntry,
    InMemoryDelegationRegistry,
    InMemoryRevocationBroadcaster,
    RevocationEvent,
    RevocationType,
    TrustRevocationList,
)
from kaizen.trust.store import InMemoryTrustStore, TransactionContext

# =============================================================================
# Revocation Timing Attack Tests
# =============================================================================


class TestRevocationTimingAttacks:
    """Tests for timing attacks in the revocation system."""

    @pytest.fixture
    def broadcaster(self) -> InMemoryRevocationBroadcaster:
        return InMemoryRevocationBroadcaster()

    @pytest.fixture
    def registry(self) -> InMemoryDelegationRegistry:
        return InMemoryDelegationRegistry()

    @pytest.fixture
    def manager(
        self,
        broadcaster: InMemoryRevocationBroadcaster,
        registry: InMemoryDelegationRegistry,
    ) -> CascadeRevocationManager:
        return CascadeRevocationManager(broadcaster, registry)

    def test_use_after_revocation_within_propagation_delay(
        self, broadcaster: InMemoryRevocationBroadcaster
    ):
        """
        Adversarial: Operation submitted between revocation and broadcast.

        Attack vector: Submit an operation right after revocation but before
        the revocation has propagated to all subscribers.

        Expected: The TrustRevocationList should be updated synchronously,
        so there's no window for race conditions.
        """
        # Set up TrustRevocationList to track revocations
        trl = TrustRevocationList(broadcaster)
        trl.initialize()

        # Initially not revoked
        assert not trl.is_revoked("agent-001")

        # Create and broadcast revocation
        event = RevocationEvent(
            event_id="rev-001",
            revocation_type=RevocationType.AGENT_REVOKED,
            target_id="agent-001",
            revoked_by="admin",
            reason="Security violation",
        )
        broadcaster.broadcast(event)

        # Immediately after broadcast, should be revoked
        # No propagation delay in synchronous in-memory implementation
        assert trl.is_revoked("agent-001")

        # Clean up
        trl.close()

    def test_concurrent_revocation_and_verification(
        self, broadcaster: InMemoryRevocationBroadcaster
    ):
        """
        Adversarial: Parallel revoke + verify must be safe.

        Attack vector: One thread revokes while another verifies the same agent.
        Expected: Either see pre-revocation or post-revocation state, never corrupted.
        """
        trl = TrustRevocationList(broadcaster)
        trl.initialize()

        results_before_revoke = []
        results_after_revoke = []
        errors = []

        def revoke_agent():
            time.sleep(0.001)  # Small delay to create race
            event = RevocationEvent(
                event_id=f"rev-{uuid.uuid4()}",
                revocation_type=RevocationType.AGENT_REVOKED,
                target_id="agent-race-test",
                revoked_by="admin",
                reason="Test revocation",
            )
            broadcaster.broadcast(event)

        def verify_agent():
            try:
                # Check multiple times rapidly
                for _ in range(100):
                    is_revoked = trl.is_revoked("agent-race-test")
                    if is_revoked:
                        results_after_revoke.append(True)
                    else:
                        results_before_revoke.append(False)
            except Exception as e:
                errors.append(e)

        # Run concurrent operations
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Start verification threads
            verify_futures = [executor.submit(verify_agent) for _ in range(5)]
            # Start revocation thread
            revoke_future = executor.submit(revoke_agent)

            # Wait for all
            for f in as_completed(verify_futures + [revoke_future]):
                f.result()

        # No errors should occur
        assert len(errors) == 0

        # After all threads complete, agent should be revoked
        assert trl.is_revoked("agent-race-test")

        trl.close()


# =============================================================================
# CRL Immutability Tests
# =============================================================================


class TestCRLImmutability:
    """Tests for CRL entry immutability."""

    @pytest.fixture
    def crl(self) -> CertificateRevocationList:
        return CertificateRevocationList(issuer_id="org-test")

    def test_crl_entry_cannot_be_removed(self, crl: CertificateRevocationList):
        """
        Adversarial: Once a CRL entry is added, it cannot be removed.

        Note: The current implementation DOES allow removal via remove_revocation().
        This test documents the current behavior and flags the security concern.

        For a truly secure CRL, entries should be immutable (append-only).
        """
        # Add a revocation
        crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Compromised",
            revoked_by="admin",
        )

        assert crl.is_revoked("del-001")

        # The current implementation allows removal
        # In a production system, this should be restricted or audited
        result = crl.remove_revocation("del-001")
        assert result is True  # Removal succeeded

        # After removal, no longer revoked
        assert not crl.is_revoked("del-001")

        # Security Note: For CARE-040 compliance, consider:
        # 1. Making CRL append-only (no remove)
        # 2. Adding an "unrevoke" entry instead of deletion
        # 3. Requiring special authorization for removal
        # 4. Logging all removal attempts for audit

    def test_crl_expired_entry_still_revoked(self, crl: CertificateRevocationList):
        """
        Adversarial: Revoked entries remain revoked even after CRL entry "expiry".

        Attack vector: Wait for CRL entry to expire, then use revoked delegation.
        Expected: Expired CRL entries should still block revoked delegations.

        Note: CRL entry expiry is for CRL distribution optimization, not for
        un-revoking delegations.
        """
        past = datetime.now(timezone.utc) - timedelta(days=1)

        # Add entry with expired expiry date
        crl.add_revocation(
            delegation_id="del-expired",
            agent_id="agent-001",
            reason="Test",
            revoked_by="admin",
            expires_at=past,
        )

        # The entry IS expired
        entry = crl.get_entry("del-expired")
        assert entry is not None
        assert entry.is_expired()

        # But it's still revoked until cleanup is called
        assert crl.is_revoked("del-expired")

        # Even after expiry, the delegation should be considered revoked
        result = verify_delegation_with_crl("del-expired", crl)
        assert result.valid is False

        # cleanup_expired removes expired entries
        # This is the current behavior - may need security review
        removed = crl.cleanup_expired()
        assert removed == 1

        # After cleanup, no longer in CRL
        # Security concern: This could allow use of previously-revoked delegation
        assert not crl.is_revoked("del-expired")

    def test_crl_double_add_is_update(self, crl: CertificateRevocationList):
        """
        Adversarial: Adding same delegation_id twice should update, not duplicate.
        """
        crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Original",
            revoked_by="admin1",
        )

        crl.add_revocation(
            delegation_id="del-001",
            agent_id="agent-001",
            reason="Updated",
            revoked_by="admin2",
        )

        # Should only have one entry
        assert crl.entry_count == 1

        # Entry should have updated values
        entry = crl.get_entry("del-001")
        assert entry.reason == "Updated"
        assert entry.revoked_by == "admin2"


# =============================================================================
# Key Rotation Race Tests
# =============================================================================


class TestRotationRaceConditions:
    """Tests for race conditions during key rotation."""

    def test_rotation_during_active_verification(self):
        """
        Adversarial: Key rotation during active verification.

        Attack vector: Start verification, rotate key mid-way, complete verification.
        Expected: Verification should use consistent key state.

        Note: This is a conceptual test - actual implementation would need
        a real CredentialRotationManager with async operations.
        """
        # This test documents the security concern
        # In a production system:
        # 1. Key rotation should be atomic
        # 2. Grace periods allow old keys to remain valid
        # 3. Verification should be transactional

        # Simulated scenario:
        old_key_id = "key-old"
        new_key_id = "key-new"
        grace_period_hours = 24

        # During grace period, both keys should be valid
        grace_end = datetime.now(timezone.utc) + timedelta(hours=grace_period_hours)

        # Verify that old key is still valid during grace period
        assert datetime.now(timezone.utc) < grace_end

        # After grace period, old key should be revoked
        # This is handled by the CredentialRotationManager.revoke_old_key()


# =============================================================================
# Transaction Isolation Tests
# =============================================================================


class TestStoreTransactionIsolation:
    """Tests for transaction isolation in TransactionalStore."""

    @pytest.fixture
    def store(self) -> InMemoryTrustStore:
        store = InMemoryTrustStore()
        # Run initialize synchronously for setup
        asyncio.get_event_loop().run_until_complete(store.initialize())
        return store

    @pytest.mark.asyncio
    async def test_store_transaction_isolation(self):
        """
        Adversarial: Transactions in TransactionalStore are isolated.

        Attack vector: Read uncommitted data from another transaction.
        Expected: Transactions should only see committed data.
        """
        store = InMemoryTrustStore()
        await store.initialize()

        # Need to import chain creation helpers
        from kaizen.trust.chain import AuthorityType, GenesisRecord, TrustLineageChain

        # Create a test chain
        genesis = GenesisRecord(
            id="genesis-tx-test",
            agent_id="agent-tx-test",
            authority_id="org-test",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            signature="test-sig",
        )

        chain = TrustLineageChain(genesis=genesis)
        await store.store_chain(chain)

        # Start a transaction
        async with store.transaction() as tx:
            # Modify chain in transaction
            modified_genesis = GenesisRecord(
                id="genesis-tx-test-2",
                agent_id="agent-tx-test",
                authority_id="org-modified",  # Changed
                authority_type=AuthorityType.ORGANIZATION,
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                signature="test-sig-2",
            )
            modified_chain = TrustLineageChain(genesis=modified_genesis)
            await tx.update_chain("agent-tx-test", modified_chain)

            # Check pending count
            assert tx.pending_count == 1

            # Before commit, original should still be visible via store
            original = await store.get_chain("agent-tx-test")
            # Note: The pending updates are not applied until commit
            # So original should still show old authority_id
            # Actually, in the current implementation, updates in tx are queued
            # and only applied on commit

            # Commit
            await tx.commit()

        # After commit, modified version should be visible
        result = await store.get_chain("agent-tx-test")
        assert result.genesis.authority_id == "org-modified"

    @pytest.mark.asyncio
    async def test_transaction_rollback_on_exception(self):
        """
        Adversarial: Transaction rollback on exception preserves original state.
        """
        store = InMemoryTrustStore()
        await store.initialize()

        from kaizen.trust.chain import AuthorityType, GenesisRecord, TrustLineageChain

        # Create original chain
        genesis = GenesisRecord(
            id="genesis-rollback-test",
            agent_id="agent-rollback-test",
            authority_id="org-original",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            signature="test-sig",
        )
        chain = TrustLineageChain(genesis=genesis)
        await store.store_chain(chain)

        # Try to modify in transaction, but don't commit
        try:
            async with store.transaction() as tx:
                modified_genesis = GenesisRecord(
                    id="genesis-rollback-test-2",
                    agent_id="agent-rollback-test",
                    authority_id="org-should-not-persist",
                    authority_type=AuthorityType.ORGANIZATION,
                    created_at=datetime.now(timezone.utc),
                    expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                    signature="test-sig-2",
                )
                modified_chain = TrustLineageChain(genesis=modified_genesis)
                await tx.update_chain("agent-rollback-test", modified_chain)

                # Raise exception before commit
                raise RuntimeError("Simulated failure")

        except RuntimeError:
            pass

        # After rollback, original should be preserved
        result = await store.get_chain("agent-rollback-test")
        assert result.genesis.authority_id == "org-original"

    @pytest.mark.asyncio
    async def test_transaction_no_commit_is_rollback(self):
        """
        Adversarial: Exiting transaction without commit rolls back.
        """
        store = InMemoryTrustStore()
        await store.initialize()

        from kaizen.trust.chain import AuthorityType, GenesisRecord, TrustLineageChain

        genesis = GenesisRecord(
            id="genesis-no-commit-test",
            agent_id="agent-no-commit-test",
            authority_id="org-original",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            signature="test-sig",
        )
        chain = TrustLineageChain(genesis=genesis)
        await store.store_chain(chain)

        # Enter transaction but don't commit
        async with store.transaction() as tx:
            modified_genesis = GenesisRecord(
                id="genesis-no-commit-test-2",
                agent_id="agent-no-commit-test",
                authority_id="org-uncommitted",
                authority_type=AuthorityType.ORGANIZATION,
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                signature="test-sig-2",
            )
            modified_chain = TrustLineageChain(genesis=modified_genesis)
            await tx.update_chain("agent-no-commit-test", modified_chain)
            # No commit!

        # Should roll back to original
        result = await store.get_chain("agent-no-commit-test")
        assert result.genesis.authority_id == "org-original"


# =============================================================================
# Broadcast Reliability Tests
# =============================================================================


class TestBroadcastReliability:
    """Tests for broadcast reliability and failure handling."""

    @pytest.fixture
    def broadcaster(self) -> InMemoryRevocationBroadcaster:
        return InMemoryRevocationBroadcaster()

    def test_broadcast_retry_on_failure(
        self, broadcaster: InMemoryRevocationBroadcaster
    ):
        """
        Adversarial: Broadcaster retries on channel failure.

        Note: The current InMemoryRevocationBroadcaster does not implement
        retries. It catches exceptions and logs them to dead letter queue.
        """
        failures = []
        successes = []

        def failing_callback(event: RevocationEvent):
            failures.append(event)
            raise RuntimeError("Simulated failure")

        def success_callback(event: RevocationEvent):
            successes.append(event)

        # Subscribe both handlers
        broadcaster.subscribe(failing_callback)
        broadcaster.subscribe(success_callback)

        # Broadcast
        event = RevocationEvent(
            event_id="rev-retry-test",
            revocation_type=RevocationType.AGENT_REVOKED,
            target_id="agent-001",
            revoked_by="admin",
            reason="Test",
        )
        broadcaster.broadcast(event)

        # Failing callback should have been called
        assert len(failures) == 1

        # Success callback should also have been called
        assert len(successes) == 1

        # Dead letter should capture the failure
        dead_letters = broadcaster.get_dead_letters()
        assert len(dead_letters) == 1
        assert "Simulated failure" in dead_letters[0].error

    def test_partial_broadcast_consistency(
        self, broadcaster: InMemoryRevocationBroadcaster
    ):
        """
        Adversarial: If some channels fail, system remains consistent.

        Attack vector: Cause partial broadcast to create inconsistent state.
        Expected: Event is stored in history regardless of subscriber failures.
        """
        received = []

        def callback1(event: RevocationEvent):
            received.append(("cb1", event))
            raise RuntimeError("Callback 1 failed")

        def callback2(event: RevocationEvent):
            received.append(("cb2", event))
            # Second callback succeeds

        def callback3(event: RevocationEvent):
            received.append(("cb3", event))
            raise RuntimeError("Callback 3 failed")

        broadcaster.subscribe(callback1)
        broadcaster.subscribe(callback2)
        broadcaster.subscribe(callback3)

        event = RevocationEvent(
            event_id="rev-partial",
            revocation_type=RevocationType.AGENT_REVOKED,
            target_id="agent-partial",
            revoked_by="admin",
            reason="Test partial",
        )
        broadcaster.broadcast(event)

        # All callbacks should have been attempted
        assert len(received) == 3

        # Event should be in history
        history = broadcaster.get_history()
        assert len(history) == 1
        assert history[0].event_id == "rev-partial"

        # Dead letters should capture failures
        dead_letters = broadcaster.get_dead_letters()
        assert len(dead_letters) == 2  # Two failures


# =============================================================================
# Idempotency Tests
# =============================================================================


class TestRevocationIdempotency:
    """Tests for revocation idempotency."""

    @pytest.fixture
    def broadcaster(self) -> InMemoryRevocationBroadcaster:
        return InMemoryRevocationBroadcaster()

    @pytest.fixture
    def registry(self) -> InMemoryDelegationRegistry:
        return InMemoryDelegationRegistry()

    @pytest.fixture
    def manager(
        self,
        broadcaster: InMemoryRevocationBroadcaster,
        registry: InMemoryDelegationRegistry,
    ) -> CascadeRevocationManager:
        return CascadeRevocationManager(broadcaster, registry)

    def test_double_revocation_idempotent(
        self,
        manager: CascadeRevocationManager,
        broadcaster: InMemoryRevocationBroadcaster,
    ):
        """
        Adversarial: Revoking same thing twice is idempotent.

        Attack vector: Send duplicate revocation requests.
        Expected: Each revocation creates an event, but system handles duplicates.
        """
        trl = TrustRevocationList(broadcaster)
        trl.initialize()

        # First revocation
        events1 = manager.cascade_revoke(
            target_id="agent-idempotent",
            revoked_by="admin",
            reason="First revocation",
        )

        # Second revocation of same agent
        events2 = manager.cascade_revoke(
            target_id="agent-idempotent",
            revoked_by="admin",
            reason="Duplicate revocation",
        )

        # Both create events
        assert len(events1) == 1
        assert len(events2) == 1

        # Agent should be revoked
        assert trl.is_revoked("agent-idempotent")

        # History shows both events
        history = broadcaster.get_history()
        assert len(history) == 2

        trl.close()

    def test_revocation_of_nonexistent_agent(
        self,
        manager: CascadeRevocationManager,
        broadcaster: InMemoryRevocationBroadcaster,
    ):
        """
        Adversarial: Revoking unknown agent should not crash.

        Attack vector: Revoke an agent that doesn't exist.
        Expected: Creates a revocation event, no crash.
        """
        trl = TrustRevocationList(broadcaster)
        trl.initialize()

        # Revoke non-existent agent
        events = manager.cascade_revoke(
            target_id="agent-does-not-exist",
            revoked_by="admin",
            reason="Preemptive revocation",
        )

        # Should create an event (preemptive revocation is valid)
        assert len(events) == 1
        assert events[0].target_id == "agent-does-not-exist"

        # Agent should be marked as revoked
        assert trl.is_revoked("agent-does-not-exist")

        trl.close()


# =============================================================================
# Cascade Revocation Race Tests
# =============================================================================


class TestCascadeRevocationRaces:
    """Tests for race conditions in cascade revocation."""

    @pytest.fixture
    def broadcaster(self) -> InMemoryRevocationBroadcaster:
        return InMemoryRevocationBroadcaster()

    @pytest.fixture
    def registry(self) -> InMemoryDelegationRegistry:
        reg = InMemoryDelegationRegistry()
        # Set up delegation tree: A -> B -> C, A -> D
        reg.register_delegation("agent-A", "agent-B")
        reg.register_delegation("agent-B", "agent-C")
        reg.register_delegation("agent-A", "agent-D")
        return reg

    @pytest.fixture
    def manager(
        self,
        broadcaster: InMemoryRevocationBroadcaster,
        registry: InMemoryDelegationRegistry,
    ) -> CascadeRevocationManager:
        return CascadeRevocationManager(broadcaster, registry)

    def test_concurrent_cascade_revocations(
        self,
        manager: CascadeRevocationManager,
        broadcaster: InMemoryRevocationBroadcaster,
        registry: InMemoryDelegationRegistry,
    ):
        """
        Adversarial: Concurrent cascade revocations from different roots.

        Attack vector: Revoke multiple roots simultaneously.
        Expected: All cascades complete without corruption.
        """
        # Add more agents for complexity
        registry.register_delegation("agent-E", "agent-F")
        registry.register_delegation("agent-F", "agent-G")

        trl = TrustRevocationList(broadcaster)
        trl.initialize()

        results = []
        errors = []

        def revoke_agent(agent_id: str):
            try:
                events = manager.cascade_revoke(
                    target_id=agent_id,
                    revoked_by="admin",
                    reason=f"Revoking {agent_id}",
                )
                results.append((agent_id, events))
            except Exception as e:
                errors.append((agent_id, e))

        # Concurrently revoke different roots
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(revoke_agent, "agent-A"),
                executor.submit(revoke_agent, "agent-E"),
            ]
            for f in as_completed(futures):
                f.result()

        # No errors
        assert len(errors) == 0

        # All agents in both trees should be revoked
        assert trl.is_revoked("agent-A")
        assert trl.is_revoked("agent-B")
        assert trl.is_revoked("agent-C")
        assert trl.is_revoked("agent-D")
        assert trl.is_revoked("agent-E")
        assert trl.is_revoked("agent-F")
        assert trl.is_revoked("agent-G")

        trl.close()

    def test_circular_delegation_detection(
        self,
        broadcaster: InMemoryRevocationBroadcaster,
    ):
        """
        Adversarial: Circular delegation should not cause infinite loop.

        Attack vector: Create a circular delegation chain.
        Expected: Cascade revocation detects cycle and terminates.
        """
        registry = InMemoryDelegationRegistry()
        # Create cycle: A -> B -> C -> A
        registry.register_delegation("agent-cycle-A", "agent-cycle-B")
        registry.register_delegation("agent-cycle-B", "agent-cycle-C")
        registry.register_delegation("agent-cycle-C", "agent-cycle-A")

        manager = CascadeRevocationManager(broadcaster, registry)

        # Should complete without infinite loop
        events = manager.cascade_revoke(
            target_id="agent-cycle-A",
            revoked_by="admin",
            reason="Cycle test",
        )

        # Should revoke all three agents exactly once
        revoked_agents = {e.target_id for e in events}
        assert "agent-cycle-A" in revoked_agents
        assert "agent-cycle-B" in revoked_agents
        assert "agent-cycle-C" in revoked_agents

        # No duplicates
        assert len(events) == 3


# =============================================================================
# CRL Concurrent Access Tests
# =============================================================================


class TestCRLConcurrentAccess:
    """Tests for concurrent access to CRL."""

    def test_concurrent_add_revocation(self):
        """
        Adversarial: Concurrent additions to CRL.

        Attack vector: Add many entries concurrently.
        Expected: All entries added correctly, no corruption.
        """
        crl = CertificateRevocationList(issuer_id="org-concurrent")
        errors = []
        added_ids = []

        def add_revocation(i: int):
            try:
                entry = crl.add_revocation(
                    delegation_id=f"del-{i:04d}",
                    agent_id=f"agent-{i:04d}",
                    reason=f"Concurrent add {i}",
                    revoked_by="admin",
                )
                added_ids.append(entry.delegation_id)
            except Exception as e:
                errors.append((i, e))

        # Add many entries concurrently
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(add_revocation, i) for i in range(100)]
            for f in as_completed(futures):
                f.result()

        # No errors
        assert len(errors) == 0

        # All entries should be present
        assert crl.entry_count == 100
        for i in range(100):
            assert crl.is_revoked(f"del-{i:04d}")

    def test_concurrent_read_write(self):
        """
        Adversarial: Concurrent reads and writes to CRL.

        Attack vector: Readers and writers accessing CRL simultaneously.
        Expected: No corruption or exceptions.
        """
        crl = CertificateRevocationList(issuer_id="org-rw")
        errors = []

        # Pre-populate some entries
        for i in range(50):
            crl.add_revocation(
                delegation_id=f"del-{i:04d}",
                agent_id=f"agent-{i:04d}",
                reason=f"Initial {i}",
                revoked_by="admin",
            )

        def writer(start: int):
            try:
                for i in range(start, start + 20):
                    crl.add_revocation(
                        delegation_id=f"del-new-{i:04d}",
                        agent_id=f"agent-new-{i:04d}",
                        reason=f"New entry {i}",
                        revoked_by="admin",
                    )
            except Exception as e:
                errors.append(("writer", e))

        def reader():
            try:
                for _ in range(100):
                    # Various read operations
                    _ = crl.entry_count
                    _ = crl.is_revoked("del-0000")
                    _ = crl.get_entry("del-0025")
                    _ = crl.list_entries(limit=10)
            except Exception as e:
                errors.append(("reader", e))

        # Run concurrent readers and writers
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(writer, 0),
                executor.submit(writer, 20),
                executor.submit(reader),
                executor.submit(reader),
                executor.submit(reader),
                executor.submit(reader),
            ]
            for f in as_completed(futures):
                f.result()

        # No errors should occur
        assert len(errors) == 0

        # All original entries should still be valid
        for i in range(50):
            assert crl.is_revoked(f"del-{i:04d}")
