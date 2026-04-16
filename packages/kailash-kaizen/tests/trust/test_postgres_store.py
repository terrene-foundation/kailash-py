"""
Tests for PostgresTrustStore implementation.

Demonstrates usage patterns for:
1. Storing trust chains with caching
2. Retrieving chains with <10ms performance
3. Filtering and pagination
4. Soft delete functionality
5. Integrity verification
"""

import os
from datetime import datetime, timedelta, timezone
from typing import List

import pytest
import pytest_asyncio
from kailash.trust.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    Constraint,
    ConstraintEnvelope,
    ConstraintType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
)
from kailash.trust.exceptions import (
    TrustChainInvalidError,
    TrustChainNotFoundError,
    TrustStoreDatabaseError,
)

from kaizen.trust.store import PostgresTrustStore


def _postgres_available() -> bool:
    """Check if PostgreSQL is available for testing."""
    url = os.getenv("POSTGRES_URL")
    if not url:
        return False
    try:
        import asyncio

        import asyncpg

        async def _check():
            conn = await asyncpg.connect(url)
            await conn.close()
            return True

        return asyncio.get_event_loop().run_until_complete(_check())
    except Exception:
        return False


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not _postgres_available(),
        reason="PostgreSQL not available (set POSTGRES_URL env var)",
    ),
]

# Fixtures


@pytest_asyncio.fixture
async def trust_store():
    """Create a PostgresTrustStore instance with caching enabled."""
    store = PostgresTrustStore(
        database_url=os.getenv("POSTGRES_URL"),
        enable_cache=True,
        cache_ttl_seconds=300,
    )
    await store.initialize()
    yield store
    await store.close()


@pytest.fixture
def sample_genesis_record() -> GenesisRecord:
    """Create a sample genesis record for testing."""
    return GenesisRecord(
        id="genesis-001",
        agent_id="agent-001",
        authority_id="org-acme",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        signature="mock-signature-genesis",
        signature_algorithm="Ed25519",
        metadata={"department": "engineering", "owner": "alice@acme.com"},
    )


@pytest.fixture
def sample_capability() -> CapabilityAttestation:
    """Create a sample capability attestation for testing."""
    return CapabilityAttestation(
        id="cap-001",
        capability="read:user_data",
        capability_type=CapabilityType.ACCESS,
        constraints=["department:engineering"],
        attester_id="org-acme",
        attested_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=90),
        signature="mock-signature-cap",
        scope={"resource_types": ["user", "profile"]},
    )


@pytest.fixture
def sample_trust_chain(
    sample_genesis_record: GenesisRecord,
    sample_capability: CapabilityAttestation,
) -> TrustLineageChain:
    """Create a complete sample trust chain for testing."""
    # Create constraint envelope
    constraint_envelope = ConstraintEnvelope(
        id="env-agent-001",
        agent_id="agent-001",
        active_constraints=[
            Constraint(
                id="const-001",
                constraint_type=ConstraintType.OPERATIONAL,
                value={"max_api_calls": 1000},
                source="org-acme",
                priority=1,
            )
        ],
    )

    return TrustLineageChain(
        genesis=sample_genesis_record,
        capabilities=[sample_capability],
        delegations=[],
        constraint_envelope=constraint_envelope,
        audit_anchors=[],
    )


# Test Cases


@pytest.mark.asyncio
async def test_store_and_retrieve_chain(
    trust_store: PostgresTrustStore,
    sample_trust_chain: TrustLineageChain,
):
    """Test basic store and retrieve operations."""
    # Store chain
    agent_id = await trust_store.store_chain(sample_trust_chain)
    assert agent_id == "agent-001"

    # Retrieve chain
    retrieved_chain = await trust_store.get_chain("agent-001")

    # Verify chain data
    assert retrieved_chain.genesis.agent_id == "agent-001"
    assert retrieved_chain.genesis.authority_id == "org-acme"
    assert len(retrieved_chain.capabilities) == 1
    assert retrieved_chain.capabilities[0].capability == "read:user_data"


@pytest.mark.asyncio
async def test_upsert_behavior(
    trust_store: PostgresTrustStore,
    sample_trust_chain: TrustLineageChain,
    sample_capability: CapabilityAttestation,
):
    """Test that store_chain performs upsert (insert or update)."""
    # First store
    await trust_store.store_chain(sample_trust_chain)

    # Modify chain and store again
    sample_trust_chain.capabilities.append(
        CapabilityAttestation(
            id="cap-002",
            capability="write:user_data",
            capability_type=CapabilityType.ACTION,
            constraints=["department:engineering"],
            attester_id="org-acme",
            attested_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=90),
            signature="mock-signature-cap-2",
        )
    )

    # Store again (should update)
    await trust_store.store_chain(sample_trust_chain)

    # Retrieve and verify update
    retrieved_chain = await trust_store.get_chain("agent-001")
    assert len(retrieved_chain.capabilities) == 2


