# 02 — Shard Decomposition: `kaizen.nodes.rag` behavioral coverage (F8)

Phase-01 proposal. `/todos` turns this into the approved plan. Pairs
with `01-test-strategy.md`.

Counts authoritative per `01-analysis/01-research/01-node-surface-
inventory.md` + this session's AST enumeration: **55 registered node
classes** across 16 code modules + 3 undecorated classes (`RAGConfig`
×2 — same name in `advanced.py` and `strategies.py`; `RAGWorkflowRegistry`
in `registry.py`). `__all__`=56 (exports `RAGConfig` once + omits
`RAGPipelineWorkflowNode`, which IS `@register_node`-decorated in
`workflows.py` but absent from `__all__` — a public-surface
inconsistency the workflow shard MUST surface and fix per
`rules/orphan-detection.md` Rule 6, not just cover).

## Shard sizing rationale (per `rules/autonomous-execution.md` § Capacity Budget)

Sizing is by **complexity, not LOC alone**. Behavioral test code for a
deterministic node is closer to boilerplate (one pattern stamped per
node: construct → `run(**inputs)` → assert output shape/values/edge
cases) than to load-bearing logic, so a shard holds 5-7 node classes
within ONE infra class (≤~450 LOC test code, but the load-bearing
_invariant_ count is the real cap: each shard holds ≤8 invariants =
the shared contract shape + edge-case taxonomy + the log/typed-error
contract for ONE infra class). Cross-infra-class mixing is what would
blow the invariant budget, so shards are partitioned by infra class
(the natural axis the inventory doc identified), never by raw count.

Each shard: ≤7 node classes, one infra class, ≤8 invariants, ≤3
call-graph hops (test → node.run → fallback/compute), describable in
≤3 sentences. A live feedback loop (pytest runs every shard) grants the
3-5× multiplier per Capacity Budget Rule 3, but shards are kept at base
size because the value is per-node provable correctness, not throughput.

## Ordering principle (per `rules/value-prioritization.md` MUST-1)

Ordered by **user value = how central the node is to "the RAG
capability the user chose to preserve"** (brief value-anchor), NOT by
fittability. The user named specific capabilities in the resurrection
directive (quoted in brief lines 15-17): _"GraphRAG, AgenticRAG,
FederatedRAG, MultimodalRAG, ColBERT/HyDE"_. Those named capabilities
rank highest — they are the explicit reason resurrection was chosen
over deletion. Generic infrastructure (registry, perf monitor) ranks
last. Shard-fit is identical across all shards (all fit one shard), so
fit is NOT the discriminator — value is.

---

## Proposed shards (10 total, value-ordered)

### Shard 1 — Similarity / retrieval core (7 nodes, `similarity.py`)

**Scope:** `DenseRetrievalNode`, `SparseRetrievalNode`,
`ColBERTRetrievalNode`, `MultiVectorRetrievalNode`,
`CrossEncoderRerankNode`, `HybridFusionNode`,
`PropositionBasedRetrievalNode`. Tier 1 (deterministic numpy/keyword
fallback path) + Tier 2a (real numpy). ~7 invariants (shared
query→results→scores contract + 4 edge cases + score-range invariant +
typed-error). ~430 LOC test.
**Value-anchor:** The user explicitly named _"ColBERT/HyDE"_ as
unreplaced capability in the resurrection directive (brief lines 15-17,
quoting `workspaces/kaizen-rag-resurrection/briefs/00-brief.md`
§ "Out of scope"); ColBERT lives here. Retrieval is the literal core of
"RAG" — if these 7 are not provably correct, the preserved capability
is hollow. Highest user value.

### Shard 2 — Graph RAG (3 nodes, `graph.py`)

**Scope:** `GraphRAGNode`, `GraphBuilderNode`, `GraphQueryNode`. Tier 1

- Tier 2a against real `networkx`. ~6 invariants (graph
  construction, query traversal, density/component metrics, empty-graph
  edge case, LLM-fallback path, malformed-graph typed-error).
  **Value-anchor:** _"GraphRAG"_ is the FIRST capability the user named
  in the resurrection directive (brief line 15). networkx is a real
  declared `[rag]` backend so coverage is fully provable with no infra
  gap.

### Shard 3 — Agentic RAG (3 nodes, `agentic.py`)

