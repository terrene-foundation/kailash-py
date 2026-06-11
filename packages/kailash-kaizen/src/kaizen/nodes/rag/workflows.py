"""
RAG Workflow Nodes

Pre-built WorkflowNode components that combine multiple RAG strategies
and operations into reusable workflow patterns.
"""

import logging
import os
from typing import Any, Optional

from kailash.nodes.base import register_node

# PythonCodeNode is imported for BOTH its @register_node side effect (the inner
# workflows reference it by the string "PythonCodeNode") AND so the L3
# messages-composer fix below can call `PythonCodeNode.from_function(fn)`.
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.workflow import WorkflowNode
from kailash.workflow.builder import WorkflowBuilder

from .strategies import (
    RAGConfig,
    create_hierarchical_rag_workflow,
    create_hybrid_rag_workflow,
    create_semantic_rag_workflow,
    create_statistical_rag_workflow,
)

logger = logging.getLogger(__name__)


# F9 #1126: env-loaded default LLM model. Mirrors the router.py precedent
# (F8 B10). May be None when neither env var is set — that is
# env-models-compliant; do NOT fall back to a hardcoded model name.
_DEFAULT_LLM_MODEL = os.environ.get(
    "OPENAI_PROD_MODEL", os.environ.get("DEFAULT_LLM_MODEL")
)


# ---------------------------------------------------------------------------
# Messages-composer function (L3 fix — same reference template as
# conversational.py, query_processing.py, agentic.py, and graph.py).
#
# LLMAgentNode consumes context EXCLUSIVELY through its `messages` param (the
# OpenAI chat format: a list of {"role","content"} dicts) plus `system_prompt`.
# `LLMAgentNode.run` reads `messages = kwargs["messages"]`; ANY OTHER wired port
# name is read via `kwargs.get` and SILENTLY DROPPED.
#
# In AdaptiveRAGWorkflowNode the ONLY direct LLMAgentNode stage —
# `rag_strategy_analyzer` — was wired `document_preprocessor.result ->
# rag_strategy_analyzer.input`. `input` is NOT a port LLMAgentNode reads, so
# the strategy analyzer answered from its `system_prompt` alone: it never saw
# the document characteristics (count / average length / structure / technical
# signals / content types) NOR the user query it is meant to analyze to select
# the optimal RAG strategy (the L3 "LLM ignores its input" defect).
#
# The composer renders the REAL in-graph data characteristics the
# `document_preprocessor` PythonCodeNode genuinely publishes (document_count,
# avg_length, has_structure, is_technical, content_types) PLUS the real user
# query into a `messages` list wired to the VALID `messages` port. This is pure
# data rendering (the permitted output-formatting exception per
# rules/agent-reasoning.md) — NO if-else routing / keyword classification on
# content, and NO NEW deterministic agent-loop logic (the existing strategy
# routing/orchestration in workflows.py is unchanged).
#
# IN-GRAPH HONESTY (zero-tolerance Rule 2): every field rendered is a real key
# the `document_preprocessor` codegen publishes on its `result` (verified
# against the `analyze_for_llm` return dict). No input is invented.
# ---------------------------------------------------------------------------


def _coerce_text(value: Any) -> str:
    """Coerce a wired input to a clean string.

    The parameter injector delivers top-level inputs as plain strings; a wired
    upstream port may arrive None on an unwired optional branch.
    """
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return str(value).strip()


def compose_strategy_analyzer_messages(
    query="",
    document_count=0,
    avg_length=0,
    has_structure=False,
    is_technical=False,
    content_types=None,
):
    """Compose the ``messages`` list for AdaptiveRAGWorkflowNode's
    ``rag_strategy_analyzer`` LLM stage.

    Renders the REAL document characteristics the upstream
    ``document_preprocessor`` publishes (``document_count`` / ``avg_length`` /
    ``has_structure`` / ``is_technical`` / ``content_types``) AND the real user
    ``query`` into a ``messages`` list wired to the LLMAgentNode ``messages``
    port — so the analyzer selects the RAG strategy FROM the actual corpus +
    query, not from its ``system_prompt`` alone. Returns ``{"messages": [...]}``.

    Mirrors the analyzer's ``prompt_template`` field shape (Count / Average
    length / Has structure / Technical content / Content types / Query) so the
    rendered message carries exactly the inputs the ``system_prompt`` advertises
    it will reason over. Every value is a genuine in-graph
    ``document_preprocessor.result`` key — none is invented.
    """
    q = _coerce_text(query)
    types = content_types if isinstance(content_types, list) else []
    types_text = ", ".join(str(t) for t in types) if types else "none detected"
    content = (
        "Analyze these documents for optimal RAG strategy selection:\n\n"
        "Document Analysis:\n"
        f"- Count: {document_count}\n"
        f"- Average length: {avg_length} characters\n"
        f"- Has structure (headings/sections): {has_structure}\n"
        f"- Technical content detected: {is_technical}\n"
        f"- Content types: {types_text}\n\n"
        "Query (if provided): " + (q if q else "(none)") + "\n\n"
        "Recommend the optimal RAG strategy:"
    )
    return {"messages": [{"role": "user", "content": content}]}


# ---------------------------------------------------------------------------
# Strategy-decision parser (OUTPUT-side fix — same reference template as the O1
# evaluation.py response parsers `_unwrap_response_content` + `parse_*_response`).
#
# LLMAgentNode publishes its model output on the `response` port as a dict
# `{"content": "<text or JSON string>", "success": ..., "usage": ...,
# "metadata": ...}`. The `rag_strategy_analyzer` system_prompt instructs the LLM
# to emit ONLY a JSON object `{"recommended_strategy", "reasoning", "confidence",
# "fallback_strategy"}` — but that object lives as a JSON STRING inside
# `response["content"]`.
#
# The pre-shard topology wired `rag_strategy_analyzer.result -> ...` (a port
# LLMAgentNode does NOT publish) into the SwitchNode `strategy_executor`
# (condition_field `recommended_strategy`) AND the `results_aggregator`
# PythonCodeNode (reads `llm_decision.get("recommended_strategy")` etc.). Both
# consumers therefore received NOTHING — the strategy DECISION never drove the
# executor nor reached the aggregator (every field resolved to its default/None).
#
# This parser consumes the REAL `response` port, unwraps `.content`, and
# `json.loads` it into a PARSED dict the SwitchNode + aggregator can read:
# `{recommended_strategy, reasoning, confidence, fallback_strategy}` at the top
# level (so `condition_field: "recommended_strategy"` resolves against the
# from_function `result` dict).
#
# HONESTY (zero-tolerance Rule 2): on non-JSON / missing-field / malformed
# output the parser returns a TYPED parse-error sentinel
# (`{"recommended_strategy": None, "parse_error": "<reason>"}`) — NEVER a
# fabricated default like `"semantic"` (that would be the fake-dispatch /
# fake-classification failure mode). The SwitchNode `cases` allowlist
# (`["semantic","statistical","hybrid","hierarchical"]`) fails CLOSED when
# `recommended_strategy` is None (no case matches) — that is the CORRECT honest
# behavior for unparseable LLM output, NOT papered with a default case.
#
# This is tool-result PARSING (permitted deterministic logic per
# rules/agent-reasoning.md exception 6 — extracting structured data from LLM
# output), NOT agent decision-making: the LLM still makes the strategy decision;
# this function only extracts it. NO if-else strategy heuristics are added.
# ---------------------------------------------------------------------------


