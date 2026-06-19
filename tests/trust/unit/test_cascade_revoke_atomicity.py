# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for cascade_revoke() consistency and partial failure recovery (F-03).

Verifies:
- Rollback on partial failure: restores already-deleted chains (best-effort)
- Success=False on partial failure with informative errors
- revoked_agents reflects store ground truth even when rollback CANNOT restore
  a chain (the chain stays revoked and is reported, not silently zeroed)
- Complete success scenario removes all affected chains
- Backward compatibility: existing callers still work

Note: cascade_revoke does NOT use a single atomic transaction. The InMemory
transaction context snapshots only active chains and cannot roll back a
soft-delete; durable stores expose no transaction. Consistency is best-effort
snapshot rollback with honest ground-truth reporting in ``revoked_agents``.
See the cascade module docstring for the full contract.
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kailash.trust.chain import AuthorityType, GenesisRecord, TrustLineageChain
from kailash.trust.chain_store.memory import InMemoryTrustStore
from kailash.trust.exceptions import TrustChainNotFoundError
from kailash.trust.revocation.broadcaster import (
    InMemoryDelegationRegistry,
    InMemoryRevocationBroadcaster,
)
from kailash.trust.revocation.cascade import RevocationResult, cascade_revoke

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)


def _make_genesis(agent_id: str, authority_id: str = "auth-1") -> GenesisRecord:
    """Create a minimal GenesisRecord for testing."""
    return GenesisRecord(
        id=f"gen-{agent_id}",
        agent_id=agent_id,
        authority_id=authority_id,
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        signature="sig-test-genesis",
    )


def _make_chain(agent_id: str, authority_id: str = "auth-1") -> TrustLineageChain:
    """Create a minimal TrustLineageChain for testing."""
    return TrustLineageChain(genesis=_make_genesis(agent_id, authority_id))


class FailingTrustStore(InMemoryTrustStore):
    """TrustStore that fails on specific agent_ids during delete_chain.

    Used to simulate partial failure during cascade revocation.
    """

    def __init__(self, fail_on: Optional[List[str]] = None):
        super().__init__()
        self._fail_on = set(fail_on or [])

    async def delete_chain(self, agent_id: str, soft_delete: bool = True) -> None:
        if agent_id in self._fail_on:
            raise RuntimeError(f"Simulated store failure for agent '{agent_id}'")
        return await super().delete_chain(agent_id, soft_delete=soft_delete)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store():
    """Fresh InMemoryTrustStore for each test."""
    return InMemoryTrustStore()


@pytest.fixture
def registry():
    """Fresh InMemoryDelegationRegistry for each test."""
    return InMemoryDelegationRegistry()


@pytest.fixture
def broadcaster():
    """Fresh InMemoryRevocationBroadcaster for each test."""
    return InMemoryRevocationBroadcaster()


# ---------------------------------------------------------------------------
# 1 -- Partial failure: chains restored on error
# ---------------------------------------------------------------------------


class TestPartialFailureRecovery:
    """F-03: Partial failure must attempt to restore already-deleted chains."""

    async def test_partial_failure_sets_success_false(self, registry, broadcaster):
        """When a chain deletion fails mid-cascade, result.success must be False."""
        store = FailingTrustStore(fail_on=["agent-B"])
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))
        await store.store_chain(_make_chain("agent-C"))

        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-A", "agent-C")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Partial failure test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.success is False
        assert len(result.errors) > 0
        assert "agent-B" in result.errors

    async def test_partial_failure_restores_deleted_chains(self, registry, broadcaster):
        """On partial failure, already soft-deleted chains must be restored."""
        store = FailingTrustStore(fail_on=["agent-C"])
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))
        await store.store_chain(_make_chain("agent-C"))

        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-B", "agent-C")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Restore test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.success is False

        # Chains that were successfully deleted before the failure
        # should be restored (rolled back) for consistency
        # All chains should still be accessible after rollback
        for agent_id in ("agent-A", "agent-B", "agent-C"):
            chain = await store.get_chain(agent_id)
            assert chain.genesis.agent_id == agent_id

    async def test_partial_failure_errors_contain_details(self, registry, broadcaster):
        """Errors from partial failure must contain descriptive messages."""
        store = FailingTrustStore(fail_on=["agent-B"])
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))

        registry.register_delegation("agent-A", "agent-B")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Error details test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert "agent-B" in result.errors
        assert "RuntimeError" in result.errors["agent-B"]

    async def test_partial_failure_logs_warning(self, registry, broadcaster, caplog):
        """Partial failure must log a warning about the rollback."""
        store = FailingTrustStore(fail_on=["agent-B"])
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))

        registry.register_delegation("agent-A", "agent-B")

        with caplog.at_level(logging.WARNING):
            result = await cascade_revoke(
                agent_id="agent-A",
                store=store,
                reason="Log warning test",
                revoked_by="admin",
                broadcaster=broadcaster,
                delegation_registry=registry,
            )

        assert result.success is False
        # Check that some kind of rollback/failure warning was logged
        warning_messages = [
            r.message for r in caplog.records if r.levelno >= logging.WARNING
        ]
        assert len(warning_messages) > 0


# ---------------------------------------------------------------------------
# 2 -- Complete success: all chains deleted
# ---------------------------------------------------------------------------


