# 02 — Node Contract Deep-Dive (overview + reconciliation + part A)

Source of truth: `packages/kailash-kaizen/src/kaizen/nodes/rag/*.py` on `main`
(`0f906a1e0`). Read alongside `01-node-surface-inventory.md` (mechanical
baseline) and `briefs/00-brief.md`.

Split into two parts because full per-class detail exceeds ~300 lines:

- **02-node-contracts.md** (this file) — counts, the 58/55/56 reconciliation,
  the systemic findings that apply across many classes, and per-class
  contracts for the first 9 modules (advanced, agentic, conversational,
  evaluation, federated, graph, multimodal, optimized, privacy).
- **02b-node-contracts.md** — per-class contracts for the remaining 8
  modules (query_processing, realtime, registry, router, similarity,
  strategies, workflows) + the full Contract summary table (all 58 rows)
  - the infra-tier histogram + the HIGH-breakage roll-up.

## Counts confirmed

| Metric                     | Value | Method                                  |
| -------------------------- | ----- | --------------------------------------- |
| `class X` definitions      | 58    | per-module `grep -cE '^class '` summed  |
| `@register_node` decorated | 55    | per-module `grep -cE '^@register_node'` |
| `__init__.__all__` exports | 56    | `ast.parse` of `__init__.py::__all__`   |
| Modules (excl. `__init__`) | 17    |                                         |

Per-module class distribution matches `01-node-surface-inventory.md`
exactly (similarity 7, query_processing 6, strategies 5, advanced 5,
workflows 4, optimized 4, router/realtime/privacy/multimodal/graph/
federated/evaluation/agentic 3 each, conversational 2, registry 1).

## The 58 / 55 / 56 reconciliation (explicit)

### 58 classes vs 55 `@register_node` — the 3 non-decorated classes

1. **`RAGConfig`** — `strategies.py:21`. A `@dataclass` config holder
   (chunk_size, embedding_model, retrieval_k, …). Not a node, not
   registered. IS exported in `__all__`.
2. **`RAGConfig`** — `advanced.py:29`. A SECOND, DIFFERENT class with the
   same name: a hand-rolled fallback "to avoid circular import" (its own
   docstring says so). Not a dataclass, not registered, NOT in `__all__`.
   This name collision is itself a finding (see § Systemic finding S3).
3. **`RAGWorkflowRegistry`** — `registry.py:37`. A plain discovery/factory
   class (not a `Node`). Not registered. IS exported in `__all__`.

### 56 `__all__` vs 55 `@register_node` — the delta

`__all__` (56) = the 55 `@register_node` node classes, **minus 1**
not-exported decorated class, **plus 2** non-node exports:

- **Not in `__all__` though `@register_node`:** `RAGPipelineWorkflowNode`
  (`workflows.py:452`). It is decorated and registered, and `registry.py`
  imports it (used as the `"configurable"` workflow), but it is NOT in the
  package's public `__all__`. Net effect: the registry can instantiate it
  but `from kaizen.nodes.rag import RAGPipelineWorkflowNode` is not an
  advertised import (it still resolves because it is module-scope imported
  in `registry.py`, not in `__init__.py`).
- **In `__all__` though NOT `@register_node`:** `RAGConfig`
  (strategies.py dataclass) + `RAGWorkflowRegistry`.

Arithmetic: 55 decorated − 1 (`RAGPipelineWorkflowNode`, decorated but not
exported) + 1 (`RAGConfig` dataclass, exported non-node) + 1
(`RAGWorkflowRegistry`, exported non-node) = **56**. Consistent.

### Hidden non-`__all__` factory helpers (not in any of the 3 counts)

`strategies.py` also defines 4 module-level factory FUNCTIONS
(`create_semantic_rag_workflow`, `create_statistical_rag_workflow`,
`create_hybrid_rag_workflow`, `create_hierarchical_rag_workflow`) that
`registry.py` and `workflows.py` import directly. They are not classes so
they are correctly outside the 58 count, but every strategy node's `run()`
and every workflow node's `__init__` routes through them — they are the
real behavioral surface for ~13 nodes and MUST be exercised by the shard
tests even though they are not in `__all__`.

## How a rag node takes its backend (the central testability question)

Two structural shapes across all 58:

**Shape P — pure `Node` with self-contained `run()`.** The `run()` body is
deterministic Python over `documents`/`query` kwargs (set-overlap scoring,
BM25, RRF, networkx, deque index). NO LLM, NO embedding model, NO vector
store. The docstrings advertise embeddings/CLIP/cross-encoders but the
`run()` implementations are keyword-overlap stand-ins. These are
PURE_COMPUTE and testable with `[rag]` alone (numpy/networkx only). This is
the LARGE majority of the leaf retrieval/query/index/eval/privacy nodes.

