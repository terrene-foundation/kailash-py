# Common Mistakes to Avoid

## Node Naming

```python
# Modern SDK Setup
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Example setup
workflow = WorkflowBuilder()

# ❌ WRONG - Instance-based node creation (deprecated)
workflow.add_node("CSVReaderNode", "reader", {}), {})
workflow.add_node("DataTransformerNode", "processor", {}), {})

# ✅ CORRECT - String-based node creation with WorkflowBuilder
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("DataTransformerNode", "processor", {"operations": []})

```

## Parameter Passing

```python
# Modern SDK Setup
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Example setup
workflow = WorkflowBuilder()

# ❌ WRONG - Using 'inputs' instead of 'parameters'
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={"data": [1,2,3]})

# ❌ WRONG - Flat parameters for node-specific data
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={"data": [1,2,3]})

# ✅ CORRECT - Node-specific parameters
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "processor": {"data": [1,2,3], "threshold": 0.8}
})

```

## API Conventions

```python
# Modern SDK Setup
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Example setup
workflow = WorkflowBuilder()

# ❌ WRONG - Using camelCase
workflow = WorkflowBuilder()
workflow.addNode("reader", node)
workflow.connectNodes("reader", "processor")

# ✅ CORRECT - Use snake_case
workflow = WorkflowBuilder()
workflow.add_node("reader", node)
workflow.add_connection("reader", "result", "processor", "input")

```

## Execution Patterns

```python
# Modern SDK Setup
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Example setup
workflow = WorkflowBuilder()

# ❌ WRONG - Direct workflow execution
workflow = WorkflowBuilder()
runtime.execute(workflow.build(), )  # Workflow has no execute method

# ❌ WRONG - Expecting only results
runtime = LocalRuntime()
results = runtime.execute(workflow.build())  # Returns tuple

# ✅ CORRECT - Runtime returns tuple with built workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

```

## Connection Mapping

```python
# ❌ WRONG - Old connect syntax (deprecated)
# workflow.add_connection("python_node", "result", "next_node", "input")

# ✅ CORRECT - Use 4-parameter add_connection with dot notation
workflow.add_connection("python_node", "result", "next_node", "input_data")
# Or access nested fields with dot notation
workflow.add_connection("python_node", "result.data", "next_node", "input_data")

```

## Cycle Configuration

```python
# Modern SDK Setup
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Example setup
workflow = WorkflowBuilder()

# ❌ WRONG - Deprecated # Use CycleBuilder API instead syntax
# # Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()  # DEPRECATED
# # Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()  # DEPRECATED

# ✅ CORRECT - Use CycleBuilder API
workflow.add_connection("A", "result", "B", "input")  # Regular
workflow.add_connection("B", "result", "C", "input")  # Regular

# For cycles, build workflow first then create cycle
built_workflow = workflow.build()
cycle = built_workflow.create_cycle("main_cycle")
cycle.connect("C", "A") \
     .max_iterations(10) \
     .converge_when("condition == True") \
     .build()

```

## Environment Variables

```python
# Modern SDK Setup
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Example setup
workflow = WorkflowBuilder()

# ❌ WRONG - Hardcoded credentials
workflow.add_node("HTTPRequestNode", "api", {
    "api_key": "sk-1234567890abcdef"  # NEVER hardcode secrets!
})

# ✅ CORRECT - Use environment variables
import os
workflow.add_node("HTTPRequestNode", "api", {
    "api_key": os.getenv("API_KEY"),
    "url": "https://api.example.com"
})

```

## Error Handling

```python
# Modern SDK Setup
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Example setup
workflow = WorkflowBuilder()

# ❌ WRONG - No error handling
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
data = results["processor"]["data"]  # KeyError if node failed

# ✅ CORRECT - Check for errors
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
if "processor" in results and "error" not in results["processor"]:
    data = results["processor"].get("data", [])
else:
    print(f"Processing failed: {results.get('processor', {}).get('error')}")

```

## File Paths

```python
# Modern SDK Setup
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Example setup
workflow = WorkflowBuilder()

# ❌ WRONG - Relative paths in production
workflow.add_node("CSVReaderNode", "reader", {
    "file_path": "../data/input.csv"  # Breaks when working directory changes
})

# ✅ CORRECT - Use absolute paths or data methods
import os
workflow.add_node("CSVReaderNode", "reader", {
    "file_path": os.path.abspath("data/input.csv")
})
# Or use data directory pattern
workflow.add_node("CSVReaderNode", "reader", {
    "file_path": "data/input.csv"  # Will be resolved relative to project root
})

```

## Node Initialization

```python
# ❌ WRONG - Setting attributes after super().__init__()
class CustomNode(Node):
    def __init__(self, threshold=0.8):
        super().__init__()
        self.threshold = threshold  # Too late!

# ✅ CORRECT - Set attributes before super().__init__()
class CustomNode(Node):
    def __init__(self, threshold=0.8):
        self.threshold = threshold  # Set first
        super().__init__()

```

## Async Operations

```python
# ❌ WRONG - Blocking in async context
import time
class SlowNode(Node):
    async def run(self, context, **kwargs):
        time.sleep(5)  # Blocks event loop!
        return {"done": True}

# ✅ CORRECT - Use async sleep
import asyncio
class SlowNode(Node):
    async def run(self, context, **kwargs):
        await asyncio.sleep(5)  # Non-blocking
        return {"done": True}

```

## Common Import Errors

```python
# ❌ WRONG - Importing from wrong modules or using deprecated imports
from kailash.core import Workflow  # No such module
from kailash.runtime import Runtime  # Too generic
from kailash.workflow.builder import WorkflowBuilder  # Old approach

# ✅ CORRECT - Modern imports
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

```

## Memory Management

```python
# ❌ WRONG - Loading entire file
class BadFileProcessor(Node):
    def run(self, context, **kwargs):
        with open("huge_file.csv") as f:
            data = f.read()  # Loads entire file!
            return {"lines": len(data.splitlines())}

# ✅ CORRECT - Stream processing
class GoodFileProcessor(Node):
    def run(self, context, **kwargs):
        line_count = 0
        with open("huge_file.csv") as f:
            for line in f:  # Streams line by line
                line_count += 1
        return {"lines": line_count}

```

## Debugging Tips

1. **Enable Debug Logging**:
   ```python
import logging
logging.basicConfig(level=logging.DEBUG)
   ```

2. **Check Node Output Structure**:
   ```python
# Modern SDK Setup
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
import json

# Example setup
workflow = WorkflowBuilder()
runtime = LocalRuntime()

# Execute and inspect results
results, run_id = runtime.execute(workflow.build())
print(json.dumps(results, indent=2))  # See actual structure
   ```

3. **Use Workflow Visualization**:
   ```python
from kailash.visualization import visualize_workflow
visualize_workflow(workflow.build(), "debug.png")
   ```

## Next Steps
- [Troubleshooting guide](../developer/05-troubleshooting.md)
- [Best practices](040-pythoncode-best-practices.md)
