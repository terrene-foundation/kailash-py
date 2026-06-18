# DISCOVERY — `kaizen.nodes.rag` is a false floor: 0/55 node classes instantiable

Date: 2026-05-19
Phase: 01 /analyze (F8 — kaizen-rag-node-coverage)
Severity: CRITICAL (dominant finding — reframes the workstream)

## What was found

Empirical instantiation test against `.venv` (kaizen editable + kailash 2.23.0,
the resurrection target version):

- All 7 `kaizen.nodes.rag.similarity` `Node`-subclasses raise
  `TypeError: Node.__init__() takes 1 positional argument but 2 were given`
  on EVERY construction form (`name=` kw, positional, no-arg).
- MRO is `[<Node>, Node, ABC, object]` — rag nodes subclass
  `kailash.nodes.base.Node` directly. NO intermediate compat shim
  (the analyst's "a shim may exist" caveat is resolved: it does not).

Generalization: the failing pattern is `super().__init__(name)` (positional)
against `kailash.nodes.base.Node.__init__(self, **kwargs)` (keyword-only,
`src/kailash/nodes/base.py:339`). That call site exists at all 55
`@register_node` rag classes (e.g. `similarity.py:81/218/500/758/1061/1302/1588`).
→ **0 of the 55 `Node`-subclass rag node classes can be instantiated.**

## Root cause (settled, not regression)

`grep super().__init__(name)` returns **0 hits outside `/rag/`** in
`packages/kailash-kaizen/src/kaizen/nodes/`. Live (non-rag) kaizen nodes use
the current correct constructor contract. The positional pattern is
**rag-local, frozen since the 2026-03-11 monorepo move** — it is stale
2-month-old code, NOT a `kailash.nodes.base.Node` regression affecting all
kaizen. Stale shape (`similarity.py:70-81`): rag node defines
`__init__(self, name=<default>, <node kwargs>)`, stashes node kwargs as bare
instance attrs, then `super().__init__(name)` positionally — bypassing
`Node`'s validated-config kwargs mechanism entirely.

## Why the resurrection's "structural floor" missed this (institutional finding)

`tests/regression/test_rag_resurrection_import_smoke.py` asserts import +
`@register_node` registration. The `@register_node` decorator registers the
class object; it never INSTANTIATES it. Python runs class bodies + decorators
at import — but not `__init__`. So a 100%-non-instantiable package passes the
import-smoke gate cleanly. The resurrection's success criterion ("RAG
capability provably correct, not merely importable") was satisfied in a hollow
way: importable, registrable, and completely non-functional.

→ Follow-on hardening: the import-smoke regression SHOULD instantiate ≥1 node
per module (one line per module) — that single addition would have caught this
at resurrection time. Fold into Shard A.

## Reconciliation of the three parallel analyses

- **analyst** `02-risk-analysis.md` R1 = CORRECT and is THE finding (not one
  risk among several). Root cause now precisely characterized as rag-local
  staleness, not kailash regression.
- **testing-specialist** `02-plans/*` = tiering INVALID where it assumes
  construction succeeds ("31 PURE_COMPUTE testable with `[rag]` alone" → 0
  testable until Shard A lands). The decision-tree (no LLM/vector hard-dep)
  may still hold AFTER the constructor fix — re-derive post-Shard-A.
- **kaizen-specialist** `02-node-contracts.md` "5 broken / 13 HIGH" =
  undercount; static contract read did not instantiate. Effective
  behavioral-breakage surface pre-Shard-A = 55/55.

## Workstream reframing

F8 is NOT "add behavioral coverage to a working-but-untested package." It is:

1. **Shard A (load-bearing, package-wide, prerequisite):** repair the rag
   constructor contract across all 55 `Node` subclasses — `super().__init__`
   to the correct kwargs contract AND reconcile node-specific config with
   `Node`'s validated-config mechanism. BUILD repo → fix directly
   (`zero-tolerance.md` Rule 4). + add per-module instantiation to the
   import-smoke regression.
2. **Then** behavioral coverage per a shard plan re-derived against
   now-instantiable nodes.

The user's value-anchor ("provably correct, not merely importable") is not
weakened by this — it is precisely the gap the anchor targets; the gap is
just deeper than the brief assumed.

## Brief corrections (gate before /todos, per agents.md + specs-authority)

- Count: 58 class defs / 55 `@register_node` / 56 `__all__` (brief said "~53").
- 58/55/56 reconciled: 3 non-decorated = `RAGConfig` (strategies.py:21
  dataclass) + a SECOND distinct `RAGConfig` (advanced.py:29 — same-name
  collision) + `RAGWorkflowRegistry` (registry.py:37). `__all__`=56 because
  `RAGPipelineWorkflowNode` (workflows.py:452) is registered but absent from
  `__init__.__all__` — `orphan-detection.md` Rule 6 finding to fix in-shard.
- "all imports repointed to kailash.\*" incomplete: `graph.py:24`,
  `agentic.py:26` import intra-kaizen `..ai.llm_agent` (not a defect; scope
  correction).
