# DECISION — Scope B: all 3 collisions + core registry guard

Date: 2026-05-18
Phase: /analyze → /todos gate

## Decision

User-gated 2026-05-18. Of three scope options surfaced, the user selected
**Scope B**: rename all three colliding node pairs AND land the cross-module
registry guard in core SDK.

## Why this was a user gate

Issue #891 names only `HybridSearchNode`. Scope B expands to `BulkUpsertNode` +
`StreamingRAGNode` (sibling collisions surfaced by the scan — journal/0001) and
touches kailash core (not just dataflow+kaizen). That is a scope change beyond
the issue title → user decision, not agent self-authorization.

## Rejected options

- **Scope A (just #891):** cannot land the core guard — it would crash imports
  on the two un-fixed collisions — so the bug class stays structurally open.
- **Scope C (all 3, no guard):** fixes today's collisions but leaves no
  structural defense; a 4th collision could slip in silently on the next
  monorepo refactor.

## Atomicity constraint

The core `__module__` guard and the six renames are ONE atomic change. The guard
raises `NodeConfigurationError` on any cross-module name collision at import
time; shipping it before all six renames land would crash package import. They
land together or not at all.

## Resolution shape (from 01-analysis/02)

Option (a) rename + narrowed option (c) guard. Option (b) package-prefix
namespacing rejected (ecosystem-wide blast radius); plain option (c) hard-fail
rejected (breaks DataFlow model re-decoration per ADR-002).
