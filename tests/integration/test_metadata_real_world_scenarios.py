"""
Integration tests for metadata parameter fix with real-world scenarios.

Tests actual workflow execution, monitoring nodes, CLI access, and DataFlow integration.
"""

from typing import Any, Dict, Optional

import pytest
from kailash.nodes.base import Node, NodeParameter, NodeRegistry
from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class ChunkerNode(Node):
    """Simulates chunker node that might have metadata parameter."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "text": NodeParameter(
                name="text", type=str, required=True, description="Text to chunk"
            ),
            "chunk_size": NodeParameter(
                name="chunk_size",
                type=int,
                required=False,
                default=100,
                description="Chunk size",
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=False,
                default=None,
                description="Metadata to attach to each chunk",
            ),
        }

    def run(
        self,
        text: str,
        chunk_size: int = 100,
        metadata: Optional[dict] = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Chunk text and attach metadata."""
        chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

        return {
            "chunks": chunks,
            "chunk_count": len(chunks),
            "metadata": metadata,  # Return the metadata that was passed
            "node_name": self.metadata.name,  # Access internal NodeMetadata
        }


class MonitoringNode(Node):
    """Simulates monitoring node that tracks metadata."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation to monitor",
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=False,
                default=None,
                description="Monitoring metadata",
            ),
        }

    def run(
        self, operation: str, metadata: Optional[dict] = None, **kwargs
    ) -> dict[str, Any]:
        """Monitor operation with metadata."""
        return {
            "operation": operation,
            "monitored": True,
            "monitoring_metadata": metadata,
            "node_description": self.metadata.description,  # Access internal NodeMetadata
        }


class TransformNode(Node):
    """Node that transforms data and preserves metadata."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data", type=str, required=True, description="Data to transform"
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=False,
                default=None,
                description="Metadata to preserve",
            ),
        }

    def run(
        self, data: str, metadata: Optional[dict] = None, **kwargs
    ) -> dict[str, Any]:
        """Transform data and preserve metadata."""
        transformed = data.upper()
        return {
            "transformed_data": transformed,
            "original_metadata": metadata,
            "node_id": self.id,  # Access internal _node_id via property
        }


