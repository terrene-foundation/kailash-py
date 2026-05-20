# Kaizen RAG Node Toolkit

The `kaizen.nodes.rag` package is a toolkit of retrieval-augmented-generation
nodes. Every node is a `kailash.nodes.base.Node` subclass and registers via
`@register_node()`. This spec is built incrementally — it documents only the
behavior that ships on `main` and is covered by behavioral tests. F8 shard B1
contributes the `## Similarity / dense retrieval` section.

## Similarity / dense retrieval

`kaizen/nodes/rag/similarity.py` defines seven retrieval/reranking/fusion
nodes. The toolkit ships **no LLM client and no vector store** — the `[rag]`
extra carries `numpy`, `Pillow`, `networkx`, `aiosqlite`, and `requests`. None
of the seven nodes hard-requires an LLM key or a vector database: every
`run()` method computes its result with deterministic `numpy` / keyword logic.
That deterministic path IS the shipped default path, not a degraded fallback.

All seven nodes share a `run(self, **kwargs) -> Dict[str, Any]` contract.
Constructors take only configuration (model names, fusion method, weights);
the query and corpus are passed to `run()`.

### Common output contract

On the success path, every node returns a dict with:

- `results` — a list of matched-document dicts, sorted by descending score.
- `scores` — a list of floats, parallel to `results`, descending.
- `retrieval_method` — a string tag identifying the node.
- `total_results` — `len(results)`.

On the error path (an unexpected exception inside `run()`), every node
returns `results: []`, `scores: []`, the `retrieval_method` tag, and an
`error` key carrying `str(e)`. The exception is also emitted via
`logger.error` on the `kaizen.nodes.rag.similarity` logger — the error log
line is the observable contract for the error path.

Each result document dict carries `content`, `metadata`, `id`, and a
node-specific `similarity_type` tag. When an input document omits `id`, the
node synthesises `doc_<index>`.

### DenseRetrievalNode

Constructor: `DenseRetrievalNode(name, embedding_model, similarity_metric,
use_instruction_embeddings)`. `run()` accepts `query: str`, `documents: list`,
`k: int = 5`.

Shipped scoring path: keyword-overlap. The query is lowercased and split into a
word set; each document's `content` is lowercased and split likewise; the
score is `len(query_words ∩ doc_words) / len(query_words)`, a value in
`[0, 1]`. Documents with a zero score are dropped. The surviving documents are
sorted by descending score and truncated to the top `k`.

- `retrieval_method`: `"dense"`. `similarity_type`: `"dense"`.
- Empty `query` or empty `documents` → empty result (no `error`).
- A document with no `content` key scores 0 and is dropped cleanly.

### SparseRetrievalNode

Constructor: `SparseRetrievalNode(name, method, use_query_expansion)`. The
instance also carries BM25 constants `k1 = 1.2` and `b = 0.75`. `run()`
accepts `query`, `documents`, `k = 5`.

Shipped scoring path: BM25. The query is lowercased and split into terms. For
each document the node computes the term frequency, an inverse-document-
frequency term via `numpy.log`, and combines them with the BM25 length-
normalised formula using `k1`, `b`, and the corpus average document length.
Documents with a zero score are dropped; survivors are sorted descending and
truncated to top `k`. BM25 scores are non-negative `numpy` floats.

- `retrieval_method`: `"sparse"`. `similarity_type`: `"sparse"`.
- Empty `query` or empty `documents` → `results: []`, `scores: []`.
- IDF rewards term rarity: a query for a term unique to one document surfaces
  that document first.

### ColBERTRetrievalNode

Constructor: `ColBERTRetrievalNode(name, token_model)`. `run()` accepts
`query`, `documents`, `k = 5`.

Shipped scoring path: simplified late interaction. The query and each document
are tokenised by whitespace. For each query token the node computes a per-token
max-similarity against the document tokens — `1.0` for an exact token match,
`0.5` for a substring match in either direction, `0.0` otherwise. The document
score is the average max-similarity over query tokens, a value in `[0, 1]`.
Zero-score documents are dropped; survivors are sorted descending and truncated
to top `k`.

- `retrieval_method`: `"colbert"`. `similarity_type`: `"late_interaction"`.
- A whitespace-only query yields no tokens → empty result.
- Empty `query` or empty `documents` → empty result.

### MultiVectorRetrievalNode

Constructor: `MultiVectorRetrievalNode(name)`. `run()` accepts `query`,
`documents`, `k = 5`.

Shipped scoring path: weighted multi-representation overlap. For each document
the node builds three representations — the full lowercased content, the first
200 characters as a summary, and the words longer than four characters
(first 10) as keywords. It scores each representation by query-word overlap
count, then combines them as `(0.5·full + 0.3·summary + 0.2·keywords) /
len(query_words)`. Zero-score documents are dropped; survivors are sorted
descending and truncated to top `k`.

- `retrieval_method`: `"multi_vector"`. `similarity_type`: `"multi_vector"`.
- Empty `query` or empty `documents` → empty result.

### CrossEncoderRerankNode

Constructor: `CrossEncoderRerankNode(name, rerank_model)`. `run()` accepts
`query: str`, `initial_results: dict`, `k: int = 10`. `initial_results` is the
output of a first-stage retrieval node — a dict with `results` and `scores`
lists.

Shipped scoring path: keyword-based two-stage reranking. The node takes the
first 20 documents of `initial_results["results"]`. For each it computes
`coverage` (query-word overlap ÷ query-word count) and `precision` (overlap ÷
content-word count), then blends them with the carried-over initial score:
`rerank_score = 0.4·initial_score + 0.3·coverage + 0.3·precision`, a value in
`[0, 1]`. The reranked documents are sorted descending and truncated to top
`k`.

- `retrieval_method`: `"cross_encoder_rerank"`. The result also carries
  `reranked_count` — the number of documents that were reranked (≤ 20).
- Empty `query` or empty `initial_results` → empty result.
- A missing `scores` list in `initial_results` makes the initial-score
  component default to `0.0`.

### HybridFusionNode

Constructor: `HybridFusionNode(name, fusion_method, weights)`. `fusion_method`
defaults to `"rrf"`; `weights` defaults to `{"dense": 0.7, "sparse": 0.3}`.
`run()` accepts `retrieval_results: list` (a list of result-set dicts, each
with `results` and `scores`), `fusion_method` (overrides the constructor
value), `k: int = 10`.

Shipped fusion paths:

- **`rrf`** (default) — Reciprocal Rank Fusion. Each document's fused score
  accumulates `1 / (60 + rank + 1)` across every result set it appears in. A
  document appearing in multiple result sets accumulates a higher score.
- **any other value** — weighted average. Each document's fused score is the
  arithmetic mean of the scores it received across result sets.

Fused documents are sorted descending and truncated to top `k`.

- The result carries the `fusion_method` actually used and `input_count` —
  the number of input result sets.
- Empty `retrieval_results` → `results: []`, `scores: []`.
- `HybridFusionNode` identifies documents by `id`, falling back to a hash of
  `content` — it never calls string methods on `content`.

### PropositionBasedRetrievalNode

Constructor: `PropositionBasedRetrievalNode(name)`. `run()` accepts `query`,
`documents`, `k = 5`.

Shipped scoring path: sentence-level proposition matching. Each document's
`content` is split on `". "` into candidate sentences; sentences whose
stripped length exceeds 20 characters become propositions. For each document
the node finds the single best-matching proposition by query-word overlap
ratio (in `[0, 1]`). Documents whose best proposition scores 0 are dropped;
survivors are sorted descending and truncated to top `k`.

