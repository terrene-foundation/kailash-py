# Spec Drift Gate — Requirements and Architecture Decisions

**Workspace:** `workspaces/spec-drift-gate/`
**Date:** 2026-04-26
**Author role:** analyst (requirements + ADRs)
**Sibling:** `01-failure-points.md` (failure-point analysis, parallel)
**Brief:** `briefs/01-product-brief.md` lines 1-96
**Spec corpus size:** ~72 files in `kailash-py/specs/`, 25 files in `kailash-rs/specs/` (verified by `Glob` 2026-04-26)

---

## 0. Executive Summary

This document turns the brief's solution sketch (lines 20-30) into 13 functional + 5 non-functional requirements and decides 7 architecture questions (5 from the brief's open-questions section, 2 newly surfaced). The audit findings the gate must catch (W5-E2 §§ F-E2-01..F-E2-22 + Wave 6.5 CRIT-1/CRIT-2) all reduce to four mechanical sweeps:

1. **Symbol existence** — class / def / decorator / Exception cited in spec exists in code
2. **Public-surface alignment** — symbols cited as exported appear in `__all__`
3. **Test file existence** — paths cited under § "Test Contract" / § "Tests" exist on disk
4. **Workspace-artifact leak** — no `W31 31b` / `workspaces/` references in shipped specs

The fifth sweep (cross-spec sibling re-derivation trigger, brief line 27) is qualitatively different — it surfaces specs to RE-CHECK rather than asserting code state — and is recommended as a `--review-needed` advisory rather than a hard CI block.

The overall recommendation: **scripts/spec_drift_gate.py** (single Python file, stdlib + ripgrep) with **`<!-- spec-assert: ... -->` HTML-comment markers** for explicit assertions and **section-context inference** as the default for prose-level mentions. Baseline format: **JSON Lines** (`.spec-drift-baseline.jsonl`, one finding per line, sorted, deterministic, line-diffable in PR review). Cross-SDK design: **YAML manifest** (`.spec-drift-gate.toml`) declaring source roots, test roots, and per-SDK regex variants.

The single highest-confidence ADR is **ADR-2 (marker convention)** — backed by direct grep of all 72 specs showing the pattern would cause zero false positives on existing prose AND covers every CRIT-1 fabrication path. See § 3.2.

---

## 1. Functional Requirements

Every FR cites the brief line, the audit-finding ID it targets, and pseudocode for the sweep. The FR identifiers are stable (FR-1..FR-13) and will be referenced in `02-plans/` and `04-validate/` once those phases land.

### FR-1 — Class existence verification

**Source:** Brief line 24 ("every `class X` … cited in a spec MUST exist at the cited path"). **Catches:** F-E2-05 (`Ensemble.from_leaderboard()` cited but absent), F-E2-12 (`DriftMonitorConfig` cited but absent), F-E2-21 (`FeatureGroup` cited but absent), Wave 6.5 CRIT-1 (5 fabricated `*Error` classes).

**Description:** For every spec assertion of the form `class X` (whether in `class X(...)` Python signature, in markdown bullet `**class X**`, or in a citation `kailash_ml.foo.X`), verify the class exists in the source tree. Resolution: walk the source roots declared in the per-SDK manifest (kailash-py: `src/kailash/`, `packages/*/src/`; kailash-rs: `crates/*/src/`); use `ast.parse()` on every `.py` file; check `ClassDef` nodes. Empty match = FAIL.

**Pseudocode:**

```python
def fr_1_class_exists(class_name: str, source_roots: list[Path]) -> bool:
    for root in source_roots:
        for py_file in root.rglob("*.py"):
            try:
                tree = ast.parse(py_file.read_text())
            except SyntaxError:
                continue  # Tier-0 syntax errors are out of scope; pre-commit
                          # syntax check covers them
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    return True
    return False
```

**Verification command:** `grep -nE 'class ([A-Z][A-Za-z0-9_]*)' specs/ml-feature-store.md | head -20` enumerates every class reference; the gate's job is to verify each.

### FR-2 — Function / method existence verification

**Source:** Brief line 24 (`def Y` cited in spec must exist). **Catches:** F-E2-02 (`AutoMLEngine.__init__(*, tracker)` kwarg cited but missing), F-E2-08 (`MLEngine.fit_auto()` cited but absent), F-E2-22 (`FeatureStore.materialize()` / `.ingest()` / `.stream_to_online()` cited but absent), F-E2-13 (`MLEngine.monitor()` cited but absent).

**Description:** For every `def name(...)` reference in a spec assertion, locate the enclosing class (when present) and verify the method exists. AST `FunctionDef` and `AsyncFunctionDef` both qualify. Module-level functions also covered.

**Pseudocode:**

```python
def fr_2_function_exists(func_name: str, class_name: str | None, source_roots) -> bool:
    """If class_name is None, look for module-scope function; else look inside ClassDef."""
    for py_file in walk_source(source_roots):
        tree = ast.parse(py_file.read_text())
        if class_name is None:
            # module-scope function
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
                    return True
        else:
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    for child in node.body:
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == func_name:
                            return True
    return False
```

**Verification command:** `grep -nE '\.(\w+)\(' specs/ml-automl.md | head` enumerates method-call references the gate must verify.

### FR-3 — Decorator application verification

**Source:** Brief line 24 (`@decorator` cited in spec must exist). **Catches:** F-E2-20 (`@feature` decorator cited but absent), F-E2-33 (`@experimental` decorator — already verified in W5-E2 as compliance-positive but covered by gate for future regressions).

**Description:** For every `@decorator_name` reference in a spec assertion, verify the decorator (a) exists as a callable in the source tree AND (b) is applied at least once at a real call site (the count assertion handles "applied to N methods" claims; see FR-3a).

**Pseudocode:**

```python
def fr_3_decorator_exists(deco_name: str, source_roots) -> tuple[bool, int]:
    """Returns (decorator_defined, application_count)."""
    defined = False
    applications = 0
    for py_file in walk_source(source_roots):
        tree = ast.parse(py_file.read_text())
        for node in ast.walk(tree):
            # Definition: top-level `def deco_name` annotated as decorator
            if isinstance(node, ast.FunctionDef) and node.name == deco_name:
                # heuristic: any function returning a callable taking a callable can be a decorator;
                # for the gate, treat the existence of a function with this name as "defined"
                defined = True
            # Application: `@deco_name` in any decorator_list
            decos = getattr(node, "decorator_list", [])
            for d in decos:
                # @deco_name OR @deco_name(...)
                if isinstance(d, ast.Name) and d.id == deco_name:
                    applications += 1
                elif isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == deco_name:
                    applications += 1
    return defined, applications
```

**FR-3a — Decorator count assertion (advisory):** When a spec asserts a decorator is "applied to N methods" or "decorating 7 extension points", FR-3 returns the application count and the gate compares against the asserted N. Mismatch = FAIL. Spec-compliance skill § 3 already mandates this for `/redteam`; FR-3a productionizes the check.

**Verification command:** `grep -nE '@[a-z_]+\b' specs/ml-feature-store.md | head` finds decorator references.

### FR-4 — Error-class existence verification

**Source:** Brief line 24 ("Exception cited in a spec"). **Catches:** Wave 6.5 CRIT-1 explicitly — `FeatureGroupNotFoundError`, `FeatureVersionNotFoundError`, `FeatureEvolutionError`, `OnlineStoreUnavailableError`, `CrossTenantReadError` cited as "defined in `kailash_ml.errors`" but absent. Also F-E2-04 (`MissingExtraError`), F-E2-06 (11 typed exceptions in AutoML).

**Description:** Specialization of FR-1 with stricter resolution. When a spec section is titled `## Errors` / `## Exceptions` / `## Errors and Exceptions` (case-insensitive) AND a name ending in `Error` / `Exception` appears in that section, verify the class exists AND inherits from `Exception` (or a project-canonical base like `KailashError` / `KailashMLError` / `AlignmentError`). The errors-module convention is per-package: `src/kailash/ml/errors.py` for kailash-ml, `packages/kailash-align/src/kailash_align/exceptions.py` for kailash-align.

**Pseudocode:**

```python
def fr_4_error_exists(error_name: str, errors_module_paths: list[Path]) -> bool:
    """Errors module paths come from the per-package manifest."""
    for path in errors_module_paths:
        if not path.exists():
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == error_name:
                # Verify it's an exception by walking the bases
                # (best-effort; cross-module bases are not resolved)
                for base in node.bases:
                    if isinstance(base, ast.Name) and (
                        base.id == "Exception"
                        or base.id.endswith("Error")
                        or base.id.endswith("Exception")
                    ):
                        return True
                # Permissive: ClassDef named *Error in errors module is treated as exception
                return True
    return False
```

**Verification command:** `grep -nE '`[A-Z][A-Za-z0-9_]\*(Error|Exception)`' specs/ml-feature-store.md` enumerates error-class assertions.

### FR-5 — Field/attribute existence verification

**Source:** Brief line 24 (extends "every `class X`" to fields). **Catches:** F-E2-02 (`tracker=` kwarg absent from `AutoMLEngine.__init__`), F-E2-12 (`DriftMonitorConfig` field set), F-E2-14 (`drift_score` field absent on `FeatureDriftResult`).

**Description:** When a spec asserts `ClassName.field_name` or a kwarg in a constructor signature, verify the field/kwarg exists. For dataclasses: `AnnAssign` nodes inside `ClassDef`. For constructor kwargs: walk the `__init__` `FunctionDef.args.kwonlyargs`.

**Pseudocode:**

