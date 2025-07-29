# Developer Guide - Quick Reference

## 🚨 Critical Rules
1. **Node names**: ALL end with "Node" (`CSVReaderNode` ✓, `CSVReader` ✗)
2. **Parameter types**: ONLY `str`, `int`, `float`, `bool`, `list`, `dict`, `Any`
3. **Never use generics**: No `List[T]`, `Dict[K,V]`, `Optional[T]`, `Union[A,B]`
4. **PythonCodeNode**: Input variables EXCLUDED from outputs! + **Dot Notation**
   - `# mapping removed)
   - `# mapping removed)
   - `# mapping removed)
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
| Async operations | `AsyncLocalRuntime` + `AsyncWorkflowBuilder` | Manual async handling |
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
- **[Node Index](../nodes/node-index.md)** - ⭐ Quick reference (47 lines)
- **[Node Selection Guide](../nodes/node-selection-guide.md)** - Smart selection (436 lines)
- **[Full Catalog](../nodes/comprehensive-node-catalog.md)** - Exhaustive docs (2194 lines)
- **[examples/](examples/)** - Working code examples

## ⚡ Quick Fix Templates

### WorkflowBuilder (Current API)
```python
# ✅ CORRECT: String-based node creation
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# Create nodes using string types
workflow.add_node(
    "CSVReaderNode",           # Node type as string
    "csv_reader",              # Node ID as string
    {                          # Configuration dictionary
        "file_path": "/data/inputs/customers.csv"
    }
)

workflow.add_node(
    "PythonCodeNode",
    "data_processor",
    {
        "code": "result = {'processed': len(input_data)}"
    }
)

# Connect using add_connection (4 parameters required)
workflow.add_connection("csv_reader", "data", "data_processor", "input_data")

```

### ⚠️ IMPORTANT: Connection Syntax Difference
```python
# WorkflowBuilder uses add_connection() with 4 parameters:
workflow = WorkflowBuilder()
workflow.add_connection(
    "source_node",       # Source node ID
    "output",            # Source output parameter name
    "target_node",       # Target node ID
    "input"              # Target input parameter name
)

# Standard workflow connection pattern:
workflow = WorkflowBuilder()
workflow.add_connection("source_node", "result", "target_node", "input")

# ❌ WRONG: Don't use old syntax!
# This will fail:
# workflow.connect(node1, node2, mapping={"output": "input"})

# This will fail on Workflow:
workflow.add_connection("node1", "output", "node2", "input")
```

### Unified Runtime (Enterprise Features)
```python
# ✅ CORRECT: Unified runtime with enterprise capabilities
from kailash.runtime.local import LocalRuntime
from kailash.access_control import UserContext

# Basic usage (backward compatible)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

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
results, run_id = runtime.execute(workflow.build(), parameters=parameters)

