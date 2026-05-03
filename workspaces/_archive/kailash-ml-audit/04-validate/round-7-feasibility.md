# Round 7 Feasibility Audit

**Date:** 2026-04-21
**Persona:** Implementation Feasibility Auditor
**Scope:** 23 specs post Phase-G (15 core ml + 6 supporting + 2 Phase-E meta)
**Method:** Re-derived from scratch per `rules/testing.md` § Audit Mode; full-sibling sweep per `rules/specs-authority.md §5b` (mandatory after 5 rounds of narrow-scope misses).

---

## Headline: 23/23 READY + 0 NEEDS-PATCH + 0 BLOCKED

**FIRST CLEAN ROUND ACHIEVED.** 0 CRIT / 0 HIGH / 0 MED / 0 LOW open. Ready for Round 8 convergence confirmation (2-consecutive-clean-rounds exit criterion).

Progress: Round-6 (21 READY + 2 NEEDS-PATCH / 2 HIGH) → Round-7 (23 READY / 0 HIGH). Phase-G closed both HIGHs: G1 swept kaizen-ml `kml_agent_*` → `_kml_agent_*`; G3a introduced §7.1.2 Single-Format-Per-Row Invariant reconciling RegisterResult dict vs DDL singular column.

---

## Matrix

### Core 15 ml specs

| #   | Spec                    | Verdict   | Note                                                                                                                                                                                                                                              |
| --- | ----------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | ml-engines-v2           | **READY** | §15.8 `km.lineage` signature pinned; §15.9 6-group `__all__` with Group 6 Engine Discovery; §18 checklist includes eager-import + lineage/engine_info/list_engines Group-6 bullets; `resolve_store_url` plumbed via §2.1                          |
| 2   | ml-engines-v2-addendum  | **READY** | §E1.1 enumerates 18 engines (MLEngine + 17 support); §E11.1 exports `EngineInfo`/`MethodSignature`/`ParamSpec`/`ClearanceRequirement`/`ClearanceLevel`/`ClearanceAxis`; §E11.3 MUST 4 asserts 18-engine wiring test; `engine.lineage(...)` grep=0 |
| 3   | ml-tracking             | **READY** | 8 CREATE TABLE `_kml_*`; 1 legit `kml_experiment` at L684 (Python module stem, rationalized)                                                                                                                                                      |
| 4   | ml-autolog              | **READY** | No DDL; errors + signatures intact; `get_current_run()` accessor via ml-tracking §10.1                                                                                                                                                            |
| 5   | ml-registry             | **READY** | §7.1 `artifact_uris: dict[str, str]` + §7.1.1 back-compat property + **§7.1.2 Single-Format-Per-Row Invariant**; DDL §5A.2 `format VARCHAR(16) NOT NULL` + `artifact_uri TEXT NOT NULL` + `UNIQUE (tenant_id, name, version)` now reconciled      |
| 6   | ml-serving              | **READY** | 3 DDL tables `_kml_*`; §2.5.3 pickle-gate cite; §9A.1 internal-table rationale; `allow_pickle=False` default                                                                                                                                      |
| 7   | ml-feature-store        | **READY** | 4 DDL tables `_kml_*`; §10A.1 distinguishes `_kml_` system prefix from user-configurable `kml_feat_` per-tenant prefix (2 residual `kml_feat_` hits at L69 + L556 are rationalized)                                                               |
| 8   | ml-drift                | **READY** | 4 DDL tables `_kml_*`; `reference_artifact_uri` is unrelated column (drift reference), not `RegisterResult.artifact_uri`                                                                                                                          |
| 9   | ml-automl               | **READY** | 1 DDL table `_kml_*`; ambient contextvar auto-wire                                                                                                                                                                                                |
| 10  | ml-backends             | **READY** | No DDL; 3 errors; `resolve_store_url` plumbed via ml-engines-v2 §2.1                                                                                                                                                                              |
| 11  | ml-diagnostics          | **READY** | No new DDL; 3 cross-refs to `_kml_metric` at L284/L506/L515                                                                                                                                                                                       |
| 12  | ml-dashboard            | **READY** | `km.lineage(run_id, tenant_id=<req-tenant>)` at L205 with Phase-F F5 default signature                                                                                                                                                            |
| 13  | ml-rl-core              | **READY** | No DDL; 10 errors; SafetyFilter contract pinned                                                                                                                                                                                                   |
| 14  | ml-rl-algorithms        | **READY** | No DDL; dataclasses intact                                                                                                                                                                                                                        |
| 15  | ml-rl-align-unification | **READY** | No DDL; cross-framework bindings intact                                                                                                                                                                                                           |

