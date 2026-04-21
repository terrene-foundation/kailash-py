# Round-4 /redteam — Implementation Feasibility Auditor (Post-Phase-D)

**Persona:** Implementation Feasibility Auditor
**Date:** 2026-04-21
**Inputs:**

- `round-3-feasibility.md` (9 HIGH + 9/15 READY after Phase-C)
- `round-3-SYNTHESIS.md`
- 15 `specs-draft/ml-*.md` (16,479 LOC — up from 14,030 LOC at Round-3; +2,449 LOC from Phase-D)
- 6 `supporting-specs-draft/*-ml-integration-draft.md` (2,454 LOC total; align/dataflow/kailash-core/kaizen/nexus/pact)

**Gate question:** Can an autonomous agent today open a worktree, pick one shard, and write the code without stopping to ask a question?

**Summary verdict:** **NOT YET 21/21 READY.** 7 HIGHs closed by Phase-D. **3 Round-3 HIGHs remain OPEN (B3, B4, B9).** 1 new HIGH surfaced from the Phase-D edits themselves (N1, cross-spec DDL prefix drift). 1 new partial-close HIGH surfaced from the A10-3 split across ml-serving/ml-registry (B11 residue — the register-time ONNX probe is referenced but not defined). Target 21/21 READY remains reachable in one more focused spec-edit pass (~75 min).

---

## Section A — Per-Spec Feasibility Scorecard (Re-scored Round-4, full 21-spec surface)

Legend: `Y` complete / `P` partial / `N` missing. Verdict: READY / NEEDS-PATCH / BLOCKED.

### A.1 — Core 15 ml specs

| Spec                          | Sigs | Dataclasses                                                            | Invariants | Schemas (DDL)                                                                          | Errors            | Extras           | Migration         | Senior-practitioner HIGHs           | **Round-4 Verdict**                                                                 |
| ----------------------------- | ---- | ---------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------- | ----------------- | ---------------- | ----------------- | ----------------------------------- | ----------------------------------------------------------------------------------- |
| ml-tracking-draft             | Y    | Y                                                                      | Y          | Y (8 CREATE TABLE)                                                                     | Y (13)            | Y                | Y                 | Y                                   | **READY**                                                                           |
| ml-autolog-draft              | Y    | Y                                                                      | Y          | N/A                                                                                    | Y (5)             | Y                | N/A               | Y                                   | **READY**                                                                           |
| ml-diagnostics-draft          | Y    | Y                                                                      | Y          | N/A                                                                                    | Y                 | Y                | N/A               | Y                                   | **READY**                                                                           |
| ml-backends-draft             | Y    | Y                                                                      | Y          | N/A                                                                                    | Y (3)             | Y                | N/A               | Y                                   | **READY**                                                                           |
| ml-registry-draft             | Y    | Y                                                                      | Y          | **Y — 4 CREATE TABLE blocks §5A.2 + SQLite variant §5A.3 + Tier-2 tests §5A.4**        | Y (13)            | Y                | Y                 | **P (A10-3 probe — see B11′)**      | **NEEDS-PATCH** (B11′: register-time ONNX probe referenced but not defined; 25 min) |
| ml-drift-draft                | Y    | Y                                                                      | Y          | Y (4 CREATE TABLE)                                                                     | Y (9)             | Y                | N/A               | Y                                   | **NEEDS-PATCH** (N1 prefix drift — uses `_kml_*` where siblings use `kml_*`; 5 min) |
| ml-serving-draft              | Y    | Y (BatchInferenceResult, StreamingInferenceSpec, OnnxExportUOpsError)  | Y          | **Y — 3 CREATE TABLE §9A.2 + SQLite §9A.3 + Tier-2 tests §9A.4**                       | Y (12)            | Y ([grpc] noted) | Y (§12 inventory) | **Y — A3-3, A7-3, A10-1/2/3 all Y** | **READY**                                                                           |
| ml-feature-store-draft        | Y    | Y                                                                      | Y          | **Y — 4 CREATE TABLE §10A.2 + SQLite §10A.3 + Tier-2 tests §10A.4**                    | Y (10)            | Y                | N/A               | Y                                   | **READY**                                                                           |
| ml-dashboard-draft            | Y    | Y                                                                      | Y          | N/A                                                                                    | Y (12)            | Y                | N/A               | —                                   | **READY**                                                                           |
| ml-automl-draft               | Y    | Y                                                                      | Y          | **Y — `kml_automl_agent_audit` CREATE TABLE §8A.2 + SQLite §8A.3 + Tier-2 test §8A.4** | Y (9)             | Y                | N/A               | Y                                   | **READY**                                                                           |
| ml-rl-core-draft              | Y    | Y                                                                      | Y          | N/A                                                                                    | Y (10)            | Y                | Y                 | Y                                   | **READY**                                                                           |
| ml-rl-algorithms-draft        | Y    | Y                                                                      | Y          | N/A                                                                                    | P (inherits core) | Y                | N/A               | Y                                   | **READY**                                                                           |
| ml-rl-align-unification-draft | Y    | Y                                                                      | Y          | N/A                                                                                    | P                 | Y                | Y                 | Y                                   | **READY**                                                                           |
| ml-engines-v2-draft           | Y    | Y                                                                      | Y          | N/A (defers)                                                                           | Y (9)             | Y                | Y                 | Y                                   | **NEEDS-PATCH** (B9 AutoMLEngine demotion-vs-first-class still conflicts; 15 min)   |
| ml-engines-v2-addendum-draft  | Y    | **N — `EngineInfo` + `LineageGraph` still pseudocode at §E10.2/E11.1** | Y          | N/A                                                                                    | P                 | N                | P                 | —                                   | **NEEDS-PATCH** (B3, B4 unchanged since Round-3; 50 min)                            |

