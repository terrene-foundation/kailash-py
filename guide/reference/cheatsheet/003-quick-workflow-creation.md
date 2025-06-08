# Quick Workflow Creation

## Method 1: Direct Construction (Recommended)
```python
# Create workflow with ID and name
workflow = Workflow("wf-001", name="my_pipeline")

# Add nodes with CONFIGURATION parameters (static settings)
workflow.add_node("reader", CSVReaderNode(), file_path="input.csv")  # WHERE to read
workflow.add_node("processor", DataTransformerNode(),
    operations=[{"type": "filter", "condition": "age > 18"}]  # HOW to process
)
workflow.add_node("writer", CSVWriterNode(), file_path="output.csv")  # WHERE to write

# Connect nodes - RUNTIME data flows through these connections
workflow.connect("reader", "processor")  # Automatic mapping when names match
workflow.connect("processor", "writer", mapping={"transformed": "data"})  # Explicit mapping

# Execute with runtime (ALWAYS RECOMMENDED)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

# With parameter overrides
results, run_id = runtime.execute(workflow, parameters={
    "reader": {"file_path": "custom.csv"}  # Override at runtime
})

# Direct execution (less features, no tracking)
results = workflow.execute()  # Note: No 'inputs' parameter
```

## Method 2: Builder Pattern (Deprecated - Use Method 1)
```python
# NOTE: WorkflowBuilder can cause confusion. Prefer Workflow.connect() instead.
workflow = (WorkflowBuilder()
    .create("my_pipeline")
    .add_node("reader", CSVReaderNode, {"file_path": "input.csv"})
    .add_node("processor", DataTransformerNode, {
        "operations": [{"type": "filter", "condition": "age > 18"}]
    })
    .add_node("writer", CSVWriterNode, {"file_path": "output.csv"})
    .connect("reader", "processor")
    .connect("processor", "writer")
    .build()
)
```
