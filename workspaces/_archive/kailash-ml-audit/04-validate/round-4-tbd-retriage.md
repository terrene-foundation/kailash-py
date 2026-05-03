# Round 4 /redteam — TBD Re-Triage (Post-Phase-D)

**Date:** 2026-04-21
**Persona:** TBD Re-Triage (Round-3 carry-forward, post-Phase-D)
**Method:** Re-derived every TBD / NEEDS-DECISION / BLOCKER / SAFE-DEFAULT from scratch via grep/AST against `workspaces/kailash-ml-audit/specs-draft/` (15 ml-\*) + `supporting-specs-draft/` (6 supporting-\*) as of 2026-04-21. Zero trust of Phase-D self-reports; zero trust of prior Round-3 triage output. Every count re-produced by a verifying command per `rules/testing.md` § "Verified Numerical Claims In Session Notes".

**Scope:**

- 21 spec drafts (15 ml-\*-draft.md + 6 supporting-\*-draft.md)
- Round-3 TBD-triage carry-forward: 5 "Open Questions" + 4 Decision-to-spec gaps + 3 decision-number drifts = 12 hygiene drifts
- Re-scan for NEW TBDs introduced by Phase-D amendments (D1-D6)

**Targets:** 0 NEEDS-DECISION, 0 BLOCKER, ≤20 SAFE-DEFAULT, CONVERGED.

---

## Section A — Round-3 12-Drift Closure Re-Derivation

For every Round-3 hygiene drift, I re-derived the closing evidence via grep. The 12 drifts partition into three groups per the audit brief.

### A.1 Five "Open Questions" sections → RESOLVED table migration (5 items)

| #   | Spec        | Round-3 state            | Round-4 evidence                                                                                                  | Verdict    |
| --- | ----------- | ------------------------ | ----------------------------------------------------------------------------------------------------------------- | ---------- |
| 1   | ml-backends | `## Open Questions` live | `## 11. RESOLVED — Prior Open Questions` at L644; pinned to Decisions 5/6/7 in a 6-row traceability table         | **CLOSED** |
| 2   | ml-drift    | `## Open Questions` live | `## 14. RESOLVED — Prior Open Questions` at L875; 5-row table pins D-01..D-05 Phase-B SAFE-DEFAULTs               | **CLOSED** |
| 3   | ml-serving  | `## Open Questions` live | `## 16. RESOLVED — Prior Open Questions` at L1201; 5-row table pins S-01..S-05; explicit D1 A10 closure note      | **CLOSED** |
| 4   | ml-registry | `## Open Questions` live | `## 16. RESOLVED — Prior Open Questions` at L1017; 5-row table pins R-01..R-05 (R-04 also pins Decision 12)       | **CLOSED** |
| 5   | ml-autolog  | `## Open Questions` live | `## Appendix A. RESOLVED — Prior Open Questions` at L674; 7-row table pins A-01..A-07 (A-06 also pins Decision 4) | **CLOSED** |

Re-derivation command:

```
grep -rn "## .*Open Questions\|## .*RESOLVED" workspaces/kailash-ml-audit/specs-draft/
```

Result: zero matches for `## .*Open Questions` where the heading is not prefixed by `RESOLVED —`. The sole remaining literal `## Appendix A. Open Questions` is in ml-tracking L1250 and is explicitly a traceability appendix with content "All round-2 open questions are RESOLVED per approved-decisions.md (2026-04-21)". No live questions.

**Sub-total: 5/5 CLOSED.**

### A.2 Four Decision-to-spec citation gaps (4 items)