### A.2 — 6 supporting-spec integrations (scored for the first time at Round-4)

| Spec                                                               | Sigs | Dataclasses                                                       | Invariants | Cross-Refs                                                      | Errors                          | Test Contract                                    | **Round-4 Verdict** |
| ------------------------------------------------------------------ | ---- | ----------------------------------------------------------------- | ---------- | --------------------------------------------------------------- | ------------------------------- | ------------------------------------------------ | ------------------- |
| align-ml-integration-draft (Target: kailash-align 1.0.0)           | Y    | 0 (inherits RLLifecycleProtocol + DeviceReport from ml specs)     | Y          | Y (cites ml-rl-align-unification §2, ml-backends DeviceReport)  | Y (5)                           | Y (Tier 1/2/3 matrix §6)                         | **READY**           |
| dataflow-ml-integration-draft (Target: kailash-dataflow 2.1.0)     | Y    | 0 (extends existing dataflow surface)                             | Y          | Y (cites ml-feature-store §6.2)                                 | Y (6)                           | Y (Tier 2 polars/SQL-safety tests)               | **READY**           |
| kailash-core-ml-integration-draft (Target: kailash 2.8.11 → 2.9.0) | Y    | Y (RLDiagnostic Protocol, DiagnosticReport frozen dc)             | Y          | Y (cites ml-diagnostics §2.3, MultiTenantOpError Decision 12)   | Y (16-family MLError hierarchy) | Y                                                | **READY**           |
| kaizen-ml-integration-draft (Target: kailash-kaizen 2.12.0)        | Y    | Y (CostTracker microdollar wire format, TraceExporter SQLiteSink) | Y          | Y (cites kailash-core-ml-integration §2 for Protocol expansion) | Y (4)                           | Y                                                | **READY**           |
| nexus-ml-integration-draft (Target: kailash-nexus 1.1.0)           | Y    | Y (DashboardPrincipal)                                            | Y          | Y (cites ml-dashboard §4.1)                                     | Y (4)                           | Y                                                | **READY**           |
| pact-ml-integration-draft (Target: kailash-pact 1.1.0)             | Y    | Y (3 dataclasses: admission, clearance, cross-tenant op)          | Y          | Y (cites ml-automl Decision 3 agent-infused audit)              | Y (4)                           | Y (Tier 1 + Tier 2 + cross-SDK parity test §6.3) | **READY**           |

**Round-4 summary:** **17 READY / 4 NEEDS-PATCH / 0 BLOCKED out of 21 specs.**

**Progress:**

- Round-2b: 4 READY / 11 NEEDS-PATCH / 0 BLOCKED (of 15 core; supporting not yet drafted)
- Round-3: 9 READY / 6 NEEDS-PATCH / 0 BLOCKED (of 15 core)
- Round-4: 17 READY / 4 NEEDS-PATCH / 0 BLOCKED (of 21 — 15 core + 6 supporting)

---

## Section B — Phase-D Verification of Round-3 HIGHs

Per the gate question in the round-3 report. Evidence lines cited from the spec files.

### B3 (STILL OPEN). `EngineInfo` dataclass body

**Verdict at Round-3:** OPEN — pseudocode-only at lines 394-402 of ml-engines-v2-addendum.
**Round-4 re-verify:** `ml-engines-v2-addendum-draft.md` is still 510 lines (unchanged from Round-3). `grep -n '@dataclass|class EngineInfo|class MethodSignature|class ParamSpec' ml-engines-v2-addendum-draft.md` → **0 matches**. The example at §E11.1 line 394-402 remains a Python comment block. The formal `@dataclass(frozen=True)` blocks that Round-3 specified for `ParamSpec`, `MethodSignature`, and `EngineInfo` did NOT land in Phase-D.

**Verdict:** **STILL OPEN.** 20-min fix; no new surface area. Blocks `kaizen-ml-integration-draft.md` consumer — Kaizen agent tool discovery cannot be implemented without the typed shape.

### B4 (STILL OPEN). `LineageGraph` dataclass body

**Round-4 re-verify:** `§E10.2` lines 360-370 still list 7 fields in a bullet list. `grep -n '@dataclass|class LineageGraph|class LineageNode|class LineageEdge' ml-engines-v2-addendum-draft.md` → **0 matches**. The `LineageNode`, `LineageEdge`, `LineageGraph` frozen-dataclass definitions Round-3 specified did NOT land.

