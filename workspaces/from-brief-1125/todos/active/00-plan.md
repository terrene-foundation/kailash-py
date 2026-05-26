# /todos active plan v1 — Issue #1125 `from_brief()` primitives

**Status:** Draft for human approval (Phase-02 structural gate per `workspaces/CLAUDE.md`).
**Source plan:** `workspaces/from-brief-1125/02-plans/01-architecture.md` v2 (Round-2 converged; 10/10 amendments VERIFIED).
**Brief:** `workspaces/from-brief-1125/briefs/00-brief.md` (verbatim issue #1125 body).
**Acceptance criteria:** AC 1-11 enumerated in the brief.
**Approved open-question dispositions:** see § "Approved dispositions" below — these are baked into the shards as concrete constraints.
**Per-PR Tier-2 cost (user-authorized):** ~$0.05–0.30 per CI run for the 11 LLM-API-bearing fixtures (best ballpark at gpt-4-class pricing). This is per-PR overhead, NOT a recurring monthly bill. User-authorized in /todos approval.

---

## Approved dispositions (carried from architecture plan §6 open questions)

These 8 dispositions were approved by the user. Each is baked into the shards below as a concrete constraint, not a "TBD".

| # | Question | Disposition | Where baked in |
|---|----------|-------------|----------------|
| Q1 | `FeatureSchema` choice for `kailash_ml.from_brief` | **Frozen + content-addressed** (`kailash_ml/features/schema.py:175`). S6 docs MUST teach the `with_features(new_features)` adapter pattern for end-user refinement. | S6 invariants + S6 docs section |
| Q2 | Bootstrap profile coverage | **`dev` and `prod` only** (matches AC 4). Other profile values raise `BriefInterpretationError`. | S5 invariants + S5 realizer |
| Q3 | MCP-tool exposure of `from_brief` family | **DEFER** (not in AC 1-11; out of scope for v1). Filed as v2 follow-up note. | "Out of scope" section below |
| Q4 | `scaffold_*` MCP tools deprecation | **KEEP** (different audience — IDE-driven code gen). Both coexist. | "Out of scope" section + S2-S6 docs do NOT deprecate scaffold tools |
| Q5 | Specs placement | **Extend existing** `specs/core-workflows.md` (430 lines), `specs/dataflow-core.md` (568 lines), `specs/ml-engines-v2.md` (2512 lines), `specs/kaizen-signatures.md` (244 lines). **Create new** `specs/bootstrap.md`. Per `spec-accuracy.md` Rule 5: code lands FIRST on `main`; spec extensions land in follow-up PRs AFTER each shard merges, describing only shipped behavior. | Each shard S2-S6 carries a "spec extension (post-merge)" deliverable |
| Q6 | Bootstrap enum values | **Lock at resolver** — `runtime ∈ {local, async, nexus}`, `deployment_target ∈ {dev, prod, containerized}`. Out-of-allowlist value raises `BriefInterpretationError` per `zero-tolerance.md` Rule 3 (no silent fallback). | S5 invariants + S5 typed-plan-validator |
| Q7 | Tier-2 fixtures directory | **`tests/regression/from_brief/fixtures/`** with one YAML per fixture (brief + expected shape + asserted invariants). Each shard's Tier-2 tests reference fixtures from this directory. | S1 invariants (fixtures-scan helper) + S2-S6 Tier-2 tests |
| Q8 | Cross-surface composition (chained briefs) | **DEFER to v2** (out of scope for AC 1-11). Documented in plan §6 Q8 so future sessions don't re-derive. | "Out of scope" section below |

---

## Specs reference table (per Q5)

Each shard updates its surface's spec inline per `rules/spec-accuracy.md` Rule 5 (code first, spec describes what landed). New spec files are authored AFTER the corresponding shard's code lands on `main`.

| Spec file | Status | Lines today | Shard touching it | Extension scope |
|-----------|--------|-------------|-------------------|-----------------|
| `specs/core-workflows.md` | Existing | 430 | S2 | New § "Workflow.from_brief" describing the classmethod, signature, return contract, AC 1 + 6 |
| `specs/dataflow-core.md` | Existing | 568 | S3 | New § "DataFlow.from_brief" describing the classmethod, conn_str semantics, round-trip contract, AC 2 + 7 |
| `specs/kaizen-signatures.md` | Existing | 244 | S4 | New § "Kaizen.signature_from_brief" describing the meta-Signature pattern, SignatureMeta realizer, AC 3 + 8 |
| `specs/ml-engines-v2.md` | Existing | 2512 | S6 | New § "kailash_ml.from_brief" describing the (FeatureSchema, ModelSpec, EvalSpec) triple, frozen-schema choice, with_features adapter, AC 5 + 10 |
| `specs/bootstrap.md` | **NEW** (author after S5 code lands) | — | S5 | Full new spec describing `kailash.bootstrap(brief, profile)`, BootstrapConfig dataclass, enum allowlists, dev/prod profiles, AC 4 + 9 |

Each spec extension is a **separate follow-up PR** after its shard's code PR merges. Spec PRs use `release/v*` branch convention if metadata-only, else a fresh `feat/<surface>-spec` branch.

---

## Sequencing diagram

```
                    ┌──────────────────────────────┐
                    │ S1 Foundation                │
                    │ (private LLM-mediation       │
                    │  layer + scrubber +          │
                    │  validator + allowlist +     │
                    │  confidence + fixture scan)  │
                    └────────────┬─────────────────┘
                                 │ MUST land before S2-S6
                                 ▼
        ┌───────────────────────┴────────────────────────┐
        │  Wave-of-3 parallel worktree agents            │
        │  (per worktree-isolation.md Rule 4 cap of 3)   │
        ├──────────────┬──────────────┬──────────────────┤
        │      S2      │      S3      │       S4         │
        │  Workflow    │  DataFlow    │  Kaizen          │
        │  surface     │  surface     │  Signature       │
        │              │              │  surface         │
        └──────┬───────┴──────┬───────┴───────┬──────────┘
               │ wait for all 3 to merge      │
               ▼                              ▼
        ┌──────────────────────┬──────────────────────────┐
        │  Wave-of-2 parallel worktree agents             │
        ├──────────────────────┬──────────────────────────┤
        │       S5             │         S6               │
        │  Bootstrap surface   │  ML surface + README     │
        │                      │  Quick Start (AC 11)     │
        └──────────────────────┴──────────────────────────┘
                               │
                               ▼
                       All 5 surfaces shipped;
                       spec extensions land
                       as follow-up PRs.
```

**Total:** 6 shards. **Wall-clock:** S1 sequential (~1 cycle, greenfield ~2-3× multiplier) + wave-of-3 in parallel (~1 cycle) + wave-of-2 in parallel (~1 cycle) = **~3 cycles** under the autonomous execution model per `rules/autonomous-execution.md` § 10x Throughput Multiplier (parallel-agent factor).

**Cap:** Each wave caps at 3 parallel worktree agents per `rules/worktree-isolation.md` MUST Rule 4 (waves of ≤3 — burst of 4+ Opus agents server-side rate-limits).

---

## Shard S1 — Foundation (LLM-mediation layer)

**ID:** S1
**Dependency:** None — must land before S2-S6.
**Wave:** Sequential (gate for the parallel waves below).
**Estimated LOC:** ~550 (boilerplate-class scaling per `autonomous-execution.md` MUST-2 — most additions are dataclass/exception boilerplate, not load-bearing logic).

**Value-anchor (per `value-prioritization.md` MUST-2 citing issue #1125 brief):**
> The brief asserts: "Without `from_brief()` primitives, the documented 'natural-language to running workflow' pipeline cannot complete without an engineer hand-authoring the intermediate Python classes." S1 delivers the shared LLM-mediation layer all 5 surfaces compose — without it, none of AC 1-5 can be satisfied. This is the foundation block; the user's brief explicitly enumerates all 5 surfaces as the target.

**Acceptance criteria satisfied:** Enables AC 1-5 (provides the shared infrastructure they all depend on); AC 6-10 indirectly (fixtures-scan helper).

**Files created/edited (absolute paths under worktree):**
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/src/kailash/_from_brief/__init__.py` — module init
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/src/kailash/_from_brief/scrubber.py` — `scrub_brief()` credential scrubber routed via `kailash.utils.url_credentials`
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/src/kailash/_from_brief/exceptions.py` — typed `BriefInterpretationError` (with `low_confidence`, `unknown_value`, `malformed` discriminator fields)
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/src/kailash/_from_brief/validator.py` — Pydantic/dataclass plan validator
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/src/kailash/_from_brief/allowlist.py` — allowlist-validation helpers (node-type / field-type / config-value)
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/src/kailash/_from_brief/confidence.py` — `interpretation_confidence` field contract + 0.6 threshold
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/src/kailash/_from_brief/branching.py` — branching-connection realizer helpers
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/src/kailash/_from_brief/signatures.py` — Kaizen `Signature` boilerplate base class shared across surfaces
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/regression/from_brief/__init__.py` — regression test package init
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/regression/from_brief/fixtures/.gitkeep` — fixtures dir (Q7)
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/regression/from_brief/test_fixtures_no_secrets.py` — pre-commit/CI fixture-scan test (B2b — no-secrets-in-fixtures discipline)
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/unit/_from_brief/test_scrubber.py` — Tier-1 unit tests
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/unit/_from_brief/test_validator.py`
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/unit/_from_brief/test_allowlist.py`

**Invariants (per `autonomous-execution.md` MUST Rule 1 — ≤5–10):**
1. LLM-first reasoning — no conditional logic on brief content (per `rules/agent-reasoning.md`).
2. `.env`-sourced model — every `from_brief` call reads `DEFAULT_LLM_MODEL` from env per `rules/env-models.md`.
3. Typed validation gate — every Signature output goes through `validator.py` before realizer.
4. Allowlist gate — every LLM-emitted node-type / field-type / config-value validated against source-of-truth allowlist.
5. Confidence gate — `interpretation_confidence < 0.6` raises `BriefInterpretationError(low_confidence=True)`.
6. Credential scrub gate — `scrub_brief()` runs BEFORE any logging path (B2a).
7. No-secrets fixtures scan — regex scan over `tests/regression/from_brief/fixtures/` raises `BriefFixtureLeakError` on match (B2b).

**Spec extension (post-merge follow-up PR):** None — S1 is private internal infrastructure (`_from_brief/`); no public surface to document. Implementation details live in code + docstrings.

---

## Shard S2 — `Workflow.from_brief` surface

**ID:** S2
**Dependency:** S1 (uses `_from_brief` infrastructure).
**Wave:** First parallel wave (with S3 + S4).
**Estimated LOC:** ~450.

**Value-anchor (per `value-prioritization.md` MUST-2 citing issue #1125 brief):**
> The brief's minimal repro names `Workflow.from_brief(brief)` as surface #1 and the AC 1 contract: "returns a `WorkflowBuilder` whose `.build().execute()` runs end-to-end on the synthesized graph." Today the call raises `AttributeError` — this shard converts the documented contract from "aspirational" to "executable", which is the issue's HIGH severity claim.

**Acceptance criteria satisfied:** AC 1 + AC 6.

**Files created/edited:**
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/src/kailash/workflow/from_brief.py` — `WorkflowPlanSignature` + `Workflow.from_brief` classmethod implementation
- Edit: `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/src/kailash/workflow/__init__.py` — bind `from_brief` classmethod onto `Workflow` class
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/integration/kailash/test_workflow_from_brief.py` — Tier-2 tests covering ≥3 brief shapes (simple linear, branching, error-path) per AC 6
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/regression/from_brief/fixtures/workflow_linear.yaml`
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/regression/from_brief/fixtures/workflow_branching.yaml`
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/regression/from_brief/fixtures/workflow_error_path.yaml`

**Invariants:**
1. LLM-mediated graph synthesis via Kaizen `ReActAgent` (with `core.list_node_types` introspection tool).
2. Deterministic realization via `WorkflowBuilder.add_node` / `add_connection` — no conditional logic on brief content.
3. Round-trip `wf.build().execute()` MUST succeed end-to-end (AC 1).
4. Node-type allowlist validation — every LLM-emitted node-type validated against `core.list_node_types` before construction.
5. Tier-2 tests assert SHAPE (isinstance, count, type) per `rules/testing.md` 3-tier section — NO MOCKING in Tier 2.

**Spec extension (post-merge follow-up PR):** Extend `specs/core-workflows.md` (430 lines today) with new § "Workflow.from_brief" describing classmethod signature, ReActAgent integration, allowlist behavior, executability contract. Lands on a fresh `feat/spec-workflow-from-brief` branch AFTER S2 code merges to main.

---

## Shard S3 — `DataFlow.from_brief` surface

**ID:** S3
**Dependency:** S1.
**Wave:** First parallel wave (with S2 + S4).
**Estimated LOC:** ~450.

**Value-anchor (per `value-prioritization.md` MUST-2 citing issue #1125 brief):**
> The brief's AC 2 contract: "returns a configured `DataFlow` whose synthesized model classes pass round-trip `create()` → `get()` against the connection string." Today, schema authoring requires hand-written `@db.model` classes — this shard delivers the prose → executable model pipeline the brief asserts is missing.

**Acceptance criteria satisfied:** AC 2 + AC 7.

**Files created/edited:**
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/packages/kailash-dataflow/src/dataflow/from_brief.py` — `SchemaPlanSignature` + `DataFlow.from_brief` classmethod
- Edit: `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/packages/kailash-dataflow/src/dataflow/__init__.py` — bind `from_brief` classmethod
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/integration/dataflow/test_dataflow_from_brief.py` — Tier-2 tests covering ≥2 brief shapes (single-model, multi-model with relationship) per AC 7
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/regression/from_brief/fixtures/dataflow_single_model.yaml`
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/regression/from_brief/fixtures/dataflow_multi_model.yaml`

**Invariants:**
1. LLM-mediated schema synthesis via Kaizen `Signature`-only (no ReAct needed).
2. Deterministic `@db.model` registration via `type()` calls bound to the `DataFlow` instance — no conditional logic on brief.
3. Round-trip `create()` → `get()` MUST succeed against real Postgres container per `rules/testing.md` § Tier-2 (NO MOCKING).
4. Field-type allowlist validation — every LLM-emitted field-type validated against DataFlow's known type set.
5. When `conn_str is None`, uses in-memory SQLite (existing `DataFlow()` default).
6. Does NOT use MCP `scaffold_model` tool (Q4 — different audience).

**Spec extension (post-merge follow-up PR):** Extend `specs/dataflow-core.md` (568 lines today) with new § "DataFlow.from_brief" describing classmethod, conn_str semantics, round-trip contract, scaffold-coexistence rationale. Spec file is >300 lines today — if extension pushes it past 800-line natural split point, split into sub-files per `specs-authority.md` Rule 8.

---

## Shard S4 — `Kaizen.signature_from_brief` surface

**ID:** S4
**Dependency:** S1.
**Wave:** First parallel wave (with S2 + S3).
**Estimated LOC:** ~400.

**Value-anchor (per `value-prioritization.md` MUST-2 citing issue #1125 brief):**
> The brief's AC 3 contract: "returns a `Signature` subclass with typed input + output fields, usable as the `signature=` arg to any Kaizen agent constructor." Today, Signature authoring is hand-written Python class boilerplate — this shard delivers the prose → runtime Signature class meta-pattern the brief asserts is missing.

**Acceptance criteria satisfied:** AC 3 + AC 8.

**Files created/edited:**
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/packages/kailash-kaizen/src/kaizen/signatures/from_brief.py` — `SignaturePlanSignature` + `Kaizen.signature_from_brief` classmethod
- Edit: `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/packages/kailash-kaizen/src/kaizen/__init__.py` — bind `signature_from_brief` classmethod
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/integration/kaizen/test_signature_from_brief.py` — Tier-2 tests covering ≥2 brief shapes (single-input single-output, multi-field) per AC 8
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/regression/from_brief/fixtures/kaizen_single_io.yaml`
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/regression/from_brief/fixtures/kaizen_multi_field.yaml`

**Invariants:**
1. LLM-mediated Signature synthesis via Kaizen `Signature`-only (meta — a Signature that produces a Signature spec).
2. Deterministic realization via existing `SignatureMeta` metaclass at `kaizen/signatures/core.py:118` — single `type(name, (Signature,), namespace)` call.
3. Return value usable as `signature=` arg to existing Kaizen agent constructors (round-trip test).
4. Field-type allowlist — input/output field types validated against Signature's known type set.
5. Verb chosen `signature_from_brief` (not `from_brief`) because the result is a `Signature` subclass, NOT a `Kaizen` instance (per architecture §4).

**Spec extension (post-merge follow-up PR):** Extend `specs/kaizen-signatures.md` (244 lines today) with new § "Kaizen.signature_from_brief" describing the meta-Signature pattern, `SignatureMeta` realization path, AC 3 + 8 contracts.

---

## Shard S5 — `kailash.bootstrap` surface

**ID:** S5
**Dependency:** S1 (+ wait for wave-of-3 to merge before launching).
**Wave:** Second parallel wave (with S6).
**Estimated LOC:** ~450.

**Value-anchor (per `value-prioritization.md` MUST-2 citing issue #1125 brief):**
> The brief's AC 4 contract: "returns a `BootstrapConfig` resolving `db_url`, `llm_model`, `runtime`, and `deployment_target` consistent with the brief + profile." Today, multi-component configuration requires separate hand-wired env reads and instantiation — this shard delivers the prose → typed config dataclass the brief asserts is missing.

**Acceptance criteria satisfied:** AC 4 + AC 9.

**Files created/edited:**
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/src/kailash/bootstrap.py` — top-level module exposing `kailash.bootstrap(...)` function + `BootstrapConfig` dataclass + `BootstrapPlanSignature`
- Edit: `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/src/kailash/__init__.py` — re-export `bootstrap` + `BootstrapConfig`
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/integration/kailash/test_bootstrap.py` — Tier-2 tests covering `dev` + `prod` profiles with env-var resolution per AC 9
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/regression/from_brief/fixtures/bootstrap_dev.yaml`
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/regression/from_brief/fixtures/bootstrap_prod.yaml`

**Invariants:**
1. LLM-mediated config resolution via Kaizen `ReActAgent` with `env_lookup` deterministic tool (reads `os.environ.get(...)` per `rules/env-models.md`).
2. Profile allowlist enforced at resolver — `profile ∈ {"dev", "prod"}` per Q2; other values raise `BriefInterpretationError(unknown_value="profile")`.
3. Enum allowlist enforced at resolver per Q6 — `runtime ∈ {"local", "async", "nexus"}`, `deployment_target ∈ {"dev", "prod", "containerized"}`; out-of-allowlist value raises `BriefInterpretationError` (no silent fallback per `zero-tolerance.md` Rule 3).
4. `.env`-grounded — `env_lookup` tool reads existing env vars before LLM proposes config values.
5. Tier-2 tests use real env vars (no monkeypatch leakage per `rules/testing.md` § env-var serialization).

**Spec extension (post-merge follow-up PR):** Author NEW `specs/bootstrap.md` describing `kailash.bootstrap(brief, profile)`, `BootstrapConfig` dataclass, profile + enum allowlists, dev/prod semantics. Update `specs/_index.md` to register the new spec. Per `specs-authority.md` Rule 1 (`_index.md` is the canonical manifest).

---

## Shard S6 — `kailash_ml.from_brief` surface + README Quick Start

**ID:** S6
**Dependency:** S1 (+ wait for wave-of-3 to merge before launching).
**Wave:** Second parallel wave (with S5).
**Estimated LOC:** ~500.

**Value-anchor (per `value-prioritization.md` MUST-2 citing issue #1125 brief):**
> The brief's AC 5 contract: "returns a `(FeatureSchema, ModelSpec, EvalSpec)` triple whose `FeatureSchema` matches the dataframe's columns and `ModelSpec.task` matches the brief's stated prediction goal." AC 11 contract: "Public docs (README Quick Start) updated to use `from_brief()` entry points instead of class-authoring entry points." S6 delivers the final ML surface AND the docs flip that makes all 5 surfaces user-discoverable.

**Acceptance criteria satisfied:** AC 5 + AC 10 + AC 11.

**Files created/edited:**
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/packages/kailash-ml/src/kailash_ml/from_brief.py` — `MLPlanSignature` + `kailash_ml.from_brief` module-level function
- Edit: `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/packages/kailash-ml/src/kailash_ml/__init__.py` — re-export `from_brief`
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/integration/ml/test_ml_from_brief.py` — Tier-2 tests covering classification + regression per AC 10
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/regression/from_brief/fixtures/ml_classification.yaml`
- `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/tests/regression/from_brief/fixtures/ml_regression.yaml`
- Edit: `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/from-brief-1125/README.md` — Quick Start replacement: replace class-authoring entry points with `from_brief()` entry points across all 5 surfaces. Includes the **5-surface comparison table** (C3a per architecture plan §7) explaining classmethod vs module-function naming, AND the `with_features(new_features)` adapter pattern docs (C2a per architecture plan §7) for frozen schema refinement.

**Invariants:**
1. LLM-mediated MLPlan synthesis via Kaizen `Signature`-only.
2. Deterministic dataframe-schema extraction BEFORE LLM call — `df.dtypes` extracted by realizer, passed as Signature input field (permitted structural plumbing per `rules/agent-reasoning.md`).
3. `FeatureSchema` returned uses the **frozen + content-addressed** type at `kailash_ml/features/schema.py:175` per Q1 (NOT the mutable `kailash_ml/types.py:157` version).
4. `FeatureSchema.columns` MUST match `df.columns` (AC 5).
5. `ModelSpec.task` MUST match brief's stated prediction goal (asserted by Tier-2 test).
6. README Quick Start uses `from_brief()` consistently and teaches `with_features(new_features)` adapter for refining the frozen schema.

**Spec extension (post-merge follow-up PR):** Extend `specs/ml-engines-v2.md` (2512 lines today — already large, may need split per `specs-authority.md` Rule 8 in this PR) with new § "kailash_ml.from_brief" describing the triple return, frozen-schema choice rationale, `with_features` adapter pattern, AC 5 + 10 contracts.

---

## Out of scope (per approved dispositions Q3 + Q4 + Q8)

These items were considered and explicitly deferred. The architecture plan §6 documents the rationale; this section records the deferral so future sessions don't re-derive.

- **MCP-tool exposure of `from_brief` family** (Q3 DEFER). Not in AC 1-11. If users want MCP-tool exposure later, file as v2 follow-up issue.
- **Deprecation of `scaffold_*` MCP tools** (Q4 KEEP). Different audience (operators using IDE-driven code gen). Both coexist; S2-S6 docs DO NOT deprecate scaffold tools.
- **Cross-surface composition / chained briefs** (Q8 DEFER). Users chaining `Workflow.from_brief(...)` after `DataFlow.from_brief(...)` — out of scope for v1 (AC 1-11 do not require shared state across calls). Filed as v2 follow-up. If implemented later, will need an optional `context: dict[str, Any]` kwarg on each `from_brief` — but adding it now without exercising it is premature stub per `zero-tolerance.md` Rule 2.

---

## Risk register (carried from architecture plan §8)

These risks were named at `/analyze`, closed at `/redteam` Round 2, and are now baked into shard invariants:

| Risk | Mitigation | Where enforced |
|------|------------|----------------|
| Prompt injection on brief (B1a) | Allowlist validation of LLM-emitted symbols against source-of-truth allowlists | S1 `allowlist.py` + S2/S3/S4 per-surface allowlists |
| Secrets in brief (B2a) | `scrub_brief()` runs before any logging path | S1 `scrubber.py` |
| Output validation (B3a) | Typed `BriefInterpretationError` + Pydantic plan validator | S1 `exceptions.py` + `validator.py` |
| Ambiguous briefs (C1a) | `interpretation_confidence` field + 0.6 threshold + typed error | S1 `confidence.py` |
| No-secrets in test fixtures (B2b) | Regex scan over `tests/regression/from_brief/fixtures/` raises `BriefFixtureLeakError` | S1 `test_fixtures_no_secrets.py` + pre-commit hook |
| Cross-surface composition (B5a/C6a) | DEFER to v2 (documented as Q8) | "Out of scope" section above |

---

## Approval gate (per `workspaces/CLAUDE.md` Phase-02 contract + `rules/communication.md` § Approval Gates)

This plan stops here for human approval before `/implement` may proceed. Please answer the three questions below; the next session will read your answer from this file or chat.

**1. Does this cover everything you described in the issue #1125 brief?**

(yes / no / partial — if partial, what's missing?)

> _Awaiting human answer._

**2. Is anything here that you didn't ask for or don't want?**

(yes / no — if yes, what should be removed?)

> _Awaiting human answer._

**3. Is anything missing that you expected to see?**

(yes / no — if yes, what should be added?)

> _Awaiting human answer._

---

**Plan author:** /todos phase orchestrator (Claude Code, 2026-05-26)
**Plan source:** `workspaces/from-brief-1125/02-plans/01-architecture.md` v2 + 8 approved dispositions (user-approved in this session)
**Next phase:** `/implement` (gated by human approval above)
