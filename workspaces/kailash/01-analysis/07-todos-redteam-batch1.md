# Todos Red Team — Batch 1 (DataFlow, MCP, Nexus)

Date: 2026-04-01
Scope: 32 todos across 3 workspaces (9 DataFlow, 12 MCP, 11 Nexus NTR-prefixed)

---

## dataflow-enhancements

### TSG-000: Milestone Tracker

- **Spec completeness**: PASS
- **Issues**: None. Well-structured dependency graph, parallelization plan, and red team finding coverage table.
- **Missing**: Nothing. This is a tracking document, not an implementation spec.

### TSG-100: DerivedModelEngine -- scheduled and manual refresh modes

- **Spec completeness**: PASS
- **Issues**: None. File paths specified, code sketches provided, design decisions documented with rationale.
- **Acceptance criteria**: All testable. Decorator syntax, compute invocation, BulkUpsert pipeline, scheduler, status reporting, error tracking — each has a corresponding test.
- **Red team coverage**: R1-7 (memory limitation documented), R1-8 (effort confirmed), R1-9 (deferred to TSG-101 correctly), R1-6 (modular design). All addressed.
- **Test plan**: 8-10 unit + 3-4 integration. Adequate. Sync variant test included.
- **Missing**: Nothing material. The code sketch shows `...` ellipsis in method bodies, but these are sketches, not stubs — the acceptance criteria define the behavior.

### TSG-101: DerivedModel on_source_change mode

- **Spec completeness**: PASS
- **Issues**: None. Excellent specificity on the 8-subscription approach, debounce mechanism, and cycle detection algorithm.
- **Acceptance criteria**: All testable. Each criterion maps to a specific behavior with a test listed.
- **Red team coverage**: R1-1 (wildcard gap — 8 specific subscriptions), R1-2 (async dispatch), R1-9 (cycle detection with DFS), R2-01 (payload not data), R2-03 (sync variants). All addressed.
- **Test plan**: 7 unit + 3 integration. Adequate. Debounce coalescing test is critical and included.
- **Missing**: The debounce window (100ms) is mentioned in the description but not in an acceptance criterion checkbox. Should be an explicit AC: "Debounce window defaults to 100ms, configurable via `debounce_ms` parameter on `@db.derived_model()`."

### TSG-102: FileSourceNode

- **Spec completeness**: PASS
- **Issues**: None. Format auto-detection, lazy imports, fail-soft coercion, SyncExpress variant — all specified.
- **Acceptance criteria**: All testable. Each format has a test. Lazy import failure messages include install hints.
- **Red team coverage**: R1-6 (no engine.py changes), R2-03 (SyncExpress mirror). Addressed.
- **Test plan**: 8-10 unit + 2-3 integration. Adequate.
- **Missing**: Nothing material.

### TSG-103: Declarative ValidationRules

- **Spec completeness**: PASS
- **Issues**: One concern — the acceptance criteria state `validate_on_write` defaults to `True`, but R2 verification (Section "Existing tests that will break") notes this could break existing Express write tests. The todo itself acknowledges this: "existing test models have no `__validation__` defined, so no validation is attempted." This is correct — validation only fires when `__validation__` is defined. The reasoning is sound but the AC should make this explicit.
- **Acceptance criteria**: All testable. The equivalence test (dict vs decorator producing identical internal format) is particularly valuable.
- **Red team coverage**: R2-03 (SyncExpress), R2-06 (builder convergence), R1-6 (minimal engine.py). Addressed.
- **Test plan**: 6-8 unit + 2-3 integration. Adequate.
- **Missing**: Add explicit AC: "Existing models without `__validation__` dict are NOT validated even when `validate_on_write=True` — validation only activates when `__validation__` is present on the model class."

### TSG-104: Express Cache Wiring

