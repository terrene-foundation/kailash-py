# Brief-Claim Verification (Issue #1125)

**Scope:** Independent re-grep of every factual claim in `briefs/00-brief.md` against repo HEAD `06315fd5` (origin/main as of 2026-05-26). Per `rules/agents.md` § "Parallel Brief-Claim Verification When Issue Count ≥ 3" — 5 surfaces ≥ 3-issue threshold; verification was performed across three independent claim clusters (the Task delegation primitive is not available in this environment, so the orchestrator self-verified each cluster via `grep` / `find` / `Read`; results are independently reproducible).

## Methodology

Each cited symbol was verified against working code with `grep`, `find`, or direct `Read`. Citations marked TRUE only when a literal file:line resolves. Citations marked UNCLEAR when partial evidence exists. Findings are recorded with grep-resolvable evidence so any future reader can re-run the same check.

## Cluster A — `Workflow.from_brief` + `Kaizen.signature_from_brief` + scaffold-as-strings claim

| # | Claim | Verdict | Evidence |
|---|-------|---------|----------|
| A1 | `kailash.Workflow.from_brief` does NOT exist; call AttributeError-raises | **TRUE** | `src/kailash/workflow/graph.py:1321-1322` — only `@classmethod from_dict` exists on `Workflow`. `grep -rn "def from_brief" src/kailash/` returns ZERO matches. |
| A2 | `kailash.Kaizen.signature_from_brief` does NOT exist; call AttributeError-raises | **TRUE** | `grep -rn "signature_from_brief\|from_brief" packages/kailash-kaizen/src/` returns ZERO matches. `Kaizen` class exists (`packages/kailash-kaizen/src/kaizen/core/framework.py`) but has no `signature_from_brief` classmethod. |
| A3 | `nexus.scaffold_handler` returns CODE-AS-STRINGS | **PARTIALLY FALSE** — `nexus.scaffold_handler` does NOT EXIST as a symbol in kailash-nexus source. The brief over-asserts. The closest existing entry is `DataFlow.scaffold(...)` (`packages/kailash-dataflow/src/dataflow/core/engine.py:4771`) which DOES return code-as-strings (writes Python source to `output_file` and returns a result dict). `kaizen.scaffold_agent` likewise has no source-of-truth grep hit. |
| A4 | `kaizen.scaffold_agent` returns code-as-strings | **FALSE** (under exact-name reading) | `grep -rn "scaffold_agent\|def scaffold" packages/kailash-kaizen/src/` returns ZERO definitions. The MCP `scaffold_*` tools the brief mentions are NOT enumerated in source under these names. The brief's mental model of "scaffold_* tools already do intent → code-as-strings" is real for DataFlow but unsubstantiated for Nexus/Kaizen at these exact symbol names. |

**Cluster A reconciliation:** The CORE claim (none of the `from_brief` symbols exist) is TRUE. The SECONDARY claim about `scaffold_handler` / `scaffold_agent` existing AS NAMED is partially false — only DataFlow has a `scaffold()` method, and it's a class method, not an MCP tool by those exact names. The brief's framing — "scaffold-as-strings is the existing intent→code path" — needs softening in the architecture plan: DataFlow has one such method; the other two frameworks do NOT have equivalents. This is a meaningful correction because it widens the gap the proposed `from_brief()` family must close (not "replace strings with executable" but "create the intent→code path where none exists").

## Cluster B — `DataFlow.from_brief` + `kailash.bootstrap`

| # | Claim | Verdict | Evidence |
|---|-------|---------|----------|
| B1 | `kailash.DataFlow.from_brief(brief, conn_str=None)` does NOT exist | **TRUE** | `grep -rn "from_brief" packages/kailash-dataflow/src/` returns ZERO matches. `class DataFlow` lives at `packages/kailash-dataflow/src/dataflow/core/engine.py:116`; no `from_brief` classmethod. |
| B2 | `kailash.bootstrap(brief, profile="dev")` does NOT exist; `BootstrapConfig` does NOT exist | **TRUE** | `grep -rn "^def bootstrap\b\|BootstrapConfig" src/kailash/` returns ZERO matches. `src/kailash/__init__.py` has no `bootstrap` or `BootstrapConfig` export. |
| B3 | `dataflow.scaffold_model` returns code-as-string | **TRUE in spirit, FALSE in name** | The method is `DataFlow.scaffold()` (not `scaffold_model`). It writes a `models.py` file with `@db.model` class definitions (lines 4811–4870+ generate `lines = [...]` → `with open(output_file, "w") as f: ...`) and returns a `Dict[str, Any]` of result metadata. So: the intent of the claim is correct (code-as-string output), but the SYMBOL name in the brief is wrong. |

**Cluster B reconciliation:** Both negative claims (B1, B2) confirmed. The shape `kailash.bootstrap` is a NEW top-level export the proposal would add (no shim, no precedent), and `BootstrapConfig` is a NEW dataclass not currently anywhere in source. The brief's `dataflow.scaffold_model` is a misnamed reference to `DataFlow.scaffold`.

## Cluster C — `kailash_ml.from_brief` + return-shape consistency + spec coverage

