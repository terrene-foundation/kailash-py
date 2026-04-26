---
id: W6-019
title: Strip stale FeatureSchema docstring at automl/engine.py:7-12
priority: P2
estimated_sessions: 1
depends_on: []
blocks: []
status: pending
finding_id: W6.5-followup-2
severity: LOW
spec: specs/ml-automl.md
domain: ml
specialist: ml-specialist
wave: W7
---

## Why

W6.5 review § AutoML LOW-2 + commit `f21e9844` follow-up #2: engine module docstring at `automl/engine.py:7-12` mentions FeatureSchema auto-derivation; not implemented; misleading.

## What changes

- Edit docstring lines 7-12 in `packages/kailash-ml/src/kailash_ml/automl/engine.py` to remove the FeatureSchema auto-derivation claim.
- Replace with an accurate description of the engine's actual ParamSpec contract.

## Capacity check

- LOC: ~10 (docstring only)
- Invariants: 1 (claim accuracy)
- Call-graph hops: 0
- Describable: "Fix one inaccurate docstring."

## Spec reference

- `specs/ml-automl.md` § 3.1

## Acceptance

- [ ] Docstring no longer claims FeatureSchema auto-derivation
- [ ] Docstring accurately reflects ParamSpec construction
- [ ] No CHANGELOG entry needed (docstring-only)

## Dependencies

- None

## Related

- Source: commit `f21e9844` § Wave 6 follow-ups
- Review: `04-validate/W6.5-v2-draft-review.md` AutoML LOW-2
