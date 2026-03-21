# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for InMemoryTrustStore soft_delete and include_inactive support (F-01).

Verifies:
- soft_delete=True moves chain to _inactive instead of deleting
- soft_delete=False hard-deletes from both _chains and _inactive
- get_chain with include_inactive=True checks _inactive
- get_chain with include_inactive=False only checks _chains
- list_chains with active_only=False includes inactive chains
- list_chains with active_only=True excludes inactive chains
- count_chains respects active_only parameter
- Backward compatibility: existing callers get same behavior
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kailash.trust.chain import AuthorityType, GenesisRecord, TrustLineageChain
from kailash.trust.exceptions import TrustChainNotFoundError
from kailash.trust.chain_store.memory import InMemoryTrustStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store():
    """Fresh InMemoryTrustStore for each test."""
    return InMemoryTrustStore()


# ---------------------------------------------------------------------------
# 1 -- _inactive dict exists on init
# ---------------------------------------------------------------------------


class TestInactiveStorageInit:
    """F-01: InMemoryTrustStore must have _inactive dict on init."""

    def test_inactive_dict_exists(self, store):
        """Store must have _inactive attribute as an empty dict."""
        assert hasattr(store, "_inactive")
        assert isinstance(store._inactive, dict)
        assert len(store._inactive) == 0


# ---------------------------------------------------------------------------
# 2 -- soft_delete=True behavior
# ---------------------------------------------------------------------------


class TestSoftDeleteTrue:
    """F-01: soft_delete=True must move chain from _chains to _inactive."""

    async def test_soft_delete_moves_to_inactive(self, store):
        """Soft-deleting must move the chain from _chains to _inactive."""
        await store.store_chain(_make_chain("agent-A"))
        assert "agent-A" in store._chains

        await store.delete_chain("agent-A", soft_delete=True)

        assert "agent-A" not in store._chains
        assert "agent-A" in store._inactive

    async def test_soft_delete_preserves_chain_data(self, store):
        """Soft-deleted chain data must be preserved in _inactive."""
        chain = _make_chain("agent-A")
        await store.store_chain(chain)

        await store.delete_chain("agent-A", soft_delete=True)

        inactive_chain = store._inactive["agent-A"]
        assert inactive_chain.genesis.agent_id == "agent-A"
        assert inactive_chain.genesis.authority_id == "auth-1"

    async def test_soft_delete_chain_not_found_raises(self, store):
        """Soft-deleting a non-existent chain must raise TrustChainNotFoundError."""
        with pytest.raises(TrustChainNotFoundError):
            await store.delete_chain("ghost-agent", soft_delete=True)

    async def test_soft_delete_is_default(self, store):
        """Default delete_chain behavior must be soft_delete (soft_delete=True)."""
        await store.store_chain(_make_chain("agent-A"))

        # Call without explicit soft_delete parameter -- default is True
        await store.delete_chain("agent-A")

        assert "agent-A" not in store._chains
        assert "agent-A" in store._inactive


# ---------------------------------------------------------------------------
# 3 -- soft_delete=False behavior
# ---------------------------------------------------------------------------


class TestSoftDeleteFalse:
    """F-01: soft_delete=False must hard-delete from both _chains and _inactive."""

    async def test_hard_delete_removes_from_chains(self, store):
        """Hard delete must remove chain from _chains completely."""
        await store.store_chain(_make_chain("agent-A"))

        await store.delete_chain("agent-A", soft_delete=False)

        assert "agent-A" not in store._chains
        assert "agent-A" not in store._inactive

    async def test_hard_delete_removes_from_inactive(self, store):
        """Hard delete must also remove from _inactive if chain was soft-deleted first."""
        await store.store_chain(_make_chain("agent-A"))
        await store.delete_chain("agent-A", soft_delete=True)
        assert "agent-A" in store._inactive

        # Now hard-delete the inactive chain
        await store.delete_chain("agent-A", soft_delete=False)

        assert "agent-A" not in store._chains
        assert "agent-A" not in store._inactive

    async def test_hard_delete_non_existent_raises(self, store):
        """Hard-deleting a chain not in _chains or _inactive must raise TrustChainNotFoundError."""
        with pytest.raises(TrustChainNotFoundError):
            await store.delete_chain("ghost-agent", soft_delete=False)


