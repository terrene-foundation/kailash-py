# Common Mistakes to Avoid

## Node Naming

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

# ❌ WRONG - Missing "Node" suffix
workflow = Workflow("example", name="Example")
workflow.add_node("reader", CSVReader())
workflow.add_node("processor", DataTransformer())

# ✅ CORRECT - Always use "Node" suffix
workflow = Workflow("example", name="Example")
workflow.add_node("reader", CSVReaderNode())
workflow.add_node("processor", DataTransformerNode())

```

## Parameter Passing

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

# ❌ WRONG - Using 'inputs' instead of 'parameters'
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, inputs={"data": [1,2,3]})

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

# ❌ WRONG - Using camelCase
workflow = Workflow("example", name="Example")
workflow.addNode("reader", node)
workflow.connectNodes("reader", "processor")

# ✅ CORRECT - Use snake_case
workflow = Workflow("example", name="Example")
workflow.add_node("reader", node)
workflow.connect("reader", "processor")

```

## Execution Patterns

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

# ❌ WRONG - Direct workflow execution
workflow = Workflow("example", name="Example")
workflow.execute()  # Workflow has no execute method

# ❌ WRONG - Expecting only results
runtime = LocalRuntime()
results = runtime.execute(workflow)  # Returns tuple

# ✅ CORRECT - Runtime returns tuple
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

```

## Connection Mapping

```python
# ❌ WRONG - No mapping for PythonCodeNode
workflow.connect("python_node", "next_node")
# PythonCodeNode outputs nested structure {"result": {...}}

# ✅ CORRECT - Use nested paths
workflow.connect("python_node", "next_node",
    mapping={"result.data": "input_data"})

```

## Cycle Configuration

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

# ❌ WRONG - Multiple cycle=True edges
workflow = Workflow("example", name="Example")
workflow.connect("A", "B", cycle=True)
workflow.connect("B", "C", cycle=True)
workflow.connect("C", "A", cycle=True)

# ✅ CORRECT - Only mark closing edge
workflow = Workflow("example", name="Example")
workflow.connect("A", "B")  # Regular
workflow.connect("B", "C")  # Regular
workflow.connect("C", "A", cycle=True, max_iterations=10)  # Closing edge only

```

## Environment Variables

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

# ❌ WRONG - Hardcoded credentials
workflow = Workflow("example", name="Example")
workflow.add_node("api", HTTPRequestNode(
    api_key="sk-1234567890abcdef"
))

# ✅ CORRECT - Use environment variables
import os
workflow = Workflow("example", name="Example")
workflow.add_node("api", HTTPRequestNode(
    api_key=os.getenv("API_KEY")
))

```

## Error Handling

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

# ❌ WRONG - No error handling
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)
data = results["processor"]["data"]  # KeyError if node failed

# ✅ CORRECT - Check for errors
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)
if "processor" in results and "error" not in results["processor"]:
    data = results["processor"].get("data", [])
else:
    print(f"Processing failed: {results.get('processor', {}).get('error')}")

```

## File Paths

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

# ❌ WRONG - Relative paths in production
workflow = Workflow("example", name="Example")
workflow.add_node("reader", CSVReaderNode(
    file_path="../data/input.csv"  # Breaks when working directory changes
))

# ✅ CORRECT - Use data path methods
workflow = Workflow("example", name="Example")
workflow.add_node("reader", CSVReaderNode(
    file_path=workflow.get_input_data_path("input.csv")
))

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
# ❌ WRONG - Importing from wrong modules
from kailash.core import Workflow  # No such module
from kailash.runtime import Runtime  # Too generic

# ✅ CORRECT - Proper imports
from kailash import Workflow
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
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
import json

# Example setup
workflow = Workflow("example", name="Example")
runtime = LocalRuntime()

# Execute and inspect results
results, run_id = runtime.execute(workflow)
print(json.dumps(results, indent=2))  # See actual structure
   ```

3. **Use Workflow Visualization**:
   ```python
from kailash.visualization import visualize_workflow
visualize_workflow(workflow, "debug.png")
   ```

## Next Steps
- [Troubleshooting guide](../developer/05-troubleshooting.md)
- [Best practices](040-pythoncode-best-practices.md)
