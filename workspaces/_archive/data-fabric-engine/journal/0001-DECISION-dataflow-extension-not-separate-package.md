---
type: DECISION
date: 2026-04-02
created_at: 2026-04-02T14:30:00+08:00
author: co-authored
session_turn: 3
project: data-fabric-engine
topic: Ship fabric as DataFlow extension, not 9th package
phase: analyze
tags: [architecture, packaging, dataflow, platform-coherence]
---

# Decision: Ship Fabric as `kailash-dataflow[fabric]`, Not `kailash-fabric`

## Context

The initial analysis proposed `kailash-fabric` as a separate package (Option B in architecture options). Two independent red team passes converged on recommending a DataFlow extension instead.

## Decision

Ship the data fabric engine as an optional extension of `kailash-dataflow`, installed via `pip install kailash-dataflow[fabric]`.

Code lives in `packages/kailash-dataflow/src/dataflow/fabric/`. Uses only the public API of DataFlow's cache module. If adoption warrants standalone promotion, extract later.

## Alternatives Considered

1. **Separate `kailash-fabric` package** — Clean separation, but creates 9th top-level package (cognitive load, platform dilution, version matrix explosion). Dependency on DataFlow's cache creates coupling anyway.
2. **Inside DataFlow core** — Conceptual mismatch. DataFlow is "database operations." Fabric adds non-database sources. But as an EXTENSION, it expands DataFlow's mission naturally: "zero-config data operations" → "zero-config data operations across ALL sources."
3. **Standalone reimplementation** — Violates framework-first. Would reimplement caching, DB access, endpoint serving.

## Rationale

- Existing DataFlow users discover fabric organically
- No new package to learn, version, or maintain
- Easy to split later (extract is cheap), hard to merge after separation
- Value auditor: "A new user could discover it organically: I use DataFlow for my database, and now I need to add an API source — oh, DataFlow has a fabric extension"

## Consequences

- DataFlow's pyproject.toml gains optional `[fabric]` extra with source-specific deps
- DataFlow's `__init__.py` conditionally imports fabric when installed
- Cache module must publish a stable `CacheProtocol` that fabric depends on
- Fabric must NOT import DataFlow private APIs

## For Discussion

1. Given that DataFlow is already 250 files / 139K LOC, at what point does adding fabric (estimated 23-30 files, 8-11K LOC) make it too large? What is the extraction trigger?
2. If Denodo had started as a database extension and later extracted into a standalone platform, would they have reached the same market position? Does starting small risk staying small?
3. What happens when a DataFlow adapter breaks — does it block fabric releases? How do we manage the shared release cadence?
