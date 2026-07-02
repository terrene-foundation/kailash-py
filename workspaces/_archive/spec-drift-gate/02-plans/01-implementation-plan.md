# Spec Drift Gate — Implementation Plan

**Date:** 2026-04-26
**Phase:** /analyze synthesis (input to /todos)
**Inputs:** `briefs/01-product-brief.md`, `01-analysis/01-failure-points.md` (28 failure modes), `01-analysis/02-requirements-and-adrs.md` (13 FRs + 5 NFRs + 7 ADRs)

This plan sequences the work; FR/ADR detail lives in `01-analysis/02-requirements-and-adrs.md`. Risk detail lives in `01-analysis/01-failure-points.md`. References here, not duplication.

## 1. Goal & exit gates

**Goal:** Mechanically prevent spec-vs-code drift at PR time. Replace the audit-after-the-fact loop (Wave 5 → Wave 6.5) with prevent-at-insertion. Catch the three patterns observed in Wave 5: overstated specs, fabricated typed exceptions, stale anchors.

**Exit gates (all required to declare gate "shipped"):**

1. `scripts/spec_drift_gate.py` runs in <30s on the full 72-spec corpus (NFR-1).
2. Run against `specs/ml-automl.md` v2.0.0 produces ZERO findings (the pristine baseline; ADR-2 verification command).
3. Run against `workspaces/portfolio-spec-audit/04-validate/W6.5-v2-draft-review.md`-cited fixtures (5 fabricated FeatureStore errors + 1 fabricated wiring test) produces ≥6 findings (the demo regression).
4. `.spec-drift-baseline.jsonl` captures the 36 pre-existing HIGHs from W5 audit; new violations beyond the baseline fail CI.
5. `.pre-commit-config.yaml` entry runs locally; pre-commit run --all-files passes on a fresh checkout.
6. (Proposed) `.github/workflows/spec-drift-gate.yml` opens a PR for user review per `feedback_no_auto_cicd.md`; not auto-merged.

## 2. Architectural keystone

ADR-2 (marker convention — section-context inference + `<!-- spec-assert: ... -->` overrides) is the load-bearing decision. **17 of 28 failure-mode mitigations collapse onto this one decision** (failure-points.md § Closing Notes). Every other ADR depends on it being right. Validate ADR-2 against the live spec corpus before touching ADR-3 (baseline) or ADR-4 (CI).

Section-name allowlist for sweep firing (ADR-2 § 3.2):

- `## Surface` / `## Construction` / `## Public API` → FR-1, FR-2, FR-5
- `## Errors` / `## Exceptions` → FR-4
- `## Test Contract` / `## Tests` / `## Tier .* Tests` → FR-7
- `## Migration` / `## Module Layout` w/ `MOVE` → FR-9
- `## Examples` / `## Quickstart` → FR-1, FR-2 smoke only

Sweeps are SILENT under: `## Scope`, `## Out of Scope`, `## Industry Parity`, `## Deferred to M2`, `## Cross-References`, `## Conformance Checklist`.

## 3. Sequencing — 6 sessions

Per `rules/autonomous-execution.md` § Per-Session Capacity Budget (≤500 LOC load-bearing logic / ≤5-10 invariants / ≤3-4 call-graph hops / describable in 3 sentences).

### S1 — Core sweep engine + marker parser (~400 LOC)

**Scope:** the 4 day-1-critical sweeps + ADR-2 marker discipline.

- FR-1 (class existence) with AST + cross-package resolution per ADR-1's manifest design
- FR-2 (function/method existence)
- FR-4 (error class in errors module) — drives W6.5 CRIT-1 detection
- FR-7 (test file existence) — drives W6.5 CRIT-2 detection
- ADR-2 marker parser (section-context + `<!-- spec-assert -->` + `<!-- spec-assert-skip -->`)
- CLI: `python scripts/spec_drift_gate.py [--format human|json] [<spec_path>...]`

