# Round 8 Feasibility Audit

**Date:** 2026-04-21
**Persona:** Implementation Feasibility Auditor
**Scope:** 23 specs post Phase-H (15 core ml + 6 supporting + 2 Phase-E meta)
**Method:** Re-derived from scratch per `rules/testing.md` § Audit Mode; full-sibling sweep per `rules/specs-authority.md §5b` **extended with Vector 7** (EngineInfo.signatures per-engine method count) to verify Phase-H closure.

---

## Headline: 23/23 READY + 0 NEEDS-PATCH + 0 BLOCKED

**SECOND CONSECUTIVE CLEAN ROUND ACHIEVED.** 0 CRIT / 0 HIGH / 0 MED / 0 LOW open. Convergence confirmed across 7-of-8 personas that went clean in Round 7; Round 8 holds 23/23 READY. **2-consecutive-clean-rounds feasibility convergence criterion satisfied.**

Round-6 → Round-7 → Round-8 trajectory: (21 READY + 2 NEEDS-PATCH / 2 HIGH) → (23 READY / 0 HIGH) → (**23 READY / 0 HIGH / held**). Phase-H was narrow (2 one-line descriptive edits reconciling the "8 public methods per Decision 8" misattribution); it introduced zero new drift across the full 23-spec surface.

---

## Matrix

### Core 15 ml specs

| #   | Spec                    | Verdict   | Note                                                                                                                                                                                                                                                                      |
| --- | ----------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | ml-engines-v2           | **READY** | §15.8 `km.lineage` signature pinned (`tenant_id: str \| None = None`); §15.9 6-group `__all__` with Group 6 Engine Discovery; §18 checklist complete; 8-method MLEngine contract (§2.1 MUST 5) UNCHANGED by Phase-H                                                       |
| 2   | ml-engines-v2-addendum  | **READY** | §E1.1 = 18 engines; §E11.1 `EngineInfo`/`MethodSignature`/`ParamSpec`/`ClearanceRequirement`/`ClearanceLevel`/`ClearanceAxis`; **L505 signatures comment REWRITTEN by Phase-H H1**: "Per-engine public-method count — varies per §E1.1 (MLEngine=8, support engines 1-4)" |
| 3   | ml-tracking             | **READY** | 8 CREATE TABLE `_kml_*`; 1 legit `kml_experiment` at L684 rationalized                                                                                                                                                                                                    |
| 4   | ml-autolog              | **READY** | No DDL; `get_current_run()` accessor via ml-tracking §10.1                                                                                                                                                                                                                |
| 5   | ml-registry             | **READY** | §7.1 `artifact_uris: dict[str, str]` + §7.1.1 back-compat property + §7.1.2 Single-Format-Per-Row Invariant; DDL §5A.2 reconciled                                                                                                                                         |
| 6   | ml-serving              | **READY** | 3 DDL tables `_kml_*`; `allow_pickle=False` default                                                                                                                                                                                                                       |
| 7   | ml-feature-store        | **READY** | 4 DDL tables `_kml_*`; §10A.1 distinguishes `_kml_` system prefix from user-configurable `kml_feat_` (2 rationalized residuals)                                                                                                                                           |
| 8   | ml-drift                | **READY** | 4 DDL tables `_kml_*`                                                                                                                                                                                                                                                     |
| 9   | ml-automl               | **READY** | 1 DDL table `_kml_*`; ambient contextvar auto-wire                                                                                                                                                                                                                        |
| 10  | ml-backends             | **READY** | No DDL; `resolve_store_url` plumbed                                                                                                                                                                                                                                       |
| 11  | ml-diagnostics          | **READY** | 3 cross-refs to `_kml_metric`                                                                                                                                                                                                                                             |
| 12  | ml-dashboard            | **READY** | `km.lineage(run_id, tenant_id=<req-tenant>)` at L205 with default signature                                                                                                                                                                                               |
| 13  | ml-rl-core              | **READY** | SafetyFilter contract pinned                                                                                                                                                                                                                                              |
| 14  | ml-rl-algorithms        | **READY** | Dataclasses intact                                                                                                                                                                                                                                                        |
| 15  | ml-rl-align-unification | **READY** | Cross-framework bindings intact                                                                                                                                                                                                                                           |

