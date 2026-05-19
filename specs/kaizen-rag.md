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
