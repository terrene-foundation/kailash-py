# Mistake #055: Assumption That Workflows Must Start with Source Nodes

## Problem
Incorrect assumption that workflows require source nodes to provide initial data.

### Bad Example
```python
# MISCONCEPTION - Thinking this is the only way
workflow.add_node("reader", CSVReaderNode(), file_path="data.csv")
workflow.add_node("processor", ProcessorNode())
workflow.connect("reader", "processor")

# REALITY - Multiple patterns are supported
# Pattern 1: External data injection
workflow.add_node("processor", ProcessorNode())
runtime.execute(workflow, parameters={
    "processor": {"data": [1, 2, 3]}
})

# Pattern 2: Hybrid approach
workflow.add_node("reader", CSVReaderNode(), file_path="default.csv")
runtime.execute(workflow, parameters={
    "reader": {"file_path": "custom.csv"}  # Override
})

```

## Solution
Documented that workflows support multiple input patterns:
1. Source nodes (traditional ETL pattern)
2. External data via parameters (flexible/dynamic pattern)
3. Hybrid approaches with parameter overrides
4. Multiple entry points in a single workflow

**Key Learning**: The Kailash SDK is designed for flexibility:
- Any node can be an entry point
- Data can come from files, APIs, or runtime parameters
- The `parameters` mechanism in `runtime.execute()` provides maximum flexibility

## Impact
- Overly complex workflows when simple data injection would suffice
- Confusion about workflow validation errors
- Missed opportunities for flexible workflow design

## Fixed In
Session 40 - Added comprehensive documentation and examples

## Related Issues
#49 (Missing Data Source Nodes), #53 (Configuration vs Runtime)

## Categories
workflow

---
