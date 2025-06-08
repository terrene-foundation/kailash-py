# Mistake #007: Workflow Validation Errors

## Problem
Tests creating workflows without required source nodes.

### Bad Example
```python
# BAD - Missing source nodes
workflow.add_node("processor", ProcessorNode())
workflow.execute()  # Fails - no data sources

# GOOD - Include source nodes
workflow.add_node("reader", CSVReaderNode())
workflow.add_node("processor", ProcessorNode())
workflow.connect("reader", "processor")

```

## Solution


## Fixed In
Session 27 - Performance tracking tests

## Categories
workflow, security

---
