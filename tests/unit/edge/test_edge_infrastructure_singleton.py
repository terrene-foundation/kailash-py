"""Unit tests for EdgeInfrastructure singleton class.

This test suite follows TDD principles and tests the EdgeInfrastructure
singleton that manages shared edge computing resources across workflows.
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch

import pytest
from kailash.edge.location import (
    ComplianceZone,
    EdgeCapabilities,
    EdgeLocation,
    EdgeRegion,
    GeographicCoordinates,
)


class TestEdgeInfrastructureSingleton:
    """Test EdgeInfrastructure singleton behavior and functionality."""

    @pytest.fixture
    def mock_edge_config(self):
        """Create mock edge configuration."""
        return {
            "discovery": {
                "locations": ["us-east-1", "eu-west-1", "asia-east-1"],
                "refresh_interval": 300,
            },
            "compliance": {
                "strict_mode": True,
                "default_classification": "pii",
            },
            "performance": {
                "connection_pool_size": 10,
                "health_check_interval": 60,
            },
        }

    @pytest.fixture
    def sample_edge_locations(self):
        """Create sample edge locations for testing."""
        return [
            EdgeLocation(
                location_id="us-east-1",
                name="US East 1",
                region=EdgeRegion.US_EAST,
                coordinates=GeographicCoordinates(40.7128, -74.0060),
                capabilities=EdgeCapabilities(
                    cpu_cores=8, memory_gb=32, storage_gb=500
                ),
                compliance_zones=[ComplianceZone.PUBLIC, ComplianceZone.HIPAA],
            ),
            EdgeLocation(
                location_id="eu-west-1",
                name="EU West 1",
                region=EdgeRegion.EU_WEST,
                coordinates=GeographicCoordinates(53.3498, -6.2603),
                capabilities=EdgeCapabilities(
                    cpu_cores=4, memory_gb=16, storage_gb=200
                ),
                compliance_zones=[ComplianceZone.GDPR, ComplianceZone.PUBLIC],
            ),
        ]

    def test_singleton_behavior(self, mock_edge_config):
        """Test that EdgeInfrastructure follows singleton pattern."""
        # Import here to avoid circular import issues
        from kailash.workflow.edge_infrastructure import EdgeInfrastructure

        # Clear any existing instance
        EdgeInfrastructure._instance = None
        EdgeInfrastructure._lock = threading.Lock()

        # Create multiple instances
        instance1 = EdgeInfrastructure(mock_edge_config)
        instance2 = EdgeInfrastructure(mock_edge_config)
        instance3 = EdgeInfrastructure()  # With no config

        # All should be the same instance
        assert instance1 is instance2
        assert instance2 is instance3
        assert id(instance1) == id(instance2) == id(instance3)

        # Config should be from first initialization (merged with defaults)
        # Check that the provided config values are preserved
        assert (
            instance1._config["discovery"]["locations"]
            == mock_edge_config["discovery"]["locations"]
        )
        assert (
            instance1._config["discovery"]["refresh_interval"]
            == mock_edge_config["discovery"]["refresh_interval"]
        )
        assert (
            instance1._config["compliance"]["strict_mode"]
            == mock_edge_config["compliance"]["strict_mode"]
        )
        assert (
            instance1._config["performance"]["connection_pool_size"]
            == mock_edge_config["performance"]["connection_pool_size"]
        )

        # All instances should have the same config
        assert instance1._config == instance2._config
        assert instance2._config == instance3._config

    def test_thread_safety(self, mock_edge_config):
        """Test thread-safe singleton creation."""
        from kailash.workflow.edge_infrastructure import EdgeInfrastructure

        # Clear any existing instance
        EdgeInfrastructure._instance = None
        EdgeInfrastructure._lock = threading.Lock()

        instances = []
        errors = []

        def create_instance(config):
            try:
                instance = EdgeInfrastructure(config)
                instances.append(instance)
            except Exception as e:
                errors.append(e)

        # Create instances from multiple threads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(create_instance, mock_edge_config) for _ in range(10)
            ]

            # Wait for all threads to complete
            for future in as_completed(futures):
                future.result()

        # No errors should occur
        assert len(errors) == 0

        # All instances should be the same
        assert len(instances) == 10
        first_instance = instances[0]
        for instance in instances[1:]:
            assert instance is first_instance

    @patch("kailash.workflow.edge_infrastructure.EdgeDiscovery")
    @patch("kailash.workflow.edge_infrastructure.ComplianceRouter")
    def test_lazy_initialization(
        self, mock_compliance_class, mock_discovery_class, mock_edge_config
    ):
        """Test that edge components are lazily initialized."""
        from kailash.workflow.edge_infrastructure import EdgeInfrastructure

        # Create mock instances
        mock_discovery = MagicMock()
        mock_compliance = MagicMock()
        mock_discovery_class.return_value = mock_discovery
        mock_compliance_class.return_value = mock_compliance

        # Clear any existing instance
        EdgeInfrastructure._instance = None
        EdgeInfrastructure._lock = threading.Lock()

        # Create instance
        infrastructure = EdgeInfrastructure(mock_edge_config)

        # Components should not be initialized yet
        assert infrastructure._discovery is None
        assert infrastructure._compliance_router is None
        mock_discovery_class.assert_not_called()
        mock_compliance_class.assert_not_called()

        # Access discovery - should initialize
        discovery = infrastructure.get_discovery()
        assert discovery is mock_discovery
        mock_discovery_class.assert_called_once()

        # Access again - should return same instance
        discovery2 = infrastructure.get_discovery()
        assert discovery2 is discovery
        mock_discovery_class.assert_called_once()  # Still only called once

        # Access compliance router - should initialize
        router = infrastructure.get_compliance_router()
        assert router is mock_compliance
        mock_compliance_class.assert_called_once()

    def test_edge_node_detection(self):
        """Test detection of edge nodes."""
        from kailash.workflow.edge_infrastructure import EdgeInfrastructure

        # Clear any existing instance
        EdgeInfrastructure._instance = None
        EdgeInfrastructure._lock = threading.Lock()

        infrastructure = EdgeInfrastructure()

        # Test edge node types
        assert infrastructure.is_edge_node("EdgeNode") is True
        assert infrastructure.is_edge_node("EdgeDataNode") is True
        assert infrastructure.is_edge_node("EdgeStateMachine") is True
        assert infrastructure.is_edge_node("EdgeCacheNode") is True

        # Test non-edge nodes
        assert infrastructure.is_edge_node("CSVReaderNode") is False
        assert infrastructure.is_edge_node("LLMAgentNode") is False
        assert infrastructure.is_edge_node("SQLDatabaseNode") is False

        # Test custom edge nodes (subclasses)
        assert infrastructure.is_edge_node("CustomEdgeNode") is True
        assert infrastructure.is_edge_node("MyEdgeDataNode") is True

    @patch("kailash.workflow.edge_infrastructure.EdgeDiscovery")
    @pytest.mark.asyncio
    async def test_location_management(
        self, mock_discovery_class, sample_edge_locations
    ):
        """Test edge location management through infrastructure."""
        from kailash.workflow.edge_infrastructure import EdgeInfrastructure

        # Clear any existing instance
        EdgeInfrastructure._instance = None
        EdgeInfrastructure._lock = threading.Lock()

        # Setup mock
        mock_discovery = MagicMock()
        mock_discovery_class.return_value = mock_discovery

        infrastructure = EdgeInfrastructure()

        # Add locations
        for location in sample_edge_locations:
            infrastructure.add_location(location)

        # Should initialize discovery and add locations
        assert mock_discovery.add_location.call_count == len(sample_edge_locations)

        # Get all locations
        mock_discovery.get_all_edges.return_value = sample_edge_locations
        locations = infrastructure.get_all_locations()
        assert len(locations) == len(sample_edge_locations)

        # Select edge - now async
        async def mock_select_edge(*args, **kwargs):
            return sample_edge_locations[0]

        mock_discovery.select_edge = mock_select_edge
        selected = await infrastructure.select_edge({"region": EdgeRegion.US_EAST})
        assert selected == sample_edge_locations[0]

    def test_health_monitoring(self, mock_edge_config):
        """Test health monitoring capabilities."""
        from kailash.workflow.edge_infrastructure import EdgeInfrastructure

        # Clear any existing instance
        EdgeInfrastructure._instance = None
        EdgeInfrastructure._lock = threading.Lock()

        infrastructure = EdgeInfrastructure(mock_edge_config)

        # Initial health should be good
        health = infrastructure.get_health_status()
        assert health["status"] == "healthy"
        assert health["discovery"]["initialized"] is False
        assert health["compliance"]["initialized"] is False

        # After accessing components
        infrastructure.get_discovery()
        infrastructure.get_compliance_router()

        health = infrastructure.get_health_status()
        assert health["discovery"]["initialized"] is True
        assert health["compliance"]["initialized"] is True
        assert health["discovery"]["location_count"] >= 0
        assert "uptime_seconds" in health

    @pytest.mark.asyncio
    async def test_async_cleanup(self, mock_edge_config):
        """Test async cleanup of resources."""
        from kailash.workflow.edge_infrastructure import EdgeInfrastructure

        # Clear any existing instance
        EdgeInfrastructure._instance = None
        EdgeInfrastructure._lock = threading.Lock()

        infrastructure = EdgeInfrastructure(mock_edge_config)

        # Initialize components
        infrastructure.get_discovery()
        infrastructure.get_compliance_router()

        # Cleanup
        await infrastructure.cleanup()

        # Components should be cleared
        assert infrastructure._discovery is None
        assert infrastructure._compliance_router is None

        # Health should reflect cleanup
        health = infrastructure.get_health_status()
        assert health["discovery"]["initialized"] is False
        assert health["compliance"]["initialized"] is False

    def test_configuration_validation(self):
        """Test configuration validation and defaults."""
        from kailash.workflow.edge_infrastructure import EdgeInfrastructure

        # Clear any existing instance
        EdgeInfrastructure._instance = None
        EdgeInfrastructure._lock = threading.Lock()

        # Test with invalid config
        invalid_config = {"invalid": "config"}
        infrastructure = EdgeInfrastructure(invalid_config)

        # Should have default values
        assert "discovery" in infrastructure._config
        assert "compliance" in infrastructure._config
        assert "performance" in infrastructure._config

        # Test with partial config
        EdgeInfrastructure._instance = None
        partial_config = {"discovery": {"locations": ["us-east-1"]}}
        infrastructure = EdgeInfrastructure(partial_config)

        # Should merge with defaults
        assert infrastructure._config["discovery"]["locations"] == ["us-east-1"]
        assert "compliance" in infrastructure._config
        assert "performance" in infrastructure._config

    def test_resource_pooling(self, mock_edge_config):
        """Test resource pooling for edge connections."""
        from kailash.workflow.edge_infrastructure import EdgeInfrastructure

        # Clear any existing instance
        EdgeInfrastructure._instance = None
        EdgeInfrastructure._lock = threading.Lock()

        infrastructure = EdgeInfrastructure(mock_edge_config)

        # Get connection pool
        pool = infrastructure.get_connection_pool("us-east-1")
        assert pool is not None

        # Same location should return same pool
        pool2 = infrastructure.get_connection_pool("us-east-1")
        assert pool is pool2

        # Different location should return different pool
        pool3 = infrastructure.get_connection_pool("eu-west-1")
        assert pool3 is not pool

        # Pool size should respect config
        assert pool._max_size == mock_edge_config["performance"]["connection_pool_size"]

    def test_metrics_collection(self, mock_edge_config):
        """Test metrics collection and reporting."""
        from kailash.workflow.edge_infrastructure import EdgeInfrastructure

        # Clear any existing instance
        EdgeInfrastructure._instance = None
        EdgeInfrastructure._lock = threading.Lock()

        infrastructure = EdgeInfrastructure(mock_edge_config)

        # Initial metrics
        metrics = infrastructure.get_metrics()
        assert metrics["edge_nodes_registered"] == 0
        assert metrics["active_connections"] == 0
        assert metrics["total_requests"] == 0

        # Register an edge node
        infrastructure.register_edge_node("test-node-1", {"type": "EdgeDataNode"})

        metrics = infrastructure.get_metrics()
        assert metrics["edge_nodes_registered"] == 1

        # Record a request
        infrastructure.record_request("us-east-1", 25.5)

        metrics = infrastructure.get_metrics()
        assert metrics["total_requests"] == 1
        assert "us-east-1" in metrics["latency_by_location"]
        assert metrics["latency_by_location"]["us-east-1"]["avg"] == 25.5
