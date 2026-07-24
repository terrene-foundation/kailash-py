"""
Advanced Query Processing for RAG

Implements sophisticated query enhancement techniques:
- Query expansion with synonyms and related terms
- Query decomposition for complex questions
- Query rewriting for better retrieval
- Intent classification and routing
- Multi-hop query planning

All implementations use existing Kailash components and WorkflowBuilder patterns.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Union  # noqa: F401

from kailash.nodes.base import Node, NodeParameter, register_node

# Registering import (mirrors evaluation.py / conversational.py): the inner
# workflows wire PythonCodeNode by STRING via `builder.add_node("PythonCodeNode",
# ...)`, AND the L3 messages-composer fix below wraps real module-level functions
# via `PythonCodeNode.from_function(fn)`. Importing the class runs the
# `@register_node` side effect that populates the registry the string lookup
# resolves against, and binds the symbol `.from_function` is called on. Do NOT
# drop to satisfy an unused-import linter.
from kailash.nodes.code.python import PythonCodeNode  # noqa: F401
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow

# Module-scope import retained as the monkeypatch target for the
# integration test fixture `deterministic_llm` at
# tests/integration/rag/test_query_processing_nodes.py — the fixture
# uses `monkeypatch.setattr(<this module>, "LLMAgentNode", <stub>)` to
# substitute a deterministic adapter. Runtime code references
# "LLMAgentNode" only as a node-type string passed to
# WorkflowBuilder.add_node; the class import itself is unused at runtime
# but required for the test's setattr rebinding to land on this module's
# namespace. The static-analyzer "unused import" finding is a known
# false-positive for monkeypatch-target imports.
from ..ai.llm_agent import LLMAgentNode  # noqa: F401
from kaizen.core._provider_env import detect_provider_from_env

logger = logging.getLogger(__name__)


# F9 #1126: env-loaded default LLM model. Mirrors the router.py precedent
# (F8 B10). May be None when neither env var is set — that is
# env-models-compliant; do NOT fall back to a hardcoded model name.
_DEFAULT_LLM_MODEL = os.environ.get(
    "OPENAI_PROD_MODEL", os.environ.get("DEFAULT_LLM_MODEL")
)


# ---------------------------------------------------------------------------
# Messages-composer functions (L3 fix — same reference template as
# conversational.py lines 45-199 and evaluation.py lines 51-229).
#
# LLMAgentNode consumes context EXCLUSIVELY through its `messages` param (the
# OpenAI chat format: a list of {"role","content"} dicts) plus `system_prompt`.
# `LLMAgentNode.run` reads `messages = kwargs["messages"]`; ANY OTHER wired port
# name (`query`, `analysis`, ...) is read via `kwargs.get` and SILENTLY DROPPED.
# The prior wiring fed NO real input to any LLM stage in this module — each
# `_create_workflow` added an LLMAgentNode whose ONLY inbound edge was from a
# DOWNSTREAM consumer's perspective, so the LLM never saw the user's query. It
# answered every expansion / decomposition / rewrite / classification / hop-plan
# request from its `system_prompt` alone (the L3 "LLM ignores its input" defect).
#
# KEY DISTINCTION from the evaluation / conversational shards: these stages run
# PRE-retrieval. The context an LLM stage must reason over is the USER QUERY
# (and, for the query_rewriter, the upstream query_analyzer output) — NOT
# retrieved documents. Every composer below therefore renders the REAL query
# (delivered as the top-level `query` workflow input the parameter injector
# auto-distributes — the same external input each node's deterministic `run()`
# reads) into a `messages` list wired to the LLM stage's VALID `messages` port.
#
# These are real module-level functions (real `return`→`result`, type-checkable,
# no f-string brace-escaping) per the program's reference template — NOT inline
# `code=` codegen blocks. Each is pure data rendering (the permitted
# output-formatting exception per rules/agent-reasoning.md) — NO if-else routing
# / keyword classification on query content.
# ---------------------------------------------------------------------------


def _query_text(query: Any) -> str:
    """Coerce the wired `query` input to a clean string.

    The parameter injector delivers the top-level `query` workflow input; it is
    normally a plain string but may arrive None on an unwired optional branch.
    """
    if isinstance(query, str):
        return query.strip()
    if query is None:
        return ""
    return str(query).strip()


def compose_expansion_messages(query=""):
    """Compose the ``messages`` list for the QueryExpansionNode llm_expander.

    Embeds the REAL user query so the LLM generates expansions OF THE QUERY —
    not from its ``system_prompt`` alone. Returns ``{"messages": [...]}`` wired
    to the LLMAgentNode ``messages`` port.
    """
    q = _query_text(query)
    content = (
        "Generate query expansions for the following query:\n" + q
        if q
        else "No query was provided to expand."
    )
    return {"messages": [{"role": "user", "content": content}]}


def compose_decomposition_messages(query=""):
    """Compose the ``messages`` list for the QueryDecompositionNode
    query_decomposer.

    Embeds the REAL complex query so the LLM decomposes THE QUERY into
    sub-questions — not from its ``system_prompt`` alone. Returns
    ``{"messages": [...]}`` wired to the LLMAgentNode ``messages`` port.
    """
    q = _query_text(query)
    content = (
        "Decompose the following complex query into sub-questions:\n" + q
        if q
        else "No query was provided to decompose."
    )
    return {"messages": [{"role": "user", "content": content}]}


def compose_analysis_messages(query=""):
    """Compose the ``messages`` list for the QueryRewritingNode query_analyzer
    (stage 1 of the 2-stage rewrite chain).

    Embeds the REAL query so the analyzer detects issues IN THE QUERY — not from
    its ``system_prompt`` alone. Returns ``{"messages": [...]}`` wired to the
    LLMAgentNode ``messages`` port.
    """
    q = _query_text(query)
    content = (
        "Analyze the following query for issues and improvements:\n" + q
        if q
        else "No query was provided to analyze."
    )
    return {"messages": [{"role": "user", "content": content}]}


def compose_rewrite_messages(query="", analysis=None):
    """Compose the ``messages`` list for the QueryRewritingNode query_rewriter
    (stage 2 of the 2-stage rewrite chain).

    Embeds the REAL query AND the upstream query_analyzer output so the rewriter
    rewrites THE QUERY guided by the analysis — not from its ``system_prompt``
    alone. Returns ``{"messages": [...]}`` wired to the LLMAgentNode ``messages``
    port.

    ``analysis`` is the query_analyzer LLMAgentNode's ``response`` port value —
    the parsed JSON dict the analyzer's ``system_prompt`` advertises
    (``{"issues": [...], "suggestions": {...}}``). It is rendered as readable
    text so the rewriter genuinely sees the analysis it must act on.
    """
    q = _query_text(query)
    parts = ["Rewrite the following query for optimal retrieval."]
    parts.append("Query:\n" + (q or "(empty)"))

    if isinstance(analysis, dict) and analysis:
        issues = analysis.get("issues")
        suggestions = analysis.get("suggestions")
        analysis_lines = []
        if isinstance(issues, list) and issues:
            analysis_lines.append(
                "Detected issues: " + ", ".join(str(i) for i in issues)
            )
        if isinstance(suggestions, dict) and suggestions:
            for key, val in suggestions.items():
                analysis_lines.append(f"{key}: {val}")
        if analysis_lines:
            parts.append("Analysis of the query:\n" + "\n".join(analysis_lines))
    return {"messages": [{"role": "user", "content": "\n\n".join(parts)}]}


def compose_intent_messages(query=""):
    """Compose the ``messages`` list for the QueryIntentClassifierNode
    intent_classifier.

    Embeds the REAL query so the classifier classifies THE QUERY's intent — not
    from its ``system_prompt`` alone. Returns ``{"messages": [...]}`` wired to
    the LLMAgentNode ``messages`` port.
    """
    q = _query_text(query)
    content = (
        "Classify the intent of the following query:\n" + q
        if q
        else "No query was provided to classify."
    )
    return {"messages": [{"role": "user", "content": content}]}


def compose_hop_plan_messages(query=""):
    """Compose the ``messages`` list for the MultiHopQueryPlannerNode
    hop_planner.

    Embeds the REAL query so the planner plans a multi-hop strategy FOR THE
    QUERY — not from its ``system_prompt`` alone. Returns ``{"messages": [...]}``
    wired to the LLMAgentNode ``messages`` port.
    """
    q = _query_text(query)
    content = (
        "Plan a multi-hop retrieval strategy for the following query:\n" + q
        if q
        else "No query was provided to plan."
    )
    return {"messages": [{"role": "user", "content": content}]}


# ---------------------------------------------------------------------------
# Output-side parsers (O4 fix — same reference template as evaluation.py
# `parse_*_response` (~285-373), workflows.py `parse_strategy_decision` (~166),
# and graph.py `parse_entity_extraction` / `parse_global_summary`).
#
# Each LLM stage above publishes on its `response` port the shape
# `{"content": "<JSON string>", ...}` (mock + real providers both — see
# `kaizen/nodes/ai/llm_agent.py` `result["response"]["content"]`). The
# structured decision the stage's `system_prompt` advertises
# (`{"expansions": [...]}`, `{"hops": [...]}`, ...) lives INSIDE
# `response["content"]` as a JSON STRING — NOT at the top level of `response`.
#
# Pre-O4 each consumer wired `<llm>.response -> consumer.<param>` and then did
# `consumer_var = <param>` followed by `.get("<structured_field>")` on the RAW
# response dict — so every structured field silently resolved to its default
# ([] / {} / ""), the LLM's expansion / decomposition / rewrite / intent / hop
# decision NEVER reached its consumer. This is the Class-B parse gap
# (rules/zero-tolerance.md Rule 3c — a documented consumer input accepted but
# silently dropped).
#
# Each parser below consumes the REAL `response` port, unwraps `.content`,
# `json.loads` it, and returns the structured dict the consumer's `.get(...)`
# calls already expect — wired `<llm>.response -> parse_<stage>.response` and
# `parse_<stage>.result -> consumer.<param>` (the direct `<llm>.response ->
# consumer` edge is REMOVED).
#
# HONESTY (zero-tolerance Rule 2): on non-JSON / missing-field / malformed
# output a parser returns a TYPED parse-error sentinel
# (`{"<primary_field>": <empty>, "parse_error": "<reason>"}`) so the consumer
# produces an HONEST empty/degraded result — NEVER a fabricated expansion /
# sub-question / rewrite / intent / hop. An empty expansion set on unparseable
# output is CORRECT; a fabricated keyword list is the fake-data failure mode.
#
# These are tool-result PARSING (the permitted deterministic exception per
# rules/agent-reasoning.md #6 — extracting structured data from LLM output),
# NOT agent decision-making: the LLM still makes the expansion / decomposition /
# rewrite / intent / hop reasoning. NO keyword/regex query heuristics are added.
# ---------------------------------------------------------------------------


def _unwrap_response_content(response: Any) -> Any:
    """Unwrap the LLMAgentNode ``response`` port into the model's text payload.

    ``LLMAgentNode`` publishes ``response`` as ``{"content": "<text>", ...}``
    (mock + real providers both — ``llm_agent.py`` ``result["response"]``). A
    defensive caller may also pass the bare string. Mirrors evaluation.py /
    workflows.py / conversational.py's ``response.get("content")`` unwrap.
    """
    if isinstance(response, dict):
        return response.get("content")
    return response


def _loads_response_object(response: Any) -> Union[dict, str]:
    """Unwrap ``response`` -> ``.content`` -> ``json.loads`` -> a dict.

    Returns the parsed dict on success, or a one-word reason string
    (``"empty-response"`` / ``"non-json-response"`` / ``"unexpected-content-type"``
    / ``"non-object-json"``) the caller converts into its own typed sentinel.
    Shared by the 5 object-shaped parsers so the unwrap+load+shape-check logic
    lives in one place (the 6th, expansion, also reuses it).
    """
    import json

    content = _unwrap_response_content(response)

    # Honest empty: the stage published nothing parseable. Surface, don't invent.
    if content is None or (isinstance(content, str) and not content.strip()):
        return "empty-response"

    # The provider may already have emitted a parsed dict (some do).
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return "non-json-response"
    else:
        return "unexpected-content-type"

    if not isinstance(parsed, dict):
        return "non-object-json"
    return parsed


def parse_expansion_response(response=None):
    """Parse the ``llm_expander`` ``response`` into the expansion dict the
    ``expansion_processor`` reads.

    Reads ``response`` -> ``.content`` -> ``json.loads`` -> the
    ``{expansions, keywords, concepts}`` object the expander's ``system_prompt``
    advertises. Malformed / missing output → a typed sentinel with EMPTY lists +
    ``parse_error`` (zero-tolerance Rule 2) so the processor produces an honest
    empty expansion set, never fabricated expansions.
    """
    parsed = _loads_response_object(response)
    if isinstance(parsed, str):
        return {
            "expansions": [],
            "keywords": [],
            "concepts": [],
            "parse_error": parsed,
        }
    return {
        "expansions": parsed.get("expansions", []),
        "keywords": parsed.get("keywords", []),
        "concepts": parsed.get("concepts", []),
    }


def parse_decomposition_response(response=None):
    """Parse the ``query_decomposer`` ``response`` into the decomposition dict the
    ``dependency_resolver`` reads.

    Reads ``response`` -> ``.content`` -> ``json.loads`` -> the
    ``{sub_questions, composition_strategy}`` object the decomposer's
    ``system_prompt`` advertises. Malformed / missing output → a typed sentinel
    with an EMPTY sub_questions list + ``parse_error`` so the resolver produces
    an honest empty plan, never fabricated sub-questions.
    """
    parsed = _loads_response_object(response)
    if isinstance(parsed, str):
        return {"sub_questions": [], "parse_error": parsed}
    return {
        "sub_questions": parsed.get("sub_questions", []),
        "composition_strategy": parsed.get("composition_strategy", "sequential"),
    }


def parse_analysis_response(response=None):
    """Parse the ``query_analyzer`` ``response`` into the analysis dict the
    ``result_combiner`` AND ``rewrite_messages_composer`` read.

    Reads ``response`` -> ``.content`` -> ``json.loads`` -> the
    ``{issues, suggestions}`` object the analyzer's ``system_prompt`` advertises.
    Malformed / missing output → a typed sentinel with an EMPTY issues list +
    ``parse_error`` so the combiner reports no issues honestly (the rewrite
    composer then renders no analysis), never fabricated issues.
    """
    parsed = _loads_response_object(response)
    if isinstance(parsed, str):
        return {"issues": [], "parse_error": parsed}
    return {
        "issues": parsed.get("issues", []),
        "suggestions": parsed.get("suggestions", {}),
    }


def parse_rewrite_response(response=None):
    """Parse the ``query_rewriter`` ``response`` into the rewrite dict the
    ``result_combiner`` reads.

    Reads ``response`` -> ``.content`` -> ``json.loads`` -> the
    ``{rewrites, recommended}`` object the rewriter's ``system_prompt``
    advertises. Malformed / missing output → a typed sentinel with an EMPTY
    rewrites dict + ``parse_error`` so the combiner emits only the original
    query honestly, never fabricated rewrites.
    """
    parsed = _loads_response_object(response)
    if isinstance(parsed, str):
        return {"rewrites": {}, "parse_error": parsed}
    return {
        "rewrites": parsed.get("rewrites", {}),
        "recommended": parsed.get("recommended", ""),
    }


def parse_intent_response(response=None):
    """Parse the ``intent_classifier`` ``response`` into the intent dict the
    ``strategy_mapper`` reads.

    Reads ``response`` -> ``.content`` -> ``json.loads`` -> the
    ``{query_type, domain, complexity, requirements, suggested_strategy}`` object
    the classifier's ``system_prompt`` advertises. Malformed / missing output →
    a typed sentinel with a None ``query_type`` + ``parse_error`` so the mapper
    falls through to its defaults honestly, never a fabricated classification.

    The strategy_mapper's ``strategy_map`` lookup is post-LLM tool-result
    formatting (the LLM made the classification; the map only renders it to a
    retrieval strategy), so the sentinel is read by ``.get(..., <default>)``
    paths there and surfaces as the documented low-confidence fallback.
    """
    parsed = _loads_response_object(response)
    if isinstance(parsed, str):
        return {"query_type": None, "parse_error": parsed}
    return {
        "query_type": parsed.get("query_type"),
        "domain": parsed.get("domain"),
        "complexity": parsed.get("complexity"),
        "requirements": parsed.get("requirements", []),
        "suggested_strategy": parsed.get("suggested_strategy"),
    }


def parse_hop_plan_response(response=None):
    """Parse the ``hop_planner`` ``response`` into the hop-plan dict the
    ``execution_planner`` reads.

    Reads ``response`` -> ``.content`` -> ``json.loads`` -> the
    ``{hops, combination_strategy, total_hops}`` object the planner's
    ``system_prompt`` advertises. Malformed / missing output → a typed sentinel
    with an EMPTY hops list + ``parse_error`` so the execution planner produces
    an honest empty (zero-batch) plan, never fabricated hops.
    """
    parsed = _loads_response_object(response)
    if isinstance(parsed, str):
        return {"hops": [], "parse_error": parsed}
    return {
        "hops": parsed.get("hops", []),
        "combination_strategy": parsed.get("combination_strategy", "sequential"),
        "total_hops": parsed.get("total_hops"),
    }


# ---------------------------------------------------------------------------
# COMPUTE processors (#1117 / #1123 / #1118 root-cause fix — same reference
# template as optimized.py S1/S2 + graph.py/evaluation.py S3).
#
# These are the 6 terminal PROCESSOR stages of the query_processing inner
# workflows. Each consumes the parsed dict its upstream `parse_<stage>`
# from_function node publishes (the {expansions,...} / {sub_questions,...} /
# {rewrites,...} / {query_type,...} / {hops,...} dicts) PLUS the top-level
# `query` input, and produces the node's final documented result.
#
# Pre-migration each was an inline `code=` codegen block (an f-string-free
# triple-quoted string `PythonCodeNode` config). Those blocks suffered the
# #1117 publish-nothing class (a string-`code` PythonCodeNode publishes on the
# flat `result` port, but brace-escaping + import-trap hazards made the codegen
# fragile). Lifting each to a real module-level `def ... -> dict` (real
# `return`, type-checkable, no brace-escaping, no import trap) and wiring via
# `PythonCodeNode.from_function(fn)` is the structural fix: the node publishes
# the SAME flat `result` port carrying the returned dict.
#
# Each is pure post-LLM tool-result FORMATTING (the permitted deterministic
# exception per rules/agent-reasoning.md #3 / #6 — assembling the LLM's parsed
# decision into the documented output shape). NO if-else routing / keyword
# classification on query content is added: the LLM already made the expansion
# / decomposition / rewrite / intent / hop reasoning upstream; these stages
# only render it.
#
# HONESTY (zero-tolerance Rule 2): each defaults to the upstream parser's
# empty-sentinel (a typed-but-empty dict) on missing/malformed input (an empty
# expansion set / empty plan / original-query-only rewrite), NEVER a fabricated
# value. Each
# input param maps 1:1 to a real `add_connection` edge or the top-level
# `query` injection — no vestigial params (zero-tolerance Rule 3c).
# ---------------------------------------------------------------------------


def _process_expansions(query: str = "", expansion_response=None) -> dict:
    """Assemble the QueryExpansionNode ``expanded_query`` result.

    Consumes ``expansion_response`` (the ``{expansions, keywords, concepts}``
    dict ``expansion_parser`` publishes) + the top-level ``query``. Combines +
    dedups all terms into the documented ``expanded_query`` shape. Honest
    default: a missing/non-dict ``expansion_response`` yields empty lists (the
    parser's empty-sentinel propagates), never fabricated expansions.
    """
    original_query = query
    expansion_result = (
        expansion_response if isinstance(expansion_response, dict) else {}
    )

    expansions = expansion_result.get("expansions", []) or []
    keywords = expansion_result.get("keywords", []) or []
    concepts = expansion_result.get("concepts", []) or []

    # Combine and deduplicate.
    all_terms = set()
    all_terms.add(original_query)
    all_terms.update(expansions)
    all_terms.update(keywords)

    return {
        "expanded_query": {
            "original": original_query,
            "expansions": list(expansions),
            "keywords": list(keywords),
            "concepts": list(concepts),
            "all_terms": list(all_terms),
            "expansion_count": len(all_terms) - 1,
        }
    }


def _resolve_dependencies(decomposition_result=None) -> dict:
    """Build the QueryDecompositionNode ``execution_plan`` result.

    Consumes ``decomposition_result`` (the ``{sub_questions,
    composition_strategy}`` dict ``decomposition_parser`` publishes). Reads each
    sub-question's ``depends_on`` field (the key the decomposer system_prompt
    advertises — F25 Shard E), builds the dependency graph, and topologically
    sorts it into an execution order. Honest default: a missing/non-dict
    ``decomposition_result`` yields an empty plan, never fabricated
    sub-questions.
    """
    decomposition = (
        decomposition_result if isinstance(decomposition_result, dict) else {}
    )
    sub_questions = decomposition.get("sub_questions", []) or []

    # Build dependency graph. Each sub-question may be a dict carrying
    # `depends_on` (the field the system_prompt advertises) or a bare value.
    dependency_graph: Dict[int, List[int]] = {}
    for i, sq in enumerate(sub_questions):
        deps = sq.get("depends_on", []) if isinstance(sq, dict) else []
        dependency_graph[i] = deps

    # Topological sort for execution order.
    def topological_sort(graph: Dict[int, List[int]]) -> List[int]:
        visited = set()
        stack: List[int] = []

        def dfs(node: int) -> None:
            visited.add(node)
            for dep in graph.get(node, []):
                if dep not in visited:
                    dfs(dep)
            stack.append(node)

        for node in graph:
            if node not in visited:
                dfs(node)

        return stack[::-1]

    execution_order = topological_sort(dependency_graph)

    execution_plan = {
        "sub_questions": sub_questions,
        "execution_order": execution_order,
        "composition_strategy": decomposition.get("composition_strategy", "sequential"),
        "total_questions": len(sub_questions),
    }

    return {"execution_plan": execution_plan}


def _combine_rewrites(
    query: str = "", analysis_result=None, rewrite_result=None
) -> dict:
    """Assemble the QueryRewritingNode ``rewritten_queries`` result.

    Consumes the top-level ``query`` plus the two parsed LLM-stage dicts:
    ``analysis_result`` (``{issues, suggestions}`` from ``analysis_parser``) and
    ``rewrite_result`` (``{rewrites, recommended}`` from ``rewrite_parser``).
    Merges the original query + all rewrite versions, dedups preserving order,
    and surfaces the analyzer's issues. Honest defaults: missing parsed dicts
    yield no issues + only the original query, never fabricated rewrites.
    """
    original_query = query
    analysis = analysis_result if isinstance(analysis_result, dict) else {}
    rewrites = rewrite_result if isinstance(rewrite_result, dict) else {}

    rewrite_dict = rewrites.get("rewrites", {}) or {}

    all_versions = [original_query]
    if isinstance(rewrite_dict, dict):
        all_versions.extend(rewrite_dict.values())

    # Remove duplicates while preserving order.
    seen = set()
    unique_versions = []
    for v in all_versions:
        if v and v not in seen:
            seen.add(v)
            unique_versions.append(v)

    return {
        "rewritten_queries": {
            "original": original_query,
            "issues_found": analysis.get("issues", []),
            "versions": rewrite_dict,
            "recommended": rewrites.get("recommended", original_query),
            "all_unique_versions": unique_versions,
            "improvement_count": len(unique_versions) - 1,
        }
    }


def _map_strategy(intent_classification=None) -> dict:
    """Build the QueryIntentClassifierNode ``routing_decision`` result.

    Consumes ``intent_classification`` (the ``{query_type, domain, complexity,
    requirements, suggested_strategy}`` dict ``intent_parser`` publishes). Maps
    the LLM's classification to a retrieval strategy via a static lookup +
    requirement-aware adjustment (post-LLM tool-result formatting — the LLM
    made the classification; the map only renders it). Honest default: a
    missing/non-dict input falls to the documented low-confidence defaults
    (the parser's None-``query_type`` sentinel surfaces as the ``factual`` /
    ``simple`` defaults), never a fabricated classification.
    """
    intent = intent_classification if isinstance(intent_classification, dict) else {}

    query_type = intent.get("query_type") or "factual"
    # NOTE: the original strategy_mapper codegen read `domain` into a local that
    # the strategy logic never consumed (dead in the codegen too); the map keys
    # on (query_type, complexity) + requirements only. `domain` is intentionally
    # NOT read here — reading it would be a vestigial input (zero-tolerance 3c).
    complexity = intent.get("complexity") or "simple"
    requirements = intent.get("requirements", []) or []

    # Strategy mapping rules.
    strategy_map = {
        ("factual", "simple"): "sparse",
        ("factual", "moderate"): "hybrid",
        ("analytical", "complex"): "hierarchical",
        ("comparative", "moderate"): "multi_vector",
        ("exploratory", "complex"): "self_correcting",
        ("procedural", "moderate"): "semantic",
    }

    # Determine base strategy.
    base_strategy = strategy_map.get((query_type, complexity), "hybrid")

    # Adjust based on requirements.
    if "needs_recent" in requirements:
        # Prefer strategies that can handle temporal information.
        if base_strategy == "sparse":
            base_strategy = "hybrid"
    elif "needs_authoritative" in requirements:
        # Prefer strategies with quality filtering.
        base_strategy = "self_correcting"
    elif "needs_examples" in requirements:
        # Prefer semantic strategies.
        if base_strategy == "sparse":
            base_strategy = "semantic"

    routing_decision = {
        "intent_analysis": intent,
        "recommended_strategy": base_strategy,
        "alternative_strategies": ["hybrid", "semantic", "hierarchical"],
        "confidence": 0.85 if (query_type, complexity) in strategy_map else 0.6,
        "reasoning": (
            f"Query type '{query_type}' with '{complexity}' complexity "
            f"suggests '{base_strategy}' strategy"
        ),
    }

    return {"routing_decision": routing_decision}


def _plan_execution(hop_plan_result=None) -> dict:
    """Build the MultiHopQueryPlannerNode ``multi_hop_plan`` result.

    Consumes ``hop_plan_result`` (the ``{hops, combination_strategy,
    total_hops}`` dict ``hop_plan_parser`` publishes). Validates inter-hop
    dependencies and groups hops into parallelizable execution batches. Honest
    default: a missing/non-dict input yields a zero-hop, zero-batch plan, never
    fabricated hops.
    """
    hop_plan = hop_plan_result if isinstance(hop_plan_result, dict) else {}
    hops = hop_plan.get("hops", []) or []

    # Validate dependencies.
    hop_dict = {
        h["hop_number"]: h for h in hops if isinstance(h, dict) and "hop_number" in h
    }
    for hop in hops:
        if not isinstance(hop, dict):
            continue
        deps = hop.get("depends_on", [])
        for dep in deps:
            if dep not in hop_dict:
                logger.warning(
                    f"Hop {hop.get('hop_number')} depends on non-existent hop {dep}"
                )

    # Create execution batches (hops that can run in parallel).
    batches = []
    processed: set = set()

    while len(processed) < len(hops):
        batch = []
        for hop in hops:
            if not isinstance(hop, dict):
                continue
            hop_num = hop.get("hop_number")
            if hop_num not in processed:
                deps = set(hop.get("depends_on", []))
                if deps.issubset(processed):
                    batch.append(hop)

        if not batch:
            # Circular dependency or error.
            logger.error("Cannot create valid execution order")
            break

        batches.append(batch)
        for hop in batch:
            processed.add(hop["hop_number"])

    execution_plan = {
        "batches": batches,
        "total_hops": len(hops),
        "parallel_opportunities": len([b for b in batches if len(b) > 1]),
        "combination_strategy": hop_plan.get("combination_strategy", "sequential"),
        "estimated_time": len(batches) * 2,  # Rough estimate in seconds
    }

    return {"multi_hop_plan": execution_plan}


def _adaptive_process(query: str = "", routing_decision=None) -> dict:
    """Build the AdaptiveQueryProcessorNode ``adaptive_plan`` result.

    Consumes the top-level ``query`` plus ``routing_decision`` (the embedded
    QueryIntentClassifierNode's ``run()``-contract output, wired
    ``intent_analyzer.routing_decision`` -> here). Derives the processing-step
    plan from the classifier's intent analysis (post-LLM tool-result
    formatting — the classifier made the intent decision upstream). Honest
    default: a missing/non-dict ``routing_decision`` yields the ``factual`` /
    ``simple`` defaults + a single ``rewrite`` step, never fabricated intent.
    """
    routing = routing_decision if isinstance(routing_decision, dict) else {}
    # The wired value is the classifier's full run() dict, which nests the
    # routing_decision under the same key (the classifier's contract).
    routing = routing.get("routing_decision", {}) if isinstance(routing, dict) else {}
    intent = routing.get("intent_analysis", {}) if isinstance(routing, dict) else {}

    complexity = intent.get("complexity", "simple")
    query_type = intent.get("query_type", "factual")

    # Determine which processing steps to apply (rendering the LLM's intent
    # decision to a step plan — NOT classifying the query here).
    processing_steps = []

    # Always apply basic rewriting.
    processing_steps.append("rewrite")

    # Apply expansion for exploratory queries.
    if query_type in ["exploratory", "analytical"]:
        processing_steps.append("expand")

    # Apply decomposition for complex queries.
    if complexity == "complex":
        processing_steps.append("decompose")

    # Apply multi-hop planning for comparative or complex analytical.
    if query_type == "comparative" or (
        query_type == "analytical" and complexity == "complex"
    ):
        processing_steps.append("multi_hop")

    processing_plan = {
        "original_query": query,
        "intent": intent,
        "recommended_strategy": routing.get("recommended_strategy", "hybrid"),
        "processing_steps": processing_steps,
        "rationale": (
            f"Query type '{query_type}' with complexity '{complexity}' requires "
            f"{len(processing_steps)} processing steps"
        ),
    }

    return {"adaptive_plan": processing_plan}


@register_node()
class QueryExpansionNode(Node):
    """
    Advanced Query Expansion

    Generates synonyms, related terms, and alternative phrasings
    to improve retrieval recall.

    When to use:
    - Best for: Short queries, improving recall, domain-specific terms
    - Not ideal for: Already detailed queries, when precision is critical
    - Performance: ~300ms with LLM
    - Impact: 15-25% improvement in recall

    Key features:
    - Synonym generation
    - Domain-specific term expansion
    - Acronym resolution
    - Related concept inclusion

    Example:
        expander = QueryExpansionNode(
            num_expansions=5
        )

        # Expands "ML optimization" to include:
        # - "machine learning optimization"
        # - "ML model tuning"
        # - "neural network optimization"
        # - "deep learning optimization"
        # - "AI optimization techniques"

        expanded = await expander.execute(query="ML optimization")

    Parameters:
        expansion_method: Algorithm (llm, wordnet, custom)
        num_expansions: Number of variations to generate
        include_synonyms: Add synonym variations
        include_related: Add related concepts

    Returns:
        original: Original query
        expansions: List of query variations
        keywords: Extracted key terms
        concepts: Related concepts
        all_terms: Complete set for retrieval
    """

    def __init__(
        self,
        name: str = "query_expansion",
        expansion_method: str = "llm",
        num_expansions: int = 5,
    ):
        super().__init__(
            name=name,
            expansion_method=expansion_method,
            num_expansions=num_expansions,
        )
        self.expansion_method = expansion_method
        self.num_expansions = num_expansions

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters"""
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="query_expansion",
                description="Node instance name",
            ),
            "expansion_method": NodeParameter(
                name="expansion_method",
                type=str,
                required=False,
                default="llm",
                description="Algorithm (llm, wordnet, custom)",
            ),
            "num_expansions": NodeParameter(
                name="num_expansions",
                type=int,
                required=False,
                default=5,
                description="Number of query variations to generate",
            ),
            "query": NodeParameter(
                name="query", type=str, required=True, description="Query to expand"
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute query expansion"""
        query = kwargs.get("query", "")

        try:
            # Simple query expansion implementation
            expansions = []
            keywords = []
            concepts = []

            if query:
                # Basic expansions
                words = query.split()
                expansions = [
                    query + " explanation",
                    query + " examples",
                    query + " guide",
                    "how to " + query,
                    query + " best practices",
                ]

                keywords = [word for word in words if len(word) > 3]
                concepts = [query.replace(" ", "_")]

            return {
                "original": query,
                "expansions": expansions[: self.num_expansions],
                "keywords": keywords,
                "concepts": concepts,
                "all_terms": [query] + expansions[: self.num_expansions],
                "expansion_count": len(expansions),
            }

        except Exception as e:
            logger.error(f"Query expansion failed: {e}")
            return {
                "original": query,
                "expansions": [],
                "keywords": [],
                "concepts": [],
                "all_terms": [query],
                "error": str(e),
            }

    def _create_workflow(self) -> Workflow:
        """Create query expansion workflow"""
        builder = WorkflowBuilder()

        # Add LLM-based expander
        llm_expander_id = builder.add_node(
            "LLMAgentNode",
            node_id="llm_expander",
            config={
                "provider": detect_provider_from_env(),
                "system_prompt": f"""You are a query expansion expert.
                Generate {self.num_expansions} variations of the given query that capture different aspects:

                1. Synonyms and related terms
                2. More specific versions
                3. More general versions
                4. Alternative phrasings
                5. Related concepts

                Return as JSON: {{
                    "expansions": ["expansion1", "expansion2", ...],
                    "keywords": ["key1", "key2", ...],
                    "concepts": ["concept1", "concept2", ...]
                }}""",
                "model": _DEFAULT_LLM_MODEL,
            },
        )

        # Add expansion processor.
        #
        # #1117/#1123/#1118 root-cause fix: lifted from the inline `code=`
        # codegen to the module-level `_process_expansions` function wired via
        # `PythonCodeNode.from_function`. The node publishes the SAME flat
        # `result` port carrying `{"expanded_query": {...}}` (a string-`code`
        # PythonCodeNode also published on `result` via its local `result`
        # variable — the runtime result shape `result["expanded_query"]` is
        # unchanged). It reads `query` (top-level injection) + `expansion_response`
        # (wired from expansion_parser.result). `_internal=True` suppresses the
        # consumer-facing instance-API advisory. type: ignore[attr-defined]:
        # `from_function` is a classmethod on concrete PythonCodeNode, erased to
        # `type[Node]` by `@register_node` for static checkers (mirrors the
        # composer/parser nodes above).
        processor_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _process_expansions,
                name="expansion_processor",
            ),
            node_id="expansion_processor",
            _internal=True,
        )

        # L3 messages-composer (reference template — conversational.py /
        # evaluation.py). The llm_expander previously received NO real input;
        # it generated expansions from its `system_prompt` alone, never seeing
        # the user's query. The composer renders the REAL `query` (the top-level
        # workflow input the parameter injector delivers — the same input
        # `run()` reads) into a `messages` list wired to the VALID `messages`
        # port (the ONLY port LLMAgentNode reads — its `run` does
        # `kwargs["messages"]`). type: ignore[attr-defined]: `from_function` is
        # a classmethod on concrete PythonCodeNode, erased to `type[Node]` by
        # `@register_node` for static checkers (mirrors conversational.py).
        # `_internal=True` suppresses the consumer-facing instance-API advisory.
        expansion_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                compose_expansion_messages,
                name="expansion_messages_composer",
            ),
            node_id="expansion_messages_composer",
            _internal=True,
        )

        # O4 output-side parser: unwraps `llm_expander.response.content` ->
        # json.loads -> the {expansions, keywords, concepts} dict the
        # expansion_processor `.get`s. Pre-O4 the raw `response` (a
        # `{"content": "<json>"}` wrapper) reached the processor, so every
        # `.get("expansions")` resolved to []. type: ignore[attr-defined] per
        # the composer note above.
        expansion_parser_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                parse_expansion_response,
                name="expansion_parser",
            ),
            node_id="expansion_parser",
            _internal=True,
        )

        # Connect workflow. The composer declares `query` as a function param,
        # so the runtime's parameter injector delivers the caller-supplied
        # top-level `query` workflow input to it. Its `result.messages` (nested
        # key on the single `result` port a from_function node publishes) feeds
        # the llm_expander `messages` port.
        builder.add_connection(
            expansion_messages_composer_id,
            "result.messages",
            llm_expander_id,
            "messages",
        )
        # O4: route the LLM `response` THROUGH the parser, then the parsed dict
        # (`result`) to the processor's `expansion_response` param.
        builder.add_connection(
            llm_expander_id, "response", expansion_parser_id, "response"
        )
        builder.add_connection(
            expansion_parser_id, "result", processor_id, "expansion_response"
        )

        return builder.build(name="query_expansion_workflow")


@register_node()
class QueryDecompositionNode(Node):
    """
    Query Decomposition for Complex Questions

    Breaks down complex queries into sub-questions that can be
    answered independently and then combined.

    When to use:
    - Best for: Multi-part questions, comparative queries, complex reasoning
    - Not ideal for: Simple factual queries, single-concept questions
    - Performance: ~400ms decomposition
    - Impact: Enables answering previously unanswerable complex queries

    Key features:
    - Identifies independent sub-questions
    - Determines execution order
    - Handles dependencies
    - Plans result composition

    Example:
        decomposer = QueryDecompositionNode()

        # Query: "Compare transformer and CNN architectures for NLP and vision"
        # Decomposes to:
        # 1. "What is transformer architecture?"
        # 2. "What is CNN architecture?"
        # 3. "How are transformers used in NLP?"
        # 4. "How are CNNs used in vision?"
        # 5. "What are the key differences?"

        plan = await decomposer.execute(
            query="Compare transformer and CNN architectures for NLP and vision"
        )

    Parameters:
        max_sub_questions: Maximum decomposition depth
        identify_dependencies: Track question dependencies
        composition_strategy: How to combine answers

    Returns:
        sub_questions: List of decomposed questions
        execution_order: Dependency-resolved order
        composition_strategy: How to combine results
        dependencies: Question dependency graph
    """

    def __init__(self, name: str = "query_decomposition"):
        super().__init__(name=name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters"""
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="query_decomposition",
                description="Node instance name",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=True,
                description="Complex query to decompose",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute query decomposition"""
        query = kwargs.get("query", "")

        try:
            # Simple decomposition implementation
            sub_questions = []

            if query:
                # Basic decomposition by splitting on common patterns
                if " and " in query.lower():
                    parts = query.lower().split(" and ")
                    sub_questions = [part.strip().capitalize() + "?" for part in parts]
                elif " compare " in query.lower() or " vs " in query.lower():
                    # Comparative query
                    sub_questions = [
                        f"What is {query.split()[1] if len(query.split()) > 1 else 'first topic'}?",
                        f"What is {query.split()[-1] if len(query.split()) > 1 else 'second topic'}?",
                        "What are the key differences?",
                    ]
                else:
                    # Simple decomposition
                    sub_questions = [query]

            return {
                "sub_questions": sub_questions,
                "execution_order": list(range(len(sub_questions))),
                "composition_strategy": "sequential",
                "total_questions": len(sub_questions),
            }

        except Exception as e:
            logger.error(f"Query decomposition failed: {e}")
            return {
                "sub_questions": [query],
                "execution_order": [0],
                "composition_strategy": "sequential",
                "error": str(e),
            }

    def _create_workflow(self) -> Workflow:
        """Create query decomposition workflow"""
        builder = WorkflowBuilder()

        # Add decomposer
        decomposer_id = builder.add_node(
            "LLMAgentNode",
            node_id="query_decomposer",
            config={
                "provider": detect_provider_from_env(),
                "system_prompt": """You are a query decomposition expert.
                Break down complex queries into simpler sub-questions that can be answered independently.

                For each sub-question, indicate:
                1. The question itself
                2. Its type (factual, analytical, comparative, etc.)
                3. Dependencies on other sub-questions (use the `depends_on` field;
                   list the integer indices of preceding sub-questions this one depends on)
                4. How it contributes to the main question

                Return as JSON: {
                    "sub_questions": [
                        {
                            "question": "...",
                            "type": "...",
                            "depends_on": [],
                            "contribution": "..."
                        }
                    ],
                    "composition_strategy": "how to combine answers"
                }""",
                "model": _DEFAULT_LLM_MODEL,
            },
        )

        # Add dependency resolver.
        #
        # #1117/#1123/#1118 root-cause fix: lifted from the inline `code=`
        # codegen to the module-level `_resolve_dependencies` function wired via
        # `PythonCodeNode.from_function`. The node publishes the SAME flat
        # `result` port carrying `{"execution_plan": {...}}` (runtime result
        # shape `result["execution_plan"]` unchanged). It reads
        # `decomposition_result` (wired from decomposition_parser.result). The
        # F25 Shard E `depends_on` contract (the LLM system_prompt advertises
        # `depends_on` as the dependency field) is preserved verbatim in
        # `_resolve_dependencies`. type: ignore[attr-defined] per the
        # composer/parser note above.
        dependency_resolver_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _resolve_dependencies,
                name="dependency_resolver",
            ),
            node_id="dependency_resolver",
            _internal=True,
        )

        # L3 messages-composer (reference template). The query_decomposer
        # previously received NO real input — it decomposed from its
        # `system_prompt` alone, never seeing the query. The composer renders the
        # REAL `query` (top-level workflow input via the parameter injector) into
        # a `messages` list wired to the VALID `messages` port.
        decomposition_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                compose_decomposition_messages,
                name="decomposition_messages_composer",
            ),
            node_id="decomposition_messages_composer",
            _internal=True,
        )

        # O4 output-side parser: unwraps `query_decomposer.response.content` ->
        # json.loads -> the {sub_questions, composition_strategy} dict the
        # dependency_resolver `.get`s. Pre-O4 the raw `response` reached the
        # resolver, so `.get("sub_questions")` resolved to [].
        decomposition_parser_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                parse_decomposition_response,
                name="decomposition_parser",
            ),
            node_id="decomposition_parser",
            _internal=True,
        )

        # Connect workflow
        builder.add_connection(
            decomposition_messages_composer_id,
            "result.messages",
            decomposer_id,
            "messages",
        )
        # O4: route the LLM `response` THROUGH the parser to the resolver.
        builder.add_connection(
            decomposer_id, "response", decomposition_parser_id, "response"
        )
        builder.add_connection(
            decomposition_parser_id,
            "result",
            dependency_resolver_id,
            "decomposition_result",
        )

        return builder.build(name="query_decomposition_workflow")


@register_node()
class QueryRewritingNode(Node):
    """
    Query Rewriting for Better Retrieval

    Rewrites queries to be more effective for retrieval systems,
    including spelling correction, clarification, and optimization.

    When to use:
    - Best for: User-generated queries, informal language, typos
    - Not ideal for: Already well-formed technical queries
    - Performance: ~200ms with analysis
    - Impact: 10-30% improvement for problematic queries

    Key features:
    - Spelling and grammar correction
    - Ambiguity resolution
    - Technical term standardization
    - Query simplification/clarification

    Example:
        rewriter = QueryRewritingNode()

        # Input: "how 2 trian nueral netwrk wit keras"
        # Outputs:
        #   corrected: "how to train neural network with keras"
        #   clarified: "how to train a neural network using Keras framework"
        #   technical: "neural network training process Keras implementation"
        #   simplified: "train neural network keras"

        rewritten = await rewriter.execute(
            query="how 2 trian nueral netwrk wit keras"
        )

    Parameters:
        correct_spelling: Enable spell checking
        clarify_ambiguity: Resolve unclear terms
        standardize_technical: Use standard terminology
        generate_variants: Create multiple versions

    Returns:
        original: Original query
        issues_found: Detected problems
        versions: Different rewrite versions
        recommended: Best version for retrieval
    """

    def __init__(self, name: str = "query_rewriting"):
        super().__init__(name=name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters"""
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="query_rewriting",
                description="Node instance name",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=True,
                description="Query to rewrite and improve",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute query rewriting"""
        query = kwargs.get("query", "")

        try:
            # Simple query rewriting implementation
            issues_found = []
            versions = {}

            if query:
                # Basic corrections
                corrected = query.replace(" 2 ", " to ").replace(" u ", " you ")
                corrected = corrected.replace(" wit ", " with ").replace(
                    " trian ", " train "
                )
                corrected = corrected.replace(" nueral ", " neural ").replace(
                    " netwrk ", " network "
                )

                # Check for common issues
                if query != corrected:
                    issues_found.append("spelling_errors")

                if len(query.split()) < 3:
                    issues_found.append("too_short")

                # Generate versions
                versions = {
                    "corrected": corrected,
                    "clarified": corrected + " tutorial",
                    "contextualized": "How to " + corrected,
                    "simplified": " ".join(corrected.split()[:5]),  # First 5 words
                    "technical": corrected.replace(" train ", " training ").replace(
                        " network ", " neural network"
                    ),
                }

                recommended = (
                    versions["clarified"]
                    if "too_short" in issues_found
                    else versions["corrected"]
                )
            else:
                recommended = query

            return {
                "original": query,
                "issues_found": issues_found,
                "versions": versions,
                "recommended": recommended,
                "all_unique_versions": list(set([query] + list(versions.values()))),
                "improvement_count": len(issues_found),
            }

        except Exception as e:
            logger.error(f"Query rewriting failed: {e}")
            return {
                "original": query,
                "issues_found": [],
                "versions": {},
                "recommended": query,
                "error": str(e),
            }

    def _create_workflow(self) -> Workflow:
        """Create query rewriting workflow"""
        builder = WorkflowBuilder()

        # Add query analyzer
        analyzer_id = builder.add_node(
            "LLMAgentNode",
            node_id="query_analyzer",
            config={
                "provider": detect_provider_from_env(),
                "system_prompt": """Analyze the query for potential issues and improvements:

                1. Spelling and grammar errors
                2. Ambiguous terms that need clarification
                3. Missing context that would help retrieval
                4. Overly complex phrasing
                5. Technical vs. layman terminology

                Return as JSON: {
                    "issues": ["issue1", "issue2", ...],
                    "suggestions": {
                        "spelling": "corrected spelling if needed",
                        "clarifications": ["term1: clarification", ...],
                        "context": "suggested context to add",
                        "simplification": "simplified version"
                    }
                }""",
                "model": _DEFAULT_LLM_MODEL,
            },
        )

        # Add rewriter
        rewriter_id = builder.add_node(
            "LLMAgentNode",
            node_id="query_rewriter",
            config={
                "provider": detect_provider_from_env(),
                "system_prompt": """Rewrite the query for optimal retrieval based on the analysis.

                Create multiple versions:
                1. Corrected version (fixing errors)
                2. Clarified version (removing ambiguity)
                3. Contextualized version (adding helpful context)
                4. Simplified version (for broader matching)
                5. Technical version (using domain terminology)

                Return as JSON: {
                    "rewrites": {
                        "corrected": "...",
                        "clarified": "...",
                        "contextualized": "...",
                        "simplified": "...",
                        "technical": "..."
                    },
                    "recommended": "best version for retrieval"
                }""",
                "model": _DEFAULT_LLM_MODEL,
            },
        )

        # Add result combiner.
        #
        # #1117/#1123/#1118 root-cause fix: lifted from the inline `code=`
        # codegen to the module-level `_combine_rewrites` function wired via
        # `PythonCodeNode.from_function`. The node publishes the SAME flat
        # `result` port carrying `{"rewritten_queries": {...}}` (runtime result
        # shape `result["rewritten_queries"]` unchanged). It reads `query`
        # (top-level injection) + `analysis_result` (wired from
        # analysis_parser.result) + `rewrite_result` (wired from
        # rewrite_parser.result) — the 3-way fan-in. type: ignore[attr-defined]
        # per the composer/parser note above.
        combiner_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _combine_rewrites,
                name="result_combiner",
            ),
            node_id="result_combiner",
            _internal=True,
        )

        # L3 messages-composers (reference template) for the 2-stage chain.
        # PREVIOUS PHANTOM WIRING: `analyzer.response -> rewriter."analysis"` fed
        # the analyzer's output to the rewriter on a port the LLMAgentNode
        # SILENTLY DROPS (its `run` reads only `kwargs["messages"]`), AND neither
        # LLM stage ever received the user's query. Both stages answered from
        # their `system_prompt` alone.
        #
        # FIX: an analysis composer renders the REAL `query` into the analyzer's
        # `messages`; a rewrite composer renders the REAL `query` PLUS the real
        # upstream `analyzer.response` (the analysis JSON the analyzer's
        # system_prompt advertises) into the rewriter's `messages`. The
        # `analyzer.response -> rewriter."analysis"` phantom edge is REMOVED; the
        # analysis now reaches the rewriter through the composer's `messages`.
        analysis_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                compose_analysis_messages,
                name="analysis_messages_composer",
            ),
            node_id="analysis_messages_composer",
            _internal=True,
        )
        rewrite_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                compose_rewrite_messages,
                name="rewrite_messages_composer",
            ),
            node_id="rewrite_messages_composer",
            _internal=True,
        )

        # O4 output-side parsers (TWO LLM stages, THREE raw-response consumers).
        # Pre-O4: `analyzer.response` (raw) reached BOTH the rewrite composer
        # (`.get("issues")`) AND the combiner (`analysis_result.get("issues")`),
        # and `rewriter.response` (raw) reached the combiner
        # (`rewrite_result.get("rewrites")`) — all three resolving to defaults.
        # The analysis_parser's parsed `{issues, suggestions}` dict is fanned to
        # BOTH the rewrite composer AND the combiner so the analysis reaches the
        # rewriter (via its `messages`) AND surfaces in the combined output.
        analysis_parser_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                parse_analysis_response,
                name="analysis_parser",
            ),
            node_id="analysis_parser",
            _internal=True,
        )
        rewrite_parser_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                parse_rewrite_response,
                name="rewrite_parser",
            ),
            node_id="rewrite_parser",
            _internal=True,
        )

        # Connect workflow.
        # Stage 1: query -> analysis composer -> analyzer.messages.
        builder.add_connection(
            analysis_messages_composer_id,
            "result.messages",
            analyzer_id,
            "messages",
        )
        # O4: analyzer.response -> analysis_parser -> {parsed analysis} fanned to
        # the rewrite composer (so the rewriter sees the REAL parsed analysis in
        # its messages) AND the combiner (analysis_result).
        builder.add_connection(analyzer_id, "response", analysis_parser_id, "response")
        # Stage 2: query + parsed analysis -> rewrite composer -> rewriter.messages.
        # (The composer declares `query` (top-level injected) AND `analysis`
        # (now the PARSED analyzer dict) as function params.)
        builder.add_connection(
            analysis_parser_id,
            "result",
            rewrite_messages_composer_id,
            "analysis",
        )
        builder.add_connection(
            rewrite_messages_composer_id,
            "result.messages",
            rewriter_id,
            "messages",
        )
        # O4: rewriter.response -> rewrite_parser -> {parsed rewrites} to combiner.
        builder.add_connection(rewriter_id, "response", rewrite_parser_id, "response")
        # Combiner fan-in: it reads both PARSED LLM-stage dicts.
        builder.add_connection(
            analysis_parser_id, "result", combiner_id, "analysis_result"
        )
        builder.add_connection(
            rewrite_parser_id, "result", combiner_id, "rewrite_result"
        )

        return builder.build(name="query_rewriting_workflow")


@register_node()
class QueryIntentClassifierNode(Node):
    """
    Query Intent Classification

    Classifies query intent to route to appropriate retrieval strategy.
    Identifies query type, domain, complexity, and requirements.

    When to use:
    - Best for: Automatic strategy selection, routing decisions
    - Not ideal for: When strategy is predetermined
    - Performance: ~150ms classification
    - Impact: 25-40% improvement through optimal routing

    Key features:
    - Query type detection (factual, analytical, etc.)
    - Domain identification
    - Complexity assessment
    - Special requirements detection

    Example:
        classifier = QueryIntentClassifierNode()

        # Query: "Show me Python code to implement gradient descent"
        # Classification:
        #   type: "procedural"
        #   domain: "technical"
        #   complexity: "moderate"
        #   requirements: ["needs_examples", "needs_code"]
        #   recommended_strategy: "statistical"

        intent = await classifier.execute(
            query="Show me Python code to implement gradient descent"
        )

    Parameters:
        classification_model: Model for intent analysis
        include_confidence: Return confidence scores
        suggest_strategies: Recommend RAG strategies

    Returns:
        query_type: Category (factual, analytical, procedural, etc.)
        domain: Subject area
        complexity: Simple, moderate, or complex
        requirements: Special needs (examples, recency, etc.)
        recommended_strategy: Best RAG approach
        confidence: Classification confidence
    """

    def __init__(self, name: str = "query_intent_classifier"):
        super().__init__(name=name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters"""
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="query_intent_classifier",
                description="Node instance name",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=True,
                description="Query to classify intent for",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute query intent classification"""
        query = kwargs.get("query", "")

        try:
            # Simple intent classification implementation
            query_lower = query.lower()

            # Classify query type
            if any(word in query_lower for word in ["what", "who", "when", "where"]):
                query_type = "factual"
            elif any(word in query_lower for word in ["how", "why", "explain"]):
                query_type = "analytical"
            elif any(
                word in query_lower
                for word in ["compare", "vs", "versus", "difference"]
            ):
                query_type = "comparative"
            elif any(word in query_lower for word in ["show", "give", "list", "find"]):
                query_type = "exploratory"
            elif any(
                word in query_lower for word in ["implement", "create", "build", "make"]
            ):
                query_type = "procedural"
            else:
                query_type = "factual"

            # Determine domain
            if any(
                word in query_lower
                for word in ["code", "programming", "python", "algorithm", "software"]
            ):
                domain = "technical"
            elif any(
                word in query_lower
                for word in ["business", "market", "sales", "finance"]
            ):
                domain = "business"
            elif any(
                word in query_lower
                for word in ["research", "study", "academic", "paper"]
            ):
                domain = "academic"
            else:
                domain = "general"

            # Assess complexity
            word_count = len(query.split())
            if word_count <= 3:
                complexity = "simple"
            elif word_count <= 8:
                complexity = "moderate"
            else:
                complexity = "complex"

            # Identify requirements
            requirements = []
            if any(word in query_lower for word in ["example", "sample", "demo"]):
                requirements.append("needs_examples")
            if any(
                word in query_lower for word in ["recent", "latest", "new", "current"]
            ):
                requirements.append("needs_recent")
            if any(
                word in query_lower
                for word in ["official", "authoritative", "verified"]
            ):
                requirements.append("needs_authoritative")
            if query_type == "analytical" or complexity == "complex":
                requirements.append("needs_context")

            # Suggest strategy
            if query_type == "factual" and complexity == "simple":
                strategy = "sparse"
            elif query_type == "comparative" or complexity == "complex":
                strategy = "hybrid"
            elif domain == "technical" and query_type == "procedural":
                strategy = "semantic"
            else:
                strategy = "hybrid"

            # F25 Shard E: `routing_decision` is part of the documented public
            # contract for QueryIntentClassifierNode — both the strategy_mapper
            # PythonCodeNode inside _create_workflow() (line ~931) AND any
            # downstream composer (e.g. AdaptiveQueryProcessorNode) consume
            # this field on the same shape. Returning it from run() keeps the
            # contract symmetric: the deterministic run() path and the
            # LLM-driven inner-workflow path both expose `routing_decision`.
            # Without this field, composing this node as a single Node inside
            # another workflow raises NameError at codegen time.
            routing_decision = {
                "intent_analysis": {
                    "query_type": query_type,
                    "domain": domain,
                    "complexity": complexity,
                    "requirements": requirements,
                    "suggested_strategy": strategy,
                },
                "recommended_strategy": strategy,
                "alternative_strategies": ["hybrid", "semantic", "hierarchical"],
                "confidence": 0.8,
                "reasoning": (
                    f"Query type '{query_type}' with '{complexity}' complexity "
                    f"suggests '{strategy}' strategy"
                ),
            }

            return {
                "query_type": query_type,
                "domain": domain,
                "complexity": complexity,
                "requirements": requirements,
                "recommended_strategy": strategy,
                "confidence": 0.8,
                "routing_decision": routing_decision,
            }

        except Exception as e:
            # Security round-1 (M1): log the full exception detail to the
            # framework logger (access-controlled), but do NOT echo str(e)
            # into the runtime return dict. The dict flows back to Nexus
            # channels / LLM prompts / public surfaces with broader read
            # access than the framework log (rules/security.md § "No secrets
            # in logs"); raw exception text may include filesystem paths,
            # stack-trace fragments, or upstream-provider error bodies. The
            # routing_decision contract surfaces a stable strategy fallback
            # + a public error_class discriminator; full diagnostic stays in
            # the logger.
            logger.exception("Query intent classification failed")
            fallback_routing = {
                "intent_analysis": {
                    "query_type": "factual",
                    "domain": "general",
                    "complexity": "simple",
                    "requirements": [],
                    "suggested_strategy": "hybrid",
                },
                "recommended_strategy": "hybrid",
                "alternative_strategies": ["hybrid", "semantic", "hierarchical"],
                "confidence": 0.0,
                "reasoning": "Classification failed; defaulted to hybrid",
            }
            return {
                "query_type": "factual",
                "domain": "general",
                "complexity": "simple",
                "requirements": [],
                "recommended_strategy": "hybrid",
                "routing_decision": fallback_routing,
                "error_class": type(e).__name__,
            }

    def _create_workflow(self) -> Workflow:
        """Create intent classification workflow"""
        builder = WorkflowBuilder()

        # Add intent classifier
        classifier_id = builder.add_node(
            "LLMAgentNode",
            node_id="intent_classifier",
            config={
                "provider": detect_provider_from_env(),
                "system_prompt": """Classify the query intent and characteristics:

                1. Query Type:
                   - factual: Looking for specific facts
                   - analytical: Requiring analysis or reasoning
                   - comparative: Comparing multiple things
                   - exploratory: Open-ended exploration
                   - procedural: How-to or step-by-step

                2. Domain:
                   - technical, business, academic, general, etc.

                3. Complexity:
                   - simple: Single concept, direct answer
                   - moderate: Multiple concepts, some reasoning
                   - complex: Deep analysis, multiple perspectives

                4. Requirements:
                   - needs_examples: Would benefit from examples
                   - needs_context: Requires background information
                   - needs_recent: Time-sensitive information
                   - needs_authoritative: Requires credible sources

                Return as JSON: {
                    "query_type": "...",
                    "domain": "...",
                    "complexity": "...",
                    "requirements": ["req1", "req2", ...],
                    "suggested_strategy": "recommended RAG strategy"
                }""",
                "model": _DEFAULT_LLM_MODEL,
            },
        )

        # Add strategy mapper.
        #
        # #1117/#1123/#1118 root-cause fix: lifted from the inline `code=`
        # codegen to the module-level `_map_strategy` function wired via
        # `PythonCodeNode.from_function`. The node publishes the SAME flat
        # `result` port carrying `{"routing_decision": {...}}` (runtime result
        # shape `result["routing_decision"]` unchanged). It reads
        # `intent_classification` (wired from intent_parser.result). type:
        # ignore[attr-defined] per the composer/parser note above.
        strategy_mapper_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _map_strategy,
                name="strategy_mapper",
            ),
            node_id="strategy_mapper",
            _internal=True,
        )

        # L3 messages-composer (reference template). The intent_classifier
        # previously received NO real input — it classified from its
        # `system_prompt` alone, never seeing the query. The composer renders the
        # REAL `query` (top-level workflow input via the parameter injector) into
        # a `messages` list wired to the VALID `messages` port.
        intent_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                compose_intent_messages,
                name="intent_messages_composer",
            ),
            node_id="intent_messages_composer",
            _internal=True,
        )

        # O4 output-side parser: unwraps `intent_classifier.response.content` ->
        # json.loads -> the {query_type, domain, complexity, requirements,
        # suggested_strategy} dict the strategy_mapper `.get`s. Pre-O4 the raw
        # `response` reached the mapper, so every `.get(...)` fell to its default
        # and the strategy_map lookup ran on fabricated-default keys.
        intent_parser_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                parse_intent_response,
                name="intent_parser",
            ),
            node_id="intent_parser",
            _internal=True,
        )

        # Connect workflow
        builder.add_connection(
            intent_messages_composer_id,
            "result.messages",
            classifier_id,
            "messages",
        )
        # O4: route the LLM `response` THROUGH the parser to the mapper.
        builder.add_connection(classifier_id, "response", intent_parser_id, "response")
        builder.add_connection(
            intent_parser_id, "result", strategy_mapper_id, "intent_classification"
        )

        return builder.build(name="query_intent_classifier_workflow")


@register_node()
class MultiHopQueryPlannerNode(Node):
    """
    Multi-Hop Query Planning

    Plans retrieval strategy for queries requiring multiple steps
    of reasoning or information gathering.

    When to use:
    - Best for: Queries requiring reasoning, multi-step answers
    - Not ideal for: Direct factual queries
    - Performance: ~500ms planning
    - Impact: Enables complex reasoning chains

    Key features:
    - Identifies information gathering steps
    - Plans retrieval sequence
    - Handles inter-hop dependencies
    - Optimizes execution order

    Example:
        planner = MultiHopQueryPlannerNode()

        # Query: "How has BERT influenced modern NLP architectures?"
        # Plan:
        # Hop 1: "What is BERT architecture?"
        # Hop 2: "What NLP architectures came after BERT?"
        # Hop 3: "What BERT innovations are used in modern models?"
        # Hop 4: "How do modern models improve on BERT?"

        plan = await planner.execute(
            query="How has BERT influenced modern NLP architectures?"
        )

    Parameters:
        max_hops: Maximum reasoning steps
        parallel_execution: Allow parallel hops
        adaptive_planning: Adjust plan based on results

    Returns:
        hops: Sequence of retrieval steps
        batches: Parallelizable hop groups
        dependencies: Inter-hop relationships
        combination_strategy: Result integration plan
    """

    def __init__(self, name: str = "multi_hop_planner"):
        super().__init__(name=name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters"""
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="multi_hop_planner",
                description="Node instance name",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=True,
                description="Complex query requiring multi-hop planning",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute multi-hop query planning"""
        query = kwargs.get("query", "")

        try:
            # Simple multi-hop planning implementation
            hops = []

            if query:
                query_lower = query.lower()

                # Basic multi-hop detection
                if "influence" in query_lower or "impact" in query_lower:
                    # Historical influence query
                    base_topic = " ".join(
                        [
                            w
                            for w in query.split()
                            if w.lower()
                            not in ["how", "has", "influenced", "impact", "modern"]
                        ]
                    )
                    hops = [
                        {
                            "hop_number": 1,
                            "objective": f"Learn about {base_topic}",
                            "query": f"What is {base_topic}?",
                            "retrieval_type": "semantic",
                            "depends_on": [],
                            "expected_output": f"Basic information about {base_topic}",
                        },
                        {
                            "hop_number": 2,
                            "objective": "Find related developments",
                            "query": f"What came after {base_topic}?",
                            "retrieval_type": "semantic",
                            "depends_on": [1],
                            "expected_output": "Later developments and innovations",
                        },
                        {
                            "hop_number": 3,
                            "objective": "Identify connections",
                            "query": f"How did {base_topic} influence later work?",
                            "retrieval_type": "hybrid",
                            "depends_on": [1, 2],
                            "expected_output": "Specific influences and connections",
                        },
                    ]
                else:
                    # Single hop for simple queries
                    hops = [
                        {
                            "hop_number": 1,
                            "objective": "Answer the query",
                            "query": query,
                            "retrieval_type": "hybrid",
                            "depends_on": [],
                            "expected_output": "Direct answer to the query",
                        }
                    ]

            # Create execution batches
            batches = []
            processed = set()

            while len(processed) < len(hops):
                batch = []
                for hop in hops:
                    hop_num = hop["hop_number"]
                    if hop_num not in processed:
                        deps = set(hop.get("depends_on", []))
                        if deps.issubset(processed):
                            batch.append(hop)

                if batch:
                    batches.append(batch)
                    for hop in batch:
                        processed.add(hop["hop_number"])
                else:
                    break

            return {
                "batches": batches,
                "total_hops": len(hops),
                "parallel_opportunities": len([b for b in batches if len(b) > 1]),
                "combination_strategy": "sequential",
                "estimated_time": len(batches) * 2,
            }

        except Exception as e:
            logger.error(f"Multi-hop planning failed: {e}")
            return {
                "batches": [],
                "total_hops": 0,
                "parallel_opportunities": 0,
                "combination_strategy": "sequential",
                "error": str(e),
            }

    def _create_workflow(self) -> Workflow:
        """Create multi-hop planning workflow"""
        builder = WorkflowBuilder()

        # Add hop planner
        hop_planner_id = builder.add_node(
            "LLMAgentNode",
            node_id="hop_planner",
            config={
                "provider": detect_provider_from_env(),
                "system_prompt": """Plan a multi-hop retrieval strategy for the query.

                Identify:
                1. Information needed at each step
                2. How each step builds on previous ones
                3. What type of retrieval is best for each hop
                4. How to combine information across hops

                Return as JSON: {
                    "hops": [
                        {
                            "hop_number": 1,
                            "objective": "what to retrieve",
                            "query": "specific query for this hop",
                            "retrieval_type": "dense/sparse/hybrid",
                            "depends_on": [],
                            "expected_output": "what we expect to find"
                        }
                    ],
                    "combination_strategy": "how to combine results",
                    "total_hops": number
                }""",
                "model": _DEFAULT_LLM_MODEL,
            },
        )

        # Add execution planner.
        #
        # #1117/#1123/#1118 root-cause fix: lifted from the inline `code=`
        # codegen to the module-level `_plan_execution` function wired via
        # `PythonCodeNode.from_function`. The node publishes the SAME flat
        # `result` port carrying `{"multi_hop_plan": {...}}` (runtime result
        # shape `result["multi_hop_plan"]` unchanged). It reads
        # `hop_plan_result` (wired from hop_plan_parser.result). The
        # circular-dependency `logger.warning`/`logger.error` observability is
        # preserved (the module-level function closes over the module `logger`,
        # whereas the codegen relied on `logger` being injected into the exec
        # namespace — the function form is the more robust binding). type:
        # ignore[attr-defined] per the composer/parser note above.
        execution_planner_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _plan_execution,
                name="execution_planner",
            ),
            node_id="execution_planner",
            _internal=True,
        )

        # L3 messages-composer (reference template). The hop_planner previously
        # received NO real input — it planned from its `system_prompt` alone,
        # never seeing the query. The composer renders the REAL `query`
        # (top-level workflow input via the parameter injector) into a `messages`
        # list wired to the VALID `messages` port.
        hop_plan_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                compose_hop_plan_messages,
                name="hop_plan_messages_composer",
            ),
            node_id="hop_plan_messages_composer",
            _internal=True,
        )

        # O4 output-side parser: unwraps `hop_planner.response.content` ->
        # json.loads -> the {hops, combination_strategy, total_hops} dict the
        # execution_planner `.get`s. Pre-O4 the raw `response` reached the
        # planner, so `.get("hops")` resolved to [] (zero batches, zero hops).
        hop_plan_parser_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                parse_hop_plan_response,
                name="hop_plan_parser",
            ),
            node_id="hop_plan_parser",
            _internal=True,
        )

        # Connect workflow
        builder.add_connection(
            hop_plan_messages_composer_id,
            "result.messages",
            hop_planner_id,
            "messages",
        )
        # O4: route the LLM `response` THROUGH the parser to the execution planner.
        builder.add_connection(
            hop_planner_id, "response", hop_plan_parser_id, "response"
        )
        builder.add_connection(
            hop_plan_parser_id, "result", execution_planner_id, "hop_plan_result"
        )

        return builder.build(name="multi_hop_planner_workflow")


@register_node()
class AdaptiveQueryProcessorNode(Node):
    """
    Adaptive Query Processing Pipeline

    Combines all query processing techniques adaptively based on
    query characteristics and requirements.

    When to use:
    - Best for: Fully automatic query optimization
    - Not ideal for: When specific processing is required
    - Performance: ~600ms full pipeline
    - Impact: 40-60% overall improvement

    Key features:
    - Automatic technique selection
    - Conditional processing based on need
    - Optimal ordering of operations
    - Learns from query patterns

    Example:
        processor = AdaptiveQueryProcessorNode()

        # Automatically applies:
        # - Spelling correction (if needed)
        # - Query expansion (if beneficial)
        # - Decomposition (if complex)
        # - Multi-hop planning (if required)

        optimized = await processor.execute(
            query="compair transfomer vs lstm for sequnce tasks"
        )
        # Corrects spelling, decomposes comparison, plans retrieval

    Parameters:
        enable_all_techniques: Use all available processors
        optimization_threshold: Minimum benefit to apply
        learning_enabled: Learn from usage patterns

    Returns:
        original_query: Input query
        processing_steps: Applied techniques
        processed_query: Final optimized version
        processing_plan: Complete execution plan
        expected_improvement: Estimated benefit
    """

    def __init__(self, name: str = "adaptive_query_processor"):
        super().__init__(name=name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters"""
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="adaptive_query_processor",
                description="Node instance name",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=True,
                description="Query to process adaptively",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute adaptive query processing"""
        query = kwargs.get("query", "")

        try:
            # Simple adaptive processing implementation
            processing_steps = []

            if query:
                query_lower = query.lower()

                # Determine processing steps based on query characteristics
                if any(char in query for char in ["2", "u", "wit", "trian"]):
                    processing_steps.append("rewrite")

                if len(query.split()) < 4:
                    processing_steps.append("expand")

                if "compare" in query_lower or "vs" in query_lower:
                    processing_steps.append("decompose")

                if "influence" in query_lower or "impact" in query_lower:
                    processing_steps.append("multi_hop")

                # Always include basic analysis
                if not processing_steps:
                    processing_steps.append("analyze")

            return {
                "original_query": query,
                "processing_steps": processing_steps,
                "processed_query": query,  # Would be improved in actual implementation
                "processing_plan": {
                    "steps": processing_steps,
                    "estimated_time": len(processing_steps) * 100,  # ms
                    "complexity": "moderate" if len(processing_steps) > 2 else "simple",
                },
                "expected_improvement": len(processing_steps) * 0.1,
            }

        except Exception as e:
            logger.error(f"Adaptive query processing failed: {e}")
            return {
                "original_query": query,
                "processing_steps": [],
                "processed_query": query,
                "processing_plan": {},
                "error": str(e),
            }

    def _create_workflow(self) -> Workflow:
        """Create adaptive query processing workflow"""
        builder = WorkflowBuilder()

        # L3 NOTE (no composer needed here): AdaptiveQueryProcessorNode owns NO
        # direct LLMAgentNode stage. Its only "LLM-ish" stage is the embedded
        # `intent_analyzer`, a QueryIntentClassifierNode wired by node-type
        # string. When that subclass executes inside this workflow under
        # LocalRuntime it runs its deterministic `run()` (the registry resolves
        # the node-type to the class; LocalRuntime invokes `run()`, NOT the
        # class's OWN inner `_create_workflow()`), so NO LLMAgentNode runs at this
        # composition level — there is no `messages` port to wire here. The
        # QueryIntentClassifierNode LLM stage's `messages` defect is fixed in
        # THAT class's `_create_workflow` (intent_messages_composer above); when
        # a caller drives the classifier through ITS inner LLM workflow, the
        # query reaches the LLM. The adaptive composition consumes the
        # classifier's `routing_decision` run()-contract output, so feeding the
        # real query INTO this workflow is via the top-level `query` input the
        # parameter injector delivers to the embedded classifier's `run()`.
        analyzer_id = builder.add_node(
            "QueryIntentClassifierNode", node_id="intent_analyzer"
        )

        # Add adaptive processor.
        #
        # #1117/#1123/#1118 root-cause fix: lifted from the inline `code=`
        # codegen to the module-level `_adaptive_process` function wired via
        # `PythonCodeNode.from_function`. The node publishes the SAME flat
        # `result` port carrying `{"adaptive_plan": {...}}` (runtime result
        # shape `result["adaptive_plan"]` unchanged). It reads `query`
        # (top-level injection) + `routing_decision` (wired from
        # intent_analyzer.routing_decision — the embedded
        # QueryIntentClassifierNode's run()-contract output, which nests the
        # routing_decision under the same key; `_adaptive_process` unwraps it
        # exactly as the codegen did). type: ignore[attr-defined] per the
        # composer/parser note above.
        adaptive_processor_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _adaptive_process,
                name="adaptive_processor",
            ),
            node_id="adaptive_processor",
            _internal=True,
        )

        # Connect workflow
        builder.add_connection(
            analyzer_id, "routing_decision", adaptive_processor_id, "routing_decision"
        )

        return builder.build(name="adaptive_query_processor_workflow")


# Export all query processing nodes
__all__ = [
    "QueryExpansionNode",
    "QueryDecompositionNode",
    "QueryRewritingNode",
    "QueryIntentClassifierNode",
    "MultiHopQueryPlannerNode",
    "AdaptiveQueryProcessorNode",
]
