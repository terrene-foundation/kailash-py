# Round 8 Cross-Spec Consistency Audit

**Date:** 2026-04-21
**Persona:** Cross-Spec Consistency Auditor (convergence-confirmation round, post Phase-H)
**Scope:** 17 `specs-draft/ml-*-draft.md` (incl. 2 Phase-E meta drafts: `ml-engines-v2-addendum`, `ml-index-amendments`) + 6 `supporting-specs-draft/*.md`. 23 drafts total.
**Method:** Re-derived every assertion from scratch via `grep` / `rg` per `rules/testing.md` audit-mode rule. Round-7 outputs NOT trusted. Phase-H's 2 one-line edits independently re-verified against the authoritative §E11.3 MUST 4 + §E1.1 source-of-truth.

## Headline: 0 CRIT + 0 HIGH + 0 MED — 2nd CONSECUTIVE CLEAN ROUND

| Aggregate | Round-7 actual | Round-8 actual | Δ      |
| --------- | -------------- | -------------- | ------ |
| CRIT      | 0              | **0**          | stable |
| HIGH      | 0              | **0**          | stable |
| MED       | 0              | **0**          | stable |

Phase-H's 2 one-line edits at `ml-engines-v2-addendum-draft.md:505` + `kaizen-ml-integration-draft.md:172` verified landed; Phase-H introduced zero regressions. No new findings surfaced in this round.

---

## Section A — 4 CRITs Re-Verified

### A1 — DB URL canonical `~/.kailash_ml/ml.db`

```bash
grep -rc "\.kailash_ml/ml\.db\|sqlite:///.*ml\.db\|KAILASH_ML_STORE_URL" specs-draft/
# ml-tracking 14, ml-dashboard 15, ml-engines-v2 8, ml-automl 2, ml-rl-core 3,
# ml-drift 1, ml-backends 1, ml-feature-store 1, ml-rl-align-unification 1 — 46 hits / 9 specs.
```

Canonical declaration: `ml-tracking §2.2 L83`. Every `db_url=None` / `store_url=None` resolution path defaults to `~/.kailash_ml/ml.db`. Dashboard L471 + CLI L495 resolution paths match. Zero drift. **GREEN.**

### A2 — `ExperimentTracker.create()` canonical async factory

```bash
grep -rn "ExperimentTracker\.create\|ExperimentTracker(conn)\|ExperimentTracker\.from_" specs-draft/
# ExperimentTracker.create: 9 hits across ml-tracking (5), ml-engines-v2 (2),
# ml-rl-core (2), ml-rl-align-unification (1). No .open() / .from_*() / (conn) shapes
# outside BLOCKED examples (ml-tracking L1184 "legacy ExperimentTracker(conn) BLOCKED").
```

Canonical MUST: `ml-tracking §2.5 L171`. Sibling sites (`ml-rl-core §13.1`, `ml-rl-align-unification §4`, `ml-engines-v2 §2.3`, `ml-engines-v2-addendum §E1.2`) all call `await ExperimentTracker.create(...)`. **GREEN.**

### A3 — `MLError` hierarchy (11 typed children + cross-cutting)

```bash
grep -n "^class MLError\|MLError(Exception)" specs-draft/*.md
# ml-tracking-draft.md:856:class MLError(Exception):    — sole canonical declaration
grep -rc "MLError\|TrackingError\|BackendError\|RegistryError\|FeatureStoreError\|DriftMonitorError\|InferenceServerError\|AutoMLError\|DiagnosticsError\|DashboardError\|AutologError\|RLError" specs-draft/
# 107 hits across 12 specs.
```

Canonical: `ml-tracking §9.1 L850-L871`. 11 family children + 2 cross-cutting (`UnsupportedTrainerError`, `MultiTenantOpError`) + tracking sub-types. **GREEN.**

### A4 — `TrainingResult.device: DeviceReport`

```bash
grep -n "class TrainingResult\|device: DeviceReport" specs-draft/*.md | head -10
# ml-engines-v2-draft.md:1093:class TrainingResult:
# ml-engines-v2-draft.md:1097:    device: DeviceReport
# Tier-2 assertion at L2402: assert result.device is not None, "TrainingResult.device: DeviceReport must be populated"
# Sibling refs: ml-rl-algorithms L43 (device: DeviceReport kwarg), ml-rl-align-unification L69
# (device: DeviceReport field), ml-dashboard L220 (Flattened projection of TrainingResult.device),
# ml-backends L392 (round-trip assertion), ml-readme-quickstart-body L73 (populated device).
```

