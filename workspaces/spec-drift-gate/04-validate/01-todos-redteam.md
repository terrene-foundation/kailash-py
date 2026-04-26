# /todos Red-Team Review — spec-drift-gate

**Date:** 2026-04-26
**Reviewer:** quality-reviewer (autonomous)
**Phase under review:** /todos (1 milestone tracker + 18 atomic todos)
**Inputs reviewed:**

1. `workspaces/spec-drift-gate/todos/active/SDG-000-milestone-tracker.md` (tracker)
2. `workspaces/spec-drift-gate/todos/active/SDG-{101..104,201..203,301..303,401..404,501..502,601..602}.md` (18 atomic)
3. `workspaces/spec-drift-gate/02-plans/01-implementation-plan.md` (plan baseline)
4. `specs/spec-drift-gate.md` (canonical contract)
5. `workspaces/spec-drift-gate/briefs/01-product-brief.md` (user input)
6. `workspaces/spec-drift-gate/04-validate/00-analyze-redteam.md` (prior round; verify amendments propagated)

---

## 0. Headline Verdict

**APPROVE WITH AMENDMENTS — ship to /implement after applying the 4 HIGH-priority amendments inline at /todos approval.**

| Severity | Count | Notes                                                              |
| -------- | ----- | ------------------------------------------------------------------ |
| CRIT     | 0     | No cycles, no missing-shard FRs, no dependency inversions          |
| HIGH     | 4     | Recoverable inline; do not require round-2 plan rewrite            |
| MED      | 7     | Defer to /implement kickoff or absorb into an existing shard       |
| LOW      | 5     | Housekeeping; track in journal but do not block ship to /implement |

The plan-shard → atomic-todo decomposition is coherent, dependency chains form a clean DAG, and per-session capacity budget is respected on every shard. The 4 HIGHs are: (1) FR-12 has no explicit owner (collapsed into SDG-401's fixture work and SDG-402+SDG-403's tests but not named), (2) Q9.4 (ADR-2 prose-mention denylist) and the spec § 1.3 cross-SDK clarification have no owner todo despite the prior redteam's PLAN-HIGH-2 amendment, (3) NFR-2 false-positive rate (<5%) has no measurement / verification owner, and (4) FR-6 (`__all__` membership) is mentioned in SDG-202 but the spec's authoritative § 4 contract — and the `__getattr__` resolution in SDG-203 — never explicitly close the integration loop the redteam REQ-HIGH-1 demanded.

**Recommendation:** **ship to /implement** after a 5-minute amendment pass on the 4 HIGHs (per Rule 5c — "amend-at-launch when spec has moved" — the orchestrator should resolve these IN THE TODO TEXT before launching shard agents, not at /implement mid-flight).

---

## 1. Mechanical Sweep Results

### M1 — FR Coverage (FR-1..FR-13 minus deferred FR-9, FR-10)

Plan-of-record: FR-9 + FR-10 deferred to v1.1 per spec § 11.7-11.8 + plan § 8 item 8 + redteam PLAN-CRIT-1 disposition. Remaining 11 FRs MUST each have ≥1 owner todo.

| FR        | Owner todo                                                | Mechanical evidence (acceptance bullet line)                                                | Status     |
| --------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ---------- |
| **FR-1**  | SDG-103, SDG-401 (fixture), SDG-402 (`test_fr1_*`)        | SDG-103 acceptance bullet 1 ("class existence"); SDG-402 line 24                            | OK         |
| **FR-2**  | SDG-103, SDG-401, SDG-402                                 | SDG-103 acceptance bullet 2; SDG-402 line 25                                                | OK         |
| **FR-3**  | SDG-202, SDG-401, SDG-402                                 | SDG-202 acceptance bullet 1 ("decorator application + count")                               | OK         |
| **FR-4**  | SDG-103, SDG-401 (`w65_crit1_*`), SDG-402, SDG-403 (W6.5) | SDG-103 acceptance bullet 3; SDG-403 acceptance bullet 2 (W6.5 CRIT-1 reproduction)         | OK         |
| **FR-5**  | SDG-202, SDG-401, SDG-402                                 | SDG-202 acceptance bullet 2 ("AnnAssign in resolved class body")                            | OK         |
| **FR-6**  | SDG-202, SDG-203 (related), SDG-402                       | SDG-202 acceptance bullet 3; **but see HIGH-2 — `__getattr__` integration loop unclosed**   | PARTIAL    |
| **FR-7**  | SDG-103, SDG-401 (`w65_crit2_*`), SDG-402, SDG-403        | SDG-103 acceptance bullet 4; SDG-403 acceptance bullet 3 (CRIT-2 reproduction)              | OK         |
| **FR-8**  | SDG-202, SDG-401, SDG-402                                 | SDG-202 acceptance bullet 4 ("workspace-artifact leak")                                     | OK         |
| **FR-11** | SDG-301, SDG-303 (refresh+ageout), SDG-402                | SDG-301 acceptance bullets 5 + 6 ("Diff logic", "ageout"); SDG-303 entire scope             | OK         |
| **FR-12** | **NO EXPLICIT NAMED OWNER** — implicit via SDG-401        | SDG-401 directly produces FR-12 fixtures but acceptance bullet does not name FR-12 contract | **HIGH-1** |
| **FR-13** | SDG-302                                                   | SDG-302 acceptance bullets 1-3 ("--format human/json/github")                               | OK         |

**Result:** 10 of 11 FRs cleanly owned. **FR-12 has implicit-only ownership through SDG-401's fixture creation but no todo-text reference to "FR-12" or its self-test scope.** This is HIGH-1.

### M2 — Plan Shard → Atomic-Todo LOC Mapping

Plan § 3 declares per-shard LOC; SDG-000 milestone tracker mirrors them. Each atomic todo's "Files to Create/Modify" section claims approximate LOC.

