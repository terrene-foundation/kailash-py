"""
Tests for federated-rag advanced RAG example.

This test suite validates:
1. Individual agent behavior (SourceCoordinatorAgent, DistributedRetrieverAgent, ResultMergerAgent, ConsistencyCheckerAgent, FinalAggregatorAgent)
2. Source coordination and selection
3. Distributed retrieval across multiple sources
4. Result merging and deduplication
5. Consistency checking across sources
6. Shared memory for federated coordination

Following TDD methodology - these tests are written BEFORE implementation.
"""

# Standardized example loading
from example_import_helper import import_example_module

# Load federated-rag example
_federated_module = import_example_module("examples/4-advanced-rag/federated-rag")
SourceCoordinatorAgent = _federated_module.SourceCoordinatorAgent
DistributedRetrieverAgent = _federated_module.DistributedRetrieverAgent
ResultMergerAgent = _federated_module.ResultMergerAgent
ConsistencyCheckerAgent = _federated_module.ConsistencyCheckerAgent
FinalAggregatorAgent = _federated_module.FinalAggregatorAgent
FederatedRAGConfig = _federated_module.FederatedRAGConfig
federated_rag_workflow = _federated_module.federated_rag_workflow


class TestFederatedRAGAgents:
    """Test individual agent behavior."""

    def test_source_coordinator_selects_sources(self):
        """Test SourceCoordinatorAgent selects appropriate sources."""

        config = FederatedRAGConfig(llm_provider="mock")
        agent = SourceCoordinatorAgent(config)

        query = "What are transformers in deep learning?"
        available_sources = [
            {"id": "arxiv", "type": "papers"},
            {"id": "wikipedia", "type": "encyclopedia"},
            {"id": "docs", "type": "documentation"},
        ]

        result = agent.coordinate(query, available_sources)

        assert result is not None
        assert "selected_sources" in result
        assert isinstance(result["selected_sources"], list)
        assert "selection_reasoning" in result

    def test_distributed_retriever_retrieves_from_source(self):
        """Test DistributedRetrieverAgent retrieves from single source."""

        config = FederatedRAGConfig(llm_provider="mock")
        agent = DistributedRetrieverAgent(config)

        query = "What are transformers?"
        source = {"id": "arxiv", "type": "papers"}

        result = agent.retrieve(query, source)

        assert result is not None
        assert "documents" in result
        assert "source_id" in result
        assert result["source_id"] == "arxiv"

    def test_result_merger_merges_results(self):
        """Test ResultMergerAgent merges results from multiple sources."""

        config = FederatedRAGConfig(llm_provider="mock")
        agent = ResultMergerAgent(config)

        retrieval_results = [
            {"source_id": "arxiv", "documents": [{"content": "Doc 1"}]},
            {"source_id": "wikipedia", "documents": [{"content": "Doc 2"}]},
        ]

        result = agent.merge(retrieval_results)

        assert result is not None
        assert "merged_documents" in result
        assert isinstance(result["merged_documents"], list)
        assert "deduplication_count" in result

    def test_consistency_checker_checks_consistency(self):
        """Test ConsistencyCheckerAgent checks consistency across sources."""

        config = FederatedRAGConfig(llm_provider="mock")
        agent = ConsistencyCheckerAgent(config)

        query = "What are transformers?"
        merged_documents = [
            {"content": "Transformers are neural networks", "source": "arxiv"},
            {"content": "Transformers use attention", "source": "wikipedia"},
        ]

        result = agent.check(query, merged_documents)

        assert result is not None
        assert "consistency_score" in result
        assert "conflicts" in result
        assert isinstance(result["conflicts"], list)

    def test_final_aggregator_aggregates_answer(self):
        """Test FinalAggregatorAgent aggregates final answer."""

        config = FederatedRAGConfig(llm_provider="mock")
        agent = FinalAggregatorAgent(config)

        query = "What are transformers?"
        merged_documents = [{"content": "Doc 1"}, {"content": "Doc 2"}]
        consistency_result = {"consistency_score": 0.9, "conflicts": []}

        result = agent.aggregate(query, merged_documents, consistency_result)

        assert result is not None
        assert "final_answer" in result
        assert "source_attribution" in result


class TestFederatedRAGWorkflow:
    """Test federated RAG workflow."""

    def test_single_query_processing(self):
        """Test processing a single query across multiple sources."""

        config = FederatedRAGConfig(llm_provider="mock")

        query = "What are transformers in deep learning?"
        available_sources = [
            {"id": "arxiv", "type": "papers"},
            {"id": "wikipedia", "type": "encyclopedia"},
        ]

        result = federated_rag_workflow(query, available_sources, config)

        assert result is not None
        assert "selected_sources" in result
        assert "retrieval_results" in result
        assert "merged_documents" in result
        assert "consistency_score" in result
        assert "final_answer" in result

    def test_multi_source_retrieval(self):
        """Test retrieval from multiple sources."""

        config = FederatedRAGConfig(llm_provider="mock", max_sources=3)

        query = "Compare transformers and RNNs"
        available_sources = [
            {"id": "arxiv", "type": "papers"},
            {"id": "wikipedia", "type": "encyclopedia"},
            {"id": "docs", "type": "documentation"},
        ]

        result = federated_rag_workflow(query, available_sources, config)

        assert "retrieval_results" in result
        assert len(result["retrieval_results"]) <= config.max_sources

    def test_source_coordination(self):
        """Test source selection and coordination.

        Note: With mock provider, we test structure only. Content depends on
        LLM provider (real or mock).
        """
        config = FederatedRAGConfig(llm_provider="mock")
        agent = SourceCoordinatorAgent(config)

        query = "What are transformers?"
        sources = [
            {"id": "source1", "type": "type1"},
            {"id": "source2", "type": "type2"},
        ]

        result = agent.coordinate(query, sources)

        # Structure test only - selected_sources may be empty list with mock provider
        assert "selected_sources" in result
        assert isinstance(result["selected_sources"], list)