### Supporting 6 integration specs

| #   | Spec                        | Verdict   | Note                                                                                                                                                                                                                    |
| --- | --------------------------- | --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 16  | pact-ml-integration         | **READY** | No DDL; D/T/R axis binding to `ClearanceRequirement` intact                                                                                                                                                             |
| 17  | nexus-ml-integration        | **READY** | No DDL; channels wiring intact                                                                                                                                                                                          |
| 18  | kaizen-ml-integration       | **READY** | **G1 closed**: 8 `_kml_agent_*` hits, 0 bare `kml_agent_*`; §2.4 Agent Tool Discovery complete (§2.4.1–§2.4.7); §2.4.2 imports `ClearanceRequirement` from `kailash_ml.engines.registry` matching §E11.1 export surface |
| 19  | align-ml-integration        | **READY** | 2 refs to `_kml_metric` at L277/L531; 3 `kml_key` at L186-188 are Python variable names (legit code identifiers, not DDL)                                                                                               |
| 20  | kailash-core-ml-integration | **READY** | No DDL; lifecycle-helper accessors intact                                                                                                                                                                               |
| 21  | dataflow-ml-integration     | **READY** | No DDL; tenant + classification bindings intact                                                                                                                                                                         |

### Phase-E meta 2

| #   | Spec                      | Verdict   | Note                                                                                                          |
| --- | ------------------------- | --------- | ------------------------------------------------------------------------------------------------------------- |
| 22  | ml-readme-quickstart-body | **READY** | Canonical Quick Start body references `result.artifact_uris` (plural dict, §2); SHA-256 pinned to Tier-3 test |
| 23  | ml-index-amendments       | **READY** | `specs/_index.md` diff complete (183 LOC with rationale + row count)                                          |

---

## Phase-G closure verification

### G1 — kaizen-ml `kml_agent_*` → `_kml_agent_*` rename (Round-6 N1′-RESIDUAL)

```bash
grep -c '\bkml_agent_' /Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/kaizen-ml-integration-draft.md
# → 0 (target: 0) ✅

grep -c '_kml_agent_' /Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/kaizen-ml-integration-draft.md
# → 8 (target: ≥8) ✅
```

L446 confirms `table_prefix: str = "_kml_agent_",` — class default now conforms to the `_kml_*` internal-table convention.

### G3a — ml-registry §7.1.2 Single-Format-Per-Row Invariant (Round-6 HIGH-R6-1-NEW)

```bash
grep -n '7\.1\.2' /Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-registry-draft.md
# → L488 "7.1.2 Single-Format-Per-Row Invariant (v1.0.0)" ✅

grep -n 'len(RegisterResult.artifact_uris) == 1' /Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-registry-draft.md
# → L498 invariant statement ✅
```

§7.1.2 L490-505 resolves the DDL-vs-dataclass drift: dict shape is a **projection** over one or more DDL rows, with v1.0.0 invariant `len(artifact_uris) == 1`. L500-505 names v1.1+ migration paths (Shape B UNIQUE extension / Shape C JSONB consolidation). L507 records the Shape A rationale.

### Internal consistency (Phase-G did not introduce NEW drift)

1. **§7.1.2 invariant vs §5A.2 UNIQUE constraint** — §7.1.2 L490 ("one row per `(tenant_id, name, version)`") matches §5A.2 L283 (`UNIQUE (tenant_id, name, version)`). Consistent.

