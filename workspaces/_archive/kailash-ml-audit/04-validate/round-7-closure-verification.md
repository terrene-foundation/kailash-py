# Round 7 Closure Verification

**Date:** 2026-04-21
**Persona:** Round-7 Closure Verifier (post Phase-G merge)
**Scope:** 22 closure items — 15 Phase-F + 7 Phase-G re-derived from scratch against the current `specs-draft/` + `supporting-specs-draft/` tree. Prior round outputs not trusted (audit-mode rule `rules/testing.md § Audit Mode`).

## Headline: 22/22 GREEN + 0 RED + 0 HIGH

**First clean closure round achieved.** Every Phase-F and Phase-G closure item reproduces against a literal grep on the current spec state.

---

## Per-item table

| #   | Item                                                      | Command                                                                                                    | Expected | Actual                                   | Verdict   |
| --- | --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | -------- | ---------------------------------------- | --------- |
| 1   | F1 in-prose `[^_]kml_(run\|metric\|agent)` residual       | `rg -n '[^_]kml_(run\|metric\|agent)' specs-draft/ supporting-specs-draft/`                                | 0        | **0**                                    | **GREEN** |
| 2   | F1 `CREATE TABLE _kml_` DDL count                         | `rg -n 'CREATE TABLE.*_kml_' specs-draft/ supporting-specs-draft/ \| wc -l`                                | ≥24      | **26** (24 ml-\* + 2 kaizen-ml)          | **GREEN** |
| 2b  | F1 bare `CREATE TABLE kml_` DDL                           | `rg -n 'CREATE TABLE.*[^_]kml_' specs-draft/ supporting-specs-draft/`                                      | 0        | **0**                                    | **GREEN** |
| 3   | F1 full residual bare-`kml_` sweep                        | `rg -n '\bkml_[a-z]' specs-draft/ supporting-specs-draft/`                                                 | 0 drift  | **6 hits — all legitimate**¹             | **GREEN** |
| 4   | F2 `resolve_store_url` 6-spec plumbing                    | `rg -l 'resolve_store_url' specs-draft/ supporting-specs-draft/ \| wc -l`                                  | 6        | **6**                                    | **GREEN** |
| 5   | F3 RegisterResult `artifact_uris` plural                  | `rg -n 'artifact_uris: dict\[str, str\]' specs-draft/ml-registry-draft.md`                                 | present  | **L424 + L490 (both hit)**               | **GREEN** |
| 6   | F3 §7.1.1 back-compat shim                                | `rg -n '^#### 7\.1\.1' specs-draft/ml-registry-draft.md`                                                   | present  | **L455**                                 | **GREEN** |
| 7   | F3 `onnx_status: Optional[Literal` field                  | `rg -n 'onnx_status: Optional\[Literal' specs-draft/ml-registry-draft.md`                                  | present  | **L236 (semantics) + L436 (F3)**         | **GREEN** |
| 8   | F4 kaizen-ml §2.4 section heading                         | `rg -n '^### 2\.4' supporting-specs-draft/kaizen-ml-integration-draft.md`                                  | present  | **L126 `### 2.4 Agent Tool…`**           | **GREEN** |
| 9   | F4 km.engine_info/km.list_engines reference count         | `rg -c 'km\.engine_info\|km\.list_engines' supporting-specs-draft/kaizen-ml-integration-draft.md`          | ≥11      | **11**                                   | **GREEN** |
| 10  | F5 km.lineage `tenant_id: str \| None = None`             | `rg -n 'tenant_id: str \| None = None' specs-draft/ml-engines-v2-draft.md ml-engines-v2-addendum-draft.md` | both     | **engines-v2 L2169 + addendum L418**     | **GREEN** |
| 11  | F5 YELLOW-G `engine.lineage(` anti-pattern                | `rg -n 'engine\.lineage\(' specs-draft/ml-engines-v2-addendum-draft.md`                                    | 0        | **0**                                    | **GREEN** |
| 12  | F5 YELLOW-H Group 6 in `__all__`                          | `rg -n 'Group 6' specs-draft/ml-engines-v2-draft.md`                                                       | present  | **L2180 + L2233 + L2239 + L2485**        | **GREEN** |
| 13  | F6 `class ClearanceRequirement` dataclass                 | `rg -n 'class ClearanceRequirement' specs-draft/ml-engines-v2-addendum-draft.md`                           | present  | **L489**                                 | **GREEN** |
| 14  | F6 ml-serving Decision 8 ↔ §2.5.3 citation                | `rg -n 'Decision 8.*§2\.5\.3' specs-draft/ml-serving-draft.md`                                             | present  | **L1191**                                | **GREEN** |
| 15  | F6 lineage eager-import in §15.9                          | `rg -n 'from kailash_ml\.engines\.lineage' specs-draft/ml-engines-v2-draft.md`                             | present  | **L2254 + L2482**                        | **GREEN** |
| 16  | G1 kaizen-ml `[^_]kml_agent_` residual                    | `rg -n '[^_]kml_agent_' supporting-specs-draft/kaizen-ml-integration-draft.md`                             | 0        | **0**                                    | **GREEN** |
| 17  | G2 kaizen-ml §2.4.2 `Optional[tuple[ClearanceRequirement` | `rg -n 'Optional\[tuple\[ClearanceRequirement' supporting-specs-draft/kaizen-ml-integration-draft.md`      | present  | **L171**                                 | **GREEN** |
| 18  | G3a ml-registry §7.1.2 single-format invariant            | `rg -n '^#### 7\.1\.2' specs-draft/ml-registry-draft.md`                                                   | present  | **L488** (single-format-per-row)         | **GREEN** |
| 19  | G3b approved-decisions.md L31 `_kml_` prefix              | `rg -n 'Postgres tables use.*_kml_\|Postgres tables use.*kml_' 04-validate/approved-decisions.md`          | `_kml_`  | **L31 — `_kml_` present**                | **GREEN** |
| 20  | G3c ml-engines-v2 "six named groups"                      | `rg -n 'six named groups' specs-draft/ml-engines-v2-draft.md`                                              | present  | **L2180**                                | **GREEN** |
| 21  | G3c Group 6 eager-import `engine_info, list_engines`      | `rg -n 'engine_info, list_engines' specs-draft/ml-engines-v2-draft.md`                                     | present  | **L2255** (eager import)                 | **GREEN** |
| 22  | G3d ml-engines-v2-addendum §E11.3 MUST 4 "18 engines"     | `rg -n 'all \*\*18 engines\*\*\|18 engines \(MLEngine' specs-draft/ml-engines-v2-addendum-draft.md`        | present  | **L602** (explicit "all **18 engines**") | **GREEN** |

