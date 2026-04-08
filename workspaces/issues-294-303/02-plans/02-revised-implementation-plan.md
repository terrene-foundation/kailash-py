# Revised Implementation Plan — Optimal Architecture

Supersedes `01-implementation-plan.md`. Incorporates all red team findings.

## Execution Strategy

3 waves, 9 PRs. Every PR implements the architecturally optimal solution, not the quick fix.

---

## Wave 1: Bugs + Independent (5 PRs, parallel)

### PR-1: fix(ml): DataExplorer correlation robustness overhaul (#295)

**Scope**: Not just isfinite guards — fix the root cause and prevent future regressions.

**Architecture changes**:

1. **Centralized `_sanitize_float()`** — new function in data_explorer.py that ALL numeric outputs pass through. Returns `None` for non-finite values (not 0.0). Prevents future regressions when new statistics are added.
2. **Pairwise-complete correlation** — replace `fill_null(0.0)` with per-column-pair null dropping. Fast-path to `df.corr()` when no nulls present. This fixes demonstrably wrong correlation values.
3. **Row-count guard** — `data.height < 2` early return in Pearson/Spearman (single row has no variance).
4. **None semantics** — undefined correlations are `None`, not `0.0`. Type annotation: `dict[str, dict[str, float | None]]`.
5. **Alert guard** — threshold check handles `None` values. Optional: add `"undefined_correlation"` alert type.
6. **HTML report** — render "N/A" with tooltip for `None` correlation values.

**Files**:

- `packages/kailash-ml/src/kailash_ml/engines/data_explorer.py` — \_sanitize_float, \_compute_pearson (pairwise), \_compute_spearman (pairwise), \_compute_cramers_v, \_generate_alerts
- `packages/kailash-ml/src/kailash_ml/engines/_data_explorer_report.py` — \_matrix_table N/A rendering
- `packages/kailash-ml/tests/unit/test_data_explorer.py` — constant column, zero-variance, single-row, null-heavy tests

---

### PR-2: fix(dataflow): implement bulk_upsert() with structured results (#296)

**Scope**: New method + fix sync bulk_update gap + structured return values.

**Architecture changes**:

1. **Use BulkUpsertNode directly** — single vectorized call, NOT a loop. Database-native INSERT...ON CONFLICT.
2. **Structured return** — `{records: [...], created: int, updated: int, total: int}`. Do NOT strip to bare list like bulk_create does.
3. **Validate conflict_on** — check field names against model schema before SQL execution.
4. **Fix missing sync bulk_update()** — add to SyncExpress for API completeness (all 4 bulk ops have sync variants).
5. **Optional batch_size** — pass through to BulkUpsertNode (default 1000).
6. **Event emission** — `_emit_write_event(model, "bulk_upsert", record_id=None)`.

**Files**:

- `packages/kailash-dataflow/src/dataflow/features/express.py` — async bulk_upsert, sync bulk_upsert, sync bulk_update
- `packages/kailash-dataflow/tests/unit/features/test_dataflow_events.py` — event emission test
- `packages/kailash-dataflow/tests/unit/features/test_express_bulk_upsert.py` — round-trip + structured result tests

---

### PR-3: feat(align): ModelLoader abstraction + on-prem workflow (#298)

**Scope**: Proper abstraction layer, not band-aid helpers.

**Architecture changes**:

1. **ModelLoader class** — single entry point for ALL HuggingFace model/tokenizer/config loading. Centralizes offline_mode, cache_dir, revision, trust_remote_code. All modules import from it — impossible to accidentally bypass offline mode.
2. **Nest OnPremConfig in AlignmentConfig** — `config.onprem: OnPremConfig | None`. Eliminates parameter proliferation and the `local_files_only` / `offline_mode` dual-boolean confusion.
3. **Structured SetupChecklist** — `ChecklistItem` dataclass with `to_markdown()`, `to_dict()`. Agents can process programmatically, CLI renders as table, API returns JSON.
4. **Network isolation test** — mock filesystem matching HF cache layout + monkey-patch `requests.Session` to raise on any network call. Proves "offline means offline."

