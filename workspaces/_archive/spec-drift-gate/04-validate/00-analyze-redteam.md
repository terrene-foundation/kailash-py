# /analyze Red-Team Review — spec-drift-gate

**Date:** 2026-04-26
**Reviewer:** quality-reviewer (autonomous)
**Phase under review:** /analyze (5 outputs + 1 spec + 1 index update)
**Inputs reviewed:**

1. `workspaces/spec-drift-gate/briefs/01-product-brief.md` (input — not reviewed for verdict)
2. `workspaces/spec-drift-gate/01-analysis/01-failure-points.md` (output — verdict required)
3. `workspaces/spec-drift-gate/01-analysis/02-requirements-and-adrs.md` (output — verdict required)
4. `workspaces/spec-drift-gate/02-plans/01-implementation-plan.md` (output — verdict required)
5. `workspaces/spec-drift-gate/03-user-flows/01-developer-flow.md` (output — verdict required)
6. `specs/spec-drift-gate.md` (output — verdict required)
7. `specs/_index.md` (output — index update only; verified via mechanical sweep, not separate verdict)

---

## 0. Headline Verdict (5 docs)

| Document                                  | Verdict                     | Severity Distribution           |
| ----------------------------------------- | --------------------------- | ------------------------------- |
| `01-analysis/01-failure-points.md`        | **APPROVE WITH AMENDMENTS** | 0 CRIT · 2 HIGH · 3 MED · 2 LOW |
| `01-analysis/02-requirements-and-adrs.md` | **APPROVE WITH AMENDMENTS** | 0 CRIT · 3 HIGH · 4 MED · 2 LOW |
| `02-plans/01-implementation-plan.md`      | **APPROVE WITH AMENDMENTS** | 1 CRIT · 3 HIGH · 2 MED · 1 LOW |
| `03-user-flows/01-developer-flow.md`      | **APPROVE WITH AMENDMENTS** | 0 CRIT · 1 HIGH · 2 MED · 2 LOW |
| `specs/spec-drift-gate.md`                | **APPROVE WITH AMENDMENTS** | 0 CRIT · 2 HIGH · 4 MED · 2 LOW |

**Recommendation:** **SHIP TO `/todos` AFTER AMENDMENTS** — the single CRIT (FR-9 + FR-10 unassigned to any shard) is a 1-line fix in the plan; HIGHs are coverage / cross-reference inconsistencies addressable inline at `/todos` time. No round-2 analyst recall needed.

The brief's open-question / acceptance-criteria coverage is solid; the marker-convention keystone (ADR-2) is well-grounded; the 6-shard sequencing fits the autonomous capacity budget. The amendments below tighten cross-document consistency without rewriting any conclusion.

---

## 1. Mechanical Sweep Results (run BEFORE LLM judgment)

### M1 — Brief → Plan Shard Traceability

The brief (`briefs/01-product-brief.md`) has three accountability sections: § "Acceptance criteria for this workspace cycle" (lines 70-78, 8 bullets), § "Success criteria" (lines 53-60, 6 numbered items), § "Constraints" (lines 39-45, 5 items).

| Brief item                                                       | Source line     | Shard delivering it                | Status           |
| ---------------------------------------------------------------- | --------------- | ---------------------------------- | ---------------- | ------------- | --- | --------------------- | --- |
| `scripts/spec_drift_gate.py` implementing 4 sweeps               | 71              | S1 + S2                            | OK               |
| `.pre-commit-config.yaml` entry on `specs/**.md`                 | 72              | S5                                 | OK               |
| `.github/workflows/spec-drift-gate.yml` (proposed)               | 73              | S6                                 | OK               |
| `.spec-drift-baseline.json` (or equivalent) with 36-HIGH backlog | 74              | S5                                 | OK (jsonl)       |
| One-spec prototype (likely `ml-automl.md`)                       | 75              | S1 verification (gate § 1.5/§ 5.5) | OK               |
| Documentation in `skills/spec-compliance/SKILL.md`               | 76              | S6                                 | OK               |
| Tier 1 + Tier 2 tests for the gate itself                        | 77              | S4                                 | OK               |
| Demonstration: deliberately-broken spec edit fails CI            | 78              | S4 + S6                            | OK               |
| Coverage success: every `class.\*Error                           | class \w+Engine | class \w+Store                     | class \w+Manager | def [a-z]\w+` | 55  | FR-1, FR-2, FR-4 → S1 | OK  |
| FP rate <5%                                                      | 56              | NFR-2; ADR-2                       | OK               |
| Performance: <30s wall clock                                     | 57              | NFR-1; tested in S4                | OK               |
| One-time baseline                                                | 58              | S5 (FR-11 in S3)                   | OK               |
| CI integration: PR fails the spec-drift-gate job                 | 59              | S6                                 | OK               |
| Demonstrable on real PR: simulate Wave 6.5 CRIT-1                | 60              | S4 (test_w65_crit1_replay)         | OK               |
| Constraint: stdlib `ast`, `grep`/`ripgrep`, `pathlib`; <30s      | 41              | NFR-1; ADR-3 forbids YAML for this | OK               |
| Constraint: <2 weeks blocking velocity (one-time grace)          | 42              | FR-11 / S3                         | OK               |
| Constraint: gate reports + blocks; no auto-mutate                | 43              | ADR-6 (fix-hint, no auto-fix)      | OK               |
| Constraint: respect `feedback_no_auto_cicd.md`                   | 44              | S6 explicit "open as separate PR"  | OK               |
| Constraint: cross-SDK alignment, kailash-py first                | 45              | NFR-4; ADR-5                       | OK               |

**Result:** All brief acceptance / success / constraint items map to a shard or an ADR. **No M1 findings.**

### M2 — FR Coverage in Plan (FR-1..FR-13 across S1-S6)

The analysis declares **13 FRs** (FR-1 through FR-13, with FR-3a as a sub-clause of FR-3). The plan's shard descriptions explicitly mention:

| FR        | Mentioned in plan?                            | Shard owning it    |
| --------- | --------------------------------------------- | ------------------ |
| FR-1      | YES (`02-plans/01-implementation-plan.md:44`) | S1                 |
| FR-2      | YES (`...plan.md:45`)                         | S1                 |
| FR-3      | YES (`...plan.md:62`)                         | S2                 |
| FR-4      | YES (`...plan.md:46`)                         | S1                 |
| FR-5      | YES (`...plan.md:63`)                         | S2                 |
| FR-6      | YES (`...plan.md:64`)                         | S2                 |
| FR-7      | YES (`...plan.md:47`)                         | S1                 |
| FR-8      | YES (`...plan.md:65`)                         | S2                 |
| **FR-9**  | **NO — not named in any shard**               | **MISSING (CRIT)** |
| **FR-10** | **NO — not named in any shard**               | **MISSING (CRIT)** |
| FR-11     | YES (`...plan.md:77`)                         | S3                 |
| FR-12     | YES (`...plan.md:90`)                         | S4                 |
| FR-13     | YES (`...plan.md:79`)                         | S3                 |