### Supporting 6 integration specs

| #   | Spec                        | Verdict   | Note                                                                                                                                                                                                                                                                           |
| --- | --------------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 16  | pact-ml-integration         | **READY** | D/T/R axis binding to `ClearanceRequirement` intact                                                                                                                                                                                                                            |
| 17  | nexus-ml-integration        | **READY** | Channels wiring intact                                                                                                                                                                                                                                                         |
| 18  | kaizen-ml-integration       | **READY** | **§2.4.2 L172 signatures-row REWRITTEN by Phase-H H2**: "Per-engine public-method signatures — count varies per ml-engines-v2-addendum §E1.1 (MLEngine=8 per Decision 8 Lightning lock-in; support engines 1-4). NOT a fixed-8 invariant"; §2.4.2 imports match §E11.1 exports |
| 19  | align-ml-integration        | **READY** | 3 `kml_key` at L186-188 are Python variables, not DDL                                                                                                                                                                                                                          |
| 20  | kailash-core-ml-integration | **READY** | Lifecycle-helper accessors intact                                                                                                                                                                                                                                              |
| 21  | dataflow-ml-integration     | **READY** | Tenant + classification bindings intact                                                                                                                                                                                                                                        |

### Phase-E meta 2

| #   | Spec                      | Verdict   | Note                                                                                                      |
| --- | ------------------------- | --------- | --------------------------------------------------------------------------------------------------------- |
| 22  | ml-readme-quickstart-body | **READY** | Canonical Quick Start body references `result.artifact_uris` (plural dict); SHA-256 pinned to Tier-3 test |
| 23  | ml-index-amendments       | **READY** | `specs/_index.md` diff complete (183 LOC with rationale + row count)                                      |

---

## §5b sibling sweep (7 vectors)

### Vector 1 — RegisterResult field-shape

```bash
grep -rn 'RegisterResult' specs-draft/ supporting-specs-draft/ | wc -l
# → 35 hits across 5 files
```

All consumers read `RegisterResult.artifact_uris` (plural dict). Singular `artifact_uri` survives only as (a) DDL column in `_kml_model_versions`, (b) §7.1.1 back-compat `@property` shim (v1.x only, removed at v2.0), (c) unrelated drift column `reference_artifact_uri` in ml-drift. **Verdict: ZERO drift.**

### Vector 2 — ClearanceRequirement type-shape

`grep -rln 'ClearanceRequirement'` → 2 files: ml-engines-v2-addendum (definition at §E11.1 L488-492) + kaizen-ml-integration (import at L154-159 + table row at L171 + usage L193-202). Both use `Optional[tuple[ClearanceRequirement, ...]]` exactly. **Verdict: ZERO drift.**

### Vector 3 — `_kml_*` DDL prefix

Residual bare `kml_` hits (all rationalized):

- `ml-feature-store-draft.md: 2` — user-configurable `kml_feat_` per-tenant prefix at L69 + L556, distinguished from internal `_kml_*` in §10A.1
- `ml-tracking-draft.md: 1` — L684 `kml_experiment` is a Python module stem (leading `_` is reserved for private modules); physical table is `_kml_experiment`
- `align-ml-integration-draft.md: 3` — L186-188 `kml_key` are Python local variable names, not DDL

`grep -c '\bkml_agent_' supporting-specs-draft/kaizen-ml-integration-draft.md` → **0** (G1 closure holds).
`grep -c '_kml_agent_' supporting-specs-draft/kaizen-ml-integration-draft.md` → **8**.

**Verdict: ZERO drift.**

### Vector 4 — `km.lineage` signature (`tenant_id: str | None = None`)

