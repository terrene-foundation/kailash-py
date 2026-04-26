---
id: W6-015
title: RLTrainingResult — inherit from TrainingResult; add 8 missing fields
priority: P0
estimated_sessions: 1
depends_on: []
blocks: []
status: pending
finding_id: F-E1-38
severity: HIGH
spec: specs/ml-rl-core.md
domain: ml-rl
specialist: ml-specialist
wave: W5
---

## Why

W5-E1 finding F-E1-38: `RLTrainingResult` does NOT inherit from `TrainingResult`; 8 spec-required fields missing. Breaks the polymorphic contract `km.train` ↔ `km.register` per `rules/zero-tolerance.md` § "Fake integration via missing handoff field".

## What changes

- Update `RLTrainingResult` to inherit from `TrainingResult` per `specs/ml-rl-core.md`.
- Add the 8 missing fields enumerated in finding F-E1-38 (verify list against spec § RL training results).
- Sweep all `RLTrainingResult` construction sites to populate the new fields.
- Add Tier-2 e2e regression: `km.rl_train → km.register` round-trip per `rules/testing.md` § "End-to-End Pipeline Regression".
- **VERSION OWNER for kailash-ml in W5 wave**: bump `__version__`, update `pyproject.toml`, write CHANGELOG entry covering W6-013, W6-014, AND this todo.

## Capacity check

- LOC: ~300 (dataclass change + sweep + e2e test + version bump)
- Invariants: 6 (inheritance, 8-field schema, sweep, e2e regression, CHANGELOG, version)
- Call-graph hops: 4 (km.rl_train → trainer → result → register)
- Describable: "Make RLTrainingResult inherit TrainingResult; add 8 fields; populate at every site; e2e test."

## Spec reference

- `specs/ml-rl-core.md` § RL training results
- `specs/ml-engines-v2.md` § TrainingResult
- `rules/zero-tolerance.md` § "Fake integration via missing handoff field"

## Acceptance

- [ ] `RLTrainingResult(TrainingResult)` inheritance verified
- [ ] All 8 fields present with correct types
- [ ] Every construction site populates the new fields
- [ ] Tier-2 e2e: `km.rl_train(env, policy=..., timesteps=...) → result → km.register(result)` succeeds
- [ ] CHANGELOG covers W5 wave (W6-013 catboost + W6-014 lineage defer + W6-015 RL schema)
- [ ] `__version__` bumped per `rules/zero-tolerance.md` Rule 5

## Dependencies

- None (parallel with W6-013, W6-014; orchestrator integrates at merge per `rules/agents.md` § "Parallel-Worktree Package Ownership Coordination")

## Coordination

**Version owner for W5 wave** (kailash-ml). W6-013 + W6-014 explicitly excluded from version files.

## Related

- Finding detail: `04-validate/W5-E1-findings.md` F-E1-38