**Result:** **2 FRs are unassigned to any shard — FR-9 (MOVE shim verification) and FR-10 (cross-spec sibling re-derivation advisory).** This is the headline CRIT. See finding **PLAN-CRIT-1** below.

The new spec at `specs/spec-drift-gate.md:175-178` enumerates FR-9 and FR-10 in the Sweep Contracts table — so the spec assumes they ship, but the plan provides no shard. This is a spec-vs-plan inconsistency the orchestrator at `/todos` time will surface as either "ship FR-9 + FR-10 in S2 (re-cap S2 LOC budget)" or "drop FR-9 + FR-10 to v1.1 (and edit § 1.1 of the spec)".

### M3 — ADR Consistency (analysis ↔ spec)

The analysis declares **7 ADRs** (ADR-1..ADR-7). The spec cites by number:

| ADR   | Spec cite location                                                             | Cited in analysis at | Content match?                                                                                                                                     |
| ----- | ------------------------------------------------------------------------------ | -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| ADR-1 | not cited explicitly                                                           | analysis § 3.1       | n/a                                                                                                                                                |
| ADR-2 | spec § 3 ("Marker Convention (the architectural keystone)"), § 3.1, § 3.2      | analysis § 3.2       | OK — section-allowlist regex matches verbatim (rows match)                                                                                         |
| ADR-3 | spec § 5 ("Baseline Lifecycle"), § 5.4, § 5.4                                  | analysis § 3.3       | OK                                                                                                                                                 |
| ADR-4 | spec § 2.3 (workflow PROPOSED), § 2.2 (hook scope)                             | analysis § 3.4       | OK                                                                                                                                                 |
| ADR-5 | spec § 2.4 (manifest schema)                                                   | analysis § 3.5       | OK — TOML schema shape matches; § 2.4 uses `[[source_roots]]` array, § 3.5 declares `[gate.errors_modules]` table; minor representation difference |
| ADR-6 | spec § "Conformance Checklist" + § 6 cite ADR-6 implicitly via fix-hint format | analysis § 3.6       | partially — the spec does NOT verbatim quote ADR-6 nor render the `(a)/(b)/(c)` triad. See **SPEC-MED-2**.                                         |
| ADR-7 | spec § 11.4 cites ADR-7 by name                                                | analysis § 3.7       | OK — both forms reserved, `mech:` as alias                                                                                                         |

**Result:** ADR-1, ADR-6 not cited by name in the spec; ADR-5 manifest schema has minor representation drift (TOML array-of-tables vs nested table). See **SPEC-HIGH-1**, **SPEC-MED-2**, **SPEC-MED-3**.

### M4 — Top-5 Failure Mode Coverage in Plan § 4 (Risks & mitigations)

failure-points.md § "Top 5 Must-Not-Fail-On-Day-1" (lines 416-428) lists:

1. **B1** — `__getattr__` re-exports
2. **A3** — Deferred-section references
3. **B6** — Test file existence vs FUNCTION existence
4. **D3** — False-positive fatigue
5. **D4** — Baseline rot

Plan § 4 (lines 128-134) covers risks via a 5-row table:

| failure-points.md Top-5 | Plan § 4 row                            | Coverage                                        |
| ----------------------- | --------------------------------------- | ----------------------------------------------- |
| **B1**                  | Row 1 (`B1 — __getattr__ re-exports`)   | OK — S2                                         |
| **A3**                  | Row 2 (`A3 — Deferred-section symbols`) | OK — S1                                         |
| **B6**                  | Row 3 (`B6 — Test file path resolved`)  | OK — S1+S2 (file-only, function-level deferred) |
| **D3**                  | Row 4 (`D3 — False-positive fatigue`)   | OK — S4                                         |
| **D4**                  | Row 5 (`D4 — Baseline rot`)             | OK — S3                                         |

**Result:** All 5 day-1-critical failure modes have a mitigation row + owner shard in the plan. **No M4 findings.**

However: **B6 partially deferred to function-level in S2 is INCONSISTENT with its Top-5 ranking.** The Top-5 entry (line 424) says "Day-1 gate MUST resolve test paths via `pathlib` AND verify `pytest --collect-only -q` shows the function (or AST-extracts the function name)." The plan deliberately splits this into "S1 file-only; S2 function-level". The user-flow doc (line 174-175) only shows file-level FR-7 ("absent on disk at" — file). Function-level test detection IS NOT in S1 owner-shard. This is documented but contradicts the failure-points "MUST" framing. See **PLAN-HIGH-2**.

### M5 — Plan Shard LOC Sum (claimed ~1330 LOC)

Plan § 3 declares per-shard LOC estimates: S1=400, S2=250, S3=200, S4=300, S5=100, S6=80.

Sum = 400 + 250 + 200 + 300 + 100 + 80 = **1330 LOC** ✓

Analysis doc § 7.1 (line 1284) claims "Total: ~1330 LOC across 6 sessions."

**Result:** Sum matches claim. **No M5 findings.**

### M6 — Spec Section Count (§ 1-12 per analysis)

The new spec `specs/spec-drift-gate.md` headings (verified via grep):

```
## 1. Purpose & Scope
## 2. Surface
## 3. Marker Convention (the architectural keystone)
## 4. Sweep Contracts
## 5. Baseline Lifecycle
## 6. Errors
## 7. Test Contract
## 8. Examples
## 9. Cross-References
## 10. Conformance Checklist
## 11. Deferred to M2 milestone
## 12. Maintenance Notes
```

Twelve top-level sections. ✓

The user task description claims "spec MUST have § 1-12 per the analysis. Confirm § Cross-References lines up with analysis doc § 10."

- Spec § 9 = Cross-References
- Analysis § 10 = Cross-References

The analysis doc's § 10 has 13 cross-reference bullets. The spec's § 9 has 16 bullets. The spec adds: workspace artifact links (briefs, failure-points, requirements, plan, user-flow), portfolio-spec-audit links (W5/W6.5), `facade-manager-detection.md`, `autonomous-execution.md`. The spec § 9 strictly subsumes analysis § 10 + adds workspace-back-pointers. **Acceptable expansion** — the spec is the durable artifact and benefits from full back-traceability.

**Result:** Spec section count matches analysis § 10's enumeration philosophy. No M6 findings.

### M7 — Open-Question Handling (4 questions Q9.1-Q9.4)

Analysis doc § 9 (lines 1330-1342) lists exactly 4 open questions: Q9.1 (multi-package errors module), Q9.2 (Pydantic vs dataclass), Q9.3 (versioned `__all__` re-exports / `__getattr__`), Q9.4 (spec-prose-mention denylist).