- **Spec completeness**: PASS
- **Issues**: None. The most complex DataFlow todo and it handles the complexity well. The decision to skip `CacheInvalidator` for Express writes and use `clear_pattern()` directly is pragmatic and well-reasoned.
- **Acceptance criteria**: All testable. Cache hit/miss, TTL, model-scoped invalidation, stats, auto-detection — all have tests.
- **Red team coverage**: R1-3 (CacheInvalidator async refactor), R1-4 (dual-mode key generation), R2-02 (direct clear_pattern), R2-03 (SyncExpress), R1-6 (minimal engine.py). All addressed.
- **Test plan**: 8-10 unit + 3-4 integration. Adequate. Correctly notes existing cache tests will break and need migration.
- **Missing**: The `CacheBackendProtocol` location is ambiguous — code sketch mentions "in cache/invalidation.py or cache/protocols.py". Should be decided: recommend `cache/protocols.py` for clean separation. Not blocking, but an implementer would need to choose.

### TSG-105: ReadReplicaSupport

- **Spec completeness**: PASS
- **Issues**: One concern — the `ConnectionManager` refactor is mentioned as needed ("add an optional `url` parameter that overrides") but the exact change is not specified in the acceptance criteria. This is an internal refactoring detail, but it is the key technical challenge identified by both R1 and R2.
- **Acceptance criteria**: All testable. Dual adapter, use_primary, pool validation, health check — all specified.
- **Red team coverage**: R1-5 (Express-level routing), R2-04 (dual pool exhaustion — separate pool sizes + warning), R2-03 (SyncExpress), R1-6 (engine.py), dataflow-pool rules. All addressed.
- **Test plan**: 6-8 unit + 4-5 integration. Adequate. The "dual SQLite files" approach for integration testing is pragmatic.
- **Missing**: Add explicit AC for the `ConnectionManager` refactor: "ConnectionManager constructor accepts optional `url_override: str` and `pool_size_override: int` parameters. When provided, these override the values from the DataFlow instance." This was flagged as the key technical hurdle in R2 and needs to be explicit.

### TSG-106: RetentionEngine

- **Spec completeness**: PASS
- **Issues**: None. Clean SQL with parameterized queries, `_validate_identifier()` on table names, transactions. All infrastructure-sql rules followed.
- **Acceptance criteria**: All testable. Archive, delete, partition (PostgreSQL-only with clear error), dry run, status.
- **Red team coverage**: R1-6 (engine.py), R2-03 (SyncExpress), infrastructure-sql rules 1-3. Addressed.
- **Test plan**: 6-8 unit + 3-4 integration. Adequate.
- **Missing**: The `cutoff_field` is interpolated into SQL via f-string in the code sketch (`f"WHERE {policy.cutoff_field} < ?"`). The `cutoff_field` should be validated with `_validate_identifier()` just like `table_name` and `archive_table`. Add AC: "Cutoff field name validated with `_validate_identifier()` before SQL interpolation."

### TSG-201: DataFlowEventMixin

- **Spec completeness**: PASS
- **Issues**: None. Excellent specificity on `payload` vs `data` field name, `WRITE_OPERATIONS` constant, `hasattr` guard for backward compat, and the no-op behavior when no subscribers exist.
- **Acceptance criteria**: All testable. 8 write nodes instrumented, event type format, `on_model_change()` with 8 subscriptions, pre-initialize guard.
- **Red team coverage**: R1-1 (specific subscriptions, WRITE_OPERATIONS constant), R2-01 (payload field name), R2-03 (no new Express methods needed), R1-6 (3 lines in engine.py). All addressed.
- **Test plan**: 5-7 unit + 2-3 integration. Adequate. The `test_emit_write_event_correct_field_name` test is a direct R2-01 regression test.
- **Missing**: The code sketch shows the write node instrumentation pattern but does not specify exactly which existing files contain the 4 single-record write nodes (`CreateNode`, `UpdateNode`, `DeleteNode`, `UpsertNode`). It says `core/nodes.py` "or equivalent." An implementer would need to locate these — add a definitive file path. This is a minor gap since the implementer can search for the node class names.

---

## mcp-platform-server