**Shape W — `WorkflowNode` subclass.** `__init__` calls
`self._create_workflow()` which builds a `WorkflowBuilder` graph of
string-typed `kailash.nodes.*` node types (`LLMAgentNode`,
`EmbeddingGeneratorNode`, `VectorDatabaseNode`, `HybridRetrieverNode`,
`SemanticChunkerNode`, `PythonCodeNode`, `SwitchNode`, …) and returns
`builder.build()`. Behavioral execution of these requires the kailash
runtime AND, for the `LLMAgentNode`/`EmbeddingGeneratorNode`/
`VectorDatabaseNode` nodes inside the built graph, a live LLM provider /
embedding model / vector index that is ABSENT from the `[rag]` extra.
Construction (`__init__` → `_create_workflow` → `builder.build()`) is
testable with `[rag]` alone and is itself meaningful coverage (it exercises
the whole graph-wiring contract). Full golden-path `run()` is COMPOSITE
(needs LLM + embedding + vector infra).

A third sub-shape: a few Shape-P nodes hard-import a class but only USE the
string form in `add_node` (`query_processing.py:23`, `advanced.py:23`,
`router.py:14`, `graph.py:24`, `agentic.py:26`, `multimodal.py:27`,
`evaluation.py:28`, `conversational.py:29` all do
`from ..ai.llm_agent import LLMAgentNode`). The hard import is the
import-time breakage surface (S1 below); the runtime path never touches the
imported symbol for the pure-`run()` nodes.

Backend injection: NO rag node takes an injected client param. Strategy/
workflow nodes take an optional `config: RAGConfig` (chunk/embedding/k
knobs only). The "backend" is always the kailash node-type STRING resolved
by the runtime registry — so behavioral coverage of Shape-W golden paths
depends entirely on whether those kailash node types are registered and
whether their providers are reachable, NEITHER of which `[rag]` supplies.

## Systemic findings (apply across many classes — read before sharding)

### S1 — HIGH: `from ..ai.llm_agent import LLMAgentNode` is a dead-code-era coupling on 8 modules

