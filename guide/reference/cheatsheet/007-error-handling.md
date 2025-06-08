# Error Handling

```python
try:
    workflow.validate()  # Check workflow structure
    results = workflow.execute(inputs={})
except WorkflowValidationError as e:
    print(f"Workflow structure error: {e}")
except NodeExecutionError as e:
    print(f"Node {e.node_id} failed: {e}")
```