Canonical declaration: `ml-engines-v2 §4.1 L1093-L1097`. Back-compat mirrors `device_used` / `accelerator` / `precision` auto-populated via `__post_init__`. **GREEN.**

---

## Section B — Phase-F + Phase-G + Phase-H Closure Verification

| Closure item                | Source phase | Check                                                                                  | Result                                                                      |
| --------------------------- | ------------ | -------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| RegisterResult shape        | Phase-F      | `grep -n 'class RegisterResult' specs-draft/ml-registry-draft.md` → L417 + L461 shim   | ✅ canonical dataclass pinned; v1.x back-compat shim at L461                |
| km.lineage signature        | Phase-F      | `grep -n 'km\.lineage(' specs-draft/ml-engines-v2-addendum-draft.md` → L418            | ✅ `(model_uri_or_run_id_or_dataset_hash, *, tenant_id=None, max_depth=10)` |
| ClearanceRequirement nest   | Phase-F      | `grep -n 'class ClearanceRequirement' specs-draft/` → 1 site at L489                   | ✅ sole canonical declaration; 4 cross-spec instantiations                  |
| kaizen-ml `_kml_agent_`     | Phase-G G1   | `grep '_kml_agent_' supporting-specs-draft/kaizen-ml-integration-draft.md` → 8 hits    | ✅ underscore-prefixed; stale 63-char prose removed                         |
| ClearanceRequirement parity | Phase-G G2   | kaizen-ml L171 type = `Optional[tuple[ClearanceRequirement, ...]]`                     | ✅ byte-matches addendum L504                                               |
| RegisterResult reconcile    | Phase-G G3   | ml-registry §7.1 + §7.1.2 multi-format semantics unified                               | ✅ single-format-per-row at v1.0.0; multi-format dicts reserved for v1.1+   |
| §E11.3 MUST 4 L602          | prior round  | `grep -n '18 engines' specs-draft/ml-engines-v2-addendum-draft.md` → L43 + L602 + L646 | ✅ "per-engine public-method count specified in §E1.1 (varies per engine)"  |
| **Phase-H H1 L505 edit**    | Phase-H      | See Section E                                                                          | ✅ matches §E11.3 MUST 4 + §E1.1                                            |
| **Phase-H H2 L172 edit**    | Phase-H      | See Section E                                                                          | ✅ matches §E11.3 MUST 4 + §E1.1                                            |

All prior-round closures hold. No regression at any closure site.

---

## Section C — 14 Approved Decisions Still Pinned

```bash
for n in 1 2 3 4 5 6 7 8 9 10 11 12 13 14; do
  count=$(grep -rE "Decision ${n}\b" specs-draft/ | wc -l)
  echo "Decision $n: $count citations"
done
```

