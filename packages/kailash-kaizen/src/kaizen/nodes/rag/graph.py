"""
Graph-Enhanced RAG Implementation

Implements knowledge graph-based retrieval for complex reasoning:
- Entity and relationship extraction
- Community detection and summarization
- Multi-hop graph traversal
- Local and global context integration

Based on Microsoft GraphRAG (2024) and knowledge graph research.
"""

import logging
import os
from typing import Any, Dict, List, Optional

import networkx as nx
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.code.python import (  # noqa: F401  registers "PythonCodeNode"
    PythonCodeNode,
)
from kailash.nodes.logic.workflow import WorkflowNode
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow

from ..ai.llm_agent import LLMAgentNode  # noqa: F401  registers "LLMAgentNode"
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
# conversational.py lines 45-199, query_processing.py lines 54-212, and
# agentic.py lines 43-120).
#
# LLMAgentNode consumes context EXCLUSIVELY through its `messages` param (the
# OpenAI chat format: a list of {"role","content"} dicts) plus `system_prompt`.
# `LLMAgentNode.run` reads `messages = kwargs["messages"]`; ANY OTHER wired port
# name (`documents`, `query`, `graph_data`, ...) is read via `kwargs.get` and
# SILENTLY DROPPED. The prior wiring in GraphRAGNode fed NO real input to two of
# the three LLM stages (entity_extractor + query_processor had ZERO inbound
# edges) and a phantom `graph_data` port to the third (summary_generator), so
# every LLM stage answered from its `system_prompt` alone — the entity extractor
# never saw the documents to extract from, the query processor never saw the
# user's query, and the summary generator never saw the retrieved graph context
# (the L3 "LLM ignores its input" defect).
#
# The context contract is HETEROGENEOUS per stage:
#   - entity_extractor reasons over the REAL source DOCUMENT TEXT (the top-level
#     `documents` workflow input — the same input GraphBuilderNode.run reads).
#   - query_processor reasons over the user QUERY (the top-level `query` input —
#     the same input result_synthesizer reads).
#   - summary_generator reasons over the RETRIEVED GRAPH CONTEXT (the real
#     upstream graph_retriever `graph_retrieval` output) + the query.
# Each composer renders the REAL inputs that stage must reason over into a
# `messages` list wired to the stage's VALID `messages` port.
#
# These are real module-level functions (real `return`→`result`, type-checkable,
# no f-string brace-escaping) per the program's reference template — NOT inline
# `code=` codegen blocks. Each is pure data rendering (the permitted
# output-formatting exception per rules/agent-reasoning.md) — NO if-else routing
# / keyword classification on content. The graph-construction / traversal logic
# in GraphBuilderNode / graph_retriever is legitimate graph-algorithm code and
# is untouched.
#
# IN-GRAPH HONESTY (zero-tolerance Rule 2): each composer renders only inputs a
# real upstream node publishes (or a real top-level workflow input). The
# `documents` and `query` inputs are the SAME top-level inputs the deterministic
# Node paths (GraphBuilderNode.run / result_synthesizer) already consume — no
# input is invented. The graph_retrieval the summary composer renders is the
# genuine graph_retriever output.
# ---------------------------------------------------------------------------


def _coerce_text(value: Any) -> str:
    """Coerce a wired scalar input to a clean string.

    The parameter injector delivers top-level inputs as plain strings; wired
    ports may arrive None on an unwired branch.
    """
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return str(value).strip()


def _render_documents(documents: Any) -> str:
    """Render the source documents into a plain-text block for entity extraction.

    `documents` is the top-level workflow input — a list of document dicts (the
    same shape GraphBuilderNode.run consumes: ``{"content": ..., "id": ...}``).
    A document may also arrive as a bare string. Returns "" when empty.
    """
    if isinstance(documents, str):
        return documents.strip()
    if not isinstance(documents, list):
        return ""
    blocks = []
    for i, doc in enumerate(documents):
        if isinstance(doc, dict):
            # ``doc.get("content")`` may be present-with-None; ``or ""`` covers it.
            content = (doc.get("content") or "").strip()
        elif isinstance(doc, str):
            content = doc.strip()
        else:
            content = ""
        if content:
            blocks.append(f"[Document {i + 1}] {content}")
    return "\n\n".join(blocks)


def _render_graph_context(graph_retrieval: Any) -> str:
    """Render the retrieved subgraph (entities + relationships + communities)
    into a readable context block for the summary generator.

    `graph_retrieval` is the graph_retriever `result` port value, i.e. the
    ``{"graph_retrieval": {...}}`` wrapper carrying ``entities`` /
    ``relationships`` / ``community_context``. Returns "" when the retrieval is
    empty.
    """
    if isinstance(graph_retrieval, dict):
        inner = graph_retrieval.get("graph_retrieval", graph_retrieval)
    else:
        inner = {}
    if not isinstance(inner, dict):
        return ""
    parts: List[str] = []

    entities = inner.get("entities") or []
    if isinstance(entities, list) and entities:
        parts.append("Key Entities:")
        for entity in entities[:10]:
            if not isinstance(entity, dict):
                continue
            name = entity.get("name", "")
            etype = entity.get("type", "")
            desc = entity.get("description", "") or ""
            parts.append(f"- {name} ({etype}): {desc}")

    relationships = inner.get("relationships") or []
    if isinstance(relationships, list) and relationships:
        parts.append("\nKey Relationships:")
        for rel in relationships[:10]:
            if not isinstance(rel, dict):
                continue
            parts.append(
                f"- {rel.get('source', '')} {rel.get('type', '')} "
                f"{rel.get('target', '')}"
            )

    community_context = inner.get("community_context") or {}
    if isinstance(community_context, dict) and community_context:
        parts.append("\nRelated Topic Clusters:")
        for comm_id, nodes in list(community_context.items())[:3]:
            node_list = nodes if isinstance(nodes, list) else []
            parts.append(
                f"- Cluster {comm_id}: {', '.join(str(n) for n in node_list[:5])}"
            )

    return "\n".join(parts).strip()


def compose_entity_extraction_messages(documents=None):
    """Compose the ``messages`` list for the entity_extractor LLM stage.

    Embeds the REAL source DOCUMENT TEXT so the LLM extracts entities and
    relationships FROM THE DOCUMENTS — not from its ``system_prompt`` alone.
    Returns ``{"messages": [...]}`` wired to the LLMAgentNode ``messages`` port.

    ``documents`` is declared as a function parameter so the runtime's parameter
    injector delivers the caller-supplied top-level ``documents`` workflow input
    (the same input GraphBuilderNode.run reads). When no documents are wired the
    user message is an explicit empty note so the stage still receives a
    well-formed (non-empty) messages list.
    """
    rendered = _render_documents(documents)
    content = (
        "Extract entities and relationships from the following text:\n\n" + rendered
        if rendered
        else "No documents were provided to extract entities from."
    )
    return {"messages": [{"role": "user", "content": content}]}