### MCP-500: Server skeleton

- **Spec completeness**: PASS
- **Issues**: None. This is the strongest todo in the batch. The R2-04 BLOCKING issue (module path conflict) is resolved with explicit rename steps. The code sketch is production-quality, not a placeholder.
- **Acceptance criteria**: All testable. File rename, contributor loop with exception handling, namespace validation, security tier enforcement, CLI entry point, pyproject.toml changes.
- **Red team coverage**: R2-04 (BLOCKING — rename first), RT-1a (catch Exception), RT-1c/RT-4a (namespace validation), R2-02 (stderr logging), R2-05 (SAFE rename), R2-12 (create_platform_server name), RT-6a (stderr), RT-6c (startup duration). Comprehensive.
- **Test plan**: 7 unit tests listed with clear scenarios. Integration deferred to MCP-510.
- **Missing**: The `contrib/__init__.py` code sketch contains `raise NotImplementedError("Contributor modules must implement register_tools()")` in the example `register_tools()` function. This is a documentation example, not production code, but it could confuse an implementer. The function should either be removed (it is a protocol, not a callable) or renamed to `_example_register_tools`. Minor.

### MCP-501: Core SDK contributor

- **Spec completeness**: PASS
- **Issues**: Minor — the validation tool (`core.validate_workflow`) acceptance criteria say "Checks: all node types exist in discovered node types (warns on unknown)" but do not specify whether unknown node types cause `valid: false` or just add a warning. Should clarify: unknown node types produce `warnings`, not `errors`, since custom nodes are valid but not discoverable via AST.
- **Acceptance criteria**: Mostly testable. The AST scanning heuristic ("class name ends with `Node`") is well-defined.
- **Red team coverage**: R2-11 (scan_metadata), GAP-2 (AST scanning), R2-07 (core only uses base package), RT-2a (no sub-package imports). Addressed.
- **Test plan**: Adequate. Tests against real `kailash.nodes` package, not mocks.
- **Missing**: Cache invalidation logic is vague: "cache invalidated by mtime check on `kailash/nodes/` directory." How? Check mtime of directory stat? Or max mtime of all files in the directory? Specify the invalidation mechanism.

### MCP-502: DataFlow contributor

- **Spec completeness**: PASS
- **Issues**: None. The AST detection heuristic for `@db.model` is well-documented with code sketch covering both `ast.Attribute(attr="model")` and `ast.Call(func=ast.Attribute(attr="model"))` patterns. The R2-07 import path variants are explicitly addressed.
- **Acceptance criteria**: All testable. 5 tools, each with output schema. Dynamic registration limitation documented.
- **Red team coverage**: GAP-2 (AST scanning), R2-07 (model detection heuristic), R2-08 (dynamic registration limitation), R2-09 (external packages), R2-11 (scan_metadata). Comprehensive.
- **Test plan**: 6 unit tests with specific scenarios including all 5 R2-07 decorator patterns.
- **Missing**: The `table_name` field in the output uses a hardcoded heuristic (`node.name.lower() + "s"`), but DataFlow's actual table name convention may differ (e.g., `__dataflow__["table_name"]` override). The scan_metadata limitations should document this: "Table names use default convention (lowercase + 's'); custom table_name overrides not detected via AST."

### MCP-503: Nexus contributor

- **Spec completeness**: PASS
- **Issues**: The handler detection is acknowledged as more fragile (R2-13), and this is properly documented in scan_metadata limitations. The code sketch for `_parse_add_handler_call` is solid.
- **Acceptance criteria**: All testable. 4 tools, handler detection patterns documented.
- **Red team coverage**: GAP-2 (AST scanning), R2-13 (imperative registration fragility), R2-11 (scan_metadata). Addressed.
- **Test plan**: 5 unit tests. Adequate given the acknowledged limitations.
- **Missing**: The `nexus.validate_handler` tool is listed in acceptance criteria but has no validation logic specified — what does "validate handler definition" mean? Check for async def? Check for correct parameter types? Check for return type? This needs specification or it is too vague for an implementer.

