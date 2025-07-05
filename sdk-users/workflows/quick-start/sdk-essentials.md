# Kailash SDK Essentials

**Critical patterns covering 80% of common issues** - Consolidated from 74 mistakes and key API patterns.

## 🚨 The Golden Rules (MEMORIZE)

### 1. Config vs Runtime (Mistake #001 - THE #1 ISSUE)
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# ✅ CORRECT: Config = HOW (static setup), Runtime = WHAT (dynamic data)
workflow = Workflow("example", name="Example")
workflow.  # Method signature)

# Execution: Runtime = WHAT data to process
runtime = LocalRuntime()
# Parameters setup
workflow.{
    "processor": {"data": [1, 2, 3]}  # Runtime: WHAT actual data
})

# ❌ WRONG: Mixing config and runtime
workflow = Workflow("example", name="Example")
workflow.  # Method signature)

```

### 2. Node Naming Convention
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# ✅ CORRECT: ALL node classes end with "Node"
CSVReaderNode, PythonCodeNode, SwitchNode

# ❌ WRONG: Missing "Node" suffix
CSVReader, PythonCode, Switch

```

### 3. Workflow Connection Pattern
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# ✅ CORRECT: Use Workflow.connect() with mapping
workflow = Workflow("example", name="Example")
workflow.workflow = Workflow("example", name="Example")
  # Method signature

# ❌ WRONG: Using WorkflowBuilder (different API)
builder = WorkflowBuilder()  # Different API, causes confusion

```

### 4. PythonCodeNode Constructor
```python
# ✅ CORRECT: Always include name parameter FIRST
PythonCodeNode(name="my_node", code="result = data * 2")

# ❌ WRONG: Missing name parameter
PythonCodeNode(code="result = data * 2")  # TypeError

```

## 🔄 Cycle Patterns (Critical for Iterative Workflows)

### Basic Cycle Setup
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Create cycle with specific field mapping (NOT generic)
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature

# ✅ CRITICAL: Use specific field mapping in cycles
# ❌ NEVER: {"output": "output"} - generic mapping fails in cycles

```

### Cycle Parameter Access (Safe Pattern)
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

workflow = Workflow("example", name="Example")
workflow.  # Method signature)

```

### Convergence Check Pattern
```python
# ✅ CORRECT: Use direct field names
convergence_check="converged == True"
convergence_check="error < 0.01"
convergence_check="count >= 10"

# ❌ WRONG: Nested path access
convergence_check="result.converged == True"  # Fails

```

## 📊 Data Handling Essentials

### PythonCodeNode Data Processing
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

workflow = Workflow("example", name="Example")
workflow.  # Method signature
result = {
    "data": df.to_dict('records'),        # JSON serializable
    "summary": df.describe().to_dict(),   # Convert all pandas objects
    "shape": df.shape                     # Tuples are fine
}

# ✅ CRITICAL: NumPy array serialization
arr = np.array([1, 2, 3])
result["array"] = arr.tolist()  # Convert to list

# ✅ CRITICAL: Use bare except (not specific exceptions)
try:
    risky_operation()
except:  # ✅ Bare except works in sandbox
    result["error"] = "Operation failed"
'''
))

```

### Multi-Node Input Pattern
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# ✅ CORRECT: Use MergeNode for multiple inputs
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("merger", MergeNode())
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature

# ❌ WRONG: Direct multi-input without merge
# Multiple connections to same node without MergeNode fails

```

## 🤖 AI/LLM Integration

### LLMAgentNode with MCP (Modern Pattern)
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# ✅ CORRECT: Built-in MCP capabilities
workflow = Workflow("example", name="Example")
workflow.  # Method signature)

# ❌ WRONG: Separate MCPClient node (deprecated pattern)
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("mcp_client", MCPClientNode())  # Overly complex

```