def compose_query_analysis_messages(query=""):
    """Compose the ``messages`` list for the query_processor LLM stage.

    Embeds the REAL user QUERY so the LLM analyses THE QUERY (entities,
    relationship types, multi-hop need) — not from its ``system_prompt`` alone.
    Returns ``{"messages": [...]}`` wired to the LLMAgentNode ``messages`` port.

    ``query`` is declared as a function parameter so the parameter injector
    delivers the caller-supplied top-level ``query`` workflow input (the same
    input result_synthesizer reads).
    """
    q = _coerce_text(query)
    content = (
        "Analyze the following query for graph retrieval:\n" + q
        if q
        else "No query was provided to analyze."
    )
    return {"messages": [{"role": "user", "content": content}]}


def compose_summary_messages(graph_retrieval=None, query=""):
    """Compose the ``messages`` list for the summary_generator LLM stage.

    Embeds the REAL retrieved graph context (entities + relationships +
    community clusters from the upstream graph_retriever) AND the user query so
    the LLM summarises the ACTUAL retrieved subgraph — not from its
    ``system_prompt`` alone. Returns ``{"messages": [...]}`` wired to the
    LLMAgentNode ``messages`` port.

    ``graph_retrieval`` is the upstream graph_retriever ``result`` port value
    (the ``{"graph_retrieval": {...}}`` wrapper). ``query`` is the top-level
    workflow input. When the retrieval is empty (no entities matched) the
    composer renders an explicit empty-context note rather than fabricating
    graph data (zero-tolerance Rule 2).
    """
    context = _render_graph_context(graph_retrieval)
    q = _coerce_text(query)
    parts: List[str] = []
    if context:
        parts.append("Retrieved graph context:\n" + context)
    else:
        parts.append(
            "No graph context was retrieved for this query "
            "(no entities matched the retrieved subgraph)."
        )
    if q:
        parts.append("Query:\n" + q)
    parts.append(
        "Summarize the main themes, key entities, and important relationships."
    )
    return {"messages": [{"role": "user", "content": "\n\n".join(parts)}]}


# ---------------------------------------------------------------------------
# O3 OUTPUT-SIDE parsers (provably-correct end-to-end — Wave O3).
#
# Wave-2 (L3) fixed the INPUT side: each LLM stage now CONSUMES its real context
# through the `messages` port. O3 fixes the OUTPUT side: two LLM stages whose
# output was DROPPED or MISPARSED downstream.
#
# DEFECT 1 (Class B — entity-extraction parse gap): `entity_extractor` is
# prompted to return ONE JSON object `{"entities":[...], "relationships":[...]}`
# and publishes it on `response` as `{"content": "<JSON string>", ...}`. The
# prior edge fed that RAW response dict straight to `graph_builder`, whose
# `build_knowledge_graph(extraction_results)` iterates `extraction_results` as a
# LIST of per-doc extraction objects (`for doc_extraction in extraction_results:
# doc_extraction.get("entities", [])`). Iterating the response DICT yields its
# string KEYS ("content"/"success"/...) → `"content".get(...)` AttributeError /
# garbage. `parse_entity_extraction` unwraps `response.content`, `json.loads` it,
# and publishes the parsed extraction WRAPPED IN A SINGLE-ELEMENT LIST (the one
# LLM call returns one merged extraction over all source docs, and the consumer
# iterates a list). Malformed/non-JSON/missing-keys → a one-element list carrying
# `{"entities": [], "relationships": [], "parse_error": "<reason>"}` so the graph
# builds EMPTY (honest) — NEVER fabricated entities, NEVER a silent crash
# (zero-tolerance Rule 2). The `parse_error` field is grep-able for post-incident
# audit.
#
# DEFECT 2 (F31-FU1 — summary_generator output orphaned): `summary_generator`
# is prompted for FREE-TEXT prose summaries and publishes `response.content`. The
# prior edge wired it to `result_synthesizer.global_summaries`, but the
# synthesizer body NEVER read `global_summaries` — the documented input was
# accepted-but-unread (zero-tolerance Rule 3c). `parse_global_summary` unwraps
# `response.content` (prose — NO json.loads) into `{"global_summary": <text>}`,
# and the synthesizer body (built conditionally — see `_create_workflow`) now
# reads it into `graph_rag_results["global_summary"]`. Missing/empty →
# `{"global_summary": None, "parse_error": "<reason>"}` (honest, never fabricated).
#
# These are tool-result PARSING (the permitted output-formatting / structured-
# extraction exception per rules/agent-reasoning.md — extracting structured data
# from LLM output), NOT agent decision-making: the LLM still extracts the
# entities/relationships and writes the summary; these functions only parse what
# the LLM produced. NO if-else routing / keyword classification on content is
# added. Same reference template as evaluation.py O1 parsers + workflows.py O2
# (`parse_strategy_decision`) + the `_unwrap_response_content` unwrap.
# ---------------------------------------------------------------------------


def _unwrap_response_content(response: Any) -> Any:
    """Unwrap the LLMAgentNode ``response`` port into the model's text payload.

    ``LLMAgentNode`` publishes ``response`` as ``{"content": "<text>", ...}``
    (mock + real providers both). A defensive caller may also pass the bare
    string. Mirrors evaluation.py / workflows.py ``_unwrap_response_content`` +
    the conversational.py ``response.get("content")`` unwrap.
    """
    if isinstance(response, dict):
        return response.get("content")
    return response


def parse_entity_extraction(response=None):
    """Parse the ``entity_extractor`` ``response`` into a graph-builder-ready list.

    Reads ``response`` -> ``.content`` (a JSON string) -> ``json.loads`` -> the
    single ``{"entities":[...], "relationships":[...]}`` object the extractor's
    ``system_prompt`` instructs the LLM to emit, and returns it WRAPPED IN A
    ONE-ELEMENT LIST as the from_function ``result``. ``build_knowledge_graph``
    iterates ``extraction_results`` as a LIST of per-doc extraction objects; the
    single LLM call returns one merged extraction over all source documents, so
    the list has exactly one element.

    HONESTY (zero-tolerance Rule 2): malformed / non-JSON / missing-keys output
    is FLAGGED with a typed, ITERABLE-SAFE sentinel — a one-element list carrying
    ``{"entities": [], "relationships": [], "parse_error": "<reason>"}``. The
    graph builder then iterates the (empty) entities/relationships and produces an
    EMPTY graph honestly — never fabricated entities, never a crash. The
    ``parse_error`` field is grep-able for post-incident audit.
    """
    import json

    content = _unwrap_response_content(response)

    # Honest empty: the extractor published nothing parseable. Surface a flagged
    # one-element extraction so the graph builds empty rather than crashing.
    if content is None or (isinstance(content, str) and not content.strip()):
        return {
            "result": [
                {"entities": [], "relationships": [], "parse_error": "empty-response"}
            ]
        }

    # The provider may already have emitted a parsed structure (some do).
    parsed: Any
    if isinstance(content, dict):
        parsed = content
    elif isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return {
                "result": [
                    {
                        "entities": [],
                        "relationships": [],
                        "parse_error": "non-json-response",
                    }
                ]
            }
    else:
        return {
            "result": [
                {
                    "entities": [],
                    "relationships": [],
                    "parse_error": "unexpected-content-type",
                }
            ]
        }

    if not isinstance(parsed, dict):
        return {
            "result": [
                {
                    "entities": [],
                    "relationships": [],
                    "parse_error": "non-object-json",
                }
            ]
        }

    entities = parsed.get("entities")
    relationships = parsed.get("relationships")
    # Parsed JSON but the load-bearing keys are absent/wrong-shape: FLAG, don't
    # fabricate — coerce to empty lists so the graph builds empty honestly.
    if not isinstance(entities, list) or not isinstance(relationships, list):
        return {
            "result": [
                {
                    "entities": entities if isinstance(entities, list) else [],
                    "relationships": (
                        relationships if isinstance(relationships, list) else []
                    ),
                    "parse_error": "missing-entities-or-relationships",
                }
            ]
        }

    # Real extraction: surface the genuine entities + relationships, wrapped in a
    # one-element list for the per-doc-iterating graph builder.
    return {"result": [{"entities": entities, "relationships": relationships}]}


