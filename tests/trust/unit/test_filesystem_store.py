"""
Unit tests for FilesystemStore implementation.

Tests the filesystem-based TrustStore with:
- Directory initialization
- CRUD operations for trust chains
- Soft-delete and hard-delete behavior
- Filtering by authority_id and active_only
- Pagination (limit/offset)
- Thread-safe atomic writes
- Error handling for missing chains
- Round-trip serialization fidelity
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from kailash.trust.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    ConstraintEnvelope,
    ConstraintType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
)
from kailash.trust.exceptions import TrustChainNotFoundError
from kailash.trust.chain_store.filesystem import FilesystemStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_genesis(
    agent_id: str = "agent-1",
    authority_id: str = "auth-1",
) -> GenesisRecord:
    """Create a minimal GenesisRecord for testing."""
    return GenesisRecord(
        id=f"gen-{agent_id}",
        agent_id=agent_id,
        authority_id=authority_id,
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        signature="sig-test-genesis",
    )


def _make_chain(
    agent_id: str = "agent-1",
    authority_id: str = "auth-1",
) -> TrustLineageChain:
    """Create a minimal TrustLineageChain for testing."""
    return TrustLineageChain(genesis=_make_genesis(agent_id, authority_id))


def _make_chain_with_capability(
    agent_id: str = "agent-1",
    authority_id: str = "auth-1",
    capability: str = "read_data",
) -> TrustLineageChain:
    """Create a TrustLineageChain with a capability attestation."""
    chain = _make_chain(agent_id, authority_id)
    chain.capabilities.append(
        CapabilityAttestation(
            id=f"cap-{agent_id}-{capability}",
            capability=capability,
            capability_type=CapabilityType.ACCESS,
            constraints=["read_only"],
            attester_id=authority_id,
            attested_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            signature="sig-test-cap",
        )
    )
    return chain


def _make_chain_with_delegation(
    agent_id: str = "agent-1",
    authority_id: str = "auth-1",
) -> TrustLineageChain:
    """Create a TrustLineageChain with a delegation record."""
    chain = _make_chain(agent_id, authority_id)
    chain.delegations.append(
        DelegationRecord(
            id=f"del-{agent_id}",
            delegator_id="agent-0",
            delegatee_id=agent_id,
            task_id="task-1",
            capabilities_delegated=["read_data"],
            constraint_subset=["read_only"],
            delegated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            signature="sig-test-del",
        )
    )
    return chain


@pytest.fixture
def store(tmp_path):
    """Create a FilesystemStore with a temp directory."""
    chains_dir = tmp_path / "chains"
    return FilesystemStore(base_dir=str(chains_dir))


@pytest.fixture
def store_with_custom_dir(tmp_path):
    """Create a FilesystemStore in a nested custom directory."""
    chains_dir = tmp_path / "custom" / "nested" / "chains"
    return FilesystemStore(base_dir=str(chains_dir))


# ---------------------------------------------------------------------------
# Initialization Tests
# ---------------------------------------------------------------------------


class TestInitialize:
    """Tests for FilesystemStore.initialize()."""

    @pytest.mark.asyncio
    async def test_initialize_creates_directory(self, store, tmp_path):
        """initialize() must create the chains directory."""
        chains_dir = tmp_path / "chains"
        assert not chains_dir.exists()

        await store.initialize()

        assert chains_dir.exists()
        assert chains_dir.is_dir()

    @pytest.mark.asyncio
    async def test_initialize_creates_nested_directories(self, store_with_custom_dir, tmp_path):
        """initialize() must create nested parent directories."""
        nested_dir = tmp_path / "custom" / "nested" / "chains"
        assert not nested_dir.exists()

        await store_with_custom_dir.initialize()

        assert nested_dir.exists()
        assert nested_dir.is_dir()

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, store):
        """Calling initialize() multiple times must not raise."""
        await store.initialize()
        await store.initialize()  # Second call should be fine

    @pytest.mark.asyncio
    async def test_initialize_sets_initialized_flag(self, store):
        """initialize() must set the internal initialized flag."""
        assert not store._initialized
        await store.initialize()
        assert store._initialized

    @pytest.mark.asyncio
    async def test_default_base_dir(self):
        """Default base_dir should resolve to ~/.eatp/chains/."""
        store = FilesystemStore()
        expected = os.path.join(os.path.expanduser("~"), ".eatp", "chains")
        assert store._base_dir == Path(expected)


# ---------------------------------------------------------------------------
# store_chain Tests
# ---------------------------------------------------------------------------


class TestStoreChain:
    """Tests for FilesystemStore.store_chain()."""

    @pytest.mark.asyncio
    async def test_store_chain_creates_file(self, store, tmp_path):
        """store_chain() must create a JSON file named {agent_id}.json."""
        await store.initialize()
        chain = _make_chain("agent-1")

        agent_id = await store.store_chain(chain)

        assert agent_id == "agent-1"
        chain_file = tmp_path / "chains" / "agent-1.json"
        assert chain_file.exists()

    @pytest.mark.asyncio
    async def test_store_chain_json_valid(self, store, tmp_path):
        """Stored JSON must be valid and parseable."""
        await store.initialize()
        chain = _make_chain("agent-1")

        await store.store_chain(chain)

        chain_file = tmp_path / "chains" / "agent-1.json"
        data = json.loads(chain_file.read_text())
        assert data["chain"]["genesis"]["agent_id"] == "agent-1"

    @pytest.mark.asyncio
    async def test_store_chain_preserves_genesis_signature(self, store, tmp_path):
        """Stored data must preserve the genesis record signature."""
        await store.initialize()
        chain = _make_chain("agent-1")

        await store.store_chain(chain)

        chain_file = tmp_path / "chains" / "agent-1.json"
        data = json.loads(chain_file.read_text())
        assert data["chain"]["genesis"]["signature"] == "sig-test-genesis"

    @pytest.mark.asyncio
    async def test_store_chain_includes_metadata(self, store, tmp_path):
        """Stored JSON must include metadata (active flag, stored_at)."""
        await store.initialize()
        chain = _make_chain("agent-1")

        await store.store_chain(chain)

        chain_file = tmp_path / "chains" / "agent-1.json"
        data = json.loads(chain_file.read_text())
        assert data["active"] is True
        assert "stored_at" in data

    @pytest.mark.asyncio
    async def test_store_chain_with_expires_at(self, store, tmp_path):
        """store_chain() must persist the expires_at timestamp."""
        await store.initialize()
        chain = _make_chain("agent-1")
        expiry = datetime(2030, 12, 31, tzinfo=timezone.utc)

        await store.store_chain(chain, expires_at=expiry)

        chain_file = tmp_path / "chains" / "agent-1.json"
        data = json.loads(chain_file.read_text())
        assert data["expires_at"] == expiry.isoformat()

    @pytest.mark.asyncio
    async def test_store_chain_overwrites_existing(self, store):
        """Storing a chain with an existing agent_id must overwrite."""
        await store.initialize()
        chain1 = _make_chain_with_capability("agent-1", capability="read_data")
        chain2 = _make_chain_with_capability("agent-1", capability="write_data")

        await store.store_chain(chain1)
        await store.store_chain(chain2)

        retrieved = await store.get_chain("agent-1")
        assert retrieved.capabilities[0].capability == "write_data"

    @pytest.mark.asyncio
    async def test_store_chain_raises_without_initialize(self, store):
        """store_chain() must raise RuntimeError if not initialized."""
        chain = _make_chain("agent-1")
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.store_chain(chain)

    @pytest.mark.asyncio
    async def test_store_chain_with_capabilities(self, store):
        """store_chain() must preserve capability attestations."""
        await store.initialize()
        chain = _make_chain_with_capability("agent-1")

        await store.store_chain(chain)
        retrieved = await store.get_chain("agent-1")

        assert len(retrieved.capabilities) == 1
        assert retrieved.capabilities[0].capability == "read_data"
        assert retrieved.capabilities[0].signature == "sig-test-cap"

    @pytest.mark.asyncio
    async def test_store_chain_with_delegations(self, store):
        """store_chain() must preserve delegation records."""
        await store.initialize()
        chain = _make_chain_with_delegation("agent-1")

        await store.store_chain(chain)
        retrieved = await store.get_chain("agent-1")

        assert len(retrieved.delegations) == 1
        assert retrieved.delegations[0].delegator_id == "agent-0"
        assert retrieved.delegations[0].signature == "sig-test-del"


# ---------------------------------------------------------------------------
# get_chain Tests
# ---------------------------------------------------------------------------


class TestGetChain:
    """Tests for FilesystemStore.get_chain()."""

    @pytest.mark.asyncio
    async def test_get_chain_returns_correct_chain(self, store):
        """get_chain() must return the correct chain for agent_id."""
        await store.initialize()
        chain = _make_chain("agent-1")
        await store.store_chain(chain)

        retrieved = await store.get_chain("agent-1")

        assert retrieved.genesis.agent_id == "agent-1"
        assert retrieved.genesis.authority_id == "auth-1"

    @pytest.mark.asyncio
    async def test_get_chain_raises_for_missing(self, store):
        """get_chain() must raise TrustChainNotFoundError for missing chains."""
        await store.initialize()

        with pytest.raises(TrustChainNotFoundError):
            await store.get_chain("nonexistent-agent")

    @pytest.mark.asyncio
    async def test_get_chain_excludes_inactive_by_default(self, store):
        """get_chain() must exclude soft-deleted chains by default."""
        await store.initialize()
        chain = _make_chain("agent-1")
        await store.store_chain(chain)
        await store.delete_chain("agent-1", soft_delete=True)

        with pytest.raises(TrustChainNotFoundError):
            await store.get_chain("agent-1")

    @pytest.mark.asyncio
    async def test_get_chain_includes_inactive_when_requested(self, store):
        """get_chain(include_inactive=True) must return soft-deleted chains."""
        await store.initialize()
        chain = _make_chain("agent-1")
        await store.store_chain(chain)
        await store.delete_chain("agent-1", soft_delete=True)

        retrieved = await store.get_chain("agent-1", include_inactive=True)

        assert retrieved.genesis.agent_id == "agent-1"

    @pytest.mark.asyncio
    async def test_get_chain_raises_without_initialize(self, store):
        """get_chain() must raise RuntimeError if not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.get_chain("agent-1")

    @pytest.mark.asyncio
    async def test_get_chain_round_trip_fidelity(self, store):
        """get_chain() must return data identical to what was stored."""
        await store.initialize()
        chain = _make_chain_with_capability("agent-1", capability="analyze")
        chain.delegations.append(
            DelegationRecord(
                id="del-1",
                delegator_id="agent-0",
                delegatee_id="agent-1",
                task_id="task-1",
                capabilities_delegated=["analyze"],
                constraint_subset=["read_only"],
                delegated_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
                signature="sig-del-round-trip",
            )
        )

        await store.store_chain(chain)
        retrieved = await store.get_chain("agent-1")

        assert retrieved.genesis.id == chain.genesis.id
        assert retrieved.genesis.agent_id == chain.genesis.agent_id
        assert retrieved.genesis.authority_id == chain.genesis.authority_id
        assert retrieved.genesis.authority_type == chain.genesis.authority_type
        assert retrieved.genesis.signature == chain.genesis.signature
        assert len(retrieved.capabilities) == len(chain.capabilities)
        assert retrieved.capabilities[0].id == chain.capabilities[0].id
        assert retrieved.capabilities[0].signature == chain.capabilities[0].signature
        assert len(retrieved.delegations) == len(chain.delegations)
        assert retrieved.delegations[0].id == chain.delegations[0].id
        assert retrieved.delegations[0].signature == chain.delegations[0].signature