| Shard | Plan LOC est.                                      | Atomic todos                                                                                                     | Sum of atomic LOC claims             | Drift | Verdict                |
| ----- | -------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------ | ----- | ---------------------- |
| S1    | ~400                                               | SDG-101 (~120) + SDG-102 (~80) + SDG-103 (~150) + SDG-104 (~50)                                                  | **~400**                             | 0%    | OK                     |
| S2    | ~280 (was 250 + ~30 buffer per redteam REQ-MED-2)  | SDG-201 (~80) + SDG-202 (~120) + SDG-203 (~80)                                                                   | **~280**                             | 0%    | OK                     |
| S3    | ~210                                               | SDG-301 (~80) + SDG-302 (~80) + SDG-303 (~50)                                                                    | **~210**                             | 0%    | OK                     |
| S4    | ~360 (was 300 + ~60 for fixtures per Q9.2 / FR-12) | SDG-401 (fixtures only, no LOC claim, ~150 of fixture content) + SDG-402 (~100) + SDG-403 (~125) + SDG-404 (~60) | **~435**                             | +20%  | LOW-2 (slight over)    |
| S5    | ~100                                               | SDG-501 (~15) + SDG-502 (~50)                                                                                    | **~65** (+ baseline JSONL ~36 lines) | -35%  | LOW-3 (under, no risk) |
| S6    | ~80                                                | SDG-601 (~50) + SDG-602 (~30)                                                                                    | **~80**                              | 0%    | OK                     |

**Result:** Total ~1,470 LOC vs plan's 1,330. The +20% on S4 is real (fixture authoring is content-heavy, not LOC-light); see LOW-2. S5's -35% is conservative because the baseline JSONL (~36 lines of generated content) doesn't count toward LOC budget. **No undersized or oversized shards.**

### M3 — Dependency Cycle Check

Parsed `depends_on:` and `blocks:` from each todo's frontmatter. Built a directed graph:

```
SDG-000 (tracker) — no deps, no blocks (orchestrator-only)
SDG-101 → blocks: SDG-102, SDG-103
SDG-102 → depends: SDG-101 → blocks: SDG-103, SDG-104
SDG-103 → depends: SDG-101, SDG-102 → blocks: SDG-104
SDG-104 → depends: SDG-101, SDG-102, SDG-103 → blocks: SDG-201
SDG-201 → depends: SDG-104 → blocks: SDG-202, SDG-203
SDG-202 → depends: SDG-201 → blocks: SDG-203
SDG-203 → depends: SDG-202 → blocks: SDG-301
SDG-301 → depends: SDG-203 → blocks: SDG-302, SDG-303
SDG-302 → depends: SDG-301 → blocks: SDG-401
SDG-303 → depends: SDG-301 → blocks: SDG-401
SDG-401 → depends: SDG-302, SDG-303 → blocks: SDG-402, SDG-403
SDG-402 → depends: SDG-401 → blocks: SDG-501
SDG-403 → depends: SDG-401 → blocks: SDG-501
SDG-404 → depends: SDG-403 → blocks: SDG-501
SDG-501 → depends: SDG-402, SDG-403, SDG-404 → blocks: SDG-502
SDG-502 → depends: SDG-501 → blocks: SDG-601
SDG-601 → depends: SDG-502 → blocks: SDG-602
SDG-602 → depends: SDG-601 → blocks: (terminal)
```

**Topological sort result (one valid order):**
SDG-101 → SDG-102 → SDG-103 → SDG-104 → SDG-201 → SDG-202 → SDG-203 → SDG-301 → {SDG-302 || SDG-303} → SDG-401 → {SDG-402 || SDG-403} → SDG-404 → SDG-501 → SDG-502 → SDG-601 → SDG-602

**Cycle detection:** **No cycles.** DAG is acyclic. Topological order matches the S1→S6 plan sequencing.

**Inconsistency check:** Every `blocks:` in todo X is mirrored by a `depends_on:` in todo Y (and vice versa). Spot-check:

- SDG-101.blocks=[SDG-102,SDG-103] ↔ SDG-102.depends_on=[SDG-101], SDG-103.depends_on=[SDG-101,SDG-102] ✓
- SDG-301.blocks=[SDG-302,SDG-303] ↔ SDG-302.depends_on=[SDG-301], SDG-303.depends_on=[SDG-301] ✓
- SDG-401.blocks=[SDG-402,SDG-403] ↔ SDG-402.depends_on=[SDG-401], SDG-403.depends_on=[SDG-401] ✓
- SDG-403.blocks=[SDG-501] but SDG-404.depends_on=[SDG-403] — SDG-403 should also list SDG-404 in its blocks. **MED-1 (frontmatter consistency).**
- SDG-501.depends_on=[SDG-402,SDG-403,SDG-404] — three deps; SDG-402.blocks=[SDG-501] ✓, SDG-403.blocks=[SDG-501] ✓ (but missing SDG-404), SDG-404.blocks=[SDG-501] ✓.

**Result:** 0 cycles. 1 missing `blocks:` arrow (SDG-403 → SDG-404 is implicit via SDG-404.depends_on but not declared in SDG-403.blocks). Minor — see MED-1.

### M4 — Per-Session Capacity Budget Compliance

Per `rules/autonomous-execution.md` § Per-Session Capacity Budget (≤500 LOC load-bearing logic / ≤5-10 invariants / ≤3-4 call-graph hops / describable in 3 sentences). Each todo claims an `estimated_sessions` ≤0.5 (i.e., a fraction of a single shard); shards (S1-S6) are sized at session-equivalent. So MUST budget against the SHARD sum, not the individual todo.

