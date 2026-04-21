# Round 8 Closure Verification

**Date:** 2026-04-21
**Persona:** Round-8 Closure Verifier (post Phase-H merge)
**Scope:** 22 Phase-F + Phase-G items + 2 Phase-H items = **24 checks**. All re-derived from scratch against the current spec tree. Round-7 outputs NOT trusted (audit-mode, `rules/testing.md § Audit Mode`).

## Headline: 24/24 GREEN + 0 RED + 0 HIGH

**Second consecutive clean closure round.** Every Phase-F, Phase-G, and Phase-H closure item reproduces against a literal `grep` on the current spec state. Phase-H's sibling-consistency assertion (method count varies per engine, per §E1.1; MLEngine=8 per Decision 8 as a per-engine invariant) holds across all four locations.

---

## Per-item table

| #      | Phase / ID                                                                     | Command                                                                                                               | Expected | Actual                               | Verdict   |
| ------ | ------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- | -------- | ------------------------------------ | --------- |
| 1      | F1 `[^_]kml_(run\|metric\|agent)` residual                                     | `rg '[^_]kml_(run\|metric\|agent)' specs-draft/ supporting-specs-draft/`                                              | 0        | **0**                                | **GREEN** |
| 2      | F1 `CREATE TABLE _kml_` DDL count                                              | `rg 'CREATE TABLE.*_kml_' specs-draft/ supporting-specs-draft/ \| count`                                              | ≥24      | **26** (24 ml-\* + 2 kaizen-ml)      | **GREEN** |
| 2b     | F1 bare `CREATE TABLE kml_` DDL                                                | `rg 'CREATE TABLE.*[^_]kml_' specs-draft/ supporting-specs-draft/`                                                    | 0        | **0**                                | **GREEN** |
| 3      | F1 bare `kml_[a-z]` residual                                                   | `rg '\bkml_[a-z]' specs-draft/ supporting-specs-draft/`                                                               | 0 drift  | **6 hits — all legitimate**¹         | **GREEN** |
| 4      | F2 `resolve_store_url` plumbing                                                | `rg -l 'resolve_store_url' specs-draft/ supporting-specs-draft/`                                                      | 6        | **6** (all in specs-draft/)          | **GREEN** |
| 5      | F3 `artifact_uris: dict[str, str]`                                             | `rg 'artifact_uris: dict\[str, str\]' specs-draft/ml-registry-draft.md`                                               | present  | **L424 + L490**                      | **GREEN** |
| 6      | F3 §7.1.1 back-compat shim                                                     | `rg '^#### 7\.1\.1' specs-draft/ml-registry-draft.md`                                                                 | present  | **L455**                             | **GREEN** |
| 7      | F3 `onnx_status: Optional[Literal`                                             | `rg 'onnx_status: Optional\[Literal' specs-draft/ml-registry-draft.md`                                                | present  | **L236 + L436**                      | **GREEN** |
| 8      | F4 kaizen-ml §2.4 heading                                                      | `rg '^### 2\.4' supporting-specs-draft/kaizen-ml-integration-draft.md`                                                | present  | **L126 `### 2.4 Agent Tool…`**       | **GREEN** |
| 9      | F4 `km.engine_info`/`km.list_engines` refs                                     | `rg -c 'km\.engine_info\|km\.list_engines' supporting-specs-draft/kaizen-ml-integration-draft.md`                     | ≥11      | **11**                               | **GREEN** |
| 10     | F5 km.lineage `tenant_id: str \| None = None`                                  | `rg 'tenant_id: str \| None = None' specs-draft/ml-engines-v2-draft.md specs-draft/ml-engines-v2-addendum-draft.md`   | both     | **engines-v2 L2169 + addendum L418** | **GREEN** |
| 11     | F5 YELLOW-G `engine.lineage(` anti-pattern                                     | `rg 'engine\.lineage\(' specs-draft/ml-engines-v2-addendum-draft.md`                                                  | 0        | **0**                                | **GREEN** |
| 12     | F5 YELLOW-H Group 6 in `__all__`                                               | `rg 'Group 6' specs-draft/ml-engines-v2-draft.md`                                                                     | present  | **L2180 + L2233 + L2239 + L2485**    | **GREEN** |
| 13     | F6 `class ClearanceRequirement`                                                | `rg 'class ClearanceRequirement' specs-draft/ml-engines-v2-addendum-draft.md`                                         | present  | **L489**                             | **GREEN** |
| 14     | F6 ml-serving Decision 8 ↔ §2.5.3 citation                                     | `rg 'Decision 8.*§2\.5\.3' specs-draft/ml-serving-draft.md`                                                           | present  | **L1191**                            | **GREEN** |
| 15     | F6 lineage eager-import in §15.9                                               | `rg 'from kailash_ml\.engines\.lineage' specs-draft/ml-engines-v2-draft.md`                                           | present  | **L2254 + L2482**                    | **GREEN** |
| 16     | G1 kaizen-ml `[^_]kml_agent_` residual                                         | `rg '[^_]kml_agent_' supporting-specs-draft/kaizen-ml-integration-draft.md`                                           | 0        | **0**                                | **GREEN** |
| 17     | G2 kaizen-ml §2.4.2 `Optional[tuple[ClearanceRequirement`                      | `rg 'Optional\[tuple\[ClearanceRequirement' supporting-specs-draft/kaizen-ml-integration-draft.md`                    | present  | **L171**                             | **GREEN** |
| 18     | G3a ml-registry §7.1.2 single-format invariant                                 | `rg '^#### 7\.1\.2' specs-draft/ml-registry-draft.md`                                                                 | present  | **L488**                             | **GREEN** |
| 19     | G3b approved-decisions.md `_kml_` prefix                                       | `rg 'Postgres tables use' 04-validate/approved-decisions.md`                                                          | `_kml_`  | **L31 — `_kml_` present**            | **GREEN** |
| 20     | G3c ml-engines-v2 "six named groups"                                           | `rg 'six named groups' specs-draft/ml-engines-v2-draft.md`                                                            | present  | **L2180**                            | **GREEN** |
| 21     | G3c Group 6 eager-import `engine_info, list_engines`                           | `rg 'engine_info, list_engines' specs-draft/ml-engines-v2-draft.md`                                                   | present  | **L2255**                            | **GREEN** |
| 22     | G3d addendum §E11.3 MUST 4 "18 engines"                                        | `rg 'all \*\*18 engines\*\*\|18 engines \(MLEngine' specs-draft/ml-engines-v2-addendum-draft.md`                      | present  | **L602**                             | **GREEN** |
| **23** | **H1 — old "8 public methods per Decision 8" comment REMOVED**                 | `rg -c '8 public methods per Decision 8' specs-draft/ml-engines-v2-addendum-draft.md`                                 | **0**    | **0**                                | **GREEN** |
| **24** | **H1 — new "Per-engine public-method count" comment PRESENT**                  | `rg -c 'Per-engine public-method count' specs-draft/ml-engines-v2-addendum-draft.md`                                  | **1**    | **1 (L505)**                         | **GREEN** |
| **25** | **H2 — old "Eight public-method signatures (Decision 8 lock-in)" row REMOVED** | `rg -c 'Eight public-method signatures \(Decision 8 lock-in\)' supporting-specs-draft/kaizen-ml-integration-draft.md` | **0**    | **0**                                | **GREEN** |
| **26** | **H2 — new "Per-engine public-method signatures" row PRESENT**                 | `rg -c 'Per-engine public-method signatures' supporting-specs-draft/kaizen-ml-integration-draft.md`                   | **1**    | **1 (L172)**                         | **GREEN** |