**Invariants:** (1) section-context discrimination, (2) cross-package symbol resolution, (3) override directive precedence, (4) errors-module convention, (5) test-path resolution, (6) symbol-index cache (per failure-points C1.3 — cold-cache full-corpus sweep would exceed NFR-1 30s budget; cache keyed by `(file_path, mtime, sha)` is the structural defense).

**Verification:** sweep against `specs/ml-automl.md` v2 → 0 findings. Sweep against synthetic fixture mimicking W6.5 round-1 FeatureStore → exactly 6 findings.

**Day-1 critical risks addressed:** B1 (`__getattr__` re-exports — partially; full fix in S2), A3 (deferred sections — full fix), B6 (test file vs function — file-level only in S1).

### S2 — Manifest + remaining sweeps + `__getattr__` resolution (~250 LOC)

**Scope:** the manifest config + 4 secondary sweeps + the day-1 CRIT mitigation.

- `.spec-drift-gate.toml` manifest (per ADR-1 + ADR-5) declaring source roots, errors modules, exclusion patterns
- FR-3 (decorator application + count)
- FR-5 (field/attribute on dataclass) — `AnnAssign` recognizer
- FR-6 (`__all__` membership)
- FR-8 (workspace-artifact leak grep)
- **`__getattr__` resolution** — parse the lazy import map at `kailash_ml/__init__.py:580-622` style; emit B1-class WARN when a top-level export resolves to a different module than the spec asserts. (The W6.5 motivating example.)

**Invariants:** (1) manifest schema stability (canonical form is `specs/spec-drift-gate.md` § 2.4 — supersedes the divergent example in `02-requirements-and-adrs.md` ADR-5), (2) decorator expression matching, (3) `AnnAssign` field detection, (4) `__getattr__` AST traversal — emits **WARN-only** in v1.0; full hard-fail integration with FR-6 deferred to v1.1 per analyst Q9.3, (5) `__all__` consistency.

**Deferred to v1.1 (per redteam PLAN-CRIT-1 disposition):**

- ~~FR-9 (MOVE shim verification)~~ — see `specs/spec-drift-gate.md` § 11.7
- ~~FR-10 (cross-spec sibling re-derivation advisory)~~ — see `specs/spec-drift-gate.md` § 11.8

These two FRs are well-pseudocoded in the analysis doc but do not catch any of the W5/W6.5 patterns the v1.0 gate must address. Holding S2 at ~250 LOC keeps it focused on the day-1-CRIT (B1 `__getattr__` resolution) without budget pressure.

**Verification:** sweep against `kailash_ml/__init__.py` → flags the legacy-vs-canonical AutoMLEngine divergence as a B1-class WARN (matches W5-E2 F-E2-01 + W6.5 review HIGH-2).

### S3 — Baseline + grace logic + output formats (~200 LOC)

**Scope:** the baseline lifecycle, fix-hint discipline, dual output.

- `.spec-drift-baseline.jsonl` format per ADR-3 (one finding per line, sorted, citation field)
- FR-11 grace logic — diff sweep findings against baseline; only NEW findings fail
- ADR-6 fix-hint format — every failure produces a one-line typed instruction (`rules/zero-tolerance.md` Rule 3a pattern)
- FR-13 dual output — `--format human` for pre-commit / `--format json` for CI annotations / `--format github` for PR review markup
- Baseline rot mitigation: each entry cites an audit finding ID (`F-E2-NN`) AND records a 90-day age-out date

**Invariants:** (1) JSONL determinism (sorted, stable), (2) baseline entry schema, (3) grace-window semantics, (4) fix-hint grammar.

**Verification:** baseline diff round-trip — generate baseline, intentionally add new drift, confirm only the new entry fails.

### S4 — Self-test fixtures + Tier 2 corpus test (~300 LOC)

**Scope:** the gate has its own tests.