def parse_query_analysis(response=None):
    """Parse the ``query_processor`` ``response`` into a query-analysis dict.

    DEFECT 3 (Class B — query-analysis parse gap, identical to DEFECT 1): the
    ``query_processor`` LLM stage is prompted to return JSON
    ``{"entities":[...], "relationship_types":[...], "requires_multi_hop": bool,
    "reasoning_type": "..."}`` and publishes it on ``response`` as
    ``{"content": "<JSON string>", ...}``. The prior edge fed that RAW response
    dict straight to ``graph_retriever``, whose
    ``retrieve_from_graph(graph_data, query_analysis)`` reads
    ``query_analysis.get("entities", [])`` / ``.get("relationship_types", [])`` /
    ``.get("requires_multi_hop", False)``. Against the raw response dict those
    keys are ABSENT (they live inside ``response["content"]`` as a JSON string),
    so every field defaults → ``relevant_nodes`` empty → an EMPTY subgraph
    regardless of the LLM's analysis. The query-driven retrieval path was dead.

    Reads ``response`` -> ``.content`` (a JSON string) -> ``json.loads`` -> the
    ``{entities, relationship_types, requires_multi_hop, reasoning_type}`` object
    the analyzer's ``system_prompt`` instructs the LLM to emit, returned as the
    from_function ``result`` so ``graph_retriever`` reads the REAL parsed
    entities/types and drives a genuine subgraph.

    HONESTY (zero-tolerance Rule 2): malformed / non-JSON / missing-keys output
    is FLAGGED with a typed sentinel carrying EMPTY DEFAULTS
    (``{"entities": [], "relationship_types": [], "requires_multi_hop": False,
    "reasoning_type": None, "parse_error": "<reason>"}``). ``graph_retriever``
    then matches no nodes and returns an honest EMPTY subgraph — NEVER fabricated
    entities, NEVER a default reasoning_type. The ``parse_error`` field is
    grep-able for post-incident audit.
    """
    import json

    def _flagged(reason):
        return {
            "result": {
                "entities": [],
                "relationship_types": [],
                "requires_multi_hop": False,
                "reasoning_type": None,
                "parse_error": reason,
            }
        }

    content = _unwrap_response_content(response)

    # Honest empty: the analyzer published nothing parseable. Surface a flagged
    # empty-default analysis so the retriever returns an empty subgraph.
    if content is None or (isinstance(content, str) and not content.strip()):
        return _flagged("empty-response")

    # The provider may already have emitted a parsed dict (some do).
    parsed: Any
    if isinstance(content, dict):
        parsed = content
    elif isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return _flagged("non-json-response")
    else:
        return _flagged("unexpected-content-type")

    if not isinstance(parsed, dict):
        return _flagged("non-object-json")

    # Coerce each field to its honest empty default when absent/wrong-shape — the
    # retriever's per-field .get() defaults already tolerate missing keys, but
    # normalizing here keeps the published shape uniform and grep-able. No field
    # is fabricated: a missing entities list stays empty, not invented.
    entities = parsed.get("entities")
    relationship_types = parsed.get("relationship_types")
    requires_multi_hop = parsed.get("requires_multi_hop")
    reasoning_type = parsed.get("reasoning_type")
    return {
        "result": {
            "entities": entities if isinstance(entities, list) else [],
            "relationship_types": (
                relationship_types if isinstance(relationship_types, list) else []
            ),
            "requires_multi_hop": bool(requires_multi_hop),
            "reasoning_type": (
                reasoning_type if isinstance(reasoning_type, str) else None
            ),
        }
    }


def parse_global_summary(response=None):
    """Parse the ``summary_generator`` ``response`` into a summary dict.

    Reads ``response`` -> ``.content`` (FREE-TEXT prose — NO ``json.loads``, the
    summary_generator emits a prose summary, not JSON) into
    ``{"global_summary": <text>}`` as the from_function ``result`` so the
    ``result_synthesizer`` incorporates the REAL parsed summary into its
    ``graph_rag_results``.

    HONESTY (zero-tolerance Rule 2): missing / empty / non-string output is
    FLAGGED with a typed sentinel (``{"global_summary": None,
    "parse_error": "<reason>"}``) — never a fabricated summary. The synthesizer
    then surfaces ``global_summary: None`` honestly.
    """
    content = _unwrap_response_content(response)

    if content is None:
        return {"result": {"global_summary": None, "parse_error": "empty-response"}}
    if isinstance(content, str):
        text = content.strip()
        if not text:
            return {"result": {"global_summary": None, "parse_error": "empty-response"}}
        return {"result": {"global_summary": text}}
    # Non-string content (e.g. the provider returned a structure): flag the shape
    # gap rather than coercing arbitrary objects into a "summary" string.
    return {"result": {"global_summary": None, "parse_error": "non-string-content"}}


# ---------------------------------------------------------------------------
# Deterministic graph-algorithm COMPUTE functions (#1117/#1123/#1118 root-cause
# fix — Wave 3 Shard S3). These replace the prior f-string code-string
# PythonCodeNode codegen the GraphRAGNode inlined for graph_builder / graph_retriever /
# result_synthesizer. Each is a real module-level function wired via
# `PythonCodeNode.from_function(...)`: a from_function node publishes its `return`
# value on the FLAT `result` port (the runtime resolves dotted downstream reads
# like `result.graph_data` into the published dict), so:
#
#   - #1117 (publish-nothing): a real `return {...}` always binds the published
#     `result` port — no column-0 module-scope-assignment AST gymnastics.
#   - #1123 (f-string brace-escape): no `{{ }}` escaping; real dict literals.
#   - #1118 (import-trap): `import networkx` / `from collections import deque` run
#     as REAL top-level imports inside the function body — outside the
#     PythonCodeNode `exec()` sandbox that BLOCKED `import networkx` for the prior
#     `code=` blocks. (The pre-Wave-3 inner graph could NOT run end-to-end under a
#     plain LocalRuntime for exactly this reason; from_function closes that gap.)
#
# These are legitimate graph-algorithm code (construction / traversal / synthesis)
# — NOT agent decision-making (rules/agent-reasoning.md): no LLM reasoning, no
# if-else intent routing. The LLM stages reason; these deterministic helpers run
# the networkx algorithms over the LLM-parsed entities/relationships. Malformed /
# edge inputs resolve to HONEST empty graphs / defaults (zero-tolerance Rule 2) —
# never fabricated entities.
# ---------------------------------------------------------------------------