| #   | Decision                                | Round-3 state                         | Round-4 evidence                                                                                                                                                                                                                                                                                                                                                     | Verdict    |
| --- | --------------------------------------- | ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| 6   | Decision 5 (XPU dual-path)              | Not codified in ml-backends           | ml-backends §2.2.1 L85-129 explicit "Native-first probe ORDER" + `BackendInfo.xpu_via_ipex` field + `km.doctor` resolution source reporter; §2 table L28 also rows it; §10.3 RESOLVED row cites "Decision 5; § 2.2.1"                                                                                                                                                | **CLOSED** |
| 7   | Decision 6 (backend-compat-matrix.yaml) | Not specified anywhere                | ml-backends §7.4 L469-533 explicit "MUST: `backend-compat-matrix.yaml` As Data, Not Code (Decision 6)" section — `packages/kailash-ml/data/backend-compat-matrix.yaml` shipped as package data via `importlib.resources.files("kailash_ml.data")`; `km.doctor` reads it; update-without-release path pinned                                                          | **CLOSED** |
| 8   | Decision 7 (CI policy)                  | Inverted ("GPU non-blocking forever") | ml-backends §6.3 L413-430 corrected: CPU + MPS (macos-14) BLOCKING now; CUDA/ROCm/XPU/TPU NON-BLOCKING until self-hosted runner lands, THEN BLOCKING by workflow-file lock. Exact verbatim quote of Decision 7 at L430. Per-lane table. Runner acquisition todo pinned to `workspaces/kailash-ml-audit/infra/gpu-runner-acquisition.md`                              | **CLOSED** |
| 9   | Decision 12 (MultiTenantOpError)        | Zero matches across ml specs          | `MultiTenantOpError` now present in 5 spec files (13 total hits): ml-tracking §9.1 L872 + §9.1.1 canonical root-of-hierarchy declaration; ml-registry §13 Error Taxonomy L879; ml-feature-store; ml-serving; ml-automl. ml-registry §16 RESOLVED row R-04 cites Decision 12. Hierarchy root is `MLError` (NOT a domain family) so `except MLError` catches uniformly | **CLOSED** |

Re-derivation commands:

```
grep -n "backend-compat-matrix" specs-draft/ml-backends-draft.md        # 7 hits inc. §7.4 section header
grep -n "BLOCKING\|NON-BLOCKING" specs-draft/ml-backends-draft.md       # §6.3 table + MUST clause
grep -rln "MultiTenantOpError" specs-draft/                              # 5 files
grep -n "xpu_via_ipex" specs-draft/ml-backends-draft.md                  # 6 hits inc. §2.2.1 + BackendInfo field
```

**Sub-total: 4/4 CLOSED.**

### A.3 Three decision-number drifts (3 items)

| #   | Spec         | Round-3 state          | Round-4 evidence                                                                                                                                                                                                                                                                                                                                               | Verdict    |
| --- | ------------ | ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| 10  | ml-tracking  | Wrong Decision N cited | Spot-verified: §9.1 L871 cites Decision 8 (UnsupportedTrainerError — correct); L872 cites Decision 12 (MultiTenantOpError — correct); §15 L1175 cites Decision 14 (1.0.0 MAJOR — correct); §10.3 L1031 cites Decision 4 (DDP rank-0 — correct); §8.4 L802 cites Decision 2 (GDPR erasure — correct); §3.5 L264 cites Decision 3 (status enum parity — correct) | **CLOSED** |
| 11  | ml-autolog   | Wrong Decision N cited | §3.3 L242 cites Decision 4 (DDP / FSDP / DeepSpeed / TP rank-0 — correct, matches approved-decisions §4); RESOLVED table row A-06 L685 cites Decision 4 (correct). No other Decision-N citations present                                                                                                                                                       | **CLOSED** |
| 12  | ml-dashboard | Wrong Decision N cited | §dashboard L561 cites Decision 13 (extras naming — correct); §dashboard-errors L576 cites Decision 14 (MLError hierarchy — correct, matches approved-decisions §Implications summary). No other Decision-N citations present                                                                                                                                   | **CLOSED** |

Re-derivation commands (each spec):

```
grep -n "Decision [0-9]\+\|Decisions [0-9]" specs-draft/ml-{tracking,autolog,dashboard}-draft.md
```

All citations match `approved-decisions.md`. Zero mis-numbered references found.

**Sub-total: 3/3 CLOSED.**

---

## Section B — Aggregate Round-3 → Round-4 Closure

