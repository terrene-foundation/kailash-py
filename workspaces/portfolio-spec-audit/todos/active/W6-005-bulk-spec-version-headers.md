---
id: W6-005
title: Bulk update stale spec version headers (dataflow + kaizen + ml + align)
priority: P2
estimated_sessions: 1
depends_on: []
blocks: []
status: pending
finding_id: LOW-bulk (multiple)
severity: LOW (volume)
spec: specs/* (bulk)
domain: docs
specialist: general-purpose
wave: W2
---

## Why

W5 audit surfaced spec `**Version:**` headers claiming an older release than `__version__` actually shipped, across most dataflow + kaizen + ml + align specs. Single bulk doc-cleanup PR addresses ~30 LOW findings.

## What changes

- For each spec file, read the matching package's `__version__` from `pyproject.toml` / `__init__.py`.
- Update the spec's `**Version:**` header to match.
- One commit, one PR, no implementation impact.

## Capacity check

- LOC: ~30 single-line edits across ~30 spec files
- Invariants: 1 (header matches `__version__`)
- Call-graph hops: 0
- Describable: "Run `wc -l` worth of `sed` on spec headers."

## Spec reference

- All ml-*.md, dataflow-*.md, kaizen-*.md, alignment-*.md files

## Acceptance

- [ ] Every affected spec's `**Version:**` line matches the corresponding package `__version__`
- [ ] Diff is mechanical (no prose changes)
- [ ] Single commit, single PR

## Dependencies

- None

## Related

- Finding pattern: `04-validate/00-portfolio-summary.md` § "Notable LOW patterns"