- `retrieval_method`: `"proposition"`. `similarity_type`: `"proposition"`.
- The result carries `matched_propositions` — a list parallel to `results`,
  one best-matching proposition string per result document.
- Sentences of 20 characters or fewer are not eligible propositions.
- Empty `query` or empty `documents` → empty result.

### Malformed-document handling

Every node accepts a `documents` (or `initial_results["results"]`) list of
dicts. A document may omit `content` (treated as empty) or carry `content:
None` (coerced to empty). Neither case raises — the document scores 0 and is
dropped, and `run()` returns a normal (non-`error`) result. A document that is
not a dict at all (e.g. a bare string) triggers the error path: `run()`
returns an `error` key and emits a `logger.error` line.

### `_create_workflow` helpers

`SparseRetrievalNode`, `ColBERTRetrievalNode`, `MultiVectorRetrievalNode`,
`CrossEncoderRerankNode`, `HybridFusionNode`, and `PropositionBasedRetrievalNode`
each expose a private `_create_workflow(self) -> Workflow` method that builds a
`WorkflowBuilder` graph and returns the built `kailash.workflow.graph.Workflow`.
These helpers are not exercised by the `run()` default path; they are the
workflow-composition surface for callers that want to run the retrieval logic
through the Kailash runtime.

## Graph RAG

`kaizen/nodes/rag/graph.py` defines three knowledge-graph nodes. The toolkit
ships `networkx` (via the `[rag]` extra) as the real graph backend — there is
no separate graph database. `GraphBuilderNode` and `GraphQueryNode` compute
their results entirely with deterministic `networkx` operations on the
`run()` path. `GraphRAGNode` is a `kailash.nodes.logic.workflow.WorkflowNode`.

### `GraphBuilderNode`

Builds a knowledge graph from documents. `run(self, **kwargs) -> Dict[str, Any]`.

- Inputs (`get_parameters()`): `documents` (`list`, required), `existing_graph`
  (`dict`, optional — a prior graph to extend), `entity_types` (`list`,
  optional), plus the constructor-config parameters `merge_similar_entities`,
  `similarity_threshold`, `track_temporal`, `confidence_scoring`.
- The graph is a `networkx.MultiDiGraph`. When `existing_graph` is supplied it
  is reconstructed via `nx.node_link_graph` and extended; otherwise a fresh
  graph is created.
- Entity extraction is a simplified deterministic rule: a document whose
  `content` contains the word `transformer` (case-insensitive) contributes a
  `transformer` node (`type="technology"`) and an `attention` node
  (`type="concept"`) joined by a `uses` edge. Documents without that word
  contribute no nodes. Entity nodes are keyed by name, so multiple documents
  naming the same entity collapse to one node.
- A document may omit `content`, carry `content: None`, or be a non-dict
  element of the `documents` list. None of these raises: a missing or `None`
  content is coerced to an empty string, and a non-dict element is skipped.
  `build_metadata["documents_processed"]` still counts every element of the
  input list.
- Returns: `graph` (a `nx.node_link_data` dict — JSON-shaped, round-trippable),
  `entity_map` (a dict, currently empty), `statistics`
  (`total_nodes`, `total_edges`, `density`, `components`, all computed by
  `networkx`), and `build_metadata` (`documents_processed`, `merge_applied`,
  `temporal_tracking`).

### `GraphQueryNode`

Queries a knowledge graph. `run(self, **kwargs) -> Dict[str, Any]`.

- Inputs (`get_parameters()`): `graph` (`dict`, required — a node-link graph),
  `query_type` (`str`, required), `query_params` (`dict`, required).
- The result always carries `query_type`, `query_params`, `matches`, `paths`,
  and `aggregations`. Three query types populate them:
  - `path` — finds connections between `query_params["source_entity"]` and
    `query_params["target_entity"]` (both lower-cased) via
    `nx.all_simple_paths`, bounded by `max_length` (default 3), capped at 10
    paths. Each path entry carries `path`, `length`, and `edges`. If either
    endpoint is absent from the graph, `paths` is empty.
  - `pattern` — returns nodes matching `query_params["pattern"]["node_type"]`
    (or all nodes when no type is given), each with `entity`, `attributes`,
    and `degree`; capped at 20 matches.
  - `aggregate` — returns `node_count`, `edge_count`, `density`, `avg_degree`,
    and `clustering_coefficient`. The clustering coefficient is computed over
    `nx.Graph(G.to_undirected())` — the multigraph is collapsed to a simple
    undirected graph because `nx.average_clustering` is undefined on a
    multigraph. An empty graph yields zeroed statistics.
- An unrecognised `query_type` returns the base result shape with empty
  `matches`, `paths`, and `aggregations` — no exception.

### `GraphRAGNode`

`GraphRAGNode` is a `WorkflowNode`. Its `run()` (inherited from `WorkflowNode`)
executes a sub-workflow built at construction time by
`_create_workflow(self) -> Workflow`.

- Constructor config: `entity_types` (default
  `["person", "organization", "concept", "technology"]`), `relationship_types`
  (default `["relates_to", "influences", "uses", "created_by"]`), `max_hops`
  (default 2), `community_algorithm` (default `"louvain"`), and
  `use_global_summary` (default `True`).
- `_create_workflow()` builds a `WorkflowBuilder` graph. With
  `use_global_summary=True` the workflow has six nodes — `entity_extractor`,
  `graph_builder`, `query_processor`, `graph_retriever`, `summary_generator`,
  `result_synthesizer`. With `use_global_summary=False` the `summary_generator`
  node and its connections are omitted, leaving five nodes.
- The constructor config flows into the generated workflow: `entity_types`
  and `relationship_types` appear in the `entity_extractor` node's system
  prompt, and `max_hops` is interpolated into the `graph_retriever` node's
  `PythonCodeNode` code template as the BFS depth bound.
- `entity_extractor`, `query_processor`, and `summary_generator` are
  `LLMAgentNode` steps — executing the sub-workflow end-to-end requires an LLM
  key, which the `[rag]` extra does not carry.

## Agentic RAG

`kaizen/nodes/rag/agentic.py` defines three nodes that bring autonomous-agent
patterns (tool use, ReAct-style reasoning loops, multi-step reasoning chains)
to RAG. `ToolAugmentedRAGNode` is a direct `Node` with a deterministic
`run()`; `AgenticRAGNode` and `ReasoningRAGNode` are `WorkflowNode`s whose
behavior is a sub-workflow built at construction time.

### `ToolAugmentedRAGNode`

A `kailash.nodes.base.Node` with a direct `run(self, **kwargs) -> Dict[str, Any]`.
It augments retrieval by invoking registered tool callables.

- Constructor: `ToolAugmentedRAGNode(name, tool_registry, auto_detect_tools)`.
  `tool_registry` is a `Dict[str, Callable]` mapping a tool name to a callable
  invoked as `tool(query, context)`; it defaults to an empty dict.
- Inputs (`get_parameters()`): `query` (`str`, required), `documents`
  (`list`, optional), `context` (`dict`, optional), plus the three
  constructor parameters.
- `run()` calls `_detect_required_tools(query)` — a keyword scan that appends
  `calculator` for a query containing `calculate`/`compute`/`sum`/`average`,
  `unit_converter` for `convert`/`unit`/`measurement`, and `date_calculator`
  for `date`/`days`/`weeks`/`months`. Each detected tool that is present in
  `tool_registry` is invoked; a tool that raises is caught and recorded as
  `{"error": str(e)}` in `tool_outputs`, and the failure is logged via
  `logger.error` on the `kaizen.nodes.rag.agentic` logger.