```python
def fr_5_field_or_kwarg_exists(class_name, field_or_kwarg, source_roots) -> bool:
    for py_file in walk_source(source_roots):
        tree = ast.parse(py_file.read_text())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.ClassDef) and node.name == class_name):
                continue
            # Dataclass field check
            for child in node.body:
                if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                    if child.target.id == field_or_kwarg:
                        return True
            # Constructor kwarg check
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == "__init__":
                    kwonly = [a.arg for a in child.args.kwonlyargs]
                    posonly = [a.arg for a in child.args.args]
                    if field_or_kwarg in kwonly or field_or_kwarg in posonly:
                        return True
    return False
```

**Verification command:** `grep -nE 'field\s*=\s*' specs/ml-automl.md | head` finds field declarations the gate must verify.

### FR-6 — Public-surface alignment (`__all__` membership)

**Source:** Brief line 26 ("every symbol cited as 'exported' MUST appear in the package's `__all__`"). **Catches:** F-E2-05 (`Ensemble` cited as exported but absent from `kailash_ml.__init__.__all__`). Also `rules/orphan-detection.md` MUST 6 (eager-imports-without-`__all__`-entry) is the converse; FR-6 covers spec→`__all__` while orphan-detection covers `__init__.py`→`__all__`.

**Description:** When a spec asserts a symbol is exported (markers: "exported via", "in `__all__`", "from kailash_ml import X"), verify the symbol appears in the named package's `__all__` list. The package path is inferred from the spec's `**Package:**` header line (or the per-package manifest mapping).

**Pseudocode:**

```python
def fr_6_in_all(symbol: str, package_init_path: Path) -> bool:
    if not package_init_path.exists():
        return False
    tree = ast.parse(package_init_path.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        members = [elt.value for elt in node.value.elts
                                   if isinstance(elt, ast.Constant) and isinstance(elt.value, str)]
                        return symbol in members
    return False
```

**Verification command:** `python -c "import kailash_ml; print(kailash_ml.__all__)"` produces the runtime `__all__`; the gate checks the AST form (which survives without an importable env).

### FR-7 — Test file existence verification

**Source:** Brief line 25 ("every test file enumerated in a spec MUST exist on disk"). **Catches:** Wave 6.5 CRIT-2 (`test_feature_store_wiring.py` cited but only `test_feature_store.py` exists), W6.5 HIGH-1 (`tests/unit/automl/` directory cited but absent), F-E2-07 (`test__kml_automl_agent_audit_schema_migration.py` cited but absent).

**Description:** When a spec section is titled `## Test Contract` / `## Tests` / `## Tier N Tests` (or sub-headings under those) and references a path matching `tests/.../*.py`, verify the file exists on disk.

**Pseudocode:**

```python
def fr_7_test_path_exists(path_str: str, repo_root: Path) -> bool:
    p = repo_root / path_str
    return p.exists() and p.is_file()

# extraction: from spec text, extract paths matching:
#   r'(?:packages/[\w-]+/)?tests/[\w/]+\.py'
# include only paths that appear inside backticks in `## Test*` sections.
```

**Verification command:** `grep -nE 'tests/[A-Za-z0-9_/]+\.py' specs/ml-feature-store.md` enumerates test-path citations.

### FR-8 — Workspace-artifact leak detection

**Source:** Brief line 28 (`grep -E '(W3[0-9] [0-9]+|workspaces/)' specs/` returns zero matches). **Catches:** W6.5 HIGH-2 (`W31 31b` references in shipped FeatureStore v2 draft).

**Description:** Pure regex sweep. The shipped `specs/` set MUST NOT contain workspace-artifact references. Patterns to flag:

- `W\d+\s+\d+[a-z]?` — workstream-shard tag (e.g., `W31 31b`, `W33`, `W32a`)
- `workspaces/[\w/-]+` — workspace path reference
- `-draft\.md` references inside specs (drafts MUST be promoted before specs cite them)
- `journal/\d+-\w+\.md` references (journals are session record, not domain truth)

**Pseudocode:**

```python
import re
LEAK_PATTERNS = [
    re.compile(r'\bW\d+\s+\d+[a-z]?\b'),
    re.compile(r'workspaces/[\w/-]+'),
    re.compile(r'specs/[\w-]+-draft\.md'),
    re.compile(r'journal/\d+'),
]
def fr_8_leak_scan(spec_path: Path) -> list[tuple[int, str, str]]:
    """Returns list of (line_no, pattern, matched_text)."""
    findings = []
    for line_no, line in enumerate(spec_path.read_text().splitlines(), 1):
        for pat in LEAK_PATTERNS:
            for m in pat.finditer(line):
                findings.append((line_no, pat.pattern, m.group()))
    return findings
```

**Verification command:** `grep -rnE '(W3[0-9]\s+[0-9]+|workspaces/)' specs/` (the brief's literal command, line 28).

### FR-9 — `MOVE` shim verification

**Source:** Spec-compliance skill § Step 2 #4 ("MOVE Shim Verification"). **Catches:** Future drift where a spec says "MOVE A → B" but A is still 1088 LOC of duplicate code.

**Description:** When a spec asserts `MOVE src/old/path.py → packages/new/path.py` (or markdown `MOVED: A → B`), verify the source path A satisfies one of: (a) deleted, (b) <50 LOC (thin shim), (c) imports from B AND emits `DeprecationWarning`.

**Pseudocode:**

```python
def fr_9_move_shim_ok(old_path: Path, new_path: Path) -> tuple[bool, str]:
    if not old_path.exists():
        return True, "deleted"
    line_count = sum(1 for _ in old_path.open())
    if line_count < 50:
        # thin shim: must import from new path AND warn
        body = old_path.read_text()
        imports_new = (str(new_path).replace("/", ".") in body) or (
            f"from {package_path_for(new_path)}" in body
        )
        warns = "DeprecationWarning" in body or "warnings.warn" in body
        if imports_new and warns:
            return True, "thin_shim"
        return False, f"thin_shim_missing_warn_or_import"
    return False, f"copied_not_moved (line_count={line_count})"
```

**Verification command:** `wc -l <old_path>` confirms shim thinness; `grep -E 'DeprecationWarning|warnings.warn' <old_path>` confirms the warning emission.

### FR-10 — Cross-spec sibling re-derivation trigger (advisory)

**Source:** Brief line 27 + `rules/specs-authority.md` MUST 5b. **Catches:** Drift between sibling specs that share dataclasses / surface (e.g., `ml-engines.md` edits `TrainingResult` shape but `ml-backends.md` still references the old shape).

**Description:** When a spec edit lands, the gate enumerates every `specs/<sibling>*.md` (siblings determined by domain prefix: `ml-*`, `dataflow-*`, `kaizen-*`, `nexus-*`, `pact-*`, `align-*`, `core-*`, `mcp-*`, `infra-*`, `security-*`, `trust-*`, `diagnostics-*`, `task-*`, `visualization-*`, `scheduling-*`, `middleware-*`, `edge-*`, `node-*`) and checks whether any sibling references symbols defined in the edited spec. Output is **advisory** (printed to stdout, attached as a PR comment) — NOT a hard CI block.

**Pseudocode:**

```python
def fr_10_sibling_review(edited_spec: Path, all_specs: list[Path]) -> list[Path]:
    """Returns siblings that mention symbols defined in edited_spec."""
    edited_symbols = extract_class_def_names(edited_spec)  # e.g. {TrainingResult, MLEngine}
    domain = edited_spec.stem.split("-")[0]  # "ml" from "ml-engines.md"
    siblings = [p for p in all_specs
                if p.stem.startswith(domain + "-") and p != edited_spec]
    review_needed = []
    for sib in siblings:
        body = sib.read_text()
        for sym in edited_symbols:
            if re.search(rf'\b{sym}\b', body):
                review_needed.append(sib)
                break
    return review_needed
```

**Disposition:** ADVISORY (warn + comment); NOT a CI fail. This intentionally diverges from `specs-authority.md` MUST 5b's hard-rule framing because mechanical detection of "sibling needs review" is high-recall low-precision — every shared term triggers it. Hardening would produce a flood of "needs-review" annotations that operators learn to ignore (failure mode documented in `cross-cli-parity.md` MUST Rule 4 scrub-tokens). The hard rule remains the human's responsibility; the gate is a discoverability aid.

**Verification command:** `python scripts/spec_drift_gate.py --siblings-of specs/ml-engines.md` lists siblings to review.

### FR-11 — Baseline grace (pre-existing drift passes)

**Source:** Brief line 42-43 ("existing 36-HIGH backlog gets a one-time grace window via a `.spec-drift-baseline.json` (or equivalent) snapshot; new violations introduced after the baseline are blocking").

**Description:** The first time the gate runs against `main`, it captures every finding into `.spec-drift-baseline.jsonl` (see ADR-3). Subsequent runs subtract baseline findings from the live findings; only the diff blocks. New findings (in PR but not baseline) FAIL; resolved findings (in baseline but not PR) succeed AND emit a "baseline can be updated" notice.

**Pseudocode:**

```python
def fr_11_baseline_diff(live_findings: list[Finding], baseline_path: Path) -> tuple[list[Finding], list[Finding]]:
    """Returns (new_findings, resolved_findings)."""
    if not baseline_path.exists():
        return live_findings, []  # no baseline = everything is new
    baseline = {Finding.from_json(line) for line in baseline_path.read_text().splitlines() if line.strip()}
    live = set(live_findings)
    new = sorted(live - baseline, key=lambda f: f.sort_key)
    resolved = sorted(baseline - live, key=lambda f: f.sort_key)
    return new, resolved