def parse_strategy_decision(response=None):
    """Parse the ``rag_strategy_analyzer`` ``response`` into a strategy-decision dict.

    Reads ``response`` -> ``.content`` (a JSON string) -> ``json.loads`` -> the
    ``{recommended_strategy, reasoning, confidence, fallback_strategy}`` object
    the analyzer's ``system_prompt`` instructs the LLM to emit. The parsed object
    is returned as the from_function ``result`` so the downstream SwitchNode
    (``condition_field: "recommended_strategy"``) switches on the REAL parsed
    strategy and the ``results_aggregator`` reads the REAL reasoning/confidence/
    fallback.

    Malformed / non-JSON / missing-strategy output is FLAGGED with a typed
    sentinel (``{"recommended_strategy": None, "parse_error": "<reason>"}``) —
    never a fabricated strategy (zero-tolerance Rule 2). The SwitchNode then
    fails closed (no case matches ``None``), surfacing the parse failure honestly
    rather than dispatching to an invented strategy.
    """
    import json

    content = _unwrap_response_content(response)

    # Honest empty: the analyzer published nothing parseable. Surface, don't
    # invent — the SwitchNode fails closed on a None strategy.
    if content is None or (isinstance(content, str) and not content.strip()):
        return {"recommended_strategy": None, "parse_error": "empty-response"}

    # The provider may already have emitted a parsed dict (some do).
    parsed: Any
    if isinstance(content, dict):
        parsed = content
    elif isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return {"recommended_strategy": None, "parse_error": "non-json-response"}
    else:
        return {
            "recommended_strategy": None,
            "parse_error": "unexpected-content-type",
        }

    if not isinstance(parsed, dict):
        return {"recommended_strategy": None, "parse_error": "non-object-json"}

    strategy = parsed.get("recommended_strategy")
    if not isinstance(strategy, str) or not strategy.strip():
        # Parsed JSON but the load-bearing decision field is absent/blank. FLAG,
        # don't fabricate — the SwitchNode fails closed.
        return {"recommended_strategy": None, "parse_error": "missing-strategy"}

    # Real decision: surface the strategy + its rationale fields so the SwitchNode
    # switches on the genuine strategy and the aggregator reports genuine metadata.
    return {
        "recommended_strategy": strategy,
        "reasoning": parsed.get("reasoning"),
        "confidence": parsed.get("confidence"),
        "fallback_strategy": parsed.get("fallback_strategy"),
    }


def _unwrap_response_content(response: Any) -> Any:
    """Unwrap the LLMAgentNode ``response`` port into the model's text payload.

    ``LLMAgentNode`` publishes ``response`` as ``{"content": "<text>", ...}``
    (mock + real providers both). A defensive caller may also pass the bare
    string. Mirrors evaluation.py's ``_unwrap_response_content`` + the
    conversational.py ``response.get("content")`` unwrap.
    """
    if isinstance(response, dict):
        return response.get("content")
    return response


# ---------------------------------------------------------------------------
# COMPUTE-stage functions (#1117/#1123/#1118 root-cause fix).
#
# Each function below was lifted verbatim from a prior PythonCodeNode `"code"`
# string body and is wired via `PythonCodeNode.from_function(fn)`. A
# from_function node publishes its `return` on the SINGLE flat `result` port
# (NOT the top-level keys the f-string codegen assembled), so every downstream
# `add_connection(..., "<node_id>", ...)` reading a top-level key was rewired to
# read the nested `result.<key>` port. The lift makes the bodies statically
# checkable real functions (real `return` -> `result`) and closes the
# brace-escape / import-trap / publish-nothing defect classes. Mirrors the
# reference template landed in optimized.py / graph.py / evaluation.py /
# query_processing.py + the strategy parser/composer above in this file.
#
# IN-GRAPH HONESTY (zero-tolerance Rule 2): each function's computation is
# behavior-equivalent to the prior codegen; honest defaults on edge inputs
# (a cache-miss / unwired-optional branch arriving None), never fabricated data.
# ---------------------------------------------------------------------------


def _analyze_documents(documents=None) -> dict:
    """Analyze document quality and recommend a RAG strategy.

    AdvancedRAGWorkflowNode entry stage (was the ``quality_analyzer`` ``code``
    string). Filters non-dict elements, computes corpus characteristics, and
    selects a strategy. Publishes ``{"analysis": <dict>, "documents": <list>}``
    on the from_function ``result`` port — the SwitchNode router + the validator
    read ``result.analysis`` / ``result.documents``.
    """

    def _content(doc):
        # `_content` filters a present-but-None `content` key (dict.get returns
        # None, so `or ""` is required); non-dict elements are filtered out by
        # the comprehension below before this is reached.
        return (doc.get("content") or "") if isinstance(doc, dict) else ""

    documents = [d for d in (documents or []) if isinstance(d, dict)]
    analysis = {
        "total_docs": len(documents),
        "avg_length": (
            sum(len(_content(doc)) for doc in documents) / len(documents)
            if documents
            else 0
        ),
        "has_structure": any("section" in doc or "heading" in doc for doc in documents),
        "is_technical": any(
            keyword in _content(doc).lower()
            for doc in documents
            for keyword in ["code", "function", "algorithm", "api", "class"]
        ),
        "recommended_strategy": "semantic",  # Default
    }

    # Determine best strategy based on analysis
    if analysis["has_structure"] and analysis["avg_length"] > 2000:
        analysis["recommended_strategy"] = "hierarchical"
    elif analysis["is_technical"]:
        analysis["recommended_strategy"] = "statistical"
    elif analysis["total_docs"] > 100:
        analysis["recommended_strategy"] = "hybrid"

    return {"analysis": analysis, "documents": documents}