(Table carries 26 rows matching 24 unique checks; items 2 + 2b are complementary sub-assertions of F1; items 23-26 are the 4 mechanical sub-asserts of the 2 Phase-H edits.)

¹ Item 3 legitimate non-drift hits (re-verified against Round-6 §A.4 + Round-7 audit):

- `ml-tracking-draft.md:684` — Python migration filename stem (`0001_create_kml_experiment.py`); module name cannot start with `_`; physical table remains `_kml_experiment`.
- `ml-feature-store-draft.md:69` — documents deprecated v0.9.x `table_prefix="kml_feat_"` API removal (historical reference).
- `ml-feature-store-draft.md:556` — design doc explicitly distinguishing internal `_kml_` vs user-configurable `kml_feat_` prefix.
- `align-ml-integration-draft.md:186-188` — Python local variable `kml_key` in a metric-name mapping (not a table).

All four categories re-verified 2026-04-21. No regressions vs Round 7.

---

## Phase-H Sibling-Consistency Check

The Phase-H edits touched 2 of 4 canonical locations where the per-engine method count is described. Round-8 MUST verify all 4 agree:

| #   | Location                                                      | Content (re-read 2026-04-21)                                                                                                                                                                                                                                                                             |
| --- | ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `ml-engines-v2-addendum-draft.md:505` (EngineInfo.signatures) | "Per-engine public-method count — **varies per §E1.1** (MLEngine=8, support engines 1-4). Decision 8 is Lightning lock-in, NOT a method-count invariant. See §E11.3 MUST 4."                                                                                                                             |
| 2   | `ml-engines-v2-addendum-draft.md:602` (§E11.3 MUST 4)         | "…every `EngineInfo.signatures` tuple contains the **per-engine public-method count specified in §E1.1** (varies per engine — MLEngine's 8-method surface per Decision 8 is a per-engine invariant, NOT a fixed '8 per engine' constraint across all 18)."                                               |
| 3   | `ml-engines-v2-addendum-draft.md:18-43` (§E1.1 enumeration)   | 18 engines with per-row "Primary mutation methods audited" column: MLEngine lists 5 mutation methods; ModelRegistry lists 4; Preprocessing lists 2; etc. — confirms counts **vary per engine**. MLEngine's 8-method public surface (Decision 8) is the Lightning lock-in invariant, not a universal one. |
| 4   | `kaizen-ml-integration-draft.md:172` (§2.4.2 signatures row)  | "Per-engine public-method signatures — count varies per `ml-engines-v2-addendum §E1.1` (MLEngine=8 per Decision 8 Lightning lock-in; support engines 1-4). NOT a fixed-8 invariant."                                                                                                                     |

