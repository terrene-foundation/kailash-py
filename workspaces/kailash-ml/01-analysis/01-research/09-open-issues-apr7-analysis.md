# Open Issues Analysis — 2026-04-07

10 open issues on `terrene-foundation/kailash-py`: 2 kaizen bugs (P0), 8 ML features (P0-P2).

## Issue Inventory

| #   | Title                                                 | Package        | Type | Priority | Complexity  |
| --- | ----------------------------------------------------- | -------------- | ---- | -------- | ----------- |
| 339 | BaseAgent MCP tool execution broken                   | kailash-kaizen | bug  | **P0**   | Medium      |
| 340 | GoogleGeminiProvider response_mime_type + tools crash | kailash-kaizen | bug  | **P0**   | Low         |
| 341 | Expose kailash_ml.metrics public module               | kailash-ml     | feat | **P0**   | Low-Medium  |
| 342 | Add log_loss, brier_score_loss, average_precision     | kailash-ml     | feat | **P0**   | Trivial     |
| 343 | TrainingPipeline.cross_validate() per-fold scores     | kailash-ml     | feat | **P0**   | Medium      |
| 344 | Clustering engine                                     | kailash-ml     | feat | **P1**   | Medium-High |
| 345 | Dimensionality reduction engine                       | kailash-ml     | feat | **P1**   | Medium      |
| 346 | Text feature extraction in FeatureStore               | kailash-ml     | feat | **P1**   | Medium      |
| 347 | classification_report equivalent                      | kailash-ml     | feat | **P2**   | Low         |
| 348 | Anomaly detection engine                              | kailash-ml     | feat | **P2**   | Medium-High |

---

## Kaizen Bugs — Verified Against Code

### #339: BaseAgent MCP tool execution broken (3 sub-issues)

**Root cause**: The tool execution pipeline has 3 independent breakpoints that collectively make native tool calling non-functional end-to-end.

#### Sub-issue 1: `convert_mcp_to_openai_tools()` strips `mcp_server_config`

- **File**: `packages/kailash-kaizen/src/kaizen/core/tool_formatters.py:56-112`
- **Verified**: Function extracts only `name`, `description`, `inputSchema` from MCP tools. The `mcp_server_config` (needed to connect back to the MCP server for execution) is discarded.
- **Impact**: `_execute_mcp_tool_call()` at `llm_agent.py:2444` reads `mcp_tool.get("function", {}).get("mcp_server_config", {})` which always returns `{}`. Tool execution fails silently.

**Fix approach**: Preserve `mcp_server_config` in the converted tool dict. The OpenAI format allows extra fields — add it alongside `name`/`description`/`parameters` inside the `function` key.

#### Sub-issue 2: `_execute_regular_tool()` returns mock data

- **File**: `packages/kailash-kaizen/src/kaizen/nodes/ai/llm_agent.py:2585-2592`
- **Verified**: Returns hardcoded `{"status": "success", "result": f"Executed {tool_name}...", "note": "Regular tool execution not yet implemented"}`
- **Zero-tolerance violation**: This is a stub (Rule 2). Either implement real tool execution or raise a clear error.

**Fix approach**: Non-MCP tools registered via `BaseAgent(tools=[...])` need an execution registry. The tool functions should be stored during registration and invoked here. If not implementable now, this method must raise `NotImplementedError` with a clear message, not return fake success.

**Note**: Zero-tolerance Rule 2 says `raise NotImplementedError` is also blocked. The correct fix is to implement actual tool execution — store callable references during tool registration and invoke them.

#### Sub-issue 3: System prompt injects text-based tool instructions alongside native function declarations

- **File**: `packages/kailash-kaizen/src/kaizen/core/base_agent.py:1664-1684`
- **Verified**: `_generate_system_prompt()` always appends "To use a tool, set the 'action' field to 'tool_use'" instructions when `_discovered_mcp_tools` is non-empty. This happens regardless of whether native function declarations are being sent to the provider.
- **Impact**: The LLM sees conflicting instructions — native function calling format (from `tools` parameter) vs text-based ReAct format (from system prompt). It follows the prompt and outputs text-based tool calls, bypassing the native tool execution pipeline entirely.

**Fix approach**: When tools are sent as native function declarations (i.e., `node_config["tools"]` is populated), suppress the text-based tool instructions in the system prompt. The system prompt should document available tools (names + descriptions) but NOT instruct on calling format — the provider's native format handles that.

#### Risk assessment