¹ Item 3 legitimate hits (re-verified from Round-6 Section A.4):

- `ml-tracking-draft.md:684` — migration filename stem (`0001_create_kml_experiment.py`, Python module name cannot start with `_`; physical table remains `_kml_experiment`).
- `ml-feature-store-draft.md:69` — documents deprecated v0.9.x `table_prefix="kml_feat_"` removal (historical reference).
- `ml-feature-store-draft.md:556` — explicit distinction between internal `_kml_` vs user-configurable `kml_feat_` prefix (design doc).
- `align-ml-integration-draft.md:186-188` — Python local variable `kml_key` (not a table).

All four categories reviewed in Round-6 Section A.4 and re-verified in Round 7 as LEGITIMATE non-drift.

---

## Additional Cross-Verification

Beyond the 22 canonical items, I also spot-checked Phase-G's implementation:

**Phase-G G1 — kaizen-ml DDL rewrite verification:**

```
$ rg -n '_kml_agent' supporting-specs-draft/kaizen-ml-integration-draft.md | wc -l
8
```

The 8 `_kml_agent` hits correspond to (re-derived from `rg -n '_kml_agent' supporting-specs-draft/kaizen-ml-integration-draft.md`):

- L459: `CREATE TABLE IF NOT EXISTS _kml_agent_traces (` ✅
- L470: `CREATE INDEX ... _kml_agent_traces_tenant_idx ON _kml_agent_traces(...)` ✅
- L471: `CREATE INDEX ... _kml_agent_traces_run_idx ON _kml_agent_traces(...)` ✅
- L473: `CREATE TABLE IF NOT EXISTS _kml_agent_trace_events (` ✅
- L475: `REFERENCES _kml_agent_traces(trace_id)` (FK) ✅
- L483: `CREATE INDEX ... _kml_agent_trace_events_trace_idx ON _kml_agent_trace_events(...)` ✅
- L492: "join `_kml_run` to `_kml_agent_traces` on run_id" (prose) ✅

All 6 DDL tokens + 2 prose references unified on `_kml_agent_*` prefix.

**Phase-G G3b — approved-decisions.md L31 prose:**

