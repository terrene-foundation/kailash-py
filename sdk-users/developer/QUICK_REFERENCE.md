# Developer Guide - Quick Reference

## 🚨 Critical Rules
1. **Node names**: ALL end with "Node" (`CSVReaderNode` ✓, `CSVReader` ✗)
2. **Parameter types**: ONLY `str`, `int`, `float`, `bool`, `list`, `dict`, `Any`
3. **Never use generics**: No `List[T]`, `Dict[K,V]`, `Optional[T]`, `Union[A,B]`
4. **PythonCodeNode**: Input variables EXCLUDED from outputs! + **Dot Notation**
   - `mapping={"result": "input_data"}` ✓ (simple mapping)
   - `mapping={"result.data": "input_data"}` ✓ (nested access)
   - `mapping={"result": "result"}` ✗ (self-reference)
5. **Always include name**: `PythonCodeNode(name="processor", code="...")`
6. **Node Creation**: Can create without required params (validated at execution)
7. **Auto-Mapping**: NodeParameter supports automatic connection discovery:
   - `auto_map_primary=True` → Maps primary input automatically
   - `auto_map_from=["alt1", "alt2"]` → Maps from alternative names
   - `workflow_alias="name"` → Maps from workflow-level parameter
8. **Data Files**: Use centralized `/data/` with `examples/utils/data_paths.py`
9. **Workflow Resilience**: Built into standard Workflow (no separate class needed)
10. **Credentials**: Always use CredentialManagerNode (never hardcode)
11. **SharePoint Auth**: Use SharePointGraphReaderEnhanced for multi-auth

## 📋 Quick Node Selection
| Task | Use | Don't Use |
|------|-----|-----------|
| Read CSV | `CSVReaderNode` | `PythonCodeNode` with manual CSV |
| Find files | `DirectoryReaderNode` | `PythonCodeNode` with `os.listdir` |
| Run Python | `PythonCodeNode(name="x")` | Missing `name` parameter |
| HTTP calls | `HTTPRequestNode` | `HTTPClientNode` (deprecated) |
| Send alerts | `DiscordAlertNode` | Manual webhook requests |
| Transform data | `DataTransformer` | Complex PythonCodeNode |
| Async operations | `LocalRuntime(enable_async=True)` | `AsyncLocalRuntime` (deprecated) |
| Enterprise features | `LocalRuntime` with enterprise params | Custom implementations |

## 🧪 Tests vs Examples
| Purpose | Location | Content | Audience |
|---------|----------|---------|----------|
| **Validate SDK** | `tests/` | Assertions, edge cases, mocks | Contributors, CI/CD |
| **Learn SDK** | `examples/` | Working solutions, tutorials | Users, documentation |

## 📁 Guide Structure
- **[01-fundamentals.md](01-fundamentals.md)** - ⭐ START HERE: Core SDK concepts and patterns
- **[02-workflows.md](02-workflows.md)** - ⭐ Workflow creation, connections, and execution
- **[03-advanced-features.md](03-advanced-features.md)** - Enterprise patterns and async operations
- **[Node Catalog](../nodes/comprehensive-node-catalog.md)** - ⭐ Complete reference of all 110+ nodes
- **[examples/](examples/)** - Working code examples

## ⚡ Quick Fix Templates

### WorkflowBuilder (Current API)
```python
# ✅ CORRECT: String-based node creation
from kailash.workflow.builder import WorkflowBuilder

builder = WorkflowBuilder()

# Create nodes using string types
reader_id = builder.add_node(
    "CSVReaderNode",           # Node type as string
    node_id="csv_reader",      # Optional custom ID
    config={                   # Configuration dictionary
        "name": "csv_reader",
        "file_path": "/data/inputs/customers.csv"
    }
)

processor_id = builder.add_node(
    "PythonCodeNode",
    node_id="data_processor",
    config={
        "name": "data_processor",
        "code": "result = {'processed': len(input_data)}"
    }
)

# Connect using add_connection (4 parameters required)
builder.add_connection(reader_id, "output", processor_id, "input")

```

### Unified Runtime (Enterprise Features)
```python
# ✅ CORRECT: Unified runtime with enterprise capabilities
from kailash.runtime.local import LocalRuntime
from kailash.access_control import UserContext

# Basic usage (backward compatible)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

# With enterprise features
user_context = UserContext(
    user_id="analyst_01",
    tenant_id="acme_corp",
    email="analyst@acme.com",
    roles=["data_analyst", "viewer"]
)

runtime = LocalRuntime(
    enable_monitoring=True,      # Auto performance tracking
    enable_audit=True,          # Auto compliance logging
    enable_security=True,       # Auto access control
    enable_async=True,          # Auto async node detection
    max_concurrency=20,         # Parallel execution limit
    user_context=user_context,  # Multi-tenant isolation
    resource_limits={           # Resource constraints
        "memory_mb": 4096,
        "cpu_cores": 4
    }
)

# Execute with automatic enterprise integration
results, run_id = runtime.execute(workflow, task_manager, parameters)

```

### Middleware Integration
```python
# ✅ CORRECT: Middleware imports and usage
from kailash.middleware import (
    AgentUIMiddleware,
    RealtimeMiddleware,
    APIGateway,
    create_gateway
)

# Create gateway with middleware
gateway = create_gateway(
    title="My Application",
    cors_origins=["http://localhost:3000"],
    enable_docs=True
)

# Access integrated components
agent_ui = gateway.agent_ui

```

### Basic Custom Node
```python
from typing import Any, Dict
from kailash.nodes.base import Node, NodeParameter

class YourNode(Node):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            'param': NodeParameter(
                name='param',
                type=str,  # Use basic type or Any
                required=True,
                description='Description'
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        return {'result': kwargs['param']}

```

### PythonCodeNode (Best Practices)

