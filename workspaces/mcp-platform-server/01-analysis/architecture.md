# MCP Platform Server: Architecture

## 1. Current State -- 6 Implementations

### Inventory

| # | Location | Protocol | Quality | Action |
|---|----------|----------|---------|--------|
| 1 | `packages/kailash-nexus/src/nexus/mcp/server.py` | Custom JSON (NOT JSON-RPC 2.0) | Low | **Delete** |
| 2 | `packages/kailash-nexus/src/nexus/mcp_websocket_server.py` | JSON-RPC 2.0 bridge | Medium | **Delete** |
| 3 | `src/kailash/trust/plane/mcp_server.py` | FastMCP | High | **Keep as reference** |
| 4 | `src/kailash/api/mcp_integration.py` | In-process registry | Medium | **Refactor** |
| 5 | `src/kailash/channels/mcp_channel.py` | Nexus channel | Medium | **Refactor** |
| 6 | `packages/kaizen-agents/src/kaizen_agents/delegate/mcp.py` | stdio JSON-RPC client | High | **Keep** |

### Detailed Assessment

**1. Nexus MCP Server** (`nexus/mcp/server.py`, `nexus/mcp/transport.py`): The `MCPServer` class registers `Workflow` objects and exposes them as MCP tools over WebSocket using a custom JSON message protocol. Supports `list_tools`, `call_tool`, `list_resources`. Transport layer includes `WebSocketServerTransport` and `WebSocketClientTransport`. Includes a `SimpleMCPClient` for testing. **Problem**: Non-standard protocol -- not JSON-RPC 2.0. Must delete.

**2. MCPWebSocketServer** (`nexus/mcp_websocket_server.py`): JSON-RPC 2.0 wrapper around server #1. Implements `initialize`, `tools/list`, `tools/call`, `resources/list`, `resources/read`. Bridges between `_tools` dict and `_workflows` dict. Uses `websockets 14.0+` API. **Problem**: Only exists because #1 isn't spec-compliant. Delete with #1.

**3. TrustPlane MCP Server** (`trust/plane/mcp_server.py`): Production-quality FastMCP server exposing 5 tools: `trust_check`, `trust_record`, `trust_envelope`, `trust_status`, `trust_verify`. Uses `mcp.server.FastMCP` (official MCP Python SDK). Thread-safe caching with double-checked locking, file-watching for manifest changes, standalone CLI entry point (`trustplane-mcp`). **This is the model to follow.**

**4. Core SDK MCP Integration** (`kailash/api/mcp_integration.py`): `MCPIntegration` is a tool/resource registry. Registers Python functions as MCP tools, wraps them in `MCPToolNode` for workflow execution. Includes a safe math evaluator (AST-based). Not a server -- an in-process integration layer. **Refactor**: becomes the internal tool registration API that feeds FastMCP.

**5. MCP Channel** (`kailash/channels/mcp_channel.py`): `MCPChannel` is a Nexus channel exposing workflows via MCP. Registers default tools (`list_workflows`, `execute_workflow`, `get_workflow_schema`, `channel_status`). Delegates to `MiddlewareMCPServer`. **Refactor**: thin wrapper around FastMCP.

**6. Kaizen MCP Client** (`kaizen_agents/delegate/mcp.py`): `McpClient` is a production-quality stdio JSON-RPC client managing MCP server subprocesses. Performs initialize handshake, discovers tools via `tools/list`, executes via `tools/call`. Tools registered into Kaizen `ToolRegistry` with `mcp_<server>_<tool>` prefix. Handles edge cases (EOF, timeouts, pending future cleanup). **Keep as-is -- this is a client, not a server.**

### Other MCP Components (Keep)

- `MCPPlatformAdapter` (`kailash/adapters/mcp_platform_adapter.py`) -- translates platform-format to SDK-format configs
- `EnterpriseMLCPExecutorNode` (`kailash/nodes/enterprise/mcp_executor.py`) -- workflow node calling MCP tools with circuit breaker
- `MCPCapabilityMixin` (`kailash/nodes/mixins/mcp.py`) -- adds MCP discovery/execution to workflow nodes
- `MCPEATPHandler` (`nexus/trust/mcp_handler.py`) -- EATP trust context for A2A MCP calls
- `mcp_registry.json` -- persistent server registry (test artifact)

