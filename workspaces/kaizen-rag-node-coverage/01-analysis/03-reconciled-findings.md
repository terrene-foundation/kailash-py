# 03 — Reconciled Findings (authoritative plan-input)

Supersedes the contradictions among the three parallel analyses
(`01-research/02*-node-contracts.md`, `02-plans/01-02*`, `02-risk-analysis.md`).
Every claim below is empirically verified against `.venv` (kaizen editable +
kailash 2.23.0) on `main` `0f906a1e0`, 2026-05-19. This doc is what `/todos`
shards from.

## The dominant fact

`kaizen.nodes.rag` imports + registers but is **non-functional**: not one of
its node classes can be constructed/run as-is. The resurrection's import-smoke
gate is a FALSE FLOOR (the `@register_node` decorator never instantiates).
Root cause = rag-local code frozen since the 2026-03-11 monorepo move; NOT a
kailash regression (0 `super().__init__(name)` sites outside `/rag/`).

## Verified surface (authoritative counts)

| Bucket                         | Count | Source of truth                                                                                                             |
| ------------------------------ | ----- | --------------------------------------------------------------------------------------------------------------------------- |
| Total `class X` defs           | 58    | `grep -hE '^class '`                                                                                                        |
| `@register_node`               | 55    | grep                                                                                                                        |
| `__init__.__all__`             | 56    | ast                                                                                                                         |
| `Node` subclasses (R1 pattern) | ~38   | base-class introspection + `grep -c super().__init__(name)` = 38                                                            |
| `WorkflowNode` subclasses      | 17    | base-class introspection                                                                                                    |
| Non-node (`object`)            | 3     | `RAGConfig`@advanced.py:29, `RAGConfig`@strategies.py:21 (distinct same-name classes), `RAGWorkflowRegistry`@registry.py:37 |

`__all__`=56 reconciled: 55 registered − `RAGPipelineWorkflowNode`
(workflows.py:452, registered but absent from `__all__` — `orphan-detection.md`
Rule 6 finding) + `RAGConfig` (exported) + `RAGWorkflowRegistry` (exported).

## Three distinct repair classes (the load-bearing decomposition)

### R1 — `Node`-subclass constructor (≈38 classes) — MECHANICAL, BOUNDED

`super().__init__(name)` (positional) vs
`kailash.nodes.base.Node.__init__(self, **kwargs)` (`src/kailash/nodes/base.py:339`).
Empirically: every `similarity.*` node raises
`TypeError: Node.__init__() takes 1 positional argument but 2 were given`
on all construction forms. Fix = route through the kwargs contract AND
reconcile node-specific config (currently stashed as bare instance attrs
pre-`super()`) with `Node`'s validated-config mechanism. One pattern, ~38 sites.

### R2 — `WorkflowNode`-subclass constructor (subset of 17) — MECHANICAL-ish, BOUNDED

e.g. `graph.GraphRAGNode`: `TypeError: WorkflowNode.__init__() takes from 1 to
2 positional arguments but 3 were given` — `super().__init__(name, workflow)`
positional vs `WorkflowNode.__init__(self, workflow=None, **kwargs)`. Same bug
class as R1, different base signature. Per-module convention may vary (analyst
R2: ≥3 conventions across workflows.py/strategies.py/graph.py) — enumerate all
17 before fixing.

### R3 — sub-workflow registry references (subset of 17) — NOT MECHANICAL, UNBOUNDED-UNTIL-INVESTIGATED

e.g. `workflows.AdaptiveRAGWorkflowNode`: constructs past the super() call,
then `WorkflowValidationError: Node 'SemanticChunkerNode' not found in
registry`. Its internal sub-workflow wires node-type strings that are stale
(renamed since March) or genuinely absent (`SemanticChunkerNode`, `CacheNode`
— the resurrection brief noted CacheNode/ImageReaderNode as commented-out
TODOs). Disposition per missing node is a JUDGEMENT call (register/repair the
referenced node vs correct the stale string vs document boundary) — this is
the cost-inflation risk surfaced to and accepted by the user.

## Shipped placeholder (zero-tolerance Rule 2 violation, in the resurrected pkg)

`advanced.py:38-45` `create_hybrid_rag_workflow(config)` — docstring "return a
simple mock workflow", body `return Workflow(name="hybrid_rag_fallback",
nodes=[], connections=[])`. Used by `SelfCorrectingRAGNode` / `RAGFusionNode`
/ `HyDENode` / `StepBackRAGNode`. Must be implemented (not stubbed) in the
advanced shard — BUILD repo, fix directly.

## specs/ disposition (spec-accuracy.md Rule 5 — explicit, so /redteam does not flag absence as a gap)

`specs/` exists at project root with a Kaizen section in `_index.md`; there is
NO `kaizen-rag.md`. Creating one NOW is BLOCKED by `spec-accuracy.md` Rule 5
(spec describes only behavior shipped + working on `main`; RAG behavior
currently raises `TypeError` — an ahead-of-code spec would be a phantom).
**Disposition: `specs/kaizen-rag.md` is authored INCREMENTALLY, code-first —
each fix+coverage shard appends the spec section for the nodes it makes
provably-correct, in the SAME shard.** The node-contract research docs
(`01-research/02*`) serve as the working domain reference until then. This is
the rule-aligned posture, not a skipped MUST.

## Corrected disposition of the three parallel analyses

- `02-risk-analysis.md` (analyst): R1/R2 = CORRECT, now empirically confirmed
  - root-caused + split into R1/R2/R3. Promote to primary.
- `02-plans/01-02` (testing-specialist): infra tiering (no LLM/vector hard-dep)
  may hold but is UNVERIFIABLE until nodes construct — RE-DERIVE post-Shard-A.
  Its 10-shard value-ordering is a useful skeleton for the COVERAGE shards
  (post-fix), not the fix shards.
- `02*-node-contracts.md` (kaizen-specialist): per-class contracts useful;
  "5 broken / 13 HIGH" = undercount (static, no instantiation). Effective
  pre-fix breakage = 100%.

## Sharding implication for /todos

- **Shard A1** = R1 (≈38 Node subclasses) + import-smoke hardening
  (instantiate ≥1 node/module). Bounded, mechanical. Prerequisite for all
  coverage.
- **Shard A2** = R2 (17 WorkflowNode subclasses, enumerate conventions first).
  Bounded. Prerequisite for workflow-node coverage.
- **Shard A3 (investigation)** = R3 triage: enumerate every sub-workflow
  node-type reference, classify stale-string vs genuinely-absent, produce a
  per-reference disposition. Output sizes the remaining coverage shards.
- **Coverage shards B1..Bn** = behavioral coverage, value-ordered per the
  testing-specialist skeleton, RE-DERIVED against now-instantiable nodes,
  each with its own value-anchor + incremental `specs/kaizen-rag.md` section.
