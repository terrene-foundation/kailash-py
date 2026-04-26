---
id: W6-022
title: Create test_feature_store_wiring.py (facade-manager-detection §1)
priority: P0
estimated_sessions: 1
depends_on: []
blocks: [W6-021]
status: pending
finding_id: W6.5-followup-5
severity: HIGH
spec: specs/ml-feature-store.md
domain: ml
specialist: ml-specialist
wave: W8
---

## Why

W6.5 review § FeatureStore CRIT-2 + commit `f21e9844` follow-up #5: spec § 11.1 cites `test_feature_store_wiring.py` but file does not exist. The existing `test_feature_store.py` exercises the LEGACY engine, not canonical surface. `rules/facade-manager-detection.md` MUST 1 violation.

## What changes

- Create `packages/kailash-ml/tests/integration/test_feature_store_wiring.py` per `rules/facade-manager-detection.md` § 2 naming.
- Tier-2 test: real `DataFlow(...)` instance + real Postgres + `dataflow.ml_feature_source` binding.
- Cover the 8 conformance assertions in `specs/ml-feature-store.md` § 14.
- Test imports the canonical `kailash_ml.features.FeatureStore`, NOT the legacy `kailash_ml.engines.feature_store.FeatureStore`.

## Capacity check

- LOC: ~280 (8 conformance assertions × ~30 LOC each)
- Invariants: 8 (one per spec § 14 conformance assertion)
- Call-graph hops: 3 (test → DataFlow → FeatureStore → ml_feature_source)
- Describable: "Create the spec-mandated wiring test for canonical FeatureStore."

## Spec reference

- `specs/ml-feature-store.md` § 11.1, § 14
- `rules/facade-manager-detection.md` MUST 1, § 2

## Acceptance

- [ ] File exists at canonical path
- [ ] Imports `kailash_ml.features.FeatureStore` (canonical)
- [ ] All 8 conformance assertions covered
- [ ] Test runs against real Postgres
- [ ] `pytest --collect-only` exit 0
- [ ] CHANGELOG entry

## Dependencies

- None

## Blocks

- W6-021 (Tier-3 e2e depends on this Tier-2 wiring foundation)

## Related

- Source: commit `f21e9844` § Wave 6 follow-ups
- Review: `04-validate/W6.5-v2-draft-review.md` FeatureStore CRIT-2
