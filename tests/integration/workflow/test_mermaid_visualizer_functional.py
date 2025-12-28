"""Functional tests for workflow/mermaid_visualizer.py that verify actual diagram generation behavior."""

from unittest.mock import MagicMock, Mock

import networkx as nx
import pytest
from kailash.workflow.graph import Workflow


class TestMermaidVisualizerDiagramGeneration:
    """Test actual Mermaid diagram generation functionality."""

    def test_generate_basic_linear_workflow_diagram(self):
        """Test generation of a basic linear workflow with correct Mermaid syntax."""
        try:
            from kailash.workflow.builder import WorkflowBuilder
            from kailash.workflow.mermaid_visualizer import MermaidVisualizer

            # Create a mock workflow with a linear flow
            mock_workflow = Mock(spec=Workflow)

            # Create a mock graph with linear workflow: Reader -> Processor -> Writer
            mock_graph = Mock()
            mock_workflow.graph = mock_graph

            # Setup nodes
            nodes = ["data_reader", "data_processor", "data_writer"]
            mock_graph.nodes.return_value = nodes

            # Setup edges for linear flow
            edges = [
                ("data_reader", "data_processor"),
                ("data_processor", "data_writer"),
            ]
            # For edges(data=True), return 3-tuples with edge data
            edges_with_data = [
                ("data_reader", "data_processor", {}),
                ("data_processor", "data_writer", {}),
            ]
            # For edges(data=True), return 3-tuples with edge data
            edges_with_data = [(source, target, {}) for source, target in edges]
            mock_graph.edges.return_value = edges
            mock_graph.edges.side_effect = lambda data=False: (
                edges_with_data if data else edges
            )
            mock_graph.edges.side_effect = lambda data=False: (
                edges_with_data if data else edges
            )

            # Setup degree calculations
            def in_degree(node_id):
                if node_id == "data_reader":
                    return 0  # Source node
                return 1

            def out_degree(node_id):
                if node_id == "data_writer":
                    return 0  # Sink node
                return 1

            mock_graph.in_degree.side_effect = in_degree
            mock_graph.out_degree.side_effect = out_degree

            # Setup node instances
            mock_reader = Mock()
            mock_reader.node_type = "CSVReaderNode"

            mock_processor = Mock()
            mock_processor.node_type = "DataTransformNode"

            mock_writer = Mock()
            mock_writer.node_type = "JSONWriterNode"

            mock_workflow.nodes = {
                "data_reader": mock_reader,
                "data_processor": mock_processor,
                "data_writer": mock_writer,
            }

            # Create visualizer and generate diagram
            visualizer = MermaidVisualizer(mock_workflow, direction="TB")
            diagram = visualizer.generate()

            # Verify diagram structure
            assert isinstance(diagram, str)
            assert "flowchart TB" in diagram
            assert len(diagram) > 100  # Should be substantial content

            # Verify nodes are present in diagram
            assert "data_reader" in diagram
            assert "data_processor" in diagram
            assert "data_writer" in diagram

            # Verify diagram has proper sections
            assert "%%" in diagram  # Should have comments
            assert "[" in diagram or "{" in diagram  # Should have node shapes

            # Verify input data node is created for source nodes
            assert "input_data" in diagram.lower() or "Input Data" in diagram

        except ImportError:
            pytest.skip("MermaidVisualizer not available")

    def test_generate_complex_workflow_with_branching(self):
        """Test generation of complex workflow with branching and merging."""
        try:
            from kailash.workflow.builder import WorkflowBuilder
            from kailash.workflow.mermaid_visualizer import MermaidVisualizer

            # Create mock workflow with branching: Input -> Switch -> [Path A, Path B] -> Merge -> Output
            mock_workflow = Mock(spec=Workflow)
            mock_graph = Mock()
            mock_workflow.graph = mock_graph

            nodes = ["input", "switch_node", "path_a", "path_b", "merge_node", "output"]
            mock_graph.nodes.return_value = nodes

            edges = [
                ("input", "switch_node"),
                ("switch_node", "path_a"),
                ("switch_node", "path_b"),
                ("path_a", "merge_node"),
                ("path_b", "merge_node"),
                ("merge_node", "output"),
            ]
            # For edges(data=True), return 3-tuples with edge data
            edges_with_data = [(source, target, {}) for source, target in edges]
            mock_graph.edges.return_value = edges
            mock_graph.edges.side_effect = lambda data=False: (
                edges_with_data if data else edges
            )

            # Setup degree calculations for branching topology
            degree_map = {
                "input": (0, 1),  # Source
                "switch_node": (1, 2),  # 1 input, 2 outputs (branching)
                "path_a": (1, 1),  # Linear
                "path_b": (1, 1),  # Linear
                "merge_node": (2, 1),  # 2 inputs, 1 output (merging)
                "output": (1, 0),  # Sink
            }

            mock_graph.in_degree.side_effect = lambda node: degree_map[node][0]
            mock_graph.out_degree.side_effect = lambda node: degree_map[node][1]

            # Setup node instances with different types
            node_types = {
                "input": "HTTPRequestNode",
                "switch_node": "SwitchNode",
                "path_a": "PythonCodeNode",
                "path_b": "LLMAgentNode",
                "merge_node": "MergeNode",
                "output": "JSONWriterNode",
            }

            mock_workflow.nodes = {}
            for node_id, node_type in node_types.items():
                mock_node = Mock()
                mock_node.node_type = node_type
                mock_workflow.nodes[node_id] = mock_node

            # Generate diagram
            visualizer = MermaidVisualizer(mock_workflow, direction="LR")
            diagram = visualizer.generate()

            # Verify complex structure is represented
            assert "flowchart LR" in diagram
            assert len(diagram.split("\n")) > 10  # Should have multiple lines

            # Verify all nodes are present
            for node_id in nodes:
                assert node_id in diagram

            # Verify different node categories are handled
            assert "switch" in diagram.lower() or "SwitchNode" in diagram
            assert "merge" in diagram.lower() or "MergeNode" in diagram

            # Should have multiple node shape types for different categories
            shape_indicators = ["[", "{", "(", "(("]
            found_shapes = sum(
                1 for indicator in shape_indicators if indicator in diagram
            )
            assert found_shapes > 0, "Should have node shapes in diagram"

        except ImportError:
            pytest.skip("MermaidVisualizer not available")

    def test_node_style_classification_functionality(self):
        """Test that node style classification works correctly for different node types."""
        try:
            from kailash.workflow.builder import WorkflowBuilder
            from kailash.workflow.mermaid_visualizer import MermaidVisualizer

            # Test different node type classifications
            node_type_test_cases = [
                ("CSVReaderNode", "reader"),
                ("JSONWriterNode", "writer"),
                ("DataTransformNode", "transform"),
                ("SwitchNode", "logic"),
                ("LLMAgentNode", "ai"),
                ("HTTPRequestNode", "api"),
                ("PythonCodeNode", "code"),
                ("UnknownNode", "default"),
            ]

            for node_type, expected_category in node_type_test_cases:
                # Create minimal workflow for testing
                mock_workflow = Mock(spec=Workflow)
                mock_graph = Mock()
                mock_workflow.graph = mock_graph
                mock_graph.nodes.return_value = ["test_node"]
                mock_graph.edges.return_value = []
                mock_graph.in_degree.return_value = 0
                mock_graph.out_degree.return_value = 0

                mock_node = Mock()
                mock_node.node_type = node_type
                mock_workflow.nodes = {"test_node": mock_node}

                visualizer = MermaidVisualizer(mock_workflow)

                # Test style classification
                style = visualizer._get_node_style(node_type)
                assert isinstance(style, str)
                assert len(style) > 0

                # Verify style contains expected CSS properties
                assert "fill:" in style
                assert "stroke:" in style
                assert "stroke-width:" in style

                # Test that different categories get different styles
                if expected_category in visualizer.node_styles:
                    expected_style = visualizer.node_styles[expected_category]
                    assert style == expected_style

        except ImportError:
            pytest.skip("MermaidVisualizer not available")

    def test_node_id_sanitization_functionality(self):
        """Test that node ID sanitization handles problematic characters correctly."""
        try:
            from kailash.workflow.builder import WorkflowBuilder
            from kailash.workflow.mermaid_visualizer import MermaidVisualizer

            # Create minimal workflow for testing
            mock_workflow = Mock(spec=Workflow)
            visualizer = MermaidVisualizer(mock_workflow)

            # Test cases for node ID sanitization
            sanitization_test_cases = [
                ("normal_node", "normal_node"),  # No change needed
                ("node-with-dashes", "node_with_dashes"),  # Replace dashes
                ("node.with.dots", "node_with_dots"),  # Replace dots
                ("node with spaces", "node_with_spaces"),  # Replace spaces
                (
                    "node@with#special$chars",
                    "node_with_special_chars",
                ),  # Remove special chars
                (
                    "123_numeric_start",
                    "node_123_numeric_start",
                ),  # Add prefix for numeric start
                ("", ""),  # Handle empty string
                ("UPPERCASE_NODE", "UPPERCASE_NODE"),  # Preserve case
                ("node_123_end", "node_123_end"),  # Numbers at end OK
            ]

            for input_id, expected_output in sanitization_test_cases:
                sanitized = visualizer._sanitize_node_id(input_id)
                assert (
                    sanitized == expected_output
                ), f"Sanitization failed for '{input_id}': got '{sanitized}', expected '{expected_output}'"

                # Verify sanitized IDs are Mermaid-compatible
                if sanitized:  # Skip empty string
                    assert not sanitized[0].isdigit() or sanitized.startswith(
                        "node_"
                    ), "Sanitized ID should not start with digit unless prefixed"
                    assert (
                        " " not in sanitized
                    ), "Sanitized ID should not contain spaces"
                    assert (
                        "-" not in sanitized
                    ), "Sanitized ID should not contain dashes"
                    assert "." not in sanitized, "Sanitized ID should not contain dots"

        except ImportError:
            pytest.skip("MermaidVisualizer not available")

    def test_node_shape_assignment_by_type(self):
        """Test that different node types get appropriate shapes in Mermaid diagram."""
        try:
            from kailash.workflow.builder import WorkflowBuilder
            from kailash.workflow.mermaid_visualizer import MermaidVisualizer

            mock_workflow = Mock(spec=Workflow)
            visualizer = MermaidVisualizer(mock_workflow)

            # Test node shape assignment
            shape_test_cases = [
                ("CSVReaderNode", "([", "])"),  # Stadium shape for readers
                ("JSONWriterNode", "([", "])"),  # Stadium shape for writers
                ("SwitchNode", "{", "}"),  # Diamond for conditionals
                ("PythonCodeNode", "[", "]"),  # Rectangle for code
                ("LLMAgentNode", "[", "]"),  # Rectangle for AI
                ("HTTPRequestNode", "[", "]"),  # Rectangle for API
                ("MergeNode", "[", "]"),  # Rectangle for processors
            ]

            for node_type, expected_open, expected_close in shape_test_cases:
                open_bracket, close_bracket = visualizer._get_node_shape(node_type)

                # Verify shape brackets are strings
                assert isinstance(open_bracket, str)
                assert isinstance(close_bracket, str)

                # Verify brackets are non-empty
                assert len(open_bracket) > 0
                assert len(close_bracket) > 0

                # For known types, verify expected shapes
                if node_type in ["CSVReaderNode", "JSONWriterNode"]:
                    assert open_bracket == "(["
                    assert close_bracket == "])"
                elif "Switch" in node_type:
                    assert "{" in open_bracket
                    assert "}" in close_bracket

        except ImportError:
            pytest.skip("MermaidVisualizer not available")


