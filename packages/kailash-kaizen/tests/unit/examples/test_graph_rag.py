"""
Tests for graph-rag advanced RAG example.

This test suite validates:
1. Individual agent behavior (EntityExtractorAgent, RelationshipMapperAgent, GraphQueryAgent, ContextAggregatorAgent, AnswerSynthesizerAgent)
2. Knowledge graph construction and querying
3. Entity-relationship extraction
4. Multi-hop graph traversal
5. Shared memory for graph coordination

Following TDD methodology - these tests are written BEFORE implementation.
"""

# Standardized example loading
from example_import_helper import import_example_module

# Load graph-rag example
_graph_rag_module = import_example_module("examples/4-advanced-rag/graph-rag")
EntityExtractorAgent = _graph_rag_module.EntityExtractorAgent
RelationshipMapperAgent = _graph_rag_module.RelationshipMapperAgent
GraphQueryAgent = _graph_rag_module.GraphQueryAgent
ContextAggregatorAgent = _graph_rag_module.ContextAggregatorAgent
AnswerSynthesizerAgent = _graph_rag_module.AnswerSynthesizerAgent
GraphRAGConfig = _graph_rag_module.GraphRAGConfig
graph_rag_workflow = _graph_rag_module.graph_rag_workflow


class TestGraphRAGAgents:
    """Test individual agent behavior."""

    def test_entity_extractor_extracts_entities(self):
        """Test EntityExtractorAgent extracts entities from query."""

        config = GraphRAGConfig(llm_provider="mock")
        agent = EntityExtractorAgent(config)

        query = (
            "What is the relationship between transformers and attention mechanisms?"
        )

        result = agent.extract(query)

        assert result is not None
        assert "entities" in result
        assert isinstance(result["entities"], list)

    def test_relationship_mapper_maps_relationships(self):
        """Test RelationshipMapperAgent maps entity relationships."""

        config = GraphRAGConfig(llm_provider="mock")
        agent = RelationshipMapperAgent(config)

        entities = ["transformers", "attention mechanisms"]

        result = agent.map_relationships(entities)

        assert result is not None
        assert "relationships" in result
        assert isinstance(result["relationships"], list)

    def test_graph_query_queries_graph(self):
        """Test GraphQueryAgent queries knowledge graph."""

        config = GraphRAGConfig(llm_provider="mock")
        agent = GraphQueryAgent(config)

        entities = ["transformers"]
        relationships = [
            {"source": "transformers", "relation": "uses", "target": "attention"}
        ]

        result = agent.query(entities, relationships)

        assert result is not None
        assert "graph_results" in result

    def test_context_aggregator_aggregates_context(self):
        """Test ContextAggregatorAgent aggregates graph context."""

        config = GraphRAGConfig(llm_provider="mock")
        agent = ContextAggregatorAgent(config)

        graph_results = [
            {"entity": "transformers", "context": "Neural network architecture"}
        ]

        result = agent.aggregate(graph_results)

        assert result is not None
        assert "aggregated_context" in result

    def test_answer_synthesizer_synthesizes_answer(self):
        """Test AnswerSynthesizerAgent synthesizes answer from graph."""

        config = GraphRAGConfig(llm_provider="mock")
        agent = AnswerSynthesizerAgent(config)

        query = "What are transformers?"
        context = {"entities": ["transformers"], "relationships": []}

        result = agent.synthesize(query, context)

        assert result is not None
        assert "answer" in result
        assert "graph_evidence" in result