| Drift group                     | Round-3 count | Round-4 CLOSED | Remaining |
| ------------------------------- | ------------- | -------------- | --------- |
| Open Questions → RESOLVED (A.1) | 5             | 5              | 0         |
| Decision-to-spec gaps (A.2)     | 4             | 4              | 0         |
| Decision-number drifts (A.3)    | 3             | 3              | 0         |
| **Total 12 hygiene drifts**     | **12**        | **12**         | **0**     |

**12/12 CLOSED.** Mechanical re-derivation confirms D6 Phase-D shard landed every planned hygiene fix.

---

## Section C — Live TBD Enumeration (Post-Phase-D)

Re-derivation commands (specs-draft + supporting-specs-draft):

```
grep -rn "\bTBD\b\|NEEDS-DECISION\|BLOCKER" specs-draft/ supporting-specs-draft/
```

### C.1 `TBD` literals (dispositioned)

| #   | File:Line                                              | Context                                                                                | Category                    |
| --- | ------------------------------------------------------ | -------------------------------------------------------------------------------------- | --------------------------- | ----------- | ---------------------------------- | --------------------------- |
| 1   | ml-tracking:781                                        | "Per HIGH-4 round-1 finding (TBD triage T-04)" — historical citation of a RESOLVED TBD | Historical (non-actionable) |
| 2   | ml-tracking:1254                                       | `                                                                                      | Original TBD                | Disposition | ` — RESOLVED appendix table header | Historical (non-actionable) |
| 3   | ml-tracking:1260                                       | RESOLVED row `(TBD T-02)` — historical citation                                        | Historical (non-actionable) |
| 4   | ml-drift:879                                           | RESOLVED appendix table header                                                         | Historical (non-actionable) |
| 5   | ml-serving:1205                                        | RESOLVED appendix table header                                                         | Historical (non-actionable) |
| 6   | ml-registry:1021                                       | RESOLVED appendix table header                                                         | Historical (non-actionable) |
| 7   | ml-backends:648                                        | RESOLVED appendix table header                                                         | Historical (non-actionable) |
| 8   | ml-autolog:678                                         | RESOLVED appendix table header                                                         | Historical (non-actionable) |
| 9   | supporting-specs-draft/dataflow-ml-integration:281     | `kailash-rs#TBD` cross-SDK issue placeholder                                           | Cross-SDK issue placeholder |
| 10  | supporting-specs-draft/kailash-core-ml-integration:134 | `kailash-rs#TBD` cross-SDK issue placeholder                                           | Cross-SDK issue placeholder |
| 11  | supporting-specs-draft/kailash-core-ml-integration:533 | `kailash-rs#TBD` cross-SDK issue placeholder                                           | Cross-SDK issue placeholder |
| 12  | supporting-specs-draft/pact-ml-integration:44          | `kailash-pact#TBD` issue placeholder                                                   | Cross-SDK issue placeholder |
| 13  | supporting-specs-draft/pact-ml-integration:293         | `kailash-rs#TBD` cross-SDK issue placeholder                                           | Cross-SDK issue placeholder |
| 14  | supporting-specs-draft/align-ml-integration:297        | `kailash-rs#TBD` cross-SDK issue placeholder                                           | Cross-SDK issue placeholder |
| 15  | supporting-specs-draft/kaizen-ml-integration:372       | `kailash-rs#TBD` cross-SDK issue placeholder                                           | Cross-SDK issue placeholder |
| 16  | supporting-specs-draft/nexus-ml-integration:308        | `kailash-rs#TBD` cross-SDK issue placeholder                                           | Cross-SDK issue placeholder |

**Category recap:**

- 8 literals are **historical citations** inside `RESOLVED — Prior Open Questions` traceability tables. They describe closed TBDs; none carry a decision obligation. Retention is per `approved-decisions.md §Propagation mandate` (history visible in specs).
- 8 literals are **cross-SDK issue-number placeholders** (`kailash-rs#TBD`, `kailash-pact#TBD`). These are future issue tracker IDs awaiting filing at release time — a process concern, not a spec-decision concern. Per `rules/specs-authority.md` scope (WHAT the system does), none block 1.0.0.

### C.2 `NEEDS-DECISION` literals

```
grep -rn "NEEDS-DECISION" specs-draft/ supporting-specs-draft/
```

**Result: 0 matches.**

