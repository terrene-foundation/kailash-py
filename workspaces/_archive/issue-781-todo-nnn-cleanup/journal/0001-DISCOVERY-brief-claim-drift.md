# DISCOVERY: brief claim drift surfaced by parallel /analyze verification

**Date:** 2026-05-03
**Phase:** /analyze
**Trigger:** `rules/agents.md` MUST "Parallel Brief-Claim Verification" (≥3 distinct claims)

## Verification setup

Three parallel verification agents launched against `briefs/01-issue-781.md`:

- A — counts (244 hits / 118 files / 98 IDs)
- B — top-5 density paths + three taxonomy spot-check examples
- C — three-class taxonomy + `(GOV-NNN)` precedent

Working tree: `main @ dab10c5d`.

## Findings

### A. Counts — DRIFTED on hits/files, FALSE on distinct IDs

| Recipe                             | Brief | Actual | Verdict       |
| ---------------------------------- | ----: | -----: | ------------- |
| Total hits                         |   244 |    254 | DRIFTED (+10) |
| Distinct files                     |   118 |    111 | DRIFTED (-7)  |
| Distinct IDs (narrow regex)        |    98 |     50 | FALSE         |
| Distinct IDs (wider `TODO-[0-9]+`) |     — |     56 | new datapoint |

The brief's narrow regex `TODO-(0[0-9]+|1[0-9]+|2[0-9]+)` requires ≥2 digits AND first digit 0/1/2 — it misses TODO-300+ band (≥6 distinct IDs) AND single-digit forms. Even with the wider regex, distinct IDs land at 56, vastly below the 98 the brief claims. Plausible explanation: the brief author counted line-instances rather than `sort -u` IDs at authoring time.

### B. Density + spot-checks — TRUE

All five top-density file paths exist with exact counts (28/15/8/7/6). All three taxonomy spot-check examples resolve verbatim:

- `src/kailash/runtime/local.py:770` — `# === Coordinated Shutdown (v0.12.0, TODO-015) ===`
- `packages/kailash-dataflow/src/dataflow/__init__.py:146` — `# TODO-153: Type-Aware Field Processor`
- `packages/kailash-dataflow/src/dataflow/migrations/staging_environment_manager.py:12` — `Integration with existing migration components (TODO-137,138,140,142)`

A docs/markdown file (`packages/kaizen-agents/.../00-phase6-overview.md`, 19 hits) ranks #2 in raw density but is correctly excluded from the production-source ranking by extension filter.

### C. Taxonomy — directionally correct, but Class 1 has a sub-distinction the brief misses

30-row uniform sample distribution: **Class 1 = 22 / Class 2 = 1 / Class 3 = 6 / Unclassifiable = 0.**

Extrapolated to 254 hits: roughly 186 Class 1 / 8 Class 2 / 51 Class 3 / 9 ambiguous. The brief's 3-class taxonomy holds — but Class 1 has two distinct sub-shapes that need different rename mechanics:

- **Class 1a (header banner)** — `# === Coordinated Shutdown (v0.12.0, TODO-015) ===`. Section dividers in shipped code. Rename mechanics: replace tracker tag with completed-work parenthetical. The brief's example.
- **Class 1b (module/docstring provenance)** — `Created: 2025-10-27 (Phase 3, Day 2, TODO-174)` or `Mitigation Strategy Engine... — TODO-140 Phase 2`. Module/class docstring lines describing which workstream produced the file. Same intent (breadcrumb to shipped work) but different syntactic shape. Rename mechanics: convert to changelog-style attribution OR delete entirely.

~7% of the sample (#3 registry.py:173, #9 manager.py:37) is genuinely ambiguous between Class 1 and Class 2 — disposition cannot be pattern-matched and requires consulting the external TODO ledger or git blame.

### C. `(GOV-NNN)` precedent — FALSE

Brief proposes renaming Class 1 markers to `(V<release>-NNN)` "matching the existing `(GOV-NNN)` convention used elsewhere in the codebase".

`grep -rnE '\(GOV-[0-9]+\)' src/ packages/*/src/` returns **zero** hits. The cited convention does not exist.

Actual parenthetical conventions in production source (descending count):

| Prefix       | Count | Likely meaning                |
| ------------ | ----: | ----------------------------- |
| `(DF-NNN)`   |    91 | DataFlow error catalog codes  |
| `(TODO-NNN)` |    78 | the pattern being renamed     |
| `(CARE-NNN)` |    50 | CARE governance spec refs     |
| `(ADR-NNN)`  |    32 | Architecture Decision Records |
| `(TSG-NNN)`  |    25 | Trust/Storage Group refs      |
| `(SPEC-NNN)` |    23 | Spec section refs             |
| `(INV-NNN)`  |    14 | Invariant tags                |
| `(BP-NNN)`   |     9 | Bug pattern findings          |

Real precedents: `ADR-NNN`, `BP-NNN`, `DF-NNN`. The brief's proposed `(V<release>-NNN)` (e.g., `(V0.12.0-015)`) has zero in-tree precedent and visually collides with semver pre-release tags.

## Implications for the architecture plan

1. **Adopt the wider regex** `TODO-[0-9]+` as the canonical detection rule — the narrow regex leaks 6+ tracker IDs in the 300+ band.
2. **Update aggregate counts in the plan** to current main: 254 / 111 / 56.
3. **Refine taxonomy** to 1a / 1b / 2 / 3 with explicit rename mechanics per class.
4. **Replace the `(V<release>-NNN)` proposal** with an evidence-grounded convention. Two candidates surface: (a) `(SHIPPED-vX.Y.Z)` (no in-tree precedent but unambiguous), or (b) reuse `(ADR-NNN)` when the work has an ADR/release-note number. Recommendation: open question for human at /todos gate.
5. **Allocate disposition budget for ambiguous Class-1/2 boundary** — ~9 hits in the full set need git-blame / TODO-ledger lookup, not pattern-match.

## Brief corrections to land in 02-plans

The architecture plan's `## Brief corrections` section MUST capture these four items so the plan inherits ground truth, not the brief's authoring-time assertions. Same-class to the kailash-ml-1.5.x-followup precedent (`rules/agents.md` MUST "Parallel Brief-Claim Verification" Origin).