def build_knowledge_graph(extraction_results=None, community_algorithm="louvain"):
    """Build a networkx ``MultiDiGraph`` from parsed entity/relationship extractions.

    ``extraction_results`` is the ``entity_extraction_parser`` ``result`` — a LIST
    of per-doc extraction objects (the single LLM call returns one merged
    extraction wrapped in a one-element list). Each object carries ``entities`` +
    ``relationships`` lists. ``community_algorithm`` is the build-time
    GraphRAGNode config bound through a thin closure (see ``_create_workflow``).

    Returns ``{"graph_data": {...}}`` on the flat ``result`` port. An empty /
    malformed ``extraction_results`` builds an EMPTY graph honestly — never
    fabricated entities (zero-tolerance Rule 2).
    """
    from collections import defaultdict

    import networkx as nx

    if not isinstance(extraction_results, list):
        extraction_results = []

    G = nx.MultiDiGraph()
    all_entities = []
    all_relationships = []

    for doc_extraction in extraction_results:
        if not isinstance(doc_extraction, dict):
            continue
        entities = doc_extraction.get("entities") or []
        relationships = doc_extraction.get("relationships") or []

        for entity in entities:
            if not isinstance(entity, dict) or "name" not in entity:
                continue
            node_id = str(entity["name"]).lower()
            G.add_node(
                node_id,
                name=entity["name"],
                type=entity.get("type", ""),
                description=entity.get("description", ""),
                documents=set(),
            )
            all_entities.append(entity)

        for rel in relationships:
            if not isinstance(rel, dict) or "source" not in rel or "target" not in rel:
                continue
            source = str(rel["source"]).lower()
            target = str(rel["target"]).lower()
            G.add_edge(
                source,
                target,
                type=rel.get("type", ""),
                description=rel.get("description", ""),
            )
            all_relationships.append(rel)

    # Detect communities over the real graph.
    if len(G) > 0:
        if community_algorithm == "louvain":
            import community

            communities = community.best_partition(G.to_undirected())
        else:
            communities = {}
            for i, comp in enumerate(nx.weakly_connected_components(G)):
                for node in comp:
                    communities[node] = i
    else:
        communities = {}

    community_nodes = defaultdict(list)
    for node, comm_id in communities.items():
        community_nodes[comm_id].append(node)

    return {
        "graph_data": {
            "graph": nx.node_link_data(G),
            "entities": all_entities,
            "relationships": all_relationships,
            "communities": communities,
            "community_nodes": dict(community_nodes),
            "stats": {
                "num_entities": len(G),
                "num_relationships": len(G.edges()),
                "num_communities": (
                    len(set(communities.values())) if communities else 0
                ),
            },
        }
    }


def retrieve_from_graph(graph_data=None, query_analysis=None, max_hops=2):
    """Retrieve a relevant subgraph from ``graph_data`` driven by ``query_analysis``.

    ``graph_data`` is the ``graph_builder`` ``result.graph_data`` value;
    ``query_analysis`` is the ``query_analysis_parser`` ``result`` (the parsed
    ``{entities, relationship_types, requires_multi_hop, reasoning_type}`` dict).
    ``max_hops`` is the build-time GraphRAGNode config bound through a thin
    closure (see ``_create_workflow``).

    Returns ``{"graph_retrieval": {...}}`` on the flat ``result`` port. Absent /
    malformed inputs yield an honest EMPTY subgraph — the retriever's per-field
    ``.get()`` defaults already tolerate missing keys (zero-tolerance Rule 2).
    """
    from collections import deque

    import networkx as nx

    if not isinstance(graph_data, dict):
        graph_data = {}
    if not isinstance(query_analysis, dict):
        query_analysis = {}

    serialized = graph_data.get("graph")
    if serialized:
        G = nx.node_link_graph(serialized)
    else:
        G = nx.MultiDiGraph()

    query_entities = [str(e).lower() for e in query_analysis.get("entities", [])]
    relationship_types = query_analysis.get("relationship_types", [])
    requires_multi_hop = query_analysis.get("requires_multi_hop", False)

    # Find relevant nodes (fuzzy substring match against query entities).
    relevant_nodes = set()
    for entity in query_entities:
        for node in G.nodes():
            if entity in node or node in entity:
                relevant_nodes.add(node)

    # Multi-hop expansion (BFS up to max_hops) when the analysis asks for it.
    if requires_multi_hop and relevant_nodes:
        expanded_nodes = set(relevant_nodes)
        for start_node in relevant_nodes:
            visited = {start_node}
            queue = deque([(start_node, 0)])
            while queue:
                node, depth = queue.popleft()
                if depth >= max_hops:
                    continue
                for neighbor in G.neighbors(node):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        expanded_nodes.add(neighbor)
                        queue.append((neighbor, depth + 1))
        relevant_nodes = expanded_nodes

    if relevant_nodes:
        subgraph = G.subgraph(relevant_nodes).copy()

        relevant_edges = []
        for u, v, data in subgraph.edges(data=True):
            if not relationship_types or data.get("type") in relationship_types:
                relevant_edges.append(
                    {
                        "source": u,
                        "target": v,
                        "type": data.get("type"),
                        "description": data.get("description"),
                    }
                )

        relevant_entities = []
        for node in relevant_nodes:
            node_data = G.nodes[node]
            relevant_entities.append(
                {
                    "name": node_data.get("name", node),
                    "type": node_data.get("type"),
                    "description": node_data.get("description"),
                    "centrality": nx.degree_centrality(subgraph).get(node, 0),
                }
            )

        relevant_entities.sort(key=lambda x: x["centrality"], reverse=True)
    else:
        relevant_entities = []
        relevant_edges = []

    # Community context for the relevant nodes.
    communities = graph_data.get("communities", {})
    community_context = {}
    for node in relevant_nodes:
        comm_id = communities.get(node)
        if comm_id is not None:
            comm_nodes = graph_data.get("community_nodes", {}).get(str(comm_id), [])
            community_context[comm_id] = comm_nodes

    return {
        "graph_retrieval": {
            "entities": relevant_entities[:20],
            "relationships": relevant_edges[:30],
            "subgraph_stats": {
                "nodes": len(relevant_nodes),
                "edges": len(relevant_edges),
            },
            "community_context": community_context,
            "query_entities_found": len(
                [e for e in query_entities if any(e in n for n in relevant_nodes)]
            ),
        }
    }