@pytest.mark.asyncio
async def test_cache_performance(
    trust_store: PostgresTrustStore,
    sample_trust_chain: TrustLineageChain,
):
    """Test that caching provides <10ms retrieval performance."""
    import time

    # Store chain
    await trust_store.store_chain(sample_trust_chain)

    # First retrieval (cache miss)
    start = time.perf_counter()
    await trust_store.get_chain("agent-001")
    first_time = (time.perf_counter() - start) * 1000  # Convert to ms

    # Second retrieval (cache hit)
    start = time.perf_counter()
    await trust_store.get_chain("agent-001")
    cached_time = (time.perf_counter() - start) * 1000  # Convert to ms

    print(f"First retrieval: {first_time:.2f}ms")
    print(f"Cached retrieval: {cached_time:.2f}ms")

    # Cached retrieval should be significantly faster
    assert cached_time < first_time
    # Target: cached retrieval < 10ms
    assert cached_time < 10.0


@pytest.mark.asyncio
async def test_get_chain_not_found(trust_store: PostgresTrustStore):
    """Test that get_chain raises TrustChainNotFoundError for missing chains."""
    with pytest.raises(TrustChainNotFoundError) as exc_info:
        await trust_store.get_chain("nonexistent-agent")

    assert "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_update_chain(
    trust_store: PostgresTrustStore,
    sample_trust_chain: TrustLineageChain,
):
    """Test updating an existing trust chain."""
    # Store initial chain
    await trust_store.store_chain(sample_trust_chain)

    # Modify chain
    sample_trust_chain.capabilities.append(
        CapabilityAttestation(
            id="cap-003",
            capability="delete:user_data",
            capability_type=CapabilityType.ACTION,
            constraints=["department:engineering", "role:admin"],
            attester_id="org-acme",
            attested_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=90),
            signature="mock-signature-cap-3",
        )
    )

    # Update chain
    await trust_store.update_chain("agent-001", sample_trust_chain)

    # Retrieve and verify
    retrieved_chain = await trust_store.get_chain("agent-001")
    assert len(retrieved_chain.capabilities) >= 2


@pytest.mark.asyncio
async def test_soft_delete(
    trust_store: PostgresTrustStore,
    sample_trust_chain: TrustLineageChain,
):
    """Test soft delete functionality."""
    # Store chain
    await trust_store.store_chain(sample_trust_chain)

    # Soft delete
    await trust_store.delete_chain("agent-001", soft_delete=True)

    # Should not be found by default
    with pytest.raises(TrustChainNotFoundError):
        await trust_store.get_chain("agent-001")

    # But can be retrieved with include_inactive=True
    inactive_chain = await trust_store.get_chain("agent-001", include_inactive=True)
    assert inactive_chain.genesis.agent_id == "agent-001"


@pytest.mark.asyncio
async def test_hard_delete(
    trust_store: PostgresTrustStore,
    sample_trust_chain: TrustLineageChain,
):
    """Test hard delete functionality."""
    # Store chain
    await trust_store.store_chain(sample_trust_chain)

    # Hard delete
    await trust_store.delete_chain("agent-001", soft_delete=False)

    # Should not be found even with include_inactive=True
    with pytest.raises(TrustChainNotFoundError):
        await trust_store.get_chain("agent-001", include_inactive=True)


@pytest.mark.asyncio
async def test_list_chains_no_filter(
    trust_store: PostgresTrustStore,
    sample_genesis_record: GenesisRecord,
    sample_capability: CapabilityAttestation,
):
    """Test listing all chains without filtering."""
    # Create and store multiple chains
    for i in range(5):
        genesis = GenesisRecord(
            id=f"genesis-{i}",
            agent_id=f"agent-{i}",
            authority_id="org-acme",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            signature=f"mock-signature-{i}",
        )

        chain = TrustLineageChain(genesis=genesis, capabilities=[sample_capability])
        await trust_store.store_chain(chain)

    # List all chains
    chains = await trust_store.list_chains()

    assert len(chains) >= 5
    agent_ids = [chain.genesis.agent_id for chain in chains]
    for i in range(5):
        assert f"agent-{i}" in agent_ids


@pytest.mark.asyncio
async def test_list_chains_with_authority_filter(
    trust_store: PostgresTrustStore,
    sample_capability: CapabilityAttestation,
):
    """Test filtering chains by authority_id."""
    # Create chains with different authorities
    for authority in ["org-acme", "org-beta", "org-gamma"]:
        for i in range(3):
            genesis = GenesisRecord(
                id=f"genesis-{authority}-{i}",
                agent_id=f"agent-{authority}-{i}",
                authority_id=authority,
                authority_type=AuthorityType.ORGANIZATION,
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=365),
                signature=f"mock-signature-{authority}-{i}",
            )

            chain = TrustLineageChain(genesis=genesis, capabilities=[sample_capability])
            await trust_store.store_chain(chain)

    # Filter by authority
    acme_chains = await trust_store.list_chains(authority_id="org-acme")

    assert len(acme_chains) >= 3
    for chain in acme_chains:
        assert chain.genesis.authority_id == "org-acme"


