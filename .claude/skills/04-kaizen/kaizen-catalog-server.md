# Kaizen Catalog MCP Server

Standalone MCP server for agent catalog discovery, deployment, application management, and governance validation.

## Overview

The Catalog MCP Server exposes Kaizen agent catalog operations as MCP tools over stdio:

- **11 MCP tools** across 4 categories: Discovery (4), Deployment (3), Application (2), Governance (2)
- **Separate from KaizenMCPServer**: This server handles catalog/registry operations; KaizenMCPServer handles BaseAgent tool execution
- **Pre-seeds 14 built-in agents** (simple-qa, react-agent, chain-of-thought, planning-agent, rag-research, code-gen, memory-agent, vision-agent, debate-agent, consensus-agent, and more) on startup
- **In-memory registry** with bounded storage (max 10,000 agents, 10,000 apps) and LRU eviction
- **Entry point**: `python -m kaizen.mcp.catalog_server`

**Source modules**:

- `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/server.py` -- `CatalogMCPServer`
- `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/registry.py` -- `MemoryRegistry`
- `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/__main__.py` -- Entry point
- `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/tools/discovery.py` -- Discovery tool handlers
- `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/tools/deployment.py` -- Deployment tool handlers
- `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/tools/application.py` -- Application tool handlers
- `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/tools/governance.py` -- Governance tool handlers

---

## Starting the Server

### Command Line

```bash
python -m kaizen.mcp.catalog_server
```

The server reads JSON-RPC requests from stdin and writes responses to stdout (line-delimited JSON). Logs go to stderr at WARNING level.

### Claude Code MCP Configuration

Add to your Claude Code MCP settings (`.claude/mcp.json` or equivalent):

```json
{
  "mcpServers": {
    "kaizen-catalog": {
      "command": "python",
      "args": ["-m", "kaizen.mcp.catalog_server"],
      "transport": "stdio"
    }
  }
}
```

### Programmatic Usage

```python
from kaizen.mcp.catalog_server.server import CatalogMCPServer

server = CatalogMCPServer()

# Handle a single JSON-RPC request
response = server.handle_request({
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {},
})
# response["result"]["serverInfo"]["name"] == "kaizen-catalog"

# Or run the stdio loop
server.serve_stdio()
```

---

## MCP Protocol Flow

The server follows the MCP specification:

1. Client sends `initialize` -- server responds with capabilities
2. Client sends `notifications/initialized` -- server acknowledges (no response)
3. Client sends `tools/list` -- server responds with 11 tool definitions
4. Client sends `tools/call` with tool name and arguments -- server executes and returns

The server requires `initialize` before accepting `tools/list` or `tools/call` requests.

---

## All 11 Tools

### Discovery Tools (4)

#### `catalog_search`

Search the agent catalog by query string, capabilities, type, or status.

| Parameter      | Type       | Required | Description                                                |
| -------------- | ---------- | -------- | ---------------------------------------------------------- |
| `query`        | `string`   | No       | Substring match against agent name or description          |
| `capabilities` | `string[]` | No       | Filter agents that have ALL of these capabilities          |
| `type`         | `string`   | No       | Filter by agent type (substring match on `class_name`)     |
| `status`       | `string`   | No       | Filter by exact status (e.g. `"registered"`, `"deployed"`) |

**Returns**: List of matching agent records.

```json
{
  "name": "catalog_search",
  "arguments": { "query": "market", "capabilities": ["analysis"] }
}
```

#### `catalog_describe`

Get the full detail record for a specific agent by name.

| Parameter | Type     | Required | Description               |
| --------- | -------- | -------- | ------------------------- |
| `name`    | `string` | Yes      | The agent name to look up |

**Returns**: Full agent record including capabilities, tools, module path, governance. Returns `null` if not found.

```json
{ "name": "catalog_describe", "arguments": { "name": "react-agent" } }
```

#### `catalog_schema`

Retrieve the input and output JSON Schema for an agent.

| Parameter | Type     | Required | Description               |
| --------- | -------- | -------- | ------------------------- |
| `name`    | `string` | Yes      | The agent name to look up |

**Returns**: Agent's `input_schema` and `output_schema` if declared in the manifest.

```json
{ "name": "catalog_schema", "arguments": { "name": "market-analyzer" } }
```

#### `catalog_deps`

Validate the dependency graph (DAG) for a composite agent pipeline.

| Parameter | Type       | Required | Description                                                   |
| --------- | ---------- | -------- | ------------------------------------------------------------- |
| `agents`  | `object[]` | Yes      | Agent descriptors with `name` (str) and `inputs_from` (str[]) |

**Returns**: DAG validation result with `is_valid`, `topological_order`, `cycles`, `warnings`.

```json
{
  "name": "catalog_deps",
  "arguments": {
    "agents": [
      { "name": "fetcher", "inputs_from": [] },
      { "name": "analyzer", "inputs_from": ["fetcher"] }
    ]
  }
}
```

### Deployment Tools (3)

#### `deploy_agent`

Deploy an agent from an inline TOML manifest string. File paths are NOT accepted -- pass the TOML content directly.

| Parameter       | Type     | Required | Description                                             |
| --------------- | -------- | -------- | ------------------------------------------------------- |
| `manifest_toml` | `string` | Yes      | TOML manifest content as a string (must have `[agent]`) |

**Returns**: Registration result with `agent_name`, `status`.

```json
{
  "name": "deploy_agent",
  "arguments": {
    "manifest_toml": "[agent]\nmanifest_version = \"1.0\"\nname = \"my-agent\"\nmodule = \"my_module\"\nclass_name = \"MyAgent\"\n"
  }
}
```

#### `deploy_status`

Query the deployment status of an agent by name.