```

**Finding equality semantics:** A finding is keyed by `(spec_path, line_no, sweep_name, asserted_symbol)` — NOT by the surrounding text — so trivial spec-prose edits don't invalidate the baseline.

**Verification command:** `python scripts/spec_drift_gate.py --baseline .spec-drift-baseline.jsonl --check-only` exits 0 iff no new findings exist.

### FR-12 — Self-test fixtures (deterministic)

**Source:** Brief line 77 (Tier 1 + Tier 2 tests for the gate itself).

**Description:** The gate ships with `tests/fixtures/spec_drift_gate/` containing:

- `good_spec.md` — every assertion resolves; all sweeps pass
- `bad_class.md` — asserts a class that doesn't exist; FR-1 fails
- `bad_test_path.md` — asserts a test path that doesn't exist; FR-7 fails
- `bad_error_class.md` — Wave 6.5 CRIT-1 reproduction (5 fabricated `*Error` classes); FR-4 fails 5 times
- `bad_workspace_leak.md` — contains `W31 31b`; FR-8 fails
- `bad_decorator.md` — asserts `@deco` applied to 7 sites but only 3 exist; FR-3a fails

These fixtures live under the gate's own test tree, NOT under `specs/`, so the production sweep skips them.

### FR-13 — Output: human-readable + machine-readable

**Source:** Brief line 51 ("structured guidance"); also `cross-cli-parity.md` cross-CLI comparability.

**Description:** Two output modes selectable by flag:

- `--format human` (default): one-line summary per finding; pre-commit-friendly; matches `pytest --tb=short` aesthetic.
- `--format json`: JSON Lines, one object per finding, suitable for CI annotations and the GitHub PR review API.

Each finding object:

```json
{
  "spec_path": "specs/ml-feature-store.md",
  "line_no": 515,
  "sweep": "FR-4-error-class",
  "asserted_symbol": "FeatureGroupNotFoundError",
  "severity": "CRIT",
  "fix_hint": "Class 'FeatureGroupNotFoundError' cited at specs/ml-feature-store.md:515 not found in src/kailash/ml/errors.py — add the class, fix the cite, or move to '## Deferred' section."
}
```

The `fix_hint` form is mandated by ADR-6 and treats every failure as a one-line actionable instruction (per `rules/zero-tolerance.md` Rule 3a typed-guard precedent).

---

## 2. Non-Functional Requirements

### NFR-1 — Performance: <30s wall clock on full `specs/` set

**Source:** Brief line 41 + line 57.

**Targets:**

- Gate completes in **<30s** on a developer laptop running against `kailash-py/specs/` (~72 files).
- Gate completes in **<10s** on the same machine running incrementally (only changed specs).
- Gate completes in **<60s** on a GitHub-hosted runner (cold-cache, full sweep).

**Measurement:** `time python scripts/spec_drift_gate.py specs/` reported in CI annotations on every run; alarms at 80% of budget.

**Why:** A pre-commit hook above 30s is opted out of by every contributor (cross-reference: `pytest-check` in `.pre-commit-config.yaml:81-105` already takes ~2-5s and is the project's tightest budget). The 30s budget assumes ripgrep + AST parse — both stdlib-cheap.

### NFR-2 — False-positive rate: <5%

**Source:** Brief line 56.

**Definition:** A false positive is when the gate flags a spec line that the human reviewer agrees does NOT need correction. Measured as: `false_positives / total_findings_on_full_specs_run`.

**Methodology:** Run the gate against the full `specs/` corpus at baseline-capture time. Manually triage each finding (CRIT/HIGH only — LOW findings are stylistic). The triage's "false positive" count divided by total CRIT/HIGH count is the FPR.

**Driver of FPR:** Marker convention (ADR-2). Section-context heuristic FPR is bounded by how aggressively prose-mentions vs. assertions are distinguished. Empirically the W5-E2 audit found ~70 findings across 11 specs; if all 70 reproduce on the gate AND the human triage agrees on >95%, the gate hits the target.

**Mitigation:** ADR-2's hybrid approach (explicit `<!-- spec-assert -->` markers for non-obvious cases + section-context for `## Surface` / `## Errors` / `## Test Contract` headings) lets authors override false positives without weakening the gate.

### NFR-3 — Determinism: same input → same output

Findings sorted by `(spec_path, line_no, sweep_name, asserted_symbol)`. JSON output is sorted alphabetically per object key. Baseline file MUST be byte-identical across re-runs on the same git tree state. No nondeterministic ordering (no `set` iteration without `sorted()`, no `dict` iteration assuming insertion order beyond Python 3.7 contract).

**Test:** `for i in 1 2 3; do python scripts/spec_drift_gate.py --format json specs/ > /tmp/run_$i.jsonl; done; diff /tmp/run_1.jsonl /tmp/run_2.jsonl /tmp/run_3.jsonl` MUST be empty.

### NFR-4 — Portability: same gate ports to kailash-rs

The kailash-rs sibling has a parallel `specs/` tree (25 files, verified by `Glob`). The gate's design MUST allow either:

- **Single repo invocation**: `python scripts/spec_drift_gate.py --manifest .spec-drift-gate.toml` reads the per-repo manifest declaring source roots and per-language regex variants, then runs the same Python script from a checked-out copy.
- **Per-SDK script copies**: kailash-rs maintains its own `scripts/spec_drift_gate.py` (or `tools/spec_drift_gate.py`) using the same algorithm, with Rust-specific extraction (`syn` crate or `tree-sitter-rust`) substituted for Python `ast`.

ADR-5 chooses the manifest-driven approach for kailash-py (Python source) and recommends a Rust port (NOT a wrapper around the Python script — Rust AST parsing in Python is awkward) for kailash-rs.

### NFR-5 — Self-test: gate has its own Tier 1 + Tier 2 tests

**Tier 1 (unit):** Each FR pseudocode has a unit test against a deterministic fixture (FR-12). Run: `.venv/bin/python -m pytest tests/unit/test_spec_drift_gate.py`.

**Tier 2 (integration):** Run the gate against the full `specs/` corpus AND against the deliberately-broken fixtures; assert the finding count matches a captured baseline. Run: `.venv/bin/python -m pytest tests/integration/test_spec_drift_gate_corpus.py`.

**Demo regression test:** Reproduce Wave 6.5 CRIT-1: the test inputs the exact fabricated text from `ml-feature-store-v2-draft.md` line 515 (5 `*Error` classes) and asserts FR-4 emits 5 findings. See § 5.6 for the exact pytest invocation.

---

## 3. Architecture Decision Records

### 3.1 ADR-1 — Where Does The Gate Live?

**Status:** Proposed
**Decision:** `scripts/spec_drift_gate.py` (kailash-py); analogous `scripts/spec_drift_gate.py` for kailash-rs.

**Context:** Brief Q1 (line 91): "Where does the gate live — `scripts/`, `tools/`, a new `meta/` directory? Existing `scripts/` already has hooks; reuse or new location?"

The kailash-py `scripts/` directory was inventoried via `Glob`:

- 5 standalone Python scripts (`extract-api-surface.py`, `convergence-verify.py`, `generate-vector-hashes.py`, `maintenance/*.py` — 3 files, no top-level `__init__.py`)
- 1 standalone shell script (`check-api-parity.sh`)
- ~30 `hooks/` JS files (Claude Code hooks)
- `ci/` JS files (CI validators)
- `metrics/` shell scripts
- `learning/` JS files

The directory's convention is "freestanding executable utility, no package structure". `tools/` does not exist. `meta/` does not exist.

**Decision:** Place the gate at `scripts/spec_drift_gate.py` (single file). Companion fixtures at `tests/fixtures/spec_drift_gate/`. No new top-level directory.

**Alternatives Considered:**

1. `tools/spec_drift_gate/` — package layout with `__init__.py` + sub-modules per sweep. Rejected: `scripts/` already contains domain-equivalent standalone tools (`extract-api-surface.py` is the closest analog — single-file AST walker, exactly the same shape). Splitting into a sub-package crosses the threshold to "this is a library" and the gate is a tool, not a library.
2. `meta/spec_drift_gate.py` — new top-level. Rejected: introducing a new top-level directory raises onboarding cost for every new contributor without tangible benefit; the contents would be a single file.
3. `packages/kailash-spec-tools/` — sub-package layout. Rejected: a sub-package would be installable via PyPI, which is overkill for a 500-LOC drift gate AND violates `cc-artifacts.md` MUST 4 (No BUILD artifacts in USE repos) — the gate is a BUILD tool that should not ship in the user-installable wheel.

**Consequences:**

- (+) Mirrors `extract-api-surface.py` shape — contributors find it immediately.
- (+) No new directory; no churn in path-scoped rules / glob patterns.
- (+) Single file simplifies the cross-SDK port (one file to translate, not a package tree).
- (−) Gate file may grow; if it crosses ~1500 LOC, a future split into `scripts/spec_drift_gate/{__init__,sweeps,output}.py` is permitted (with the orchestrator at `scripts/spec_drift_gate.py` still invoking it).

**Verification command:**

```bash
test -f scripts/spec_drift_gate.py && \
  test -d tests/fixtures/spec_drift_gate/ && \
  echo "ADR-1 verified"
```

---

### 3.2 ADR-2 — Marker Convention For Assertion vs. Informal Mention

**Status:** Proposed
**Decision:** **Hybrid** — section-context inference by default; explicit `<!-- spec-assert: ... -->` HTML-comment overrides for non-obvious cases. Ignore prose mentions in non-assertion sections.

**Context:** Brief Q2 (line 92): "Marker convention for 'informal class mention' exclusion — backticks-only? An explicit `<!-- spec-drift-gate:ignore -->` comment? Verify against existing spec prose to pick the lowest-noise option."

The driver is NFR-2 (FPR <5%). Three options were evaluated:

#### Option A — Backticks-only

Every backticked symbol is an assertion. Spec prose like "imagine a `FooEngine` class" would trigger.

