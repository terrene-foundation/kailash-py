---
id: W6-012
title: MLAwareAgent + km.list_engines() — wire OR delete spec § 2.4
priority: P0
estimated_sessions: 1
depends_on: []
blocks: []
status: pending
finding_id: F-D-55
severity: HIGH
spec: specs/kaizen-ml-integration.md
domain: kaizen-ml
specialist: kaizen-specialist
wave: W4
---

## Why

W5-D finding F-D-55: spec § 2.4 mandates `MLAwareAgent` + `km.list_engines()` discovery surface; ZERO production code consumes it. Classic orphan pattern.

## What changes

**Audit step:**
- `grep -rn "MLAwareAgent\|list_engines\|engine_info" packages/`
- Determine if any BaseAgent-tool-construction code path consumes the discovery surface.

**If YES:**
- Wire `BaseAgent` to consume `km.list_engines()` for tool registration
- Add Tier-2 test via `kaizen.BaseAgent` constructing tools from `km.engine_info`

**If NO:**
- Delete spec § 2.4 entirely
- Strip `km.list_engines()` from `kailash_ml.__all__` if unused
- Update spec to say "Agent-side ML discovery is deferred to future work"

## Capacity check

- LOC: ~250 (impl path) or ~100 (delete path)
- Invariants: 4 (discovery, classification, tool registration, BaseAgent contract)
- Call-graph hops: 3
- Describable: "Audit MLAwareAgent consumers; wire if any, delete spec § 2.4 if none."

## Spec reference

- `specs/kaizen-ml-integration.md` § 2.4
- `specs/ml-engines-v2.md` § km.list_engines / km.engine_info

## Acceptance

- [ ] Audit findings in PR body
- [ ] Spec + code aligned
- [ ] If wire: Tier-2 test green
- [ ] If delete: km.list_engines also removed if no other consumer
- [ ] CHANGELOG entry

## Dependencies

- None

## Related

- Finding detail: `04-validate/W5-D-findings.md` F-D-55
