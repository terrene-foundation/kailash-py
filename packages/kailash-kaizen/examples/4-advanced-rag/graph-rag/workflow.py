"""
Graph RAG Advanced Example

This example demonstrates knowledge graph-based retrieval using multi-agent coordination.

Agents:
1. EntityExtractorAgent - Extracts entities from query
2. RelationshipMapperAgent - Maps relationships between entities
3. GraphQueryAgent - Queries knowledge graph structure
4. ContextAggregatorAgent - Aggregates graph context
5. AnswerSynthesizerAgent - Synthesizes answer from graph evidence

Use Cases:
- Knowledge graph-based QA
- Multi-hop reasoning over structured data
- Entity-relationship extraction
- Graph traversal and aggregation

Architecture Pattern: Graph Pipeline with Multi-Hop Traversal
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.signatures import InputField, OutputField, Signature

# ===== Configuration =====


@dataclass
class GraphRAGConfig:
    """Configuration for graph RAG workflow."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"
    max_hops: int = 2
    enable_entity_linking: bool = True
    graph_depth: int = 3


# ===== Signatures =====


class EntityExtractionSignature(Signature):
    """Signature for entity extraction."""

    query: str = InputField(description="User query to extract entities from")

    entities: str = OutputField(description="Extracted entities as JSON")
    entity_types: str = OutputField(description="Entity types as JSON")


class RelationshipMappingSignature(Signature):
    """Signature for relationship mapping."""

    entities: str = InputField(description="Entities to map relationships for as JSON")

    relationships: str = OutputField(description="Entity relationships as JSON")
    relationship_types: str = OutputField(description="Relationship types as JSON")


class GraphQuerySignature(Signature):
    """Signature for graph querying."""

    entities: str = InputField(description="Entities to query as JSON")
    relationships: str = InputField(description="Relationships to query as JSON")

    graph_results: str = OutputField(description="Graph query results as JSON")
    traversal_path: str = OutputField(description="Graph traversal path as JSON")


class ContextAggregationSignature(Signature):
    """Signature for context aggregation."""

    graph_results: str = InputField(description="Graph results to aggregate as JSON")

    aggregated_context: str = OutputField(description="Aggregated context")
    key_insights: str = OutputField(description="Key insights from graph as JSON")


class AnswerSynthesisSignature(Signature):
    """Signature for answer synthesis."""

    query: str = InputField(description="Original query")
    context: str = InputField(description="Graph context as JSON")

    answer: str = OutputField(description="Synthesized answer")
    graph_evidence: str = OutputField(description="Graph evidence as JSON")


# ===== Agents =====


class EntityExtractorAgent(BaseAgent):
    """Agent for extracting entities from query."""

    def __init__(
        self,
        config: GraphRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "extractor",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=EntityExtractionSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.graph_config = config

    def extract(self, query: str) -> Dict[str, Any]:
        """Extract entities from query."""
        # Run agent
        result = self.run(query=query)

        # Extract outputs
        entities_raw = result.get("entities", "[]")
        if isinstance(entities_raw, str):
            try:
                entities = json.loads(entities_raw) if entities_raw else []
            except:
                entities = [entities_raw]
        else:
            entities = entities_raw if isinstance(entities_raw, list) else []

        # UX Improvement: One-line extraction

        entity_types = self.extract_list(result, "entity_types", default=[])

        extraction_result = {"entities": entities, "entity_types": entity_types}

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=extraction_result,  # Auto-serialized
            tags=["entity_extraction", "graph_pipeline"],
            importance=0.9,
            segment="graph_pipeline",
        )

        return extraction_result