# ---------------------------------------------------------------------------
# 4 -- get_chain with include_inactive
# ---------------------------------------------------------------------------


class TestGetChainIncludeInactive:
    """F-01: get_chain must support include_inactive parameter."""

    async def test_get_active_chain_default(self, store):
        """get_chain must return active chains by default."""
        await store.store_chain(_make_chain("agent-A"))
        chain = await store.get_chain("agent-A")
        assert chain.genesis.agent_id == "agent-A"

    async def test_get_soft_deleted_chain_without_include_inactive_raises(self, store):
        """get_chain without include_inactive must NOT find soft-deleted chains."""
        await store.store_chain(_make_chain("agent-A"))
        await store.delete_chain("agent-A", soft_delete=True)

        with pytest.raises(TrustChainNotFoundError):
            await store.get_chain("agent-A")

    async def test_get_soft_deleted_chain_with_include_inactive_false_raises(self, store):
        """get_chain with include_inactive=False must NOT find soft-deleted chains."""
        await store.store_chain(_make_chain("agent-A"))
        await store.delete_chain("agent-A", soft_delete=True)

        with pytest.raises(TrustChainNotFoundError):
            await store.get_chain("agent-A", include_inactive=False)

    async def test_get_soft_deleted_chain_with_include_inactive_true(self, store):
        """get_chain with include_inactive=True must find soft-deleted chains."""
        await store.store_chain(_make_chain("agent-A"))
        await store.delete_chain("agent-A", soft_delete=True)

        chain = await store.get_chain("agent-A", include_inactive=True)
        assert chain.genesis.agent_id == "agent-A"

    async def test_get_active_chain_with_include_inactive_true(self, store):
        """get_chain with include_inactive=True must also find active chains."""
        await store.store_chain(_make_chain("agent-A"))

        chain = await store.get_chain("agent-A", include_inactive=True)
        assert chain.genesis.agent_id == "agent-A"

    async def test_get_non_existent_chain_with_include_inactive_true_raises(self, store):
        """get_chain with include_inactive=True for non-existent chain must raise."""
        with pytest.raises(TrustChainNotFoundError):
            await store.get_chain("ghost-agent", include_inactive=True)


# ---------------------------------------------------------------------------
# 5 -- list_chains with active_only
# ---------------------------------------------------------------------------


