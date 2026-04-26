# Spec Drift Gate Specification

**Version:** 1.0.0 (planned — implementation gates `/todos` approval)
**Status:** v1.0 spec authored 2026-04-26 from `/analyze` synthesis at `workspaces/spec-drift-gate/`
**Surface:** `scripts/spec_drift_gate.py` (Python, stdlib + ripgrep), invoked via pre-commit hook + GitHub Actions
**License:** Apache-2.0
**Owner:** Terrene Foundation (Singapore CLG)

The Spec Drift Gate is the executable form of the protocol documented at `.claude/skills/spec-compliance/SKILL.md`. It mechanically verifies "is implemented" assertions in `specs/*.md` against the source tree at PR time, replacing the audit-after-the-fact loop (Wave 5 portfolio audit → Wave 6.5 spec realignment) with prevent-at-insertion.

Origin: Wave 5 portfolio audit surfaced 38 HIGH spec/code drift findings across 7 shards; Wave 6.5 realigned 13 of them via `ml-automl.md` + `ml-feature-store.md` v2 (PR #639). The gate productionizes the mechanical sweeps the audit shards ran by hand.

---

## 1. Purpose & Scope

### 1.1 In Scope (v1.0)

The gate verifies the following classes of assertion in `specs/*.md`:

1. **Class existence** — every backticked `ClassName` cited in an allowlisted assertion section MUST exist as an AST `ClassDef` in the configured source roots.
2. **Function / method existence** — every cited `func()` or `Class.method()` MUST exist as `FunctionDef` / `AsyncFunctionDef` in the resolved class body.
3. **Decorator application + count** — every claim "the `@feature` decorator is applied to N functions" MUST be reproducible by AST count.
4. **Error-class existence** — every cited `XError` in `## Errors` / `## Exceptions` sections MUST exist in the configured errors module(s).
5. **Field/attribute existence** — every cited dataclass field MUST exist as `AnnAssign` in the class body.
6. **`__all__` membership** — every symbol cited as "exported" MUST appear in the relevant package's `__all__`.
7. **Test file existence** — every test path enumerated in `## Test Contract` sections MUST exist on disk.
8. **Workspace-artifact leak detection** — `grep -E '(W3[0-9] [0-9]+|workspaces/)' specs/` returns zero matches outside explicit citation contexts.

### 1.2 Out of Scope (v1.0 — see § 11 for M2 deferrals)

- Method-body content verification (`/redteam` Check 8 owns this).
- Orphan call-site detection (`rules/orphan-detection.md` MUST 1 stays at `/redteam`).
- Cross-SDK Python↔Rust drift (M2 — see § 11.2).
- Spec generation from code (different workstream).
- Adversarial Unicode evasion (gate is hygiene, not security).
- Narrative quality / prose review.
- Dynamically-generated classes (metaclass / `type(...)` factories) — flagged WARN, not blocked.

---

## 2. Surface

### 2.1 CLI

```
python scripts/spec_drift_gate.py [OPTIONS] [<spec_path>...]

OPTIONS:
  --format {human,json,github}   Output format (default: human)
  --baseline <path>              Baseline file (default: .spec-drift-baseline.jsonl)
  --refresh-baseline             Remove resolved entries; write to .spec-drift-resolved.jsonl
  --filter <expr>                Filter findings (e.g., origin:F-E2-01)
  --no-baseline                  Run without baseline grace; show all findings
  --version                      Print version + manifest path
  --help                         Show usage

ARGUMENTS:
  <spec_path>...                 Optional spec paths (default: all specs/*.md)
```

### 2.2 Pre-commit hook

Defined in `.pre-commit-config.yaml`:

```yaml
- id: spec-drift-gate
  name: spec-drift-gate
  entry: python scripts/spec_drift_gate.py
  language: python
  files: ^specs/.*\.md$
  pass_filenames: true
  stages: [pre-commit, manual]
```

Hook scope is `specs/**.md` ONLY — the gate does NOT trigger on `.py` source changes (per ADR-4; reverse-index hook is M2 per `01-failure-points.md` § C3).

### 2.3 GitHub Actions workflow (PROPOSED)

`.github/workflows/spec-drift-gate.yml` ships as a SEPARATE PR per `feedback_no_auto_cicd.md`. Cost footprint per ADR-4: ~40 minutes/month at full corpus per PR. Trigger: `pull_request` paths-filter on `specs/**.md`.

### 2.4 Manifest

`.spec-drift-gate.toml` at repo root declares source roots, errors modules, and exclusion patterns. The manifest schema is the canonical form for the gate (overrides any divergent example in `workspaces/spec-drift-gate/01-analysis/02-requirements-and-adrs.md` ADR-5). The schema is forward-compatible with cross-SDK reuse (kailash-py + kailash-rs); single-invocation cross-repo verification is M2 — see § 11.2:

```toml
[gate]
version = "1.0"
spec_glob = "specs/**.md"

[[source_roots]]
package = "kailash-core"
path = "src/kailash"

[[source_roots]]
package = "kailash-ml"
path = "packages/kailash-ml/src/kailash_ml"

[[source_roots]]
package = "kailash-dataflow"
path = "packages/kailash-dataflow/src/dataflow"

[errors_modules]
default = "src/kailash/ml/errors.py"
overrides = [
  { package = "kailash-pact", path = "packages/kailash-pact/src/pact/errors.py" },
]

[exclusions]
test_specs = ["tests/fixtures/spec_drift_gate/*.md"]
```

---

## 3. Marker Convention (the architectural keystone)

Per `01-analysis/02-requirements-and-adrs.md` ADR-2, the gate's discrimination of assertion vs. informal mention is the load-bearing decision — **17 of 28 failure-mode mitigations depend on it** (`01-analysis/01-failure-points.md` § Closing Notes).

### 3.1 Default mode — section-context inference

Backticked symbols are treated as assertions ONLY when they appear inside an allowlisted section heading:

| Section heading regex (case-insensitive)            | Sweeps applied   |
| --------------------------------------------------- | ---------------- |
| `## (Surface\|Construction\|Public API)`            | FR-1, FR-2, FR-5 |
| `## Errors\|## Exceptions`                          | FR-4             |
| `## (Test Contract\|Tests\|Tier .* Tests)`          | FR-7             |
| (no v1.0 sweep — FR-9 deferred to v1.1, see § 11.7) | —                |
| `## (Examples\|Quickstart)`                         | FR-1, FR-2 smoke |

Sweeps are SILENT in: `## Scope`, `## Out of Scope`, `## Industry Parity`, `## Deferred to M2`, `## Cross-References`, `## Conformance Checklist`, and any heading not matched by the regex above.

### 3.2 Explicit override directives

Two HTML-comment directives override the section-context inference:

**`<!-- spec-assert: <kind>:<symbol> -->`** — force-assert a symbol the heuristic missed.

```markdown
<!-- spec-assert: class:Ensemble.from_leaderboard -->

The `Ensemble.from_leaderboard()` classmethod is canonical.
```

**`<!-- spec-assert-skip: <kind>:<symbol> reason:"..." -->`** — force-skip a symbol the heuristic flagged. The `reason:` field is REQUIRED for review hygiene.

```markdown
<!-- spec-assert-skip: class:SentimentAnalysisAgent reason:"illustrative example only" -->

Imagine a `SentimentAnalysisAgent` class…
```

Reviewers grep `grep -rn spec-assert-skip specs/` to audit overrides — every directive is grep-able, every reason is human-readable.

### 3.3 Section heading drift (failure mode A3 / R1)

When the gate finds zero assertions in a spec, it emits an INFO line listing scanned sections. If the spec uses a non-allowlisted heading (e.g., `## Public Interface` instead of `## Surface`), the gate emits a WARN suggesting the canonical name — silently un-swept sections are caught immediately, not at the next audit.

---

## 4. Sweep Contracts

The 13 functional requirements (FR-1..FR-13) live in full at `workspaces/spec-drift-gate/01-analysis/02-requirements-and-adrs.md` § 1. Each FR has: trigger condition, AST/grep pseudocode, edge cases, fix-hint format. Summary table:

| FR        | Sweep                              | What it catches (audit cite)                                                                                                  |
| --------- | ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| FR-1      | Class existence                    | F-E2-05 `Ensemble.from_leaderboard` absent                                                                                    |
| FR-2      | Function/method existence          | F-E2-08 `MLEngine.fit_auto()` signature absent                                                                                |
| FR-3      | Decorator application + count      | "12 training methods registered" claim verification                                                                           |
| FR-4      | Error class in errors module       | **W6.5 CRIT-1**: 5 fabricated `*Error` classes                                                                                |
| FR-5      | Field/attribute on dataclass       | F-E1-38 `RLTrainingResult` missing 8 spec fields                                                                              |
| FR-6      | `__all__` membership               | PR #523/#529 (4 DeviceReport symbols missing)                                                                                 |
| FR-7      | Test file existence                | **W6.5 CRIT-2**: `test_feature_store_wiring.py` absent                                                                        |
| FR-8      | Workspace-artifact leak            | spec-level leak — `W31 31b` mention surfaced in W6.5 round-1 FeatureStore draft (now fixed in `specs/ml-feature-store.md` v2) |
| ~~FR-9~~  | ~~MOVE shim verification~~         | **deferred to v1.1 — see § 11.7**                                                                                             |
| ~~FR-10~~ | ~~Sibling re-derivation advisory~~ | **deferred to v1.1 — see § 11.8**                                                                                             |
| FR-11     | Baseline grace                     | Pre-existing 36-HIGH backlog handling                                                                                         |
| FR-12     | Self-test fixtures                 | Gate's own Tier 1 + Tier 2 coverage                                                                                           |
| FR-13     | Output: human + JSON + GitHub      | Pre-commit / CI / PR-review markup                                                                                            |

---

## 5. Baseline Lifecycle

Per ADR-3 — JSON Lines format at `.spec-drift-baseline.jsonl`, one finding per line, sorted, committed to repo root.

### 5.1 Entry schema

```json
{
  "spec": "specs/ml-feature-store.md",
  "line": 515,
  "finding": "FR-4",
  "symbol": "FeatureGroupNotFoundError",
  "kind": "class",
  "origin": "F-E2-18",
  "added": "2026-04-26",
  "ageout": "2026-07-25"
}
```

Every entry MUST have:

- **`origin`** — citation: an audit finding ID (`F-E2-NN`), a PR number (`#NNN-discovery`), or an issue (`gh-NNN`). Free-form text is BLOCKED.
- **`added`** — ISO date the entry first landed in baseline.
- **`ageout`** — ISO date 90 days after `added`. Past this date, the gate emits WARN; 90 days past WARN, the gate hard-fails the entry (forces resolution or explicit re-justification).

### 5.2 Lifecycle states

```
new finding → not in baseline → FAIL (block PR)
new finding → in baseline → PASS (grace)
existing baseline entry, code/spec resolved it → INFO ("resolved; refresh-baseline to remove")
existing baseline entry, past ageout → WARN ("expired; resolve or extend justification")
existing baseline entry, past 2× ageout → FAIL (force resolution)
```

### 5.3 `--refresh-baseline` flow

1. Run all sweeps without baseline grace.
2. Compute set of findings present today.
3. Diff against current baseline:
   - Findings in baseline but not today → resolved (write to `.spec-drift-resolved.jsonl` with resolving-commit SHA + remove from baseline).
   - Findings today not in baseline → would fail if added (refresh does NOT auto-add new findings; that's a deliberate `git add` on the baseline file).
4. Write the updated `.spec-drift-baseline.jsonl`; the resolved-archive `.spec-drift-resolved.jsonl` is the audit trail.

### 5.4 Anti-rot mechanisms

Per `01-failure-points.md` § D4 (baseline rot is the single biggest long-term risk):

1. **Origin field required** — no untracked drift; every baseline entry traces back.
2. **Age-out timestamps** — entries can't live forever; 90 days is the default review window (configurable in manifest).
3. **PR description prompt** — when `.spec-drift-baseline.jsonl` is touched in a PR, the PR template asks "are you adding to the baseline (justify) or resolving an entry (cite SHA)?".
4. **Quarterly cleanup PRs** — `chore(spec-drift): refresh baseline` opens a scheduled PR (suggested cron at `01-analysis/02-requirements-and-adrs.md` § 4.2) that surfaces resolved entries for removal review.

---

## 6. Errors

### 6.1 Errors raised by the gate at runtime

| Error class             | When raised                                                                                                      |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `ManifestNotFoundError` | `.spec-drift-gate.toml` missing; gate refuses to run (no implicit defaults — explicit configuration is required) |
| `ManifestSchemaError`   | manifest fails schema validation (typo in source root path, missing `[gate]` table, etc.)                        |
| `BaselineParseError`    | `.spec-drift-baseline.jsonl` is malformed JSON or missing required fields                                        |
| `SweepRuntimeError`     | An AST parse failure on a `.py` file in a source root; emits the file path + parse offset; aborts                |
| `MarkerSyntaxError`     | A `<!-- spec-assert: ... -->` directive has malformed syntax (e.g., missing `kind:` prefix)                      |
| `TenantRequiredError`   | n/a (reserved — gate runs without tenant context)                                                                |

All errors derive from `SpecDriftGateError(Exception)` for catchable hierarchy.

### 6.2 Findings (NOT errors)

Findings are the gate's intended output, not Python exceptions. They are emitted via the chosen `--format` (human / json / github). See § 7.4 of `01-analysis/02-requirements-and-adrs.md` for the exact output schemas.

---

## 7. Test Contract

### 7.1 Tier 1 (Unit)

`tests/spec_drift_gate/unit/`:

- `test_section_inference.py` — ADR-2 heading regex matches the canonical 5 section types; rejects `## Public Interface`-style drift.
- `test_marker_parsing.py` — `<!-- spec-assert -->` and `<!-- spec-assert-skip -->` round-trip; missing `reason:` raises `MarkerSyntaxError`.
- `test_ast_class_resolution.py` — single class, namespaced class, dotted method (`Class.method`).
- `test_getattr_resolution.py` — `__getattr__` map at `kailash_ml/__init__.py` style produces correct B1-class WARN when top-level export resolves to a different module than the spec asserts.
- `test_baseline_diff.py` — round-trip: generate baseline, mutate sweep result, confirm only-new entries surface.

### 7.2 Tier 2 (Integration)

`tests/spec_drift_gate/integration/`:

- `test_corpus_pass.py` — gate runs against full `specs/` corpus on a real checkout; ≤NFR-1 budget (30s); zero findings beyond baseline.
- `test_w65_crit1_replay.py` — fixture mirrors W6.5 round-1 FeatureStore draft; gate produces exactly 5 FR-4 findings (the 5 fabricated `*Error` classes).
- `test_w65_crit2_replay.py` — fixture mirrors the W6.5 fabricated `test_feature_store_wiring.py` reference; gate produces exactly 1 FR-7 finding.
- `test_pristine_baseline_capture.py` — fresh checkout, gate produces 36 baseline entries matching W5 audit count.

### 7.3 Self-test fixtures

`tests/fixtures/spec_drift_gate/` — deliberately-broken specs, one per FR. Names per FR-12 in the analysis doc. Fixtures are NOT under `specs/` (production sweep skips them); reachable only via the test harness.

### 7.4 Wiring test (per `rules/facade-manager-detection.md` MUST 1)

`tests/spec_drift_gate/integration/test_gate_wiring.py` — exercises the full surface: `python scripts/spec_drift_gate.py --format json` against a real fixture corpus + assertion that JSON shape matches the schema.

---

## 8. Examples

### 8.1 Editing a spec — success path

```markdown
## 3. Public API

### 3.1 `MLEngine.deploy(model, *, channels)`

Deploy a registered model through the canonical serving stack.
```

```bash
$ git commit -m "docs(specs): add MLEngine.deploy() to public API"
spec-drift-gate.................................................Passed
```

### 8.2 Editing a spec — false positive recovered via override

```markdown
## 5. Examples

<!-- spec-assert-skip: class:SentimentAnalysisAgent reason:"illustrative only" -->

Imagine a `SentimentAnalysisAgent` class…
```

### 8.3 W6.5 CRIT-1 reproduction

The 5 fabricated `*Error` classes in round-1 FeatureStore draft surface as 5 FR-4 findings:

```bash
$ python scripts/spec_drift_gate.py tests/fixtures/spec_drift_gate/w65_crit1_fabricated_errors.md
FAIL tests/fixtures/spec_drift_gate/w65_crit1_fabricated_errors.md:515 FR-4: class FeatureGroupNotFoundError — not found in src/kailash/ml/errors.py
FAIL tests/fixtures/spec_drift_gate/w65_crit1_fabricated_errors.md:515 FR-4: class FeatureVersionNotFoundError — not found in src/kailash/ml/errors.py
FAIL tests/fixtures/spec_drift_gate/w65_crit1_fabricated_errors.md:515 FR-4: class FeatureEvolutionError — not found in src/kailash/ml/errors.py
FAIL tests/fixtures/spec_drift_gate/w65_crit1_fabricated_errors.md:515 FR-4: class OnlineStoreUnavailableError — not found in src/kailash/ml/errors.py
FAIL tests/fixtures/spec_drift_gate/w65_crit1_fabricated_errors.md:515 FR-4: class CrossTenantReadError — not found in src/kailash/ml/errors.py
```

The reviewer's job in W6.5 round 1 was to do this manually. The gate does it in <1s.

---

## 9. Cross-References

- `workspaces/spec-drift-gate/briefs/01-product-brief.md` — vision, scope, success criteria
- `workspaces/spec-drift-gate/01-analysis/01-failure-points.md` — 28 failure modes, Top 5 day-1 critical, M2 deferrals
- `workspaces/spec-drift-gate/01-analysis/02-requirements-and-adrs.md` — 13 FRs + 5 NFRs + 7 ADRs + workplan
- `workspaces/spec-drift-gate/02-plans/01-implementation-plan.md` — 6-session sequencing
- `workspaces/spec-drift-gate/03-user-flows/01-developer-flow.md` — four-persona flow
- `.claude/skills/spec-compliance/SKILL.md` — protocol-level documentation; the gate productionizes this
- `.claude/skills/16-validation-patterns/orphan-audit-playbook.md` — sibling audit protocol
- `.claude/rules/specs-authority.md` § 5, § 5b, § 5c — rule basis the gate enforces
- `.claude/rules/orphan-detection.md` MUST 6 — `__all__` contract (FR-6 basis)
- `.claude/rules/zero-tolerance.md` Rule 3a — typed-guard basis for fix-hint format (ADR-6)
- `.claude/rules/git.md` § Pre-FIRST-Push CI Parity — informs ADR-4 CI design
- `.claude/rules/autonomous-execution.md` § Per-Session Capacity Budget — sharding basis (S1-S6)
- `.claude/rules/facade-manager-detection.md` MUST 1 — wiring-test discipline (FR-7 basis)
- `workspaces/portfolio-spec-audit/04-validate/W5-E2-findings.md` — 38 HIGH drift patterns
- `workspaces/portfolio-spec-audit/04-validate/W6.5-v2-draft-review.md` — CRIT-1 / CRIT-2 reproduction targets

---

## 10. Conformance Checklist

A v1.0-compliant Spec Drift Gate implementation MUST satisfy:

- [ ] CLI surface matches § 2.1 verbatim (flags + arguments)
- [ ] Pre-commit hook scoped to `specs/**.md` (§ 2.2)
- [ ] Manifest schema matches § 2.4 (TOML, `[gate]` table, `[[source_roots]]` array, `[errors_modules]`, `[exclusions]`)
- [ ] Section-context inference matches § 3.1 allowlist regex
- [ ] Override directives `<!-- spec-assert -->` + `<!-- spec-assert-skip -->` parse per § 3.2; `reason:` is REQUIRED on skip
- [ ] All 13 FRs implemented (§ 4 + analysis doc)
- [ ] Baseline format matches § 5.1 schema; entries carry `origin`, `added`, `ageout`
- [ ] `--refresh-baseline` writes `.spec-drift-resolved.jsonl` audit trail (§ 5.3)
- [ ] Anti-rot mechanisms in place (§ 5.4 — origin required, age-out, PR-template prompt, quarterly cleanup)
- [ ] Errors derive from `SpecDriftGateError` (§ 6.1)
- [ ] Tier 1 + Tier 2 self-tests pass (§ 7)
- [ ] W6.5 CRIT-1 + CRIT-2 reproductions pass (§ 7.2)
- [ ] Performance: <30s wall clock on full `specs/` corpus (NFR-1)
- [ ] False-positive rate <5% on the live corpus (NFR-2)
- [ ] Section-heading drift produces WARN, not silent skip (§ 3.3)

---

## 11. Deferred to M2 milestone

### 11.1 `__getattr__` lazy-resolution AST traversal

**Today (v1.0):** the gate detects when a top-level symbol resolves through a `__getattr__` map (B1-class WARN), but the AST traversal of the map body is shallow.
**M2:** full traversal with edge cases (nested maps, conditional resolution, runtime-injected attributes).
**Spec citation:** `01-failure-points.md` § B1.

### 11.2 Cross-SDK reference verification (Python ↔ Rust)

**Today (v1.0):** scoped to kailash-py source roots only. Cross-SDK assertions emit `WARN unverified — cross-SDK` with a sibling-spec link.
**M2:** single config (`workspaces/.cross-sdk-spec-drift.toml`) names both repos; one gate invocation runs against both source trees.
**Spec citation:** `01-failure-points.md` § E2; ADR-5 in analysis doc.

### 11.3 Reverse-index trigger (`.py` change → re-verify specs)

**Today (v1.0):** hook fires on `specs/**.md` change ONLY. A `.py` change that breaks a spec assertion is caught at the next spec edit, not immediately.
**M2:** persistent symbol index (cached); `.py` change triggers a quick targeted re-verification of any spec citing changed symbols.
**Spec citation:** `01-failure-points.md` § C3.

### 11.4 Executable spec annex format

**Today (v1.0):** assertions use the section-context heuristic + override directives (§ 3).
**M2:** structured `<!-- mech: ... -->` annex format (per brief line 30) becomes a synonym for `<!-- spec-assert: ... -->`. Migration is one-line per directive.
**Spec citation:** ADR-7 in analysis doc.

### 11.5 Pydantic / attrs / dataclass-like field detection

**Today (v1.0):** FR-5 handles `AnnAssign` (covers `dataclass`, `dataclass(frozen=True, slots=True)`).
**M2:** explicit Pydantic v2 `BaseModel` recognizer + attrs `class_decorator` recognizer.
**Spec citation:** open question Q9.2 in analysis doc.

### 11.6 Multi-package errors module primary-fallback

**Today (v1.0):** union scan across all `[errors_modules]` paths in manifest; class found in any → PASS.
**M2:** explicit primary-fallback ordering when ambiguity arises.
**Spec citation:** open question Q9.1 in analysis doc.

### 11.7 MOVE shim verification (was FR-9)

**Today (v1.0):** Not implemented. Spec sections containing `MOVE: old_path → new_path` claims are not mechanically verified.
**v1.1:** verify both paths resolve correctly via filesystem + AST checks. Roughly ~30 LOC; held back from v1.0 to keep S2 focused on core sweeps + the day-1-CRIT `__getattr__` resolution.
**Spec citation:** `02-requirements-and-adrs.md` FR-9 § 1 + redteam PLAN-CRIT-1 disposition.

### 11.8 Cross-spec sibling re-derivation advisory (was FR-10)

**Today (v1.0):** Not implemented. The discipline at `rules/specs-authority.md` § 5b (full-sibling re-derivation when a spec is edited) remains an agent-driven check at `/redteam` time.
**v1.1:** advisory WARN-emission listing every sibling spec that mentions edited spec's surface. Roughly ~50 LOC; deferred together with FR-9 for the same reason.
**Spec citation:** `02-requirements-and-adrs.md` FR-10 § 1 + redteam PLAN-CRIT-1 disposition.

---

## 12. Maintenance Notes

The gate is **defensive infrastructure** — it pays off most when it sits in the background and rarely fires. The day the gate starts firing 10× per PR is the day to investigate (bad authoring discipline, spec churn, manifest drift), not to relax the rules.

Per `01-failure-points.md` § D1 — D4, the long-term failure modes are sociological:

- D1 — gate becomes the new mock (lots of `spec-assert-skip` markers)
- D2 — specialists disable the gate when it blocks
- D3 — false-positive fatigue (even <5% × 72 specs)
- D4 — baseline rot

The mitigations are:

- Quarterly review of `grep -rn spec-assert-skip specs/` (audit overrides)
- PR description prompt for baseline edits
- 90-day baseline ageout
- Dogfood pass before each minor version release

The gate is a tool. It cannot replace `/redteam` (semantic alignment), `/codify` (knowledge capture), or human judgment about what to spec at all. It only enforces that what's written matches what's there.
