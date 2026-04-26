---
id: W6-011
title: Create kaizen judges Tier-1 test directory
priority: P0
estimated_sessions: 1
depends_on: []
blocks: []
status: pending
finding_id: F-D-25
severity: HIGH
spec: specs/kaizen-judges.md
domain: kaizen-judges
specialist: kaizen-specialist
wave: W4
---

## Why

W5-D finding F-D-25: spec asserts 24 Tier-1 unit tests at `tests/unit/judges/`; the directory does NOT exist. Either the tests must land or the spec claim must be retracted.

## What changes

- Default per `rules/orphan-detection.md` Rule 1: implement the missing tests, since the spec is recent + the surface is shipped (`packages/kailash-kaizen/src/kaizen/judges/`).
- Create `packages/kailash-kaizen/tests/unit/judges/` with 24 tests covering: LLMJudge construction, position-swap mitigation, microdollar budget enforcement, Delegate routing, error taxonomy, classification redaction.
- Each test follows `rules/testing.md` § Tier 1 conventions (mocks allowed, <1s).

## Capacity check

- LOC: ~400 (24 tests at ~15 LOC each)
- Invariants: 6 (one per testing concern enumerated above)
- Call-graph hops: 2
- Describable: "Create the 24 Tier-1 tests the spec mandates for kaizen.judges."

## Spec reference

- `specs/kaizen-judges.md` § 11 Test Contract

## Acceptance

- [ ] 24 Tier-1 tests exist at `packages/kailash-kaizen/tests/unit/judges/`
- [ ] All pass under `<1s` per test
- [ ] `pytest --collect-only` exit 0
- [ ] No mock leakage to Tier-2 sibling tests
- [ ] CHANGELOG entry

## Dependencies

- None

## Related

- Finding detail: `04-validate/W5-D-findings.md` F-D-25
