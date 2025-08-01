# Common Mistakes & How to Fix Them

*Real examples of errors and their solutions*

## 📦 **Required Imports**

All examples in this guide assume these imports:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode, CSVWriterNode, JSONReaderNode, JSONWriterNode
from kailash.nodes.ai import LLMAgentNode, IterativeLLMAgentNode, EmbeddingGeneratorNode
from kailash.nodes.api import HTTPRequestNode, RESTClientNode
from kailash.nodes.logic import SwitchNode, MergeNode, WorkflowNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.transform import DataTransformerNode
from kailash.nodes.transaction import DistributedTransactionManagerNode, SagaCoordinatorNode, TwoPhaseCommitCoordinatorNode
from kailash.nodes.base import Node, NodeParameter
```

## 🚨 **Most Common Mistakes**

### **Mistake #-1: Missing Required Parameters (NEW in v0.7.0+)**

```python
# ❌ WRONG - Missing required parameters
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice"
    # Missing required 'email' parameter!
})
# Error: Node 'create' missing required inputs: ['email']

# ✅ CORRECT - Use one of three methods:

# Method 1: Node config
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "email": "alice@example.com"
})

# Method 2: Connection from another node
workflow.add_connection("form_data", "email", "create", "email")

# Method 3: Runtime parameters
runtime.execute(workflow.build(), parameters={
    "create": {"email": "alice@example.com"}
})
```

**See**: [Parameter Passing Guide](../../3-development/parameter-passing-guide.md)

### **Mistake #0: Insecure Secret Management (SECURITY CRITICAL)**

```python
# ❌ WRONG - Hardcoded secrets in workflow parameters
workflow.add_node("HTTPRequestNode", "api", {
    "url": "https://api.example.com",
    "headers": {"Authorization": "Bearer sk-abc123"}  # SECURITY RISK!
})

# ❌ WRONG - Environment variables for secrets
import os
api_key = os.getenv("API_KEY")
workflow.add_node("HTTPRequestNode", "api", {
    "headers": {"Authorization": f"Bearer {api_key}"}
})

# ❌ WRONG - Template substitution for secrets
workflow.add_node("HTTPRequestNode", "api", {
    "headers": {"Authorization": "Bearer ${API_TOKEN}"}
})

# ✅ CORRECT - Use environment variables with runtime parameters
from kailash.runtime.local import LocalRuntime
import os

# Keep secrets out of workflow definition
workflow.add_node("HTTPRequestNode", "api", {
    "url": "https://api.example.com"
    # No secret in node config!
})

# Provide secrets at runtime only
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build(), parameters={
    "api": {"headers": {"Authorization": f"Bearer {os.getenv('API_TOKEN')}"}}
})
```

**Environment Setup for Secrets:**
```bash
# ✅ CORRECT - Use environment variables
export API_TOKEN="sk-abc123"
export JWT_SIGNING_KEY="secret-key"
```

**Why this matters:**
- Hardcoded secrets are visible in logs and stored in workflow definitions
- Runtime parameter injection keeps secrets out of workflow definitions
- Environment variables are only accessed at runtime execution
- Enables secret rotation without code changes

### **Mistake #1: Cycle Parameter Passing Errors**

```python
# ❌ WRONG - Direct field mapping for PythonCodeNode
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "counter", {"code": "count = x + 1; result = {'count': count}"})
# Use CycleBuilder API: workflow.create_cycle("name").connect(...).build()

# ✅ CORRECT - Use dot notation for PythonCodeNode outputs
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "counter", {"code": "count = x + 1; result = {'count': count}"})
cycle_builder = workflow.create_cycle("counter_cycle")
cycle_builder.connect("counter", "counter", mapping={"count": "x"}).max_iterations(10).build()
```

```python
# ❌ WRONG - No initial parameters for cycle
runtime.execute(workflow.build())  # ERROR: Required parameter 'x' not provided

# ✅ CORRECT - Provide initial parameters
runtime.execute(workflow.build(), parameters={"counter": {"x": 0}})
```

```python
# ❌ WRONG - Dot notation in convergence check
.converge_when("result.done == True")

# ✅ CORRECT - Flattened field names in convergence
.converge_when("done == True")
```

### **Mistake #2: Wrong Execution Pattern**
```python