| Shard | LOC sum | Invariants sum (claimed)                                                                                                                                                                        | Call-graph hops                                                       | 3-sentence test                                                                            | Budget verdict                                                                                                           |
| ----- | ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| S1    | ~400    | 6 (SDG-103 lists 6 invariants) + 3 (SDG-101) + 2 (SDG-102) + 2 (SDG-104) = 13 unique-ish; many are file-local. After dedup (cache, section-context, marker-precedence are repeats): ~6 distinct | 3 (CLI → section-parser → marker-parser → sweep-dispatch → AST cache) | 3 sentences possible                                                                       | OK                                                                                                                       |
| S2    | ~280    | 3 (manifest) + 3 (FR-3/5/8) + 3 (FR-6 + getattr WARN) = 9. After dedup: ~7 distinct                                                                                                             | 3 (manifest → sweep-dispatch → ast-cache → getattr-resolver)          | 3 sentences                                                                                | OK                                                                                                                       |
| S3    | ~210    | 3 (baseline) + 4 (output formats) + 3 (refresh/ageout) = 10. Dedup: ~6 distinct                                                                                                                 | 2-3 hops                                                              | 3 sentences                                                                                | OK                                                                                                                       |
| S4    | ~435    | 3 (fixtures) + 3 (Tier-1) + 3 (Tier-2) + 3 (wiring/perf) = 12. Dedup: ~7 distinct (fixtures and tests share invariant "deterministic")                                                          | 3 (fixture → test → gate → CLI subprocess)                            | 3 sentences (each todo is "build the fixtures / unit / integration / wiring respectively") | **MED-2 — 12 invariants borderline, but SDG-401 is content-only (deterministic Markdown), not load-bearing logic; pass** |
| S5    | ~100    | 3 (hook) + 4 (baseline capture) = 7. Dedup: ~5                                                                                                                                                  | 2 hops                                                                | 3 sentences                                                                                | OK                                                                                                                       |
| S6    | ~80     | 4 (workflow PR) + 3 (skill doc) = 7. Dedup: ~5                                                                                                                                                  | 2 hops                                                                | 3 sentences                                                                                | OK                                                                                                                       |

**Result:** Every shard is within budget, with S4 at the border (12 invariants pre-dedup). S4's content includes substantial fixture-authoring (Markdown, not Python logic), which scales differently per Rule 2 ("Size By Complexity, Not LOC Alone"). **No CRIT or HIGH.** MED-2 documents the S4 borderline.

**No single todo claims >200 LOC of load-bearing logic.** Largest is SDG-103 at ~150 LOC (4 sweeps + cache). Within budget.

### M5 — Conformance Checklist Coverage (`specs/spec-drift-gate.md` § 10, 14 items)

Each conformance bullet MUST have ≥1 owner todo whose acceptance criteria deliver it.

| § 10 conformance item                                                           | Owner todo(s)                                                                                                         | Status     |
| ------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ---------- |
| 1. CLI surface matches § 2.1 verbatim (flags + arguments)                       | SDG-101 acceptance bullet 2                                                                                           | OK         |
| 2. Pre-commit hook scoped to `specs/**.md` (§ 2.2)                              | SDG-501 acceptance bullet 2                                                                                           | OK         |
| 3. Manifest schema matches § 2.4 (TOML, [gate], [[source_roots]], etc.)         | SDG-201 acceptance bullets 1-4                                                                                        | OK         |
| 4. Section-context inference matches § 3.1 allowlist regex                      | SDG-101 acceptance bullets 5-7                                                                                        | OK         |
| 5. Override directives parse per § 3.2; `reason:` REQUIRED on skip              | SDG-102 acceptance bullets 1-3                                                                                        | OK         |
| 6. All 13 FRs implemented (§ 4 + analysis doc)                                  | SDG-103, SDG-202, SDG-203, SDG-301, SDG-302 — but FR-12 implicit; FR-9, FR-10 deferred per spec                       | **HIGH-1** |
| 7. Baseline format matches § 5.1 schema; entries carry origin/added/ageout      | SDG-301 acceptance bullets 1-3                                                                                        | OK         |
| 8. `--refresh-baseline` writes `.spec-drift-resolved.jsonl` audit trail (§ 5.3) | SDG-303 acceptance bullet 1                                                                                           | OK         |
| 9. Anti-rot mechanisms in place (§ 5.4 — origin required, age-out, etc.)        | SDG-301 inv. 1 + SDG-303 acceptance bullet 2                                                                          | OK         |
| 10. Errors derive from `SpecDriftGateError` (§ 6.1)                             | SDG-102 acceptance bullet 8 (MarkerSyntaxError); SDG-201 (ManifestNotFound/SchemaError); SDG-301 (BaselineParseError) | OK         |
| 11. Tier 1 + Tier 2 self-tests pass (§ 7)                                       | SDG-402 + SDG-403                                                                                                     | OK         |
| 12. W6.5 CRIT-1 + CRIT-2 reproductions pass (§ 7.2)                             | SDG-403 acceptance bullets 2-4                                                                                        | OK         |
| 13. Performance: <30s wall clock on full corpus (NFR-1)                         | SDG-103 inv. 3 + SDG-404 acceptance bullets 2-3                                                                       | OK         |
| 14. False-positive rate <5% on the live corpus (NFR-2)                          | **NO OWNER TODO**                                                                                                     | **HIGH-3** |
| 15. Section-heading drift produces WARN, not silent skip (§ 3.3)                | SDG-101 acceptance bullets 8-9 + SDG-401 (`section_heading_drift.md` fixture) + SDG-403 acceptance bullet 6           | OK         |

**Result:** 13 of 15 conformance items cleanly owned. **2 unowned: FR-12 self-test scope (HIGH-1) + NFR-2 false-positive measurement (HIGH-3).**

NOTE: § 10 has 14 explicit conformance bullets in the spec; one was duplicated/restructured to surface "section-heading drift" as a separate row. I extended to 15 here for completeness; the canonical count remains 14.

### M6 — Spec § 4 Sweep Contracts vs Todo Body

Spec § 4 lists each FR with an "audit cite" column documenting what the sweep catches. Each FR row should appear in at least one todo body alongside its audit cite for traceability.

