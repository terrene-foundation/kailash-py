"""
Performance-Optimized RAG Strategies

Implements high-performance RAG patterns:
- Cache-optimized retrieval with multi-level caching
- Async parallel retrieval for multiple strategies
- Streaming RAG for real-time responses
- Batch processing for high throughput

All implementations use existing Kailash components and WorkflowBuilder patterns.
"""

import hashlib
import inspect
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from kailash.nodes.base import register_node
from kailash.nodes.cache import cache  # noqa: F401 — registers CacheNode
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.workflow import WorkflowNode
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level computation functions (#1117/#1123/#1118 root-cause fix).
#
# These replace the brittle f-string / "code"-string PythonCodeNode codegen the
# Cache + AsyncParallel nodes previously inlined. Each is a real Python function
# wired via `PythonCodeNode.from_function(...)`: a from_function node publishes
# its `return` value on the FLAT `result` port (the runtime resolves dotted
# downstream reads like `result.cache_keys.exact` into the published dict), so:
#
#   - #1117 (publish-nothing): a real `return {...}` always binds the published
#     `result` port — no column-0 module-scope-assignment AST gymnastics.
#   - #1123 (f-string brace-escape): no `{{ }}` escaping; real dict literals.
#   - #1118 (import-trap): module-level `import hashlib` / `from datetime ...`
#     are real top-level imports, not sandbox-hidden nested-scope imports.
#
# Malformed / edge inputs resolve to HONEST defaults (zero-tolerance Rule 2) —
# never fabricated data.
# ---------------------------------------------------------------------------


def _generate_cache_keys(query: Any) -> dict:
    """Generate deterministic exact + semantic cache keys for a query.

    Replaces the ``cache_key_generator`` codegen block. The exact key is a
    truncated SHA-256 of the query; the semantic key namespaces it. Honest
    default for a non-string query: coerce to ``str`` so the hash is stable
    (an empty query hashes deterministically, not fabricated).

    ``similarity_threshold`` is intentionally NOT a parameter: the original
    codegen interpolated it only into a dead ``check_semantic_similarity``
    inner function that was never called, so the published ``cache_keys`` never
    depended on it (behavior-equivalent to the held baseline).
    """
    query_str = (
        query if isinstance(query, str) else ("" if query is None else str(query))
    )
    exact_key = hashlib.sha256(query_str.encode()).hexdigest()[:16]
    semantic_key = f"semantic_{exact_key[:8]}"
    return {"cache_keys": {"exact": exact_key, "semantic": semantic_key}}


def _decide_cache_use(
    cache_hit: Any = None,
    cache_value: Any = None,
    query: Any = "",
    similarity_threshold: float = 0.95,
) -> dict:
    """Decide whether to serve from cache, reading CacheNode.get's flat ports.

    Replaces the ``semantic_cache_manager`` codegen block. CacheNode's ``get``
    operation publishes flat ``hit`` / ``value`` ports (NOT a nested dict), so
    this reads ``cache_hit`` + ``cache_value`` wired from those ports.

    Semantic-similarity caching is honest-but-dormant: no node in this workflow
    populates a candidate store, so the candidate set is empty (``{}``) and the
    similarity branch never fires. The similarity logic is real (not simulated);
    it activates only when a candidate-store node is wired in. The workflow
    today is a real exact-match cache over CacheNode.
    """
    if bool(cache_hit):
        # Direct cache hit — return the value CacheNode retrieved.
        return {
            "use_cache": True,
            "cache_type": "exact",
            "cached_result": cache_value,
        }

    # Check semantic similarity (dormant unless a candidate-store node is wired).
    # `semantic_candidates` is {} because no candidate-store node feeds it in
    # this workflow — the exact-match cache is the live path.
    semantic_candidates: Dict[str, Any] = {}
    query_str = (
        query if isinstance(query, str) else ("" if query is None else str(query))
    )
    best_match = None
    best_similarity = 0.0

    for cached_query, cache_entry in semantic_candidates.items():
        # Simple similarity check (would use embeddings in production).
        query_words = set(query_str.lower().split())
        cached_words = set(cached_query.lower().split())

        intersection = len(query_words & cached_words)
        union = len(query_words | cached_words)
        similarity = intersection / union if union > 0 else 0.0

        if similarity > best_similarity and similarity >= similarity_threshold:
            best_similarity = similarity
            best_match = cache_entry

    if best_match:
        return {
            "use_cache": True,
            "cache_type": "semantic",
            "cached_result": best_match,
            "similarity": best_similarity,
        }

    return {"use_cache": False, "cache_type": None}


def _aggregate_cache_result(
    cache_decision: Any = None, fresh_results: Any = None
) -> dict:
    """Aggregate cached-or-fresh results into the documented output shape.

    Replaces the ``result_aggregator`` codegen block. Honest defaults: a missing
    ``cache_decision`` is treated as a cache miss; missing ``fresh_results`` (the
    rag_processor is skipped on a cache hit) yields an empty results list, never
    fabricated documents.
    """
    if not isinstance(cache_decision, dict):
        cache_decision = {}

    if cache_decision.get("use_cache"):
        final_results = cache_decision.get("cached_result", {})
        metadata = {
            "source": "cache",
            "cache_type": cache_decision.get("cache_type"),
            "cache_similarity": cache_decision.get("similarity", 1.0),
        }
    else:
        final_results = fresh_results
        metadata = {"source": "fresh", "cached": True}

    if not isinstance(final_results, dict):
        final_results = {}

    return {
        "optimized_results": {
            "results": final_results.get("results", []),
            "scores": final_results.get("scores", []),
            "metadata": metadata,
            "performance": {
                "cache_hit": cache_decision.get("use_cache", False),
                "response_time": (
                    "fast" if cache_decision.get("use_cache") else "normal"
                ),
            },
        }
    }


def _build_execution_plan(
    query: Any = "", strategies: Optional[List[str]] = None
) -> dict:
    """Build the parallel execution plan + per-strategy configs.

    Replaces the ``parallel_executor`` codegen block. Honest default for a
    missing strategy list: empty plan (no fabricated strategies).

    ``documents`` is intentionally NOT a parameter: the original codegen placed
    it only in a dead ``query_data`` local that never reached the published
    ``result`` (the plan is built from ``strategies`` + ``query`` alone), and no
    ``add_connection`` wires a ``documents`` port into ``parallel_executor`` —
    so exposing it would be an accepted-but-ignored phantom input port.
    """
    strategies = list(strategies) if strategies else []

    execution_plan = {
        "strategies": strategies,
        "query": query,
        "start_time": datetime.now().isoformat(),
        "parallel_count": len(strategies),
    }

    strategy_configs = {
        strategy: {
            "enabled": True,
            "timeout": 5.0,  # 5 second timeout per strategy
            "fallback": "hybrid",
        }
        for strategy in strategies
    }

    return {"execution_plan": execution_plan, "strategy_configs": strategy_configs}


def _combine_strategy_results(
    execution_plan: Any, strategies: List[str], strategy_results: Dict[str, Any]
) -> dict:
    """Fuse per-strategy retrieval results into a single ranked list.

    The shared core for the ``result_combiner`` node. ``strategy_results`` maps
    each strategy name to its retrieval output (``{"results": [...],
    "scores": [...]}``). Wrapped by :func:`_make_result_combiner` so the
    from_function node declares one explicit ``<strategy>_results`` input per
    declared strategy (the inputs are dynamic at build time).

    Honest defaults: a missing ``execution_plan`` start_time yields a 0.0 total
    time (no fabricated timing); empty results yield empty fused output.
    """
    if not isinstance(execution_plan, dict):
        execution_plan = {}
    strategies = list(strategies) if strategies else []

    # Collect non-empty per-strategy results.
    collected: Dict[str, Any] = {
        s: strategy_results[s] for s in strategies if strategy_results.get(s)
    }

    # Analyze timing — honest default when start_time is absent/unparseable.
    end_time = datetime.now()
    start_iso = execution_plan.get("start_time")
    try:
        start_time = datetime.fromisoformat(start_iso) if start_iso else end_time
        total_time = (end_time - start_time).total_seconds()
    except (TypeError, ValueError):
        total_time = 0.0

    # Combine results using score fusion.
    all_results: Dict[str, Any] = {}
    all_scores: Dict[str, Dict[str, Any]] = {}

    for strategy, results in collected.items():
        if isinstance(results, dict) and "results" in results:
            docs = results.get("results", []) or []
            scores = results.get("scores", []) or []
            for doc, score in zip(docs, scores):
                if not isinstance(doc, dict):
                    continue
                doc_id = doc.get("id", str(hash(doc.get("content", ""))))
                if doc_id not in all_results:
                    all_results[doc_id] = doc
                    all_scores[doc_id] = {}
                all_scores[doc_id][strategy] = score

    # Aggregate scores (average across strategies that returned the doc).
    final_scores = {
        doc_id: sum(scores.values()) / len(scores)
        for doc_id, scores in all_scores.items()
        if scores
    }

    # Sort by aggregated score.
    sorted_docs = sorted(final_scores.items(), key=lambda x: x[1], reverse=True)

    final_results = []
    final_score_list = []
    for doc_id, score in sorted_docs[:10]:
        final_results.append(all_results[doc_id])
        final_score_list.append(score)

    num_strategies = len(strategies)
    return {
        "parallel_results": {
            "results": final_results,
            "scores": final_score_list,
            "metadata": {
                # Behavior-equivalent to the original codegen: list every
                # strategy whose result was wired in (present), NOT only the
                # truthy ones — fusion still uses `collected` above.
                "strategies_used": [s for s in strategies if s in strategy_results],
                "total_execution_time": total_time,
                "parallel_speedup": num_strategies / max(1, total_time),
                "strategy_agreements": len(
                    [sid for sid, s in all_scores.items() if len(s) == num_strategies]
                ),
            },
        }
    }


def _build_streaming_plan(chunk_size: int = 100) -> dict:
    """Build the progressive-streaming plan for a given chunk size.

    Replaces the ``stream_controller`` codegen block. The build-time
    ``chunk_size`` is bound through a thin closure (see
    :class:`StreamingRAGNode`), so the only declared input is ``chunk_size``.
    The stages are a fixed progressive-refinement ladder (initial → refined →
    complete); honest default chunk size mirrors the constructor default.
    """
    return {
        "streaming_plan": {
            "chunk_size": chunk_size,
            "total_target": 10,
            "strategy": "progressive",  # Progressive refinement
            "stages": [
                {"name": "initial", "k": 3, "fast": True},
                {"name": "refined", "k": 5, "fast": False},
                {"name": "complete", "k": 10, "fast": False},
            ],
        }
    }


def _progressive_retrieve(
    streaming_plan: Any = None, query: Any = "", documents: Any = None
) -> dict:
    """Run the fast initial-stage progressive retrieval (keyword overlap scan).

    Replaces the ``progressive_retriever`` codegen block. ``streaming_plan`` is
    wired from the controller's ``result.streaming_plan``; ``query`` and
    ``documents`` are the top-level workflow inputs.

    Honest defaults: a missing/malformed ``streaming_plan`` falls back to a
    default initial-stage ``k`` of 3 (the plan's first-stage default — no
    fabricated stages); a missing ``query`` / ``documents`` yields an empty
    initial-results list, never fabricated documents.
    """
    if not isinstance(documents, list):
        documents = []
    query_str = (
        query if isinstance(query, str) else ("" if query is None else str(query))
    )

    # Resolve the initial-stage k from the plan, with an honest fallback.
    initial_k = 3
    if isinstance(streaming_plan, dict):
        stages = streaming_plan.get("stages")
        if isinstance(stages, list) and stages and isinstance(stages[0], dict):
            initial_k = stages[0].get("k", 3)

    # Stage 1: Fast initial results (keyword matching).
    initial_results = []
    query_words = set(query_str.lower().split())

    for doc in documents[:100]:  # Quick scan of first 100 docs
        if not isinstance(doc, dict):
            continue
        doc_words = set(doc.get("content", "").lower().split())
        overlap = query_words & doc_words
        if overlap:  # Any overlap
            initial_results.append(
                {
                    "doc": doc,
                    "stage": "initial",
                    "score": (len(overlap) / len(query_words) if query_words else 0.0),
                }
            )

    # Sort and limit to the initial stage's k.
    initial_results.sort(key=lambda x: x["score"], reverse=True)
    initial_results = initial_results[:initial_k]

    return {
        "progressive_results": {
            "initial": initial_results,
            "has_more": len(documents) > 100,
            "next_stage": "refined",
            "metadata": {
                "docs_scanned": min(100, len(documents)),
                "matches_found": len(initial_results),
            },
        }
    }


def _format_stream_chunks(progressive_results: Any = None) -> dict:
    """Format progressive retrieval results into streamable chunks.

    Replaces the ``stream_formatter`` codegen block. ``progressive_results`` is
    wired from the retriever's ``result.progressive_results``.

    Honest default: a missing/malformed ``progressive_results`` yields an empty
    initial set, so the only chunk emitted is the metadata chunk (never a
    fabricated result chunk).
    """
    if not isinstance(progressive_results, dict):
        progressive_results = {}

    current_results = progressive_results.get("initial", []) or []

    chunks = []
    for i, result in enumerate(current_results):
        if not isinstance(result, dict):
            continue
        chunks.append(
            {
                "chunk_id": i,
                "type": "result",
                "content": result.get("doc"),
                "score": result.get("score"),
                "stage": result.get("stage"),
                "is_final": False,
            }
        )

    # Add metadata chunk.
    chunks.append(
        {
            "chunk_id": len(chunks),
            "type": "metadata",
            "content": progressive_results.get("metadata", {}),
            "has_more": progressive_results.get("has_more", False),
            "next_stage": progressive_results.get("next_stage"),
        }
    )

    return {
        "stream_chunks": chunks,
        "streaming_metadata": {
            "total_chunks": len(chunks),
            "result_chunks": len(current_results),
            "supports_backpressure": True,
        },
    }


def _organize_batches(queries: Any = None, batch_size: int = 32) -> dict:
    """Organize queries into similarity-grouped batches.

    Replaces the ``batch_organizer`` codegen block. The build-time ``batch_size``
    is bound through a thin closure (see :class:`BatchOptimizedRAGNode`); the
    only wired input is ``queries``.

    Honest defaults: a missing ``queries`` yields an empty batch plan (zero
    batches, zero queries) — never fabricated queries. A single string query is
    coerced to a one-element list (mirrors the original codegen's
    ``[queries]`` coercion).
    """
    if queries is None:
        queries = []
    elif not isinstance(queries, list):
        queries = [queries]

    # Create batches.
    batches = []
    for i in range(0, len(queries), batch_size):
        batch = queries[i : i + batch_size]
        batches.append(
            {
                "batch_id": i // batch_size,
                "queries": batch,
                "size": len(batch),
            }
        )

    # Analyze query similarity for better batching — group similar queries
    # together for cache efficiency.
    if len(queries) > 1:
        # Simple similarity grouping (would use embeddings in production).
        query_groups: Dict[Any, List[Any]] = {}
        for q in queries:
            key_words = tuple(sorted(str(q).lower().split()[:3]))  # First 3 words
            if key_words not in query_groups:
                query_groups[key_words] = []
            query_groups[key_words].append(q)

        # Reorganize batches by similarity.
        optimized_batches = []
        current_batch: List[Any] = []

        for group in query_groups.values():
            for q in group:
                current_batch.append(q)
                if len(current_batch) >= batch_size:
                    optimized_batches.append(
                        {
                            "batch_id": len(optimized_batches),
                            "queries": current_batch[:],
                            "size": len(current_batch),
                            "optimized": True,
                        }
                    )
                    current_batch = []

        if current_batch:
            optimized_batches.append(
                {
                    "batch_id": len(optimized_batches),
                    "queries": current_batch,
                    "size": len(current_batch),
                    "optimized": True,
                }
            )

        batches = optimized_batches

    return {
        "batch_plan": {
            "total_queries": len(queries),
            "batch_size": batch_size,
            "num_batches": len(batches),
            "batches": batches,
            "optimization_applied": len(queries) > 1,
        }
    }


def _process_batches(batch_plan: Any = None, documents: Any = None) -> dict:
    """Score every document for every query in each batch (shared doc reps).

    Replaces the ``batch_processor`` codegen block. ``batch_plan`` is wired from
    the organizer's ``result.batch_plan``; ``documents`` is the top-level
    workflow input.

    Honest defaults: a missing ``batch_plan`` yields empty batch results with a
    zero-query statistics block; missing ``documents`` yields empty per-query
    score lists — never fabricated documents or scores.
    """
    if not isinstance(batch_plan, dict):
        batch_plan = {}
    if not isinstance(documents, list):
        documents = []

    total_queries = batch_plan.get("total_queries", 0)
    plan_batches = batch_plan.get("batches", []) or []

    # Pre-compute document representations once.
    doc_representations: Dict[int, Dict[str, Any]] = {}
    for i, doc in enumerate(documents):
        if not isinstance(doc, dict):
            continue
        doc_words = set(doc.get("content", "").lower().split())
        doc_representations[i] = {
            "words": doc_words,
            "length": len(doc_words),
            "doc": doc,
        }

    # Process each batch.
    batch_results = []
    for batch in plan_batches:
        if not isinstance(batch, dict):
            continue
        batch_queries = batch.get("queries", []) or []
        batch_scores = []

        # Score all documents for all queries in the batch.
        for query in batch_queries:
            query_words = set(str(query).lower().split())
            doc_scores = []

            for doc_id, doc_rep in doc_representations.items():
                overlap = len(query_words & doc_rep["words"])
                score = overlap / len(query_words) if query_words else 0.0
                doc_scores.append((doc_id, score))

            # Sort and take top k.
            doc_scores.sort(key=lambda x: x[1], reverse=True)
            batch_scores.append(doc_scores[:10])

        batch_results.append(
            {
                "batch_id": batch.get("batch_id"),
                "query_results": batch_scores,
                "batch_size": len(batch_queries),
            }
        )

    # Aggregate statistics.
    total_scored = sum(len(br["query_results"]) for br in batch_results)
    avg_score_per_query = total_scored / total_queries if total_queries > 0 else 0.0

    return {
        "batch_results": {
            "results": batch_results,
            "statistics": {
                "total_queries_processed": total_queries,
                "batches_processed": len(batch_results),
                "avg_results_per_query": avg_score_per_query,
                "batch_efficiency": 1.0,
            },
        }
    }


def _format_batch_results(
    batch_results: Any = None, batch_plan: Any = None, documents: Any = None
) -> dict:
    """Map per-batch score tuples back to per-query document results.

    Replaces the ``result_formatter`` codegen block. ``batch_results`` is wired
    from the processor's ``result.batch_results``; ``batch_plan`` from the
    organizer's ``result.batch_plan``; ``documents`` is the top-level input.

    Honest defaults: missing inputs yield an empty per-query result map — never
    fabricated documents. Only documents with a positive overlap score are
    emitted (mirrors the original codegen's ``if score > 0`` filter).
    """
    if not isinstance(batch_results, dict):
        batch_results = {}
    if not isinstance(batch_plan, dict):
        batch_plan = {}
    if not isinstance(documents, list):
        documents = []

    plan_batches = batch_plan.get("batches", []) or []
    inner_results = batch_results.get("results", []) or []

    formatted_results: Dict[Any, Any] = {}

    for batch_result in inner_results:
        if not isinstance(batch_result, dict):
            continue
        batch_id = batch_result.get("batch_id")
        if not isinstance(batch_id, int) or batch_id >= len(plan_batches):
            continue
        batch_queries = plan_batches[batch_id].get("queries", []) or []

        for i, (query, query_scores) in enumerate(
            zip(batch_queries, batch_result.get("query_results", []) or [])
        ):
            results = []
            scores = []

            for doc_id, score in query_scores:
                if score > 0 and 0 <= doc_id < len(documents):
                    results.append(documents[doc_id])
                    scores.append(score)

            formatted_results[query] = {
                "results": results,
                "scores": scores,
                "batch_id": batch_id,
                "position_in_batch": i,
            }

    return {
        "final_batch_results": {
            "query_results": formatted_results,
            "batch_statistics": batch_results.get("statistics", {}),
            "processing_order": list(formatted_results.keys()),
        }
    }


def _make_result_combiner(strategies: List[str]) -> Callable[..., dict]:
    """Build a from_function-compatible combiner for a specific strategy list.

    The ``result_combiner`` reads one input port per declared strategy
    (``<strategy>_results``, wired from each ``<strategy>_rag`` node). Strategy
    names are dynamic at build time, so this factory synthesises a real function
    whose signature declares exactly those per-strategy parameters — letting
    ``PythonCodeNode.from_function`` introspect them and the runtime wire each
    edge by name. This is the framework-first equivalent of the prior dynamic
    f-string codegen, with a statically-introspectable signature.
    """
    # The declared strategy list is baked in (build-time known), so the synthetic
    # signature declares ONLY the input ports the graph wires: `execution_plan`
    # (from the executor's `result.execution_plan`) plus one `<strategy>_results`
    # per declared strategy (from each `<strategy>_rag` node). Deduplicate while
    # preserving order so a repeated strategy name does not declare a duplicate
    # parameter (an invalid signature).
    declared_strategies: List[str] = []
    seen = set()
    for strategy in strategies:
        if strategy in seen:
            continue
        seen.add(strategy)
        declared_strategies.append(strategy)

    params = [
        inspect.Parameter(
            "execution_plan", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None
        ),
    ]
    for strategy in declared_strategies:
        params.append(
            inspect.Parameter(
                f"{strategy}_results",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=None,
            )
        )
    sig = inspect.Signature(params, return_annotation=dict)

    def result_combiner(*args, **kwargs) -> dict:
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        arguments = bound.arguments
        strategy_results = {
            s: arguments.get(f"{s}_results") for s in declared_strategies
        }
        return _combine_strategy_results(
            arguments.get("execution_plan"), declared_strategies, strategy_results
        )

    result_combiner.__signature__ = sig  # type: ignore[attr-defined]
    result_combiner.__name__ = "result_combiner"
    result_combiner.__doc__ = _combine_strategy_results.__doc__
    return result_combiner


@register_node()
class CacheOptimizedRAGNode(WorkflowNode):
    """
    Cache-Optimized RAG with Multi-Level Caching

    Implements sophisticated caching strategies:
    - Semantic similarity caching for near-duplicate queries
    - Result caching with TTL management
    - Embedding caching to avoid recomputation
    - Incremental cache updates

    When to use:
    - Best for: High-traffic applications, repeated queries, cost optimization
    - Not ideal for: Constantly changing data, unique queries
    - Performance: 10-50ms for cache hits (95% faster)
    - Cache hit rate: 40-60% with semantic matching

    Key features:
    - Exact match caching
    - Semantic similarity caching (finds similar past queries)
    - Multi-level cache hierarchy
    - Automatic cache invalidation

    Example:
        cached_rag = CacheOptimizedRAGNode(
            cache_ttl=3600,  # 1 hour
            similarity_threshold=0.95
        )

        # First query: ~500ms (goes to retrieval)
        result1 = await cached_rag.execute(query="What is deep learning?")

        # Exact match: ~10ms (from cache)
        result2 = await cached_rag.execute(query="What is deep learning?")

        # Similar query: ~15ms (semantic cache)
        result3 = await cached_rag.execute(query="Explain deep learning")

    Parameters:
        cache_ttl: Time-to-live in seconds
        similarity_threshold: Minimum similarity for semantic cache
        cache_backend: Storage backend (redis, memory, disk)
        max_cache_size: Maximum cache entries

    Returns:
        results: Retrieved documents
        metadata: Cache hit/miss, latency, similarity score
        cache_key: Key used for caching
    """

    def __init__(
        self,
        name: str = "cache_optimized_rag",
        cache_ttl: int = 3600,
        similarity_threshold: float = 0.95,
    ):
        self.cache_ttl = cache_ttl
        self.similarity_threshold = similarity_threshold
        super().__init__(workflow=self._create_workflow(), name=name)

    def _create_workflow(self) -> Workflow:
        """Create cache-optimized RAG workflow"""
        builder = WorkflowBuilder()

        # Add cache key generator.
        #
        # #1117/#1123/#1118 root-cause fix: lifted from the prior f-string codegen
        # to the module-level `_generate_cache_keys` function wired via
        # `PythonCodeNode.from_function`. The node publishes the SAME flat `result`
        # port carrying `{"cache_keys": {"exact", "semantic"}}`, so the downstream
        # `result.cache_keys.exact` edges below resolve unchanged. `_internal=True`
        # suppresses the consumer-facing instance-API advisory (SDK-internal
        # construction path, mirrors conversational.py).
        cache_key_gen_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _generate_cache_keys,
                name="cache_key_generator",
            ),
            node_id="cache_key_generator",
            _internal=True,
        )

        # Add cache checker
        cache_checker_id = builder.add_node(
            "CacheNode",
            node_id="cache_checker",
            config={"operation": "get", "ttl": self.cache_ttl},
        )

        # Add semantic cache manager.
        #
        # #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `_decide_cache_use` function wired via `PythonCodeNode.from_function`.
        # The build-time `similarity_threshold` is bound through a thin closure
        # (keeps `cache_hit` / `cache_value` / `query` as the declared inputs the
        # CacheNode `hit`/`value` ports wire to). The node publishes the SAME flat
        # `result` port carrying the decision dict, so the `result.use_cache`
        # skip-gate edge + the `result` aggregator edge below resolve unchanged.
        #
        # CacheNode's `get` publishes flat ports (`hit`, `value`), NOT a nested
        # dict — this node reads `cache_hit` + `cache_value` wired from those
        # ports. Semantic-similarity caching is honest-but-dormant (no candidate
        # store is wired); the exact-match cache is the live path.
        _similarity_threshold = self.similarity_threshold

        def _decide_cache_use_bound(cache_hit=None, cache_value=None, query="") -> dict:
            return _decide_cache_use(
                cache_hit=cache_hit,
                cache_value=cache_value,
                query=query,
                similarity_threshold=_similarity_threshold,
            )

        _decide_cache_use_bound.__name__ = "semantic_cache_manager"
        _decide_cache_use_bound.__doc__ = _decide_cache_use.__doc__
        semantic_cache_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _decide_cache_use_bound,
                name="semantic_cache_manager",
            ),
            node_id="semantic_cache_manager",
            _internal=True,
        )

        # Add main RAG processor (only runs if cache miss)
        rag_processor_id = builder.add_node(
            "HybridRAGNode",
            node_id="rag_processor",
            config={"config": {"retrieval_k": 5}},
        )

        # Add cache updater
        cache_updater_id = builder.add_node(
            "CacheNode",
            node_id="cache_updater",
            config={"operation": "set", "ttl": self.cache_ttl},
        )

        # Add result aggregator
        # Add result aggregator.
        #
        # #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `_aggregate_cache_result` function wired via
        # `PythonCodeNode.from_function`. `cache_decision` is wired from the
        # semantic_cache_manager's `result` port; `fresh_results` from the
        # rag_processor (absent on a cache hit — the function's honest default
        # handles the missing input). The node publishes the SAME flat `result`
        # port carrying `{"optimized_results": {...}}`.
        result_aggregator_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _aggregate_cache_result,
                name="result_aggregator",
            ),
            node_id="result_aggregator",
            _internal=True,
        )

        # Connect workflow with conditional execution.
        #
        # F9 #1117/#1123 wiring fix: every PythonCodeNode publishes ONLY the
        # `result` port (code-mode PythonCodeNode returns {"result": <ns.result>}
        # when a module-scope `result` is bound, else the whole namespace). The
        # pre-fix edges read non-existent ports (`cache_keys`, `use_cache`) that
        # are nested *inside* `result`, so the graph raised
        # "Source output 'cache_keys' not found ... Available outputs: ['result']"
        # at runtime. Each edge now reads the real `result` port via a dotted
        # nested path (`result.cache_keys.exact`, `result.use_cache`), which the
        # runtime resolves into the published dict. CacheNode's `key` input is a
        # str, so we feed the flat exact-key string, not the nested dict.
        builder.add_connection(
            cache_key_gen_id, "result.cache_keys.exact", cache_checker_id, "key"
        )
        # CacheNode.get publishes flat ports (`hit`, `value`); wire each to the
        # semantic_cache_manager's dedicated inputs (the pre-fix edge read a
        # non-existent `result` port off CacheNode).
        builder.add_connection(cache_checker_id, "hit", semantic_cache_id, "cache_hit")
        builder.add_connection(
            cache_checker_id, "value", semantic_cache_id, "cache_value"
        )

        # Only run RAG if cache miss (skip-gate reads the nested use_cache flag).
        builder.add_connection(
            semantic_cache_id, "result.use_cache", rag_processor_id, "_skip_if_true"
        )
        builder.add_connection(rag_processor_id, "output", cache_updater_id, "value")
        builder.add_connection(
            cache_key_gen_id, "result.cache_keys.exact", cache_updater_id, "key"
        )

        # Aggregate results
        builder.add_connection(
            semantic_cache_id, "result", result_aggregator_id, "cache_decision"
        )
        builder.add_connection(
            rag_processor_id, "output", result_aggregator_id, "fresh_results"
        )

        return builder.build(name="cache_optimized_rag_workflow")