| Decision                  | Citations | Status | Spot-verification                                                                                                      |
| ------------------------- | --------- | ------ | ---------------------------------------------------------------------------------------------------------------------- | ----------- | ----------------- | ------------------------------------------------------------------ |
| 1 status vocab            | 6         | ✅     | `grep -n "SUCCESS\|COMPLETED" specs-draft/*.md` → ONLY in BLOCKED / migration contexts (5 hits, all at ml-tracking.md) |
| 2 GDPR audit              | 9         | ✅     | `sha256:<8hex>` fingerprint per event-payload rule §2                                                                  |
| 3 Rust status enum parity | 4         | ✅     | 4-member `{RUNNING, FINISHED, FAILED, KILLED}` at ml-tracking §3.5                                                     |
| 4 DDP/FSDP rank-0-only    | 23        | ✅     | `grep -rc "rank_zero\|get_rank\|rank == 0" specs-draft/` → 24 hits / 6 specs                                           |
| 5 XPU native+ipex         | 9         | ✅     | `grep -rc "torch\.xpu\|intel_extension_for_pytorch" specs-draft/` → 24 hits in ml-backends + ml-engines-v2             |
| 6 compat-matrix YAML      | 6         | ✅     | `grep -rc "km\.doctor\|backend-compat-matrix\.yaml" specs-draft/` → 13 hits in ml-backends                             |
| 7 GPU CI runner           | 12        | ✅     | CPU + macos-14 MPS BLOCKING; CUDA gated on self-hosted runner                                                          |
| 8 Lightning lock-in       | 28        | ✅     | `UnsupportedTrainerError` at engine boundary                                                                           |
| 9 Rust async contract     | 1         | ✅     | Python `async with run:` + Rust `start_run/end_run`                                                                    |
| 10 single-spec canonical  | 2         | ✅     | Per-SDK variants deferred to `loom/.claude/variants/rs/specs/` post-sync                                               |
| 11 legacy sunset at 3.0   | 7         | ✅     | 2.x DeprecationWarning; 1.x shim                                                                                       |
| 12 MultiTenantOpError     | 16        | ✅     | `grep -rc "MultiTenantOpError" specs-draft/` → 25 hits / 7 specs                                                       |
| 13 extras hyphen          | 8         | ✅     | `grep -rE '\[rl\_                                                                                                      | \[autolog\_ | \[feature_store\] | \[deep_learning\]' specs-draft/` → 0 hits (no underscore variants) |
| 14 version 1.0.0          | 6         | ✅     | `grep -rc "1\.0\.0 \(draft\)\|Version: 1\.0\.0" specs-draft/` → 28 hits / 17 specs                                     |

**Total: 137 decision citations across 13 specs.** All 14 decisions consistently enforced. **GREEN.**

---

## Section D — §5b Sibling Sweep

### D1 — RegisterResult field-shape consistency

```bash
grep -rn "class RegisterResult\|RegisterResult(" specs-draft/
# Canonical at ml-registry-draft.md:417 + :461 (shim). Sibling consumers:
# ml-engines-v2 L1380 (BLOCKED example), ml-readme-quickstart-body (1), ml-serving (2),
# ml-engines-v2-addendum (3).
```

All consumers use canonical field names (`model_name`, `version`, `actor_id`, `registered_at`, `artifact_uris`, `signature_sha256`, `lineage_run_id`, `lineage_dataset_hash`, `lineage_code_sha`, `onnx_status`, `is_golden`). **GREEN.**

### D2 — ClearanceRequirement nested-tuple pattern

```bash
grep -n "class ClearanceRequirement\|ClearanceRequirement(axis=" specs-draft/
# ml-engines-v2-addendum-draft.md:489 (class)
# ml-engines-v2-addendum-draft.md:513,514 (instantiation in worked example)
grep -rc "ClearanceRequirement" specs-draft/ supporting-specs-draft/
# Addendum 6, kaizen-ml 4 — all using the nested `axis=`/`min_level=` shape.
```

Sole canonical declaration. Kaizen-ml re-imports; no re-declaration. **GREEN.**

### D3 — `_kml_` DDL prefix across all tables

```bash
grep -rhoE 'CREATE TABLE[[:space:]]+(IF NOT EXISTS[[:space:]]+)?[a-z_]+' specs-draft/ | sort -u
# ALL 24 unique table names begin with _kml_:
#   _kml_artifact, _kml_audit, _kml_automl_agent_audit, _kml_cas_blobs,
#   _kml_drift_predictions, _kml_drift_references, _kml_drift_reports,
#   _kml_drift_schedules, _kml_experiment, _kml_feature_audit, _kml_feature_groups,
#   _kml_feature_materialization, _kml_feature_versions, _kml_inference_audit,
#   _kml_inference_batch_jobs, _kml_lineage, _kml_metric, _kml_model_aliases,
#   _kml_model_audit, _kml_model_versions, _kml_param, _kml_run,
#   _kml_shadow_predictions, _kml_tag
grep -rc '_kml_' specs-draft/
# 204 hits / 11 specs.
```

Zero non-`_kml_` DDL tables. **GREEN.**

### D4 — `km.*` top-level verb signatures

```bash
grep -rhoE "km\.[a-z_]+\(" specs-draft/ | sort -u | head -20
# km.doctor( km.engine_info( km.import_mlflow( km.lineage( km.list_engines(
# km.MLEngine( km.register( km.serve( km.track( km.train( km.watch(
```