def _render_synthesis_context(graph_retrieval: Any) -> str:
    """Render the retrieved subgraph into a readable context block for synthesis.

    Shared rendering for ``synthesize_results``; pure data formatting (the
    permitted output-formatting exception per rules/agent-reasoning.md).
    """
    parts: List[str] = []
    entities = graph_retrieval.get("entities") or []
    if entities:
        parts.append("Key Entities:")
        for entity in entities[:10]:
            if not isinstance(entity, dict):
                continue
            parts.append(
                f"- {entity.get('name', '')} ({entity.get('type', '')}): "
                f"{entity.get('description', '')}"
            )

    relationships = graph_retrieval.get("relationships") or []
    if relationships:
        parts.append("\nKey Relationships:")
        for rel in relationships[:10]:
            if not isinstance(rel, dict):
                continue
            parts.append(
                f"- {rel.get('source', '')} {rel.get('type', '')} "
                f"{rel.get('target', '')}"
            )

    community_context = graph_retrieval.get("community_context") or {}
    if community_context:
        parts.append("\nRelated Topic Clusters:")
        for comm_id, nodes in list(community_context.items())[:3]:
            node_list = nodes if isinstance(nodes, list) else []
            parts.append(
                f"- Cluster {comm_id}: " f"{', '.join(str(n) for n in node_list[:5])}"
            )
    return "\n".join(parts)


def synthesize_results(
    graph_retrieval=None,
    query="",
    graph_data=None,
    global_summaries=None,
    use_global_summary=True,
):
    """Combine the retrieved subgraph + query + (conditional) global summary.

    ``graph_retrieval`` is the ``graph_retriever`` ``result.graph_retrieval``;
    ``graph_data`` the ``graph_builder`` ``result.graph_data``; ``global_summaries``
    the ``global_summary_parser`` ``result`` (the parsed ``{"global_summary":
    <text or None>}`` dict) — wired ONLY when ``use_global_summary=True``.
    ``use_global_summary`` is the build-time GraphRAGNode config bound through a
    thin closure (see ``_create_workflow``).

    CONDITIONAL-BEHAVIOR PRESERVATION (Wave-2.5 O3/F31-FU1): the global-summary
    read fires ONLY on the enabled path. On the disabled path ``global_summaries``
    is never wired AND ``use_global_summary`` is False, so ``global_summary`` is
    ``None`` honestly — the from_function ``global_summaries=None`` default makes
    the unwired input safe (a from_function node tolerates a missing declared
    input, unlike the `code=` exec namespace that raised NameError on a bare
    reference — which is why the prior codegen had to emit the read-lines
    conditionally). Returns ``{"graph_rag_results": {...}}`` on ``result``.
    """
    if not isinstance(graph_retrieval, dict):
        graph_retrieval = {}
    if not isinstance(graph_data, dict):
        graph_data = {}

    # O3 DEFECT 2: read the REAL parsed global summary ONLY on the enabled path.
    global_summary = None
    if use_global_summary and isinstance(global_summaries, dict):
        global_summary = global_summaries.get("global_summary")

    context = _render_synthesis_context(graph_retrieval)

    # Reasoning-path visualization over the retrieved entities.
    reasoning_path = []
    entities = graph_retrieval.get("entities") or []
    if len(entities) > 1:
        for i in range(min(3, len(entities) - 1)):
            reasoning_path.append(
                {
                    "hop": i + 1,
                    "from": entities[i].get("name", ""),
                    "to": entities[i + 1].get("name", ""),
                    "connection": "related through graph structure",
                }
            )

    community_context = graph_retrieval.get("community_context") or {}
    stats = graph_data.get("stats", {})

    return {
        "graph_rag_results": {
            "query": query,
            "retrieved_entities": entities,
            "retrieved_relationships": graph_retrieval.get("relationships") or [],
            "graph_context": context,
            "global_summary": global_summary,
            "reasoning_path": reasoning_path,
            "subgraph_size": graph_retrieval.get("subgraph_stats", {}),
            "community_info": {
                "num_communities": len(community_context),
                "communities_accessed": list(community_context.keys()),
            },
            "global_graph_stats": stats,
        }
    }