def _validate_rag_results(rag_results=None, analysis=None) -> dict:
    """Validate RAG strategy output against quality thresholds.

    AdvancedRAGWorkflowNode terminal stage (was the ``quality_validator``
    ``code`` string). ``rag_results`` arrives from whichever strategy pipeline
    fired (``output`` port); ``analysis`` from the quality analyzer. Honest
    defaults (empty dict) when an upstream branch did not fire. Publishes the
    full validation envelope on the from_function ``result`` port.
    """
    results = rag_results if isinstance(rag_results, dict) else {}
    analysis = analysis if isinstance(analysis, dict) else {}

    scores = results.get("scores") or []
    validation = {
        "results_count": len(results.get("documents", [])),
        "avg_score": (sum(scores) / len(scores)) if scores else 0,
        "quality_score": 0.0,
        "passed": False,
    }

    # Calculate quality score
    if validation["results_count"] > 0:
        validation["quality_score"] = validation["avg_score"] * (
            validation["results_count"] / 5.0
        )
        validation["passed"] = validation["quality_score"] > 0.5

    return {
        "results": results,
        "validation": validation,
        "strategy_used": analysis.get("recommended_strategy"),
        "final_status": "passed" if validation["passed"] else "needs_improvement",
    }


def _analyze_for_llm(documents=None, query="") -> dict:
    """Compute document characteristics for AdaptiveRAGWorkflowNode's LLM analyzer.

    Entry stage (was the ``document_preprocessor`` ``code`` string). Filters
    non-dict elements, derives corpus characteristics + content types, and
    echoes the ``query`` + filtered ``documents``. Publishes the FLAT analysis
    dict on the from_function ``result`` port — the strategy-analyzer messages
    composer reads ``result.document_count`` / ``result.avg_length`` /
    ``result.has_structure`` / ``result.is_technical`` / ``result.content_types``
    / ``result.query``; the SwitchNode executor + aggregator read ``result`` as
    ``preprocessed_data``.

    (The prior codegen carried an ``import re`` that the body never used; it is
    dropped in the lift — zero behavioral change, no vestigial import.)
    """

    def _content(doc):
        # Filter a present-but-None `content` key (dict.get returns None ->
        # `or ""`); non-dict elements are removed by the comprehension below.
        return (doc.get("content") or "") if isinstance(doc, dict) else ""

    documents = [d for d in (documents or []) if isinstance(d, dict)]
    if not documents:
        return {
            "document_count": 0,
            "avg_length": 0,
            "has_structure": False,
            "is_technical": False,
            "content_types": [],
            "query": query,
        }

    # Analyze documents
    total_length = sum(len(_content(doc)) for doc in documents)
    avg_length = total_length / len(documents)

    # Check for structure
    has_structure = any(
        any(
            keyword in _content(doc).lower()
            for keyword in ["# ", "## ", "### ", "heading", "section", "chapter"]
        )
        for doc in documents
    )

    # Check for technical content
    technical_keywords = [
        "code",
        "function",
        "class",
        "algorithm",
        "api",
        "import",
        "def ",
        "return",
        "variable",
    ]
    is_technical = any(
        any(keyword in _content(doc).lower() for keyword in technical_keywords)
        for doc in documents
    )

    # Determine content types
    content_types = []
    if has_structure:
        content_types.append("structured")
    if is_technical:
        content_types.append("technical")
    if avg_length > 2000:
        content_types.append("long_form")
    if len(documents) > 50:
        content_types.append("large_collection")

    return {
        "document_count": len(documents),
        "avg_length": int(avg_length),
        "has_structure": has_structure,
        "is_technical": is_technical,
        "content_types": content_types,
        "query": query,
        "documents": documents,
    }


def _aggregate_adaptive_results(
    rag_results=None, llm_decision=None, preprocessed_data=None
) -> dict:
    """Aggregate the AdaptiveRAGWorkflowNode terminal output.

    Terminal stage (was the ``results_aggregator`` ``code`` string).
    ``rag_results`` arrives from whichever strategy pipeline fired (``output``
    port); ``llm_decision`` from the strategy-decision parser's ``result`` port
    (the PARSED ``{recommended_strategy, reasoning, confidence,
    fallback_strategy}`` decision); ``preprocessed_data`` from the
    preprocessor's ``result`` port. Honest defaults (empty dict) when an
    upstream branch did not fire. Publishes the aggregate envelope on the flat
    ``result`` port.
    """
    llm_decision = llm_decision if isinstance(llm_decision, dict) else {}
    preprocessed_data = preprocessed_data if isinstance(preprocessed_data, dict) else {}

    return {
        "results": rag_results,
        "strategy_used": llm_decision.get("recommended_strategy"),
        "llm_reasoning": llm_decision.get("reasoning"),
        "confidence": llm_decision.get("confidence"),
        "document_analysis": {
            "count": preprocessed_data.get("document_count"),
            "avg_length": preprocessed_data.get("avg_length"),
            "content_types": preprocessed_data.get("content_types"),
        },
        "adaptive_metadata": {
            # F9 #1126: the actual model is read from the upstream LLMAgentNode
            # config; emit a documented sentinel here (this aggregate does not
            # carry the build-time model name).
            "llm_model_used": "<env-default>",
            "strategy_selection_method": "llm_analysis",
            "fallback_available": llm_decision.get("fallback_strategy"),
        },
    }


def _make_config_processor(
    *,
    default_strategy: str,
    chunk_size: int,
    chunk_overlap: int,
    embedding_model: str,
    retrieval_k: int,
):
    """Build a from_function-compatible ``config_processor`` bound to build-time
    RAGConfig values for RAGPipelineWorkflowNode.

    This is the closure-bound factory (#1118 import-trap / #1123 brace-escape
    root-cause fix): the prior ``config_processor`` was an f-STRING codegen
    interpolating ``repr()``-escaped RAGConfig literals into the ``code`` body
    (doubled ``{{`` braces, `repr()` injection-hardening). Lifting to a real
    function with the literals captured in a closure removes the f-string +
    brace-escape surface entirely while preserving the SAME injection-safety
    invariant — the values are bound as Python objects (already typed-coerced by
    the caller), never re-rendered into source text.

    The returned function declares ``documents`` / ``query`` / ``strategy`` as
    its explicit inputs (the same ports the prior codegen read as locals) and
    returns the flat ``processed_config`` dict on the from_function ``result``
    port. The SwitchNode dispatcher reads ``strategy`` as a top-level key of that
    dict; the formatter reads the whole dict as ``config``.
    """

    def _process_config(documents=None, query="", strategy="") -> dict:
        return {
            "strategy": strategy if strategy else default_strategy,
            "documents": documents,
            "query": query if query else "",
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "embedding_model": embedding_model,
            "retrieval_k": retrieval_k,
        }

    _process_config.__name__ = "config_processor"
    _process_config.__doc__ = "Build the RAGPipelineWorkflowNode processed_config."
    return _process_config


