# RAG Per-Node Ship/Fix/Quarantine Ledger — 2026-06-08

Read-only Round-2 deep-dive of the `/redteam` provably-correct audit. Per-node
classification of all 55 `kaizen.nodes.rag` Node subclasses by run-path reality.
Mechanical scan (sim/keyword/real-work/advertised-guarantee markers across the whole
class body) + hand-verified overrides on the 8 SHIP-bucket nodes with sim>=3 (comment
text inspected to separate core-capability simulation from peripheral simplification).

**Tiers:** `SHIP` real · `SHIP-caveat` real core, simplified peripheral (document it) ·
`FIX` advertises a capability it simulates (zero-tolerance Rule 2) · `QUARANTINE`
actively misleading / fundamentally simulated (fabricated output presented as real).

**Totals:** SHIP=30 · SHIP-caveat=4 · FIX=13 · QUARANTINE=8 (55 total)

| tier | node | file | sim | kw | real | adv |
| ---- | ---- | ---- | --- | -- | ---- | --- |
| QUARANTINE | ToolAugmentedRAGNode | agentic.py | 4 | 6 | 0 | 0 |
| QUARANTINE | ReasoningRAGNode | agentic.py | 3 | 0 | 0 | 0 |
| QUARANTINE | RAGBenchmarkNode | evaluation.py | 9 | 0 | 2 | 0 |
| QUARANTINE | RAGEvaluationNode | evaluation.py | 7 | 0 | 1 | 0 |
| QUARANTINE | GraphBuilderNode | graph.py | 3 | 0 | 0 | 0 |
| QUARANTINE | VisualQuestionAnsweringNode | multimodal.py | 4 | 0 | 0 | 3 |
| QUARANTINE | QueryRewritingNode | query_processing.py | 5 | 0 | 2 | 0 |
| QUARANTINE | RealtimeRAGNode | realtime.py | 5 | 0 | 2 | 0 |
| FIX | TestDatasetGeneratorNode | evaluation.py | 1 | 0 | 0 | 0 |
| FIX | FederatedRAGNode | federated.py | 7 | 0 | 11 | 0 |
| FIX | GraphQueryNode | graph.py | 1 | 0 | 0 | 0 |
| FIX | MultimodalRAGNode | multimodal.py | 6 | 1 | 21 | 6 |
| FIX | ImageTextMatchingNode | multimodal.py | 2 | 2 | 1 | 3 |
| FIX | SecureMultiPartyRAGNode | privacy.py | 12 | 0 | 6 | 13 |
| FIX | PrivacyPreservingRAGNode | privacy.py | 2 | 0 | 19 | 26 |
| FIX | AdaptiveQueryProcessorNode | query_processing.py | 1 | 5 | 1 | 0 |
| FIX | QueryIntentClassifierNode | query_processing.py | 1 | 22 | 1 | 0 |
| FIX | QueryDecompositionNode | query_processing.py | 0 | 3 | 4 | 0 |
| FIX | RAGStrategyRouterNode | router.py | 0 | 4 | 3 | 0 |
| FIX | ColBERTRetrievalNode | similarity.py | 6 | 0 | 50 | 0 |
| FIX | CrossEncoderRerankNode | similarity.py | 2 | 0 | 2 | 0 |
| SHIP-caveat | ConversationalRAGNode | conversational.py | 3 | 1 | 5 | 0 |
| SHIP-caveat | CrossSiloRAGNode | federated.py | 5 | 0 | 5 | 0 |
| SHIP-caveat | CacheOptimizedRAGNode | optimized.py | 5 | 0 | 11 | 0 |
| SHIP-caveat | BatchOptimizedRAGNode | optimized.py | 3 | 0 | 9 | 0 |
| SHIP | HyDENode | advanced.py | 2 | 0 | 4 | 0 |
| SHIP | RAGFusionNode | advanced.py | 0 | 0 | 4 | 0 |
| SHIP | SelfCorrectingRAGNode | advanced.py | 0 | 2 | 0 | 0 |
| SHIP | StepBackRAGNode | advanced.py | 0 | 0 | 1 | 0 |
| SHIP | AgenticRAGNode | agentic.py | 3 | 0 | 12 | 0 |
| SHIP | ConversationMemoryNode | conversational.py | 3 | 0 | 7 | 0 |
| SHIP | EdgeRAGNode | federated.py | 2 | 0 | 4 | 0 |
| SHIP | GraphRAGNode | graph.py | 0 | 0 | 2 | 0 |
| SHIP | AsyncParallelRAGNode | optimized.py | 0 | 0 | 2 | 0 |
| SHIP | StreamingRAGNode | optimized.py | 0 | 0 | 2 | 0 |
| SHIP | ComplianceRAGNode | privacy.py | 0 | 0 | 2 | 0 |
| SHIP | MultiHopQueryPlannerNode | query_processing.py | 0 | 2 | 1 | 0 |
| SHIP | QueryExpansionNode | query_processing.py | 0 | 0 | 1 | 0 |
| SHIP | RealtimeStreamingRAGNode | realtime.py | 1 | 0 | 4 | 0 |
| SHIP | IncrementalIndexNode | realtime.py | 0 | 0 | 3 | 0 |
| SHIP | RAGPerformanceMonitorNode | router.py | 0 | 0 | 1 | 0 |
| SHIP | RAGQualityAnalyzerNode | router.py | 0 | 0 | 2 | 0 |
| SHIP | DenseRetrievalNode | similarity.py | 2 | 0 | 39 | 0 |
| SHIP | PropositionBasedRetrievalNode | similarity.py | 2 | 0 | 7 | 0 |
| SHIP | SparseRetrievalNode | similarity.py | 1 | 0 | 41 | 0 |
| SHIP | HybridFusionNode | similarity.py | 0 | 0 | 13 | 0 |
| SHIP | MultiVectorRetrievalNode | similarity.py | 0 | 0 | 39 | 0 |
| SHIP | HierarchicalRAGNode | strategies.py | 0 | 0 | 0 | 0 |
| SHIP | HybridRAGNode | strategies.py | 0 | 0 | 0 | 0 |
| SHIP | SemanticRAGNode | strategies.py | 0 | 0 | 1 | 0 |
| SHIP | StatisticalRAGNode | strategies.py | 0 | 0 | 0 | 0 |
| SHIP | AdaptiveRAGWorkflowNode | workflows.py | 0 | 2 | 0 | 0 |
| SHIP | AdvancedRAGWorkflowNode | workflows.py | 0 | 1 | 0 | 0 |
| SHIP | RAGPipelineWorkflowNode | workflows.py | 0 | 0 | 5 | 0 |
| SHIP | SimpleRAGWorkflowNode | workflows.py | 0 | 0 | 0 | 0 |

