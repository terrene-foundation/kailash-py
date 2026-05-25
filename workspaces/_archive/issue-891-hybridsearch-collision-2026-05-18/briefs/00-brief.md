# Brief — Issue #891: HybridSearchNode name collision

## Source

GitHub issue #891 (OPEN, created 2026-05-08). Surfaced via smoke-test warning
during kailash 2.17.0 release-prep. Pre-existing since `b553104c` (2026-03-11
monorepo refactor). Picked up F4 — user-gated 2026-05-18 (anchor re-validated:
user selected F4 from the stale-ledger gate).

## The bug (verified live 2026-05-18)

Two distinct classes register the same registry string `"HybridSearchNode"`:

- `packages/kailash-dataflow/src/dataflow/nodes/vector_nodes.py:323`
  `class HybridSearchNode(AsyncNode)` — pgvector hybrid vector+keyword search.
  Requires `dataflow_instance`, `table_name`. Registered via `@register_node()`.
- `packages/kailash-kaizen/src/kaizen/nodes/ai/hybrid_search.py:303`
  `class HybridSearchNode(Node)` — RAG-shape API. Registered via `@register_node()`.

`register_node(alias=None)` defaults the name to `node_class.__name__`, so both
land on `"HybridSearchNode"` in the global `NodeRegistry._nodes` dict. Whichever
imports last silently overwrites the other (`base.py:2373` INFO log). A workflow
that consumes both kailash-dataflow vector search AND kailash-kaizen RAG in one
process gets import-order-dependent dispatch.

## Constraint discovered

`base.py:2373` INFO-not-WARNING is intentional per ADR-002 — DataFlow model
decoration legitimately re-registers nodes. So a blanket "hard-fail on any
duplicate registration" (acceptance option c) would break DataFlow. Any
hard-fail must be narrowed to cross-class / cross-package collisions.

## Resolution shapes (from issue acceptance criteria)

- (a) Rename one or both classes to non-colliding names + `DeprecationWarning`
  shim per `rules/zero-tolerance.md` Rule 6a.
- (b) Namespace registration with package prefix.
- (c) Hard-fail at registration on duplicate name with a typed error.

Decision is a public-API change affecting downstream `add_node("HybridSearchNode")`
callers → requires user gate at /todos.

## Acceptance criteria (issue #891)

- [ ] Decide resolution shape (a/b/c) — user gate.
- [ ] Fix lands in BOTH kailash-dataflow + kailash-kaizen in one release cycle.
- [ ] Tier-2 regression test importing BOTH packages, asserting each shape is
      reachable via a non-colliding identifier.
- [ ] CHANGELOG entries on both packages documenting the migration step.

## Scope estimate

~150–300 LOC, single shard. Invariants: registry uniqueness, deprecation shim
(one minor cycle), both-packages-same-cycle, Tier-2 cross-import test, dual
CHANGELOG. Upper edge of single-shard budget but within it.