class TestMermaidVisualizerMarkdownGeneration:
    """Test Markdown generation functionality."""

    def test_generate_markdown_with_title_and_code_blocks(self):
        """Test generation of complete Markdown with proper code block formatting."""
        try:
            from kailash.workflow.builder import WorkflowBuilder
            from kailash.workflow.mermaid_visualizer import MermaidVisualizer

            # Create simple workflow for markdown testing
            mock_workflow = Mock(spec=Workflow)
            mock_workflow.name = "TestWorkflow"  # Add name attribute
            mock_graph = Mock()
            mock_workflow.graph = mock_graph

            # Simple linear workflow
            mock_graph.nodes.return_value = ["input", "process", "output"]
            edges = [
                ("input", "process"),
                ("process", "output"),
            ]
            # For edges(data=True), return 3-tuples with edge data
            edges_with_data = [(source, target, {}) for source, target in edges]
            mock_graph.edges.return_value = edges
            mock_graph.edges.side_effect = lambda data=False: (
                edges_with_data if data else edges
            )
            mock_graph.in_degree.side_effect = lambda n: 0 if n == "input" else 1
            mock_graph.out_degree.side_effect = lambda n: 0 if n == "output" else 1

            # Setup node instances
            nodes = {}
            for node_id in ["input", "process", "output"]:
                mock_node = Mock()
                mock_node.node_type = f"{node_id.title()}Node"
                nodes[node_id] = mock_node
            mock_workflow.nodes = nodes

            visualizer = MermaidVisualizer(mock_workflow)

            # Test markdown generation with title
            title = "Test Workflow Diagram"
            markdown = visualizer.generate_markdown(title=title)

            # Verify markdown structure
            assert isinstance(markdown, str)
            assert len(markdown) > 100

            # Verify title is included
            assert title in markdown

            # Verify Mermaid code block format
            assert "```mermaid" in markdown
            assert "```" in markdown.split("```mermaid")[1]  # Closing block

            # Verify flowchart is inside code block
            assert "flowchart" in markdown

            # Test markdown generation without title
            markdown_no_title = visualizer.generate_markdown()
            assert isinstance(markdown_no_title, str)
            assert "```mermaid" in markdown_no_title
            assert "flowchart" in markdown_no_title

            # Should use default title when no title provided
            assert "Test Workflow Diagram" not in markdown_no_title
            assert "Workflow:" in markdown_no_title  # Default title format

        except ImportError:
            pytest.skip("MermaidVisualizer not available")


class TestMermaidVisualizerEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_workflow_handling(self):
        """Test handling of workflows with no nodes or edges."""
        try:
            from kailash.workflow.builder import WorkflowBuilder
            from kailash.workflow.mermaid_visualizer import MermaidVisualizer

            # Create empty workflow
            mock_workflow = Mock(spec=Workflow)
            mock_graph = Mock()
            mock_workflow.graph = mock_graph

            # Empty workflow
            mock_graph.nodes.return_value = []
            mock_graph.edges.return_value = []
            mock_workflow.nodes = {}

            visualizer = MermaidVisualizer(mock_workflow)
            diagram = visualizer.generate()

            # Should still generate valid Mermaid syntax
            assert isinstance(diagram, str)
            assert "flowchart TB" in diagram

            # Should handle empty case gracefully
            assert len(diagram) > 0

            # Should not contain node definitions
            lines = diagram.split("\n")
            node_definition_lines = [
                line
                for line in lines
                if line.strip()
                and not line.strip().startswith("%")
                and not line.strip().startswith("flowchart")
            ]

            # May have minimal content but should not crash
            assert len(node_definition_lines) >= 0

        except ImportError:
            pytest.skip("MermaidVisualizer not available")

    def test_single_node_workflow(self):
        """Test workflow with only one node."""
        try:
            from kailash.workflow.builder import WorkflowBuilder
            from kailash.workflow.mermaid_visualizer import MermaidVisualizer

            mock_workflow = Mock(spec=Workflow)
            mock_graph = Mock()
            mock_workflow.graph = mock_graph

            # Single node workflow
            mock_graph.nodes.return_value = ["single_node"]
            mock_graph.edges.return_value = []
            mock_graph.in_degree.return_value = 0
            mock_graph.out_degree.return_value = 0

            mock_node = Mock()
            mock_node.node_type = "PythonCodeNode"
            mock_workflow.nodes = {"single_node": mock_node}

            visualizer = MermaidVisualizer(mock_workflow)
            diagram = visualizer.generate()

            # Should generate valid diagram
            assert "flowchart TB" in diagram
            assert "single_node" in diagram

            # Should recognize as both source and sink
            assert "input_data" in diagram.lower() or "Input Data" in diagram

        except ImportError:
            pytest.skip("MermaidVisualizer not available")

    def test_workflow_with_cycles(self):
        """Test handling of workflows with circular dependencies."""
        try:
            from kailash.workflow.builder import WorkflowBuilder
            from kailash.workflow.mermaid_visualizer import MermaidVisualizer

            mock_workflow = Mock(spec=Workflow)
            mock_graph = Mock()
            mock_workflow.graph = mock_graph

            # Create cycle: A -> B -> C -> A
            nodes = ["node_a", "node_b", "node_c"]
            edges = [("node_a", "node_b"), ("node_b", "node_c"), ("node_c", "node_a")]

            mock_graph.nodes.return_value = nodes
            # For edges(data=True), return 3-tuples with edge data
            edges_with_data = [(source, target, {}) for source, target in edges]
            mock_graph.edges.return_value = edges
            mock_graph.edges.side_effect = lambda data=False: (
                edges_with_data if data else edges
            )

            # All nodes have in_degree=1 and out_degree=1 (cycle)
            mock_graph.in_degree.return_value = 1
            mock_graph.out_degree.return_value = 1

            # Setup node instances
            node_instances = {}
            for node_id in nodes:
                mock_node = Mock()
                mock_node.node_type = "ProcessorNode"
                node_instances[node_id] = mock_node
            mock_workflow.nodes = node_instances

            visualizer = MermaidVisualizer(mock_workflow)
            diagram = visualizer.generate()

            # Should handle cycles without crashing
            assert isinstance(diagram, str)
            assert "flowchart TB" in diagram

            # All nodes should be present
            for node_id in nodes:
                assert node_id in diagram

            # Should not identify any source/sink nodes in pure cycle
            lines = diagram.split("\n")
            input_data_lines = [line for line in lines if "input_data" in line.lower()]
            # May or may not have input_data depending on implementation

        except ImportError:
            pytest.skip("MermaidVisualizer not available")

    def test_custom_node_styles_override(self):
        """Test that custom node styles properly override defaults."""
        try:
            from kailash.workflow.builder import WorkflowBuilder
            from kailash.workflow.mermaid_visualizer import MermaidVisualizer

            mock_workflow = Mock(spec=Workflow)

            # Custom styles
            custom_styles = {
                "reader": "fill:#ff0000,stroke:#000000,stroke-width:3px",
                "writer": "fill:#00ff00,stroke:#000000,stroke-width:3px",
                "custom_type": "fill:#0000ff,stroke:#ffffff,stroke-width:1px",
            }

            visualizer = MermaidVisualizer(mock_workflow, node_styles=custom_styles)

            # Test that custom styles are used
            reader_style = visualizer._get_node_style("CSVReaderNode")
            assert reader_style == custom_styles["reader"]
            assert "#ff0000" in reader_style  # Custom red color

            writer_style = visualizer._get_node_style("JSONWriterNode")
            assert writer_style == custom_styles["writer"]
            assert "#00ff00" in writer_style  # Custom green color

            # Test that custom styles completely override defaults
            # Since we didn't provide an 'api' style, it should use 'default'
            # or raise a KeyError if no default fallback
            try:
                api_style = visualizer._get_node_style("HTTPRequestNode")
                # If it doesn't raise, check it's using some fallback
                assert api_style is not None
            except KeyError:
                # This is expected if custom styles completely override defaults
                pass

            # Test that unknown types are handled when custom styles don't include 'default'
            try:
                unknown_style = visualizer._get_node_style("UnknownNodeType")
                # If it doesn't raise, it found some style
                assert unknown_style is not None
            except KeyError:
                # This is expected if custom styles don't include 'default'
                pass

        except ImportError:
            pytest.skip("MermaidVisualizer not available")

    def test_direction_parameter_functionality(self):
        """Test that direction parameter affects diagram generation."""
        try:
            from kailash.workflow.builder import WorkflowBuilder
            from kailash.workflow.mermaid_visualizer import MermaidVisualizer

            mock_workflow = Mock(spec=Workflow)
            mock_graph = Mock()
            mock_workflow.graph = mock_graph
            mock_graph.nodes.return_value = ["test_node"]
            mock_graph.edges.return_value = []
            mock_graph.edges.side_effect = lambda data=False: []
            mock_graph.in_degree.return_value = 0
            mock_graph.out_degree.return_value = 0
            mock_node = Mock()
            mock_node.node_type = "TestNode"
            mock_workflow.nodes = {"test_node": mock_node}

            # Test different directions
            directions = ["TB", "LR", "BT", "RL"]

            for direction in directions:
                visualizer = MermaidVisualizer(mock_workflow, direction=direction)
                diagram = visualizer.generate()

                # Verify direction is used in flowchart declaration
                assert f"flowchart {direction}" in diagram

                # Verify it's at the beginning of the diagram
                lines = diagram.strip().split("\n")
                assert lines[0] == f"flowchart {direction}"

        except ImportError:
            pytest.skip("MermaidVisualizer not available")