- `run()` returns `answer` (a synthesized string), `tools_invoked` (the list
  of detected tool names), `tool_outputs` (the per-tool result dict), and
  `confidence` (`0.9` when any tool produced output, else `0.7`).
- A tool detected by keyword but absent from `tool_registry` is still listed
  in `tools_invoked`; it simply contributes no `tool_outputs` entry.
- Edge handling: a missing `documents` kwarg defaults to an empty list; a
  `query` of `None` is coerced to an empty string before tool detection;
  malformed documents (non-dict elements, `{}`, `{"content": None}`) are
  tolerated — synthesis only counts `len(documents)`. A registered tool
  returning a non-dict value (tools are arbitrary callables with no
  return-shape contract) is treated as a successful result.

### `AgenticRAGNode`

`AgenticRAGNode` is a `WorkflowNode`. Its `run()` (inherited from
`WorkflowNode`) executes a sub-workflow built at construction time by
`_create_workflow(self) -> Workflow`.

- Constructor config: `tools` (default `["search", "calculator",
"database"]`), `max_reasoning_steps` (default 5), `planning_strategy`
  (default `"react"`), and `verification_enabled` (default `True`).
- `_create_workflow()` builds a `WorkflowBuilder` graph. With
  `verification_enabled=True` the workflow has six nodes — `planner_agent`,
  `react_agent`, `tool_executor`, `state_manager`, `verifier_agent`,
  `result_synthesizer`. With `verification_enabled=False` the
  `verifier_agent` node and its connections are omitted, leaving five nodes.
- `planner_agent`, `react_agent`, and `verifier_agent` are `LLMAgentNode`
  steps; `tool_executor`, `state_manager`, and `result_synthesizer` are
  `PythonCodeNode` steps carrying a `code` template.
- The constructor config flows into the generated workflow: the `tools` list
  appears in the `planner_agent` system prompt, `max_reasoning_steps` is
  interpolated into the `state_manager` `code` template as the step bound and
  into the `result_synthesizer` template's `metadata.max_steps`, and
  `planning_strategy` is interpolated into the `result_synthesizer`
  template's `metadata.planning_strategy`.
- The `tool_executor` `code` template implements the `search`, `calculate`,
  `database`, and `verify` tools. `search` scores documents by query-word
  overlap; a document whose `content` or `title` is missing or `None` is
  coerced to an empty string and a non-dict document element is skipped.
  `calculate` evaluates arithmetic via an AST-walked safe evaluator (no
  `eval`/`exec`).
- The `LLMAgentNode` steps require an LLM key to execute end-to-end, which
  the `[rag]` extra does not carry.

### `ReasoningRAGNode`

`ReasoningRAGNode` is a `WorkflowNode`. Its `run()` (inherited) executes a
sub-workflow built at construction time by
`_create_workflow(self) -> Workflow`.

- Constructor config: `reasoning_depth` (default 3) and `strategy` (default
  `"chain_of_thought"`).
- `_create_workflow()` builds a `WorkflowBuilder` graph with three nodes —
  `problem_decomposer`, `step_reasoner`, and `logic_verifier`, all
  `LLMAgentNode` steps.
- The constructor config flows into the generated workflow: `strategy` and
  `reasoning_depth` are interpolated into the `problem_decomposer` system
  prompt.
- The `LLMAgentNode` steps require an LLM key to execute end-to-end, which
  the `[rag]` extra does not carry.

## Multimodal RAG

`kaizen.nodes.rag.multimodal` provides three node classes for retrieval and
question-answering over text + image content. Their behavior is locked by
`tests/unit/rag/test_multimodal_nodes.py` and
`tests/integration/rag/test_multimodal_nodes.py`.

### `VisualQuestionAnsweringNode`

`VisualQuestionAnsweringNode` is a `Node` subclass; its `run()` answers a
question about an image on a deterministic rule-based path — no LLM key is
required.

- `get_parameters()` declares `image_path` and `question` as required, and
  `model` (default `"blip2-base"`), `enable_captioning` (default `True`),
  `name`, and `context` as optional.
- `run()` returns `answer`, `confidence`, `image_caption`, `detected_objects`,
  and `model_used`. The answer and detected-objects list are selected by
  matching the lower-cased question against keyword groups: a `"what"` +
  `"components"`/`"parts"` question returns four interconnected-component
  objects at confidence `0.85`; a `"how many"` question returns six elements;
  a `"where"` question returns a central-location answer; an unmatched
  question falls back to a generic answer at confidence `0.7`.
- `image_caption` is non-empty only when `enable_captioning` is `True`;
  `model_used` echoes the constructor `model`.
- Edge handling: a missing `question` kwarg defaults to an empty string; a
  `question` of `None` is coerced to an empty string before keyword matching
  (`kwargs.get("question") or ""` — the `get` default applies only to a
  missing key, not a present-but-`None` value); `image_path` is never
  dereferenced as a string in `run()`, so a `None` or missing `image_path` is
  tolerated.

### `ImageTextMatchingNode`

`ImageTextMatchingNode` is a `Node` subclass; its `run()` ranks a collection
against a query on a deterministic rule-based scoring path.

- `get_parameters()` declares `query` (a `str` or `dict`) and `collection`
  (a `list`) as required, and `matching_model` (default `"clip"`),
  `bidirectional` (default `True`), `top_k` (default 5), and `name` as
  optional.
- `run()` returns `matches`, `similarity_scores`, `match_type`, `model`, and
  `total_searched`. A `str` query selects `match_type="text_to_image"`; any
  non-`str` query selects `match_type="image_to_text"`. On the text path a
  query containing `"architecture"` against a `"diagram"`-tagged item scores
  `0.9`, a query-word overlap with the item caption scores `0.7`, and
  everything else scores `0.3`; the image path scores a flat `0.5`. Results
  are sorted by descending score and capped at `top_k`.
- `total_searched` reports the raw `collection` length; `model` echoes the
  constructor `matching_model`.
- Edge handling: a missing or `None` `collection` defaults to an empty list;
  a non-dict element in the `collection` is skipped (collection elements are
  arbitrary user input and a non-dict element has no `.get`), while
  `total_searched` still counts it; a present-but-`None` caption or tag is
  tolerated by the `str()` coercion in scoring.

### `MultimodalRAGNode`

`MultimodalRAGNode` is a `WorkflowNode`. Its `run()` (inherited from
`WorkflowNode`) executes a sub-workflow built at construction time by
`_create_workflow(self) -> Workflow`.

- Constructor config: `image_encoder` (default `"clip-base"`), `enable_ocr`
  (default `True`), and `fusion_strategy` (default `"weighted"`); all three
  are stored in the node `config`.
- `_create_workflow()` builds a `WorkflowBuilder` graph with six nodes —
  `query_analyzer`, `doc_preprocessor`, `multimodal_encoder`,
  `cross_modal_retriever`, `response_generator`, and `result_formatter`.
- `query_analyzer` and `response_generator` are `LLMAgentNode` steps;
  `doc_preprocessor`, `multimodal_encoder`, `cross_modal_retriever`, and
  `result_formatter` are `PythonCodeNode` steps carrying a `code` template.
- The constructor config flows into the generated workflow: `enable_ocr` is
  interpolated into the `doc_preprocessor` `code` template's OCR branch, and
  `image_encoder` is interpolated into the `multimodal_encoder` template's
  `encoding_method`.