- **Severity**: High. MCP tool execution is completely broken — agents can discover tools but never execute them.
- **Blast radius**: Any BaseAgent using `mcp_servers=[...]` or `tools=[...]`.
- **Cross-SDK**: Kaizen in kailash-rs uses a different agent architecture (Delegate-based), so this specific bug likely doesn't apply. The tool_formatters pattern may need inspection.

---

### #340: GoogleGeminiProvider response_mime_type + tools crash

**Root cause**: No mutual exclusion between structured output (`response_mime_type: "application/json"`) and tools (`tools=[...]`) on the Gemini API request config.

- **File**: `packages/kailash-kaizen/src/kaizen/nodes/ai/ai_providers.py:3930-3955`
- **Verified**: Lines 3930-3944 set `config_params["response_mime_type"]` when `response_format` is present. Line 3947 builds `request_config` with those params. Line 3955 adds `tools` to the same config. No guard.
- **File**: `packages/kailash-kaizen/src/kaizen/core/workflow_generator.py:286-363`
- **Verified**: Line 287 adds `response_format`, line 363 adds `tools`. Both go into the same `node_config`. No conflict detection.

**Gemini API constraint**: Gemini 2.5 models reject `response_mime_type + tools` together with `400 INVALID_ARGUMENT`. Gemini 3.x models support the combination.

**Fix approach**: In `GoogleGeminiProvider.chat()`, after building `config_params`, check if both `response_mime_type` and `tools` will be present. If so:

- Strip `response_mime_type` and `response_json_schema` from `config_params`
- Log a warning
- The system prompt already contains JSON guidance (added by `workflow_generator.py:293-307`), so structured output is still achievable via prompt

Model-aware gating (Gemini 2.5 vs 3.x) is a refinement but not required for the fix — the safe default is to always prefer tools over structured output format when both are present.

#### Risk assessment

- **Severity**: Medium-High. Crashes any agent using both structured output and tools on Gemini 2.5 (the current GA model family).
- **Blast radius**: GoogleGeminiProvider users with MCP tools. OpenAI and Anthropic providers unaffected.
- **Cross-SDK**: kailash-rs Kaizen doesn't use the same provider layer, but the Gemini API constraint is universal.

---

## ML Features — Verified Against Code

### #341: Expose `kailash_ml.metrics` public module (P0)

**Current state**: No `kailash_ml/metrics.py` exists. Metrics are computed internally via `_shared.compute_metrics_by_name()` which uses a flat if-elif chain supporting 9 metrics: accuracy, f1, precision, recall, auc, mse, rmse, mae, r2.

**What's needed**: A public `kailash_ml.metrics` module re-exporting sklearn metrics as first-class API. Thin wrappers with consistent `(y_true, y_pred)` signatures.

**Implementation approach**:

1. Create `kailash_ml/metrics.py` with classification, regression, clustering metric functions
2. Each wraps the corresponding sklearn function
3. Register in `__init__.py` for public access
4. Reuse in `_shared.compute_metrics_by_name()` (dedup)

**Complexity**: Low-Medium. ~200 lines of wrapper code + tests. No architectural decisions needed.

### #342: Add 3 metrics to compute_metrics_by_name (P0)

**Current state**: `_shared.py:82-160` — 9 metrics via if-elif chain. Missing: `log_loss`, `brier_score_loss`, `average_precision`.

**Implementation**: Add 3 elif branches to `compute_metrics_by_name()`. ~15 lines. Note: `log_loss` and `brier_score_loss` need probability predictions (like `auc`), so they need the `model` + `X_test` parameters.

**Complexity**: Trivial. Can be done in the same PR as #341.

### #343: TrainingPipeline.cross_validate() (P0)

**Current state**: `training_pipeline.py:645-700` — kfold splits exist but `_kfold_first_fold()` returns only the first fold pair. No full CV loop.

**What's needed**: A `cross_validate()` method that:

1. Runs training on ALL k folds (not just first)
2. Returns per-fold metric arrays
3. Returns mean/std aggregates

**Implementation approach**: New method on TrainingPipeline. Uses existing `_split()` infrastructure but iterates all folds. Returns a `CrossValidationResult` dataclass with `fold_scores`, `mean_scores`, `std_scores`.

**Complexity**: Medium. The split infrastructure exists; main work is the CV loop + result aggregation + tests.

### #344: Clustering engine (P1)

**Current state**: No clustering code exists. AutoML rejects `task_type="clustering"`.

**What's needed**: New `ClusterEngine` with KMeans, DBSCAN, GMM, SpectralClustering, HDBSCAN, Agglomerative. Includes evaluation (silhouette, calinski-harabasz, davies-bouldin) and elbow/k-range analysis.