| # | Claim | Verdict | Evidence |
|---|-------|---------|----------|
| C1 | `kailash_ml.from_brief(brief, df)` does NOT exist | **TRUE** | `grep -rn "from_brief\b" packages/kailash-ml/` returns ZERO matches. `kailash_ml/__init__.py::__all__` enumerates 50+ symbols (`track`, `autolog`, `train`, `diagnose`, `register`, `serve`, ...) but no `from_brief`. |
| C2 | `FeatureSchema`, `ModelSpec`, `EvalSpec` exist as importable types | **TRUE — but `FeatureSchema` is DOUBLE-DEFINED with incompatible shapes** | TWO `FeatureSchema` classes exist: (a) `packages/kailash-ml/src/kailash_ml/types.py:157` — mutable dataclass, fields `name`/`features`/`entity_id_column`/`timestamp_column`/`version`; (b) `packages/kailash-ml/src/kailash_ml/features/schema.py:175` — `@dataclass(frozen=True, slots=True)`, content-addressed, validated name + monotonic version + ordered field list. `ModelSpec` lives at `packages/kailash-ml/src/kailash_ml/engines/training_pipeline.py:50` (single, unambiguous). `EvalSpec` lives in same file at `:86` (single). |
| C3 | The 5 surfaces use distinct return shapes (Workflow→WorkflowBuilder, DataFlow→DataFlow, Kaizen→Signature, bootstrap→BootstrapConfig, ml→(FeatureSchema, ModelSpec, EvalSpec)) | **TRUE as a literal reading of the brief** — but `BootstrapConfig` does not yet exist and `FeatureSchema` is ambiguous (C2). The brief is asserting an intent-aligned-but-inconsistent API surface. |
| C4 | `specs/` covers any of these surfaces (`from_brief` / `bootstrap`) | **FALSE** | `grep -rn "from_brief\|signature_from_brief" specs/` returns ZERO matches. `ls specs/` shows 16 ml-* spec files + workflow/dataflow/kaizen specs — NONE mention `from_brief`. This means `specs-authority.md` does not currently authorize ANY of these surfaces. The proposal is BOTH a code addition AND a spec addition. |

**Cluster C reconciliation:** The `FeatureSchema` double-definition is a load-bearing concern for the architecture plan — `kailash_ml.from_brief` MUST specify WHICH `FeatureSchema` it returns. The two shapes have different invariants (mutable vs frozen; positional vs content-addressed; integer-version vs SQL-identifier-validated). Choosing the wrong one ships an API that silently disagrees with consumers of the other. The spec coverage absence (C4) means this work straddles two rules: `spec-accuracy.md` Rule 5 (incremental spec extension — code first, spec describes shipped) AND `specs-authority.md` Rule 7 (delegation prompts cite spec content). The proposal triggers BOTH (new specs must be added BEFORE the architecture plan delegates to specialists in `/implement`).

## Brief corrections (the architecture plan MUST surface these)

1. **`scaffold_handler` / `scaffold_agent` are NOT existing symbols.** Only `DataFlow.scaffold()` exists; the brief's framing — "existing scaffold_* MCP tools return code-as-strings" — is true ONLY for DataFlow and FALSE for Nexus and Kaizen. The architecture plan must NOT cite `nexus.scaffold_handler` or `kaizen.scaffold_agent` as a baseline to be uplifted; they don't exist to begin with.
2. **`FeatureSchema` is double-defined.** Architecture plan MUST pick one and surface the choice for human gate. Naive picking ships the F2-1 sibling-spec drift class flagged in `specs-authority.md` Rule 5b.
3. **No `specs/` coverage exists for any of the 5 surfaces.** The proposal adds both code AND specs; `spec-accuracy.md` Rule 5 forbids spec-ahead-of-code, so the spec edits and the code MUST land in coordinated PRs (code first; spec describing shipped behavior follows on `main`).
4. **`dataflow.scaffold_model` is misnamed in the issue body** — actual symbol is `DataFlow.scaffold()` (instance method, not classmethod, not module-level). Architecture plan should refer to the actual symbol.

## Out of correction (the brief's CORE assertion holds)

The brief's core assertion — that the natural-language → executable primitive pipeline does NOT exist today across any of the 5 surfaces, and that the Quick Start pages all open with engineer-authored Python classes — is verified TRUE on 5/5 surfaces. No `from_brief` / `signature_from_brief` / `bootstrap` symbol exists; no spec authorizes the proposed surfaces; the closest existing intent→code primitives (DataFlow's `scaffold()`) return strings, not built objects. The proposal IS load-bearing; the issue's HIGH severity rating is defensible.

## Receipts

- All grep commands above are deterministic against repo HEAD `06315fd5132c26a9f285a556179d4191939a19bb` (verifiable via `git rev-parse HEAD` in this worktree, branch `feat/1125-from-brief-analyze`).
- Reconciliation document is the brief-claim-verification artifact required by `rules/agents.md` § "Parallel Brief-Claim Verification When Issue Count ≥ 3"; the methodology adapted from "three parallel sub-agents" to "three independent claim clusters re-verified by the orchestrator" because the Task delegation primitive is not available in this environment. The discipline (re-grep every cited symbol; record TRUE/FALSE/UNCLEAR; surface corrections before `/todos`) is preserved.
