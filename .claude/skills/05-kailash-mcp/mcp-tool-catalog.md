---
name: mcp-tool-catalog
description: "Complete catalog of kailash-mcp platform tools by framework and security tier. Use when asking 'mcp tools list', 'available mcp tools', 'tool catalog', 'what tools does kailash-mcp have', or 'mcp tool reference'."
---

# MCP Platform Tool Catalog

Complete reference of all tools registered by the kailash-mcp platform server, organized by framework contributor and security tier.

> **Skill Metadata**
> Category: `mcp`
> Priority: `MEDIUM`
> SDK Version: `0.9.25+`
> Related Skills: [`mcp-platform-overview`](mcp-platform-overview.md), [`mcp-security-tiers`](mcp-security-tiers.md)
> Related Subagents: `mcp-specialist` (tool implementation, custom tools)

## Tool Summary

| Namespace  | Tier 1 (Introspect) | Tier 2 (Scaffold) | Tier 3 (Validate) | Tier 4 (Execute) |  Total |
| ---------- | ------------------: | ----------------: | ----------------: | ---------------: | -----: |
| `core`     |                   4 |                 0 |                 1 |                0 |      5 |
| `platform` |                   2 |                 0 |                 0 |                0 |      2 |
| `dataflow` |                   3 |                 2 |                 1 |                0 |      6 |
| `nexus`    |                   2 |                 2 |                 1 |                1 |      6 |
| `kaizen`   |                   2 |                 2 |                 0 |                1 |      5 |
| `trust`    |                   1 |                 0 |                 0 |                0 |      1 |
| `pact`     |                   1 |                 0 |                 0 |                0 |      1 |
| **Total**  |              **15** |             **6** |             **3** |            **2** | **26** |

## Core SDK (`core.*`)

Always available -- no sub-package dependency.

### `core.list_node_types` -- Tier 1

List all available Kailash Core SDK node types.

- **Input**: none
- **Output**: `{ node_types: [{name, category, description, parameters_count}], total, scan_metadata }`
- **Method**: AST scan of `kailash.nodes` package

### `core.list_node_categories` -- Tier 1

List node type categories with counts.

- **Input**: none
- **Output**: `{ categories: [{name, count}], total_categories, scan_metadata }`

### `core.describe_node` -- Tier 1

Detailed info for a single node type including parameters.

- **Input**: `node_type: str` (e.g., `"TransformNode"`)
- **Output**: `{ name, category, description, parameters: [{name, type, required, description}], file, scan_metadata }`

### `core.get_sdk_version` -- Tier 1

Kailash SDK version and installed framework information.

- **Input**: none
- **Output**: `{ versions: {kailash, kailash-dataflow, ...}, python_version, scan_metadata }`
- Returns `null` for packages not installed

### `core.validate_workflow` -- Tier 3

Validate a workflow JSON structure against known node types.

- **Input**: `workflow_json: str` (JSON string)
- **Output**: `{ valid: bool, errors: [], warnings: [], node_count, has_cycles, scan_metadata }`
- Checks: node types exist, no duplicate IDs, connections reference existing nodes, cycle detection
- **Requires**: `KAILASH_MCP_ENABLE_VALIDATION != "false"`

## Platform (`platform.*`)

Always available. Aggregates cross-framework data.

### `platform.platform_map` -- Tier 1

Full cross-framework project graph in a single call.

- **Input**: `filter: str = ""` (reserved for future use)
- **Output**: `{ project, frameworks, models, handlers, agents, channels, connections, trust, scan_metadata }`
- Detects model-to-handler, model-to-agent, and agent-to-tool connections via naming conventions

### `platform.project_info` -- Tier 1

Project metadata and framework versions.

- **Input**: none
- **Output**: `{ project: {name, root, python_version, kailash_version}, frameworks: {core: {installed, version}, ...}, scan_metadata }`

## DataFlow (`dataflow.*`)

Available when `kailash-dataflow` is installed.

### `dataflow.list_models` -- Tier 1

List all DataFlow models found in the project.

- **Input**: none
- **Output**: `{ models: [{name, fields_count, has_timestamps, table_name, file}], total, scan_metadata }`
- **Method**: AST scan for `@db.model` decorated classes

### `dataflow.describe_model` -- Tier 1

Describe a model with its fields and generated CRUD node names.

- **Input**: `model_name: str` (e.g., `"User"`)
- **Output**: `{ name, fields: [{name, type, primary_key, nullable, default}], generated_nodes: ["CreateUser", ...], file, scan_metadata }`

### `dataflow.query_schema` -- Tier 1

Project-level DataFlow metadata.

- **Input**: none
- **Output**: `{ database_url_configured: bool, dialect, models_count, dataflow_version, scan_metadata }`

### `dataflow.scaffold_model` -- Tier 2

Generate a DataFlow model definition from a field spec.

- **Input**: `name: str`, `fields: str` (comma-separated, e.g., `"name:str, price:float, active:bool"`)
- **Output**: `{ file_path, code, scan_metadata }`
- Generated code is syntax-validated before returning

### `dataflow.generate_tests` -- Tier 2

Generate pytest test scaffolds for a model.

- **Input**: `model_name: str`, `tier: str = "all"` (`"unit"`, `"integration"`, or `"all"`)
- **Output**: `{ test_code, test_path, imports, scan_metadata }`
- Integration tests include state persistence verification (write + read-back)

