"""Workflow visualization utilities.

Generates Mermaid diagrams and DOT format output for workflow graphs.
No external dependencies required — renders in GitHub, IDEs, and any
Markdown viewer that supports Mermaid.
"""

from pathlib import Path
from typing import Any

from kailash.workflow.graph import Workflow


class WorkflowVisualizer:
    """Visualize workflows as Mermaid diagrams and DOT graphs.

    Outputs text-based formats that render natively in GitHub, VS Code,
    JetBrains, Jupyter, and any Mermaid-compatible viewer.
    """

    def __init__(
        self,
        workflow: Workflow | None = None,
        direction: str = "TB",
    ):
        self.workflow = workflow
        self.direction = direction

    def _get_node_shape(self, node_type: str) -> tuple[str, str]:
        """Return Mermaid node delimiters based on type."""
        if "Reader" in node_type or "Writer" in node_type:
            return "[(", ")]"  # stadium
        elif (
            "Switch" in node_type or "Merge" in node_type or "Conditional" in node_type
        ):
            return "{", "}"  # diamond
        elif "AI" in node_type or "LLM" in node_type or "Model" in node_type:
            return "[[", "]]"  # subroutine
        elif "Code" in node_type or "Python" in node_type:
            return "[/", "/]"  # parallelogram
        return "[", "]"  # rectangle (default)

    def _sanitize_id(self, node_id: str) -> str:
        """Sanitize node ID for Mermaid compatibility."""
        return node_id.replace(" ", "_").replace("-", "_").replace(".", "_")

    def to_mermaid(self, workflow: Workflow | None = None) -> str:
        """Generate Mermaid diagram syntax.

        Args:
            workflow: Workflow to visualize (uses self.workflow if not provided)

        Returns:
            Mermaid diagram string
        """
        wf = workflow or self.workflow
        if not wf:
            raise ValueError("No workflow provided")

        lines = [f"graph {self.direction}"]

        # Define nodes with shapes based on type
        for node_id in wf.graph.nodes():
            safe_id = self._sanitize_id(node_id)
            node_instance = wf.nodes.get(node_id)
            if node_instance:
                node_type = node_instance.node_type
                label = f"{node_id}\\n({node_type})"
                open_d, close_d = self._get_node_shape(node_type)
            else:
                label = node_id
                open_d, close_d = "[", "]"
            lines.append(f'    {safe_id}{open_d}"{label}"{close_d}')

        # Define edges
        for source, target, data in wf.graph.edges(data=True):
            safe_source = self._sanitize_id(source)
            safe_target = self._sanitize_id(target)

            from_output = data.get("from_output")
            to_input = data.get("to_input")
            mapping = data.get("mapping", {})

            if from_output and to_input:
                label = f"{from_output} -> {to_input}"
                lines.append(f"    {safe_source} -->|{label}| {safe_target}")
            elif mapping:
                parts = [f"{s}->{d}" for s, d in mapping.items()]
                label = ", ".join(parts)
                lines.append(f"    {safe_source} -->|{label}| {safe_target}")
            else:
                lines.append(f"    {safe_source} --> {safe_target}")

        # Add style classes
        for node_id in wf.graph.nodes():
            safe_id = self._sanitize_id(node_id)
            node_instance = wf.nodes.get(node_id)
            if node_instance:
                node_type = node_instance.node_type
                if "Reader" in node_type or "Writer" in node_type:
                    lines.append(f"    style {safe_id} fill:#e1f5fe,stroke:#01579b")
                elif "AI" in node_type or "LLM" in node_type:
                    lines.append(f"    style {safe_id} fill:#e8f5e9,stroke:#1b5e20")
                elif "Switch" in node_type or "Conditional" in node_type:
                    lines.append(f"    style {safe_id} fill:#fce4ec,stroke:#880e4f")
                elif "Code" in node_type or "Python" in node_type:
                    lines.append(f"    style {safe_id} fill:#fffde7,stroke:#f57f17")

        return "\n".join(lines)

    def to_dot(self, workflow: Workflow | None = None) -> str:
        """Generate DOT (Graphviz) format.

        Args:
            workflow: Workflow to visualize (uses self.workflow if not provided)

        Returns:
            DOT format string (render with `dot -Tsvg workflow.dot -o workflow.svg`)
        """
        wf = workflow or self.workflow
        if not wf:
            raise ValueError("No workflow provided")

        lines = [
            f'digraph "{wf.name}" {{',
            "    rankdir=TB;",
            '    node [shape=box, style="rounded,filled", fontname="Arial"];',
            '    edge [fontname="Arial", fontsize=10];',
        ]

        # Node type to color mapping
        color_map = {
            "data": "#e1f5fe",
            "transform": "#fff3e0",
            "logic": "#fce4ec",
            "ai": "#e8f5e9",
            "code": "#fffde7",
            "default": "#f5f5f5",
        }

        for node_id in wf.graph.nodes():
            node_instance = wf.nodes.get(node_id)
            if node_instance:
                node_type = node_instance.node_type
                label = f"{node_id}\\n({node_type})"
                # Determine color category
                nt_lower = node_type.lower()
                if "reader" in nt_lower or "writer" in nt_lower:
                    color = color_map["data"]
                elif "ai" in nt_lower or "llm" in nt_lower:
                    color = color_map["ai"]
                elif "switch" in nt_lower or "conditional" in nt_lower:
                    color = color_map["logic"]
                elif "code" in nt_lower or "python" in nt_lower:
                    color = color_map["code"]
                else:
                    color = color_map["default"]
            else:
                label = node_id
                color = color_map["default"]

            lines.append(f'    "{node_id}" [label="{label}", fillcolor="{color}"];')

        for source, target, data in wf.graph.edges(data=True):
            mapping = data.get("mapping", {})
            if mapping:
                parts = [f"{s}->{d}" for s, d in mapping.items()]
                label = ", ".join(parts)
                lines.append(f'    "{source}" -> "{target}" [label="{label}"];')
            else:
                lines.append(f'    "{source}" -> "{target}";')

        lines.append("}")
        return "\n".join(lines)

    def visualize(
        self,
        output_path: str | None = None,
        format: str = "mermaid",
        **kwargs,
    ) -> str:
        """Generate visualization output.

        Args:
            output_path: Path to save output. If None, returns the string.
            format: Output format — "mermaid" (default) or "dot"

        Returns:
            The diagram string (Mermaid or DOT format)
        """
        if format == "dot":
            content = self.to_dot()
        else:
            content = self.to_mermaid()

        if output_path:
            path = Path(output_path)
            if format == "mermaid" and not path.suffix:
                path = path.with_suffix(".md")
                content = f"```mermaid\n{content}\n```"
            elif format == "dot" and not path.suffix:
                path = path.with_suffix(".dot")

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

        return content

    def save(self, output_path: str, format: str = "mermaid", **kwargs) -> None:
        """Save visualization to file."""
        self.visualize(output_path=output_path, format=format, **kwargs)

    def create_execution_graph(
        self, run_id: str, task_manager: Any, output_path: str | None = None
    ) -> str:
        """Create a Mermaid visualization showing execution status.

        Args:
            run_id: Run ID to visualize
            task_manager: Task manager instance
            output_path: Optional path to save the markdown file

        Returns:
            Path to the created markdown file
        """
        from kailash.tracking import TaskStatus
        from kailash.workflow.mermaid_visualizer import MermaidVisualizer

        tasks = task_manager.list_tasks(run_id)

        status_emojis = {
            TaskStatus.PENDING: "⏳",
            TaskStatus.RUNNING: "🔄",
            TaskStatus.COMPLETED: "✅",
            TaskStatus.FAILED: "❌",
            TaskStatus.SKIPPED: "⏭️",
        }

        node_status = {}
        for task in tasks:
            node_status[task.node_id] = task.status

        visualizer = MermaidVisualizer(self.workflow)
        mermaid_code = visualizer.generate()

        lines = mermaid_code.split("\n")
        new_lines = []

        for line in lines:
            new_lines.append(line)
            for node_id, status in node_status.items():
                sanitized_id = visualizer._sanitize_node_id(node_id)
                if sanitized_id in line and '["' in line:
                    emoji = status_emojis.get(status, "")
                    if emoji:
                        new_lines[-1] = line.replace('"]', f' {emoji}"]')

        newline_joined = "\n".join(new_lines)
        markdown_content = f"""# Workflow Execution Status

**Run ID**: `{run_id}`
**Workflow**: {self.workflow.name}

## Execution Diagram

```mermaid
{newline_joined}
```

## Status Legend

| Status | Symbol |
|--------|--------|
| Pending | ⏳ |
| Running | 🔄 |
| Completed | ✅ |
| Failed | ❌ |
| Skipped | ⏭️ |

## Task Details

| Node ID | Status | Duration |
|---------|--------|----------|
"""
        for task in tasks:
            status_emoji = status_emojis.get(task.status, "")
            duration = f"{task.duration:.2f}s" if task.duration else "N/A"
            markdown_content += f"| {task.node_id} | {task.status.value} {status_emoji} | {duration} |\n"

        if output_path is None:
            project_root = Path(__file__).parent.parent.parent.parent
            output_dir = (
                project_root
                / "data"
                / "outputs"
                / "visualizations"
                / "workflow_executions"
            )
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / f"execution_{run_id}.md")
        else:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            f.write(markdown_content)

        return output_path


# Add visualization method to Workflow class
def add_visualization_to_workflow():
    """Add visualization method to Workflow class."""

    def visualize(
        self, output_path: str | None = None, format: str = "mermaid", **kwargs
    ) -> str:
        """Visualize the workflow as Mermaid or DOT.

        Args:
            output_path: Path to save the visualization
            format: "mermaid" (default) or "dot"

        Returns:
            The diagram string
        """
        visualizer = WorkflowVisualizer(self)
        return visualizer.visualize(output_path, format=format, **kwargs)

    Workflow.visualize = visualize


add_visualization_to_workflow()
