# Framework Dependencies on Core SDK

## 1. Overview

This document maps every import path from the three framework packages (DataFlow, Nexus, Kaizen)
into the Core SDK (`kailash.*`). This defines the **public contract surface area** that SDK 2.0
must preserve during the Rust core migration.

## 2. DataFlow Dependencies

DataFlow (`apps/kailash-dataflow/src/dataflow/`) is the heaviest consumer of Core SDK APIs.

### 2.1 Import Map

| Core SDK Import                                                      | DataFlow Files Using It                                                                                                                                                                                 | Category              |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------- |
| `kailash.workflow.builder.WorkflowBuilder`                           | engine.py, model_registry.py, workflow_binding.py, gateway_integration.py, migration/_.py, validators/_.py, testing/\*.py, nodes/workflow_connection_manager.py                                         | Workflow Construction |
| `kailash.runtime.local.LocalRuntime`                                 | engine.py, model_registry.py, workflow_binding.py, gateway_integration.py, migration/_.py, testing/_.py, protection_middleware.py                                                                       | Sync Execution        |
| `kailash.runtime.AsyncLocalRuntime`                                  | engine.py, model_registry.py, gateway_integration.py, migration/_.py, testing/_.py                                                                                                                      | Async Execution       |
| `kailash.nodes.base.Node`                                            | nodes.py, protection_middleware.py, nodes/smart_operations.py, nodes/dynamic_update.py, nodes/schema_nodes.py, nodes/natural_language_filter.py, nodes/semantic_memory.py                               | Node Base Class       |
| `kailash.nodes.base.NodeParameter`                                   | nodes.py, all nodes/\*.py files                                                                                                                                                                         | Parameter Definition  |
| `kailash.nodes.base.NodeRegistry`                                    | engine.py (x2), nodes.py, nodes/smart_operations.py, nodes/workflow_connection_manager.py, nodes/natural_language_filter.py                                                                             | Node Lookup           |
| `kailash.nodes.base_async.AsyncNode`                                 | nodes.py, all async nodes/\*.py files (bulk_create, bulk_update, bulk_delete, bulk_upsert, transaction_nodes, saga_coordinator, etc.)                                                                   | Async Node Base       |
| `kailash.nodes.base.register_node`                                   | All nodes/_.py files (bulk*create, bulk_update, bulk_delete, bulk_upsert, bulk_create_pool, security*_, monitoring*\*, transaction*\*, saga_coordinator, two_phase_commit, vector_nodes, mongodb_nodes) | Node Registration     |
| `kailash.nodes.data.async_sql.AsyncSQLDatabaseNode`                  | engine.py (x6), nodes.py (x2), protected*engine.py, nodes/bulk*\*.py, nodes/schema_nodes.py, migration/migration_connection_manager.py                                                                  | Database Operations   |
| `kailash.nodes.data.sql.SQLDatabaseNode`                             | model_registry.py                                                                                                                                                                                       | Sync DB Operations    |
| `kailash.nodes.data.workflow_connection_pool.WorkflowConnectionPool` | nodes/bulk_create_pool.py, nodes/workflow_connection_manager.py                                                                                                                                         | Connection Pooling    |
| `kailash.workflow.graph.Workflow`                                    | protection_middleware.py                                                                                                                                                                                | Workflow Type         |
| `kailash.sdk_exceptions.*`                                           | nodes.py, all nodes/\*.py files                                                                                                                                                                         | Exception Types       |
| `kailash.access_control.managers.AccessControlManager`               | nodes/security_access_control.py                                                                                                                                                                        | RBAC                  |
| `kailash.nodes.auth.mfa.MultiFactorAuthNode`                         | nodes/security_mfa.py                                                                                                                                                                                   | MFA Integration       |
| `kailash.nodes.security.threat_detection.*`                          | nodes/security_threat_detection.py                                                                                                                                                                      | Threat Detection      |
| `kailash.nodes.transaction.saga_coordinator.*`                       | nodes/saga_coordinator.py                                                                                                                                                                               | Saga Pattern          |
| `kailash.nodes.transaction.two_phase_commit.*`                       | nodes/two_phase_commit_coordinator.py                                                                                                                                                                   | 2PC Pattern           |
| `kailash.nodes.transaction.distributed_transaction_manager.*`        | nodes/transaction_manager.py                                                                                                                                                                            | Distributed Txn       |
| `kailash.nodes.monitoring.*`                                         | nodes/monitoring_integration.py                                                                                                                                                                         | Monitoring Nodes      |