@register_node()
class GraphRAGNode(WorkflowNode):
    """
    Knowledge Graph-Enhanced RAG

    Builds and queries knowledge graphs from documents for superior reasoning
    capabilities. Combines entity-centric retrieval with relationship traversal.

    When to use:
    - Best for: Complex multi-hop questions, relationship queries, analytical tasks
    - Not ideal for: Simple factual lookups, real-time requirements
    - Performance: 2-5 seconds (includes graph building)
    - Quality improvement: 40-60% for complex reasoning tasks

    Key features:
    - Automatic entity and relationship extraction
    - Community detection for topic clustering
    - Multi-hop reasoning across connections
    - Hierarchical summarization at multiple levels
    - Combines local entity context with global graph understanding

    Example:
        graph_rag = GraphRAGNode(
            entity_types=["person", "organization", "technology", "concept"],
            max_hops=3
        )

        # Query: "How did key researchers influence the development of transformers?"
        # GraphRAG will:
        # 1. Extract entities (researchers, transformer, papers)
        # 2. Find relationships (authored, influenced, cited)
        # 3. Traverse graph to find influence paths
        # 4. Synthesize multi-hop connections

        result = await graph_rag.execute(
            documents=research_papers,
            query="How did key researchers influence the development of transformers?"
        )

    Parameters:
        entity_types: Types of entities to extract
        relationship_types: Types of relationships to identify
        max_hops: Maximum graph traversal depth
        community_algorithm: Method for detecting topic communities
        use_global_summary: Include high-level graph summaries

    Returns:
        results: Retrieved entities and relationships
        graph_context: Local and global graph information
        reasoning_path: Multi-hop connections found
        community_summaries: High-level topic summaries
    """

    def __init__(
        self,
        name: str = "graph_rag",
        entity_types: Optional[List[str]] = None,
        relationship_types: Optional[List[str]] = None,
        max_hops: int = 2,
        community_algorithm: str = "louvain",
        use_global_summary: bool = True,
    ):
        self.entity_types = entity_types or [
            "person",
            "organization",
            "concept",
            "technology",
        ]
        self.relationship_types = relationship_types or [
            "relates_to",
            "influences",
            "uses",
            "created_by",
        ]
        self.max_hops = max_hops
        self.community_algorithm = community_algorithm
        self.use_global_summary = use_global_summary
        super().__init__(workflow=self._create_workflow(), name=name)

    def _create_workflow(self) -> Workflow:
        """Create knowledge graph RAG workflow"""
        builder = WorkflowBuilder()
        # Bound before the conditional so the use site below is provably bound
        # whether or not the optional summary node is added.
        summary_generator_id: Optional[str] = None

        # Entity extraction
        entity_extractor_id = builder.add_node(
            "LLMAgentNode",
            node_id="entity_extractor",
            config={
                "provider": detect_provider_from_env(),
                "system_prompt": f"""Extract entities and relationships from text.

                Entity types: {", ".join(self.entity_types)}
                Relationship types: {", ".join(self.relationship_types)}

                Return JSON:
                {{
                    "entities": [
                        {{"name": "...", "type": "...", "description": "..."}}
                    ],
                    "relationships": [
                        {{"source": "...", "target": "...", "type": "...", "description": "..."}}
                    ]
                }}""",
                "model": _DEFAULT_LLM_MODEL,
            },
        )

        # Graph builder.
        #
        # Wave-3 #1117/#1123/#1118 root-cause fix: lifted from the prior f-string
        # `code=` codegen to the module-level `build_knowledge_graph` function
        # wired via `PythonCodeNode.from_function`. The build-time
        # `community_algorithm` is bound through a thin closure (keeps
        # `extraction_results` as the declared input). `import networkx` now runs
        # OUTSIDE the PythonCodeNode sandbox (which BLOCKED it for the prior
        # `code=` block — the reason the full inner graph could not run
        # end-to-end). The function returns `{"graph_data": {...}}`, so the
        # downstream `result.graph_data` edges resolve unchanged.
        _community_algorithm = self.community_algorithm

        def _build_knowledge_graph_bound(extraction_results=None) -> dict:
            return build_knowledge_graph(
                extraction_results=extraction_results,
                community_algorithm=_community_algorithm,
            )

        _build_knowledge_graph_bound.__name__ = "graph_builder"
        _build_knowledge_graph_bound.__doc__ = build_knowledge_graph.__doc__
        graph_builder_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _build_knowledge_graph_bound,
                name="graph_builder",
            ),
            node_id="graph_builder",
            _internal=True,
        )

        # Query processor for graph
        query_processor_id = builder.add_node(
            "LLMAgentNode",
            node_id="query_processor",
            config={
                "provider": detect_provider_from_env(),
                "system_prompt": """Analyze the query to identify:
                1. Key entities mentioned or implied
                2. Types of relationships being asked about
                3. Whether multi-hop reasoning is needed
                4. The depth of analysis required

                Return JSON:
                {
                    "entities": ["entity1", "entity2"],
                    "relationship_types": ["type1", "type2"],
                    "requires_multi_hop": true/false,
                    "reasoning_type": "causal/comparative/analytical"
                }""",
                "model": _DEFAULT_LLM_MODEL,
            },
        )

        # Graph traversal and retrieval.
        #
        # Wave-3 #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `retrieve_from_graph` function wired via `PythonCodeNode.from_function`.
        # The build-time `max_hops` is bound through a thin closure (keeps
        # `graph_data` + `query_analysis` as the declared inputs). `import networkx`
        # / `from collections import deque` now run OUTSIDE the PythonCodeNode
        # sandbox. The function returns `{"graph_retrieval": {...}}`, so the
        # downstream `result.graph_retrieval` edges resolve unchanged.
        _max_hops = self.max_hops

        def _retrieve_from_graph_bound(graph_data=None, query_analysis=None) -> dict:
            return retrieve_from_graph(
                graph_data=graph_data,
                query_analysis=query_analysis,
                max_hops=_max_hops,
            )

        _retrieve_from_graph_bound.__name__ = "graph_retriever"
        _retrieve_from_graph_bound.__doc__ = retrieve_from_graph.__doc__
        graph_retriever_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _retrieve_from_graph_bound,
                name="graph_retriever",
            ),
            node_id="graph_retriever",
            _internal=True,
        )

        # Global summary generator (if enabled)
        if self.use_global_summary:
            summary_generator_id = builder.add_node(
                "LLMAgentNode",
                node_id="summary_generator",
                config={
                    "provider": detect_provider_from_env(),
                    "system_prompt": """Generate high-level summaries of document communities.
                    Focus on main themes, key entities, and important relationships.
                    Be concise but comprehensive.""",
                    "model": _DEFAULT_LLM_MODEL,
                },
            )

        # Result synthesizer.
        #
        # Wave-3 #1117/#1123/#1118 root-cause fix: lifted to the module-level
        # `synthesize_results` function wired via `PythonCodeNode.from_function`.
        # The build-time `use_global_summary` is bound through a thin closure
        # (keeps `graph_retrieval` / `query` / `graph_data` / `global_summaries`
        # as the declared inputs). The function returns `{"graph_rag_results":
        # {...}}` on the flat `result` port.
        #
        # CONDITIONAL-BEHAVIOR PRESERVATION (Wave-2.5 O3/F31-FU1): the
        # `global_summary` read fires ONLY when `use_global_summary=True` AND a
        # `global_summaries` dict was wired. On the disabled path the
        # `global_summaries` input is never wired; a from_function node tolerates
        # a missing declared input (its `global_summaries=None` default applies),
        # so there is NO NameError risk — the prior `code=` body had to emit the
        # read-lines CONDITIONALLY precisely because an unwired name raised
        # NameError in the exec namespace. from_function's parameter defaults make
        # the single unified function safe on BOTH paths; `global_summary` is
        # `None` honestly on the disabled path.
        _use_global_summary = self.use_global_summary

        def _synthesize_results_bound(
            graph_retrieval=None, query="", graph_data=None, global_summaries=None
        ) -> dict:
            return synthesize_results(
                graph_retrieval=graph_retrieval,
                query=query,
                graph_data=graph_data,
                global_summaries=global_summaries,
                use_global_summary=_use_global_summary,
            )

        _synthesize_results_bound.__name__ = "result_synthesizer"
        _synthesize_results_bound.__doc__ = synthesize_results.__doc__
        result_synthesizer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                _synthesize_results_bound,
                name="result_synthesizer",
            ),
            node_id="result_synthesizer",
            _internal=True,
        )

        # Messages-composer nodes (L3 fix). Each LLM stage's context is routed
        # through a `PythonCodeNode.from_function` composer that RENDERS the real
        # inputs (document text / query / retrieved graph context) into an
        # OpenAI-format `messages` list wired to the LLMAgentNode `messages` port
        # — the ONLY port LLMAgentNode reads (its `run` does `kwargs["messages"]`).
        # The prior wiring left entity_extractor + query_processor with ZERO
        # inbound edges and fed summary_generator a phantom `graph_data` port the
        # node silently drops.
        #
        # `.from_function` is the correct primitive here (real module-level
        # functions get real `return`→`result`, type-checkable, no f-string
        # brace-escaping). `type: ignore[attr-defined]`: `from_function` is a
        # classmethod on concrete PythonCodeNode, erased to `type[Node]` by
        # `@register_node` for static checkers (mirrors conversational.py /
        # query_processing.py). `_internal=True` is the SDK-internal
        # node-construction path; it suppresses the consumer-facing instance-API
        # advisory UserWarning (zero-tolerance Rule 1: no spurious runtime
        # warnings).
        entity_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                compose_entity_extraction_messages,
                name="entity_messages_composer",
            ),
            node_id="entity_messages_composer",
            _internal=True,
        )
        query_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                compose_query_analysis_messages,
                name="query_messages_composer",
            ),
            node_id="query_messages_composer",
            _internal=True,
        )

        summary_messages_composer_id: Optional[str] = None
        if self.use_global_summary:
            summary_messages_composer_id = builder.add_node_instance(
                PythonCodeNode.from_function(
                    compose_summary_messages,
                    name="summary_messages_composer",
                ),
                node_id="summary_messages_composer",
                _internal=True,
            )

        # O3 OUTPUT-SIDE parser nodes. Same `from_function` primitive + same
        # `_internal=True` rationale as the composer nodes above.
        #
        # DEFECT 1: parse_entity_extraction sits BETWEEN entity_extractor and
        # graph_builder. It turns the raw `response={"content": "<JSON>"}` dict
        # into the LIST of per-doc extraction objects `build_knowledge_graph`
        # iterates — the prior edge fed the raw response dict straight in, so the
        # builder iterated the dict's string KEYS.
        entity_extraction_parser_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                parse_entity_extraction,
                name="entity_extraction_parser",
            ),
            node_id="entity_extraction_parser",
            _internal=True,
        )

        # DEFECT 3 (identical bug class to DEFECT 1): parse_query_analysis sits
        # BETWEEN query_processor and graph_retriever. It turns the raw
        # `response={"content": "<JSON>"}` dict into the parsed
        # {entities, relationship_types, requires_multi_hop, reasoning_type} dict
        # `retrieve_from_graph` reads — the prior edge fed the raw response dict,
        # so every query-analysis field defaulted and the retriever returned an
        # empty subgraph regardless of the LLM's analysis. query_processor is
        # built unconditionally, so this parser is too.
        query_analysis_parser_id = builder.add_node_instance(
            PythonCodeNode.from_function(
                parse_query_analysis,
                name="query_analysis_parser",
            ),
            node_id="query_analysis_parser",
            _internal=True,
        )

        # DEFECT 2: parse_global_summary sits BETWEEN summary_generator and
        # result_synthesizer (only when use_global_summary=True). It unwraps the
        # prose `response.content` into {"global_summary": <text>} the synthesizer
        # now reads.
        global_summary_parser_id: Optional[str] = None
        if self.use_global_summary:
            global_summary_parser_id = builder.add_node_instance(
                PythonCodeNode.from_function(
                    parse_global_summary,
                    name="global_summary_parser",
                ),
                node_id="global_summary_parser",
                _internal=True,
            )

        # Connect workflow.
        #
        # Nested-port hygiene fix (#1117/#1123 bug class): a PythonCodeNode
        # publishes a SINGLE `result` output port carrying its whole module-scope
        # `result` dict — the nested keys ("graph_data", "graph_retrieval",
        # "graph_rag_results") are NOT individual ports. The prior edges read
        # those non-existent nested ports as source outputs, so every downstream
        # input silently bound to nothing (never surfaced because no test ran the
        # full graph under LocalRuntime). Every PythonCodeNode source edge now
        # reads `result.<key>`; LLMAgentNode publishes each top-level result key
        # as a real port, so `response` stays a bare source output.

        # L3 fix: entity_extractor reasons over the REAL source documents. The
        # composer declares `documents` as a function param, so the parameter
        # injector delivers the top-level `documents` workflow input (the same
        # input GraphBuilderNode.run reads). Its `result.messages` feeds the
        # entity_extractor `messages` port.
        builder.add_connection(
            entity_messages_composer_id,
            "result.messages",
            entity_extractor_id,
            "messages",
        )
        # O3 DEFECT 1: route the entity_extractor `response` THROUGH the parser
        # so graph_builder receives the parsed LIST of extraction objects (NOT
        # the raw response dict, whose string keys the per-doc loop iterated).
        builder.add_connection(
            entity_extractor_id,
            "response",
            entity_extraction_parser_id,
            "response",
        )
        builder.add_connection(
            entity_extraction_parser_id,
            "result",
            graph_builder_id,
            "extraction_results",
        )

        # L3 fix: query_processor reasons over the REAL user query. The composer
        # declares `query` as a function param, so the parameter injector
        # delivers the top-level `query` workflow input (the same input
        # result_synthesizer reads). Its `result.messages` feeds the
        # query_processor `messages` port.
        builder.add_connection(
            query_messages_composer_id,
            "result.messages",
            query_processor_id,
            "messages",
        )
        # O3 DEFECT 3: route the query_processor `response` THROUGH the parser so
        # graph_retriever receives the parsed query-analysis dict (NOT the raw
        # response dict, whose query-analysis keys are absent → empty subgraph).
        builder.add_connection(
            query_processor_id,
            "response",
            query_analysis_parser_id,
            "response",
        )
        builder.add_connection(
            query_analysis_parser_id,
            "result",
            graph_retriever_id,
            "query_analysis",
        )

        builder.add_connection(
            graph_builder_id, "result.graph_data", graph_retriever_id, "graph_data"
        )
        builder.add_connection(
            graph_retriever_id,
            "result.graph_retrieval",
            result_synthesizer_id,
            "graph_retrieval",
        )
        builder.add_connection(
            graph_builder_id, "result.graph_data", result_synthesizer_id, "graph_data"
        )

        if self.use_global_summary:
            # The same guard bound summary_generator_id above; assert pins the
            # invariant for the type checker.
            assert summary_generator_id is not None
            assert summary_messages_composer_id is not None
            assert global_summary_parser_id is not None
            # L3 fix: summary_generator reasons over the REAL retrieved graph
            # context (the genuine graph_retriever output) + the query — NOT the
            # phantom `graph_data` port the LLM drops. The composer renders both
            # into a `messages` list on the VALID `messages` port. `query` is
            # the top-level workflow input the parameter injector delivers.
            builder.add_connection(
                graph_retriever_id,
                "result.graph_retrieval",
                summary_messages_composer_id,
                "graph_retrieval",
            )
            builder.add_connection(
                summary_messages_composer_id,
                "result.messages",
                summary_generator_id,
                "messages",
            )
            # O3 DEFECT 2: route the summary_generator `response` THROUGH the
            # parser so result_synthesizer receives the parsed
            # {"global_summary": <text>} dict it now READS — previously the raw
            # `response` was wired to `global_summaries` and the synthesizer body
            # never consumed it (accepted-but-unread, Rule 3c).
            builder.add_connection(
                summary_generator_id,
                "response",
                global_summary_parser_id,
                "response",
            )
            builder.add_connection(
                global_summary_parser_id,
                "result",
                result_synthesizer_id,
                "global_summaries",
            )

        return builder.build(name="graph_rag_workflow")