- The `doc_preprocessor` `code` template separates a mixed-media corpus into
  text and image documents. A non-dict document element is skipped — in the
  per-document loop body and in the stats-block `multimodal_docs` list
  comprehension — and a present-but-`None` `content` is coerced to an empty
  string.
- The `multimodal_encoder` `code` template builds query / text / image
  embeddings with numpy-backed math. Its `text_encoder` and `image_encoder`
  helpers coerce a non-string input to an empty string at the boundary, and
  the text-document and image-document concatenations coerce a
  present-but-`None` `content` / `title` / `caption` / `ocr_text` to an empty
  string before the `+`.
- The `cross_modal_retriever` `code` template scores, sorts, and splits
  retrieved results by text / image modality; its visual-term boost coerces a
  `None` or non-string `query` workflow input to an empty string before
  `.lower()`.
- The `LLMAgentNode` steps require an LLM key to execute the sub-workflow
  end-to-end, which the `[rag]` extra does not carry; the `PythonCodeNode`
  `code` templates are deterministic and exercised directly in the
  integration tests.

## Federated RAG

`kaizen/nodes/rag/federated.py` defines three nodes for retrieval across
distributed data sources without centralization: `EdgeRAGNode`,
`CrossSiloRAGNode`, and `FederatedRAGNode`. `EdgeRAGNode` and
`CrossSiloRAGNode` are `kailash.nodes.base.Node` subclasses with a direct
`run()`; `FederatedRAGNode` is a `kailash.nodes.logic.workflow.WorkflowNode`.
None of the three requires an LLM key or a network call on its shipped default
path — `federated.py` marks the federated executor explicitly as "simulated -
would use actual network calls". The federated aggregation, the cross-silo
governance, and the edge retrieval are all deterministic compute, and that
deterministic path IS the shipped default.

### `EdgeRAGNode`

Resource-constrained RAG over a local document corpus. `get_parameters()`
declares `query` (str, required) and `local_data` (list, required), plus
`sync_with_cloud` (bool, optional) and the constructor profile parameters
(`model_size`, `max_cache_size_mb`, `update_strategy`, `power_mode`).

`run()` returns a dict with four keys: `results`, `resource_usage`,
`sync_recommendations`, and `edge_metadata`. `_edge_optimized_retrieval`
keyword-matches the query words against each document's `content` and returns
the top five scored documents; `_generate_edge_response` builds an answer
whose detail scales with `model_size` (`tiny` reports a match count, `small`
echoes the top document, `medium` joins the top two). A repeated identical
query returns the cached result object unless `power_mode` is `"performance"`,
which bypasses the cache. `sync_recommendations` flags `should_sync` when the
local corpus has fewer than ten documents, when the cache nears capacity, or
when `sync_with_cloud` was requested.

`local_data` is arbitrary user input: a non-dict element is skipped, and a
present-but-`None` `content` is coerced to an empty string in both
`_edge_optimized_retrieval` and the `_generate_edge_response` content slices.
A `None` or missing `query` is coerced to an empty string before the cache-key
`hashlib.sha256(...).encode()`.

### `CrossSiloRAGNode`

RAG across organizational silos with data-governance enforcement.
`get_parameters()` declares `query`, `requester_org`, and `access_permissions`
(all required), plus `purpose` (optional) and the constructor parameters
(`silos`, `data_sharing_agreement`, `audit_mode`, `governance_rules`).

`run()` first calls `_validate_cross_silo_access`: the requester must be a
member of `silos`, must hold the permissions the `data_sharing_agreement` tier
requires (`minimal` → `read_aggregated`; `standard` adds `read_anonymized`;
`full` adds `read_samples`), and must state a `purpose` in the governance
allow-list. A failed check returns `{"error": "Access denied", "reason": ...,
"required_permissions": ...}`. On the granted path `run()` returns
`silo_results`, `audit_trail`, `compliance_report`, and `federation_metadata`.

`_execute_cross_silo_query` produces a per-silo result. `_apply_governance` is
the cross-organization data boundary: the requester's OWN silo keeps `full`
content; for every OTHER silo, a `minimal` agreement calls `_minimize_content`
(truncates to the first twenty words and appends "[Details restricted by data
sharing agreement]") and a `standard` agreement calls `_anonymize_content`
(replaces each silo name with `[Organization]` and redacts numeric and
all-caps identifiers). The governed result carries a `governance_applied`
marker (`"minimal_sharing"` or `"anonymized"`); the requester's own result
carries none. `audit_mode="minimal"` returns the string "Audit available on
request" in place of the structured `audit_trail` dict.

A `None` or missing `query` is coerced to an empty string before the
audit-trail `query.encode()` hash; a `None` or missing `access_permissions` is
coerced to an empty list before the membership check.

### `FederatedRAGNode`

Federated RAG as a `WorkflowNode`. The constructor accepts `federation_nodes`,
`aggregation_strategy` (`"weighted_average"`, `"voting"`, or simple merge),
`min_participating_nodes`, `timeout_per_node`, and `enable_caching`; the values
are stored as instance attributes and interpolated into the generated
workflow. `run()` is inherited from `WorkflowNode` and executes the sub-workflow
built by `_create_workflow()`.

`_create_workflow()` returns a `kailash.workflow.Workflow` built by
`WorkflowBuilder`. With `enable_caching=True` the workflow has five
`PythonCodeNode` steps — `query_distributor`, `federated_executor`,
`result_aggregator`, `cache_coordinator`, and `result_formatter`; with
`enable_caching=False` the `cache_coordinator` node is omitted.
`min_participating_nodes` is interpolated into the `federated_executor`
template's quorum check and `aggregation_strategy` into the `result_aggregator`
template's strategy branch.

Each step carries a `code` template (read off a built workflow node via
`workflow.get_node(node_id).code`). `query_distributor` builds one
target-node entry per endpoint. `federated_executor` is the simulated
federated path — it generates a per-node response with deterministic
`random`-seeded content and a quorum statistic. `result_aggregator` combines
the per-node results under the configured strategy; its result-intake loop
skips a non-dict peer result and coerces a present-but-`None` `content` to an
empty string before the grouping key, so every downstream strategy sees only
well-formed dicts. `cache_coordinator` selects high-score, high-agreement
results and coerces a `None` `content` to an empty string before the
`content_hash`. `result_formatter` builds the final `federated_rag_output`.

### What crosses the federated boundary

The federated RAG nodes advertise data locality — `FederatedRAGNode`'s
docstring states "Data never leaves source organizations" and
`CrossSiloRAGNode`'s states "strict data governance". The shipped contract,
precisely:

- `FederatedRAGNode` has no document-corpus input. Its workflow entry point
  (`query_distributor`, `def distribute_query(query, node_endpoints,
federation_config)`) reads only a query and per-node endpoints — there is no
  raw local document for the node to leak. The aggregate produced by
  `result_aggregator` carries per-result `content`, `score`, and `metadata`
  (source-node ids, weights, agreement) plus an `aggregation_metadata` block of
  `strategy`, `node_weights`, and `participating_nodes` — counts and scores,
  not a caller-supplied raw corpus.
- `CrossSiloRAGNode` is the real cross-organization boundary. The requester's
  own silo returns full content (its own data); every other silo's content is
  governed before it crosses — truncated and stamped under `minimal`,
  anonymized under `standard`.
- `EdgeRAGNode` is local-only by construction: there is no federated boundary,
  and its output legitimately contains the local document text because nothing
  is shared with any peer.

