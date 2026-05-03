# Red Team Round 3: Test Coverage & Value Audit

**Date**: 2026-04-01
**Scope**: All 5 workspace areas (DataFlow, Nexus, MCP, ML, Align) + Trust (PACT)
**Method**: Manual audit of all test files against source, edge-case coverage analysis, and enterprise buyer value assessment.

---

## Part 1: Test Coverage Audit

### 1.1 DataFlow Tests

#### test_derived_model.py (TSG-100) -- 55 tests

**Covered well:**

- Interval parsing (seconds, minutes, hours, case-insensitive, whitespace, invalid inputs)
- DerivedModelMeta dataclass defaults and custom values
- RefreshResult dataclass variants (default, error, with sources)
- Circular dependency detection (no cycle, self-cycle, two-node cycle, plain source leaf)
- Engine registration (valid, duplicate raises)
- Dependency validation (no cycles, cycles raise)
- Engine status (empty, with models)
- Refresh lifecycle (unregistered model, compute invocation, error tracking, multi-source, empty compute result)
- Scheduler (start/stop, skips manual models, fires refresh)
- Decorator integration (registers model + derived, scheduled without schedule raises, missing compute raises, custom schedule)
- Status and sync variants
- Integration with real SQLite (manual refresh end-to-end, multi-source derived, result metadata)
- on_source_change event subscription (8 per source, multi-source, manual no-sub, missing bus, idempotent)
- on_source_change handler (write triggers recompute, unrelated no-trigger, debounce coalesces, error capture)
- Circular detection for on_source_change models

**Coverage gaps:**

- **GAP-DF-01**: No test for `None` or empty string sources list
- **GAP-DF-02**: No test for very large source datasets (memory pressure / pagination)
- **GAP-DF-03**: No test for concurrent refresh calls to the same derived model
- **GAP-DF-04**: No test for `compute_fn` returning records with missing `id` field
- **GAP-DF-05**: No test for scheduler behavior when engine is stopped mid-refresh
- **GAP-DF-06**: No test for `refresh_derived_sync` on a model not registered (only async path tested)

#### test_file_source_node.py (TSG-102) -- 18 tests

**Covered well:**

- Format auto-detection for all 7 extensions
- Unknown extension error
- Manual format override
- CSV parsing (basic, TSV, skip_rows)
- JSON parsing (list, non-list raises)
- JSONL parsing (basic, blank lines skipped)
- Excel/Parquet lazy import errors
- Column mapping (renames, mapping before coercion)
- Type coercion (int, float, bool with multiple truthy values, coercion failure soft mode)
- File not found error

**Coverage gaps:**

- **GAP-DF-07**: No test for empty CSV file (zero rows after header)
- **GAP-DF-08**: No test for CSV with inconsistent column counts across rows
- **GAP-DF-09**: No test for very large files (streaming behavior / memory)
- **GAP-DF-10**: No test for file_path with spaces or unicode characters
- **GAP-DF-11**: No test for CSV with BOM (byte-order mark)
- **GAP-DF-12**: No test for JSONL with malformed JSON line (not just blank lines)

#### test_validation_dsl.py (TSG-103) -- 12 tests

**Covered well:**

- one_of_validator (valid, invalid, numeric)
- Validation dict parsing (min/max length, email, range, one_of, pattern, custom callable)
- Unknown validator raises
- Config key skipping
- Invalid rules type raises
- Integration with validate_model (dict vs decorator equivalence, valid passes, invalid fails, multiple rules per field)

**Coverage gaps:**

- **GAP-DF-13**: No test for nested validation (model with relationships)
- **GAP-DF-14**: No test for None/missing field values against validators
- **GAP-DF-15**: No test for very long strings against length validators (boundary testing)
- **GAP-DF-16**: No test for validate_on_read config behavior

#### test_retention_engine.py (TSG-106) -- 11 tests

**Covered well:**

- Table name validation (valid/invalid names including SQL injection)
- RetentionPolicy defaults and custom values
- Engine registration (valid, invalid table, invalid archive table)
- Archive table name generation
- Status (empty, with policies)
- RetentionResult dataclass (defaults, dry_run, error)
- Partition policy validation (non-PostgreSQL raises)

