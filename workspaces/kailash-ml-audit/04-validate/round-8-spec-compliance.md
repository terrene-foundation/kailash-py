# Round 8 Spec-Compliance Audit

**Date:** 2026-04-21
**Protocol:** `/Users/esperie/repos/loom/kailash-py/.claude/skills/spec-compliance/SKILL.md`
**Scope:** 17 specs under `workspaces/kailash-ml-audit/specs-draft/` + 6 specs under `workspaces/kailash-ml-audit/supporting-specs-draft/` post Phase-H (2026-04-21).

Round-8 is the 3rd consecutive confirmation after Round-6 / Round-7 clean spec-compliance runs. Phase-H (2 one-line descriptive edits) merged 2026-04-21 to close MED-R7-1 at `ml-engines-v2-addendum-draft.md:505` and `kaizen-ml-integration-draft.md:172`.

Every row below re-derived from literal `grep -n` / `rg` / `Read` against the specs — no inheritance from Round 6 or Round 7 outputs per SKILL.md self-report-trust-ban + `rules/testing.md` audit-mode rules.

## Headline: 20/20 PASS + 0 HIGH + 0 MED + G-REG 7/7 + H-REG 4/4

Third consecutive clean round. Δ vs Round 7: ±0 PASS, ±0 HIGH, ±0 MED; 4 new Phase-H regression guards all PASS on first derivation. Convergence exit bar (2 consecutive clean rounds) met at Round 7 and reconfirmed at Round 8.

## Assertion table (confirmation round — brief form)

| AC-N  | Assertion                                                     | Expected | Actual                                                                                                     | Verdict  |
| ----- | ------------------------------------------------------------- | -------- | ---------------------------------------------------------------------------------------------------------- | -------- |
| AC-1  | `MLError` hierarchy + `ParamValueError` multi-inherit         | 11+2+1   | L856 MLError; L860-870 11 children; L873 UnsupportedTrainerError; L891 ParamValueError                     | **PASS** |
| AC-2  | `ExperimentTracker.create()` + `get_current_run()` cross-refs | ≥1+≥1    | 51 hits across 9 files (ml-tracking 22, engines-v2 8, rl-core 6, diagnostics 4, ...)                       | **PASS** |
| AC-3  | 24× `CREATE TABLE _kml_*`; 0× bare `CREATE TABLE kml_*`       | 24 / 0   | 24 confirmed (tracking=8, drift=4, serving=3, feature-store=4, automl=1, registry=4); 0 bare               | **PASS** |
| AC-4  | `RegisterResult` §7.1 + §7.1.1 shim + §7.1.2 invariant        | all 3    | L424 `artifact_uris: dict[str,str]`; L455-486 shim+DeprecationWarning; L488-507 invariant section          | **PASS** |
| AC-5  | `EngineInfo`/`MethodSignature`/`ParamSpec` frozen dataclasses | 3        | L457 ParamSpec, L470 MethodSignature, L494 EngineInfo; `signatures: tuple[MethodSignature,...]` at L505    | **PASS** |
| AC-6  | `LineageGraph`/`LineageNode`/`LineageEdge` frozen dataclasses | 3        | L368 LineageNode, L384 LineageEdge, L399 LineageGraph                                                      | **PASS** |
| AC-7  | `ClearanceRequirement` axis/level split                       | 3 decls  | L485 ClearanceLevel, L486 ClearanceAxis, L489 class + L491-492 fields                                      | **PASS** |
| AC-8  | km.\* 15-verb surface Groups 1–6                              | 13+2=15  | Group 1 L2185-2198 = 13; Group 6 L2233-2235 = 2. Total 15 verbs.                                           | **PASS** |
| AC-9  | 14 approved-decisions cited                                   | ≥128     | **129 cites** across 13 files (stable; matches Round-7 129)                                                | **PASS** |
| AC-10 | `Version: 1.0.0 (draft)` header                               | 17/17    | 17/17 specs emit `Version: 1.0.0 (draft)` on L3. Zero variants.                                            | **PASS** |
| AC-11 | Cache keyspace `kailash_ml:v1:{tenant_id}:...`                | ≥30/≥6   | 32 hits across 6 specs (tracking=11, engines-v2=9, feature-store=5, rl-core=3, rl-algorithms=2, serving=2) | **PASS** |
| AC-12 | Status enum {RUNNING,FINISHED,FAILED,KILLED}                  | 4 files  | 4 files match (automl, serving, tracking, dashboard). PENDING extension orthogonal.                        | **PASS** |
| AC-13 | `resolve_store_url()` wiring                                  | ≥16/≥5   | 18 hits across 6 specs (engines-v2=6, dashboard=8, tracking/feature-store/automl/registry=1 each)          | **PASS** |
| AC-14 | ONNX probe + `unsupported_ops` + typed errors                 | all      | 30 hits across 4 specs (registry=14, serving=13, tracking=2, autolog=1)                                    | **PASS** |
| AC-15 | `RegisterResult.is_golden` + `ImmutableGoldenReferenceError`  | all      | 29 hits across 3 files (registry=26, engines-v2=2, tracking=1)                                             | **PASS** |
| AC-16 | Lightning hard lock-in + `UnsupportedTrainerError`            | all      | 51 hits across 6 specs (engines-v2=33, tracking=5, backends=5, diagnostics=4, automl=3, serving=1)         | **PASS** |
| AC-17 | DDP rank-0 + Accelerate `is_main_process` dual-axis           | ≥25/≥5   | 26 hits across 6 specs (autolog=11, diagnostics=9, tracking=2, rl-core=2, engines-v2=1, serving=1)         | **PASS** |
| AC-18 | XPU dual-path (torch.xpu + ipex fallback)                     | both     | 10 hits across 2 specs (backends=9, engines-v2=1)                                                          | **PASS** |
| AC-19 | `km.engine_info()` + `km.list_engines()` discovery            | all      | 7 hits in addendum §E11.2 (L562 header, L567 list_engines, L575 engine_info, 4 usage)                      | **PASS** |
| AC-20 | Agent Tool Discovery §E11.3 4 MUST clauses                    | 4 MUSTs  | L586 MUST 1 SSoT; L590 MUST 2 decorator; L594 MUST 3 atomic version; L598-602 MUST 4 Tier 2 wiring         | **PASS** |