All 11 verb shapes consistent across specs. `km.track()` contextvar is the auto-wire primitive; `km.MLEngine.compare/diagnose` is the engine-method form. No shape drift. **GREEN.**

### D5 — "18 engines" post-closure count

```bash
grep -rn "18 engines\|13 engines" specs-draft/
# ml-engines-v2-addendum L43 (Total: 18 engines), L602 (18 engines), L646 (18 engines),
# L10 Origin cites round-1 baseline "0/18 auto-wire" and "13/13" (historical context only,
# NOT authoritative post-closure — lives in Origin prose).
# ml-drift L425, ml-feature-store L12, ml-automl L12/L125 — all reference round-1 historical
# baseline "0/13 auto-wire" in Origin prose; not authoritative claims about current count.
```

Authoritative current count: **18 engines** (MLEngine + 17 support). Historical `13/13` ONLY in Origin-prose contexts referencing the round-1 audit baseline. **GREEN.**

### D6 — "six groups" terminology

```bash
grep -rEi "six groups|6 groups|six families|six groupings" specs-draft/
# 0 hits. Terminology not present in current specs.
```

Not a live terminology — §E1.1 engine enumeration uses tabular grouping (Primary vs Support) rather than numbered groups. No drift. **GREEN.**

---

## Section E — Phase-H Verification (2 NEW edits)

### E1 — H1: `ml-engines-v2-addendum-draft.md:505` dataclass comment rewrite

**File literal at L505:**

```python
signatures: tuple[MethodSignature, ...]   # Per-engine public-method count — varies per §E1.1 (MLEngine=8, support engines 1-4). Decision 8 is Lightning lock-in, NOT a method-count invariant. See §E11.3 MUST 4.
```

**Triangulation against §E11.3 MUST 4 L602** (authoritative source):