**Coverage gaps:**

- **GAP-DF-17**: No test for `engine.run()` with delete or archive policy on real SQLite (only partition tested)
- **GAP-DF-18**: No test for dry_run=True behavior (only dataclass tested, not engine execution)
- **GAP-DF-19**: No test for `after_days=0` edge case
- **GAP-DF-20**: No test for retention on empty tables
- **GAP-DF-21**: No integration test for archive policy (records moved to archive table, then read-back)

#### test_express_cache_wiring.py (TSG-104) -- 15 tests

**Covered well:**

- Cache hit/miss behavior
- Cache set then get round-trip
- TTL=0 bypasses cache (get and set)
- Global TTL=0 disables caching entirely
- Model-scoped invalidation (clears target only, handles no-cache)
- Cache stats structure (with hits/misses, disabled)
- Sync get_cache_stats
- CacheBackendProtocol compliance
- Auto-detection fallback to InMemoryCache
- Key generation (deterministic, different params produce different keys)
- Clear cache (model-scoped, global)
- Reset stats

**Coverage gaps:**

- **GAP-DF-22**: No test for TTL expiry (waiting for cache entry to expire)
- **GAP-DF-23**: No test for concurrent cache access (thread safety)
- **GAP-DF-24**: No test for Redis backend (all tests use InMemoryCache)
- **GAP-DF-25**: No test for cache behavior with None values

#### test_dataflow_events.py (TSG-201) -- 7 tests

**Covered well:**

- WRITE_OPERATIONS constant completeness (all 8)
- Event mixin init creates bus
- Event bus property
- Emit publishes with correct payload field (not `data`)
- Zero-subscriber no-op
- Emit when bus is None
- on_model_change (8 subscriptions, before-connected raises, receives all events)
- hasattr guard backward compat

**Coverage gaps:**

- **GAP-DF-26**: No test for unsubscribing from model changes
- **GAP-DF-27**: No test for event handler that raises (error propagation behavior)

#### test_read_replica.py (TSG-105) -- 16 tests

**Covered well:**

- Single-adapter backward compatibility
- Dual-adapter creation
- Read routing to replica (list, read, count, find_one, search)
- Write routing to primary (create, update, delete, upsert, bulk_create)
- Primary-only access method
- Single-adapter routing (all ops to primary)
- ConnectionManager url_override and pool_size_override
- read_pool_size passthrough
- Health check (single and dual adapter)
- Express/SyncExpress use_primary parameter signatures (8 tests)

**Coverage gaps:**

- **GAP-DF-28**: No integration test that actually reads from replica and writes to primary (all tests are structural/signature checks)
- **GAP-DF-29**: No test for failover behavior when replica is unavailable
- **GAP-DF-30**: No test for use_primary=True actually forcing reads to primary

### 1.2 Nexus Tests

#### test_dataflow_bridge.py (NTR-020) -- 11 tests

**Covered well:**

- Bridge installation (correct subscriptions per model, correct event types, empty models, missing event bus)
- Event translation (domain to nexus event with correct data, all 8 actions translate correctly, unsubscribed type not bridged)
- integrate_dataflow convenience method (returns self, creates bridge)
- Write actions constant alignment with DataFlow

**Coverage gaps:**

- **GAP-NX-01**: No test for bridge with high event volume (throughput/ordering)
- **GAP-NX-02**: No test for bridge teardown/cleanup
- **GAP-NX-03**: No test for event translation with missing payload fields
- **GAP-NX-04**: No integration test with real DataFlow + real Nexus (bridge is tested with fakes only)

### 1.3 MCP Tests (8 test files)

#### test_platform_server.py (MCP-500)

**Covered:** SecurityTier env var gating (Tier 1-4), server creation, contributor list, discovery order.

#### test_execution_tools.py (MCP-509)

**Covered:** Tier 4 tool registration gating (absent by default, present when enabled).

#### test_resources.py (MCP-507)

