---
id: W6-004
title: Delete legacy engines/inference_server.py
priority: P1
estimated_sessions: 1
depends_on: []
blocks: []
status: pending
finding_id: F-E1-28
severity: HIGH
spec: specs/ml-serving.md
domain: ml
specialist: ml-specialist
wave: W2
---

## Why

W5-E1 finding F-E1-28: dual `InferenceServer` classes exist — `engines/inference_server.py` (legacy) + `serving/server.py` (canonical 1.0+). `rules/orphan-detection.md` §3 mandates "Removed = Deleted, Not Deprecated" — the legacy class is an orphan that confuses consumers about which is canonical.

## What changes

- Delete `packages/kailash-ml/src/kailash_ml/engines/inference_server.py`.
- Sweep all imports of the deleted symbol per `rules/orphan-detection.md` Rule 4.
- Update spec `specs/ml-serving.md` to remove any cross-reference.
- Confirm no test file references the legacy class (Rule 4: "API removal MUST sweep tests in same PR").

## Capacity check

- LOC: ~−400 (deletion-heavy)
- Invariants: 2 (no production import; no test reference)
- Call-graph hops: 1
- Describable: "Delete legacy InferenceServer file; sweep imports + tests."

## Spec reference

- `specs/ml-serving.md`
- `rules/orphan-detection.md` § 3, § 4

## Acceptance

- [ ] File deleted
- [ ] `grep -rn "engines.inference_server\|engines/inference_server"` returns zero matches in production code
- [ ] All test imports of legacy class deleted/migrated to canonical
- [ ] `pytest --collect-only` exit 0
- [ ] CHANGELOG entry in kailash-ml

## Dependencies

- None

## Related

- Finding detail: `04-validate/W5-E1-findings.md` F-E1-28