# ❌ WRONG - These will cause errors
workflow = WorkflowBuilder()
# These patterns will cause errors:
# workflow.runtime.execute(workflow.build(), runtime)  # workflow has no runtime attribute
# workflow.execute(runtime)  # ❌ workflow has no execute method

# ✅ CORRECT - Runtime execution pattern
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "test", {"code": "result = {'value': 42}"})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

```

### **Mistake #3: Wrong Parameter Name for Overrides**
```python

# ❌ WRONG - These parameter names don't exist
runtime = LocalRuntime()
runtime.execute(workflow.build(), config={"reader": {"file_path": "data.csv"}})
runtime.execute(workflow.build(), overrides={"reader": {"file_path": "data.csv"}})
runtime.execute(workflow.build(), inputs={"reader": {"file_path": "data.csv"}})

# ✅ CORRECT - Use 'parameters'
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build(), parameters={
    "reader": {"file_path": "data.csv"}
})

```

### **Mistake #4: Missing "Node" Suffix**
```python
# ❌ WRONG - These classes don't exist
from kailash.nodes.data import CSVReader, JSONWriter
from kailash.nodes.api import HTTPRequest, RESTClient

# ✅ CORRECT - All classes end with "Node"
from kailash.nodes.data import CSVReaderNode, JSONWriterNode
from kailash.nodes.api import HTTPRequestNode, RESTClientNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode

```

### **Mistake #5: CamelCase Method Names**
```python