def _format_pipeline_results(strategy_results=None, processed_config=None) -> dict:
    """Format the RAGPipelineWorkflowNode terminal output.

    Terminal stage (was the ``results_formatter`` ``code`` string).
    ``strategy_results`` arrives from whichever strategy pipeline fired
    (``output`` port); ``processed_config`` from the ``config_processor``'s
    ``result``. Honest default (empty dict) when no config flowed. Publishes the
    formatted envelope on the flat ``result`` port.
    """
    config = processed_config if isinstance(processed_config, dict) else {}
    return {
        "results": strategy_results,
        "strategy_used": config.get("strategy"),
        "configuration": config,
        "pipeline_type": "configurable",
        "success": True if strategy_results else False,
    }


@register_node()
class SimpleRAGWorkflowNode(WorkflowNode):
    """
    Simple RAG Workflow Node

    Basic chunk → embed → store → retrieve pipeline using semantic chunking.
    Perfect for getting started with RAG or simple document Q&A.

    Inputs
    ------
    text : str
        Document text to chunk + embed + store. Routed to the inner-graph
        ``semantic_chunker`` via ``input_mapping`` (see __init__).

    The mapping makes the workflow self-sufficient at the public API surface:
    callers invoke ``node.execute(text="...")`` and the inner-graph chunker
    receives ``text`` without the caller having to know inner-graph node IDs.
    """

    def __init__(
        self, name: str = "simple_rag_workflow", config: Optional[RAGConfig] = None
    ):
        self.rag_config = config or RAGConfig()

        # Create semantic RAG workflow
        workflow_node = create_semantic_rag_workflow(self.rag_config)

        # Initialize as WorkflowNode.
        # `# type: ignore[attr-defined]` on every `.workflow` access in this
        # module: @register_node erases the concrete WorkflowNode type to base
        # Node, so a static checker does not see `.workflow` — but it IS a real
        # read-only WorkflowNode property (added by shard A3) and resolves at
        # runtime. (Known Core SDK type-erasure gap; B1-B6 worked around it the
        # same way at the call site.)
        #
        # ``input_mapping`` routes the public ``text`` parameter to the
        # inner-graph ``semantic_chunker`` node's ``text`` parameter. Without
        # this mapping the inner graph's chunker has no source for ``text`` —
        # ``LocalRuntime`` raises ``WorkflowValidationError`` on execute. The
        # entry-node parameter MUST be exposed via the WorkflowNode facade so
        # users don't have to learn inner-graph node IDs to invoke the
        # workflow.
        super().__init__(
            workflow=workflow_node.workflow,  # type: ignore[attr-defined]
            name=name,
            description="Simple RAG workflow with semantic chunking and dense retrieval",
            input_mapping={
                "text": {
                    "node": "semantic_chunker",
                    "parameter": "text",
                    "type": str,
                    "required": True,
                    "description": "Document text to chunk + embed + store",
                }
            },
        )