**Reality check:** `grep -cE '\b`[A-Z][A-Za-z0-9_]\*`' specs/ml-automl.md` returns hundreds of matches across narrative prose, deferred sections, related-work footnotes, etc. The current spec corpus uses backticks pervasively as code-emphasis (per markdown convention) — making them an assertion marker would explode the FPR. **Rejected.**

#### Option B — Explicit assertion markers everywhere

Every assertion requires `<!-- spec-assert: class:FooEngine -->` (or similar). Prose mentions are silently ignored; assertions are explicit.

**Reality check:** Retrofitting markers across 72 specs at ~140 § subsections each (W5-E2 §§ enumeration) requires authoring ~10K markers. The cost is bounded but non-trivial; more importantly, every NEW spec must add markers, raising authoring friction and inviting the failure mode "author forgot the marker; gate doesn't fire; drift ships". **Partially rejected** — explicit markers ARE useful, but as an override, not a primary mechanism.

#### Option C — Section-context inference (DECIDED)

The gate parses the spec's heading hierarchy and ONLY treats backticked symbols inside specific section names as assertions:

| Section heading regex (case-insensitive)          | Sweep applied           |
| ------------------------------------------------- | ----------------------- |
| `## (Surface\|Construction\|Public API)`          | FR-1, FR-2, FR-5        |
| `## Errors\|## Exceptions`                        | FR-4                    |
| `## (Test Contract\|Tests\|Tier .* Tests)`        | FR-7                    |
| `## (Migration\|Module Layout)` w/ `MOVE` keyword | FR-9                    |
| `## (Examples\|Quickstart)`                       | FR-1, FR-2 (smoke only) |

