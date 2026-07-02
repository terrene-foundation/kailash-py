# Gap Analysis: MCP Platform Server

## Critical Gaps

### GAP-1: Module Path Conflict (BLOCKING)

**Issue**: The brief specifies `src/kailash/mcp/server.py` for the platform server. This file already exists and contains the Rust-backed `McpApplication` class.

**Impact**: Cannot proceed with implementation as designed without resolving the naming conflict.

**Resolution options**:

1. Rename existing `server.py` to `application.py` and update `__init__.py` imports
2. Place platform server in a submodule: `src/kailash/mcp/platform/server.py`
3. Use a different filename: `src/kailash/mcp/platform_server.py`

**Recommendation**: Option 1. Rename `McpApplication` to `application.py`. The existing module's `__init__.py` already re-exports `McpApplication` by name, so updating the import path is a one-line change. The platform server takes the `server.py` name as the brief intended.

**Effort**: Minimal (file rename + import update), but must happen first in TSG-500.

### GAP-2: Static vs Runtime Introspection Strategy Not Defined

**Issue**: The brief assumes introspection tools can query framework registries. But the MCP server runs as a standalone process (`kailash-mcp`), not inside the project's application. Framework registries (DataFlow models, Nexus handlers, Kaizen agents) are populated at APPLICATION runtime, not at import time.

**Impact**: The platform server cannot simply call `DataFlow._models` because no DataFlow instance exists in the MCP server process.

**Resolution**: Two-tier introspection strategy:

- **Primary (Tier 1)**: AST-based source scanning of `project_root`. Scan for `@db.model` decorators, `BaseAgent` subclasses, handler registrations. No imports required.
- **Secondary (Tier 3/4)**: For validation and execution tools, import the project's code in a subprocess.

**Implication**: This fundamentally changes how Tier 1 introspection tools work. They become static analysis tools, not runtime registry queries. The architecture document's examples showing `db._models` access are not directly viable.

### GAP-3: nexus-transport-refactor Workspace Overlap

**Issue**: A `nexus-transport-refactor` workspace exists at `workspaces/nexus-transport-refactor/`. The MCP consolidation (deleting `nexus/mcp/server.py` and `nexus/mcp_websocket_server.py`) overlaps with that workspace's transport refactoring scope.

**Impact**: If both workspaces modify Nexus MCP code simultaneously, merge conflicts are guaranteed.

**Resolution**: Coordinate sequencing. Either:

- Complete mcp-platform-server's deletions first (TSG-500), then nexus-transport-refactor works on the remaining Nexus transport
- Or complete nexus-transport-refactor first, then mcp-platform-server only needs to add the platform server

**Recommendation**: mcp-platform-server TSG-500 deletes Nexus MCP files first. nexus-transport-refactor is informed of the deletion.

---

## Moderate Gaps

### GAP-4: Kaizen Has No Central Agent Registry for Source Scanning

**Issue**: Unlike DataFlow (which has `@db.model` decorator pattern) and Core SDK (which has `NodeRegistry`), Kaizen has no single registry for "all agents in this project." The existing registries are:

- `kaizen.trust.registry.AgentRegistry` — runtime trust registry
- `kaizen.deploy.registry.LocalRegistry` — file-based at `~/.kaizen/registry/`
- `introspect_agent(module, class_name)` — inspects a single agent

None of these discovers agents in a project directory by scanning.

**Resolution**: The Kaizen contributor needs an AST-based scanner that:

1. Scans `project_root` recursively for `.py` files
2. Parses each file's AST
3. Finds classes inheriting from `BaseAgent`
4. Extracts `Signature` inner classes, tool registrations, strategy

**Effort**: ~100 lines of AST scanning code in `contrib/kaizen.py`.

### GAP-5: Cross-Framework Connection Detection is Complex

**Issue**: `platform_map()` must detect connections like `model_to_handler` (a handler references `CreateUser` generated node). This requires:

1. Knowing the generated node names for each model (`Create{Name}`, `Read{Name}`, etc.)
2. Scanning handler source code for those names
3. Correlating across frameworks

**Resolution**: This works for the deterministic naming pattern (`Create{ModelName}`, `Read{ModelName}`, `Update{ModelName}`, `Delete{ModelName}`, `List{ModelName}`), but:

- Custom node names break detection
- Dynamic handler registration breaks detection
- Only works for DataFlow-generated names, not arbitrary workflow references

**Recommendation**: Document the detection limitations. Initial implementation covers the deterministic pattern. Future improvement: runtime correlation via execution traces.

### GAP-6: No `kailash[mcp]` Optional Extra

**Issue**: The brief says "Ships As: kailash[mcp] optional install." But `mcp[cli]` is already in the base `dependencies`, not in `optional-dependencies`. There is no `mcp` extra to install.

**Resolution**: This is actually simpler than the brief assumed. The platform server is available to all `kailash` users. No extra installation step needed. Update documentation to reflect this.

### GAP-7: Test Fixture Project Design

**Issue**: The testing strategy requires a fixture project at `tests/fixtures/mcp_test_project/` with a DataFlow model, Nexus handler, and Kaizen agent. This fixture must be importable by the MCP server for validation tools but must not pollute the main test suite.

**Resolution**: Create the fixture with a `pyproject.toml` that makes it a valid Python package. Use `sys.path` manipulation in tests or `PYTHONPATH` env var when starting the MCP server subprocess.

---

## Minor Gaps

### GAP-8: MCP Resource Subscription Lifecycle

**Issue**: MCP resources with subscriptions (`kailash://models`, `kailash://platform-map`) need change notification. The brief mentions this but doesn't detail how change detection works for in-process registries.

**Resolution**: Use the mtime-based approach from the TrustPlane reference model. Check source file mtimes on each resource access. If changed, rebuild the cached data and notify subscribers.

### GAP-9: Prompt Templates Need Content

**Issue**: The brief lists 3 MCP prompts (`new-model`, `new-handler`, `new-agent`) but doesn't specify their content. These need to combine documentation with live introspection.

**Resolution**: Defer prompts to TSG-506 (test generation) or a separate todo. They are lower priority than tools and resources.

### GAP-10: Entry Point Module Path

**Issue**: If we rename `server.py` -> `application.py` and create a new `server.py` for the platform server, the `kailash-mcp` entry point should point to:

```toml
kailash-mcp = "kailash.mcp.server:main"
```

But this conflicts with the existing `McpApplication` import expectations. Some code may do `from kailash.mcp.server import McpApplication`.

**Resolution**: Update `__init__.py` to import `McpApplication` from the new location. Since `__init__.py` re-exports it, external code using `from kailash.mcp import McpApplication` continues to work.
