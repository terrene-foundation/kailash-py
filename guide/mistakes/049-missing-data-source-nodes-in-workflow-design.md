# Mistake #049: Missing Data Source Nodes in Workflow Design

## Problem
Creating workflows that expect external input injection instead of starting with proper data source nodes.

### Bad Example
```python
# BAD - Workflow expects external input
def create_workflow():
    workflow = Workflow("processing_pipeline")
    processor = ProcessorNode()  # Expects external document_content
    workflow.add_node("processor", processor)
    # No data source - validation fails

    # Execution requires external input injection
    runtime.execute(workflow, {"processor": {"document_content": "external data"}})

# GOOD - Workflow starts with data source
def create_workflow():
    workflow = Workflow("complete_pipeline")
    data_source = DocumentInputNode()  # Provides data autonomously
    processor = ProcessorNode()
    workflow.add_node("source", data_source)
    workflow.add_node("processor", processor)
    workflow.connect("source", "processor", {"document_content": "document_content"})

    # Self-contained execution
    runtime.execute(workflow, {})  # No external input needed

```

## Solution
Always start workflows with proper data source nodes (CSVReaderNode, DocumentInputNode, etc.) that can provide initial data autonomously.
**Root Cause**: Misunderstanding workflow design pattern - workflows should be complete pipelines, not processing fragments.
**Workflow Pattern**: Data Source → Processing Node 1 → Processing Node 2 → Output Node

## Impact
Workflow validation fails with "Node 'X' missing required inputs" because the workflow expects self-contained data flow.

## Lesson Learned
Workflow validation errors about missing inputs are correct behavior - they enforce proper workflow architecture.

## Fixed In
Session 35 - Hierarchical RAG workflow redesign

## Categories
workflow

---