**⚠️ MOST COMMON MISTAKE: Not using from_function for complex code**
*"This mistake keeps occurring every new run" - Session 064*

**🚀 MANDATORY: Use `.from_function()` for code > 3 lines**
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

# ✅ ALWAYS use from_function for complex logic:
def workflow.()  # Type signature example -> dict:
    """Full IDE support: highlighting, completion, debugging!"""
    files = input_data.get("files", [])
    # Complex processing with IDE support
    processed = [transform(f) for f in files]
    return {"result": processed, "count": len(processed)}

processor = PythonCodeNode.from_function(
    func=process_files,
    name="processor",
    description="Process file data"
)

```

**String code only for: dynamic generation, user input, templates, one-liners**
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

# OK for simple one-liner
node = PythonCodeNode(name="calc", code="result = value * 1.1")

# OK for dynamic generation
code = f"result = data['{user_field}'] > {threshold}"
node = PythonCodeNode(name="filter", code=code)

```

**⚠️ Remember: Input variables EXCLUDED from outputs**
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

# CORRECT: Different variable names for mapping
workflow = Workflow("example", name="Example")
workflow.  # Method signature

```

### Resilient Workflow (NEW)
```python
from kailash.workflow import Workflow, RetryStrategy

workflow = Workflow(workflow_id="resilient", name="Resilient Pipeline")

# Add retry policy
workflow.configure_retry(
    "api_call",
    max_retries=3,
    strategy=RetryStrategy.EXPONENTIAL
)

# Add fallback
workflow.add_fallback("primary_service", "backup_service")

# Add circuit breaker
workflow.configure_circuit_breaker("api_call", failure_threshold=5)

```

### Credential Management (NEW)
```python
from kailash.nodes.security import CredentialManagerNode

# Never hardcode credentials!
cred_node = CredentialManagerNode(
    credential_name="api_service",
    credential_type="api_key",
    credential_sources=["vault", "env"],  # Try vault first
    cache_duration_seconds=3600
)

```

### SharePoint Multi-Auth (NEW)
```python
from kailash.nodes.data import SharePointGraphReaderEnhanced

# Certificate auth (production)
sp_node = SharePointGraphReaderEnhanced()
result = await sp_node.execute(
    auth_method="certificate",
    certificate_path="/secure/cert.pem",
    tenant_id="tenant-id",
    client_id="app-id",
    site_url="https://company.sharepoint.com/sites/data",
    operation="list_files"
)

# Managed Identity (Azure)
result = await sp_node.execute(
    auth_method="managed_identity",
    site_url="https://company.sharepoint.com/sites/data",
    operation="list_files"
)

```

### DirectoryReaderNode (Best Practice)
```python
from kailash.nodes.data import DirectoryReaderNode

# Better than manual file discovery
file_discoverer = DirectoryReaderNode(
    name="discoverer",
    directory_path="data/inputs",
    recursive=False,
    file_patterns=["*.csv", "*.json", "*.txt"],
    include_metadata=True
)

```

### MCP Gateway Integration
```python
# Create gateway with MCP support
from kailash.middleware import create_gateway
from kailash.api.mcp_integration import MCPIntegration, MCPToolNode

# 1. Create gateway
gateway = create_gateway(
    title="MCP-Enabled App",
    cors_origins=["http://localhost:3000"]
)

# 2. Create MCP server
mcp = MCPIntegration("tools")

# Add tools (sync or async)
async def search_web('query', limit: int = 10):
    return {"results": ["result1", "result2"]}

mcp.add_tool("search", search_web, "Search web", {
    "query": {"type": "string", "required": True},
    "limit": {"type": "integer", "default": 10}
})

# 3. Use in workflows
from kailash.workflow.builder import WorkflowBuilder

builder = WorkflowBuilder("mcp_workflow")

# Add MCP tool node
search_node = MCPToolNode(
    mcp_server="tools",
    tool_name="search",
    parameter_mapping={"search_query": "query"}  # Map workflow -> tool params
)
builder.add_node("search", search_node)

# Register workflow
await gateway.agent_ui.register_workflow(
    "mcp_workflow", builder.build(), make_shared=True
)

```

### Centralized Data Access
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

from examples.utils.data_paths import get_input_data_path, get_output_data_path

# CORRECT: Use centralized data utilities
customer_file = get_input_data_path("customers.csv")
output_file = get_output_data_path("processed_data.csv")

reader = CSVReaderNode(name="reader", file_path=str(customer_file))

# WRONG: Hardcoded paths
reader = CSVReaderNode(name="reader", file_path="examples/data/customers.csv")

```

## 🔴 Common Mistakes
1. **Forgetting node suffix**: `CSVReader` → `CSVReaderNode`
2. **Using generic types**: `List[str]` → `list`
3. **Mapping to same variable**: `{"result": "result"}` → `{"result": "input_data"}`
4. **Missing PythonCodeNode name**: `PythonCodeNode(code=...)` → `PythonCodeNode(name="x", code=...)`
5. **Manual file operations**: Use `DirectoryReaderNode` not `os.listdir`
6. **Hardcoded data paths**: `"examples/data/file.csv"` → Use `get_input_data_path("file.csv")`
7. **Old execution pattern**: `node.execute()` → Use `node.execute()` for complete lifecycle

## 🎯 **Find What You Need**

| **I want to...** | **Go to...** |
|-------------------|--------------|
| Learn the basics | **[Fundamentals](01-fundamentals.md)** |
| Build workflows | **[Workflows](02-workflows.md)** |
| Find the right node | **[Node Catalog](../nodes/comprehensive-node-catalog.md)** |
| Use enterprise features | **[Advanced Features](03-advanced-features.md)** |
| Fix errors | **[Troubleshooting](05-troubleshooting.md)** |
