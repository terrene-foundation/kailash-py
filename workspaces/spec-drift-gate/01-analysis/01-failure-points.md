# Spec Drift Gate — Failure Point Analysis

**Date:** 2026-04-26
**Workspace:** `workspaces/spec-drift-gate/`
**Brief:** `briefs/01-product-brief.md` (2026-04-26)
**Author:** analyst

## Executive Summary

The spec-drift-gate proposes a mechanical CI/pre-commit check that verifies "is implemented" assertions in `specs/*.md` against actual code. The primary failure modes fall into five orthogonal axes: **false positives** (gate blocks legitimate prose), **false negatives** (gate misses real drift in dynamically-resolved code), **performance/scale** (corpus is 72 specs and growing), **adoption/agent behavior** (gate becomes the new mock), and **cross-SDK/future evolution** (Rust sibling, executable annex). Highest-severity failure mode: **B1 (re-exports through `__getattr__`)** — verified in W6.5 review where `kailash_ml.AutoMLEngine` resolves to LEGACY scaffold via `__getattr__`, but a class-name AST grep on `class AutoMLEngine` finds the wrong class with no signal of mismatch. This is the exact pattern the gate must catch and the one most likely to be missed by a naive `class.*Error` regex sweep.

The leverage point on which most mitigations depend is the **marker convention** (brief Open Question #2): whether the gate uses backticks-only context, an explicit `<!-- spec-drift-gate:ignore -->` HTML comment, section-header context (e.g. "Deferred to M2"), or a structured machine-readable annex. Of the 28 mitigations enumerated below, **17 depend directly on the marker convention** — informal mention exclusion, deferred-section parsing, ignore-list governance, code-block context distinction, and the F1/F2 adversarial cases all collapse to "what does the gate consider an assertion vs. prose."

Complexity: **Moderate** (well-scoped, but the FP/FN trade-off is non-trivial and demands prototyping).

---

## A. False Positives — Gate Blocks Legitimate Work

### A1. Informal class mention in prose

**Trigger.** Spec narrative refers to a class for context but does not assert its existence at a path. Example: in `specs/ml-engines-v2.md:113` the rationale paragraph says "the v0.9.x audit identified the 'six-constructor ceremony' (FeatureStore + ModelRegistry + TrainingPipeline + ExperimentTracker + ConnectionManager + ArtifactStore) as the #1 DX failure." `TrainingPipeline` and `ConnectionManager` are mentioned as historical concepts; the spec does not assert they exist on the canonical 1.0+ surface. A naive regex `class \w+Manager|class \w+Pipeline` would flag both.

**Blast radius.** HIGH. False positives compound across 72 specs. Even at 5% FP rate per spec, the gate fires on ~4 specs per PR with no signal, and authors learn to bypass the gate (D1).

**Mitigation.** The gate MUST distinguish _assertion context_ from _narrative context_. Concrete strategies, in increasing rigor:

1. **Backtick-only matching** — only consider class names inside inline code (\`FeatureStore\`) or fenced code blocks. Prose mentions "FeatureStore" as an English noun are skipped.
2. **Sentence-class heuristic** — flag only when the assertion verb pattern is present: "exists", "is defined", "lives at", "located at", "MUST be", "MUST exist", "Verified at `path:line`".
3. **Explicit assertion table** — only "is implemented" claims inside assertion tables (Markdown tables with columns like `Spec promise | Implementation source | Status`) count.
4. **Marker convention** — opt-out via `<!-- spec-drift-gate:ignore-next-paragraph -->` / `<!-- spec-drift-gate:ignore -->` HTML comments OR explicit machine-readable annex (`<!-- mech: class:kailash_ml.automl.AutoMLEngine -->`) per brief.

**Example.** `ml-engines-v2.md:113` rationale paragraph mentions `TrainingPipeline` (historical six-constructor ceremony). With strategy (2), the gate skips because the sentence has no assertion verb. With strategy (1), `TrainingPipeline` is in backticks and would be flagged unless paired with a citation. Strategy (3) is most robust: the W6.5 v2 drafts already use assertion tables (see `W6.5-v2-draft-review.md` line 45-65 for AutoML and 137-156 for FeatureStore) — these are the gate's primary input surface.

### A2. Cross-spec sibling references

**Trigger.** Spec A references symbols owned by spec B for navigation, not for verification. Example: `specs/ml-engines-v2.md:7-12` lists companion specs and the symbols each owns: "`ml-feature-store.md` — `FeatureStore` schema versioning". `FeatureStore` is mentioned in `ml-engines-v2.md` but its existence is verified by `ml-feature-store.md`, not by `ml-engines-v2.md`.

**Blast radius.** MED. Incorrectly flagging cross-spec references produces N×M false positives where N = specs and M = average sibling refs per spec (~5-10 from `_index.md` table inspection).

**Mitigation.** Two-pass design.

1. **Symbol ownership map** — gate first builds a map: every spec declares which symbols it OWNS (canonical authority). A sibling reference to that symbol resolves to the OWNER's verification, not the citing spec's. Implementation: `<!-- mech: owns:kailash_ml.features.FeatureStore -->` or extract from assertion tables.
2. **Reference resolution** — when spec A asserts "see `ml-feature-store.md` § 3 for `FeatureStore`", gate verifies (a) `ml-feature-store.md` exists, (b) section 3 exists in that file, (c) the symbol IS owned by `ml-feature-store.md` per its assertion table — but does NOT re-verify the symbol against code in spec A's pass.

**Example.** `_index.md:75` ("ml-engines-v2.md ... `Trainable` protocol, `TrainingResult` + `DeviceReport`") owns those symbols; their existence is verified ONCE when `ml-engines-v2.md` is the spec under sweep, not every time another spec mentions them.

### A3. Deferred-section references

**Trigger.** `specs/ml-feature-store.md` § 11 "Deferred to M2" enumerates symbols intentionally absent from the codebase (`@feature` decorator, `FeatureGroup`, `OnlineStoreUnavailableError`). The whole section's purpose is to document NON-existence. A naive sweep flags every entry as a missing symbol.

**Blast radius.** CRIT. The W6.5 FeatureStore v2 draft has 11 entries in § 11. Every one is "absent by design". A gate that flags all 11 would block the PR that adds the deferred section — the EXACT structure the W6.5 review approved as best practice. This kills gate adoption immediately.

**Mitigation.** Section-header context required. Gate parses Markdown structure (section headings) and skips assertions under sections matching:

- `^#+\s+(.*Deferred|Awaiting M2|Out of Scope|Removed|Legacy|Non-Goals|MUST NOT)`
- explicit marker `<!-- spec-drift-gate:section-deferred -->` at section start

The gate should also positively check the inverse: a spec's "Deferred" section MUST NOT contain symbols that DO exist in code (which would be silently-implemented features the spec falsely claims are deferred). This is a small additional sweep but catches a subtler drift.

**Example.** `ml-feature-store.md:478` "## 11. Deferred to M2" → § 11.1 mentions `FeatureGroup` class. Gate sees the parent `## 11. Deferred to M2` heading, skips. § 11.7 "Typed Exceptions Absent At The Surface (F-E2-22)" — same skip. This is exactly the pattern that W6.5 round 2 of FeatureStore adopted (lines 478-540) and that round 1 violated by listing `FeatureGroupNotFoundError` etc. in § 10.2 (a NON-deferred section header) — that's the CRIT-1 case the gate exists to catch.

### A4. Example code in code blocks

**Trigger.** Specs use `python` blocks to teach API usage. Some declare new classes for illustration: `ml-engines-v2.md:65-72` shows "DO" / "DO NOT" examples that import `AutoModelForSequenceClassification` from transformers (an external library) and reference `package_data = {"kailash_ml": ["weights/bert-base.bin"]}` (a hypothetical anti-pattern not in code).

**Blast radius.** HIGH if mishandled. Code blocks contain the densest concentration of class/symbol mentions in a typical spec — most are real, some are anti-pattern examples, some are external libraries.

**Mitigation.** Three-tier handling:

1. **Line-prefix detection in code blocks** — lines starting with `# DO NOT` or `# Anti-pattern` or `# Hypothetical` mark the following code as illustrative, not assertional. Match preceding `# DO` blocks against code; skip `# DO NOT` blocks.
2. **External-library skip-list** — gate ships with a built-in skip list for stdlib (`asyncio`, `pathlib`, `typing`, `dataclasses`), well-known external libs (`transformers`, `polars`, `torch`, `sklearn`, `pl.LazyFrame`, `pd.DataFrame`), and project-declared third-party deps (read from `pyproject.toml [dependencies]`). `AutoModelForSequenceClassification` resolves to `transformers` → skipped. `FeatureStore` does not resolve to a known external → verify against project source.
3. **Code-block-as-assertion only when paired with citation** — the W6.5 v2 draft pattern: assertion tables cite `(file:line)` immediately before/after the block. Code blocks WITHOUT a `path/to/file.py:NNN` citation in the surrounding context are illustrative. With strategy (3), `ml-feature-store.md:75-82` (cited as `features/store.py:98-114`) IS an assertion; `ml-engines-v2.md:65-72` (cited only as anti-pattern) is NOT.

**Example.** `ml-feature-store.md:58-67` shows `__all__ = ["CANONICAL_SINGLE_TENANT_SENTINEL", "FeatureField", ...]` immediately preceded by "Verified at `features/__init__.py:12-27`". This is an assertion (verify each symbol). Conversely, `ml-engines-v2.md:140-145` shows "DO NOT — per-primitive env var proliferation" with `KAILASH_ML_TRACKER_DB`, `KAILASH_ML_REGISTRY_URL` — the anti-pattern block. Strategy (1) sees `# DO NOT` and skips.

### A5. Standard-library / external class references

**Trigger.** Spec mentions `asyncio.Task`, `pl.LazyFrame`, `lightning.Trainer`, `sklearn.linear_model.LogisticRegression`. Gate sweeping `class \w+` regex over python files would not find these in the project source and would flag them as missing.

**Blast radius.** MED. Likely produces 10-30 false positives per spec depending on how heavily it depends on external libs.

**Mitigation.** Same as A4 strategy (2): external-library skip-list. Implementation:

1. Symbols namespaced under recognized stdlib roots (`asyncio.`, `typing.`, `pathlib.`) → skip.
2. Symbols namespaced under declared third-party packages (read from `pyproject.toml`, `packages/*/pyproject.toml`) → skip.
3. Symbols cited via fully-qualified path that resolves to NEITHER project source NOR known external → MED finding (potential typo); not blocking unless fully-qualified path includes project root.

**Example.** `ml-engines-v2.md:107` `LightningTrainer(accelerator="auto")` and `:166-167` `ConnectionManager(url)` / `ModelRegistry(conn)` — `LightningTrainer` is a hypothetical wrapper (the spec discusses it as a default Engine constructs internally) but the actual class might live at `packages/kailash-ml/src/kailash_ml/...`; `ConnectionManager` may be in `kailash.db.connection_manager`. The gate must resolve fully-qualified names, not bare class names, OR explicitly require the spec to qualify them.

---

## B. False Negatives — Gate Misses Real Drift

### B1. Re-exports through `__getattr__`

**Trigger.** `kailash_ml.AutoMLEngine` is exposed via runtime `__getattr__` resolution in `kailash_ml/__init__.py` that maps the name to a module path. The actual mapping at line 593 (per W6.5 review HIGH-2 in `W6.5-v2-draft-review.md:80`) is `"AutoMLEngine": "kailash_ml.engines.automl_engine"` — i.e., resolves to the LEGACY scaffold, not the canonical `kailash_ml.automl.AutoMLEngine` class. A mechanical `grep -n 'class AutoMLEngine' packages/` finds TWO classes: legacy at `engines/automl_engine.py:425` and canonical at `automl/engine.py:410`. The gate's job is to detect that the cited symbol resolves to a different class than the spec expects.

**Blast radius.** CRIT. This is THE canonical Wave 6 finding (F-E2-01 in `W5-E2-findings.md:39-47`). It is the exact failure mode the gate is built to catch. If the gate misses it, the gate has zero credibility on day one.

**Mitigation.** Resolution-tracing, not name-grep.

1. **AST + import-graph trace.** When a spec asserts "`from kailash_ml import AutoMLEngine`", the gate MUST trace: `kailash_ml/__init__.py` → `__getattr__` map → resolve to module path → AST-parse THAT module → confirm class definition → match constructor signature against spec.
2. **Two-class disambiguation.** When two classes share a name across the codebase, the gate MUST require the spec to disambiguate via fully-qualified path (`kailash_ml.automl.AutoMLEngine` vs. `kailash_ml.engines.automl_engine.AutoMLEngine`) OR the gate MUST resolve through the public surface (`from kailash_ml import X` → trust `__getattr__` map).
3. **Spec MUST cite the import path.** The convention adopted in W6.5 round 2 of FeatureStore (line 86: "Verified at `features/store.py:98-114`") is the pattern. Gate enforces: every "is implemented" assertion cites a path; gate checks THAT path, not a name search.

**Example.** F-E2-01 (W5-E2-findings.md:39-47): "Two divergent `AutoMLEngine` implementations". Spec § 2.1 declares constructor `(config, feature_store, model_registry, trials_store, tenant_id, tracker)`. Canonical at `automl/engine.py:410` has `(*, config, tenant_id, actor_id, connection, cost_tracker, governance_engine)` — does NOT accept `feature_store`. A bare `class AutoMLEngine` regex finds the class but does NOT compare signatures; only AST signature comparison catches it. Mitigation strategy (1) is mandatory.

### B2. Indirect / lazy / conditional imports

**Trigger.** `try: from X import Y; except ImportError: Y = None` patterns. Symbol "exists" at one path but only when an extra is installed. Spec asserts "Y exists in module X"; gate verifies AST-level presence; but the runtime behavior is that `Y` may be `None` at import time.

**Blast radius.** MED. Common in ML/AI code that depends on optional `[gpu]` / `[torch]` / `[onnx]` extras. Spec might assert "ONNX export is provided by `kailash_ml.bridge.onnx_exporter`"; AST finds the class; runtime importer fails because the user doesn't have `[onnx]`.

**Mitigation.** Two-tier classification:

1. **AST presence is sufficient for "is defined"** — if the class is in source, the gate considers the assertion satisfied.
2. **Conditional imports flagged separately** — gate lints for `try/except ImportError: X = None` and emits MED warning "extra-gated symbol: spec MUST declare which extra installs it". Cross-references `rules/dependencies.md`.

**Example.** `ml-engines-v2.md:7-12` companion-spec list mentions classes that may be in `[dl]` / `[ml]` extras. Gate AST-checks the class presence but separately verifies the extras-gating story.

### B3. Dynamically-generated classes (metaclass / `type(...)` factories)

**Trigger.** Some classes are generated at import time by a factory function: `MyClass = type("MyClass", (Base,), {"foo": lambda self: ...})` or via metaclass. AST grep on `class MyClass` returns zero matches. Spec assertion fails.

**Blast radius.** LOW. Rare in kailash-py codebase (a quick grep `^MyClass\s*=\s*type\(` would show this is uncommon). But it occurs in agent scaffolds and DataFlow's auto-generated nodes (140+ nodes per `_index.md` Core SDK section).

**Mitigation.** Defer to executable annex (M2). Day-1 gate produces FN here; document the limitation explicitly. As a partial mitigation, the gate scans for `type(<class_name_str>` and `<class_name_str>\s*=\s*type\(`, treats matches as candidate definitions.

**Example.** DataFlow auto-generates `UserCreateNode`, `UserReadNode`, etc. from `@db.model` decorators. Specs asserting "DataFlow auto-generates 9 nodes per `@db.model`" cannot be verified by class-name AST grep. Acceptance: the gate verifies the _generator_ (the `@db.model` decorator + node-class factory) exists and produces the documented count via a one-time dynamic introspection in the test tier — not in the gate's hot path.

### B4. Method existence on a class

**Trigger.** Spec says "`engine.fit_auto()` exists with signature `(data, *, task, target, time_budget, …)`" (per F-E2-08, `W5-E2-findings.md:91`). Gate finds `class MLEngine` at the right path. But `fit_auto` method is absent — only `fit()` exists. AST class-only check passes; method-level check fails.

**Blast radius.** HIGH. Methods are the second-most-common assertion type after class existence (probably equal frequency in the audit findings: F-E2-04 missing `executor=` kwarg, F-E2-08 missing `MLEngine.fit_auto`, F-E2-13 missing `MLEngine.monitor`).

**Mitigation.** Walk the class body's AST. Per `skills/spec-compliance/SKILL.md:50-63` (Step 2 Check 1), the verification protocol already mandates this: "Use `ast.parse` for precision … `init = next((n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == "__init__"), None); params = [a.arg for a in (init.args.args if init else [])]`". The gate MUST implement this walk for every method-level assertion.

**Example.** F-E2-08 (`W5-E2-findings.md:91-96`): spec declares `MLEngine.fit_auto(data, *, task, target, time_budget, ...) -> LeaderboardReport`. Gate AST walks `class MLEngine`, lists method names, finds `fit` but not `fit_auto`, and `LeaderboardReport` dataclass is also absent — three drifts in one assertion. The gate MUST report all three.

### B5. Field existence on a dataclass

**Trigger.** Same as B4 but for `@dataclass` fields. Spec asserts "`AutoMLConfig` has 13 fields including `early_stopping_patience` and `families`" (F-E2-08); actual class has neither.

**Blast radius.** HIGH. Dataclass field drift is common (F-E2-08, F-E2-30 default `db_url`, F-E2-12 `DriftMonitorConfig` absent entirely).

**Mitigation.** AST walk for `ast.AnnAssign` nodes inside the class body. Per `skills/spec-compliance/SKILL.md:74-83` (Check 2). Implementation: for each field name in the spec assertion table, look for an annotated assignment node with that target name inside the class body. Empty match = FAIL.

**Example.** `ml-feature-store.md:130-141` declares `FeatureSchema` with 6 fields including `content_hash` (init=False, derived). Gate AST-walks `features/schema.py`, finds the dataclass, checks each field. F-E2-12 case (`DriftMonitorConfig` declared in spec but absent in code) — gate finds zero `class DriftMonitorConfig` and zero `DriftMonitorConfig =` assignments → FAIL.

### B6. Test file existence vs test FUNCTION existence

**Trigger.** Spec says "Tier-2 wiring test at `tests/integration/test_feature_store_wiring.py`". File does NOT exist (W6.5 CRIT-2, `W6.5-v2-draft-review.md:178-198`). Spec asserts a function `test_create_index_rejects_sql_injection` inside an existing file; the file exists but the function was deleted in a refactor.

**Blast radius.** HIGH. CRIT-2 in W6.5 review is exactly this case. Spec lied about a file's existence; downstream code following the spec for `rules/facade-manager-detection.md` Rule 1 compliance silently shipped a manager with no Tier-2 coverage.

**Mitigation.** Two-level check:

1. **File existence** via `pathlib.Path.exists()`.
2. **Function existence** via `pytest --collect-only -q <file>` OR AST walk for `ast.FunctionDef` with names starting with `test_`.

Both must succeed. Spec assertion of a test path MUST cite the test file; if the spec also names the test function, the gate verifies the function name appears.

**Example.** W6.5 CRIT-2: spec asserted `tests/integration/test_feature_store_wiring.py` exists. Gate's `pathlib` check returns False. CRIT finding. The next sweep should also detect that the EXISTING `test_feature_store.py` file imports the LEGACY `kailash_ml.engines.feature_store.FeatureStore` and NOT the canonical surface — a more sophisticated check that's worth deferring to M2 (see § E3).

### B7. Cross-package symbols

**Trigger.** `from kailash.ml.errors import FeatureNotFoundError` — symbol lives in `src/kailash/ml/errors.py` (top-level kailash, not packages/kailash-ml). Spec audited under packages/kailash-ml might assert "raises FeatureNotFoundError" without making the import path explicit. Gate searching ONLY `packages/kailash-ml/src/kailash_ml/` returns zero matches; FALSE FAIL.

**Blast radius.** HIGH. The errors taxonomy IS at `src/kailash/ml/errors.py` (per W6.5 review line 154-155 "verified `errors.py:632/636/641/340/589`"). Many ml-\* specs cite errors that live there.

**Mitigation.** Multi-root source resolution. Gate ships a config (`spec-drift-gate.toml`?) declaring source roots:

```
source_roots = [
    "src/",
    "packages/kailash-dataflow/src/",
    "packages/kailash-nexus/src/",
    "packages/kailash-kaizen/src/",
    "packages/kailash-pact/src/",
    "packages/kailash-ml/src/",
    "packages/kailash-align/src/",
    ...
]
```

Resolution searches all roots; first match wins (with disambiguation warning per B1 if multiple). Same config supports cross-SDK migration to kailash-rs (per E1).

**Example.** `ml-feature-store.md:294` "Verified at `kailash_ml.errors:632/636/641/340/589`" cites the canonical `kailash.ml.errors` taxonomy at the top-level `src/kailash/ml/errors.py`. Gate's `src/` root catches it; a packages-only sweep would miss it.

### B8. Renamed-but-not-removed legacy paths

**Trigger.** Both `kailash_ml.engines.feature_store.FeatureStore` (legacy) and `kailash_ml.features.store.FeatureStore` (canonical) ship. Spec doesn't disambiguate. Gate's first-match-wins resolves to whichever appears first in the source roots; might be the wrong one.

**Blast radius.** CRIT. This is structurally B1 (same name, two classes), but with the legacy/canonical asymmetry where ONE is correct and the gate must choose. F-E2-01 is the AutoML version of this; the FeatureStore version is exactly W6.5 CRIT-2 where the existing test exercises the LEGACY engine.

**Mitigation.** Same as B1 strategy (3): require fully-qualified import path in spec assertions. Gate emits HIGH finding when a name resolves to multiple classes within configured source roots and the spec doesn't disambiguate. Concretely: spec assertion "`FeatureStore` constructor signature" → gate MUST fail unless spec writes `kailash_ml.features.FeatureStore` (or equivalent disambiguation).

**Example.** F-E2-18 (`W5-E2-findings.md:174-179`) is the canonical case: spec § 2.1 wrote "`FeatureStore(store: str | ConnectionManager, *, online, tenant_id, ...)`" — but actual canonical at `features/store.py:98` is `FeatureStore(dataflow: DataFlow, *, default_tenant_id=None)`. The legacy at `engines/feature_store.py` matches yet another shape. Gate that just greps `class FeatureStore` finds three classes (canonical, legacy, possibly a test-fixture `FeatureStore`) and cannot tell which is canonical without the import path disambiguation.

---

## C. Performance & Scale

### C1. Spec corpus growth

**Trigger.** kailash-py has 72 specs today (verified via `Glob specs/**/*.md` → 72 entries). Brief mandates <30s wall clock. Per-spec budget = ~400ms.

**Blast radius.** MED → HIGH over time. If the gate runs in 25s today on 72 specs, the next 30 specs (within a quarter) push it to ~36s. CI minutes scale linearly; pre-commit becomes annoying enough that authors disable it (D2).

**Mitigation.** Three strategies:

1. **Incremental mode by default for pre-commit** — only sweep specs touched by `git diff HEAD`. Full-corpus sweep runs only in CI.
2. **AST cache** — parse each `.py` file once per run, cache the resulting `ast.Module` indexed by mtime. Reuse across spec sweeps.
3. **Symbol-index cache** — maintain `.spec-drift-cache/symbol-index.json` mapping every `class Foo` / `def bar` / `Baz =` declaration to `(path, line)`. Invalidate by file mtime. Lookup is O(1).

The brief's <30s budget is achievable for full-corpus sweep with strategy (3); for pre-commit incremental mode the budget should be <3s on any single-spec edit.

**Example.** `_index.md` shows 72 specs, conservatively 50-100 assertions each = ~5,000-7,000 assertions per full sweep. AST-walking a `.py` file costs ~10ms uncached, ~0ms cached. Symbol-index lookup is ~µs per hit. Realistic full-corpus runtime estimate: 10-15s with caching, 60-90s without.

### C2. AST parsing cost over the source tree

**Trigger.** Source tree includes `src/` (~70k LOC per top-level `find` count not run), `packages/kailash-*/src/` (each ~10-50k LOC). Total AST-parseable surface likely 200-500k LOC. Parsing all of it on every gate invocation is ~5-15s on a developer laptop.

**Blast radius.** MED. Doubles the runtime budget if not cached.

**Mitigation.** Symbol-index strategy from C1.3. Specifically: build the index once per run, parse only the `.py` files whose `class X` / `def X` declarations the spec assertions touch. For 5-10 unique symbols per spec, the gate parses 5-10 files, not 500.

**Example.** `ml-feature-store.md` cites `features/store.py`, `features/__init__.py`, `features/schema.py`, `features/cache_keys.py`, and references `errors.py`. ~5 files × 10ms = 50ms per spec. 72 specs × 50ms = 3.6s. Comfortably within budget.

### C3. Pre-commit runs on every commit

**Trigger.** `pre-commit` triggers on `git commit` regardless of which files changed. If the hook is configured to fire on `specs/**.md`, it runs only when those files change — fine. But the hook's source-tree dependencies (any `.py` file referenced in any spec) mean a `.py`-only edit to `src/kailash/ml/errors.py` does NOT trigger the hook, but DOES drift the spec's assertions about that file.

**Blast radius.** MED. The gate's drift-detection is asymmetric: spec edits trigger the gate; code edits that contradict an existing spec assertion do NOT. This is a subtle FN in the pre-commit configuration.

**Mitigation.** Two-tier hook:

1. **Pre-commit hook on `specs/**.md`\*\* — fast incremental check on the edited spec only.
2. **Pre-commit hook on `**/\*.py`** — when a `.py` file changes, find which specs cite that file (reverse index from the symbol-index) and re-verify only those specs' assertions about that file.

The reverse index is cheap to maintain alongside the symbol index.

**Example.** Editing `packages/kailash-ml/src/kailash_ml/features/store.py` to remove the `dataflow` constructor argument. `ml-feature-store.md:75-82` asserts the constructor signature includes `dataflow`. Pre-commit on the `.py` edit triggers re-verification of `ml-feature-store.md`, catches the drift, blocks the commit.

### C4. Cache invalidation

**Trigger.** Symbol-index cache invalidation is mtime-based. Edits to mtime (e.g. `touch`) without content change invalidate; legitimate content edits with mtime preservation (rare but possible via VCS hooks) skip invalidation.

**Blast radius.** LOW. Mtime-based invalidation is the standard approach and produces a tiny rate of false misses. Better than content-hash-per-file, which is more expensive.

**Mitigation.** mtime + size composite key. CI always runs from cold cache (no false-cache); developer pre-commit accepts occasional staleness, mitigated by `pre-commit run --all-files` periodic full-corpus run.

---

## D. Adoption & Agent Behavior

### D1. Gate becomes the new mock

**Trigger.** Agents add `<!-- spec-drift-gate:ignore -->` markers liberally to silence the gate rather than fix the assertion. Within 3-6 months, every spec has a sprinkling of ignore markers, and the gate's effective coverage drops to whatever the agents bothered to verify.

**Blast radius.** CRIT (long-term). Same failure mode as `# noqa`, `# type: ignore`, `@SuppressWarnings` — the universally observed degradation pattern of mechanical lint gates over time.

**Mitigation.** Four structural defenses:

1. **Ignore markers require justification + tracking issue.** The marker syntax MUST be `<!-- spec-drift-gate:ignore reason="X" issue="#NNN" -->`. Reason and issue are mandatory; gate fails if either is missing. Mirrors `rules/zero-tolerance.md` Rule 1b for "scanner deferral requires tracking issue + runtime-safety proof".
2. **Ignore counter in CI.** Every PR reports the delta in ignore-marker count vs main. `+5 ignores` on a PR triggers a special reviewer attention flag.
3. **Periodic ignore audit.** A weekly CI job lists every active ignore marker by spec, age, and tracking issue. Markers older than 60 days emit MED finding.
4. **`/redteam` cross-check.** `/redteam` Step 1 (this skill: `skills/spec-compliance/SKILL.md`) MUST cross-check that every gate-ignore marker in a spec it audits has a corresponding `<!-- spec-drift-gate:ignore -->` marker that genuinely justifies the absence — i.e., the agent doesn't trust the ignore, it re-verifies.

**Example.** Same evolution observed in CodeQL deferrals (`rules/zero-tolerance.md` Rule 1b origin: PR #611 release cycle): "17 `py/unsafe-cyclic-import` findings deferred via issue #612 after ml-specialist verified all cycles are TYPE_CHECKING-guarded; 23 other CodeQL errors fixed in the release PR." That's the workable pattern — defer with proof and tracking; don't dismiss.

### D2. Specialists fight the gate

**Trigger.** Framework specialist (e.g., dataflow-specialist, ml-specialist) ships a feature whose spec includes assertions the gate flags. Under deadline pressure, the specialist's path of least resistance is to disable the gate, soften the assertion, OR bypass via `--no-verify`.

**Blast radius.** HIGH. The specialists are the gate's primary users. If they don't trust the signal, the gate fails.

**Mitigation.** Three layers:

1. **Loud-signal output.** Gate output is structured: each finding includes spec file, line, assertion verbatim, expected vs actual, and a one-line remediation (per `skills/spec-compliance/SKILL.md` output format). Specialists can ACT on the finding, not just see "gate failed".
2. **Short, actionable feedback loop in pre-commit.** Pre-commit fails in <3s with a focused failure listing only the specialist's edited spec. CI failure lists the full failures with grouping.
3. **Specialist agent prompts include gate context.** Per `rules/agents.md` § "Specs Context in Delegation", every specialist delegation includes relevant spec content. The orchestrator MUST also include "this spec edit will be checked by spec-drift-gate; cite each MUST assertion with a `path:line` reference" in the delegation prompt.

**Example.** AutoML v2 round 1 (W6.5) per W6.5 review HIGH-1: "test path claim is wrong" — spec asserted `tests/unit/automl/` directory exists; it does not. The analyst could have re-derived from `find packages/kailash-ml/tests -name 'test_automl*'` BEFORE writing the assertion. Gate enforces this discipline.

### D3. False-positive fatigue

**Trigger.** Even at <5% FP rate (brief success criterion), 72 specs × 5% = ~4 FPs per full-corpus run. Over a quarter of CI runs, authors see thousands of FPs and become numb to gate output.

**Blast radius.** HIGH. Same failure mode as flaky tests (per `rules/testing.md` "Intermittent failures erode trust; developers start ignoring real failures").

**Mitigation.**

1. **Conservative defaults.** Day-1 gate has FN-leaning thresholds — better to miss a real issue than to ship 50 FPs. Tighten over time via empirical FP/FN measurement.
2. **FP triage workflow.** Each FP report includes a "report as FP" link/comment. Gate maintainers track FP patterns, harden the gate iteratively.
3. **Dogfood on representative specs.** Brief acceptance criterion #6 (demonstrate on Wave 6.5 CRIT-1) is the right calibration target; before rollout, run the gate against ALL 72 specs and tune until FP rate is <5% AND gate catches all known W5/W6.5 findings.

**Example.** The brief explicitly references "informal class mention in prose (e.g., 'imagine a `FooEngine` class…') MUST NOT trigger the gate." This is the test case for the marker convention. Gate development MUST start by running against all 72 specs in a "dry run" mode, comparing findings against the audit database (W5-E2 + W6.5 known issues + Wave 6 follow-ups), and tuning to minimize FP.

### D4. Baseline rot

**Trigger.** Per brief: "the existing 36-HIGH backlog passes via baseline snapshot; only new violations block." Six months later, the baseline has 80 entries, half are real drift that nobody fixed, the rest are stale from refactors. Nobody clears the baseline; new drift gets added because "the baseline already has stuff like this".

**Blast radius.** HIGH (long-term). Identical failure mode to ESLint baseline files, mypy `# type: ignore`, and Black `# fmt: off` accumulations.

**Mitigation.**

1. **Baseline entries expire.** Each entry has a `last_seen` and `expires` field. CI emits MED finding when entry is older than 90 days. Forces periodic cleanup.
2. **Baseline diff in PR comment.** Every PR comments showing `+3 / -1` baseline entries. Reviewers see when baseline grew.
3. **Quarterly baseline audit.** Calendar-driven `/redteam` cycle (cross-reference brief's relationship to existing /redteam) verifies every baseline entry against current code; expired ones are re-evaluated.
4. **Baseline entries cite the audit finding.** Every entry MUST link to F-E2-NN or equivalent. Entries with no audit-finding citation are rejected from the baseline. This forces the existing 36-HIGH backlog to be enumerated against W5-E2 findings before becoming baseline.

**Example.** F-E2-01..70 enumerates 70 W5-E2 findings of all severities; 38 were HIGH at audit close. After PR #637 (kailash 2.11.2 hotfix) closed 2 HIGHs and Wave 6.5 (PR #639) closed 13 more, the remaining HIGH backlog the gate's day-1 baseline must capture is **36 entries** (per `workspaces/portfolio-spec-audit/04-validate/00-portfolio-summary.md` line 12). Each baseline entry cites its F-E2 ID and 90-day age-out date. New violations added without citation = blocked. Canonical numbers: 70 total findings of all severities; 38 HIGHs at audit close; 36 HIGH backlog post-Wave-6.5 → S5 baseline target.

### D5. Inconsistent with /redteam

**Trigger.** Spec passes the gate (mechanical) but `/redteam` finds drift (semantic). OR `/redteam` clears a spec; gate later flags it. Authors don't know which to trust.

**Blast radius.** MED. Authority confusion delays merges and erodes both gate and `/redteam` credibility.

**Mitigation.** Define authority hierarchy explicitly in the gate's documentation:

1. **Gate is necessary, not sufficient.** Gate verifies mechanical assertions. `/redteam` verifies semantic alignment (intent vs implementation, missing test coverage, security mitigation tests, orphan classes — see `rules/orphan-detection.md` MUST 2 + `skills/spec-compliance/SKILL.md` checks 5-7). Gate green AND `/redteam` green → ship.
2. **`/redteam` consumes gate output.** `/redteam` Step 1 (`skills/spec-compliance/SKILL.md`) explicitly references the gate's symbol-index as a starting input, then performs additional semantic checks the gate skips.
3. **Conflicting verdicts → human gate.** When gate green and `/redteam` finds drift (or vice versa), the failure is sent to the spec author + reviewer for arbitration, not silently merged.

**Example.** Per `skills/spec-compliance/SKILL.md` Self-Report Trust Ban (line 162-169): `/redteam` MUST NOT trust prior `.spec-coverage` files. The gate's output is one input among several to `/redteam` Step 1, not a substitute.

---

## E. Cross-SDK & Future Evolution

### E1. Rust sibling drift

**Trigger.** `kailash-rs` ships its own specs/, its own /redteam, its own symbol resolution. Same gate? Per-SDK gate? Brief says "kailash-py first; design with kailash-rs in mind so the same gate ports across."

**Blast radius.** HIGH if not designed for it. Adding a kailash-rs-specific gate later (vs. configuring the same gate) means duplicate maintenance and divergent enforcement (`rules/cross-cli-parity.md` analog).

**Mitigation.** Configurable source roots + language adapters.

1. **`spec-drift-gate.toml` per-repo config.** `language = "python"` selects AST adapter. `language = "rust"` selects a tree-sitter or `syn`-based adapter. Symbol-resolution rules are language-agnostic; AST queries are language-specific.
2. **Shared assertion-table format.** Both SDKs adopt the same `Spec promise | Implementation source | Status` table convention, so the gate's parser is shared.
3. **Cross-SDK skill alignment.** Update `skills/spec-compliance/SKILL.md` once; the file already declares (line 71) "kailash-rs maintains its OWN equivalent verification protocol locally at `.claude/skills/spec-compliance/rust-parity.md`, which loom never overwrites."

**Example.** `kaizen-judges.md:43` already cites cross-SDK parity ("with N4 canonical fingerprint parity (kailash-rs#468 / v3.17.1+)"). Gate must verify the kailash-py side; a separate kailash-rs gate verifies the Rust side. Both gates use the same configuration schema.

### E2. Multi-package monorepo cross-SDK references

**Trigger.** Spec in kailash-py asserts a kailash-rs class exists for cross-SDK parity. Gate runs from `kailash-py/` root; the kailash-rs source tree is in a sibling repo.

**Blast radius.** MED. Cross-SDK assertions are real (the brief's Open Question #5 calls this out) and infrequent but high-value.

**Mitigation.** Day-1 gate scopes verification to kailash-py source only; flags cross-SDK assertions as "unverified — cross-SDK". M2 enhancement: gate optionally checks against a sibling-repo path (e.g., `~/repos/loom/kailash-rs/`) when configured.

**Example.** `kaizen-judges.md:43` cross-SDK assertion would be classified "unverified — cross-SDK" with the corresponding GitHub issue link. The kailash-rs sibling gate handles the Rust side; cross-SDK consistency is checked at /codify time when both repos sync to the same template.

### E3. Spec-as-test evolution

**Trigger.** Brief mentions a future executable annex (`<!-- mech: class:kailash_ml.automl.AutoMLEngine -->`). Day-1 gate must not architecturally preclude this evolution.

**Blast radius.** LOW for day 1; HIGH for M2 if architecture forecloses the path.

**Mitigation.** Design the gate's input layer with two modes from day 1:

1. **Heuristic mode (day 1)** — parse Markdown structure, extract assertion tables, apply marker-convention exclusions, search `.py` source.
2. **Annex mode (M2)** — read `<!-- mech: ... -->` machine-readable annex; validate every assertion in the annex; cross-check against heuristic-derived assertions for completeness.

Both modes share the same symbol-resolution + verification engine; only the input layer differs. Gate ships day 1 with heuristic mode; annex mode is opt-in per spec via a top-of-file marker.

**Example.** `ml-feature-store.md:54-67` already has machine-readable structure (the `__all__` list inside a code block is parseable). M2 can layer an explicit annex on top; day-1 heuristics work against the existing structure.

---

## F. Adversarial / Edge Cases

### F1. Spec author intentionally evades

**Trigger.** Author writes "class \\u0046ooEngine" (Unicode escape resolves to `FooEngine` at parse time, but bytes-level grep doesn't see `FooEngine`). Or writes class names with zero-width characters interspersed.

**Blast radius.** LOW (intent is rare; capability is real).

**Mitigation.** Markdown is rendered text; the gate operates on the textual representation. Apply Unicode normalization (NFKC) before regex/AST extraction; reject specs with non-printable characters in identifier-position contexts. Beyond that, this is a social/process problem — `/redteam` audit should flag suspicious spec patterns.

**Example.** No real cases observed in the audit history. Mitigation is preventive.

### F2. Comment-out-then-re-add

**Trigger.** A `class FooEngine: …` is commented out via `# class FooEngine: …`. AST parser does NOT see it. Bytes-level grep DOES. Spec asserts `FooEngine` exists; gate decides whether commented-out code counts.

**Blast radius.** LOW. Pattern is uncommon and quickly resolves itself (either the class is in code or it's not).

**Mitigation.** AST is authoritative. Bytes-level grep is a hint, not a verification. Commented-out code is NOT a definition.

### F3. Conditionally-imported symbols based on Python version / extras

**Trigger.** `if sys.version_info >= (3, 12): class Foo: ...; else: class Foo(LegacyFoo): ...`. Two definitions; gate finds both.

**Blast radius.** LOW-MED. Pattern exists in core Python libraries and may exist in kailash-py for backwards compatibility.

**Mitigation.** When AST walk finds multiple definitions of the same name in the same module, gate emits MED finding "conditional definition — verify both branches match spec assertion". Spec author manually annotates which branch is canonical, OR the spec asserts both.

### F4. Specs with no class citations

**Trigger.** Pure-prose specs (philosophy, design rationale, non-goal documents) have no `class X` / `def Y` assertions. Gate's "pass when assertion table empty" must not produce noise.

**Blast radius.** LOW. Trivial to handle.

**Mitigation.** Empty assertion table → silent PASS. Gate output for empty-assertion specs is a single line "no assertions to verify". Cross-check `_index.md` for specs that ought to have assertions (e.g., any spec under "Core SDK" or "ML Lifecycle") but have empty tables; emit LOW finding.

**Example.** `_index.md` Core SDK section lists 4 specs; if `core-runtime.md` has zero assertions parseable by the gate, that's itself a LOW finding (the spec is either pure prose — fine — or under-detailed — needs re-derivation per `rules/specs-authority.md` Rule 3 "detailed not summaries").

---

## Top 5 Must-Not-Fail-On-Day-1 Failure Modes

These are the failure modes whose mishandling kills gate credibility within the first PR cycle:

1. **B1 — Re-exports through `__getattr__`.** The W6.5 CRIT case (`AutoMLEngine` resolves to legacy via `__getattr__`) is THE motivating example for the gate. If the day-1 gate cannot detect this, the gate's value proposition collapses. Mitigation: AST + import-graph tracing through `__getattr__` maps; require fully-qualified import paths in spec assertions.

2. **A3 — Deferred-section references.** The W6.5-approved structure (`§ 11. Deferred to M2`) intentionally lists symbols absent from code. A naive day-1 gate would flag every entry — exactly the sections that represent best-practice spec hygiene. Mitigation: section-header context parsing, with the canonical section-name allowlist (Deferred / Awaiting / Out of Scope / MUST NOT / Removed / Legacy).

3. **B6 — Test file existence vs test FUNCTION existence.** W6.5 CRIT-2 is exactly this: spec asserted a wiring test path; the file does not exist. Day-1 gate MUST resolve test paths via `pathlib` AND verify `pytest --collect-only -q` shows the function (or AST-extracts the function name).

4. **D3 — False-positive fatigue.** Even at the brief's <5% FP threshold, 4 FPs per full-corpus run over 72 specs degrades trust quickly. Mitigation: pre-rollout dogfood against all 72 specs with FP triage; conservative thresholds; FP-report workflow built into gate output.

5. **D4 — Baseline rot.** The 36-HIGH backlog is the single biggest risk to long-term gate health. If the day-1 baseline is just a flat list with no expiration, no audit-finding citation, no quarterly cleanup mandate, it will accumulate every drift the team chose not to fix. Mitigation: baseline entries cite F-E2-NN, expire after 90 days, are diffed in every PR.

---

## Defer to M2 / Explicit Non-Goals

The following failure modes the gate cannot fully solve and should not pretend to:

- **B3 (dynamically-generated classes via `type(...)` / metaclass).** AST cannot see runtime-generated classes. Day-1 gate emits LOW unverified-symbol finding; M2 may add dynamic introspection in the test tier (Tier 2 wiring test executes the factory and grep the result).

- **C3 — Bidirectional `.py`-edit triggering.** Day-1 hook fires on `specs/**.md` only. The reverse-index hook (re-verify specs when cited `.py` files change) is M2 because it requires the symbol index to be persistent across runs.

- **E2 — Cross-SDK reference verification.** Day-1 gate scopes to kailash-py source roots only. Cross-SDK assertions are flagged "unverified — cross-SDK" with a link to the sibling repo's gate. Verification happens at /codify time.

- **E3 — Executable spec annex.** Day-1 ships heuristic mode; annex mode is M2 with a clean upgrade path designed in from day 1.

- **F1 — Adversarial Unicode evasion.** The gate is not a security tool; it is a hygiene tool. Adversarial evasion is a `/redteam` concern, not a gate concern. Apply NFKC normalization and stop.

- **Semantic alignment / orphan detection at the source level.** `rules/orphan-detection.md` MUST 1 (production call site) is enforced by `/redteam`, not the gate. The gate verifies that cited classes EXIST; it does not verify that cited classes are CALLED. This split keeps the gate fast and focused.

- **Method-body content verification.** The gate verifies signatures, fields, and decorator application (`skills/spec-compliance/SKILL.md` checks 1-3). It does NOT verify that a method's body implements the documented behavior (e.g., "yields ≥2 distinct values"). That's `/redteam` Check 8 (fake-implementation pattern scan).

- **Coverage of every spec's prose nuance.** The brief's success criterion is to catch the THREE drift patterns (overstated specs, fabricated typed exceptions, stale anchors). The gate is not a complete spec-vs-reality oracle.

---

## Closing Notes

**Section count:** 28 failure modes across 6 categories (A1-A5, B1-B8, C1-C4, D1-D5, E1-E3, F1-F4) plus Top 5 / Defer sections.

**Highest-severity failure mode:** **B1 (Re-exports through `__getattr__`)**, severity CRIT. This is THE canonical Wave 6 pattern (F-E2-01) and the most likely day-1 false negative if the gate uses bare class-name regex sweeps. Mitigation requires AST + import-graph tracing AND requiring fully-qualified import paths in spec assertions — a non-trivial day-1 design constraint that the requirements analyst MUST anchor on.

**Mitigations dependent on the marker-convention decision (brief Open Question #2):** **17 of 28 mitigations** (A1, A2, A3, A4, B1, B2, B3, B4, B5, B6, C3, D1, D4, D5, E3, F1, F2). The marker convention is the single highest-leverage decision in the design — it determines how the gate distinguishes assertion from prose, deferred from current, ignored from active, and how the executable annex evolves. The requirements analyst should treat marker convention as a first-class design axis, not an implementation detail.

**Cross-references for the requirements analyst:**

- `briefs/01-product-brief.md` — vision, success criteria, open questions
- `workspaces/portfolio-spec-audit/04-validate/W5-E2-findings.md` — F-E2-01..70, the drift patterns the gate must flag
- `workspaces/portfolio-spec-audit/04-validate/W6.5-v2-draft-review.md` — CRIT-1 (fabricated exceptions) + CRIT-2 (fabricated test path) — canonical day-1 cases
- `.claude/skills/spec-compliance/SKILL.md` — protocol-level documentation; the gate is the executable form
- `.claude/rules/specs-authority.md` § 5, § 5b, § 5c — rule basis
- `.claude/rules/orphan-detection.md` MUST 6 + `.claude/skills/16-validation-patterns/orphan-audit-playbook.md` § 6 — `__all__` contract enforcement (gate's surface alignment sweep)
- `.claude/rules/zero-tolerance.md` Rule 1b — pattern for "deferral requires tracking issue + runtime-safety proof", informs D1 mitigation
- `specs/_index.md` — full 72-spec inventory for performance budgeting (C1)
- `specs/ml-feature-store.md` § 11 — canonical "Deferred to M2" structure for A3 mitigation
- `specs/ml-engines-v2.md` lines 7-12, 113, 124 — canonical informal-mention prose for A1 calibration