- `tests/fixtures/spec_drift_gate/` — deliberately-broken fixture specs, one per FR (per FR-12)
- Tier 1 unit tests — each FR sweep against fixture (deterministic)
- Tier 2 integration test — gate against full `specs/` corpus on a real checkout
- W6.5 reproduction test — fixture imitating round-1 FeatureStore draft → exactly 6 findings
- Performance regression test — full-corpus sweep < NFR-1 budget (30s)

**Invariants:** (1) fixture isolation (fixtures NOT under `specs/` — production sweep skips them), (2) deterministic fixtures, (3) reproducible CRIT-1 / CRIT-2 demo, (4) perf budget enforcement.

**Parallelizable with S5.**

### S5 — Pre-commit integration + baseline capture (~100 LOC)

**Scope:** live integration on the kailash-py repo.

- `.pre-commit-config.yaml` entry (ADR-4 — runs only on `specs/**.md` change)
- Capture pristine baseline: run gate against current `specs/` → 36 HIGHs from W5 → write `.spec-drift-baseline.jsonl`
- Add `.spec-drift-baseline.jsonl` to repo root, commit
- Local pre-commit run --all-files passes (NFR-1 verified end-to-end)

**Invariants:** (1) hook-scope correctness (specs/\*\*.md only — avoids C3 perf cost), (2) baseline correctness (every W5 HIGH lands as a baseline entry), (3) pre-commit auto-stash compatibility (per `rules/git.md` § Pre-Commit Hook Workarounds).

**Parallelizable with S4.**

### S6 — (Proposed) GH Actions workflow + skill doc update (~80 LOC)

**Scope:** the CI side + documentation.

- Author `.github/workflows/spec-drift-gate.yml` (per ADR-4 — only on PRs touching `specs/**.md`; runs `python scripts/spec_drift_gate.py --format github`)
- **Open as separate PR** per `feedback_no_auto_cicd.md` (cost implication: ~40 min/month at S6 ADR-4 estimate; user reviews before merge)
- Add new section to `.claude/skills/spec-compliance/SKILL.md` linking the executable form to the protocol-level documentation
- Add ADR-2 marker convention example to `skills/spec-compliance/SKILL.md`

**Invariants:** (1) workflow trigger scope matches local pre-commit scope (parity), (2) skill doc cross-link is bidirectional.

**Parallelizable with S5.**

## 4. Risks & mitigations (top 5 — full set in failure-points.md)

| Risk                                                         | Severity | Mitigation                                                                                                               | Owner shard                         |
| ------------------------------------------------------------ | -------- | ------------------------------------------------------------------------------------------------------------------------ | ----------------------------------- |
| **B1** — `__getattr__` re-exports silently match wrong class | CRIT     | AST traversal of `__getattr__` map; require fully-qualified import in spec assertions                                    | S2                                  |
| **A3** — Deferred-section symbols incorrectly flagged        | HIGH     | ADR-2 section-allowlist; gate emits scanned-section list per spec for review                                             | S1                                  |
| **B6** — Test file path resolved but test function absent    | HIGH     | S1: file-level check; later: AST-extract test function names                                                             | S1 (file-only); S2 (function-level) |
| **D3** — False-positive fatigue erodes trust                 | HIGH     | Pre-rollout dogfood against full 72-spec corpus; FP triage list before merging S5                                        | S4                                  |
| **D4** — Baseline rot — backlog never gets cleared           | HIGH     | Baseline entries cite F-E2-NN; 90-day age-out timestamp; PR description requires "delete entry vs. extend justification" | S3                                  |

## 5. Acceptance criteria → verification