## Phase-G regression guards (7/7 PASS)

| Guard   | Assertion                                                                    | Expected                                     | Actual                                                                                           | Verdict  |
| ------- | ---------------------------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------------------ | -------- |
| G-REG-1 | kaizen-ml §2.4.2 clearance_level type matches addendum §E11.1 L504 byte-wise | `Optional[tuple[ClearanceRequirement, ...]]` | kaizen-ml L171 byte-matches addendum L504; L158 import; L193/L202 nested-axis rationale          | **PASS** |
| G-REG-2 | ml-registry §7.1.2 "Single-Format-Per-Row Invariant" section exists          | §7.1.2 header                                | L488 `#### 7.1.2 Single-Format-Per-Row Invariant (v1.0.0)` — sole match                          | **PASS** |
| G-REG-3 | approved-decisions.md says `_kml_` (leading underscore)                      | literal `_kml_`                              | L31 "Postgres tables use `_kml_` prefix ..." + per-spec unification enumeration                  | **PASS** |
| G-REG-4 | ml-engines-v2 §15.9 "six named groups" (not "five")                          | 1 / 0                                        | L2180 sole "six named groups" match; 0 "five named groups" matches                               | **PASS** |
| G-REG-5 | ml-engines-v2 eager-imports `engine_info, list_engines`                      | ≥1                                           | L2255 sole match: `from kailash_ml.engines.registry import engine_info, list_engines  # Group 6` | **PASS** |
| G-REG-6 | ml-engines-v2-addendum §E11.3 MUST 4 says "18 engines"                       | 3 / 0                                        | 3 "18 engines" hits (L43 §E1.1, L602 MUST 4, L646 tier-2 E2E); 0 "13 engines" hits               | **PASS** |
| G-REG-7 | No bare `kml_agent_` (all carry leading underscore)                          | 0                                            | Zero matches in supporting-specs-draft/ for `[^_]kml_agent_\|^kml_agent_`                        | **PASS** |

