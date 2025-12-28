"""Unit tests for EdgeDataNode."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.edge.location import (
    ComplianceZone,
    EdgeCapabilities,
    EdgeLocation,
    EdgeMetrics,
    EdgeRegion,
    GeographicCoordinates,
)
from kailash.nodes.edge.edge_data import ConsistencyModel, EdgeDataNode


@pytest.fixture
def mock_edge_locations():
    """Create mock edge locations for testing."""
    locations = []

    for i, (location_id, name, region, zone_names) in enumerate(
        [
            ("us-east-1", "edge-us-east", EdgeRegion.US_EAST, ["sox", "hipaa"]),
            ("us-west-2", "edge-us-west", EdgeRegion.US_WEST, ["sox", "ccpa"]),
            ("eu-west-1", "edge-eu-west", EdgeRegion.EU_WEST, ["gdpr", "sox"]),
        ]
    ):
        capabilities = EdgeCapabilities(
            cpu_cores=8,
            memory_gb=16,
            storage_gb=100,
            gpu_available=False,
            bandwidth_gbps=10,
        )

        metrics = EdgeMetrics(
            latency_p50_ms=10.0 + i * 5,
            cpu_utilization=0.3 + i * 0.1,
            memory_utilization=0.4 + i * 0.1,
            storage_utilization=0.5 + i * 0.1,
            throughput_rps=1000 - i * 100,
            error_rate=0.01 + i * 0.005,
        )

        # Convert zone names to ComplianceZone enums
        compliance_zones = []
        for zone_name in zone_names:
            try:
                compliance_zones.append(ComplianceZone[zone_name.upper()])
            except KeyError:
                # Skip unknown zones
                pass

        coordinates = GeographicCoordinates(
            latitude=40.0 - i * 10, longitude=-74.0 + i * 10
        )

        location = EdgeLocation(
            location_id=location_id,
            name=name,
            region=region,
            coordinates=coordinates,
            capabilities=capabilities,
            compliance_zones=compliance_zones,
        )

        # Set metrics after creation
        location.metrics = metrics

        locations.append(location)

    return locations


@pytest.fixture
def edge_data_node(mock_edge_locations):
    """Create EdgeDataNode instance with mocked dependencies."""
    node = EdgeDataNode(
        consistency="eventual", replication_factor=3, edge_strategy="balanced"
    )

    # Mock edge discovery
    node.edge_discovery = Mock()
    node.edge_discovery.get_all_edges.return_value = mock_edge_locations
    node.edge_discovery.get_edge.side_effect = lambda name: next(
        (e for e in mock_edge_locations if e.name == name), None
    )
    node.edge_discovery.select_edge.return_value = mock_edge_locations[0]

    # Mock compliance router
    node.compliance_router = Mock()
    node.compliance_router.classify_data.return_value = "personal_data"
    node.compliance_router.is_compliant_location.return_value = True

    # Set current edge
    node.current_edge = mock_edge_locations[0]

    return node


class TestEdgeDataNode:
    """Test suite for EdgeDataNode."""

    @pytest.mark.asyncio
    async def test_write_eventual_consistency(self, edge_data_node):
        """Test write operation with eventual consistency."""
        result = await edge_data_node.execute_async(
            action="write",
            key="test_key",
            data={"value": "test_value"},
            consistency="eventual",
        )

        assert result["success"] is True
        assert result["key"] == "test_key"
        assert result["version"] == 1
        assert result["edge"] == "edge-us-east"
        assert result["consistency"] == "eventual"

    @pytest.mark.asyncio
    async def test_write_strong_consistency(self, edge_data_node):
        """Test write operation with strong consistency."""
        # Mock 2PC methods
        edge_data_node._prepare_replication = AsyncMock(return_value=True)
        edge_data_node._commit_replication = AsyncMock(return_value=True)

        result = await edge_data_node.execute_async(
            action="write",
            key="test_key",
            data={"value": "test_value"},
            consistency="strong",
        )

        assert result["success"] is True
        assert result["consistency"] == "strong"

        # Verify 2PC was called
        assert edge_data_node._prepare_replication.called
        assert edge_data_node._commit_replication.called

    @pytest.mark.asyncio
    async def test_read_not_found(self, edge_data_node):
        """Test read operation when key doesn't exist."""
        result = await edge_data_node.execute_async(
            action="read", key="nonexistent_key"
        )

        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_read_after_write(self, edge_data_node):
        """Test read operation after successful write."""
        # Write data
        write_result = await edge_data_node.execute_async(
            action="write", key="test_key", data={"value": "test_value"}
        )

        assert write_result["success"] is True

        # Read data
        read_result = await edge_data_node.execute_async(action="read", key="test_key")

        assert read_result["success"] is True
        assert read_result["key"] == "test_key"
        assert read_result["data"] == {"value": "test_value"}
        assert read_result["version"] == 1

    @pytest.mark.asyncio
    async def test_replicate_operation(self, edge_data_node):
        """Test manual replication operation."""
        # Write data first
        await edge_data_node.execute_async(
            action="write", key="test_key", data={"value": "test_value"}
        )

        # Mock replication method
        edge_data_node._replicate_to_edge = AsyncMock(return_value=True)

        # Replicate to specific edges
        result = await edge_data_node.execute_async(
            action="replicate",
            key="test_key",
            target_edges=["edge-us-west", "edge-eu-west"],
        )

        assert result["success"] is True
        assert result["key"] == "test_key"
        assert result["source_edge"] == "edge-us-east"
        assert result["replication_results"]["edge-us-west"] is True
        assert result["replication_results"]["edge-eu-west"] is True

    @pytest.mark.asyncio
    async def test_sync_operation(self, edge_data_node):
        """Test sync operation for consistency."""
        # Setup different versions across edges
        edge_data_node._edge_data = {
            "edge-us-east": {
                "key1": {
                    "data": "value1",
                    "version": 1,
                    "timestamp": "2024-01-01T00:00:00",
                    "edge": "edge-us-east",
                }
            },
            "edge-us-west": {
                "key1": {
                    "data": "value1_old",
                    "version": 0,
                    "timestamp": "2024-01-01T00:00:00",
                    "edge": "edge-us-west",
                }
            },
        }

        edge_data_node._data_versions = {
            "edge-us-east": {"key1": 1},
            "edge-us-west": {"key1": 0},
        }

        # Mock replication
        edge_data_node._replicate_to_edge = AsyncMock(return_value=True)

        result = await edge_data_node.execute_async(action="sync", keys=["key1"])

        assert result["success"] is True
        assert result["sync_results"]["key1"]["status"] == "synced"
        assert result["sync_results"]["key1"]["winner_edge"] == "edge-us-east"
        assert result["sync_results"]["key1"]["winner_version"] == 1
        assert "edge-us-west" in result["sync_results"]["key1"]["synced_edges"]

    @pytest.mark.asyncio
    async def test_consistency_model_validation(self, edge_data_node):
        """Test different consistency models."""
        for consistency in ["strong", "eventual", "causal", "bounded_staleness"]:
            result = await edge_data_node.execute_async(
                action="write",
                key=f"test_{consistency}",
                data={"value": f"test_{consistency}"},
                consistency=consistency,
            )

            assert result["success"] is True
            assert result["consistency"] == consistency

    @pytest.mark.asyncio
    async def test_write_without_key(self, edge_data_node):
        """Test write operation without key raises error."""
        from kailash.sdk_exceptions import NodeExecutionError

        with pytest.raises(NodeExecutionError, match="Write requires 'key' and 'data'"):
            await edge_data_node.execute_async(action="write", data={"value": "test"})

    @pytest.mark.asyncio
    async def test_write_without_data(self, edge_data_node):
        """Test write operation without data raises error."""
        from kailash.sdk_exceptions import NodeExecutionError

        with pytest.raises(NodeExecutionError, match="Write requires 'key' and 'data'"):
            await edge_data_node.execute_async(action="write", key="test_key")

    @pytest.mark.asyncio
    async def test_version_increment(self, edge_data_node):
        """Test version increments on successive writes."""
        # First write
        result1 = await edge_data_node.execute_async(
            action="write", key="version_test", data={"value": "v1"}
        )
        assert result1["version"] == 1

        # Second write
        result2 = await edge_data_node.execute_async(
            action="write", key="version_test", data={"value": "v2"}
        )
        assert result2["version"] == 2

        # Third write
        result3 = await edge_data_node.execute_async(
            action="write", key="version_test", data={"value": "v3"}
        )
        assert result3["version"] == 3

    @pytest.mark.asyncio
    async def test_bounded_staleness_read(self, edge_data_node):
        """Test read with bounded staleness consistency."""
        # Setup stale data
        edge_data_node._edge_data = {
            "edge-us-east": {
                "stale_key": {
                    "data": "stale_value",
                    "version": 1,
                    "timestamp": "2020-01-01T00:00:00",  # Very old
                    "edge": "edge-us-east",
                }
            }
        }

        # Mock refresh method
        edge_data_node._refresh_from_primary = AsyncMock()

        result = await edge_data_node.execute_async(
            action="read",
            key="stale_key",
            consistency="bounded_staleness",
            staleness_threshold_ms=1000,  # 1 second
        )

        # Should attempt to refresh due to staleness
        assert edge_data_node._refresh_from_primary.called

    @pytest.mark.asyncio
    async def test_compliance_check(self, edge_data_node):
        """Test compliance checking during write."""
        # Make compliance check fail
        edge_data_node.ensure_compliance = AsyncMock(return_value=False)

        result = await edge_data_node.execute_async(
            action="write", key="gdpr_data", data={"personal_info": "test"}
        )

        assert result["success"] is False
        assert "No compliant edge available" in result["error"]

    @pytest.mark.asyncio
    async def test_replication_targets_selection(
        self, edge_data_node, mock_edge_locations
    ):
        """Test selection of replication targets."""
        edge_data_node.config["replication_factor"] = 3

        targets = await edge_data_node._select_replication_targets()

        # Should select 2 targets (current edge + 2 = replication_factor)
        assert len(targets) == 2

        # Current edge should not be in targets
        assert edge_data_node.current_edge not in targets

        # Targets should be sorted by latency
        assert targets[0].metrics.latency_p50_ms < targets[1].metrics.latency_p50_ms

    @pytest.mark.asyncio
    async def test_causal_consistency_write(self, edge_data_node):
        """Test write with causal consistency tracking."""
        # Mock causal replication
        edge_data_node._replicate_causal = AsyncMock(return_value=True)

        result = await edge_data_node.execute_async(
            action="write",
            key="causal_key",
            data={"value": "causal_value"},
            consistency="causal",
        )

        assert result["success"] is True
        assert result["consistency"] == "causal"

    @pytest.mark.asyncio
    async def test_unknown_action(self, edge_data_node):
        """Test unknown action raises error."""
        from kailash.sdk_exceptions import NodeExecutionError

        with pytest.raises(NodeExecutionError, match="Unknown action"):
            await edge_data_node.execute_async(action="unknown_action", key="test")

    @pytest.mark.asyncio
    async def test_2pc_partial_failure(self, edge_data_node):
        """Test 2PC handling when some replicas fail to prepare."""
        # Mock one success, one failure in prepare phase
        edge_data_node._prepare_replication = AsyncMock(side_effect=[True, False, True])
        edge_data_node._abort_replication = AsyncMock(return_value=True)

        from kailash.sdk_exceptions import NodeExecutionError

        with pytest.raises(
            NodeExecutionError, match="Strong consistency replication failed"
        ):
            await edge_data_node.execute_async(
                action="write",
                key="2pc_test",
                data={"value": "test"},
                consistency="strong",
            )

        # Verify abort was called for prepared replicas
        assert edge_data_node._abort_replication.called
