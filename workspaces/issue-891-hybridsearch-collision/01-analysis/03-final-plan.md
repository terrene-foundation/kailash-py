# 03 — Final Plan (Scope B: all 3 collisions + core guard)

User gate 2026-05-18: Scope B — rename all three colliding pairs + land the
cross-`__module__` registry guard.

## Naming principle

Rename BOTH classes in a collision UNLESS an existing convention already
designates a canonical owner — then keep the owner, rename the other.

| Registry name      | Class                                 | Package      | New class + alias            | Rationale                                                                                            |
| ------------------ | ------------------------------------- | ------------ | ---------------------------- | ---------------------------------------------------------------------------------------------------- |
| `HybridSearchNode` | `vector_nodes.HybridSearchNode`       | dataflow     | `PgVectorHybridSearchNode`   | no canonical owner → rename both                                                                     |
| `HybridSearchNode` | `ai/hybrid_search.HybridSearchNode`   | kaizen       | `SemanticHybridSearchNode`   | no canonical owner → rename both                                                                     |
| `BulkUpsertNode`   | `data/bulk_operations.BulkUpsertNode` | kailash core | `SQLBulkUpsertNode`          | no canonical owner (generic SQL vs pooled) → rename both                                             |
| `BulkUpsertNode`   | `nodes/bulk_upsert.BulkUpsertNode`    | dataflow     | `DataFlowBulkUpsertNode`     | no canonical owner → rename both                                                                     |
| `StreamingRAGNode` | `rag/realtime.StreamingRAGNode`       | kaizen       | `RealtimeStreamingRAGNode`   | convention exists — `rag/__init__.py:177` already aliases realtime as `RealtimeStreamingRAGNode`     |
| `StreamingRAGNode` | `rag/optimized.StreamingRAGNode`      | kaizen       | **keeps** `StreamingRAGNode` | bare `StreamingRAGNode` import + `__all__` entry resolve to optimized — it is the convention's owner |

All registrations become explicit: `@register_node(alias="<NewName>")`.

## Core SDK guard (`src/kailash/nodes/base.py` `NodeRegistry.register`)

On `node_name` already in `cls._nodes`:

- same `__module__` → INFO-log + overwrite (unchanged — ADR-002 / DataFlow model
  re-decoration path).
- different `__module__` → raise `NodeConfigurationError` naming both
  classes + modules.

Atomicity: the guard crashes import on any un-renamed collision, so it lands in
the SAME change as all six renames.

## Rename call-site inventory

### HybridSearchNode — dataflow (`PgVectorHybridSearchNode`)

`vector_nodes.py` (class + decorator + 6 docstring/error strings),
`nodes/__init__.py:25,50` (import + `__all__`), tests
`test_vector_nodes.py` + `test_vector_nodes_integration.py`, docs
(`pgvector-quickstart.md`, `pgvector-implementation-plan.md`,
`database-expansion-strategy.md`), `examples/pgvector_rag_example.py`.
Public → one-cycle module alias `HybridSearchNode = PgVectorHybridSearchNode`
(plain assignment, NOT re-decorated).

### HybridSearchNode — kaizen (`SemanticHybridSearchNode`)

`ai/hybrid_search.py:302,303,765` (decorator, class, internal instantiation),
`ai/__init__.py:19,73` (import + `__all__`). Internal-only → no shim required.

### BulkUpsertNode — kailash core (`SQLBulkUpsertNode`)

`data/bulk_operations.py:704,705` (decorator + class). Not in
`nodes/__init__.py`/`data/__init__.py` exports — registry-string is the public
surface. CHANGELOG on core kailash documents the `add_node` migration.

### BulkUpsertNode — dataflow (`DataFlowBulkUpsertNode`)

`nodes/bulk_upsert.py:44,72,101,646,653,667` (class, decorator, docstrings,
errors, `.execute` monkeypatch), `gateway_integration.py:18,325` (import +
`add_node` literal), `core/workflow_binding.py:60` (`"BulkUpsert"` keyword map),
`nodes/file_source.py:6,75` (docstring refs). NOTE: `f"{model_name}BulkUpsertNode"`
in `engine.py:3040` / `engine_production.py:209` / `protected_engine.py:137` are
GENERATED per-model node names (`UserBulkUpsertNode`) — NOT the static node,
leave untouched.

### StreamingRAGNode — kaizen realtime (`RealtimeStreamingRAGNode`)

`rag/realtime.py:404,417,767` (class, internal instantiation, `__all__`),
`rag/__init__.py:177` (`as RealtimeStreamingRAGNode` alias becomes a direct
import). Optimized side unchanged.

## Deliverables

- Core guard + 6 renames (atomic).
- Tier-2 regression test: import all three package pairs, assert each shape
  reachable via its non-colliding identifier, assert cross-module collision
  raises.
- CHANGELOG entries: kailash core, kailash-dataflow, kailash-kaizen.
- Pre-flight: confirm no OTHER cross-module collision exists in the in-repo
  node set (scan already done — only these 3; `CSVReaderNode`/`MyNode` hits
  were docstring examples, not real registrations).