`advanced.py:23`, `agentic.py:26`, `conversational.py:29`,
`evaluation.py:28`, `graph.py:24`, `multimodal.py:27`,
`query_processing.py:23`, `router.py:14` each do
`from ..ai.llm_agent import LLMAgentNode` at module scope. For the
pure-`run()` nodes (query_processing, evaluation's helpers, router) the
symbol is imported but NEVER referenced (the workflow path uses the string
`"LLMAgentNode"`). For `advanced.py` / `router.py` it IS referenced
(`LLMAgentNode(name=..., model=..., provider=..., system_prompt=...)`
constructed directly in `_initialize_components` / `run`). Risk: the module
was dead since 2026-03-11; if `kaizen.nodes.ai.llm_agent.LLMAgentNode`
moved/renamed/changed its constructor kwargs in that window, every one of
these 8 modules fails at import OR at first `run()`. The resurrection PR
asserts modules import clean on `main` today (so the import path resolves
NOW), but the DIRECT-CONSTRUCTION sites (`advanced.py:154`,
`advanced.py:585`, `advanced.py:1039`, `advanced.py:1354`,
`router.py:76`) pass `name=`, `model=`, `provider=`, `system_prompt=`
positionally-by-keyword to `LLMAgentNode(...)` — these kwargs are an
unverified API contract that has had ZERO behavioral exercise since March.
The implement-phase test for any node in `advanced.py`/`router.py` MUST
construct the real `LLMAgentNode` and assert the kwargs are still accepted;
if they raise `TypeError`, that is a real defect to fix in-shard
(`zero-tolerance.md` Rule 4), not a test skip.

### S2 — HIGH: `advanced.py` `create_hybrid_rag_workflow` is a broken stub the 4 advanced nodes call at runtime

`advanced.py:39-45`:

```python
def create_hybrid_rag_workflow(config):
    """Simple fallback workflow creator"""
    from ...workflow.graph import Workflow
    return Workflow(name="hybrid_rag_fallback", nodes=[], connections=[])
```

`SelfCorrectingRAGNode._initialize_components` (`:151`),
`RAGFusionNode._initialize_components` (`:594`),
`HyDENode._initialize_components` (`:1048`),
`StepBackRAGNode._initialize_components` (`:1363`) all set
`self.base_rag_workflow = create_hybrid_rag_workflow(rag_config)` then call
`self.base_rag_workflow.run(documents=..., query=..., operation="retrieve")`
(`:209`, `:711`, `:1126`, `:1464`). Two compounding defects:

1. **Import-target existence:** `from ...workflow.graph import Workflow`
   resolves to `kaizen.workflow.graph.Workflow`. This is a different module
   tree than the `kailash.workflow.builder` used everywhere else. After 2
   months dead, `kaizen.workflow.graph.Workflow` may not exist or may not
   accept `nodes=[], connections=[]` kwargs. This import is INSIDE the
   function body, so it does NOT break module import (S1's import-clean
   claim still holds) — it breaks on FIRST `run()` of any advanced node.
2. **Contract mismatch:** even if `Workflow(name=, nodes=[], connections=[])`
   constructs, a bare `Workflow` graph object almost certainly has no
   `.run(documents=, query=, operation=)` method (that signature is the
   RAG-node convention, not the core `Workflow` API). So
   `SelfCorrectingRAGNode.run()` golden path is provably broken at
   `advanced.py:209`.

This is NOT a "needs LLM infra" problem — it is a runtime AttributeError/
ImportError that fires with PURE_COMPUTE inputs. The 4 advanced nodes are
LOW testability-cost but HIGH breakage-risk: a single Tier-2 test calling
`SelfCorrectingRAGNode().run(documents=[{...}], query="x")` will surface it
immediately. Implement phase MUST fix `create_hybrid_rag_workflow` (the
intended target is the real `strategies.create_hybrid_rag_workflow`, which
returns a `WorkflowNode` that DOES have an `.execute()` — note: `.execute`,
not `.run`, so the call sites at `:209`/`:711`/`:1126`/`:1464` also need
auditing) — `zero-tolerance.md` Rule 4, fix the SDK directly, no
workaround.

### S3 — MED: duplicate `RAGConfig` class name across `strategies.py` and `advanced.py`

`strategies.RAGConfig` is a `@dataclass`; `advanced.RAGConfig` is a plain
class with a different field set (no `embedding_provider`,
`vector_db_provider`, `similarity_threshold`). `__init__.py` exports the
strategies one. Any test that constructs an advanced node with a
`config=` dict will silently bind to `advanced.RAGConfig(**config)`
(advanced.py:150 etc.), NOT the exported dataclass — a contract-confusion
bug class. Behavioral tests MUST assert WHICH `RAGConfig` an advanced node
actually instantiates and that the documented config keys take effect.

### S4 — LOW: hardcoded model strings inside workflow configs (`env-models.md` violation, not a breakage)

`workflows.py:219` (`AdaptiveRAGWorkflowNode.__init__` default
`llm_model: str = "gpt-4"`), and `"model": "gpt-4"` / `"gpt-4-vision"`
literals embedded in dozens of `_create_workflow` `add_node` configs
(advanced, agentic, conversational, evaluation, graph, multimodal,
query_processing, router, similarity). These are `env-models.md`
violations (hardcoded model names). They do NOT break import or
PURE_COMPUTE `run()`, but a Shape-W golden-path test that actually drives
the LLM sub-nodes will pin a deprecated model. Note for implement phase:
when behavioral coverage forces a real LLM call, the model MUST come from
`.env` — the test harness, not the node, supplies it; the hardcoded
default is a latent defect to flag (track, fix opportunistically per
shard since it is mechanical).

### S5 — MED: kailash node-type imports beyond `[rag]` create per-module import-breakage surface

Modules import concrete kailash node classes at module scope (used only as
import-time existence assertions; the runtime uses string node-types):
`agentic.py:19,22` `RESTClientNode`, `SQLDatabaseNode`;
`federated.py:24` `RESTClientNode`; `privacy.py:26`
`CredentialManagerNode` (imported, never used);
`realtime.py:24` `EventStreamNode`; `optimized.py:24`
`AsyncLocalRuntime`. Each is a 2-month-stale `kailash.*` symbol assumption.
If any moved, the module fails at import. The resurrection import-smoke
test only proves a REPRESENTATIVE subset registers — it does NOT prove
every one of these 17 modules imports. The implement-phase shard for each
module MUST begin with an explicit `import kaizen.nodes.rag.<module>`
assertion as test #0 (cheap, and converts a silent S5 breakage into a loud
named failure that the shard then fixes).

### S6 — LOW: in-PythonCodeNode runtime deps absent from `[rag]`

