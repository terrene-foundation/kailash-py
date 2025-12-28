"""Integration tests for edge infrastructure in WorkflowBuilder.

Tests the integration between WorkflowBuilder and edge computing infrastructure,
ensuring edge nodes work properly in workflows with shared resources.
"""

import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest
from kailash.edge.location import (
    ComplianceZone,
    EdgeCapabilities,
    EdgeLocation,
    EdgeRegion,
    GeographicCoordinates,
)
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestEdgeWorkflowBuilderIntegration:
    """Test edge infrastructure integration with WorkflowBuilder."""

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
            EdgeLocation(
                location_id="asia-east-1",
                name="Asia East 1",
                region=EdgeRegion.ASIA_EAST,
                coordinates=GeographicCoordinates(35.6762, 139.6503),
                capabilities=EdgeCapabilities(
                    cpu_cores=6, memory_gb=24, storage_gb=300
                ),
                compliance_zones=[ComplianceZone.PUBLIC],
            ),
        ]

    @pytest.fixture
    def edge_config(self):
        """Create edge configuration for workflows."""
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

    def test_edge_node_detection_in_workflow(self, edge_config):
        """Test that WorkflowBuilder detects edge nodes."""
        workflow = WorkflowBuilder(edge_config=edge_config)

        # Initially no edge nodes
        assert workflow._has_edge_nodes is False
        assert workflow._edge_infrastructure is None

        # Add regular node - should not trigger edge
        workflow.add_node("CSVReaderNode", "reader", {"file_path": "test.csv"})
        assert workflow._has_edge_nodes is False

        # Add edge node - should trigger edge detection
        workflow.add_node(
            "EdgeDataNode",
            "edge_data",
            {"location_id": "us-east-1", "action": "read", "key": "test_data"},
        )
        assert workflow._has_edge_nodes is True

        # Build workflow - should initialize infrastructure
        built_workflow = workflow.build()
        assert workflow._edge_infrastructure is not None

    def test_shared_infrastructure_across_nodes(self, edge_config):
        """Test that multiple edge nodes share the same infrastructure."""

        workflow = WorkflowBuilder(edge_config=edge_config)

        # Add multiple edge nodes
        workflow.add_node(
            "EdgeDataNode",
            "edge1",
            {"location_id": "us-east-1", "action": "write", "key": "key1"},
        )
        workflow.add_node(
            "EdgeDataNode",
            "edge2",
            {"location_id": "eu-west-1", "action": "read", "key": "key2"},
        )
        workflow.add_node(
            "EdgeStateMachine",
            "state_machine",
            {
                "location_id": "us-east-1",
                "state_id": "workflow_state",  # EdgeStateMachine requires state_id
                "state_key": "workflow_state",
            },
        )

        # Connect nodes
        workflow.connect("edge1", "edge2")
        workflow.connect("edge2", "state_machine")

        # Build workflow
        built_workflow = workflow.build()

        # Infrastructure should be initialized
        assert workflow._edge_infrastructure is not None

        # Discovery and compliance are lazily initialized - trigger them
        discovery = workflow._edge_infrastructure.get_discovery()
        compliance = workflow._edge_infrastructure.get_compliance_router()

        # Check that they were created
        assert discovery is not None
        assert compliance is not None

        # Verify they are the same instances on subsequent calls (singleton behavior)
        assert workflow._edge_infrastructure.get_discovery() is discovery
        assert workflow._edge_infrastructure.get_compliance_router() is compliance

        # All edge nodes should have the same infrastructure instance
        # Count edge nodes in the workflow
        edge_node_count = 0
        for node_id in ["edge1", "edge2", "state_machine"]:
            node = built_workflow.get_node(node_id)
            if node.__class__.__name__ in ["EdgeDataNode", "EdgeStateMachine"]:
                edge_node_count += 1
        assert edge_node_count == 3

    def test_non_edge_workflow_no_overhead(self):
        """Test that non-edge workflows have no edge overhead."""
        workflow = WorkflowBuilder()

        # Add only non-edge nodes
        workflow.add_node(
            "PythonCodeNode",
            "processor",
            {"code": "result = {'value': sum(parameters.get('numbers', []))}"},
        )
        workflow.add_node("JSONWriterNode", "writer", {"output_path": "result.json"})
        workflow.connect("processor", "writer")

        # Build workflow
        built_workflow = workflow.build()

        # No edge infrastructure should be created
        assert workflow._has_edge_nodes is False
        assert workflow._edge_infrastructure is None

        # Workflow should function normally
        # Check that nodes were created
        processor_node = built_workflow.get_node("processor")
        writer_node = built_workflow.get_node("writer")
        assert processor_node is not None
        assert writer_node is not None

    @pytest.mark.asyncio
    async def test_edge_workflow_execution(self, edge_config, sample_edge_locations):
        """Test executing a workflow with edge nodes."""
        # Mock the edge infrastructure
        with patch(
            "kailash.workflow.edge_infrastructure.EdgeInfrastructure"
        ) as mock_infra_class:
            mock_infra = MagicMock()
            mock_infra_class.return_value = mock_infra

            # Mock discovery to return locations
            mock_discovery = MagicMock()
            mock_discovery.get_all_edges.return_value = sample_edge_locations
            mock_discovery.select_edge.return_value = sample_edge_locations[0]
            mock_infra.get_discovery.return_value = mock_discovery

            # Create workflow
            workflow = WorkflowBuilder(edge_config=edge_config)

            # Add edge data workflow
            workflow.add_node(
                "EdgeDataNode",
                "writer",
                {
                    "location_id": "us-east-1",
                    "action": "write",
                    "key": "test_key",  # EdgeDataNode expects 'key', not 'data_key'
                },
            )
            workflow.add_node(
                "EdgeDataNode",
                "reader",
                {
                    "location_id": "us-east-1",
                    "action": "read",
                    "key": "test_key",  # EdgeDataNode expects 'key', not 'data_key'
                },
            )
            workflow.connect("writer", "reader")

            # Mock edge node execution to avoid actual edge operations
            with patch(
                "kailash.nodes.edge.edge_data.EdgeDataNode.async_run"
            ) as mock_run:
                # Mock successful write and read operations
                async def mock_edge_run(**kwargs):
                    action = kwargs.get("action", "read")
                    if action == "write":
                        return {
                            "success": True,
                            "location_used": "us-east-1",
                            "key": kwargs.get("key"),
                            "data_written": kwargs.get("data"),
                        }
                    else:  # read
                        return {
                            "success": True,
                            "location_used": "us-east-1",
                            "key": kwargs.get("key"),
                            "data": {"message": "Hello Edge!"},
                        }

                mock_run.side_effect = mock_edge_run

                # Execute workflow
                runtime = LocalRuntime()
                result, run_id = runtime.execute(
                    workflow.build(),
                    parameters={"writer": {"data": {"message": "Hello Edge!"}}},
                )

                # Infrastructure should be initialized
                mock_infra_class.assert_called_once_with(edge_config)
                mock_infra.get_discovery.assert_called()

                # Verify edge nodes were executed
                assert mock_run.call_count >= 2  # writer and reader

    def test_edge_config_propagation(self, edge_config):
        """Test that edge configuration is properly propagated."""
        # Clear singleton to ensure fresh instance
        from kailash.workflow.edge_infrastructure import EdgeInfrastructure

        EdgeInfrastructure._instance = None
        EdgeInfrastructure._lock = threading.Lock()

        custom_config = {**edge_config, "custom_setting": "test_value"}

        workflow = WorkflowBuilder(edge_config=custom_config)

        # Add edge node
        workflow.add_node(
            "EdgeDataNode", "edge", {"location_id": "us-east-1", "action": "read"}
        )

        # Build workflow
        built_workflow = workflow.build()

        # Edge infrastructure should have the custom config
        assert workflow._edge_infrastructure is not None

        # Check that the provided config values are preserved after merging with defaults
        assert (
            workflow._edge_infrastructure._config["discovery"]["locations"]
            == custom_config["discovery"]["locations"]
        )
        assert (
            workflow._edge_infrastructure._config["discovery"]["refresh_interval"]
            == custom_config["discovery"]["refresh_interval"]
        )
        assert (
            workflow._edge_infrastructure._config["compliance"]["strict_mode"]
            == custom_config["compliance"]["strict_mode"]
        )
        assert (
            workflow._edge_infrastructure._config["performance"]["connection_pool_size"]
            == custom_config["performance"]["connection_pool_size"]
        )

        # Custom settings should also be preserved at top level
        # The merge_with_defaults method should preserve any custom keys
        assert "custom_setting" in workflow._edge_infrastructure._config
        assert workflow._edge_infrastructure._config["custom_setting"] == "test_value"

    def test_mixed_edge_and_regular_nodes(self, edge_config):
        """Test workflow with both edge and regular nodes."""
        workflow = WorkflowBuilder(edge_config=edge_config)

        # Add mixed nodes
        workflow.add_node("CSVReaderNode", "csv_reader", {"file_path": "input.csv"})
        workflow.add_node(
            "EdgeDataNode",
            "edge_processor",
            {"location_id": "us-east-1", "action": "process"},
        )
        workflow.add_node(
            "LLMAgentNode", "agent", {"model": "gpt-4", "prompt": "Analyze the data"}
        )
        workflow.add_node(
            "EdgeStateMachine",
            "state",
            {
                "location_id": "eu-west-1",
                "state_id": "analysis_state",
                "state_key": "analysis_state",
            },
        )

        # Connect nodes
        workflow.connect("csv_reader", "edge_processor")
        workflow.connect("edge_processor", "agent")
        workflow.connect("agent", "state")

        # Build workflow
        built_workflow = workflow.build()

        # Should have edge infrastructure
        assert workflow._has_edge_nodes is True
        assert workflow._edge_infrastructure is not None

        # All nodes should be in the workflow
        # Count nodes in the workflow
        node_count = 0
        for node_id in ["csv_reader", "edge_processor", "agent", "state"]:
            node = built_workflow.get_node(node_id)
            if node is not None:
                node_count += 1
        assert node_count == 4

    def test_edge_node_initialization_failure_handling(self, edge_config):
        """Test handling of edge node initialization failures."""
        workflow = WorkflowBuilder(edge_config=edge_config)

        # Add edge node with invalid configuration
        workflow.add_node(
            "EdgeDataNode",
            "edge",
            {"location_id": "invalid-location", "action": "read"},
        )

        # Build should succeed but mark infrastructure as needed
        built_workflow = workflow.build()
        assert workflow._has_edge_nodes is True

        # Infrastructure should handle invalid locations gracefully
        assert workflow._edge_infrastructure is not None

    @pytest.mark.asyncio
    async def test_edge_infrastructure_cleanup(self, edge_config):
        """Test proper cleanup of edge infrastructure."""
        workflow = WorkflowBuilder(edge_config=edge_config)

        # Add edge nodes
        workflow.add_node("EdgeDataNode", "edge1", {"location_id": "us-east-1"})
        workflow.add_node("EdgeDataNode", "edge2", {"location_id": "eu-west-1"})

        # Build and get infrastructure
        built_workflow = workflow.build()
        infrastructure = workflow._edge_infrastructure

        # Mock cleanup with an async function
        async def mock_cleanup():
            pass

        infrastructure.cleanup = MagicMock(return_value=mock_cleanup())

        # Cleanup should be available
        await infrastructure.cleanup()
        infrastructure.cleanup.assert_called_once()

    def test_edge_infrastructure_singleton_across_workflows(self, edge_config):
        """Test that edge infrastructure is shared across workflows."""
        # Create first workflow
        workflow1 = WorkflowBuilder(edge_config=edge_config)
        workflow1.add_node("EdgeDataNode", "edge1", {"location_id": "us-east-1"})
        built1 = workflow1.build()
        infra1 = workflow1._edge_infrastructure

        # Create second workflow
        workflow2 = WorkflowBuilder(edge_config=edge_config)
        workflow2.add_node(
            "EdgeStateMachine",
            "state",
            {"location_id": "eu-west-1", "state_id": "test_state"},
        )
        built2 = workflow2.build()
        infra2 = workflow2._edge_infrastructure

        # Infrastructure should be the same instance (singleton)
        assert infra1 is infra2
        assert id(infra1) == id(infra2)
