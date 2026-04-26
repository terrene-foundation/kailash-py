---
id: W6-017
title: dataflow.hash() byte-vector pinning tests vs kailash-rs
priority: P1
estimated_sessions: 1
depends_on: []
blocks: []
status: pending
finding_id: F-B-31
severity: HIGH
spec: specs/dataflow-core.md
domain: dataflow
specialist: dataflow-specialist
wave: W6
---

## Why

W5-B finding F-B-31: cross-SDK `dataflow.hash()` parity claim has no byte-vector pinning test, violating `cross-sdk-inspection.md` § 4. Without pinned vectors, a future `hashlib` change could silently diverge from kailash-rs without any test catching it.

## What changes

- Generate ≥3 byte-vector reference cases by running the canonical hash on representative inputs in kailash-rs (esperie/kailash-rs).
- Add `packages/kailash-dataflow/tests/regression/test_hash_byte_vectors.py` with the pinned outputs.
- Mark `@pytest.mark.regression` per `rules/testing.md` § "Regression Testing".
- Test asserts kailash-py output byte-equals the kailash-rs reference.

## Capacity check

- LOC: ~120 (test + 3 reference vectors)
- Invariants: 3 (one per pinned vector)
- Call-graph hops: 1
- Describable: "Pin 3+ byte vectors from kailash-rs; assert kailash-py matches."

## Spec reference

- `specs/dataflow-core.md` § dataflow.hash() cross-SDK parity
- `rules/cross-sdk-inspection.md` § 4 (if loaded — otherwise pattern from kailash-py audit memory)

## Acceptance

- [ ] ≥3 byte-vector test cases land
- [ ] Each cites the kailash-rs commit SHA + test file that produced the reference
- [ ] Test runs <1s per case (Tier 1 boundary)
- [ ] CHANGELOG entry in kailash-dataflow

## Dependencies

- None

## Related

- Finding detail: `04-validate/W5-B-findings.md` F-B-31