class TestGraphRAGWorkflow:
    """Test graph RAG workflow."""

    def test_single_query_processing(self):
        """Test processing a single query with graph retrieval."""

        config = GraphRAGConfig(llm_provider="mock")

        query = "What is the relationship between transformers and attention?"

        result = graph_rag_workflow(query, config)

        assert result is not None
        assert "entities" in result
        assert "relationships" in result
        assert "graph_results" in result
        assert "answer" in result

    def test_multi_hop_traversal(self):
        """Test multi-hop graph traversal."""

        config = GraphRAGConfig(llm_provider="mock", max_hops=3)

        query = "How do transformers relate to NLP through attention mechanisms?"

        result = graph_rag_workflow(query, config)

        assert result is not None
        assert "hops" in result

    def test_entity_relationship_extraction(self):
        """Test entity and relationship extraction."""

        config = GraphRAGConfig(llm_provider="mock")

        extractor = EntityExtractorAgent(config)
        mapper = RelationshipMapperAgent(config)

        query = "Compare RNNs and transformers"

        entities_result = extractor.extract(query)
        relationships_result = mapper.map_relationships(entities_result["entities"])

        assert "entities" in entities_result
        assert "relationships" in relationships_result


class TestSharedMemoryIntegration:
    """Test shared memory usage in graph RAG."""

    def test_entity_extraction_writes_to_memory(self):
        """Test EntityExtractorAgent writes entities to shared memory."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = GraphRAGConfig(llm_provider="mock")
        shared_pool = SharedMemoryPool()
        agent = EntityExtractorAgent(config, shared_pool, "extractor")

        query = "What are transformers?"
        agent.extract(query)

        # Check shared memory
        insights = shared_pool.read_relevant(
            agent_id="mapper", tags=["entity_extraction"], segments=["graph_pipeline"]
        )

        assert len(insights) > 0
        assert insights[0]["agent_id"] == "extractor"

    def test_relationship_mapping_reads_from_memory(self):
        """Test RelationshipMapperAgent reads entities from memory."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = GraphRAGConfig(llm_provider="mock")
        shared_pool = SharedMemoryPool()

        extractor = EntityExtractorAgent(config, shared_pool, "extractor")
        RelationshipMapperAgent(config, shared_pool, "mapper")

        # Extractor writes
        query = "What are transformers?"
        extractor.extract(query)

        # Mapper reads
        insights = shared_pool.read_relevant(
            agent_id="mapper", tags=["entity_extraction"], segments=["graph_pipeline"]
        )

        assert len(insights) > 0


class TestKnowledgeGraph:
    """Test knowledge graph operations."""

    def test_graph_construction(self):
        """Test knowledge graph construction."""

        config = GraphRAGConfig(llm_provider="mock")
        agent = GraphQueryAgent(config)

        entities = ["transformers", "attention"]
        relationships = [
            {"source": "transformers", "relation": "uses", "target": "attention"}
        ]

        result = agent.query(entities, relationships)

        assert "graph_results" in result

    def test_multi_hop_query(self):
        """Test multi-hop graph query."""

        config = GraphRAGConfig(llm_provider="mock", max_hops=2)

        query = "What connects transformers to language models?"

        result = graph_rag_workflow(query, config)

        assert "hops" in result
        assert result["hops"] <= 2

    def test_entity_linking(self):
        """Test entity linking in graph."""

        config = GraphRAGConfig(llm_provider="mock")
        agent = EntityExtractorAgent(config)

        query = "How do BERT and GPT compare?"

        result = agent.extract(query)

        assert "entities" in result
        assert isinstance(result["entities"], list)


class TestConfigurationOptions:
    """Test configuration options."""

    def test_default_config(self):
        """Test default configuration."""

        config = GraphRAGConfig()

        assert config.llm_provider == "mock"
        assert config.model == "gpt-3.5-turbo"
        assert config.max_hops == 2

    def test_custom_config(self):
        """Test custom configuration."""

        config = GraphRAGConfig(
            llm_provider="openai",
            model="gpt-4",
            max_hops=3,
            enable_entity_linking=True,
            graph_depth=4,
        )

        assert config.llm_provider == "openai"
        assert config.model == "gpt-4"
        assert config.max_hops == 3
        assert config.enable_entity_linking is True
        assert config.graph_depth == 4

    def test_graph_config(self):
        """Test graph-specific configuration."""

        config = GraphRAGConfig(
            llm_provider="mock", max_hops=3, enable_entity_linking=True
        )

        assert config.max_hops == 3
        assert config.enable_entity_linking is True
