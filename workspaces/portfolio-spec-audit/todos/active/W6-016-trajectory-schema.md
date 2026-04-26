---
id: W6-016
title: Implement shared trajectory schema (EpisodeRecord / TrajectorySchema)
priority: P0
estimated_sessions: 1
depends_on: [W6-015]
blocks: []
status: pending
finding_id: F-E1-50
severity: HIGH
spec: specs/ml-rl-align-unification.md
domain: ml-rl-align
specialist: align-specialist
wave: W6
---

## Why

W5-E1 finding F-E1-50: shared trajectory schema (`EpisodeRecord` / `TrajectorySchema`) named in spec as the bridge between `kailash-ml.rl` and `kailash-align`; not implemented. Cited HIGH-1 against spec is closed only on paper.

## What changes

- Implement `EpisodeRecord` + `TrajectorySchema` dataclasses per `specs/ml-rl-align-unification.md`.
- Place in `packages/kailash-ml/src/kailash_ml/rl/trajectory.py` + re-export from `kailash_align`.
- Wire `RLTrainer.collect_trajectories()` and `AlignmentPipeline.consume_trajectories()` to the schema.
- Tier-2 round-trip test: RL produces, Align consumes, asserts byte-stable.
- Sequenced AFTER W6-015 (depends on RLTrainingResult inheriting TrainingResult).

## Capacity check

- LOC: ~350 (schema + 2 wiring sites + Tier-2 test)
- Invariants: 5 (schema shape, RL→Align serialization, byte-stable, classification, tenant_id)
- Call-graph hops: 4
- Describable: "Add shared trajectory dataclasses; wire RL producer + Align consumer; round-trip test."

## Spec reference

- `specs/ml-rl-align-unification.md`
- `specs/ml-rl-core.md`
- `specs/alignment-training.md`

## Acceptance

- [ ] `EpisodeRecord` + `TrajectorySchema` exist + exported
- [ ] RLTrainer + AlignmentPipeline both use the schema
- [ ] Tier-2 round-trip green on real infra
- [ ] CHANGELOG entries in both kailash-ml and kailash-align

## Dependencies

- W6-015 (RLTrainingResult must inherit TrainingResult first so trajectory result fields align)

## Related

- Finding detail: `04-validate/W5-E1-findings.md` F-E1-50
