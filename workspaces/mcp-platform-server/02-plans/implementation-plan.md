# MCP Platform Server: Implementation Plan

## Phase Overview

```
D-server (skeleton)
    |
    +---> D1 (DataFlow tools)  ---|
    +---> D2 (Nexus tools)     ---|---> D4 (platform_map)
    +---> D3 (Kaizen tools)    ---|        |
    |                                      v
    +---> D5 (Validation tools)      D6 (Test generation)
    |
    +---> Testing (full integration + E2E)
```

## Session 1: D-server -- Server Skeleton (TSG-500)

**Goal**: FastMCP server running with contributor plugin system, consolidated MCP codebase.

### Analysis Corrections (from 01-analysis)

- **GAP-1 (BLOCKING)**: `src/kailash/mcp/server.py` already contains the Rust-backed `McpApplication`. Must rename to `application.py` FIRST, then create platform server at `server.py`.
- **GAP-2**: Introspection tools cannot query runtime registries (server runs in a separate process). Must use AST-based source scanning for Tier 1 tools.
- **GAP-3**: Coordinate with nexus-transport-refactor workspace on Nexus MCP file deletions.
- **RT-1a (HIGH)**: Contributor loop must catch `Exception`, not just `ImportError`.
- **RT-6a (MEDIUM)**: All logging must go to stderr (stdio transport uses stdout).

### Steps

1. **RESOLVE MODULE CONFLICT (must be first)**:
   - Rename `src/kailash/mcp/server.py` -> `src/kailash/mcp/application.py`
   - Rename `src/kailash/mcp/server.pyi` -> `src/kailash/mcp/application.pyi`
   - Update `src/kailash/mcp/__init__.py`: change `from kailash.mcp.server import McpApplication` to `from kailash.mcp.application import McpApplication`
   - Verify all imports of `kailash.mcp.server` across codebase and update

2. Create module structure:

   ```
   src/kailash/mcp/application.py      # RENAMED from server.py
   src/kailash/mcp/application.pyi     # RENAMED from server.pyi
   src/kailash/mcp/platform_server.py  # NEW: FastMCP-based platform server
   src/kailash/mcp/contrib/__init__.py # NEW: contributor protocol
   src/kailash/mcp/contrib/core.py     # NEW: core SDK tools
   src/kailash/mcp/contrib/platform.py # NEW: platform_map tool
   ```

3. Implement `platform_server.py` (NOT `server.py` to avoid confusion with existing module):
   - `create_server(project_root: Path) -> FastMCP` function
   - `FRAMEWORK_CONTRIBUTORS` list with importlib probing loop
   - **Catch `Exception` in contributor loop, not just `ImportError`** (RT-1a fix)
   - CLI entry point with `--project-root`, `--transport`, `--port` args
   - `project_root` discovery: CLI arg -> env var -> cwd
   - Security tier enforcement: check `KAILASH_MCP_ENABLE_EXECUTION` env var before registering Tier 4 tools
   - **Redirect logging to stderr** (RT-6a fix)
   - **Log startup duration** (RT-6c)

4. Define contributor interface in `contrib/__init__.py`:

   ```python
   def register_tools(server: FastMCP, project_root: Path, namespace: str) -> None:
       """Register framework tools with the MCP server.

       All tool names must start with '{namespace}.' prefix.
       """
       ...
   ```

   Note: Added `namespace` parameter per RT-4a recommendation.

5. Consolidate existing MCP code:
   - **Delete**: `packages/kailash-nexus/src/nexus/mcp/server.py`
   - **Delete**: `packages/kailash-nexus/src/nexus/mcp/transport.py`
   - **Delete**: `packages/kailash-nexus/src/nexus/mcp_websocket_server.py`
   - **Refactor**: `src/kailash/channels/mcp_channel.py` to wrap FastMCP
   - **Keep but flag**: `src/kailash/api/mcp_integration.py` (MCPToolNode still useful)
   - **Migrate or delete**: existing tests referencing deleted classes

6. Add `kailash-mcp` to `pyproject.toml` console_scripts:

   ```toml
   [project.scripts]
   kailash-mcp = "kailash.mcp.platform_server:main"
   ```

7. Verify dependency: `mcp[cli]>=1.23.0,<2.0` already in base dependencies (not optional).

8. Write unit tests:
   - Contributor discovery with mocked imports
   - Graceful `ImportError` AND `Exception` handling (RT-1a)
   - Security tier enforcement (env var present/absent)
   - Namespace validation for tool names (RT-4a)

### Deliverable