| Parameter | Type     | Required | Description             |
| --------- | -------- | -------- | ----------------------- |
| `name`    | `string` | Yes      | The agent name to query |

**Returns**: Agent status record or null if not found.

#### `catalog_deregister`

Remove an agent from the catalog registry.

| Parameter | Type     | Required | Description                  |
| --------- | -------- | -------- | ---------------------------- |
| `name`    | `string` | Yes      | The agent name to deregister |

**Returns**: `{"removed": true}` or `{"removed": false}` if not found.

### Application Tools (2)

#### `app_register`

Register an application that uses one or more agents.

| Parameter                     | Type       | Required | Description                                            |
| ----------------------------- | ---------- | -------- | ------------------------------------------------------ |
| `name`                        | `string`   | Yes      | Application name                                       |
| `description`                 | `string`   | No       | Application description                                |
| `owner`                       | `string`   | No       | Application owner email or identifier                  |
| `org_unit`                    | `string`   | No       | Organizational unit                                    |
| `agents_requested`            | `string[]` | No       | List of agent names this application needs             |
| `budget_monthly_microdollars` | `integer`  | No       | Monthly budget cap in microdollars (1 USD = 1,000,000) |
| `justification`               | `string`   | No       | Justification for requesting these agents              |

**Returns**: Application registration record.

#### `app_status`

Query the status of a registered application by name.

| Parameter | Type     | Required | Description                   |
| --------- | -------- | -------- | ----------------------------- |
| `name`    | `string` | Yes      | The application name to query |

**Returns**: Application record or null if not found.

### Governance Tools (2)

#### `validate_composition`

Validate a composite agent pipeline for DAG cycles and optionally check schema compatibility.

| Parameter | Type       | Required | Description                                                                   |
| --------- | ---------- | -------- | ----------------------------------------------------------------------------- |
| `agents`  | `object[]` | Yes      | Agent descriptors with `name`, `inputs_from`, `output_schema`, `input_schema` |

**Returns**: Validation result with DAG validity and schema compatibility details.

#### `budget_status`

Query budget tracking status for a named scope (agent or application).

| Parameter             | Type      | Required | Description                                   |
| --------------------- | --------- | -------- | --------------------------------------------- |
| `scope`               | `string`  | Yes      | Budget scope name (agent or application name) |
| `budget_microdollars` | `integer` | No       | Total budget allocation in microdollars       |
| `spent_microdollars`  | `integer` | No       | Amount already spent in microdollars          |

**Returns**: Budget status with remaining budget, utilization percentage.

---

## Built-in Agents

The server pre-seeds these Kaizen built-in agents on startup:

| Name               | Class                 | Capabilities            |
| ------------------ | --------------------- | ----------------------- |
| `simple-qa`        | `SimpleQAAgent`       | qa                      |
| `react-agent`      | `ReActAgent`          | reasoning, tool_use     |
| `chain-of-thought` | `ChainOfThoughtAgent` | reasoning               |
| `planning-agent`   | `PlanningAgent`       | planning                |
| `rag-research`     | `RAGResearchAgent`    | research, rag           |
| `code-gen`         | `CodeGenAgent`        | code_generation         |
| `memory-agent`     | `MemoryAgent`         | memory                  |
| `vision-agent`     | `VisionAgent`         | vision, image_analysis  |
| `debate-agent`     | `DebateWorkflow`      | debate, coordination    |
| `consensus-agent`  | `ConsensusWorkflow`   | consensus, coordination |

Additional built-in agents may be registered depending on the server version. User-deployed agents are added alongside these built-in entries.

---

## MemoryRegistry

The server uses `MemoryRegistry` for in-memory agent and application storage.

**Bounded storage**: Maximum 10,000 agents and 10,000 applications. When capacity is reached, the oldest entry (LRU) is evicted.

**Name validation**: Agent and application names must match `^[a-zA-Z][a-zA-Z0-9_-]{0,127}$` to prevent injection.

**API**:

```python
from kaizen.mcp.catalog_server.registry import MemoryRegistry

registry = MemoryRegistry()

# Agent operations
registry.register({"name": "my-agent", "description": "...", ...})
agent = registry.get_agent("my-agent")  # Dict or None
agents = registry.search(query="market", capabilities=["analysis"])
all_agents = registry.list_agents()
removed = registry.deregister("my-agent")  # bool

# Application operations
registry.register_app({"name": "my-app", "owner": "team@example.com", ...})
app = registry.get_app("my-app")  # Dict or None
all_apps = registry.list_apps()
```

---

## Error Handling

The server distinguishes between expected and unexpected errors:

- **Expected errors** (ValueError, KeyError, TypeError): The error message is returned to the client in an MCP error content block with `isError: true`. These are safe to display.
- **Unexpected errors**: Logged via `logger.exception()` and the client receives a generic `"Internal tool error. Check server logs for details."` message. Internal details are NOT leaked.

---

## Critical Rules

- **ALWAYS** initialize the server before sending `tools/list` or `tools/call` -- the server rejects requests with `_INVALID_REQUEST` otherwise
- **NEVER** pass file paths to `deploy_agent` -- the tool accepts only inline TOML content
- The in-memory registry does NOT persist across restarts -- use `FileRegistry` (from `kaizen.deploy.registry`) for durable storage
- Agent names must start with a letter and contain only alphanumeric characters, hyphens, and underscores (max 128 chars)
- The server logs to stderr at WARNING level by default -- increase to DEBUG for troubleshooting

## References

- **Source**: `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/server.py`
- **Source**: `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/registry.py`
- **Source**: `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/__main__.py`
- **Related**: [`kaizen-agent-manifest`](kaizen-agent-manifest.md) -- Manifest format and deploy API
- **Related**: [`kaizen-composition`](kaizen-composition.md) -- DAG validation used by `catalog_deps` and `validate_composition`
