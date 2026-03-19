"""
Unit tests for SqliteTrustStore implementation.

Tests the SQLite-based TrustStore with:
- Database initialization and WAL mode
- CRUD operations for trust chains
- Soft-delete and hard-delete behavior
- Filtering by authority_id and active_only
- Pagination (limit/offset)
- Concurrent access (two store instances on same DB)
- Close and reopen (data persists)
- get_chains_missing_reasoning() compliance query
- Update chain preserves stored_at, updates updated_at
- Round-trip serialization fidelity
"""

import asyncio
import os
import sqlite3

from datetime import datetime, timezone
import pytest

from eatp.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
)
from eatp.exceptions import TrustChainNotFoundError
from eatp.store.sqlite import SqliteTrustStore


# ---------------------------------------------------------------------------
# Helpers
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
    reasoning_trace=None,
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
            reasoning_trace=reasoning_trace,
        )
    )
    return chain


@pytest.fixture
def db_path(tmp_path):
    """Return a temporary database file path."""
    return str(tmp_path / "trust.db")


@pytest.fixture
def store(db_path):
    """Create a SqliteTrustStore with a temp database."""
    return SqliteTrustStore(db_path=db_path)


# ---------------------------------------------------------------------------
# Initialization Tests
# ---------------------------------------------------------------------------


class TestInitialize:
    """Tests for SqliteTrustStore.initialize()."""

    async def test_initialize_creates_database_file(self, store, db_path):
        """initialize() must create the SQLite database file."""
        assert not os.path.exists(db_path)

        await store.initialize()

        assert os.path.exists(db_path)

    async def test_initialize_creates_trust_chains_table(self, store, db_path):
        """initialize() must create the trust_chains table."""
        await store.initialize()

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trust_chains'")
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "trust_chains"

    async def test_initialize_sets_wal_mode(self, store, db_path):
        """initialize() must set journal_mode to WAL."""
        await store.initialize()

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        conn.close()

        assert mode.lower() == "wal"

    async def test_initialize_idempotent(self, store):
        """Calling initialize() multiple times must not raise."""
        await store.initialize()
        await store.initialize()

    async def test_initialize_creates_parent_directories(self, tmp_path):
        """initialize() must create parent directories if they do not exist."""
        nested = tmp_path / "deep" / "nested" / "dir" / "trust.db"
        store = SqliteTrustStore(db_path=str(nested))

        await store.initialize()

        assert nested.exists()

    async def test_default_db_path(self):
        """Default db_path should resolve to ~/.eatp/trust.db."""
        store = SqliteTrustStore()
        expected = os.path.join(os.path.expanduser("~"), ".eatp", "trust.db")
        assert store._db_path == expected


# ---------------------------------------------------------------------------
# store_chain Tests
# ---------------------------------------------------------------------------