## Phase-H regression guards (4/4 PASS — first derivation)

| Guard   | Assertion                                                                                                  | Command                                                                                                               | Expected | Actual   | Verdict  |
| ------- | ---------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | -------- | -------- | -------- |
| H-REG-1 | MED-R7-1 site A purged — no "8 public methods per Decision 8" in ml-engines-v2-addendum                    | `grep -c '8 public methods per Decision 8' specs-draft/ml-engines-v2-addendum-draft.md`                               | 0        | 0        | **PASS** |
| H-REG-2 | Phase-H site A new prose — "Per-engine public-method count" exists in ml-engines-v2-addendum               | `grep -c 'Per-engine public-method count' specs-draft/ml-engines-v2-addendum-draft.md`                                | 1        | 1 (L505) | **PASS** |
| H-REG-3 | MED-R7-1 site B purged — no "Eight public-method signatures (Decision 8 lock-in)" in kaizen-ml-integration | `grep -c 'Eight public-method signatures (Decision 8 lock-in)' supporting-specs-draft/kaizen-ml-integration-draft.md` | 0        | 0        | **PASS** |
| H-REG-4 | Phase-H site B new prose — "Per-engine public-method signatures" exists in kaizen-ml-integration           | `grep -c 'Per-engine public-method signatures' supporting-specs-draft/kaizen-ml-integration-draft.md`                 | 1        | 1 (L172) | **PASS** |

**Phase-H exact content at L505 (addendum):** `signatures: tuple[MethodSignature, ...]   # Per-engine public-method count — varies per §E1.1 (MLEngine=8, support engines 1-4). Decision 8 is Lightning lock-in, NOT a method-count invariant. See §E11.3 MUST 4.`

**Phase-H exact content at L172 (kaizen-ml):** ``Per-engine public-method signatures — count varies per `ml-engines-v2-addendum §E1.1` (MLEngine=8 per Decision 8 Lightning lock-in; support engines 1-4). NOT a fixed-8 invariant.``

Both edits carry the correct clarification: method count varies per-engine per §E1.1; Decision 8 is Lightning-lock-in (trainer family), not a method-count invariant. The three contradicting failure modes MED-R7-1 flagged — (a) wrong attribution to Decision 8, (b) implied fixed-8-count across support engines, (c) contradicts §E11.1 TrainingPipeline worked example with one MethodSignature — are all closed.

## Open findings

**0 CRIT / 0 HIGH / 0 MED / 0 LOW.** Third consecutive clean round.

Ancillary observations (not findings):

- AC-9 decision citation count stable at 129 (Round-7 baseline). Phase-H's 2 descriptive edits neither added nor removed Decision citations.
- AC-12 `PENDING` status extension in ml-automl + ml-serving remains orthogonal to Decision 3 tracker 4-member enum — same disposition as Round 6 and Round 7.

## Convergence assertion (3rd consecutive clean round)

**Round-6:** 20/20 PASS + 0 HIGH + 0 MED (first clean).
**Round-7:** 20/20 PASS + 0 HIGH + 0 MED + 7/7 G-REG guards (second consecutive clean — convergence exit bar met per Round-5 brief).
**Round-8 (this round):** 20/20 PASS + 0 HIGH + 0 MED + 7/7 G-REG + 4/4 H-REG guards (third consecutive clean — MED-R7-1 closed by Phase-H, verified on first derivation).

The convergence bar ("two consecutive clean rounds = convergence exit") was met at Round 7 and is reconfirmed at Round 8 with the Phase-H closure of the sole outstanding item (MED-R7-1). The spec-compliance trajectory from Round-4 → Round-8 shows monotonic narrowing: A10-3 HIGH (R4) → A11-NEW-1/2 MED (R5-R6) → MED-R7-1 MED (R7, within-file descriptive) → 0 MED (R8). Severity and scope both monotonically decreasing to zero.