**Cross-spec impact:** `ml-dashboard-draft.md §4.1` (`/api/v1/lineage/{run_id}`) cannot pin its REST JSON-serialization contract without this shape. Reader-side pseudocode in `ml-dashboard-draft.md` matches the bullet list but has no JSON serialization test to fail against.

**Verdict:** **STILL OPEN.** 30-min fix; cross-spec consistency blocker between engines-v2-addendum and ml-dashboard.

### B6 (CLOSED). ml-serving shadow/batch/audit table DDL

**Evidence:** `ml-serving-draft.md §9A.2` (line 819-869) defines 3 `CREATE TABLE` blocks: `kml_shadow_predictions`, `kml_inference_batch_jobs`, `kml_inference_audit`. §9A.3 (line 871-883) documents SQLite variant substitutions. §9A.4 (line 885-891) documents three Tier-2 schema-migration tests (`test_kml_shadow_predictions_schema_migration.py`, `test_kml_inference_batch_jobs_schema_migration.py`, `test_kml_inference_audit_schema_migration.py`). Status vocab `{PENDING, RUNNING, FINISHED, FAILED, KILLED}` matches Decision 1.

**Verdict:** **CLOSED.**

### B7 (CLOSED, with minor scope reduction). ml-feature-store table DDL

**Evidence:** `ml-feature-store-draft.md §10A.2` (line 562-607) defines 4 `CREATE TABLE` blocks: `kml_feature_groups`, `kml_feature_versions`, `kml_feature_materialization`, `kml_feature_audit`. SQLite variant §10A.3 and Tier-2 tests §10A.4 present.

**Design decision from Phase-D:** The Round-3 HIGH listed `_kml_feature_group_history` and `_kml_feat_{name}_v{version}` template tables. Phase-D consolidated the version-history concern into `kml_feature_versions` (append-only via the `UNIQUE (feature_group_id, version_sha)` constraint — same immutability contract) + materialization state into `kml_feature_materialization`. The per-feature-group tables `_kml_feat_*` are still discussed in prose (§5.3 composite-index MUST, §6.2, §8.1a) but have no DDL template in §10A.2 — this is acceptable because per-group DDL is a caller-side template that varies by feature schema, not a static DDL.

**Verdict:** **CLOSED** (design delta accepted — the four static tables are defined; the dynamic per-group template is caller-generated).

### B9 (STILL OPEN). AutoMLEngine legacy-vs-first-class conflict

**Round-4 re-verify:**

- `ml-engines-v2-draft.md §8.2` line 1488: `| from kailash_ml import AutoMLEngine | engine.compare() → .finalize() |` — still listed in the v0.9.x→v2.0 demotion table.
- `ml-engines-v2-draft.md §8.3` line 1505: "`FeatureStore, ModelRegistry, ExperimentTracker, InferenceServer, DriftMonitor`" preserved — `AutoMLEngine` is NOT in the preserved list.
- `ml-automl-draft.md §2.1` line 50: `from kailash_ml import AutoMLEngine` used as first-class public API.

The two specs still contradict. A user following ml-engines-v2 will `from kailash_ml.legacy import AutoMLEngine` with a deprecation warning; a user following ml-automl will `from kailash_ml import AutoMLEngine` and expect it to be first-class. Both cannot be true in the published 1.0.0 package.

**Similarly for EnsembleEngine:** `ml-engines-v2-draft.md §8.2` line 1491 demotes `from kailash_ml import EnsembleEngine → kailash_ml.primitives.Ensemble`, while `ml-automl-draft.md §7.1` uses `from kailash_ml import Ensemble` (as a top-level re-export). The demotion-row reads as though the top-level `Ensemble` is ALSO demoted; the distinction Round-3 called for (demote `EnsembleEngine`, keep `Ensemble` top-level) was not applied.

**Verdict:** **STILL OPEN.** 15-min fix: delete the `AutoMLEngine` row from §8.2, move `AutoMLEngine` into §8.3 preserved list; clarify §8.2 `EnsembleEngine` demotion as engine-class-only (top-level `Ensemble` survives via §8.3).

### B11 (SPLIT: mostly CLOSED, partial residue B11′). ml-serving A10 items

- **A10-1 padding strategy** — **CLOSED.** §4.1.1 `padding_strategy: Literal["bucket", "pad_to_max", "dynamic", "none"] = "bucket"` on `BatchInferenceRequest` and echoed on `BatchInferenceResult` (line 403, 427, 437). Per-strategy waste computation §4.1.3 (line 477) + length-bucket defaults `DEFAULT_LENGTH_BUCKETS = (64, 128, 256, 512, 1024, 2048, 4096, 8192)` §4.1.2 line 458 + Tier-2 test `test_predict_batch_padding_strategy_contract.py` line 486 + four test assertions §4.1.5 line 488-491.
- **A10-2 streaming backpressure** — **CLOSED.** §5.2.1 `StreamingInferenceSpec` dataclass at line 543-549 with `max_buffered_chunks: int = 256`, `abort_on_disconnect: bool = True`. Backpressure contract §5.3 (lines 557-562): pause producer, emit `stream.backpressure.paused` event, resume at 50% watermark. Client-disconnect semantics §5.3.1 (line 576-584): abort + reason in audit. Test coverage §5.3.2 (line 590-593).
- **A10-3 ONNX export probe** — **PARTIALLY CLOSED, residue B11′.** §2.5.2 OnnxExportUnsupportedOpsError dataclass + load-time raise (line 224-232). §2.5.1 step 3 (line 216): "if the model was tagged by the registry with `unsupported_ops: list[str]` (non-empty — set when `register_model(format="onnx")` probed and recorded unsupported ops; see `ml-registry-draft.md §4`), the server MUST raise ..." — this references ml-registry §4. **However, `ml-registry-draft.md §4` is the aliases section, NOT a probe section.** `grep -n 'onnx|unsupported_ops|opset_imports|register_model.*onnx|torch\.onnx\.export' ml-registry-draft.md` returns matches only for the format enum and artifact CAS — NO register-time probe, NO `unsupported_ops` column, NO MUST rule for running the probe. The cross-reference is broken. See B11′ below.