class TestRealWorldScenarios:
    """Integration tests for real-world metadata usage."""

    @pytest.fixture(autouse=True)
    def register_nodes(self):
        """Register test nodes."""
        NodeRegistry.register(ChunkerNode)
        NodeRegistry.register(MonitoringNode)
        NodeRegistry.register(TransformNode)
        yield
        NodeRegistry.unregister("ChunkerNode")
        NodeRegistry.unregister("MonitoringNode")
        NodeRegistry.unregister("TransformNode")

    def test_chunker_with_metadata_parameter(self):
        """Test chunker node with metadata parameter."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ChunkerNode",
            "chunker",
            {
                "text": "Hello World! This is a test of chunking with metadata.",
                "chunk_size": 10,
                "metadata": {"source": "test", "author": "Alice"},
            },
        )

        with LocalRuntime() as runtime:
            results, _ = runtime.execute(workflow.build())

        result = results["chunker"]
        assert result["chunk_count"] > 0
        assert result["metadata"] == {"source": "test", "author": "Alice"}
        assert result["node_name"] == "ChunkerNode"

    def test_monitoring_node_with_metadata(self):
        """Test monitoring node with metadata parameter."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "MonitoringNode",
            "monitor",
            {
                "operation": "data_processing",
                "metadata": {"environment": "test", "version": "1.0"},
            },
        )

        with LocalRuntime() as runtime:
            results, _ = runtime.execute(workflow.build())

        result = results["monitor"]
        assert result["operation"] == "data_processing"
        assert result["monitored"] is True
        assert result["monitoring_metadata"] == {
            "environment": "test",
            "version": "1.0",
        }
        assert result["node_description"] != ""  # Has default description

    def test_metadata_flow_through_pipeline(self):
        """Test metadata flowing through a multi-node pipeline."""
        workflow = WorkflowBuilder()

        # Node 1: Chunker with metadata
        workflow.add_node(
            "ChunkerNode",
            "chunker",
            {
                "text": "Hello World",
                "chunk_size": 5,
                "metadata": {"pipeline": "test", "step": 1},
            },
        )

        # Node 2: Transform receives metadata from chunker
        workflow.add_node(
            "TransformNode",
            "transform",
            {
                "data": "dummy",  # Will be overridden by connection
            },
        )

        # Connect chunker chunks to transform data
        workflow.add_connection("chunker", "chunks", "transform", "data")
        workflow.add_connection("chunker", "metadata", "transform", "metadata")

        with LocalRuntime() as runtime:
            results, _ = runtime.execute(workflow.build())

        chunker_result = results["chunker"]
        transform_result = results["transform"]

        # Verify chunker metadata
        assert chunker_result["metadata"] == {"pipeline": "test", "step": 1}

        # Verify transform received metadata via connection
        assert transform_result["original_metadata"] == {"pipeline": "test", "step": 1}

    def test_multiple_nodes_with_different_metadata(self):
        """Test multiple nodes each with their own metadata parameters."""
        workflow = WorkflowBuilder()

        workflow.add_node(
            "ChunkerNode",
            "chunker1",
            {"text": "Text 1", "metadata": {"source": "file1.txt", "type": "doc"}},
        )

        workflow.add_node(
            "ChunkerNode",
            "chunker2",
            {"text": "Text 2", "metadata": {"source": "file2.txt", "type": "email"}},
        )

        workflow.add_node(
            "MonitoringNode",
            "monitor",
            {
                "operation": "chunking",
                "metadata": {"monitored_nodes": ["chunker1", "chunker2"]},
            },
        )

        with LocalRuntime() as runtime:
            results, _ = runtime.execute(workflow.build())

        # Each node should have received its own metadata
        assert results["chunker1"]["metadata"] == {"source": "file1.txt", "type": "doc"}
        assert results["chunker2"]["metadata"] == {
            "source": "file2.txt",
            "type": "email",
        }
        assert results["monitor"]["monitoring_metadata"] == {
            "monitored_nodes": ["chunker1", "chunker2"]
        }

    def test_node_metadata_property_access_during_execution(self):
        """Test that internal NodeMetadata is accessible during execution."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ChunkerNode", "chunker", {"text": "Test", "metadata": {"user": "data"}}
        )

        with LocalRuntime() as runtime:
            results, _ = runtime.execute(workflow.build())

        result = results["chunker"]

        # Node should have accessed internal NodeMetadata.name
        assert result["node_name"] == "ChunkerNode"

        # And also received user metadata
        assert result["metadata"] == {"user": "data"}

    def test_metadata_with_none_value(self):
        """Test explicit None for metadata parameter."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ChunkerNode",
            "chunker",
            {"text": "Test", "metadata": None},  # Explicit None
        )

        with LocalRuntime() as runtime:
            results, _ = runtime.execute(workflow.build())

        result = results["chunker"]
        assert result["metadata"] is None

    def test_metadata_omitted_uses_default(self):
        """Test that omitted metadata uses default value."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ChunkerNode",
            "chunker",
            {
                "text": "Test"
                # metadata omitted
            },
        )

        with LocalRuntime() as runtime:
            results, _ = runtime.execute(workflow.build())

        result = results["chunker"]
        assert result["metadata"] is None  # Default value

    def test_complex_nested_metadata(self):
        """Test complex nested metadata structures."""
        complex_metadata = {
            "author": {
                "name": "Alice Smith",
                "email": "alice@example.com",
                "roles": ["admin", "editor"],
            },
            "tags": ["important", "reviewed"],
            "processing": {
                "timestamp": "2025-01-01T00:00:00Z",
                "version": 2,
                "flags": {"validated": True, "encrypted": False},
            },
        }

        workflow = WorkflowBuilder()
        workflow.add_node(
            "ChunkerNode",
            "chunker",
            {"text": "Complex test", "metadata": complex_metadata},
        )

        with LocalRuntime() as runtime:
            results, _ = runtime.execute(workflow.build())

        result = results["chunker"]
        assert result["metadata"] == complex_metadata
        assert result["metadata"]["author"]["name"] == "Alice Smith"
        assert result["metadata"]["processing"]["flags"]["validated"] is True

    def test_serialization_with_metadata_parameter(self):
        """Test workflow serialization preserves metadata parameter."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ChunkerNode", "chunker", {"text": "Test", "metadata": {"key": "value"}}
        )

        # Serialize
        built_workflow = workflow.build()
        workflow_dict = {
            "nodes": {
                node_id: {"type": node_data.node_type, "config": node_data.config}
                for node_id, node_data in built_workflow.nodes.items()
            }
        }

        # Verify metadata parameter in serialized form
        assert "metadata" in workflow_dict["nodes"]["chunker"]["config"]
        assert workflow_dict["nodes"]["chunker"]["config"]["metadata"] == {
            "key": "value"
        }

    def test_multiple_workflows_with_same_node_different_metadata(self):
        """Test that different workflow instances maintain separate metadata."""
        # Workflow 1
        workflow1 = WorkflowBuilder()
        workflow1.add_node(
            "ChunkerNode", "chunker", {"text": "Text 1", "metadata": {"workflow": "1"}}
        )

        # Workflow 2
        workflow2 = WorkflowBuilder()
        workflow2.add_node(
            "ChunkerNode", "chunker", {"text": "Text 2", "metadata": {"workflow": "2"}}
        )

        with LocalRuntime() as runtime:
            results1, _ = runtime.execute(workflow1.build())
            results2, _ = runtime.execute(workflow2.build())

        # Each workflow should have its own metadata
        assert results1["chunker"]["metadata"] == {"workflow": "1"}
        assert results2["chunker"]["metadata"] == {"workflow": "2"}


class TestBackwardCompatibility:
    """Test backward compatibility with existing code."""

    @pytest.fixture(autouse=True)
    def register_nodes(self):
        NodeRegistry.register(ChunkerNode)
        yield
        NodeRegistry.unregister("ChunkerNode")

    def test_node_instance_metadata_property(self):
        """Test that existing code accessing node.metadata still works."""
        # Create node instance
        node = ChunkerNode(text="Test", metadata={"user": "data"})

        # Access internal NodeMetadata via property (backward compat)
        assert hasattr(node, "metadata")
        assert node.metadata.name == "ChunkerNode"
        assert hasattr(node.metadata, "description")

        # User metadata should be in config
        assert node.config.get("metadata") == {"user": "data"}

    def test_node_to_dict_serialization(self):
        """Test that node.to_dict() still works correctly."""
        node = ChunkerNode(text="Test", metadata={"user": "data"})

        node_dict = node.to_dict()

        # Should serialize internal NodeMetadata
        assert "metadata" in node_dict
        assert node_dict["metadata"]["name"] == "ChunkerNode"

        # User metadata should be in config
        assert node_dict["config"]["metadata"] == {"user": "data"}
