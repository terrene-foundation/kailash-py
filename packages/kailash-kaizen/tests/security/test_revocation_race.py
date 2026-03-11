"""
Security Tests for Revocation Race Conditions (Tier 1)

Tests that verify race condition handling during revocation operations.
Part of CARE-040: Security testing for trust framework.

Coverage:
- Immediate invalidation after revocation
- Cascade timing behavior
- Operations during revocation processing

Note: These are unit tests (Tier 1) that test the revocation system's
behavior. Mocking of stores is allowed since these test the revocation
logic, not the store implementation.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kaizen.trust.chain import (
    ActionResult,
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
    VerificationLevel,
    VerificationResult,
)
from kaizen.trust.crl import (
    CertificateRevocationList,
    CRLEntry,
    verify_delegation_with_crl,
)
from kaizen.trust.crypto import generate_keypair
from kaizen.trust.exceptions import TrustChainNotFoundError
from kaizen.trust.revocation import (
    CascadeRevocationManager,
    InMemoryDelegationRegistry,
    InMemoryRevocationBroadcaster,
    RevocationEvent,
    RevocationType,
)


class TestRevokedChainImmediatelyInvalid:
    """Test that revoked chains immediately become invalid for verification."""

    @pytest.fixture
    def crl(self):
        """Create a CRL for testing."""
        return CertificateRevocationList(issuer_id="org-acme")

    @pytest.fixture
    def sample_delegation_id(self):
        """Return a sample delegation ID."""
        return "del-001"

    @pytest.fixture
    def sample_agent_id(self):
        """Return a sample agent ID."""
        return "agent-001"

    def test_revoked_chain_immediately_invalid(
        self, crl, sample_delegation_id, sample_agent_id
    ):
        """
        After revoking a trust chain, subsequent verification fails immediately.

        This test verifies that once a delegation is added to the CRL,
        any verification against that delegation immediately returns invalid.
        There should be no grace period or delay - revocation is instant.
        """
        # Initially, the delegation should be valid (not in CRL)
        initial_result = verify_delegation_with_crl(sample_delegation_id, crl)
        assert (
            initial_result.valid is True
        ), "Delegation should be valid before revocation"
        assert (
            initial_result.entry is None
        ), "No CRL entry should exist before revocation"

        # Add revocation to CRL
        crl.add_revocation(
            delegation_id=sample_delegation_id,
            agent_id=sample_agent_id,
            reason="Security breach detected",
            revoked_by="admin",
        )

        # IMMEDIATELY after revocation, verification should fail
        post_revocation_result = verify_delegation_with_crl(sample_delegation_id, crl)
        assert (
            post_revocation_result.valid is False
        ), "Delegation should be invalid immediately after revocation"
        assert post_revocation_result.entry is not None, "CRL entry should be returned"
        assert post_revocation_result.entry.reason == "Security breach detected"
        assert "revoked" in post_revocation_result.reason.lower()

    def test_revocation_is_synchronous_not_eventual(self, crl, sample_agent_id):
        """
        Verify that revocation takes effect immediately, not eventually.

        This ensures there's no eventual consistency delay that could
        allow unauthorized operations between revocation and propagation.
        """
        delegation_ids = [f"del-{i:03d}" for i in range(10)]

        # Revoke all delegations and verify each is immediately invalid
        for delegation_id in delegation_ids:
            # Verify valid before
            assert verify_delegation_with_crl(delegation_id, crl).valid is True

            # Revoke
            crl.add_revocation(
                delegation_id=delegation_id,
                agent_id=sample_agent_id,
                reason="Test revocation",
                revoked_by="system",
            )

            # Verify invalid immediately after - no delay needed
            assert verify_delegation_with_crl(delegation_id, crl).valid is False

    def test_revocation_persists_without_refresh(
        self, crl, sample_delegation_id, sample_agent_id
    ):
        """
        Verify that revocation persists and remains valid without refresh.

        Once revoked, a delegation should stay revoked until explicitly
        removed from the CRL.
        """
        crl.add_revocation(
            delegation_id=sample_delegation_id,
            agent_id=sample_agent_id,
            reason="Compromised key",
            revoked_by="admin",
        )

        # Check multiple times - should consistently be invalid
        for _ in range(5):
            result = verify_delegation_with_crl(sample_delegation_id, crl)
            assert result.valid is False, "Revocation should persist"


class TestCascadeRevocationTiming:
    """Test cascade revocation timing - root revocation invalidates children."""

    @pytest.fixture
    def broadcaster(self):
        """Create a revocation broadcaster."""
        return InMemoryRevocationBroadcaster()

    @pytest.fixture
    def registry(self):
        """Create a delegation registry with a chain of delegations."""
        registry = InMemoryDelegationRegistry()
        # Build delegation chain: root -> child1 -> grandchild
        # and root -> child2
        registry.register_delegation("root-agent", "child1-agent")
        registry.register_delegation("root-agent", "child2-agent")
        registry.register_delegation("child1-agent", "grandchild-agent")
        return registry

    @pytest.fixture
    def cascade_manager(self, broadcaster, registry):
        """Create a cascade revocation manager."""
        return CascadeRevocationManager(broadcaster, registry)

    def test_cascade_revocation_timing(self, cascade_manager, broadcaster):
        """
        Revoking root of chain invalidates all children in same operation.

        When an agent at the root of a delegation chain is revoked,
        all downstream agents should be revoked as part of the same
        cascade operation, not as separate delayed operations.
        """
        # Revoke the root agent
        revoked_events = cascade_manager.cascade_revoke(
            target_id="root-agent",
            revoked_by="admin",
            reason="Root compromise",
        )

        # All agents in the chain should be revoked
        revoked_ids = {event.target_id for event in revoked_events}
        assert "root-agent" in revoked_ids, "Root agent should be revoked"
        assert "child1-agent" in revoked_ids, "Child1 should be cascade revoked"
        assert "child2-agent" in revoked_ids, "Child2 should be cascade revoked"
        assert "grandchild-agent" in revoked_ids, "Grandchild should be cascade revoked"

        # Verify all events are in broadcaster history (synchronous propagation)
        history = broadcaster.get_history()
        history_ids = {event.target_id for event in history}
        assert history_ids == revoked_ids, "All revocations should be in history"

    def test_partial_cascade_does_not_leave_orphans(
        self, cascade_manager, broadcaster, registry
    ):
        """
        If we revoke only child1, root and siblings remain unaffected.

        This tests that cascade revocation only flows downward in the
        delegation chain, not upward or sideways.
        """
        # Revoke just child1 (should revoke child1 and grandchild, not root or child2)
        revoked_events = cascade_manager.cascade_revoke(
            target_id="child1-agent",
            revoked_by="admin",
            reason="Child1 compromise",
        )

        revoked_ids = {event.target_id for event in revoked_events}

        # Child1 and grandchild should be revoked
        assert "child1-agent" in revoked_ids
        assert "grandchild-agent" in revoked_ids

        # Root and child2 should NOT be revoked
        assert "root-agent" not in revoked_ids
        assert "child2-agent" not in revoked_ids

    def test_cascade_revocation_order(self, cascade_manager, broadcaster):
        """
        Verify that cascade revocation happens in proper order.

        The root should be revoked before children to ensure there's
        no window where children could still operate.
        """
        cascade_manager.cascade_revoke(
            target_id="root-agent",
            revoked_by="admin",
            reason="Test order",
        )

        history = broadcaster.get_history()

        # Find indices of events by target_id
        def find_event_index(target_id):
            for i, event in enumerate(history):
                if event.target_id == target_id:
                    return i
            return -1

        root_idx = find_event_index("root-agent")
        child1_idx = find_event_index("child1-agent")
        child2_idx = find_event_index("child2-agent")
        grandchild_idx = find_event_index("grandchild-agent")

        # Root should be revoked first (or at same time as direct children)
        assert root_idx >= 0, "Root should be in history"
        assert child1_idx >= 0, "Child1 should be in history"
        # Grandchild should come after child1 (its parent)
        assert (
            grandchild_idx > child1_idx or child1_idx == grandchild_idx
        ), "Grandchild should be revoked after (or with) its parent"


class TestNoActionDuringRevocation:
    """Test that no verification succeeds during revocation processing."""

    @pytest.fixture
    def crl(self):
        """Create a CRL for testing."""
        return CertificateRevocationList(issuer_id="org-acme")

    def test_no_action_during_revocation(self, crl):
        """
        No verification succeeds during revocation processing.

        This test simulates concurrent verification attempts during
        the revocation process. Once revocation starts for a delegation,
        all verifications should fail.

        Note: In the current synchronous implementation, revocation is
        atomic so this tests the state transition behavior.
        """
        delegation_id = "del-concurrent"
        agent_id = "agent-concurrent"

        # Verify starts valid
        assert verify_delegation_with_crl(delegation_id, crl).valid is True

        # Start "processing" - add the revocation
        crl.add_revocation(
            delegation_id=delegation_id,
            agent_id=agent_id,
            reason="Concurrent test",
            revoked_by="admin",
        )

        # During and after processing, verification should fail
        # (In a real async system, this would test concurrent access)
        for _ in range(10):
            result = verify_delegation_with_crl(delegation_id, crl)
            assert (
                result.valid is False
            ), "Verification should fail once revocation is initiated"

    def test_crl_verification_atomicity(self):
        """
        Test that CRL operations are atomic - no partial states visible.

        When a revocation is added, it should be fully visible or not
        visible at all, never in a partial state.
        """
        crl = CertificateRevocationList(issuer_id="org-acme")

        delegation_id = "del-atomic"
        agent_id = "agent-atomic"

        # Add revocation with all fields
        entry = crl.add_revocation(
            delegation_id=delegation_id,
            agent_id=agent_id,
            reason="Atomic test",
            revoked_by="admin",
        )

        # Retrieve and verify all fields are set (no partial state)
        stored_entry = crl.get_entry(delegation_id)
        assert stored_entry is not None, "Entry should exist"
        assert stored_entry.delegation_id == delegation_id
        assert stored_entry.agent_id == agent_id
        assert stored_entry.reason == "Atomic test"
        assert stored_entry.revoked_by == "admin"
        assert stored_entry.revoked_at is not None

    def test_multiple_concurrent_revocations(self):
        """
        Test handling of multiple revocations happening concurrently.

        In a real system, multiple revocations might be processed
        at the same time. Each should complete fully.
        """
        crl = CertificateRevocationList(issuer_id="org-acme")

        # Add multiple revocations rapidly
        num_revocations = 100
        for i in range(num_revocations):
            crl.add_revocation(
                delegation_id=f"del-{i:03d}",
                agent_id=f"agent-{i:03d}",
                reason=f"Bulk revocation {i}",
                revoked_by="bulk-admin",
            )

        # Verify all were revoked
        assert crl.entry_count == num_revocations

        for i in range(num_revocations):
            result = verify_delegation_with_crl(f"del-{i:03d}", crl)
            assert result.valid is False, f"Delegation del-{i:03d} should be revoked"

    def test_revocation_with_signed_crl(self):
        """
        Test that revocation invalidates even on signed CRLs.

        Adding a revocation should invalidate any existing signature,
        preventing use of stale signed CRLs.
        """
        private_key, public_key = generate_keypair()
        crl = CertificateRevocationList(issuer_id="org-acme")

        # Add initial revocation and sign
        crl.add_revocation(
            delegation_id="del-initial",
            agent_id="agent-initial",
            reason="Initial",
            revoked_by="admin",
        )
        crl.sign(private_key)
        assert crl.verify_signature(public_key) is True

        # Add new revocation - should invalidate signature
        crl.add_revocation(
            delegation_id="del-new",
            agent_id="agent-new",
            reason="New revocation",
            revoked_by="admin",
        )

        # Signature should now be invalid (CRL was modified)
        assert crl.verify_signature(public_key) is False

        # But verifications should still work
        assert verify_delegation_with_crl("del-initial", crl).valid is False
        assert verify_delegation_with_crl("del-new", crl).valid is False