Spec-compliance is **CONVERGED** (3 consecutive clean rounds). All 29 checks (20 AC + 7 G-REG + 4 H-REG) PASS under re-derivation from literal grep/Read commands.

## Round-8 entry assertions satisfied

All 9 Round-8 entry assertions listed in Round-7 report §"Round-8 entry assertions" pass under re-derivation:

1. **AC-3 + G-REG-7 prefix stability** — `CREATE TABLE _kml_` = 24; bare `kml_agent_` = 0. ✓
2. **AC-4 + G-REG-2 RegisterResult shape** — §7.1 dict field + §7.1.1 shim + §7.1.2 invariant section at L488. ✓
3. **AC-10 version uniformity** — 17/17 `Version: 1.0.0 (draft)` headers. ✓
4. **AC-13 env-var plumbing** — `resolve_store_url` = 18 hits across 6 specs. ✓
5. **AC-17 rank-0 dual-axis** — `is_main_process` subset = 26 hits across 6 specs. ✓
6. **AC-20 + G-REG-6 E11.3 discovery** — 4 MUST clauses + "18 engines" MUST 4 at L602. ✓
7. **G-REG-1 kaizen-ml clearance** — `Optional[tuple[ClearanceRequirement, ...]]` byte-matches addendum. ✓
8. **G-REG-4 "six named groups"** — 0 "five named groups" matches. ✓
9. **G-REG-5 eager-import** — `engine_info, list_engines` = 1 match at L2255. ✓

## Section summary

- **Round-8 outcome:** 3rd consecutive clean spec-compliance round. 20/20 PASS + 7/7 G-REG guards + 4/4 H-REG guards. 0 CRIT + 0 HIGH + 0 MED + 0 LOW.
- **Convergence status:** CONVERGED (3 consecutive clean rounds; Round-7 already met 2-consecutive bar, Round-8 reconfirms post-Phase-H).
- **Full-sibling sweep compliance (`rules/specs-authority.md §5b`):** every check re-derived against the full 23-spec surface (17 ml-\*-draft + 6 supporting-specs-draft). No narrow-scope inheritance.
- **Zero self-report inheritance:** every assertion re-derived from literal `grep` / `Read` against the specs-draft/ + supporting-specs-draft/ surfaces. Round-7 outputs used only for structural baseline (assertion enumeration), not as evidence.
- **Phase-H closure verified:** MED-R7-1 descriptive-site drift closed cleanly; no regressions introduced at either site; sibling locations unaffected.

## Files referenced (absolute paths)

Specs under `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/`:

- `ml-engines-v2-draft.md`, `ml-engines-v2-addendum-draft.md`, `ml-tracking-draft.md`, `ml-registry-draft.md`, `ml-serving-draft.md`, `ml-drift-draft.md`, `ml-feature-store-draft.md`, `ml-automl-draft.md`, `ml-dashboard-draft.md`, `ml-diagnostics-draft.md`, `ml-autolog-draft.md`, `ml-backends-draft.md`, `ml-rl-core-draft.md`, `ml-rl-algorithms-draft.md`, `ml-rl-align-unification-draft.md`, `ml-readme-quickstart-body-draft.md`, `ml-index-amendments-draft.md`

Supporting specs under `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/`:

- `kaizen-ml-integration-draft.md`, `align-ml-integration-draft.md`, `dataflow-ml-integration-draft.md`, `nexus-ml-integration-draft.md`, `pact-ml-integration-draft.md`, `kailash-core-ml-integration-draft.md`

Baseline (not trusted evidence):

- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-7-spec-compliance.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-7-SYNTHESIS.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/approved-decisions.md`

---

_End of report. Authored per `skills/spec-compliance/SKILL.md` self-report-trust-ban + `rules/specs-authority.md §5b` full-sibling-sweep + `rules/testing.md` audit-mode re-derivation. Verdict: **20/20 PASS + 7/7 G-REG + 4/4 H-REG — 3rd consecutive clean round. Spec-compliance CONVERGED.**_
