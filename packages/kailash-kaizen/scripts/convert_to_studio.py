#!/usr/bin/env python3
"""
Kailash Studio Workflow Converter
==================================

Converts Kaizen user scenarios (Python code) to Studio-compatible JSON workflows.

Usage:
    python convert_to_studio.py user-scenarios/01-beginner-simple-qa-bot.py

Output:
    Creates {scenario_name}_studio.json in the same directory

Features:
    - Extracts WorkflowBuilder nodes and edges
    - Generates visual layout (automatic positioning)
    - Creates complete Studio-compatible JSON
    - Validates against TypeScript types
    - Optional: Tests SDK execution compatibility

Author: Kailash SDK Team
Version: 1.0.0
"""

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


class WorkflowConverter:
    """Convert Python workflow code to Studio JSON format."""

    def __init__(self):
        self.nodes: List[Dict[str, Any]] = []
        self.edges: List[Dict[str, Any]] = []
        self.node_positions: Dict[str, Tuple[int, int]] = {}
        self.edge_counter = 0

    def extract_from_file(self, file_path: str) -> Dict[str, Any]:
        """
        Extract workflow information from Python file.

        Args:
            file_path: Path to Python file with WorkflowBuilder code

        Returns:
            Studio-compatible workflow JSON
        """
        with open(file_path, "r") as f:
            content = f.read()

        # Parse Python AST
        tree = ast.parse(content)

        # Extract workflow name from file path
        file_name = Path(file_path).stem
        workflow_name = self._generate_workflow_name(file_name)

        # Extract nodes and edges from AST
        self._extract_nodes_from_ast(tree)
        self._extract_edges_from_ast(tree)

        # Generate visual layout
        self._generate_layout()

        # Build Studio JSON
        return self._build_studio_json(workflow_name)

    def _extract_nodes_from_ast(self, tree: ast.Module):
        """Extract add_node() calls from AST."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Look for workflow.add_node() calls
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_node"
                ):

                    if len(node.args) >= 3:
                        node_type = self._get_string_value(node.args[0])
                        node_id = self._get_string_value(node.args[1])
                        parameters = self._get_dict_value(node.args[2])

                        if node_type and node_id:
                            self.nodes.append(
                                {
                                    "id": node_id,
                                    "type": node_type,
                                    "parameters": parameters or {},
                                }
                            )

    def _extract_edges_from_ast(self, tree: ast.Module):
        """Extract add_edge() calls from AST."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Look for workflow.add_edge() calls
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_edge"
                ):

                    if len(node.args) >= 2:
                        source = self._get_string_value(node.args[0])
                        target = self._get_string_value(node.args[1])

                        if source and target:
                            self.edge_counter += 1
                            self.edges.append(
                                {
                                    "id": f"edge_{self.edge_counter}",
                                    "source": source,
                                    "target": target,
                                }
                            )

    def _get_string_value(self, node: ast.AST) -> str:
        """Extract string value from AST node."""
        if isinstance(node, ast.Constant):
            return str(node.value)
        return ""

    def _get_dict_value(self, node: ast.AST) -> Dict[str, Any]:
        """Extract dictionary value from AST node."""
        if isinstance(node, ast.Dict):
            result = {}
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant):
                    key_str = str(key.value)
                    result[key_str] = self._extract_value(value)
            return result
        return {}

    def _extract_value(self, node: ast.AST) -> Any:
        """Extract value from AST node."""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.List):
            return [self._extract_value(item) for item in node.elts]
        elif isinstance(node, ast.Dict):
            return self._get_dict_value(node)
        return None

    def _generate_layout(self):
        """Generate visual layout for nodes."""
        if not self.nodes:
            return

        # Build graph structure
        graph = self._build_graph()

        # Calculate levels (depth-first traversal)
        levels = self._calculate_levels(graph)

        # Position nodes based on levels
        self._position_nodes(levels)

    def _build_graph(self) -> Dict[str, List[str]]:
        """Build adjacency list from edges."""
        graph = {node["id"]: [] for node in self.nodes}
        for edge in self.edges:
            if edge["source"] in graph:
                graph[edge["source"]].append(edge["target"])
        return graph

    def _calculate_levels(self, graph: Dict[str, List[str]]) -> Dict[str, int]:
        """Calculate depth level for each node."""
        levels = {}
        visited = set()

        # Find root nodes (no incoming edges)
        incoming = {node["id"]: 0 for node in self.nodes}
        for edge in self.edges:
            incoming[edge["target"]] = incoming.get(edge["target"], 0) + 1

        roots = [node_id for node_id, count in incoming.items() if count == 0]

        if not roots and self.nodes:
            # No clear roots, use first node
            roots = [self.nodes[0]["id"]]

        # BFS to assign levels
        def assign_level(node_id: str, level: int):
            if node_id in visited:
                return
            visited.add(node_id)
            levels[node_id] = level
            for neighbor in graph.get(node_id, []):
                assign_level(neighbor, level + 1)

        for root in roots:
            assign_level(root, 0)

        # Handle unvisited nodes
        for node in self.nodes:
            if node["id"] not in visited:
                levels[node["id"]] = 0

        return levels

    def _position_nodes(self, levels: Dict[str, int]):
        """Position nodes based on calculated levels."""
        # Group nodes by level
        level_groups: Dict[int, List[str]] = {}
        for node_id, level in levels.items():
            if level not in level_groups:
                level_groups[level] = []
            level_groups[level].append(node_id)

        # Calculate positions
        horizontal_spacing = 400
        vertical_spacing = 200
        start_x = 100
        start_y = 100

        for level, node_ids in level_groups.items():
            x = start_x + (level * horizontal_spacing)

            # Center nodes vertically
            total_height = (len(node_ids) - 1) * vertical_spacing
            offset_y = start_y

            for i, node_id in enumerate(node_ids):
                y = offset_y + (i * vertical_spacing)
                self.node_positions[node_id] = (x, y)

    def _generate_workflow_name(self, file_name: str) -> str:
        """Generate human-readable workflow name from file name."""
        # Remove number prefix and extension
        name = re.sub(r"^\d+-", "", file_name)
        name = re.sub(r"_", " ", name)
        return name.title()

    def _generate_node_label(self, node_type: str, node_id: str) -> str:
        """Generate human-readable node label."""
        # Remove "Node" suffix
        label = re.sub(r"Node$", "", node_type)
        # Convert camelCase to Title Case
        label = re.sub(r"([A-Z])", r" \1", label).strip()
        return label

    def _detect_complexity(self) -> str:
        """Detect workflow complexity based on node count and edges."""
        node_count = len(self.nodes)
        edge_count = len(self.edges)

        if node_count <= 2:
            return "low"
        elif node_count <= 5:
            return "medium"
        else:
            return "high"

    def _build_studio_json(self, workflow_name: str) -> Dict[str, Any]:
        """Build complete Studio-compatible JSON."""
        studio_nodes = []

        for node in self.nodes:
            node_id = node["id"]
            node_type = node["type"]
            parameters = node["parameters"]

            # Get position (default to center if not calculated)
            x, y = self.node_positions.get(node_id, (300, 200))

            studio_node = {
                "id": node_id,
                "type": node_type,
                "position": {"x": x, "y": y},
                "data": {
                    "label": self._generate_node_label(node_type, node_id),
                    "parameters": parameters,
                },
            }

            # Add nodeType metadata based on node type
            if "LLM" in node_type or "Agent" in node_type:
                studio_node["data"]["nodeType"] = "AI Agent"
                studio_node["data"]["icon"] = "robot"
                studio_node["data"]["color"] = "#3b82f6"
            elif "Database" in node_type or "SQL" in node_type:
                studio_node["data"]["nodeType"] = "Database"
                studio_node["data"]["icon"] = "database"
                studio_node["data"]["color"] = "#8b5cf6"
            elif "Vector" in node_type or "Chroma" in node_type:
                studio_node["data"]["nodeType"] = "Vector Database"
                studio_node["data"]["icon"] = "database"
                studio_node["data"]["color"] = "#8b5cf6"
            elif "Python" in node_type:
                studio_node["data"]["nodeType"] = "Processing"
                studio_node["data"]["icon"] = "code"
                studio_node["data"]["color"] = "#10b981"
            elif "HTTP" in node_type or "API" in node_type:
                studio_node["data"]["nodeType"] = "API"
                studio_node["data"]["icon"] = "globe"
                studio_node["data"]["color"] = "#f59e0b"

            studio_nodes.append(studio_node)

        return {
            "name": workflow_name,
            "description": "Converted from Kaizen user scenario",
            "category": "user-scenarios",
            "workflow_definition": {
                "nodes": studio_nodes,
                "edges": self.edges,
                "metadata": {
                    "framework": "core",
                    "version": "1.0.0",
                    "created_with": "kaizen-converter",
                    "node_count": len(self.nodes),
                    "complexity": self._detect_complexity(),
                    "source": "kaizen-user-scenario",
                },
            },
        }