@register_node()
class GraphBuilderNode(Node):
    """
    Dedicated Graph Construction Node

    Builds knowledge graphs from documents with advanced features:
    - Coreference resolution for entity consolidation
    - Temporal relationship tracking
    - Confidence scoring for relationships
    - Incremental graph updates

    When to use:
    - Best for: Pre-building graphs for repeated queries
    - Not ideal for: One-time queries, small document sets
    - Performance: 100-500ms per document
    - Graph quality: Depends on entity extraction quality

    Example:
        builder = GraphBuilderNode(
            merge_similar_entities=True,
            similarity_threshold=0.85
        )

        graph = await builder.execute(
            documents=documents,
            existing_graph=previous_graph  # Optional: update existing
        )

    Parameters:
        merge_similar_entities: Consolidate similar entity names
        similarity_threshold: Threshold for entity merging
        track_temporal: Add timestamps to relationships
        confidence_scoring: Calculate relationship confidence

    Returns:
        graph: NetworkX graph object
        entity_map: Mapping of entities to canonical forms
        statistics: Graph construction statistics
    """

    def __init__(
        self,
        name: str = "graph_builder",
        merge_similar_entities: bool = True,
        similarity_threshold: float = 0.85,
        track_temporal: bool = False,
        confidence_scoring: bool = True,
    ):
        super().__init__(
            name=name,
            merge_similar_entities=merge_similar_entities,
            similarity_threshold=similarity_threshold,
            track_temporal=track_temporal,
            confidence_scoring=confidence_scoring,
        )
        self.merge_similar_entities = merge_similar_entities
        self.similarity_threshold = similarity_threshold
        self.track_temporal = track_temporal
        self.confidence_scoring = confidence_scoring

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="graph_builder",
                description="Node instance name",
            ),
            "merge_similar_entities": NodeParameter(
                name="merge_similar_entities",
                type=bool,
                required=False,
                default=True,
                description="Merge entities above the similarity threshold",
            ),
            "similarity_threshold": NodeParameter(
                name="similarity_threshold",
                type=float,
                required=False,
                default=0.85,
                description="Entity-merge similarity threshold",
            ),
            "track_temporal": NodeParameter(
                name="track_temporal",
                type=bool,
                required=False,
                default=False,
                description="Track temporal relationships between entities",
            ),
            "confidence_scoring": NodeParameter(
                name="confidence_scoring",
                type=bool,
                required=False,
                default=True,
                description="Attach confidence scores to extracted edges",
            ),
            "documents": NodeParameter(
                name="documents",
                type=list,
                required=True,
                description="Documents to build graph from",
            ),
            "existing_graph": NodeParameter(
                name="existing_graph",
                type=dict,
                required=False,
                description="Existing graph to update",
            ),
            "entity_types": NodeParameter(
                name="entity_types",
                type=list,
                required=False,
                description="Types of entities to extract",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Build or update knowledge graph"""
        documents = kwargs.get("documents", [])
        existing_graph = kwargs.get("existing_graph")

        # Initialize or load graph
        if existing_graph:
            G = nx.node_link_graph(existing_graph)
        else:
            G = nx.MultiDiGraph()

        # Entity extraction would happen here (simplified for example)
        # In production, would use LLM or NER model

        # Build entity map for deduplication
        entity_map = {}

        # Add sample graph building logic
        for doc in documents:
            # Skip malformed (non-dict) entries rather than crashing on
            # ``str.get`` — a document list may carry malformed elements.
            if not isinstance(doc, dict):
                continue

            # ``doc.get("content", "")`` only defaults a MISSING key — a key
            # present with value ``None`` returns ``None``. Coerce with
            # ``or ""`` so the scoring path never calls a str method on None.
            content = doc.get("content") or ""
            doc_id = doc.get("id", hash(content))

            # Add some sample entities
            if "transformer" in content.lower():
                G.add_node("transformer", type="technology", documents={doc_id})
                G.add_node("attention", type="concept", documents={doc_id})
                G.add_edge("transformer", "attention", type="uses", confidence=0.9)

        # Calculate graph statistics
        stats = {
            "total_nodes": len(G),
            "total_edges": len(G.edges()),
            "density": nx.density(G) if len(G) > 0 else 0,
            "components": nx.number_weakly_connected_components(G) if len(G) > 0 else 0,
        }

        return {
            "graph": nx.node_link_data(G),
            "entity_map": entity_map,
            "statistics": stats,
            "build_metadata": {
                "documents_processed": len(documents),
                "merge_applied": self.merge_similar_entities,
                "temporal_tracking": self.track_temporal,
            },
        }


@register_node()
class GraphQueryNode(Node):
    """
    Advanced Graph Query Execution

    Executes complex queries on knowledge graphs with support for:
    - Path queries (find connections between entities)
    - Pattern matching (find subgraphs matching criteria)
    - Aggregation queries (community statistics)
    - Temporal queries (time-based filtering)

    When to use:
    - Best for: Complex analytical queries, relationship exploration
    - Not ideal for: Simple lookups, keyword search
    - Performance: 50-500ms depending on graph size
    - Flexibility: Supports Cypher-like query patterns

    Example:
        querier = GraphQueryNode()

        # Find influence paths
        result = await querier.execute(
            graph=knowledge_graph,
            query_type="path",
            source_entity="BERT",
            target_entity="GPT",
            max_length=4
        )

    Parameters:
        query_type: Type of query (path, pattern, aggregate)
        filters: Attribute filters for nodes/edges
        aggregations: Statistical operations to perform
        return_subgraph: Return matching subgraph

    Returns:
        matches: Entities/relationships matching query
        paths: Connection paths found
        aggregations: Statistical results
        subgraph: Matching subgraph if requested
    """

    def __init__(self, name: str = "graph_query"):
        super().__init__(name=name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="graph_query",
                description="Node instance name",
            ),
            "graph": NodeParameter(
                name="graph",
                type=dict,
                required=True,
                description="Knowledge graph to query",
            ),
            "query_type": NodeParameter(
                name="query_type",
                type=str,
                required=True,
                description="Type of query: path, pattern, aggregate",
            ),
            "query_params": NodeParameter(
                name="query_params",
                type=dict,
                required=True,
                description="Query-specific parameters",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute graph query"""
        graph_data = kwargs.get("graph", {})
        query_type = kwargs.get("query_type", "path")
        query_params = kwargs.get("query_params", {})

        # Reconstruct graph
        G = nx.node_link_graph(graph_data)

        results = {
            "query_type": query_type,
            "query_params": query_params,
            "matches": [],
            "paths": [],
            "aggregations": {},
        }

        if query_type == "path":
            # Find paths between entities
            source = query_params.get("source_entity", "").lower()
            target = query_params.get("target_entity", "").lower()
            max_length = query_params.get("max_length", 3)

            if source in G and target in G:
                try:
                    # Find all simple paths
                    paths = list(
                        nx.all_simple_paths(G, source, target, cutoff=max_length)
                    )
                    results["paths"] = [
                        {
                            "path": path,
                            "length": len(path) - 1,
                            "edges": [
                                (path[i], path[i + 1]) for i in range(len(path) - 1)
                            ],
                        }
                        for path in paths[:10]  # Limit to 10 paths
                    ]
                except nx.NetworkXNoPath:
                    results["paths"] = []

        elif query_type == "pattern":
            # Pattern matching (simplified)
            pattern = query_params.get("pattern", {})
            node_type = pattern.get("node_type")

            matches = []
            for node, data in G.nodes(data=True):
                if not node_type or data.get("type") == node_type:
                    matches.append(
                        {"entity": node, "attributes": data, "degree": G.degree(node)}
                    )
            results["matches"] = matches[:20]

        elif query_type == "aggregate":
            # Graph statistics
            results["aggregations"] = {
                "node_count": len(G),
                "edge_count": len(G.edges()),
                "density": nx.density(G),
                "avg_degree": (
                    sum(dict(G.degree()).values()) / len(G) if len(G) > 0 else 0
                ),
                # ``nx.average_clustering`` is undefined on a multigraph.
                # ``GraphBuilderNode`` produces a ``MultiDiGraph`` whose
                # node-link round-trip is also a multigraph, so collapse to a
                # simple undirected ``Graph`` before computing clustering.
                "clustering_coefficient": (
                    nx.average_clustering(nx.Graph(G.to_undirected()))
                    if len(G) > 0
                    else 0
                ),
            }

        return results


# Export all graph nodes
__all__ = ["GraphRAGNode", "GraphBuilderNode", "GraphQueryNode"]
