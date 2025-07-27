# Kailash SDK Essentials

**Critical patterns covering 80% of common issues** - Consolidated from 74 mistakes and key API patterns.

## 🚨 The Golden Rules (MEMORIZE)

### 1. Config vs Runtime (Mistake #001 - THE #1 ISSUE)
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# ✅ CORRECT: Config = HOW (static setup), Runtime = WHAT (dynamic data)
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "processor", {"code": "result = data"})  # Config: HOW to process

# Execution: Runtime = WHAT data to process
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build(), parameters={
    "processor": {"data": [1, 2, 3]}  # Runtime: WHAT actual data
})

# ❌ WRONG: Mixing config and runtime
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "processor", {"code": "result = data"})

```

### 2. Node Naming Convention
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# ✅ CORRECT: ALL node classes end with "Node"
CSVReaderNode, PythonCodeNode, SwitchNode

# ❌ WRONG: Missing "Node" suffix
CSVReader, PythonCode, Switch

```

### 3. Workflow Connection Pattern
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# ✅ CORRECT: Use workflow.add_connection() with 4 parameters
workflow = WorkflowBuilder()
workflow.add_connection("source", "output", "target", "input")

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
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Create cycle with specific field mapping (NOT generic)
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "processor", {"code": "result = {'count': x + 1}"})
cycle_builder = workflow.create_cycle("improvement_cycle")
cycle_builder.connect("processor", "processor", mapping={"count": "x"}).max_iterations(10).build()

# ✅ CRITICAL: Use specific field mapping in cycles
# ❌ NEVER: {"output": "output"} - generic mapping fails in cycles

```

### Cycle Parameter Access (Safe Pattern)
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "processor", {"code": "result = kwargs"})

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
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "processor", {"code": """
import pandas as pd
import numpy as np
result = {
    "data": df.to_dict('records'),        # JSON serializable
    "summary": df.describe().to_dict(),   # Convert all pandas objects
    "shape": df.shape                     # Tuples are fine
}
"""})

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
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# ✅ CORRECT: Use MergeNode for multiple inputs
workflow = WorkflowBuilder()
workflow.add_node("MergeNode", "merger", {}))
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# ❌ WRONG: Direct multi-input without merge
# Multiple connections to same node without MergeNode fails

```

## 🤖 AI/LLM Integration

### LLMAgentNode with MCP (Modern Pattern)
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# ✅ CORRECT: Built-in MCP capabilities
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

# ❌ WRONG: Separate MCPClient node (deprecated pattern)
workflow = WorkflowBuilder()
workflow.add_node("MCPClientNode", "mcp_client", {}))  # Overly complex

```

### Iterative Agent Pattern
```python
# ✅ MODERN: Use IterativeLLMAgentNode for complex analysis
workflow.add_node("IterativeLLMAgentNode", "strategy_agent", {}))

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
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# ✅ PREVENT: "Required parameter 'data' not provided"
workflow = WorkflowBuilder()
workflow.add_node("SomeNode", "node", {}))  # Use defaults
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
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# ✅ PREVENT: "ValueError: Required parameter 'input_data' not provided"
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
# NOT # mapping removed, 'float128'):
    use_extended_precision = True
else:
    use_extended_precision = False

```

## 🎯 Quick Workflow Creation

### 30-Second ETL Pipeline
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {}))
workflow.add_node("PythonCodeNode", "processor", {}) > 100]"
))
workflow.add_node("CSVWriterNode", "writer", {}))

# Connect
workflow.add_connection("reader", "processor", "data", "data")
workflow.add_connection("processor", "writer", "result", "data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "reader": {"file_path": "input.csv"},
    "writer": {"file_path": "output.csv"}
})

```

### 30-Second API Integration
```python
workflow = WorkflowBuilder()
workflow.add_node("RestClientNode", "api_call", {}))
workflow.add_node("PythonCodeNode", "transformer", {}))}"
))

workflow.add_connection("api_call", "transformer", "response", "response")

runtime.execute(workflow.build(), parameters={
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
