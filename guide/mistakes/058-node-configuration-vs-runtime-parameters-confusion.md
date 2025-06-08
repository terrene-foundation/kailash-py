# Mistake #058: Node Configuration vs Runtime Parameters Confusion

## Problem
The #1 most common mistake - trying to pass runtime data as node configuration.

### Bad Example
```python
# BAD - Runtime data passed as config
workflow.add_node("processor", PythonCodeNode(),
    data=[1, 2, 3])  # Error: 'data' is not a config parameter!

# GOOD - Config defines behavior, data flows through connections
workflow.add_node("processor", PythonCodeNode(),
    code="result = [x * 2 for x in data]")  # Config: HOW to process
workflow.connect("source", "processor", mapping={"output": "data"})

```

## Solution
Remember - Config=HOW (static), Runtime=WHAT (dynamic data)

## Impact
Causes TypeError or "missing required inputs" errors

## Lesson Learned
Node configuration parameters define behavior (code, file paths, models), while runtime data flows through connections or is injected via runtime.execute()

## Fixed In
Session 28 - Cyclic workflow implementation

## Categories
api-design, workflow, configuration

---
