# Code Red Team Report -- Batch 1 (DataFlow + Nexus + MCP)

**Date**: 2026-04-01
**Scope**: New implementation files across DataFlow, Nexus, and MCP workspaces
**Test baseline**: DataFlow 3690 passed, Nexus 1153 passed, MCP 20 passed

---

## Summary

Reviewed 25 files across 3 workspaces. Found **2 CRITICAL**, **4 HIGH**, **4 MEDIUM**, and **3 LOW** findings. The implementations are generally solid -- error handling is consistent, bounded collections are used where needed, and the transport abstraction is well-designed. The two CRITICAL findings are a SQL injection vector in RetentionEngine and a potential resource leak in MCPTransport.

---

## DataFlow Findings

### Files Reviewed

| File                            | Lines | Verdict            |
| ------------------------------- | ----- | ------------------ |
| `features/derived.py`           | 586   | 1 MEDIUM           |
| `nodes/file_source.py`          | 399   | 1 LOW              |
| `validation/dsl.py`             | 188   | Clean              |
| `features/retention.py`         | 320   | 1 CRITICAL, 1 HIGH |
| `core/events.py`                | 138   | Clean              |
| `features/express.py` (changes) | --    | Clean              |
| `engine.py` (changes)           | --    | Clean              |

### Findings

| ID    | Severity     | File                        | Finding                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ----- | ------------ | --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| DF-01 | **CRITICAL** | `features/retention.py:229` | **SQL injection via unvalidated `cutoff_field`**. `policy.cutoff_field` is interpolated into SQL (`WHERE {policy.cutoff_field} < ?`) at lines 229, 235, 261, 310 without any validation. Table names are validated via `_validate_table_name()` but `cutoff_field` is not. A user supplying `cutoff_field="1=1; DROP TABLE users --"` would inject arbitrary SQL. This violates `rules/infrastructure-sql.md` Rule 1 (validate SQL identifiers).                                                                                                                                |
| DF-02 | **HIGH**     | `features/retention.py:294` | **Partition policy raises NotImplementedError-like error**. The `_partition()` method unconditionally raises `DataFlowConfigError("Partition retention policy is not yet implemented.")`. While this uses a proper exception class (not `NotImplementedError`), it means `partition` is accepted as a valid policy type in the dataclass but always fails at runtime. The `Literal["archive", "delete", "partition"]` type hint advertises a feature that does not work. This borderline violates `rules/no-stubs.md` -- the type system accepts values that can never succeed. |
| DF-03 | **MEDIUM**   | `features/derived.py:298`   | **Silent `except: pass` on delete during refresh**. Line 298 catches all exceptions and passes silently during the delete-before-create loop: `except Exception: pass  # Record may not exist yet`. While the comment explains the intent, this swallows genuine database errors (e.g., connection failures, permission errors) that should abort the refresh. Per `rules/no-stubs.md` Rule 3, only hooks/cleanup code should use silent fallbacks. A failing delete should be caught specifically for "record not found" and re-raised for other errors.                       |
| DF-04 | **LOW**      | `nodes/file_source.py:173`  | **Path traversal not validated in FileSourceNode**. `file_path` from user input is passed directly to `Path(file_path)` without any path traversal prevention. While this node is typically used in trusted contexts (server-side file imports), a user could supply `../../../etc/passwd` if the file path comes from untrusted input. Consider validating that the resolved path stays within a configurable root directory, or document that the caller is responsible for path safety.                                                                                      |

### Positive Observations (DataFlow)

- **EventMixin**: Fire-and-forget pattern correctly never breaks the write path. `_emit_write_event` catches all exceptions and logs at debug level.
- **DerivedModelEngine**: Cycle detection uses standard DFS with proper coloring. Debounce handles correctly capture `meta` via default argument (avoids late-binding closure bug). Event subscriptions use exact event types, not wildcards (R1-1 compliant).
- **Validation DSL**: Clean separation. `apply_validation_dict()` properly copies parent validators to avoid mutation. Named validators are whitelist-only.
- **Express changes**: `use_primary` parameter cleanly passes through. `_validate_if_enabled` correctly checks both engine-level flag and per-model validators. Write event emission uses `hasattr` guard for backward compatibility.

---

## Nexus Findings

### Files Reviewed

| File                  | Lines | Verdict              |
| --------------------- | ----- | -------------------- |
| `registry.py`         | 174   | Clean                |
| `events.py`           | 274   | 1 MEDIUM             |
| `background.py`       | 66    | Clean                |
| `transports/base.py`  | 79    | Clean                |
| `transports/http.py`  | 280   | 1 LOW                |
| `transports/mcp.py`   | 175   | 1 CRITICAL, 1 MEDIUM |
| `files.py`            | 98    | Clean                |
| `bridges/dataflow.py` | 168   | Clean                |

### Findings