**Covered:** ResourceCache mtime-based invalidation, caching, thread safety.

#### test_trust_contributor.py, test_pact_contributor.py, test_platform_contributor.py

**Covered:** Contributor registration, tool/resource creation per framework.

#### test_test_generation.py

**Covered:** Test scaffold generation.

#### test_server_enhanced.py

**Covered:** Enhanced server features.

**MCP Coverage gaps:**

- **GAP-MCP-01**: No test for AST scanning accuracy on real Python projects with complex patterns (decorators, metaclasses, dynamic imports)
- **GAP-MCP-02**: No test for platform_map with very large projects (100+ files, nested packages)
- **GAP-MCP-03**: No test for MCP transport layer (stdio, SSE) -- all tests use direct function calls
- **GAP-MCP-04**: No integration test with actual Claude Code client
- **GAP-MCP-05**: No test for error recovery when project root is deleted during scan

### 1.4 ML Tests

#### test_interop.py -- 17 tests

**Covered well:**

- to_sklearn_input (numeric, categorical encoding, boolean, nulls->NaN, no target, auto feature columns, utf8 raises, null column raises)
- from_sklearn_output (restore column names, 1D predictions, round-trip column names)
- polars_to_arrow (basic, schema validation pass/fail)
- to_pandas/from_pandas (numeric, categorical, datetime, nulls, full schema)
- polars_to_dict_records (basic, max_rows exceeded, empty)

#### test_feature_store.py -- 9 integration tests

**Covered well (real SQLite, no mocking):**

- register_features (creates table, idempotent, rejects schema drift)
- compute validation (wrong columns, nullable check, column projection)
- Store+retrieve round-trip with value verification
- Point-in-time correctness (temporal queries at different dates)
- Training set retrieval with time windows
- Lazy retrieval (LazyFrame)
- List multiple schemas

#### test_model_registry.py -- Integration tests with real SQLite

#### test_inference_server.py -- Integration tests with real sklearn models

#### test_drift_monitor.py -- Integration tests with real scipy statistics

#### test_training_pipeline.py -- Integration tests with real sklearn/LightGBM

#### test_hyperparameter_search.py -- Integration tests with real search

**ML Coverage gaps:**

- **GAP-ML-01**: No unit tests for individual engines (ModelRegistry, InferenceServer, DriftMonitor, TrainingPipeline, HyperparameterSearch) -- only integration tests exist
- **GAP-ML-02**: No test for ONNX bridge (OnnxBridge engine) -- no test file found
- **GAP-ML-03**: No test for ExperimentTracker engine
- **GAP-ML-04**: No test for AutoML engine
- **GAP-ML-05**: No test for DataQuality engine
- **GAP-ML-06**: No test for model versioning conflict resolution
- **GAP-ML-07**: No test for inference with missing features (partial input)
- **GAP-ML-08**: No test for drift monitor with categorical features
- **GAP-ML-09**: No test for pipeline failure midway (rollback behavior)
- **GAP-ML-10**: No benchmark tests (bench/ directory is empty)

### 1.5 Align Tests (7 test files)

#### test_config.py -- 30 tests

**Covered well:** LoRAConfig, SFTConfig, DPOConfig, AdapterSignature, AlignmentConfig validation (NaN/Inf, ranges, mutual exclusion, required fields, frozen dataclasses).

#### test_pipeline.py -- 10 tests

**Covered well:** Pipeline init, DPO/SFT+DPO dataset requirements, preference dataset validation (missing columns, empty dataset, empty strings, valid), checkpoint detection, AlignmentResult dataclass.

#### test_evaluator.py -- 13 tests

**Covered well:** TaskResult/EvalResult serialization, EvalConfig defaults, task resolution presets, lm-eval import error, mocked evaluation, results storage in registry, comparison builder.

#### test_merge.py -- 5 tests

**Covered well:** Merge requires registry, idempotent (already merged), rejects exported adapter.

#### test_registry.py, test_exceptions.py, test_package.py

**Covered:** Registry operations, exception hierarchy, package skeleton (version, lazy imports, module structure, py.typed).