**Files**:

- `packages/kailash-align/src/kailash_align/model_loader.py` — NEW: ModelLoader class
- `packages/kailash-align/src/kailash_align/onprem.py` — OnPremSetupGuide with SetupChecklist
- `packages/kailash-align/src/kailash_align/config.py` — nest OnPremConfig in AlignmentConfig
- `packages/kailash-align/src/kailash_align/pipeline.py` — use ModelLoader
- `packages/kailash-align/src/kailash_align/evaluator.py` — use ModelLoader
- `packages/kailash-align/src/kailash_align/merge.py` — use ModelLoader
- `packages/kailash-align/src/kailash_align/vllm_backend.py` — use ModelLoader
- `packages/kailash-align/src/kailash_align/serving.py` — use ModelLoader
- `packages/kailash-align/tests/test_model_loader.py` — NEW: loader tests
- `packages/kailash-align/tests/test_onprem.py` — network isolation test

---

### PR-4: fix(mcp): runtime introspection for Nexus contributor (#299)

**Scope**: Replace pure AST with hybrid runtime + AST approach.

**Architecture changes**:

1. **Runtime introspection primary** — try importing and querying the Nexus instance directly. Handler metadata (description from docstring, channel, middleware) comes from runtime registries.
2. **AST fallback** — when runtime import fails (e.g., missing dependencies), fall back to current AST parser.
3. **list_events as separate concern** — add to Core SDK contributor or platform contributor, querying EventBus subscription registry directly.
4. **list_channels from runtime** — query `nexus.get_active_channels()` or inspect channel registrations.

**Files**:

- `src/kailash/mcp/contrib/nexus.py` — hybrid introspection + AST, list_events tool
- `src/kailash/mcp/contrib/platform.py` — list_events if placed here
- Tests for new tools and enhanced output

---

### PR-5: ci: monorepo-aware test pipelines with coverage (#303)

**Scope**: Not just per-package workflows — a scalable CI architecture.

**Architecture changes**:

1. **Changed-package detector** — `git diff` identifies modified packages, matrix only runs affected tests + dependents.
2. **Coverage enforcement** — pytest-cov with per-package thresholds (ML: 70%, Align: 60%, Core: 85%). Fail if coverage drops >2%.
3. **Inter-package dependency testing** — test kailash-align with dev version of kailash-ml (not PyPI).
4. **3-layer cache** — package-specific lock keys, compiled wheel cache, venv cache.
5. **Version consistency check** — pyproject.toml == **init**.py.**version**.
6. **Optional GPU job** — nightly + workflow_dispatch on GitHub-hosted GPU runners.

**Files**:

- `.github/workflows/test-kailash-ml.yml` — monorepo-aware, 3-variant matrix
- `.github/workflows/test-kailash-align.yml` — monorepo-aware + GPU optional
- `.github/scripts/detect-changed-packages.sh` — shared detector
- `.github/scripts/check-version-consistency.py` — version validator

---

## Wave 2: Dependent Features + Testing (3 PRs, parallel)

### PR-6: feat(align): 4 Kaizen agents with engine-backed tools (#297)

**Scope**: Agents + tools that delegate to existing engines.

**Architecture changes**:

1. **BaseAgent + Signature pattern** — match kailash-ml exactly (not Delegate). Single-shot reasoning, not multi-turn tool loops.
2. **Engine-backed tools** — `estimate_lora_memory_tool()` wraps `gpu_memory.estimate_training_memory()`. `get_gpu_memory_tool()` wraps `gpu_memory.get_gpu_info()`. `list_training_methods_tool()` wraps `METHOD_REGISTRY`. Zero reimplementation.
3. **Optional orchestrator function** — `alignment_workflow()` composes Strategist → DataCuration → TrainingConfig → EvalInterpreter. Stateless function, not a class.
4. **[agents] extra** — gate kailash-kaizen dependency.

**Files**:

