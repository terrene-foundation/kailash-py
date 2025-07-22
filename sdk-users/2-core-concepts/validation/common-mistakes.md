# Common Mistakes & How to Fix Them

*Real examples of errors and their solutions*

## 📦 **Required Imports**

All examples in this guide assume these imports:

```python
from kailash import Workflow
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

### **✅ FIXED: Mistake #0: Connection Parameter Security - NOW SECURE BY DEFAULT**

**🔒 AUTOMATIC (v0.8.6+): Connection validation is now STRICT by default with performance optimization**

```python
# ✅ SECURE BY DEFAULT (no configuration needed)
runtime = LocalRuntime()  # Automatically prevents SQL injection, type confusion, parameter attacks
workflow.add_connection("source", "data", "database", "query")  # Validated automatically
# Fast performance with built-in caching

# ✅ RECOMMENDED: Add parameter validation in your nodes
class SecureDatabaseNode(Node):
    def get_parameters(self):
        return {
            "query": NodeParameter(type=str, required=True),  # SDK validates automatically
            "max_rows": NodeParameter(type=int, required=True)
        }

# ⚠️ LEGACY MIGRATION (only if needed for old workflows)
runtime = LocalRuntime(connection_validation="warn")  # Temporarily disable for migration
# Then remove this override - strict mode is safer and just as fast
```

**Benefits of secure-by-default:**
- **No Configuration**: Security works automatically
- **Fast Performance**: Built-in caching makes strict validation faster than warn mode
- **Enterprise Ready**: Meets security compliance requirements out-of-the-box
- **Unauthorized Parameter Blocking**: Rejects undeclared parameters automatically
- **No Performance Impact**: Caching makes validation faster than previous versions

### **Mistake #1: Missing Required Parameters (NEW in v0.7.0+)**

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
workflow.add_node("api", HTTPRequestNode(), {
    "url": "https://api.example.com",
    "headers": {"Authorization": "Bearer sk-abc123"}  # SECURITY RISK!
})

# ❌ WRONG - Environment variables for secrets
import os
api_key = os.getenv("API_KEY")
workflow.add_node("api", HTTPRequestNode(), {
    "headers": {"Authorization": f"Bearer {api_key}"}
})

# ❌ WRONG - Template substitution for secrets
workflow.add_node("api", HTTPRequestNode(), {
    "headers": {"Authorization": "Bearer ${API_TOKEN}"}
})

# ✅ CORRECT - Runtime secret management (v0.8.1+)
from kailash.runtime.secret_provider import EnvironmentSecretProvider
from kailash.runtime.local import LocalRuntime

secret_provider = EnvironmentSecretProvider()
runtime = LocalRuntime(secret_provider=secret_provider)

# Node declares secret requirements
class APINode(Node):
    @classmethod
    def get_secret_requirements(cls):
        return [SecretRequirement("api-token", "auth_token")]

# Secrets injected at runtime, not stored in workflow
workflow.add_node("api", APINode(), {
    "url": "https://api.example.com"
    # No secret in parameters - injected automatically!
})
```

**Environment Setup for Secrets:**
```bash
# ✅ CORRECT - Use KAILASH_SECRET_ prefix
export KAILASH_SECRET_API_TOKEN="sk-abc123"
export KAILASH_SECRET_JWT_SIGNING_KEY="secret-key"

# ❌ WRONG - Direct environment variables
export API_TOKEN="sk-abc123"  # Avoid this pattern
```

**Why this matters:**
- Hardcoded secrets are visible in logs and stored in workflow definitions
- Environment variables expose secrets in process lists and crash dumps
- Runtime secret management fetches secrets only when needed
- Supports enterprise providers (Vault, AWS Secrets Manager)
- Enables secret rotation without code changes

### **Mistake #1: Cycle Parameter Passing Errors**

```python
# ❌ WRONG - Direct field mapping for PythonCodeNode
counter = PythonCodeNode.from_function(lambda x=0: {"count": x+1}, name="counter")
workflow.connect("counter", "counter", {"count": "x"}, cycle=True)

# ✅ CORRECT - Use dot notation for PythonCodeNode outputs
workflow.connect("counter", "counter", {"result.count": "x"}, cycle=True)
```

```python
# ❌ WRONG - No initial parameters for cycle
runtime.execute(workflow)  # ERROR: Required parameter 'x' not provided

# ✅ CORRECT - Provide initial parameters
runtime.execute(workflow, parameters={"counter": {"x": 0}})
```