`graph.py:178` (inside the `graph_builder` PythonCodeNode string)
`import community` (python-louvain) when `community_algorithm=="louvain"`
(the default). `community` is NOT in `[rag]` (only networkx is). For
GraphRAGNode Shape-W golden path with default louvain, the built graph's
PythonCodeNode will `ImportError` at runtime. Behavioral coverage MUST
either (a) construct GraphRAGNode with `community_algorithm` ≠ "louvain"
(the connected-components branch uses only networkx — testable with
`[rag]`), or (b) the implement phase adds `python-louvain` to `[rag]` and
tests the default. Recommend (a) for the construction/non-louvain contract
test + flag (b) as a coverage-completeness decision for the user.

### S7 — context: commented-out absent nodes (consistent with brief out-of-scope)

`conversational.py:26` `# from ..data.cache import CacheNode  # TODO`,
`optimized.py:21` same, `multimodal.py:22`
`# from ..data.readers import ImageReaderNode  # TODO`. These match the
brief's "Out of scope — CacheNode, ImageReaderNode genuinely absent".
NOTE: `optimized.py:147` (`CacheOptimizedRAGNode._create_workflow`) STILL
references `builder.add_node("CacheNode", ...)` by STRING at two sites
(`cache_checker`, `cache_updater`). So `CacheOptimizedRAGNode`'s Shape-W
golden path is broken-by-design (the `"CacheNode"` string will not resolve
in the registry — CacheNode was never implemented). Construction
(`builder.build()`) MAY still succeed (string node-types are resolved
lazily at execute time, not build time) — that is the contract the
shard test should pin: "constructs, but documented golden path raises a
registry-miss at execute". This is the same class as S2 but the
disposition differs: CacheNode is genuinely-absent-by-brief, so the test
asserts the current (broken-by-missing-dep) behavior rather than the
implement phase building CacheNode (out of scope per brief).

---

## Per-class contracts — Part A (modules 1–9, alphabetical)

Legend for infra-tier: PURE_COMPUTE | EMBEDDING | LLM | VECTOR_STORE |
GRAPH_DB | NETWORK | STORAGE | MULTIMODAL | COMPOSITE(list). "testable
with [rag] alone?" = can a Tier-2 behavioral test of the documented public
contract run using only numpy/Pillow/networkx/requests/aiosqlite. For
Shape-W nodes the answer is split: CONSTRUCTION=yes, FULL-RUN=no.

### advanced.py

| Class                   | reg? | **all**? | Contract (run/process signature; cite)                                                                                                                                                                                                                                                                                                          | Infra                                                        | Backend take                                                                   | Breakage                                                               |
| ----------------------- | ---- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------ | ---------------------------------------------------------------------- |
| `RAGConfig`             | NO   | NO       | Plain config class `__init__(**kwargs)` → chunk_size/chunk_overlap/embedding_model/retrieval_k attrs (`advanced.py:29-36`). Not a node.                                                                                                                                                                                                         | PURE_COMPUTE                                                 | n/a (config)                                                                   | MED — S3 duplicate-name collision with exported `strategies.RAGConfig` |
| `SelfCorrectingRAGNode` | yes  | yes      | `run(**kwargs)` requires `documents:list`,`query:str`,opt `config:dict`; returns dict {final_response, retrieved_documents, scores, quality_assessment, self_correction_metadata, status} (`advanced.py:73-145`). Iterates ≤ max_corrections, calls `self.base_rag_workflow.run(...)` + `LLMAgentNode.execute()` verifier.                      | COMPOSITE(LLM + the broken stub)                             | hard `LLMAgentNode` ctor (`:154`) + `create_hybrid_rag_workflow` stub (`:151`) | **HIGH — S2 broken stub at `:209`; S1 LLMAgentNode ctor at `:154`**    |
| `RAGFusionNode`         | yes  | yes      | `run(**kwargs)` `documents:list`,`query:str`,opt `config:dict`; returns {original_query, query_variations, fused_results, final_response, fusion_metadata} (`advanced.py:483-580`). Generates query variations via `LLMAgentNode`, retrieves per-variation via base workflow, RRF/weighted/simple fusion (pure-compute fusion math `:729-841`). | COMPOSITE(LLM + broken stub); fusion math alone PURE_COMPUTE | hard `LLMAgentNode` ctor (`:585`) + stub (`:594`)                              | **HIGH — S2 at `:711`; S1 at `:585`**                                  |
| `HyDENode`              | yes  | yes      | `run(**kwargs)` `documents`,`query`,opt `config`; returns {hypotheses_generated, hypothesis_results, combined_retrieval, final_answer, hyde_metadata} (`advanced.py:955-1034`). `LLMAgentNode` generates hypotheses, retrieves per-hypothesis via base workflow.                                                                                | COMPOSITE(LLM + broken stub)                                 | hard `LLMAgentNode` ctor (`:1039`) + stub (`:1048`)                            | **HIGH — S2 at `:1126`; S1 at `:1039`**                                |
| `StepBackRAGNode`       | yes  | yes      | `run(**kwargs)` `documents`,`query`,opt `config`; returns {specific_query, abstract_query, specific_retrieval, abstract_retrieval, combined_results, final_answer, step_back_metadata} (`advanced.py:1279-1349`). LLM abstracts query, dual retrieval, weighted combine (combine math pure).                                                    | COMPOSITE(LLM + broken stub)                                 | hard `LLMAgentNode` ctor (`:1354`) + stub (`:1363`)                            | **HIGH — S2 at `:1464`; S1 at `:1354`**                                |