class TestSharedMemoryIntegration:
    """Test shared memory usage in federated RAG."""

    def test_source_coordination_writes_to_memory(self):
        """Test SourceCoordinatorAgent writes to shared memory."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = FederatedRAGConfig(llm_provider="mock")
        shared_pool = SharedMemoryPool()
        agent = SourceCoordinatorAgent(config, shared_pool, "coordinator")

        query = "Test query"
        sources = [{"id": "source1", "type": "type1"}]
        agent.coordinate(query, sources)

        # Check shared memory
        insights = shared_pool.read_relevant(
            agent_id="retriever",
            tags=["source_coordination"],
            segments=["federated_pipeline"],
        )

        assert len(insights) > 0
        assert insights[0]["agent_id"] == "coordinator"

    def test_distributed_retrieval_reads_from_memory(self):
        """Test DistributedRetrieverAgent reads from memory."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = FederatedRAGConfig(llm_provider="mock")
        shared_pool = SharedMemoryPool()

        coordinator = SourceCoordinatorAgent(config, shared_pool, "coordinator")
        DistributedRetrieverAgent(config, shared_pool, "retriever")

        # Coordinator writes
        query = "Test query"
        sources = [{"id": "source1", "type": "type1"}]
        coordinator.coordinate(query, sources)

        # Retriever reads
        insights = shared_pool.read_relevant(
            agent_id="retriever",
            tags=["source_coordination"],
            segments=["federated_pipeline"],
        )

        assert len(insights) > 0


class TestResultMergingAndDeduplication:
    """Test result merging and deduplication."""

    def test_result_merging(self):
        """Test merging results from multiple sources.

        Note: With mock provider, we test structure only. Content depends on
        LLM provider (real or mock).
        """
        config = FederatedRAGConfig(llm_provider="mock")
        agent = ResultMergerAgent(config)

        results = [
            {"source_id": "s1", "documents": [{"content": "Doc 1"}]},
            {"source_id": "s2", "documents": [{"content": "Doc 2"}]},
        ]

        result = agent.merge(results)

        # Structure test only - merged_documents may be empty list with mock provider
        assert "merged_documents" in result
        assert isinstance(result["merged_documents"], list)

    def test_deduplication(self):
        """Test deduplication of similar documents."""

        config = FederatedRAGConfig(llm_provider="mock", enable_deduplication=True)
        agent = ResultMergerAgent(config)

        results = [
            {"source_id": "s1", "documents": [{"content": "Same content"}]},
            {"source_id": "s2", "documents": [{"content": "Same content"}]},
        ]

        result = agent.merge(results)

        assert "deduplication_count" in result


class TestConsistencyChecking:
    """Test consistency checking across sources."""

    def test_consistency_scoring(self):
        """Test consistency scoring across sources."""

        config = FederatedRAGConfig(llm_provider="mock")
        agent = ConsistencyCheckerAgent(config)

        query = "Test query"
        documents = [
            {"content": "Fact 1", "source": "s1"},
            {"content": "Fact 2", "source": "s2"},
        ]

        result = agent.check(query, documents)

        assert "consistency_score" in result
        assert isinstance(result["consistency_score"], (int, float))

    def test_conflict_detection(self):
        """Test detecting conflicts across sources."""

        config = FederatedRAGConfig(llm_provider="mock")
        agent = ConsistencyCheckerAgent(config)

        query = "Test query"
        documents = [
            {"content": "Fact A", "source": "s1"},
            {"content": "Contradicts A", "source": "s2"},
        ]

        result = agent.check(query, documents)

        assert "conflicts" in result
        assert isinstance(result["conflicts"], list)


class TestConfigurationOptions:
    """Test configuration options."""

    def test_default_config(self):
        """Test default configuration."""

        config = FederatedRAGConfig()

        assert config.llm_provider == "mock"
        assert config.model == "gpt-3.5-turbo"
        assert config.max_sources == 5

    def test_custom_config(self):
        """Test custom configuration."""

        config = FederatedRAGConfig(
            llm_provider="openai",
            model="gpt-4",
            max_sources=10,
            enable_deduplication=True,
            consistency_threshold=0.9,
        )

        assert config.llm_provider == "openai"
        assert config.model == "gpt-4"
        assert config.max_sources == 10
        assert config.enable_deduplication is True
        assert config.consistency_threshold == 0.9

    def test_federated_config(self):
        """Test federated-specific configuration."""

        config = FederatedRAGConfig(
            llm_provider="mock", max_sources=3, enable_deduplication=True
        )

        assert config.max_sources == 3
        assert config.enable_deduplication is True