Plan § 8 ("Pre-/todos open items", lines 170-177) lists 4 items, but only **1 of 4** is a Q9.X question:

| Plan § 8 item                  | Maps to                                    |
| ------------------------------ | ------------------------------------------ |
| 1. Multi-package errors module | **Q9.1** ✓                                 |
| 2. GH Actions workflow as PR   | NOT a Q9 question (process)                |
| 3. Baseline capture timing     | NOT a Q9 question (sequencing)             |
| 4. Future evolution annex      | Touches Q9.X via ADR-7 (but not Q9.1-Q9.4) |

**Q9.2 (Pydantic / dataclass), Q9.3 (`__getattr__` resolution), Q9.4 (spec-prose-mention denylist) are NOT surfaced in the plan's pre-/todos open items.** The plan does mention `__getattr__` resolution as part of S2's scope (lines 66-67) — but Q9.3 explicitly recommends "ship FR-6 as `__all__`-only for v1.0; document `__getattr__`-resolved exports as a known gap; add in v1.1 with a regression test", which conflicts with the plan's S2 commitment.

**Result:** **3 of 4 analyst open questions are absent from the plan's open-items section.** See **PLAN-HIGH-3**.

---

## 2. Per-Document Findings

### 2.1 `01-analysis/01-failure-points.md` — APPROVE WITH AMENDMENTS

#### FP-HIGH-1: Top-5 D3 mitigation hard-codes "70 W5-E2 findings" without source

- **Location:** `01-failure-points.md:300` and `01-failure-points.md:413` ("Empirically the W5-E2 audit found ~70 findings across 11 specs")
- **What's wrong:** "~70 findings" is asserted twice as the calibration target for FPR; the brief / W5-E2 cite "38 HIGHs" (brief line 4) and the analysis doc declares "36-HIGH backlog" (analysis line 1322 + plan line 18). The 70-vs-38-vs-36 inconsistency creates confusion at /todos time when a reviewer asks "which number does the gate target?"
- **Recommended action:** Either cite the W5-E2 file's exact finding count (`grep -c '^### F-E2-' workspaces/portfolio-spec-audit/04-validate/W5-E2-findings.md`) and reconcile, OR replace "~70" with "the F-E2-NN enumerated set" and let the reader resolve by counting. Specifically reconcile in `01-failure-points.md:300` and `01-failure-points.md:413`.

#### FP-HIGH-2: `__all__` rule cite is misnumbered

- **Location:** `01-failure-points.md:469` ("`rules/orphan-detection.md` MUST 6 + `skills/16-validation-patterns/orphan-audit-playbook.md` § 6")
- **What's wrong:** The PR #523 / PR #529 evidence at the top of `rules/orphan-detection.md` Rule 6 shows kailash-ml 0.11.0 as the origin. The cite is correct, but the analysis doc § "Cross-References" calls this "`rules/orphan-detection.md` MUST 6" while the requirements doc § 1 FR-6 calls the same rule "`rules/orphan-detection.md` MUST 6 (eager-imports-without-`__all__`-entry)". Both correct; the failure-points doc just lacks the "(converse direction)" framing the requirements doc provides at line 190.
- **Recommended action:** Add to `01-failure-points.md:469` parenthetical "(spec→`__all__` is FR-6's direction; `__init__.py`→`__all__` is rule MUST 6's direction)" so the cross-reference is unambiguous.

#### FP-MED-1: Spec count claim ambiguity (72 specs)

- **Location:** `01-failure-points.md:8` ("`Glob specs/**/*.md` → 72 entries"), repeated at line 208 and line 220 and line 230 ("72 specs × 50ms")
- **What's wrong:** The Glob result is asserted but the analysis doc and plan both say "the full 72-spec corpus" without re-verification. The spec corpus changes — at the time of `/implement`, the count may differ. Failure-point analysis lasted across multiple agent turns; if the corpus shifted between, the budget calculation diverges.
- **Recommended action:** Replace the literal `72` constant with `"~72 specs (verify with Glob at /implement time)"` in `01-failure-points.md:8`, `:208`, `:220`. Defensive against drift.

#### FP-MED-2: Citation density in § B1 mitigation strategies makes proof-reading hard

- **Location:** `01-failure-points.md:97-107` (B1 mitigation, multiple `:NNN` citations + `__getattr__` + `automl/engine.py:410`)
- **What's wrong:** The body cites `kailash_ml/__init__.py:580-622`, `:593`, `automl/engine.py:410`, `engines/automl_engine.py:425` in quick succession. The `:593` cite is line-specific but the analysis doc later says "`kailash_ml/__init__.py:580-622`-style" (range) — small drift. Reviewer cannot verify all 4 lines without opening the source file.
- **Recommended action:** Consolidate to `kailash_ml/__init__.py` (and reference the `__getattr__` map without specific line numbers, since W6.5 round-2 is post-v2 and lines may have shifted). The verification command in plan § 5 already calls this out at "verify in source"-level.

#### FP-MED-3: § F1 mitigation invokes "NFKC" without defining what the gate does on detection

- **Location:** `01-failure-points.md:384-386` ("Apply Unicode normalization (NFKC) before regex/AST extraction; reject specs with non-printable characters in identifier-position contexts")
- **What's wrong:** The "reject specs with non-printable characters" line introduces a NEW behavior (gate refuses to process) that's not anchored in any FR or ADR. F1 is explicitly Defer-to-M2 (line 444). Mixing M2-deferred behavior into a day-1 mitigation paragraph creates ambiguity about whether NFKC normalization is in v1.0 or v1.1.
- **Recommended action:** Move the "reject specs with non-printable characters" sentence under § "Defer to M2" (line 432-) with explicit "F1 → M2" framing. Day-1 stays "we don't address F1; rely on /redteam."

#### FP-LOW-1: Subhead "Defer to M2 / Explicit Non-Goals" is asymmetric with the spec's "11. Deferred to M2 milestone"

- **Location:** `01-failure-points.md:432`
- **What's wrong:** The spec uses "Deferred to M2 milestone" (12 char prefix). The failure-points doc uses "Defer to M2 / Explicit Non-Goals". Same intent, different wording — minor. Affects grep consistency for cross-document discovery.
- **Recommended action:** Rename to "Deferred to M2 (Explicit Non-Goals)" for parity with `specs/spec-drift-gate.md:377`. Optional.

#### FP-LOW-2: "70 W5-E2 findings" appears 4 times as a load-bearing number

- **Location:** `01-failure-points.md:300, :315, :413, :470` (~)
- **What's wrong:** Same root cause as FP-HIGH-1 — repeated number, never sourced. This is a calibration anchor for NFR-2 (FPR<5%); if it's wrong, the FPR estimate is wrong.
- **Recommended action:** Subsumed under FP-HIGH-1.

---