`kailash-mcp --project-root .` starts, accepts JSON-RPC 2.0 on stdio, returns empty tool list (no contributors loaded yet beyond core/platform stubs).

---

## Sessions 2-4: D1/D2/D3 -- Framework Tools (Parallel)

These three sessions are independent and can run in parallel.

### Session 2: D1 -- DataFlow Contributor (TSG-501)

**Goal**: DataFlow introspection tools available via MCP.

**Analysis correction (GAP-2)**: Introspection uses AST-based source scanning, NOT runtime DataFlow registry. The MCP server runs in a separate process without a DataFlow instance.

1. Implement `src/kailash/mcp/contrib/dataflow.py`
2. Register 3 introspection tools:
   - `dataflow.list_models()` -- **AST scans** `project_root` for `@db.model` decorated classes
   - `dataflow.describe_model(model_name)` -- returns field schema, generated nodes (deterministic: `Create{Name}`, `Read{Name}`, `Update{Name}`, `Delete{Name}`, `List{Name}`), relationships
   - `dataflow.query_schema()` -- reads `pyproject.toml` for DataFlow version; checks for database URL in env
3. Register MCP resources:
   - `kailash://models` (list)
   - `kailash://models/{model_name}` (describe)
4. Error handling: unknown model_name returns `{error: "Model not found", available: [...]}` not exception
5. Unit tests with mocked DataFlow registry
6. Integration test with real DataFlow model in test fixture

### Session 3: D2 -- Nexus Contributor (TSG-502)

**Goal**: Nexus introspection and scaffold tools available via MCP.

**Analysis correction (GAP-2)**: Introspection uses AST-based scanning for handler registrations, NOT runtime Nexus app config.

1. Implement `src/kailash/mcp/contrib/nexus.py`
2. Register 3 introspection tools (Tier 1):
   - `nexus.list_handlers()` -- **AST scans** for handler registration patterns in project source
   - `nexus.list_channels()` -- reads Nexus config from project settings
   - `nexus.list_events()` -- scans for event declarations with subscribers
3. Register 1 scaffold tool (Tier 2):
   - `nexus.scaffold_handler(name, method, path)` -- returns generated code as string
4. Register MCP resources:
   - `kailash://handlers`
   - `kailash://handlers/{handler_name}`
5. Handler discovery: runtime from NexusApp config; fallback to static source scan
6. Scaffold validation: reject invalid HTTP methods, paths must start with `/`
7. Unit tests with mocked Nexus config
8. Integration test with real registered handler

### Session 4: D3 -- Kaizen Contributor (TSG-503)

**Goal**: Kaizen agent introspection and scaffold tools available via MCP.

**Analysis correction (GAP-4)**: No central agent registry exists for project-level discovery. Must implement AST-based scanner for BaseAgent subclasses.

1. Implement `src/kailash/mcp/contrib/kaizen.py`
2. Register 2 introspection tools (Tier 1):
   - `kaizen.list_agents()` -- **AST scans** `project_root` for BaseAgent subclasses and Delegate instantiations
   - `kaizen.describe_agent(agent_name)` -- extracts Signature inner classes, tool registrations, strategy from AST
3. Register 1 scaffold tool (Tier 2):
   - `kaizen.scaffold_agent(name, purpose, tools?)` -- Delegate (default) or BaseAgent pattern
   - Scaffold includes 5 guardrails: confidence score, cost budget, human approval gate, baseline comparison, audit trail
4. Register MCP resources:
   - `kailash://agents`
   - `kailash://agents/{agent_name}`
5. Agent discovery: scan `agents/` directory + Kaizen internal registry
6. Unit tests with mocked agent registry
7. Integration test with real agent

---

## Session 5: D4 -- platform_map() (TSG-504)

**Goal**: Single-call cross-framework project graph.

**Depends on**: D1, D2, D3 (uses their discovery functions, not reimplements them).

1. Implement `src/kailash/mcp/contrib/platform.py`
2. `platform_map()` aggregates D1/D2/D3 outputs
3. Cross-framework connection detection via `ast.parse`:
   - `model_to_handler`: scan handler source for generated node names (`CreateUser`, `ReadUser`)
   - `handler_to_channel`: read Nexus channel registry
   - `agent_to_tool`: read agent tool registrations
   - `model_to_agent`: check agent tools for DataFlow references
4. Expose as both tool (with optional filter param) and resource (`kailash://platform-map`)
5. Resource subscription for change notifications (watchfiles/watchdog if available)
6. Framework version detection via `importlib.metadata.version()`
7. Project name from `pyproject.toml` `[project].name` field
8. Performance target: under 2 seconds for 20 models, 20 handlers, 5 agents
9. Unit tests with mocked registries verifying `connections` assembly
10. E2E test with fixture project verifying full graph