```python
# ❌ WRONG - Dot notation in convergence check
.converge_when("result.done == True")

# ✅ CORRECT - Flattened field names in convergence
.converge_when("done == True")
```

### **Mistake #2: Wrong Execution Pattern**
```python

# ❌ WRONG - This will cause an error
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.workflow.execute(runtime)

# ✅ CORRECT - Two valid patterns
# Pattern 1: Direct execution (basic features)
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.execute()

# Pattern 2: Runtime execution (recommended)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

```

### **Mistake #2: Wrong Parameter Name for Overrides**
```python

# ❌ WRONG - These parameter names don't exist
runtime = LocalRuntime()
workflow.execute(workflow, inputs={"reader": {"file_path": "data.csv"}})
runtime = LocalRuntime()
workflow.execute(workflow, config={"reader": {"file_path": "data.csv"}})
runtime = LocalRuntime()
workflow.execute(workflow, overrides={"reader": {"file_path": "data.csv"}})

# ✅ CORRECT - Use 'parameters'
runtime = LocalRuntime()
# Parameters setup
workflow.{"reader": {"file_path": "data.csv"}})

```

### **Mistake #3: Missing "Node" Suffix**
```python
# ❌ WRONG - These classes don't exist
from kailash.nodes.data import CSVReader, JSONWriter
from kailash.nodes.api import HTTPRequest, RESTClient

# ✅ CORRECT - All classes end with "Node"
from kailash.nodes.data import CSVReaderNode, JSONWriterNode
from kailash.nodes.api import HTTPRequestNode, RESTClientNode

```

### **Mistake #4: CamelCase Method Names**
```python

# ❌ WRONG - camelCase methods don't exist
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.workflow.addNode("reader", CSVReaderNode())
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connectNodes("reader", "processor")

# ✅ CORRECT - Use snake_case
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.add_node("reader", CSVReaderNode())
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connect("reader", "processor")

```

### **Mistake #5: Wrong Parameter Order**
```python

# ❌ WRONG - Parameter order matters
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.add_node(CSVReaderNode(), "reader", file_path="data.csv")
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connect("reader", "processor", mapping={"data": "input"})

# ✅ CORRECT - node_id first, then node, then config
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.add_node("reader", CSVReaderNode(), file_path="data.csv")
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connect("reader", "processor", mapping={"data": "input"})

```

### **Mistake #6: WorkflowBuilder API Confusion (v0.6.6+)**

```python
# ❌ WRONG - Inconsistent API usage
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node(node_type="PythonCodeNode", node_id="processor", config={"code": "..."})
auto_id = workflow.add_node("JSONWriterNode")
workflow.add_node(SomeNode, "instance_node")  # Mixed patterns confuse readers

# ✅ CORRECT - Consistent style throughout workflow
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("PythonCodeNode", "processor", {"code": "..."})
workflow.add_node("JSONWriterNode", "writer", {"file_path": "output.json"})
```

```python
# ❌ WRONG - Ignoring auto-generated IDs
workflow.add_node("CSVReaderNode")  # ID not captured
workflow.add_node("PythonCodeNode")  # Can't connect nodes!

# ✅ CORRECT - Capture auto-generated IDs for connections
reader_id = workflow.add_node("CSVReaderNode", {"file_path": "data.csv"})
processor_id = workflow.add_node("PythonCodeNode", {"code": "..."})
workflow.connect(reader_id, "result", mapping={processor_id: "input_data"})
```

**See:** [WorkflowBuilder API Patterns Guide](../developer/55-workflow-builder-api-patterns.md) for comprehensive API usage

## 🔧 **Real Error Examples & Fixes**

### **Example 1: CSV Reading Gone Wrong**

#### ❌ **Broken Code**
```python
from kailash import Workflow
from kailash.nodes.data import CSVReader  # WRONG: Missing "Node"

workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.workflow.addNode("reader", CSVReader(),   # WRONG: camelCase method
    filePath="data.csv")                  # WRONG: camelCase config key

runtime = LocalRuntime()
results = workflow.execute(runtime)      # WRONG: backwards execution

```

#### ✅ **Fixed Code**
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode  # CORRECT: With "Node"

workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.add_node("reader", CSVReaderNode(),  # CORRECT: snake_case
    file_path="data.csv")                     # CORRECT: snake_case key

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)  # CORRECT: runtime executes workflow

```

### **Example 2: LLM Integration Mistakes**

#### ❌ **Broken Code**
```python
from kailash.nodes.ai import LLMAgent     # WRONG: Missing "Node"