4 canonical sites verified:

1. `ml-engines-v2-draft.md:2166-2172` — `async def lineage(..., tenant_id: str | None = None, max_depth: int = 10) -> LineageGraph`
2. `ml-engines-v2-draft.md:2262-2265` — module-level facade same signature
3. `ml-engines-v2-addendum-draft.md:418` — `km.lineage(..., tenant_id: str | None = None, max_depth=10)` prose recap
4. `ml-dashboard-draft.md:205` — consumer `km.lineage(run_id, tenant_id=<request-tenant>)` compatible with default

**Verdict: ZERO drift.**

### Vector 5 — "18 engines" vs "13 engines"

`18 engines` = canonical current (4+ anchors: §E1.1 totalizer L43, §E11.3 MUST 4 L602, §E13.1 end-to-end flow L646, kaizen-ml §2.4.8 L303).
`13 engines` = historical audit-label only, 3 origin-note hits (ml-automl L12, ml-feature-store L12, ml-drift L425). Not current claims.

**Verdict: ZERO drift.**

### Vector 6 — "five groups" vs "six groups"

6 matches all Group-6 positive (L2180 "six named groups", L2228 Group 5, L2233-2239 Group 6 Engine Discovery, L2255 eager import, L2485 §18 checklist, L2239 Group 1 vs Group 6 distinction). Zero `five groups` / `Groups 1-5` residue.

**Verdict: ZERO drift.**

### Vector 7 (NEW) — EngineInfo.signatures per-engine method count

Newly-introduced vector exercised across the 4 sites the Phase-H plan enumerated PLUS the full 23-spec sweep for any collision:

| Site | Location                                                            | Assertion                                                                                                                                                                                                                                             |
| ---- | ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | `ml-engines-v2-addendum-draft.md:505` (§E11.1 dataclass comment)    | **Phase-H H1 rewrite verified:** "Per-engine public-method count — varies per §E1.1 (MLEngine=8, support engines 1-4). Decision 8 is Lightning lock-in, NOT a method-count invariant. See §E11.3 MUST 4."                                             |
| 2    | `ml-engines-v2-addendum-draft.md:602` (§E11.3 MUST 4 test contract) | "…every `EngineInfo.signatures` tuple contains the per-engine public-method count specified in §E1.1 (varies per engine — MLEngine's 8-method surface per Decision 8 is a per-engine invariant, NOT a fixed '8 per engine' constraint across all 18)" |
| 3    | `ml-engines-v2-addendum-draft.md:22-43` (§E1.1 enumeration)         | 18-engine table + "Total: 18 engines" totalizer; Primary mutation methods column enumerates actual method counts per engine (MLEngine: 5 methods listed; TrainingPipeline: 1; ExperimentTracker: 3; etc.)                                             |
| 4    | `kaizen-ml-integration-draft.md:172` (§2.4.2 signatures row)        | **Phase-H H2 rewrite verified:** "Per-engine public-method signatures — count varies per `ml-engines-v2-addendum §E1.1` (MLEngine=8 per Decision 8 Lightning lock-in; support engines 1-4). NOT a fixed-8 invariant."                                 |

**Residual-drift sweep:**

```bash
grep -rn '8 public methods per Decision 8' specs-draft/ supporting-specs-draft/  # → 0 matches
grep -rn 'Eight public-method signatures' specs-draft/ supporting-specs-draft/    # → 0 matches
```

Both Round-7 offending strings eliminated.

**Coherence with MLEngine 8-method contract:** `grep 'eight-method\|8-method'` returns 17 hits; ALL are MLEngine-specific (§2.1 MUST 5 contract, `km.*` wrapper rationales, "no ninth method on MLEngine" rejections). None claim "8 methods per engine across all engines." Phase-H edits consistent with MLEngine's locked 8-method surface — they simply clarify the per-engine count varies for the 17 SUPPORT engines (which was always true per §E1.1's primary-methods column but was obscured by the descriptive comment at L505 and table-row at L172).

