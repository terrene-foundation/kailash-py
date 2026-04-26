---
id: W6-009
title: Reconcile nexus.register_service / InferenceServer.as_nexus_service to one path
priority: P0
estimated_sessions: 1
depends_on: []
blocks: []
status: pending
finding_id: F-C-26
severity: HIGH
spec: specs/nexus-ml-integration.md
domain: nexus-ml
specialist: nexus-specialist
wave: W3
---

## Why

W5-C finding F-C-26: spec describes `nexus.register_service()` + `InferenceServer.as_nexus_service()` but code uses `mount_ml_endpoints()` instead. Three cited paths, one shipped path. Reconcile the public API.

## What changes

- Audit shipped surface: the canonical path is `mount_ml_endpoints()` per current code.
- Update `specs/nexus-ml-integration.md` to canonicalize on `mount_ml_endpoints()`.
- Remove or alias the spec-cited `register_service` / `as_nexus_service` names.
- Add Tier-2 test exercising the canonical mount path end-to-end.

## Capacity check

- LOC: ~150 (spec edit + Tier-2 test)
- Invariants: 3 (single canonical path, spec accuracy, integration test green)
- Call-graph hops: 2
- Describable: "Pick `mount_ml_endpoints()` as canonical; update spec; add wiring test."

## Spec reference

- `specs/nexus-ml-integration.md`

## Acceptance

- [ ] Spec describes ONE canonical mount path
- [ ] Tier-2 test exercises the shipped path via real Nexus instance
- [ ] No production code references the absent names
- [ ] Sibling re-derivation per `rules/specs-authority.md` § 5b
- [ ] CHANGELOG entry

## Dependencies

- None

## Related

- Finding detail: `04-validate/W5-C-findings.md` F-C-26