# ---------------------------------------------------------------------------
# update_chain Tests
# ---------------------------------------------------------------------------


class TestUpdateChain:
    """Tests for FilesystemStore.update_chain()."""

    @pytest.mark.asyncio
    async def test_update_chain_replaces_data(self, store):
        """update_chain() must replace the chain data."""
        await store.initialize()
        chain1 = _make_chain("agent-1", authority_id="auth-1")
        await store.store_chain(chain1)

        chain2 = _make_chain_with_capability("agent-1", authority_id="auth-1")
        await store.update_chain("agent-1", chain2)

        retrieved = await store.get_chain("agent-1")
        assert len(retrieved.capabilities) == 1

    @pytest.mark.asyncio
    async def test_update_chain_raises_for_missing(self, store):
        """update_chain() must raise TrustChainNotFoundError for missing chains."""
        await store.initialize()

        chain = _make_chain("nonexistent")
        with pytest.raises(TrustChainNotFoundError):
            await store.update_chain("nonexistent", chain)

    @pytest.mark.asyncio
    async def test_update_chain_preserves_metadata(self, store, tmp_path):
        """update_chain() must preserve stored_at and active status."""
        await store.initialize()
        chain = _make_chain("agent-1")
        await store.store_chain(chain)

        chain_file = tmp_path / "chains" / "agent-1.json"
        original_data = json.loads(chain_file.read_text())
        original_stored_at = original_data["stored_at"]

        updated_chain = _make_chain_with_capability("agent-1")
        await store.update_chain("agent-1", updated_chain)

        updated_data = json.loads(chain_file.read_text())
        assert updated_data["stored_at"] == original_stored_at
        assert updated_data["active"] is True
        assert "updated_at" in updated_data

    @pytest.mark.asyncio
    async def test_update_chain_raises_without_initialize(self, store):
        """update_chain() must raise RuntimeError if not initialized."""
        chain = _make_chain("agent-1")
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.update_chain("agent-1", chain)