### 2.2 `01-analysis/02-requirements-and-adrs.md` — APPROVE WITH AMENDMENTS

#### REQ-HIGH-1: FR-6 (`__all__` membership) does NOT cover `__getattr__`-resolved exports

- **Location:** `02-requirements-and-adrs.md:188-211` (FR-6 spec)
- **What's wrong:** FR-6 reads `__all__` from AST. Per failure-points B1 (CRIT-rated), `kailash_ml/__init__.py` uses `__getattr__`-based resolution where `__all__` may NOT contain the symbol but `__getattr__` resolves it dynamically. FR-6 alone misses this — it's the analyst's own Q9.3 concern (line 1338) recommending "ship FR-6 as `__all__`-only for v1.0; add `__getattr__` in v1.1." But the plan's S2 (line 66-67) commits to `__getattr__` resolution at v1.0 ("emit B1-class WARN when a top-level export resolves to a different module than the spec asserts"). FR-6 spec doesn't reflect the WARN-emission path; the spec at § 4 sweep table line 173 (`FR-6 | __all__ membership | PR #523/#529...`) doesn't mention `__getattr__`.
- **Recommended action:** Either (a) extend FR-6's pseudocode to scan `__getattr__` body when present and resolve the asserted symbol's module, OR (b) add a new **FR-6a — `__getattr__` lazy-resolution check** as a sub-clause. The plan § 4 risk table calls this out explicitly via the B1 row, but the FR enumeration doesn't have a clean home for the WARN.

#### REQ-HIGH-2: ADR-5 manifest example uses TWO different schemas

- **Location:** `02-requirements-and-adrs.md:719-749` (single `[gate]` table) vs. `specs/spec-drift-gate.md:87-112` (`[gate]` + `[[source_roots]]` array-of-tables)
- **What's wrong:** Analysis doc ADR-5 declares a single nested `[gate.section_sweeps]`, `[gate.errors_modules]`, etc. structure. The new spec at § 2.4 declares a different shape: top-level `[gate]`, then `[[source_roots]]` array-of-tables, top-level `[errors_modules]`. The differences are concrete:
  - Analysis: `source_roots = ["src/kailash", "packages"]` (list of strings)
  - Spec: `[[source_roots]]\npackage = "kailash-core"\npath = "src/kailash"` (array of tables with named fields)
  - Analysis: `[gate.errors_modules]\n"kailash-ml" = "src/kailash/ml/errors.py"` (dotted-key form)
  - Spec: `[errors_modules]\noverrides = [{ package = "kailash-pact", path = "..." }]` (with `default` and `overrides`)
- **Recommended action:** The two manifests MUST be byte-identical (or one is the canonical form and the other cites it). Recommend the spec wins (it's the durable artifact); revise `02-requirements-and-adrs.md:719-749` ADR-5 to mirror `specs/spec-drift-gate.md:87-112` verbatim. Or vice versa — pick one and reconcile in same edit. **This is the most likely source of /implement confusion.**

#### REQ-HIGH-3: NFR-1 budget calculation appears optimistic

- **Location:** `02-requirements-and-adrs.md:392-403` (NFR-1)
- **What's wrong:** The budget is "<30s wall clock on full `specs/` set on a developer laptop." The analysis at `01-failure-points.md:208-230` computes 5K-7K assertions × ~50ms-cached / file = "10-15s with caching, 60-90s without." 60-90s without caching exceeds NFR-1's 30s budget. The mitigation (symbol-index cache) is in C1.3 but is NOT explicitly an FR — meaning S1's "core sweep engine" might not include the cache, since the cache is a performance lever only.
- **Recommended action:** Add an explicit **NFR-1.1 — Symbol-index cache requirement** OR include "implements C1.3 symbol-index cache" as an explicit S1 invariant (`02-plans/01-implementation-plan.md:51-52` invariants list). Without this, S1 ships at "30s+ first-cold-cache run" and the gate trips its own NFR.

#### REQ-MED-1: FR-3 vs FR-3a confusion in numbering

- **Location:** `02-requirements-and-adrs.md:87-117` (FR-3) vs `02-requirements-and-adrs.md:119-121` (FR-3a)
- **What's wrong:** FR-3a is described as "Decorator count assertion (advisory)" — but it's not in the FR-1..FR-13 enumeration that S1-S6 sequence against, and not a separate row in the spec § 4 sweep contracts table. Counts of "13 FRs" (analysis line 1311) include FR-3a as part of FR-3, but the plan only lists FR-3 in S2 (line 62). If FR-3a needs separate code paths (decorator definition vs application count), the plan should call it out.
- **Recommended action:** Either fold FR-3a into FR-3's pseudocode (treat count check as part of FR-3) OR promote FR-3a to FR-14 with its own row in the spec sweep table (and add to plan's S2 invariants).

#### REQ-MED-2: FR-9 (MOVE shim) and FR-10 (sibling re-derivation) lack shard ownership

- **Location:** `02-requirements-and-adrs.md:267-322` (FR-9 + FR-10)
- **What's wrong:** Same root issue as M2 mechanical sweep + PLAN-CRIT-1. The requirements describe FR-9 + FR-10 in detail (~50 LOC of pseudocode each) but the workplan at § 7.1 (table at line 1276) does not assign LOC to them. The total "~1330" claim does not include FR-9 / FR-10 LOC. If they ship at v1.0, plan total is more like ~1500 LOC.
- **Recommended action:** Decide at /todos: ship FR-9 + FR-10 in v1.0 (re-cap S2 to include them, ~+150 LOC = S2 at ~400 LOC, still within capacity budget) OR defer both to v1.1 (and edit § 1.1 of the spec).

#### REQ-MED-3: NFR-4 (Portability) is internally inconsistent on script vs manifest approach

- **Location:** `02-requirements-and-adrs.md:423-431` (NFR-4) vs `:716-717` (ADR-5 decision)
- **What's wrong:** NFR-4 line 425-431 lists "Single repo invocation" (one script + per-repo manifest) AS A POSSIBLE OPTION, then ADR-5 line 716-717 says "Two scripts with shared manifest schema" is THE decision. NFR-4's option-listing reads as if both options remain on the table; ADR-5 closes that. NFR-4 should be normative (which approach the gate adopts) — it currently reads descriptive.
- **Recommended action:** Rewrite NFR-4 first paragraph to: "Per ADR-5, kailash-py ships its own gate script; kailash-rs ships a sibling Rust port using the same manifest schema. Single-invocation cross-SDK is M2."

#### REQ-MED-4: Spec output examples in § 4.4 contradict ADR-6's `(a)/(b)/(c)` triad