```
Postgres tables use `_kml_` prefix (leading underscore distinguishes
framework-owned internal tables from user-facing tables; all names stay
within Postgres 63-char identifier limit). See `ml-tracking.md §6.3` +
`rules/dataflow-identifier-safety.md` Rule 2 for the canonical convention;
per-spec sweeps in `ml-tracking`, `ml-registry`, `ml-serving`,
`ml-feature-store`, `ml-automl`, `ml-diagnostics`, `ml-drift`, `ml-autolog`,
and the cross-domain `kaizen-ml-integration §5.2` trace tables all unify
on `_kml_*` as of Phase-G (2026-04-21).
```

The updated prose cites the Phase-G date AND enumerates the per-spec sweep — stronger than the mere prefix flip.

**Phase-G G3c — ml-engines-v2 §15.9 listing:**

```python
# Group 6 — Engine Discovery (metadata introspection per ml-engines-v2-addendum §E11.2)
"engine_info",
"list_engines",
```

`__all__` Group 6 listing plus eager-import at L2255 both land, closing MED-R6-2 and MED-R6-3 in one edit.

**Phase-G G3d — addendum §E11.3 MUST 4:**

```
... asserts `list_engines()` returns all **18 engines** enumerated in
§E1.1 (MLEngine + 17 support engines: TrainingPipeline, ExperimentTracker,
ModelRegistry, FeatureStore, InferenceServer, DriftMonitor, AutoMLEngine,
HyperparameterSearch, Ensemble, Preprocessing, FeatureEngineer,
ModelExplainer, DataExplorer, ModelVisualizer, Clustering, AnomalyDetection,
DimReduction) AND every `EngineInfo.signatures` tuple contains the
**per-engine public-method count specified in §E1.1** (varies per engine —
MLEngine's 8-method surface per Decision 8 is a per-engine invariant, NOT
a fixed "8 per engine" constraint across all 18). Any engine whose
`len(signatures)` diverges from its §E1.1 row is a §5b cross-spec drift
violation.
```

Pre-Phase-G claim "13 engines + 8 signatures" has been properly replaced with a single source of truth ("per §E1.1"), eliminating the contradiction with §E1.1's enumeration of 18 engines.

---

## Open items

**Zero. No Phase-G items regressed, no new items surfaced from the 22-item audit.**

**Observation (out of scope, not a Round-7 item):** `supporting-specs-draft/kaizen-ml-integration-draft.md:172` still carries prose "Eight public-method signatures (Decision 8 lock-in)" in the `signatures` field row of the §2.4.2 table. This is the same class of cross-spec drift as MED-R6-5 (`addendum §E11.3 MUST 4` pre-fix) — per-engine signature counts vary per §E1.1, and MLEngine's 8 is a per-engine invariant, not a universal one. This was NOT in the Phase-G plan nor the 22 Round-7 closure items (Phase-G's MED-R6-5 fix was scoped to the addendum §E11.3 MUST 4 clause only). Filing as a forward observation for the 4-by-4 Round-7 re-run; not a closure-item failure.

---

## Round-8 Entry Assertions

Phase-G has fully delivered on the Round-6 SYNTHESIS plan. The 22 mechanical checks enumerated in the plan all verify GREEN. Round-7 may now proceed to:

1. **Re-run the 8 Round-6 personas** (cross-spec consistency, closure verification, newbie UX, feasibility, industry parity, TBD re-triage, senior practitioner, spec-compliance) against post-Phase-G specs.
2. **Target**: 0 CRIT + 0 HIGH + ≤1 MED aggregate across all 8 personas.
3. **Expected exit**: If personas land clean, this satisfies the first "full clean round" criterion (Round-6 SYNTHESIS line 92). Round 8 confirms 2-consecutive-clean convergence.

**Preconditions verified for Round-7 persona re-run:**

- ✅ No `[^_]kml_agent_` residual in kaizen-ml (G1)
- ✅ `clearance_level` type consistent across §E11.1 ↔ §2.4.2 (G2)
- ✅ `RegisterResult.artifact_uris` dict-to-DDL aggregation specified in §7.1.2 (G3a)
- ✅ `approved-decisions.md` L31 aligned with DDL specs (G3b)
- ✅ ml-engines-v2 §15.9 "six groups" + eager-imports (G3c)
- ✅ addendum §E11.3 "18 engines" (G3d)
- ✅ All 15 Phase-F claims still green (no regression)