**Verdict:** A10-1 + A10-2 CLOSED. A10-3 **HAS A BROKEN CROSS-REFERENCE** — see HIGH B11′.

### B12 (CLOSED). Prometheus histogram bucket boundaries

**Evidence:** `ml-serving-draft.md §3.2.2` line 344-349 defines `LATENCY_BUCKETS_MS: tuple[float, ...]` with 16 explicit bounds covering 1ms→5min (spanning online-classical through LLM TTFT). Bound to 6 metric families (line 357-364). Cardinality budget §3.2.3 (line 366-370) pins 16 buckets × 3 tenant-classes × 2 model-classes = 96-series cap, validated at construction with `MetricCardinalityBudgetExceededError`. Tier-2 test binding §3.2.4 asserts `histogram_quantile(0.99, ...)` returns finite on a 60-second LLM-first-token-at-35s stream.

**Verdict:** **CLOSED.**

### B13 (CLOSED). Streaming token-metric split

**Evidence:** `ml-serving-draft.md §5.4` line 605-630 replaces the composite `tokens_per_sec` histogram with 4 distinct metric families: `ml_inference_stream_first_token_latency_ms` (histogram, TTFT — user-facing SLO), `ml_inference_stream_subsequent_token_latency_ms` (histogram, ITL — throughput), `ml_inference_stream_total_tokens_total` (counter, labeled by `direction in {input, output}` — cost accounting), `ml_inference_stream_duration_ms` (histogram — capacity planning). Grafana-side derivation documented line 630. Four operational counters (retained) for disconnect reason / backpressure / padding waste / active-streams listed 616-621.

**Verdict:** **CLOSED.**

### B14 (CLOSED). ml-registry DDL

**Evidence:** `ml-registry-draft.md §5A.2` line 235-295 defines 4 `CREATE TABLE` blocks: `kml_model_versions`, `kml_model_aliases`, `kml_model_audit`, `kml_cas_blobs`. SQLite variant §5A.3 (line 297-311). Tier-2 schema-migration tests §5A.4 (line 313-319) — three tests, one per mutation-observable table, asserting UNIQUE constraints + FK references + partial-index rewriting + action-vocab round-trip.

**Verdict:** **CLOSED.**

### B15 (CLOSED). ml-automl audit-table DDL

**Evidence:** `ml-automl-draft.md §8A.2` line 505-524 defines `CREATE TABLE kml_automl_agent_audit` with `(tenant_id, automl_run_id, trial_number, agent_kind, agent_model_id, actor_id, pact_decision, pact_reason, proposed_config, budget_microdollars, actual_microdollars, outcome, occurred_at)` and composite index `idx_automl_agent_tenant_run`. SQLite variant §8A.3 (line 526-535). Tier-2 test §8A.4 (line 537-539) asserts status vocab `{FINISHED, FAILED, KILLED, PENDING}` + `pact_decision` vocab + index existence + `quote_identifier()` routing (Rule 5 loop).

**Verdict:** **CLOSED.**

**Phase-D tally:** **7 Round-3 HIGHs CLOSED** (B6, B7, B11 A10-1, B11 A10-2, B12, B13, B14, B15 — counting the A10 items as 1 compound HIGH). **3 Round-3 HIGHs STILL OPEN** (B3, B4, B9). **1 partial-close residue** (B11′ — register-side of A10-3).

---

## Section C — NEW HIGH Findings From Phase-D

Phase-D added ~2,449 LOC of DDL + SQLite variants + Tier-2 tests across 5 specs. Two new HIGHs surface from the sibling-sweep required by `rules/specs-authority.md` §5b.

### N1 (NEW Round-4 HIGH). Cross-Spec DDL Prefix Drift `kml_*` vs `_kml_*`

The DDL that landed in Phase-D uses `kml_*` (no leading underscore) table names consistently in **5 of 6** DDL-emitting specs:

- `ml-tracking-draft.md` — 8 tables, all `kml_*` (line 565+)
- `ml-serving-draft.md` — 3 tables, all `kml_*` (line 819+)
- `ml-feature-store-draft.md` — 4 tables, all `kml_*` (line 562+)
- `ml-automl-draft.md` — 1 table, `kml_*` (line 507)
- `ml-registry-draft.md` — 4 tables, all `kml_*` (line 235+)