class TestListChainsActiveOnly:
    """F-01: list_chains must respect active_only parameter."""

    async def test_list_active_only_excludes_inactive(self, store):
        """list_chains with active_only=True must exclude soft-deleted chains."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))
        await store.delete_chain("agent-B", soft_delete=True)

        chains = await store.list_chains(active_only=True)
        agent_ids = [c.genesis.agent_id for c in chains]

        assert "agent-A" in agent_ids
        assert "agent-B" not in agent_ids

    async def test_list_all_includes_inactive(self, store):
        """list_chains with active_only=False must include soft-deleted chains."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))
        await store.delete_chain("agent-B", soft_delete=True)

        chains = await store.list_chains(active_only=False)
        agent_ids = [c.genesis.agent_id for c in chains]

        assert "agent-A" in agent_ids
        assert "agent-B" in agent_ids

    async def test_list_active_only_is_default(self, store):
        """Default list_chains behavior must be active_only=True."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))
        await store.delete_chain("agent-B", soft_delete=True)

        # Call without active_only -- default is True
        chains = await store.list_chains()
        agent_ids = [c.genesis.agent_id for c in chains]

        assert "agent-A" in agent_ids
        assert "agent-B" not in agent_ids

    async def test_list_with_authority_filter_and_active_only(self, store):
        """list_chains with authority_id filter must respect active_only."""
        await store.store_chain(_make_chain("agent-A", authority_id="auth-1"))
        await store.store_chain(_make_chain("agent-B", authority_id="auth-1"))
        await store.store_chain(_make_chain("agent-C", authority_id="auth-2"))
        await store.delete_chain("agent-B", soft_delete=True)

        # active_only=True with authority filter
        chains = await store.list_chains(authority_id="auth-1", active_only=True)
        agent_ids = [c.genesis.agent_id for c in chains]
        assert "agent-A" in agent_ids
        assert "agent-B" not in agent_ids

        # active_only=False with authority filter
        chains = await store.list_chains(authority_id="auth-1", active_only=False)
        agent_ids = [c.genesis.agent_id for c in chains]
        assert "agent-A" in agent_ids
        assert "agent-B" in agent_ids
        assert "agent-C" not in agent_ids

    async def test_list_pagination_with_inactive(self, store):
        """list_chains pagination must work correctly with active_only=False."""
        for i in range(5):
            await store.store_chain(_make_chain(f"agent-{i}"))
        await store.delete_chain("agent-2", soft_delete=True)
        await store.delete_chain("agent-4", soft_delete=True)

        # All including inactive (5 total)
        all_chains = await store.list_chains(active_only=False)
        assert len(all_chains) == 5

        # Only active (3 total)
        active_chains = await store.list_chains(active_only=True)
        assert len(active_chains) == 3


# ---------------------------------------------------------------------------
# 6 -- count_chains with active_only
# ---------------------------------------------------------------------------


class TestCountChainsActiveOnly:
    """F-01: count_chains must respect active_only parameter."""

    async def test_count_active_only(self, store):
        """count_chains with active_only=True must exclude soft-deleted chains."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))
        await store.delete_chain("agent-B", soft_delete=True)

        count = await store.count_chains(active_only=True)
        assert count == 1

    async def test_count_all(self, store):
        """count_chains with active_only=False must include soft-deleted chains."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))
        await store.delete_chain("agent-B", soft_delete=True)

        count = await store.count_chains(active_only=False)
        assert count == 2

    async def test_count_with_authority_filter_and_active_only(self, store):
        """count_chains with authority_id filter must respect active_only."""
        await store.store_chain(_make_chain("agent-A", authority_id="auth-1"))
        await store.store_chain(_make_chain("agent-B", authority_id="auth-1"))
        await store.delete_chain("agent-B", soft_delete=True)

        assert await store.count_chains(authority_id="auth-1", active_only=True) == 1
        assert await store.count_chains(authority_id="auth-1", active_only=False) == 2


# ---------------------------------------------------------------------------
# 7 -- close() clears both _chains and _inactive
# ---------------------------------------------------------------------------


class TestCloseCleanup:
    """F-01: close() must clear both _chains and _inactive."""

    async def test_close_clears_inactive(self, store):
        """close() must clear the _inactive dict as well."""
        await store.store_chain(_make_chain("agent-A"))
        await store.delete_chain("agent-A", soft_delete=True)
        assert len(store._inactive) == 1

        await store.close()

        assert len(store._chains) == 0
        assert len(store._inactive) == 0


# ---------------------------------------------------------------------------
# 8 -- Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """F-01: Existing callers must not break."""

    async def test_store_and_get_still_works(self, store):
        """Basic store and get operations must still work."""
        chain = _make_chain("agent-A")
        agent_id = await store.store_chain(chain)
        assert agent_id == "agent-A"

        retrieved = await store.get_chain("agent-A")
        assert retrieved.genesis.agent_id == "agent-A"

    async def test_update_still_works(self, store):
        """Update operation must still work."""
        await store.store_chain(_make_chain("agent-A"))
        new_chain = _make_chain("agent-A", authority_id="auth-2")
        await store.update_chain("agent-A", new_chain)

        retrieved = await store.get_chain("agent-A")
        assert retrieved.genesis.authority_id == "auth-2"

    async def test_transaction_still_works(self, store):
        """Transaction operations must still work with _inactive dict present."""
        await store.store_chain(_make_chain("agent-A"))
        new_chain = _make_chain("agent-A", authority_id="auth-2")

        async with store.transaction() as tx:
            await tx.update_chain("agent-A", new_chain)
            await tx.commit()

        retrieved = await store.get_chain("agent-A")
        assert retrieved.genesis.authority_id == "auth-2"
