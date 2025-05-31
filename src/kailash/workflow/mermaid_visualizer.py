"""Mermaid diagram visualization for workflows.

This module provides Mermaid diagram generation for workflow visualization,
offering a text-based format that can be embedded in markdown files and
rendered in various documentation platforms.
"""

from typing import Dict, Optional, Tuple

from kailash.workflow.graph import Workflow


class MermaidVisualizer:
    """Generate Mermaid diagrams for workflow visualization.

    This class provides methods to convert Kailash workflows into Mermaid
    diagram syntax, which can be embedded in markdown files for better
    documentation and visualization.

    Attributes:
        workflow: The workflow to visualize
        node_styles: Custom styles for different node types
        direction: Graph direction (TB, LR, etc.)
    """

    def __init__(
        self,
        workflow: Workflow,
        direction: str = "TB",
        node_styles: Optional[Dict[str, str]] = None,
    ):
        """Initialize the Mermaid visualizer.

        Args:
            workflow: The workflow to visualize
            direction: Graph direction (TB=top-bottom, LR=left-right, etc.)
            node_styles: Custom node styles mapping node types to Mermaid styles
        """
        self.workflow = workflow
        self.direction = direction
        self.node_styles = node_styles or self._default_node_styles()

    def _default_node_styles(self) -> Dict[str, str]:
        """Get default node styles for different node types.

        Returns:
            Dict mapping node type patterns to Mermaid style classes
        """
        return {
            "reader": "fill:#e1f5fe,stroke:#01579b,stroke-width:2px",
            "writer": "fill:#f3e5f5,stroke:#4a148c,stroke-width:2px",
            "transform": "fill:#fff3e0,stroke:#e65100,stroke-width:2px",
            "logic": "fill:#fce4ec,stroke:#880e4f,stroke-width:2px",
            "ai": "fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px",
            "api": "fill:#f3e5f5,stroke:#4527a0,stroke-width:2px",
            "code": "fill:#fffde7,stroke:#f57f17,stroke-width:2px",
            "default": "fill:#f5f5f5,stroke:#424242,stroke-width:2px",
        }

    def _get_pattern_label(self, node_id: str, node_instance) -> str:
        """Get a pattern-oriented label for a node.

        Args:
            node_id: The node ID
            node_instance: The node instance

        Returns:
            Pattern-oriented label for the node
        """
        node_type = node_instance.node_type

        # Try to get a meaningful name from the node
        node = self.workflow.get_node(node_id)
        if node and hasattr(node, "name") and node.name:
            return node.name

        # Otherwise use the node type with ID
        clean_type = self._get_node_type_label(node_type)
        # Use line break without parentheses to avoid Mermaid parsing issues
        return f"{clean_type}<br/>{node_id}"

    def _get_pattern_edge_label(self, source: str, target: str, data: Dict) -> str:
        """Get a pattern-oriented edge label.

        Args:
            source: Source node ID
            target: Target node ID
            data: Edge data

        Returns:
            Pattern-oriented edge label
        """
        # Get basic edge label
        basic_label = self._get_edge_label(source, target, data)

        # Check if this is a validation or error path
        source_node = self.workflow.nodes.get(source)
        target_node = self.workflow.nodes.get(target)

        if source_node and target_node:
            source_type = source_node.node_type.lower()
            target_type = target_node.node_type.lower()

            # Check for validation patterns
            if "valid" in source_type or "check" in source_type:
                if "error" in target_type or "fail" in target_type:
                    return "Invalid"
                elif basic_label:
                    return f"Valid|{basic_label}"
                else:
                    return "Valid"

            # Check for switch/router patterns
            if "switch" in source_type or "router" in source_type:
                if basic_label and "case_" in basic_label:
                    case_name = basic_label.replace("case_", "").split("→")[0]
                    return case_name.title()

        return basic_label

    def _get_pattern_style(self, node_type: str) -> str:
        """Get pattern-oriented styling for a node type.

        Args:
            node_type: The node type

        Returns:
            Style string for the node
        """
        node_type_lower = node_type.lower()

        # Data I/O nodes
        if "reader" in node_type_lower:
            return "fill:#e1f5fe,stroke:#01579b,stroke-width:2px"
        elif "writer" in node_type_lower:
            return "fill:#f3e5f5,stroke:#4a148c,stroke-width:2px"

        # Validation nodes
        elif any(x in node_type_lower for x in ["valid", "check", "verify"]):
            return "fill:#fff3e0,stroke:#ff6f00,stroke-width:2px"

        # Error handling nodes
        elif any(x in node_type_lower for x in ["error", "fail", "exception"]):
            return "fill:#ffebee,stroke:#c62828,stroke-width:2px"

        # Logic nodes
        elif any(x in node_type_lower for x in ["switch", "router", "conditional"]):
            return "fill:#fce4ec,stroke:#880e4f,stroke-width:2px"
        elif "merge" in node_type_lower:
            return "fill:#f3e5f5,stroke:#4a148c,stroke-width:2px"

        # Processing nodes
        elif any(
            x in node_type_lower
            for x in ["transform", "filter", "process", "aggregate"]
        ):
            return "fill:#fff3e0,stroke:#e65100,stroke-width:2px"

        # Code execution nodes
        elif "python" in node_type_lower or "code" in node_type_lower:
            return "fill:#fffde7,stroke:#f57f17,stroke-width:2px"

        # AI/ML nodes
        elif any(x in node_type_lower for x in ["ai", "ml", "model", "embedding"]):
            return "fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px"

        # API nodes
        elif any(x in node_type_lower for x in ["api", "http", "rest", "graphql"]):
            return "fill:#e8eaf6,stroke:#283593,stroke-width:2px"

        # Default
        else:
            return "fill:#f5f5f5,stroke:#616161,stroke-width:2px"

    def _get_node_style(self, node_type: str) -> str:
        """Get the style for a specific node type.

        Args:
            node_type: The type of the node

        Returns:
            Mermaid style string for the node
        """
        node_type_lower = node_type.lower()

        if "reader" in node_type_lower:
            return self.node_styles["reader"]
        elif "writer" in node_type_lower:
            return self.node_styles["writer"]
        elif any(
            x in node_type_lower
            for x in ["transform", "filter", "processor", "aggregator"]
        ):
            return self.node_styles["transform"]
        elif any(
            x in node_type_lower for x in ["switch", "merge", "conditional", "logic"]
        ):
            return self.node_styles["logic"]
        elif any(x in node_type_lower for x in ["ai", "llm", "model", "embedding"]):
            return self.node_styles["ai"]
        elif any(
            x in node_type_lower for x in ["api", "http", "rest", "graphql", "oauth"]
        ):
            return self.node_styles["api"]
        elif "python" in node_type_lower or "code" in node_type_lower:
            return self.node_styles["code"]
        else:
            return self.node_styles["default"]

    def _sanitize_node_id(self, node_id: str) -> str:
        """Sanitize node ID for Mermaid compatibility.

        Args:
            node_id: Original node ID

        Returns:
            Sanitized node ID safe for Mermaid
        """
        # Replace special characters with underscores
        sanitized = node_id.replace("-", "_").replace(" ", "_").replace(".", "_")
        # Ensure it starts with a letter
        if sanitized and sanitized[0].isdigit():
            sanitized = f"node_{sanitized}"
        return sanitized

    def _get_node_label(self, node_id: str) -> str:
        """Get display label for a node.

        Args:
            node_id: The node ID

        Returns:
            Display label for the node
        """
        node = self.workflow.get_node(node_id)
        if node:
            # Use node name if available
            if hasattr(node, "name") and node.name:
                return node.name
            # Fall back to node type
            if hasattr(node, "node_type"):
                return f"{node_id}<br/>({node.node_type})"

        # Last resort: use node instance from workflow
        node_instance = self.workflow.nodes.get(node_id)
        if node_instance:
            return f"{node_id}<br/>({node_instance.node_type})"

        return node_id

    def _get_node_type_label(self, node_type: str) -> str:
        """Get a clean label for a node type.

        Args:
            node_type: The node type string

        Returns:
            Clean label for display
        """
        # Remove 'Node' suffix if present
        if node_type.endswith("Node"):
            return node_type[:-4]
        return node_type

    def _get_node_shape(self, node_type: str) -> Tuple[str, str]:
        """Get the shape brackets for a node type.

        Args:
            node_type: The type of the node

        Returns:
            Tuple of (opening bracket, closing bracket)
        """
        node_type_lower = node_type.lower()

        # Different shapes for different node types
        if "reader" in node_type_lower:
            return "([", "])"  # Stadium shape for inputs
        elif "writer" in node_type_lower:
            return "([", "])"  # Stadium shape for outputs
        elif any(x in node_type_lower for x in ["switch", "conditional"]):
            return "{", "}"  # Rhombus for decisions
        elif any(x in node_type_lower for x in ["merge"]):
            return "((", "))"  # Circle for merge
        else:
            return "[", "]"  # Rectangle for processing

    def generate(self) -> str:
        """Generate the Mermaid diagram code.

        Returns:
            Complete Mermaid diagram as a string
        """
        lines = []
        lines.append(f"flowchart {self.direction}")
        lines.append("")

        # Identify source and sink nodes
        source_nodes = []
        sink_nodes = []
        intermediate_nodes = []

        for node_id in self.workflow.graph.nodes():
            in_degree = self.workflow.graph.in_degree(node_id)
            out_degree = self.workflow.graph.out_degree(node_id)

            if in_degree == 0:
                source_nodes.append(node_id)
            elif out_degree == 0:
                sink_nodes.append(node_id)
            else:
                intermediate_nodes.append(node_id)

        # Add input data nodes if there are sources
        if source_nodes:
            lines.append("    %% Input Data")
            lines.append("    input_data([Input Data])")
            lines.append("")

        # Group nodes by type for better organization
        readers = []
        writers = []
        processors = []
        validators = []
        routers = []
        mergers = []

        # Categorize nodes
        for node_id in self.workflow.graph.nodes():
            node_instance = self.workflow.nodes.get(node_id)
            if node_instance:
                node_type = node_instance.node_type
                node_type_lower = node_type.lower()

                if "reader" in node_type_lower:
                    readers.append((node_id, node_instance))
                elif "writer" in node_type_lower:
                    writers.append((node_id, node_instance))
                elif any(
                    x in node_type_lower for x in ["switch", "router", "conditional"]
                ):
                    routers.append((node_id, node_instance))
                elif "merge" in node_type_lower:
                    mergers.append((node_id, node_instance))
                elif any(x in node_type_lower for x in ["valid", "check", "verify"]):
                    validators.append((node_id, node_instance))
                else:
                    processors.append((node_id, node_instance))

        # Generate node definitions by category
        if readers:
            lines.append("    %% Data Input nodes")
            for node_id, node_instance in readers:
                sanitized_id = self._sanitize_node_id(node_id)
                label = self._get_pattern_label(node_id, node_instance)
                # Use quotes for labels with special characters
                lines.append(f'    {sanitized_id}["{label}"]')
            lines.append("")

        if validators:
            lines.append("    %% Validation nodes")
            for node_id, node_instance in validators:
                sanitized_id = self._sanitize_node_id(node_id)
                label = self._get_pattern_label(node_id, node_instance)
                # Use quotes for labels with special characters
                lines.append(f'    {sanitized_id}{{"{label}"}}')
            lines.append("")

        if processors:
            lines.append("    %% Processing nodes")
            for node_id, node_instance in processors:
                sanitized_id = self._sanitize_node_id(node_id)
                label = self._get_pattern_label(node_id, node_instance)
                # Use quotes for labels with special characters
                lines.append(f'    {sanitized_id}["{label}"]')
            lines.append("")

        if routers:
            lines.append("    %% Routing/Decision nodes")
            for node_id, node_instance in routers:
                sanitized_id = self._sanitize_node_id(node_id)
                label = self._get_pattern_label(node_id, node_instance)
                # Use quotes for labels with special characters
                lines.append(f'    {sanitized_id}{{"{label}"}}')
            lines.append("")

        if mergers:
            lines.append("    %% Merge nodes")
            for node_id, node_instance in mergers:
                sanitized_id = self._sanitize_node_id(node_id)
                label = self._get_pattern_label(node_id, node_instance)
                # Use quotes for labels with special characters
                lines.append(f'    {sanitized_id}(("{label}"))')
            lines.append("")

        if writers:
            lines.append("    %% Data Output nodes")
            for node_id, node_instance in writers:
                sanitized_id = self._sanitize_node_id(node_id)
                label = self._get_pattern_label(node_id, node_instance)
                # Use quotes for labels with special characters
                lines.append(f'    {sanitized_id}["{label}"]')
            lines.append("")

        # Add output data node if there are sinks
        if sink_nodes:
            lines.append("    %% Output Data")
            lines.append("    output_data([Output Data])")
            lines.append("")

        # Generate flow section
        lines.append("    %% Flow")

        # Connect input data to source nodes
        if source_nodes:
            for source in source_nodes:
                sanitized_id = self._sanitize_node_id(source)
                lines.append(f"    input_data --> {sanitized_id}")

        # Add all workflow edges
        for source, target, data in self.workflow.graph.edges(data=True):
            source_id = self._sanitize_node_id(source)
            target_id = self._sanitize_node_id(target)

            # Determine edge type for better visualization
            edge_label = self._get_pattern_edge_label(source, target, data)

            if edge_label:
                lines.append(f"    {source_id} -->|{edge_label}| {target_id}")
            else:
                lines.append(f"    {source_id} --> {target_id}")

        # Connect sink nodes to output data
        if sink_nodes:
            for sink in sink_nodes:
                sanitized_id = self._sanitize_node_id(sink)
                lines.append(f"    {sanitized_id} --> output_data")

        # Generate styling section
        lines.append("")
        lines.append("    %% Styling")

        # Style input/output data nodes
        if source_nodes:
            lines.append(
                "    style input_data fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,stroke-dasharray: 5 5"
            )
        if sink_nodes:
            lines.append(
                "    style output_data fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,stroke-dasharray: 5 5"
            )

        # Style workflow nodes
        for node_id in self.workflow.graph.nodes():
            sanitized_id = self._sanitize_node_id(node_id)
            node_instance = self.workflow.nodes.get(node_id)
            if node_instance:
                style = self._get_pattern_style(node_instance.node_type)
                lines.append(f"    style {sanitized_id} {style}")

        return "\n".join(lines)

    def _get_edge_label(self, source: str, target: str, data: Dict) -> str:
        """Get label for an edge.

        Args:
            source: Source node ID
            target: Target node ID
            data: Edge data dictionary

        Returns:
            Edge label string
        """
        # Check for direct output/input mapping
        from_output = data.get("from_output")
        to_input = data.get("to_input")

        if from_output and to_input:
            return f"{from_output}→{to_input}"

        # Check for mapping dictionary
        mapping = data.get("mapping", {})
        if mapping:
            # For single mapping, show inline
            if len(mapping) == 1:
                src, dst = next(iter(mapping.items()))
                return f"{src}→{dst}"
            # For multiple mappings, show count
            else:
                return f"{len(mapping)} mappings"

        return ""

    def generate_markdown(self, title: Optional[str] = None) -> str:
        """Generate a complete markdown section with the Mermaid diagram.

        Args:
            title: Optional title for the diagram section

        Returns:
            Complete markdown text with embedded Mermaid diagram
        """
        lines = []

        # Add title if provided
        if title:
            lines.append(f"## {title}")
            lines.append("")
        else:
            lines.append(f"## Workflow: {self.workflow.name}")
            lines.append("")

        # Add description if available
        if hasattr(self.workflow, "description") and self.workflow.description:
            lines.append(f"_{self.workflow.description}_")
            lines.append("")

        # Add the Mermaid diagram
        lines.append("```mermaid")
        lines.append(self.generate())
        lines.append("```")
        lines.append("")

        # Add node summary
        lines.append("### Nodes")
        lines.append("")
        lines.append("| Node ID | Type | Description |")
        lines.append("|---------|------|-------------|")

        for node_id in sorted(self.workflow.graph.nodes()):
            node = self.workflow.get_node(node_id)
            node_instance = self.workflow.nodes.get(node_id)

            if node_instance:
                node_type = node_instance.node_type
                description = ""

                if node and hasattr(node, "__doc__") and node.__doc__:
                    # Get first line of docstring
                    description = node.__doc__.strip().split("\n")[0]

                lines.append(f"| {node_id} | {node_type} | {description} |")

        lines.append("")

        # Add edge summary if there are connections
        edges = list(self.workflow.graph.edges(data=True))
        if edges:
            lines.append("### Connections")
            lines.append("")
            lines.append("| From | To | Mapping |")
            lines.append("|------|-----|---------|")

            for source, target, data in edges:
                edge_label = self._get_edge_label(source, target, data)
                lines.append(f"| {source} | {target} | {edge_label} |")

            lines.append("")

        return "\n".join(lines)

    def save_markdown(self, filepath: str, title: Optional[str] = None) -> None:
        """Save the Mermaid diagram as a markdown file.

        Args:
            filepath: Path to save the markdown file
            title: Optional title for the diagram
        """
        content = self.generate_markdown(title)
        with open(filepath, "w") as f:
            f.write(content)

    def save_mermaid(self, filepath: str) -> None:
        """Save just the Mermaid diagram code.

        Args:
            filepath: Path to save the Mermaid file
        """
        content = self.generate()
        with open(filepath, "w") as f:
            f.write(content)