workflow.add_node("llm", LLMAgent(),      # WRONG: Class doesn't exist
    Provider="openai",                    # WRONG: Capital P
    Model="gpt-4",                       # WRONG: Capital M
    Temperature=0.7)                     # WRONG: Capital T

runtime.execute(workflow, inputs={       # WRONG: 'inputs' parameter
    "llm": {"prompt": "Hello"}
})

```

#### ✅ **Fixed Code**
```python
from kailash.nodes.ai import LLMAgentNode  # CORRECT: With "Node"

workflow.add_node("llm", LLMAgentNode(),   # CORRECT: Proper class name
    provider="openai",                     # CORRECT: lowercase
    model="gpt-4",                        # CORRECT: lowercase
    temperature=0.7)                      # CORRECT: lowercase

runtime.execute(workflow, parameters={    # CORRECT: 'parameters'
    "llm": {"prompt": "Hello"}
})

```

### **Example 3: Connection Mapping Errors**

#### ❌ **Broken Code**
```python

# Wrong mapping parameter order
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connect("reader", "processor", mapping={"data": "input"})

# Missing mapping parameter name
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connect("reader", "processor", mapping={"data": "input"})

# Self-referencing mapping in PythonCodeNode
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connect("reader", "processor", mapping={"data": "input"})

```

#### ✅ **Fixed Code**
```python

# Correct parameter order with explicit mapping
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connect("reader", "processor", mapping={"data": "input"})

# Automatic mapping when names match
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connect("reader", "processor")  # maps "data" → "data"

# Proper cyclic connection (different output/input names)
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connect("reader", "processor", mapping={"data": "input"})

```

## 🐛 **Debugging Checklist**

When your code fails, check these in order:

### **1. Import Errors**
```python
# ✅ Check imports are correct
from kailash import Workflow                           # Core
from kailash.runtime.local import LocalRuntime        # Runtime
from kailash.nodes.data import CSVReaderNode          # Data nodes
from kailash.nodes.ai import LLMAgentNode             # AI nodes
from kailash.nodes.api import HTTPRequestNode         # API nodes

```

### **2. Method Name Errors**
```python

# ✅ Verify you're using correct method names
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.add_node()    # NOT addNode()
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.connect()     # NOT connectNodes()
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.workflow.validate()    # NOT check()
workflow = Workflow("mistakes_demo", name="Common Mistakes Demo")
workflow.workflow.execute()     # NOT run()

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
workflow.add_node("id", NodeClass(), **config)        # Correct order
runtime.execute(workflow, parameters={...})           # Use 'parameters'
workflow.connect("from", "to", mapping={...})         # Use 'mapping'

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
- **Fix**: Use `runtime.execute(workflow)` not `workflow.execute(runtime)`