**Verdict: ZERO drift. Vector 7 clean on first sweep.**

---

## Phase-H closure verification

### H1 — `ml-engines-v2-addendum-draft.md` L505 dataclass comment rewrite

**Expected (Round-7 plan):**

> New: `# Per-engine public-method count — varies per §E1.1 (MLEngine=8, support engines 1-4). Decision 8 is Lightning lock-in, not a method-count invariant.`

**Actual (Round-8 verify):**

```
signatures: tuple[MethodSignature, ...]   # Per-engine public-method count — varies per §E1.1 (MLEngine=8, support engines 1-4). Decision 8 is Lightning lock-in, NOT a method-count invariant. See §E11.3 MUST 4.
```

Matches plan + adds a cross-ref to §E11.3 MUST 4 (the test-contract anchor). **H1 closed.**

### H2 — `kaizen-ml-integration-draft.md` L172 signatures-row purpose rewrite

**Expected (Round-7 plan):**

> New: `Per-engine public-method signatures — count varies per ml-engines-v2-addendum §E1.1 (MLEngine=8 per Decision 8 Lightning lock-in; support engines 1-4)`

**Actual (Round-8 verify):**

```
| `signatures` | `tuple[MethodSignature, ...]` | Per-engine public-method signatures — count varies per `ml-engines-v2-addendum §E1.1` (MLEngine=8 per Decision 8 Lightning lock-in; support engines 1-4). NOT a fixed-8 invariant. |
```

Matches plan + adds closing invariant clarification "NOT a fixed-8 invariant." **H2 closed.**

### Internal consistency (Phase-H introduced no new drift)

1. **§E11.1 L505 comment ↔ §E11.3 MUST 4 test contract** — Both describe the same per-engine-varying count rule; L505 references L602 explicitly. Consistent.
2. **kaizen-ml §2.4.2 L172 ↔ ml-engines-v2-addendum §E1.1** — L172 links directly to §E1.1 as the authority for the count. Consistent.
3. **MLEngine's 8-method surface (§2.1 MUST 5) ↔ Phase-H edits** — Phase-H PRESERVES the MLEngine=8 invariant (stated explicitly at both edited sites); it only clarifies that the OTHER 17 support engines have 1-4 methods each per §E1.1. No conflict with §2.1 MUST 5 which is MLEngine-scoped.
4. **Decision 8 attribution** — Phase-H correctly re-attributes Decision 8 as "Lightning lock-in" (matching ml-engines-v2-draft L489 "Lightning Hard Lock-In (Decision 8 — pinned)" and ml-rl-core-draft L12 "Decision 8 (Lightning lock-in)"). Zero residual "Decision 8 = 8 methods" conflation.

---

## Convergence assertion (2-consecutive-clean)

### Round-by-round feasibility dashboard

| Round | READY  | NEEDS-PATCH | BLOCKED | HIGH  | MED   | LOW   | Scope  | Status                                |
| ----- | ------ | ----------- | ------- | ----- | ----- | ----- | ------ | ------------------------------------- |
| 2b    | 4      | 11          | 0       | ?     | ?     | ?     | 15     | —                                     |
| 3     | 9      | 6           | 0       | ?     | ?     | ?     | 15     | —                                     |
| 4     | 17     | 4           | 0       | 5     | —     | —     | 21     | —                                     |
| 5     | 14     | 9           | 0       | 1     | 2     | 1     | 23     | —                                     |
| 6     | 21     | 2           | 0       | 2     | 0     | 0     | 23     | —                                     |
| 7     | **23** | **0**       | **0**   | **0** | **0** | **0** | **23** | **1st clean**                         |
| **8** | **23** | **0**       | **0**   | **0** | **0** | **0** | **23** | **2nd consecutive clean — CONVERGED** |

### Convergence satisfied