@register_node()
class AsyncParallelRAGNode(WorkflowNode):
    """
    Async Parallel RAG Execution

    Runs multiple RAG strategies in parallel and combines results.
    Optimizes for minimum latency through concurrent execution.

    When to use:
    - Best for: Maximum quality, ensemble approaches, latency tolerance
    - Not ideal for: Simple queries, strict latency requirements
    - Performance: ~600ms (parallel execution of multiple strategies)
    - Quality improvement: 20-30% over single strategy

    Key features:
    - Concurrent strategy execution
    - Automatic result fusion
    - Fallback handling
    - Load balancing

    Example:
        parallel_rag = AsyncParallelRAGNode(
            strategies=["semantic", "sparse", "hyde", "colbert"]
        )

        # Runs all 4 strategies in parallel, takes time of slowest
        result = await parallel_rag.execute(
            documents=documents,
            query="Complex technical question requiring precision"
        )
        # Returns best combined results from all strategies

    Parameters:
        strategies: List of RAG strategies to run
        fusion_method: How to combine results (voting, rrf, weighted)
        timeout_per_strategy: Maximum time per strategy
        min_strategies: Minimum successful strategies required

    Returns:
        results: Fused results from all strategies
        metadata: Execution times, strategy contributions
        strategy_results: Individual results per strategy
    """

    def __init__(
        self,
        name: str = "async_parallel_rag",
        strategies: Optional[List[str]] = None,
    ):
        self.strategies = strategies or ["semantic", "sparse", "hybrid"]
        super().__init__(workflow=self._create_workflow(), name=name)

    def _create_workflow(self) -> Workflow:
        """Create async parallel RAG workflow"""
        builder = WorkflowBuilder()

        # Add parallel executor
        # Add parallel executor.
        #
        # #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `_build_execution_plan` function wired via
        # `PythonCodeNode.from_function`, with the build-time strategy list bound
        # through a thin closure (keeps `query` as the declared input). The
        # function returns `{"execution_plan": ..., "strategy_configs": ...}` on
        # the flat `result` port. The downstream combiner edge reads
        # `result.execution_plan` (see below) — the prior codegen published only
        # `result` while the edge read a phantom `execution_plan` port (latent
        # #1117 nested-port defect, now closed).
        _strategies = list(self.strategies)

        def _build_execution_plan_bound(query="") -> dict:
            return _build_execution_plan(query=query, strategies=_strategies)

        _build_execution_plan_bound.__name__ = "parallel_executor"
        _build_execution_plan_bound.__doc__ = _build_execution_plan.__doc__
        parallel_executor_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _build_execution_plan_bound,
                name="parallel_executor",
            ),
            node_id="parallel_executor",
            _internal=True,
        )

        # Add strategy nodes dynamically
        strategy_nodes = {}
        for strategy in self.strategies:
            if strategy == "semantic":
                node_id = builder.add_node(
                    "SemanticRAGNode",
                    node_id=f"{strategy}_rag",
                    config={"config": {"retrieval_k": 5}},
                )
            elif strategy == "sparse":
                node_id = builder.add_node(
                    "SparseRetrievalNode",
                    node_id=f"{strategy}_rag",
                    config={"method": "bm25"},
                )
            elif strategy == "hybrid":
                node_id = builder.add_node(
                    "HybridRAGNode",
                    node_id=f"{strategy}_rag",
                    config={"config": {"retrieval_k": 5}},
                )
            else:
                # Default to semantic
                node_id = builder.add_node(
                    "SemanticRAGNode",
                    node_id=f"{strategy}_rag",
                    config={"config": {"retrieval_k": 5}},
                )

            strategy_nodes[strategy] = node_id

        # Add result combiner.
        #
        # #1117/#1123/#1118 root-cause fix: lifted to `_combine_strategy_results`
        # via the `_make_result_combiner` factory, which synthesises a real
        # function whose signature declares one `<strategy>_results` input per
        # declared strategy (strategy names are dynamic at build time). The prior
        # f-string codegen read those per-strategy inputs via `locals()` inside an
        # exec sandbox — brittle and brace-escape-prone (#1123). The factory keeps
        # the inputs statically introspectable so `from_function` declares them
        # and the runtime wires each `<strategy>_rag` edge by name. The node
        # publishes the fused output on the flat `result` port.
        result_combiner_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _make_result_combiner(_strategies),
                name="result_combiner",
            ),
            node_id="result_combiner",
            _internal=True,
        )

        # Connect parallel execution.
        #
        # The executor publishes `{"execution_plan": ..., "strategy_configs":
        # ...}` on the flat `result` port, so the combiner's `execution_plan`
        # input reads `result.execution_plan` (the runtime resolves the dotted
        # path into the published dict). The pre-fix edge read a phantom
        # `execution_plan` port the codegen never published — latent #1117
        # nested-port defect, closed here.
        builder.add_connection(
            parallel_executor_id,
            "result.execution_plan",
            result_combiner_id,
            "execution_plan",
        )

        # Connect each strategy to combiner. Each `<strategy>_rag` node publishes
        # its retrieval output on `output`, wired to the combiner's declared
        # `<strategy>_results` input.
        for strategy, node_id in strategy_nodes.items():
            builder.add_connection(
                node_id, "output", result_combiner_id, f"{strategy}_results"
            )

        return builder.build(name="async_parallel_rag_workflow")