### Codegen-template runtime boundary

The `FederatedRAGNode` `_create_workflow()` codegen functions build a local
`result` dict as their final statement but do not `return` it; the integration
tests exercise each template by exec-ing the rendered function with an appended
`return result`. End-to-end runtime execution of the assembled sub-workflow is
not covered by the `[rag]` extra alone — the `PythonCodeNode` `code` templates
are deterministic and are covered directly.

## Advanced RAG

`kaizen/nodes/rag/advanced.py` ships four advanced RAG techniques as
`kailash.nodes.base.Node` subclasses with a direct `run()` —
`SelfCorrectingRAGNode`, `RAGFusionNode`, `HyDENode`, `StepBackRAGNode` — plus
the shared retrieval workflow `create_hybrid_rag_workflow` and the
module-local `RAGConfig`.

### `RAGConfig`

`RAGConfig` is a `**kwargs`-based config class. Its four fields and defaults:
`chunk_size` (1000), `chunk_overlap` (200), `embedding_model`
(`"text-embedding-3-small"`), `retrieval_k` (5). An unrecognized kwarg is
ignored, not raised. `retrieval_k` is the field that influences
`create_hybrid_rag_workflow` — it caps the fused result count.

### `create_hybrid_rag_workflow`

`create_hybrid_rag_workflow(config: RAGConfig)` builds a genuine hybrid-RAG
retrieval workflow and returns it wrapped in a `WorkflowNode`. Hybrid RAG
combines dense (embedding-similarity) retrieval with sparse (keyword /
term-frequency) retrieval and fuses the two with Reciprocal Rank Fusion (RRF).

The workflow graph has four nodes:

- `source` (`PythonCodeNode`) — entry node; receives `documents` and `query`
  via the `WorkflowNode` `input_mapping` and fans them out.
- `dense` (`DenseRetrievalNode`) — embedding-similarity retrieval. With no LLM
  key configured it runs its deterministic keyword-overlap fallback.
- `sparse` (`SparseRetrievalNode`) — keyword / term-frequency retrieval.
- `fuse` (`PythonCodeNode`) — RRF over the dense and sparse result lists;
  emits `results`, `scores`, and `metadata` as separate node outputs.

The graph has six connections: `source` fans `documents` and `query` to both
`dense` and `sparse` (four edges), and `dense` and `sparse` each feed their
`results` output into `fuse` (two edges). The returned `WorkflowNode` carries
an `input_mapping` (`documents`, `query` → `source`) and an `output_mapping`
(`results`, `scores`, `metadata` ← `fuse`), so a `run(documents=...,
query=..., operation="retrieve")` call returns a dict with top-level
`results` (the fused document list), `scores` (the fused RRF scores), and
`metadata` (`fusion_method`, `retrieval_modes`, `retrieval_k`, `dense_count`,
`sparse_count`). The `fuse` codegen template skips a non-dict document and
coerces a present-but-`None` `content` to an empty string before the dedup
key, so a malformed corpus does not crash workflow execution.

`advanced.py` imports `kaizen.nodes.rag.similarity` for the side effect of
registering `DenseRetrievalNode` / `SparseRetrievalNode` with the Kailash
`NodeRegistry`, which `WorkflowBuilder.build()` requires.

### The four advanced node classes

All four nodes declare `documents` (list) and `query` (str) as `required=True`
run-time parameters and accept an optional `config` dict. Each `run()` first
calls `_initialize_components()`, which builds the node's `LLMAgentNode`
helper(s) and the shared `base_rag_workflow` via `create_hybrid_rag_workflow`.
Every LLM-backed step (verification, query-variation generation, hypothesis
generation, abstract-query generation) is wrapped in a `try/except` that falls
back to a deterministic rule-based implementation — with no LLM key
configured, the node still produces a real, contract-shaped output.

The document-text helpers `_doc_content` and `_doc_dedup_key` are the
module's shared guards against malformed documents: `_doc_content` collapses a
missing key, a present-but-`None` `content`, and a non-dict element to `""`;
`_doc_dedup_key` returns a stable dedup key (explicit `id`, else the first 50
chars of content) and is safe against the same malformed inputs.

- **`SelfCorrectingRAGNode`** — retrieves, verifies result quality, and
  iteratively refines up to `max_corrections` times. `run()` returns `query`,
  `final_response`, `retrieved_documents`, `scores`, `quality_assessment`,
  `self_correction_metadata` (one `correction_history` entry per attempt), and
  `status` (`"corrected"` if the confidence threshold was met, else
  `"best_effort"`).
- **`RAGFusionNode`** — generates query variations, retrieves for the original
  query plus each variation, and fuses the result lists. `run()` returns
  `original_query`, `query_variations`, `fused_results`, `final_response`, and
  `fusion_metadata`. `_fuse_results` dispatches on `fusion_method` —
  `_reciprocal_rank_fusion` (the default and the fallback for an unknown
  method), `_weighted_fusion`, `_simple_concatenation`.
- **`HyDENode`** — generates hypothetical answers, retrieves using each
  hypothesis as the query, and combines the per-hypothesis results. `run()`
  returns `original_query`, `hypotheses_generated`, `hypothesis_results`,
  `combined_retrieval`, `final_answer`, and `hyde_metadata`.
- **`StepBackRAGNode`** — generates an abstract step-back query, retrieves for
  both the specific and the abstract query, and combines the two result sets
  with specific results weighted 0.7 and abstract 0.3. `run()` returns
  `specific_query`, `abstract_query`, `specific_retrieval`,
  `abstract_retrieval`, `combined_results`, `final_answer`, and
  `step_back_metadata`.

## Workflow & strategy RAG

`kaizen.nodes.rag.strategies` and `kaizen.nodes.rag.workflows` are the
documented RAG Quick Start surface — the chunk → embed → store → retrieve
pipelines and the multi-strategy routers a user reaches first.

### `RAGConfig` and the `create_*_rag_workflow` builders

`RAGConfig` (`strategies.py`) is the configuration dataclass shared by every
builder: `chunk_size` (1000), `chunk_overlap` (200), `embedding_model`
(`text-embedding-3-small`), `embedding_provider` (`openai`),
`vector_db_provider` (`postgresql`), `retrieval_k` (5), `similarity_threshold`
(0.7). Each field is overridable via the constructor and flows into the
corresponding node config in the built graph.

Four module-level builders each return a `WorkflowNode` wrapping a
`WorkflowBuilder`-constructed `Workflow`:

- **`create_semantic_rag_workflow`** — `semantic_chunker` → `embedder` →
  `vector_db` → `retriever` (dense `HybridRetrieverNode`).
- **`create_statistical_rag_workflow`** — `statistical_chunker` → `embedder` +
  `keyword_extractor` → `vector_db` → `retriever` (sparse). The
  `keyword_extractor` `PythonCodeNode` extracts stop-word-filtered keyword
  tokens per chunk.
- **`create_hybrid_rag_workflow(config, fusion_method="rrf")`** — embeds the
  semantic and statistical sub-workflows as `WorkflowNode` nodes and fuses
  their outputs in a `result_fusion` `PythonCodeNode`. The `fusion_method`
  argument is consumed — it is baked into the fusion codegen's output field.
- **`create_hierarchical_rag_workflow`** — `hierarchical_chunker` → `embedder`
  - `level_processor` → per-level vector DBs (`doc_vector_db`,
    `section_vector_db`, `para_vector_db`) → `hierarchical_retriever`. The
    `level_processor` `PythonCodeNode` buckets chunks by `hierarchy_level`.

