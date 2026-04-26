<!-- expected: findings=5 fr_codes=[FR-4 x5] origin=W6.5_CRIT_1_replay -->
<!-- spec_drift_gate self-test fixture — DO NOT promote to specs/. -->

# Fictitious FeatureStore Spec — W6.5 CRIT-1 Replay

Status: TESTING-FIXTURE — replays Wave 6.5 round-1 FeatureStore draft
fabrications. The five typed exceptions below MUST be flagged FR-4 by the
gate because none exist in `src/kailash/ml/errors.py` (verified at audit
time by `04-validate/W6.5-v2-draft-review.md` § DRAFT 2 CRIT-1).

## Errors

The taxonomy in `kailash_ml.errors` ALSO defines `FeatureGroupNotFoundError`,
`FeatureVersionNotFoundError`, `FeatureEvolutionError`,
`OnlineStoreUnavailableError`, and `CrossTenantReadError`. These are
deferred-feature placeholders.