### 2.2 Usage Patterns

DataFlow's core engine (`core/engine.py`, ~6600+ LOC) is the primary consumer:

```python
# Pattern 1: Workflow construction + execution (most common)
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.runtime import AsyncLocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("AsyncSQLDatabaseNode", node_id, config)
runtime = AsyncLocalRuntime()
results, run_id = await runtime.execute_workflow_async(workflow.build())

# Pattern 2: Node registration (DataFlow auto-generates nodes per model)
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode

@register_node()
class CreateUser(AsyncNode):
    def get_parameters(self): ...
    async def execute_async(self, **kwargs): ...

# Pattern 3: Direct node class access
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
node = AsyncSQLDatabaseNode(connection_string=db_url, query=sql)
```

### 2.3 Critical Dependencies

- **AsyncSQLDatabaseNode**: DataFlow's most critical dependency (imported 15+ times). This node wraps SQLAlchemy async and provides query execution. DataFlow uses it internally, not as a workflow node.
- **WorkflowBuilder + Runtime**: Every DataFlow operation compiles down to a workflow that is executed via the runtime.
- **NodeRegistry**: DataFlow auto-generates 11 node types per model and registers them.

## 3. Nexus Dependencies

Nexus (`apps/kailash-nexus/src/nexus/`) depends on Core SDK for workflow execution and MCP.

### 3.1 Import Map

| Core SDK Import                                              | Nexus Files Using It                            | Category               |
| ------------------------------------------------------------ | ----------------------------------------------- | ---------------------- |
| `kailash.workflow.Workflow`                                  | core.py, resources.py, discovery.py             | Workflow Type          |
| `kailash.workflow.builder.WorkflowBuilder`                   | core.py, resources.py, discovery.py             | Workflow Construction  |
| `kailash.servers.gateway.create_gateway`                     | core.py                                         | Gateway Factory        |
| `kailash.channels.ChannelConfig`                             | core.py                                         | Channel Config         |
| `kailash.channels.ChannelType`                               | core.py                                         | Channel Type Enum      |
| `kailash.channels.MCPChannel`                                | core.py                                         | MCP Channel            |
| `kailash.mcp_server.MCPServer`                               | core.py, resources.py                           | MCP Server             |
| `kailash.mcp_server.auth.APIKeyAuth`                         | core.py                                         | MCP Auth               |
| `kailash.runtime.AsyncLocalRuntime`                          | core.py, mcp_websocket_server.py, mcp/server.py | Async Runtime          |
| `kailash.runtime.get_runtime`                                | core.py                                         | Runtime Factory        |
| `kailash.nodes.handler.make_handler_workflow`                | core.py                                         | Handler Workflows      |
| `kailash.nodes.code.common.ALLOWED_MODULES`                  | core.py                                         | Module Whitelist       |
| `kailash.nodes.code.common.ALLOWED_ASYNC_MODULES`            | core.py                                         | Async Module Whitelist |
| `kailash.middleware.auth.auth_manager.MiddlewareAuthManager` | plugins.py                                      | Auth Middleware        |

### 3.2 Usage Patterns

```python
# Pattern 1: Multi-channel deployment
from kailash.servers.gateway import create_gateway
from kailash.channels import ChannelConfig, ChannelType, MCPChannel
from kailash.mcp_server import MCPServer

gateway = create_gateway(workflows, channels=[api, cli, mcp])

# Pattern 2: Handler-based workflows (bypasses PythonCodeNode sandbox)
from kailash.nodes.handler import make_handler_workflow
workflow = make_handler_workflow(handler_func, "handler_name")

# Pattern 3: Async execution for API requests
from kailash.runtime import AsyncLocalRuntime
runtime = AsyncLocalRuntime()
results, run_id = await runtime.execute_workflow_async(workflow.build())
```

### 3.3 Critical Dependencies

