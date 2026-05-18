# 02 — Resolution Options Analysis

Issue #891 acceptance criteria offer three shapes. Analysis below; recommendation
at the end. This is a public-API change → user gate at /todos.

## Option (a) — Rename both classes [RECOMMENDED]

Rename both colliding classes to capability-descriptive names; register each
under an explicit alias matching the class name.

- Kaizen: `HybridSearchNode` → `SemanticHybridSearchNode`
  `@register_node(alias="SemanticHybridSearchNode")`.
  Per kaizen-specialist: **internal-only** symbol (not in `kaizen/__init__.py`,
  only reachable via `kaizen.nodes.ai.hybrid_search`). Rule 6a deprecation shim
  is therefore NOT mandatory. 4 lines, 2 source files, zero tests, zero
  `add_node` literals.
- DataFlow: `HybridSearchNode` → `PgVectorHybridSearchNode`
  `@register_node(alias="PgVectorHybridSearchNode")`.
  Per dataflow-specialist: **public** symbol — exported from
  `dataflow/nodes/__init__.py::__all__:50`. Rename touches ~6 source/doc files +
  2 test files. Public → keep a one-cycle module alias
  `HybridSearchNode = PgVectorHybridSearchNode` (plain assignment, NOT re-decorated
  — a re-decorated alias would re-create the registry collision) so deep importers
  do not hard-break; CHANGELOG migration entry.

Pros: each name maps to exactly one class; names are self-documenting; blast
radius is contained to the two packages; honors Rule 6a where it applies (public
dataflow symbol) and skips ceremony where it doesn't (internal kaizen symbol).
Cons: `add_node("HybridSearchNode", ...)` in old downstream workflow code stops
resolving — surfaces as a loud "node not found" (acceptable: loud > silent-wrong;
CHANGELOG documents the migration). Optional: register an ambiguity sentinel
under `"HybridSearchNode"` that raises a typed error naming both replacements —
gold-plating, listed as a sub-option for the user.

## Option (b) — Namespace registration with package prefix

Register as `dataflow.HybridSearchNode` / `kaizen.HybridSearchNode`.

Rejected. The registry is a flat string→class dict. Prefixing only these two
nodes makes the API inconsistent (every other node bare-named, these two
prefixed). Prefixing ALL nodes is an ecosystem-wide breaking change to every
`add_node(...)` call. Worst blast radius of the three.

## Option (c) — Hard-fail at registration on duplicate name

Rejected AS A STANDALONE FIX for two reasons:

1. A blanket hard-fail breaks DataFlow model re-decoration (see 01-rootcause.md
   — ADR-002). Even a `is not node_class` identity check breaks it, because
   re-decoration produces fresh class objects.
2. Even if narrowed, (c) alone does not FIX the collision — it converts silent
   wrong-dispatch into a loud crash, which BREAKS the legitimate use case
   "consume both vector search and RAG in one process". (c) is hardening, not a
   resolution.

BUT a `__module__`-narrowed (c) is a valuable COMPLEMENT to (a): make
`NodeRegistry.register` raise `NodeConfigurationError` when a name collides with
a class from a DIFFERENT `__module__`, keep INFO-log for same-module
re-registration. This makes the entire collision class structurally impossible
to recur silently — any future cross-package name clash fails loudly at import.

## Recommendation

**Option (a) + narrowed-(c) hardening**:

1. Rename kaizen `HybridSearchNode` → `SemanticHybridSearchNode` (no shim — internal).
2. Rename dataflow `HybridSearchNode` → `PgVectorHybridSearchNode` (one-cycle
   module alias — public; CHANGELOG migration entry).
3. Core SDK: `NodeRegistry.register` raises on cross-`__module__` name collision;
   same-module re-registration keeps the ADR-002 INFO-log path.
4. Tier-2 regression test importing BOTH packages, asserting each shape is
   reachable via its non-colliding identifier and that `"HybridSearchNode"` no
   longer silently overwrites.
5. CHANGELOG entries on kailash-dataflow + kailash-kaizen.

Open sub-decision for the user: register an ambiguity sentinel under the old
`"HybridSearchNode"` string (helpful typed error) vs. leave it unregistered
(plain "node not found"). Recommend leaving unregistered — simpler, and the
narrowed-(c) hardening + CHANGELOG already cover the migration.

## Scope

~150–300 LOC across 3 packages (core SDK + dataflow + kaizen). Invariants:
registry uniqueness, ADR-002 preservation, public-symbol shim (dataflow only),
cross-import Tier-2 test, dual CHANGELOG. 5 invariants, ~3 call-graph hops —
within single-shard budget.
