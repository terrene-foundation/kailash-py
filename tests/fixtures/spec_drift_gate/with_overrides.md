<!-- expected: findings=1 fr_codes=[FR-1 x1] origin=with_overrides_demo -->
<!-- spec_drift_gate self-test fixture — DO NOT promote to specs/. -->

# Fictitious Spec — Override Directives

Status: TESTING-FIXTURE — exercises ADR-2 § 3.2 override directives
inside an allowlisted `## Surface` section. Avoids inline-negation
keywords (`fabricated`, `not implemented`, `deferred`) so the gate
treats the citations as real assertions. Net expected finding count:
1 FR-1.

## Surface

The illustrative `OverrideSkippedClass` is silenced via the skip
directive immediately below.

<!-- spec-assert-skip: class:OverrideSkippedClass reason:"illustrative only" -->

The class `OverrideKeptClass` powers the demo flow. (No skip directive,
so the gate flags it as missing from source.)
