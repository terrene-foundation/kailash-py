---
id: W6-010
title: Nexus package-name canonicalization (kailash_nexus vs nexus)
priority: P0
estimated_sessions: 1
depends_on: []
blocks: []
status: pending
finding_id: F-C-39
severity: HIGH
spec: specs/nexus-core.md
domain: nexus
specialist: nexus-specialist
wave: W4
---

## Why

W5-C finding F-C-39: spec uses `kailash_nexus` but code uses `nexus`. Every cross-package import described by the spec is broken because the names disagree.

## What changes

- Decide canonical name based on PyPI package + actual `pyproject.toml` (likely `kailash_nexus` is correct, `nexus` is the legacy / module-shorthand).
- Sweep `specs/nexus-*.md` to use the canonical name uniformly.
- If code is the source of drift, refactor imports.
- Document the alias if both must coexist for back-compat (alias-only — no behavior duplication).

## Capacity check

- LOC: ~250 (mostly spec sweeps + targeted code rename)
- Invariants: 2 (canonical name, no broken cross-package imports)
- Call-graph hops: 3
- Describable: "Pick canonical nexus package name; sweep all references; verify imports."

## Spec reference

- `specs/nexus-core.md`, `specs/nexus-channels.md`, `specs/nexus-auth.md`, `specs/nexus-services.md`, `specs/nexus-ml-integration.md`

## Acceptance

- [ ] Single canonical name across all 5 nexus specs
- [ ] All cross-package imports resolve in tests
- [ ] `pytest --collect-only` exit 0
- [ ] CHANGELOG entry if any rename
- [ ] Sibling re-derivation per `rules/specs-authority.md` § 5b

## Dependencies

- W6-009 (related nexus-ml work; coordinate)

## Related

- Finding detail: `04-validate/W5-C-findings.md` F-C-39
