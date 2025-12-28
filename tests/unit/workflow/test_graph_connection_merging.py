"""Unit tests for graph connection merging functionality.

This module tests the critical fix for multiple connections between the same nodes
in workflow graphs. The fix ensures that when multiple connections are made between
the same pair of nodes, the connection mappings are merged rather than overwritten.

Key functionality tested:
- Single connection creation and storage
- Multiple connections between same nodes (the main bug fix)
- Edge data merging in NetworkX graphs
- Backward compatibility with existing connection formats
- Complex path mappings (e.g., "result.alerts", "result.needs_alerting")
- Error handling for duplicate connections
"""

from unittest.mock import MagicMock

import pytest
from kailash.workflow.graph import Workflow


class TestGraphConnectionMerging:
    """Unit tests for connection merging in workflow graphs."""

    @pytest.fixture
    def workflow(self):
        """Create a clean workflow for testing."""
        return Workflow(
            workflow_id="test_workflow_id",
            name="test_workflow",
            description="Test workflow for connection merging",
        )

    @pytest.fixture
    def mock_nodes(self, workflow):
        """Add mock nodes to the workflow for testing connections."""
        # Mock node classes
        mock_node_a = MagicMock()
        mock_node_a.__class__.__name__ = "MockNodeA"
        mock_node_b = MagicMock()
        mock_node_b.__class__.__name__ = "MockNodeB"

        # Add nodes to workflow's internal storage
        workflow.nodes["node_a"] = mock_node_a
        workflow.nodes["node_b"] = mock_node_b

        return {"node_a": mock_node_a, "node_b": mock_node_b}

    def test_single_connection_creation(self, workflow, mock_nodes):
        """Test that single connections are created correctly."""
        # Create a single connection
        workflow.connect(
            source_node="node_a", target_node="node_b", mapping={"output1": "input1"}
        )

        # Verify connection exists in graph
        assert workflow.graph.has_edge("node_a", "node_b")

        # Verify edge data structure
        edge_data = workflow.graph.get_edge_data("node_a", "node_b")
        assert "mapping" in edge_data
        assert edge_data["mapping"] == {"output1": "input1"}

        # Verify backward compatibility fields
        assert edge_data["from_output"] == "output1"
        assert edge_data["to_input"] == "input1"

    def test_multiple_connections_same_nodes(self, workflow, mock_nodes):
        """Test the core fix: multiple connections between same nodes are merged."""
        # First connection
        workflow.connect(
            source_node="node_a", target_node="node_b", mapping={"output1": "input1"}
        )

        # Second connection (should merge, not overwrite)
        workflow.connect(
            source_node="node_a", target_node="node_b", mapping={"output2": "input2"}
        )

        # Verify both connections are preserved
        edge_data = workflow.graph.get_edge_data("node_a", "node_b")
        expected_mapping = {"output1": "input1", "output2": "input2"}
        assert edge_data["mapping"] == expected_mapping

        # Verify backward compatibility for multiple connections
        assert set(edge_data["from_output"]) == {"output1", "output2"}
        assert set(edge_data["to_input"]) == {"input1", "input2"}

    def test_three_connections_merging(self, workflow, mock_nodes):
        """Test merging of three or more connections."""
        connections = [
            {"output1": "input1"},
            {"output2": "input2"},
            {"output3": "input3"},
        ]

        # Add connections one by one
        for mapping in connections:
            workflow.connect("node_a", "node_b", mapping)

        # Verify all three are merged
        edge_data = workflow.graph.get_edge_data("node_a", "node_b")
        expected_mapping = {
            "output1": "input1",
            "output2": "input2",
            "output3": "input3",
        }
        assert edge_data["mapping"] == expected_mapping

    def test_complex_path_mappings(self, workflow, mock_nodes):
        """Test merging with complex nested path mappings."""
        # First connection with nested path
        workflow.connect("node_a", "node_b", mapping={"result.alerts": "alerts"})

        # Second connection with another nested path
        workflow.connect(
            "node_a", "node_b", mapping={"result.needs_alerting": "needs_alerting"}
        )

        # Verify complex paths are preserved
        edge_data = workflow.graph.get_edge_data("node_a", "node_b")
        expected_mapping = {
            "result.alerts": "alerts",
            "result.needs_alerting": "needs_alerting",
        }
        assert edge_data["mapping"] == expected_mapping

    def test_duplicate_connection_rejection(self, workflow, mock_nodes):
        """Test that truly duplicate connections are rejected."""
        # First connection
        workflow.connect("node_a", "node_b", mapping={"output1": "input1"})

        # Attempt duplicate connection (same mapping)
        with pytest.raises(Exception) as exc_info:
            workflow.connect("node_a", "node_b", mapping={"output1": "input1"})

        assert "Duplicate connection" in str(exc_info.value)

    def test_mixed_single_and_multiple_mappings(self, workflow, mock_nodes):
        """Test mixing single and multiple mappings in connections."""
        # Single mapping first
        workflow.connect("node_a", "node_b", mapping={"output1": "input1"})

        # Multiple mappings in second connection
        workflow.connect(
            "node_a", "node_b", mapping={"output2": "input2", "output3": "input3"}
        )

        # Verify all mappings merged
        edge_data = workflow.graph.get_edge_data("node_a", "node_b")
        expected_mapping = {
            "output1": "input1",
            "output2": "input2",
            "output3": "input3",
        }
        assert edge_data["mapping"] == expected_mapping

    def test_connection_merging_preserves_order(self, workflow, mock_nodes):
        """Test that connection merging preserves the order mappings were added."""
        mappings = [{"a": "1"}, {"b": "2"}, {"c": "3"}, {"d": "4"}]

        for mapping in mappings:
            workflow.connect("node_a", "node_b", mapping)

        edge_data = workflow.graph.get_edge_data("node_a", "node_b")

        # All mappings should be present
        assert len(edge_data["mapping"]) == 4
        for mapping in mappings:
            for key, value in mapping.items():
                assert edge_data["mapping"][key] == value

    def test_connection_list_tracking(self, workflow, mock_nodes):
        """Test that the connections list tracks all individual connections."""
        # Add multiple connections
        workflow.connect("node_a", "node_b", mapping={"output1": "input1"})
        workflow.connect("node_a", "node_b", mapping={"output2": "input2"})

        # Verify connections list has both connections
        connections_to_b = [
            c
            for c in workflow.connections
            if c.source_node == "node_a" and c.target_node == "node_b"
        ]
        assert len(connections_to_b) == 2

        # Verify individual connection data
        outputs = {c.source_output for c in connections_to_b}
        inputs = {c.target_input for c in connections_to_b}
        assert outputs == {"output1", "output2"}
        assert inputs == {"input1", "input2"}

    def test_edge_case_empty_mapping(self, workflow, mock_nodes):
        """Test handling of empty mappings (should use default)."""
        workflow.connect("node_a", "node_b", mapping=None)

        edge_data = workflow.graph.get_edge_data("node_a", "node_b")
        # Should use default mapping
        assert edge_data["mapping"] == {"output": "input"}

    def test_different_node_pairs_independent(self, workflow, mock_nodes):
        """Test that connections between different node pairs are independent."""
        # Add third node
        mock_node_c = MagicMock()
        mock_node_c.__class__.__name__ = "MockNodeC"
        workflow.nodes["node_c"] = mock_node_c

        # Connections between different pairs
        workflow.connect("node_a", "node_b", mapping={"out1": "in1"})
        workflow.connect("node_a", "node_c", mapping={"out2": "in2"})
        workflow.connect("node_b", "node_c", mapping={"out3": "in3"})

        # Verify each pair has independent edge data
        edge_ab = workflow.graph.get_edge_data("node_a", "node_b")
        edge_ac = workflow.graph.get_edge_data("node_a", "node_c")
        edge_bc = workflow.graph.get_edge_data("node_b", "node_c")

        assert edge_ab["mapping"] == {"out1": "in1"}
        assert edge_ac["mapping"] == {"out2": "in2"}
        assert edge_bc["mapping"] == {"out3": "in3"}

    def test_connection_merging_real_world_scenario(self, workflow, mock_nodes):
        """Test the exact scenario that caused the original bug."""
        # Simulate monitoring workflow with health evaluation and alerting

        # Mock additional nodes for realistic scenario
        mock_health = MagicMock()
        mock_health.__class__.__name__ = "HealthEvaluatorNode"
        mock_alerts = MagicMock()
        mock_alerts.__class__.__name__ = "AlertSenderNode"

        workflow.nodes["evaluate_health"] = mock_health
        workflow.nodes["send_alerts"] = mock_alerts

        # The connections that were failing before the fix
        workflow.connect(
            "evaluate_health", "send_alerts", mapping={"result.alerts": "alerts"}
        )
        workflow.connect(
            "evaluate_health",
            "send_alerts",
            mapping={"result.needs_alerting": "needs_alerting"},
        )

        # Verify the exact mapping structure expected by runtime
        edge_data = workflow.graph.get_edge_data("evaluate_health", "send_alerts")
        expected_mapping = {
            "result.alerts": "alerts",
            "result.needs_alerting": "needs_alerting",
        }
        assert edge_data["mapping"] == expected_mapping

    def test_regression_no_connection_overwrite(self, workflow, mock_nodes):
        """Regression test: ensure mappings aren't overwritten."""
        # First connection
        workflow.connect(
            "node_a", "node_b", mapping={"important_data": "critical_input"}
        )

        # Verify first connection is stored
        edge_data = workflow.graph.get_edge_data("node_a", "node_b")
        assert "important_data" in edge_data["mapping"]
        assert edge_data["mapping"]["important_data"] == "critical_input"

        # Second connection
        workflow.connect("node_a", "node_b", mapping={"additional_data": "extra_input"})

        # Verify BOTH connections are preserved (regression test)
        edge_data = workflow.graph.get_edge_data("node_a", "node_b")
        assert "important_data" in edge_data["mapping"]  # Must not be lost!
        assert "additional_data" in edge_data["mapping"]
        assert edge_data["mapping"]["important_data"] == "critical_input"
        assert edge_data["mapping"]["additional_data"] == "extra_input"

    def test_connection_merging_with_networkx_graph(self, workflow, mock_nodes):
        """Test that NetworkX graph structure is correct after merging."""
        # Add connections
        workflow.connect("node_a", "node_b", mapping={"out1": "in1"})
        workflow.connect("node_a", "node_b", mapping={"out2": "in2"})

        # Verify NetworkX graph structure
        assert len(workflow.graph.edges()) == 1  # Still one edge
        assert workflow.graph.has_edge("node_a", "node_b")

        # Verify no duplicate edges created
        edges_between = list(workflow.graph.edges("node_a"))
        edges_to_b = [edge for edge in edges_between if edge[1] == "node_b"]
        assert len(edges_to_b) == 1

    def test_backward_compatibility_single_connection(self, workflow, mock_nodes):
        """Test backward compatibility fields for single connections."""
        workflow.connect("node_a", "node_b", mapping={"single_out": "single_in"})

        edge_data = workflow.graph.get_edge_data("node_a", "node_b")

        # For single connections, should be strings (backward compatibility)
        assert edge_data["from_output"] == "single_out"
        assert edge_data["to_input"] == "single_in"
        assert isinstance(edge_data["from_output"], str)
        assert isinstance(edge_data["to_input"], str)

    def test_backward_compatibility_multiple_connections(self, workflow, mock_nodes):
        """Test backward compatibility fields for multiple connections."""
        workflow.connect("node_a", "node_b", mapping={"out1": "in1"})
        workflow.connect("node_a", "node_b", mapping={"out2": "in2"})

        edge_data = workflow.graph.get_edge_data("node_a", "node_b")

        # For multiple connections, should be lists
        assert isinstance(edge_data["from_output"], list)
        assert isinstance(edge_data["to_input"], list)
        assert set(edge_data["from_output"]) == {"out1", "out2"}
        assert set(edge_data["to_input"]) == {"in1", "in2"}