## 2. FastMCP-Based Server Design

### Module Layout

```
src/kailash/mcp/
    __init__.py          # Exports KailashPlatformMCP
    server.py            # FastMCP instance, CLI entry point, contributor loader
    contrib/
        __init__.py      # register_tools() interface definition
        core.py          # Core SDK tools (list_node_types, describe_node, validate_workflow)
        platform.py      # platform_map() -- always loaded
        dataflow.py      # DataFlow tools (requires kailash-dataflow)
        nexus.py         # Nexus tools (requires kailash-nexus)
        kaizen.py        # Kaizen tools (requires kailash-kaizen)
        trust.py         # Trust tools (requires kailash[trust])
        pact.py          # PACT tools (requires kailash-pact)
```

### Server Lifecycle

```python
from mcp.server import FastMCP
import importlib
import logging

logger = logging.getLogger("kailash.mcp")

FRAMEWORK_CONTRIBUTORS = [
    ("kailash.mcp.contrib.core", "core"),
    ("kailash.mcp.contrib.platform", "platform"),
    ("kailash.mcp.contrib.dataflow", "dataflow"),
    ("kailash.mcp.contrib.nexus", "nexus"),
    ("kailash.mcp.contrib.kaizen", "kaizen"),
    ("kailash.mcp.contrib.trust", "trust"),
    ("kailash.mcp.contrib.pact", "pact"),
]

def create_server(project_root: Path) -> FastMCP:
    server = FastMCP("kailash-platform")
    
    for module_path, namespace in FRAMEWORK_CONTRIBUTORS:
        try:
            mod = importlib.import_module(module_path)
            mod.register_tools(server, project_root)
            logger.info("Loaded %s contributor (%d tools)", namespace, ...)
        except ImportError:
            logger.info("Framework %s not installed, skipping", namespace)
    
    return server
```

### Contributor Protocol

Every contributor module implements exactly one function:

```python
def register_tools(server: FastMCP, project_root: Path) -> None:
    """Register framework tools with the MCP server.
    
    Args:
        server: FastMCP instance to register tools on.
        project_root: Absolute path to the project being introspected.
    """
    @server.tool(name="namespace.tool_name", description="...")
    async def tool_name(...) -> dict:
        ...
```

The `project_root` parameter is critical -- introspection tools scan the project's actual models, handlers, and agents. Discovery order:

1. `--project-root` CLI argument
2. `KAILASH_PROJECT_ROOT` environment variable
3. `Path.cwd()`

### Framework Auto-Discovery

Contributors do not hardcode names. They use the same introspection the framework itself uses:

- **DataFlow**: Imports project models module, scans for `@db.model` decorated classes via DataFlow registry
- **Nexus**: Reads Nexus app configuration for registered handlers and channels
- **Kaizen**: Scans for `BaseAgent` subclasses and `Delegate` instances
- **Core SDK**: Reads node registry for all registered node types

## 3. Tool Schemas by Category

### Introspection Tools (Tier 1 -- read-only, safe)

| Tool | Input | Output |
|------|-------|--------|
| `dataflow.list_models()` | none | `{models: [{name, fields_count, has_timestamps, table_name, soft_delete}]}` |
| `dataflow.describe_model(model_name)` | `{model_name: str}` | `{name, fields: [{name, type, primary_key, nullable, default, classification}], generated_nodes: [str], relationships: [...]}` |
| `dataflow.query_schema()` | none | `{database_url_configured: bool, dialect: str, models_count: int, migrations_pending: bool}` |
| `nexus.list_handlers()` | none | `{handlers: [{name, method, path, description, channel, middleware}]}` |
| `nexus.list_channels()` | none | `{channels: [{name, type, status, handlers_count}]}` |
| `nexus.list_events()` | none | `{events: [{name, handlers_subscribed: [str], event_type}]}` |
| `kaizen.list_agents()` | none | `{agents: [{name, class, signature_fields, tools_count, strategy, mcp_servers}]}` |
| `kaizen.describe_agent(agent_name)` | `{agent_name: str}` | `{name, signature: {inputs, outputs}, tools, strategy, mcp_servers, guardrails}` |
| `core.list_node_types()` | none | `{node_types: [{name, description, category, parameters}]}` |
| `core.describe_node(node_type)` | `{node_type: str}` | `{name, parameters: [{name, type, required, default, description}], inputs, outputs}` |
| `platform.platform_map()` | optional `{frameworks?: [str], include_connections?: bool}` | Full cross-framework graph (see section 4) |
| `trust.trust_status()` | none | `{posture, has_envelope, blocked_actions, session_info}` |
| `pact.org_tree()` | none | `{hierarchy with governance envelopes}` |

