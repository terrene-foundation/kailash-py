<!-- expected: findings=6 fr_codes=[FR-4 x5, FR-7 x1] origin=W6.5_combined_demo -->
<!-- spec_drift_gate self-test fixture — DO NOT promote to specs/. -->

# Fictitious FeatureStore Spec — W6.5 Combined Demo

Status: TESTING-FIXTURE — combines CRIT-1 + CRIT-2 fabrications into a
single fixture so the gate's exit-code-1 demo regression can run against
one file. Per spec § 8.3 the combined sweep MUST produce exactly 6
findings (5 FR-4 + 1 FR-7).

## Errors

The taxonomy in `kailash_ml.errors` ALSO defines `FeatureGroupNotFoundError`,
`FeatureVersionNotFoundError`, `FeatureEvolutionError`,
`OnlineStoreUnavailableError`, and `CrossTenantReadError`. These are
deferred-feature placeholders.

## Test Contract

The 1.0+ Tier-2 wiring test lives at
`packages/kailash-ml/tests/integration/test_feature_store_wiring.py`.