**Align Coverage gaps:**

- **GAP-AL-01**: No test for actual model loading/training (all tests mock or skip GPU)
- **GAP-AL-02**: No test for GGUF export pipeline end-to-end
- **GAP-AL-03**: No test for Kaizen bridge (agent alignment integration)
- **GAP-AL-04**: No test for adapter loading/inference after merge
- **GAP-AL-05**: No test for checkpoint resume during training
- **GAP-AL-06**: No test for multi-GPU or distributed training config
- **GAP-AL-07**: No test for dataset format validation beyond preference (instruction datasets)

### 1.6 Trust Tests (PACT)

#### test_shadow_stores.py -- 20 tests

**Covered well (both MemoryShadowStore and SqliteShadowStore):**

- Protocol conformance
- Append and retrieve
- Retrieval order (newest first)
- Filtering (agent_id, since, limit)
- Bounded eviction
- Metrics aggregation (all verdict types)
- Metrics with time window
- Clear
- Thread safety (concurrent writes)
- SQLite persistence across instances
- File permissions (0o600 on POSIX)
- ShadowEnforcer integration (without store, with memory store, with SQLite store, broken store resilience)

#### test_signed_envelope.py -- 12 tests

**Covered well:**

- sign_envelope creates valid SignedEnvelope
- Custom expiry, zero expiry raises
- Frozen dataclass immutability
- Verification (valid signature, wrong key fails, tampered envelope fails, expired fails)
- is_valid non-throwing variant (valid, invalid, garbage key)
- Serialization round-trip (to_dict/from_dict)

**Trust Coverage gaps:**

- **GAP-TR-01**: No test for key rotation scenario (sign with key A, rotate to key B, verify with key A)
- **GAP-TR-02**: No test for signing envelopes with very large constraint sets
- **GAP-TR-03**: No test for concurrent signing/verification (thread safety of crypto operations)

---

## Part 2: Value Audit

_Perspective: skeptical enterprise buyer evaluating whether to adopt each component over existing alternatives._

### 2.1 kailash-ml

**Would a data scientist choose kailash-ml over raw sklearn + MLflow?**

**Partial yes, with caveats.**

The value proposition is genuine for teams already on Kailash: you get a FeatureStore, ModelRegistry, TrainingPipeline, InferenceServer, DriftMonitor, and HyperparameterSearch that share a single ConnectionManager and integrate natively with DataFlow models. The interop module (polars <-> sklearn <-> pandas) is well-designed and tested.

However, for a team NOT already on Kailash, the value is thin:

- **FeatureStore**: Adds value over raw DataFlow through schema validation, temporal point-in-time queries, and compute pipelines. This is a genuine feature store -- not just "DataFlow with extra steps." The point-in-time correctness test proves it handles temporal joins correctly, which is non-trivial.
- **ModelRegistry**: Competes with MLflow Model Registry. Kailash's version is simpler (SQLite-backed, artifact store abstraction), which is good for small teams but lacks MLflow's ecosystem (experiment tracking UI, model serving endpoints, community integrations).
- **DriftMonitor**: Uses PSI (Population Stability Index) with real scipy. Legitimate statistical approach, tested with real distributions. This adds genuine value over rolling-your-own.
- **TrainingPipeline / HyperparameterSearch**: Convenience wrappers around sklearn/LightGBM. Adds value through FeatureStore integration and automatic model registration, but not enough to switch from existing sklearn workflows.

**ONNX bridge reliability**: Cannot assess -- no test file exists for OnnxBridge. This is a **critical gap** if ONNX interop is a selling point. A buyer who chose kailash-ml for ONNX portability would hit undocumented behavior immediately.

**Engine integration**: The 9 engines share ConnectionManager and FeatureStore, which is genuinely useful -- you train from FeatureStore features, register the model, serve inference, and monitor drift without leaving the platform. But 4 engines have no test coverage at all (OnnxBridge, ExperimentTracker, AutoML, DataQuality), which undermines confidence.