### Scaffold Tools (Tier 2 -- code generation, returned as text)

| Tool | Input | Output |
|------|-------|--------|
| `dataflow.scaffold_model(name, fields)` | `{name: str, fields: [{name: str, type: str}]}` | `{file_path: str, code: str}` |
| `nexus.scaffold_handler(name, method, path)` | `{name: str, method: str, path: str, description?: str}` | `{file_path: str, code: str, tests_path: str, tests_code: str}` |
| `kaizen.scaffold_agent(name, purpose)` | `{name: str, purpose: str, tools?: [str]}` | `{file_path: str, code: str, test_path: str, test_code: str}` |

Scaffold tools return code as text. The AI writes the files. The tool does NOT write to disk.

### Validation Tools (Tier 3 -- project analysis, subprocess-isolated)

| Tool | Input | Output |
|------|-------|--------|
| `dataflow.validate_model(model_name)` | `{model_name: str}` | `{valid: bool, errors: [str], warnings: [str]}` |
| `nexus.validate_handler(handler_name)` | `{handler_name: str}` | `{valid: bool, errors: [str], warnings: [str]}` |
| `core.validate_workflow(workflow)` | `{workflow: dict}` | `{valid: bool, errors: [str], node_count: int, has_cycles: bool}` |

Validation tools import and inspect project code, which may trigger module-level side effects. Each validation call runs in a subprocess with a 10-second timeout.

### Test Generation Tools (Tier 2)

| Tool | Input | Output |
|------|-------|--------|
| `dataflow.generate_tests(model_name, tier?)` | `{model_name: str, tier: str = "all"}` | `{test_code: str, test_path: str, imports: [str]}` |
| `nexus.generate_tests(handler_name)` | `{handler_name: str}` | `{test_code: str}` |
| `kaizen.generate_tests(agent_name)` | `{agent_name: str}` | `{test_code: str}` |
| `core.generate_test_data(model_name, count?)` | `{model_name: str, count: int = 5}` | `{test_data: [dict], factory_code: str}` |

### Execution Tools (Tier 4 -- dangerous, require authorization)

| Tool | Input | Output |
|------|-------|--------|
| `nexus.test_handler(handler_name, request)` | `{handler_name: str, method: str, path: str, body?: dict}` | `{status_code: int, body: dict, headers: dict}` |
| `kaizen.test_agent(agent_name, input)` | `{agent_name: str, input: str}` | `{output: str, tool_calls: [dict], tokens_used: int}` |

## 4. platform_map() Design

The highest-value tool. Single-call understanding of the entire project.

### Output Schema