**Consistency verdict: CONSISTENT.** All four locations state the same invariant with identical semantics (count varies, MLEngine=8 is Lightning-lock-in-specific, not a universal constraint).

**Stale-claim sweep:** `rg '13 engines|8 public methods per engine|8 per engine.*invariant|Eight public-method signatures'` returns zero hits in specs-draft + supporting-specs-draft for claim prose (3 residual hits for "13/13 engines" are legitimate round-1 historical-origin references in drift/feature-store origin prose — not active claims).

---

## Convergence Assertion (2-consecutive-clean cross-spec + closure)

Round-7 achieved the first clean closure round (22/22 GREEN). Round-8 holds 22/22 + verifies 2 Phase-H items → **24/24 GREEN with zero regressions**. Per Round-6 SYNTHESIS line 92 ("2 consecutive clean rounds required for convergence"):

- **Closure-verification dimension:** Round-7 clean (22/22) + Round-8 clean (24/24) = **2 consecutive clean rounds** ✅
- **Cross-spec-consistency dimension:** Phase-H sibling check above (4/4 locations consistent) = clean ✅
- **Full-sibling re-derivation (`rules/specs-authority.md §5b`):** Phase-H edited 2 spec locations; Round-8 re-verified against the full ml-\* + kaizen-ml sibling set including §E1.1 enumeration and §E11.3 MUST 4 clause. No cross-spec drift detected.

**Convergence verdict: CONVERGED.** The `specs-draft/` + `supporting-specs-draft/` ontology is now self-consistent, internally grep-verifiable, and stable across two consecutive audit rounds. The audit is complete; Phase-I ("promote drafts to canonical specs") is unblocked.

---

## Open Items

**Zero.** No Phase-H items regressed, no Phase-F/G items regressed, no new observations from the 24-item audit. The out-of-scope observation flagged in Round-7 (kaizen-ml §2.4.2 L172 row) has been addressed by Phase-H H2 and re-verified GREEN in item #26.

---

## Mechanical Verification Log

All 24 counts in this report were produced by live `Grep` (ripgrep) against `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/` at audit time (2026-04-21). No trust in Round-7 outputs — every check re-executed. Key commands:

