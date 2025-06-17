# Core Patterns

These are the fundamental patterns for working with Kailash SDK. Start here if you're new to the framework.

## 1. Linear Pipeline Pattern (ETL)

**Purpose**: Sequential data processing from source to destination

```python
from kailash import Workflow
from kailash.nodes.data import CSVReaderNode, JSONWriterNode
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = Workflow("etl_pipeline", "ETL Pipeline")

# Add nodes with configuration
workflow.add_node("reader", CSVReaderNode(), file_path="input.csv")
workflow.add_node("transformer", PythonCodeNode(),
    code="""
result = []
for row in data:
    row['processed'] = True
    row['timestamp'] = datetime.now().isoformat()
    result.append(row)
""",
    imports=["from datetime import datetime"]
)
workflow.add_node("writer", JSONWriterNode(), file_path="output.json")

# Connect in sequence
workflow.connect("reader", "transformer", mapping={"data": "data"})
workflow.connect("transformer", "writer", mapping={"result": "data"})

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)
print(f"Pipeline completed: {run_id}")

```

**Use Cases**:
- Data migration
- Report generation
- Batch processing
- Data transformation pipelines

**Variations**:

### With Error Handling
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Add validation node
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("validator", PythonCodeNode(),
    code="""
errors = []
valid_data = []
for row in data:
    if 'id' in row and 'name' in row:
        valid_data.append(row)
    else:
        errors.append(f"Invalid row: {row}")
result = {"valid": valid_data, "errors": errors}
"""
)

# Connect with validation
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature

```

### With Multiple Outputs
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Write to multiple formats
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("json_writer", JSONWriterNode(), file_path="output.json")
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("csv_writer", CSVWriterNode(), file_path="output.csv")

# Fork the output
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature

```

## 2. Direct Node Execution Pattern

**Purpose**: Quick operations without workflow orchestration

```python
from kailash.nodes.data import CSVReaderNode, JSONWriterNode

# Direct execution - no workflow needed
csv_reader = CSVReaderNode(file_path="data.csv")
data = csv_reader.run()  # Direct node execution

# Process data
processed_data = []
for row in data["data"]:
    processed_row = {
        "id": row["id"],
        "name": row["name"].upper(),
        "processed": True
    }
    processed_data.append(processed_row)

# Write results
json_writer = JSONWriterNode(file_path="output.json")
json_writer.run(data=processed_data)

print(f"Processed {len(processed_data)} records")

```

**Use Cases**:
- Prototyping
- Simple scripts
- One-off operations
- Testing individual nodes

**Variations**:

### With Async Execution
```python
import asyncio
from kailash.nodes.data import CSVReaderNode, JSONWriterNode

async def process_data_async():
    # Read data
    csv_reader = CSVReaderNode(file_path="data.csv")
    data = await csv_reader.run_async()

    # Process in parallel
    tasks = []
    for row in data["data"]:
        task = process_row_async(row)
        tasks.append(task)

    processed_data = await asyncio.gather(*tasks)

    # Write results
    json_writer = JSONWriterNode(file_path="output.json")
    await json_writer.run_async(data=processed_data)

    return len(processed_data)

async def process_row_async(row):
    # Simulate async processing
    await asyncio.sleep(0.01)
    return {
        "id": row["id"],
        "name": row["name"].upper(),
        "processed": True
    }

# Run async
result = asyncio.run(process_data_async())
print(f"Processed {result} records asynchronously")

```

### With Configuration Override
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Create node with default config
csv_reader = CSVReaderNode(file_path="default.csv", delimiter=",")

# Override at execution time
data = csv_reader.run(file_path="custom.csv", delimiter="|")

# Process and save
processed = [{"id": r["id"], "value": r["value"] * 2} for r in data["data"]]

# Dynamic output path
output_path = f"output_{len(processed)}_records.json"
json_writer = JSONWriterNode()
json_writer.run(data=processed, file_path=output_path)

```

## Key Differences

| Aspect | Linear Pipeline | Direct Execution |
|--------|----------------|------------------|
| **Use Case** | Production workflows | Quick scripts |
| **Orchestration** | Full workflow management | Manual control |
| **Error Handling** | Built-in workflow validation | Manual try/except |
| **Monitoring** | Task tracking, run IDs | Basic logging |
| **Reusability** | Export/import workflows | Copy/paste code |
| **Testing** | Workflow-level tests | Unit tests |

## Best Practices

1. **Choose Linear Pipeline when**:
   - Building production workflows
   - Need monitoring and tracking
   - Workflow will be reused
   - Multiple team members involved

2. **Choose Direct Execution when**:
   - Prototyping ideas
   - One-time data processing
   - Testing node behavior
   - Simple scripts

3. **Common Pitfalls**:
   - Don't use direct execution for complex multi-step processes
   - Don't skip error handling in production pipelines
   - Always validate data between nodes
   - Consider memory usage for large datasets

## See Also
- [Control Flow Patterns](02-control-flow-patterns.md) - Add conditional logic
- [Data Processing Patterns](03-data-processing-patterns.md) - Handle complex data flows
- [Error Handling Patterns](05-error-handling-patterns.md) - Build resilient workflows
