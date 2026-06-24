---
type: A3-R1-EMPIRICAL
shard: A3
round: 1
workspace: kaizen-rag-node-coverage
branch: feat/kaizen-rag-A0-r4-enumeration
base_sha: ca552101d
worktree_head_sha: a63d5b98a
main_head_sha_at_probe: 06315fd51
produced_by: A3 Round 1 — empirical construction probe
date: 2026-05-26
---

# A3 — Round 1 — Empirical RAG-Class Construction Probe

## Mission

Round 1 of the A3 disposition protocol verifies the brief's literal empirical claim — "0 of 55 registered rag node classes can be constructed" (`workspaces/kaizen-rag-resurrection/briefs/00-brief.md:53-54`, value-anchor section) — against the actual current state of `kaizen.nodes.rag` at the worktree's base SHA `ca552101d`.

## Method

1. Discovered every class in `kaizen.nodes.rag.*` via `inspect.getmembers` walk over each of the 17 declared rag modules.
2. Deduped by fully-qualified `module.qualname`.
3. Attempted minimal construction: `cls()` first (no args); on `TypeError`, fell back to `cls(id=f"test_{name}")`.
4. Grouped failures by `type(e).__name__` and recorded first ~5 distinct first-line messages per class.

## Provenance — Source Tree Verification

The probe ran under `/Users/esperie/repos/loom/kailash-py/.venv/bin/python`, which has an editable `kailash-kaizen` install pointing at `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/`. Two `git diff`s verified the probed source IS the worktree's base state:

- Worktree `feat/kaizen-rag-A0-r4-enumeration` (HEAD `a63d5b98a`) vs base `ca552101d` in `packages/kailash-kaizen/src/kaizen/nodes/rag/`: **empty diff** (A0 R4 added only workspace markdown).
- Main checkout `06315fd51` vs base `ca552101d` in same path: **empty diff** (no upstream rag-source merges between base and current main).

Therefore the venv-resolved source tree IS the source tree at `ca552101d` for the purposes of `kaizen.nodes.rag` import + construction. The probe's verdict applies to the worktree's effective state.

## Verbatim Probe Output (Summary)

```
=== IMPORT PHASE ===
modules tried: 17, import failures: 0

=== CONSTRUCTION PHASE ===
unique rag classes discovered: 58
constructible: 58/58
failure classes: 0
```

All 58 unique classes constructed cleanly with no exception raised. The probe additionally emitted ~50 advisory WARN lines from `PythonCodeNode` (`'xxx' contains N lines of code, exceeding the recommended maximum of 10 lines`) — these are framework-emitted code-style hints, NOT exceptions or failures; the probe's `try/except` traps did not fire on any class, the WARN lines emit from inside `__init__` AFTER construction succeeds.

## Full OK-List (58 classes)

```
AdaptiveQueryProcessorNode, AdaptiveRAGWorkflowNode, AdvancedRAGWorkflowNode,
AgenticRAGNode, AsyncParallelRAGNode, BatchOptimizedRAGNode,
CacheOptimizedRAGNode, ColBERTRetrievalNode, ComplianceRAGNode,
ConversationMemoryNode, ConversationalRAGNode, CrossEncoderRerankNode,
CrossSiloRAGNode, DenseRetrievalNode, EdgeRAGNode, FederatedRAGNode,
GraphBuilderNode, GraphQueryNode, GraphRAGNode, HierarchicalRAGNode,
HyDENode, HybridFusionNode, HybridRAGNode, ImageTextMatchingNode,
IncrementalIndexNode, MultiHopQueryPlannerNode, MultiVectorRetrievalNode,
MultimodalRAGNode, PrivacyPreservingRAGNode, PropositionBasedRetrievalNode,
QueryDecompositionNode, QueryExpansionNode, QueryIntentClassifierNode,
QueryRewritingNode, RAGBenchmarkNode, RAGConfig, RAGEvaluationNode,
RAGFusionNode, RAGPerformanceMonitorNode, RAGPipelineWorkflowNode,
RAGQualityAnalyzerNode, RAGStrategyRouterNode, RAGWorkflowRegistry,
RealtimeRAGNode, RealtimeStreamingRAGNode, ReasoningRAGNode,
SecureMultiPartyRAGNode, SelfCorrectingRAGNode, SemanticRAGNode,
SimpleRAGWorkflowNode, SparseRetrievalNode, StatisticalRAGNode,
StepBackRAGNode, StreamingRAGNode, TestDatasetGeneratorNode,
ToolAugmentedRAGNode, VisualQuestionAnsweringNode, RAGConfig
```