| Brief criterion                           | Verification command (verifies it landed)                                                                                               |
| ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/spec_drift_gate.py` exists       | `test -x scripts/spec_drift_gate.py && python scripts/spec_drift_gate.py --version`                                                     |
| `.pre-commit-config.yaml` entry           | `grep -A3 spec_drift_gate .pre-commit-config.yaml` shows the hook                                                                       |
| Workflow PR proposed                      | `gh pr list --search "spec-drift-gate workflow"` returns one open PR                                                                    |
| Baseline captures 36 HIGHs                | `wc -l .spec-drift-baseline.jsonl` ≥ 36                                                                                                 |
| One-spec prototype clean                  | `python scripts/spec_drift_gate.py specs/ml-automl.md` → exit 0                                                                         |
| Documentation in spec-compliance skill    | `grep spec_drift_gate .claude/skills/spec-compliance/SKILL.md` shows reference                                                          |
| Tier 1 + Tier 2 self-tests                | `pytest tests/spec_drift_gate/ -v` → all PASS                                                                                           |
| W6.5 demo: deliberately-broken spec fails | `python scripts/spec_drift_gate.py tests/fixtures/spec_drift_gate/featurestore_round1_replay.md` → exactly 6 findings (5 FR-4 + 1 FR-7) |

## 6. Out of scope (re-confirmed from brief + reviewer)

- Rewriting prose / narrative quality (gate is mechanical only).
- Cross-SDK Python↔Rust drift (E2 — designed for, deferred to M2 per ADR-5).
- Spec generation from code (different workstream).
- Method-body content verification (`/redteam` Check 8 owns this).
- Orphan call-site detection (`rules/orphan-detection.md` MUST 1 stays at `/redteam`).
- Adversarial Unicode evasion (F1 — gate is hygiene, not security).

## 7. References

- `briefs/01-product-brief.md` — vision + 5 open questions (4 of 5 resolved by ADRs; one — multi-package errors module — surfaced as Q9.1 for S2)
- `01-analysis/01-failure-points.md` — 28 failure modes, Top 5, M2 deferrals
- `01-analysis/02-requirements-and-adrs.md` — 13 FRs, 5 NFRs, 7 ADRs, workplan
- `workspaces/portfolio-spec-audit/04-validate/W5-E2-findings.md` — drift patterns the gate catches
- `workspaces/portfolio-spec-audit/04-validate/W6.5-v2-draft-review.md` — CRIT-1 / CRIT-2 reproduction targets
- `.claude/rules/specs-authority.md` § 5, § 5b, § 5c — rule basis
- `.claude/rules/zero-tolerance.md` Rule 3a — fix-hint format basis
- `.claude/rules/autonomous-execution.md` § Per-Session Capacity Budget — sharding basis
- `.claude/skills/spec-compliance/SKILL.md` — protocol-level documentation; the gate productionizes this

## 8. Pre-/todos open items

These need user decision at /todos approval, not at /implement:

1. **Q9.1** (multi-package errors module convention) — primary-fallback ordering vs. union scan? Recommend: union scan in S1, primary-fallback added in S2 if needed.
2. **Q9.2** (Pydantic / attrs / frozen-dataclass detection) — FR-5 ships `AnnAssign`-only in v1.0 (covers `dataclass` + `dataclass(frozen=True, slots=True)`); Pydantic v2 / attrs detection deferred to v1.1. User confirms scope.
3. **Q9.3** (`__getattr__`-resolved exports as FR-6 scope) — Per redteam REQ-HIGH-1: S2 emits B1-class WARN when a top-level export resolves through `__getattr__` to a different module than the spec asserts. Hard-fail integration with FR-6 deferred to v1.1. User confirms WARN-only is the right v1.0 shape.
4. **Q9.4** (spec-prose-mention denylist for `## Out of Scope` references) — ADR-2 override directives cover this; no separate denylist needed. User confirms.
5. **GH Actions workflow as separate PR** — confirm OK to ship S6 as a follow-up PR (recommended) vs. bundle with S5.
6. **Baseline capture timing** — capture at S5 (recommended, after gate is functionally complete) vs. earlier (S3) and refine.
7. **Future evolution annex** — ADR-7 path is sketched. User should confirm M2 timing is acceptable (the brief deferred this; the analysts did too).
8. **FR-9 + FR-10 v1.1 deferral** — per redteam PLAN-CRIT-1, these are deferred to v1.1 to keep S2 focused. User confirms (alternative: extend S2 to ~330 LOC and ship in v1.0).
