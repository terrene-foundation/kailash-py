# DISCOVERY — StreamingRAGNode is dead code; AggregateNode is the real 3rd collision

Date: 2026-05-19
Phase: /implement (baseline + collision census)

## What the runtime census found

A definitive runtime census (monkeypatch `NodeRegistry.register`, force-import
every node module across all 3 packages) found exactly **three LIVE
cross-module collisions**:

| Registry name      | Module A                              | Module B                             |
| ------------------ | ------------------------------------- | ------------------------------------ |
| `HybridSearchNode` | `dataflow.nodes.vector_nodes`         | `kaizen.nodes.ai.hybrid_search`      |
| `BulkUpsertNode`   | `dataflow.nodes.bulk_upsert`          | `kailash.nodes.data.bulk_operations` |
| `AggregateNode`    | `dataflow.nodes.aggregate_operations` | `dataflow.nodes.mongodb_nodes`       |

`StreamingRAGNode` did **NOT** appear — and the reason changes the plan.

## StreamingRAGNode: not a collision — dead code

`kaizen/nodes/rag/realtime.py` and `kaizen/nodes/rag/optimized.py` are
**un-importable**. Their imports target a `kaizen.nodes.{code,data,logic}` +
`kaizen.runtime.async_local` module tree that **does not exist** in the kaizen
package — those paths exist only in the core `kailash.*` SDK:

- `from ..base import Node` — `kaizen.nodes.base` never re-exports `Node`
- `from ..code.python import PythonCodeNode` — no `kaizen.nodes.code`
- `from ..data.streaming import EventStreamNode` — no `kaizen.nodes.data`
- `from ..logic.workflow import WorkflowNode` — no `kaizen.nodes.logic`
- `from ...runtime.async_local import AsyncLocalRuntime` — no `kaizen.runtime.async_local`

`git blame` dates the broken import to `b553104c` (2026-03-11 monorepo refactor)
— the SAME commit that originated the HybridSearchNode collision. The refactor
moved `rag/` into kaizen but never repointed its imports from `kailash.*` to the
new layout. The whole `kaizen.nodes.rag` package has been dead since.

Consequence: neither `StreamingRAGNode` class can import → neither registers →
there is **no live `StreamingRAGNode` registry collision**. The /analyze-phase
belief that it was a live collision was wrong — the `rag/__init__.py`
`as RealtimeStreamingRAGNode` alias masked it (the package looked intentional).

`kaizen.nodes.rag` is isolated dead code — NOT imported by `kaizen/__init__.py`
or `kaizen/nodes/__init__.py`.

## AggregateNode: the real third collision

Two `AggregateNode` classes, both in dataflow, different modules:

- `aggregate_operations.AggregateNode(Node)` — registered via explicit
  `NodeRegistry.register(AggregateNode, alias="AggregateNode")` (`:416`).
- `mongodb_nodes.AggregateNode(AsyncNode)` — MongoDB aggregation pipeline,
  registered via bare `@register_node()` (`:473`).

`dataflow/nodes/__init__.py:4-5` already disambiguates the Python symbol
(`from .mongodb_nodes import AggregateNode as MongoAggregateNode`) and `__all__`
has both names — identical pattern to StreamingRAGNode's `as`-alias, registry
collision left unfixed. The convention owner is clear: `aggregate_operations`
keeps `AggregateNode`; `mongodb_nodes` renames to `MongoAggregateNode`.

My /analyze scan missed it because `aggregate_operations` registers via an
explicit `NodeRegistry.register(...)` call, not a decorator — the decorator-only
grep didn't see it.

## Impact on the plan

- **T3 (StreamingRAGNode rename) is moot** — renaming un-importable dead code.
- **AggregateNode is new, in-scope** — live collision, same bug class; the core
  guard (T4) would crash import on it if unfixed.
- The dead `kaizen.nodes.rag` package is a separate pre-existing bug (broken
  monorepo-refactor imports), open-ended (never-exercised code, unknown further
  breakage) → exceeds this 1-shard budget → separate tracked issue per
  `autonomous-execution.md` MUST Rule 4 budget-exceeded carve-out.

→ Surfaced to user for re-gate (the /todos Scope-B gate named StreamingRAGNode,
not AggregateNode).