`strategies.py` imports `kailash.nodes.transform.chunkers` for the side effect
of registering `SemanticChunkerNode` / `StatisticalChunkerNode` /
`HierarchicalChunkerNode` with the Kailash `NodeRegistry` — Kailash's lazy
module cache does not populate those node types until the module is imported,
and the builders reference them by string in `add_node(...)`.

### The four strategy `Node` classes

`SemanticRAGNode`, `StatisticalRAGNode`, `HybridRAGNode`, and
`HierarchicalRAGNode` wrap the corresponding builder as a single graph node.
Each declares `documents` (list, `required=True`), `query` (str), and
`operation` (str, default `"index"`) run-time parameters and accepts an
optional `config`; `HybridRAGNode` additionally declares `fusion_method`
(default `"rrf"`). Each `run()` lazily builds its wrapped `WorkflowNode` on
first call and delegates execution to it. `HybridRAGNode.run()` rebuilds the
wrapped workflow when the `fusion_method` kwarg differs from the cached value.

### The four `workflows.py` pipeline classes

All four are `WorkflowNode` subclasses; each `__init__` builds an inner
`Workflow` and passes it to `super().__init__(workflow=..., name=...)`:

- **`SimpleRAGWorkflowNode`** — wraps `create_semantic_rag_workflow`'s
  four-node graph directly.
- **`AdvancedRAGWorkflowNode`** — a `quality_analyzer` `PythonCodeNode`
  inspects the corpus, a `strategy_router` `SwitchNode` routes to one of four
  embedded strategy pipelines, and a `quality_validator` scores the result.
- **`AdaptiveRAGWorkflowNode`** — a `document_preprocessor` analyzes the
  corpus for an `rag_strategy_analyzer` `LLMAgentNode`, a `strategy_executor`
  `SwitchNode` routes to the chosen pipeline, and a `results_aggregator`
  combines the output.
- **`RAGPipelineWorkflowNode`** — a `config_processor` merges user config, a
  `strategy_dispatcher` `SwitchNode` routes to one of four strategy
  sub-workflows keyed on the `strategy` field, and a `results_formatter`
  shapes the output. `default_strategy` defaults to `"hybrid"`.

`RAGPipelineWorkflowNode` is registered via `@register_node()` and exported
from the `kaizen.nodes.rag` package `__all__`.

### Switch-router wiring

The `AdvancedRAGWorkflowNode` / `AdaptiveRAGWorkflowNode` /
`RAGPipelineWorkflowNode` routers are `SwitchNode` instances in multi-case
mode: `cases=["semantic", "statistical", "hybrid", "hierarchical"]`. A
multi-case `SwitchNode` emits each matched value on a `case_<value>` output
port, so the router-to-pipeline connections are
`add_connection(router, "case_<strategy>", pipeline, "input")` in the
canonical four-argument `WorkflowBuilder.add_connection(from_node,
from_output, to_node, to_input)` form.

### Malformed-input hygiene

The corpus-analysis `PythonCodeNode` templates — `quality_analyzer` and
`document_preprocessor` in `workflows.py`, `keyword_extractor` and
`level_processor` in `strategies.py` — filter `documents` / `chunks` to dict
elements with `isinstance` and read content via a nested `_content` helper
that collapses a missing key and a present-but-`None` `content` to `""`. A
malformed corpus (a non-dict element, a present-but-`None` `content`) does not
crash the codegen.

## Query processing

`kaizen.nodes.rag.query_processing` ships the pre-retrieval half of every
preserved RAG pipeline — the six `Node` subclasses that transform an incoming
query before it reaches a retriever. Each class also exposes a
`_create_workflow` builder that returns a `Workflow` (via `WorkflowBuilder`)
wiring the deterministic `run()` path's components as graph nodes for callers
that want to embed query processing inside a larger pipeline.

### `QueryExpansionNode`

Generates query variations to improve recall. The constructor accepts
`name` (default `"query_expansion"`), `expansion_method` (default `"llm"`),
and `num_expansions` (default `5`). `get_parameters()` declares `query`
(required `str`) plus the three constructor kwargs as optional parameters.
`run(query=...)` returns a dict with `original`, `expansions` (truncated
to `num_expansions`), `keywords`, `concepts`, `all_terms`, and
`expansion_count`. `_create_workflow()` builds a two-node graph:
`llm_expander` (`LLMAgentNode`, system prompt asks for `num_expansions`
variations + synonyms / concepts) → `expansion_processor` (`PythonCodeNode`
that merges expansions, keywords, concepts and deduplicates against the
original query). The connection is
`add_connection(llm_expander, "response", expansion_processor, "expansion_response")`.

### `QueryDecompositionNode`

Breaks complex queries into independent sub-questions. The constructor
accepts only `name` (default `"query_decomposition"`). `run(query=...)`
returns `sub_questions`, `execution_order`, `composition_strategy`
(`"sequential"`), and `total_questions`. A query containing `" and "` splits
on the conjunction; a query containing `" compare "` or `" vs "` yields a
3-question comparative breakdown. `_create_workflow()` builds a two-node
graph: `query_decomposer` (`LLMAgentNode`) → `dependency_resolver`
(`PythonCodeNode` that topologically-sorts sub-question dependencies into
an `execution_plan`).

### `QueryRewritingNode`

Rewrites queries for retrieval. The constructor accepts only `name`
(default `"query_rewriting"`). `run(query=...)` returns `original`,
`issues_found` (`"spelling_errors"`, `"too_short"`), a `versions` dict with
five keys — `corrected`, `clarified`, `contextualized`, `simplified`,
`technical` — and `recommended` / `all_unique_versions` /
`improvement_count`. The deterministic corrector substitutes the documented
typos `2 → to`, `u → you`, `wit → with`, `trian → train`, `nueral → neural`,
`netwrk → network`. `_create_workflow()` builds a three-node fan-in graph:
`query_analyzer` (`LLMAgentNode`) feeds both `query_rewriter`
(`LLMAgentNode`, on input `analysis`) and `result_combiner`
(`PythonCodeNode`, on input `analysis_result`); `query_rewriter` feeds
`result_combiner` on input `rewrite_result`.

### `QueryIntentClassifierNode`

Classifies query intent for strategy routing. The constructor accepts only
`name` (default `"query_intent_classifier"`). `run(query=...)` returns
`query_type` (`"factual"` / `"analytical"` / `"comparative"` /
`"exploratory"` / `"procedural"`), `domain` (`"technical"` / `"business"` /
`"academic"` / `"general"`), `complexity` (`"simple"` / `"moderate"` /
`"complex"` — bucketed by word count), `requirements` (a subset of
`"needs_examples"`, `"needs_recent"`, `"needs_authoritative"`,
`"needs_context"`), `recommended_strategy`, and `confidence` (`0.8` for
the deterministic path). The deterministic classifier matches on the
first keyword family it encounters — `what`/`who`/`when`/`where` →
factual; `how`/`why`/`explain` → analytical; `compare`/`vs`/`versus`/
`difference` → comparative; `show`/`give`/`list`/`find` → exploratory;
`implement`/`create`/`build`/`make` → procedural; default → factual.
`_create_workflow()` builds a two-node graph: `intent_classifier`
(`LLMAgentNode`) → `strategy_mapper` (`PythonCodeNode` containing a
`(query_type, complexity) → strategy` lookup table with
requirements-based adjustments).

### `MultiHopQueryPlannerNode`

