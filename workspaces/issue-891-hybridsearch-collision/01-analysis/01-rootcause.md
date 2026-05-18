# 01 — Root Cause: HybridSearchNode registry collision

## Verified mechanics (2026-05-18)

1. `register_node(alias=None)` (`src/kailash/nodes/base.py:2607`) defaults the
   registry name to `node_class.__name__` when no alias is passed.
2. Both nodes use a bare `@register_node()`:
   - `packages/kailash-dataflow/src/dataflow/nodes/vector_nodes.py:322-323`
     → registers as `"HybridSearchNode"` (pgvector hybrid search, `AsyncNode`).
   - `packages/kailash-kaizen/src/kaizen/nodes/ai/hybrid_search.py:302-303`
     → registers as `"HybridSearchNode"` (RAG semantic search, `Node`).
3. `NodeRegistry.register` (`base.py:2368-2375`) on a name clash does NOT fail —
   it INFO-logs `Overwriting existing node registration for 'HybridSearchNode'`
   (`base.py:2373`) and overwrites. Last import wins.
4. Result: `workflow.add_node("HybridSearchNode", ...)` resolves to whichever
   class was imported last — import-order-dependent, non-deterministic across
   environments and refactors.

## The ADR-002 constraint (critical — rules out naive option c)

`base.py:2371-2373` INFO-not-WARNING is intentional per ADR-002: DataFlow
**legitimately** re-registers nodes. dataflow-specialist confirmed the mechanism:

- `@db.model` (`dataflow/core/engine.py:1813`, decoration at `:1982-1983`) calls
  `_generate_crud_nodes` on every decoration.
- `dataflow/core/nodes.py:488` `_create_node_class` runs a `class DataFlowNode(AsyncNode):`
  statement **inside the method body** (`nodes.py:498`) — a fresh class object
  every call.
- `nodes.py:443,481` re-register each fresh class via `NodeRegistry.register(...)`.

⇒ A blanket "hard-fail on any duplicate name" (acceptance option c) — and even a
narrowed `registry[name] is not node_class` identity check — would raise on
legitimate DataFlow model re-decoration (re-import, test re-run, hot reload),
because re-decoration produces a NEW class object each time.

**Safe narrowing:** hard-fail only when the colliding classes have a DIFFERENT
`__module__` (true cross-package collision). Same-module re-registration keeps
the INFO-log path. This preserves ADR-002 while closing the collision class.

## Severity

MEDIUM — silent, import-order-dependent. No user report yet; live since
`b553104c` (2026-03-11 monorepo refactor). Becomes a real failure the moment one
process consumes both kailash-dataflow vector search and kailash-kaizen RAG.
