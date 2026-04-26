---
id: W6-023
title: Strip "W31 31b" workspace artifact from features/store.py:354-361 ImportError
priority: P2
estimated_sessions: 1
depends_on: []
blocks: []
status: pending
finding_id: W6.5-followup-6
severity: LOW
spec: specs/ml-feature-store.md
domain: ml
specialist: ml-specialist
wave: W8
---

## Why

W6.5 review § FeatureStore HIGH-2 + commit `f21e9844` follow-up #6: runtime `ImportError` message at `features/store.py:354-361` references "W31 31b" — a workspace artifact, not a durable cross-spec citation. User-facing strings MUST cite specs, not workspace history per `rules/specs-authority.md` § 1.

## What changes

- Edit `packages/kailash-ml/src/kailash_ml/features/store.py:354-361`.
- Replace "tracked as W31 31b in specs/dataflow-ml-integration.md §1.1" with "see specs/dataflow-ml-integration.md §1.1".
- Verify spec § 6.x and § 16.1 references in the spec itself are also W31-free (W6.5 commit may have already cleaned them; double-check).

## Capacity check

- LOC: ~10 (one error message)
- Invariants: 1 (no workspace artifact in user-facing string)
- Call-graph hops: 1
- Describable: "Strip W31 31b from one ImportError message."

## Spec reference

- `specs/ml-feature-store.md` § 6.2 / § 16.1
- `rules/specs-authority.md` § 1 (specs are project-state truth, not workspace history)

## Acceptance

- [ ] No "W31 31b" or "W31-31b" in `features/store.py` runtime strings
- [ ] Cross-check spec ml-feature-store.md is also W31-free
- [ ] CHANGELOG entry (docs-only)

## Dependencies

- None

## Related

- Source: commit `f21e9844` § Wave 6 follow-ups
- Review: `04-validate/W6.5-v2-draft-review.md` FeatureStore HIGH-2