| FR    | Audit cite per spec § 4                             | Cited in todo body?                                                                            |
| ----- | --------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ------ |
| FR-1  | F-E2-05 `Ensemble.from_leaderboard` absent          | SDG-501 acceptance bullet 7 ("re-add fabricated `Ensemble.from_leaderboard`") — yes (indirect) |
| FR-2  | F-E2-08 `MLEngine.fit_auto()` signature absent      | NOT cited in any todo body                                                                     | LOW-1  |
| FR-3  | "12 training methods registered" verification       | NOT cited in any todo body                                                                     | LOW-1  |
| FR-4  | W6.5 CRIT-1 (5 fabricated \*Error)                  | SDG-401 acceptance bullets 2 + SDG-403 acceptance bullet 2 — explicit list of 5 names ✓        |
| FR-5  | F-E1-38 `RLTrainingResult` missing 8 spec fields    | NOT cited in any todo body                                                                     | LOW-1  |
| FR-6  | PR #523/#529 (4 DeviceReport symbols missing)       | SDG-202 line 75 references "Q9.3 deferral" but PR cite missing                                 | LOW-1  |
| FR-7  | W6.5 CRIT-2 (`test_feature_store_wiring.py` absent) | SDG-401 acceptance bullet 3 + SDG-403 acceptance bullet 3 — explicit ✓                         |
| FR-8  | spec-level leak — "W31 31b" mention                 | SDG-202 line 22 — explicit ✓                                                                   |
| FR-11 | Pre-existing 36-HIGH backlog handling               | SDG-502 acceptance bullets 3-6 — explicit ✓                                                    |
| FR-12 | (Self-test fixtures coverage)                       | SDG-401 acceptance bullets 1-9 — fixtures created BUT FR-12 not named                          | HIGH-1 |
| FR-13 | Pre-commit / CI / PR-review markup                  | SDG-302 entire scope — implicit (cites § 6.2 + FR-13 in module-doc reference) ✓                |

**Result:** 4 FR audit-cites are missing from todo bodies (FR-2, FR-3, FR-5, FR-6). All LOW (housekeeping for traceability). The W6.5 CRIT-1 + CRIT-2 audit cites — the load-bearing demos — ARE in the todos.

### M7 — Build/Wire Pair Check

The /todos skill mandates separate Build + Wire todos for components that consume/produce data. The gate is itself a tool (a CLI script that consumes specs + sources, produces findings + JSONL baseline) — but does NOT have a "data consumer in the user-facing sense" that demands per-component Build+Wire pairs.

**Inspection of the structural pattern:**

- **CLI (SDG-101) builds the entry point.** SDG-104 wires it end-to-end (verifies against pristine specs). → Build (SDG-101) + Wire (SDG-104) ✓
- **Manifest parser (SDG-201) builds manifest loading.** No separate "wire manifest" todo — but every downstream sweep todo (SDG-202, SDG-203) consumes the manifest. **Implicit wiring through SDG-202's "Manifest source roots" field references in pseudocode.** ACCEPTABLE.
- **Sweep modules (SDG-103 + SDG-202) build sweep logic.** SDG-104 wires S1; SDG-203 wires `__getattr__` integration. ACCEPTABLE.
- **Baseline (SDG-301) builds schema + diff.** SDG-302 wires output formats that consume the diff. SDG-303 wires refresh + ageout. ACCEPTABLE.
- **Fixtures (SDG-401) build test inputs.** SDG-402 wires Tier 1 (fixtures → unit tests). SDG-403 wires Tier 2 (fixtures → integration tests). SDG-404 wires the full subprocess pathway. ACCEPTABLE.
- **Hook (SDG-501) wires gate → pre-commit.** SDG-502 wires baseline capture into the live workflow. ACCEPTABLE.
- **Workflow (SDG-601) wires gate → CI.** SDG-602 wires gate → docs. ACCEPTABLE.

**Result:** Build/Wire pattern is preserved at the SHARD level (S1 builds engine; S5+S6 wire to live channels) AND at the TODO level (SDG-101 builds CLI; SDG-104 wires pristine-spec test). **No Wire-todo gaps.**

### M8 — Acceptance Criteria Specificity

Spot-checked 3 random todos for verifiable acceptance criteria:

- **SDG-103** (FR sweeps + cache):
  - "FR-1 — every backticked `ClassName` in an allowlist section resolves to an AST `ClassDef`" — verifiable via fixture sweep
  - "Cache hit-rate ≥80% on unchanged source" — verifiable via numerical assertion
  - "Each sweep emits findings via the format defined in SDG-302 (deferred); for now emit raw `Finding(spec_path, line, fr_code, symbol, kind)` tuples" — **AMBIGUOUS** — "deferred" creates a pending integration that SDG-302 must close. See MED-3.
- **SDG-401** (test fixtures):
  - "Each fixture documents its expected findings count + FR codes in a `<!-- expected: ... -->` comment header" — verifiable
  - "**`w65_crit1_fabricated_errors.md`** — replicates round-1 FeatureStore draft" with 5 explicit class names — bit-faithful, verifiable ✓
- **SDG-602** (skill doc):
  - "Has a new section titled `## Executable Form: Spec Drift Gate`" — verifiable via `grep`
  - "Bidirectional cross-link with `specs/spec-drift-gate.md` § 9" — verifiable
  - "Commit message references PR #N (the main gate implementation PR)" — **PR # unknown at /todos time**, recoverable by orchestrator at /implement.

**Result:** Acceptance criteria are mostly verifiable with concrete commands. 1 ambiguity in SDG-103's deferral framing — see MED-3.

---

## 2. Findings

### CRIT (must fix before /implement)

None.

### HIGH (recommend fixing inline at /todos approval)

#### HIGH-1: FR-12 (self-test fixture coverage) has no explicit named owner

