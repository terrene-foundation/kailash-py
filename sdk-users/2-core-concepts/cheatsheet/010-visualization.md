# Workflow Visualization & Debugging

## Basic Workflow Visualization
```python
from kailash.workflow.builder import WorkflowBuilderVisualizer
from kailash.workflow.mermaid_visualizer import MermaidVisualizer

# Create visualizer
visualizer = WorkflowVisualizer()

# Generate PNG/SVG diagram
visualizer.visualize(workflow,
    output_path="my_workflow.png",
    format="png",           # Options: png, svg, pdf
    layout="hierarchical",  # Options: hierarchical, circular, spring
    include_parameters=True,
    show_data_types=True
)

# Generate interactive HTML
visualizer.visualize(workflow,
    output_path="workflow.html",
    format="html",
    interactive=True,
    include_execution_stats=True
)

```

## Mermaid Diagrams (GitHub/Markdown Compatible)
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Generate Mermaid code for documentation
mermaid_code = MermaidVisualizer.generate(workflow,
    direction="TD",         # Top-Down (or LR for Left-Right)
    include_node_types=True,
    include_parameters=False,
    style="minimal"         # minimal, detailed, or full
)

# Save to markdown file
with open("workflow_diagram.md", "w") as f:
    f.write("```mermaid\n")
    f.write(mermaid_code)
    f.write("\n```")

print("Mermaid diagram:")
print(mermaid_code)

```

## Runtime Visualization
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Visualize workflow with execution results
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Show execution flow with timing
execution_visualizer = WorkflowVisualizer(include_execution_data=True)
execution_visualizer.visualize(workflow,
    output_path="execution_flow.png",
    execution_results=results,
    show_timing=True,
    show_data_flow=True,
    highlight_errors=True
)

```

## Advanced Visualization Options
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Detailed visualization with all information
visualizer.visualize(workflow,
    output_path="detailed_workflow.svg",
    format="svg",

    # Node information
    include_parameters=True,
    include_node_types=True,
    include_descriptions=True,

    # Connection information
    show_data_types=True,
    show_mapping_details=True,

    # Layout options
    layout="hierarchical",
    node_spacing=100,
    level_spacing=150,

    # Styling
    color_by_type=True,
    custom_colors={
        "CSVReaderNode": "#4CAF50",
        "PythonCodeNode": "#2196F3",
        "CSVWriterNode": "#FF9800"
    }
)

```

## Debugging Workflows Visually
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Debug mode visualization
debug_visualizer = WorkflowVisualizer(debug_mode=True)

# Show potential issues
debug_visualizer.visualize(workflow,
    output_path="debug_workflow.png",

    # Highlight problems
    highlight_unconnected_nodes=True,
    highlight_missing_parameters=True,
    highlight_type_mismatches=True,

    # Show validation info
    include_validation_status=True,
    show_data_flow_analysis=True
)

# Generate debug report
debug_report = debug_visualizer.generate_debug_report(workflow)
print("Debug Issues Found:")
for issue in debug_report["issues"]:
    print(f"- {issue['severity']}: {issue['message']}")

```

## Export Options
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Multiple format export
formats = ["png", "svg", "pdf", "html", "mermaid"]

for fmt in formats:
    visualizer.visualize(workflow,
        output_path=f"workflow.{fmt}",
        format=fmt,
        include_parameters=True
    )

# Programmatic access to graph data
graph_data = visualizer.get_graph_data(workflow)
print("Nodes:", [node["id"] for node in graph_data["nodes"]])
print("Edges:", [(edge["from"], edge["to"]) for edge in graph_data["edges"]])

```

## Integration with Jupyter Notebooks
```python
# Display in Jupyter notebook
from IPython.display import Image, SVG, HTML

# PNG for simple display
workflow_png = visualizer.visualize(workflow, format="png", return_data=True)
Image(workflow_png)

# SVG for scalable display
workflow_svg = visualizer.visualize(workflow, format="svg", return_data=True)
SVG(workflow_svg)

# Interactive HTML
workflow_html = visualizer.visualize(workflow, format="html", return_data=True)
HTML(workflow_html)

```

## Command Line Visualization
```bash
# CLI tool for quick visualization
kailash visualize my_workflow.py --output workflow.png --format png
kailash visualize my_workflow.py --output workflow.html --interactive
kailash visualize my_workflow.py --output README.md --format mermaid
```

## Quick Debugging Commands
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# One-liner for quick debugging
workflow.visualize()  # Opens default viewer

# Quick validation check
workflow.validate_and_visualize()  # Shows issues visually

# Performance analysis
workflow.analyze_performance()  # Shows bottlenecks

```

## Visualization Best Practices
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# For documentation - use Mermaid
mermaid_code = MermaidVisualizer.generate(workflow, style="minimal")

# For debugging - use detailed PNG/SVG
visualizer.visualize(workflow, "debug.png", include_parameters=True)

# For presentations - use clean HTML
visualizer.visualize(workflow, "presentation.html",
    format="html", style="clean", interactive=False)

# For development - use interactive HTML
visualizer.visualize(workflow, "dev.html",
    format="html", interactive=True, include_execution_stats=True)

```

## Custom Visualization Themes
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Define custom theme
custom_theme = {
    "background_color": "#f8f9fa",
    "node_colors": {
        "data": "#28a745",
        "transform": "#007bff",
        "ai": "#6f42c1",
        "output": "#fd7e14"
    },
    "edge_color": "#6c757d",
    "text_color": "#212529",
    "font_family": "Arial, sans-serif"
}

# Apply theme
visualizer.visualize(workflow,
    output_path="themed_workflow.png",
    theme=custom_theme
)

```

## Next Steps
- [Export Workflows](009-export-workflows.md) - Save and share workflows
- [Performance Optimization](026-performance-optimization.md) - Optimize based on visualizations
- [Troubleshooting](../developer/07-troubleshooting.md) - Advanced debugging techniques