But **`ml-drift-draft.md` alone** uses `_kml_*` (leading underscore) in its 4 `CREATE TABLE` blocks (line 203, 314, 456, 516). Additionally, the PROSE in all 6 specs (including the Phase-D Phase-D resolution-banner prose at the top of each new §) still references tables as `_kml_*` — so every Phase-D-edited spec contains an INTERNAL inconsistency between its prose (`_kml_*`) and its DDL (`kml_*`). Counts from `grep -c "_kml_"`:

- ml-serving: 18 `_kml_*` prose references, DDL uses `kml_*`
- ml-drift: 30 `_kml_*` both prose AND DDL
- ml-registry: 46 `_kml_*` prose references, DDL uses `kml_*`
- ml-feature-store: 18 `_kml_*` prose references, DDL uses `kml_*`
- ml-tracking: 5 `_kml_*` prose references, DDL uses `kml_*`
- ml-automl: 4 `_kml_*` prose references, DDL uses `kml_*`

Cross-spec impact: ml-drift line 594 asserts "Shadow divergence feeds from `_kml_shadow_predictions`" but ml-serving §9A.2 defines `kml_shadow_predictions` (no leading underscore). A caller reading ml-drift will write `SELECT * FROM _kml_shadow_predictions` and receive "relation does not exist".

This violates `rules/dataflow-identifier-safety.md` Rule 2 — the caller's prefix regex `^[a-zA-Z_][a-zA-Z0-9_]*$` must validate against ONE canonical prefix. Two prefixes in one codebase means two call sites of `quote_identifier()` with different validator assumptions; the intent is one.

**Required fix:** pick ONE canonical prefix for the entire ml package. Based on the majority vote (5/6 specs use `kml_*`, 1/6 uses `_kml_*`), the canonical MUST be `kml_*`. Three edits land in one commit:

1. Rewrite ml-drift DDL `_kml_drift_*` → `kml_drift_*` (4 CREATE TABLE blocks).
2. Rewrite ml-drift prose `_kml_*` → `kml_*` (30 references — sed-scriptable).
3. Rewrite prose `_kml_*` → `kml_*` in the other 5 DDL-emitting specs (91 total references across 5 files).

Alternative canonical: `_kml_*` (the minority form). Would match the leading-underscore convention used for private/internal symbols in Python `__all__` hygiene — but the cost is 5x the edits (5 DDL blocks + 18+46+18+5+4 prose references) AND the `kml_*` form is already what Phase-D authors converged on.

**Verdict:** HIGH (30 min — sed-driven; 1 small decision + mechanical global edit).

### B11′ (NEW Round-4 HIGH — Phase-D residue). ml-registry register-time ONNX probe absent

Phase-D landed the consumer side of A10-3 correctly in ml-serving §2.5 but left the producer side undefined in ml-registry. The chain:

1. `ml-serving-draft.md §2.5.1` step 3 (line 216): "If the model was tagged by the registry with `unsupported_ops: list[str]` (non-empty — set when `register_model(format="onnx")` probed and recorded unsupported ops; see `ml-registry-draft.md §4`), the server MUST raise `OnnxExportUnsupportedOpsError(...)`."
2. `ml-registry-draft.md §4` = **"Aliases — Semantic Pointers to Versions"** — NOT about ONNX probe.
3. `grep -n 'onnx|ONNX|OnnxExport|unsupported_ops|torch\.onnx\.export' ml-registry-draft.md` returns matches only for (a) sibling-spec cross-reference, (b) the format enum `Literal["onnx", "torchscript", "gguf", "pickle"]`, and (c) cross-runtime serving prose. **No probe, no `unsupported_ops` column in `kml_model_versions`, no MUST rule for running the probe at register time.**

A caller following the ml-serving contract expects ml-registry to ship with:

- `kml_model_versions.unsupported_ops TEXT[]` column (Postgres) / `unsupported_ops TEXT` JSON (SQLite).
- A `ModelRegistry.register_model(format="onnx")` MUST Rule: "run `torch.onnx.export(model, dummy_input, strict=True)` eagerly; capture the set of unsupported ops; persist to `unsupported_ops`. Failure with an empty op-set = `OnnxInvalidExportError`."
- A server-side contract that `unsupported_ops IS NULL` (not probed) is distinguishable from `unsupported_ops = []` (probed, empty — success).

The A10-3 test in §2.5.4 (`test_inference_onnx_unsupported_ops_enumeration.py`) assumes the probe ran — it registers a torch model using FlashAttention-2 and asserts the registry tagged `unsupported_ops=["FlashAttentionForward"]`. Without the probe MUST-rule, this test has no implementation contract to bind to.

**Required fix:** add `ml-registry-draft.md §11.2` (or a new §5.x adjacent to `§5A.2` where registry DDL lives) titled "ONNX Custom-Op Probe" with:

1. Column addition to `kml_model_versions`: `unsupported_ops JSONB` (Postgres) / `unsupported_ops TEXT` (SQLite).
2. MUST Rule: `register_model(format="onnx")` MUST eager-call `torch.onnx.export(..., strict=True)` in a subprocess (avoid polluting the parent process with optional deps). Capture the set of ops the export rejected; persist to `unsupported_ops`. On subprocess failure, raise `OnnxInvalidExportError(model_name, export_error)`.
3. MUST Rule: `unsupported_ops = NULL` on registration with `format != "onnx"`. Not a probe-skipped signal.
4. Tier-2 test: `test_kml_model_registry_onnx_probe.py` — registers a torch model using FlashAttention-2 → `unsupported_ops=["FlashAttentionForward"]` persisted; registers a model WITHOUT custom ops → `unsupported_ops=[]` persisted.
5. Update §5A.2 `kml_model_versions` DDL to include the `unsupported_ops` column.
6. Fix ml-serving §2.5.1 line 216 cross-reference: `see ml-registry-draft.md §11.2` (or wherever the probe section lands).

**Verdict:** HIGH (25 min — one new section + 1 column + 1 test + 1 cross-ref fix).

---

## Section D — 29 Senior-Practitioner HIGH Re-Verification (Round-3 tally updated)

Of the 29 original HIGHs, Round-3 tallied 25 RESOLVED / 4 OPEN (all 4 in ml-serving: A3-3, A7-3, A10-1, A10-2, A10-3 — counting the A10 trio as 3).

**Round-4 update:** All 5 ml-serving A10-series items are CLOSED in ml-serving itself (A3-3, A7-3, A10-1, A10-2, A10-3 consumer-side). A10-3 producer-side (register-time probe in ml-registry) is the new residue B11′ above.

| Finding ID | Area                         | Round-4 status               | Evidence                                                                        |
| ---------- | ---------------------------- | ---------------------------- | ------------------------------------------------------------------------------- |
| A3-3       | Prometheus buckets           | **RESOLVED**                 | ml-serving §3.2.2 — 16 explicit bounds + 96-series cap + Tier-2 test            |
| A7-3       | Token metric split           | **RESOLVED**                 | ml-serving §5.4 — 4 distinct metric families + Grafana derivation doc           |
| A10-1      | Padding strategy             | **RESOLVED**                 | ml-serving §4.1.1 + DEFAULT_LENGTH_BUCKETS + 4 test assertions                  |
| A10-2      | Streaming backpressure       | **RESOLVED**                 | ml-serving §5.2.1 StreamingInferenceSpec + §5.3 backpressure contract           |
| A10-3      | ONNX export probe (serving)  | **RESOLVED (consumer side)** | ml-serving §2.5 OnnxExportUnsupportedOpsError + load-time raise                 |
| A10-3′     | ONNX export probe (registry) | **OPEN — B11′ residue**      | ml-registry has no §4 probe; cross-reference from ml-serving line 216 is broken |

**Tally:** 28 of 29 RESOLVED. 1 partial-close (A10-3 producer side = B11′). No new senior-practitioner findings; Round-4 did not re-derive the Sec-A matrix from scratch because Phase-D didn't touch the 25 already-RESOLVED items.

---

## Section E — Updated Shard Plan + Dependency Waves

Round-3 published a 34-shard / 8-wave plan. Round-4 re-derives.

| Spec                        | Shard count | Wave | Blockers (spec files)                                         | Round-4 shard delta vs Round-3                          |
| --------------------------- | ----------- | ---- | ------------------------------------------------------------- | ------------------------------------------------------- |
| ml-backends                 | 1           | 1a   | None                                                          | unchanged                                               |
| ml-tracking                 | 3           | 1b   | ml-backends                                                   | unchanged                                               |
| ml-engines-v2 (main)        | 3           | 2    | ml-backends, ml-tracking                                      | unchanged                                               |
| ml-engines-v2-addendum      | 2           | 3    | ml-engines-v2 main                                            | unchanged                                               |
| ml-registry                 | 2           | 4a   | ml-engines-v2                                                 | unchanged; B11′ adds <50 LOC to shard 1                 |
| ml-feature-store            | 3           | 4b   | ml-engines-v2                                                 | unchanged; Phase-D DDL is now precise                   |
| ml-autolog                  | 3           | 5    | ml-tracking                                                   | unchanged                                               |
| ml-diagnostics              | 3           | 5    | ml-tracking, ml-engines-v2                                    | unchanged                                               |
| ml-serving                  | 3           | 6    | ml-registry, ml-tracking, ml-drift                            | unchanged; padding + backpressure + ONNX fit in shard 1 |
| ml-drift                    | 2           | 6    | ml-registry, ml-serving (shadow table)                        | unchanged; N1 prefix rewrite is no-code                 |
| ml-dashboard                | 2           | 7    | ml-tracking, ml-registry, ml-drift                            | unchanged                                               |
| ml-rl-core                  | 2           | 6    | ml-engines-v2, ml-backends                                    | unchanged                                               |
| ml-rl-algorithms            | 2           | 7    | ml-rl-core                                                    | unchanged                                               |
| ml-rl-align-unification     | 1           | 8    | ml-rl-core, ml-rl-algorithms, kailash-align 1.0               | unchanged                                               |
| ml-automl                   | 2           | 8    | ml-engines-v2, ml-tracking, ml-feature-store                  | unchanged                                               |
| align-ml-integration        | 1           | 8    | ml-rl-align-unification, kailash-align 1.0                    | **NEW (supporting)**                                    |
| dataflow-ml-integration     | 1           | 4b   | ml-feature-store, kailash-dataflow 2.1                        | **NEW (supporting)**                                    |
| kailash-core-ml-integration | 1           | 1a   | None (pure Protocol-expansion) — lands with kailash 2.9.0     | **NEW (supporting)**                                    |
| kaizen-ml-integration       | 1           | 5    | kailash-core-ml-integration, ml-tracking, kailash-kaizen 2.12 | **NEW (supporting)**                                    |
| nexus-ml-integration        | 1           | 7    | ml-dashboard, kailash-nexus 1.1                               | **NEW (supporting)**                                    |
| pact-ml-integration         | 1           | 8    | ml-automl, kailash-pact 1.1                                   | **NEW (supporting)**                                    |