---

## Session 6: D5 -- Validation Tools (TSG-505)

**Goal**: Tier 3 validation with subprocess isolation.

1. Extend dataflow, nexus, and core contributors with validation tools
2. `dataflow.validate_model(model_name)`: field type validity, primary key, unique constraints, FK targets
3. `nexus.validate_handler(handler_name)`: async signature, valid method, path format, route conflicts
4. `core.validate_workflow(workflow_json)`: node types exist, DAG acyclic, required params provided
5. Subprocess isolation: each call spawns a fresh process (ProcessPoolExecutor or subprocess.run)
6. 10-second timeout; timeout returns `{valid: false, errors: ["Validation timed out"]}`
7. Error translation: catch ImportError/SyntaxError/AttributeError -> human-readable messages
8. Default: enabled (set `KAILASH_MCP_ENABLE_VALIDATION=false` to disable)
9. Unit tests with mocked subprocess
10. Integration tests with intentionally broken model/handler/workflow

---

## Session 7: D6 -- Test Generation Tools (TSG-506)

**Goal**: Tier 2 test scaffold generation.

1. Extend dataflow, nexus, kaizen contributors with test generation tools
2. Add `core.generate_test_data(model_name, count)` to core contributor
3. DataFlow test scaffold: CRUD round-trip, validation, unique constraints
4. Nexus test scaffold: happy path, input validation, error response
5. Kaizen test scaffold: mock LLM response, tool call verification
6. `tier` parameter: `"unit"`, `"integration"`, `"all"` (default)
7. Test data generation: type-aware (str -> "test_value", int -> 42, email -> "test@example.com")
8. Classification-aware: PII fields get masked test data
9. Template-based generation (string templates, no Jinja2 dependency)
10. Verify generated code is valid Python via `ast.parse`

---

## Session 8: Testing -- Full Integration & E2E (TSG-507)

**Goal**: Comprehensive test coverage using Kaizen McpClient as test harness.

1. Create test fixture project:

   ```
   tests/fixtures/mcp_test_project/
       models/user.py       # DataFlow User model
       handlers/create_user.py  # Nexus handler using CreateUser node
       agents/support.py    # Kaizen SupportAgent
   ```

2. Integration tests (all use McpClient):
   - Start server as subprocess; call `tools/list`; verify expected tool names
   - `dataflow.list_models()` returns User
   - `nexus.list_handlers()` returns create_user
   - `kaizen.list_agents()` returns SupportAgent
   - `platform.platform_map()` includes `model_to_handler` connection
   - Scaffold tools return parseable Python
   - Security: Tier 4 tools absent without env var

3. Graceful degradation test:
   - Start server with mock ImportError for dataflow, nexus, kaizen
   - Verify only `core.*` and `platform.*` tools registered

4. E2E connection detection test:
   - Fixture handler source references `CreateUser` generated node name
   - Verify `platform_map()` detects `model_to_handler` connection

5. Performance: full test suite runs in under 30 seconds
6. All tests marked `@pytest.mark.integration` and excluded from unit run
7. Tests pass in CI with `kailash[mcp]` installed

---

## Dependency Graph

```
TSG-500 (skeleton)
  |
  +---> TSG-501 (dataflow) ------+
  +---> TSG-502 (nexus) ---------+--> TSG-504 (platform_map) --+
  +---> TSG-503 (kaizen) --------+                              |
  +---> TSG-505 (validation)                                    |
  +---> TSG-506 (test gen, depends on 501+502+503)             |
  |                                                             |
  +---> TSG-507 (testing, depends on all) <---------------------+
```

## Estimated Effort

| Todo                    | Effort                                   | Parallel?           |
| ----------------------- | ---------------------------------------- | ------------------- |
| TSG-500 Server skeleton | 2 sessions                               | No (first)          |
| TSG-501 DataFlow tools  | 1 session                                | Yes (with 502, 503) |
| TSG-502 Nexus tools     | 1 session                                | Yes (with 501, 503) |
| TSG-503 Kaizen tools    | 1 session                                | Yes (with 501, 502) |
| TSG-504 platform_map    | 1 session                                | No (needs 501-503)  |
| TSG-505 Validation      | 1 session                                | Yes (with 501-504)  |
| TSG-506 Test generation | 1 session                                | Yes (after 501-503) |
| TSG-507 Full testing    | 1 session                                | No (last)           |
| **Total**               | **~5-6 sessions** (with parallelization) |                     |
