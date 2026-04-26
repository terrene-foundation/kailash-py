---
id: W6-018
title: Flip kailash_ml/__init__.py:593 __getattr__ map → canonical AutoMLEngine
priority: P0
estimated_sessions: 1
depends_on: []
blocks: []
status: pending
finding_id: W6.5-followup-1
severity: HIGH
spec: specs/ml-automl.md
domain: ml
specialist: ml-specialist
wave: W7
---

## Why

W6.5 review § AutoML HIGH-2 + commit `f21e9844` follow-up #1: top-level `kailash_ml.AutoMLEngine` resolves via `__getattr__` to LEGACY scaffold `kailash_ml.engines.automl_engine`, NOT the canonical `kailash_ml.automl.engine`. Two coexisting surfaces is transitional state, not permanent.

## What changes

- Edit `kailash_ml/__init__.py:593` `_LAZY_MAP` entry: `"AutoMLEngine": "kailash_ml.automl.engine"` (replace legacy module path).
- Verify `kailash_ml.AutoMLEngine` and `from kailash_ml.automl import AutoMLEngine` resolve to the SAME class.
- Add Tier-1 test: `from kailash_ml import AutoMLEngine` + `from kailash_ml.automl import AutoMLEngine`; assert `is` identity.
- Update `specs/ml-automl.md` § 1.3 "Two Coexisting Surfaces" to single canonical surface.

## Capacity check

- LOC: ~50 (1 line code change + 1 test + spec edit)
- Invariants: 2 (canonical resolution, identity)
- Call-graph hops: 1
- Describable: "Flip __getattr__ map; assert single canonical AutoMLEngine class."

## Spec reference

- `specs/ml-automl.md` § 1.3
- `rules/orphan-detection.md` § 3

## Acceptance

- [ ] `_LAZY_MAP["AutoMLEngine"] == "kailash_ml.automl.engine"`
- [ ] Tier-1 identity test in `tests/unit/test_kailash_ml_lazy_map.py`
- [ ] Spec § 1.3 updated to remove "Two Coexisting Surfaces"
- [ ] Legacy `kailash_ml.engines.automl_engine` deleted OR renamed `_legacy_automl_engine.py` (deprecation marker)
- [ ] CHANGELOG entry

## Dependencies

- None (W6.5 follow-up is post-spec realignment, code is ready)

## Related

- Source: commit `f21e9844` § Wave 6 follow-ups
- Review: `04-validate/W6.5-v2-draft-review.md` AutoML HIGH-2
