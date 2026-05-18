# Spec — Node Registry Naming & Cross-Package Collision

Domain: Core SDK `NodeRegistry` (`src/kailash/nodes/base.py`).

## Contract

1. Every registry string name maps to exactly ONE node class across the entire
   kailash ecosystem. (Currently violated by `"HybridSearchNode"`.)
2. Same-module re-registration of a node name is LEGITIMATE and MUST remain
   non-fatal (INFO-log). Rationale: DataFlow `@db.model` decoration regenerates
   CRUD/bulk node classes on every decoration — fresh class objects, same
   `__module__`. This is ADR-002.
3. Cross-`__module__` re-registration of the same name is a COLLISION and MUST
   fail loudly at registration time with `NodeConfigurationError`, naming both
   the incumbent and the colliding class + their modules.

## Behavior change

`NodeRegistry.register(node_class, alias=None)` — when `node_name` already in
`cls._nodes`:

- if `cls._nodes[node_name].__module__ == node_class.__module__`
  → INFO-log "Overwriting…" + overwrite (unchanged, ADR-002 path).
- else → raise `NodeConfigurationError` with both class+module names.

## The two renames

| Was                                                    | Becomes                    | Registry alias             | Package          | Public?                                                                                                               |
| ------------------------------------------------------ | -------------------------- | -------------------------- | ---------------- | --------------------------------------------------------------------------------------------------------------------- |
| `HybridSearchNode(AsyncNode)` (pgvector hybrid search) | `PgVectorHybridSearchNode` | `PgVectorHybridSearchNode` | kailash-dataflow | public (`dataflow/nodes/__init__.py::__all__`) → one-cycle module alias `HybridSearchNode = PgVectorHybridSearchNode` |
| `HybridSearchNode(Node)` (RAG semantic search)         | `SemanticHybridSearchNode` | `SemanticHybridSearchNode` | kailash-kaizen   | internal (`kaizen.nodes.ai.hybrid_search` only) → no shim required                                                    |

Both classes register via explicit `@register_node(alias="<NewName>")` —
explicit alias makes the registration intentional and grep-auditable, vs the
implicit class-name default that caused the collision.

## Acceptance (issue #891)

- [ ] Each name maps to one class; cross-package collision raises at registration.
- [ ] Fix lands in BOTH kailash-dataflow + kailash-kaizen, one release cycle.
- [ ] Tier-2 regression test imports BOTH packages, asserts each shape is
      reachable via its non-colliding identifier, asserts no silent overwrite.
- [ ] CHANGELOG migration entries on both packages.

## Edge cases

- `add_node("HybridSearchNode", ...)` in legacy downstream code → after the fix
  the string is unregistered → loud "node not found". Acceptable (loud >
  silent-wrong). CHANGELOG documents migration to the explicit names.
- DataFlow module alias is a PLAIN assignment, never `@register_node`-decorated —
  a decorated alias would re-create the registry collision.
- The new cross-module hard-fail must itself not break the existing core test
  suite — verify no in-repo node pair already collides cross-module.
