---
type: DECISION
date: 2026-04-02
created_at: 2026-04-02T15:30:00+08:00
author: co-authored
session_turn: 5
project: data-fabric-engine
topic: DataFlow IS the fabric — not extension, not separate package
phase: analyze
tags: [architecture, dataflow, identity, fabric]
---

# Decision: DataFlow IS the Fabric

## Context

Three options were analyzed:

1. Separate `kailash-fabric` package (red team recommended against)
2. DataFlow extension `kailash-dataflow[fabric]` (red team recommended)
3. DataFlow itself evolves into a fabric (user's challenge)

After analyzing DataFlow's core abstractions, the user's challenge revealed that DataFlow's architecture is already source-agnostic. The only database-specific parts are the constructor, auto-migration, and SQL node generation. Everything else (BaseAdapter, Express API, cache invalidation) works for any source type.

## Decision

DataFlow's mission evolves from "zero-config database operations" to "zero-config data operations." No separate package. No extension. DataFlow IS the fabric.

- `@db.model` registers a database table (existing, unchanged)
- `@db.source()` registers any external source (new)
- `@db.product()` defines materialized views over sources (new)
- Express API works for all sources
- Cache becomes pipeline-driven, not TTL-driven

## Supersedes

This supersedes `0001-DECISION-dataflow-extension-not-separate-package.md`. That decision recommended extension; this goes further — DataFlow's identity evolves.

## Rationale

1. DataFlow's `BaseAdapter` is already source-agnostic — no SQL, just `connect()/disconnect()/supports_feature()`
2. Express API dispatches on string model names and dicts — works for any source
3. Cache invalidation is semantic (model + operation → keys) — no database coupling
4. One engine, one API, one cache layer — no wrapping, no coupling
5. Users already know DataFlow — extending it is zero cognitive overhead
6. 100% backward compatible — all existing `@db.model` code unchanged

## Consequences

- DataFlow pyproject.toml gains optional extras for source-specific deps (httpx, boto3, watchdog, openpyxl)
- New adapter subclasses added alongside existing ones
- `fabric/` subdirectory added to DataFlow for product/pipeline/serving
- Documentation evolves from "database framework" to "data framework"
- README.md and Sphinx docs must reflect the new identity

## For Discussion

1. Does "DataFlow" as a name still work? "Data Flow" implies movement of data, which aligns with fabric (data flowing from sources through pipeline into cache). The name is accidentally perfect.
2. At 139K LOC + 5-7K new LOC, DataFlow becomes ~145K LOC. Is there a size threshold where extraction makes sense? What would trigger it?
3. The `db = DataFlow(...)` variable name `db` is database-flavored. Should documentation use `df` or `data` instead? Or is `db` fine since databases remain the primary use case?