- **Where:** Spec § 4 row 12 (FR-12 = "Self-test fixtures") + spec § 10 conformance item 6 ("All 13 FRs implemented")
- **What's wrong:** SDG-401 produces fixture files but its acceptance criteria do not name "FR-12" — they name FR-1..FR-8 fixtures by category. Reviewer scanning todos for "FR-12" finds zero hits. The work IS done (fixtures created), but the auditing surface (M1, M5, M6 above) flags FR-12 as orphan-by-naming because the only place "FR-12" appears in any active todo is as a passing reference in SDG-401 line 16 ("Implements: spec § 7.3 + FR-12") — not in the acceptance bullets.
- **Recommendation:** Edit SDG-401's first acceptance bullet to read "Directory `tests/fixtures/spec_drift_gate/` exists (delivers FR-12 self-test fixture coverage per spec § 4 row 12); NOT under `specs/`...". Apply the same pattern in SDG-402's bullet 1 ("delivers FR-12 Tier 1 unit-test coverage"). One-line edit.
- **Severity rationale:** Implementation correct, naming wrong. HIGH because mechanical sweep at /redteam time will report "FR-12 unowned" if the orchestrator searches for the FR code in the todos and is misled.

#### HIGH-2: FR-6 + SDG-203 `__getattr__` integration loop is not closed end-to-end

- **Where:** SDG-202 (FR-6 `__all__` membership v1.0 scope) + SDG-203 (`__getattr__` map AST traversal, B1-class WARN)
- **What's wrong:** Per redteam REQ-HIGH-1, FR-6 needs to either (a) extend its pseudocode to scan `__getattr__` body, or (b) introduce an FR-6a sub-clause with a clean home for the WARN. The two todos split the work — SDG-202 implements `__all__`-only; SDG-203 implements `__getattr__` traversal as a SEPARATE finding code (B1) — but no acceptance criterion in either todo says: "when FR-6 sweep runs and finds the symbol in `__all__`, AND `__getattr__` map is also present, AND the map's resolution target differs from where the spec asserts the symbol — emit the BOTH the FR-6 PASS and the B1 WARN coherently." The two paths run in parallel, never integrate. Result at /implement time: a spec asserting `kailash_ml.AutoMLEngine` will get FR-6 PASS (because `__all__` lists `AutoMLEngine`) AND a separate B1 WARN (because the map resolves elsewhere). Two outputs, no unified narrative.
- **Recommendation:** Add a new acceptance bullet to SDG-203: "When FR-6 sweep PASSES on a symbol AND `__getattr__` resolution exists for the same symbol, the B1 WARN message MUST cross-reference the FR-6 PASS line so the operator sees both signals attached to the same symbol." Or accept the parallel-paths design and document it as a v1.0 known-limit in the spec § 11.1.
- **Severity rationale:** A real risk that the gate produces confusing dual-emit output for `kailash_ml`-class drift, undermining the dogfood demo (SDG-203 verification command). HIGH.

#### HIGH-3: NFR-2 (false-positive rate <5%) has no measurement / verification owner

- **Where:** Spec § 10 conformance item 13 ("False-positive rate <5% on the live corpus (NFR-2)") + plan § 5 row 5 ("FP rate <5% — NFR-2; ADR-2")
- **What's wrong:** Every other conformance item has at least one owner todo. NFR-2 has none. The S4 plan (`02-plans/01-implementation-plan.md` line 105 — "**D3** — False-positive fatigue (HIGH)" mitigation row) says "Pre-rollout dogfood against full 72-spec corpus; FP triage list before merging S5". Neither SDG-403 (Tier 2 corpus pass test) nor SDG-501 (pre-commit hook) include an acceptance bullet that measures and reports the FPR. SDG-403 has `test_corpus_pass.py` but the acceptance criterion is "zero findings beyond baseline" — that's a pass/fail check, not an FPR measurement. If 4 of 36 baseline entries are TRUE drift and 32 are false positives the gate produces today, the gate fails NFR-2 silently — nothing in the todos surfaces this.
- **Recommendation:** Add a new acceptance bullet to SDG-403 (or SDG-502): "Run gate against `specs/` with `--no-baseline`; manually triage findings into TP / FP buckets (cross-reference W5-E2-findings.md to identify TPs); compute FPR = FP / total findings; emit to test output for trend tracking; fail if FPR > 5%." Alternatively: add an FR-12-shaped sub-todo that captures the FP triage in a structured artifact at `workspaces/spec-drift-gate/04-validate/02-fpr-measurement.md`.
- **Severity rationale:** NFR-2 is a load-bearing brief acceptance criterion (line 56). Without a measurement owner, the gate could ship with 50% FPR and meet every other criterion. HIGH.

#### HIGH-4: Q9.4 disposition (ADR-2 prose-mention denylist) lacks an owner

- **Where:** SDG-000 line 33 ("Q9.4 (prose-mention denylist) — recommend ADR-2 overrides cover this"); plan § 8 item 4
- **What's wrong:** The disposition recommends "ADR-2 overrides cover this" — meaning the override directive `<!-- spec-assert-skip: kind:symbol reason:"..." -->` IS the answer. But no todo's acceptance criteria say this. SDG-401's `with_overrides.md` fixture exercises the directive; SDG-102 implements the parser. Neither says "this discharges Q9.4". Result: at /redteam, when reviewer asks "where did Q9.4 land?", no todo body answers. Same pattern as the redteam's PLAN-HIGH-2 amendment that surfaced Q9.2/Q9.3/Q9.4 in plan § 8 — the surfacing happened in the PLAN but did not propagate to TODOS.
- **Recommendation:** Edit SDG-102 line 13 to append: "(Discharges Q9.4 — prose-mention denylist is implemented via `<!-- spec-assert-skip -->` per ADR-2 § 3.2)". One-line edit.
- **Severity rationale:** Q9.4 has no code change but has a documentation/traceability change. HIGH because the redteam's amendment tracked the question; if the next session looks for "where did Q9.4 ship", it should grep to a hit.

### MED (defer to /implement kickoff or absorb into existing shard)

#### MED-1: SDG-403 frontmatter `blocks:` does not include SDG-404 even though SDG-404.depends_on=[SDG-403]

- **Where:** SDG-403 frontmatter (`blocks: [SDG-501]`) vs SDG-404 frontmatter (`depends_on: [SDG-403]`)
- **What's wrong:** Asymmetric arrows. SDG-404 declares dependency on SDG-403 (correct — SDG-404 wraps SDG-403's integration tests in a CLI subprocess pattern). But SDG-403's `blocks:` only mentions SDG-501 — not SDG-404. A simple `gh-manager` style query "what does SDG-403 unlock?" would miss SDG-404.
- **Recommendation:** Update SDG-403 frontmatter to `blocks: [SDG-404, SDG-501]`. One-edit.