(Two `RAGConfig` entries appear because the dedup key was `module.qualname` and `RAGConfig` is re-exported from two distinct module paths. Both constructed cleanly. Net unique class count remains 58.)

## Brief Claim Reconciliation

| Brief claim (verbatim) | Empirical state at `ca552101d` |
|---|---|
| "0 of 55 registered rag node classes can be constructed" (`briefs/00-brief.md:53-54`) | **58 / 58 classes constructed cleanly. Zero failures.** |
| "the package cannot import until it is resolved [StreamingRAGNode collision]" (`briefs/00-brief.md:30-31`) | `import kaizen.nodes.rag` succeeds. The 2.23.0 cross-module guard does NOT fire — collision was already resolved. |
| "dead-on-arrival since the 2026-03-11 monorepo move ... `..X` relative imports point at a non-existent `kaizen.nodes.{base,code,data,logic}`" (`briefs/00-brief.md:5-10`) | All 17 modules import; relative-import repair has ALREADY happened upstream of `ca552101d`. |
| "RealtimeStreamingRAGNode + StreamingRAGNode (optimized) both register distinctly" (`briefs/00-brief.md:63-65`) | Both classes present in the constructible set; no collision at registration. |

The brief's expected work — import-repair, StreamingRAGNode rename, import-clean gate, smoke-import regression test — appears to have been completed by upstream merges between brief authorship (2026-05-19) and the workspace's pickup time. The brief's empirical claims that supported the "resurrect as separate PR this session" decision no longer describe the codebase.

## Cross-Reference to A0 R4 Verdict

A0's R4 enumeration table (`04-A0-r4-table.md`) reported "0 LEAKs across 51 FormattedValue interpolation sites" via a pure-AST walk. A3 Round 1's empirical probe — runtime construction of every registered RAG class — corroborates from a different angle: even if A0's AST classification missed a real LEAK (a Disposition 2 candidate), that hidden LEAK does NOT prevent `__init__` from succeeding (the f-string code-template is constructed at init but NOT exec'd until `process()` runs). Construction-clean ≠ exec-clean. The Round 1 verdict bears specifically on the brief's "constructible" claim; LEAK-at-exec hazards remain a deeper-layer question.

## Round 1 Verdict

**The brief's literal empirical claim is STALE / FALSE on the current codebase.** The premise of the kaizen-rag-resurrection workstream — that the package is dead-on-arrival and must be resurrected — does not describe the state at `ca552101d`. This shifts the A3 disposition decisively toward **Disposition 3 (brief premise is stale)** as the primary candidate, with one caveat investigated in Round 2.

## Caveat For Round 2

Construction-clean does NOT prove exec-clean. The brief's value-anchor — "the RAG capability the user chose to preserve is provably correct, not merely importable" — explicitly distinguishes import from correctness. A0 R4 already addressed this from the AST angle (zero LEAKs at exec); Round 2 needs to consider whether any RAG class has a documented behavioral failure mode that survives `__init__`-clean. Round 2 will inspect the test surface (regression tests, integration tests) and any prior CI runs on rag/ to confirm or contest the "merely importable" disposition.

## Recommendation Direction (for Round 3)

Pending Round 2 confirmation, the candidate disposition is:
- **Pick: Disposition 3 (brief premise is stale).**
- **Recommended action**: close the kaizen-rag-resurrection workspace with a value-decay rationale (work landed elsewhere via upstream merges, per `value-prioritization.md` MUST-4); preserve the brief's deferred behavioral-coverage value-anchor for a follow-up workstream IF the user re-validates that anchor.
- **Closure requires user gate** per `value-prioritization.md` MUST-4 — auto-closure of value-bearing deferred work is BLOCKED. Round 3 will package the recommendation for human disposition.