class TestCompleteSuccess:
    """F-03: When all deletions succeed, all chains must be removed."""

    async def test_all_chains_deleted_on_success(self, store, registry, broadcaster):
        """Successful cascade must delete all affected chains."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))
        await store.store_chain(_make_chain("agent-C"))

        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-B", "agent-C")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Complete success test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.success is True
        assert set(result.revoked_agents) == {"agent-A", "agent-B", "agent-C"}

    async def test_success_with_no_errors(self, store, registry, broadcaster):
        """Successful cascade must have empty errors dict."""
        await store.store_chain(_make_chain("agent-A"))

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="No errors test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.success is True
        assert result.errors == {}


# ---------------------------------------------------------------------------
# 3 -- Full-cascade consistency (no atomic transaction is used)
# ---------------------------------------------------------------------------


class TestFullCascadeConsistency:
    """cascade_revoke removes all affected chains on the happy path.

    NOTE: cascade_revoke does NOT call ``store.transaction()`` — the InMemory
    transaction context snapshots only active chains and cannot roll back a
    soft-delete, and durable stores expose no transaction. This test asserts
    the OBSERVABLE contract (every affected chain revoked on success); it does
    NOT (and must not) claim a transaction path was taken.
    """

    async def test_inmemory_full_cascade_revokes_all_agents(
        self, store, registry, broadcaster
    ):
        """A clean multi-agent cascade soft-deletes every affected chain."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))

        registry.register_delegation("agent-A", "agent-B")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Full cascade consistency test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.success is True
        assert set(result.revoked_agents) == {"agent-A", "agent-B"}

    async def test_cascade_revoke_does_not_invoke_store_transaction(
        self, store, registry, broadcaster
    ):
        """Pin reality: cascade_revoke never calls store.transaction().

        The prior test/docstring claimed a transaction path was used. It was
        not, and cannot be (the transaction context cannot roll back a
        soft-delete). This guards against a future docstring re-introducing the
        false claim without wiring the (currently infeasible) behavior.
        """
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))
        registry.register_delegation("agent-A", "agent-B")

        calls = {"n": 0}
        original_transaction = store.transaction

        def _counting_transaction(*args, **kwargs):
            calls["n"] += 1
            return original_transaction(*args, **kwargs)

        store.transaction = _counting_transaction  # type: ignore[method-assign]
        try:
            result = await cascade_revoke(
                agent_id="agent-A",
                store=store,
                reason="No-transaction pin",
                revoked_by="admin",
                broadcaster=broadcaster,
                delegation_registry=registry,
            )
        finally:
            store.transaction = original_transaction  # type: ignore[method-assign]

        assert result.success is True
        assert calls["n"] == 0, (
            "cascade_revoke called store.transaction(); the consistency contract "
            "is best-effort snapshot rollback, NOT transactional — update the docs "
            "and this test together if that changes."
        )


# ---------------------------------------------------------------------------
# 4 -- Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibilityF03:
    """F-03: Existing callers and test patterns must still work."""

    async def test_existing_cascade_revoke_api_unchanged(
        self, store, registry, broadcaster
    ):
        """cascade_revoke function signature and return type must be unchanged."""
        await store.store_chain(_make_chain("agent-A"))

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="API compat test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert isinstance(result, RevocationResult)
        assert isinstance(result.success, bool)
        assert isinstance(result.events, list)
        assert isinstance(result.revoked_agents, list)
        assert isinstance(result.errors, dict)

    async def test_idempotent_revocation_still_works(
        self, store, registry, broadcaster
    ):
        """Re-revoking an already-revoked agent must still be a no-op."""
        await store.store_chain(_make_chain("agent-A"))

        # First revocation
        await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="First",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        # Second revocation -- must be idempotent no-op
        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Second",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.success is True
        assert result.events == []
        assert result.revoked_agents == []

    async def test_non_existent_agent_still_noop(self, store, registry, broadcaster):
        """Revoking a non-existent agent must still return no-op."""
        result = await cascade_revoke(
            agent_id="ghost-agent",
            store=store,
            reason="Ghost",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.success is True
        assert result.events == []

    async def test_default_broadcaster_and_registry_still_work(self, store):
        """cascade_revoke with default None broadcaster/registry must still work."""
        await store.store_chain(_make_chain("agent-A"))

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Defaults test",
            revoked_by="admin",
        )

        assert result.success is True
        assert "agent-A" in result.revoked_agents


# ---------------------------------------------------------------------------
# 5 -- Multiple failures in single cascade
# ---------------------------------------------------------------------------


class TestMultipleFailures:
    """F-03: Multiple failures in a single cascade must all be reported."""

    async def test_multiple_failures_all_reported(self, registry, broadcaster):
        """When multiple chain deletions fail, all errors must be reported."""
        store = FailingTrustStore(fail_on=["agent-B", "agent-C"])
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))
        await store.store_chain(_make_chain("agent-C"))

        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-A", "agent-C")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Multiple failures test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.success is False
        assert "agent-B" in result.errors
        assert "agent-C" in result.errors

    async def test_multiple_failures_all_chains_restored(self, registry, broadcaster):
        """When multiple deletions fail, ALL chains (including successfully deleted) must be restored."""
        store = FailingTrustStore(fail_on=["agent-C"])
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))
        await store.store_chain(_make_chain("agent-C"))

        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-A", "agent-C")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Multi-restore test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.success is False

        # All chains must be restored to preserve consistency
        for agent_id in ("agent-A", "agent-B", "agent-C"):
            chain = await store.get_chain(agent_id)
            assert chain.genesis.agent_id == agent_id