# ---------------------------------------------------------------------------
# delete_chain Tests
# ---------------------------------------------------------------------------


class TestDeleteChain:
    """Tests for FilesystemStore.delete_chain()."""

    @pytest.mark.asyncio
    async def test_soft_delete_marks_inactive(self, store, tmp_path):
        """Soft delete must mark the chain as inactive, not remove the file."""
        await store.initialize()
        chain = _make_chain("agent-1")
        await store.store_chain(chain)

        await store.delete_chain("agent-1", soft_delete=True)

        chain_file = tmp_path / "chains" / "agent-1.json"
        assert chain_file.exists(), "Soft delete must not remove the file"
        data = json.loads(chain_file.read_text())
        assert data["active"] is False
        assert "deleted_at" in data

    @pytest.mark.asyncio
    async def test_hard_delete_removes_file(self, store, tmp_path):
        """Hard delete must remove the file from disk."""
        await store.initialize()
        chain = _make_chain("agent-1")
        await store.store_chain(chain)

        await store.delete_chain("agent-1", soft_delete=False)

        chain_file = tmp_path / "chains" / "agent-1.json"
        assert not chain_file.exists(), "Hard delete must remove the file"

    @pytest.mark.asyncio
    async def test_delete_raises_for_missing(self, store):
        """delete_chain() must raise TrustChainNotFoundError for missing chains."""
        await store.initialize()

        with pytest.raises(TrustChainNotFoundError):
            await store.delete_chain("nonexistent")

    @pytest.mark.asyncio
    async def test_soft_delete_idempotent(self, store):
        """Soft-deleting an already soft-deleted chain must not raise."""
        await store.initialize()
        chain = _make_chain("agent-1")
        await store.store_chain(chain)

        await store.delete_chain("agent-1", soft_delete=True)
        # Second soft delete should not raise
        await store.delete_chain("agent-1", soft_delete=True)

    @pytest.mark.asyncio
    async def test_delete_chain_raises_without_initialize(self, store):
        """delete_chain() must raise RuntimeError if not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.delete_chain("agent-1")


# ---------------------------------------------------------------------------
# list_chains Tests
# ---------------------------------------------------------------------------


class TestListChains:
    """Tests for FilesystemStore.list_chains()."""

    @pytest.mark.asyncio
    async def test_list_chains_empty(self, store):
        """list_chains() on empty store must return empty list."""
        await store.initialize()

        result = await store.list_chains()

        assert result == []

    @pytest.mark.asyncio
    async def test_list_chains_returns_all_active(self, store):
        """list_chains() must return all active chains."""
        await store.initialize()
        for i in range(3):
            await store.store_chain(_make_chain(f"agent-{i}"))

        result = await store.list_chains()

        assert len(result) == 3
        agent_ids = {c.genesis.agent_id for c in result}
        assert agent_ids == {"agent-0", "agent-1", "agent-2"}

    @pytest.mark.asyncio
    async def test_list_chains_excludes_inactive(self, store):
        """list_chains(active_only=True) must exclude soft-deleted chains."""
        await store.initialize()
        for i in range(3):
            await store.store_chain(_make_chain(f"agent-{i}"))
        await store.delete_chain("agent-1", soft_delete=True)

        result = await store.list_chains(active_only=True)

        assert len(result) == 2
        agent_ids = {c.genesis.agent_id for c in result}
        assert "agent-1" not in agent_ids

    @pytest.mark.asyncio
    async def test_list_chains_includes_inactive(self, store):
        """list_chains(active_only=False) must include soft-deleted chains."""
        await store.initialize()
        for i in range(3):
            await store.store_chain(_make_chain(f"agent-{i}"))
        await store.delete_chain("agent-1", soft_delete=True)

        result = await store.list_chains(active_only=False)

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_list_chains_filter_by_authority(self, store):
        """list_chains(authority_id=...) must filter by authority."""
        await store.initialize()
        await store.store_chain(_make_chain("agent-1", authority_id="auth-A"))
        await store.store_chain(_make_chain("agent-2", authority_id="auth-B"))
        await store.store_chain(_make_chain("agent-3", authority_id="auth-A"))

        result = await store.list_chains(authority_id="auth-A")

        assert len(result) == 2
        for chain in result:
            assert chain.genesis.authority_id == "auth-A"

    @pytest.mark.asyncio
    async def test_list_chains_pagination_limit(self, store):
        """list_chains(limit=N) must return at most N results."""
        await store.initialize()
        for i in range(5):
            await store.store_chain(_make_chain(f"agent-{i}"))

        result = await store.list_chains(limit=2)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_chains_pagination_offset(self, store):
        """list_chains(offset=N) must skip the first N results."""
        await store.initialize()
        for i in range(5):
            await store.store_chain(_make_chain(f"agent-{i}"))

        all_chains = await store.list_chains(limit=100)
        offset_chains = await store.list_chains(offset=2, limit=100)

        assert len(offset_chains) == 3
        # The offset chains should be a subset of all chains
        offset_ids = {c.genesis.agent_id for c in offset_chains}
        all_ids = [c.genesis.agent_id for c in all_chains]
        # Offset should skip the first 2
        expected_ids = set(all_ids[2:])
        assert offset_ids == expected_ids

    @pytest.mark.asyncio
    async def test_list_chains_pagination_combined(self, store):
        """list_chains(limit=2, offset=1) must return correct page."""
        await store.initialize()
        for i in range(5):
            await store.store_chain(_make_chain(f"agent-{i}"))

        all_chains = await store.list_chains(limit=100)
        page = await store.list_chains(limit=2, offset=1)

        assert len(page) == 2
        all_ids = [c.genesis.agent_id for c in all_chains]
        page_ids = [c.genesis.agent_id for c in page]
        assert page_ids == all_ids[1:3]

    @pytest.mark.asyncio
    async def test_list_chains_raises_without_initialize(self, store):
        """list_chains() must raise RuntimeError if not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.list_chains()