```json
{
  "project": {
    "name": "my-app",
    "root": "/path/to/project",
    "python_version": "3.12",
    "kailash_version": "0.7.1"
  },
  "frameworks": {
    "core": {"installed": true, "version": "0.7.1"},
    "dataflow": {"installed": true, "version": "0.4.2"},
    "nexus": {"installed": true, "version": "0.3.1"},
    "kaizen": {"installed": true, "version": "0.6.8"},
    "pact": {"installed": false},
    "trust": {"installed": true, "version": "0.7.1"}
  },
  "models": [
    {
      "name": "User",
      "fields": ["id", "name", "email", "created_at"],
      "generated_nodes": ["CreateUser", "ReadUser", "UpdateUser", "DeleteUser", "ListUser"],
      "used_by_handlers": ["create_user_handler", "get_user_handler"],
      "used_by_agents": []
    }
  ],
  "handlers": [
    {
      "name": "create_user_handler",
      "method": "POST",
      "path": "/api/users",
      "uses_models": ["User"],
      "channel": "api"
    }
  ],
  "agents": [
    {
      "name": "SupportAgent",
      "tools": ["search_docs", "create_ticket"],
      "mcp_servers": ["github"],
      "uses_models": [],
      "strategy": "multi_cycle"
    }
  ],
  "channels": [
    {"name": "api", "type": "http", "handlers_count": 12},
    {"name": "cli", "type": "cli", "commands_count": 5},
    {"name": "mcp", "type": "mcp", "tools_count": 8}
  ],
  "connections": [
    {"from": "User", "to": "create_user_handler", "type": "model_to_handler"},
    {"from": "create_user_handler", "to": "api", "type": "handler_to_channel"},
    {"from": "SupportAgent", "to": "search_docs", "type": "agent_to_tool"}
  ],
  "trust": {
    "posture": "cautious",
    "has_envelope": true,
    "blocked_actions": ["delete_production_data"]
  }
}
```

### Cross-Framework Connection Detection

Connections are discovered via static analysis + registry inspection (no execution):

1. **Model-to-Handler**: Scan handler source for DataFlow generated node references (`CreateUser`, `ReadUser`). Generated names follow deterministic pattern `{Action}{ModelName}`. Use `ast.parse` for reliable detection.
2. **Handler-to-Channel**: Read Nexus app configuration for handler-to-channel mappings.
3. **Agent-to-Tool**: Read agent tool registrations and MCP server configurations.
4. **Model-to-Agent**: Check if agent tool implementations reference DataFlow Express or generated nodes.

### Performance

Target: under 2 seconds for a project with 20 models, 20 handlers, 5 agents.

`platform_map()` is exposed as both:
- A **tool** (callable with optional filter parameters)
- A **resource** at `kailash://platform-map` (subscriptable; clients notified on change)

## 5. MCP Resources vs Tools vs Prompts

### Resources (read-only, subscriptable)

Use resources for structural data that benefits from MCP resource subscriptions:

- `kailash://models` -- list of all DataFlow models (resource template)
- `kailash://models/{model_name}` -- schema for a specific model
- `kailash://handlers` -- list of all Nexus handlers
- `kailash://agents` -- list of all Kaizen agents
- `kailash://platform-map` -- full platform graph
- `kailash://node-types` -- available Core SDK node types
- `kailash://trust/envelope` -- current constraint envelope

### Tools (callable functions with side effects or dynamic input)

- All scaffold operations (generate code)
- All validation operations (need specific input)
- All execution operations (run tests, call handlers)
- `platform_map()` as both resource and tool (resource for subscriptions, tool for filtered queries)

### Prompts (reusable templates)

- `kailash://prompts/new-model` -- prompt for creating a DataFlow model
- `kailash://prompts/new-handler` -- prompt for creating a Nexus handler
- `kailash://prompts/new-agent` -- prompt for creating a Kaizen agent

Prompts combine documentation with live introspection context.

## 6. Security Model

### Tier 1: Introspection (read-only)

No authorization required. Tools read project metadata and return it. Cannot modify state or execute code.

### Tier 2: Scaffold (code generation)

Low risk. Tool returns code as a string. The AI writes the file. The tool itself does not write to disk. Input validation prevents path traversal in suggested file paths.

### Tier 3: Validation (project analysis)

Medium risk. Validation tools import and inspect project code. They do not execute business logic, but importing modules triggers module-level side effects. **Mitigation**: validation runs in a subprocess (or ProcessPoolExecutor). 10-second timeout per call. Default: enabled (set `KAILASH_MCP_ENABLE_VALIDATION=false` to disable).

### Tier 4: Execution (test_handler, test_agent)

High risk. `test_handler()` makes HTTP requests. `test_agent()` invokes LLM calls (costs money, may have side effects).