### MCP-504: Kaizen contributor

- **Spec completeness**: PASS
- **Issues**: None. The agent detection heuristic with `_KNOWN_AGENT_BASES` set and the Delegate instantiation detection are well-specified. The coverage estimates (~90%) are honest and documented.
- **Acceptance criteria**: All testable. 3 tools, detection patterns for class-based and Delegate agents, scaffold with both patterns.
- **Red team coverage**: GAP-2 (AST), GAP-4 (BaseAgent heuristic), R2-10 (inheritance chain), R2-11 (scan_metadata). Addressed.
- **Test plan**: 5 unit tests including indirect inheritance in same file.
- **Missing**: The `_extract_tools` function referenced in the code sketch is not defined or sketched. How are tools detected? From `tools=` parameter in constructor call? From class-level attribute? From `@tool` decorators in the class body? An implementer needs guidance here. Add a brief description of the tool extraction heuristic.

### MCP-505: Trust + PACT contributors

- **Spec completeness**: PASS
- **Issues**: The PACT contributor is underspecified compared to the Trust contributor. Where does the PACT org definition live? What file format? The Trust contributor clearly reads from `{project_root}/trust-plane/manifest.json`, but the PACT contributor just says "reads org definition from PACT config files in project_root" without specifying the file name or format.
- **Acceptance criteria**: Trust tools are testable. PACT tools are vague.
- **Red team coverage**: RT-3c (trust advisory), R2-11 (scan_metadata), GAP-2 (file-based). Addressed for Trust. PACT coverage is thin.
- **Test plan**: 4 unit tests. Adequate for Trust. PACT needs more.
- **Missing**: PACT contributor needs: (a) exact file path(s) to read (e.g., `{project_root}/pact.yaml` or `{project_root}/pact/org.py`), (b) expected file format (Python dataclass definition? YAML? JSON?), (c) parsing strategy (AST scan of Python file? YAML parse?). Without these, an implementer cannot build `pact.org_tree`.

### MCP-506: Platform map

- **Spec completeness**: PASS
- **Issues**: None. The cross-framework connection detection via deterministic naming (`Create{ModelName}` in handler source) is clever and well-specified with code sketch.
- **Acceptance criteria**: All testable. Output schema documented. Performance target (<2s) specified.
- **Red team coverage**: GAP-5 (connection detection), RT-2b (missing frameworks), R2-11/R2-11b (scan_metadata, no completeness claim). Addressed.
- **Test plan**: 5 unit + 1 deferred integration. Adequate.
- **Missing**: The `_safe_scan` helper function is referenced but not defined. Presumably wraps scanner calls in try/except to return `[]` on failure. Minor — an implementer can infer this.

### MCP-507: MCP Resources

- **Spec completeness**: PASS
- **Issues**: The `_get_max_mtime` function walks ALL Python files in project_root for every resource access. For large projects, this could be slow. The performance concern is not addressed.
- **Acceptance criteria**: All testable. 5 resources, mtime-based caching, thread safety.
- **Red team coverage**: GAP-8 (mtime detection), RT-5b (debouncing), RT-5a (cleanup). Addressed.
- **Test plan**: 4 unit tests. Adequate.
- **Missing**: Performance concern — walking all .py files on every resource access needs a mitigation. Suggest: cache the max mtime result for N seconds (e.g., 5s) to avoid repeated filesystem walks within the same tool call batch. Add AC: "Mtime scan result cached for 5 seconds to avoid repeated filesystem walks during batched resource access."

### MCP-508: Test generation tools

- **Spec completeness**: PASS
- **Issues**: Minor — the DataFlow test template uses `async def` test methods in a class, but this requires `pytest-asyncio` configuration (either `asyncio_mode = "auto"` or `@pytest.mark.asyncio` decorators). The generated test code should include the necessary markers.
- **Acceptance criteria**: All testable. Three framework generators, tier parameter, template-based.
- **Red team coverage**: R2-11 (scan_metadata). Addressed. Other findings not directly relevant.
- **Test plan**: 4 unit tests. Adequate.
- **Missing**: Generated test code should include `@pytest.mark.asyncio` on async test methods or a `pytest.ini` configuration note. Without this, generated tests will fail with "coroutine was never awaited."