**Verdict: B-** -- Genuine integration value for Kailash shops. FeatureStore and DriftMonitor are the strongest selling points. ONNX bridge is untested. Half the engines lack any test coverage.

### 2.2 kailash-align

**Would an ML engineer choose kailash-align over raw TRL scripts?**

**No, not yet.**

The test suite reveals that kailash-align is a well-architected framework that cannot actually train anything in its current test environment. Every test either validates config dataclasses, mocks the training call, or checks error handling. No test loads a model, trains it, or produces an adapter artifact.

This is architecturally sound -- the config validation is thorough (NaN/Inf checks, mutual exclusion, frozen dataclasses), the pipeline dispatch logic is correct, the evaluator integrates properly with lm-eval. But:

- **GGUF pipeline**: No end-to-end test. The merge and export path exists in code but is never verified with a real model. A user following the documentation will discover whether it works at runtime.
- **Kaizen bridge**: No test at all. The "use kailash-align with Kaizen agents" story is entirely untested.
- **Adapter loading after merge**: Untested. You can merge an adapter (idempotent check works), but nobody has verified the merged model produces correct inference.
- **Checkpoint resume**: Untested. The `_find_checkpoint` method is tested (finds latest checkpoint-N directory), but no test verifies that training actually resumes from a checkpoint.

The value proposition against TRL is: managed adapter lifecycle (AdapterRegistry with versioning, merge status tracking, GGUF export tracking, evaluation results storage). This is genuine -- TRL has no adapter registry. But the buyer must trust the training pipeline works without test evidence.

**Verdict: C+** -- Strong architecture and config validation, but the core value (training + export) is unverified. An ML engineer would need to run a smoke test before committing.

### 2.3 MCP Platform Server

**Would a developer add kailash-mcp to their Claude Code config?**

**Yes, conditionally.**

The tiered security model (Introspection -> Scaffold -> Validation -> Execution) is well-designed and properly gated by environment variables. The platform_server correctly registers contributors in order and gates Tier 4 (execution) behind explicit opt-in.

**AST scanning**: The ResourceCache (mtime-based invalidation, thread-safe) is solid. However, no test verifies AST scanning accuracy on real projects. The platform_map tool's value depends entirely on how well it parses decorators, metaclasses, and dynamic patterns -- and this is untested.

**platform_map value**: For a developer working on a Kailash project, having their models, workflows, handlers, and agents discoverable through MCP is genuinely valuable. Claude Code can see "this project has 5 DataFlow models, 3 Nexus handlers, 2 Kaizen agents" and provide contextually-aware assistance. This is a real differentiator over generic MCP servers.

But the platform_map is ONLY useful for Kailash projects. A developer not using Kailash gets zero value. This is fine -- it is explicitly a Kailash platform server.

**Missing**: No end-to-end test with a real MCP client. All tests call functions directly. A developer adding this to `claude_desktop_config.json` is trusting that the stdio/SSE transport works correctly.

**Verdict: B** -- Genuine value for Kailash developers. Security model is properly implemented. AST scanning accuracy is the biggest risk (untested on complex real-world code).

### 2.4 DataFlow Enhancements

**DerivedModelEngine (TSG-100): Does it solve a real problem?**

**Yes.** Materialized views are a real need, and doing them in Python (vs PostgreSQL `CREATE MATERIALIZED VIEW`) means they work on SQLite too. The three refresh modes (manual, scheduled, on_source_change) are well-designed. The event-driven refresh with debounce is particularly well-tested. This solves a real pain point: "I want an OrderSummary table that auto-updates when Orders change."

**Risk**: The integration tests use string types for all numeric fields (`"100.0"` instead of `100.0`), suggesting the engine may have issues with numeric type coercion. A buyer who tries `amount: float` in their derived model may hit unexpected behavior.

**ReadReplica support (TSG-105): Does it work without complex configuration?**

**Partially.** The API is clean: `DataFlow(url, read_url="replica://...")`. Routing logic is correct (reads to replica, writes to primary). But every test is structural -- no test actually executes a query through the routing layer. A buyer has zero evidence that `read_url` actually sends queries to the replica database.

