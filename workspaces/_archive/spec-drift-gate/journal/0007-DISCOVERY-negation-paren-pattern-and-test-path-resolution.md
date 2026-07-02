# DISCOVERY — Two ADR-2 keystone calibrations surfaced during S1 pristine-corpus run

**Date:** 2026-04-26
**Phase:** /implement S1
**Workspace:** spec-drift-gate

## Finding

The S1 pristine-corpus acceptance test (`specs/ml-automl.md` + `specs/ml-feature-store.md` → 0 findings) initially produced 7 findings against the freshly-realigned v2 specs. Both findings classes were calibration issues in the gate's design, not spec drift. Both surfaced because the v2 specs adopted authoring conventions the gate's initial implementation hadn't anticipated:

1. **Inline-paren NOT pattern.** Spec text reads: `ValueError (NOT \`InvalidConfigError\` — see § 10 deferral note)`. The gate's INLINE_NEGATION_RE matched `\bNOT\s+(implemented|raised|...)`but not`(NOT \`...\` ...)` — the paren-and-backtick negation form authors use to denote "this class is NOT raised but spec v1 said it was."

2. **Package-relative test paths.** v2 spec § Test Contract cites `tests/unit/test_automl_engine.py` (relative to the package), but the file lives at `packages/kailash-ml/tests/unit/test_automl_engine.py`. The gate's FR-7 sweep called `Path(symbol).exists()` from cwd; the helper `_resolve_test_path` (which tries `cwd + packages/*/`) was written but never wired into the dispatch.

## Why this matters

These are exactly the ADR-2 keystone calibrations that journal `0001-DISCOVERY-marker-convention-keystone.md` predicted: "17 of 28 mitigations collapse onto the marker-convention decision." Both bugs were authoring-convention mismatches, not implementation correctness bugs. Either:

- The spec is wrong → fix the spec
- The gate is wrong → fix the gate

The ADR-2 discipline ("ship calibrations against the live corpus, not band-aids") chooses correctly: the v2 specs are pristine; the gate must match how authors think about negation and paths. Both fixes are now structural, applied at the regex / helper-wiring layer, not at individual spec file level.

## Fixes (committed at `ef9d93aa`)

1. **INLINE_NEGATION_RE** extended with `(NOT \`` and `— NOT `patterns. The full regex now covers:`\bNOT\s+<verb>`, `MUST NOT`, `does/do/is/are/were NOT`, `not implemented/raised/...`, `(NOT \`...\``, `— NOT ...`, `v\d+[- ]spec'd`, `Spec v\d+`, `v\d+ spec`, `fabricated`, `not present`, `does not raise/implement/exist`.

2. **`_resolve_test_path`** wired into FR-7 dispatch. Sweeps now try `Path(symbol)` then `Path("packages") / pkg / symbol` for each pkg. Updated finding message: `"does not exist on disk (searched cwd + packages/*/)"`.

## Replay-ability

The pattern (run pristine-corpus → triage findings as gate-cal vs spec-drift → ship structural fixes) is the discipline the gate enforces from now on. Future calibration iterations that surface against new spec authoring conventions follow the same loop:

1. Findings against v2/v3 spec are presumed to be gate calibration unless proven otherwise
2. Fix is at the regex / dispatch layer
3. Document the new convention in spec § 3 (marker convention) so authors see it
4. Tier 1 test added against the new convention to lock the calibration

## References

- Commit: `ef9d93aa feat(spec-drift-gate): SDG-101..104 — S1 core sweep engine + 4 day-1 sweeps`
- Journal: `0001-DISCOVERY-marker-convention-keystone.md` (ADR-2 keystone — 17/28 mitigations dependency)
- Spec: `specs/spec-drift-gate.md` § 3.3 (section-heading drift) — same class of failure mode at the section level
- Failure-points: `01-analysis/01-failure-points.md` § A1 (informal mention) + § B6 (test file path resolution)