@pytest.mark.asyncio
async def test_list_chains_pagination(
    trust_store: PostgresTrustStore,
    sample_capability: CapabilityAttestation,
):
    """Test pagination in list_chains."""
    # Create 15 chains
    for i in range(15):
        genesis = GenesisRecord(
            id=f"genesis-page-{i}",
            agent_id=f"agent-page-{i}",
            authority_id="org-acme",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            signature=f"mock-signature-page-{i}",
        )

        chain = TrustLineageChain(genesis=genesis, capabilities=[sample_capability])
        await trust_store.store_chain(chain)

    # Get first page
    page1 = await trust_store.list_chains(limit=5, offset=0)
    assert len(page1) == 5

    # Get second page
    page2 = await trust_store.list_chains(limit=5, offset=5)
    assert len(page2) == 5

    # Verify different results
    page1_ids = {chain.genesis.agent_id for chain in page1}
    page2_ids = {chain.genesis.agent_id for chain in page2}
    assert len(page1_ids.intersection(page2_ids)) == 0


@pytest.mark.asyncio
async def test_count_chains(
    trust_store: PostgresTrustStore,
    sample_capability: CapabilityAttestation,
):
    """Test counting chains with filtering."""
    # Create chains with different authorities
    for authority in ["org-acme", "org-beta"]:
        for i in range(5):
            genesis = GenesisRecord(
                id=f"genesis-count-{authority}-{i}",
                agent_id=f"agent-count-{authority}-{i}",
                authority_id=authority,
                authority_type=AuthorityType.ORGANIZATION,
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=365),
                signature=f"mock-signature-count-{authority}-{i}",
            )

            chain = TrustLineageChain(genesis=genesis, capabilities=[sample_capability])
            await trust_store.store_chain(chain)

    # Count all chains
    total_count = await trust_store.count_chains(active_only=True)
    assert total_count >= 10

    # Count filtered by authority
    acme_count = await trust_store.count_chains(
        authority_id="org-acme", active_only=True
    )
    assert acme_count >= 5


@pytest.mark.asyncio
async def test_verify_chain_integrity(
    trust_store: PostgresTrustStore,
    sample_trust_chain: TrustLineageChain,
):
    """Test chain integrity verification."""
    # Store chain
    await trust_store.store_chain(sample_trust_chain)

    # Verify integrity
    is_valid = await trust_store.verify_chain_integrity("agent-001")
    assert is_valid is True


@pytest.mark.asyncio
async def test_store_expired_chain_fails(
    trust_store: PostgresTrustStore,
    sample_genesis_record: GenesisRecord,
):
    """Test that storing an expired chain raises TrustChainInvalidError."""
    # Create expired genesis record
    expired_genesis = GenesisRecord(
        id="genesis-expired",
        agent_id="agent-expired",
        authority_id="org-acme",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime.now(timezone.utc) - timedelta(days=100),
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),  # Expired
        signature="mock-signature-expired",
    )

    expired_chain = TrustLineageChain(genesis=expired_genesis)

    # Should raise TrustChainInvalidError
    with pytest.raises(TrustChainInvalidError) as exc_info:
        await trust_store.store_chain(expired_chain)

    assert "expired" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_list_active_only(
    trust_store: PostgresTrustStore,
    sample_capability: CapabilityAttestation,
):
    """Test that active_only filter excludes soft-deleted chains."""
    # Create and store chains
    for i in range(5):
        genesis = GenesisRecord(
            id=f"genesis-active-{i}",
            agent_id=f"agent-active-{i}",
            authority_id="org-acme",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            signature=f"mock-signature-active-{i}",
        )

        chain = TrustLineageChain(genesis=genesis, capabilities=[sample_capability])
        await trust_store.store_chain(chain)

    # Soft delete some chains
    await trust_store.delete_chain("agent-active-0", soft_delete=True)
    await trust_store.delete_chain("agent-active-1", soft_delete=True)

    # List with active_only=True (default)
    active_chains = await trust_store.list_chains(active_only=True)
    active_ids = {chain.genesis.agent_id for chain in active_chains}

    assert "agent-active-0" not in active_ids
    assert "agent-active-1" not in active_ids
    assert "agent-active-2" in active_ids

    # List with active_only=False
    all_chains = await trust_store.list_chains(active_only=False)
    all_ids = {chain.genesis.agent_id for chain in all_chains}

    assert "agent-active-0" in all_ids
    assert "agent-active-1" in all_ids