**Validation DSL (TSG-103): Is it easier than @field_validator decorators?**

**Yes, for simple cases.** The declarative dict syntax (`{"name": {"min_length": 2, "max_length": 50}}`) is more concise than decorator-based validation. The integration test proves both approaches produce identical outcomes. For non-technical users (COC target audience), the dict approach is more accessible.

**Risk**: No support for conditional validation, cross-field validation, or async validators. Complex validation still requires decorators. The DSL covers ~70% of common cases.

**Verdict: B+** -- DerivedModelEngine is the standout feature with strong test coverage. ReadReplica needs integration tests. Validation DSL is a nice convenience.

### 2.5 Trust (PACT additions)

**ShadowStore (Issue #206)**

**Strong.** Both MemoryShadowStore and SqliteShadowStore are thoroughly tested: protocol conformance, bounded eviction, thread safety, persistence, metrics aggregation, time-windowed queries, file permissions, and integration with ShadowEnforcer. The broken-store resilience test (store failure does not block enforcement) is exactly right for a security component.

**SignedEnvelope (Issue #207)**

**Strong.** Ed25519 signing, expiry, tamper detection, serialization round-trip, and frozen immutability are all tested. The is_valid() non-throwing variant handles garbage keys correctly. This is a well-tested security primitive.

**Verdict: A-** -- Both additions are production-ready with security-appropriate test coverage. Missing only key-rotation and concurrency tests.

---

## Convergence: Overall Readiness Assessment

### Summary Table

| Workspace             | Tests | Coverage Quality                    | Value Grade | Ship-Ready?                                |
| --------------------- | ----- | ----------------------------------- | ----------- | ------------------------------------------ |
| DataFlow enhancements | 134   | B+ (solid, gaps in integration)     | B+          | Yes, with caveats                          |
| Nexus bridge          | 11    | B (fakes only, no real integration) | B           | Yes, for event-aware Nexus users           |
| MCP platform server   | ~40   | B- (no real client test)            | B           | Yes, for Kailash developers                |
| kailash-ml            | ~60   | C+ (4 engines untested)             | B-          | No -- ONNX bridge and 4 engines need tests |
| kailash-align         | ~65   | C (no real training test)           | C+          | No -- needs one real training smoke test   |
| Trust (PACT)          | 32    | A- (thorough, security-appropriate) | A-          | Yes                                        |

### Critical Gaps Requiring Immediate Action

1. **kailash-ml OnnxBridge**: No test file exists. If ONNX is a selling point, it needs at least a smoke test with a small ONNX model.
2. **kailash-ml AutoML, ExperimentTracker, DataQuality engines**: Zero test coverage for 3 of 9 engines. A buyer inspecting test coverage would flag this immediately.
3. **kailash-align real training**: Not a single test loads a model or produces an adapter. One smoke test with a tiny model (distilgpt2 + 10 samples) would provide confidence.
4. **ReadReplica integration**: 16 tests, all structural. One test that writes via primary and reads via replica would close the gap.

### Positive Findings

1. **DataFlow DerivedModelEngine**: Best-in-class coverage with 55 tests covering unit, integration, decorator, scheduler, and event-driven refresh paths.
2. **Trust components**: Security-appropriate testing (thread safety, broken-store resilience, file permissions, tamper detection).
3. **DataFlow FeatureStore**: Real SQLite integration tests with point-in-time correctness verification -- this is how ML feature stores should be tested.
4. **Align config validation**: Thorough NaN/Inf/boundary testing on all numeric fields -- follows trust-plane-security patterns.
5. **All tests use state persistence verification**: Write operations are followed by read-back assertions, consistent with testing rules.

### Recommendation

**Ship DataFlow, Nexus bridge, MCP, and Trust.** These have acceptable test coverage for their maturity level.

**Hold kailash-ml and kailash-align** until:

- ML: OnnxBridge smoke test + one test per untested engine
- Align: One real training smoke test (can be gated behind `@pytest.mark.slow` for CI)

Total gap count: 37 specific missing test cases identified across all workspaces.
