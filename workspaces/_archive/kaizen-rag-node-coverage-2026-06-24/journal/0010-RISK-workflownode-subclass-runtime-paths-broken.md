---
type: RISK
date: 2026-05-19
created_at: 2026-05-19T00:00:00Z
author: agent
session_id: f8-b3-implement
session_turn: 1
project: kaizen-rag-node-coverage
topic: WorkflowNode-subclass rag nodes have broken codegen/runtime paths — pattern across B1/B2/B3
phase: implement
tags: [f8, b1, b2, b3, workflownode, codegen, runtime, follow-up, risk]
---

# RISK — `WorkflowNode`-subclass rag nodes have broken codegen / sub-workflow-runtime paths

## Context

`/implement` cycles B1–B3 (similarity, graph, agentic coverage) each surfaced
a defect class that is OUT of the per-shard None-content scope but forms a
coherent pattern: the `WorkflowNode`-subclass rag nodes — whose `run()`
builds and executes a sub-workflow via `_create_workflow()` — have broken
codegen and/or sub-workflow-runtime paths. Their **direct `run()` /
deterministic paths are fully covered and green**; the failure is confined to
the sub-workflow composition path.

## The pattern (3 shards of evidence)

| Shard | Module     | WorkflowNode-runtime finding                                                                                                                                                                                                                                                                                                                              |
| ----- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| B1    | similarity | `_create_workflow()` codegen workflows un-executable end-to-end via `LocalRuntime`: (a) ColBERT `token_embedder` emits numpy arrays → `WorkflowExecutionError: outputs must be JSON-serializable`; (b) sparse/hybrid templates `NameError: defaultdict` — `PythonCodeNode` does not expose the template's module-scope imports to nested function bodies. |
| B2    | graph      | `GraphRAGNode._create_workflow()` builds cleanly; its `LLMAgentNode` sub-steps need an LLM key (absent from `[rag]`) — a documented scope boundary, no defect.                                                                                                                                                                                            |
| B3    | agentic    | `AgenticRAGNode.run()` → `NodeExecutionError: Workflow contains unmarked cycles` (`react_agent`↔`state_manager`↔`tool_executor`) — `add_connection` calls at `agentic.py:516-540` form cycles without `cycle=True`. `ReasoningRAGNode.run()` wires invalid `LLMAgentNode` params (`reasoning_plan` `agentic.py:832`, `reasoning_to_verify` `:837`).       |

Two distinct sub-classes emerge:

1. **Genuine wiring/codegen defects** — B1's numpy-serializability + the
   `PythonCodeNode` nested-scope import gap; B3's unmarked cycles + invalid
   `LLMAgentNode` params. These are real bugs in the 2-month-dead rag code
   (and one possible Core SDK behavior — the `PythonCodeNode` nested-scope
   import question). They are NOT same-bug-class as the None-content defect
   each B-shard fixes in-scope, and fixing them needs sub-workflow-graph
   redesign — a separate shard, not the owning B-shard's budget.
2. **LLM-key scope boundary** — B2's `GraphRAGNode` (and any WorkflowNode
   whose sub-workflow wires `LLMAgentNode`): end-to-end execution needs an
   LLM key absent from `[rag]`. This is the documented boundary the test
   strategy (`02-plans/01-test-strategy.md` §"hardest infra problem")
   already anticipated — covered by Tier-1 graph-shape contract tests +
   the env-gated E2E.

## Why this is logged as RISK not DISCOVERY

The plan's `02-plans/01-test-strategy.md` already flagged the WorkflowNode
sub-workflow path as "the hardest infra-availability problem" and routed
`workflows.py`+`strategies.py` (8 WorkflowNode classes) to shard **B7**,
sequenced last. But B1/B2/B3 show the WorkflowNode-subclass problem is NOT
confined to B7's `workflows.py`/`strategies.py` — it is scattered across
similarity / graph / agentic and every other module with a WorkflowNode
subclass. The RISK: if each B-shard only files a "separate finding" and B7
only covers `workflows.py`/`strategies.py`, the scattered WorkflowNode-runtime
defects (similarity codegen, agentic cycles, …) have **no owning shard** and
fall through.

## Recommended disposition (for user decision)

Consolidate the genuine WorkflowNode-runtime defects into ONE follow-up:
either (a) a dedicated post-B "B-WF" shard covering WorkflowNode-subclass
sub-workflow runtime correctness across all rag modules, OR (b) widen B7's
charter from `workflows.py`/`strategies.py` to all WorkflowNode subclasses.
The per-shard B-coverage (B1–B10) continues to fully cover the direct `run()`
paths — the production path users actually exercise. The LLM-key-boundary
sub-class needs no fix (documented boundary + env-gated E2E per the strategy).

This is surfaced to the user at B3 close for the routing decision; it is NOT
auto-closed and NOT silently deferred.

## For Discussion

1. Counterfactual — if B7 had run FIRST (before B1–B3), would the
   WorkflowNode-runtime breakage have been characterised as a single
   `workflows.py` problem and the scattered similarity/agentic instances
   missed entirely? The value-ordered B1→B10 sequence surfaced the pattern
   precisely because the WorkflowNode subclasses are spread across modules.
2. B1's `PythonCodeNode`-nested-scope-import gap: is it a rag-codegen bug
   (the template should inline its imports inside the function body) or a
   Core SDK `PythonCodeNode` limitation that affects every consumer?
3. `AgenticRAGNode`'s unmarked cycles — the sub-workflow is genuinely cyclic
   (a ReAct agent loop). Does the fix mark `cycle=True`, or is the cyclic
   topology itself wrong for the Kailash runtime's execution model?