- **Location:** `02-requirements-and-adrs.md:1078-1097` (output example) vs `:783-805` (ADR-6 decision)
- **What's wrong:** ADR-6 (line 786-787) declares the canonical output format as `FAIL <FR-N>: <asserted_symbol> cited at <spec_path>:<line_no> <action_verb> <where>` followed by `→ fix: (a) ... (b) ... (c)`. The output example at line 1083-1088 omits the `(a)/(b)/(c)` triad on most lines — only line 1083 has `→ fix: (a) add the class, (b) fix the cite, OR (c) move to '## Deferred to M2'`; subsequent lines elide it as `... (3 more FR-4 failures elided)`. Inconsistent — either every failure shows the triad or none do.
- **Recommended action:** Either expand the elided lines or document `(a)/(b)/(c)` as "indented under each FAIL line; elided in this example for brevity" with explicit `[ELIDED]` annotation.

#### REQ-LOW-1: § 8 "Counts" claim mismatch with concrete pseudocode count

- **Location:** `02-requirements-and-adrs.md:1314` ("Concrete pseudocode sweeps: 10 (FR-1 through FR-9 + FR-11 baseline diff)")
- **What's wrong:** That's 9 pseudocode blocks (FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7, FR-8, FR-9) + FR-11 baseline diff = 10. But FR-3a also has pseudocode (line 96-117 IS FR-3 pseudocode but FR-3a is described as "FR-3 returns the application count and the gate compares against the asserted N" — no separate pseudocode block). Count is correct but the parenthetical "FR-1 through FR-9 + FR-11" suggests FR-10 lacks pseudocode (correct — FR-10 has pseudocode at line 304-318, contradicting). Actually counted: FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7, FR-8, FR-9, FR-10, FR-11 — that's 11 pseudocode blocks if you include FR-10. The "10" claim is undercounting by 1.
- **Recommended action:** Re-count or change to "10-11 (depending on whether FR-10 advisory counts)".

#### REQ-LOW-2: Multiple references to `01-failure-points.md` use mixed formatting

- **Location:** Throughout the requirements doc
- **What's wrong:** Cross-references to the sibling failure-points doc use mixed forms: "see `01-failure-points.md` § B1", "per `01-failure-points.md`'s § C1.3", "(failure-points.md § Closing Notes)". The omitted-leading-`01-` form is fine when in same workspace; consistency aids grep.
- **Recommended action:** Pick one canonical form (`01-failure-points.md § X`) and replace alternates. Optional.

---

### 2.3 `02-plans/01-implementation-plan.md` — APPROVE WITH AMENDMENTS

#### PLAN-CRIT-1: FR-9 (MOVE shim) + FR-10 (sibling re-derivation) unassigned to any shard

- **Location:** `01-implementation-plan.md:36-124` (S1-S6 enumeration)
- **What's wrong:** Per M2 sweep above. FR-9 and FR-10 are declared in `02-requirements-and-adrs.md:267-322` and listed in `specs/spec-drift-gate.md:175-178` Sweep Contracts table (FR-9 = MOVE shim, FR-10 = Sibling re-derivation). The plan enumerates S2 as covering FR-3, FR-5, FR-6, FR-8 + the `__getattr__` resolution; FR-9 / FR-10 do not appear in any shard description. The work IS pseudocoded in the requirements doc (~30 LOC each); they need owner shards.
- **Recommended action:** Insert into S2 invariants (line 68-70):
  - "(6) MOVE shim verification — FR-9 (~30 LOC)"
  - "(7) Sibling re-derivation advisory — FR-10 (~50 LOC)"
    And revise S2 LOC estimate from 250 → ~330 LOC. Total plan moves from ~1330 → ~1410 LOC, still within autonomous budget. Alternatively defer FR-9 + FR-10 to v1.1, and edit `specs/spec-drift-gate.md` § 1.1 to remove items 9 + 10.

#### PLAN-HIGH-1: Plan § 4 risk table mitigation for B6 disagrees with failure-points Top-5 ranking

- **Location:** `01-implementation-plan.md:132` ("S1: file-level check; later: AST-extract test function names")
- **What's wrong:** Per M4 sweep above. failure-points.md Top-5 entry 3 (line 424) says day-1 gate MUST resolve test paths via `pathlib` AND verify function via `pytest --collect-only` OR AST. The plan says "S1: file-only; S2: function-level" which is a partial fulfillment of the MUST. Either the failure-points "MUST" is over-strong or the plan's split is acceptable; reconcile in one document.
- **Recommended action:** Either (a) move function-level FR-7 work to S1 invariants list ("file + function name AST extraction is single shard"), or (b) edit `01-failure-points.md:424` to read "Day-1 file-existence; function-level deferred to ADR-7-style M2 enhancement". The user-flow doc only shows file-level (line 174-175) — so acceptable to soften the failure-points framing.

#### PLAN-HIGH-2: § 8 "Pre-/todos open items" only surfaces 1 of 4 analyst Q9 questions

- **Location:** `01-implementation-plan.md:170-177`
- **What's wrong:** Per M7 sweep. Q9.2 (Pydantic / dataclass), Q9.3 (`__getattr__` resolution policy), Q9.4 (spec-prose-mention denylist) are NOT in the plan's open-items list. Q9.1 IS (item 1). The plan adds 3 items that are not Q9.X (workflow PR timing, baseline capture timing, ADR-7 timing) — these are sequencing concerns, not unresolved questions. The user at /todos approval will not see Q9.2-Q9.4 unless they open the requirements doc.
- **Recommended action:** Append items 5-7 to plan § 8:
  - "5. **Q9.2** — Pydantic / attrs / frozen-dataclass detection. Recommend: AnnAssign-only in v1.0; expand in v1.1."
  - "6. **Q9.3** — `__getattr__`-resolved exports as FR-6 scope. Recommend: WARN-emission in v1.0 per S2 (line 67); full traversal v1.1."
  - "7. **Q9.4** — Spec-prose-mention denylist for narrative `## Out of Scope` references. Recommend: ADR-2 overrides cover this; document in skill."

#### PLAN-HIGH-3: Plan § 5 Acceptance criteria table missing a row for one brief item

- **Location:** `01-implementation-plan.md:138-148`
- **What's wrong:** The brief lists 8 acceptance items (lines 70-78). The plan § 5 acceptance criteria table has 8 rows, but row 7 ("Tier 1 + Tier 2 self-tests") and row 8 ("W6.5 demo: deliberately-broken spec fails") arguably collapse `## tier 1 + tier 2 tests for the gate itself` (brief 77) with `Demonstration: a deliberately-broken spec edit fails CI; the realignment passes` (brief 78). The brief explicitly separates these — the gate's OWN tests vs. the demo regression.
- **Recommended action:** Split the table into 8 distinct rows aligning 1:1 with brief lines 71-78. Currently 7 of 8 are clearly mapped; the demo regression row (brief line 78) needs the "second push (after fix) passes" verification command.

#### PLAN-MED-1: S6 cost-implication footnote uses "~40 min/month"; ADR-4 uses "20-40 min/month"