### MCP-509: Execution tools (Tier 4)

- **Spec completeness**: PASS
- **Issues**: The subprocess execution model is well-defined with timeouts and structured error output. One concern: the `_execute_in_subprocess` function passes `env={**dict(os.environ), "PYTHONPATH": str(project_root)}` which could leak sensitive environment variables into the subprocess stdout if the executed code prints them. This is defense-in-depth territory — the subprocess already inherits the parent environment, but the explicit env construction makes it visible.
- **Acceptance criteria**: All testable. Security gating, subprocess isolation, timeouts.
- **Red team coverage**: RT-3a (env var gating), RT-3c (trust plane advisory), R2-11 (scan_metadata). Addressed.
- **Test plan**: 4 unit + 1 deferred integration. Adequate.
- **Missing**: The agent testing subprocess script is not sketched. How does the subprocess instantiate an agent from an AST scan result? It needs to: (1) import the module, (2) find the agent class, (3) instantiate it with appropriate config, (4) run the task. Steps 2-3 need specification for both BaseAgent subclasses and Delegate instances. This is the hardest part of MCP-509 and is unspecified.

### MCP-510: Integration + E2E test suite

- **Spec completeness**: PASS
- **Issues**: None. The fixture project design is smart — explicit `CreateUser` string reference in handler source for connection detection testing. McpClient usage pattern is production-quality.
- **Acceptance criteria**: All testable. 10+ integration tests, security tier tests, graceful degradation, startup time budget.
- **Red team coverage**: RT-6c/R2-03 (startup time), RT-3a (security tiers), RT-2a/2b (graceful degradation), GAP-5 (connection detection), GAP-7 (fixture project). Comprehensive.
- **Test plan**: This todo IS the test plan.
- **Missing**: Nothing material.

### MCP-511: Old MCP cleanup

- **Spec completeness**: PASS
- **Issues**: None. Clean deletion scope, import surface analysis, cross-workspace coordination documented.
- **Acceptance criteria**: All verifiable. File deletions, import updates, cross-workspace notes, verification commands.
- **Red team coverage**: GAP-3 (Nexus overlap), R2-06 (Option A sequencing). Addressed.
- **Test plan**: Post-deletion import verification and test suite pass. Adequate.
- **Missing**: The assessment of `src/kailash/channels/mcp_channel.py` and `src/kailash/api/mcp_integration.py` is deferred to implementation ("Assess and update if needed"). These should be investigated during the todo authoring phase, not left for the implementer to discover. NEEDS WORK — add explicit assessment: does each file reference the deleted modules? What is the migration path?

---

## nexus-transport-refactor (NTR-prefixed only)

### NTR-000: Milestone Tracker

- **Spec completeness**: PASS
- **Issues**: None. Clean phase structure, sequencing rules, baseline recording instructions.
- **Missing**: Nothing.

### NTR-001: Dead code removal

- **Spec completeness**: PASS
- **Issues**: None. Extremely precise — line numbers, method names, verification grep commands.
- **Acceptance criteria**: All verifiable. Three methods removed, grep confirms zero remaining references, tests pass.
- **Red team coverage**: R1 Finding 6, R2-04 (first commit). Addressed.
- **Test plan**: Before/after test comparison. Adequate.
- **Missing**: Nothing.

### NTR-002: HandlerRegistry extraction

- **Spec completeness**: PASS
- **Issues**: None. The strongest NTR todo. Complete `registry.py` code provided, modification points in `core.py` specified with line numbers, backward-compat properties documented.
- **Acceptance criteria**: All testable. Three registration paths preserved, MCP tool registration still works, `_execute_workflow()` still finds workflows.
- **Red team coverage**: R1 Challenge 1 (preserve all paths), R2-05 (no test breakage), R2-04 (independently revertible). Addressed.
- **Test plan**: Baseline comparison + grep for internal dict access. Adequate.
- **Missing**: Nothing.