class TestStoreChain:
    """Tests for SqliteTrustStore.store_chain()."""

    async def test_store_and_get_round_trip(self, store):
        """store_chain() followed by get_chain() must return the same data."""
        await store.initialize()
        chain = _make_chain("agent-1")

        agent_id = await store.store_chain(chain)

        assert agent_id == "agent-1"
        retrieved = await store.get_chain("agent-1")
        assert retrieved.genesis.agent_id == "agent-1"
        assert retrieved.genesis.authority_id == "auth-1"

    async def test_store_chain_returns_agent_id(self, store):
        """store_chain() must return the agent_id from the chain."""
        await store.initialize()
        chain = _make_chain("agent-42")

        result = await store.store_chain(chain)

        assert result == "agent-42"

    async def test_store_chain_with_expires_at(self, store, db_path):
        """store_chain() must persist the expires_at timestamp."""
        await store.initialize()
        chain = _make_chain("agent-1")
        expiry = datetime(2030, 12, 31, tzinfo=timezone.utc)

        await store.store_chain(chain, expires_at=expiry)

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT expires_at FROM trust_chains WHERE agent_id = 'agent-1'")
        row = cursor.fetchone()
        conn.close()
        assert row[0] == expiry.isoformat()

    async def test_store_chain_overwrites_existing(self, store):
        """Storing a chain with an existing agent_id must overwrite."""
        await store.initialize()
        chain1 = _make_chain_with_capability("agent-1", capability="read_data")
        chain2 = _make_chain_with_capability("agent-1", capability="write_data")

        await store.store_chain(chain1)
        await store.store_chain(chain2)

        retrieved = await store.get_chain("agent-1")
        assert retrieved.capabilities[0].capability == "write_data"

    async def test_store_chain_preserves_genesis_signature(self, store):
        """Stored data must preserve the genesis record signature."""
        await store.initialize()
        chain = _make_chain("agent-1")

        await store.store_chain(chain)

        retrieved = await store.get_chain("agent-1")
        assert retrieved.genesis.signature == "sig-test-genesis"

    async def test_store_chain_with_capabilities(self, store):
        """store_chain() must preserve capability attestations."""
        await store.initialize()
        chain = _make_chain_with_capability("agent-1")

        await store.store_chain(chain)
        retrieved = await store.get_chain("agent-1")

        assert len(retrieved.capabilities) == 1
        assert retrieved.capabilities[0].capability == "read_data"
        assert retrieved.capabilities[0].signature == "sig-test-cap"

    async def test_store_chain_with_delegations(self, store):
        """store_chain() must preserve delegation records."""
        await store.initialize()
        chain = _make_chain_with_delegation("agent-1")

        await store.store_chain(chain)
        retrieved = await store.get_chain("agent-1")

        assert len(retrieved.delegations) == 1
        assert retrieved.delegations[0].delegator_id == "agent-0"
        assert retrieved.delegations[0].signature == "sig-test-del"

    async def test_store_chain_raises_without_initialize(self, store):
        """store_chain() must raise RuntimeError if not initialized."""
        chain = _make_chain("agent-1")
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.store_chain(chain)


# ---------------------------------------------------------------------------
# get_chain Tests
# ---------------------------------------------------------------------------


