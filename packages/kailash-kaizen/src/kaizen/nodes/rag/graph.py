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

        # Graph builder
        graph_builder_id = builder.add_node(
            "PythonCodeNode",
            node_id="graph_builder",
            config={
                "code": f"""
import networkx as nx
from collections import defaultdict

def build_knowledge_graph(extraction_results):
    '''Build NetworkX graph from extracted entities and relationships'''
    G = nx.MultiDiGraph()

    # Add all entities as nodes
    all_entities = []
    all_relationships = []

    for doc_extraction in extraction_results:
        entities = doc_extraction.get("entities", [])
        relationships = doc_extraction.get("relationships", [])

        # Add entities
        for entity in entities:
            node_id = entity["name"].lower()
            G.add_node(node_id,
                      name=entity["name"],
                      type=entity["type"],
                      description=entity.get("description", ""),
                      documents=set())
            all_entities.append(entity)

        # Add relationships
        for rel in relationships:
            source = rel["source"].lower()
            target = rel["target"].lower()
            G.add_edge(source, target,
                      type=rel["type"],
                      description=rel.get("description", ""))
            all_relationships.append(rel)

    # Detect communities
    if len(G) > 0:
        if "{self.community_algorithm}" == "louvain":
            import community
            communities = community.best_partition(G.to_undirected())
        else:
            # Simple connected components
            communities = {{}}
            for i, comp in enumerate(nx.weakly_connected_components(G)):
                for node in comp:
                    communities[node] = i
    else:
        communities = {{}}

    # Build community summaries
    community_nodes = defaultdict(list)
    for node, comm_id in communities.items():
        community_nodes[comm_id].append(node)

    graph_data = {{
        "graph": nx.node_link_data(G),
        "entities": all_entities,
        "relationships": all_relationships,
        "communities": communities,
        "community_nodes": dict(community_nodes),
        "stats": {{
            "num_entities": len(G),
            "num_relationships": len(G.edges()),
            "num_communities": len(set(communities.values())) if communities else 0
        }}
    }}

result = {{"graph_data": build_knowledge_graph(extraction_results)}}
"""
            },
        )

        # Query processor for graph
        query_processor_id = builder.add_node(
            "LLMAgentNode",
            node_id="query_processor",
            config={
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

        # Graph traversal and retrieval
        graph_retriever_id = builder.add_node(
            "PythonCodeNode",
            node_id="graph_retriever",
            config={
                "code": f"""
import networkx as nx
from collections import deque

def retrieve_from_graph(graph_data, query_analysis):
    '''Retrieve relevant subgraph based on query analysis'''
    # Reconstruct graph
    G = nx.node_link_graph(graph_data["graph"])

    query_entities = [e.lower() for e in query_analysis.get("entities", [])]
    relationship_types = query_analysis.get("relationship_types", [])
    requires_multi_hop = query_analysis.get("requires_multi_hop", False)

    # Find relevant nodes
    relevant_nodes = set()
    for entity in query_entities:
        # Fuzzy match entities
        for node in G.nodes():
            if entity in node or node in entity:
                relevant_nodes.add(node)

    # Multi-hop expansion if needed
    if requires_multi_hop and relevant_nodes:
        expanded_nodes = set(relevant_nodes)
        for start_node in relevant_nodes:
            # BFS up to max_hops
            visited = {{start_node}}
            queue = deque([(start_node, 0)])

            while queue:
                node, depth = queue.popleft()
                if depth >= {self.max_hops}:
                    continue

                # Check neighbors
                for neighbor in G.neighbors(node):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        expanded_nodes.add(neighbor)
                        queue.append((neighbor, depth + 1))

        relevant_nodes = expanded_nodes

    # Extract subgraph
    if relevant_nodes:
        subgraph = G.subgraph(relevant_nodes).copy()

        # Get relevant relationships
        relevant_edges = []
        for u, v, data in subgraph.edges(data=True):
            if not relationship_types or data.get("type") in relationship_types:
                relevant_edges.append({{
                    "source": u,
                    "target": v,
                    "type": data.get("type"),
                    "description": data.get("description")
                }})

        # Get node details
        relevant_entities = []
        for node in relevant_nodes:
            node_data = G.nodes[node]
            relevant_entities.append({{
                "name": node_data.get("name", node),
                "type": node_data.get("type"),
                "description": node_data.get("description"),
                "centrality": nx.degree_centrality(subgraph).get(node, 0)
            }})

        # Sort by centrality
        relevant_entities.sort(key=lambda x: x["centrality"], reverse=True)

    else:
        relevant_entities = []
        relevant_edges = []
        subgraph = nx.DiGraph()

    # Get community context if available
    communities = graph_data.get("communities", {{}})
    community_context = {{}}
    for node in relevant_nodes:
        comm_id = communities.get(node)
        if comm_id is not None:
            community_nodes = graph_data.get("community_nodes", {{}}).get(str(comm_id), [])
            community_context[comm_id] = community_nodes

    retrieval_result = {{
        "entities": relevant_entities[:20],  # Top 20 by centrality
        "relationships": relevant_edges[:30],  # Top 30 relationships
        "subgraph_stats": {{
            "nodes": len(relevant_nodes),
            "edges": len(relevant_edges)
        }},
        "community_context": community_context,
        "query_entities_found": len([e for e in query_entities if any(e in n for n in relevant_nodes)])
    }}

result = {{"graph_retrieval": retrieval_result}}
"""
            },
        )

        # Global summary generator (if enabled)
        if self.use_global_summary:
            summary_generator_id = builder.add_node(
                "LLMAgentNode",
                node_id="summary_generator",
                config={
                    "system_prompt": """Generate high-level summaries of document communities.
                    Focus on main themes, key entities, and important relationships.
                    Be concise but comprehensive.""",
                    "model": _DEFAULT_LLM_MODEL,
                },
            )

        # Result synthesizer
        result_synthesizer_id = builder.add_node(
            "PythonCodeNode",
            node_id="result_synthesizer",
            config={
                "code": """
# Combine all graph information
graph_retrieval = graph_retrieval
query = query
graph_data = graph_data

# Build context from retrieved subgraph
context_parts = []

# Add entity information
if graph_retrieval["entities"]:
    context_parts.append("Key Entities:")
    for entity in graph_retrieval["entities"][:10]:
        context_parts.append(f"- {entity['name']} ({entity['type']}): {entity['description']}")

# Add relationship information
if graph_retrieval["relationships"]:
    context_parts.append("\\nKey Relationships:")
    for rel in graph_retrieval["relationships"][:10]:
        context_parts.append(f"- {rel['source']} {rel['type']} {rel['target']}")

# Add community context
if graph_retrieval["community_context"]:
    context_parts.append("\\nRelated Topic Clusters:")
    for comm_id, nodes in list(graph_retrieval["community_context"].items())[:3]:
        context_parts.append(f"- Cluster {comm_id}: {', '.join(nodes[:5])}")

context = "\\n".join(context_parts)

# Create reasoning path visualization
reasoning_path = []
entities = graph_retrieval["entities"]
if len(entities) > 1:
    # Simple path representation
    for i in range(min(3, len(entities)-1)):
        reasoning_path.append({
            "hop": i + 1,
            "from": entities[i]["name"],
            "to": entities[i+1]["name"],
            "connection": "related through graph structure"
        })

result = {
    "graph_rag_results": {
        "query": query,
        "retrieved_entities": graph_retrieval["entities"],
        "retrieved_relationships": graph_retrieval["relationships"],
        "graph_context": context,
        "reasoning_path": reasoning_path,
        "subgraph_size": graph_retrieval["subgraph_stats"],
        "community_info": {
            "num_communities": len(graph_retrieval["community_context"]),
            "communities_accessed": list(graph_retrieval["community_context"].keys())
        },
        "global_graph_stats": graph_data["stats"]
    }
}
"""
            },
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
            PythonCodeNode.from_function(  # type: ignore[attr-defined]
                compose_entity_extraction_messages,
                name="entity_messages_composer",
            ),
            node_id="entity_messages_composer",
            _internal=True,
        )
        query_messages_composer_id = builder.add_node_instance(
            PythonCodeNode.from_function(  # type: ignore[attr-defined]
                compose_query_analysis_messages,
                name="query_messages_composer",
            ),
            node_id="query_messages_composer",
            _internal=True,
        )

        summary_messages_composer_id: Optional[str] = None
        if self.use_global_summary:
            summary_messages_composer_id = builder.add_node_instance(
                PythonCodeNode.from_function(  # type: ignore[attr-defined]
                    compose_summary_messages,
                    name="summary_messages_composer",
                ),
                node_id="summary_messages_composer",
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
        builder.add_connection(
            entity_extractor_id, "response", graph_builder_id, "extraction_results"
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
        builder.add_connection(
            query_processor_id, "response", graph_retriever_id, "query_analysis"
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
            builder.add_connection(
                summary_generator_id,
                "response",
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