# ❌ WRONG - camelCase methods don't exist
workflow = WorkflowBuilder()
workflow.addNode("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.connectNodes("reader", "processor")

# ✅ CORRECT - Use snake_case
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("PythonCodeNode", "processor", {"code": "result = input_data"})
workflow.add_connection("reader", "data", "processor", "input_data")

```

### **Mistake #6: Wrong Parameter Order**
```python

# ❌ WRONG - Parameter order matters
workflow = WorkflowBuilder()
workflow.add_node("reader", "CSVReaderNode", {"file_path": "data.csv"})  # Wrong order
workflow.add_connection("reader", "processor", "data", "input")  # Wrong order

# ✅ CORRECT - node_type, node_id, config
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("PythonCodeNode", "processor", {"code": "result = input_data"})
workflow.add_connection("reader", "data", "processor", "input_data")

```

### **Mistake #7: WorkflowBuilder API Confusion**

```python
# ❌ WRONG - Inconsistent API usage
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node(node_type="PythonCodeNode", node_id="processor", config={"code": "..."})  # Keyword args
auto_id = workflow.add_node("JSONWriterNode")  # No node_id
workflow.add_node(SomeNode(), "instance_node")  # Instance instead of string

# ✅ CORRECT - Consistent string-based API
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("PythonCodeNode", "processor", {"code": "result = input_data"})
workflow.add_node("JSONWriterNode", "writer", {"file_path": "output.json"})
```

```python
# ❌ WRONG - Missing node IDs makes connections impossible
workflow.add_node("CSVReaderNode")  # How to reference this node?
workflow.add_node("PythonCodeNode")  # Can't connect without IDs!

# ✅ CORRECT - Always provide explicit node IDs
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("PythonCodeNode", "processor", {"code": "result = input_data"})
workflow.add_connection("reader", "data", "processor", "input_data")
```

**See:** [WorkflowBuilder API Patterns Guide](../developer/55-workflow-builder-api-patterns.md) for comprehensive API usage

## 🔧 **Real Error Examples & Fixes**

### **Example 1: CSV Reading Gone Wrong**

#### ❌ **Broken Code**
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.data import CSVReader  # WRONG: Missing "Node"

workflow = WorkflowBuilder()
workflow.addNode("reader", CSVReader(),   # WRONG: camelCase method
    filePath="data.csv")                  # WRONG: camelCase config key

runtime = LocalRuntime()
results = runtime.execute(workflow.build(), runtime)      # WRONG: backwards execution

```

#### ✅ **Fixed Code**
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {  # CORRECT: snake_case, string-based
    "file_path": "data.csv"                     # CORRECT: snake_case key
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())  # CORRECT: runtime executes workflow

```

### **Example 2: LLM Integration Mistakes**

#### ❌ **Broken Code**
```python
from kailash.nodes.ai import LLMAgent     # WRONG: Missing "Node"

workflow.add_node("llm", LLMAgent(),      # WRONG: Class doesn't exist
    Provider="openai",                    # WRONG: Capital P
    Model="gpt-4",                       # WRONG: Capital M
    Temperature=0.7)                     # WRONG: Capital T

runtime.execute(workflow, parameters={       # WRONG: 'inputs' parameter
    "llm": {"prompt": "Hello"}
})

```

#### ✅ **Fixed Code**
```python
from kailash.nodes.ai import LLMAgentNode  # CORRECT: With "Node"

workflow.add_node("LLMAgentNode", "llm", {     # CORRECT: Proper class name
    "provider": "openai",                     # CORRECT: lowercase
    "model": "gpt-4",                        # CORRECT: lowercase
    "temperature": 0.7                       # CORRECT: lowercase
})

runtime.execute(workflow, parameters={    # CORRECT: 'parameters'
    "llm": {"prompt": "Hello"}
})

```

### **Example 3: Connection Mapping Errors**

#### ❌ **Broken Code**
```python

# Wrong mapping parameter order
workflow = WorkflowBuilder()
workflow.add_connection("reader", "processor", "data", "input")  # WRONG: wrong order

# Missing output/input specification
workflow = WorkflowBuilder()
workflow.add_connection("reader", "processor")  # WRONG: missing output/input ports

# Incorrect connection patterns
workflow = WorkflowBuilder()
workflow.add_connection("reader", "reader", "data", "input")  # WRONG: self-connection

```

#### ✅ **Fixed Code**
```python

# Correct parameter order with explicit mapping
workflow = WorkflowBuilder()
workflow.add_connection("reader", "data", "processor", "input")

# Correct 4-parameter connection pattern
workflow = WorkflowBuilder()
workflow.add_connection("reader", "data", "processor", "input_data")

# Proper cyclic connection (different output/input names)
workflow = WorkflowBuilder()
cycle_builder = workflow.create_cycle("data_cycle")
cycle_builder.connect("processor", "reader", mapping={"result": "input"}).build()

```

## 🐛 **Debugging Checklist**

When your code fails, check these in order:

### **1. Import Errors**
```python
# ✅ Check imports are correct
from kailash.workflow.builder import WorkflowBuilder                           # Core
from kailash.runtime.local import LocalRuntime        # Runtime
from kailash.nodes.data import CSVReaderNode          # Data nodes
from kailash.nodes.ai import LLMAgentNode             # AI nodes
from kailash.nodes.api import HTTPRequestNode         # API nodes

```

### **2. Method Name Errors**
```python

# ✅ Verify you're using correct method names
workflow = WorkflowBuilder()
workflow.add_node("NodeType", "id", {})    # NOT addNode()
workflow.add_connection("source", "result", "target", "input")  # NOT connectNodes()
workflow.validate()    # NOT check()
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())     # NOT workflow.run()

```

### **3. Class Name Errors**
```python
# ✅ All node classes end with "Node"
CSVReaderNode     # NOT CSVReader
LLMAgentNode      # NOT LLMAgent
HTTPRequestNode   # NOT HTTPRequest
PythonCodeNode    # NOT PythonCode

```

### **4. Parameter Errors**
```python
# ✅ Check parameter names and order
workflow.add_node("NodeType", "id", config)        # Correct order
runtime.execute(workflow.build(), parameters={...})           # Use 'parameters'
workflow.add_connection("from", "output", "to", "input")         # 4-parameter format

```

### **5. Configuration Key Errors**
```python
# ✅ Use exact configuration keys (case-sensitive)
file_path="..."     # NOT filePath
has_header=True     # NOT hasHeader
max_tokens=100      # NOT maxTokens
temperature=0.7     # NOT Temperature