class TestGetChain:
    """Tests for SqliteTrustStore.get_chain()."""

    async def test_get_chain_raises_for_missing(self, store):
        """get_chain() must raise TrustChainNotFoundError for missing chains."""
        await store.initialize()

        with pytest.raises(TrustChainNotFoundError):
            await store.get_chain("nonexistent-agent")

    async def test_get_chain_excludes_inactive_by_default(self, store):
        """get_chain() must exclude soft-deleted chains by default."""
        await store.initialize()
        chain = _make_chain("agent-1")
        await store.store_chain(chain)
        await store.delete_chain("agent-1", soft_delete=True)

        with pytest.raises(TrustChainNotFoundError):
            await store.get_chain("agent-1")

    async def test_get_chain_includes_inactive_when_requested(self, store):
        """get_chain(include_inactive=True) must return soft-deleted chains."""
        await store.initialize()
        chain = _make_chain("agent-1")
        await store.store_chain(chain)
        await store.delete_chain("agent-1", soft_delete=True)

        retrieved = await store.get_chain("agent-1", include_inactive=True)

        assert retrieved.genesis.agent_id == "agent-1"

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

    async def test_get_chain_raises_without_initialize(self, store):
        """get_chain() must raise RuntimeError if not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.get_chain("agent-1")


# ---------------------------------------------------------------------------
# update_chain Tests
# ---------------------------------------------------------------------------


class TestUpdateChain:
    """Tests for SqliteTrustStore.update_chain()."""

    async def test_update_chain_replaces_data(self, store):
        """update_chain() must replace the chain data."""
        await store.initialize()
        chain1 = _make_chain("agent-1", authority_id="auth-1")
        await store.store_chain(chain1)

        chain2 = _make_chain_with_capability("agent-1", authority_id="auth-1")
        await store.update_chain("agent-1", chain2)

        retrieved = await store.get_chain("agent-1")
        assert len(retrieved.capabilities) == 1

    async def test_update_chain_raises_for_missing(self, store):
        """update_chain() must raise TrustChainNotFoundError for missing chains."""
        await store.initialize()

        chain = _make_chain("nonexistent")
        with pytest.raises(TrustChainNotFoundError):
            await store.update_chain("nonexistent", chain)

    async def test_update_chain_preserves_stored_at_updates_updated_at(self, store, db_path):
        """update_chain() must preserve created_at and set updated_at."""
        await store.initialize()
        chain = _make_chain("agent-1")
        await store.store_chain(chain)

        # Read original timestamps
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT created_at, updated_at FROM trust_chains WHERE agent_id = 'agent-1'")
        row = cursor.fetchone()
        conn.close()
        original_created_at = row[0]
        original_updated_at = row[1]

        # Small delay to ensure timestamp difference
        await asyncio.sleep(0.01)

        updated_chain = _make_chain_with_capability("agent-1")
        await store.update_chain("agent-1", updated_chain)

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT created_at, updated_at FROM trust_chains WHERE agent_id = 'agent-1'")
        row = cursor.fetchone()
        conn.close()

        assert row[0] == original_created_at, "created_at must be preserved"
        assert row[1] != original_updated_at, "updated_at must be changed"

    async def test_update_chain_raises_without_initialize(self, store):
        """update_chain() must raise RuntimeError if not initialized."""
        chain = _make_chain("agent-1")
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.update_chain("agent-1", chain)


# ---------------------------------------------------------------------------
# delete_chain Tests
# ---------------------------------------------------------------------------


class TestDeleteChain:
    """Tests for SqliteTrustStore.delete_chain()."""

    async def test_soft_delete_marks_inactive(self, store, db_path):
        """Soft delete must mark the chain as inactive, not remove the row."""
        await store.initialize()
        chain = _make_chain("agent-1")
        await store.store_chain(chain)

        await store.delete_chain("agent-1", soft_delete=True)

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT active, deleted_at FROM trust_chains WHERE agent_id = 'agent-1'")
        row = cursor.fetchone()
        conn.close()

        assert row is not None, "Row must still exist after soft delete"
        assert row[0] == 0, "active must be 0 after soft delete"
        assert row[1] is not None, "deleted_at must be set after soft delete"

    async def test_hard_delete_removes_row(self, store, db_path):
        """Hard delete must remove the row from the database."""
        await store.initialize()
        chain = _make_chain("agent-1")
        await store.store_chain(chain)

        await store.delete_chain("agent-1", soft_delete=False)

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM trust_chains WHERE agent_id = 'agent-1'")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 0, "Row must be removed after hard delete"

    async def test_delete_raises_for_missing(self, store):
        """delete_chain() must raise TrustChainNotFoundError for missing chains."""
        await store.initialize()

        with pytest.raises(TrustChainNotFoundError):
            await store.delete_chain("nonexistent")

    async def test_hard_delete_after_soft_delete(self, store, db_path):
        """Hard delete of a soft-deleted chain must remove the row."""
        await store.initialize()
        chain = _make_chain("agent-1")
        await store.store_chain(chain)

        await store.delete_chain("agent-1", soft_delete=True)
        await store.delete_chain("agent-1", soft_delete=False)

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM trust_chains WHERE agent_id = 'agent-1'")
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 0

    async def test_get_chain_after_hard_delete_raises(self, store):
        """get_chain() must raise after hard delete, even with include_inactive."""
        await store.initialize()
        chain = _make_chain("agent-1")
        await store.store_chain(chain)
        await store.delete_chain("agent-1", soft_delete=False)

        with pytest.raises(TrustChainNotFoundError):
            await store.get_chain("agent-1")

        with pytest.raises(TrustChainNotFoundError):
            await store.get_chain("agent-1", include_inactive=True)

    async def test_delete_chain_raises_without_initialize(self, store):
        """delete_chain() must raise RuntimeError if not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.delete_chain("agent-1")


# ---------------------------------------------------------------------------
# list_chains Tests
# ---------------------------------------------------------------------------


