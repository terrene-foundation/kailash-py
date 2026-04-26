---
id: W6-003
title: Rename MLTenantRequiredError → TenantRequiredError + back-compat alias
priority: P1
estimated_sessions: 1
depends_on: []
blocks: []
status: pending
finding_id: F-B-23
severity: HIGH
spec: specs/dataflow-ml-integration.md
domain: dataflow-ml
specialist: dataflow-specialist
wave: W1
---

## Why

W5-B finding F-B-23: `dataflow.ml` ships `MLTenantRequiredError` but the spec says `TenantRequiredError`. Spec-following users hit `ImportError`. Rename to match the spec.

## What changes

- Rename `MLTenantRequiredError` → `TenantRequiredError` at definition site.
- Update every internal raise site.
- Add `MLTenantRequiredError = TenantRequiredError` alias at the module level for back-compat (1-release deprecation cycle, NOT shim per `feedback_no_shims`).
- Mark the alias `__deprecated__` and emit `DeprecationWarning` on first use.
- Update spec to clarify the canonical name + alias.

## Capacity check

- LOC: ~80 (rename + alias + 1 spec edit + tests)
- Invariants: 2 (rename does not change behavior; alias warns once)
- Call-graph hops: 2
- Describable: "Rename one error class; add deprecation-warning alias; update spec."

## Spec reference

- `specs/dataflow-ml-integration.md` § Error taxonomy
- `rules/zero-tolerance.md` § "Removed = Deleted, Not Deprecated" — but renames with explicit deprecation cycle are permitted when spec compliance demands it; the alias is a 1-release bridge, not a permanent shim.

## Acceptance

- [ ] Canonical name `TenantRequiredError` in code + spec
- [ ] Alias `MLTenantRequiredError = TenantRequiredError` at module top with `DeprecationWarning`
- [ ] Tier-1 test asserts both import paths resolve to the same class
- [ ] CHANGELOG entry: "Renamed MLTenantRequiredError → TenantRequiredError; alias deprecated, slated for removal in v3.0"

## Dependencies

- None

## Related

- Finding detail: `04-validate/W5-B-findings.md` F-B-23