**Scope:** `AgenticRAGNode`, `ToolAugmentedRAGNode`, `ReasoningRAGNode`.
Tier 1 (rule-based fallback path, no key) + Tier 2a (loopback
`http.server` for `RESTClientNode` tool path). ~7 invariants
(reasoning-chain output, tool-augmentation path, fallback when no LLM,
empty-tool edge case, REST-tool real-call, typed-error, WARN-log
assertion).
**Value-anchor:** _"AgenticRAG"_ named explicitly by the user (brief
line 15). The agentic reasoning path is the most behaviorally complex
and most likely to harbor a resurrection defect — provable correctness
here is high user value per the brief's "provably correct" anchor.

### Shard 4 — Multimodal RAG (3 nodes, `multimodal.py`)

**Scope:** `MultimodalRAGNode`, `VisualQuestionAnsweringNode`,
`ImageTextMatchingNode`. Tier 1 + Tier 2a with a real Pillow-generated
PNG fixture. ~6 invariants (text+image fusion output, VQA answer shape,
cross-modal score, no-image edge case, fallback path, typed-error).
**Value-anchor:** _"MultimodalRAG"_ named explicitly by the user (brief
line 15). Pillow is a real declared `[rag]` backend — real image bytes,
no mock, fully provable.

### Shard 5 — Federated / distributed RAG (3 nodes, `federated.py`)

**Scope:** `FederatedRAGNode`, `EdgeRAGNode`, `CrossSiloRAGNode`. Tier
1 + Tier 2a (loopback server for any real REST; simulated-aggregation
path is real shipped code). ~6 invariants (aggregation correctness,
edge-optimization path, cross-silo no-data-leak contract, empty-node
edge case, deterministic-aggregation invariant, typed-error).
**Value-anchor:** _"FederatedRAG"_ named explicitly by the user (brief
line 15). The cross-silo "no individual data exposed" property is a
correctness claim the resurrection floor never verified — exactly the
"provably correct, not merely importable" value the user chose.

### Shard 6 — Advanced techniques: HyDE & co (4 nodes, `advanced.py`)

**Scope:** `HyDENode`, `RAGFusionNode`, `SelfCorrectingRAGNode`,
`StepBackRAGNode` (+ the `advanced.py` `RAGConfig` undecorated class —
assert its defaults). Tier 1 (rule-based fallback) + Tier 2b where a
node composes a sub-workflow (real `LocalRuntime`). ~7 invariants.
**Value-anchor:** _"HyDE"_ named explicitly by the user (brief line
15). Self-correction / fusion are the "advanced" capabilities that
differentiate this toolkit from a trivial retriever — their provable
correctness is the substance of what the user preserved.

### Shard 7 — Workflow + strategy composition (8 nodes; `workflows.py` 4 + `strategies.py` 4)

**Scope:** `SimpleRAGWorkflowNode`, `AdvancedRAGWorkflowNode`,
`AdaptiveRAGWorkflowNode`, `RAGPipelineWorkflowNode`,
`SemanticRAGNode`, `StatisticalRAGNode`, `HybridRAGNode`,
`HierarchicalRAGNode`. Tier 2b (real `LocalRuntime`) + the
`RAGPipelineWorkflowNode`-missing-from-`__all__` fix
(`rules/orphan-detection.md` Rule 6) in the same shard. ~8 invariants.
**Sequencing:** runs LAST among value-tier shards — depends on the
contract deep-dive (`02-node-contracts.md`) resolving whether the inner
`LLMAgentNode`/`EmbeddingGeneratorNode` of the sub-workflows degrade
gracefully with no key (the hardest infra-availability problem per
`01-test-strategy.md` §3). Orchestrator MUST amend this shard's todo at
launch per `rules/specs-authority.md` 5c if the deep-dive moved the
contract.
**Value-anchor:** These 8 are the end-to-end pipelines the package
docstring teaches users to call (`__init__.py` Quick Start). "The RAG
capability the user chose to preserve" IS the pipeline a user runs;
proving the documented Quick Start executes is the most direct
expression of the brief's value-anchor — but it is sequenced after the
named-capability shards because those were the user's explicit naming.

### Shard 8 — Query processing (6 nodes, `query_processing.py`)

**Scope:** `QueryExpansionNode`, `QueryDecompositionNode`,
`QueryRewritingNode`, `QueryIntentClassifierNode`,
`MultiHopQueryPlannerNode`, `AdaptiveQueryProcessorNode`. Tier 1
(rule-based fallback) + WARN-log assertions. ~7 invariants.
**Value-anchor:** Query processing is the pre-retrieval half of every
RAG pipeline the user preserved; an un-proven query rewriter silently
degrades every downstream retrieval. Per the brief's "provably correct"
anchor this is real user value, ranked below the explicitly-named
capabilities but above generic infra.

