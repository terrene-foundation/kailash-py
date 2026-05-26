# Architecture Plan — Issue #1125 `from_brief()` primitives

**Status:** v2 (post-Round 1, pre-Round 2). Folds in 6 HIGH + 3 MEDIUM amendments from `04-validate/round-01.md`. Gated for human approval at `/todos` after `/redteam` convergence.
**Workspace:** `workspaces/from-brief-1125/`
**Brief:** `briefs/00-brief.md` (verbatim issue body)
**Verification:** `01-analysis/01-brief-verification.md` (4 corrections recorded; core HIGH-severity claim verified TRUE)

## 1. Brief corrections (carried forward from `01-analysis/01-brief-verification.md`)

Recommended that the human gate review these BEFORE approving `/todos`:

1. **Existing `scaffold_*` MCP tools take TYPED parameters, not prose.** They DO return code-as-strings, but the proposal is a NEW LLM-mediated layer (prose → executable object), not just a return-type swap. Two axes of change, not one.
2. **`FeatureSchema` is double-defined** (`kailash_ml/types.py` mutable vs `kailash_ml/features/schema.py` frozen+content-addressed). Architecture MUST pick one; defaulting silently ships sibling-spec drift.
3. **No `specs/` coverage exists** for any of the 5 proposed surfaces. Adding code AND specs in one workstream; `spec-accuracy.md` Rule 5 forbids spec-ahead-of-code, so code lands FIRST, specs follow on `main` describing shipped behavior.
4. **`DataFlow.scaffold()` (instance method) is distinct from the MCP `dataflow.scaffold_model` tool.** Architecture plan distinguishes them throughout.

## 2. Recommendation (per `rules/recommendation-quality.md`)

I recommend: **Implement the 5 `from_brief()` surfaces as a unified Kaizen-mediated layer, sharded across 5 work-streams (one per surface) plus 1 spec foundation work-stream, totaling 6 shards. Each surface delegates LLM reasoning to a single Kaizen `Signature` + `ReActAgent` pair; deterministic plumbing (parameter validation, output formatting, schema realization) lives in the framework module under standard `rules/agent-reasoning.md` § Permitted Deterministic Logic carve-outs.**

### What this means in plain language

