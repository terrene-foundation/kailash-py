"""
Unit tests for EATP credential rotation.

Tests the CredentialRotationManager in isolation using mocked dependencies.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import eatp.rotation as rotation_module
from kaizen.trust.authority import (
    AuthorityPermission,
    OrganizationalAuthority,
    OrganizationalAuthorityRegistry,
)
from kaizen.trust.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
)
from kaizen.trust.exceptions import AuthorityInactiveError, AuthorityNotFoundError
from kaizen.trust.operations import TrustKeyManager
from kaizen.trust.rotation import (
    CredentialRotationManager,
    RotationError,
    RotationResult,
    RotationStatus,
    RotationStatusInfo,
    ScheduledRotation,
)
from kaizen.trust.store import PostgresTrustStore


@pytest.fixture
def key_manager():
    """Create a TrustKeyManager."""
    return TrustKeyManager()


@pytest.fixture
def mock_trust_store():
    """Create a mock PostgresTrustStore."""
    store = MagicMock(spec=PostgresTrustStore)
    store.list_chains = AsyncMock(return_value=[])
    store.update_chain = AsyncMock()
    return store


@pytest.fixture
def mock_authority_registry():
    """Create a mock OrganizationalAuthorityRegistry."""
    registry = MagicMock(spec=OrganizationalAuthorityRegistry)
    registry.get_authority = AsyncMock()
    registry.update_authority = AsyncMock()
    return registry


@pytest.fixture
def rotation_manager(key_manager, mock_trust_store, mock_authority_registry):
    """Create a CredentialRotationManager."""
    manager = CredentialRotationManager(
        key_manager=key_manager,
        trust_store=mock_trust_store,
        authority_registry=mock_authority_registry,
        rotation_period_days=90,
        grace_period_hours=24,
    )
    return manager


@pytest.fixture
def sample_authority():
    """Create a sample OrganizationalAuthority."""
    return OrganizationalAuthority(
        id="org-test",
        name="Test Organization",
        authority_type=AuthorityType.ORGANIZATION,
        public_key="test-public-key",
        signing_key_id="key-001",
        permissions=[AuthorityPermission.CREATE_AGENTS],
        is_active=True,
        metadata={},
    )


@pytest.fixture
def sample_chain():
    """Create a sample TrustLineageChain."""
    genesis = GenesisRecord(
        id="gen-001",
        agent_id="agent-001",
        authority_id="org-test",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime.now(timezone.utc),
        signature="genesis-signature",
    )

    capability = CapabilityAttestation(
        id="cap-001",
        capability="analyze_data",
        capability_type=CapabilityType.ACCESS,
        constraints=["read_only"],
        attester_id="org-test",
        attested_at=datetime.now(timezone.utc),
        signature="capability-signature",
    )

    return TrustLineageChain(
        genesis=genesis,
        capabilities=[capability],
    )


@pytest.mark.asyncio
class TestCredentialRotationManager:
    """Test suite for CredentialRotationManager."""

    async def test_initialize(self, rotation_manager):
        """Test initialization."""
        await rotation_manager.initialize()
        assert rotation_manager._initialized is True

        # Should be idempotent
        await rotation_manager.initialize()
        assert rotation_manager._initialized is True

    async def test_rotate_key_basic(
        self,
        rotation_manager,
        mock_authority_registry,
        mock_trust_store,
        sample_authority,
    ):
        """Test basic key rotation."""
        # Setup
        mock_authority_registry.get_authority.return_value = sample_authority
        mock_trust_store.list_chains.return_value = []

        await rotation_manager.initialize()

        # Mock generate_keypair using patch.object for reliable patching
        with patch.object(rotation_module, "generate_keypair") as mock_gen:
            mock_gen.return_value = ("new-private-key", "new-public-key")

            # Rotate
            result = await rotation_manager.rotate_key("org-test")

        # Verify result
        assert isinstance(result, RotationResult)
        assert result.old_key_id == "key-001"
        assert result.new_key_id.startswith("key-")
        assert result.chains_updated == 0
        assert result.grace_period_end is not None

        # Verify authority was updated
        mock_authority_registry.update_authority.assert_called_once()
        updated_authority = mock_authority_registry.update_authority.call_args[0][0]
        assert updated_authority.signing_key_id != "key-001"
        assert updated_authority.public_key == "new-public-key"
        assert "key_rotation_history" in updated_authority.metadata

    async def test_rotate_key_with_chains(
        self,
        rotation_manager,
        mock_authority_registry,
        mock_trust_store,
        sample_authority,
        sample_chain,
        key_manager,
    ):
        """Test key rotation with existing trust chains."""
        # Setup
        mock_authority_registry.get_authority.return_value = sample_authority
        mock_trust_store.list_chains.return_value = [sample_chain]

        await rotation_manager.initialize()

        # Mock generate_keypair using patch.object for reliable patching
        with (
            patch.object(rotation_module, "generate_keypair") as mock_gen,
            patch.object(rotation_module, "serialize_for_signing") as mock_serialize,
        ):
            # Generate a real keypair for the new key
            from kaizen.trust.crypto import generate_keypair as real_gen

            new_private_key, new_public_key = real_gen()
            mock_gen.return_value = (new_private_key, new_public_key)

            # Mock serialization to return simple string
            mock_serialize.return_value = "mock-payload"

            # Rotate
            result = await rotation_manager.rotate_key("org-test")

        # Verify chains were updated
        assert result.chains_updated == 1
        assert mock_trust_store.update_chain.call_count == 1

    async def test_rotate_key_authority_not_found(
        self,
        rotation_manager,
        mock_authority_registry,
    ):
        """Test rotation fails when authority not found."""
        mock_authority_registry.get_authority.side_effect = AuthorityNotFoundError(
            "org-missing"
        )

        await rotation_manager.initialize()

        with pytest.raises(RotationError) as exc_info:
            await rotation_manager.rotate_key("org-missing")

        assert exc_info.value.authority_id == "org-missing"

    async def test_rotate_key_concurrent_rotation_prevented(
        self,
        rotation_manager,
        mock_authority_registry,
        sample_authority,
    ):
        """Test that concurrent rotations are prevented."""
        mock_authority_registry.get_authority.return_value = sample_authority

        await rotation_manager.initialize()

        # Start first rotation
        rotation_manager._active_rotations.add("org-test")

        # Try second rotation
        with pytest.raises(RotationError) as exc_info:
            await rotation_manager.rotate_key("org-test")

        assert "in progress" in str(exc_info.value).lower()

    async def test_rotate_key_grace_period(
        self,
        rotation_manager,
        mock_authority_registry,
        mock_trust_store,
        sample_authority,
    ):
        """Test grace period is set correctly."""
        mock_authority_registry.get_authority.return_value = sample_authority
        mock_trust_store.list_chains.return_value = []

        await rotation_manager.initialize()

        with patch.object(rotation_module, "generate_keypair") as mock_gen:
            mock_gen.return_value = ("new-private-key", "new-public-key")

            # Rotate with custom grace period
            result = await rotation_manager.rotate_key(
                "org-test", grace_period_hours=48
            )

        # Verify grace period
        assert result.grace_period_end is not None
        expected_end = result.started_at + timedelta(hours=48)
        assert abs((result.grace_period_end - expected_end).total_seconds()) < 1

        # Verify old key is in grace period
        assert "org-test" in rotation_manager._grace_period_keys
        assert "key-001" in rotation_manager._grace_period_keys["org-test"]

    async def test_schedule_rotation(
        self,
        rotation_manager,
        mock_authority_registry,
        sample_authority,
    ):
        """Test scheduling a future rotation."""
        mock_authority_registry.get_authority.return_value = sample_authority

        await rotation_manager.initialize()

        future_time = datetime.now(timezone.utc) + timedelta(days=90)
        rotation_id = await rotation_manager.schedule_rotation(
            "org-test", at=future_time
        )

        # Verify scheduled rotation was created
        assert rotation_id.startswith("rot-")
        assert "org-test" in rotation_manager._scheduled_rotations
        assert len(rotation_manager._scheduled_rotations["org-test"]) == 1

        scheduled = rotation_manager._scheduled_rotations["org-test"][0]
        assert scheduled.authority_id == "org-test"
        assert scheduled.scheduled_at == future_time
        assert scheduled.status == RotationStatus.PENDING

    async def test_schedule_rotation_past_time_fails(
        self,
        rotation_manager,
        mock_authority_registry,
        sample_authority,
    ):
        """Test scheduling rotation in the past fails."""
        mock_authority_registry.get_authority.return_value = sample_authority

        await rotation_manager.initialize()

        past_time = datetime.now(timezone.utc) - timedelta(days=1)

        with pytest.raises(RotationError) as exc_info:
            await rotation_manager.schedule_rotation("org-test", at=past_time)

        assert "future" in str(exc_info.value).lower()

    async def test_get_rotation_status_no_history(
        self,
        rotation_manager,
        mock_authority_registry,
        sample_authority,
    ):
        """Test getting rotation status with no history."""
        mock_authority_registry.get_authority.return_value = sample_authority

        await rotation_manager.initialize()

        status = await rotation_manager.get_rotation_status("org-test")

        assert isinstance(status, RotationStatusInfo)
        assert status.current_key_id == "key-001"
        assert status.last_rotation is None
        assert status.next_scheduled is None
        assert status.status == RotationStatus.COMPLETED
        assert len(status.pending_revocations) == 0

    async def test_get_rotation_status_with_history(
        self,
        rotation_manager,
        mock_authority_registry,
        mock_trust_store,
        sample_authority,
    ):
        """Test getting rotation status with history."""
        mock_authority_registry.get_authority.return_value = sample_authority
        mock_trust_store.list_chains.return_value = []

        await rotation_manager.initialize()

        # Perform a rotation
        with patch.object(rotation_module, "generate_keypair") as mock_gen:
            mock_gen.return_value = ("new-private-key", "new-public-key")
            result = await rotation_manager.rotate_key("org-test")

        # Get status
        status = await rotation_manager.get_rotation_status("org-test")

        assert status.last_rotation is not None
        assert status.last_rotation == result.completed_at
        assert len(status.grace_period_keys) == 1
        assert "key-001" in status.grace_period_keys

    async def test_get_rotation_status_with_scheduled(
        self,
        rotation_manager,
        mock_authority_registry,
        sample_authority,
    ):
        """Test getting rotation status with scheduled rotation."""
        mock_authority_registry.get_authority.return_value = sample_authority

        await rotation_manager.initialize()

        # Schedule rotation
        future_time = datetime.now(timezone.utc) + timedelta(days=90)
        await rotation_manager.schedule_rotation("org-test", at=future_time)

        # Get status
        status = await rotation_manager.get_rotation_status("org-test")

        assert status.next_scheduled is not None
        assert status.next_scheduled == future_time

    async def test_revoke_old_key_success(
        self,
        rotation_manager,
        mock_authority_registry,
        sample_authority,
    ):
        """Test successful key revocation after grace period."""
        mock_authority_registry.get_authority.return_value = sample_authority

        await rotation_manager.initialize()

        # Add key to grace period (expired)
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        rotation_manager._grace_period_keys["org-test"] = {"key-old": past_time}

        # Revoke key
        await rotation_manager.revoke_old_key("org-test", "key-old")

        # Verify key was removed from grace period
        assert "key-old" not in rotation_manager._grace_period_keys["org-test"]

    async def test_revoke_old_key_grace_period_not_expired(
        self,
        rotation_manager,
        mock_authority_registry,
        sample_authority,
    ):
        """Test revocation fails when grace period not expired."""
        mock_authority_registry.get_authority.return_value = sample_authority

        await rotation_manager.initialize()

        # Add key to grace period (not expired)
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        rotation_manager._grace_period_keys["org-test"] = {"key-new": future_time}

        # Try to revoke key
        with pytest.raises(RotationError) as exc_info:
            await rotation_manager.revoke_old_key("org-test", "key-new")

        assert "not expired" in str(exc_info.value).lower()

    async def test_revoke_old_key_not_in_grace_period(
        self,
        rotation_manager,
        mock_authority_registry,
        sample_authority,
    ):
        """Test revocation fails when key not in grace period."""
        mock_authority_registry.get_authority.return_value = sample_authority

        await rotation_manager.initialize()

        # Try to revoke key that's not in grace period
        with pytest.raises(RotationError) as exc_info:
            await rotation_manager.revoke_old_key("org-test", "key-nonexistent")

        assert "grace period" in str(exc_info.value).lower()

    async def test_process_scheduled_rotations_no_due(
        self,
        rotation_manager,
        mock_authority_registry,
        sample_authority,
    ):
        """Test processing scheduled rotations with none due."""
        mock_authority_registry.get_authority.return_value = sample_authority

        await rotation_manager.initialize()

        # Schedule rotation in the future
        future_time = datetime.now(timezone.utc) + timedelta(days=90)
        await rotation_manager.schedule_rotation("org-test", at=future_time)

        # Process scheduled rotations
        results = await rotation_manager.process_scheduled_rotations()

        # No rotations should have been performed
        assert len(results) == 0

    async def test_process_scheduled_rotations_with_due(
        self,
        rotation_manager,
        mock_authority_registry,
        mock_trust_store,
        sample_authority,
    ):
        """Test processing scheduled rotations with due rotation."""
        mock_authority_registry.get_authority.return_value = sample_authority
        mock_trust_store.list_chains.return_value = []

        await rotation_manager.initialize()

        # Schedule rotation in the past
        past_time = datetime.now(timezone.utc) - timedelta(minutes=1)
        scheduled = ScheduledRotation(
            rotation_id="rot-test",
            authority_id="org-test",
            scheduled_at=past_time,
        )
        rotation_manager._scheduled_rotations["org-test"] = [scheduled]

        # Process scheduled rotations
        with patch.object(rotation_module, "generate_keypair") as mock_gen:
            mock_gen.return_value = ("new-private-key", "new-public-key")
            results = await rotation_manager.process_scheduled_rotations()

        # Rotation should have been performed
        assert len(results) == 1
        assert results[0].old_key_id == "key-001"
        assert scheduled.status == RotationStatus.COMPLETED

    async def test_rotation_result_to_dict(self):
        """Test RotationResult serialization."""
        result = RotationResult(
            new_key_id="key-new",
            old_key_id="key-old",
            chains_updated=5,
            started_at=datetime(2025, 1, 1, 12, 0, 0),
            completed_at=datetime(2025, 1, 1, 12, 5, 0),
            rotation_id="rot-123",
            grace_period_end=datetime(2025, 1, 2, 12, 0, 0),
        )

        result_dict = result.to_dict()

        assert result_dict["rotation_id"] == "rot-123"
        assert result_dict["new_key_id"] == "key-new"
        assert result_dict["old_key_id"] == "key-old"
        assert result_dict["chains_updated"] == 5
        assert "started_at" in result_dict
        assert "completed_at" in result_dict
        assert "grace_period_end" in result_dict

    async def test_rotation_status_info_to_dict(self):
        """Test RotationStatusInfo serialization."""
        status = RotationStatusInfo(
            last_rotation=datetime(2025, 1, 1, 12, 0, 0),
            next_scheduled=datetime(2025, 4, 1, 12, 0, 0),
            current_key_id="key-001",
            pending_revocations=["key-old-1", "key-old-2"],
            rotation_period_days=90,
            status=RotationStatus.GRACE_PERIOD,
            grace_period_keys={"key-old": datetime(2025, 1, 2, 12, 0, 0)},
        )

        status_dict = status.to_dict()

        assert status_dict["current_key_id"] == "key-001"
        assert status_dict["rotation_period_days"] == 90
        assert status_dict["status"] == "grace_period"
        assert len(status_dict["pending_revocations"]) == 2
        assert "last_rotation" in status_dict
        assert "next_scheduled" in status_dict
        assert "grace_period_keys" in status_dict

    async def test_close(self, rotation_manager):
        """Test cleanup."""
        rotation_manager._active_rotations.add("org-test")
        rotation_manager._rotation_locks["org-test"] = None

        await rotation_manager.close()

        assert len(rotation_manager._active_rotations) == 0
        assert len(rotation_manager._rotation_locks) == 0