class RelationshipMapperAgent(BaseAgent):
    """Agent for mapping entity relationships."""

    def __init__(
        self,
        config: GraphRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "mapper",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=RelationshipMappingSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.graph_config = config

    def map_relationships(self, entities: List[str]) -> Dict[str, Any]:
        """Map relationships between entities."""
        # Run agent
        result = self.run(entities=json.dumps(entities))

        # Extract outputs
        # UX Improvement: One-line extraction

        relationships = self.extract_list(result, "relationships", default=[])

        # UX Improvement: One-line extraction

        relationship_types = self.extract_list(result, "relationship_types", default=[])

        mapping_result = {
            "relationships": relationships,
            "relationship_types": relationship_types,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=mapping_result,  # Auto-serialized
            tags=["relationship_mapping", "graph_pipeline"],
            importance=0.85,
            segment="graph_pipeline",
        )

        return mapping_result


class GraphQueryAgent(BaseAgent):
    """Agent for querying knowledge graph."""

    def __init__(
        self,
        config: GraphRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "query",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=GraphQuerySignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.graph_config = config

    def query(
        self, entities: List[str], relationships: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Query knowledge graph."""
        # Run agent
        result = self.run(
            entities=json.dumps(entities), relationships=json.dumps(relationships)
        )

        # Extract outputs
        graph_results_raw = result.get("graph_results", "[]")
        if isinstance(graph_results_raw, str):
            try:
                graph_results = (
                    json.loads(graph_results_raw) if graph_results_raw else []
                )
            except:
                graph_results = [{"result": graph_results_raw}]
        else:
            graph_results = (
                graph_results_raw if isinstance(graph_results_raw, list) else []
            )

        # UX Improvement: One-line extraction

        traversal_path = self.extract_list(result, "traversal_path", default=[])

        query_result = {
            "graph_results": graph_results,
            "traversal_path": traversal_path,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=query_result,  # Auto-serialized
            tags=["graph_query", "graph_pipeline"],
            importance=1.0,
            segment="graph_pipeline",
        )

        return query_result


class ContextAggregatorAgent(BaseAgent):
    """Agent for aggregating graph context."""

    def __init__(
        self,
        config: GraphRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "aggregator",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=ContextAggregationSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.graph_config = config

    def aggregate(self, graph_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate graph context."""
        # Run agent
        result = self.run(graph_results=json.dumps(graph_results))

        # Extract outputs
        aggregated_context = result.get("aggregated_context", "No context aggregated")

        key_insights_raw = result.get("key_insights", "[]")
        if isinstance(key_insights_raw, str):
            try:
                key_insights = json.loads(key_insights_raw) if key_insights_raw else []
            except:
                key_insights = [key_insights_raw]
        else:
            key_insights = (
                key_insights_raw if isinstance(key_insights_raw, list) else []
            )

        aggregation_result = {
            "aggregated_context": aggregated_context,
            "key_insights": key_insights,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=aggregation_result,  # Auto-serialized
            tags=["context_aggregation", "graph_pipeline"],
            importance=0.95,
            segment="graph_pipeline",
        )

        return aggregation_result


class AnswerSynthesizerAgent(BaseAgent):
    """Agent for synthesizing answer from graph."""

    def __init__(
        self,
        config: GraphRAGConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "synthesizer",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=AnswerSynthesisSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.graph_config = config

    def synthesize(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Synthesize answer from graph context."""
        # Run agent
        result = self.run(query=query, context=json.dumps(context))

        # Extract outputs
        answer = result.get("answer", "No answer generated")

        graph_evidence_raw = result.get("graph_evidence", "[]")
        if isinstance(graph_evidence_raw, str):
            try:
                graph_evidence = (
                    json.loads(graph_evidence_raw) if graph_evidence_raw else []
                )
            except:
                graph_evidence = [graph_evidence_raw]
        else:
            graph_evidence = (
                graph_evidence_raw if isinstance(graph_evidence_raw, list) else []
            )

        synthesis_result = {"answer": answer, "graph_evidence": graph_evidence}

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=synthesis_result,  # Auto-serialized
            tags=["answer_synthesis", "graph_pipeline"],
            importance=1.0,
            segment="graph_pipeline",
        )

        return synthesis_result


# ===== Workflow Functions =====


def graph_rag_workflow(
    query: str,
    config: Optional[GraphRAGConfig] = None,
    knowledge_graph: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute graph RAG workflow with knowledge graph traversal.

    Args:
        query: User query
        config: Configuration for graph RAG
        knowledge_graph: Optional knowledge graph (for testing)

    Returns:
        Complete graph RAG result with entities, relationships, graph results, and answer
    """
    if config is None:
        config = GraphRAGConfig()

    # Create shared memory pool
    shared_pool = SharedMemoryPool()

    # Create agents
    extractor = EntityExtractorAgent(config, shared_pool, "extractor")
    mapper = RelationshipMapperAgent(config, shared_pool, "mapper")
    query_agent = GraphQueryAgent(config, shared_pool, "query")
    aggregator = ContextAggregatorAgent(config, shared_pool, "aggregator")
    synthesizer = AnswerSynthesizerAgent(config, shared_pool, "synthesizer")

    # Stage 1: Extract entities
    entity_result = extractor.extract(query)
    entities = entity_result["entities"]

    # Stage 2: Map relationships
    relationship_result = mapper.map_relationships(entities)
    relationships = relationship_result["relationships"]

    # Stage 3: Query graph with multi-hop traversal
    graph_result = query_agent.query(entities, relationships)
    graph_results = graph_result["graph_results"]

    # Track hops (for multi-hop queries)
    hops = (
        min(len(graph_result["traversal_path"]), config.max_hops)
        if graph_result["traversal_path"]
        else 1
    )

    # Stage 4: Aggregate context
    aggregation = aggregator.aggregate(graph_results)

    # Stage 5: Synthesize answer
    context = {
        "entities": entities,
        "relationships": relationships,
        "graph_results": graph_results,
        "aggregated_context": aggregation["aggregated_context"],
        "key_insights": aggregation["key_insights"],
    }

    synthesis = synthesizer.synthesize(query, context)

    return {
        "query": query,
        "entities": entities,
        "entity_types": entity_result["entity_types"],
        "relationships": relationships,
        "relationship_types": relationship_result["relationship_types"],
        "graph_results": graph_results,
        "traversal_path": graph_result["traversal_path"],
        "hops": hops,
        "aggregated_context": aggregation["aggregated_context"],
        "key_insights": aggregation["key_insights"],
        "answer": synthesis["answer"],
        "graph_evidence": synthesis["graph_evidence"],
    }


# ===== Main Entry Point =====

if __name__ == "__main__":
    # Example usage
    config = GraphRAGConfig(llm_provider="mock")

    # Single query
    query = "What is the relationship between transformers and attention mechanisms?"

    print("=== Graph RAG Query ===")
    result = graph_rag_workflow(query, config)
    print(f"Query: {result['query']}")
    print(f"Entities: {result['entities']}")
    print(f"Relationships: {len(result['relationships'])}")
    print(f"Graph Results: {len(result['graph_results'])}")
    print(f"Hops: {result['hops']}")
    print(f"Answer: {result['answer'][:100]}...")

    # Multi-hop query
    multi_hop_query = "How do transformers relate to NLP through attention mechanisms?"

    print("\n=== Multi-Hop Graph Query ===")
    multi_hop_result = graph_rag_workflow(multi_hop_query, config)
    print(f"Entities: {multi_hop_result['entities']}")
    print(f"Relationships: {len(multi_hop_result['relationships'])}")
    print(f"Hops: {multi_hop_result['hops']}")
    print(f"Key Insights: {len(multi_hop_result['key_insights'])}")