```

### Middleware Integration
```python
# ✅ CORRECT: Middleware imports and usage
from kailash.api.middleware import (
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

# ✅ ALWAYS use from_function for complex logic:
def process_files(input_data: dict) -> dict:
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

# OK for simple one-liner
workflow.add_node("PythonCodeNode", "calc", {"code": "result = value * 1.1"})

# OK for dynamic generation
code = f"result = data['{user_field}'] > {threshold}"
workflow.add_node("PythonCodeNode", "filter", {"code": code})

```

**⚠️ Remember: Input variables EXCLUDED from outputs**
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

# CORRECT: Different variable names for mapping
workflow = WorkflowBuilder()
workflow.add_connection("source", "output_data", "processor", "processed_data")

```

### Resilient Workflow (NEW)
```python
from kailash.workflow import Workflow, RetryStrategy

workflow = WorkflowBuilder()

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
workflow = WorkflowBuilder()
workflow.add_node("CredentialManagerNode", "cred_manager", {
    "credential_name": "api_service",
    "credential_type": "api_key",
    "credential_sources": ["vault", "env"],  # Try vault first
    "cache_duration_seconds": 3600
})

```

### SharePoint Multi-Auth (NEW)
```python
from kailash.nodes.data import SharePointGraphReaderEnhanced

# Certificate auth (production)
workflow = WorkflowBuilder()
workflow.add_node("SharePointGraphReaderEnhanced", "sp_reader", {})
runtime = AsyncLocalRuntime()
results, run_id = await runtime.execute_async(workflow.build(), parameters={
    "sp_reader": {
        "auth_method": "certificate",
        "certificate_path": "/secure/cert.pem",
        "tenant_id": "tenant-id",
        "client_id": "app-id",
        "site_url": "https://company.sharepoint.com/sites/data",
        "operation": "list_files"
    }
})

# Managed Identity (Azure)
results, run_id = await runtime.execute_async(workflow.build(), parameters={
    "sp_reader": {
        "auth_method": "managed_identity",
        "site_url": "https://company.sharepoint.com/sites/data",
        "operation": "list_files"
    }
})

```

### DirectoryReaderNode (Best Practice)
```python
from kailash.nodes.data import DirectoryReaderNode

# Better than manual file discovery
workflow = WorkflowBuilder()
workflow.add_node("DirectoryReaderNode", "discoverer", {
    "directory_path": "data/inputs",
    "recursive": False,
    "file_patterns": ["*.csv", "*.json", "*.txt"],
    "include_metadata": True
})

```

### MCP Gateway Integration
```python
# Create gateway with MCP support
from kailash.api.middleware import create_gateway
from kailash.api.mcp_integration import MCPIntegration, MCPToolNode

# 1. Create gateway
gateway = create_gateway(
    title="MCP-Enabled App",
    cors_origins=["http://localhost:3000"]
)

# 2. Create MCP server
mcp = MCPIntegration("tools")

# Add tools (sync or async)
async def search_web(query: str, limit: int = 10):
    return {"results": ["result1", "result2"]}

mcp.add_tool("search", search_web, "Search web", {
    "query": {"type": "string", "required": True},
    "limit": {"type": "integer", "default": 10}
})

# 3. Use in workflows
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# Add MCP tool node
workflow.add_node("MCPToolNode", "search", {
    "mcp_server": "tools",
    "tool_name": "search"
})

# Register workflow
await gateway.agent_ui.register_workflow(
    "mcp_workflow", workflow.build(), make_shared=True
)

```

### Centralized Data Access
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

from examples.utils.data_paths import get_input_data_path, get_output_data_path

# CORRECT: Use centralized data utilities
customer_file = get_input_data_path("customers.csv")
output_file = get_output_data_path("processed_data.csv")

workflow.add_node("CSVReaderNode", "reader", {"file_path": str(customer_file)})

# WRONG: Hardcoded paths
# reader = CSVReaderNode(name="reader", file_path="examples/data/customers.csv")  # Instance-based

```

## 🔴 Common Mistakes
1. **Forgetting node suffix**: `CSVReader` → `CSVReaderNode`
2. **Using generic types**: `List[str]` → `list`
3. **Mapping to same variable**: `{"result": "result"}` → `{"result": "input_data"}`
4. **Missing PythonCodeNode name**: `PythonCodeNode(code=...)` → `PythonCodeNode(name="x", code=...)`
5. **Manual file operations**: Use `DirectoryReaderNode` not `os.listdir`
6. **Hardcoded data paths**: `"examples/data/file.csv"` → Use `get_input_data_path("file.csv")`
7. **Old execution pattern**: `node.execute()` → Use workflow execution with `runtime.execute(workflow.build())`

## 🎯 **Find What You Need**

| **I want to...** | **Go to...** |
|-------------------|--------------|
| Learn the basics | **[Fundamentals](01-fundamentals.md)** |
| Build workflows | **[Workflows](02-workflows.md)** |
| Find the right node | **[Node Catalog](../nodes/comprehensive-node-catalog.md)** |
| Use enterprise features | **[Advanced Features](03-advanced-features.md)** |
| Fix errors | **[Troubleshooting](05-troubleshooting.md)** |
