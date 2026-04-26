---
id: W6-013
title: Implement CatBoostTrainable adapter (or remove [catboost] extra + spec)
priority: P0
estimated_sessions: 1
depends_on: []
blocks: []
status: pending
finding_id: F-E1-01
severity: HIGH
spec: specs/ml-engines-v2-addendum.md
domain: ml
specialist: ml-specialist
wave: W5
---

## Why

W5-E1 finding F-E1-01: spec mandates `CatBoostTrainable` as a first-class non-Torch family. The `[catboost]` extra ships in `pyproject.toml` but the adapter does not exist.

## What changes

**Default disposition**: implement (per `02-plans/01-wave6-implementation-plan.md` § "Decision-required todos" — small surface, spec mandate, extra is shipped).

- Add `packages/kailash-ml/src/kailash_ml/engines/trainables/catboost_trainable.py` implementing the `Trainable` protocol per `specs/ml-engines-v2-addendum.md`.
- Register in `kailash_ml.engines.__init__.py` discovery + add to `kailash_ml.__all__` per `rules/orphan-detection.md` § 6.
- Tier-1 unit tests (mocked CatBoost) + Tier-2 with real `[catboost]` extra installed.
- COORDINATION NOTE: This wave (W5) batches W6-013 + W6-014 + W6-015 in the ml package. W6-015 is the version owner for kailash-ml CHANGELOG/`__version__`. **Do NOT edit `pyproject.toml` / `__version__` / `CHANGELOG.md` in this todo.**

## Capacity check

- LOC: ~250 (impl + tests)
- Invariants: 5 (Trainable protocol, CatBoost API, classification, env-var, hardware detection)
- Call-graph hops: 3
- Describable: "Implement CatBoostTrainable per spec; register; test."

## Spec reference

- `specs/ml-engines-v2-addendum.md` § Classical-ML surface
- `specs/ml-engines-v2.md` § Trainable protocol

## Acceptance

- [ ] CatBoostTrainable class implements Trainable protocol
- [ ] Registered in `kailash_ml.engines` discovery
- [ ] Tier-1 mocked + Tier-2 real `[catboost]` integration
- [ ] `pip install kailash-ml[catboost]` resolves and imports
- [ ] No CHANGELOG / `__version__` / `pyproject.toml` edits (W6-015 owns)

## Dependencies

- None (parallel with W6-014, W6-015 in W5 wave)

## Coordination

W5 wave batches three ml todos. Version owner: **W6-015**.

## Related

- Finding detail: `04-validate/W5-E1-findings.md` F-E1-01