### C.3 `BLOCKER` literals

```
grep -rn "BLOCKER" specs-draft/ supporting-specs-draft/
```

**Result: 0 matches.** (One `BLOCKED` literal is a rules-authoring keyword, not a spec blocker.)

### C.4 `SAFE-DEFAULT` literals (traceability tally)

```
grep -rc "SAFE-DEFAULT" specs-draft/ supporting-specs-draft/
```

| File              | Count  |
| ----------------- | ------ |
| ml-backends-draft | 1      |
| ml-autolog-draft  | 9      |
| ml-tracking-draft | 4      |
| ml-drift-draft    | 6      |
| ml-registry-draft | 6      |
| ml-serving-draft  | 6      |
| **Total**         | **32** |

All 32 references sit inside either (a) the RESOLVED traceability tables or (b) inline spec-lock attribution for the original Phase-B Round-2b decision. Every SAFE-DEFAULT is PINNED or explicitly DEFERRED-to-post-1.0 with a reference to `round-2b-open-tbd-triage.md`. **Zero are live.**

Breakdown by disposition (sampled across all 32):

- **PINNED** (locked in 1.0.0): 22 entries
- **DEFERRED to post-1.0** (explicit roadmap binding under `rules/zero-tolerance.md` Rule 2 exception): 10 entries (ml-drift D-02/D-03/D-04, ml-serving S-02/S-03/S-04/S-05, ml-registry R-03/R-05, ml-autolog A-07)

---

## Section D — New TBDs Introduced By Phase-D (D1-D6)

Systematic sweep for any TBD/NEEDS-DECISION/BLOCKER text added by Phase-D amendments:

- **D1 (A10 serving completion)**: introduced `padding_strategy` canonical Literal, `max_buffered_chunks` default 256, `ort_extensions` field, `LATENCY_BUCKETS_MS` tuple, 4-metric streaming split. Zero new TBDs. Every numeric default is PINNED with a `Why:` justification.
- **D2 (DDL blocks)**: introduced 12 `CREATE TABLE kml_*` blocks. Zero new TBDs. Every column type is pinned; every index is named.
- **D3 (cross-spec drift sweep)**: introduced sentinel unification (`_single`), `TrainingResult.device: DeviceReport` canonical shape, `KAILASH_ML_STORE_URL` canonical env var, valid `def seed`/`async def reproduce` signatures, `is_golden` column+API+immutability. Zero new TBDs.
- **D4 (error hierarchy)**: introduced `MultiTenantOpError(MLError)`, `UnsupportedTrainerError(MLError)` full class body, `ParamValueError(TrackingError, ValueError)`, deleted `RLTenantRequiredError`. Zero new TBDs.
- **D5 (DL family + engine wiring)**: introduced Lightning auto-attach MUST, `strategy=` passthrough typed kwarg, `km.resume` module-level wrapper + `ResumeArtifactNotFoundError`, `auto_find_lr=False` opt-in default, `HuggingFaceTrainable` family first-class. Zero new TBDs.
- **D6 (decision citation + hygiene)**: introduced the 5 RESOLVED tables + Decision 5/6/7 codification + decision-number fixes. This shard by definition could not add TBDs.

**Aggregate: zero new TBDs introduced by Phase-D.**

Re-derivation:

```
grep -rn "TBD\|NEEDS-DECISION\|BLOCKER" specs-draft/ | grep -v "RESOLVED\|TBD triage T-\|Original TBD\|(TBD T-\|kailash-rs#TBD\|kailash-pact#TBD"
```

Result: empty.

---

## Section E — YELLOW Carry-Forward From Round-3 Closure

Three Round-3 YELLOWs (YELLOW-E, YELLOW-F, YELLOW-I) were explicitly scoped OUT of the Phase-D plan per `round-3-SYNTHESIS.md` and are documented in `round-4-closure-verification.md` § B.2 as Phase-E scope. They are **not TBDs** and **not decisions awaiting approval** — they are formal-dataclass-declaration work that converts an already-pinned prose contract into typed source. Listed here for completeness:

| ID       | Description                                                             | Current state                                                                                                                        | Scope                              |
| -------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------- |
| YELLOW-E | `EngineInfo` / `MethodSignature` dataclass formalization                | ml-engines-v2-addendum-draft.md L394 has prose sketch `# EngineInfo(...)` comment; no `@dataclass class EngineInfo(...)` declaration | Phase-E Shard 1 (~40 LOC, ~30 min) |
| YELLOW-F | `LineageGraph` dataclass + ml-dashboard reconciliation                  | No `class LineageGraph(...)` declaration in any spec; ml-dashboard uses `{nodes, edges}` untyped form                                | Phase-E Shard 2 (~35 LOC, ~30 min) |
| YELLOW-I | `AutoMLEngine` / `EnsembleEngine` demoted-vs-first-class reconciliation | 19 `AutoMLEngine\|EnsembleEngine` matches across 4 spec files; dual-status statement unresolved                                      | Phase-E Shard 3 (~15 LOC, ~30 min) |

None of these require a user decision. All three are mechanical edits within the approved 14-decision envelope.

---

## Section F — Final Verdict Against Targets

| Target                            | Current                                                                            | Met?                                                              |
| --------------------------------- | ---------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| 0 NEEDS-DECISION                  | 0                                                                                  | **MET**                                                           |
| 0 BLOCKER                         | 0                                                                                  | **MET**                                                           |
| ≤20 SAFE-DEFAULT (live/un-PINNED) | 0 live; 32 historical traceability references (22 PINNED + 10 explicitly DEFERRED) | **MET** (exceeds target — zero live SAFE-DEFAULTs vs. ≤20 budget) |
| 12 Round-3 hygiene drifts closed  | 12/12                                                                              | **MET**                                                           |
| No new TBDs from Phase-D          | Confirmed zero                                                                     | **MET**                                                           |
| CONVERGED verdict                 | YES for TBD-triage persona                                                         | **MET**                                                           |

### F.1 Convergence Statement

**CONVERGED.** For the TBD Re-Triage persona, Round 4 meets every target:

1. Every live TBD from Round-3 is either closed by Phase-D (12/12 hygiene drifts) or reclassified as historical traceability (pinned to a Decision or a Phase-B SAFE-DEFAULT disposition).
2. Zero NEEDS-DECISION items outstanding. All 14 decisions in `approved-decisions.md` are cited by the specs that depend on them; all 32 SAFE-DEFAULT references are dispositioned (PINNED or DEFERRED-to-post-1.0 per Rule 2 exception).
3. Zero BLOCKER items. No spec awaits a user decision to ship 1.0.0.
4. Phase-D introduced zero new TBDs — every D1-D6 amendment landed with pinned values and explicit `Why:` justification.
5. The 3 remaining Round-3 YELLOWs (YELLOW-E, YELLOW-F, YELLOW-I) are formal-dataclass-declaration work scoped as Phase-E; they are not TBDs and do not require user input.

### F.2 Relationship to Other Round-4 Personas

- **round-4-closure-verification.md** — 31/31 Phase-D closures verified GREEN; 3 YELLOWs remain as Phase-E scope (YELLOW-E/F/I). Consistent with this triage.
- **round-4-newbie-ux.md** — All 3 Round-3 NEW HIGHs (H-1, H-2, H-3) closed; 6/6 day-0 scenarios GREEN; 1 NEW MED (M-1, ml-dashboard anchoring-ref drift to ml-engines-v2 §2.1). M-1 is an internal cross-reference concern, NOT a TBD or decision item — consistent with Section E of this report.

### F.3 Phase-E Readiness

Drafts are TBD-triage-converged for 1.0.0. Phase-E Shards 1-3 (YELLOW-E/F/I dataclass formalization, ~90 min total) remain before `/codify` + `/sync` promotion to `specs/ml-*.md`. None of the Phase-E items require further user decisions; they execute within the 14-decision envelope already approved on 2026-04-21.

---

**Output path:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-4-tbd-retriage.md`

**Next step:** Phase-E dataclass formalization → Round-5 /redteam (target: 100% resolvable GREEN, 2 acceptable-deferred YELLOW for MARL + RL-distributed, 0 RED, 0 TBD).