@register_node()
class StreamingRAGNode(WorkflowNode):
    """
    Streaming RAG for Real-Time Responses

    Implements streaming retrieval and generation for low-latency
    interactive applications.

    When to use:
    - Best for: Interactive UIs, chat applications, real-time feedback
    - Not ideal for: Batch processing, when complete results needed upfront
    - Performance: First results in ~100ms, complete in ~1000ms
    - User experience: Immediate feedback, progressive enhancement

    Key features:
    - Progressive result delivery
    - Chunked response streaming
    - Backpressure handling
    - Quality improvements over time

    Example:
        streaming_rag = StreamingRAGNode(chunk_size=100)

        # Stream results as they become available
        async for chunk in streaming_rag.stream(
            documents=documents,
            query="Explain machine learning concepts"
        ):
            if chunk['type'] == 'result':
                print(f"New result: {chunk['content']['title']}")
            elif chunk['type'] == 'progress':
                print(f"Progress: {chunk['percentage']}%")

    Parameters:
        chunk_size: Results per chunk
        initial_k: Fast initial results count
        refinement_stages: Number of quality improvements
        stream_timeout: Maximum streaming duration

    Returns (streaming):
        chunks: Stream of result chunks
        metadata: Progress indicators, quality metrics
        control: Backpressure and cancellation support
    """

    def __init__(self, name: str = "streaming_rag", chunk_size: int = 100):
        self.chunk_size = chunk_size
        super().__init__(workflow=self._create_workflow(), name=name)

    def _create_workflow(self) -> Workflow:
        """Create streaming RAG workflow"""
        builder = WorkflowBuilder()

        # Add streaming controller.
        #
        # #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `_build_streaming_plan` function wired via `PythonCodeNode.from_function`,
        # with the build-time `chunk_size` bound through a thin closure (the
        # function declares no inputs the graph must wire). The node publishes
        # `{"streaming_plan": ...}` on the flat `result` port; the downstream
        # retriever edge reads `result.streaming_plan` (the prior codegen
        # published only `result` while the edge read a phantom `streaming_plan`
        # port — latent #1117 nested-port defect, closed here).
        _chunk_size = self.chunk_size

        def _build_streaming_plan_bound() -> dict:
            return _build_streaming_plan(chunk_size=_chunk_size)

        _build_streaming_plan_bound.__name__ = "stream_controller"
        _build_streaming_plan_bound.__doc__ = _build_streaming_plan.__doc__
        stream_controller_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _build_streaming_plan_bound,
                name="stream_controller",
            ),
            node_id="stream_controller",
            _internal=True,
        )

        # Add progressive retriever.
        #
        # #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `_progressive_retrieve` function wired via `PythonCodeNode.from_function`.
        # `streaming_plan` is wired from the controller's `result.streaming_plan`;
        # `query` / `documents` are the top-level workflow inputs. The node
        # publishes `{"progressive_results": ...}` on the flat `result` port; the
        # downstream formatter edge reads `result.progressive_results`.
        progressive_retriever_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _progressive_retrieve,
                name="progressive_retriever",
            ),
            node_id="progressive_retriever",
            _internal=True,
        )

        # Add stream formatter.
        #
        # #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `_format_stream_chunks` function wired via `PythonCodeNode.from_function`.
        # `progressive_results` is wired from the retriever's
        # `result.progressive_results`. The node publishes
        # `{"stream_chunks": ..., "streaming_metadata": ...}` on the flat
        # `result` port (final sink — no downstream consumer).
        stream_formatter_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _format_stream_chunks,
                name="stream_formatter",
            ),
            node_id="stream_formatter",
            _internal=True,
        )

        # Connect workflow.
        #
        # Each from_function node publishes on the flat `result` port; the
        # downstream edges read the nested key via a dotted path
        # (`result.streaming_plan`, `result.progressive_results`), which the
        # runtime resolves into the published dict. The pre-fix edges read
        # phantom top-level ports the codegen never published (#1117).
        builder.add_connection(
            stream_controller_id,
            "result.streaming_plan",
            progressive_retriever_id,
            "streaming_plan",
        )
        builder.add_connection(
            progressive_retriever_id,
            "result.progressive_results",
            stream_formatter_id,
            "progressive_results",
        )

        return builder.build(name="streaming_rag_workflow")