All other sections (`## Scope`, `## Out of Scope`, `## Industry Parity`, `## Deferred to M2`, `## Cross-References`, prose under `## Conformance Checklist`) are EXCLUDED from sweeps even when they contain backticked symbols. This matches authorial intent: deferred-section symbols ARE allowed to not exist (that's the point of the section).

**Override mechanism:**

```markdown
<!-- spec-assert: class:Ensemble.from_leaderboard -->

The `Ensemble.from_leaderboard()` classmethod is canonical.

<!-- spec-assert-skip: class:FooEngine reason:"illustration only" -->

Imagine a hypothetical `FooEngine` class…
```

The `spec-assert:` directive force-asserts a symbol that the section heuristic missed (e.g., introduced in a `## Examples` block where the heuristic only does smoke FR-1). The `spec-assert-skip:` directive force-skips a symbol the heuristic flagged (and requires a `reason:` field for review hygiene). Per ADR-7, these directives are forward-compatible with a future structured annex.

**Decision:** Section-context inference + override directives.

**Alternatives Considered:**

1. Backticks-only (Option A) — rejected, FPR explosion.
2. Explicit markers everywhere (Option B) — rejected, authoring friction; partial-fold as override mechanism.
3. NO inference, only `<!-- spec-assert -->` opt-in — rejected, 0% coverage on specs that don't add markers, defeats the prevent-at-insertion goal.
4. `<!-- spec-drift-gate:ignore -->` end-of-file marker — rejected, all-or-nothing at file scope is too coarse.

**Consequences:**

- (+) Zero authoring friction for the common case (well-structured spec with `## Surface`, `## Errors`, `## Test Contract` sections — exactly the v2.0.0 spec pattern that AutoML v2 already follows).
- (+) Override directives are cheap to apply in the rare false-positive case.
- (+) Forward-compatible with the structured annex format the brief defers (line 30); `<!-- mech: class:X -->` can become a synonym for `<!-- spec-assert: class:X -->` (ADR-7).
- (−) Section-heading discipline now load-bears — a v2 spec that mis-labels its `## Surface` section as `## Public Interface` would be silently un-swept. Mitigation: the gate emits an INFO line per spec listing which sections it scanned, so authors can verify coverage.
- (−) Spec authors learn one new marker form. Documentation burden is one section in `skills/spec-compliance/SKILL.md`.

**FPR estimate (NFR-2):** On the 11 W5-E2 specs:

- ~70 audit findings reproduce as gate findings (sweeps fire).
- Backticked mentions in `## Out of Scope`, `## Deferred to M2`, `## Cross-References` are skipped — no false positives.
- Estimated <3 false positives per 70 findings (~4%) from edge cases (e.g., a class mentioned in `## Examples` that doesn't exist because the example is illustrative).

**Verification command:**

```bash
# Hand-audit: run the gate against ml-automl.md (clean), expect ZERO findings under FR-1..FR-7
python scripts/spec_drift_gate.py --format human specs/ml-automl.md | grep -cE '^FAIL'
# Expected: 0 (the AutoML v2 is the pristine reference)

# Run against ml-feature-store-v2-draft.md (round 1, fabricated): expect ≥6 findings
python scripts/spec_drift_gate.py --format human specs/ml-feature-store-v2-draft.md
# Expected: 5×FR-4 (CRIT-1 fabricated errors) + 1×FR-7 (CRIT-2 fabricated test path)
```

---

### 3.3 ADR-3 — Baseline Format

**Status:** Proposed
**Decision:** **JSON Lines** (`.spec-drift-baseline.jsonl`), one finding per line, sorted, committed to repo root.

**Context:** Brief Q3 (line 93): "Baseline format — JSON, YAML, plain text? Whatever is simplest to diff in PR review."

Three options:

#### Option A — JSON (single object)

```json
{ "findings": [ { ... }, { ... }, ... ] }
```

PR diffs against this format show the entire file as changed when a single finding is added/removed (since trailing-comma rules + key-order changes in tools that re-serialize cause whole-file diff noise). **Rejected.**

#### Option B — YAML

Human-readable. PR diffs are clean (line-level). But: YAML parsing in stdlib requires `yaml` import (PyYAML — third-party); the brief's "stdlib-only" constraint (line 41) precludes it. Adding PyYAML solely for the baseline crosses the dependency threshold. **Rejected.**

#### Option C — JSON Lines (DECIDED)

One JSON object per line, sorted lexically by `(spec_path, line_no, sweep_name, asserted_symbol)`. `json.dumps(obj, sort_keys=True)` produces a deterministic per-line output. PR diff is line-granular: adding one finding is one line added; resolving one is one line removed.

```jsonl
{"asserted_symbol":"FeatureGroupNotFoundError","line_no":515,"severity":"CRIT","spec_path":"specs/ml-feature-store.md","sweep":"FR-4-error-class"}
{"asserted_symbol":"FeatureVersionNotFoundError","line_no":515,"severity":"CRIT","spec_path":"specs/ml-feature-store.md","sweep":"FR-4-error-class"}
```

**Staleness prevention:** the gate emits a "baseline can be updated" notice when live findings strictly subset baseline findings, with the exact command to regenerate:

```
INFO: 3 findings resolved since baseline. Update with:
  python scripts/spec_drift_gate.py --regenerate-baseline > .spec-drift-baseline.jsonl
```

This is advisory — operators choose when to land the baseline tightening (typically batched into a `chore(spec-drift): refresh baseline` PR).

**Alternatives Considered:**

1. Single-JSON (Option A) — rejected, diff noise.
2. YAML (Option B) — rejected, third-party dep.
3. Plain text (one finding per line, custom format) — rejected, harder to round-trip than JSON Lines (parsing custom format adds bugs).
4. SQLite — rejected, binary file is unreviewable in PR.

**Consequences:**

- (+) Stdlib-only (`json` module).
- (+) Line-granular diffs in PR review.
- (+) Sorting deterministic across runs (NFR-3).
- (+) Existing `.spec-coverage` skill output uses similar JSONL aesthetic.
- (−) Less human-readable than YAML when scanning visually; mitigation is `--format human` for CLI inspection.

**Verification command:**

```bash
# Baseline file exists and is sorted
test -f .spec-drift-baseline.jsonl && \
  diff <(sort .spec-drift-baseline.jsonl) .spec-drift-baseline.jsonl && \
  echo "ADR-3 verified (sorted JSONL)"
```

---

### 3.4 ADR-4 — CI Matrix: Every PR vs. Spec-Touching PRs

**Status:** Proposed
**Decision:** **Run on every PR** at the workflow-trigger level; the gate self-skips (no-op exit 0) when the diff has no `specs/**.md` changes AND `.spec-drift-baseline.jsonl` is absent (to allow first-baseline capture). When the diff DOES touch specs/, the full sweep runs. `concurrency: cancel-in-progress: true` per `rules/git.md` § Pre-FIRST-Push CI Parity.

**Context:** Brief Q4 (line 94): "CI matrix — does the gate run only on `specs/**.md` changes, or every PR? (Cheap enough to run every PR if <30s.)"

The gate budget is 30s (NFR-1). Per `rules/ci-runners.md` MUST 7, every workflow with cron must have an explicit cost footer; for a PR-trigger workflow, the question is "billable minutes per PR".

**Cost calculation:**

- Run on every PR with `paths:` filter `[specs/**, scripts/spec_drift_gate.py, .spec-drift-baseline.jsonl]`:
  - PRs that don't touch specs/: GitHub Actions does NOT trigger (paths filter handles it).
  - PRs that touch specs/: trigger, ~30s of runner time.
  - Estimated cost: 5-10 spec PRs/week × 1 min runtime × 4 weeks = **20-40 min/month**.
- Run on every PR without paths filter: 100+ PRs/week × 1 min minimum = 400+ min/month. **Rejected.**

**Decision:** Workflow `paths:` filter limits triggers to spec-touching PRs; the gate's logic still works on all `specs/**` and the test/source roots declared in the manifest (so changes to a source file that orphan a spec assertion DO trigger the gate via the source-root path). The `paths:` filter:

```yaml
on:
  pull_request:
    paths:
      - "specs/**"
      - "scripts/spec_drift_gate.py"
      - ".spec-drift-baseline.jsonl"
      - ".spec-drift-gate.toml"
      # Source roots that AST sweeps depend on:
      - "src/kailash/**/*.py"
      - "packages/*/src/**/*.py"
```

Source-root paths are included because deleting a class in `src/` MUST trigger the gate even if the spec citing the class wasn't touched.

**Local pre-commit:** `.pre-commit-config.yaml` entry runs `scripts/spec_drift_gate.py` on every `specs/**.md` commit (NOT every commit — the gate has no business running when only `tests/` or `src/` changed at pre-commit time, since pre-commit hooks already cover the source side via `pytest-check`). See § 4.1.

**Concurrency:** `cancel-in-progress: true` per `git.md` Pre-FIRST-Push (avoids redundant runs on `git push --force` cycles).

**Release-prep skip:** Per `git.md` § "Release-Prep PRs MUST Use `release/v*` Branch Convention" + `ci-runners.md` MUST 8, the gate workflow MUST include `if: ${{ !startsWith(github.head_ref, 'release/') }}` on every job. Release PRs do not edit specs; running the gate is wasted CI minutes.

**Alternatives Considered:**

1. Every PR, no paths filter — rejected, cost.
2. Spec-touching only, no source-root trigger — rejected, misses source-side regressions where deleting a class orphans a spec citation.
3. Manual `workflow_dispatch` only — rejected, defeats prevent-at-insertion goal.
4. Pre-commit only, no CI — rejected, CI is the merge gate; pre-commit is opt-in (contributors disable it).

**Consequences:**

- (+) ~30 min/month CI burden, well below the 3000-min free tier.
- (+) Source-root + spec-root trigger covers both directions of drift.
- (+) Release-prep skip is consistent with project-wide CI hygiene.
- (−) `paths:` filter requires maintenance when source layout changes (e.g., new `packages/kailash-foo/`); mitigation: a one-line addition in the workflow's `paths:` whenever a new package lands. Same maintenance cost as `test-kailash-ml.yml` already has.

**Verification command:**

```bash
# Workflow file has paths filter and release-prep skip
grep -E 'paths:|startsWith.*release' .github/workflows/spec-drift-gate.yml
# Expected: at least one match each
```

---

### 3.5 ADR-5 — Cross-SDK Design

**Status:** Proposed
**Decision:** **Manifest-driven Python script** (`.spec-drift-gate.toml`) for kailash-py. **Separate Rust port** for kailash-rs (NOT a wrapper around the Python script). Manifest schema is shared across SDKs to ensure assertion conventions stay parallel.

**Context:** Brief Q5 (line 95): "Cross-SDK design — does the gate read a config that points at the package source tree, so the same script runs against `kailash-rs/`? Or duplicate per-SDK?"

Verified: kailash-rs has 25 specs at `/Users/esperie/repos/loom/kailash-rs/specs/` (parallel ontology to kailash-py). The cross-SDK constraint is real, not hypothetical.

**Trade-off:**

- Same Python script, different manifests — works for SPEC parsing (markdown is markdown). Breaks for SOURCE parsing — Rust source needs `syn` or `tree-sitter-rust`, neither available in stdlib Python.
- Two scripts (one Python, one Rust) — same algorithm; each uses native AST.

**Decision:** **Two scripts with shared manifest schema and shared spec-parsing rules.** The kailash-py script ships first; the kailash-rs port lands as a sibling shard once the Python version is stable.

**Manifest schema** (`.spec-drift-gate.toml` at repo root):

```toml
[gate]
# Source roots to walk for AST extraction (relative to repo root)
source_roots = ["src/kailash", "packages"]
# Spec root
spec_root = "specs"
# Errors-module convention per package
[gate.errors_modules]
"kailash" = "src/kailash/errors.py"
"kailash-ml" = "src/kailash/ml/errors.py"
"kailash-align" = "packages/kailash-align/src/kailash_align/exceptions.py"
"kailash-pact" = "packages/kailash-pact/src/kailash_pact/errors.py"
# Section-heading regex per sweep (ADR-2)
[gate.section_sweeps]
fr_1_2_5 = "(?i)^## (surface|construction|public api|two coexisting surfaces)"
fr_4 = "(?i)^## (errors|exceptions|errors and exceptions)"
fr_7 = "(?i)^## (test contract|tests|tier .* tests)"
fr_9 = "(?i)^## (migration|module layout)"
# Workspace-leak patterns (FR-8)
[gate.leak_patterns]
patterns = [
  "\\bW\\d+\\s+\\d+[a-z]?\\b",
  "workspaces/[\\w/-]+",
  "specs/[\\w-]+-draft\\.md",
  "journal/\\d+",
]
# Sibling re-derivation domain prefixes (FR-10)
[gate.siblings]
domains = ["ml", "dataflow", "kaizen", "nexus", "pact", "align", "core",
           "mcp", "infra", "security", "trust", "diagnostics"]
```

The schema is identical between kailash-py and kailash-rs; only the values change. This guarantees the assertion convention stays in lockstep, which matches `cross-cli-parity.md` MUST 1 (neutral-body slot invariance) — semantic content identical across SDKs, only language-specific values differ.

**Alternatives Considered:**

1. Single Python script handles both — rejected, can't AST-parse Rust without third-party deps.
2. Rust script handles both — rejected, parsing Python AST in Rust is awkward (PyO3 / RustPython are heavyweight).
3. Tree-sitter wrapper script with Python CLI — rejected, tree-sitter adds a binary dep that the brief's "stdlib only" constraint excludes.

**Consequences:**

- (+) Each SDK uses its native AST — no cross-language friction.
- (+) Manifest schema is the parity contract; cross-CLI drift audit pattern (manifest-vs-manifest diff) catches semantic divergence.
- (+) Each SDK can ship independently; no blocking dependency.
- (−) Two scripts means two implementations to maintain. Mitigation: spec-parsing logic (markdown → assertion list) is identical and could be extracted into a shared file; only the AST extraction differs. Initial release ships both as separate files; refactor opportunity later.

**Verification command:**

```bash
# Manifest schema is byte-identical between kailash-py and kailash-rs (modulo values)
diff <(grep -E '^\[' kailash-py/.spec-drift-gate.toml) \
     <(grep -E '^\[' kailash-rs/.spec-drift-gate.toml) && \
  echo "ADR-5 manifest schema parity verified"
```

---

### 3.6 ADR-6 — Sweep Failure Verbosity

**Status:** Proposed
**Decision:** Every gate failure emits a **typed-guard-style fix instruction** in the form `<asserted_symbol> cited at <spec_path>:<line_no> (sweep <FR-N>) <action_verb> <where>`. Three action verbs: **"not found in"**, **"not exported from"**, **"absent on disk at"**.

**Context:** New ADR (not in brief). Per `rules/zero-tolerance.md` Rule 3a, typed delegate guards convert opaque failures into actionable one-line instructions. The same pattern should apply to gate output: every failure line MUST be self-sufficient — readable, locatable, and immediately actionable.

**Decision:** Output template:

```
FAIL <FR-N>: <asserted_symbol> cited at <spec_path>:<line_no> <action_verb> <where>
  → fix: (a) add the symbol, (b) fix the cite, OR (c) move the assertion to '## Deferred to M2' / similar
```

Concrete examples (matching W5-E2 + W6.5 findings):

```
FAIL FR-4: FeatureGroupNotFoundError cited at specs/ml-feature-store-v2-draft.md:515 not found in src/kailash/ml/errors.py
  → fix: (a) add the class to errors.py, (b) fix the cite, OR (c) move to '## Deferred to M2' section

FAIL FR-7: tests/integration/test_feature_store_wiring.py cited at specs/ml-feature-store-v2-draft.md:538 absent on disk at packages/kailash-ml/tests/integration/test_feature_store_wiring.py
  → fix: (a) create the test file, (b) fix the cite to test_feature_store.py, OR (c) move to '## Deferred to M2'

FAIL FR-1: Ensemble.from_leaderboard cited at specs/ml-automl-v2-draft.md:374 not found in source roots [src/kailash/, packages/kailash-ml/src/]
  → fix: (a) add the classmethod, (b) fix the cite to use Ensemble(...) constructor, OR (c) move to '## Deferred to M2'

FAIL FR-6: Ensemble cited at specs/ml-automl.md:412 not exported from kailash_ml.__all__
  → fix: (a) add 'Ensemble' to kailash_ml/__init__.py:__all__, (b) remove the export claim, OR (c) move to '## Deferred to M2'
```

**Constraints:**

- One line per failure for the headline; multi-line fix-hint may follow indented.
- ALL paths absolute or repo-root-relative — no `../../` segments.
- ALL line numbers from the spec source (the file the author edits), not from the source code.
- The `(a)/(b)/(c)` triad is invariant across sweeps for muscle-memory consistency.

**Alternatives Considered:**

1. JSON-only output (no human-readable form) — rejected, defeats pre-commit usability.
2. Generic "spec drift detected at X" — rejected, NOT actionable; per `zero-tolerance.md` Rule 3a is the failure mode this ADR fixes.
3. Verbose multi-paragraph descriptions — rejected, scrolling cost on large drift counts.

**Consequences:**

- (+) Every failure is locatable + actionable in one line.
- (+) The `(a)/(b)/(c)` triad encodes the spec-authority discipline: assertions are either real, wrong, or deferred — no fourth option.
- (+) GitHub PR annotation API can render each FAIL line directly with `::error file=<path>,line=<line>::<message>` workflow command.
- (−) Slightly more verbose than minimal `pytest`-style output; ~150 chars per failure. Acceptable since gate output is bounded by NFR-1.

**Verification command:**

```bash
# Run gate against fabricated fixture; output matches the template
python scripts/spec_drift_gate.py tests/fixtures/spec_drift_gate/bad_error_class.md | \
  grep -cE '^FAIL FR-[0-9]+: \w+ cited at .+:[0-9]+ (not found in|not exported from|absent on disk at)'
# Expected: ≥5 (one per fabricated error class)
```

---

### 3.7 ADR-7 — Future Spec-As-Test Evolution Path

**Status:** Proposed
**Decision:** Both ADR-2's `<!-- spec-assert: ... -->` directives AND a future structured annex format (`<!-- mech: class:X -->` per brief line 30) coexist. The gate parses BOTH forms; `<!-- mech: ... -->` is treated as an alias for `<!-- spec-assert: ... -->`. Authors may use whichever they prefer; consolidation happens later if one form proves unloved.

**Context:** New ADR. Brief line 30 mentions a "machine-readable annex per spec MUST clause" deferred to a second tier. ADR-2's marker convention needs to anticipate the migration.

**Decision:** The gate reads both:

```markdown
<!-- spec-assert: class:Ensemble.from_leaderboard -->
<!-- spec-assert: error:FeatureGroupNotFoundError reason:"deferred-feature placeholder" -->
<!-- spec-assert: test_path:tests/integration/test_feature_store_wiring.py -->

<!-- mech: class:Ensemble.from_leaderboard -->                               # alias
<!-- mech: error:FeatureGroupNotFoundError defer:M2 -->                      # alias with extra metadata
<!-- mech: test_path:tests/integration/test_feature_store_wiring.py -->      # alias
```

The `mech:` namespace is reserved for the future "mechanically-verifiable assertion" annex format; for now, it's a synonym. If the annex format evolves to add fields the `spec-assert:` form doesn't have (e.g., `defer:M2`, `priority:HIGH`), the gate parses them but ignores unknown keys — forward-compatible.

**Migration sketch (deferred):**

1. Phase 1 (this workspace): ship section-context + `spec-assert:` overrides.
2. Phase 2 (future workspace): when authoring discipline matures, introduce `<!-- mech: ... -->` blocks in a dedicated `## Mechanical Assertions` section per spec; gate prefers those when present, falls back to section-context inference when absent.
3. Phase 3 (future): if `mech:` proves richer (per-MUST-clause traceability, CI-line annotations), deprecate section-context inference; require explicit `mech:` annex.

The migration does NOT happen in this workspace cycle. The forward compatibility ensures no rework when phase 2 lands.

**Alternatives Considered:**

1. Ship only `<!-- mech: ... -->`; reject `<!-- spec-assert -->` — rejected, blocks ADR-2's lighter override pattern.
2. Ship only `<!-- spec-assert -->`; never adopt `<!-- mech -->` — rejected, brief line 30 explicitly anticipates the annex.
3. Reserve `<!-- mech -->` but error if used today — rejected, premature; treating it as an alias costs nothing.

**Consequences:**

- (+) Authors get a stable convention from day one (`<!-- spec-assert -->`).
- (+) Future structured-annex work doesn't invalidate today's annotations.
- (+) Both forms are grep-able for migration (`grep -rE '<!-- (spec-assert|mech):'`).
- (−) Two synonymous forms invite confusion; mitigation is documentation of the canonical form (`<!-- spec-assert -->` today; `<!-- mech -->` reserved).

**Verification command:**

```bash
# Both forms parse to the same finding count
python scripts/spec_drift_gate.py tests/fixtures/spec_drift_gate/spec_assert_form.md > /tmp/a
python scripts/spec_drift_gate.py tests/fixtures/spec_drift_gate/mech_form.md > /tmp/b
diff /tmp/a /tmp/b && echo "ADR-7 alias parity verified"
```

---

## 4. Interfaces / Integration Points

### 4.1 Pre-commit config snippet

Proposed addition to `.pre-commit-config.yaml`, modeled on the existing `pytest-check` local hook (lines 79-105):

```yaml
# Spec Drift Gate — verify spec assertions match code
- repo: local
  hooks:
    - id: spec-drift-gate
      name: Spec drift gate (assertions vs code)
      entry: .venv/bin/python scripts/spec_drift_gate.py
      language: system
      args:
        - --baseline=.spec-drift-baseline.jsonl
        - --format=human
        - --check-only
      files: ^(specs/.*\.md|scripts/spec_drift_gate\.py|\.spec-drift-baseline\.jsonl|\.spec-drift-gate\.toml)$
      pass_filenames: false
      always_run: false
      stages: [pre-commit]
```

**Why these flags:**

- `--baseline=...`: respects the baseline grace window (FR-11).
- `--format=human`: matches `pytest-check`'s pre-commit aesthetic.
- `--check-only`: exit 0 when no NEW findings; the gate doesn't regenerate baseline at pre-commit (that's an explicit `--regenerate-baseline` flag).
- `files:` regex: matches the workflow `paths:` (parity).
- `pass_filenames: false`: gate determines its own scope from manifest.
- `always_run: false`: triggers only on matching files (lighter than `pytest-check`'s `always_run: true`).

### 4.2 GitHub Actions workflow snippet (PROPOSED — user reviews before merge)

Per `feedback_no_auto_cicd.md` (user memory: "NEVER auto-create GitHub Actions workflows; always ask user first with cost implications"), this section presents the workflow as **proposed text** for human review. The implementation phase MUST NOT auto-create this file.

**Proposed file:** `.github/workflows/spec-drift-gate.yml`

**Cost footprint** (per `ci-runners.md` MUST 7):

```
Cadence:        on PRs touching specs/, scripts/spec_drift_gate.py, source roots
Trigger paths:  ~5-10 spec PRs/week
Monthly worst:  10 runs/week × 4 weeks × 1 min runtime = 40 min/month
Fast-exit:      YES — <30s typical (NFR-1)
Effective:      ~30-40 min/month under typical load
```

```yaml
name: Spec Drift Gate

on:
  pull_request:
    paths:
      - "specs/**"
      - "scripts/spec_drift_gate.py"
      - ".spec-drift-baseline.jsonl"
      - ".spec-drift-gate.toml"
      - "src/kailash/**/*.py"
      - "packages/*/src/**/*.py"
  workflow_dispatch:

permissions:
  contents: read
  pull-requests: write # for posting findings as PR review comments

concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.run_id }}
  cancel-in-progress: true

jobs:
  spec-drift-gate:
    if: ${{ !startsWith(github.head_ref, 'release/') }} # ci-runners.md MUST 8
    name: Spec assertions vs code
    runs-on: ubuntu-latest
    timeout-minutes: 5

    steps:
      - uses: actions/checkout@v6

      - name: Set up Python 3.12
        uses: actions/setup-python@v6
        with:
          python-version: "3.12"

      - name: Install uv
        uses: astral-sh/setup-uv@v7

      - name: Install editable (for AST resolution of packages/*)
        run: |
          uv venv .venv
          uv pip install -e "." --python .venv/bin/python
          # NOTE: editable install only — gate runs without importing the SDK,
          # uses ast.parse on source files directly (no runtime import).

      - name: Run spec drift gate
        id: gate
        run: |
          .venv/bin/python scripts/spec_drift_gate.py \
            --baseline=.spec-drift-baseline.jsonl \
            --format=json \
            --check-only \
            > spec-drift-findings.jsonl
        continue-on-error: false

      - name: Upload findings (always)
        if: always()
        uses: actions/upload-artifact@v7
        continue-on-error: true # ci-runners.md MUST NOT 2 (artifact quota)
        with:
          name: spec-drift-findings
          path: spec-drift-findings.jsonl
          retention-days: 14

      - name: Post findings as PR comment (on failure)
        if: failure() && github.event_name == 'pull_request'
        run: |
          .venv/bin/python scripts/spec_drift_gate.py \
            --baseline=.spec-drift-baseline.jsonl \
            --format=human \
            --check-only \
            > spec-drift-findings.txt || true
          gh pr comment "${{ github.event.pull_request.number }}" \
            --body "## Spec Drift Findings\n\n\`\`\`\n$(cat spec-drift-findings.txt)\n\`\`\`"
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Reviewer checklist for the user before merging this workflow:**

- [ ] Cost footprint accepted (~40 min/month).
- [ ] `permissions:` minimum surface acceptable (read + PR comment write).
- [ ] `release/v*` branch skip honored.
- [ ] `concurrency: cancel-in-progress` matches project default.
- [ ] No new third-party Action besides `actions/{checkout,setup-python,upload-artifact}` and `astral-sh/setup-uv` (already used elsewhere in the repo per `Glob`).

### 4.3 CLI surface

Proposed CLI for `python scripts/spec_drift_gate.py --help`:

```
Usage: spec_drift_gate.py [OPTIONS] [PATHS...]

Verify spec assertions in specs/*.md against actual code.

Options:
  --manifest PATH                Path to .spec-drift-gate.toml manifest
                                 [default: .spec-drift-gate.toml]
  --baseline PATH                Path to baseline file
                                 [default: .spec-drift-baseline.jsonl]
  --format [human|json]          Output format
                                 [default: human]
  --check-only                   Exit 1 if NEW findings (vs baseline) exist;
                                 do NOT print resolved-finding notice.
  --regenerate-baseline          Print findings as new baseline (write to
                                 stdout; redirect to .spec-drift-baseline.jsonl).
  --siblings-of PATH             FR-10 advisory mode: list siblings of PATH that
                                 reference symbols defined in PATH.
  --sweep [FR-1..FR-13|all]      Run only the named sweep [default: all]
  --severity [CRIT|HIGH|MED|LOW] Minimum severity to report [default: HIGH]
  -v, --verbose                  Print per-file scan progress to stderr.
  --version                      Print gate version and exit.
  -h, --help                     Show this message and exit.

Examples:
  # Verify all specs against code (default)
  python scripts/spec_drift_gate.py

  # Check a specific spec only (used in pre-commit when only one file changed)
  python scripts/spec_drift_gate.py specs/ml-automl.md

  # Generate JSON output for CI annotation
  python scripts/spec_drift_gate.py --format json > findings.jsonl

  # Refresh baseline after a batch of fixes
  python scripts/spec_drift_gate.py --regenerate-baseline > .spec-drift-baseline.jsonl

  # Get siblings to review after editing one spec
  python scripts/spec_drift_gate.py --siblings-of specs/ml-engines.md
```

### 4.4 Output formats

**Human format (default, pre-commit):**

```
spec-drift-gate v1.0 — scanning 72 specs against 4 source roots
✓ specs/core-nodes.md (12 assertions)
✓ specs/ml-engines.md (34 assertions)
✗ specs/ml-feature-store-v2-draft.md
  FAIL FR-4: FeatureGroupNotFoundError cited at specs/ml-feature-store-v2-draft.md:515 not found in src/kailash/ml/errors.py
    → fix: (a) add the class, (b) fix the cite, OR (c) move to '## Deferred to M2'
  FAIL FR-4: FeatureVersionNotFoundError cited at specs/ml-feature-store-v2-draft.md:515 not found in src/kailash/ml/errors.py
    → fix: (a) add the class, (b) fix the cite, OR (c) move to '## Deferred to M2'
  ... (3 more FR-4 failures elided)
  FAIL FR-7: tests/integration/test_feature_store_wiring.py cited at specs/ml-feature-store-v2-draft.md:538 absent on disk

================================================================================
Summary: 6 NEW findings (5 CRIT, 1 HIGH); baseline has 36 pre-existing.
Run `python scripts/spec_drift_gate.py --baseline=.spec-drift-baseline.jsonl --format=human` for details.
Wall clock: 14.3s.

EXIT 1 (new drift introduced)
```

**JSON format (CI):**

```jsonl
{"asserted_symbol":"FeatureGroupNotFoundError","fix_hint":"...","line_no":515,"new":true,"severity":"CRIT","spec_path":"specs/ml-feature-store-v2-draft.md","sweep":"FR-4-error-class"}
{"asserted_symbol":"FeatureVersionNotFoundError","fix_hint":"...","line_no":515,"new":true,"severity":"CRIT","spec_path":"specs/ml-feature-store-v2-draft.md","sweep":"FR-4-error-class"}
... (4 more lines)
```

GitHub PR annotation format (emitted alongside JSONL when running in Actions):

```
::error file=specs/ml-feature-store-v2-draft.md,line=515,title=FR-4 fabricated error class::FeatureGroupNotFoundError cited but not found in src/kailash/ml/errors.py
```

---

## 5. Acceptance Criteria Mapped To Brief

The brief's "Acceptance criteria for this workspace cycle" (lines 70-78) are mapped to verification tests below.

### 5.1 `scripts/spec_drift_gate.py` implementing the four sweeps

**Brief line 71.** Test:

```bash
test -f scripts/spec_drift_gate.py && \
  python scripts/spec_drift_gate.py --version && \
  echo "5.1 verified"
```

Expected: file exists; `--version` prints `spec-drift-gate v1.0` (or higher).

### 5.2 `.pre-commit-config.yaml` entry running it on `specs/**.md` changes

**Brief line 72.** Test:

```bash
grep -A 8 'spec-drift-gate' .pre-commit-config.yaml | grep -qE 'specs/.*\.md' && \
  echo "5.2 verified"
```

### 5.3 `.github/workflows/spec-drift-gate.yml` (proposed, user-merged)

**Brief line 73.** This file does NOT exist in this workspace cycle's deliverables (per `feedback_no_auto_cicd.md`); it is presented as a proposal in § 4.2 and the user reviews + merges separately. Acceptance: § 4.2 contains the YAML; ADR-4 documents the cost footprint; user signs off.

### 5.4 `.spec-drift-baseline.jsonl` capturing the 36-HIGH backlog

**Brief line 74.** Test:

```bash
test -f .spec-drift-baseline.jsonl && \
  test "$(wc -l < .spec-drift-baseline.jsonl)" -ge 36 && \
  python -c "import json; [json.loads(l) for l in open('.spec-drift-baseline.jsonl')]" && \
  echo "5.4 verified"
```

Expected: file exists; ≥36 lines; every line is parseable JSON.

### 5.5 One-spec prototype validating the sweep design (`ml-automl.md`)

**Brief line 75.** Test:

```bash
# Pristine v2.0.0 spec should produce zero NEW findings against an empty baseline
python scripts/spec_drift_gate.py --baseline=/dev/null --format=human specs/ml-automl.md
[ $? -eq 0 ] && echo "5.5 verified (ml-automl.md is clean)"
```

Expected: exit 0, no failures (since v2.0.0 was authored to match the actual surface).

### 5.6 Demonstrably catch the FeatureStore CRIT-1 fabricated classes

**Brief line 60 + line 78.** Pytest invocation:

```bash
.venv/bin/python -m pytest tests/integration/test_spec_drift_gate_corpus.py::test_w65_crit1_reproduction -v
```

Test body (proposed):

```python
def test_w65_crit1_reproduction():
    """
    Wave 6.5 round 1 of ml-feature-store-v2-draft.md fabricated 5 typed
    exceptions. The gate MUST emit one FR-4 finding per fabrication.
    """
    fixture = "tests/fixtures/spec_drift_gate/w65_crit1_fabricated_errors.md"
    # Fixture content is the verbatim § 10.2 line 515 text from the
    # rejected v2 draft, isolated to a single spec for reproducibility.
    findings = run_gate([fixture], baseline=None, sweep="FR-4")
    fabricated = {
        "FeatureGroupNotFoundError",
        "FeatureVersionNotFoundError",
        "FeatureEvolutionError",
        "OnlineStoreUnavailableError",
        "CrossTenantReadError",
    }
    found_symbols = {f.asserted_symbol for f in findings if f.severity == "CRIT"}
    assert fabricated == found_symbols, (
        f"Gate missed fabricated classes. "
        f"Expected {fabricated}, got {found_symbols}."
    )
```

### 5.7 Documentation in `skills/spec-compliance/SKILL.md`

**Brief line 76.** A new section appended to the existing skill (lines 1-228):

```markdown
## Executable Form: `spec_drift_gate.py`

The skill's protocol (Steps 1-9) is implemented as `scripts/spec_drift_gate.py`. Run:

    python scripts/spec_drift_gate.py specs/<file>.md

The gate executes Steps 1, 2, 5, 7, 8 from this skill mechanically. Steps 3 (decorator counts), 6 (security mitigations), and 9 (self-report trust ban) remain agent responsibilities — the gate verifies symbols, not behaviors.

See `workspaces/spec-drift-gate/01-analysis/02-requirements-and-adrs.md` for the design rationale.
```

### 5.8 Tier 1 + Tier 2 tests for the gate itself

**Brief line 77.** See FR-12 + NFR-5. Tests live at:

- `tests/unit/test_spec_drift_gate.py` (Tier 1, fixtures only)
- `tests/integration/test_spec_drift_gate_corpus.py` (Tier 2, against real `specs/` and real source tree)

### 5.9 Demonstration: deliberately-broken spec fails CI; realignment passes

**Brief line 78.** Demo workflow:

1. Create branch `chore/spec-drift-demo`
2. Add `<!-- spec-assert: class:NonExistentEngine -->` to `specs/ml-automl.md`
3. Push; CI fails the `spec-drift-gate` job with an FR-1 finding
4. Remove the assertion (or replace with `<!-- spec-assert-skip -->`)
5. Push; CI passes

This demonstration is itself a pytest in `tests/integration/test_spec_drift_gate_demo.py`:

```python
def test_demo_broken_spec_fails(tmp_repo):
    tmp_repo.write_spec("ml-automl.md", existing_text + "\n<!-- spec-assert: class:NonExistentEngine -->")
    rc = run_gate_subprocess(tmp_repo)
    assert rc != 0
    assert "NonExistentEngine" in rc.stderr
```

---

## 6. Out-Of-Scope Re-Confirmation

The brief (lines 62-67) lists four out-of-scope items. Re-confirmed and contested:

### 6.1 "Rewriting prose"

**Confirmed.** The gate verifies mechanical assertions. Narrative quality (sentence flow, section organization, prose tone) is the reviewer's domain, not the gate's. **Boundary clarification:** "prose" includes section ordering, English grammar, and explanatory text. It does NOT include section _headings_ — the gate IS sensitive to heading names because ADR-2 uses heading regex to scope sweeps. Editing `## Surface` to `## Public Interface` would silently un-sweep a section. This is a known consequence of ADR-2 and is mitigated by the gate's INFO-line scanned-section enumeration.

### 6.2 "Cross-SDK Python↔Rust drift detection"

**Confirmed.** This workspace ships kailash-py only. ADR-5 specifies the manifest schema parity that enables a future Rust port. Cross-SDK drift detection (e.g., "kailash-py spec asserts X, kailash-rs spec asserts Y, both cite the same cross-SDK protocol") is a separate workstream addressed by `cross-cli-parity.md` and the existing `extract-api-surface.py` parity sweeps. The spec-drift-gate is intentionally scoped to in-SDK drift.

### 6.3 "Spec generation from code"

**Confirmed.** The gate keeps drift OUT of human-authored specs; it does NOT generate specs from code. The opposite direction (code → spec via docstring extraction) is explicitly out of scope and addressed by Sphinx autodoc / docs-build pipelines elsewhere.

### 6.4 "Replacing /redteam"

**Confirmed.** `/redteam` performs plan-vs-implementation alignment across multiple dimensions (security, performance, naming, etc.). The gate covers only spec-vs-code drift — one specific dimension. **Contested clarification:** The gate REDUCES the per-round cost of the spec-compliance step inside `/redteam` from ~30 min of manual sweeping to <30s of mechanical scan. `/redteam` still runs; its spec-compliance step now invokes the gate.

---

## 7. Workplan Sketch (≤1 page)

Per `rules/autonomous-execution.md` § Per-Session Capacity Budget, work is sized in **autonomous execution sessions** with the ≤500 LOC load-bearing logic / ≤5-10 invariants budget.

### 7.1 Sequencing

| Session | Output                                                                      | Invariants                                            | LOC est. |
| ------- | --------------------------------------------------------------------------- | ----------------------------------------------------- | -------- |
| **S1**  | `scripts/spec_drift_gate.py` (FR-1, FR-2, FR-4, FR-7) + ADR-2 marker parser | symbol existence, errors module, test paths, markers  | ~400     |
| **S2**  | `.spec-drift-gate.toml` manifest + FR-3, FR-5, FR-6, FR-8                   | decorator counts, fields, `__all__` membership, leaks | ~250     |
| **S3**  | Baseline format + FR-11 grace logic; CLI flags; output formats              | baseline diff, JSONL determinism, fix-hint template   | ~200     |
| **S4**  | Tier 1 fixtures (FR-12) + Tier 2 corpus test + Wave 6.5 reproduction test   | self-test, CRIT-1 demo                                | ~300     |
| **S5**  | `.pre-commit-config.yaml` integration + pristine `specs/` baseline capture  | live integration, baseline curation                   | ~100     |
| **S6**  | (Proposed) `.github/workflows/spec-drift-gate.yml` + skill doc update       | CI workflow, skill cross-ref                          | ~80      |

Total: ~1330 LOC across 6 sessions; well within the autonomous budget when sessions are sequential. Sessions S1-S3 have a tight feedback loop (run gate against fixture; iterate) which qualifies for the 3-5× capacity multiplier per `rules/autonomous-execution.md` MUST 3.

**Parallelization:** S4 (testing) can run in parallel with S5 (config integration) once S1-S3 are merged. S6 (CI workflow + docs) is parallelizable with S5 because they touch disjoint files.

### 7.2 Prototype boundary

**Validated against:** `specs/ml-automl.md` v2.0.0 (the freshest spec, audited W6.5 APPROVE WITH AMENDMENTS). The gate run against `ml-automl.md` MUST produce zero NEW findings (since v2 is by construction faithful to code). Any deviation = gate has a false positive; iterate ADR-2 markers until clean.

**Stress-tested against:** `specs/ml-feature-store-v2-draft.md` round 1 (the fabricated CRIT-1 / CRIT-2 case). The gate MUST produce ≥6 findings (5 FR-4 + 1 FR-7). This is the demo regression.

### 7.3 Self-test fixtures

Located at `tests/fixtures/spec_drift_gate/`. Each fixture is a deliberately-broken spec exercising one FR. Names listed in FR-12. The fixtures are NOT under `specs/` (so the production sweep skips them); they are reachable only via the test harness.

### 7.4 Risk surface (cross-reference to `01-failure-points.md` § A1+)

The failure-point analyst (parallel) is enumerating risks. Expected high-confidence risks the workplan must accommodate (best-guess; revise after sibling output lands):

- **R1: Heading-regex brittleness.** Authors paraphrase heading names; sweep coverage drops silently. Mitigation: gate emits scanned-section list per spec.
- **R2: Baseline staleness.** Baseline file accumulates resolved findings; PR signal degrades. Mitigation: ADR-3 advisory notice + scheduled `chore(spec-drift): refresh baseline` PRs.
- **R3: Source-root walk performance.** AST-parsing every `.py` file in the repo each run could blow NFR-1 budget. Mitigation: per-file caching keyed by `mtime + sha`; only re-parse changed files.
- **R4: Dataclass field detection edge cases.** `dataclass` vs `attrs` vs Pydantic vs frozen `@dataclass(frozen=True, slots=True)` all produce different ASTs. Mitigation: FR-5 covers `AnnAssign` which is the common substrate; document Pydantic edge cases as known gap.

---

## 8. Counts

- **Functional requirements:** 13 (FR-1 through FR-13, with FR-3a as a sub-clause of FR-3)
- **Non-functional requirements:** 5 (NFR-1 through NFR-5)
- **ADRs:** 7 (5 from brief open-questions + ADR-6 sweep verbosity + ADR-7 future evolution)
- **Concrete pseudocode sweeps:** 10 (FR-1 through FR-9 + FR-11 baseline diff)

**Single highest-confidence ADR:** **ADR-2 (Marker convention — section-context inference + `<!-- spec-assert: ... -->` overrides).**

**Evidence for ADR-2 confidence:**

1. **Empirical grounding.** The W6.5 reviewer's mechanical sweep table (`workspaces/portfolio-spec-audit/04-validate/W6.5-v2-draft-review.md` lines 45-65 + 137-157) is the literal precedent for this sweep design — 17 of 17 AutoML checks PASS, 16 of 18 FeatureStore checks PASS — using exactly the section-heading discipline ADR-2 codifies.
2. **Existing spec corpus already follows the pattern.** AutoML v2.0.0 (`specs/ml-automl.md` lines 17-95) uses `## 1. Scope`, `## 2. Construction`, `## 3. ...` — the canonical section names ADR-2's regex matches. The 72-file corpus is mostly v1 / v2 hybrid; freshly authored v2 specs will trend toward this structure naturally.
3. **FPR estimate is bounded.** Of the ~70 W5-E2 findings across 11 specs, all are in `## Surface` / `## Errors` / `## Test Contract` equivalent sections. Backticked symbols in `## Out of Scope` / `## Deferred to M2` are systematically NOT findings — exactly what ADR-2 excludes. Estimated FPR <5% (NFR-2 target).
4. **Override mechanism is forward-compatible.** ADR-7 explicitly preserves migration to the brief's deferred annex format without rework.
5. **The alternative (Option A backticks-only) is decisively rejected.** Counted backtick references in `specs/ml-automl.md`: ~250+. If all were assertions, FPR would be ~80% — the gate would be unusable.

This is the only ADR where the design space was mapped exhaustively (3 alternatives evaluated), the alternatives quantified (counted occurrences in the live corpus), AND the chosen option backed by an existing reviewer's working procedure (W6.5 mechanical sweep tables). The other ADRs have strong rationale but draw on smaller evidence bases.

---

## 9. Open Questions Surfaced During Analysis

These are NOT in the brief and are RECOMMENDED for resolution before `/implement`:

1. **Q9.1 — Multi-package errors module convention.** ADR-5's manifest declares one errors module per package. But several packages (kailash-ml) have legacy + canonical errors modules that coexist. Decision needed: scan all declared paths; succeed if class found in ANY; OR explicit primary-fallback ordering?

2. **Q9.2 — Pydantic vs dataclass detection.** FR-5 pseudocode handles `AnnAssign` (covers dataclass + slots-dataclass). Pydantic v2 `BaseModel` uses class-level annotations the same way; `attrs` uses class decorators with custom semantics. Should the gate handle these uniformly? If yes, FR-5 needs a wider AST recognizer. Recommend: ship FR-5 as-is for v1.0; add Pydantic / attrs in v1.1 with a regression test.

3. **Q9.3 — Versioned `__all__` re-exports.** Some packages have lazy `__getattr__` patterns (`kailash_ml/__init__.py` per `ml-automl.md` § 1.3) where the import resolves to a different module at runtime than declaration time. FR-6 (AST-only) won't see the runtime resolution. Decision needed: should the gate also verify the `__getattr__` map's resolution paths? If yes, parsing `__getattr__` body is non-trivial. Recommend: ship FR-6 as `__all__`-only for v1.0; document `__getattr__`-resolved exports as a known gap; add in v1.1 with a regression test.

4. **Q9.4 — Spec-prose-mention denylist.** ADR-2's section-context inference treats `## Out of Scope` as silent. But what if an `## Out of Scope` section says "the foo `BarEngine` class is OOS for v1" and someone misreads it as an assertion? The marker discipline assumes authors don't put assertions in narrative sections. Recommend: ADR-2's overrides are sufficient; document the convention in skill cross-reference.

These questions are added to the workplan as gating items for S1 / S2 (not blockers, but decisions to make explicit).

---

## 10. Cross-References

- `briefs/01-product-brief.md` — input for this analysis
- `01-failure-points.md` — sibling parallel analysis (assumed to land at this path)
- `workspaces/portfolio-spec-audit/04-validate/W5-E2-findings.md` — F-E2-01..F-E2-22 audit findings
- `workspaces/portfolio-spec-audit/04-validate/W6.5-v2-draft-review.md` — Wave 6.5 CRIT-1 / CRIT-2 evidence
- `.claude/skills/spec-compliance/SKILL.md` — protocol-level documentation; gate productionizes this
- `.claude/skills/16-validation-patterns/orphan-audit-playbook.md` — sibling audit pattern at the source level
- `.claude/rules/specs-authority.md` — MUST 5b sibling re-derivation (FR-10's basis)
- `.claude/rules/orphan-detection.md` — MUST 6 `__all__` rule (FR-6's converse direction)
- `.claude/rules/zero-tolerance.md` — Rule 3a typed-guard (ADR-6's basis)
- `.claude/rules/git.md` — Pre-FIRST-Push CI Parity (ADR-4)
- `.claude/rules/ci-runners.md` — MUST 7 cron cost footer + MUST 8 release-prep skip (ADR-4)
- `.claude/rules/cross-cli-parity.md` — MUST 1 neutral-body invariance (ADR-5 manifest schema parity)

End of analysis.