### NTR-003: EventBus implementation

- **Spec completeness**: PASS
- **Issues**: One concern — the `start()` method wiring in `core.py` is uncertain. The code sketch says "Note: Since `start()` blocks on `self._gateway.run()`, the EventBus needs to start before that blocking call. If there is no running loop at this point, create a helper that starts the bus in the gateway's event loop. The exact wiring depends on how the gateway's loop is structured." This ambiguity could block an implementer.
- **Acceptance criteria**: All testable. Janus queue lifecycle, bounded history, subscriber fan-out, backward-compat `broadcast_event()`/`get_events()`.
- **Red team coverage**: R1 Finding 2 (janus correct), R1 Finding 7 (broadcast_event migration), R2-06 (bounded history), R2-03 (subscribe_filtered for bridge). Addressed.
- **Test plan**: Baseline + 4 new EventBus unit tests. Adequate.
- **Missing**: Resolve the `start()` wiring ambiguity. Add an explicit AC: "EventBus `start()` is called via `loop.run_until_complete()` in `Nexus.start()` before the blocking `self._gateway.run()` call. If no event loop exists at that point, `asyncio.new_event_loop()` is created." This was flagged but left as a "depends on how the gateway's loop is structured" open question.

### NTR-004: BackgroundService ABC

- **Spec completeness**: PASS
- **Issues**: None. Small, well-scoped. ~50 lines of ABC + lifecycle wiring.
- **Acceptance criteria**: All testable. ABC methods, lifecycle wiring, health check aggregation.
- **Red team coverage**: R2-01 (safe intermediate state). Addressed.
- **Test plan**: Baseline + 1 minimal unit test. Adequate.
- **Missing**: Nothing.

### NTR-005: B0a Integration verification

- **Spec completeness**: PASS
- **Issues**: None. Excellent validation gate — plugin audit, MIGRATION.md, test verification, architecture verification.
- **Acceptance criteria**: All verifiable. Import checks, property delegation, cross-package tests.
- **Red team coverage**: R1 Finding 3 (plugin audit), R1 Finding 5 (baseline), R2-01 (MIGRATION.md), R2-06 (bounded history). Addressed.
- **Test plan**: This todo IS the test plan for B0a.
- **Missing**: Nothing.

### NTR-010: Transport ABC definition

- **Spec completeness**: PASS
- **Issues**: None. Clean ABC definition. The decision to NOT wire `start()` into Nexus lifecycle yet (deferred to NTR-011) is correct — keeps this as a pure definition.
- **Acceptance criteria**: All testable. ABC interface, no lifecycle wiring yet.
- **Red team coverage**: R2-01 (safe intermediate state). Addressed.
- **Test plan**: 1 unit test with mock Transport. Adequate.
- **Missing**: Nothing.

### NTR-011: HTTPTransport extraction

- **Spec completeness**: PASS
- **Issues**: This is the largest and riskiest NTR todo. The coupling map (10 line ranges) is excellent. The middleware/router/endpoint queuing pattern is well-designed. One concern: the `_execute_workflow()` method raises `HTTPException` — this is the last FastAPI import that may remain in `core.py`. The todo mentions "this import can be made lazy" but does not specify how. Should be an explicit AC.
- **Acceptance criteria**: All testable. Public API compatibility, deprecation warnings, no FastAPI imports in core.py.
- **Red team coverage**: Gap Analysis findings (register_workflow, enable_auth, enable_monitoring), R1 Finding 4 (middleware ordering), R2-05 (no test breakage), endpoint timing. Addressed.
- **Test plan**: Baseline + 6 new tests. Adequate.
- **Missing**: Add explicit AC for the `_execute_workflow` HTTPException handling: "The `_execute_workflow()` method uses a lazy import `from fastapi import HTTPException` inside the method body, not at module level. This is the ONLY remaining FastAPI reference in core.py."