Plans multi-step retrieval strategies. The constructor accepts only
`name` (default `"multi_hop_planner"`). `run(query=...)` returns
`batches` (lists of hops grouped by dependency-resolution wave),
`total_hops`, `parallel_opportunities`, `combination_strategy`
(`"sequential"`), and `estimated_time`. The deterministic planner emits
a 3-hop chain when the query contains `"influence"` or `"impact"`
(hop 3 depends on hops 1 and 2); otherwise a single hop. The batching
groups hops whose dependencies are all already processed.
`_create_workflow()` builds a two-node graph: `hop_planner`
(`LLMAgentNode`) → `execution_planner` (`PythonCodeNode` that validates
hop dependencies and emits parallelizable batches).

### `AdaptiveQueryProcessorNode`

Composes the other five processors based on query characteristics. The
constructor accepts only `name` (default `"adaptive_query_processor"`).
`run(query=...)` returns `original_query`, `processing_steps` (a subset
of `"rewrite"`, `"expand"`, `"decompose"`, `"multi_hop"`, `"analyze"`),
`processed_query`, `processing_plan` (a dict carrying `steps`,
`estimated_time`, and `complexity`), and `expected_improvement`. The
deterministic step-selection: `"rewrite"` fires when the query contains
any of `"2"`, `"u"`, `"wit"`, `"trian"` (the rewrite trigger;
substring-based, hits most queries with the letter `u`); `"expand"`
fires for queries with fewer than 4 words; `"decompose"` fires for
queries containing `"compare"` or `"vs"`; `"multi_hop"` fires for
queries containing `"influence"` or `"impact"`; `"analyze"` is the
default-only fallback. `_create_workflow()` builds a two-node graph:
`intent_analyzer` (a `QueryIntentClassifierNode` instance, by string)
→ `adaptive_processor` (`PythonCodeNode` that maps the intent's
`(query_type, complexity)` into a real processing-step list).

## Privacy & compliance

`kaizen.nodes.rag.privacy` ships three classes that protect sensitive data
across the RAG path — PII redaction + differential-privacy noise on the
core retrieval node, cryptographic data-sharing for federated retrieval,
and regulation-aware consent / retention enforcement.

### `PrivacyPreservingRAGNode`

A `WorkflowNode` subclass that composes a 6-stage privacy pipeline. The
constructor accepts `name` (default `"privacy_preserving_rag"`),
`privacy_budget` (default `1.0` — ε for differential privacy; lower =
more private), `redact_pii` (default `True`), `anonymize_queries`
(default `True`), and `audit_logging` (default `True`). `__init__`
calls `super().__init__(workflow=self._create_workflow(), name=name)` so
the assembled `Workflow` becomes the node's executable body.
`_create_workflow()` returns a `Workflow` built via `WorkflowBuilder`
wiring up to 7 `PythonCodeNode` instances:

| Node id                | Role                                                                                        |
| ---------------------- | ------------------------------------------------------------------------------------------- |
| `pii_detector`         | Regex-based detection + redaction of email, phone, SSN, credit-card, name, address patterns |
| `query_anonymizer`     | Generalizes specific tokens in the query (medical IDs, dates) when `anonymize_queries=True` |
| `private_rag_executor` | Runs the underlying retrieval against the redacted query                                    |
| `dp_noise_injector`    | Adds calibrated Laplace noise scaled to `privacy_budget`                                    |
| `secure_aggregator`    | Combines noised retrieval results into the final response                                   |
| `audit_logger`         | Records the pipeline trace when `audit_logging=True` (only wired in that branch)            |
| `result_formatter`     | Assembles the final dict: `results`, `privacy_report`, `audit_record`, `confidence_bounds`  |

The PII codegen template (`privacy.py:107`) and the query-anonymizer
codegen template (`privacy.py:178`) carry inner `{key}` substitutions
the framework resolves at `PythonCodeNode` runtime; the outer f-string
escapes those to `{{key}}` so it does not try to interpolate them at
class-construction time. The `audit_logger_id` is `Optional[str]` and
initialized to `None` at function entry; the `if self.audit_logging:`
branch is the only site that binds it to a real node id, and a typed
`assert audit_logger_id is not None` narrows the value before
`add_connection` reads it.

### `SecureMultiPartyRAGNode`

A `Node` subclass that runs RAG across multiple data-holding parties
without exposing raw data. The constructor accepts `name` (default
`"secure_multiparty_rag"`), `parties` (default `[]` — a list of party
names), `protocol` (default `"secret_sharing"` — accepts
`"secret_sharing"` / `"homomorphic"`), and `threshold` (default `2` —
minimum parties required to compute). `get_parameters()` declares the
query plus optional `party_data` and `computation_type` parameters.
`run()` returns a dict with `aggregate_result`, `computation_proof`,
`party_contributions` (one entry per party with `computed` + the noise
level applied), and a `fully_encrypted: True` flag.

### `ComplianceRAGNode`

A `Node` subclass that enforces consent + retention rules. The
constructor accepts `name` (default `"compliance_rag"`), `regulations`
(default `["gdpr", "ccpa"]` — also accepts `"hipaa"`, `"pipeda"`),
`default_retention_days` (default `30`), and `require_explicit_consent`
(default `True`). `get_parameters()` declares the query plus optional
`user_consent`, `jurisdiction`, and `data_classification` parameters.
`run()` returns `results`, `compliance_report`, `retention_policy` (the
declared retention window), and `user_rights` (the set of rights the
configured regulations grant — deletion, access, portability,
rectification, restriction).

### A3-triage R4 LEAK disposition

The B9a shard fixed 4 single-brace f-string LEAKs that previously broke
`PrivacyPreservingRAGNode._create_workflow()` with a NameError on the
inner codegen-template variables. The fix doubles the braces in the
outer f-string so the runtime substitution survives:

| Source line      | Inner variable         |
| ---------------- | ---------------------- |
| `privacy.py:152` | `{{hash_value}}`       |
| `privacy.py:152` | `{{pii_type.upper()}}` |
| `privacy.py:221` | `{{pattern}}`          |
| `privacy.py:221` | `{{replacement}}`      |

With those 4 escapes, `PrivacyPreservingRAGNode()` constructs cleanly
under the smoke test; the prior `xfail(strict=True)` mark was removed in
the same shard (B9a).


## Evaluation & conversational

`kaizen.nodes.rag.evaluation` ships three classes that measure RAG
quality + benchmark performance + generate synthetic test datasets.
`kaizen.nodes.rag.conversational` ships two classes that support
multi-turn conversation with sliding-window context, optional
summarization, optional coreference resolution, optional topic tracking,
and persistent per-user long-term memory.

### `RAGEvaluationNode`

A `WorkflowNode` subclass composing a 6-node evaluation pipeline. The
constructor accepts `name` (default `"rag_evaluation"`), `metrics`
(default `["faithfulness", "relevance", "context_precision",
"answer_quality"]`), `use_reference_answers` (default `True`), and
`llm_judge_model` (default `"gpt-4"`). `__init__` calls
`super().__init__(workflow=self._create_workflow(), name=name)` so the
assembled `Workflow` becomes the node's executable body.
`_create_workflow()` returns a `Workflow` built via `WorkflowBuilder`
wiring up to 6 nodes:

