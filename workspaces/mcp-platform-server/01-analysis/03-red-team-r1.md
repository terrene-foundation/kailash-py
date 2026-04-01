# Red Team Report: Round 1

## RT-1: Contributor Plugin System Robustness

### Attack Surface

A contributor module's `register_tools()` could:

1. Raise an exception other than `ImportError` (e.g., `TypeError`, `AttributeError`)
2. Block indefinitely (network call during registration)
3. Register tools with names that collide with other contributors
4. Import heavy dependencies that slow server startup

### Findings

**RT-1a: Non-ImportError exceptions crash the server**

The brief's contributor loop only catches `ImportError`:

```python
try:
    mod = importlib.import_module(module_path)
    mod.register_tools(server, project_root)
except ImportError:
    logger.info("Framework %s not installed, skipping", namespace)
```

If `register_tools()` raises `AttributeError` (module exists but function doesn't), `TypeError` (wrong signature), or `RuntimeError` (framework initialization failure), the server crashes.

**Fix**: Catch `Exception` with logging, not just `ImportError`:

```python
except ImportError:
    logger.info(...)
except Exception as exc:
    logger.error("Contributor %s failed to register: %s", namespace, exc)
```

**RT-1b: No timeout on contributor registration**

A buggy contributor calling a network endpoint during `register_tools()` blocks the entire server startup.

**Fix**: Wrap registration in `asyncio.wait_for()` with a 5-second timeout. Or document that `register_tools()` must be synchronous and non-blocking.

**RT-1c: Tool name collision**

Two contributors could register `list_models` without a namespace prefix. The brief specifies namespace-prefixed names (`dataflow.list_models`), but nothing enforces this.

**Fix**: The `contrib/__init__.py` should validate that all tools registered by a contributor start with `{namespace}.`. Or the server should check for duplicates after each contributor loads.

**Severity**: HIGH for RT-1a (crash), MEDIUM for RT-1b (startup hang), LOW for RT-1c (preventable by convention).

---

## RT-2: Graceful Degradation When Frameworks Not Installed

### Scenario

User has `kailash` installed but not `kailash-dataflow`. They run `kailash-mcp`.

### Findings

**RT-2a: Core and platform contributors must work without any sub-packages**

The `core` contributor imports `NodeRegistry` from `kailash.nodes.base`. This is in the base package. But if it tries to import DataFlow-specific nodes, it could fail.

**Fix**: `core` contributor must only use `kailash` base package imports. Framework-specific imports go in framework-specific contributors.

**RT-2b: `platform_map()` must handle missing frameworks gracefully**

If DataFlow is not installed, `platform_map()` should return:

```json
{
  "frameworks": {
    "dataflow": { "installed": false }
  },
  "models": []
}
```

Not raise `ImportError` or return an error.

**Fix**: `platform_map()` catches `ImportError` per framework and populates accordingly. The platform contributor must not import framework packages at module level.

**RT-2c: `tools/list` response must be stable regardless of installed packages**

An MCP client may cache tool lists. If `kailash-dataflow` is installed mid-session, the tool list changes. Claude Code would need to re-discover.

**Fix**: Document that tool list is determined at server start. Restart required to pick up new packages. This is standard MCP behavior.

**Severity**: MEDIUM for RT-2a/2b (user experience), LOW for RT-2c (documented limitation).

---

## RT-3: Security Tier Enforcement

### Findings

**RT-3a: Env var check happens at registration time, not call time**

The plan says Tier 4 tools are not registered without `KAILASH_MCP_ENABLE_EXECUTION=true`. This means:

- If the env var is set at startup, tools are registered for the session
- If the env var is unset at startup, tools cannot be enabled without restart

This is the correct behavior (defense in depth). A tool that exists cannot be called if it was never registered.

**RT-3b: No per-tool authorization for Tier 3**

Tier 3 tools default to enabled. A user who wants to disable specific Tier 3 tools (e.g., `core.validate_workflow`) has only the global toggle (`KAILASH_MCP_ENABLE_VALIDATION=false`). This disables ALL validation tools.

**Fix**: Consider per-tool disable list: `KAILASH_MCP_DISABLE_TOOLS=core.validate_workflow,nexus.validate_handler`. Low priority; the global toggle is sufficient for v1.

**RT-3c: Tier 4 Trust Plane integration requires trust directory existence**

If `KAILASH_MCP_ENABLE_EXECUTION=true` but no `trust-plane/` directory exists, Tier 4 tools should still work (Trust Plane is advisory, not mandatory).

**Fix**: Tier 4 tools check for Trust Plane availability. If not configured, skip trust check and proceed with a warning in the response.

**Severity**: LOW for all. Design is sound for v1.

---

## RT-4: Tool Name Conflicts Across Frameworks

### Scenario

Two frameworks expose tools with similar semantics. Examples:

- `dataflow.validate_model` vs `core.validate_workflow` — clear, different namespaces
- What if a custom contributor registers `dataflow.custom_tool`?

### Findings

**RT-4a: Namespace enforcement is purely conventional**

The contributor protocol defines `register_tools(server, project_root)` with no namespace parameter. A contributor could register any tool name.

**Fix**: Pass `namespace` to `register_tools()`:

```python
def register_tools(server: FastMCP, project_root: Path, namespace: str) -> None:
```

The function validates that all registered tools start with `f"{namespace}."`.

Or: the server wrapper validates after registration.

**RT-4b: FastMCP duplicate tool registration behavior**

If two contributors register a tool with the same name, what does FastMCP do? It likely overwrites silently.

**Fix**: Check for duplicates after each contributor loads. Log a warning if a tool name is already registered.

**Severity**: LOW. Namespace prefixing by convention is sufficient for built-in contributors. Third-party plugins would need enforcement.

---

## RT-5: Resource Subscription Lifecycle Management

### Findings

**RT-5a: Resource subscriptions leak if client disconnects ungracefully**

MCP resources with subscriptions (e.g., `kailash://platform-map`) maintain server-side state for each subscriber. If the client crashes without unsubscribing, the server accumulates stale subscriptions.

**Fix**: FastMCP handles transport-level disconnection detection. The server should clean up subscriptions on transport close. Verify that FastMCP does this by default.

**RT-5b: Resource change notifications could be chatty**

If source files change frequently (IDE auto-save), `platform_map` resource notifications fire on every save. This could flood the MCP client.

**Fix**: Debounce change notifications. Check mtime at most once per tool/resource call, not via file watcher. The TrustPlane pattern (check mtime on access) naturally debounces.

**Severity**: LOW. FastMCP likely handles cleanup. Debouncing is handled by the mtime-on-access pattern.

---

## RT-6: stdio vs SSE Transport Testing Strategy

### Findings

**RT-6a: stdio is the primary path but hardest to debug**

stdio transport means the server's stdout is the response channel. Any `print()` statement or library that writes to stdout corrupts the protocol.

**Fix**:

- Redirect all logging to stderr (`logging.StreamHandler(sys.stderr)`)
- Verify no `print()` calls exist in the server or contributors
- Set `sys.stdout` to a null device after FastMCP takes over (FastMCP may handle this)

**RT-6b: SSE transport testing requires HTTP client**

SSE tests need a different test approach than stdio. The Kaizen McpClient only supports stdio.

**Fix**: For SSE testing, use `httpx` or `aiohttp` to connect to the SSE endpoint. Or verify that FastMCP's test infrastructure provides SSE test utilities. Lower priority since Claude Code uses stdio.

**RT-6c: Server startup time matters for stdio**

The McpClient has a 15-second init timeout. The platform server must complete all contributor registration within this window.

**Fix**: Measure startup time in CI. With 7 contributors, each doing AST scanning, startup could approach the limit for large projects. Lazy contributor loading (scan on first tool call, not at startup) would help but adds latency to the first call.

**Recommendation**: Eager registration with a startup time budget. Log startup duration. Alert if approaching 10 seconds.

**Severity**: MEDIUM for RT-6a (silent data corruption), LOW for RT-6b/6c.

---

## Summary of Findings

| ID    | Finding                                         | Severity | Action                                 |
| ----- | ----------------------------------------------- | -------- | -------------------------------------- |
| RT-1a | Non-ImportError exceptions crash server         | HIGH     | Catch `Exception` in contributor loop  |
| RT-1b | No timeout on contributor registration          | MEDIUM   | Document sync+non-blocking requirement |
| RT-1c | Tool name collision possible                    | LOW      | Validate namespace prefix              |
| RT-2a | Core contributor must avoid sub-package imports | MEDIUM   | Review core contributor imports        |
| RT-2b | platform_map must handle missing frameworks     | MEDIUM   | Catch ImportError per framework        |
| RT-3c | Trust Plane advisory, not mandatory for Tier 4  | LOW      | Skip trust check if not configured     |
| RT-4a | Namespace enforcement is conventional           | LOW      | Pass namespace to register_tools       |
| RT-5b | Resource notifications could be chatty          | LOW      | Mtime-on-access pattern debounces      |
| RT-6a | stdout corruption in stdio transport            | MEDIUM   | Redirect all logging to stderr         |
| RT-6c | Server startup time budget                      | MEDIUM   | Measure and log startup duration       |