- **Gateway/Channels**: Nexus's core value proposition is multi-channel deployment. It depends heavily on `kailash.servers.gateway` and `kailash.channels.*`.
- **MCPServer**: Nexus wraps the Core SDK's MCP server for tool exposure.
- **Handler system**: `make_handler_workflow` converts async functions into workflows.

## 4. Kaizen Dependencies

Kaizen (`apps/kailash-kaizen/src/kaizen/`) depends on Core SDK for workflow execution, node system, and MCP.

### 4.1 Import Map

| Core SDK Import                            | Kaizen Files Using It                                                                                                                                                                                       | Category              |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------- |
| `kailash.workflow.builder.WorkflowBuilder` | core/base_agent.py, core/workflow_generator.py, orchestration/runtime.py, orchestration/core/patterns.py, strategies/_.py, mixins/_.py, trust/_.py, governance/_.py, agents/nodes.py, memory/backends/\*.py | Workflow Construction |
| `kailash.runtime.AsyncLocalRuntime`        | orchestration/runtime.py, strategies/async_single_shot.py, trust/_.py, governance/_.py, integrations/nexus/storage.py                                                                                       | Async Runtime         |
| `kailash.runtime.local.LocalRuntime`       | strategies/single_shot.py, strategies/multi_cycle.py, memory/backends/dataflow_backend.py                                                                                                                   | Sync Runtime          |
| `kailash.nodes.base.Node`                  | core/base_agent.py, nodes/ai/\*.py                                                                                                                                                                          | Node Base Class       |
| `kailash.nodes.base.NodeParameter`         | core/base_agent.py, nodes/ai/\*.py                                                                                                                                                                          | Parameter Definition  |
| `kailash.nodes.base.register_node`         | nodes/ai/\*.py (llm_agent, agents, models, embedding_generator, semantic_memory, hybrid_search, self_organizing, streaming_analytics, intelligent_agent_orchestrator)                                       | Node Registration     |
| `kailash.nodes.code.python.PythonCodeNode` | signatures/core.py (x2)                                                                                                                                                                                     | Code Execution        |
| `kailash.mcp_server.MCPServer`             | mcp/builtin_server/server.py                                                                                                                                                                                | MCP Server            |
| `kailash.mcp_server.client.MCPClient`      | core/base_agent.py, nodes/ai/llm_agent.py (x3)                                                                                                                                                              | MCP Client            |
| `kailash.mcp_server.enable_auto_discovery` | core/base_agent.py                                                                                                                                                                                          | MCP Discovery         |
| `kailash.runtime.ResourceRegistry`         | orchestration/runtime.py                                                                                                                                                                                    | Resource Management   |
| `kailash.workflow.base.Workflow`           | orchestration/runtime.py                                                                                                                                                                                    | Workflow Type         |
| `kailash.nodes.NodeRegistry`               | agents/nodes.py                                                                                                                                                                                             | Node Lookup           |

### 4.2 Usage Patterns

```python
# Pattern 1: Agent as workflow (BaseAgent inherits from Node)
from kailash.nodes.base import Node, NodeParameter
from kailash.workflow.builder import WorkflowBuilder

class BaseAgent(Node):
    # Agent IS a node, can be composed in workflows
    def run(self, **inputs):
        workflow = WorkflowBuilder()
        # Build internal workflow with LLM nodes
        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

# Pattern 2: Strategy-based execution
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

class SingleShotStrategy:
    def execute(self, workflow_builder):
        runtime = LocalRuntime()
        return runtime.execute(workflow_builder.build())

# Pattern 3: MCP integration for tool use
from kailash.mcp_server.client import MCPClient
client = MCPClient(server_url)
tools = await client.list_tools()
result = await client.call_tool("tool_name", args)
```

### 4.3 Critical Dependencies

- **BaseAgent inherits from Node**: This is the deepest integration. Kaizen agents ARE workflow nodes. Breaking the Node interface breaks all agents.
- **WorkflowBuilder + Runtime**: Every agent execution builds and runs a workflow internally.
- **MCPClient**: Agent tool-use depends on MCP client for external tool invocation.
- **PythonCodeNode**: Signature compilation generates PythonCodeNode instances.

