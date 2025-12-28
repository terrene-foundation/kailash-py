"""Test visualization with real workflows."""

from pathlib import Path

import pytest
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.transform import DataTransformer
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
        assert output_path.stat().st_size > 0  # File has content

        # Test TODO-111: Visualizer with optional workflow parameter
        visualizer_no_workflow = WorkflowVisualizer()  # No workflow in constructor
        assert visualizer_no_workflow.workflow is None
        visualizer_no_workflow.workflow = workflow

        output_path2 = temp_data_dir / "workflow2.png"
        visualizer_no_workflow.visualize(output_path=str(output_path2))
        assert output_path2.exists()

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

        # Test TODO-111: New methods exist
        assert hasattr(visualizer, "_draw_graph")
        assert hasattr(visualizer, "_get_layout_positions")
        assert hasattr(visualizer, "_get_node_colors")

        # Test visualization methods work
        visualizer.visualize()  # Should not raise
        mermaid_content = mermaid.generate()  # Should not raise
        assert mermaid_content  # Should produce content

        # Test TODO-111: _draw_graph with workflow parameter
        builder2 = WorkflowBuilder()
        builder2.add_node("PythonCodeNode", "python_node", {"code": "result = 42"})
        workflow2 = builder2.build("test2")

        # Should be able to draw different workflow
        import matplotlib.pyplot as plt

        plt.figure()
        visualizer._draw_graph(workflow=workflow2)
        plt.close()  # Clean up

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

    def test_visualizer_with_cyclic_workflow(self, temp_data_dir: Path):
        """Test TODO-111: Visualizing cyclic workflows."""
        # Create workflow with cycle
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "node1",
            {"code": "result = {'value': input.get('value', 0) + 1}"},
        )
        builder.add_node(
            "PythonCodeNode",
            "node2",
            {"code": "result = {'converged': input['value'] > 5}"},
        )

        # Regular connection
        builder.add_connection("node1", "result", "node2", "input")

        # Build workflow first
        workflow = builder.build("cyclic_test")

        # Then create cycle
        workflow.create_cycle("test_cycle").connect(
            "node2", "node1", {"result.value": "input.value"}
        ).max_iterations(3).build()

        # Visualize cyclic workflow
        visualizer = WorkflowVisualizer(workflow)
        output_path = temp_data_dir / "cyclic_workflow.png"
        visualizer.visualize(output_path=str(output_path))

        assert output_path.exists()
        assert output_path.stat().st_size > 0

        # Edge colors should exist
        assert "default" in visualizer.edge_colors
        assert visualizer.edge_colors["default"] == "gray"

    def test_node_color_mapping(self, temp_data_dir: Path):
        """Test TODO-111: Node color mapping by type."""
        # Create workflow with different node types
        builder = WorkflowBuilder()
        builder.add_node("CSVReaderNode", "data_node", config={"file_path": "test.csv"})
        builder.add_node("DataTransformer", "transform_node")
        builder.add_node("PythonCodeNode", "python_node", {"code": "result = data"})

        # Add AI-like node (name contains 'llm')
        builder.add_node("PythonCodeNode", "llm_processor", {"code": "result = 'ai'"})

        # Connect them
        builder.add_connection("data_node", "data", "transform_node", "data")
        builder.add_connection("transform_node", "data", "python_node", "data")

        workflow = builder.build("color_test")

        visualizer = WorkflowVisualizer(workflow)

        # Test _get_node_colors method
        colors = visualizer._get_node_colors(workflow)

        # Should have color for each node
        assert len(colors) == 4

        # Verify color categories
        assert visualizer.node_colors["data"] in colors  # CSV node
        assert visualizer.node_colors["transform"] in colors  # Transform & Python nodes

    def test_custom_colors_and_layout(self, temp_data_dir: Path):
        """Test TODO-111: Custom colors and layouts."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "node1", {"code": "result = 1"})
        builder.add_node("PythonCodeNode", "node2", {"code": "result = 2"})
        builder.add_connection("node1", "result", "node2", "input")

        workflow = builder.build("custom_test")

        # Test with custom colors
        custom_node_colors = {"default": "#FF00FF", "transform": "#00FF00"}
        custom_edge_colors = {"default": "#0000FF"}

        # Test different layouts
        for layout in ["hierarchical", "circular", "spring"]:
            visualizer = WorkflowVisualizer(
                workflow,
                node_colors=custom_node_colors,
                edge_colors=custom_edge_colors,
                layout=layout,
            )

            output_path = temp_data_dir / f"custom_{layout}.png"
            visualizer.visualize(output_path=str(output_path))

            assert output_path.exists()

    def test_draw_graph_error_handling(self):
        """Test TODO-111: Error handling in _draw_graph."""
        import pytest

        # Create visualizer without workflow
        visualizer = WorkflowVisualizer()

        # Should raise error when no workflow provided
        with pytest.raises(ValueError, match="No workflow provided to draw"):
            visualizer._draw_graph()
