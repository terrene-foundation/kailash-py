"""
Integration tests for EATP credential rotation.

Tests the CredentialRotationManager with real infrastructure (PostgreSQL, Redis).
Follows the NO MOCKING policy for Tier 2 integration tests.

NOTE: These tests require POSTGRES_URL environment variable to be set.
They will be skipped if PostgreSQL is not available.
"""

import os

# Check PostgreSQL availability using pg_isready
import subprocess

import pytest
import pytest_asyncio

POSTGRES_URL = os.getenv("POSTGRES_URL")


def _check_postgres_available():
    """Check if PostgreSQL is actually available (not just configured)."""
    if not POSTGRES_URL:
        return False, "POSTGRES_URL not set"

    try:
        # Parse connection info from URL
        import re

        match = re.match(r"postgresql://[^@]+@([^:]+):(\d+)/", POSTGRES_URL)
        if not match:
            return False, "Could not parse POSTGRES_URL"
        host, port = match.groups()

        # Try pg_isready
        result = subprocess.run(
            ["pg_isready", "-h", host, "-p", port], capture_output=True, timeout=5
        )
        if result.returncode != 0:
            return False, f"PostgreSQL not responding at {host}:{port}"
        return True, None
    except Exception as e:
        return False, str(e)


_pg_available, _pg_reason = _check_postgres_available()
if not _pg_available:
    pytest.skip(f"PostgreSQL not available: {_pg_reason}", allow_module_level=True)

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from kaizen.trust.authority import (
    AuthorityPermission,
    OrganizationalAuthority,
    OrganizationalAuthorityRegistry,
)
from kaizen.trust.chain import AuthorityType, CapabilityType
from kaizen.trust.crypto import generate_keypair
from kaizen.trust.exceptions import AuthorityNotFoundError
from kaizen.trust.operations import CapabilityRequest, TrustKeyManager, TrustOperations
from kaizen.trust.rotation import CredentialRotationManager
from kaizen.trust.rotation import RotationError
from kaizen.trust.rotation import RotationError as RotationErrorException
from kaizen.trust.rotation import RotationResult, RotationStatus, RotationStatusInfo
from kaizen.trust.store import PostgresTrustStore


@pytest.fixture
def database_url():
    """Get database URL from environment."""
    return os.getenv("POSTGRES_URL")


@pytest_asyncio.fixture
async def trust_store(database_url):
    """Create a PostgresTrustStore with test database."""
    store = PostgresTrustStore(
        database_url=database_url,
        enable_cache=True,
        cache_ttl_seconds=60,
    )
    await store.initialize()
    yield store
    await store.close()


@pytest_asyncio.fixture
async def authority_registry(database_url):
    """Create an OrganizationalAuthorityRegistry with test database."""
    registry = OrganizationalAuthorityRegistry(
        database_url=database_url,
        enable_cache=True,
        cache_ttl_seconds=60,
    )
    await registry.initialize()
    yield registry
    await registry.close()


@pytest.fixture
def key_manager():
    """Create a TrustKeyManager."""
    return TrustKeyManager()


@pytest_asyncio.fixture
async def rotation_manager(key_manager, trust_store, authority_registry):
    """Create a CredentialRotationManager with real infrastructure."""
    manager = CredentialRotationManager(
        key_manager=key_manager,
        trust_store=trust_store,
        authority_registry=authority_registry,
        rotation_period_days=90,
        grace_period_hours=24,
    )
    await manager.initialize()
    yield manager
    await manager.close()


@pytest_asyncio.fixture
async def test_authority(authority_registry, key_manager):
    """Create a test authority."""
    private_key, public_key = generate_keypair()
    authority_id = f"org-test-{uuid4().hex[:8]}"
    signing_key_id = f"key-{uuid4().hex[:8]}"

    # Register key
    key_manager.register_key(signing_key_id, private_key)

    # Create authority
    authority = OrganizationalAuthority(
        id=authority_id,
        name="Test Organization",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=public_key,
        signing_key_id=signing_key_id,
        permissions=[
            AuthorityPermission.CREATE_AGENTS,
            AuthorityPermission.GRANT_CAPABILITIES,
        ],
        is_active=True,
        metadata={},
    )

    await authority_registry.register_authority(authority)
    return authority