2. **kaizen-ml §2.4.2 imports match §E11.1 exports** — §2.4.2 L154-159 imports `EngineInfo, MethodSignature, ParamSpec, ClearanceRequirement` from `kailash_ml.engines.registry`. §E11.1 defines all four at L488-495 in the same module. `ClearanceLevel` / `ClearanceAxis` are type aliases used as field types (not required to be re-imported by consumers). Consistent.

3. **§E11.3 MUST 4 "18 engines" vs §E1.1 enumeration** — §E1.1 L24-41 lists exactly 18 engines (MLEngine + TrainingPipeline + ExperimentTracker + ModelRegistry + FeatureStore + InferenceServer + DriftMonitor + AutoMLEngine + HyperparameterSearch + Ensemble + Preprocessing + FeatureEngineer + ModelExplainer + DataExplorer + ModelVisualizer + Clustering + AnomalyDetection + DimReduction). §E11.3 MUST 4 L602 enumerates the same 18. L43 totalizer asserts "Total: 18 engines". Consistent.

---

## §5b full-sibling sweep findings

Per `rules/specs-authority.md §5b`, every edit triggers re-derivation across the FULL sibling set. Phase-G edited 2 specs (kaizen-ml + ml-registry); Round-7 re-grepped the entire 23-spec surface for the 6 drift vectors named in the prompt.

### Vector 1 — RegisterResult field-shape

```bash
grep -rn 'RegisterResult' /Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/
# Matches in 5 files: ml-registry, ml-engines-v2, ml-engines-v2-addendum, ml-serving, ml-readme-quickstart-body
```

All 5 consumers read `RegisterResult.artifact_uris` (plural dict). The singular `artifact_uri` survives only as: (a) the DDL column name in `_kml_model_versions`, (b) the `@property artifact_uri` back-compat shim at §7.1.1 (v1.x only, removed at v2.0), (c) unrelated drift column `reference_artifact_uri` in ml-drift §10 (different table, different column — not RegisterResult-related).

**Verdict:** ZERO cross-spec drift on RegisterResult.

### Vector 2 — ClearanceRequirement type-shape

```bash
grep -rn 'ClearanceRequirement' /Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/{specs-draft,supporting-specs-draft}/
# Matches in 2 files: ml-engines-v2-addendum (defn + usage), kaizen-ml-integration (import + table-row + usage)
```

Both consumers use the typed `Optional[tuple[ClearanceRequirement, ...]]` shape per §E11.1 L504. kaizen-ml §2.4.2 table row L171 matches the addendum's type annotation exactly. Usage snippet at addendum L512-515 + kaizen-ml L193-202 both construct `ClearanceRequirement(axis="...", min_level="...")`.

**Verdict:** ZERO cross-spec drift on ClearanceRequirement.

### Vector 3 — `_kml_*` DDL prefix sweep

```bash
for f in /Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/*.md /Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/*.md; do
  c=$(grep -c '\bkml_' "$f"); [ "$c" != "0" ] && echo "$f: $c"
done
```

Residual bare `kml_` hits (all rationalized, not drift):

- `ml-feature-store-draft.md: 2` — both are the user-configurable `kml_feat_` per-tenant feature-table prefix at L69 + L556, explicitly distinguished in §10A.1 from internal `_kml_*` metadata prefix.
- `ml-tracking-draft.md: 1` — L684 `kml_experiment` is a Python module stem (leading underscore is reserved for private modules); physical table is `_kml_experiment`.
- `align-ml-integration-draft.md: 3` — all three hits at L186-188 are Python local variable names (`kml_key`), not DDL.

`kml_agent_*` bare count is **0** in kaizen-ml (G1 closure confirmed). Previously broken state had 8 bare hits at L439/L452/L463/L464/L466/L468/L476/L485.

**Verdict:** ZERO cross-spec DDL-prefix drift. All `kml_*` non-underscore hits are either user-facing config defaults, Python module names, or Python variable names — not DDL.

### Vector 4 — `km.lineage` signature consistency (tenant_id default)