class TestListChains:
    """Tests for SqliteTrustStore.list_chains()."""

    async def test_list_chains_empty(self, store):
        """list_chains() on empty store must return empty list."""
        await store.initialize()

        result = await store.list_chains()

        assert result == []

    async def test_list_chains_returns_all_active(self, store):
        """list_chains() must return all active chains."""
        await store.initialize()
        for i in range(3):
            await store.store_chain(_make_chain(f"agent-{i}"))

        result = await store.list_chains()

        assert len(result) == 3
        agent_ids = {c.genesis.agent_id for c in result}
        assert agent_ids == {"agent-0", "agent-1", "agent-2"}

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

    async def test_list_chains_includes_inactive(self, store):
        """list_chains(active_only=False) must include soft-deleted chains."""
        await store.initialize()
        for i in range(3):
            await store.store_chain(_make_chain(f"agent-{i}"))
        await store.delete_chain("agent-1", soft_delete=True)

        result = await store.list_chains(active_only=False)

        assert len(result) == 3

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

    async def test_list_chains_pagination_limit(self, store):
        """list_chains(limit=N) must return at most N results."""
        await store.initialize()
        for i in range(5):
            await store.store_chain(_make_chain(f"agent-{i}"))

        result = await store.list_chains(limit=2)

        assert len(result) == 2

    async def test_list_chains_pagination_offset(self, store):
        """list_chains(offset=N) must skip the first N results."""
        await store.initialize()
        for i in range(5):
            await store.store_chain(_make_chain(f"agent-{i}"))

        await store.list_chains(limit=100)
        offset_chains = await store.list_chains(offset=2, limit=100)

        assert len(offset_chains) == 3

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

    async def test_list_chains_raises_without_initialize(self, store):
        """list_chains() must raise RuntimeError if not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.list_chains()


# ---------------------------------------------------------------------------
# count_chains Tests
# ---------------------------------------------------------------------------


class TestCountChains:
    """Tests for SqliteTrustStore.count_chains()."""

    async def test_count_chains_empty(self, store):
        """count_chains() on empty store must return 0."""
        await store.initialize()

        count = await store.count_chains()

        assert count == 0

    async def test_count_chains_all_active(self, store):
        """count_chains() must count active chains."""
        await store.initialize()
        for i in range(3):
            await store.store_chain(_make_chain(f"agent-{i}"))

        count = await store.count_chains()

        assert count == 3

    async def test_count_chains_excludes_inactive(self, store):
        """count_chains(active_only=True) must exclude soft-deleted chains."""
        await store.initialize()
        for i in range(3):
            await store.store_chain(_make_chain(f"agent-{i}"))
        await store.delete_chain("agent-1", soft_delete=True)

        count = await store.count_chains(active_only=True)

        assert count == 2

    async def test_count_chains_includes_inactive(self, store):
        """count_chains(active_only=False) must include soft-deleted chains."""
        await store.initialize()
        for i in range(3):
            await store.store_chain(_make_chain(f"agent-{i}"))
        await store.delete_chain("agent-1", soft_delete=True)

        count = await store.count_chains(active_only=False)

        assert count == 3

    async def test_count_chains_filter_by_authority(self, store):
        """count_chains(authority_id=...) must filter by authority."""
        await store.initialize()
        await store.store_chain(_make_chain("agent-1", authority_id="auth-A"))
        await store.store_chain(_make_chain("agent-2", authority_id="auth-B"))
        await store.store_chain(_make_chain("agent-3", authority_id="auth-A"))

        count = await store.count_chains(authority_id="auth-A")

        assert count == 2

    async def test_count_chains_raises_without_initialize(self, store):
        """count_chains() must raise RuntimeError if not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.count_chains()


# ---------------------------------------------------------------------------
# close Tests
# ---------------------------------------------------------------------------


class TestClose:
    """Tests for SqliteTrustStore.close()."""

    async def test_close_does_not_raise(self, store):
        """close() must not raise."""
        await store.initialize()
        await store.store_chain(_make_chain("agent-1"))

        await store.close()

    async def test_close_and_reopen_persists_data(self, db_path):
        """Data must persist after close and reopen."""
        store1 = SqliteTrustStore(db_path=db_path)
        await store1.initialize()
        await store1.store_chain(_make_chain("agent-1"))
        await store1.close()

        store2 = SqliteTrustStore(db_path=db_path)
        await store2.initialize()
        retrieved = await store2.get_chain("agent-1")

        assert retrieved.genesis.agent_id == "agent-1"
        assert retrieved.genesis.authority_id == "auth-1"
        await store2.close()