(Note: `advanced.py:1596 update_init_file()` is a dead helper FUNCTION, not
a class — correctly outside the 58. It returns import-string text and is
never called; flag as dead code for implement-phase cleanup.)

### agentic.py

| Class                  | reg? | **all**? | Contract                                                                                                                                                                                                                                                                                                                                                      | Infra                                                           | Backend                                                                                                 | Breakage                                                                  |
| ---------------------- | ---- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| `AgenticRAGNode`       | yes  | yes      | `WorkflowNode`; `__init__(tools, max_reasoning_steps, planning_strategy, verification_enabled)` builds ReAct planner/react/tool-executor/state-manager/verifier/synthesizer graph (`agentic.py:84-548`). No own `run()`; inherits `WorkflowNode.run`. Tool executor PythonCodeNode contains an AST-walked safe-arith calculator (`:213-275`, real, not stub). | CONSTRUCTION=PURE_COMPUTE; FULL-RUN=COMPOSITE(LLM, multi-cycle) | string `LLMAgentNode`; hard imports `RESTClientNode`,`SQLDatabaseNode`,`PythonCodeNode` (`:19-22`)      | MED — S5 (RESTClient/SQLDatabase import-existence); construction testable |
| `ToolAugmentedRAGNode` | yes  | yes      | pure `Node.run(**kwargs)` `query:str`,opt `documents:list`,`context:dict`; returns {answer, tools_invoked, tool_outputs, confidence} (`agentic.py:594-644`). `_detect_required_tools` is keyword-match (acceptable: tool DETECTION not agent reasoning), invokes `self.tool_registry` callables.                                                              | PURE_COMPUTE (empty registry default)                           | injected `tool_registry: Dict[str,Callable]` ctor param (the ONLY injected-backend node in the toolkit) | LOW                                                                       |
| `ReasoningRAGNode`     | yes  | yes      | `WorkflowNode`; `__init__(reasoning_depth, strategy)` builds decomposer/step-reasoner/logic-verifier LLM graph (`agentic.py:721-813`). No own run.                                                                                                                                                                                                            | CONSTRUCTION=PURE_COMPUTE; FULL-RUN=LLM                         | string `LLMAgentNode`                                                                                   | MED — S5                                                                  |

### conversational.py

| Class                    | reg? | **all**? | Contract                                                                                                                                                                                                                                                                                                                                                                                                | Infra                                                                             | Backend                                                   | Breakage                                         |
| ------------------------ | ---- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- | --------------------------------------------------------- | ------------------------------------------------ |
| `ConversationalRAGNode`  | yes  | yes      | `WorkflowNode`; `__init__(max_context_turns, enable_summarization, personalization_enabled, coreference_resolution, topic_tracking)` builds context-loader/coref/topic/retriever/response-gen/summarizer/updater/formatter graph (`conversational.py:98-604`). ALSO public `create_session(user_id)` → {session_id, created, expires_in} (`:606-633`) — a non-`run` public method needing its own test. | CONSTRUCTION=PURE_COMPUTE; FULL-RUN=COMPOSITE(LLM); `create_session`=PURE_COMPUTE | string `LLMAgentNode`; hard `LLMAgentNode` import (`:29`) | MED — S1 (import only, not constructed directly) |
| `ConversationMemoryNode` | yes  | yes      | pure `Node.run(**kwargs)` `operation:str`(store/retrieve/update/forget),`user_id:str`,opt `data:dict`,`context:str`; dispatches to `_store/_retrieve/_update/_forget_memory`; in-memory `defaultdict` store, GDPR forget path (`conversational.py:727-997`). Operation dispatch is config-branching (permitted — not agent reasoning).                                                                  | PURE_COMPUTE (in-memory store)                                                    | none (self-owned `self.memory_store`)                     | LOW                                              |