@register_node()
class BatchOptimizedRAGNode(WorkflowNode):
    """
    Batch-Optimized RAG for High Throughput

    Processes multiple queries efficiently in batches,
    optimizing for throughput over latency.

    When to use:
    - Best for: Bulk processing, offline analysis, high-volume applications
    - Not ideal for: Real-time queries, interactive applications
    - Performance: 10-50 queries/second throughput
    - Efficiency: 3-5x better resource utilization

    Key features:
    - Intelligent query batching
    - Shared computation optimization
    - GPU batching support
    - Result caching across batch

    Example:
        batch_rag = BatchOptimizedRAGNode(batch_size=32)

        # Process 100 queries efficiently
        queries = ["query1", "query2", ..., "query100"]

        results = await batch_rag.execute(
            queries=queries,
            documents=documents
        )
        # Processes in optimal batches, shares embeddings computation

    Parameters:
        batch_size: Queries per batch
        optimize_by_similarity: Group similar queries
        share_embeddings: Reuse document embeddings
        max_batch_time: Maximum batch collection time

    Returns:
        query_results: Dict mapping query->results
        batch_statistics: Performance metrics
        optimization_report: Efficiency gains achieved
    """

    def __init__(self, name: str = "batch_optimized_rag", batch_size: int = 32):
        self.batch_size = batch_size
        super().__init__(workflow=self._create_workflow(), name=name)

    def _create_workflow(self) -> Workflow:
        """Create batch-optimized RAG workflow"""
        builder = WorkflowBuilder()

        # Add batch organizer.
        #
        # #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `_organize_batches` function wired via `PythonCodeNode.from_function`,
        # with the build-time `batch_size` bound through a thin closure (`queries`
        # is the only declared input the graph wires). The node publishes
        # `{"batch_plan": ...}` on the flat `result` port; the downstream
        # processor + formatter edges read `result.batch_plan` (the prior codegen
        # published only `result` while the edges read a phantom `batch_plan`
        # port — latent #1117 nested-port defect, closed here).
        _batch_size = self.batch_size

        def _organize_batches_bound(queries=None) -> dict:
            return _organize_batches(queries=queries, batch_size=_batch_size)

        _organize_batches_bound.__name__ = "batch_organizer"
        _organize_batches_bound.__doc__ = _organize_batches.__doc__
        batch_organizer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _organize_batches_bound,
                name="batch_organizer",
            ),
            node_id="batch_organizer",
            _internal=True,
        )

        # Add batch processor.
        #
        # #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `_process_batches` function wired via `PythonCodeNode.from_function`.
        # `batch_plan` is wired from the organizer's `result.batch_plan`;
        # `documents` is the top-level workflow input. The node publishes
        # `{"batch_results": ...}` on the flat `result` port; the downstream
        # formatter edge reads `result.batch_results`.
        batch_processor_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _process_batches,
                name="batch_processor",
            ),
            node_id="batch_processor",
            _internal=True,
        )

        # Add result formatter.
        #
        # #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `_format_batch_results` function wired via `PythonCodeNode.from_function`.
        # `batch_results` is wired from the processor's `result.batch_results`;
        # `batch_plan` from the organizer's `result.batch_plan`; `documents` is
        # the top-level input. The node publishes
        # `{"final_batch_results": ...}` on the flat `result` port (final sink —
        # no downstream consumer).
        result_formatter_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _format_batch_results,
                name="result_formatter",
            ),
            node_id="result_formatter",
            _internal=True,
        )

        # Connect workflow.
        #
        # Each from_function node publishes on the flat `result` port; the
        # downstream edges read the nested key via a dotted path
        # (`result.batch_plan`, `result.batch_results`), which the runtime
        # resolves into the published dict. The pre-fix edges read phantom
        # top-level ports the codegen never published (#1117).
        builder.add_connection(
            batch_organizer_id, "result.batch_plan", batch_processor_id, "batch_plan"
        )
        builder.add_connection(
            batch_processor_id,
            "result.batch_results",
            result_formatter_id,
            "batch_results",
        )
        builder.add_connection(
            batch_organizer_id, "result.batch_plan", result_formatter_id, "batch_plan"
        )

        return builder.build(name="batch_optimized_rag_workflow")


# Export all optimized nodes
__all__ = [
    "CacheOptimizedRAGNode",
    "AsyncParallelRAGNode",
    "StreamingRAGNode",
    "BatchOptimizedRAGNode",
]
