# Round 6 /redteam Synthesis

**Date:** 2026-04-21
**Scope:** 15 ml-_-draft.md + 6 supporting-_-draft.md + 2 Phase-E meta drafts post Phase-F.

## Aggregate verdict: ALMOST CONVERGED (5/8 personas PASS/CERTIFIED, 3 PARTIAL with 3 unique HIGHs)

| Audit                  | Round-5                 | Round-6                          | Status                       |
| ---------------------- | ----------------------- | -------------------------------- | ---------------------------- |
| Cross-spec consistency | 0 CRIT + 2 HIGH + 1 MED | **0 CRIT + 1 HIGH + 2 MED**      | ~ (progress)                 |
| Closure verification   | 15/16 GREEN, 1 RED (N1) | **10/12 GREEN, 2 HIGH**          | ~                            |
| Newbie UX              | 6/6 GREEN, 1 LOW        | **6/6 GREEN, 0 HIGH/MED/LOW**    | ✅ **CONVERGED** (1st clean) |
| Feasibility            | 9 HIGH, 14/23 READY     | **21/23 READY, 2 HIGH**          | ~ (big progress)             |
| Industry parity        | 24/25 GREEN             | **24/25 GREEN, 0 regressions**   | ✅ STABLE                    |
| TBD re-triage          | 0/0/0 + 0 new           | **0 NEW + 2 RESOLVED + 2 DRIFT** | ✅ **3rd consecutive clean** |
| Senior practitioner    | CERTIFIED + 1 MED       | **CERTIFIED + 29/29, 1 new MED** | ✅ CERTIFIED                 |
| Spec-compliance        | 18/20 + 2 HIGH + 3 MED  | **20/20 PASS + 0 HIGH + 0 MED**  | ✅ **1st clean**             |

**Progress Round-5 → Round-6:**

- Newbie UX: 1 LOW → **0** (first clean round)
- Spec-compliance: 2 HIGH + 3 MED → **0/0** (first clean round)
- Feasibility: 9 HIGH → **2 HIGH** (-7)
- Cross-spec: 2 HIGH → **1 HIGH**
- Closure: 1 RED → converted to 2 HIGH via deeper re-derivation
- Senior-practitioner: CERTIFIED holds, new 1 MED is self-inflicted (Phase-F MED-N2 rewrite shifted counts)
- TBD: third consecutive clean round

## Consolidated open items — 3 unique HIGHs + 5 MEDs (all cluster in Phase-G ~20 min)

### HIGH-R6-A: `kml_agent_*` residual in kaizen-ml (3-persona consensus)

**Reported by:** closure (HIGH-R6-1), cross-spec (HIGH-6-1), feasibility (N1′-RESIDUAL).

`supporting-specs-draft/kaizen-ml-integration-draft.md §5.2` still has **2 DDL tables + 7 prose/FK references** on `kml_agent_*` prefix (L439, L449, L452-L476, L485). Round-5 §G plan spelled out the rename `kml_agent_(traces|trace_events) → _kml_agent_\1`; Round-5 SYNTHESIS F1 shorthand folded it into summary and Phase-F executed from the shorthand.

**L449 rationale prose** is also factually stale: says "matching ML's 63-char Postgres prefix rule" — ML's prefix is now `_kml_*` after F1.

### HIGH-R6-B: kaizen-ml §2.4.2 `clearance_level` field-shape drift (closure)

`kaizen-ml-integration-draft.md L166`: `clearance_level: Optional[Literal["D", "T", "R", "DTR"]]` vs `ml-engines-v2-addendum-draft.md §E11.1 L504`: `Optional[tuple[ClearanceRequirement, ...]]`.

Phase-F's own MED-N2 rewrite split D/T/R axis from L/M/H level into `ClearanceRequirement(axis, min_level)` but did NOT re-derive against kaizen-ml §2.4.2. `rules/specs-authority.md §5b` violation.

### HIGH-R6-C: DDL vs dataclass field-shape drift (feasibility)

`ml-registry-draft.md`: `_kml_model_versions.artifact_uri TEXT NOT NULL` (singular column per row, `UNIQUE (tenant_id, name, version)` + `format VARCHAR(16) NOT NULL`) vs `RegisterResult.artifact_uris: dict[str, str]` (plural dict of format → uri).

Phase-F F3 flipped Python shape from `str` → `dict[str, str]` at §7.1 but did NOT touch the `§5A.2` DDL ~600 LOC earlier. Operational impact: registry write path requires N inserts for N formats; single-row semantics mismatched.