| Node id                     | Role                                                                                                  |
| --------------------------- | ----------------------------------------------------------------------------------------------------- |
| `test_executor`             | `PythonCodeNode` — runs the RAG-under-test against the test_queries fixture                           |
| `faithfulness_evaluator`    | `LLMAgentNode` (model = `llm_judge_model`) — JSON-schema judge of answer-vs-context grounding         |
| `relevance_evaluator`       | `LLMAgentNode` — JSON-schema judge of query→answer relevance + completeness                           |
| `context_evaluator`         | `PythonCodeNode` — deterministic P@k / MRR / diversity / avg_relevance metric formulas                |
| `answer_quality_evaluator`  | `LLMAgentNode` (only when `use_reference_answers=True`) — generated-vs-reference quality comparison   |
| `metric_aggregator`         | `PythonCodeNode` — aggregates per-test scores into mean/median/stdev + failure analysis + overall    |

The `answer_quality_id` is `Optional[str]` and initialized to `None` at
function entry; the `if self.use_reference_answers:` branch is the only
site that binds it, and a typed `assert answer_quality_id is not None`
narrows it before `add_connection` consumes it. The `metrics` list is
interpolated into the `metric_aggregator` code template via
`{self.metrics}`, allowing downstream filtering on the configured
metric set.

### `RAGBenchmarkNode`

A `Node` subclass that benchmarks one or more RAG systems for latency,
throughput, scalability, and resource usage. The constructor accepts
`name` (default `"rag_benchmark"`), `workload_sizes` (default
`[10, 100, 1000]`), and `concurrent_users` (default `[1, 5, 10]`).
`get_parameters()` declares required `rag_systems: dict` +
`test_queries: list`, plus optional `name` / `workload_sizes` /
`concurrent_users` / `duration` (default `60`). `run()` returns a dict
carrying `benchmark_results` (per-system latency profiles with p50/p95/
p99/mean/std_dev, throughput curves, scalability analysis, resource
usage), `comparison` (`fastest_system` / `most_scalable` /
`most_efficient` picks + recommendations), and `test_configuration`
(echo of the constructor + invocation kwargs). The comparison picks
use typed-lambda key functions (`min/max(..., key=lambda k: d[k])`)
to satisfy pyright on the dict-value-lookup overload.

### `TestDatasetGeneratorNode`

A `Node` subclass that generates synthetic test datasets for RAG
evaluation. The constructor accepts `name` (default
`"test_dataset_generator"`), `categories` (default
`["factual", "analytical", "comparative"]`), and `include_adversarial`
(default `True`). `get_parameters()` declares required `num_samples:
int` + optional `name` / `categories` / `include_adversarial` /
`domain` (default `"general"`) / `seed`. `run()` returns
`test_dataset` (list of `{id, query, reference_answer, contexts,
metadata}` entries, with 3 contexts per non-adversarial entry at
relevance 0.9 / 0.8 / 0.7), `statistics` (total_samples,
category_distribution, adversarial_count), and `generation_config`
(domain, categories, seed echo). The seeded RNG path makes the
output deterministic for reproducible test-suite fixtures.

### `ConversationalRAGNode`

A `WorkflowNode` subclass that composes a multi-turn conversation
pipeline with up to 8 inner nodes. The constructor accepts `name`
(default `"conversational_rag"`), `max_context_turns` (default `10` —
sliding-window size), `enable_summarization` (default `True`),
`personalization_enabled` (default `True`), `coreference_resolution`
(default `True`), and `topic_tracking` (default `True`).
`_create_workflow()` returns a `Workflow` built via `WorkflowBuilder`
wiring up to 8 nodes:

| Node id                | Role                                                                                                    |
| ---------------------- | ------------------------------------------------------------------------------------------------------- |
| `context_loader`       | `PythonCodeNode` — loads the per-session sliding-window context from the in-memory sessions store        |
| `coreference_resolver` | `LLMAgentNode` (only when `coreference_resolution=True`) — resolves pronouns against conversation context |
| `topic_tracker`        | `PythonCodeNode` (only when `topic_tracking=True`) — classifies topic + detects switches                  |
| `context_retriever`    | `PythonCodeNode` — boosts retrieval scores for topic-relevant + context-relevant documents                |
| `response_generator`   | `LLMAgentNode` — generates the contextual response                                                       |
| `context_summarizer`   | `LLMAgentNode` (only when `enable_summarization=True`) — summarizes the conversation for long-context use |
| `session_updater`      | `PythonCodeNode` — appends the new turn + updates current_topic + computes conversation health metrics    |
| `result_formatter`     | `PythonCodeNode` — assembles the final dict: `conversational_response`, `session_state`, `topic_info`     |

The three optional-branch IDs (`coreference_resolver_id`,
`topic_tracker_id`, `summarizer_id`) are `Optional[str]` and
initialized to `None` at function entry; their `if self.X:` branches
are the only sites that bind them, and typed `assert X is not None`
narrows each before `add_connection` consumes it. The
`max_context_turns` kwarg is interpolated into the `context_loader`
code template's sliding-window slice (`session["turns"][-N:]`).

`create_session(user_id: Optional[str] = None)` produces a new
session id (sha256 of `{user_id or 'anonymous'}_{datetime.now()}` →
first 16 hex chars) and registers a session record in the in-memory
`self.sessions` store. Different calls at different timestamps
produce different ids even for the same `user_id`.

### `ConversationMemoryNode`

A `Node` subclass that manages per-user long-term memory across
sessions. The constructor accepts `name` (default
`"conversation_memory"`), `memory_types` (default
`["episodic", "semantic", "preferences"]`), `retention_policy`
(default `"adaptive"`), and `max_memories_per_user` (default `1000`).
`get_parameters()` declares required `operation: str` +
`user_id: str`, plus optional `name` / `memory_types` /
`retention_policy` / `max_memories_per_user` / `data: dict` /
`context: str`. `run()` dispatches on `operation`:

| Operation  | Effect                                                                                                                    |
| ---------- | ------------------------------------------------------------------------------------------------------------------------- |
| `store`    | Appends episodic memories + sets/updates semantic facts + updates preferences (per the `memory_types` set)                |
| `retrieve` | Returns `relevant_memories` (matched by topic / fact-key overlap with `context`) + `memory_summary` + `personalization_hints` |
| `update`   | Updates existing semantic facts + preferences in-place; raises a typed error if the user has no prior memories             |
| `forget`   | Wipes specific memory types OR `forget_all=True` clears the user slate entirely (GDPR-compliant erasure)                   |
| Other      | Returns `{"error": f"Unknown operation: {operation}"}`                                                                    |

The per-user memory slot is typed `Dict[str, Dict[str, Any]]` — the
slot's `episodic` key carries a `deque(maxlen=max_memories_per_user)`,
`semantic` carries a fact-key→fact-record dict, and `preferences`
carries a free-form dict. The `defaultdict` factory creates each
user's slot lazily on first access. The store is in-memory by
design (the docstring notes "use persistent DB in production"); the
F8 B9b Tier-2a tests demonstrate the **read-back contract** through
this in-memory path AND demonstrate the **real aiosqlite persistence
pattern** via the kailash `AsyncSQLitePool` SDK pool primitive
(`tests/integration/rag/test_conversational_nodes.py::TestAiosqliteRoundTripViaPool`).

### A3-triage R3-L2 disposition

The B9b shard removed a dead `# from ..data.cache import CacheNode`
comment at `conversational.py:26`. The relative-import path
`..data.cache` never existed in the kaizen package tree (the comment
dates from the 2026-03-11 monorepo move); dead commented-out import
is dead code per `rules/zero-tolerance.md` Rule 2. The matching
dead comment at `optimized.py:21` belongs to B9c, not B9b.
