# Export Workflows

```python
# Export to YAML
from kailash.utils.export import export_workflow
export_workflow(workflow, "workflow.yaml", format="yaml")

# Export to dictionary
workflow_dict = workflow.to_dict()

# Load from dictionary
loaded_workflow = Workflow.from_dict(workflow_dict)
```
