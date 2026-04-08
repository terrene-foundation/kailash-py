# Implementation Plan — Issues #294-#303

## Execution Strategy

3 waves, maximum parallelism within each wave. 9 PRs total (one per actionable issue). #294 closed with note (no code changes).

## Wave 1: Bugs + Independent Features (5 PRs, parallel)

### PR-1: fix(ml): add isfinite() guards to correlation matrices (#295)

**Scope**: 3 method fixes + regression tests
**Files**:

- `packages/kailash-ml/src/kailash_ml/engines/data_explorer.py` — guard \_compute_pearson, \_compute_spearman, \_compute_cramers_v
- `packages/kailash-ml/tests/unit/test_data_explorer.py` — add constant-column and zero-variance tests

**Approach**: Follow existing skewness/kurtosis pattern (`math.isfinite(val) else 0.0`). Add tests that create DataFrames with constant columns to trigger NaN correlation.

**Estimate**: < 30 min autonomous

---

### PR-2: fix(dataflow): implement bulk_upsert() Express API with event emission (#296)

**Scope**: New method (async + sync) + event emission + tests
**Files**:

- `packages/kailash-dataflow/src/dataflow/features/express.py` — add bulk_upsert() async + sync
- `packages/kailash-dataflow/tests/unit/features/test_dataflow_events.py` — verify bulk_upsert event

**Approach**: Follow bulk_create() pattern (accepts list of records). Conflict resolution via `conflict_on` parameter (same as upsert_advanced). Emit "bulk_upsert" event with record_id=None.

**Estimate**: 1 session

---

### PR-3: feat(align): on-prem workflow — OnPremSetupGuide + config plumbing (#298)

**Scope**: OnPremSetupGuide class + wire OnPremConfig into Pipeline/Evaluator
**Files**:

- `packages/kailash-align/src/kailash_align/onprem.py` — add OnPremSetupGuide class
- `packages/kailash-align/src/kailash_align/pipeline.py` — add onprem_config parameter, add \_hf_kwargs() helper
- `packages/kailash-align/src/kailash_align/evaluator.py` — add onprem_config parameter
- `packages/kailash-align/tests/test_onprem.py` — test OnPremSetupGuide + integration tests

**Approach**: Add `_hf_kwargs()` helper that returns `{"local_files_only": True}` when offline. Thread through all HuggingFace from_pretrained() calls. OnPremSetupGuide.generate_checklist() returns markdown.

**Risk**: 15-25 HuggingFace call sites. Mitigated by \_hf_kwargs() pattern.

**Estimate**: 1 session

---

### PR-4: fix(mcp): add list_events tool + complete handler output fields (#299)

**Scope**: New tool + AST parser extension + stub-to-real list_channels
**Files**:

- `src/kailash/mcp/contrib/nexus.py` — add list_events(), extend list_handlers() output, implement list_channels()
- Tests for new/enhanced tools

**Approach**: Extend AST parser to extract docstrings and decorator metadata. list_events() scans for EventBus.subscribe() calls. list_channels() detects HTTP/CLI/MCP/WebSocket from Nexus configuration patterns.

**Estimate**: 1 session

---

### PR-5: ci: test pipelines for kailash-ml and kailash-align (#303)

**Scope**: 2 new workflow files + version consistency check
**Files**:

- `.github/workflows/test-kailash-ml.yml` — 3-variant matrix (base, [dl], [rl])
- `.github/workflows/test-kailash-align.yml` — test + optional GPU job
- Update publish pipeline with `needs:` dependencies

**Approach**: Follow unified-ci.yml pattern. Python 3.10-3.13 for ML, 3.10-3.12 for Align. Version consistency check: compare pyproject.toml version with **version**.

**Estimate**: < 30 min autonomous

---

## Wave 2: Dependent Features + Testing (3 PRs, parallel)

### PR-6: feat(align): 4 Kaizen agent definitions for alignment workflows (#297)

