---
id: W6-021
title: Tier-3 e2e tests for canonical AutoML + FeatureStore
priority: P0
estimated_sessions: 1
depends_on: [W6-018, W6-022]
blocks: []
status: pending
finding_id: W6.5-followup-4
severity: HIGH
spec: specs/ml-automl.md, specs/ml-feature-store.md
domain: ml
specialist: ml-specialist
wave: W8
---

## Why

W6.5 review surfaced absence of Tier-3 e2e for canonical AutoML + FeatureStore surfaces. Per `rules/testing.md` § "End-to-End Pipeline Regression" — README Quick Start and tutorial-grade pipelines MUST have Tier-3 regressions executing docs-exact code.

## What changes

- Add `packages/kailash-ml/tests/regression/test_automl_engine_e2e_with_real_lightgbm_trainer.py` per spec § 11.3.
- Add `packages/kailash-ml/tests/regression/test_automl_engine_e2e_with_real_postgres.py` per spec § 11.3.
- Add `packages/kailash-ml/tests/regression/test_feature_store_e2e.py` per `specs/ml-feature-store.md` § 11.4.
- Each runs against real Postgres + real engines (no mocks per `rules/testing.md` Tier 3).
- Sequenced AFTER W6-018 (canonical AutoMLEngine) + W6-022 (feature_store_wiring).

## Capacity check

- LOC: ~450 (3 e2e tests at ~150 each)
- Invariants: 6 (one per docs-exact assertion per file)
- Call-graph hops: 4
- Describable: "Three Tier-3 e2e tests against real infra; covers AutoML + FeatureStore canonical surfaces."

## Spec reference

- `specs/ml-automl.md` § 11.3
- `specs/ml-feature-store.md` § 11.4
- `rules/testing.md` § Tier 3 + § "End-to-End Pipeline Regression"

## Acceptance

- [ ] 3 Tier-3 e2e files exist, all named per spec citations
- [ ] All run against real Postgres + real engines
- [ ] CI lane configured (gated by `[postgres]` extra availability)
- [ ] CHANGELOG entry

## Dependencies

- W6-018 (canonical AutoMLEngine via __getattr__ flip)
- W6-022 (feature_store_wiring exists)

## Related

- Source: commit `f21e9844` § Wave 6 follow-ups
- Review: `04-validate/W6.5-v2-draft-review.md` AutoML HIGH-1 + FeatureStore § 11.4
