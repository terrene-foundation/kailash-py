# Issue #567 — MLFP Diagnostics Upstream: Failure-Point & Risk Analysis

**Source**: `terrene-foundation/kailash-py#567` (~7,300 LOC across 7 helpers)
**Analyst deliverable**: `/analyze`-grade failure-point + integration analysis
**Date**: 2026-04-20

---

## Executive Summary

- **Overall complexity**: **Complex** (Governance 9 + Legal 7 + Strategic 6 = 22). Seven helpers, four target packages, three known Foundation-independence violations (Langfuse, medical metaphors, TRL fallback), one framework-first concern (AgentTrace cost float-sum bypassing `kaizen.providers.cost.CostTracker`), and one cross-SDK parity surface (kailash-rs `kaizen-observability-rs` / `pact-rs`).
- **Recommendation**: **Accept 4 helpers, rework 2, reject 1 for redesign**. Ship as **7 sequential PRs** (one per helper) against a tracking issue, NOT a single mega-PR — each helper has different reviewer/specialist ownership, different extras, different spec-sweep scope. Parallel landing is BLOCKED because all 7 touch sibling `[project.optional-dependencies]` in sub-package pyprojects and several collide on `kaizen/judges/*` vs `kaizen/observability/*` namespace creation (see `rules/agents.md` § "Parallel-Worktree Package Ownership Coordination").
- **Low-risk accepts (4)**: DLDiagnostics, RAGDiagnostics, InterpretabilityDiagnostics, AlignmentDiagnostics.
- **Need cleanup before accept (2)**: LLMDiagnostics (position-swap bias + judge-cost routing), AgentDiagnostics (Langfuse strip + cost-tracker routing).
- **Reject for redesign (1)**: GovernanceDiagnostics — reading PACT audit chain from outside the PACT trust boundary via a "diagnostics" facade is a `rules/pact-governance.md` MUST #1 violation in the making (see §7 below). MUST route through the PACT governance API, not a new audit-inspector class.

---

## 1. Risk / Failure-Point Analysis Per Helper

### 1.1 DLDiagnostics (1,679 LOC → `kailash_ml.engines.dl_diagnostics`)

| Dimension               | Finding                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Integration module      | `packages/kailash-ml/src/kailash_ml/engines/dl_diagnostics.py` (new), lazy-loaded via `kailash_ml.__init__.__getattr__` like peers (`ModelExplainer`, `ModelVisualizer`)                                                                                                                                                                                                                                                                                                                                 |
| New dependencies        | `torch>=2.2` (already base dep), `plotly>=5.18` (already base dep), `matplotlib` for Grad-CAM heatmaps (NEW — add to `[dl]` extra)                                                                                                                                                                                                                                                                                                                                                                       |
| Public-API collision    | None. `ModelExplainer` (SHAP/LIME) is a non-overlapping surface; `ModelVisualizer` handles training curves not per-layer gradient flow.                                                                                                                                                                                                                                                                                                                                                                  |
| Foundation-independence | **HIGH**: Medical metaphor docstrings ("Stethoscope", "X-Ray", "ECG") MUST be stripped per `rules/terrene-naming.md` § "Canonical Terminology" — replace with production-neutral ("GradientFlowReport", "ActivationSaturationMap", "LRRangeTest").                                                                                                                                                                                                                                                       |
| Framework-first         | PASS — this is a primitive-layer helper wrapping torch hooks; no LLM/DB/API calls to bypass.                                                                                                                                                                                                                                                                                                                                                                                                             |
| Orphan risk             | Medium-High: the helper pattern (context manager + `report()` dict) is exactly the `*Report` / `*Engine` shape `rules/facade-manager-detection.md` targets. MUST ship with a Tier 2 integration test under `packages/kailash-ml/tests/integration/` that runs a real 2-epoch MNIST-scale fit and asserts `report()["dead_neurons"]` is non-empty AND asserts the diagnostics object is exposed through `kailash_ml.DLDiagnostics` (facade, not direct module import) per `rules/orphan-detection.md` §1. |
| Risk level              | **Low** (accept with cleanups 1 + 2 above)                                                                                                                                                                                                                                                                                                                                                                                                                                                               |

**Failure points:**