### NTR-012: MCPTransport

- **Spec completeness**: PASS
- **Issues**: One concern — the code sketch uses `from fastmcp import FastMCP` but the actual import path in the `mcp` package is `from mcp.server import FastMCP` (as used in MCP-500). The import path should be verified. Also, `self._server.run_ws()` may not be the correct FastMCP API for WebSocket transport — FastMCP uses `server.run(transport="sse")` or `server.run(transport="stdio")`. The WebSocket API needs verification.
- **Acceptance criteria**: All testable. Tool registration, namespace prefix, hot-registration.
- **Red team coverage**: Brief Decision 4 (FastMCP), R2-02 (file deletion overlap). Addressed.
- **Test plan**: 5 new tests. Adequate.
- **Missing**: (1) Verify the FastMCP import path (`from mcp.server import FastMCP` vs `from fastmcp import FastMCP`). (2) Verify the FastMCP WebSocket server API (`run_ws` vs `run(transport="sse")`). These are implementation details that could block an implementer if wrong.

### NTR-013: Phase 2 feature APIs

- **Spec completeness**: PASS
- **Issues**: The `NexusFile.from_upload_file()` classmethod has a questionable `RuntimeError` for async context detection. The rationale is that in async context you should read the file first — but this is a surprising API. Consider making it always synchronous (read the file in a thread) or always async.
- **Acceptance criteria**: All testable. 5 new APIs, NexusFile type with factory methods.
- **Red team coverage**: Brief Decision 12 (asyncio.create_task), Brief Decision 8 (NexusFile). Addressed.
- **Test plan**: 9 new tests. Adequate.
- **Missing**: The `on_event()` decorator says "Supports exact match and wildcard patterns (e.g., 'dataflow._')" in the docstring, but the Nexus EventBus `subscribe_filtered()` approach requires a predicate function, not a wildcard string. The wildcard claim in the docstring is misleading — `on_event("dataflow._")` would not work as written. Either implement wildcard-to-predicate conversion in the decorator, or remove the wildcard claim from the docstring.

### NTR-014: B0b Integration verification

- **Spec completeness**: PASS
- **Issues**: None. Comprehensive verification gate. Import path checks, deprecation verification, line count target.
- **Acceptance criteria**: All verifiable. MIGRATION.md update, import verification commands, deprecation test code, line count target (<1500).
- **Red team coverage**: Gap Analysis Finding 4 (line count), R1 Finding 3 (deprecation), R2-01 (MIGRATION.md), R2-02 (MCP coordination). Addressed.
- **Test plan**: This todo IS the test plan for B0b.
- **Missing**: Nothing.

### NTR-020: DataFlow-Nexus event bridge

- **Spec completeness**: PASS
- **Issues**: One concern — the `_DATAFLOW_ACTIONS` list uses `"created"`, `"updated"`, etc. but TSG-201's `WRITE_OPERATIONS` constant uses `"create"`, `"update"`, `"delete"` (without past tense). The event type format `f"dataflow.{model_name}.{action}"` in TSG-201 would produce `"dataflow.User.create"`, not `"dataflow.User.created"`. This is a naming mismatch that would cause the bridge to subscribe to wrong event types.
- **Acceptance criteria**: All testable. Bridge installation, event translation, 8 action types per model.
- **Red team coverage**: Brief Decision 9 (bridge), Brief Decision 10 (two EventBus systems), R2-03 (no wildcards). Addressed.
- **Test plan**: Unit + integration (deferred until TSG-201 complete). Adequate.
- **Missing**: **CRITICAL** — The action names in `_DATAFLOW_ACTIONS` must match the event types emitted by TSG-201's `WRITE_OPERATIONS`. TSG-201 uses `["create", "update", "delete", "upsert", "bulk_create", "bulk_update", "bulk_delete", "bulk_upsert"]`. NTR-020 uses `["created", "updated", "deleted", "bulk_created", "bulk_updated", "bulk_deleted", "read", "listed"]`. These do NOT match. Fix: align NTR-020's actions with TSG-201's `WRITE_OPERATIONS` constant, OR document that the bridge translates between naming conventions. Also: NTR-020 includes `"read"` and `"listed"` which are NOT write operations and are NOT in TSG-201's `WRITE_OPERATIONS`.