### Iterative Agent Pattern
```python
# ✅ MODERN: Use IterativeLLMAgentNode for complex analysis
workflow.add_node("strategy_agent", IterativeLLMAgentNode(
    provider="ollama",
    model="llama3.2",
    max_iterations=4,
    convergence_criteria={
        "goal_satisfaction": {"threshold": 0.85}
    },
    mcp_servers=[...],  # MCP integration built-in
    auto_discover_tools=True
))

```

## 🔧 Async Patterns (Default Approach)

### Async Execution
```python
# ✅ CORRECT: Use async patterns by default
from kailash.runtime.async_local import AsyncLocalRuntime

async def run_workflow():
    runtime = AsyncLocalRuntime()
    results, run_id = await runtime.execute(workflow, parameters=params)
    return results

# TaskGroup error fix
import asyncio
try:
    asyncio.run(run_workflow())
except RuntimeError as e:
    if "unhandled errors in a TaskGroup" in str(e):
        # Use AsyncNode instead of regular nodes for I/O operations
        pass

```

## 🚨 Critical Error Prevention

### 1. Parameter Validation Errors
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# ✅ PREVENT: "Required parameter 'data' not provided"
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("node", SomeNode(required=False))  # Use defaults
# OR provide all required parameters in runtime.execute()

```

### 2. Cycle State Persistence Issues
```python
# ✅ PREVENT: "KeyError: 'node_state'"
cycle_info = cycle_info or {}
prev_state = cycle_info.get("node_state") or {}  # Safe access

```

### 3. SwitchNode Mapping Issues
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# ✅ PREVENT: "ValueError: Required parameter 'input_data' not provided"
workflow = Workflow("example", name="Example")
workflow.  # Method signature
# NOT mapping={"output": "output"}

```

### 4. NumPy Compatibility Issues
```python
# ✅ PREVENT: "AttributeError: module 'numpy' has no attribute 'float128'"
import numpy as np
if hasattr(np, 'float128'):
    use_extended_precision = True
else:
    use_extended_precision = False

```

## 🎯 Quick Workflow Creation

### 30-Second ETL Pipeline
```python
from kailash import Workflow
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("reader", CSVReaderNode())
workflow.add_node("processor", PythonCodeNode(
    name="processor",
    code="result = [row for row in data if row.get('amount', 0) > 100]"
))
workflow.add_node("writer", CSVWriterNode())

# Connect
workflow.connect("reader", "processor", mapping={"data": "data"})
workflow.connect("processor", "writer", mapping={"result": "data"})

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "reader": {"file_path": "input.csv"},
    "writer": {"file_path": "output.csv"}
})

```

### 30-Second API Integration
```python
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("api_call", RestClientNode())
workflow.add_node("transformer", PythonCodeNode(
    name="transformer",
    code="result = {'processed': len(response.get('data', []))}"
))

workflow.connect("api_call", "transformer", mapping={"response": "response"})

runtime.execute(workflow, parameters={
    "api_call": {
        "url": "https://api.example.com/data",
        "method": "GET",
        "headers": {"Authorization": "Bearer token"}
    }
})

```

## 📋 Validation Checklist

Before deploying any workflow:

- [ ] All node classes end with "Node"
- [ ] Config vs Runtime separation is clear
- [ ] PythonCodeNode has name parameter first
- [ ] Cycle connections use specific field mapping
- [ ] DataFrame/NumPy data is serialized with .to_dict()/.tolist()
- [ ] MCP integration uses LLMAgentNode, not separate client
- [ ] Async patterns used for I/O operations
- [ ] Error handling uses bare except in PythonCodeNode
- [ ] Required parameters have defaults or are provided at runtime

## 🔗 Next Steps

- **Complex Cycles**: See [cyclic-workflows-complete.md](../advanced/cyclic-workflows-complete.md)
- **AI Agents**: See [ai-agent-coordination.md](../advanced/ai-agent-coordination.md)
- **Production**: See [enterprise-integration.md](../advanced/enterprise-integration.md)
- **Industry Examples**: See [by-industry/](../by-industry/) workflows

---

*This reference consolidates learnings from 74 documented mistakes and 3+ years of SDK development. Following these patterns prevents 80% of common issues.*
