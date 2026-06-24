# Brief — Audit-Gap Close-Out: `kaizen.nodes.rag` Behavioral Coverage

## Origin

This workspace is the audit-gap close-out for the F8 RAG behavioral-coverage
workstream. The original resurrection brief lives in the archived superseded
workspace at
`workspaces/_archive/kaizen-rag-resurrection-superseded-2026-05-26/kaizen-rag-resurrection/briefs/00-brief.md`.
The decision to resurrect the RAG package (rather than delete it after the
2026-03-11 monorepo move broke its imports) was journaled at
`workspaces/_archive/issue-891-hybridsearch-collision-2026-05-18/journal/0004-DECISION-rag-resurrection-separate-pr.md`.

Multi-session F8 execution between 2026-05-19 and 2026-05-28 landed the bulk
of the behavioral coverage in batches B4–B10. This workspace exists to close
the residual audit-gap items the 2026-05-28 audit
(`workspaces/kaizen-rag-node-coverage/04-validate/05-audit-gap-2026-05-28.md`)
surfaced AFTER that multi-session execution + re-affirmation 2026-05-28.

## Scope

The `kaizen.nodes.rag` package is **16 submodules + `__init__.py`** holding
**55 node-derived classes** (38 inheriting `Node` + 17 inheriting
`WorkflowNode`), counted via `ast.parse()` enumeration at 2026-05-28
against `packages/kailash-kaizen/src/kaizen/nodes/rag/`. The submodule list:
`__init__.py` + advanced, agentic, conversational, evaluation, federated,
graph, multimodal, optimized, privacy, realtime, retrievers, sources,
specialized, strategies, workflows — and the smoke-test scaffolds (e.g.
`_test_subclasses.py`).

The 89% (49/55) BEHAVIORAL_T2_T3 coverage ALREADY shipped via F8 batches
B4–B10 between 2026-05-19 and 2026-05-28. The remaining 6 classes
(11%) are the audit-surfaced gaps this workspace closes:

1. **Wire defect** — `SimpleRAGWorkflowNode` (`packages/kailash-kaizen/src/kaizen/nodes/rag/workflows.py:36`)
   inner graph could not run end-to-end because `chunker.text` was unwired.
   Closed by Shard C of this workspace; the defect-witness test was
   converted to assert the corrected end-to-end behavior.
2. **Edge-case coverage** — remaining gaps per the audit's 5-cluster
   decomposition (typed-error tests, `pytest.raises` patterns, etc.) are
   tracked in `workspaces/kaizen-rag-node-coverage/04-validate/05-audit-gap-2026-05-28.md` §3–§6.

## Out of scope

- **`ImageReaderNode`** — genuinely absent from the codebase
  (zero grep hits across `src/`). Not implemented; no consumer references it.

## Value-anchor (per `rules/value-prioritization.md` MUST-2)

Verbatim from the archived original brief
(`workspaces/_archive/kaizen-rag-resurrection-superseded-2026-05-26/kaizen-rag-resurrection/briefs/00-brief.md`
lines 52–54): **"the RAG capability the user chose to preserve is provably
correct, not merely importable."**

This workspace is the **audit-gap-driven close-out** — NOT a from-scratch
coverage workstream. F8 B4–B10 already delivered 89% behavioral coverage
between 2026-05-19 and 2026-05-28 across multiple sessions. The 2026-05-28
audit cycle re-affirms the value-anchor and surfaces the residual gaps
(notably the `SimpleRAGWorkflowNode` runtime defect, which is exactly the
"importable but broken" failure mode the anchor exists to close).

Re-validation gate before pickup: confirm the user still wants the RAG
toolkit live (not since-superseded) before investing the remaining 11%
behavioral-coverage effort. Re-affirmed 2026-05-28 with this audit cycle.

## Success criteria

- `SimpleRAGWorkflowNode` is runnable end-to-end at the chunker boundary
  (`text` input accepted by the workflow facade and routed to the inner
  `semantic_chunker`). The defect-witness test asserts the corrected
  behavior, not the broken behavior.
- The remaining audit-surfaced edge-case gaps (typed errors, raise paths)
  per the 2026-05-28 audit report cluster into ≤3 follow-up shards.
- `kailash-kaizen` 2.24.2 released with the wire fix + CHANGELOG entry.