@pytest.mark.asyncio
class TestCredentialRotationIntegration:
    """
    Integration test suite for CredentialRotationManager.

    Requires POSTGRES_URL to be set - these tests use real PostgreSQL
    infrastructure per the NO MOCKING policy.
    """

    async def test_rotate_key_no_chains(
        self,
        rotation_manager,
        test_authority,
    ):
        """Test key rotation with no existing trust chains."""
        # Rotate key
        result = await rotation_manager.rotate_key(test_authority.id)

        # Verify result
        assert isinstance(result, RotationResult)
        assert result.old_key_id == test_authority.signing_key_id
        assert result.new_key_id != test_authority.signing_key_id
        assert result.chains_updated == 0
        assert result.grace_period_end is not None
        assert result.completed_at > result.started_at

        # Verify authority was updated in database
        updated_authority = await rotation_manager.authority_registry.get_authority(
            test_authority.id
        )
        assert updated_authority.signing_key_id == result.new_key_id
        assert updated_authority.signing_key_id != test_authority.signing_key_id
        assert "key_rotation_history" in updated_authority.metadata
        assert len(updated_authority.metadata["key_rotation_history"]) == 1

    async def test_rotate_key_with_chains(
        self,
        rotation_manager,
        test_authority,
        trust_store,
        key_manager,
    ):
        """Test key rotation with existing trust chains."""
        # Create trust operations
        trust_ops = TrustOperations(
            authority_registry=rotation_manager.authority_registry,
            key_manager=key_manager,
            trust_store=trust_store,
        )
        await trust_ops.initialize()

        # Establish trust for an agent
        agent_id = f"agent-test-{uuid4().hex[:8]}"
        chain = await trust_ops.establish(
            agent_id=agent_id,
            authority_id=test_authority.id,
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACCESS,
                    constraints=["read_only"],
                )
            ],
        )

        # Store original signature
        original_genesis_signature = chain.genesis.signature

        # Rotate key
        result = await rotation_manager.rotate_key(test_authority.id)

        # Verify chains were updated
        assert result.chains_updated == 1

        # Retrieve chain and verify signature was updated
        updated_chain = await trust_store.get_chain(agent_id)
        assert updated_chain.genesis.signature != original_genesis_signature

        # Verify chain is still valid
        verification_result = updated_chain.verify_basic()
        assert verification_result.valid is True

    async def test_rotate_key_multiple_chains(
        self,
        rotation_manager,
        test_authority,
        trust_store,
        key_manager,
    ):
        """Test key rotation with multiple trust chains."""
        # Create trust operations
        trust_ops = TrustOperations(
            authority_registry=rotation_manager.authority_registry,
            key_manager=key_manager,
            trust_store=trust_store,
        )
        await trust_ops.initialize()

        # Establish trust for multiple agents
        agent_ids = []
        for i in range(3):
            agent_id = f"agent-multi-{uuid4().hex[:8]}"
            agent_ids.append(agent_id)
            await trust_ops.establish(
                agent_id=agent_id,
                authority_id=test_authority.id,
                capabilities=[
                    CapabilityRequest(
                        capability=f"capability_{i}",
                        capability_type=CapabilityType.ACCESS,
                    )
                ],
            )

        # Rotate key
        result = await rotation_manager.rotate_key(test_authority.id)

        # Verify all chains were updated
        assert result.chains_updated == 3

        # Verify each chain
        for agent_id in agent_ids:
            chain = await trust_store.get_chain(agent_id)
            verification_result = chain.verify_basic()
            assert verification_result.valid is True

    async def test_rotate_key_concurrent_prevention(
        self,
        rotation_manager,
        test_authority,
    ):
        """Test that concurrent rotations are prevented."""
        # Start first rotation (simulate by adding to active set)
        rotation_manager._active_rotations.add(test_authority.id)

        # Try second rotation
        with pytest.raises(RotationErrorException) as exc_info:
            await rotation_manager.rotate_key(test_authority.id)

        assert "in progress" in str(exc_info.value).lower()

        # Cleanup
        rotation_manager._active_rotations.remove(test_authority.id)

    async def test_schedule_and_process_rotation(
        self,
        rotation_manager,
        test_authority,
    ):
        """Test scheduling and processing a rotation."""
        # Schedule rotation for 1 second in the future
        future_time = datetime.now(timezone.utc) + timedelta(seconds=1)
        rotation_id = await rotation_manager.schedule_rotation(
            test_authority.id,
            at=future_time,
        )

        assert rotation_id.startswith("rot-")

        # Wait for scheduled time
        import asyncio

        await asyncio.sleep(2)

        # Process scheduled rotations
        results = await rotation_manager.process_scheduled_rotations()

        # Verify rotation was performed
        assert len(results) == 1
        assert results[0].old_key_id == test_authority.signing_key_id

    async def test_get_rotation_status_full_lifecycle(
        self,
        rotation_manager,
        test_authority,
    ):
        """Test rotation status through full lifecycle."""
        # Initial status
        status = await rotation_manager.get_rotation_status(test_authority.id)
        assert status.current_key_id == test_authority.signing_key_id
        assert status.last_rotation is None
        assert status.next_scheduled is None
        assert status.status == RotationStatus.COMPLETED

        # Schedule rotation
        future_time = datetime.now(timezone.utc) + timedelta(days=90)
        await rotation_manager.schedule_rotation(test_authority.id, at=future_time)

        # Check status with scheduled rotation
        status = await rotation_manager.get_rotation_status(test_authority.id)
        assert status.next_scheduled == future_time

        # Perform rotation
        result = await rotation_manager.rotate_key(test_authority.id)

        # Check status after rotation
        status = await rotation_manager.get_rotation_status(test_authority.id)
        assert status.last_rotation == result.completed_at
        assert status.current_key_id == result.new_key_id
        assert status.status == RotationStatus.GRACE_PERIOD
        assert test_authority.signing_key_id in status.grace_period_keys

    async def test_revoke_old_key_after_grace_period(
        self,
        rotation_manager,
        test_authority,
    ):
        """Test revoking old key after grace period expires."""
        # Rotate key with short grace period (1 second for testing)
        result = await rotation_manager.rotate_key(
            test_authority.id,
            grace_period_hours=0,  # Immediate expiry for testing
        )

        old_key_id = result.old_key_id

        # Manually set grace period to expired
        import asyncio

        await asyncio.sleep(0.1)
        rotation_manager._grace_period_keys[test_authority.id][old_key_id] = (
            datetime.now(timezone.utc) - timedelta(hours=1)
        )

        # Revoke old key
        await rotation_manager.revoke_old_key(test_authority.id, old_key_id)

        # Verify key was removed from grace period
        assert old_key_id not in rotation_manager._grace_period_keys.get(
            test_authority.id, {}
        )

    async def test_revoke_old_key_grace_period_not_expired(
        self,
        rotation_manager,
        test_authority,
    ):
        """Test that revocation fails when grace period not expired."""
        # Rotate key
        result = await rotation_manager.rotate_key(test_authority.id)

        # Try to revoke key immediately
        with pytest.raises(RotationErrorException) as exc_info:
            await rotation_manager.revoke_old_key(test_authority.id, result.old_key_id)

        assert "not expired" in str(exc_info.value).lower()

    async def test_authority_not_found(
        self,
        rotation_manager,
    ):
        """Test rotation fails for non-existent authority."""
        with pytest.raises(RotationErrorException) as exc_info:
            await rotation_manager.rotate_key("org-nonexistent")

        # Should wrap AuthorityNotFoundError
        assert exc_info.value.__cause__ is not None

    async def test_rotation_metadata_persistence(
        self,
        rotation_manager,
        test_authority,
        authority_registry,
    ):
        """Test that rotation metadata persists in database."""
        # Perform multiple rotations
        result1 = await rotation_manager.rotate_key(test_authority.id)

        # Wait a bit
        import asyncio

        await asyncio.sleep(0.1)

        result2 = await rotation_manager.rotate_key(test_authority.id)

        # Retrieve authority from database
        authority = await authority_registry.get_authority(test_authority.id)

        # Verify rotation history
        assert "key_rotation_history" in authority.metadata
        history = authority.metadata["key_rotation_history"]
        assert len(history) == 2
        assert history[0]["rotation_id"] == result1.rotation_id
        assert history[1]["rotation_id"] == result2.rotation_id

    async def test_grace_period_tracking(
        self,
        rotation_manager,
        test_authority,
    ):
        """Test grace period tracking across multiple rotations."""
        # First rotation
        result1 = await rotation_manager.rotate_key(test_authority.id)

        # Verify first key in grace period
        status = await rotation_manager.get_rotation_status(test_authority.id)
        assert len(status.grace_period_keys) == 1
        assert result1.old_key_id in status.grace_period_keys

        # Second rotation (before first grace period expires)
        result2 = await rotation_manager.rotate_key(test_authority.id)

        # Verify both keys in grace period
        status = await rotation_manager.get_rotation_status(test_authority.id)
        assert len(status.grace_period_keys) == 2
        assert result1.old_key_id in status.grace_period_keys
        assert result2.old_key_id in status.grace_period_keys

    async def test_custom_grace_period(
        self,
        rotation_manager,
        test_authority,
    ):
        """Test rotation with custom grace period."""
        # Rotate with 48-hour grace period
        result = await rotation_manager.rotate_key(
            test_authority.id,
            grace_period_hours=48,
        )

        # Verify grace period end time
        expected_end = result.started_at + timedelta(hours=48)
        assert abs((result.grace_period_end - expected_end).total_seconds()) < 1

        # Verify in status
        status = await rotation_manager.get_rotation_status(test_authority.id)
        assert result.old_key_id in status.grace_period_keys
        grace_period_end = status.grace_period_keys[result.old_key_id]
        assert abs((grace_period_end - expected_end).total_seconds()) < 1