---

## Summary

| Workspace                | Todos Reviewed    | PASS   | NEEDS WORK | CRITICAL GAPS |
| ------------------------ | ----------------- | ------ | ---------- | ------------- |
| dataflow-enhancements    | 9 (incl. tracker) | 9      | 0          | 0             |
| mcp-platform-server      | 12                | 10     | 2          | 0             |
| nexus-transport-refactor | 11 (NTR only)     | 9      | 2          | 1             |
| **Total**                | **32**            | **28** | **4**      | **1**         |

### NEEDS WORK items (non-blocking, should fix before /implement)

1. **MCP-505**: PACT contributor needs exact file path, format, and parsing strategy for org definitions. Trust contributor is fine.
2. **MCP-511**: Assessment of `mcp_channel.py` and `mcp_integration.py` deferred to implementation. Should investigate now.
3. **NTR-003**: EventBus `start()` wiring in Nexus.start() is ambiguous ("depends on how the gateway's loop is structured"). Needs explicit resolution.
4. **NTR-012**: FastMCP import path and WebSocket API need verification before implementation.

### CRITICAL GAP (must fix before /implement)

1. **NTR-020**: Action name mismatch with TSG-201. NTR-020's `_DATAFLOW_ACTIONS` uses past tense (`"created"`) and includes read operations (`"read"`, `"listed"`). TSG-201's `WRITE_OPERATIONS` uses present tense (`"create"`) and only includes write operations. The bridge will subscribe to event types that are never emitted, silently receiving zero events. This is the EXACT same class of bug as R1-1 (EventBus wildcard gap) — a subscription that never matches. Fix: change NTR-020's `_DATAFLOW_ACTIONS` to match TSG-201's `WRITE_OPERATIONS` exactly.

### Recommended fixes (improvements, not blockers)

- **TSG-101**: Add explicit debounce_ms AC checkbox
- **TSG-103**: Add explicit AC about validation-only-when-defined behavior
- **TSG-105**: Add explicit AC for ConnectionManager refactor
- **TSG-106**: Add `_validate_identifier()` for `cutoff_field` in AC
- **MCP-501**: Clarify unknown node type handling (warning vs error) in validation
- **MCP-503**: Specify what `nexus.validate_handler` actually validates
- **MCP-504**: Add `_extract_tools` heuristic description
- **MCP-507**: Add mtime scan caching for performance
- **MCP-508**: Include `@pytest.mark.asyncio` in generated test templates
- **MCP-509**: Specify subprocess agent instantiation script structure
- **NTR-011**: Make `_execute_workflow` HTTPException handling explicit
- **NTR-013**: Fix `on_event()` wildcard claim in docstring

---

## Convergence

**Can we proceed to /implement?**

**Yes, with one mandatory fix.** NTR-020's action name mismatch with TSG-201 must be corrected before implementation — subscribing to event types that never fire is a silent failure. The 4 NEEDS WORK items are resolvable during implementation but would be cleaner if addressed in the todo specs first.

The DataFlow workspace is fully implementation-ready. The MCP workspace is implementation-ready except for MCP-505 (PACT contributor underspecified) and MCP-511 (deferred assessment). The Nexus workspace is implementation-ready except for NTR-003 (ambiguous wiring) and the NTR-020 critical gap.

**Recommendation**: Fix NTR-020 action names now. Address the 4 NEEDS WORK items in the next hour. Then proceed to /implement starting with Phase 1 parallel work (DataFlow TSG-100/102/103/104/105/106 + MCP MCP-500 + Nexus NTR-001).