Feasibility is the **4th persona to achieve 2-consecutive-clean convergence** (joining Newbie UX [R6+R7], TBD re-triage [R4-R7], Spec-compliance [R6+R7]). Round 7 was the 1st clean feasibility round; Round 8 holds 23/23 READY with ZERO regressions and ZERO new drift introduced by Phase-H's narrow 2-line descriptive edit.

**Convergence exit criterion (2-consecutive-clean rounds) MET for feasibility persona.**

### Round-8 proof commands

```bash
# Phase-H H1 closure
grep -q 'Per-engine public-method count — varies per §E1.1' \
  workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-addendum-draft.md  # → exit 0 ✅

# Phase-H H2 closure
grep -q 'Per-engine public-method signatures — count varies per' \
  workspaces/kailash-ml-audit/supporting-specs-draft/kaizen-ml-integration-draft.md  # → exit 0 ✅

# Round-7 drift strings gone
test $(grep -rc '8 public methods per Decision 8' \
  workspaces/kailash-ml-audit/specs-draft/ \
  workspaces/kailash-ml-audit/supporting-specs-draft/ | awk -F: '{sum+=$2} END {print sum}') -eq 0  # → 0 ✅
test $(grep -rc 'Eight public-method signatures' \
  workspaces/kailash-ml-audit/specs-draft/ \
  workspaces/kailash-ml-audit/supporting-specs-draft/ | awk -F: '{sum+=$2} END {print sum}') -eq 0  # → 0 ✅

# Round-7 gates 1-7 still pass (feasibility regression guard)
test $(grep -c '\bkml_agent_' workspaces/kailash-ml-audit/supporting-specs-draft/kaizen-ml-integration-draft.md) -eq 0  # 0 ✅
test $(grep -c '_kml_agent_' workspaces/kailash-ml-audit/supporting-specs-draft/kaizen-ml-integration-draft.md) -ge 8   # 8 ✅
grep -q 'Single-Format-Per-Row Invariant' workspaces/kailash-ml-audit/specs-draft/ml-registry-draft.md                    # ✅
test $(grep -c 'engine\.lineage' workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-addendum-draft.md) -eq 0           # 0 ✅
test $(grep -l 'resolve_store_url' workspaces/kailash-ml-audit/specs-draft/*.md | wc -l) -ge 6                            # ≥6 ✅
grep -q 'class ClearanceRequirement' workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-addendum-draft.md              # ✅
grep -q 'artifact_uris: dict\[str, str\]' workspaces/kailash-ml-audit/specs-draft/ml-registry-draft.md                    # ✅
grep -q 'Total: 18 engines' workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-addendum-draft.md                       # ✅
```

---

## Readiness for /codify promotion

Feasibility persona holds ZERO open findings across two consecutive rounds. Spec surface is frozen on the feasibility axis — no further descriptive or structural edits required before `/codify` promotes `specs-draft/ml-*-draft.md` → `specs/ml-*.md` canonical. Downstream release path (7-package wave: kailash 2.9.0 + kailash-pact 0.10.0 + kailash-nexus 2.2.0 + kailash-kaizen 2.12.0 + kailash-align 0.5.0 + kailash-dataflow 2.1.0 + kailash-ml 1.0.0) unblocks on aggregate 8-persona clean — this feasibility audit contributes its clean signal.

---

## Absolute paths

- **This report:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-8-feasibility.md`
- **Prior round:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-7-feasibility.md`
- **Round-7 synthesis (Phase-H plan):** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-7-SYNTHESIS.md`
- **H1 target (closed):** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-addendum-draft.md` L505
- **H2 target (closed):** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/kaizen-ml-integration-draft.md` L172
- **Decisions:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/approved-decisions.md`
- **15 core specs:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-*.md`
- **6 supporting specs:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/*-ml-integration-draft.md`
- **2 Phase-E drafts:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-readme-quickstart-body-draft.md`, `.../ml-index-amendments-draft.md`

_End of round-8-feasibility.md. Author: Implementation Feasibility Auditor persona. 2026-04-21._