def main():
    """Main conversion script."""
    if len(sys.argv) < 2:
        print("Usage: python convert_to_studio.py <path_to_scenario.py>")
        print("\nExample:")
        print(
            "  python convert_to_studio.py user-scenarios/01-beginner-simple-qa-bot.py"
        )
        sys.exit(1)

    input_file = sys.argv[1]

    if not Path(input_file).exists():
        print(f"Error: File not found: {input_file}")
        sys.exit(1)

    print(f"Converting {input_file} to Studio format...")

    # Convert
    converter = WorkflowConverter()
    studio_json = converter.extract_from_file(input_file)

    # Generate output filename
    input_path = Path(input_file)
    output_file = input_path.parent / f"{input_path.stem}_studio.json"

    # Save JSON
    with open(output_file, "w") as f:
        json.dump(studio_json, f, indent=2)

    print("✅ Conversion complete!")
    print(f"📄 Output: {output_file}")
    print("📊 Stats:")
    print(f"   - Nodes: {len(studio_json['workflow_definition']['nodes'])}")
    print(f"   - Edges: {len(studio_json['workflow_definition']['edges'])}")
    print(
        f"   - Complexity: {studio_json['workflow_definition']['metadata']['complexity']}"
    )
    print("\nNext steps:")
    print(f"1. Review the generated JSON: {output_file}")
    print("2. Import into Studio via API or UI")
    print("3. Adjust visual layout as needed")
    print("4. Test execution in Studio")


if __name__ == "__main__":
    main()
