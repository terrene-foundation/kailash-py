# DISCOVERY — The registry collision is a class of 3, not a single bug

Date: 2026-05-18
Phase: /analyze (issue #891)

## Finding

Issue #891 reports ONE registry-name collision (`HybridSearchNode`). A mechanical
scan of every `@register_node`-decorated class across `src/` + `packages/*/src/`
for duplicate class names surfaced **three genuine cross-module collisions**:

| Registry name      | Class A                                                       | Class B                                       | Span                        |
| ------------------ | ------------------------------------------------------------- | --------------------------------------------- | --------------------------- |
| `HybridSearchNode` | `dataflow.nodes.vector_nodes` (`AsyncNode`)                   | `kaizen.nodes.ai.hybrid_search` (`Node`)      | cross-package               |
| `BulkUpsertNode`   | `kailash.nodes.data.bulk_operations` (`AsyncSQLDatabaseNode`) | `dataflow.nodes.bulk_upsert` (`AsyncNode`)    | cross-package               |
| `StreamingRAGNode` | `kaizen.nodes.rag.realtime` (`Node`)                          | `kaizen.nodes.rag.optimized` (`WorkflowNode`) | intra-package, cross-module |

Two scan hits were false positives — `CSVReaderNode` and `MyNode` second
instances are docstring `>>>` examples inside `src/kailash/nodes/base.py`, not
real registrations.

## Why this matters

1. **Scanner-surface symmetry** (`rules/zero-tolerance.md` Rule 1a): the two
   sibling collisions are the SAME bug class as #891. "Issue #891 only names
   HybridSearchNode" is not grounds to leave the other two live.
2. **The core hard-fail couples them.** The recommended core SDK hardening —
   `NodeRegistry.register` raises on a cross-`__module__` name collision — would
   crash package import on `BulkUpsertNode` and `StreamingRAGNode` the moment it
   lands, UNLESS all three collisions are renamed first. The hardening and the
   three renames are one atomic unit, not separable.

## StreamingRAGNode — a partial prior fix

`kaizen/nodes/rag/__init__.py:177` already aliases the realtime class as
`RealtimeStreamingRAGNode` (`from .realtime import StreamingRAGNode as
RealtimeStreamingRAGNode`) and exports both names in `__all__`. The author fixed
the **Python import-symbol** collision but NOT the **registry** collision — both
classes still `@register_node()` with the bare decorator, so the global
`NodeRegistry` still has one `"StreamingRAGNode"` slot, import-order-dependent.
Confirms the registry is a separate global that the `as`-alias workaround does
not reach. The fix: realtime registers explicitly as `RealtimeStreamingRAGNode`
(matching the existing convention), optimized keeps `StreamingRAGNode`.

## Consequence for scope

The user gated F4 = issue #891 (HybridSearchNode). This discovery expands the
technically-correct scope to all three collisions + core hardening. That is a
scope change beyond the issue title → surfaced for user gate at /todos.
