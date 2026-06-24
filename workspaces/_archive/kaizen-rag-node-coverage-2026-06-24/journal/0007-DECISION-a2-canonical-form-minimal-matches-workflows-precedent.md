---
type: DECISION
date: 2026-05-19
created_at: 2026-05-19T00:00:00Z
author: agent
session_id: f8-a2-implement
session_turn: 1
project: kaizen-rag-node-coverage
topic: A2 canonical WorkflowNode super-call form amended to minimal (workflow=, name=) — drop the plan's **<cfg>
phase: implement
tags: [f8, a2, workflownode, constructor, plan-amendment, specs-authority-5c]
---

# DECISION — A2 canonical form is minimal `super().__init__(workflow=, name=)`, not the plan's `**<cfg>`

## Context

`/implement` cycle 2, shard A2. The approved plan (`todos/active/00-plan.md`
§A2 STEP-2) specifies the canonical fix form as:

```
super().__init__(workflow=self._create_workflow(), name=name, **<cfg>)
```

The `**<cfg>` clause was written by analogy to shard A1, where every plain
`Node`-subclass constructor was corrected to pass its declared config keys as
keyword args into the validated `self.config` bag (journal/0003 §Refined
Option A — "fixes the 'config stashed as bare instance attrs' sub-defect").

## What the plan's enumeration missed

The plan's site enumeration used `grep -oE 'super\(\).__init__\([^)]*\)'` — a
**single-line** pattern. `packages/kailash-kaizen/src/kaizen/nodes/rag/workflows.py`
contains 4 `WorkflowNode` subclasses (`SimpleRAGWorkflowNode`,
`AdvancedRAGWorkflowNode`, `AdaptiveRAGWorkflowNode`, `RAGPipelineWorkflowNode`)
whose `super().__init__(` calls span multiple lines — invisible to a single-line
grep. The A1-authored regression smoke test inherited the same blind spot:
`RAG_WORKFLOWNODE_ONLY_MODULES = ["optimized", "workflows"]` asserts `workflows`
is A2-broken.

Reading those 4 constructors directly shows they are **already correct** and
have been since before F8:

```python
# workflows.py — already-canonical WorkflowNode form
super().__init__(
    workflow=workflow_node.workflow,
    name=name,
    description="...",
)
```

`workflows.py` is NOT broken, NOT A2 scope. The 13 genuinely-broken
name+workflow sites are confined to 9 modules (realtime, agentic×2, evaluation,
graph, multimodal, federated, conversational, optimized×4, privacy) — exactly
as the plan's prose count states; only the `**<cfg>` form clause and the smoke
test's `workflows` membership are inaccurate.

## Decision

A2's canonical fix form is the **minimal** keyword form:

```
super().__init__(workflow=self._create_workflow(), name=name)
```

with each node's existing bare-attr config assignments (`self.update_interval =
...`, etc.) kept **before** the `super()` call (they already are — and
`_create_workflow()` reads them, so they MUST stay before).

Rationale — the `**<cfg>` clause is dropped:

1. **In-package precedent.** The 4 already-correct `workflows.py` WorkflowNode
   subclasses pass only `workflow` + `name` (+ a hand-written `description`),
   NOT their config keys. They store config as bare attrs (`self.rag_config`,
   `self.llm_model`). For the `WorkflowNode` base class, bare-attr config
   storage is the established correct pattern — not the "sub-defect" journal
   0003 identified for plain `Node` subclasses.
2. **No validated config bag.** `WorkflowNode._validate_config()` is overridden
   to a no-op (`src/kailash/nodes/logic/workflow.py:130`). Passing `**<cfg>`
   would land the keys in an unvalidated `self.config` — cosmetic, with zero
   functional benefit, and inconsistent with the 4 workflows.py nodes.
3. **A1's `**<cfg>`rationale does not transfer.** A1 nodes subclass`Node`,
whose `self.config`IS validated against`get_parameters()`. A2 nodes
subclass `WorkflowNode`, a different base class with different semantics.

This is a launch-time todo amendment per `specs-authority.md` MUST Rule 5c
(orchestrator amends todo text when repo state contradicts the todo) — the
"state" here being the already-correct `workflows.py` precedent the plan's
enumeration could not see.

## Consequences

- The 13 A2 edits are pure call-form corrections; no `get_parameters()` change,
  no config-bag change. Strictly narrower than the plan implied — lower risk.
- The A1-authored smoke test's `RAG_WORKFLOWNODE_ONLY_MODULES` list and its
  "still broken (A2 scope)" comment are corrected in the same shard.
- A2 done-criterion is unchanged: "every name+workflow site constructs past
  `super()`". Deeper R3/CLASS4 failures remain A3-owned.

## For Discussion

1. Counterfactual — if A2 had shipped the plan's literal `**<cfg>` form, the 13
   `optimized`/`agentic`/etc. WorkflowNode nodes would carry config in
   `self.config` while the 4 `workflows.py` nodes would not. Would that split
   have surfaced as a bug in any B-shard behavioral test, or stayed a silent
   inconsistency forever?
2. The plan's single-line `grep -oE` blind spot missed 4 multi-line
   constructors. Should the A3 triage (or a B-shard) re-run the WorkflowNode
   enumeration with an AST pass to confirm no third multi-line super-call form
   exists elsewhere in rag?
3. `workflows.py`'s nodes pass a hand-written `description=`. The 13 A2 nodes
   get none. Is a per-node `description` worth adding in the owning B-shards,
   or is it noise outside the behavioral-coverage value-anchor?