- **Location:** `01-implementation-plan.md:118` ("~40 min/month") vs `02-requirements-and-adrs.md:652` ("20-40 min/month")
- **What's wrong:** Cost figure mismatch. Plan rounds up; analysis doc gives a range. At /implement time the user reviews cost; mismatched figures undermine the analyst's verification work.
- **Recommended action:** Reconcile to "20-40 min/month at typical load" in the plan. Optional but tidy.

#### PLAN-MED-2: § 2 "Architectural keystone" phrasing duplicated in spec § 3

- **Location:** `01-implementation-plan.md:23-24` and `specs/spec-drift-gate.md:118`
- **What's wrong:** Both reference "17 of 28 failure-mode mitigations collapse onto this one decision (failure-points.md § Closing Notes)" — same claim, 2 documents. If the count changes, both must update. Single-source the claim.
- **Recommended action:** Either omit the count from one (recommend the plan, since it's the workspace-process artifact) or add a "see specs/spec-drift-gate.md § 3 for the canonical statement" footer in the plan.

#### PLAN-LOW-1: Plan does not state whether S4-S5-S6 parallelization is "wave-of-3" safe

- **Location:** `01-implementation-plan.md:98, :111, :122` (parallelizable claims)
- **What's wrong:** The plan claims S4 || S5, S5 || S6. Three Opus shards in parallel? Per `worktree-isolation.md` Rule 4, waves of ≤3 concurrent worktree agents is the safe limit. Claim is consistent — but the plan should state explicitly "wave of 3" so the orchestrator at /implement does not over-launch.
- **Recommended action:** Add to S4 / S5 / S6 description: "Launches concurrently as a wave of 3 per `worktree-isolation.md` Rule 4." Optional.

---

### 2.4 `03-user-flows/01-developer-flow.md` — APPROVE WITH AMENDMENTS

#### FLOW-HIGH-1: Persona 4 references `kailash_ml/__init__.py:593` line number that may not exist

- **Location:** `01-developer-flow.md:128` ("flip kailash_ml/**init**.py:593 map entry; or document deferral")
- **What's wrong:** Hardcoded line number is a stable-anchor failure mode (per the brief's drift problem #3). At /implement time the line might be 580 or 605 depending on prior edits. The fix-hint should describe the change ("flip the `AutoMLEngine` map entry from `engines.automl_engine` to `automl.engine`") rather than pin a line number.
- **Recommended action:** Replace with description: `flip kailash_ml/__init__.py:__getattr__ map entry for "AutoMLEngine" → "kailash_ml.automl.engine"`. The gate's actual fix-hint emission (per ADR-6) should not pin line numbers in source either.

#### FLOW-MED-1: Cross-SDK flow paragraph (line 233-242) is contradictory with plan § 6

- **Location:** `01-developer-flow.md:237` ("the gate is scoped to kailash-py only") vs `02-plans/01-implementation-plan.md:155` ("Cross-SDK Python↔Rust drift (E2 — designed for, deferred to M2 per ADR-7)")
- **What's wrong:** User-flow says cross-SDK is M2 deferred (correct); plan § 6 also says M2 — but cross-references ADR-7. ADR-7 is FUTURE EVOLUTION (executable annex), NOT cross-SDK. ADR-5 is cross-SDK. Plan § 6 cites the wrong ADR.
- **Recommended action:** In `02-plans/01-implementation-plan.md:155`, change "ADR-7" to "ADR-5". In `01-developer-flow.md:237`, replace "(per ADR-5 manifest-driven design)" references for clarity. Then verify all 3 docs say "ADR-5 = cross-SDK; ADR-7 = future annex evolution".

#### FLOW-MED-2: Failure flow uses inconsistent path forms for fabricated test path

- **Location:** `01-developer-flow.md:194` (`tests/integration/test_feature_store_wiring.py`) vs `specs/spec-drift-gate.md:175` (`packages/kailash-ml/tests/integration/test_feature_store_wiring.py`) vs the corresponding wave-6.5 review
- **What's wrong:** The paths the gate emits should be repo-root-relative (per ADR-6 "ALL paths absolute or repo-root-relative — no `../../` segments"). The user-flow shows `tests/integration/...` (top-level tests) but spec § 4 row 7 shows `packages/kailash-ml/tests/integration/...`. W6.5 CRIT-2 was actually `packages/kailash-ml/tests/integration/test_feature_store_wiring.py` per the analysis doc (line 217 + 223 W6.5 CRIT-2 evidence at "spec asserted `tests/integration/test_feature_store_wiring.py`"). Multiple subtly-different forms across docs.
- **Recommended action:** Standardize on `packages/kailash-ml/tests/integration/test_feature_store_wiring.py` everywhere. Edit `01-developer-flow.md:194-195` to match.

#### FLOW-LOW-1: Persona 1 example claim "~6s on the specialist's laptop" is unsourced

- **Location:** `01-developer-flow.md:32` ("Time: ~6s on the specialist's laptop")
- **What's wrong:** "6s" is an estimate, not a measurement. NFR-1 is 30s full corpus / <3s incremental. A single-spec edit should be incremental, so ~3s; "6s" is conservative but undocumented.
- **Recommended action:** Either source the figure ("conservative estimate; NFR-1.1 incremental budget is <3s; full-corpus 30s") or remove. Optional.

#### FLOW-LOW-2: Edge case section on "section-heading drift" uses example heading not in spec

- **Location:** `01-developer-flow.md:217` ("specialist renames `## Surface` to `## Public Interface` in `specs/dataflow-core.md`")
- **What's wrong:** `specs/dataflow-core.md` does not exist in `specs/_index.md`. The closest match is `specs/dataflow-core-architecture.md`. Hypothetical example referencing non-existent spec file. Minor.
- **Recommended action:** Use a real spec file (e.g., `specs/ml-engines-v2.md`) or annotate "(hypothetical spec for illustration)".

---

### 2.5 `specs/spec-drift-gate.md` — APPROVE WITH AMENDMENTS

#### SPEC-HIGH-1: § 2.4 manifest schema differs from analysis ADR-5

- **Location:** `specs/spec-drift-gate.md:87-112` vs `02-requirements-and-adrs.md:719-749`
- **What's wrong:** Per REQ-HIGH-2 above. The two TOML manifest representations diverge in shape. If the spec is the durable artifact, the analysis doc must mirror it (and FP-Q9.1 multi-package errors module ordering must reflect spec § 2.4 `[errors_modules]` form, not ADR-5's nested-table form).
- **Recommended action:** Reconcile in same edit; recommend spec wins. Adjust `02-requirements-and-adrs.md:719-749` to match `specs/spec-drift-gate.md:87-112` byte-for-byte.

#### SPEC-HIGH-2: § 4 Sweep Contracts row 8 cite mismatch (FR-8)

