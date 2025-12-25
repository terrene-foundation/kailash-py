"""Unit tests for EdgeStateMachine."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from kailash.edge.location import (
    ComplianceZone,
    EdgeCapabilities,
    EdgeLocation,
    EdgeMetrics,
    EdgeRegion,
    GeographicCoordinates,
)
from kailash.nodes.edge.edge_state import EdgeStateMachine, StateOperation


@pytest.fixture
def mock_edge_location():
    """Create a mock edge location."""
    capabilities = EdgeCapabilities(
        cpu_cores=8,
        memory_gb=16,
        storage_gb=100,
        gpu_available=False,
        bandwidth_gbps=10,
    )

    metrics = EdgeMetrics(
        latency_p50_ms=10.0,
        cpu_utilization=0.3,
        memory_utilization=0.4,
        storage_utilization=0.5,
        throughput_rps=1000,
        error_rate=0.01,
    )

    coordinates = GeographicCoordinates(latitude=38.0, longitude=-78.0)

    location = EdgeLocation(
        location_id="us-east-1",
        name="edge-primary",
        region=EdgeRegion.US_EAST,
        coordinates=coordinates,
        capabilities=capabilities,
        compliance_zones=[ComplianceZone.SOX, ComplianceZone.HIPAA],
    )

    # Set metrics after creation
    location.metrics = metrics

    return location


@pytest_asyncio.fixture
async def edge_state_machine(mock_edge_location):
    """Create EdgeStateMachine instance with mocked dependencies."""
    # Clear global state before each test
    EdgeStateMachine._global_instances.clear()
    EdgeStateMachine._global_locks.clear()

    machine = EdgeStateMachine(
        state_id="test_state_123",
        lease_duration_ms=30000,
        enable_persistence=True,
        enable_replication=True,
    )

    # Mock edge discovery
    machine.edge_discovery = Mock()
    machine.edge_discovery.get_all_edges.return_value = [mock_edge_location]
    machine.edge_discovery.get_edge.return_value = mock_edge_location
    machine.edge_discovery.select_edge = AsyncMock(return_value=mock_edge_location)
    machine.edge_discovery.start_discovery = AsyncMock()

    # Mock compliance router
    machine.compliance_router = Mock()
    machine.compliance_router.classify_data.return_value = "general"
    machine.compliance_router.is_compliant_location.return_value = True

    # Set current edge
    machine.current_edge = mock_edge_location

    # Mock async methods
    machine._persist_state = AsyncMock()
    machine._load_persisted_state = AsyncMock()
    machine._replicate_state = AsyncMock()

    yield machine

    # Cleanup
    await machine.cleanup()


class TestEdgeStateMachine:
    """Test suite for EdgeStateMachine."""

    @pytest.mark.asyncio
    async def test_initialization_acquires_global_lock(self, edge_state_machine):
        """Test initialization acquires global lock."""
        await edge_state_machine.initialize()

        assert edge_state_machine.is_primary is True
        assert edge_state_machine.state_id in EdgeStateMachine._global_instances
        assert f"state:{edge_state_machine.state_id}" in EdgeStateMachine._global_locks

    @pytest.mark.asyncio
    async def test_duplicate_instance_fails(self, edge_state_machine):
        """Test creating duplicate instance fails."""
        # Initialize first instance
        await edge_state_machine.initialize()

        # Try to create second instance with same state_id
        duplicate = EdgeStateMachine(state_id="test_state_123", lease_duration_ms=30000)

        # Copy mocks
        duplicate.edge_discovery = edge_state_machine.edge_discovery
        duplicate.compliance_router = edge_state_machine.compliance_router
        duplicate.current_edge = edge_state_machine.current_edge

        with pytest.raises(RuntimeError, match="already exists"):
            await duplicate.initialize()

    @pytest.mark.asyncio
    async def test_get_operation(self, edge_state_machine):
        """Test GET operation."""
        await edge_state_machine.initialize()

        # Set some state
        edge_state_machine.state_data = {"key1": "value1", "key2": "value2"}

        # Get specific key
        result = await edge_state_machine.execute_async(operation="get", key="key1")

        assert result["success"] is True
        assert result["key"] == "key1"
        assert result["value"] == "value1"
        assert result["exists"] is True

        # Get non-existent key
        result = await edge_state_machine.execute_async(
            operation="get", key="nonexistent"
        )

        assert result["success"] is True
        assert result["value"] is None
        assert result["exists"] is False

        # Get entire state
        result = await edge_state_machine.execute_async(operation="get")

        assert result["success"] is True
        assert result["state"] == {"key1": "value1", "key2": "value2"}

    @pytest.mark.asyncio
    async def test_set_operation(self, edge_state_machine):
        """Test SET operation."""
        await edge_state_machine.initialize()

        result = await edge_state_machine.execute_async(
            operation="set", key="test_key", value="test_value"
        )

        assert result["success"] is True
        assert result["key"] == "test_key"
        assert result["old_value"] is None
        assert result["new_value"] == "test_value"
        assert result["version"] == 1

        # Verify state was updated
        assert edge_state_machine.state_data["test_key"] == "test_value"

        # Verify persistence was called
        assert edge_state_machine._persist_state.called

    @pytest.mark.asyncio
    async def test_update_operation(self, edge_state_machine):
        """Test UPDATE operation with function."""
        await edge_state_machine.initialize()

        # Set initial value
        edge_state_machine.state_data["counter"] = 5

        # Update with increment function
        def increment(val):
            return (val or 0) + 1

        result = await edge_state_machine.execute_async(
            operation="update", key="counter", update_fn=increment
        )

        assert result["success"] is True
        assert result["old_value"] == 5
        assert result["new_value"] == 6
        assert edge_state_machine.state_data["counter"] == 6

    @pytest.mark.asyncio
    async def test_delete_operation(self, edge_state_machine):
        """Test DELETE operation."""
        await edge_state_machine.initialize()

        # Set initial state
        edge_state_machine.state_data["to_delete"] = "value"

        result = await edge_state_machine.execute_async(
            operation="delete", key="to_delete"
        )

        assert result["success"] is True
        assert result["deleted"] is True
        assert result["old_value"] == "value"
        assert "to_delete" not in edge_state_machine.state_data

    @pytest.mark.asyncio
    async def test_increment_operation(self, edge_state_machine):
        """Test INCREMENT operation."""
        await edge_state_machine.initialize()

        # Initialize counter
        edge_state_machine.state_data["counter"] = 10

        result = await edge_state_machine.execute_async(
            operation="increment", key="counter", increment=5
        )

        assert result["success"] is True
        assert result["old_value"] == 10
        assert result["new_value"] == 15
        assert result["increment"] == 5

        # Test auto-initialization to 0
        result = await edge_state_machine.execute_async(
            operation="increment", key="new_counter"
        )

        assert result["success"] is True
        assert result["old_value"] == 0
        assert result["new_value"] == 1

    @pytest.mark.asyncio
    async def test_increment_non_numeric_fails(self, edge_state_machine):
        """Test INCREMENT on non-numeric value fails."""
        await edge_state_machine.initialize()

        edge_state_machine.state_data["string_key"] = "not_a_number"

        result = await edge_state_machine.execute_async(
            operation="increment", key="string_key"
        )

        assert result["success"] is False
        assert "Cannot increment non-numeric value" in result["error"]

    @pytest.mark.asyncio
    async def test_append_operation(self, edge_state_machine):
        """Test APPEND operation."""
        await edge_state_machine.initialize()

        # Initialize list
        edge_state_machine.state_data["items"] = ["a", "b"]

        result = await edge_state_machine.execute_async(
            operation="append", key="items", value="c"
        )

        assert result["success"] is True
        assert result["list_size"] == 3
        assert result["appended_value"] == "c"
        assert edge_state_machine.state_data["items"] == ["a", "b", "c"]

        # Test auto-initialization to empty list
        result = await edge_state_machine.execute_async(
            operation="append", key="new_list", value="first"
        )

        assert result["success"] is True
        assert result["list_size"] == 1
        assert edge_state_machine.state_data["new_list"] == ["first"]

    @pytest.mark.asyncio
    async def test_append_to_non_list_fails(self, edge_state_machine):
        """Test APPEND to non-list value fails."""
        await edge_state_machine.initialize()

        edge_state_machine.state_data["not_list"] = "string"

        result = await edge_state_machine.execute_async(
            operation="append", key="not_list", value="item"
        )

        assert result["success"] is False
        assert "Cannot append to non-list value" in result["error"]

    @pytest.mark.asyncio
    async def test_lock_operation(self, edge_state_machine):
        """Test LOCK operation."""
        await edge_state_machine.initialize()

        result = await edge_state_machine.execute_async(
            operation="lock", lock_name="resource_1", timeout_ms=5000
        )

        assert result["success"] is True
        assert result["lock_name"] == "resource_1"
        assert "resource_1" in edge_state_machine.local_locks

        # Try to acquire same lock again
        result = await edge_state_machine.execute_async(
            operation="lock", lock_name="resource_1"
        )

        assert result["success"] is False
        assert "Lock already held" in result["error"]

    @pytest.mark.asyncio
    async def test_unlock_operation(self, edge_state_machine):
        """Test UNLOCK operation."""
        await edge_state_machine.initialize()

        # Acquire lock first
        edge_state_machine.local_locks.add("resource_1")

        result = await edge_state_machine.execute_async(
            operation="unlock", lock_name="resource_1"
        )

        assert result["success"] is True
        assert result["released"] is True
        assert "resource_1" not in edge_state_machine.local_locks

        # Unlock non-existent lock
        result = await edge_state_machine.execute_async(
            operation="unlock", lock_name="not_locked"
        )

        assert result["success"] is True
        assert result["released"] is False

    @pytest.mark.asyncio
    async def test_lock_auto_release(self, edge_state_machine):
        """Test lock auto-release after timeout."""
        await edge_state_machine.initialize()

        result = await edge_state_machine.execute_async(
            operation="lock", lock_name="auto_release", timeout_ms=100  # 100ms timeout
        )

        assert result["success"] is True
        assert "auto_release" in edge_state_machine.local_locks

        # Wait for auto-release
        await asyncio.sleep(0.15)

        assert "auto_release" not in edge_state_machine.local_locks

    @pytest.mark.asyncio
    async def test_primary_redirect(self, edge_state_machine):
        """Test redirect when not primary."""
        await edge_state_machine.initialize()

        # Simulate loss of primary status
        edge_state_machine.is_primary = False
        edge_state_machine._find_primary_instance = AsyncMock(
            return_value=edge_state_machine.current_edge
        )

        result = await edge_state_machine.execute_async(operation="get")

        assert result["success"] is False
        assert result["redirect"] is True
        assert result["primary_edge"] == "edge-primary"

    @pytest.mark.asyncio
    async def test_lease_expiry(self, edge_state_machine):
        """Test handling of lease expiry."""
        await edge_state_machine.initialize()

        # Set lease to expired
        edge_state_machine.lease_expiry = datetime.now(UTC) - timedelta(seconds=1)

        result = await edge_state_machine.execute_async(operation="get")

        assert result["success"] is False
        assert result["redirect"] is True

    @pytest.mark.asyncio
    async def test_edge_affinity_hash(self, edge_state_machine, mock_edge_location):
        """Test edge affinity based on state_id hash."""
        # Create properly named mock edges
        edge2 = Mock()
        edge2.name = "edge-2"
        edge3 = Mock()
        edge3.name = "edge-3"

        edge_state_machine.edge_discovery.get_all_edges.return_value = [
            mock_edge_location,
            edge2,
            edge3,
        ]

        edge_state_machine._set_edge_affinity()

        # Should have exactly one preferred location
        assert len(edge_state_machine.preferred_locations) == 1
        assert edge_state_machine.preferred_locations[0] in [
            "edge-primary",
            "edge-2",
            "edge-3",
        ]

    @pytest.mark.asyncio
    async def test_metadata_tracking(self, edge_state_machine):
        """Test metadata is properly tracked."""
        await edge_state_machine.initialize()

        initial_access_count = edge_state_machine.state_metadata["access_count"]

        # Perform operations
        await edge_state_machine.execute_async(operation="set", key="k1", value="v1")
        await edge_state_machine.execute_async(operation="get", key="k1")
        await edge_state_machine.execute_async(operation="set", key="k2", value="v2")

        # Check metadata updates
        assert (
            edge_state_machine.state_metadata["access_count"]
            == initial_access_count + 3
        )
        assert edge_state_machine.state_metadata["version"] == 2  # Two sets
        assert "last_accessed" in edge_state_machine.state_metadata
        assert "last_modified" in edge_state_machine.state_metadata

    @pytest.mark.asyncio
    async def test_replication_enabled(self, edge_state_machine):
        """Test replication is triggered when enabled."""
        await edge_state_machine.initialize()

        edge_state_machine._replicate_state = AsyncMock()

        await edge_state_machine.execute_async(
            operation="set", key="replicated_key", value="replicated_value"
        )

        # Give async task time to start
        await asyncio.sleep(0.01)

        assert edge_state_machine._replicate_state.called

    @pytest.mark.asyncio
    async def test_migrate_to_edge(self, edge_state_machine, mock_edge_location):
        """Test state migration to different edge."""
        await edge_state_machine.initialize()

        # Create target edge
        target_edge = Mock()
        target_edge.name = "edge-target"

        success = await edge_state_machine.migrate_to_edge(target_edge)

        assert success is True
        assert edge_state_machine.is_primary is False
        assert edge_state_machine.state_id not in EdgeStateMachine._global_instances

        # Verify global lock was updated
        lock_key = f"state:{edge_state_machine.state_id}"
        assert EdgeStateMachine._global_locks[lock_key]["owner"] == "edge-target"

    @pytest.mark.asyncio
    async def test_required_parameters(self):
        """Test state_id is required."""
        with pytest.raises(ValueError, match="state_id is required"):
            EdgeStateMachine()