@register_node()
class AdvancedRAGWorkflowNode(WorkflowNode):
    """
    Advanced RAG Workflow Node

    Multi-stage RAG pipeline with quality checks, multiple retrieval strategies,
    and result validation. Includes monitoring and performance optimization.

    Inputs
    ------
    documents : list
        Document list to analyze + route through the quality-driven RAG
        strategy. Routed to the inner-graph ``quality_analyzer`` via
        ``input_mapping`` (see __init__).

    The mapping makes the workflow self-sufficient at the public API
    surface: callers invoke ``node.execute(documents=[...])`` and the
    inner-graph quality analyzer receives ``documents`` without the
    caller having to know inner-graph node IDs.
    """

    def __init__(
        self, name: str = "advanced_rag_workflow", config: Optional[RAGConfig] = None
    ):
        self.rag_config = config or RAGConfig()

        # Build advanced workflow
        workflow = self._create_advanced_workflow()

        # ``input_mapping`` routes the public ``documents`` parameter to the
        # inner-graph ``quality_analyzer`` node's ``documents`` parameter.
        # Without this mapping the facade auto-derives ``quality_analyzer_
        # documents`` (node_id + ``_`` + param_name) — users would have to
        # know the inner-graph node ID to invoke the workflow. Per F25 Shard D
        # (same defect class as SimpleRAGWorkflowNode F25 Shard C): the entry
        # parameter MUST be exposed via the WorkflowNode facade so users
        # don't have to learn inner-graph node IDs to invoke the workflow.
        super().__init__(
            workflow=workflow,
            name=name,
            description="Advanced RAG with quality checks and multi-stage processing",
            input_mapping={
                "documents": {
                    "node": "quality_analyzer",
                    "parameter": "documents",
                    "type": list,
                    "required": True,
                    "description": "Documents to analyze + route through quality-driven RAG strategy",
                }
            },
        )

    def _create_advanced_workflow(self):
        """Create advanced RAG workflow with quality checks and monitoring"""
        builder = WorkflowBuilder()

        # Document quality analyzer.
        #
        # #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `_analyze_documents` function wired via `PythonCodeNode.from_function`.
        # The node publishes its return on the flat `result` port carrying
        # `{"analysis": {...}, "documents": [...]}`; the downstream router +
        # validator now read the nested `result.analysis` port (the SwitchNode
        # `condition_field: "recommended_strategy"` resolves against the analysis
        # dict's top-level key). `_internal=True` suppresses the consumer-facing
        # instance-API advisory (SDK-internal construction; mirrors optimized.py).
        # `type: ignore[attr-defined]`: `from_function` is a classmethod on
        # concrete PythonCodeNode, erased to `type[Node]` by `@register_node`.
        quality_analyzer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _analyze_documents,
                name="quality_analyzer",
            ),
            node_id="quality_analyzer",
            _internal=True,
        )

        # Strategy router using switch node.
        # SwitchNode multi-case mode: `cases` is the list of values to match on
        # the `condition_field`; each match is emitted on a `case_<value>`
        # output port (see kailash SwitchNode._sanitize_case_name). The four
        # strategy names contain no characters that sanitize, so the ports are
        # `case_semantic` / `case_statistical` / `case_hybrid` /
        # `case_hierarchical`.
        router_id = builder.add_node(
            "SwitchNode",
            node_id="strategy_router",
            config={
                "condition_field": "recommended_strategy",
                "cases": ["semantic", "statistical", "hybrid", "hierarchical"],
            },
        )

        # Add all RAG strategy pipelines
        semantic_workflow = create_semantic_rag_workflow(self.rag_config)
        statistical_workflow = create_statistical_rag_workflow(self.rag_config)
        hybrid_workflow = create_hybrid_rag_workflow(self.rag_config)
        hierarchical_workflow = create_hierarchical_rag_workflow(self.rag_config)

        semantic_id = builder.add_node(
            "WorkflowNode",
            node_id="semantic_rag_pipeline",
            config={"workflow": semantic_workflow.workflow},  # type: ignore[attr-defined]
        )

        statistical_id = builder.add_node(
            "WorkflowNode",
            node_id="statistical_rag_pipeline",
            config={"workflow": statistical_workflow.workflow},  # type: ignore[attr-defined]
        )

        hybrid_id = builder.add_node(
            "WorkflowNode",
            node_id="hybrid_rag_pipeline",
            config={"workflow": hybrid_workflow.workflow},  # type: ignore[attr-defined]
        )

        hierarchical_id = builder.add_node(
            "WorkflowNode",
            node_id="hierarchical_rag_pipeline",
            config={"workflow": hierarchical_workflow.workflow},  # type: ignore[attr-defined]
        )

        # Quality validator.
        #
        # #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `_validate_rag_results` function wired via
        # `PythonCodeNode.from_function`. Its `rag_results` input arrives from
        # whichever strategy pipeline fired (`output` port); `analysis` from the
        # quality analyzer's nested `result.analysis` port. The node publishes
        # the validation envelope on the flat `result` port.
        validator_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _validate_rag_results,
                name="quality_validator",
            ),
            node_id="quality_validator",
            _internal=True,
        )

        # Connect the advanced pipeline. SwitchNode's primary input port is
        # `input_data`; each multi-case match emits on `case_<value>`.
        #
        # PHANTOM-PORT FIX: the SwitchNode `condition_field` reads
        # `recommended_strategy` as a TOP-LEVEL key of `input_data`, but
        # `_analyze_documents` publishes it nested inside `result.analysis`
        # (the flat `result` port carries `{"analysis": {...}, "documents": ...}`).
        # The edge now reads the nested `result.analysis` port so the SwitchNode
        # switches on the REAL strategy the analyzer selected (the pre-migration
        # edge fed the whole wrapper dict, whose top-level had no
        # `recommended_strategy` key).
        builder.add_connection(
            quality_analyzer_id, "result.analysis", router_id, "input_data"
        )

        # Connect router to all strategy pipelines via the per-case output ports.
        builder.add_connection(router_id, "case_semantic", semantic_id, "input")
        builder.add_connection(router_id, "case_statistical", statistical_id, "input")
        builder.add_connection(router_id, "case_hybrid", hybrid_id, "input")
        builder.add_connection(router_id, "case_hierarchical", hierarchical_id, "input")

        # Connect all pipelines to validator
        builder.add_connection(semantic_id, "output", validator_id, "rag_results")
        builder.add_connection(statistical_id, "output", validator_id, "rag_results")
        builder.add_connection(hybrid_id, "output", validator_id, "rag_results")
        builder.add_connection(hierarchical_id, "output", validator_id, "rag_results")
        # PHANTOM-PORT FIX: feed the validator the nested `result.analysis` dict
        # (so `analysis.get("recommended_strategy")` resolves to the real
        # strategy) rather than the whole `result` wrapper. The strategy
        # pipelines publish their RAG output on `output`, wired to `rag_results`.
        builder.add_connection(
            quality_analyzer_id, "result.analysis", validator_id, "analysis"
        )

        return builder.build(name="advanced_rag_workflow")


