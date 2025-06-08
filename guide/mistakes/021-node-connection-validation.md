# Mistake #021: Node Connection Validation

## Problem
Allowing invalid node connections in workflows.

### Bad Example
```python
# BAD - No connection validation
workflow.connect("source", "sink", {"output": "wrong_input"})

# GOOD - Validate connections
def connect(self, source, target, mapping):
    source_outputs = self.nodes[source].get_output_schema()
    target_inputs = self.nodes[target].get_parameters()
    # Validate mapping compatibility

```

## Solution


## Fixed In
Workflow validation improvements

## Categories
workflow, security

---