## Key per-node evidence (verified by direct read)

- **FederatedRAGNode** `federated.py:172,207` — federation network simulated (`simulated response`). FIX.
- **ColBERTRetrievalNode** `similarity.py:701` — `would use actual BERT tokenizer and model`; isn't ColBERT without real BERT. FIX.
- **MultimodalRAGNode / VisualQuestionAnsweringNode / ImageTextMatchingNode** `multimodal.py:220,555` — CLIP/BLIP simulated; VQA fabricates scores. FIX-overclaim / QUARANTINE.
- **PrivacyPreservingRAGNode / SecureMultiPartyRAGNode** `privacy.py:8,45` — docstrings advertise ε-differential-privacy + homomorphic encryption; impl is regex PII redaction. FIX-overclaim.
- **RAGBenchmarkNode / RAGEvaluationNode** `evaluation.py:145,262` — doesn't run the system it benchmarks; relevance judgment simulated → fabricated quality metrics. QUARANTINE (actively misleading).
- **ToolAugmentedRAGNode** `agentic.py:703,721` — keyword tool-routing + template synthesis; `LLMAgentNode` imported but unused.
- **QueryIntentClassifierNode** `query_processing.py` — 22 keyword-routing hits (`in query_lower`); `agent-reasoning.md` MUST-1 surface.

## Disposition note

`SHIP` (34) + `SHIP-caveat` (4) = the genuinely-functional core. The `FIX`/`QUARANTINE`
set is F8 Milestone B's real scope. QUARANTINE-vs-FIX for a given node is a product-scope
call (implement the real backend vs remove the over-claimed surface) — user-gated per
`value-prioritization.md` MUST-4. Receipt: this file + `06-provably-correct-redteam-2026-06-08.md`.