```

## 🔍 **Error Message Decoder**

### **"AttributeError: 'Workflow' object has no attribute 'addNode'"**
- **Problem**: Using camelCase method name
- **Fix**: Use `workflow.add_node()` instead of `workflow.addNode()`

### **"ModuleNotFoundError: No module named 'kailash.nodes.data.CSVReader'"**
- **Problem**: Missing "Node" suffix in class name
- **Fix**: Use `CSVReaderNode` instead of `CSVReader`

### **"TypeError: execute() takes 1 positional argument but 2 were given"**
- **Problem**: Using backwards execution pattern
- **Fix**: Use `runtime.execute(workflow.build())` not `runtime.execute(workflow.build(), runtime)`

### **"TypeError: execute() got an unexpected keyword argument 'inputs'"**
- **Problem**: Wrong parameter name for runtime overrides
- **Fix**: Use `parameters={}` instead of `parameters={}`

### **"TypeError: add_node() missing 1 required positional argument"**
- **Problem**: Wrong parameter order
- **Fix**: node_id first, then node class: `add_node("id", NodeClass())`

## ✅ **Validation Function for Your Code**

```python
def debug_workflow_code(workflow_code):
    """Debug common issues in workflow code"""
    issues = []

    # Check for camelCase methods
    if "addNode" in workflow_code:
        issues.append("❌ Use 'add_node()' not 'addNode()'")
    if "connectNodes" in workflow_code:
        issues.append("❌ Use 'connect()' not 'connectNodes()'")

    # Check for missing "Node" suffix
    if "CSVReader(" in workflow_code and "CSVReaderNode(" not in workflow_code:
        issues.append("❌ Use 'CSVReaderNode' not 'CSVReader'")
    if "LLMAgent(" in workflow_code and "LLMAgentNode(" not in workflow_code:
        issues.append("❌ Use 'LLMAgentNode' not 'LLMAgent'")

    # Check for wrong execution pattern
    if "runtime.execute(workflow.build(), runtime)" in workflow_code:
        issues.append("❌ Use 'runtime.execute(workflow.build())' not 'runtime.execute(workflow.build(), runtime)'")

    # Check for wrong parameter names
    if "parameters=" in workflow_code:
        issues.append("❌ Use 'parameters=' not 'parameters='")

    # Check for camelCase config keys
    if "filePath" in workflow_code:
        issues.append("❌ Use 'file_path' not 'filePath'")
    if "hasHeader" in workflow_code:
        issues.append("❌ Use 'has_header' not 'hasHeader'")

    if issues:
        print("🐛 Issues found:")
        for issue in issues:
            print(f"  {issue}")
        return False
    else:
        print("✅ No common issues detected!")
        return True

# Usage
your_code = '''
workflow.add_node("CSVReaderNode", "reader", {}), file_path="data.csv")
runtime.execute(workflow, parameters={"reader": {"delimiter": ","}})
'''

debug_workflow_code(your_code)

```

## 📚 **Quick Fix Templates**

### **Template 1: Basic CSV Processing**
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.code import PythonCodeNode

workflow = WorkflowBuilder()

workflow.add_node("CSVReaderNode", "reader", {
    "file_path": "input.csv",
    "has_header": True,
    "delimiter": ","
})

workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'processed': data}"
}))

workflow.add_node("CSVWriterNode", "writer", {
    "file_path": "output.csv",
    "include_header": True
})

workflow.add_connection("reader", "data", "processor", "data")
workflow.add_connection("processor", "result", "writer", "data")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

```

### **Template 2: API + LLM Processing**
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.code import PythonCodeNode

workflow = WorkflowBuilder()

workflow.add_node("HTTPRequestNode", "api", {
    "url": "https://api.example.com/data",
    "method": "GET"
})

workflow.add_node("LLMAgentNode", "llm", {
    "provider": "openai",
    "model": "gpt-4",
    "temperature": 0.7
})

workflow.add_connection("api", "response", "llm", "prompt")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

```

### **Mistake #15: Distributed Transaction Pattern Selection**

```python
# ❌ WRONG - Hard-coding pattern choice when capabilities are mixed
workflow = WorkflowBuilder()
workflow.add_node("TwoPhaseCommitCoordinatorNode", "coordinator", {})  # Will fail if participants don't support 2PC
# or
workflow.add_node("SagaCoordinatorNode", "coordinator", {})  # Sub-optimal for services that support 2PC

# ✅ CORRECT - Use DTM for automatic pattern selection
workflow.add_node("DistributedTransactionManagerNode", "manager", {
    "transaction_name": "mixed_services",
    "state_storage": "redis",
    "storage_config": {"redis_client": "redis_connection"}
})