### `dataflow.validate_model` -- Tier 3

Validate a DataFlow model definition.

- **Input**: `model_name: str`
- **Output**: `{ valid: bool, errors: [], warnings: [], model_name, scan_metadata }`
- Checks: primary key, `id` field convention, timestamp fields
- **Requires**: `KAILASH_MCP_ENABLE_VALIDATION != "false"`

## Nexus (`nexus.*`)

Available when `kailash-nexus` is installed.

### `nexus.list_handlers` -- Tier 1

List all Nexus handlers in the project.

- **Input**: none
- **Output**: `{ handlers: [{name, method, path, file, line}], total, scan_metadata }`
- **Method**: AST scan for `@handler` decorators and `add_handler()` calls

### `nexus.list_channels` -- Tier 1

List configured Nexus channels.

- **Input**: none
- **Output**: `{ channels: [], total, scan_metadata }`
- Channel detection requires runtime configuration scanning

### `nexus.scaffold_handler` -- Tier 2

Generate a Nexus handler with test code.

- **Input**: `name: str`, `method: str`, `path: str`, `description: str = ""`
- **Output**: `{ file_path, code, tests_path, tests_code, scan_metadata }`

### `nexus.generate_tests` -- Tier 2

Generate pytest test scaffolds for a handler.

- **Input**: `handler_name: str`
- **Output**: `{ test_code, test_path, imports, scan_metadata }`

### `nexus.validate_handler` -- Tier 3

Validate a handler definition.

- **Input**: `handler_name: str`
- **Output**: `{ valid: bool, errors: [], warnings: [], handler_name, scan_metadata }`
- **Requires**: `KAILASH_MCP_ENABLE_VALIDATION != "false"`

### `nexus.test_handler` -- Tier 4

Execute a handler in an isolated subprocess.

- **Input**: `handler_name: str`, `input_data: str = "{}"` (JSON)
- **Output**: `{ result, status_code, duration_ms }` or `{ errors: [] }`
- **Requires**: `KAILASH_MCP_ENABLE_EXECUTION=true`
- Runs in subprocess with 30s timeout

## Kaizen (`kaizen.*`)

Available when `kailash-kaizen` is installed.

### `kaizen.list_agents` -- Tier 1

List all Kaizen agents in the project.

- **Input**: none
- **Output**: `{ agents: [{name, type, file, line, signature_fields, tools_count}], total, scan_metadata }`
- **Method**: AST scan for `BaseAgent` subclasses and `Delegate` instantiations

### `kaizen.describe_agent` -- Tier 1

Describe an agent with its signature fields and tools.

- **Input**: `agent_name: str`
- **Output**: `{ name, type, signature: {inputs, outputs}, tools, file, scan_metadata }`

### `kaizen.scaffold_agent` -- Tier 2

Generate a Kaizen agent definition.

- **Input**: `name: str`, `purpose: str`, `tools: str = ""`, `pattern: str = "delegate"` (`"delegate"` or `"baseagent"`)
- **Output**: `{ file_path, code, test_path, test_code, scan_metadata }`

### `kaizen.generate_tests` -- Tier 2

Generate pytest test scaffolds for an agent.

- **Input**: `agent_name: str`
- **Output**: `{ test_code, test_path, imports, scan_metadata }`
- Generates different scaffolds for `BaseAgent` vs `Delegate` patterns

### `kaizen.test_agent` -- Tier 4

Run an agent task in an isolated subprocess.

- **Input**: `agent_name: str`, `task: str`
- **Output**: `{ result, events: [] }` or `{ errors: [] }`
- **Requires**: `KAILASH_MCP_ENABLE_EXECUTION=true`
- Runs in subprocess with 60s timeout

## Trust (`trust.*`)

Part of core SDK (no sub-package dependency).

### `trust.trust_status` -- Tier 1

Current trust plane status from trust-plane directory.

- **Input**: none
- **Output**: Trust configuration, posture store status, budget information
- Reads JSON files from `trust-plane/` directory

## PACT (`pact.*`)

Available when `kailash-pact` is installed.

### `pact.org_tree` -- Tier 1

Organizational hierarchy from PACT org definition files.

- **Input**: none
- **Output**: Organization structure, D/T/R addressing, envelope definitions
- Reads from PACT org definition files (JSON or YAML)

## MCP Resources

The platform also exposes MCP resources for read-only data access:

| URI                      | Description                           |
| ------------------------ | ------------------------------------- |
| `kailash://models`       | All DataFlow models as JSON           |
| `kailash://handlers`     | All Nexus handlers as JSON            |
| `kailash://agents`       | All Kaizen agents as JSON             |
| `kailash://platform-map` | Full platform map as JSON             |
| `kailash://node-types`   | Available Core SDK node types as JSON |

Resources provide the same data as Tier 1 tools but through the MCP resource protocol, allowing clients to subscribe to updates.

## Quick Tips

- Start with `platform.platform_map` for a project overview
- Use `core.get_sdk_version` to check which frameworks are available
- Scaffold tools (`*.scaffold_*`) generate syntax-validated code
- Test generation tools (`*.generate_tests`) include both unit and integration tiers
- Tier 4 tools run in isolated subprocesses with timeouts -- safe for exploration

<!-- Trigger Keywords: mcp tools list, available mcp tools, tool catalog, what tools does kailash-mcp have, mcp tool reference, mcp tools, tool schema, tool inputs outputs -->
