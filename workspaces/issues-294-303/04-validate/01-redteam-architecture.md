# Red Team: Architecture Review — Optimal Implementation

## Verdict: Current plan treats symptoms, not root causes. 7 of 9 PRs need architectural upgrades.

### PR-1 (#295): ML Correlation — MAJOR REDESIGN

| Finding                                    | Current Plan  | Optimal                                                     |
| ------------------------------------------ | ------------- | ----------------------------------------------------------- |
| fill_null(0.0) produces wrong correlations | Not addressed | Pairwise-complete observation (drop nulls per column pair)  |
| Ad-hoc isfinite() guards                   | 3 call sites  | Centralized `_sanitize_float()` for ALL numeric outputs     |
| NaN → 0.0 is misleading                    | 0.0 fallback  | `None` = "undefined" (distinct from 0.0 = "no correlation") |
| No row-count guard                         | Not addressed | `data.height < 2` early return                              |
| HTML shows "nan" text                      | Not addressed | Render "N/A" with tooltip                                   |
| Alert check ignores NaN                    | Not addressed | Guard alert threshold against None                          |

### PR-2 (#296): DataFlow bulk_upsert — ADDITIONS

| Finding                   | Current Plan       | Optimal                                          |
| ------------------------- | ------------------ | ------------------------------------------------ |
| Missing sync bulk_update  | Not in scope       | Fix in same PR (10 lines, consistency)           |
| conflict_on not validated | String list        | Validate field names against model schema        |
| Return value stripped     | Follow bulk_create | Return structured dict {created, updated, total} |
| No batch_size control     | Not addressed      | Optional batch_size parameter                    |

### PR-3 (#298): Align On-Prem — MAJOR REDESIGN

| Finding                     | Current Plan                      | Optimal                                                           |
| --------------------------- | --------------------------------- | ----------------------------------------------------------------- |
| \_hf_kwargs() band-aid      | Thread helper through 15-25 sites | `ModelLoader` abstraction — single entry point                    |
| Separate OnPremConfig param | New constructor param             | Nest OnPremConfig inside AlignmentConfig                          |
| Checklist returns markdown  | `-> str`                          | Structured `SetupChecklist` dataclass with `to_markdown()`        |
| No offline isolation test   | Download tiny model               | Mock filesystem + patched-network test proves zero network escape |

### PR-6 (#297): Align Agents — CORRECTIONS

| Finding                       | Current Plan         | Optimal                                                         |
| ----------------------------- | -------------------- | --------------------------------------------------------------- |
| Issue says "Delegate pattern" | Unclear              | BaseAgent + Signature (match kailash-ml pattern)                |
| Tools unspecified             | 8 tools              | 3 MUST use existing engines (gpu_memory.py, method_registry.py) |
| No orchestrator               | 4 independent agents | Add optional `alignment_workflow()` function                    |
| Hardcoded tool data           | Not addressed        | Tools wrap existing engines, never reimplement                  |

### PR-4 (#299): MCP Nexus — ARCHITECTURAL CHANGE

| Finding              | Current Plan     | Optimal                                          |
| -------------------- | ---------------- | ------------------------------------------------ |
| AST-only parsing     | Extend AST       | Runtime introspection + AST fallback             |
| list_events location | In nexus.py      | Separate core.list_events tool querying EventBus |
| list_channels stub   | Implement in AST | Query Nexus instance channels at runtime         |

### PR-7 (#300) + PR-8 (#301): MCP Tests + WS-4.5 — ADDITIONS

| Finding                 | Current Plan         | Optimal                                             |
| ----------------------- | -------------------- | --------------------------------------------------- |
| MCP protocol not tested | McpClient subprocess | Add Tier 2 STDIO protocol tests with real handshake |
| Scenario 2 missing MCP  | HTTP only            | Add `register_mcp_tools()` to InferenceServer       |
| Debounce testing flaky  | asyncio.sleep()      | Configure debounce_ms=0 for deterministic tests     |
| Separate scenarios      | 3 independent files  | Unified test fixture for cross-framework validation |

### PR-5 (#303) + PR-9 (#302): CI + Docs — MAJOR ADDITIONS

| Finding                    | Current Plan       | Optimal                                                 |
| -------------------------- | ------------------ | ------------------------------------------------------- |
| Tests all packages always  | Separate workflows | Monorepo-aware changed-package dispatch                 |
| No coverage tracking       | Not addressed      | pytest-cov with per-package thresholds                  |
| Guide code blocks untested | Not addressed      | pytest-codeblocks automation                            |
| No inter-package testing   | Not addressed      | Dev-version dependency matrix                           |
| Static markdown only       | 12 guides          | Learning progression + Jupyter notebooks for top guides |