# DTM will automatically select the best pattern
runtime = LocalRuntime()
results, run_id = await runtime.execute_async(workflow.build(), parameters={
    "manager": {
        "operation": "create_transaction",
        "requirements": {"consistency": "strong", "availability": "high"}
    }
})
```

### **Mistake #16: Saga Compensation Logic**

```python
# ❌ WRONG - Not providing compensation for saga steps
workflow = WorkflowBuilder()
workflow.add_node("SagaCoordinatorNode", "coordinator", {"saga_name": "order_processing"})
# Missing compensation configuration in node setup

# ✅ CORRECT - Always provide compensation for saga steps
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build(), parameters={
    "coordinator": {
        "operation": "add_step",
        "name": "payment",
        "node_id": "PaymentNode",
        "compensation_node_id": "RefundNode",
        "compensation_parameters": {"action": "refund_payment"}
    }
})
```

### **Mistake #17: Async/Sync Method Confusion**

```python
# ❌ WRONG - Using sync execute on async transaction nodes
workflow = WorkflowBuilder()
workflow.add_node("TwoPhaseCommitCoordinatorNode", "coordinator", {})
runtime = LocalRuntime()
result = runtime.execute(workflow.build())  # Will fail with async node

# ✅ CORRECT - Use async runtime for async transaction nodes
result, run_id = await runtime.execute_async(workflow.build(), parameters={
    "coordinator": {"operation": "execute_transaction"}
})
```

### **Mistake #18: Missing Transaction Recovery**

```python
# ❌ WRONG - Not implementing recovery for failed transactions
workflow = WorkflowBuilder()
workflow.add_node("SagaCoordinatorNode", "coordinator", {})
runtime = LocalRuntime()
try:
    await runtime.execute_async(workflow.build(), parameters={"coordinator": {"operation": "execute_saga"}})
except Exception:
    pass  # Transaction state is lost!

# ✅ CORRECT - Always implement recovery patterns
try:
    result, run_id = await runtime.execute_async(workflow.build(), parameters={
        "coordinator": {"operation": "execute_saga"}
    })
except Exception as e:
    # Attempt to recover the transaction
    recovery_result, _ = await runtime.execute_async(workflow.build(), parameters={
        "coordinator": {"operation": "load_saga", "saga_id": "saga_id_value"}
    })
    if recovery_result["status"] == "success":
        await runtime.execute_async(workflow.build(), parameters={
            "coordinator": {"operation": "resume"}
        })
```

### **Mistake #19: Using Deprecated MCP Parameters**

```python
# ❌ WRONG - Using deprecated use_real_mcp parameter (removed in v0.9.9)
workflow = WorkflowBuilder()
workflow.add_node("IterativeLLMAgentNode", "agent", {
    "provider": "openai",
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Search for data"}],
    "mcp_servers": [{"name": "data-server", "transport": "stdio", "command": "mcp-server"}],
    "use_real_mcp": True  # This parameter no longer exists!
})

# ✅ CORRECT - Simplified API always uses real MCP execution
workflow.add_node("IterativeLLMAgentNode", "agent", {
    "provider": "openai",
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Search for data"}],
    "mcp_servers": [{"name": "data-server", "transport": "stdio", "command": "mcp-server"}]
    # Real MCP execution is always enabled with graceful fallback
})
runtime = LocalRuntime()
result, run_id = runtime.execute(workflow.build())
```

```python
# ❌ WRONG - No MCP servers but expecting tool execution
workflow.add_node("IterativeLLMAgentNode", "agent", {
    "provider": "openai",
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Search for data"}]
    # Missing mcp_servers!
})

# ✅ CORRECT - Always provide MCP servers for tool execution
workflow.add_node("IterativeLLMAgentNode", "agent", {
    "provider": "openai",
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Search for data"}],
    "mcp_servers": [{
        "name": "data-server",
        "transport": "stdio",
        "command": "python",
        "args": ["-m", "data_mcp_server"]
    }],
    "auto_discover_tools": True,
    "auto_execute_tools": True
})
result, run_id = runtime.execute(workflow.build())
```

## 🔗 **Next Steps**

- **[API Reference](api-reference.md)** - Complete method signatures
- **[Critical Rules](critical-rules.md)** - Review the 5 essential rules
- **[Advanced Patterns](advanced-patterns.md)** - Complex usage scenarios

---

**Remember: Most errors come from these 5 common mistakes. Check them first!**