Today, a user wanting to use Kailash has to write Python code by hand to describe their workflow, their database tables, their AI agent, and their machine learning task. The proposal is: let the user describe what they want in plain English (a "brief"), and have the platform translate that brief into running code automatically — across all five surfaces. The recommendation is to build all five entry points the same way: each one asks an LLM (configured via `.env`) to read the brief and produce a structured plan, then deterministically constructs the runtime object from that plan. This keeps the LLM doing the reasoning (per the platform's "LLM-first" rule) and keeps the SDK doing the construction (no guessed library calls, no hallucinated symbols).

### Implications

- **One-time cost:** ~6 autonomous-execution shards (one per surface + one foundation) before any surface ships green. Each shard is bounded ≤500 LOC of load-bearing logic per `rules/autonomous-execution.md` Per-Session Capacity Budget.
- **Recovers:** The "natural-language to running workflow" contract the platform advertises in every Quick Start. The brief's HIGH severity rating becomes earned, not aspirational.
- **Ongoing:** Each surface now has a Kaizen-mediated entry point that uses the user's `.env`-configured LLM (per `rules/env-models.md`) — every Tier-2/3 regression test will hit a real LLM endpoint and cost real API calls.
- **Reversibility:** Each surface is additive — `from_brief` is a new classmethod alongside the existing class-authoring path. If a surface's `from_brief` is wrong, removing it is a clean API-removal under `rules/zero-tolerance.md` Rule 6a (deprecation shim + minor cycle, since the surface is public).

### Cons (real, not glossed)

- **Tier 2/3 CI cost.** ≥10 brief-shape integration tests × ≥1 LLM call each × every PR run. Even at `.env`-supplied gpt-4-class pricing this is a measurable per-PR budget. The architecture must surface this for human gate.
- **LLM non-determinism in tests.** Briefs are prose; LLM outputs vary across temperature settings and provider versions. Tier-2 tests can assert SHAPE (`isinstance(wf, WorkflowBuilder)`; `.build().execute()` succeeds; produced output is non-empty); they can NOT reliably assert exact field names without a sentinel-pattern test design.
- **Five surfaces, one rule-of-LLM-reasoning.** A surface like `kailash.bootstrap` is more deterministic (resolve `db_url` / `llm_model` / `runtime` / `deployment_target` from prose + profile + env) than `Workflow.from_brief` (synthesize a graph). The architecture treats them uniformly via Kaizen, but the test fixtures and shape-assertion patterns differ per surface.
- **`FeatureSchema` ambiguity is load-bearing.** Picking the wrong shape silently breaks one of the two existing consumer paths. The architecture surfaces this as an explicit human-gated decision (see §6 open question 1).
- **No precedent in source.** None of the 5 surfaces have existing implementations to extend. Each is greenfield in its package. Greenfield reduces the autonomous-execution multiplier to ~2-3x per `rules/autonomous-execution.md` § "Does NOT apply to: Greenfield domains".

### Alternative (rejected, named so the human can override)

Implement each surface independently with its own LLM-mediation pattern (raw OpenAI/Anthropic calls per surface). REJECTED because `rules/agents.md` § Specialist Delegation + `rules/framework-first.md` (Kaizen for AI agents) + `CLAUDE.md` Directive 6 (LLM-first reasoning) all converge on Kaizen as the mandated framework for any LLM-mediated reasoning in this repo. Going around Kaizen would BLOCK at gate review.

## 3. Design — per-surface architecture (uniform pattern)

The same LLM-mediation pattern applies to all 5 surfaces:

```
brief (prose)
    │
    ▼
[scrub_brief()]                                   ← strip credentials (B2a per round-01.md)
    │
    ▼
[Kaizen Signature: brief → structured plan]   ← LLM reasoning (per agent-reasoning.md)
                                                  (Signature output always includes
                                                  `interpretation_confidence: float` — C1a)
    │
    ▼
[typed plan validator]                            ← Pydantic-or-dataclass (B3a)
                                                  Raises BriefInterpretationError on:
                                                  - confidence < 0.6 (C1a)
                                                  - unknown node-type / field-type / config-value (B1a)
                                                  - malformed structure (B3a)
    │
    ▼
plan (typed dataclass)
    │
    ▼
[deterministic plumbing: realize plan into framework object]   ← Permitted Deterministic Logic
    │
    ▼
framework primitive (WorkflowBuilder | DataFlow | Signature | BootstrapConfig | tuple)
```

The split: the LLM produces a TYPED plan; the framework module validates and deterministically realizes that plan into a runtime object. No conditional routing in the agent decision path; no keyword matching on the brief. Realization is structural (loop over plan.nodes; call `workflow.add_node(...)`). Three structural defenses live between LLM output and realizer: (1) brief scrubbing prevents credentials in test logs (B2a, security.md); (2) typed-plan validation gates malformed LLM output (B3a, zero-tolerance.md Rule 3a); (3) allowlist validation gates LLM-hallucinated symbols (B1a — node types validated against `core.list_node_types`, field types validated against Signature's known type set, config-value enums validated against declared enum sets).

### 3.1 `kailash.Workflow.from_brief(brief: str) -> WorkflowBuilder`

- **Signature:** `WorkflowPlanSignature(Signature)` — `brief: str = InputField(desc="natural-language workflow intent")`; `nodes: list[NodeSpec] = OutputField(desc="ordered node list with types and parameters")`; `connections: list[ConnectionSpec] = OutputField(desc="data flow edges between nodes")`.
- **Agent:** Kaizen `ReActAgent` so the LLM can introspect available node types (via the MCP `core.list_node_types` tool documented in `specs/mcp-server.md` §3.4) before committing to a plan. ReAct gives the LLM the structural grounding to avoid hallucinated node types.
- **Realizer:** `WorkflowBuilder().add_node(...) / .add_connection(...)` loop over the plan. NO conditional logic on brief content (per `agent-reasoning.md`); the realizer is pure structural plumbing.
- **Return:** A buildable `WorkflowBuilder` — `wf.build().execute()` MUST run end-to-end (Acceptance Criterion 1).
- **LLM model:** read from `.env` via `os.environ["DEFAULT_LLM_MODEL"]` per `rules/env-models.md`.

### 3.2 `kailash.DataFlow.from_brief(brief: str, conn_str: str | None = None) -> DataFlow`

- **Signature:** `SchemaPlanSignature` — `brief: str = InputField(...)`; `models: list[ModelSpec] = OutputField(...)`. Each `ModelSpec` has `name`, `fields: list[(name, type)]`, `relationships: list[(target_model, rel_type, fk_column)]`.
- **Agent:** Kaizen `Signature`-only (no ReAct needed — schema synthesis from prose doesn't require tool use). Single-shot generation.
- **Realizer:** Build `@db.model` classes dynamically via `type()` calls bound to the `DataFlow` instance. Round-trip `create()` → `get()` MUST succeed against the connection string when `conn_str is not None` (Acceptance Criterion 2). When `conn_str is None`, return a `DataFlow` with models registered against an in-memory SQLite (the existing `DataFlow()` default).
- **Interplay with existing `scaffold_*`**: This surface does NOT use the MCP `scaffold_model` tool. It composes directly with the `DataFlow` instance's model-registration API. (`scaffold_*` MCP tools are operator-facing code-gen aids; `from_brief` is end-user-facing runtime construction.)

### 3.3 `kailash.Kaizen.signature_from_brief(brief: str) -> Signature`

- **Signature:** `SignaturePlanSignature` (meta — a Kaizen Signature that produces a Kaizen Signature spec) — `brief: str`; `input_fields: list[(name, type, desc)]`; `output_fields: list[(name, type, desc)]`; `instructions: str` (the Signature's docstring/instructions block).
- **Agent:** Kaizen `Signature`-only.
- **Realizer:** Use `SignatureMeta` (the existing metaclass at `kaizen/signatures/core.py:118`) to construct a new `Signature` subclass at runtime. The realizer is a single `type(name, (Signature,), namespace_with_InputField_OutputField_attrs)` call.
- **Return:** A `Signature` subclass, usable as `Kaizen(...).run(MySignature(...))` per the existing Signature constructor contract (Acceptance Criterion 3).

### 3.4 `kailash.bootstrap(brief: str, profile: str = "dev") -> BootstrapConfig`

- **New module:** `src/kailash/bootstrap.py` (top-level entry point exposed via `kailash.bootstrap`).
- **New dataclass:** `BootstrapConfig` with fields `db_url: str`, `llm_model: str`, `runtime: str` (PROPOSED enum: `local`, `async`, `nexus` — awaiting human approval per §6 Q6), `deployment_target: str` (PROPOSED enum: `dev`, `prod`, `containerized` — awaiting human approval per §6 Q6). Enum values NOT in the issue body; synthesized by architecture, not load-bearing for AC 4. C4 note.
- **Signature:** `BootstrapPlanSignature` — `brief: str`; `profile: str`; `resolved_config: BootstrapConfig = OutputField(...)`. The Signature's instructions tell the LLM to honor the profile (e.g. `dev` → SQLite + small local LLM; `prod` → Postgres + production LLM) AND consult environment variables for any concrete values the user already set.
- **Agent:** Kaizen `ReActAgent` with an `env_lookup` tool (deterministic; reads `os.environ.get(...)` per `rules/env-models.md`) so the LLM can ground its config decisions in the user's existing `.env`.
- **Realizer:** `BootstrapConfig(**dict_from_signature_output)`.
- **Return:** `BootstrapConfig` instance (Acceptance Criterion 4).

### 3.5 `kailash_ml.from_brief(brief: str, df: DataFrame) -> tuple[FeatureSchema, ModelSpec, EvalSpec]`

- **Signature:** `MLPlanSignature` — `brief: str`; `dataframe_schema: dict[str, str] = InputField(desc="column name → dtype map, derived from df.dtypes")`; `feature_schema: FeatureSchema = OutputField(...)`; `model_spec: ModelSpec = OutputField(...)`; `eval_spec: EvalSpec = OutputField(...)`.
- **Agent:** Kaizen `Signature`-only with deterministic dataframe-schema extraction (the realizer extracts `df.dtypes` BEFORE LLM call — this is permitted deterministic structural plumbing, not reasoning).
- **Realizer:** Construct `(FeatureSchema, ModelSpec, EvalSpec)` from Signature outputs. The columns in the resulting `FeatureSchema` MUST match `df.columns` (Acceptance Criterion 5); the `ModelSpec.task` MUST match the brief's stated prediction goal (asserted by Tier-2 test).
- **`FeatureSchema` choice:** See §6 open question 1. Recommend `kailash_ml/features/schema.py:175` (frozen + content-addressed) because it's the version the ML registry and feature store consume; using `kailash_ml/types.py:157` (mutable) would force the realizer to discard the content-hash invariant.

## 4. Cross-surface API shape decision

Recommend: **all 5 surfaces share the `(brief: str, ...) -> built-object` shape, but the constructor names differ where existing class names dictate.**

- Workflow/DataFlow/Kaizen surfaces use a classmethod `from_brief` on the existing class (`Workflow.from_brief`, `DataFlow.from_brief`, `Kaizen.signature_from_brief`). The verb `signature_from_brief` on `Kaizen` reflects that the result is a `Signature` subclass, not a `Kaizen` instance — `Kaizen.from_brief` would be misleading.
- `kailash.bootstrap(...)` and `kailash_ml.from_brief(...)` are module-level functions (they don't bind to a specific class — `bootstrap` returns a config dataclass, `kailash_ml.from_brief` returns a tuple of three specs).

### Pros

- Each surface remains discoverable in its natural namespace (`from kailash import Workflow; wf = Workflow.from_brief(...)` is idiomatic).
- The differing verbs (`from_brief` vs `signature_from_brief` vs module-level `bootstrap` vs module-level `from_brief`) document the differing return shapes.

### Cons (real)

- Inconsistent naming: a user learning the family has to remember which surface uses which form. The README Quick Start (AC 11) MUST make this explicit with a single comparison table.
- `kailash_ml.from_brief` is module-level but `kailash.bootstrap` is also module-level under a DIFFERENT verb. A future "consolidator" might want to unify these as `kailash.from_brief(target="ml", brief=..., df=...)` — but that's a different design and out-of-scope for this issue.

### Alternative (rejected, named)

Unify all 5 into `kailash.from_brief(target="workflow|dataflow|kaizen|bootstrap|ml", brief=..., **kwargs)`. REJECTED because (a) it hides the namespace each surface lives in; (b) it forces a `target=` magic-string axis that wouldn't validate at import time; (c) the brief explicitly enumerates per-class entry points, and reframing as one dispatch function would NOT match the brief's acceptance criteria (AC 1–5 cite per-class returns).

## 5. Tier 2/3 testing strategy (per `rules/testing.md`)

Per `rules/testing.md` § "NO MOCKING in Tier 2/3" — all integration tests MUST hit real LLM endpoints (`.env`-configured per `rules/env-models.md`).

Acceptance criteria 6–10 enumerate ≥10 Tier-2 tests (3 + 2 + 2 + 2 + 2 = 11 brief-shape combos). Each test:
1. Reads `DEFAULT_LLM_MODEL` from environment (auto-loaded by root `conftest.py`).
2. Calls the `from_brief()` surface with a fixture brief.
3. Asserts SHAPE of the return value (`isinstance`, presence of expected fields).
4. Where the brief implies executability (AC 1: `.build().execute()`), runs end-to-end against real infrastructure (Postgres container for DataFlow tests, local LLM service for Kaizen tests).
5. Does NOT assert exact field/node names (brief-to-output is LLM-mediated and non-deterministic at the byte level); asserts COUNT, TYPE, RELATIONSHIP-SHAPE instead.

**No-secrets-in-fixtures discipline (B2b per round-01.md).** Tier-2 fixtures (brief strings + expected-shape YAML) MUST contain NO secret-shape tokens. S1 foundation includes a regex scan over `tests/regression/from_brief/fixtures/` matching `rules/security.md` § "No hardcoded secrets" patterns (api keys starting with `sk-`, password-bearing URLs, etc.); scan runs as a pre-commit hook AND as a CI step. Any match fails the build with a typed `BriefFixtureLeakError`.

**CI cost surfacing for human gate.** Per `rules/testing.md` § "End-to-End Pipeline Regression Above Unit + Integration" — these tests must run on every PR touching the 5 surfaces. The human gate at `/todos` must explicitly approve the recurring LLM-API spend (best ballpark: ~$0.05-0.30 per PR run depending on model, at gpt-4-class pricing, for the full suite). Recommend documenting in the PR's `Tier-2 LLM cost note` section per `rules/feedback_no_resource_planning.md` discipline — surface the cost, do NOT estimate effort in human-days.

## 6. Open questions for human gate (BEFORE `/todos`)

1. **`FeatureSchema` choice for `kailash_ml.from_brief` return** (strengthened per C2a). Pick (a) `kailash_ml/types.py:157` (mutable, ML-Kaizen interop type) or (b) `kailash_ml/features/schema.py:175` (frozen, content-addressed, registry-consumed).
   - **Pros of (a):** end-user-friendly. After `kailash_ml.from_brief(...)`, a user can `schema.features.append(...)` to refine without constructing a new object. No adapter pattern needed for downstream Kaizen MCP interop (the type used in `kailash_ml/types.py` is the one Kaizen MCP consumes per its module docstring).
   - **Pros of (b):** registry-safe. Content-addressed schemas have invariant content_hash; accidental mutation cannot corrupt registry rows that pin a (name, version, content_hash) tuple. Field-name SQL-identifier validation runs at construction.
   - **Cons of (a):** the registry-pinning invariant becomes a runtime-policy contract instead of a compile-time/dataclass-enforced one — drift surface.
   - **Cons of (b):** end users have to learn the `with_features(new_features)` adapter pattern to refine a schema. S6's docs MUST teach this pattern.
   - **Recommendation:** (b) frozen+content-addressed. S6 documents the `with_features` adapter. Concrete decision needed at /todos — not deferrable to /implement.
2. **Bootstrap profile coverage.** AC 4 names `dev` and `prod`. Should the architecture also support `test`, `staging`, `containerized` as recognized profiles, or leave them as caller-extensible strings? Recommend: enumerate `dev`/`prod` only in the first cycle (matches AC), leave room for extension.
3. **MCP-tool exposure.** Should the 5 `from_brief` surfaces ALSO register themselves as MCP tools (per `specs/mcp-server.md` §3.4 — there's a Tier 2 "scaffold" category they'd fit into)? Recommend: defer to a follow-up issue. This issue's brief does not require MCP exposure (AC 1–11); adding it would expand scope beyond what's verified.
4. **`scaffold_*` MCP tools deprecation?** If `from_brief` lands and is the recommended entry point, do the existing `scaffold_*` MCP tools (with typed parameters) get deprecated? Recommend: NO. They serve a different audience (operators building from typed scaffolds, e.g. IDE-driven code gen). Both can coexist.
5. **Specs to add.** Need to author specs for the 5 surfaces. Recommend co-locating with their existing framework specs: extend `specs/core-workflows.md`, `specs/dataflow-core.md`, `specs/ml-engines-v2.md`, write new `specs/kaizen-signatures.md` § from_brief, write new `specs/bootstrap.md`. Confirm placement with human.
6. **Bootstrap enum values.** AC 4 names 4 fields but no enum values. Plan §3.4 proposes `runtime ∈ {local, async, nexus}` and `deployment_target ∈ {dev, prod, containerized}`. These are NOT in the issue body. Should the architecture lock these enums or leave them as `str` accepting any value? Recommend: lock them — open enum is silent-fallback-class (zero-tolerance.md Rule 3) when LLM emits a typo'd value. Confirm enum membership with human.
7. **Tier-2 test fixtures directory.** Need ≥11 brief-shape fixtures across 5 surfaces, each landing a real LLM-API call. Recommend `tests/regression/from_brief/fixtures/` with one YAML per fixture (brief + expected shape + asserted invariants). Confirm directory placement.
8. **Cross-surface composition (chained briefs)** — surfaced from B5a/C6a. A user MIGHT chain `Workflow.from_brief("read from my customers table")` after `DataFlow.from_brief("Customers...")`. The Workflow brief asks about a table the LLM has no knowledge of. Current architecture: 5 surfaces are INDEPENDENT (no shared state across calls). Should v1 ship with an optional `context: dict[str, Any]` kwarg on each `from_brief` that future composition can populate? Recommend: NO — out of scope for AC 1–11; file a follow-up issue for v2. The DEFERRAL is documented HERE so future sessions don't re-derive the question.

## 7. Shard plan (per `rules/autonomous-execution.md` Per-Session Capacity Budget)

Value-anchor per `rules/value-prioritization.md` MUST-2: the user's brief on issue #1125 explicitly enumerates 5 surfaces under "Affected API" and 11 acceptance criteria. Every shard's value-anchor cites a numbered AC from that brief.

| Shard | Scope | Invariants | Value-anchor (cites issue #1125 brief) |
|---|---|---|---|
| **S1** Foundation | New module `src/kailash/_from_brief/` (private LLM-mediation helpers); Kaizen `Signature` boilerplate shared across surfaces; `.env` resolver discipline; deterministic schema extraction helpers; `scrub_brief()` credential scrubber routed via `kailash.utils.url_credentials` (B2a); typed `BriefInterpretationError` exception (B3a); Pydantic-or-dataclass plan validator (B3a); allowlist-validation helpers for node-type/field-type/config-value (B1a); `interpretation_confidence` field contract + threshold-check (C1a); branching-connection realizer helpers (A2a); no-secrets fixtures regex scan (B2b). ~550 LOC (overspills the 500 nominal ceiling but stays within boilerplate-class scaling per autonomous-execution.md MUST-2 — most additions are dataclass/exception boilerplate, not load-bearing logic). | LLM-first reasoning (no conditional logic on brief content); `.env`-sourced model; output shape contract for downstream realizers; typed validation gate; allowlist gate; confidence gate; credential scrub gate. | Enables AC 1–5 by providing the shared LLM-mediation layer + 4-line structural defense (scrub → LLM → validate → allowlist) all 5 surfaces compose. |
| **S2** Workflow surface | `Workflow.from_brief` classmethod + `WorkflowPlanSignature` + realizer + Tier-2 tests at `tests/integration/kailash/test_workflow_from_brief.py` (3 brief shapes). ~450 LOC. | LLM-mediated graph synthesis; deterministic realization via `WorkflowBuilder.add_node/add_connection`; round-trip `wf.build().execute()`. | AC 1 (Workflow.from_brief returns WorkflowBuilder whose .build().execute() runs end-to-end) + AC 6 (3-brief-shape Tier-2 test). |
| **S3** DataFlow surface | `DataFlow.from_brief` classmethod + `SchemaPlanSignature` + realizer + Tier-2 tests at `tests/integration/dataflow/test_dataflow_from_brief.py` (2 brief shapes). ~450 LOC. | LLM-mediated schema synthesis; deterministic `@db.model` registration; round-trip `create()` → `get()` against real Postgres container. | AC 2 (DataFlow.from_brief returns DataFlow with round-trip-clean models) + AC 7 (2-brief-shape Tier-2 test). |
| **S4** Kaizen surface | `Kaizen.signature_from_brief` classmethod + `SignaturePlanSignature` + meta-Signature realizer + Tier-2 tests at `tests/integration/kaizen/test_signature_from_brief.py` (2 brief shapes). ~400 LOC. | LLM-mediated Signature synthesis; deterministic realization via `SignatureMeta`; usability as `signature=` arg to Kaizen agent constructor. | AC 3 (Kaizen.signature_from_brief returns usable Signature subclass) + AC 8 (2-brief-shape Tier-2 test). |
| **S5** Bootstrap surface | New `src/kailash/bootstrap.py` module + `BootstrapConfig` dataclass + `BootstrapPlanSignature` + env-aware ReActAgent + Tier-2 tests at `tests/integration/kailash/test_bootstrap.py` (2 profiles). ~450 LOC. | `.env`-grounded config resolution; profile-honoring; env-aware ReAct grounding. | AC 4 (kailash.bootstrap returns BootstrapConfig resolving db_url/llm_model/runtime/deployment_target) + AC 9 (dev/prod profile Tier-2 test). |
| **S6** ML surface + docs | `kailash_ml.from_brief` + `MLPlanSignature` + realizer + Tier-2 tests at `tests/integration/ml/test_ml_from_brief.py` (classification + regression) + README Quick Start update including the **5-surface comparison table** (C3a — which surface uses classmethod vs module function and WHY) + `with_features` adapter docs example (C2a). ~500 LOC. | Dataframe-schema → FeatureSchema realization; ModelSpec.task matches brief intent; docs rewrite uses `from_brief()` entry points; comparison table makes naming inconsistencies feel principled. | AC 5 (kailash_ml.from_brief returns (FeatureSchema, ModelSpec, EvalSpec) triple) + AC 10 (classification/regression Tier-2 test) + AC 11 (README Quick Start update). |

Each shard ≤500 LOC of load-bearing logic; each holds ≤5 invariants (within `rules/autonomous-execution.md` MUST-1 ceiling). Total: 6 shards × ~1 autonomous-execution cycle each = 6 sessions (or 2-3 days if parallelized into waves of 3 per `rules/worktree-isolation.md` Rule 4). Greenfield adjustment per `rules/autonomous-execution.md` § Conversion: first 1-2 shards run at ~2-3x multiplier (no prior Kailash precedent for LLM-mediated `from_brief` patterns); remaining 4 shards inherit the foundation pattern from S1 and run at standard ~10x.

### Shard sequencing constraints

- S1 MUST land before S2-S6 (provides the shared LLM-mediation layer).
- S2-S6 are independent of each other AFTER S1 lands; they can run as a parallel wave of 3 + a follow-up wave of 2 (per `rules/worktree-isolation.md` Rule 4 cap), with S6's README update synthesizing all 5 surfaces at the end.

## 8. Risks (named & disposition per Round 1)

These were named for `/redteam`; Round 1 (see `04-validate/round-01.md`) closed them as structural defenses in the design (now reflected in §3 pipeline diagram + §7 S1 invariants):

- **Prompt injection on the brief** (B1a). Realizers validate every LLM-emitted node-type / field-type / config-value string against allowlists BEFORE construction. Unknown values raise `BriefInterpretationError`. Source-of-truth allowlists: `core.list_node_types` (existing AST-scanned per `specs/mcp-server.md` §3.4) for Workflow; field-type enum for Kaizen; enum members for Bootstrap; declared dataframe columns for ML.
- **Secrets-in-brief** (B2a). S1 includes `scrub_brief()` routed via `kailash.utils.url_credentials.preencode_password_special_chars` + URL-pattern regex; runs BEFORE any logging path. Tier-2 fixtures additionally scanned (B2b) for no-secrets-in-fixtures.
- **Output validation** (B3a). Typed `BriefInterpretationError` exception + Pydantic-or-dataclass plan validator between every Signature output and realizer input. Realizer accepts ONLY validated typed objects.
- **Composition** (B5a / C6a). Cross-surface state inheritance OUT OF SCOPE for v1; documented as §6 Q8 deferral so future sessions don't re-derive the question.
- **Ambiguous briefs** (C1a). Every Signature outputs `interpretation_confidence: float`; realizer raises `BriefInterpretationError(low_confidence=True)` on confidence < 0.6. No fake-default auto-fill (per `rules/zero-tolerance.md` Rule 2).

## 9. Verification status

- **Brief verified:** `01-analysis/01-brief-verification.md` — 4 corrections, core HIGH-severity claim TRUE.
- **Verification methodology:** Independent re-grep per cluster against repo HEAD `06315fd5`. Reproducible.
- **Plan status:** Draft v1, awaits redteam (`/redteam` phase) convergence + human gate at `/todos`.

## Receipts

- Workspace SHA at plan write: see `git log` on `feat/1125-from-brief-analyze`.
- Architecture decisions cite `rules/agent-reasoning.md`, `rules/agents.md`, `rules/autonomous-execution.md`, `rules/recommendation-quality.md`, `rules/testing.md`, `rules/value-prioritization.md`, `rules/spec-accuracy.md`, `rules/zero-tolerance.md`, `rules/env-models.md`, `rules/security.md`, `rules/worktree-isolation.md` — all loaded in the session context.