### evaluation.py

| Class                      | reg? | **all**? | Contract                                                                                                                                                                                                                                                                                                                                                                                                                                  | Infra                                                    | Backend                                         | Breakage                                                                                                               |
| -------------------------- | ---- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- | ----------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `RAGEvaluationNode`        | yes  | yes      | `WorkflowNode`; `__init__(metrics, use_reference_answers, llm_judge_model)` builds test-executor/faithfulness/relevance/context-precision/answer-quality/aggregator graph (`evaluation.py:90-444`). test_executor + context_evaluator + aggregator are pure Python; faithfulness/relevance/answer-quality are LLM. No own run.                                                                                                            | CONSTRUCTION=PURE_COMPUTE; FULL-RUN=COMPOSITE(LLM judge) | string `LLMAgentNode`; hard import (`:28`)      | MED — S1 (import only)                                                                                                 |
| `RAGBenchmarkNode`         | yes  | yes      | pure `Node.run(**kwargs)` `rag_systems:dict`,`test_queries:list`,opt `duration:int`; returns {benchmark_results, comparison, test_configuration} (`evaluation.py:515-600`). Uses `time.sleep` to SIMULATE latency + `random` for resource usage — the timing numbers are synthetic stand-ins (flag: documented "benchmarks RAG systems" but does not actually invoke `system.run`; `:541` comment "Would call system.run in production"). | PURE_COMPUTE (synthetic timings)                         | `rag_systems` dict passed in, but NEVER invoked | LOW (runtime) but contract is partly synthetic — test asserts ACTUAL (synthetic) behavior, flag the no-op `system.run` |
| `TestDatasetGeneratorNode` | yes  | yes      | pure `Node.run(**kwargs)` `num_samples:int`,opt `domain:str`,`seed:int`; returns {test_dataset, statistics, generation_config} (`evaluation.py:727-872`). Template-based synthetic dataset; deterministic with `seed`.                                                                                                                                                                                                                    | PURE_COMPUTE                                             | none                                            | LOW                                                                                                                    |

### federated.py

| Class              | reg? | **all**? | Contract                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | Infra                                                                          | Backend                                                | Breakage                                                                                                                                                             |
| ------------------ | ---- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `FederatedRAGNode` | yes  | yes      | `WorkflowNode`; `__init__(federation_nodes, aggregation_strategy, min_participating_nodes, timeout_per_node, enable_caching)` builds distributor/executor/aggregator/cache/formatter graph (`federated.py:88-579`). The `federated_executor` PythonCodeNode SIMULATES network calls with `random` (`:189` "10% failure rate", `:199` random latency) — NO real `requests`/RESTClientNode call despite `RESTClientNode` import (`:24`). Documented as "queries across distributed nodes" but is fully synthetic. No own run. | CONSTRUCTION=PURE_COMPUTE; FULL-RUN=PURE_COMPUTE (synthetic, NOT real NETWORK) | string node-types; hard `RESTClientNode` import unused | MED — S5 (RESTClientNode import-existence). Contract is synthetic — test asserts current (simulated) behavior; flag the synthetic-network as a fidelity gap for user |
| `EdgeRAGNode`      | yes  | yes      | pure `Node.run(**kwargs)` `query:str`,`local_data:list`,opt `sync_with_cloud:bool`; returns {results, resource_usage, sync_recommendations, edge_metadata}; in-memory FIFO cache w/ size eviction (`federated.py:655-829`). `_estimate_memory_usage` is a hardcoded lookup, not real psutil.                                                                                                                                                                                                                                | PURE_COMPUTE                                                                   | self-owned `self.cache`                                | LOW (runtime); flag synthetic memory numbers                                                                                                                         |
| `CrossSiloRAGNode` | yes  | yes      | pure `Node.run(**kwargs)` `query:str`,`requester_org:str`,`access_permissions:list`,opt `purpose:str`; returns {silo_results, audit_trail, compliance_report, federation_metadata}; access validation + governance redaction (`federated.py:905-959`). `_execute_cross_silo_query` simulates silo responses with `random` (`:1020`).                                                                                                                                                                                        | PURE_COMPUTE (synthetic silos)                                                 | none                                                   | LOW (runtime); flag synthetic silo data                                                                                                                              |

### graph.py