**Round-4 total: 40 shards, 8 waves** (up from 34/8 at Round-3 — +6 shards from the 6 supporting-spec integration packages that were not scored at Round-3).

**Parallelization (Round-4):**

- Wave 1a: ml-backends (1) + kailash-core-ml-integration (1) — **2 parallel worktrees**
- Wave 1b: ml-tracking (3) — 3 parallel worktrees
- Wave 2: ml-engines-v2 main (3) — 3 sequential or parallel
- Wave 3: ml-engines-v2-addendum (2) — 2 parallel
- Wave 4a: ml-registry (2)
- Wave 4b: ml-feature-store (3) + dataflow-ml-integration (1) — 4 parallel
- Wave 5: ml-autolog (3) + ml-diagnostics (3) + kaizen-ml-integration (1) — **7 parallel worktrees**
- Wave 6: ml-serving (3) + ml-drift (2) + ml-rl-core (2) — 7 parallel worktrees
- Wave 7: ml-dashboard (2) + ml-rl-algorithms (2) + nexus-ml-integration (1) — 5 parallel worktrees
- Wave 8: ml-rl-align-unification (1) + ml-automl (2) + align-ml-integration (1) + pact-ml-integration (1) — 5 parallel worktrees

**Critical path:** ~17 shards (Wave 1a → 2 → 3 → 4a → 5 → 6 → 7 → 8 longest chain). At the 10x autonomous execution multiplier, ≈17 sessions ≈ 3-4 human-weeks equivalent.

**Phase-D delta cost:** ~75 minutes of spec editing closes B3 + B4 + B9 + N1 + B11′:

- B3 (EngineInfo dataclass): 20 min
- B4 (LineageGraph dataclass): 30 min
- B9 (AutoMLEngine demotion reconciliation): 15 min
- N1 (prefix normalization — `_kml_*` → `kml_*` in ml-drift DDL + 4 specs' prose): 30 min sed-driven
- B11′ (ml-registry register-time ONNX probe): 25 min

After those 5 edits: **21/21 READY, 0 HIGH, 0 BLOCKED.**

---

## Section F — Sibling-Spec Sweep Audit (per `rules/specs-authority.md` §5b)

Phase-D edited 5 ml specs (ml-serving, ml-feature-store, ml-registry, ml-automl, ml-drift). Round-4 re-derives against the FULL sibling set per the Rule 5b "14/14 green → 9 HIGH cross-spec drift" evidence pattern.

**Full-sibling sweep results:**

1. **DDL prefix drift (N1 above)** — surfaces ONLY at full-sibling sweep. Each Phase-D edit was internally consistent within its spec, but the cross-spec comparison exposes the `_kml_*` vs `kml_*` split. **Caught.**
2. **A10-3 producer-vs-consumer split (B11′ above)** — surfaces ONLY at full-sibling sweep. ml-serving §2.5 is internally complete; ml-registry §4 is internally complete for aliases. The cross-spec reference from ml-serving line 216 to "ml-registry §4" is the broken link that full-sibling sweep catches. **Caught.**
3. **AutoMLEngine first-class-vs-demoted (B9)** — surfaces ONLY at full-sibling sweep. ml-engines-v2 §8.2 is internally consistent as a v2.0 migration table; ml-automl §2.1 is internally consistent as a first-class API. Cross-spec conflict only visible when both are read together. **Caught.**
4. **LineageGraph shape (B4)** — surfaces ONLY at full-sibling sweep. ml-engines-v2-addendum §E10.2 is internally consistent as a 7-field bullet list; ml-dashboard §4.1 is internally consistent as a REST endpoint documentation. The missing dataclass is invisible unless both are read together. **Caught.**

**Conclusion:** Rule 5b held. The 4 HIGHs above would have been missed by any narrow-scope review. Full-sibling sweep is required and this Round-4 exercised it.

---

## Section G — Shard Delegation Prompts (Implementation-Ready, excerpt)

For the 3 still-open Round-3 HIGHs that remain after Phase-D, the delegation prompt template is:

```
Agent(isolation="worktree", prompt="""
Task: close Round-3 HIGH {B3|B4|B9} as specified in
  workspaces/kailash-ml-audit/04-validate/round-4-feasibility.md §B.

Spec files to edit (relative paths from repo root):
- {file_path_1}
- {file_path_2}

Commit discipline (MUST):
- Edit → Read-back → git add <file> && git commit -m "spec(B{3|4|9}): close {finding}"
- Do NOT hold changes uncommitted; worktree auto-cleanup WILL lose uncommitted work.

Verification (MUST before declaring done):
- Run the Round-4 grep sweeps per §B for your finding. Output MUST be empty.
- Re-read the edited section. Confirm the MUST-rule text is present.
""")
```

A single agent with all 5 fixes (B3 + B4 + B9 + N1 + B11′) in one session is tractable since the edits are local and don't touch cross-session state. Budget: ~75 min.

---

## Summary — Round-4 Verdict

**Per-spec tally:**

- **READY:** 17 (ml-tracking, ml-autolog, ml-diagnostics, ml-backends, ml-serving, ml-feature-store, ml-dashboard, ml-automl, ml-rl-core, ml-rl-algorithms, ml-rl-align-unification, and all 6 supporting specs)
- **NEEDS-PATCH:** 4 (ml-registry, ml-drift, ml-engines-v2 main, ml-engines-v2-addendum)
- **BLOCKED:** 0

**Progress:**

| Round | READY | NEEDS-PATCH | BLOCKED | Scope                       |
| ----- | ----- | ----------- | ------- | --------------------------- |
| 2b    | 4     | 11          | 0       | 15 core specs               |
| 3     | 9     | 6           | 0       | 15 core specs               |
| 4     | 17    | 4           | 0       | 21 specs (15 core + 6 supp) |

**Open HIGHs after Phase-D:**

1. **B3** — `EngineInfo` + `MethodSignature` + `ParamSpec` dataclass bodies absent in ml-engines-v2-addendum §E11.1 (STILL OPEN from Round-3).
2. **B4** — `LineageGraph` + `LineageNode` + `LineageEdge` dataclass bodies absent in ml-engines-v2-addendum §E10.2 (STILL OPEN from Round-3).
3. **B9** — `AutoMLEngine` / `EnsembleEngine` legacy-vs-first-class cross-spec conflict between ml-engines-v2 §8.2 and ml-automl §2.1 (STILL OPEN from Round-3).
4. **N1** — DDL prefix drift `kml_*` (5 specs) vs `_kml_*` (ml-drift + prose everywhere) — **NEW at Round-4**.
5. **B11′** — ml-registry register-time ONNX probe absent; ml-serving §2.5.1 cross-references `ml-registry-draft.md §4` which is the aliases section — **NEW at Round-4** (Phase-D residue from splitting A10-3 across specs).

**Recommended next action:** one focused ~75-min spec edit session (can run as a single agent with `isolation: "worktree"` + commit-each-milestone discipline per `rules/worktree-isolation.md` §5) to apply:

1. B3 — add `@dataclass(frozen=True)` blocks for `ParamSpec`, `MethodSignature`, `EngineInfo` in ml-engines-v2-addendum §E11.1 (~20 min).
2. B4 — add `@dataclass(frozen=True)` blocks for `LineageNode`, `LineageEdge`, `LineageGraph` in ml-engines-v2-addendum §E10.2, add JSON-serialization note in ml-dashboard §4.1 (~30 min).
3. B9 — delete `AutoMLEngine` row from ml-engines-v2 §8.2, add to §8.3 preserved list; clarify §8.2 `EnsembleEngine` demotion scope (~15 min).
4. N1 — rewrite ml-drift DDL `_kml_drift_*` → `kml_drift_*` (4 CREATE TABLE) + prose sweep `_kml_*` → `kml_*` in 6 specs' prose (91 references, sed-driven) (~30 min).
5. B11′ — add ml-registry §11.2 ONNX Custom-Op Probe with `unsupported_ops` column + MUST rule + Tier-2 test; fix ml-serving §2.5.1 line 216 cross-reference (~25 min).

**After those 5 edits: Round-5 /redteam feasibility audit expected to return 21/21 READY, 0 HIGH, 0 BLOCKED.**

**Per `rules/autonomous-execution.md §Structural vs Execution Gates`:** all 5 items are execution gates — autonomous agent can close them without human-authority escalation; no new structural gate from this round.

**Per `rules/specs-authority.md §5b`:** Round-4 ran the full-sibling re-derivation sweep and caught 4 of the 5 remaining HIGHs that would be invisible to narrow-scope review. This validates the rule empirically for a third consecutive session (2026-04-19 / 2026-04-20 / 2026-04-21).

---

## Absolute Paths

- **This report:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-4-feasibility.md`
- **Prior round:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-3-feasibility.md`
- **Round-3 SYNTHESIS:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-3-SYNTHESIS.md`
- **Approved decisions:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/approved-decisions.md`
- **15 core specs audited:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-*.md`
- **6 supporting specs audited:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/*-ml-integration-draft.md`

_End of round-4-feasibility.md. Author: Implementation Feasibility Auditor persona. 2026-04-21._