**Recommendation: Shape A** — single-format invariant dict (N=1 per row in v1.0.0; multi-format aggregation by caller). Add §7.1.2 paragraph + §5.6.2 cross-ref + L424 comment expansion (5 min).

### MEDs (5, editorial sweep)

- **MED-R6-1**: `approved-decisions.md §Implications summary L31` says "Postgres tables use `kml_` prefix" — contradicts 5 DDL specs on `_kml_*` (cross-spec + TBD consensus)
- **MED-R6-2**: `ml-engines-v2-draft.md §15.9 L2180` says "five named groups" — now 6 after F5 added Group 6
- **MED-R6-3**: `ml-engines-v2-draft.md §15.9` eager-import example L2250-2263 omits Group 6 `engine_info`/`list_engines` (§18 checklist L2484 DOES mandate them)
- **MED-R6-4**: `kaizen-ml-integration-draft.md L449` rationale "matching ML's 63-char Postgres prefix rule" stale
- **MED-R6-5 (A11-NEW-2, senior)**: `ml-engines-v2-addendum §E11.3 MUST 4` L602 says "13 engines (MLEngine + 12 support engines)" AND "exactly 8 MethodSignature entries" — contradicts §E1.1 L24-41 which enumerates **18 engines** with varying per-engine method counts. kaizen-ml §2.4.7 correctly says "all 18 engines."

## Phase-G plan (~25 min, 3 focused sub-shards)

**G1: kaizen-ml `kml_agent_*` → `_kml_agent_*` sweep (~12 min)**

- `supporting-specs-draft/kaizen-ml-integration-draft.md` §5.2:
  - DDL: `CREATE TABLE kml_agent_traces` → `_kml_agent_traces` (L439)
  - DDL: `CREATE TABLE kml_agent_trace_events` → `_kml_agent_trace_events` (L452)
  - FK ref updates: L463-464, L466, L468, L476
  - §2.5 table list entry: L485
  - Rationale prose fix L449 (kills MED-R6-4)

**G2: ClearanceRequirement propagation to kaizen-ml §2.4.2 (~5 min)**

- Replace `clearance_level: Optional[Literal["D", "T", "R", "DTR"]]` with `required_clearance: Optional[tuple[ClearanceRequirement, ...]]`
- Add import line from `kailash_ml.engines.registry`
- Match §E11.1 byte-for-byte

**G3: RegisterResult DDL reconciliation + editorials (~8 min)**

- `ml-registry-draft.md §7.1 L424`: expand comment on single-format invariant (kills HIGH-R6-C)
- `ml-registry-draft.md` add §7.1.2 "Single-format-per-row invariant" paragraph
- `ml-registry-draft.md §5.6.2`: cross-ref to §7.1.2
- `approved-decisions.md §Implications summary L31`: `kml_*` → `_kml_*` + rationale (kills MED-R6-1)
- `ml-engines-v2-draft.md §15.9 L2180`: "five" → "six" (kills MED-R6-2)
- `ml-engines-v2-draft.md §15.9 L2250-2263`: add `engine_info`/`list_engines` eager imports (kills MED-R6-3)
- `ml-engines-v2-addendum-draft.md §E11.3 MUST 4 L602`: "13 engines" → "18 engines (MLEngine + 17 support engines)" + remove "exactly 8 MethodSignature" (replace with "MethodSignature count per §E1.1") (kills MED-R6-5)

## Round-7 entry criteria

After Phase-G merges:

- Re-run all 8 Round-6 personas (4-by-4)
- Target: **0 CRIT + 0 HIGH + ≤1 MED** across all 8 audits
- Expected: all 8 personas clean → **FIRST FULL CLEAN ROUND**
- Round 8 confirms 2-consecutive-clean convergence exit

## What's CERTIFIED today (unchanged from Round 5)

- 14/14 user-approved decisions pinned + 128 citations across 13 specs
- All 12 Phase-B CRITs closed
- Industry parity 24/25 GREEN with 0 regressions
- Senior-practitioner CERTIFIED + 29/29 rubric items CLOSED
- Newbie UX 6/6 scenarios GREEN (first clean round)
- Spec-compliance 20/20 PASS (first clean round)
- TBD 3 consecutive clean rounds
- 7-package wave release documented
- kailash-rs#502 parity issue updated