1. **Torch version drift.** Grad-CAM implementations depend on `torch.nn.Module.register_forward_hook` semantics — pin `torch>=2.2` (matches existing base dep, no new floor needed).
2. **Memory-pinning during long runs.** Gradient-flow trackers holding per-layer tensors across 1000+ steps OOM on small GPUs. MUST implement bounded `collections.deque(maxlen=N)` per-layer history, not unbounded list.
3. **Device-report integration.** Every diagnostic report MUST include the `DeviceReport` (new in 0.11.0, see `kailash_ml._device_report`) for cross-run comparability. This is a `specs/ml-backends.md` §7 MUST per the full-sibling sweep rule.

### 1.2 LLMDiagnostics + JudgeCallable (615 + 435 = 1,050 LOC → `kaizen.judges.*`)

| Dimension                  | Finding                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Integration module         | **NEW namespace**: `packages/kailash-kaizen/src/kaizen/judges/__init__.py` with `LLMJudge`, `JudgeCallable`, `FaithfulnessJudge`, `SelfConsistencyJudge`, `RefusalCalibrator`. Kaizen has NO existing `judges/` surface — greenfield.                                                                                                                                                                                                                                                    |
| New dependencies           | `bert-score>=0.3.13`, `rouge-score>=0.1.2`, `sacrebleu>=2.4` — ALL go into a NEW optional extra `kaizen[judges]`. Do NOT make base deps — bert-score pulls torch+transformers and bloats the base install for every Kaizen user.                                                                                                                                                                                                                                                         |
| Public-API collision       | None — but MUST coordinate with `kaizen.core.autonomy.observability` (metrics/tracing/audit live there already). Judges emit evaluation records; those records MUST flow through `ObservabilityManager` (metrics counter `kaizen.judge.invocations_total`) rather than a parallel logger.                                                                                                                                                                                                |
| Foundation-independence    | PASS — no commercial couplings in judge code itself; ensure citation docstrings don't reference proprietary LLM-as-judge products by name.                                                                                                                                                                                                                                                                                                                                               |
| Framework-first            | **HIGH concern**: The `JudgeCallable` is exactly what `rules/framework-first.md` calls a Delegate-wrapped primitive. The issue body says "Delegate-wrapped" but the MLFP source code MUST be audited: if `JudgeCallable` calls `openai.chat.completions.create` or `litellm.completion` directly (bypassing `kaizen_agents.Delegate`), that is a `zero-tolerance.md` Rule 4 violation. MUST reroute through `Delegate(model=os.environ["OPENAI_PROD_MODEL"])` per `rules/env-models.md`. |
| `rules/agent-reasoning.md` | **HIGH concern**: "LLM-as-judge" with `position_swap_bias_mitigation` — verify the swap-and-compare is driven by the LLM's structured-output signature, NOT by code conditionals on the judge's free-text output. Position-swap is OK (it's a probe), but aggregation of the two judgments MUST NOT regex-match "A wins" / "B wins" — use `OutputField(description="winner")` and structured parse.                                                                                      |
| Cost routing               | **CRITICAL** — `budget_cap` in the judge MUST route through `kaizen.providers.cost.CostTracker` (which tracks integer-microdollars since kailash-kaizen 2.5+). Tracking budget as raw USD floats is a cross-helper drift against `kaizen.costs` (PACT also accumulates in microdollars via `pact.costs`).                                                                                                                                                                                |
| Orphan risk                | Medium — `LLMJudge` fits the `*Judge` naming shape covered by `rules/facade-manager-detection.md`. Needs Tier 2 test that exercises the full judge through `kaizen.judges.LLMJudge` facade import, real `.env`-sourced model.                                                                                                                                                                                                                                                            |
| Risk level                 | **Medium** (accept after cleanups: Delegate routing, structured judgment, CostTracker microdollar plumbing, bias-mitigation via signature not regex)                                                                                                                                                                                                                                                                                                                                     |

**Failure points:**

1. **Position-swap bias mitigation drift.** If the judge swaps A/B positions between calls to eliminate positional bias, the aggregation of disagreeing verdicts must be defined behaviorally (tie-break rule, or flag for human review) — NOT silently averaged.
2. **Budget cap exhaustion path.** What happens when `budget_cap` is hit mid-evaluation? Must raise a typed `JudgeBudgetExhausted` error (NOT return a partial result that looks successful) per `rules/zero-tolerance.md` Rule 3.
3. **Self-consistency N-calls.** Self-consistency judge makes N parallel LLM calls — each MUST share one `CostTracker` instance (tenant-scoped per `rules/tenant-isolation.md` Rule 5 when called under a `tenant_id` context).

### 1.3 InterpretabilityDiagnostics (529 LOC → `kaizen.interpretability.*`)

| Dimension               | Finding                                                                                                                                                                                                                                                                                         |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Integration module      | `packages/kailash-kaizen/src/kaizen/interpretability/__init__.py` (new). NOT `kailash_ml`: it's LLM-specific (Llama/Gemma/Phi/Mistral attention heatmaps, logit lens, linear probes, SAE features) — belongs with Kaizen's LLM tooling.                                                         |
| New dependencies        | `transformers>=4.40` (optional — `kaizen[interpretability]`), optionally `sae-lens>=3.0` for SAE features. NOT base deps; inline `try/except ImportError` per `rules/dependencies.md` § "Exception: Optional Extras with Loud Failure" with a clear "install kaizen[interpretability]" message. |
| Public-API collision    | None — no existing interpretability surface in either ml or kaizen.                                                                                                                                                                                                                             |
| Foundation-independence | PASS, but verify: `open-weight only (Llama/Gemma/Phi/Mistral)` — docstrings MUST describe this as a technical requirement (we need model weights to hook into attention), NOT as a commercial stance.                                                                                           |
| Framework-first         | PASS — primitive layer; no LLM API calls since it operates on local weights directly.                                                                                                                                                                                                           |
| Orphan risk             | Low — no framework-facade exposure needed; users import `from kaizen.interpretability import AttentionHeatmap`.                                                                                                                                                                                 |
| Risk level              | **Low** (accept with cleanup: optional extras loud-failure pattern)                                                                                                                                                                                                                             |

**Failure points:**

1. **HF model-loading side effects.** `AutoModelForCausalLM.from_pretrained(...)` can download multi-GB weights. MUST ship with `local_files_only=True` default and a prominent note about `HF_HOME`; do NOT silently download in a diagnostic call.
2. **VRAM blowup.** Logit-lens across a full sequence holds intermediate activations for every layer. Same `deque(maxlen=N)` discipline as DLDiagnostics.

### 1.4 RAGDiagnostics (705 LOC → `kailash_ml.engines.rag_diagnostics`)

| Dimension               | Finding                                                                                                                                                                                                                                                                                                                                                               |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Integration module      | `packages/kailash-ml/src/kailash_ml/engines/rag_diagnostics.py` (new). Alternative: `kaizen.rag.diagnostics` — DECISION: goes into kailash-ml because the metrics (recall@k, precision@k, MRR, nDCG) are IR metrics already adjacent to `kailash_ml.metrics`, and retriever leaderboards are an ML artifact. Kaizen consumes it via cross-package import when needed. |
| New dependencies        | None new — polars is already a base dep, scipy is already a base dep. Retriever leaderboard could use `kailash_ml.engines.experiment_tracker` for persistence.                                                                                                                                                                                                        |
| Public-API collision    | None. `kailash_ml.metrics` is the existing metrics namespace — RAG metrics fit cleanly as `kailash_ml.metrics.rag.*` (submodule), NOT top-level.                                                                                                                                                                                                                      |
| Foundation-independence | PASS — IR metrics are mathematical primitives.                                                                                                                                                                                                                                                                                                                        |
| Framework-first         | PASS at the diagnostic layer, but verify no raw FAISS/ChromaDB SDK calls — if retriever evaluation needs to hit a vector store, route through whatever Kaizen abstraction exists (if none, file a cross-SDK issue before shipping).                                                                                                                                   |
| Orphan risk             | Low with standard Tier 2 test.                                                                                                                                                                                                                                                                                                                                        |
| Risk level              | **Low** (accept as-is)                                                                                                                                                                                                                                                                                                                                                |

**Failure points:**

1. **Dataset-size bounds.** MRR/nDCG across 100k queries × 1k docs each is a polars groupby that can blow memory. MUST have a streaming mode via `LazyFrame.collect_async` per `rules/dependencies.md` § "Minimum Version Floors" (polars>=0.20 already pinned).

### 1.5 AgentDiagnostics + TraceEvent (668 + 360 = 1,028 LOC → `kaizen.observability.traces`)

| Dimension               | Finding                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Integration module      | MUST integrate INTO existing `packages/kailash-kaizen/src/kaizen/core/autonomy/observability/` (where `TracingManager`, `MetricsCollector`, `AuditTrailManager`, `ObservabilityManager` already live). Do NOT create a parallel `kaizen.observability/` namespace at the top level — that's a `rules/orphan-detection.md` §1 duplicate-facade risk. Sub-module: `kaizen/core/autonomy/observability/agent_traces.py`.                                             |
| New dependencies        | None if Langfuse is stripped (see Foundation-independence below).                                                                                                                                                                                                                                                                                                                                                                                                 |
| Public-API collision    | **HIGH**: `TraceEvent` is the same shape as existing `kaizen.core.autonomy.observability.types.AuditEntry` and `LogEntry`. MUST reconcile before landing — either subclass/compose the existing types or justify (in the PR body) why a third trace record type is needed. Otherwise we ship three parallel record shapes for the same concept.                                                                                                                   |
| Foundation-independence | **CRITICAL**: "AgentDiagnostics has Langfuse exporter hardcoded" is a `rules/independence.md` "No commercial references" violation AND a "Foundation-only dependencies" violation if Langfuse is a runtime dep. MUST be stripped to a `TraceExporter` Protocol with in-tree implementations (`FileTraceExporter`, `StdoutTraceExporter`); third-party exporters become a separate package or sit entirely in user code. Langfuse cannot appear in pyproject.toml. |
| Framework-first         | **CRITICAL**: "AgentTrace sums cost as floats; kaizen.cost.CostTracker uses microdollars" — this is the exact shape of `rules/framework-first.md` "Raw primitives for what Engine handles" violation. `AgentTrace.total_cost` MUST be computed by `CostTracker` (already thread-safe, already microdollars, already handles tenant scoping). Zero custom float accumulation.                                                                                      |
| Cost-tracker routing    | See above — mandatory rewrite.                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| Orphan risk             | Medium if the existing `TracingManager` / `MetricsCollector` aren't updated to consume the new trace records.                                                                                                                                                                                                                                                                                                                                                     |
| Risk level              | **Medium** (accept after: Langfuse→Protocol, CostTracker routing, TraceEvent↔AuditEntry reconciliation)                                                                                                                                                                                                                                                                                                                                                           |

**Failure points:**

1. **Loop detection state overflow.** Agent run capture holding every tool call in memory for loop detection is a DoS risk on long-running agents. MUST cap at N calls with a `LoopSuspectedWarning` at the cap.
2. **Tool-usage metric label cardinality.** Emitting `kaizen.tool.invocations{tool_name=...}` is fine; emitting `{agent_id=...}` unbounded is a `rules/tenant-isolation.md` MUST Rule 4 violation. MUST bucket beyond top-N.

### 1.6 AlignmentDiagnostics (649 LOC → `kailash_align.diagnostics`)

| Dimension               | Finding                                                                                                                                                 |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Integration module      | `packages/kailash-align/src/kailash_align/diagnostics.py` (new), exported via `kailash_align.__all__`.                                                  |
| New dependencies        | None new — kailash-align already pulls `trl`, `peft`, `transformers` as optional extras. The closed-form KL divergence and reward-margin math is numpy. |
| Public-API collision    | None; kailash-align has `AlignmentEvaluator` but that's task-level (MMLU, GSM8K, etc.), not training-health.                                            |
| Foundation-independence | LOW concern — TRL is Apache 2.0 open-source; the "trl fallback can be dropped" cleanup is a code-quality win, not a commercial-coupling fix. Verify.    |
| Framework-first         | PASS — align's own primitive layer.                                                                                                                     |
| Orphan risk             | Low with Tier 2 test against a real 2-step SFT run.                                                                                                     |
| Risk level              | **Low** (accept with cleanup: drop TRL fallback per the issue's own note)                                                                               |

**Failure points:**

1. **Reward-hacking detection heuristic.** Detecting reward-model gaming is notoriously noisy. MUST ship with a clear confidence-score output and `WARNING.md`-style docs that this is a signal-detection helper, not a ground-truth classifier.
2. **Version gate**: AlignmentDiagnostics pulls from a running trainer — MUST require `kailash-align>=0.x` where x is whatever exposes the necessary hooks. See §5 below.

### 1.7 GovernanceDiagnostics (716 LOC → **REJECT for redesign**)

| Dimension                             | Finding                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Integration module                    | PROPOSED `packages/kailash-pact/src/pact/diagnostics.py`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| New dependencies                      | None                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Public-API collision                  | **CRITICAL**: `kailash.trust.pact.audit` already owns the audit chain. Adding a second inspection surface is `rules/orphan-detection.md` §1 "parallel facade" failure mode.                                                                                                                                                                                                                                                                                                                                                                                                           |
| Foundation-independence               | PASS                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Framework-first                       | **BLOCKING**: "Read-only audit inspector: chain verification (SHA-256 prev_hash), budget consumption, negative drills, envelope snapshots" describes functionality that MUST be on the PACT engine itself, not a sibling helper. `pact.audit` already has the chain; `pact.costs` already has budget; `pact.enforcement` already has envelope resolution. A "diagnostics" class that reaches into these creates a parallel read-path with different invariants (different caching, different tenant scoping, different fail-closed semantics per `rules/pact-governance.md` MUST #4). |
| `rules/pact-governance.md` violations | MUST #1 (frozen GovernanceContext) — if diagnostics needs the engine to verify the chain, giving diagnostics engine access bypasses the frozen-context contract; #4 (fail-closed) — "negative drills" that probe denied-access paths require running the enforcement engine with a diagnostic flag that could be misused; #8 (thread safety) — adding a second reader of the audit chain without lock discipline risks torn reads.                                                                                                                                                    |
| Orphan risk                           | High                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Risk level                            | **REJECT — redesign**                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

**Disposition**: The seven features of GovernanceDiagnostics MUST be absorbed as methods on the existing PACT surfaces:

- `chain verification` → new method `GovernanceEngine.verify_audit_chain(tenant_id)` on the existing engine (uses existing lock).
- `budget consumption` → already `pact.costs.BudgetTracker.snapshot()` — file a gap issue if the snapshot API is missing fields MLFP uses.
- `envelope snapshots` → `GovernanceEngine.snapshot_envelopes(tenant_id)`.
- `negative drills` → REJECTED for upstream. Negative drills (probing what a role CAN'T do) are a testing primitive, not a production diagnostic; belongs in `pact.governance.testing` (which exists) or downstream training materials.

File **kailash-py#567-A** (Governance surface extension) as a separate ticket; close #567's GovernanceDiagnostics item by merging the chain-verification + envelope-snapshot capabilities into the main engine.

---

## 2. Cross-Cutting Failure Points

### 2.1 `@dataclass` vs polars-native mismatch

The issue says "All share common shape: context manager, polars DataFrames, plot\_\*() → go.Figure, report() → dict". MUST audit: does the MLFP code use `@dataclass(frozen=True)` for report types, matching `kailash_ml`'s `TrainingResult` / `SetupResult` / `ComparisonResult` convention? If not, rework to match — downstream consumers pattern-match on dataclass shape per `specs/ml-engines.md` §4.

### 2.2 Plotly license

`plotly>=5.18` is already a base dep of kailash-ml — no new license exposure. `go.Figure` return values are fine.

### 2.3 Medical-metaphor docstring audit (cross-helper)

`rules/terrene-naming.md` § "Canonical Terminology" is explicit: production-neutral. Every `Stethoscope`/`XRay`/`ECG`/`MRI`/`Endoscope` needs a rename at rebrand-commit time. MUST ship a single grep-regression test:

```python
@pytest.mark.regression
def test_no_medical_metaphor_in_mlfp_helpers():
    for pkg in ("kailash_ml/engines", "kaizen/judges", "kaizen/interpretability",
                "kailash_align/diagnostics", "kaizen/core/autonomy/observability"):
        for f in Path(f"packages/.../{pkg}").rglob("*.py"):
            txt = f.read_text().lower()
            for forbidden in ("stethoscope", "x-ray", "xray", "ecg", "mri", "endoscope", "surgeon"):
                assert forbidden not in txt, f"medical metaphor in {f}: {forbidden}"
```

### 2.4 Log-surface hygiene

Every helper emits structured logs (standard practice). MUST follow `rules/observability.md` Rule 8 (schema-revealing field names at DEBUG / hashed) — especially InterpretabilityDiagnostics (which could leak the names of probed model layers at INFO) and RAGDiagnostics (which logs query-level metrics that could leak query text).

### 2.5 Cross-SDK parity obligation

Per `rules/cross-sdk-inspection.md` MUST Rule 1: every accepted helper MUST have a sibling ticket filed in `esperie/kailash-rs` with a `cross-sdk` label. See `cross-sdk-parity.md` for per-helper decisions.

---

## 3. PR Shape Recommendation

**Anti-pattern**: Single mega-PR for 7,300 LOC across 4 sub-packages. This overflows the `rules/autonomous-execution.md` per-session capacity budget (≤500 LOC load-bearing, ≤5–10 invariants, ≤3–4 call-graph hops). Seven helpers × 4 target packages × ~3 invariants each = 84 invariants; unsurvivable in one pass.

**Recommended sequence** — 7 sequential PRs against a tracking issue:

| #   | PR                          | Target                                       | Specialist            | Extras                      | Blocking deps                                  |
| --- | --------------------------- | -------------------------------------------- | --------------------- | --------------------------- | ---------------------------------------------- |
| 1   | DLDiagnostics               | kailash-ml 0.16.0                            | **ml-specialist**     | `[dl]` +matplotlib          | None                                           |
| 2   | RAGDiagnostics              | kailash-ml 0.17.0                            | **ml-specialist**     | None new                    | #1 merged (shared medical-metaphor grep test)  |
| 3   | LLMDiagnostics              | kailash-kaizen 2.8.x                         | **kaizen-specialist** | NEW `[judges]`              | #1 merged (test infra)                         |
| 4   | InterpretabilityDiagnostics | kailash-kaizen 2.9.x                         | **kaizen-specialist** | NEW `[interpretability]`    | #3 merged (judges/ namespace precedent)        |
| 5   | AgentDiagnostics            | kailash-kaizen 2.10.x                        | **kaizen-specialist** | None (after Langfuse strip) | #3 + `CostTracker` microdollar audit           |
| 6   | AlignmentDiagnostics        | kailash-align 0.x                            | **align-specialist**  | Existing                    | kailash-align ≥ whatever-version-exposes-hooks |
| 7   | GovernanceDiagnostics       | **REDESIGN** into `GovernanceEngine` methods | **pact-specialist**   | None                        | Full redesign PR, separate ticket              |

Each PR independently triggers its sub-package's CHANGELOG + version bump. Parallel landing of PRs 3/4/5 is BLOCKED (all touch `packages/kailash-kaizen/pyproject.toml [project.optional-dependencies]` + `__init__.py __all__` — per `rules/agents.md` § "Parallel-Worktree Package Ownership Coordination" you MUST designate ONE version owner per sub-package or race on pyproject.toml).

**Blast radius per PR**: 500–1,500 LOC production, plus tests (Tier 2 real infra), plus spec sweep. Fits the session budget.

---

## 4. Spec Updates Required (`rules/specs-authority.md` MUST Rule 5b full-sibling sweep)

Each PR triggers a **full-sibling spec sweep**. Scope by target package:

| PR                               | Edits                                                                          | Triggers sibling sweep of                                                                                                                                                         |
| -------------------------------- | ------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| DLDiagnostics                    | `specs/ml-engines.md` (+§ Diagnostics), possibly new `specs/ml-diagnostics.md` | **ALL** `specs/ml-*.md` (engines, backends, tracking) — cross-check `TrainingResult` / `DeviceReport` references                                                                  |
| RAGDiagnostics                   | `specs/ml-engines.md` (metrics subsection)                                     | ALL `specs/ml-*.md`                                                                                                                                                               |
| LLMDiagnostics                   | NEW `specs/kaizen-judges.md` + `specs/kaizen-advanced.md` update               | **ALL** `specs/kaizen-*.md` (core, signatures, providers, advanced, llm-deployments, agents-core, agents-patterns, agents-governance) — cross-check Delegate/Signature references |
| InterpretabilityDiagnostics      | NEW `specs/kaizen-interpretability.md`                                         | ALL `specs/kaizen-*.md`                                                                                                                                                           |
| AgentDiagnostics                 | `specs/kaizen-agents-core.md` + `specs/kaizen-advanced.md`                     | ALL `specs/kaizen-*.md` + `specs/trust-*.md` (trace correlation IDs cross-cut with EATP)                                                                                          |
| AlignmentDiagnostics             | `specs/alignment-training.md` (+§ Diagnostics)                                 | ALL `specs/alignment-*.md`                                                                                                                                                        |
| GovernanceDiagnostics (redesign) | `specs/pact-enforcement.md` (extend existing engine)                           | **ALL** `specs/pact-*.md` + `specs/trust-*.md`                                                                                                                                    |

---

## 5. Dependencies & Blockers

| Helper                | Blocker                                                                                                                                                                             |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| DLDiagnostics         | None. Torch+Lightning+Plotly are base. Matplotlib is a new line in `[dl]` extras (small add).                                                                                       |
| LLMDiagnostics        | `kaizen.judges.*` is greenfield — no blocker. NEW extras `[judges]`. MUST audit actual MLFP source for raw OpenAI calls (blocker: reroute through Delegate).                        |
| Interpretability      | `kaizen[interpretability]` extras NEW. transformers already at `>=4.40` in one extras path.                                                                                         |
| RAGDiagnostics        | None.                                                                                                                                                                               |
| AgentDiagnostics      | Blocker: strip Langfuse from dependencies (ship TraceExporter Protocol instead). Blocker: route `total_cost` via `kaizen.providers.cost.CostTracker` — verify microdollar contract. |
| AlignmentDiagnostics  | Possibly blocked by kailash-align hook-surface (what version exposes `trainer_state` in a way diagnostics can read?). File as prereq ticket.                                        |
| GovernanceDiagnostics | Reject + redesign as PACT engine extension.                                                                                                                                         |

**No new cross-package extras collisions** expected, but each sub-package's `[dev]` MUST NOT duplicate sub-package test deps into root `[dev]` (`rules/python-environment.md` Rule 4 — hypothesis-memory-error trap).

---

## 6. Framework-First Audit Summary

Re-stating the mandatory specialist-consultation gate per `rules/framework-first.md` § "MUST: Specialist Consultation Before Dropping Below Engine Layer":

| Helper                      | Raw pattern risk                                                      | Required specialist                             |
| --------------------------- | --------------------------------------------------------------------- | ----------------------------------------------- |
| DLDiagnostics               | torch hooks                                                           | ml-specialist                                   |
| LLMDiagnostics              | Raw LLM API calls (likely in MLFP source) — MUST reroute via Delegate | **kaizen-specialist** (MANDATORY pre-PR review) |
| InterpretabilityDiagnostics | HF model loading — primitive OK                                       | kaizen-specialist                               |
| RAGDiagnostics              | polars — OK                                                           | ml-specialist                                   |
| AgentDiagnostics            | Float cost-sum (MUST route through CostTracker)                       | **kaizen-specialist** (MANDATORY)               |
| AlignmentDiagnostics        | numpy — OK                                                            | align-specialist                                |
| GovernanceDiagnostics       | Direct audit-chain read — MUST go through engine                      | **pact-specialist** (MANDATORY)                 |

---

## 7. Success Criteria

- [ ] Each accepted helper ships in its own PR with Tier 2 integration test using framework facade (`kailash_ml.DLDiagnostics`, `kaizen.judges.LLMJudge`, etc.) per `rules/facade-manager-detection.md` MUST Rule 1.
- [ ] Medical-metaphor grep regression test passes across all 4 target packages.
- [ ] Langfuse appears in ZERO pyproject.toml files (independence audit).
- [ ] Every `*Judge` / `*Diagnostics` / `*Exporter` class exposed on a framework facade has a corresponding `test_<name>_wiring.py` file under `tests/integration/`.
- [ ] `AgentTrace.total_cost` routed through `kaizen.providers.cost.CostTracker` with microdollar fidelity (regression test: `assert trace.total_cost_microdollars == tracker.total_cost_microdollars`).
- [ ] `GovernanceDiagnostics` item of #567 closed by referring to the new PACT-engine-extension ticket (not silently dropped).
- [ ] All 7 PRs trigger full-sibling spec-sweep (`specs/ml-*.md` or `specs/kaizen-*.md`) per `rules/specs-authority.md` 5b; audit log in each PR body.
- [ ] `rules/cross-sdk-inspection.md` MUST Rule 1: each accepted helper has a sibling `esperie/kailash-rs` issue filed with `cross-sdk` label.