### **"TypeError: execute() got an unexpected keyword argument 'inputs'"**
- **Problem**: Wrong parameter name for runtime overrides
- **Fix**: Use `parameters={}` instead of `inputs={}`

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
    if "workflow.execute(runtime)" in workflow_code:
        issues.append("❌ Use 'runtime.execute(workflow)' not 'workflow.execute(runtime)'")

    # Check for wrong parameter names
    if "inputs=" in workflow_code:
        issues.append("❌ Use 'parameters=' not 'inputs='")

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
workflow.add_node("reader", CSVReaderNode(), file_path="data.csv")
runtime.execute(workflow, parameters={"reader": {"delimiter": ","}})
'''

debug_workflow_code(your_code)

```

## 📚 **Quick Fix Templates**

### **Template 1: Basic CSV Processing**
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.code import PythonCodeNode

workflow = Workflow("csv_processing", name="CSV Processing")

workflow.add_node("reader", CSVReaderNode(),
    file_path="input.csv",
    has_header=True,
    delimiter=","
)

workflow.add_node("processor", PythonCodeNode(
    name="processor",
    code="result = {'processed': [row for row in data]}",
    input_types={"data": list}
))

workflow.add_node("writer", CSVWriterNode(),
    file_path="output.csv",
    include_header=True
)

workflow.connect("reader", "processor", mapping={"data": "data"})
workflow.connect("processor", "writer", mapping={"processed": "data"})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

```

### **Template 2: API + LLM Processing**
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.code import PythonCodeNode

workflow = Workflow("api_llm", name="API + LLM Processing")

workflow.add_node("api", HTTPRequestNode(),
    url="https://api.example.com/data",
    method="GET"
)

workflow.add_node("llm", LLMAgentNode(),
    provider="openai",
    model="gpt-4",
    temperature=0.7
)

workflow.connect("api", "llm", mapping={"response": "prompt"})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

```

### **Mistake #15: Distributed Transaction Pattern Selection**

```python
# ❌ WRONG - Hard-coding pattern choice when capabilities are mixed
coordinator = TwoPhaseCommitCoordinatorNode(...)  # Will fail if participants don't support 2PC
# or
coordinator = SagaCoordinatorNode(...)  # Sub-optimal for services that support 2PC

# ✅ CORRECT - Use DTM for automatic pattern selection
manager = DistributedTransactionManagerNode(
    transaction_name="mixed_services",
    state_storage="redis",
    storage_config={"redis_client": redis_client}
)

# DTM will automatically select the best pattern
await manager.async_run(
    operation="create_transaction",
    requirements={"consistency": "strong", "availability": "high"}
)
```

### **Mistake #16: Saga Compensation Logic**

```python
# ❌ WRONG - Not providing compensation for saga steps
coordinator = SagaCoordinatorNode(saga_name="order_processing")
coordinator.execute(
    operation="add_step",
    name="payment",
    node_id="PaymentNode"
    # Missing compensation_node_id!
)

# ✅ CORRECT - Always provide compensation for saga steps
coordinator.execute(
    operation="add_step",
    name="payment",
    node_id="PaymentNode",
    compensation_node_id="RefundNode",
    compensation_parameters={"action": "refund_payment"}
)
```

### **Mistake #17: Async/Sync Method Confusion**

```python
# ❌ WRONG - Using sync execute on async transaction nodes
coordinator = TwoPhaseCommitCoordinatorNode(...)
result = coordinator.execute(operation="execute_transaction")  # Will fail

# ✅ CORRECT - Use async_run for transaction nodes
result = await coordinator.async_run(operation="execute_transaction")
```

### **Mistake #18: Missing Transaction Recovery**

```python
# ❌ WRONG - Not implementing recovery for failed transactions
coordinator = SagaCoordinatorNode(...)
try:
    await coordinator.async_run(operation="execute_saga")
except Exception:
    pass  # Transaction state is lost!

# ✅ CORRECT - Always implement recovery patterns
try:
    result = await coordinator.async_run(operation="execute_saga")
except Exception as e:
    # Attempt to recover the transaction
    recovery_result = await coordinator.async_run(
        operation="load_saga",
        saga_id=coordinator.saga_id
    )
    if recovery_result["status"] == "success":
        await coordinator.async_run(operation="resume")
```

### **Mistake #19: IterativeLLMAgent Mock Execution**

```python
# ❌ WRONG - Disabling real MCP execution (reverts to mock)
agent = IterativeLLMAgentNode()
result = agent.execute(
    provider="openai",
    model="gpt-4",
    messages=[{"role": "user", "content": "Search for data"}],
    mcp_servers=[{"name": "data-server", "transport": "stdio", "command": "mcp-server"}],
    use_real_mcp=False  # This causes mock execution!
)

# ✅ CORRECT - Use real MCP execution (default behavior)
result = agent.execute(
    provider="openai",
    model="gpt-4",
    messages=[{"role": "user", "content": "Search for data"}],
    mcp_servers=[{"name": "data-server", "transport": "stdio", "command": "mcp-server"}],
    use_real_mcp=True  # Default: True (real tool execution)
)
```

```python
# ❌ WRONG - No MCP servers but expecting tool execution
result = agent.execute(
    provider="openai",
    model="gpt-4",
    messages=[{"role": "user", "content": "Search for data"}]
    # Missing mcp_servers!
)

# ✅ CORRECT - Always provide MCP servers for tool execution
result = agent.execute(
    provider="openai",
    model="gpt-4",
    messages=[{"role": "user", "content": "Search for data"}],
    mcp_servers=[{
        "name": "data-server",
        "transport": "stdio",
        "command": "python",
        "args": ["-m", "data_mcp_server"]
    }],
    auto_discover_tools=True,
    auto_execute_tools=True
)
```

## 🔗 **Next Steps**

- **[API Reference](api-reference.md)** - Complete method signatures
- **[Critical Rules](critical-rules.md)** - Review the 5 essential rules
- **[Advanced Patterns](advanced-patterns.md)** - Complex usage scenarios

---

**Remember: Most errors come from these 5 common mistakes. Check them first!**