# ---------------------------------------------------------------------------
# Concurrent Access Tests
# ---------------------------------------------------------------------------


class TestConcurrentAccess:
    """Tests for concurrent access to the same database."""

    async def test_two_store_instances_same_db(self, db_path):
        """Two SqliteTrustStore instances on the same DB must work."""
        store1 = SqliteTrustStore(db_path=db_path)
        store2 = SqliteTrustStore(db_path=db_path)

        await store1.initialize()
        await store2.initialize()

        await store1.store_chain(_make_chain("agent-1"))
        retrieved = await store2.get_chain("agent-1")
        assert retrieved.genesis.agent_id == "agent-1"

        await store1.close()
        await store2.close()

    async def test_concurrent_store_operations(self, db_path):
        """Concurrent store operations must not corrupt the database."""
        store = SqliteTrustStore(db_path=db_path)
        await store.initialize()

        async def store_chain(agent_id: str):
            chain = _make_chain(agent_id)
            await store.store_chain(chain)

        tasks = [store_chain(f"agent-{i}") for i in range(20)]
        await asyncio.gather(*tasks)

        count = await store.count_chains()
        assert count == 20
        await store.close()


# ---------------------------------------------------------------------------
# get_chains_missing_reasoning Tests
# ---------------------------------------------------------------------------


class TestGetChainsMissingReasoning:
    """Tests for SqliteTrustStore.get_chains_missing_reasoning()."""

    async def test_missing_reasoning_returns_agents_without_traces(self, store):
        """Chains with delegations lacking reasoning_trace must be returned."""
        await store.initialize()

        # Chain with delegation but no reasoning trace
        chain_no_reason = _make_chain_with_delegation("agent-missing", reasoning_trace=None)
        await store.store_chain(chain_no_reason)

        # Chain without delegations (should NOT be included)
        chain_no_deleg = _make_chain("agent-clean")
        await store.store_chain(chain_no_deleg)

        result = await store.get_chains_missing_reasoning()

        assert "agent-missing" in result
        assert "agent-clean" not in result

    async def test_missing_reasoning_empty_store(self, store):
        """Empty store must return empty list for missing reasoning."""
        await store.initialize()

        result = await store.get_chains_missing_reasoning()

        assert result == []

    async def test_missing_reasoning_all_have_traces(self, store):
        """Chains where all delegations have reasoning must not be returned."""
        await store.initialize()

        # Import ReasoningTrace to create a chain WITH reasoning
        from eatp.reasoning import ConfidentialityLevel, ReasoningTrace

        trace = ReasoningTrace(
            decision="delegate task to agent-complete",
            rationale="agent has required capabilities",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            confidence=0.9,
        )

        chain = _make_chain_with_delegation("agent-complete", reasoning_trace=trace)
        await store.store_chain(chain)

        result = await store.get_chains_missing_reasoning()

        assert "agent-complete" not in result


# ---------------------------------------------------------------------------
# Schema Validation Tests
# ---------------------------------------------------------------------------


class TestSchema:
    """Tests for database schema correctness."""

    async def test_schema_has_expected_columns(self, store, db_path):
        """trust_chains table must have all required columns."""
        await store.initialize()

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("PRAGMA table_info(trust_chains)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        conn.close()

        assert "agent_id" in columns
        assert "chain_data" in columns
        assert "active" in columns
        assert "authority_id" in columns
        assert "created_at" in columns
        assert "updated_at" in columns
        assert "deleted_at" in columns
        assert "expires_at" in columns

    async def test_agent_id_is_primary_key(self, store, db_path):
        """agent_id must be the primary key."""
        await store.initialize()

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("PRAGMA table_info(trust_chains)")
        for row in cursor.fetchall():
            if row[1] == "agent_id":
                # pk column is the 6th element (index 5), non-zero means PK
                assert row[5] != 0, "agent_id must be a primary key"
                break
        else:
            pytest.fail("agent_id column not found")
        conn.close()
