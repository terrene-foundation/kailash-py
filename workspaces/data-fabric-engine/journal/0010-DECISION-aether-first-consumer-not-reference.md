---
type: DECISION
date: 2026-04-02
created_at: 2026-04-02T19:00:00+08:00
author: co-authored
session_turn: 13
project: data-fabric-engine
topic: Aether is the first consumer (validates at scale), not the reference implementation
phase: analyze
tags: [aether, reference-implementation, migration, strategy]
---

# Decision: Aether Is the First Consumer, Not the Reference

## Context

Aether (~/repos/dev/aether) has 26 adapters, 52 stores, 264 routes, 31 FE hooks — all of which the fabric replaces or simplifies. The question: should Aether BE the reference implementation, or should there be a separate clean-room reference?

## Decision

**Two-track approach.**

- **Track 1**: Clean-room reference app ships with DataFlow. Minimal (3 sources, SQLite, no external credentials). Demonstrates patterns.
- **Track 2**: Aether migrates to fabric after it ships. Validates at scale (26 sources, real OAuth2, real cloud storage). Produces measurable evidence (12,750 LOC removed, 2,000 added, 6:1 reduction).

## Rationale

A reference should be minimal and self-contained. Aether has 52 stores and 264 routes — it demonstrates complexity, not clarity. But Aether is the proof that the fabric works at real scale. Both are needed.

Measured from Aether: 83% of its 264 REST routes (220) are auto-generatable CRUD. The fabric replaces those entirely. The remaining 44 are custom aggregation handlers that stay as Nexus handlers.

FE migration is minimal — 31 hooks change only their path prefix from `/` to `/fabric/`. Return types stay identical.

## Consequences

- Fabric development does NOT depend on Aether. Fabric releases first.
- Aether migration is a separate workspace/session after fabric ships.
- Reference app is the primary documentation artifact for new users.
- Aether migration benchmarks become the primary evidence for value propositions.

## For Discussion

1. Should the Aether migration be a separate workspace (`workspaces/aether-fabric-migration`) or tracked within the Aether project itself?
2. The 44 custom aggregation routes that stay as Nexus handlers — could any of these become fabric products over time? Or are they fundamentally different (dashboard aggregation = product, but CISO threat matrix = custom logic)?
3. The clean-room reference app uses JSONPlaceholder (free, no auth). Should we also include an authenticated source example using a mock API server in the reference?