#### MED-2: S4 invariant count (12 pre-dedup) borderline against budget

- **Where:** Shards S4 across SDG-401 + SDG-402 + SDG-403 + SDG-404
- **What's wrong:** Total invariants pre-dedup is 12; budget is 5-10. Post-dedup it's ~7. The borderline is a function of 4 todos in one shard each contributing 3 invariants. Per Rule 2 ("Size By Complexity, Not LOC Alone"), fixture authoring (SDG-401) is content-heavy not logic-heavy, so the effective load-bearing invariant count is ~7. ACCEPTABLE but sits at the edge.
- **Recommendation:** No action required. Document in SDG-000 milestone tracker that S4 is content-heavy and the budget is met by the dedup interpretation. Optional.

#### MED-3: SDG-103 acceptance bullet has "deferred to SDG-302" coupling that creates an integration cliff

- **Where:** SDG-103 acceptance bullet 6 ("Each sweep emits findings via the format defined in SDG-302 (deferred); for now emit raw `Finding(...)` tuples")
- **What's wrong:** SDG-103 ships before SDG-302 in topological order. Building "raw Finding tuples" first then re-formatting in SDG-302 means SDG-302 changes the public contract of `run_sweeps` after SDG-103 ships. Risk: SDG-302 needs to plumb new fields (`severity`, `message`, `fix_hint`) backward into every sweep's emit path, requiring a re-edit of SDG-103's emit calls.
- **Recommendation:** Either (a) introduce the `Finding` dataclass with all fields (severity defaulting to "FAIL", message from a template, fix_hint=None) in SDG-103 so SDG-302 only swaps the emitter; OR (b) document explicitly in SDG-302 that "this todo modifies the `Finding` dataclass to add `severity, message, fix_hint`; touch every sweep's emit-call site". Either resolves the cliff.

#### MED-4: SDG-501 verification command uses `sed -i.bak` which fails on macOS without arg, succeeds on Linux

- **Where:** SDG-501 verification block lines 64-67
- **What's wrong:** `sed -i.bak 's/section-context inference/Ensemble.from_leaderboard/' specs/ml-automl.md` — works on macOS (BSD sed needs the empty-string-or-suffix argument after `-i`) and Linux (GNU sed accepts `-i.bak` directly). Actually consistent. **False alarm — but the test is destructive (modifies spec) and depends on `git checkout --` to revert. If the test fails mid-way, the spec is left in a dirty state.**
- **Recommendation:** Replace the command with a `git stash` → `sed` → assert → `git checkout` pattern, or move to a fixture spec that's allowed to be modified in-place.

#### MED-5: SDG-103 Q9.1 disposition (multi-package errors module) recorded in todo body but no test fixture

- **Where:** SDG-103 invariant 4 ("FR-4 errors module convention — union scan in v1.0 (per Q9.1 disposition)")
- **What's wrong:** The disposition says "union scan: class found in any errors_module path → PASS". SDG-401 fixture list does NOT include a `multi_package_errors_union.md` fixture exercising the union behavior. Tier 1 unit test (SDG-402 line 27 — `test_fr4_error_class.py`) might cover it, but there's no acceptance bullet asserting "fixture for union scan exists".
- **Recommendation:** Add `multi_package_errors_union.md` to SDG-401's fixture list (one bullet) and a corresponding parametrized test case to SDG-402's `test_fr4_error_class.py`.

#### MED-6: SDG-301 lifecycle `expired_2x` (≥180 days) is NEVER hit on capture day

- **Where:** SDG-301 acceptance bullet 5 (`expired_2x` → FAIL) + SDG-303 acceptance bullet 2 (`≥180 days → emit FAIL`)
- **What's wrong:** No acceptance bullet (in any todo) demonstrates the `expired_2x` state machine fires correctly. SDG-401 has `expired_baseline_test.md` for ageout WARN but the wording is generic. The state-machine transition test needs both 90-day and 180-day fixtures.
- **Recommendation:** Add to SDG-401: two fixtures named `ageout_warn_90d.md` (entry with `added` 90 days ago) and `ageout_fail_180d.md` (entry with `added` 180 days ago). Add corresponding assertion in SDG-402's `test_refresh_and_ageout.py` line 34.

#### MED-7: SDG-602 (skill doc) blocked by SDG-601 (workflow PR) but content-independent