- **Location:** `specs/spec-drift-gate.md:175` ("FR-8 | Workspace-artifact leak | \"W31 31b\" leakage in `features/store.py:354-361`")
- **What's wrong:** FR-8 is a SPEC-LEVEL leak detector (workspace references appearing in `specs/*.md`). The cited evidence "`features/store.py:354-361`" is a SOURCE file, not a spec. The audit found `W31 31b` references in spec files, not in source. Cite is wrong.
- **Recommended action:** Cite `specs/ml-feature-store.md` (or whatever spec had the leak per W6.5 review) at the appropriate line; do NOT cite source code as evidence for spec-level leak. Verify with `grep -rn 'W31 31b' specs/` to find the right spec.

#### SPEC-MED-1: § 8.1 "Editing a spec — success path" embeds a `## 3. Public API` heading inside the spec

- **Location:** `specs/spec-drift-gate.md:296-301`
- **What's wrong:** The spec uses `## 3. Public API` as an embedded markdown example block — but markdown renderers will interpret it as a top-level heading of the spec-drift-gate spec itself, breaking the TOC. The example is intended to be illustrative content of `specs/ml-engines.md`. Currently the embedded `## 3. Public API` is rendered as section 3 of `spec-drift-gate.md` (which is "Marker Convention").
- **Recommended action:** Either fence the example in a code block (` ```markdown ` / ` ``` `), reduce the example heading depth (`#### 3. Public API`), or use indented quoted-text formatting. The `01-developer-flow.md:14-18` correctly fences this same example in a `markdown` code block.

#### SPEC-MED-2: ADR-6 fix-hint format not verbatim shown in spec

- **Location:** `specs/spec-drift-gate.md:323-329` (§ 8.3 W6.5 CRIT-1 reproduction)
- **What's wrong:** Per M3 sweep above. ADR-6 declares the canonical output format `FAIL <FR-N>: <asserted_symbol> cited at <spec_path>:<line_no> <action_verb> <where>` followed by `(a)/(b)/(c)` triad. The spec's § 8.3 reproduction example shows `FAIL specs/ml-feature-store-v2-draft.md:515 FR-4: class FeatureGroupNotFoundError — not found in src/kailash/ml/errors.py` — close but order of fields is flipped (ADR-6 puts `<FR-N>` before `<asserted_symbol>`; spec puts `<spec_path>:<line>` before `<FR-N>:`). Minor but specs/ readers may notice the inconsistency.
- **Recommended action:** Reformat § 8.3 output examples to match ADR-6 verbatim: `FAIL FR-4: FeatureGroupNotFoundError cited at specs/ml-feature-store-v2-draft.md:515 not found in src/kailash/ml/errors.py`. Add the `→ fix: (a)/(b)/(c)` line under at least the first example (elide for the rest with explicit `[ELIDED for brevity]`).

#### SPEC-MED-3: § 8.3 cites a spec file that does NOT exist (W6.5 round 1 was a draft)

- **Location:** `specs/spec-drift-gate.md:323` ("`python scripts/spec_drift_gate.py specs/ml-feature-store-v2-draft.md`")
- **What's wrong:** `specs/ml-feature-store-v2-draft.md` was the round-1 W6.5 draft that was REJECTED. Round 2 became `specs/ml-feature-store.md`. The draft does not (and SHOULD not) exist in shipped specs/. The example invocation will fail. The example should reference a TEST FIXTURE under `tests/fixtures/spec_drift_gate/` (per FR-12 fixture list mentioning `bad_error_class.md`).
- **Recommended action:** Replace the example invocation with `python scripts/spec_drift_gate.py tests/fixtures/spec_drift_gate/w65_crit1_fabricated_errors.md` (matching the FR-12 fixture name). The 5 fabricated `*Error` classes still demonstrate; the path no longer references a never-shipped draft.

#### SPEC-MED-4: § 11.2 cross-SDK milestone deferral cites ADR-5 but spec § 2.4 implies day-1 manifest is cross-SDK ready

- **Location:** `specs/spec-drift-gate.md:385-389` vs `:85-86` ("Single manifest format permits cross-SDK reuse (kailash-py + kailash-rs in M2)")
- **What's wrong:** The spec § 2.4 says the manifest is cross-SDK-ready at day 1; § 11.2 says cross-SDK reference verification is M2. Both correct (the manifest schema is forward-compatible; the verification logic is M2), but the casual reader may read § 2.4 as "cross-SDK shipped today." The distinction needs a "manifest schema is forward-compatible; cross-repo invocation is M2" sentence.
- **Recommended action:** In `specs/spec-drift-gate.md:85-86`, append "(M2 enables single-invocation cross-SDK; v1.0 ships kailash-py only with the manifest schema parity that supports the future port)."

#### SPEC-LOW-1: § 12 "Maintenance Notes" rule cite is implicit

- **Location:** `specs/spec-drift-gate.md:417-435`
- **What's wrong:** The maintenance notes section references rules without explicit numbering: "D1 — gate becomes the new mock", "D2 — specialists disable the gate when it blocks", etc. These are failure-points enumeration; the spec § 12 should cite `01-failure-points.md § D1` etc. for back-reference.
- **Recommended action:** Add `(see 01-failure-points.md § D1)` after each. Optional.

#### SPEC-LOW-2: § 1.1 In-Scope item 9 mentions "MOVE shim verification" but the plan does not deliver

- **Location:** `specs/spec-drift-gate.md:29` ("9. MOVE shim verification — every `MOVE: old_path → new_path` claim has both paths resolve correctly.")
- **What's wrong:** Same root cause as PLAN-CRIT-1. Spec advertises FR-9 in v1.0 scope; plan does not allocate a shard. If FR-9 deferred to v1.1, item 9 must move from `## 1.1 In Scope (v1.0)` to `## 11. Deferred to M2 milestone`.
- **Recommended action:** Subsumed under PLAN-CRIT-1 — either FR-9 ships in S2 (extend invariants list) or item 9 of § 1.1 moves to § 11.

---

### 2.6 `specs/_index.md` — VERIFIED (no separate verdict required)

The Tooling & Quality section (line 170) was added with one row pointing to `spec-drift-gate.md`. The description ("Mechanical pre-commit + CI check that verifies spec assertions against code; section-context inference, override directives, baseline grace") accurately summarizes the spec. No findings.

---

## 3. Cross-Document Consistency Sweep (LLM judgment)

### 3.1 ADR cross-cites

ADRs are referenced by number across documents:

- Spec → analysis: ADR-2, ADR-3, ADR-4, ADR-5, ADR-6 (implicit), ADR-7 (§ 11.4) — OK
- Plan → analysis: ADR-1 (S1), ADR-2 (§ 2 keystone), ADR-3 (S3), ADR-4 (S5/S6), ADR-5 not cited, ADR-6 (S3), ADR-7 (§ 6 — INCORRECT, should be ADR-5) — see FLOW-MED-1
- Flow → analysis: ADR-2 (Persona 2), ADR-3 (Persona 3), ADR-5 (Cross-SDK Flow) — OK