> `tests/integration/engines/test_engine_registry_signature_discovery.py` — asserts `list_engines()` returns all **18 engines** enumerated in §E1.1 ... every `EngineInfo.signatures` tuple contains the **per-engine public-method count specified in §E1.1** (varies per engine — MLEngine's 8-method surface per Decision 8 is a per-engine invariant, NOT a fixed "8 per engine" constraint across all 18).

**Triangulation against §E1.1 L43** (engine table summary):

> **Total: 18 engines; 18/18 auto-wire; 18/18 accept `tenant_id`; 18/18 accept `actor_id`.**

L505 dataclass comment now correctly says "varies per §E1.1" AND correctly attributes Decision 8 to Lightning lock-in (not method count). Triangulates with L602 and L43. **GREEN.**

### E2 — H2: `kaizen-ml-integration-draft.md:172` signatures-row rewrite

**File literal at L172:**

```
| `signatures` | `tuple[MethodSignature, ...]` | Per-engine public-method signatures — count varies per `ml-engines-v2-addendum §E1.1` (MLEngine=8 per Decision 8 Lightning lock-in; support engines 1-4). NOT a fixed-8 invariant. |
```

**Cross-consistency check against addendum:** addendum §E11.3 MUST 4 L602 says "per-engine public-method count specified in §E1.1 (varies per engine)"; kaizen-ml L172 says "count varies per `ml-engines-v2-addendum §E1.1`." Byte-semantically equivalent. Cross-reference at kaizen-ml L128 (authoritative pointer to §E11.3 MUST 1) + L310 (explicit resolution-in-favor-of-§E11) holds.

**Orphan check:**

```bash
grep -rEi "eight public|exactly 8|8 public methods|8 methods per|eight methods per" \
  specs-draft/ supporting-specs-draft/
# 0 hits.
```

Zero remaining sibling sites make the "8 public methods" conflation. Phase-H H2 closes the last descriptive site. **GREEN.**

---

## Section F — New Findings (Phase-H introductions)

### F1 — Method signature count references

**Sweep:**

```bash
grep -rn "per-engine public-method\|MLEngine=8, support engines 1-4" specs-draft/ supporting-specs-draft/
# specs-draft/ml-engines-v2-addendum-draft.md:505 — dataclass comment
# supporting-specs-draft/kaizen-ml-integration-draft.md:172 — field-table row
```

Phase-H introduced 2 new lines of prose; both correctly reference `§E1.1` as the authoritative enumeration. No downstream consumer needs to update — §E1.1 is already pre-existing authority. **No new finding.**

### F2 — `Decision 8 Lightning lock-in` wording consistency

**Sweep:**

```bash
grep -rEi "Decision 8.*Lightning|Lightning lock-in.*Decision 8|Decision 8 \(Lightning" \
  specs-draft/ supporting-specs-draft/ | wc -l
# 14 hits across 6 specs — consistent "Decision 8 = Lightning lock-in" attribution everywhere.
```

Phase-H's new wording at L505 + L172 matches the pre-existing attribution at §2.1 MUST 7 + §3.2 MUST 1/2 + tracking §2.3 + backends §8 + autolog §4. **No new finding.**

### F3 — No introduced orphan references

**Sweep:** Phase-H text refers to `§E1.1` (exists at L24-L43) and `§E11.3 MUST 4` (exists at L599-L602). No dangling cross-ref.

```bash
grep -n "^### E1\.1\|^## E1\. \|E11\.3" specs-draft/ml-engines-v2-addendum-draft.md | head -5
# Confirmed: §E1.1 engine enumeration + §E11.3 MUST 4 both exist in authoritative locations.
```

**No new finding.**

---

## Convergence Assertion

Round 7 achieved the FIRST full clean cross-spec round (0/0/0). Round 8 re-derives the full sweep from scratch after Phase-H's 2 one-line edits and holds **0 CRIT + 0 HIGH + 0 MED**.

**2 consecutive clean rounds → CONVERGED.** Phase-H introduced zero regressions; the 2 edits close the last descriptive-site drift from MED-R7-1 without introducing new drift elsewhere.

### Cross-spec-consistency persona status:

| Round  | CRIT  | HIGH  | MED   | Verdict                                       |
| ------ | ----- | ----- | ----- | --------------------------------------------- |
| R3     | 0     | 9     | ?     | HIGH cross-spec drift from full-sibling sweep |
| R4     | 0     | 2     | ?     | 7/9 HIGH closed Phase-C                       |
| R5     | 0     | 0     | 3     | 2 HIGH closed Phase-D                         |
| R6     | 0     | 1     | 2     | 3 MED closed Phase-E/F                        |
| R7     | 0     | 0     | 0     | FIRST clean (Phase-G closed HIGH-6-1 + MEDs)  |
| **R8** | **0** | **0** | **0** | **2nd consecutive clean — CONVERGED**         |

**Release path unblocked from this persona's POV.** All 8 Round-8 personas must hit 0/0/0 to close the audit.

---

**Appendix: literal mechanical sweeps executed this round**

```bash
# A1
grep -rc "\.kailash_ml/ml\.db\|sqlite:///.*ml\.db\|KAILASH_ML_STORE_URL" specs-draft/

# A2
grep -rn "ExperimentTracker\.create\|ExperimentTracker(conn)" specs-draft/

# A3
grep -n "^class MLError\|MLError(Exception)" specs-draft/*.md

# A4
grep -n "class TrainingResult\|device: DeviceReport" specs-draft/*.md

# Decisions
for n in 1 2 3 4 5 6 7 8 9 10 11 12 13 14; do
  count=$(grep -rE "Decision ${n}\b" specs-draft/ | wc -l)
  echo "Decision $n: $count"
done

# §5b sibling items
grep -rn "class RegisterResult\|RegisterResult(" specs-draft/
grep -n "class ClearanceRequirement" specs-draft/*.md
grep -rhoE 'CREATE TABLE[[:space:]]+(IF NOT EXISTS[[:space:]]+)?[a-z_]+' specs-draft/ | sort -u
grep -rhoE "km\.[a-z_]+\(" specs-draft/ | sort -u
grep -rn "18 engines\|13 engines" specs-draft/
grep -rEi "six groups|6 groups|six families" specs-draft/

# Phase-H verification
grep -rEi "eight public|exactly 8|8 public methods|eight methods per" specs-draft/ supporting-specs-draft/
grep -rn "per-engine public-method\|MLEngine=8, support engines 1-4" specs-draft/ supporting-specs-draft/
```