Requirements:
1. **Environment gating**: `KAILASH_MCP_ENABLE_EXECUTION=true` required
2. **Trust plane integration**: if `kailash[trust]` installed, calls `trust_check()` first
3. **PACT governance**: if `kailash-pact` installed, verifies caller's envelope permits the operation
4. **Tool description**: explicitly states "This will execute code/make network requests"

Default: disabled. Tier 4 tools not registered without the env var.

## 7. Testing Strategy

### Unit Tests (mock, no running server)

- Import each contributor module; verify it registers expected tools
- Mock DataFlow registry, Nexus app config, Kaizen agent registry
- Verify `platform_map()` assembles graph correctly from mocked registries
- Verify graceful degradation when frameworks are not installed (mock `ImportError`)
- Verify security tier enforcement with/without env var

### Integration Tests (real MCP client/server)

Use Kaizen's `McpClient` to connect to the platform server as a subprocess:

```python
async def test_introspection_server():
    config = McpServerConfig(
        name="kailash-platform",
        command="python",
        args=["-m", "kailash.mcp.server", "--project-root", str(project_dir)],
    )
    client = McpClient(config)
    await client.start()

    tools = await client.discover_tools()
    assert any(t.name == "dataflow.list_models" for t in tools)

    result = await client.call_tool("dataflow.list_models", {})
    parsed = json.loads(result)
    assert "models" in parsed

    await client.stop()
```

### E2E Tests (real project with real frameworks)

Test fixture project at `tests/fixtures/mcp_test_project/` with: one DataFlow model (User), one Nexus handler (create_user), one Kaizen agent (SupportAgent). Verify:

- `platform_map()` returns correct cross-framework graph
- `dataflow.describe_model("User")` returns correct schema
- `nexus.list_handlers()` lists registered handlers
- Scaffold tools return valid Python code
- Validation tools detect intentionally invalid configurations
- `model_to_handler` connection detected when handler references `CreateUser` node name

### Existing Test Infrastructure

- `tests/utils/mcp_test_runner.py` -- existing MCP test utilities
- `tests/integration/mcp_server/` -- existing integration test suites to build on

## 8. A2A Consideration (Future)

The platform MCP server's tools map to A2A as follows:

- MCP tools are the external interface for Claude Code and MCP clients
- A2A capability cards can reference MCP tool sets (agent declares "I can introspect DataFlow models" backed by `dataflow.describe_model()`)
- PACT governance applies to both MCP and A2A
- The `connections` array in `platform_map()` maps to A2A capability discovery
- `MCPEATPHandler` already exists for cross-organization trust context

For cross-org A2A, the platform server would need: authentication (JWT/mTLS), per-tool access control via PACT envelopes, delegation tracking via `MCPEATPHandler`. This is a separate milestone from the initial introspection server.

## 9. Key Existing Files

These files exist in kailash-py and are relevant to this work:

| File | Role |
|------|------|
| `src/kailash/trust/plane/mcp_server.py` | Quality reference for FastMCP usage |
| `packages/kaizen-agents/src/kaizen_agents/delegate/mcp.py` | Test harness (McpClient) |
| `src/kailash/api/mcp_integration.py` | Refactor target (tool registration) |
| `src/kailash/channels/mcp_channel.py` | Refactor target (thin FastMCP wrapper) |
| `packages/kailash-nexus/src/nexus/mcp/server.py` | Delete target |
| `packages/kailash-nexus/src/nexus/mcp_websocket_server.py` | Delete target |
| `src/kailash/adapters/mcp_platform_adapter.py` | Keep (platform config adapter) |
| `src/kailash/nodes/enterprise/mcp_executor.py` | Keep (enterprise circuit breaker) |
| `src/kailash/nodes/mixins/mcp.py` | Keep (MCP capability mixin) |
| `packages/kailash-nexus/src/nexus/trust/mcp_handler.py` | Keep (EATP trust for A2A) |
| `packages/kailash-kaizen/docs/guides/mcp-vs-a2a-decision-guide.md` | Reference |
| `pyproject.toml` | `kailash[mcp]` extra already exists |
| `tests/utils/mcp_test_runner.py` | Existing test utilities |
| `tests/integration/mcp_server/` | Existing integration tests |
