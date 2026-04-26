---
id: W6-014
title: LineageGraph — explicit deferral with Wave 6.5b tracking
priority: P0
estimated_sessions: 1
depends_on: []
blocks: []
status: pending
finding_id: F-E1-09
severity: HIGH
spec: specs/ml-tracking.md
domain: ml
specialist: ml-specialist
wave: W5
---

## Why

W5-E1 finding F-E1-09: `LineageGraph` is a placeholder behind `try/except ImportError`; canonical engine module never landed; `km.lineage()` returns hollow data. Full implementation is larger than one shard (graph DDL + traversal + DataFlow integration).

## What changes

**Default disposition**: explicit deferral per `rules/zero-tolerance.md` Rule 1b (4 conditions required).

- Update `specs/ml-tracking.md` § Lineage to mark "Deferred to Wave 6.5b — see issue #NNN"
- Strip the `try/except ImportError` placeholder from `kailash_ml/__init__.py` if `km.lineage` returns empty
- Make `km.lineage()` raise typed `LineageNotImplementedError` instead of returning hollow data (per `rules/zero-tolerance.md` Rule 2 — fake data is BLOCKED)
- File tracking issue with full design sketch
- Link tracking issue from PR body
- COORDINATION NOTE: W6-015 is version owner — no version edits here.

## Capacity check

- LOC: ~80 (spec edit + remove placeholder + typed error)
- Invariants: 4 (Rule 1b conditions all met)
- Call-graph hops: 2
- Describable: "Defer LineageGraph properly: spec + typed error + tracking issue."

## Spec reference

- `specs/ml-tracking.md` § Lineage
- `rules/zero-tolerance.md` Rule 1b (legitimate deferral)

## Acceptance

- [ ] Spec updated with deferral notice
- [ ] `km.lineage()` raises typed `LineageNotImplementedError` (no fake data)
- [ ] Tracking issue filed with design sketch
- [ ] PR body links tracking issue
- [ ] release-specialist confirms deferral disposition
- [ ] No CHANGELOG / `__version__` / `pyproject.toml` edits (W6-015 owns)

## Dependencies

- None (parallel with W6-013, W6-015 in W5 wave)

## Coordination

W5 wave batches three ml todos. Version owner: **W6-015**.

## Related

- Finding detail: `04-validate/W5-E1-findings.md` F-E1-09