| Class              | reg? | **all**? | Contract                                                                                                                                                                                                                                                                                                                                                                       | Infra                                                                              | Backend                                                                                                             | Breakage                                                                                       |
| ------------------ | ---- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `GraphRAGNode`     | yes  | yes      | `WorkflowNode`; `__init__(entity_types, relationship_types, max_hops, community_algorithm='louvain', use_global_summary)` builds entity-extractor(LLM)/graph-builder(networkx PythonCodeNode)/query-processor(LLM)/graph-retriever(networkx)/summary/synthesizer graph (`graph.py:82-451`). graph_builder PythonCodeNode `import community` when louvain (`:178`). No own run. | CONSTRUCTION=PURE_COMPUTE; FULL-RUN=COMPOSITE(LLM + GRAPH(networkx) + `community`) | string `LLMAgentNode`; hard `LLMAgentNode` import (`:24`); module-scope `import networkx as nx` (`:18`, IN `[rag]`) | **HIGH — S6 `community` not in [rag] (default louvain breaks built-graph runtime); S1 import** |
| `GraphBuilderNode` | yes  | yes      | pure `Node.run(**kwargs)` `documents:list`,opt `existing_graph:dict`,`entity_types:list`; returns {graph (node_link_data), entity_map, statistics, build_metadata} using real `networkx.MultiDiGraph` (`graph.py:530-578`). Entity extraction is a hardcoded `if "transformer" in content` stub (`:556`) — documented "uses LLM/NER" but does NOT.                             | PURE_COMPUTE (networkx, in [rag])                                                  | none (self-builds nx graph)                                                                                         | LOW (runtime); flag stub entity extraction as fidelity gap                                     |
| `GraphQueryNode`   | yes  | yes      | pure `Node.run(**kwargs)` `graph:dict`,`query_type:str`(path/pattern/aggregate),`query_params:dict`; returns {query_type, matches, paths, aggregations} via real `nx.node_link_graph` + `nx.all_simple_paths`/`nx.density`/`nx.average_clustering` (`graph.py:648-717`). query_type dispatch is config-branching (permitted).                                                  | PURE_COMPUTE (networkx, in [rag])                                                  | none                                                                                                                | LOW                                                                                            |

### multimodal.py

| Class                         | reg? | **all**? | Contract                                                                                                                                                                                                                                                                                                                                                                    | Infra                                                                          | Backend                                                   | Breakage                                                                            |
| ----------------------------- | ---- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ | --------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `MultimodalRAGNode`           | yes  | yes      | `WorkflowNode`; `__init__(image_encoder, enable_ocr, fusion_strategy)` builds query-analyzer(LLM)/doc-preprocessor/encoder/retriever/response-gen(`gpt-4-vision`)/formatter graph (`multimodal.py:84-431`). The "image encoder" PythonCodeNode is a hash-based stand-in (`:211`) — NO Pillow despite docstring; only `import base64`,`pathlib` at module scope. No own run. | CONSTRUCTION=PURE_COMPUTE; FULL-RUN=COMPOSITE(LLM vision); NOT real MULTIMODAL | string `LLMAgentNode`; hard `LLMAgentNode` import (`:27`) | MED — S1 import; S4 `gpt-4-vision` hardcoded (`:367`)                               |
| `VisualQuestionAnsweringNode` | yes  | yes      | pure `Node.run(**kwargs)` `image_path:str`,`question:str`,opt `context:dict`; returns {answer, confidence, image_caption, detected_objects, model_used} (`multimodal.py:499-554`). Pure keyword-branch SIMULATION — never opens `image_path`, no Pillow. Documented VQA but synthetic.                                                                                      | PURE_COMPUTE (synthetic, NOT MULTIMODAL)                                       | none                                                      | LOW (runtime); flag synthetic VQA — `[rag]` ships Pillow but node never uses it     |
| `ImageTextMatchingNode`       | yes  | yes      | pure `Node.run(**kwargs)` `query:Union[str,dict]`,`collection:list`,opt `top_k:int`; returns {matches, similarity_scores, match_type, model, total_searched} (`multimodal.py:622-668`). Keyword-overlap scoring stand-in. Note `query` param type is `Union[str,dict]` (only NodeParameter using a Union type — verify NodeParameter accepts it).                           | PURE_COMPUTE                                                                   | none                                                      | LOW; verify `type=Union[str,dict]` NodeParameter accepted (potential contract edge) |

### optimized.py