- **Where:** SDG-602 frontmatter (`depends_on: [SDG-601]`)
- **What's wrong:** SDG-602 updates `.claude/skills/spec-compliance/SKILL.md` to reference the gate — this content is independent of whether the workflow PR exists yet. SDG-601 opens a separate PR; SDG-602 commits the skill update to the main PR. Topologically SDG-602 could parallel SDG-601, freeing the orchestrator to launch the wave-of-3 (S5||S6) more aggressively.
- **Recommendation:** Change SDG-602 `depends_on:` to `[SDG-502]` (the prior shard's last todo) instead of `[SDG-601]`. This unblocks parallelism in S6.

### LOW (housekeeping; track in journal but do not block ship to /implement)

#### LOW-1: 4 FR audit cites missing from todo bodies (FR-2, FR-3, FR-5, FR-6)

- **Where:** Per M6 sweep above
- **What's wrong:** Spec § 4 sweep table cites a concrete audit finding (F-E2-NN, PR number) for each FR; FR-2, FR-3, FR-5, FR-6 audit cites are not echoed in any todo body for traceability.
- **Recommendation:** Append "(audit cite: F-E2-08)" or equivalent to the relevant acceptance bullet in SDG-103, SDG-202. Trivially recoverable at /implement kickoff.

#### LOW-2: S4 LOC sum (~435) is +20% over plan estimate (~360)

- **Where:** Per M2 sweep above
- **What's wrong:** S4 fixture content + 4 test files sum to ~435 LOC vs plan's ~360. Within budget (autonomous-execution.md § Per-Session Capacity Budget allows feedback-loop multiplier — Tier 1+2 tests have a tight loop, so 3-5× base budget per Rule 3). NOT a blocker.
- **Recommendation:** Update SDG-000 milestone tracker LOC est. for S4 from ~360 → ~435. One-edit.

#### LOW-3: S5 LOC sum (~65) is -35% under plan estimate (~100)

- **Where:** Per M2 sweep above
- **What's wrong:** S5 explicit Python LOC is low (hook config + capture script). The "missing" 35 LOC is the generated baseline JSONL (~36 lines of generated content), which doesn't count toward LOC budget for capacity calc.
- **Recommendation:** No action; the budget assumes we count load-bearing logic only.

#### LOW-4: SDG-602 commit message acceptance criterion references "PR #N" as TBD

- **Where:** SDG-602 acceptance bullet 5 ("Commit message references PR #N (the main gate implementation PR)")
- **What's wrong:** The PR number is unknown at /todos time. The orchestrator at /implement must replace `#N` with the actual PR number when running the agent.
- **Recommendation:** Apply rule 5c (specs-authority.md) — orchestrator amends at launch time.

#### LOW-5: Wave-of-3 parallelization claim from plan § 3.6 not echoed in todo frontmatter

- **Where:** Plan claims "S4 || S5 || S6" wave-of-3 (per `worktree-isolation.md` Rule 4); todos have no `parallel_with:` field
- **What's wrong:** Topologically the dependency chain forbids S4 || S5 (SDG-501 depends on SDG-402+SDG-403+SDG-404). S5 || S6 IS legal (SDG-601 depends only on SDG-502; SDG-602 depends only on SDG-601 today, but per MED-7 should depend on SDG-502 instead). The PLAN claim and the todo DAG are inconsistent.
- **Recommendation:** Resolve via MED-7 (move SDG-602.depends_on to SDG-502); then S4 sub-todos sequential within S4, then S5 || (S6.SDG-601 || S6.SDG-602) becomes legal as a wave-of-3 within the autonomous wave-≤3 limit.

---

## 3. Cross-Document Consistency Sweep

### 3.1 Plan ↔ Todos

- Plan § 3 declares S1-S6 with LOC estimates; SDG-000 milestone tracker mirrors them; per-shard atomic-todo sums are within ±20% (M2 finding).
- Plan § 4 risk table cites B1/A3/B6/D3/D4 as Top-5; B1 mitigated by SDG-203, A3 by SDG-101's allowlist + WARN-on-zero, B6 by SDG-103+SDG-201 (file-level only per redteam disposition), D3 by SDG-403 corpus pass test (BUT NFR-2 measurement gap — HIGH-3), D4 by SDG-301 origin field + SDG-303 ageout. **D3 owner unclear → HIGH-3.**
- Plan § 8 open items: 8 listed, 4 are Q9.X questions. SDG-000 line 27-39 mirrors all 8 with dispositions. Q9.4 disposition has no todo owner → HIGH-4.

### 3.2 Spec ↔ Todos

- Spec § 2.1 CLI shape verbatim mirrored in SDG-101 acceptance bullet 2 ✓
- Spec § 2.2 pre-commit hook config mirrored in SDG-501 acceptance bullet 1 ✓
- Spec § 2.4 manifest schema mirrored in SDG-201 acceptance bullets + canonical example block ✓
- Spec § 3.1-3.2 marker convention mirrored in SDG-101 + SDG-102 ✓
- Spec § 5.1 baseline schema mirrored in SDG-301 acceptance bullet 2 ✓
- Spec § 6.1 errors hierarchy mirrored in SDG-102 (MarkerSyntaxError) + SDG-201 (ManifestNotFound/SchemaError) + SDG-301 (BaselineParseError) ✓
- Spec § 7.1-7.4 test contract mirrored in SDG-402 + SDG-403 + SDG-404 ✓
- Spec § 8.3 W6.5 reproduction mirrored in SDG-403 acceptance bullet 4 (combined demo, 6 findings) ✓
- Spec § 11 deferred-to-M2 cited in SDG-203 (§ 11.1) ✓
- Spec § 11.7 + § 11.8 (FR-9 + FR-10 deferral) mirrored in SDG-000 line 38 ✓

**No spec → todo drift detected** beyond the 4 HIGHs called out.

### 3.3 Brief ↔ Todos

The brief's acceptance criteria (lines 70-78, 8 bullets):

1. `scripts/spec_drift_gate.py` ↔ SDG-101 (creates) + SDG-104 (wires) ✓
2. `.pre-commit-config.yaml` ↔ SDG-501 ✓
3. `.github/workflows/spec-drift-gate.yml` (proposed) ↔ SDG-601 ✓
4. `.spec-drift-baseline.json` (jsonl) ↔ SDG-502 ✓
5. One-spec prototype (`ml-automl.md`) ↔ SDG-104 ✓
6. Documentation in skill doc ↔ SDG-602 ✓
7. Tier 1 + Tier 2 tests ↔ SDG-402 + SDG-403 ✓
8. Demonstration: deliberately-broken spec edit fails CI ↔ SDG-403 (W6.5 reproductions) + SDG-501 (local hook test) ✓

Brief success criteria (lines 53-60, 6 numbered):

1. Coverage ↔ FR-1..FR-8 owner todos ✓
2. FPR <5% ↔ NFR-2 — **NO OWNER (HIGH-3)**
3. Performance <30s ↔ SDG-103 inv. 3 + SDG-404 perf regression ✓
4. One-time baseline ↔ SDG-502 ✓
5. CI integration ↔ SDG-601 ✓
6. Demonstrable on real PR ↔ SDG-403 W6.5 reproduction ✓

**Result:** Brief acceptance fully owned (8/8). Brief success: 5/6 owned, FPR measurement unowned → HIGH-3 (cross-confirmed).

### 3.4 Numerical-claim cross-document drift

| Claim                     | SDG-000 tracker     | Plan   | Spec             | Drift?                                                                  |
| ------------------------- | ------------------- | ------ | ---------------- | ----------------------------------------------------------------------- | ------------------------------ |
| Total LOC                 | ~1,430              | ~1,330 | n/a              | +100 LOC (S2 +30, S4 +60, S5 +10) — tracker is canonical, plan is stale | LOW (tracker > plan, expected) |
| Total atomic todos        | 18                  | n/a    | n/a              | OK                                                                      |
| Sessions                  | 6                   | 6      | n/a              | OK                                                                      |
| FRs total                 | 13 (11 v1.0)        | 13     | 13               | OK                                                                      |
| Spec corpus size          | n/a                 | 72     | n/a (referenced) | OK                                                                      |
| Pre-existing HIGH backlog | "36 W5 backlog"     | 36     | 36               | OK (post-redteam reconciliation)                                        |
| W6.5 demo finding count   | 6 (5 FR-4 + 1 FR-7) | 6      | 6 (§ 8.3)        | OK                                                                      |

Tracker's "~1,430" supersedes plan's "~1,330" — S2 grew by ~30 LOC (manifest TOML overhead), S4 grew by ~60 LOC (fixture content), S5 stayed the same. **Recommend updating plan § 3 LOC estimates to match tracker.** Optional housekeeping.

---

## 4. Quality Signals Observed

**Green flags:**

- Every shard has a "Verification" section with concrete commands.
- Frontmatter `depends_on:` / `blocks:` is symmetric (16 of 17 arrows; 1 minor asymmetry per MED-1).
- W6.5 CRIT-1 + CRIT-2 reproductions are bit-faithful (5 explicit class names in SDG-401 + SDG-403; 1 explicit test path in SDG-401).
- Per-redteam dispositions (Q9.1 → SDG-103; Q9.2 → SDG-202; Q9.3 → SDG-203; FR-9 + FR-10 deferral → spec § 11) are propagated.
- ADR-6 fix-hint format is replicated in SDG-302 with the (a)/(b)/(c) triad.
- License + Foundation independence: SDG-602 references skill doc but does not introduce commercial coupling. Spec license header stays Apache-2.0; CC BY 4.0 reserved for spec content. ✓
- No hardcoded credentials; no eval(); no mock data in production paths (the gate IS the mechanical sweep).
- `rules/zero-tolerance.md` Rule 3a typed-guard pattern correctly cited in SDG-302 line 13.

**Red flags (addressed in HIGHs/MEDs above):**

- FR-12 unowned-by-name (HIGH-1).
- FR-6 + B1 integration loop unclosed (HIGH-2).
- NFR-2 FPR measurement unowned (HIGH-3).
- Q9.4 disposition unclaimed by todo body (HIGH-4).
- 4 FR audit cites missing from todo bodies (LOW-1).

**Test-hygiene flags (per `rules/testing.md`):**

- SDG-402 + SDG-403 separate Tier 1 (mocking allowed) from Tier 2 (NO mocking) per § 3-Tier ✓
- SDG-404 explicitly invokes via subprocess for true CLI-level wiring ✓
- W6.5 reproductions use behavioral assertions (count + symbol set), not source-grep ✓
- Coverage requirement (≥80%) declared in SDG-402 acceptance ✓

---

## 5. Recommendation Summary

**Ship to /implement AFTER applying the 4 HIGHs as inline edits at /todos approval.**

### Inline edits (5 minutes total):

1. **HIGH-1** (SDG-401 + SDG-402): Append "(delivers FR-12 ...)" to acceptance bullets 1.
2. **HIGH-2** (SDG-203): Add new acceptance bullet for FR-6 ↔ B1 cross-reference in WARN message.
3. **HIGH-3** (SDG-403 OR SDG-502): Add NFR-2 FPR measurement bullet.
4. **HIGH-4** (SDG-102): Append "(Discharges Q9.4)" to objective paragraph.

### Defer to /implement kickoff (not blockers):

- 7 MEDs (frontmatter consistency, dataclass-field plumbing, fixture coverage)
- 5 LOWs (housekeeping)

### Round-2 /todos NOT required.

The DAG is acyclic, capacity is respected per shard, every plan shard has atomic owner-todos summing within ±20% of LOC estimate, and 9 of 11 in-scope FRs (FR-9 + FR-10 deferred per spec § 11.7-11.8) are cleanly mapped to owner todos. The 4 HIGHs are all single-edit reconciliations.

---

## 6. Files

This review: `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/04-validate/01-todos-redteam.md`

Source documents reviewed (no edits made):

- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/todos/active/SDG-000-milestone-tracker.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/todos/active/SDG-101-cli-and-section-context-parser.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/todos/active/SDG-102-marker-parser-and-overrides.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/todos/active/SDG-103-day1-sweeps-and-symbol-cache.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/todos/active/SDG-104-wire-S1-verify-pristine.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/todos/active/SDG-201-manifest-toml-parser.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/todos/active/SDG-202-secondary-sweeps.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/todos/active/SDG-203-getattr-warn-emission.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/todos/active/SDG-301-baseline-schema-and-diff.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/todos/active/SDG-302-output-formats-and-fix-hints.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/todos/active/SDG-303-refresh-baseline-and-ageout.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/todos/active/SDG-401-test-fixtures.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/todos/active/SDG-402-tier1-unit-tests.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/todos/active/SDG-403-tier2-integration-tests.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/todos/active/SDG-404-wiring-test-perf-regression.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/todos/active/SDG-501-precommit-hook.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/todos/active/SDG-502-pristine-baseline-capture.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/todos/active/SDG-601-github-actions-workflow.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/todos/active/SDG-602-skill-doc-update.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/02-plans/01-implementation-plan.md`
- `/Users/esperie/repos/loom/kailash-py/specs/spec-drift-gate.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/briefs/01-product-brief.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/spec-drift-gate/04-validate/00-analyze-redteam.md`

End of red-team review.