**Scope**: New agents/ directory with 4 agents + 8 tools + tests
**Files**:

- `packages/kailash-align/src/kailash_align/agents/__init__.py`
- `packages/kailash-align/src/kailash_align/agents/strategist.py`
- `packages/kailash-align/src/kailash_align/agents/data_curation.py`
- `packages/kailash-align/src/kailash_align/agents/training_config.py`
- `packages/kailash-align/src/kailash_align/agents/eval_interpreter.py`
- `packages/kailash-align/src/kailash_align/agents/tools.py`
- `packages/kailash-align/tests/test_agents.py`
- `packages/kailash-align/src/kailash_align/__init__.py` — update exports

**Approach**: Follow kailash-ml agent pattern exactly. Lazy Kaizen imports. Signatures with confidence: float output. 8 tools as dumb data endpoints (no decision logic). Gate via [agents] extra.

**Depends on**: Understanding from PR-3 (#298) config structure.

**Estimate**: 1 session

---

### PR-7: test(mcp): platform server McpClient integration tests (#300)

**Scope**: McpClient-based tests for platform server
**Files**:

- `tests/integration/mcp/test_platform_server_mcpclient.py` (new)
- Extend `tests/fixtures/mcp_test_project/` if needed

**Approach**: Spawn platform server as subprocess, connect via MiddlewareMCPClient, test tools/list + tool calls + security tiers + graceful degradation. Use unique port allocation per test.

**Depends on**: PR-4 (#299) for list_events tool assertions.

**Estimate**: 1 session

---

### PR-8: test: WS-4.5 integration gate — 3 cross-framework scenarios (#301)

**Scope**: 3 test files in tests/integration/ws45/
**Files**:

- `tests/integration/ws45/__init__.py`
- `tests/integration/ws45/conftest.py` — shared fixtures
- `tests/integration/ws45/test_scenario1_derived_model_event.py`
- `tests/integration/ws45/test_scenario2_inference_server.py`
- `tests/integration/ws45/test_scenario3_platform_map.py`

**Approach**:

- Scenario 1: DataFlow write → EventBus → DerivedModel refresh (real infrastructure, no mocks)
- Scenario 2: InferenceServer → Nexus HTTP POST → verify prediction response
- Scenario 3: platform_map() via MCP → verify models/handlers/agents/connections graph

**Depends on**: PR-2 (#296) for Scenario 1 event emission. platform_map() already exists.

**Estimate**: 1 session

---

## Wave 3: Documentation (1 PR)

### PR-9: docs: framework guides for kailash-ml and kailash-align (#302)

**Scope**: 12 framework guides (6 ML + 6 Align)
**Files**:

- `packages/kailash-ml/docs/guides/01-quickstart.md` through `06-onnx-export.md`
- `packages/kailash-align/docs/guides/01-quickstart.md` through `05-kaizen-bridge.md`

**Approach**: Follow kailash-dataflow guide pattern. All code examples tested against real package. Each guide includes "Common errors" section.

**Depends on**: PR-3, PR-6 for Align content; all ML features already released.

**Estimate**: 1-2 sessions (content-heavy)

---

## Close (no PR)

### #294: Cross-SDK vector node alignment

Close with comment: "No kailash-py code changes needed. Python pgvector support complete. Tracking Rust implementation at kailash-rs#196."

---

## Summary

| Wave | PRs | Issues                       | Parallel       | Dependencies    |
| ---- | --- | ---------------------------- | -------------- | --------------- |
| 1    | 5   | #295, #296, #298, #299, #303 | All 5 parallel | None            |
| 2    | 3   | #297, #300, #301             | All 3 parallel | Wave 1          |
| 3    | 1   | #302                         | Sequential     | Wave 2          |
| —    | 0   | #294                         | —              | Close with note |

**Total**: 9 PRs, ~5-6 autonomous sessions
