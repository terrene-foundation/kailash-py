# Mistake #056: Inconsistent Connection APIs Between Workflow and WorkflowBuilder

## Problem
The `Workflow` and `WorkflowBuilder` classes have different APIs for connecting nodes.

### Bad Example
```python
# Workflow uses connect() with mapping dict
workflow.connect("source", "target", mapping={"output": "input"})

# WorkflowBuilder uses add_connection() with 4 parameters
builder.add_connection("source", "output", "target", "input")

# This causes confusion and errors
builder.connect("node1", "node2")  # AttributeError: no 'connect' method
builder.add_edge("node1", "node2")  # AttributeError: no 'add_edge' method

```

## Solution
Documented the inconsistency in validation-guide.md and recommended using `Workflow.connect()` directly for consistency. The WorkflowBuilder pattern adds complexity without clear benefits.

**Key Learning**: API consistency is crucial for developer experience. Having two different ways to do the same thing (connect nodes) with different method names and signatures creates unnecessary cognitive load.

## Impact
- API inconsistency causes confusion when switching between patterns
- Examples using wrong method names fail
- Different parameter patterns require different mental models

## Fixed In
Session 40 - Added documentation about the inconsistency

## Related Issues
Integration examples had incorrect method calls

## Categories
api-design, workflow

---
