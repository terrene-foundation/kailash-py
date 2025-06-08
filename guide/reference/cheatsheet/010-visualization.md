# Visualization

```python
# Generate visualization
from kailash import WorkflowVisualizer
visualizer = WorkflowVisualizer()
visualizer.visualize(workflow, "workflow.png")

# Generate Mermaid diagram
from kailash.workflow.mermaid_visualizer import MermaidVisualizer
mermaid_code = MermaidVisualizer.generate(workflow)
```
