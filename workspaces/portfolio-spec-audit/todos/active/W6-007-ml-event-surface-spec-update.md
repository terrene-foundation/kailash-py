---
id: W6-007
title: ML event surface — update spec to match shipped API
priority: P0
estimated_sessions: 1
depends_on: []
blocks: []
status: pending
finding_id: F-B-25
severity: HIGH
spec: specs/dataflow-ml-integration.md
domain: dataflow-ml
specialist: dataflow-specialist
wave: W3
---

## Why

W5-B finding F-B-25: `dataflow.ml` ships ML event surface (`emit_train_start/end`, `on_train_start/end`, `ML_TRAIN_*_EVENT`) in `__all__` but the spec § 1.1 does NOT enumerate it. Spec-vs-code drift.

## What changes

- Audit the actual shipped event API in `dataflow.ml.__init__.py`.
- Update `specs/dataflow-ml-integration.md` § 1.1 to enumerate the event-surface symbols with signatures.
- Add a § "Event subscription contract" section if the events have non-trivial semantics.
- Per `rules/specs-authority.md` § 5b, sibling-re-derive against `kaizen-ml-integration.md` and `ml-tracking.md` (both reference event subscribers).

## Capacity check

- LOC: ~100 (spec edit only)
- Invariants: 2 (spec matches shipped surface; siblings consistent)
- Call-graph hops: 1
- Describable: "Update spec to enumerate the shipped event surface."

## Spec reference

- `specs/dataflow-ml-integration.md` § 1.1
- `specs/kaizen-ml-integration.md`, `specs/ml-tracking.md` (siblings)

## Acceptance

- [ ] Every symbol in `dataflow.ml.__all__` event-surface section appears in spec § 1.1
- [ ] Signatures verified against source via line-citation
- [ ] Sibling specs re-derived per `rules/specs-authority.md` § 5b
- [ ] No implementation change (spec-only PR)

## Dependencies

- None

## Related

- Finding detail: `04-validate/W5-B-findings.md` F-B-25