| Class                   | reg? | **all**? | Contract                                                                                                                                                                                                                                                                                                                                                                                | Infra                                                                                                    | Backend                                                            | Breakage                                                                                                                                                                                        |
| ----------------------- | ---- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `CacheOptimizedRAGNode` | yes  | yes      | `WorkflowNode`; `__init__(cache_ttl, similarity_threshold)` builds cache-key-gen/`"CacheNode"`(STRING — absent!)/semantic-cache/`"HybridRAGNode"`/`"CacheNode"`/aggregator graph (`optimized.py:80-280`). No own run.                                                                                                                                                                   | CONSTRUCTION=PURE_COMPUTE (lazy string resolution); FULL-RUN=broken (CacheNode never implemented per S7) | string node-types incl. unresolvable `"CacheNode"`                 | **HIGH — S7: `"CacheNode"` string at `:147,:212` never resolves; documented golden path raises registry-miss at execute. Test pins current broken contract (CacheNode out-of-scope per brief)** |
| `AsyncParallelRAGNode`  | yes  | yes      | `WorkflowNode`; `__init__(strategies)` builds parallel-executor + per-strategy nodes (`"SemanticRAGNode"`/`"SparseRetrievalNode"`/`"HybridRAGNode"` by string) + combiner (`optimized.py:327-487`). No own run.                                                                                                                                                                         | CONSTRUCTION=PURE_COMPUTE; FULL-RUN=COMPOSITE(strategy sub-nodes need embedding/vector)                  | string strategy node-types; `AsyncLocalRuntime` import (`:24`, S5) | MED — S5 (AsyncLocalRuntime import-existence)                                                                                                                                                   |
| `StreamingRAGNode`      | yes  | yes      | `WorkflowNode`; `__init__(chunk_size)` builds stream-controller/progressive-retriever/stream-formatter graph, all pure-Python keyword retrieval (`optimized.py:535-674`). No own run. NOTE: name collides with `realtime.RealtimeStreamingRAGNode`'s pre-rename history — THIS is the surviving `optimized.StreamingRAGNode` (in `__all__`); the realtime one was renamed (S, see 02b). | CONSTRUCTION=PURE_COMPUTE; FULL-RUN=PURE_COMPUTE                                                         | string `PythonCodeNode` only                                       | LOW                                                                                                                                                                                             |
| `BatchOptimizedRAGNode` | yes  | yes      | `WorkflowNode`; `__init__(batch_size)` builds batch-organizer/processor/formatter graph, pure-Python batched keyword scoring (`optimized.py:721-924`). `run` input is `queries:list` (not `query`/`documents` — different contract shape). No own run.                                                                                                                                  | CONSTRUCTION=PURE_COMPUTE; FULL-RUN=PURE_COMPUTE                                                         | string `PythonCodeNode` only                                       | LOW                                                                                                                                                                                             |

### privacy.py

| Class                      | reg? | **all**? | Contract                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Infra                                                              | Backend                                                             | Breakage                                                               |
| -------------------------- | ---- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `PrivacyPreservingRAGNode` | yes  | yes      | `WorkflowNode`; `__init__(privacy_budget, redact_pii, anonymize_queries, audit_logging)` builds pii-detector/query-anonymizer/dp-noise/secure-aggregator/private-rag-executor/audit-logger/formatter graph, ALL pure-Python (regex PII, Laplace noise, k-anon clustering) (`privacy.py:84-588`). No own run. NOTE: imports `CredentialManagerNode` (`:26`) but NEVER uses it (S5).                                                                                                  | CONSTRUCTION=PURE_COMPUTE; FULL-RUN=PURE_COMPUTE (no LLM in graph) | string `PythonCodeNode` only; unused `CredentialManagerNode` import | MED — S5 (`CredentialManagerNode` import-existence is the only risk)   |
| `SecureMultiPartyRAGNode`  | yes  | yes      | pure `Node.run(**kwargs)` `query:str`,`party_data:dict`,opt `computation_type:str`; returns aggregate_result + computation_proof + party_contributions; protocol dispatch (secret_sharing/homomorphic) (`privacy.py:666-689`). Crypto is SIMULATED (`random.random()` "encrypted_value" `:702`) — documented "cryptographic guarantees" but synthetic (zero-tolerance fake-encryption flavor: test asserts CURRENT synthetic behavior + flag as fidelity gap for user disposition). | PURE_COMPUTE (synthetic crypto)                                    | none                                                                | LOW (runtime); FLAG: docstring claims crypto the code does not perform |
| `ComplianceRAGNode`        | yes  | yes      | pure `Node.run(**kwargs)` `query:str`,`documents:list`,`user_consent:dict`,opt `jurisdiction:str`; returns {results, compliance_report, retention_policy, user_rights}; consent validation + classification-based redaction (`privacy.py:862-901`). Real logic (no synthetic).                                                                                                                                                                                                      | PURE_COMPUTE                                                       | none                                                                | LOW                                                                    |

---

Continued in `02b-node-contracts.md` (query_processing, realtime,
registry, router, similarity, strategies, workflows + full summary table +
histograms).
