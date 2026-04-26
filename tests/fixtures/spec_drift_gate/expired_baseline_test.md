<!-- expected: findings=1 fr_codes=[FR-1 x1] origin=expired_baseline_demo -->
<!-- spec_drift_gate self-test fixture — DO NOT promote to specs/. -->

# Fictitious Spec — Expired Baseline Demo

Status: TESTING-FIXTURE — paired with a baseline JSONL whose `added`
date is past 90 days. When the gate runs against this fixture with that
baseline, the FR-1 finding is silenced (pre-existing) AND a WARN line
fires about the entry being past `ageout`. Test harnesses construct the
baseline programmatically with a back-dated `added` so the state machine
exercises `expired` and `expired_2x` paths.

## Surface

`StaleBaselineClass` should never resolve.
