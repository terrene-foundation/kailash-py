# Round 4 /redteam Synthesis

**Date:** 2026-04-21
**Scope:** 15 ml-_-draft.md + 6 supporting-_-draft.md specs post-Phase-D.

## Aggregate verdict: ALMOST CONVERGED — 1 more Phase-E shard needed

| Audit                  | Target                      | Round-3             | Round-4                                                    | Met?          |
| ---------------------- | --------------------------- | ------------------- | ---------------------------------------------------------- | ------------- |
| Cross-spec consistency | 0 CRIT + 0 HIGH (spec)      | 0 + 9               | **0 + 0** (+ 1 operational HIGH-11 README, 1 MED cosmetic) | ✅ spec scope |
| Closure verification   | ≥95% GREEN, 0 RED           | 85.7%, 10 YELLOW    | **31/31 Phase-D GREEN, 3 YELLOW, 0 RED**                   | ~             |
| Newbie UX              | 6/6 GREEN, 0 NEW HIGH       | 6/6 + 3 NEW HIGH    | **6/6 + 0 NEW HIGH, 1 NEW MED**                            | ✅            |
| Feasibility            | 0 HIGH, 21/21 READY         | 9 HIGH, 9/15 READY  | **5 HIGH, 17/21 READY**                                    | —             |
| Industry parity        | ≥24/25 GREEN                | 23/25               | **24/25**                                                  | ✅            |
| TBD re-triage          | 0 NEEDS-DECISION, 0 BLOCKER | 0/0 + 12 drifts     | **0/0 + 0 new**                                            | ✅            |
| Senior practitioner    | CERTIFIED                   | CONDITIONAL (26/29) | **CERTIFIED** (+1 new HIGH A10-3)                          | ✅            |
| Spec-compliance        | every PASS, ≤3 MED          | 14 HIGH + 5 MED     | **14/14 PASS + 2 MED**                                     | ✅            |

**6 of 8 personas converged or certified.** Remaining gaps consolidate into a single Phase-E shard.

## Progress Round-3 → Round-4

- **CRITs:** 0 → 0 ✅
- **HIGHs:** ~47 → **6 unique** (Phase-D closed 41 findings)
- **2026-27 architectures:** 0 FAIL (unchanged)
- **Industry parity:** 23/25 → **24/25** ✅
- **Newbie scenarios:** 6/6 GREEN (unchanged, 0 new HIGHs this round)
- **Differentiators:** 3 EXTENDED + 3 STRENGTHENED → **4 EXTENDED + 2 STRENGTHENED**
- **Senior-practitioner verdict:** CONDITIONAL → **CERTIFIED**

## Consolidated open items (6 unique HIGHs + 3 YELLOWs + 2 MEDs)

### Remaining HIGHs (6 unique)

1. **B3** — `EngineInfo` / `MethodSignature` / `ParamSpec` dataclasses still pseudocode in ml-engines-v2-addendum §E11.1 (needs concrete `@dataclass(frozen=True)` blocks with typed fields)
2. **B4** — `LineageGraph` / `LineageNode` / `LineageEdge` still bullet-list in §E10.2 (needs dataclass; blocks ml-dashboard §4.1 REST contract)
3. **B9** — `AutoMLEngine` demotion-vs-first-class contradiction (ml-engines-v2 §8.2 line 1488 "demoted" vs ml-automl §2.1 line 50 "first-class")
4. **N1** — DDL prefix drift: 5 specs use `kml_*`; ml-drift alone uses `_kml_*`; ALL prose uses `_kml_*`. Violates `dataflow-identifier-safety.md` Rule 2.
5. **B11'** — ml-serving §2.5.1 cross-refs ml-registry §4 for ONNX probe, but §4 is Aliases section (needs probe + `unsupported_ops` column in `kml_model_versions`)
6. **A10-3** — Senior practitioner's cross-spec drift: ml-serving references ml-registry §4 for ONNX probe definition but registry never declares `unsupported_ops` / `opset_imports` / `ort_extensions` fields

### Remaining YELLOWs (3)

- **YELLOW-E** — EngineInfo+MethodSignature dataclass declarations elided (duplicate of B3)
- **YELLOW-F** — LineageGraph dataclass shape mismatch (duplicate of B4)
- **YELLOW-I** — AutoMLEngine demoted-vs-first-class contradiction (duplicate of B9)

### Remaining MEDs (2)

- **MED-R1** — ml-rl-core-draft.md L3 uses `**Version:** 1.0.0 (draft)` (bold); one-char fix
- **MED-R2** — ml-serving §2.5.3 cites "Decision 8" for pickle-fallback-gate; Decision 8 is Lightning lock-in, not pickle discipline. §15 L1191 already clarifies.

### Operational items (not spec-scope; tracked for release PR)

- **HIGH-11** — `packages/kailash-ml/README.md` Quick Start rewrite + version 0.9.0 → 1.0.0 (release-PR scope)
- **M-1 (newbie-UX)** — `ml-engines-v2 §2.1` should add env-var MUST clause for `KAILASH_ML_STORE_URL` to fix authority chain
- **Residual competitive risk** — `SystemMetricsCollector` primitive (~200 LOC, Phase-F post-1.0) + `ml-notebook.md` stub (50 LOC, v1.1)

## Phase-E plan (single session, ~90 min)

Collapse the 6 HIGHs + 3 YELLOWs + 2 MEDs into **3 parallel sub-shards:**

- **E1: Dataclass completion** — B3 + B4 (+ YELLOW-E + YELLOW-F duplicates). Write full `@dataclass(frozen=True)` blocks for `EngineInfo`, `MethodSignature`, `ParamSpec`, `LineageGraph`, `LineageNode`, `LineageEdge`. ~40 min.
- **E2: Cross-spec drift cleanup** — N1 (DDL prefix `kml_*` vs `_kml_*` unification, sweep 6 specs) + B9 + YELLOW-I (AutoMLEngine contradiction) + B11' + A10-3 (ONNX probe in ml-registry) + M-1 (env-var authority MUST clause) + MED-R2 (pickle-gate citation fix). ~40 min.
- **E3: Cosmetic + operational hooks** — MED-R1 (one-char Version bold fix) + HIGH-11 prep (draft the canonical 5-line Quick Start body for release-PR). ~10 min.

## Round-5 entry criteria

After Phase-E merges, run the same 8-persona panel. Convergence achieved when 2 consecutive rounds (4 and 5, OR 5 and 6) show:

- 0 CRIT + 0 HIGH across all 8 personas
- ≤3 MED across all personas
- 0 RED in closure verification
- CERTIFIED from senior practitioner
- ≥24/25 GREEN from industry parity

Round-4 hits every bar EXCEPT feasibility HIGHs and senior's 1 NEW A10-3. After Phase-E, Round 5 is expected to achieve all bars → first clean round. Round 6 confirms.

## What's certified today

- 14/14 user-approved decisions propagated and verified
- All 12 Phase-B CRITs closed
- All 9 Round-3 HIGHs in spec scope closed
- 6-persona Round-4 convergence (newbie-UX + cross-spec + industry + TBD + senior + spec-compliance)
- Industry parity target met (24/25 GREEN)
- Senior-practitioner CERTIFIED verdict
- 7-package wave release coordination documented
- kailash-rs#502 parity issue updated with wave context