## 5. Public Contract Surface Area

### 5.1 Must-Preserve APIs

These APIs are used by 2+ frameworks and form the immutable public contract:

| API                                          | DataFlow | Nexus  | Kaizen | Total Uses |
| -------------------------------------------- | -------- | ------ | ------ | ---------- |
| `WorkflowBuilder.add_node()`                 | High     | Medium | High   | ~50+       |
| `WorkflowBuilder.connect()`                  | High     | Low    | Medium | ~30+       |
| `WorkflowBuilder.build()`                    | High     | Medium | High   | ~40+       |
| `LocalRuntime.execute()`                     | High     | Low    | Medium | ~20+       |
| `AsyncLocalRuntime.execute_workflow_async()` | High     | Medium | Medium | ~15+       |
| `Node.__init__(**kwargs)`                    | High     | Low    | High   | ~30+       |
| `Node.get_parameters()`                      | High     | Low    | High   | ~30+       |
| `Node.run(**inputs)` / `execute()`           | High     | Low    | High   | ~30+       |
| `AsyncNode.execute_async()`                  | High     | Low    | Medium | ~20+       |
| `NodeRegistry.get(name)`                     | Medium   | Low    | Low    | ~10+       |
| `register_node()` decorator                  | High     | Low    | High   | ~25+       |
| `NodeParameter` model                        | High     | Low    | High   | ~30+       |

### 5.2 Framework-Specific APIs

| API                      | Framework      | Risk Level                  |
| ------------------------ | -------------- | --------------------------- |
| `AsyncSQLDatabaseNode`   | DataFlow only  | High - deep integration     |
| `MCPServer`, `MCPClient` | Nexus + Kaizen | Medium - protocol layer     |
| `create_gateway`         | Nexus only     | Low - thin wrapper          |
| `PythonCodeNode`         | Kaizen only    | Medium - compilation target |
| `make_handler_workflow`  | Nexus only     | Low - utility function      |

### 5.3 Exception Types Used Across Frameworks

All three frameworks depend on these exception types from `kailash.sdk_exceptions`:

- `NodeExecutionError` - Most common (all frameworks)
- `NodeValidationError` - DataFlow + Kaizen
- `NodeConfigurationError` - DataFlow (via Workflow internals)
- `WorkflowExecutionError` - All frameworks
- `WorkflowValidationError` - All frameworks
- `RuntimeExecutionError` - All frameworks

## 6. Dependency Graph Visualization

```
                    +------------------+
                    |   Core SDK       |
                    |   (kailash.*)    |
                    +------------------+
                   /        |          \
                  /         |           \
     +-----------+  +-------+------+  +----------+
     | DataFlow  |  |    Nexus     |  |  Kaizen  |
     +-----------+  +--------------+  +----------+
     |             |               |              |
     | workflow.*  | workflow.*    | workflow.*   |
     | runtime.*   | runtime.*    | runtime.*    |
     | nodes.base  | servers.*    | nodes.base   |
     | nodes.data  | channels.*   | nodes.code   |
     | sdk_except  | mcp_server.* | mcp_server.* |
     |             | middleware.*  | resources.*  |
     +-----------+  +--------------+  +----------+
```

## 7. Migration Impact Assessment

### 7.1 High Impact (Breaking Change Risk)

- **Node base class changes**: All 3 frameworks inherit from `Node` or `AsyncNode`
- **WorkflowBuilder.build() return type**: All frameworks expect `Workflow` objects
- **Runtime.execute() return signature**: `(dict, str|None)` tuple is universal contract
- **NodeParameter model**: Used for schema definition in all frameworks

### 7.2 Medium Impact (Adaptation Required)

- **networkx removal**: Frameworks don't import networkx directly, but they depend on `Workflow` behavior that is powered by networkx internally
- **Execution order changes**: If Rust core changes scheduling, framework tests may break
- **Validation mode changes**: Frameworks rely on current validation behavior

### 7.3 Low Impact (Transparent)

- **Performance improvements**: Faster DAG scheduling is transparent to frameworks
- **Internal refactoring**: Mixin changes, base class restructuring
- **Resource management**: Internal to runtime, frameworks use public API