### 3.2 FR cross-cites

13 FRs declared; spec § 4 enumerates 13; plan covers 11/13 (missing FR-9, FR-10) — see PLAN-CRIT-1.

### 3.3 Failure-mode citations

failure-points.md uses `B1`, `A3`, `B6`, `D3`, `D4` IDs in Top-5. Plan § 4 risks table cites all 5 by ID. Spec § 12 cites `D1`, `D2`, `D3`, `D4` — but `D1`, `D2` are not in plan. The spec preserves the broader failure surface; plan focuses on Top-5; consistent split.

### 3.4 Fix-hint format

ADR-6 declares format `FAIL <FR-N>: <asserted_symbol> cited at <spec_path>:<line_no> <action_verb> <where>`. Implementations across docs:

- Analysis output example (line 1083): different field order (puts spec_path before FR-N) — REQ-MED-4
- Flow CRIT-1 failure (line 174-191): matches ADR-6 verbatim — OK
- Spec § 8.3 (line 324-328): different order, no `(a)/(b)/(c)` — SPEC-MED-2

The spec example is the most prominent (will be read by all consumers). Recommend reconciling to ADR-6's format.

### 3.5 Numbers / counts cross-document drift

| Claim                         | Source                                | Value        | Inconsistency?                                    |
| ----------------------------- | ------------------------------------- | ------------ | ------------------------------------------------- |
| Spec corpus size              | failure-points 8, requirements 8      | 72           | Consistent                                        |
| Pre-existing HIGH backlog     | brief 4, plan 18, requirements 1322   | 38 / 36 / 36 | **Yes** — brief says 38, two analysis docs say 36 |
| W5-E2 finding count           | failure-points 300, 413               | ~70          | Different baseline than the brief                 |
| Marker mitigations dependency | plan 24, spec 118, failure-points 460 | 17 of 28     | Consistent                                        |
| Total LOC estimate            | plan 38, requirements 1284            | ~1330        | Consistent (but excludes FR-9/FR-10)              |
| Failure modes total           | failure-points 456, plan 7            | 28           | Consistent                                        |
| FRs total                     | requirements 1311, plan 5             | 13           | Consistent                                        |
| ADRs total                    | requirements 1313, plan 5             | 7            | Consistent                                        |
| NFRs total                    | requirements 1312                     | 5            | Consistent                                        |

The 38 vs 36 vs 70 inconsistency is the most consequential — it determines (a) baseline size at S5, (b) FPR calibration target. See FP-HIGH-1.

---

## 4. Recommendation Summary

**Ship to /todos AFTER amendments.**

### Critical (must fix before /todos approval)

1. **PLAN-CRIT-1** — Assign FR-9 + FR-10 to a shard, OR drop them from the spec § 1.1.

### High-priority (recommend fixing in same /todos session)

2. **REQ-HIGH-2 / SPEC-HIGH-1** — Reconcile manifest TOML schema (analysis ADR-5 vs spec § 2.4); pick the spec form, edit ADR-5.
3. **REQ-HIGH-1** — FR-6 contract for `__getattr__`-resolved exports needs an FR-6a sub-clause OR fold into FR-6 pseudocode.
4. **REQ-HIGH-3** — Add explicit symbol-index cache to S1 invariants OR risk NFR-1 budget violation.
5. **PLAN-HIGH-2** — Add Q9.2, Q9.3, Q9.4 to plan § 8 pre-/todos open items.
6. **PLAN-HIGH-3** — Split plan § 5 acceptance row 7-8 into 8 distinct rows for 1:1 brief mapping.
7. **PLAN-HIGH-1** — Reconcile failure-points Top-5 entry 3 (B6 MUST framing) with plan's S1+S2 split.
8. **SPEC-HIGH-2** — Fix § 4 row 8 evidence cite (specs leak, not source leak).
9. **FLOW-HIGH-1** — De-pin line numbers in Persona 4 fix hints.
10. **FP-HIGH-1** — Reconcile 38 vs 36 vs 70 backlog count across docs; pick canonical and propagate.
11. **FP-HIGH-2** — Add `(converse direction)` parenthetical to orphan-detection MUST 6 cite.

### Medium / Low — defer to /implement

The 9 MEDs and 4 LOWs above are housekeeping; they don't block /todos but the orchestrator should pull them in as a review-pass at /implement kickoff or codify-time.

### Round-2 analyst recall not required

The analysis is internally consistent on its core conclusions:

- ADR-2 marker-convention keystone is well-grounded (5-fold evidence in § 8 of requirements doc + corroborated by failure-points § Closing Notes "17 of 28 mitigations depend on it").
- 6-shard sequencing is within autonomous capacity budget.
- Brief acceptance criteria fully covered (all 8 brief items map to a shard).
- Top-5 day-1-critical failure modes all have mitigations + owner shards.

The 1 CRIT and 11 HIGHs are all single-edit reconciliations, not conceptual rebuilds. **Round-2 is not needed.**

---

## 5. Quality Signals Observed

**Green flags (substantiated claims):**

- ADR-2 cites concrete grep counts ("hundreds of matches" verified at requirements line 500); FPR estimate is bounded ("<3 false positives per 70 findings ~4%").
- Plan shard sizes reference `rules/autonomous-execution.md` § Per-Session Capacity Budget verbatim.
- failure-points.md crisply maps each failure mode to a code-level mitigation (e.g., B1 → "AST + import-graph trace").
- Cross-references are bidirectional — analysis doc § 10 cites brief + sibling failure-points; plan § 7 cites both back; spec § 9 closes the loop.
- Foundation Independence + Apache 2.0 license headers correct (spec line 7 — "Owner: Terrene Foundation (Singapore CLG)"; line 6 — "License: Apache-2.0"). No commercial coupling.

**Red flags (addressed above):**

- Some spec assertions cite line numbers that drift (FLOW-HIGH-1).
- Manifest schema duplicated, two forms (REQ-HIGH-2 / SPEC-HIGH-1).
- Open-questions surfaced by analyst not propagated to plan (PLAN-HIGH-2).

---

## 6. File path for orchestrator

This review file: `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/04-validate/00-analyze-redteam.md`

Source documents reviewed (no edits made):

- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/briefs/01-product-brief.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/01-analysis/01-failure-points.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/01-analysis/02-requirements-and-adrs.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/02-plans/01-implementation-plan.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/03-user-flows/01-developer-flow.md`
- `/Users/esperie/repos/loom/kailash-py/specs/spec-drift-gate.md`
- `/Users/esperie/repos/loom/kailash-py/specs/_index.md`

End of red-team review.