def add_mermaid_to_workflow():
    """Add Mermaid visualization methods to Workflow class."""

    def to_mermaid(self, direction: str = "TB") -> str:
        """Generate Mermaid diagram for this workflow.

        Args:
            direction: Graph direction (TB, LR, etc.)

        Returns:
            Mermaid diagram as string
        """
        visualizer = MermaidVisualizer(self, direction=direction)
        return visualizer.generate()

    def to_mermaid_markdown(self, title: Optional[str] = None) -> str:
        """Generate markdown with embedded Mermaid diagram.

        Args:
            title: Optional title for the diagram

        Returns:
            Complete markdown text
        """
        visualizer = MermaidVisualizer(self)
        return visualizer.generate_markdown(title)

    def save_mermaid_markdown(self, filepath: str, title: Optional[str] = None) -> None:
        """Save workflow as markdown with Mermaid diagram.

        Args:
            filepath: Path to save the markdown file
            title: Optional title for the diagram
        """
        visualizer = MermaidVisualizer(self)
        visualizer.save_markdown(filepath, title)

    # Add methods to Workflow class
    Workflow.to_mermaid = to_mermaid
    Workflow.to_mermaid_markdown = to_mermaid_markdown
    Workflow.save_mermaid_markdown = save_mermaid_markdown


# Call this when module is imported
add_mermaid_to_workflow()