@register_node()
class AdaptiveRAGWorkflowNode(WorkflowNode):
    """
    Adaptive RAG Workflow Node

    AI-driven strategy selection that uses LLM to analyze documents and queries
    to automatically choose the optimal RAG approach for each use case.

    Inputs
    ------
    documents : list
        Document list to analyze for adaptive strategy selection. Routed
        to the inner-graph ``document_preprocessor`` via ``input_mapping``.
    query : str, optional
        Query text passed alongside ``documents`` for LLM-driven strategy
        selection. Defaults to ``""`` (matches preprocessor codegen
        default). Also routed via ``input_mapping``.

    The mapping makes the workflow self-sufficient at the public API
    surface: callers invoke ``node.execute(documents=[...], query="...")``
    and the inner-graph preprocessor receives both without the caller
    having to know inner-graph node IDs.
    """

    def __init__(
        self,
        name: str = "adaptive_rag_workflow",
        llm_model: Optional[str] = _DEFAULT_LLM_MODEL,
        config: Optional[RAGConfig] = None,
    ):
        self.rag_config = config or RAGConfig()
        self.llm_model = llm_model

        # Build adaptive workflow
        workflow = self._create_adaptive_workflow()

        # ``input_mapping`` routes the public ``documents`` + ``query``
        # parameters to the inner-graph ``document_preprocessor`` node's
        # ``documents`` / ``query`` parameters. Without this mapping the
        # facade auto-derives ``document_preprocessor_documents`` /
        # ``document_preprocessor_query`` — users would have to know the
        # inner-graph node ID to invoke the workflow. Per F25 Shard D
        # (same defect class as SimpleRAGWorkflowNode F25 Shard C).
        super().__init__(
            workflow=workflow,
            name=name,
            description="AI-driven adaptive RAG with intelligent strategy selection",
            input_mapping={
                "documents": {
                    "node": "document_preprocessor",
                    "parameter": "documents",
                    "type": list,
                    "required": True,
                    "description": "Documents to analyze for adaptive strategy selection",
                },
                "query": {
                    "node": "document_preprocessor",
                    "parameter": "query",
                    "type": str,
                    "required": False,
                    "default": "",
                    "description": "Query text for LLM-driven strategy selection",
                },
            },
        )

    def _create_adaptive_workflow(self):
        """Create adaptive RAG workflow with LLM-driven strategy selection"""
        builder = WorkflowBuilder()

        # LLM Strategy Analyzer
        llm_analyzer_id = builder.add_node(
            "LLMAgentNode",
            node_id="rag_strategy_analyzer",
            config={
                "model": self.llm_model,
                "provider": "openai",
                "system_prompt": """You are a RAG strategy expert. Analyze documents and queries to recommend the optimal RAG approach.

Available strategies:
- semantic: Best for narrative content, general Q&A, semantic similarity
- statistical: Best for technical docs, code, structured content, keyword matching
- hybrid: Best for mixed content, combines semantic + statistical (20-30% better performance)
- hierarchical: Best for long documents, structured content with sections/headings

Analyze the input and respond with ONLY a JSON object:
{
    "recommended_strategy": "semantic|statistical|hybrid|hierarchical",
    "reasoning": "Brief explanation of why this strategy is optimal",
    "confidence": 0.0-1.0,
    "fallback_strategy": "backup strategy if primary fails"
}""",
                "prompt_template": """Analyze these documents for optimal RAG strategy:

Document Analysis:
- Count: {document_count}
- Average length: {avg_length} characters
- Has structure (headings/sections): {has_structure}
- Technical content detected: {is_technical}
- Content types: {content_types}

Query (if provided): {query}

Recommend the optimal RAG strategy:""",
            },
        )

        # Document preprocessor for LLM analysis.
        #
        # #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `_analyze_for_llm` function wired via `PythonCodeNode.from_function`.
        # The node publishes the FLAT analysis dict on the `result` port; the
        # nested `result.<key>` ports (`document_count` / `avg_length` /
        # `has_structure` / `is_technical` / `content_types` / `query`) feed the
        # strategy-analyzer messages composer (already wired below), and the
        # whole `result` feeds the SwitchNode executor + aggregator as
        # `preprocessed_data`. `_internal=True` suppresses the consumer-facing
        # instance-API advisory.
        preprocessor_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _analyze_for_llm,
                name="document_preprocessor",
            ),
            node_id="document_preprocessor",
            _internal=True,
        )

        # Strategy executor with switch
        executor_id = builder.add_node(
            "SwitchNode",
            node_id="strategy_executor",
            config={
                "condition_field": "recommended_strategy",
                "cases": ["semantic", "statistical", "hybrid", "hierarchical"],
            },
        )

        # Add strategy pipelines
        semantic_workflow = create_semantic_rag_workflow(self.rag_config)
        statistical_workflow = create_statistical_rag_workflow(self.rag_config)
        hybrid_workflow = create_hybrid_rag_workflow(self.rag_config)
        hierarchical_workflow = create_hierarchical_rag_workflow(self.rag_config)

        semantic_pipeline_id = builder.add_node(
            "WorkflowNode",
            node_id="semantic_pipeline",
            config={"workflow": semantic_workflow.workflow},  # type: ignore[attr-defined]
        )

        statistical_pipeline_id = builder.add_node(
            "WorkflowNode",
            node_id="statistical_pipeline",
            config={"workflow": statistical_workflow.workflow},  # type: ignore[attr-defined]
        )

        hybrid_pipeline_id = builder.add_node(
            "WorkflowNode",
            node_id="hybrid_pipeline",
            config={"workflow": hybrid_workflow.workflow},  # type: ignore[attr-defined]
        )

        hierarchical_pipeline_id = builder.add_node(
            "WorkflowNode",
            node_id="hierarchical_pipeline",
            config={"workflow": hierarchical_workflow.workflow},  # type: ignore[attr-defined]
        )

        # Results aggregator.
        #
        # #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `_aggregate_adaptive_results` function wired via
        # `PythonCodeNode.from_function`. `llm_decision` reads the PARSED
        # strategy-decision dict (republished on `strategy_decision_parser.result`
        # — see the OUTPUT-side wiring below); `preprocessed_data` reads the
        # preprocessor's `result`; `rag_results` reads the fired strategy
        # pipeline's `output`. The node publishes the aggregate envelope on the
        # flat `result` port.
        aggregator_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _aggregate_adaptive_results,
                name="results_aggregator",
            ),
            node_id="results_aggregator",
            _internal=True,
        )

        # L3 messages-composer (reference template — conversational.py /
        # query_processing.py / agentic.py / graph.py). The
        # `rag_strategy_analyzer` LLM stage previously received NO real input on
        # a port LLMAgentNode reads: its only inbound edge was
        # `document_preprocessor.result -> rag_strategy_analyzer.input`, and
        # `input` is a port LLMAgentNode silently drops (its `run` reads only
        # `kwargs["messages"]`). The analyzer answered from its `system_prompt`
        # alone — it never saw the document characteristics nor the query it is
        # meant to analyze to pick the optimal RAG strategy.
        #
        # The composer renders the REAL `document_preprocessor` output
        # characteristics (delivered via the nested `result.<key>` ports a
        # from_function node publishes — `document_count` / `avg_length` /
        # `has_structure` / `is_technical` / `content_types`) PLUS the real
        # top-level `query` (auto-distributed by the parameter injector) into the
        # analyzer's VALID `messages` port. `from_function` is the correct
        # primitive (real module-level function: real `return`→`result`,
        # statically checkable). `type: ignore[attr-defined]`: `from_function`
        # is a
        # classmethod on concrete PythonCodeNode, erased to `type[Node]` by
        # `@register_node` for static checkers (mirrors conversational.py).
        # `_internal=True` suppresses the consumer-facing instance-API advisory.
        strategy_analyzer_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                compose_strategy_analyzer_messages,
                name="strategy_analyzer_messages_composer",
            ),
            node_id="strategy_analyzer_messages_composer",
            _internal=True,
        )

        # Strategy-decision parser (OUTPUT-side fix — same `from_function` +
        # `add_node_instance(_internal=True)` primitive as the composer above and
        # the O1 evaluation.py response parsers). The `rag_strategy_analyzer`
        # LLMAgentNode publishes its decision on the `response` port (a dict
        # `{"content": "<JSON string>", ...}`); this parser unwraps `.content`,
        # `json.loads` it, and republishes the parsed `{recommended_strategy,
        # reasoning, confidence, fallback_strategy}` on its `result` so the
        # SwitchNode + aggregator consume the REAL decision (the pre-shard edges
        # read a `result` port LLMAgentNode never publishes — see the rewired
        # connections below). Malformed output yields a typed parse-error
        # sentinel, NOT a fabricated strategy (zero-tolerance Rule 2).
        strategy_decision_parser_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                parse_strategy_decision,
                name="strategy_decision_parser",
            ),
            node_id="strategy_decision_parser",
            _internal=True,
        )

        # Connect adaptive pipeline. SwitchNode's primary input port is
        # `input_data`; each multi-case match emits on `case_<value>`.
        #
        # FIX: the prior `document_preprocessor.result ->
        # rag_strategy_analyzer.input` phantom edge fed the analyzer a port
        # LLMAgentNode drops. The composer now renders the REAL preprocessor
        # characteristics + the real query into the analyzer's `messages` port;
        # the phantom `input` edge is REMOVED.
        #
        # The real `document_preprocessor.result` characteristics reach the
        # composer via the nested-key ports a from_function node publishes
        # (`result.<key>`); the real `query` reaches the composer the same way —
        # the top-level `query` is delivered into `document_preprocessor` via
        # `input_mapping` (see __init__), the preprocessor republishes it on
        # `result.query`, and the wired `preprocessor.result.query ->
        # composer.query` edge below carries it in. This is the production
        # delivery path (top-level input → in-graph wiring), NOT node-keyed
        # injection of the analyzer's load-bearing content.
        builder.add_connection(
            preprocessor_id,
            "result.document_count",
            strategy_analyzer_messages_composer_id,
            "document_count",
        )
        builder.add_connection(
            preprocessor_id,
            "result.avg_length",
            strategy_analyzer_messages_composer_id,
            "avg_length",
        )
        builder.add_connection(
            preprocessor_id,
            "result.has_structure",
            strategy_analyzer_messages_composer_id,
            "has_structure",
        )
        builder.add_connection(
            preprocessor_id,
            "result.is_technical",
            strategy_analyzer_messages_composer_id,
            "is_technical",
        )
        builder.add_connection(
            preprocessor_id,
            "result.content_types",
            strategy_analyzer_messages_composer_id,
            "content_types",
        )
        builder.add_connection(
            preprocessor_id,
            "result.query",
            strategy_analyzer_messages_composer_id,
            "query",
        )
        builder.add_connection(
            strategy_analyzer_messages_composer_id,
            "result.messages",
            llm_analyzer_id,
            "messages",
        )
        # OUTPUT-side fix: the analyzer publishes its decision on `response`
        # (NOT `result` — the pre-shard phantom port). Route `response` through
        # the parser, which republishes the PARSED decision dict on `result`. The
        # SwitchNode then switches on the real `recommended_strategy` (its
        # `condition_field` reads the top-level key of `input_data`), and the
        # aggregator reads the real reasoning/confidence/fallback.
        builder.add_connection(
            llm_analyzer_id, "response", strategy_decision_parser_id, "response"
        )
        builder.add_connection(
            strategy_decision_parser_id, "result", executor_id, "input_data"
        )
        builder.add_connection(
            preprocessor_id, "result", executor_id, "preprocessed_data"
        )

        # Connect executor to strategy pipelines via the per-case output ports.
        builder.add_connection(
            executor_id, "case_semantic", semantic_pipeline_id, "input"
        )
        builder.add_connection(
            executor_id, "case_statistical", statistical_pipeline_id, "input"
        )
        builder.add_connection(executor_id, "case_hybrid", hybrid_pipeline_id, "input")
        builder.add_connection(
            executor_id, "case_hierarchical", hierarchical_pipeline_id, "input"
        )

        # Connect all pipelines to aggregator
        builder.add_connection(
            semantic_pipeline_id, "output", aggregator_id, "rag_results"
        )
        builder.add_connection(
            statistical_pipeline_id, "output", aggregator_id, "rag_results"
        )
        builder.add_connection(
            hybrid_pipeline_id, "output", aggregator_id, "rag_results"
        )
        builder.add_connection(
            hierarchical_pipeline_id, "output", aggregator_id, "rag_results"
        )
        # OUTPUT-side fix: the aggregator's `llm_decision` reads the PARSED
        # decision dict (republished on `strategy_decision_parser.result`), NOT
        # the analyzer's non-existent `result` port. So `strategy_used`,
        # `llm_reasoning`, `confidence`, and `fallback_available` reflect the REAL
        # LLM strategy decision instead of defaulting to None.
        builder.add_connection(
            strategy_decision_parser_id, "result", aggregator_id, "llm_decision"
        )
        builder.add_connection(
            preprocessor_id, "result", aggregator_id, "preprocessed_data"
        )

        return builder.build(name="adaptive_rag_workflow")