```bash
grep -rn 'tenant_id: str | None = None' /Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/{specs-draft,supporting-specs-draft}/ | grep -i lineage
```

2 matches: `ml-engines-v2-draft.md:2174` + `ml-engines-v2-addendum-draft.md:418`. Full `async def lineage` signature at ml-engines-v2 L2166-2172 — `tenant_id: str | None = None`, `max_depth: int = 10`. Consumer at `ml-dashboard-draft.md:205` uses `km.lineage(run_id, tenant_id=<request-tenant>)` — positional + kwargs, compatible with default. Addendum §E10.2 L418 + §E13.1 L648 both use the same signature.

**Verdict:** ZERO cross-spec signature drift on km.lineage.

### Vector 5 — "18 engines" vs "13 engines"

```bash
grep -rn '13 engines\|18 engines' /Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/{specs-draft,supporting-specs-draft}/
```

`13 engines` appears only in 2 origin-note contexts (ml-drift L425 "Round-1 finding 0/13 engines auto-wire"; ml-feature-store L12 "Round-1 CRIT T3 — tenant isolation absent from 13/13 engines"). These are historical audit-era labels referencing the pre-addendum round-1 engine count; they document origin, not current state. `18 engines` is the canonical current count (ml-engines-v2-addendum L43 totalizer, L602 §E11.3 MUST 4 test contract, L646 §E13.1 end-to-end flow, kaizen-ml L303 test contract).

**Verdict:** ZERO cross-spec count drift. Origin notes are historical-context labels, not current claims.

### Vector 6 — "five groups" vs "six groups"

```bash
grep -rn 'five groups\|five Group\|6 groups\|six groups\|six Group\|Groups 1-[56]\|Group [56]' /Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/{specs-draft,supporting-specs-draft}/
```

All 6 matches reference Group 6 (ml-engines-v2 L2180 "six named groups", L2228 Group 5, L2233-2239 Group 6 Engine Discovery, L2255 eager import, L2485 §18 checklist). No "five groups" / "Groups 1-5" residue — Phase-F F5 already upgraded every reference to 6.

**Verdict:** ZERO cross-spec group-count drift.

### Meta: full-sibling sweep validated for 6th consecutive session

Round-6 surfaced 2 drifts that narrow-scope would have missed (N1′-RESIDUAL + HIGH-R6-1-NEW). Round-7 surfaces 0 new drifts after Phase-G — because Phase-G addressed BOTH at the source and didn't introduce new divergence. Rule §5b continues to hold as a load-bearing structural defense; Round-7 is the first round where its sweep returns empty, matching the clean-round criterion.

---

## Round-8 entry assertions

For Round-8 to certify convergence (2 consecutive clean rounds), the following assertions MUST hold. All 8 currently verified:

1. **`grep -c '\bkml_agent_' supporting-specs-draft/kaizen-ml-integration-draft.md` == 0** ✅ (verified: 0)
2. **`grep -c '_kml_agent_' supporting-specs-draft/kaizen-ml-integration-draft.md` >= 8** ✅ (verified: 8)
3. **`grep -n '7\.1\.2' specs-draft/ml-registry-draft.md` contains "Single-Format-Per-Row Invariant"** ✅ (verified: L488)
4. **`grep -c 'engine\.lineage' specs-draft/ml-engines-v2-addendum-draft.md` == 0** ✅ (verified: 0)
5. **`grep -l 'resolve_store_url' specs-draft/*.md` ≥ 6 files** ✅ (verified: 6 — engines-v2, engines-v2-addendum via §2.1, automl, feature-store, registry, tracking, dashboard)
6. **ClearanceRequirement defined in addendum §E11.1 AND imported from `kailash_ml.engines.registry` in kaizen-ml §2.4.2** ✅ (verified: L488-492 defn + L154-159 import)
7. **`artifact_uris: dict[str, str]` canonical across 5 consumer specs with NO singular `artifact_uri: str` field declaration** ✅ (verified: only property shim at §7.1.1 + DDL column)
8. **§E1.1 engine row count == 18 == §E11.3 MUST 4 test-contract count** ✅ (verified: 18 rows L24-41 + L602 enumeration)