**Recommended next action:** Launch the 8-persona Round-7 re-run in parallel (4-by-4 as Round-6 SYNTHESIS line 92 recommends). Expected runtime ~30 min per batch.

---

## Mechanical Verification Log

All 22 counts in this report were produced by live `rg` against `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/` at audit time (2026-04-21). No trust in prior round outputs. Key commands:

```bash
# Items 1-3: kml_ prefix unification
rg -n '[^_]kml_(run|metric|agent)' specs-draft/ supporting-specs-draft/          # 0
rg -n 'CREATE TABLE.*_kml_' specs-draft/ supporting-specs-draft/ | wc -l          # 26
rg -n 'CREATE TABLE.*[^_]kml_' specs-draft/ supporting-specs-draft/               # 0
rg -n '\bkml_[a-z]' specs-draft/ supporting-specs-draft/                          # 6 (all legitimate)

# Item 4: _env.resolve_store_url plumbing
rg -l 'resolve_store_url' specs-draft/ supporting-specs-draft/ | wc -l             # 6

# Items 5-7: RegisterResult F3 canonical
rg -n 'artifact_uris: dict\[str, str\]' specs-draft/ml-registry-draft.md           # L424, L490
rg -n '^#### 7\.1\.1' specs-draft/ml-registry-draft.md                             # L455
rg -n 'onnx_status: Optional\[Literal' specs-draft/ml-registry-draft.md            # L236, L436

# Items 8-9: kaizen-ml §2.4
rg -n '^### 2\.4' supporting-specs-draft/kaizen-ml-integration-draft.md            # L126
rg -c 'km\.engine_info|km\.list_engines' supporting-specs-draft/kaizen-ml-integration-draft.md  # 11

# Items 10-12: km.lineage
rg -n 'tenant_id: str \| None = None' specs-draft/ml-engines-v2-draft.md specs-draft/ml-engines-v2-addendum-draft.md  # both hit
rg -n 'engine\.lineage\(' specs-draft/ml-engines-v2-addendum-draft.md              # 0
rg -n 'Group 6' specs-draft/ml-engines-v2-draft.md                                 # 4 hits

# Items 13-15: addendum + serving + lineage eager
rg -n 'class ClearanceRequirement' specs-draft/ml-engines-v2-addendum-draft.md     # L489
rg -n 'Decision 8.*§2\.5\.3' specs-draft/ml-serving-draft.md                       # L1191
rg -n 'from kailash_ml\.engines\.lineage' specs-draft/ml-engines-v2-draft.md       # L2254, L2482

# Items 16-17: G1 + G2
rg -n '[^_]kml_agent_' supporting-specs-draft/kaizen-ml-integration-draft.md       # 0
rg -n 'Optional\[tuple\[ClearanceRequirement' supporting-specs-draft/kaizen-ml-integration-draft.md  # L171

# Items 18-19: G3a + G3b
rg -n '^#### 7\.1\.2' specs-draft/ml-registry-draft.md                             # L488
rg -n 'Postgres tables use' 04-validate/approved-decisions.md                      # L31 with _kml_

# Items 20-22: G3c + G3d
rg -n 'six named groups' specs-draft/ml-engines-v2-draft.md                        # L2180
rg -n 'engine_info, list_engines' specs-draft/ml-engines-v2-draft.md               # L2255
rg -n 'all \*\*18 engines\*\*|18 engines \(MLEngine' specs-draft/ml-engines-v2-addendum-draft.md  # L602
```

---

## Net vs Round 6

| Metric  | Round-6 Closure | Round-7 Closure               | Delta                     |
| ------- | --------------- | ----------------------------- | ------------------------- |
| Items   | 12              | **22**                        | +10 (Phase-G items added) |
| GREEN   | 10 (83.3%)      | **22 (100%)**                 | **+12 GREEN**             |
| RED     | 1 (N1 residual) | **0**                         | **−1 RED closed**         |
| HIGH    | 2 (R6-A + R6-B) | **0**                         | **−2 HIGH closed**        |
| Verdict | NOT CLEAN       | **FIRST CLEAN CLOSURE ROUND** | Convergence milestone     |

Phase-G delivered all 8 items in its plan (HIGH-R6-A + HIGH-R6-B + HIGH-R6-C + MED-R6-1 through MED-R6-5) with no regressions to the 15 Phase-F items. Round-7 is now cleared to run the 8-persona re-audit in parallel.