```bash
# Items 1-4: kml_ prefix unification + store-url plumbing (re-verified)
rg '[^_]kml_(run|metric|agent)' specs-draft/ supporting-specs-draft/          # 0 + 0
rg 'CREATE TABLE.*_kml_' specs-draft/ supporting-specs-draft/                 # 24 + 2 = 26
rg 'CREATE TABLE.*[^_]kml_' specs-draft/ supporting-specs-draft/              # 0 + 0
rg '\bkml_[a-z]' specs-draft/ supporting-specs-draft/                         # 3 + 3 = 6 legitimate
rg -l 'resolve_store_url' specs-draft/ supporting-specs-draft/                # 6 + 0

# Items 5-15: Phase-F RegisterResult / kaizen-ml / km.lineage / addendum
rg 'artifact_uris: dict\[str, str\]' specs-draft/ml-registry-draft.md         # L424, L490
rg '^#### 7\.1\.1' specs-draft/ml-registry-draft.md                           # L455
rg 'onnx_status: Optional\[Literal' specs-draft/ml-registry-draft.md          # L236, L436
rg '^### 2\.4' supporting-specs-draft/kaizen-ml-integration-draft.md          # L126
rg -c 'km\.engine_info|km\.list_engines' supporting-specs-draft/kaizen-ml-integration-draft.md  # 11
rg 'tenant_id: str \| None = None' ml-engines-v2-draft.md ml-engines-v2-addendum-draft.md  # both hit
rg 'engine\.lineage\(' specs-draft/ml-engines-v2-addendum-draft.md            # 0
rg 'Group 6' specs-draft/ml-engines-v2-draft.md                               # 4 hits
rg 'class ClearanceRequirement' specs-draft/ml-engines-v2-addendum-draft.md   # L489
rg 'Decision 8.*§2\.5\.3' specs-draft/ml-serving-draft.md                     # L1191
rg 'from kailash_ml\.engines\.lineage' specs-draft/ml-engines-v2-draft.md     # L2254, L2482

# Items 16-22: Phase-G items
rg '[^_]kml_agent_' supporting-specs-draft/kaizen-ml-integration-draft.md     # 0
rg 'Optional\[tuple\[ClearanceRequirement' supporting-specs-draft/kaizen-ml-integration-draft.md  # L171
rg '^#### 7\.1\.2' specs-draft/ml-registry-draft.md                           # L488
rg 'Postgres tables use' 04-validate/approved-decisions.md                    # L31 — _kml_ present
rg 'six named groups' specs-draft/ml-engines-v2-draft.md                      # L2180
rg 'engine_info, list_engines' specs-draft/ml-engines-v2-draft.md             # L2255
rg 'all \*\*18 engines\*\*|18 engines \(MLEngine' specs-draft/ml-engines-v2-addendum-draft.md  # L602

# Items 23-26: Phase-H (new in Round 8)
rg -c '8 public methods per Decision 8' specs-draft/ml-engines-v2-addendum-draft.md                # 0 — OLD removed
rg -c 'Per-engine public-method count' specs-draft/ml-engines-v2-addendum-draft.md                 # 1 — NEW present (L505)
rg -c 'Eight public-method signatures \(Decision 8 lock-in\)' supporting-specs-draft/kaizen-ml-integration-draft.md  # 0 — OLD removed
rg -c 'Per-engine public-method signatures' supporting-specs-draft/kaizen-ml-integration-draft.md  # 1 — NEW present (L172)
```

---

## Net vs Round 7

| Metric       | Round-7 Closure              | Round-8 Closure           | Delta                   |
| ------------ | ---------------------------- | ------------------------- | ----------------------- |
| Items        | 22                           | **24**                    | +2 (Phase-H items)      |
| GREEN        | 22 (100%)                    | **24 (100%)**             | **+2 GREEN**            |
| RED          | 0                            | **0**                     | held                    |
| HIGH         | 0                            | **0**                     | held                    |
| Open items   | 1 (out-of-scope observation) | **0** (Phase-H closed it) | **−1**                  |
| Clean rounds | **1** (first clean)          | **2 consecutive clean**   | **convergence reached** |

Phase-H delivered both planned items (H1 §E11.3 comment + H2 kaizen-ml §2.4.2 row) with no regressions to the 22 Phase-F + G items. The specs are converged.

---

## Recommended Next Action

Convergence criterion satisfied. The audit workspace is ready for Phase-I promotion (`specs-draft/*-draft.md` → `specs/*.md`, `supporting-specs-draft/*-draft.md` → `specs/*.md`). No further audit rounds required against the current spec set.