**Implementation approach**: New `cluster_engine.py` following the existing engine pattern. `ClusterSpec` dataclass for algorithm config. polars-native input with sklearn conversion at boundary via interop module.

**Cross-SDK note**: kailash-rs has `kailash-ml-cluster` crate with native KMeans and hierarchical. Python should match API semantics per EATP D6.

**Complexity**: Medium-High. New engine (~400-500 lines) + tests. Multiple algorithms with different APIs (e.g., DBSCAN has no `n_clusters`).

### #345: Dimensionality reduction engine (P1)

**Current state**: PCA exists in `preprocessing.py:1113-1158` (added in v0.7.0) but only as a preprocessing step inside `setup()`. No standalone reduction engine.

**What's needed**: New `ReductionEngine` with PCA, NMF, t-SNE, UMAP, TruncatedSVD, LDA. Returns transformed data + explained variance + loadings.

**Implementation approach**: New `reduction_engine.py`. The existing PCA in preprocessing is a different use case (auto-applied during setup) — this engine is for explicit dimensionality reduction as an analysis step.

**Cross-SDK note**: kailash-rs has `kailash-ml-decomposition` crate. Python should match semantics.

**Dependency note**: UMAP requires `umap-learn` package (optional extra). t-SNE is in sklearn. LDA is in sklearn.

**Complexity**: Medium. Simpler than clustering — fewer algorithm-specific edge cases.

### #346: Text feature extraction (P1)

**Current state**: No text vectorization anywhere. String/UTF8 columns are treated as categorical in preprocessing.

**What's needed**: TF-IDF, CountVectorizer, HashingVectorizer integration. Could live in FeatureStore as `vectorize_text()` or as a standalone preprocessing step.

**Implementation approach**: Add to FeatureStore or preprocessing. The key decision: sparse matrix output (efficient for text) vs dense polars DataFrame (consistent with kailash-ml convention). Recommend sparse + optional `.to_dense()`.

**Cross-SDK note**: kailash-rs has `kailash-ml-text` crate.

**Complexity**: Medium. Sklearn wrappers are straightforward but sparse matrix handling adds complexity.

### #347: classification_report equivalent (P2)

**Current state**: No classification_report function. Confusion matrix and ROC curve exist in ModelVisualizer.

**Implementation**: Thin wrapper around `sklearn.metrics.classification_report()`. Should return both formatted string and dict. Natural fit for the `kailash_ml.metrics` module (#341).

**Complexity**: Low. ~30 lines + tests. Bundle with #341.

### #348: Anomaly detection engine (P2)

**Current state**: No anomaly detection. Only IQR-based outlier removal in preprocessing (data cleaning, not detection).

**What's needed**: `AnomalyEngine` with IsolationForest, LOF, OneClassSVM, EllipticEnvelope. Ensemble detection + threshold tuning.

**Implementation approach**: New `anomaly_engine.py` following engine pattern. `AnomalySpec` for config. Ensemble mode combines multiple detectors via score averaging/voting.

**Complexity**: Medium-High. New engine + ensemble logic + threshold tuning.

---

## Dependency Graph

```
#342 (3 metrics) ──┐
                   ├──→ #341 (metrics module) ──→ #347 (classification_report)
#343 (cross_validate) ─┘

#339 (MCP tool exec) ── independent
#340 (Gemini tools crash) ── independent

#344 (clustering) ── independent new engine
#345 (dim reduction) ── independent new engine
#346 (text extraction) ── independent new engine
#348 (anomaly detection) ── independent new engine
```

## Recommended Execution Order

### Session 1 — Bugs + Quick Wins (parallel)

| Track                          | Issues           | Rationale                                           |
| ------------------------------ | ---------------- | --------------------------------------------------- |
| **Track A: Kaizen bugs**       | #339, #340       | P0 bugs blocking tool execution                     |
| **Track B: ML metrics**        | #341, #342, #347 | P0 metrics + classification_report (natural bundle) |
| **Track C: ML cross-validate** | #343             | P0, independent of metrics work                     |

### Session 2 — New Engines (parallel)

| Track                   | Issues | Rationale                        |
| ----------------------- | ------ | -------------------------------- |
| **Track D: Clustering** | #344   | P1, new engine, cross-SDK parity |
| **Track E: Reduction**  | #345   | P1, new engine, cross-SDK parity |
| **Track F: Text**       | #346   | P1, new engine, cross-SDK parity |

### Session 3 — P2 Engine

| Track                | Issues | Rationale                       |
| -------------------- | ------ | ------------------------------- |
| **Track G: Anomaly** | #348   | P2, new engine, lowest priority |

**Estimated**: 2-3 autonomous execution sessions for all 10 issues.