### Shard 9 — Privacy, evaluation, conversational, realtime, optimized (15 nodes; `privacy.py` 3 + `evaluation.py` 3 + `conversational.py` 2 + `realtime.py` 3 + `optimized.py` 4)

**Scope:** the remaining behavioral nodes, grouped because each is a
small same-shape cluster sharing the deterministic/fallback +
real-aiosqlite/Pillow-not-needed pattern; split into 3 sub-shards at
`/todos` if the invariant budget (>8) is exceeded — privacy
(differential-privacy Laplace-noise math + regex PII), evaluation
(BLEU/ROUGE/F1 deterministic + RAGAS-fallback), conversational+realtime
(real `aiosqlite` storage + read-back), optimized (cache/batch/async/
streaming).
**Value-anchor:** Privacy's ε-differential-privacy and PII-redaction
are correctness CLAIMS the resurrection floor never verified — a wrong
noise calibration silently breaks the privacy guarantee the user's
preserved `PrivacyPreservingRAGNode` advertises. "Provably correct, not
merely importable" (brief value-anchor) is most load-bearing exactly
where the node makes a safety claim.

### Shard 10 — Router, registry, perf-monitor + public-surface reconciliation (4 nodes; `router.py` 3 + `registry.py` `RAGWorkflowRegistry`)

**Scope:** `RAGStrategyRouterNode`, `RAGQualityAnalyzerNode`,
`RAGPerformanceMonitorNode`, `RAGWorkflowRegistry` (+ assert the
58/55/56 reconciliation: `RAGConfig` exported once, registry
undecorated-by-design, `RAGPipelineWorkflowNode` `__all__` fix landed
in Shard 7). Tier 1 + the router WARN-log fallback assertion. ~6
invariants.
**Value-anchor:** Lowest user value (generic plumbing the user did not
name), so ranked LAST per value-ordering — BUT still in scope because
the brief's success criterion is _every_ one of the 55 classes has ≥1
behavioral test; the router's no-key fallback is the realistic default
path users hit and proving it closes the "every class" criterion.

---

## Coverage accounting (brief success criterion: every class ≥1 behavioral test)

| Shard | Node count                        | Module(s)                                            | Infra class             | Tier   |
| ----- | --------------------------------- | ---------------------------------------------------- | ----------------------- | ------ |
| 1     | 7                                 | similarity                                           | embedding/numpy         | T1+T2a |
| 2     | 3                                 | graph                                                | graph/networkx          | T1+T2a |
| 3     | 3                                 | agentic                                              | LLM-fallback/network    | T1+T2a |
| 4     | 3                                 | multimodal                                           | multimodal/Pillow       | T1+T2a |
| 5     | 3                                 | federated                                            | network                 | T1+T2a |
| 6     | 4 (+1 RAGConfig)                  | advanced                                             | LLM-fallback/workflow   | T1+T2b |
| 7     | 8                                 | workflows+strategies                                 | workflow-runtime        | T2b+T3 |
| 8     | 6                                 | query_processing                                     | LLM-fallback            | T1     |
| 9     | 15                                | privacy+evaluation+conversational+realtime+optimized | mixed (storage/compute) | T1+T2a |
| 10    | 3 (+RAGWorkflowRegistry)          | router+registry                                      | LLM-fallback            | T1     |
| **Σ** | **55 registered + 3 undecorated** | 16 modules                                           | —                       | —      |

55 registered + `RAGConfig` (covered Shard 6) + `RAGWorkflowRegistry`
(covered Shard 10) = all 58 class defs have a behavioral test.

## Cross-references / amend-at-launch obligations for `/todos`

- Shard 7 launch is GATED on `02-node-contracts.md` (parallel
  kaizen-specialist deep-dive); orchestrator amends per
  `rules/specs-authority.md` 5c.
- Any node found defective during its shard is fixed in-shard +
  `tests/regression/` + kaizen version bump (`rules/zero-tolerance.md`
  Rule 4 + brief success criterion) — NOT deferred.
- Shard 9 MAY split into 3-4 sub-shards at `/todos` if the per-cluster
  invariant count exceeds 8; each sub-shard inherits Shard 9's
  value-anchor (privacy safety-claim anchor is the strongest sub-anchor
  and must lead).
