---
type: DISCOVERY
date: 2026-05-19
created_at: 2026-05-19T00:00:00Z
author: agent
session_id: f8-b1-implement
session_turn: 1
project: kaizen-rag-node-coverage
topic: B1 — None-content defect spans run() AND codegen paths; similarity _create_workflow() codegen is un-executable end-to-end
phase: implement
tags: [f8, b1, similarity, defect, zero-tolerance, codegen, follow-up]
---

# DISCOVERY — B1: the None-content defect had two execution paths; the similarity codegen path does not execute

## Context

`/implement` cycle 4, shard B1 — behavioral coverage of the 7 `similarity`
RAG nodes (`similarity.py`). The first F8 Milestone-B coverage shard. PR
#1103.

## Defect found and fixed — `content: None` `AttributeError`

Behavioral testing surfaced a real defect: 6 of the 7 similarity nodes
crashed with `AttributeError` on a document carrying `content: None`.
`doc.get("content", "")` returns the `None` _value_ when the key is present
with value `None` — the `""` default applies only to a _missing_ key. The
subsequent `.lower()` / `.split()` / `[:200]` / `len()` then raised, and the
broad `except` swallowed it into an `error` result key — a silent-fallback
defect, since the nodes advertise graceful malformed-document handling.

**The defect had TWO execution paths**, and the first fix pass missed the
second:

1. **`run()` direct scoring path** — fixed first: `(doc.get("content") or
"")` at every scoring site across the 6 affected nodes.
2. **Codegen path** — the `_create_workflow()` methods build a
   `PythonCodeNode` whose `code=` f-string template contains a SECOND copy
   of the scoring logic (`calculate_bm25_scores`, `calculate_tfidf_scores`,
   `get_token_embeddings`). The gate-review (PR #1103, reviewer HIGH) caught
   that the codegen path still had bare `doc.get("content", "")` — the
   identical bug class. Per `autonomous-execution.md` MUST-4 (same-bug-class
   gap surfaced in review, within shard budget → fix immediately), this was
   fixed in the same PR. The fix-immediately pass found a **5th** site the
   review had not named (`:427` `avg_doc_length`), and two `LOW`-marked echo
   sites (`:968` `content[:200]`, `:1884` `len(None)`) that were NOT benign
   — also fixed. 15 `or ""` sites total; 3 codegen-path regression tests
   added (`test_issue_f8b1_none_content.py`, 10 tests total).

Lesson: a node with a `_create_workflow()` codegen template carries the
SAME logic twice. A defect fix in `run()` MUST grep the `code=` template for
the same pattern — the two paths drift silently otherwise.

## Separate finding — similarity `_create_workflow()` codegen is un-executable

While writing the codegen regression tests, the B1 agent found that the
similarity nodes' `_create_workflow()` workflows **cannot execute
end-to-end through `LocalRuntime` for ANY input** — two distinct
pre-existing defects, NEITHER same-class as the None-content bug:

1. **ColBERT `token_embedder`** emits numpy arrays → `WorkflowExecutionError:
Node outputs must be JSON-serializable`.
2. **sparse / hybrid templates** hit `NameError: defaultdict` — a
   `PythonCodeNode` does not expose the template's module-scope imports to
   nested function bodies inside the `code=` block.

These are out of B1's shard budget (B1 = the 7 nodes' `run()` behavioral
coverage; the `run()` path — which every node actually uses — is fully
covered and green). The codegen regression tests therefore exercise the
template code directly via `exec` in a single namespace (isolating the
None-content contract) rather than through the runtime.

**Disposition:** recommend a follow-up issue / dedicated shard for the
similarity codegen-execution defects. The `run()` path is the production
path for these `Node`-subclasses; `_create_workflow()` is an alternative
composition helper. Surfaced to the user at B1 close.

## Consequences

- B1 ships the 7 similarity nodes provably-correct on the `run()` path: 81
  behavioral tests (55 Tier-1 + 19 Tier-2a real-numpy + 7 None-content
  regression) + 3 codegen-template regression tests.
- `specs/kaizen-rag.md` created (first B-shard) with the
  `## Similarity / dense retrieval` section.
- The codegen-execution finding is recorded here, not silently dropped.

## For Discussion

1. Counterfactual — had B1's reviewer prompt NOT included the explicit
   `grep -n 'doc.get("content"'` self-check, the codegen-path copy of the
   bug would have shipped. Should every defect-fix shard's reviewer prompt
   mandate a "grep the fix pattern across all execution paths including
   codegen templates" sweep?
2. The similarity `_create_workflow()` codegen path is un-executable for
   any input — yet it shipped (2-month-dead `kaizen.nodes.rag`). Is
   `_create_workflow()` reachable in any documented user flow, or is it
   effectively dead code that should be removed rather than repaired?
3. `PythonCodeNode` not exposing template module-scope imports to nested
   function bodies (defect 2) is a Core SDK behavior — does it affect other
   `PythonCodeNode` consumers beyond rag, and is it a documented limitation
   or a bug?