@register_node()
class RAGPipelineWorkflowNode(WorkflowNode):
    """
    Configurable RAG Pipeline Workflow Node

    Flexible RAG workflow that can be configured for different use cases
    without code changes. Supports all strategies and custom configurations.

    Inputs
    ------
    documents : list
        Document list to process through the configurable RAG pipeline.
        Routed to the inner-graph ``config_processor`` via ``input_mapping``.
    query : str, optional
        Query text for retrieval. Defaults to ``""`` (matches the
        processor codegen default). Routed via ``input_mapping``.
    strategy : str, optional
        Strategy selection (``semantic`` / ``statistical`` / ``hybrid`` /
        ``hierarchical``). Defaults to the class's ``default_strategy``
        argument. Routed via ``input_mapping``.

    The mapping makes the workflow self-sufficient at the public API
    surface: callers invoke ``node.execute(documents=[...])`` and the
    inner-graph processor receives the inputs without the caller having
    to know inner-graph node IDs.
    """

    def __init__(
        self,
        name: str = "rag_pipeline",
        default_strategy: str = "hybrid",
        config: Optional[RAGConfig] = None,
    ):
        self.rag_config = config or RAGConfig()
        self.default_strategy = default_strategy

        # Build configurable workflow
        workflow = self._create_configurable_workflow()

        # ``input_mapping`` routes the public ``documents`` + ``query`` +
        # ``strategy`` parameters to the inner-graph ``config_processor``
        # node's ``documents`` / ``query`` / ``strategy`` parameters.
        # Without this mapping the facade auto-derives ``config_processor_
        # documents`` / ``config_processor_query`` / ``config_processor_
        # strategy`` — users would have to know the inner-graph node ID to
        # invoke the workflow. Per F25 Shard D (same defect class as
        # SimpleRAGWorkflowNode F25 Shard C).
        super().__init__(
            workflow=workflow,
            name=name,
            description=f"Configurable RAG pipeline with {default_strategy} as default strategy",
            input_mapping={
                "documents": {
                    "node": "config_processor",
                    "parameter": "documents",
                    "type": list,
                    "required": True,
                    "description": "Documents to process through the configurable RAG pipeline",
                },
                "query": {
                    "node": "config_processor",
                    "parameter": "query",
                    "type": str,
                    "required": False,
                    "default": "",
                    "description": "Query text for retrieval",
                },
                "strategy": {
                    "node": "config_processor",
                    "parameter": "strategy",
                    "type": str,
                    "required": False,
                    "default": default_strategy,
                    "description": "Strategy selection: semantic / statistical / hybrid / hierarchical",
                },
            },
        )

    def _create_configurable_workflow(self):
        """Create configurable RAG workflow"""
        builder = WorkflowBuilder()

        # Configuration processor.
        #
        # F25 Shard D sibling-sweep fix (autonomous-execution.md MUST Rule 4
        # — same-bug-class fix surfaced during the entry-wiring sweep):
        # the prior codegen ended with ``result = process_config(documents,
        # **kwargs)`` but ``kwargs`` is NOT defined in the PythonCodeNode
        # exec scope (PythonCodeNode binds explicit input parameters as
        # locals — ``documents``, ``query``, ``strategy`` — not a kwargs
        # dict). Every invocation raised ``NameError: name 'kwargs' is
        # not defined`` at the entry node.
        #
        # #1117/#1123/#1118 root-cause fix: the prior ``config_processor`` was an
        # f-STRING codegen interpolating ``repr()``-escaped RAGConfig literals
        # into the ``code`` body (doubled ``{{`` braces — the #1123 brace-escape
        # surface). It is lifted to the module-level ``_make_config_processor``
        # closure factory wired via ``PythonCodeNode.from_function``: the
        # build-time RAGConfig values are captured as typed Python objects in the
        # closure, NEVER re-rendered into source text. This removes the f-string +
        # brace-escape surface entirely while preserving the SAME injection-safety
        # invariant the prior ``repr()`` hardening provided (the values are bound
        # objects, already typed-coerced below, so no source-injection path
        # exists). The returned function declares ``documents`` / ``query`` /
        # ``strategy`` as its explicit input ports (the same locals the prior
        # codegen read) and returns the flat ``processed_config`` dict on the
        # ``result`` port — the SwitchNode dispatcher reads ``strategy`` as a
        # top-level key, the formatter reads the whole dict as ``config``.
        #
        # PythonCodeNode does not expose a kwargs dict, so the original codegen's
        # "user can override chunk_size at runtime" contract was never reachable
        # through this node anyway — the override path is via ``config: RAGConfig``
        # at construction time, which IS preserved (the closure captures it).
        #
        # Strategy enum validation (M2): `default_strategy` MUST be one of the
        # SwitchNode's declared cases. An unknown strategy would silently fall
        # through to no case match — converting that into a typed ValueError
        # surfaces misuse at construction instead of producing a confusing empty
        # workflow output at runtime.
        _ALLOWED_STRATEGIES = ("semantic", "statistical", "hybrid", "hierarchical")
        if self.default_strategy not in _ALLOWED_STRATEGIES:
            raise ValueError(
                f"RAGPipelineWorkflowNode.default_strategy={self.default_strategy!r} "
                f"is not in the allowed set {_ALLOWED_STRATEGIES}; "
                f"SwitchNode would never dispatch to a matching case."
            )

        # Typed coercion of every build-time value before binding into the
        # closure (mirrors the prior ``repr(int(...))`` / ``repr(str(...))``
        # coercion — neutralizes a subclass-``__str__``/``__int__`` override
        # smuggling a non-literal value).
        config_processor_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _make_config_processor(
                    default_strategy=str(self.default_strategy),
                    chunk_size=int(self.rag_config.chunk_size),
                    chunk_overlap=int(self.rag_config.chunk_overlap),
                    embedding_model=str(self.rag_config.embedding_model),
                    retrieval_k=int(self.rag_config.retrieval_k),
                ),
                name="config_processor",
            ),
            node_id="config_processor",
            _internal=True,
        )

        # Strategy dispatcher
        dispatcher_id = builder.add_node(
            "SwitchNode",
            node_id="strategy_dispatcher",
            config={
                "condition_field": "strategy",
                "cases": ["semantic", "statistical", "hybrid", "hierarchical"],
            },
        )

        # Add all strategy implementations
        strategies = {
            "semantic": create_semantic_rag_workflow(self.rag_config),
            "statistical": create_statistical_rag_workflow(self.rag_config),
            "hybrid": create_hybrid_rag_workflow(self.rag_config),
            "hierarchical": create_hierarchical_rag_workflow(self.rag_config),
        }

        strategy_ids = {}
        for strategy_name, workflow_node in strategies.items():
            strategy_id = builder.add_node(
                "WorkflowNode",
                node_id=f"{strategy_name}_strategy",
                config={"workflow": workflow_node.workflow},  # type: ignore[attr-defined]
            )
            strategy_ids[strategy_name] = strategy_id

        # Results formatter.
        #
        # #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `_format_pipeline_results` function wired via
        # `PythonCodeNode.from_function`. `strategy_results` arrives from
        # whichever strategy pipeline fired (`output` port); `processed_config`
        # from the `config_processor`'s `result`. The node publishes the
        # formatted envelope on the flat `result` port.
        formatter_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _format_pipeline_results,
                name="results_formatter",
            ),
            node_id="results_formatter",
            _internal=True,
        )

        # Connect configurable pipeline. SwitchNode's primary input port is
        # `input_data`; each multi-case match emits on `case_<value>` where
        # `<value>` is the matched `strategy` field value.
        builder.add_connection(
            config_processor_id, "result", dispatcher_id, "input_data"
        )

        # Connect dispatcher to all strategies via the per-case output ports.
        for strategy_name, strategy_id in strategy_ids.items():
            builder.add_connection(
                dispatcher_id, f"case_{strategy_name}", strategy_id, "input"
            )
            builder.add_connection(
                strategy_id, "output", formatter_id, "strategy_results"
            )

        builder.add_connection(
            config_processor_id, "result", formatter_id, "processed_config"
        )

        return builder.build(name="configurable_rag_pipeline")