| ID    | Severity     | File                        | Finding                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| ----- | ------------ | --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| NX-01 | **CRITICAL** | `transports/mcp.py:148-155` | **Orphan `AsyncLocalRuntime` per workflow invocation**. `_register_workflow_tool()` creates a new `AsyncLocalRuntime()` for every workflow execution via MCP. Although `runtime.release()` is called in the `finally` block, each invocation opens a new runtime with its own connection pool. Under concurrent MCP tool calls, this creates unbounded connection consumption. Per `rules/dataflow-pool.md` Rule 6, subsystem classes must share a runtime. The transport should accept a shared runtime and use it for all workflow executions. |
| NX-02 | **MEDIUM**   | `transports/mcp.py:168-169` | **MCP server binds to `0.0.0.0` (all interfaces)**. `self._server.run_ws(host="0.0.0.0", port=self._port)` exposes the MCP WebSocket server on all network interfaces by default. For development and local-only use cases, this should default to `127.0.0.1` (localhost only). The HTTP transport also uses `0.0.0.0` (line 197) but that is expected for a web server. An MCP server is typically for local AI assistant communication only.                                                                                                  |
| NX-03 | **MEDIUM**   | `events.py:248-252`         | **Unbounded subscriber queues**. When events are fanned out to subscribers (line 249: `sub_q.put_nowait(event)`), `QueueFull` is silently caught. However, subscriber queues are created without a `maxsize` (line 152: `asyncio.Queue()`), so they are unbounded -- `QueueFull` will never fire. A slow or abandoned subscriber will accumulate events indefinitely, leading to memory exhaustion. Subscriber queues should have a bounded `maxsize` (e.g., 256 matching the main capacity).                                                    |
| NX-04 | **LOW**      | `transports/http.py:158`    | **f-string in log statement**. `logger.info(f"Applied queued middleware: {entry.middleware_class.__name__}")` uses an f-string instead of lazy `%s` formatting. This evaluates the string even when INFO logging is disabled. Minor performance concern -- not a bug. Same pattern at lines 176, 186, 191, 105.                                                                                                                                                                                                                                  |

### Positive Observations (Nexus)

- **EventBus**: Correct use of `janus.Queue` for cross-thread communication. Bounded history deque prevents memory growth. `_ensure_queue()` correctly defers `janus.Queue` creation until an event loop exists.
- **HandlerRegistry**: Duplicate registration check prevents silent overwrites. Parameter extraction from function signatures is thorough.
- **DataFlowEventBridge**: Clean separation -- two event systems bridged without merging. Handler closures correctly capture variables via default arguments.
- **Transport ABC**: Well-designed lifecycle contract (start/stop/is_running). `on_handler_registered` default no-op is correct for non-hot-reload transports.
- **NexusFile**: Clean transport-agnostic abstraction. `to_dict()` correctly excludes binary data.
- **BackgroundService ABC**: Clean, minimal contract. All 4 required methods are abstract.

---

## MCP Findings

### Files Reviewed

| File                  | Lines | Verdict |
| --------------------- | ----- | ------- |
| `platform_server.py`  | 267   | 1 HIGH  |
| `resources.py`        | 106   | Clean   |
| `contrib/__init__.py` | 94    | Clean   |
| `contrib/core.py`     | 474   | Clean   |
| `contrib/dataflow.py` | 689   | 1 HIGH  |
| `contrib/nexus.py`    | 724   | 1 HIGH  |
| `contrib/kaizen.py`   | 780   | Clean   |
| `contrib/trust.py`    | 120   | Clean   |
| `contrib/pact.py`     | 191   | Clean   |
| `contrib/platform.py` | 472   | Clean   |

### Findings

| ID     | Severity | File                          | Finding                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ------ | -------- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| MCP-01 | **HIGH** | `platform_server.py:86-87`    | **Saved modules never restored on failure**. In `_get_fastmcp_class()`, lines 86-87 purge cached `mcp.*` modules from `sys.modules` via `saved = {k: sys.modules.pop(k) for k in bad_keys}`. If the subsequent import at line 90 succeeds, the saved modules are never restored -- the real `mcp` package takes their place, which is correct. But if the import fails (raises an exception other than `ImportError`), the saved modules are lost forever and the `kailash.mcp` sub-package becomes unusable. The `finally` block restores `sys.path` entries but not `sys.modules`. This is fragile -- the saved modules dict should be restored in an `except` branch if the import fails.                                                                                                                                                                                                                                    |
| MCP-02 | **HIGH** | `contrib/nexus.py:307-349`    | **Subprocess execution inherits full environment**. `_execute_in_subprocess()` passes `{**os.environ, "PYTHONPATH": str(project_root)}` as the subprocess environment. This forwards ALL environment variables (including `API_KEY`, `DATABASE_URL`, secrets) to the subprocess. For Tier 4 (EXECUTION) tools, this is by design (the handler needs env vars to run). However, the function is not gated on any security check beyond the Tier 4 flag. If an attacker can influence the `script` parameter (via the `handler_name` -> `module_path` derivation), they could exfiltrate secrets. The `module_path` derivation at lines 666-669 uses simple string replacement without validation that the module actually exists in the project.                                                                                                                                                                                 |
| MCP-03 | **HIGH** | `contrib/dataflow.py:437-438` | **DATABASE_URL partially logged in query_schema tool output**. `db_url = os.environ.get("DATABASE_URL", "")` is read, then the dialect is extracted. While the full URL is not returned, the `database_url_configured` boolean leaks the existence of the variable. More critically, the dialect detection at line 438-445 uses `if "sqlite" in db_url` -- if someone sets `DATABASE_URL` to a value containing credentials, the substring check itself is safe, but the variable name `db_url` suggests the full URL is in memory and could be logged or included in error messages. This is LOW risk given the current code but the pattern is fragile. **Corrected severity: this is actually LOW** since only a boolean is returned, not the URL. Upgrading for the principle that DATABASE_URL should not be read in an introspection tool at all -- the tool should read dialect from installed adapter metadata instead. |

