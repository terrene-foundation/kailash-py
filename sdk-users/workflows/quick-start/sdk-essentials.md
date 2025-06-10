# Kailash SDK Essentials

**Critical patterns covering 80% of common issues** - Consolidated from 74 mistakes and key API patterns.

## 🚨 The Golden Rules (MEMORIZE)

### 1. Config vs Runtime (Mistake #001 - THE #1 ISSUE)
```python
# ✅ CORRECT: Config = HOW (static setup), Runtime = WHAT (dynamic data)
workflow.add_node("processor", PythonCodeNode(
    name="processor",           # Config: HOW the node works
    code="result = data * 2"    # Config: WHAT code to run
))

# Execution: Runtime = WHAT data to process
runtime.execute(workflow, parameters={
    "processor": {"data": [1, 2, 3]}  # Runtime: WHAT actual data
})

# ❌ WRONG: Mixing config and runtime
workflow.add_node("bad_node", PythonCodeNode(
    name="bad_node",
    data=[1, 2, 3]  # WRONG: Runtime data in config
))
```

### 2. Node Naming Convention
```python
# ✅ CORRECT: ALL node classes end with "Node"
CSVReaderNode, PythonCodeNode, SwitchNode

# ❌ WRONG: Missing "Node" suffix
CSVReader, PythonCode, Switch
```

### 3. Workflow Connection Pattern
```python
# ✅ CORRECT: Use Workflow.connect() with mapping
workflow = Workflow("my_workflow")
workflow.connect("source", "target", mapping={"output_field": "input_field"})

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
# Create cycle with specific field mapping (NOT generic)
workflow.connect("node_a", "node_b", mapping={"result.count": "count"})
workflow.connect("node_b", "node_c", mapping={"output.value": "input_value"})
workflow.connect("node_c", "node_a", cycle=True, mapping={"final.result": "initial_data"})

# ✅ CRITICAL: Use specific field mapping in cycles
# ❌ NEVER: {"output": "output"} - generic mapping fails in cycles
```

### Cycle Parameter Access (Safe Pattern)
```python
workflow.add_node("cycle_node", PythonCodeNode(
    name="cycle_node",
    code='''
# ✅ CORRECT: Safe parameter access with try/except
try:
    count = count  # Direct variable access
except:
    count = 0      # Default for first iteration

try:
    prev_result = prev_result
except:
    prev_result = []

# Process with defaults
result = {"count": count + 1, "data": prev_result + [count]}
'''
))
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
workflow.add_node("data_processor", PythonCodeNode(
    name="data_processor",
    code='''
import pandas as pd
import numpy as np

# ✅ CRITICAL: DataFrame serialization
df = pd.DataFrame(data)
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
# ✅ CORRECT: Use MergeNode for multiple inputs
workflow.add_node("merger", MergeNode())
workflow.connect("source1", "merger", mapping={"data": "input1"})
workflow.connect("source2", "merger", mapping={"data": "input2"})
workflow.connect("merger", "processor", mapping={"merged": "combined_data"})

# ❌ WRONG: Direct multi-input without merge
# Multiple connections to same node without MergeNode fails
```

## 🤖 AI/LLM Integration

### LLMAgentNode with MCP (Modern Pattern)
```python
# ✅ CORRECT: Built-in MCP capabilities
workflow.add_node("ai_agent", LLMAgentNode(
    provider="ollama",
    model="llama3.2",
    mcp_servers=[{
        "name": "ai-registry",
        "transport": "stdio",
        "command": "python",
        "args": ["scripts/start-ai-registry-server.py"]
    }],
    auto_discover_tools=True
))

# ❌ WRONG: Separate MCPClient node (deprecated pattern)
workflow.add_node("mcp_client", MCPClientNode())  # Overly complex
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
# ✅ PREVENT: "Required parameter 'data' not provided"
workflow.add_node("node", SomeNode(required=False))  # Use defaults
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
# ✅ PREVENT: "ValueError: Required parameter 'input_data' not provided"
workflow.connect("switch", "target", mapping={"output": "input_data"})
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
workflow = Workflow("quick_etl")
workflow.add_node("reader", CSVReaderNode())
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
workflow = Workflow("api_integration")
workflow.add_node("api_call", RestClientNode())
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
