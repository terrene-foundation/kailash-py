<!-- expected: findings=1 fr_codes=[FR-7 x1] origin=W6.5_CRIT_2_replay -->
<!-- spec_drift_gate self-test fixture — DO NOT promote to specs/. -->

# Fictitious FeatureStore Spec — W6.5 CRIT-2 Replay

Status: TESTING-FIXTURE — replays Wave 6.5 round-1 FeatureStore draft
fabricated test-file reference. The path below MUST be flagged FR-7 because
no file with that exact name exists on disk (only `test_feature_store.py`
exists, which exercises the legacy module — per W6.5 review § DRAFT 2
CRIT-2).

## Test Contract

The 1.0+ Tier-2 wiring test lives at
`packages/kailash-ml/tests/integration/test_feature_store_wiring.py` (file
existence verified by the audit; specific assertions out of scope for this
spec).