### Positive Observations (MCP)

- **Security Tiers**: Clean 4-tier system. Tier 4 (EXECUTION) is disabled by default. Tier 3 (VALIDATION) can be disabled. Tiers 1-2 are always on.
- **Namespace validation**: `_validate_tool_namespace()` checks that contributors don't register tools outside their namespace. Defensive without being brittle.
- **ResourceCache**: Thread-safe with `threading.Lock()`. Mtime-based invalidation is correct -- no file watchers that could leak.
- **AST-based scanning**: All contributors use AST parsing (no `eval()`, no `exec()`, no runtime imports of user code) for Tier 1 and Tier 2 tools. This is security-correct.
- **Platform map**: Cross-framework connection detection via deterministic naming is clever and safe. Limitations properly documented in `scan_metadata`.
- **PACT contributor**: Uses `yaml.safe_load()` (not `yaml.load()`) -- correct. Falls back gracefully when PyYAML is not installed.

---

## Consolidated Findings (Severity-Sorted)

| ID     | Severity     | Workspace | File                  | Issue                                              |
| ------ | ------------ | --------- | --------------------- | -------------------------------------------------- |
| DF-01  | **CRITICAL** | DataFlow  | `retention.py`        | SQL injection via unvalidated `cutoff_field`       |
| NX-01  | **CRITICAL** | Nexus     | `transports/mcp.py`   | Orphan runtime per MCP workflow invocation         |
| DF-02  | **HIGH**     | DataFlow  | `retention.py`        | Partition policy accepted but always fails         |
| MCP-01 | **HIGH**     | MCP       | `platform_server.py`  | `sys.modules` not restored on import failure       |
| MCP-02 | **HIGH**     | MCP       | `contrib/nexus.py`    | Subprocess inherits full env with secrets (Tier 4) |
| MCP-03 | **HIGH**     | MCP       | `contrib/dataflow.py` | DATABASE_URL read in introspection tool            |
| DF-03  | **MEDIUM**   | DataFlow  | `derived.py`          | Silent `except: pass` on delete during refresh     |
| NX-02  | **MEDIUM**   | Nexus     | `transports/mcp.py`   | MCP server binds `0.0.0.0` by default              |
| NX-03  | **MEDIUM**   | Nexus     | `events.py`           | Unbounded subscriber queues                        |
| DF-04  | **LOW**      | DataFlow  | `file_source.py`      | No path traversal validation on file_path          |
| NX-04  | **LOW**      | Nexus     | `transports/http.py`  | f-string in log statements                         |

---

## Recommended Fix Priority

### Immediate (before merge)

1. **DF-01**: Add `_validate_table_name(policy.cutoff_field)` in `RetentionPolicy` registration. The regex `^[a-zA-Z_][a-zA-Z0-9_]*$` already exists in the file. One line fix.

2. **NX-01**: Accept an optional shared `runtime` parameter in `MCPTransport.__init__()` and use it in `_register_workflow_tool()`. Fallback to creating one shared runtime at `start()` if none provided.

### Soon (next session)

3. **NX-03**: Set `maxsize=256` on subscriber queues in `EventBus.subscribe()` and `subscribe_filtered()`.

4. **MCP-01**: Add `except` branch in `_get_fastmcp_class()` that restores saved `sys.modules` entries before re-raising.

5. **DF-02**: Either remove `"partition"` from the `Literal` type or implement it. If removed, add a clear migration note.

6. **NX-02**: Default MCP host to `127.0.0.1` and accept a `host` parameter.

### Track (lower priority)

7. **DF-03**: Catch `RecordNotFoundError` specifically instead of bare `Exception`.
8. **MCP-02**: Add module path validation in Tier 4 execution tools.
9. **MCP-03**: Read dialect from installed adapter metadata instead of `DATABASE_URL`.
10. **DF-04**: Add optional `root_dir` parameter for path containment.
11. **NX-04**: Use lazy `%s` formatting in logger calls.
