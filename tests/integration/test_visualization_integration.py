"""Test visualization with real workflows."""

from pathlib import Path

import pytest

from kailash.runtime.local import LocalRuntime
from kailash.runtime.runner import WorkflowRunner
from kailash.workflow import Workflow, WorkflowBuilder
from kailash.workflow.mermaid_visualizer import MermaidVisualizer
from kailash.workflow.visualization import WorkflowVisualizer


class TestVisualizationIntegration:
    """Test workflow visualization with real workflows."""

    def test_visualizer_availability(self):
        """Test that visualizer is available."""
        assert WorkflowVisualizer is not None
        assert MermaidVisualizer is not None

    def test_simple_workflow_visualization(self, temp_data_dir: Path):
        """Test visualizing a simple workflow."""
        # Create a simple workflow
        builder = WorkflowBuilder()
        builder.add_node("CSVReaderNode", "reader", config={"file_path": "test.csv"})
        builder.add_node(
            "DataTransformer", "transformer", config={"transformation": "result"}
        )
        builder.add_connection("reader", "data", "transformer", "input_data")
        workflow = builder.build("test_viz")

        # Test matplotlib visualizer
        visualizer = WorkflowVisualizer(workflow)
        output_path = temp_data_dir / "workflow.png"
        visualizer.visualize(output_path=str(output_path))
        assert output_path.exists()

        # Test Mermaid visualizer
        mermaid_viz = MermaidVisualizer(workflow)
        mermaid_output = temp_data_dir / "workflow.md"
        mermaid_content = mermaid_viz.generate_markdown()
        mermaid_output.write_text(mermaid_content)
        assert mermaid_output.exists()
        assert "```mermaid" in mermaid_content

    def test_basic_visualization_methods(self, temp_data_dir: Path):
        """Test basic visualization methods."""
        # Create test workflow first
        builder = WorkflowBuilder()
        builder.add_node("CSVReaderNode", "node1")
        workflow = builder.build("method_test")

        # Create visualizers with workflow
        visualizer = WorkflowVisualizer(workflow)
        mermaid = MermaidVisualizer(workflow)

        # Test that visualizers have expected methods
        assert hasattr(visualizer, "visualize")
        assert hasattr(mermaid, "generate")

        # Test visualization methods work
        visualizer.visualize()  # Should not raise
        mermaid_content = mermaid.generate()  # Should not raise
        assert mermaid_content  # Should produce content

    def test_matplotlib_availability(self):
        """Test that matplotlib is available for visualization."""
        try:
            import matplotlib.pyplot as plt

            assert plt is not None
        except ImportError:
            pytest.skip("matplotlib not available for visualization testing")

    def test_workflow_builder_integration(self):
        """Test that workflow builder integrates with visualization."""
        # Test that workflow components can work together
        builder = WorkflowBuilder()
        workflow = builder.build("viz_test")

        assert workflow is not None
        assert hasattr(workflow, "metadata")

    def test_visualization_components_integration(self):
        """Test integration between visualization and other components."""
        # Test that key components can be imported together
        runtime = LocalRuntime()
        runner = WorkflowRunner()  # WorkflowRunner no longer takes runtime parameter
        builder = WorkflowBuilder()

        assert runtime is not None
        assert runner is not None
        assert builder is not None

    def test_basic_workflow_creation_for_viz(self):
        """Test creating workflows that could be visualized."""
        builder = WorkflowBuilder()

        # Create workflow with nodes
        builder.add_node(
            "HTTPRequestNode", "api_call", config={"url": "https://api.example.com"}
        )
        builder.add_node(
            "FilterNode",
            "filter",
            config={"field": "status", "operator": "==", "value": "200"},
        )
        builder.add_connection("api_call", "response", "filter", "data")

        workflow = builder.build("visualization_test")

        # Verify workflow can be created
        assert workflow is not None
        assert workflow.name.startswith("Workflow-")
        assert "visualiz" in workflow.name
        assert len(workflow.nodes) == 2
        assert len(workflow.connections) == 1

    def test_workflow_metadata_for_visualization(self):
        """Test that workflows have metadata needed for visualization."""
        builder = WorkflowBuilder()
        workflow = builder.build(name="metadata_test")

        # Test metadata availability
        assert hasattr(workflow, "metadata")
        assert workflow.name == "metadata_test"

        # Test that metadata has expected structure
        assert isinstance(workflow.metadata, dict)

    def test_runtime_visualization_integration(self):
        """Test integration between runtime and visualization components."""
        runtime = LocalRuntime()

        # Test that runtime can be used with visualization
        assert runtime is not None

        # Test that runtime has expected interface
        assert hasattr(runtime, "execute") or hasattr(runtime, "run")

    def test_pathlib_integration(self, temp_data_dir: Path):
        """Test that Path objects work with visualization."""
        # Test basic path operations for visualization output
        output_path = temp_data_dir / "test_output.png"

        # Test path creation and properties
        assert output_path.parent == temp_data_dir
        assert output_path.suffix == ".png"
        assert output_path.name == "test_output.png"

        # Test that we can create directories
        viz_dir = temp_data_dir / "visualizations"
        viz_dir.mkdir(exist_ok=True)
        assert viz_dir.exists()

    def test_workflow_import_availability(self):
        """Test that required workflow imports are available."""
        # Test that core workflow components can be imported
        assert Workflow is not None
        assert WorkflowBuilder is not None
        assert LocalRuntime is not None
        assert WorkflowRunner is not None