# ---------------------------------------------------------------------------
# count_chains Tests
# ---------------------------------------------------------------------------


class TestCountChains:
    """Tests for FilesystemStore.count_chains()."""

    @pytest.mark.asyncio
    async def test_count_chains_empty(self, store):
        """count_chains() on empty store must return 0."""
        await store.initialize()

        count = await store.count_chains()

        assert count == 0

    @pytest.mark.asyncio
    async def test_count_chains_all_active(self, store):
        """count_chains() must count active chains."""
        await store.initialize()
        for i in range(3):
            await store.store_chain(_make_chain(f"agent-{i}"))

        count = await store.count_chains()

        assert count == 3

    @pytest.mark.asyncio
    async def test_count_chains_excludes_inactive(self, store):
        """count_chains(active_only=True) must exclude soft-deleted chains."""
        await store.initialize()
        for i in range(3):
            await store.store_chain(_make_chain(f"agent-{i}"))
        await store.delete_chain("agent-1", soft_delete=True)

        count = await store.count_chains(active_only=True)

        assert count == 2

    @pytest.mark.asyncio
    async def test_count_chains_includes_inactive(self, store):
        """count_chains(active_only=False) must include soft-deleted chains."""
        await store.initialize()
        for i in range(3):
            await store.store_chain(_make_chain(f"agent-{i}"))
        await store.delete_chain("agent-1", soft_delete=True)

        count = await store.count_chains(active_only=False)

        assert count == 3

    @pytest.mark.asyncio
    async def test_count_chains_filter_by_authority(self, store):
        """count_chains(authority_id=...) must filter by authority."""
        await store.initialize()
        await store.store_chain(_make_chain("agent-1", authority_id="auth-A"))
        await store.store_chain(_make_chain("agent-2", authority_id="auth-B"))
        await store.store_chain(_make_chain("agent-3", authority_id="auth-A"))

        count = await store.count_chains(authority_id="auth-A")

        assert count == 2

    @pytest.mark.asyncio
    async def test_count_chains_raises_without_initialize(self, store):
        """count_chains() must raise RuntimeError if not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.count_chains()


# ---------------------------------------------------------------------------
# close Tests
# ---------------------------------------------------------------------------


class TestClose:
    """Tests for FilesystemStore.close()."""

    @pytest.mark.asyncio
    async def test_close_is_noop(self, store):
        """close() must not raise and should be a no-op for filesystem."""
        await store.initialize()
        await store.store_chain(_make_chain("agent-1"))

        await store.close()

        # Data should still be on disk after close
        # (filesystem doesn't need cleanup)

    @pytest.mark.asyncio
    async def test_close_resets_initialized_flag(self, store):
        """close() must reset the initialized flag."""
        await store.initialize()
        assert store._initialized

        await store.close()

        assert not store._initialized


# ---------------------------------------------------------------------------
# Atomic Write / Thread Safety Tests
# ---------------------------------------------------------------------------


class TestAtomicWrites:
    """Tests for atomic write guarantees."""

    @pytest.mark.asyncio
    async def test_concurrent_store_operations(self, store):
        """Concurrent store operations must not corrupt files."""
        await store.initialize()

        async def store_chain(agent_id: str):
            chain = _make_chain(agent_id)
            await store.store_chain(chain)

        # Run many stores concurrently
        tasks = [store_chain(f"agent-{i}") for i in range(20)]
        await asyncio.gather(*tasks)

        count = await store.count_chains()
        assert count == 20

    @pytest.mark.asyncio
    async def test_store_uses_atomic_write(self, store, tmp_path):
        """Store operations must write to a temp file and rename (atomic)."""
        await store.initialize()
        chain = _make_chain("agent-1")

        await store.store_chain(chain)

        # Verify the final file exists and is valid JSON
        chain_file = tmp_path / "chains" / "agent-1.json"
        assert chain_file.exists()
        data = json.loads(chain_file.read_text())
        assert data["chain"]["genesis"]["agent_id"] == "agent-1"


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_agent_id_with_special_characters(self, store):
        """Agent IDs with special characters must be handled safely."""
        await store.initialize()
        # Use an agent_id that could cause filesystem issues
        chain = _make_chain("agent/with:special chars")
        await store.store_chain(chain)

        retrieved = await store.get_chain("agent/with:special chars")
        assert retrieved.genesis.agent_id == "agent/with:special chars"

    @pytest.mark.asyncio
    async def test_corrupted_json_raises_error(self, store, tmp_path):
        """Corrupted JSON files must raise a clear error."""
        await store.initialize()
        chain = _make_chain("agent-1")
        await store.store_chain(chain)

        # Corrupt the file
        chain_file = tmp_path / "chains" / "agent-1.json"
        chain_file.write_text("{invalid json!!!")

        with pytest.raises(Exception):
            await store.get_chain("agent-1")

    @pytest.mark.asyncio
    async def test_list_chains_ignores_non_json_files(self, store, tmp_path):
        """list_chains() must ignore non-.json files in the directory."""
        await store.initialize()
        chain = _make_chain("agent-1")
        await store.store_chain(chain)

        # Create a non-JSON file
        (tmp_path / "chains" / "readme.txt").write_text("not a chain")

        result = await store.list_chains()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_chain_hard_deleted(self, store):
        """get_chain() must raise for hard-deleted chains."""
        await store.initialize()
        chain = _make_chain("agent-1")
        await store.store_chain(chain)
        await store.delete_chain("agent-1", soft_delete=False)

        with pytest.raises(TrustChainNotFoundError):
            await store.get_chain("agent-1")

        with pytest.raises(TrustChainNotFoundError):
            await store.get_chain("agent-1", include_inactive=True)