### Literal grep commands for Round-8 re-derivation

```bash
# Gate 1 — G1 closure (kaizen-ml DDL prefix)
test $(grep -c '\bkml_agent_' workspaces/kailash-ml-audit/supporting-specs-draft/kaizen-ml-integration-draft.md) -eq 0
test $(grep -c '_kml_agent_' workspaces/kailash-ml-audit/supporting-specs-draft/kaizen-ml-integration-draft.md) -ge 8

# Gate 2 — G3a closure (ml-registry single-format invariant)
grep -q 'Single-Format-Per-Row Invariant' workspaces/kailash-ml-audit/specs-draft/ml-registry-draft.md
grep -q 'len(RegisterResult.artifact_uris) == 1' workspaces/kailash-ml-audit/specs-draft/ml-registry-draft.md

# Gate 3 — YELLOW-G / Group-6 / lineage defaults
test $(grep -c 'engine\.lineage' workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-addendum-draft.md) -eq 0
grep -q 'tenant_id: str | None = None' workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-draft.md
grep -q 'Group 6 — Engine Discovery' workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-draft.md

# Gate 4 — env plumbing breadth
test $(grep -l 'resolve_store_url' workspaces/kailash-ml-audit/specs-draft/*.md | wc -l) -ge 6

# Gate 5 — ClearanceRequirement export/import parity
grep -q 'class ClearanceRequirement' workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-addendum-draft.md
grep -q 'ClearanceRequirement,.*# nested axis+level' workspaces/kailash-ml-audit/supporting-specs-draft/kaizen-ml-integration-draft.md

# Gate 6 — RegisterResult sweep (should find dict[str, str] definition, NO singular field decl)
grep -q 'artifact_uris: dict\[str, str\]' workspaces/kailash-ml-audit/specs-draft/ml-registry-draft.md

# Gate 7 — 18-engine enumeration
test $(grep -cE '^\| `[A-Z][A-Za-z]+`' workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-addendum-draft.md | head -1) -ge 18
grep -q 'Total: 18 engines' workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-addendum-draft.md
```

### Progression dashboard

| Round | READY  | NEEDS-PATCH | BLOCKED | HIGH  | MED   | LOW   | Scope   |
| ----- | ------ | ----------- | ------- | ----- | ----- | ----- | ------- |
| 2b    | 4      | 11          | 0       | ?     | ?     | ?     | 15 core |
| 3     | 9      | 6           | 0       | ?     | ?     | ?     | 15 core |
| 4     | 17     | 4           | 0       | 5     | —     | —     | 21      |
| 5     | 14     | 9           | 0       | 1     | 2     | 1     | 23      |
| 6     | 21     | 2           | 0       | 2     | 0     | 0     | 23      |
| **7** | **23** | **0**       | **0**   | **0** | **0** | **0** | **23**  |

Round-7 = **FIRST CLEAN ROUND**. Round-8 persona sweep (8 personas minimum: feasibility + senior-practitioner + spec-compliance + cross-spec-consistency + industry-parity + newbie-ux + tbd-retriage + closure-verification) will confirm the second clean round, satisfying the 2-consecutive-clean-rounds convergence criterion.

---

## Absolute paths

- **This report:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-7-feasibility.md`
- **Prior round:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-6-feasibility.md`
- **Phase-G plan:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-6-SYNTHESIS.md`
- **G1 target (closed):** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/kaizen-ml-integration-draft.md` §5.2 L446 + §5 DDL block
- **G3a target (closed):** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-registry-draft.md` §7.1.2 L488-507
- **Decisions:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/approved-decisions.md`
- **15 core specs:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-*.md`
- **6 supporting specs:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/*-ml-integration-draft.md`
- **2 Phase-E drafts:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-readme-quickstart-body-draft.md`, `.../ml-index-amendments-draft.md`

_End of round-7-feasibility.md. Author: Implementation Feasibility Auditor persona. 2026-04-21._