- `packages/kailash-align/src/kailash_align/agents/__init__.py` — lazy imports
- `packages/kailash-align/src/kailash_align/agents/strategist.py`
- `packages/kailash-align/src/kailash_align/agents/data_curation.py`
- `packages/kailash-align/src/kailash_align/agents/training_config.py`
- `packages/kailash-align/src/kailash_align/agents/eval_interpreter.py`
- `packages/kailash-align/src/kailash_align/agents/tools.py` — thin wrappers around existing engines
- `packages/kailash-align/src/kailash_align/agents/orchestrator.py` — alignment_workflow()
- `packages/kailash-align/tests/test_agents.py`

---

### PR-7: test(mcp): STDIO protocol tests for platform server (#300)

**Scope**: Real MCP protocol verification, not just in-process tool execution.

**Architecture changes**:

1. **Tier 2 subprocess tests** — spawn server as subprocess, real STDIO transport.
2. **MCP handshake verification** — initialize → tools/list → tools/call round-trip.
3. **Protocol compliance** — verify CallToolResult format, error handling, content array structure.
4. **Keep existing in-process tests** — they stay as Tier 1 (fast, deterministic).

**Files**:

- `tests/integration/mcp/test_platform_server_protocol.py` — NEW: STDIO protocol tests
- Extend `tests/fixtures/mcp_test_project/` if needed

---

### PR-8: test: WS-4.5 integration gate with MCP prediction tools (#301)

**Scope**: 3 scenarios + new InferenceServer MCP tools.

**Architecture changes**:

1. **Deterministic debounce** — configure `debounce_ms=0` for Scenario 1 (instant refresh, no sleep-based flakiness).
2. **InferenceServer.register_mcp_tools()** — NEW method for Scenario 2, symmetric with register_endpoints().
3. **Unified test fixture** — single fixture with DataFlow + Nexus + InferenceServer + platform_map.
4. **platform_map() already exists** — Scenario 3 validates its output format.

**Files**:

- `packages/kailash-ml/src/kailash_ml/engines/inference_server.py` — add register_mcp_tools()
- `tests/integration/ws45/conftest.py` — unified cross-framework fixture
- `tests/integration/ws45/test_scenario1_derived_model_event.py`
- `tests/integration/ws45/test_scenario2_inference_server.py`
- `tests/integration/ws45/test_scenario3_platform_map.py`

---

## Wave 3: Documentation (1 PR)

### PR-9: docs: framework guides with tested code blocks (#302)

**Scope**: Not static docs — tested, structured learning paths.

**Architecture changes**:

1. **pytest-codeblocks** — all code examples extracted and executed in CI. Guides never go stale.
2. **Learning progression** — Level 0 (concepts) → Level 1 (quickstart) → Level 2 (end-to-end) → Level 3 (advanced).
3. **Real datasets** — iris for ML classification, IMDB for Align fine-tuning.
4. **Jupyter notebooks** — top 3 guides get companion .ipynb files (runnable in Colab).
5. **Common errors section** — 2-3 mistakes + fixes per guide.

**Files**:

- `packages/kailash-ml/docs/guides/` — 6 guides + 2-3 notebooks
- `packages/kailash-align/docs/guides/` — 5 guides + 1-2 notebooks
- Guide test infrastructure (conftest or pytest plugin)

---

## Close

### #294: Cross-SDK vector node alignment

Close with note: "No kailash-py changes needed. Python pgvector complete. Tracking kailash-rs#196."

---

## Summary

| Wave | PRs | Issues                       | Key Architectural Upgrade                                              |
| ---- | --- | ---------------------------- | ---------------------------------------------------------------------- |
| 1    | 5   | #295, #296, #298, #299, #303 | Centralized sanitizer, ModelLoader, runtime introspection, monorepo CI |
| 2    | 3   | #297, #300, #301             | Engine-backed tools, STDIO protocol tests, MCP prediction tools        |
| 3    | 1   | #302                         | Tested guides with learning progression                                |
