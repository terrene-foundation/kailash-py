"""
Tests for agentic-rag advanced RAG example.

This test suite validates:
1. Individual agent behavior (QueryAnalyzerAgent, RetrievalStrategyAgent, DocumentRetrieverAgent, QualityAssessorAgent, AnswerGeneratorAgent)
2. Adaptive retrieval workflow
3. Multi-strategy retrieval (semantic, keyword, hybrid)
4. Quality-driven iteration
5. Shared memory for retrieval coordination

Following TDD methodology - these tests are written BEFORE implementation.
"""

# Standardized example loading
from example_import_helper import import_example_module

# Load agentic-rag example
_agentic_rag_module = import_example_module("examples/4-advanced-rag/agentic-rag")
QueryAnalyzerAgent = _agentic_rag_module.QueryAnalyzerAgent
RetrievalStrategyAgent = _agentic_rag_module.RetrievalStrategyAgent
DocumentRetrieverAgent = _agentic_rag_module.DocumentRetrieverAgent
QualityAssessorAgent = _agentic_rag_module.QualityAssessorAgent
AnswerGeneratorAgent = _agentic_rag_module.AnswerGeneratorAgent
AgenticRAGConfig = _agentic_rag_module.AgenticRAGConfig
agentic_rag_workflow = _agentic_rag_module.agentic_rag_workflow


class TestAgenticRAGAgents:
    """Test individual agent behavior."""

    def test_query_analyzer_analyzes_query(self):
        """Test QueryAnalyzerAgent analyzes query intent and complexity."""

        config = AgenticRAGConfig(llm_provider="mock")
        agent = QueryAnalyzerAgent(config)

        query = "What are the key differences between transformers and RNNs?"

        result = agent.analyze(query)

        assert result is not None
        assert "query_type" in result
        assert "complexity" in result
        assert "keywords" in result

    def test_retrieval_strategy_selects_strategy(self):
        """Test RetrievalStrategyAgent selects appropriate retrieval strategy."""

        config = AgenticRAGConfig(llm_provider="mock")
        agent = RetrievalStrategyAgent(config)

        query_analysis = {
            "query_type": "factual",
            "complexity": "medium",
            "keywords": ["transformers", "RNNs"],
        }

        result = agent.select_strategy(query_analysis)

        assert result is not None
        assert "strategy" in result
        assert result["strategy"] in ["semantic", "keyword", "hybrid"]

    def test_document_retriever_retrieves_documents(self):
        """Test DocumentRetrieverAgent retrieves documents."""

        config = AgenticRAGConfig(llm_provider="mock")
        agent = DocumentRetrieverAgent(config)

        query = "transformers"
        strategy = "semantic"

        result = agent.retrieve(query, strategy)

        assert result is not None
        assert "documents" in result
        assert isinstance(result["documents"], list)

    def test_quality_assessor_assesses_quality(self):
        """Test QualityAssessorAgent assesses retrieval quality."""

        config = AgenticRAGConfig(llm_provider="mock")
        agent = QualityAssessorAgent(config)

        query = "What are transformers?"
        documents = [{"content": "Transformers are neural network architectures"}]

        result = agent.assess(query, documents)

        assert result is not None
        assert "quality_score" in result
        assert "needs_refinement" in result

    def test_answer_generator_generates_answer(self):
        """Test AnswerGeneratorAgent generates answer."""

        config = AgenticRAGConfig(llm_provider="mock")
        agent = AnswerGeneratorAgent(config)

        query = "What are transformers?"
        documents = [{"content": "Transformers are neural networks"}]

        result = agent.generate(query, documents)

        assert result is not None
        assert "answer" in result
        assert "sources" in result


class TestAgenticRAGWorkflow:
    """Test agentic RAG workflow."""

    def test_single_query_processing(self):
        """Test processing a single query with adaptive retrieval."""

        config = AgenticRAGConfig(llm_provider="mock")

        query = "What are transformers in deep learning?"

        result = agentic_rag_workflow(query, config)

        assert result is not None
        assert "query_analysis" in result
        assert "retrieval_strategy" in result
        assert "documents" in result
        assert "quality_assessment" in result
        assert "answer" in result

    def test_iterative_refinement(self):
        """Test iterative refinement when quality is low."""

        config = AgenticRAGConfig(llm_provider="mock", max_iterations=3)

        query = "Complex multi-hop question"

        result = agentic_rag_workflow(query, config)

        assert result is not None
        assert "iterations" in result

    def test_strategy_selection(self):
        """Test different retrieval strategies are selected."""

        config = AgenticRAGConfig(llm_provider="mock")
        agent = RetrievalStrategyAgent(config)

        # Factual query
        factual_analysis = {"query_type": "factual", "complexity": "low"}
        factual_result = agent.select_strategy(factual_analysis)
        assert "strategy" in factual_result

        # Complex query
        complex_analysis = {"query_type": "analytical", "complexity": "high"}
        complex_result = agent.select_strategy(complex_analysis)
        assert "strategy" in complex_result


class TestSharedMemoryIntegration:
    """Test shared memory usage in agentic RAG."""

    def test_query_analysis_writes_to_memory(self):
        """Test QueryAnalyzerAgent writes analysis to shared memory."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = AgenticRAGConfig(llm_provider="mock")
        shared_pool = SharedMemoryPool()
        agent = QueryAnalyzerAgent(config, shared_pool, "analyzer")

        query = "What are transformers?"
        agent.analyze(query)

        # Check shared memory
        insights = shared_pool.read_relevant(
            agent_id="strategy", tags=["query_analysis"], segments=["rag_pipeline"]
        )

        assert len(insights) > 0
        assert insights[0]["agent_id"] == "analyzer"

    def test_strategy_reads_from_memory(self):
        """Test RetrievalStrategyAgent reads query analysis from memory."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = AgenticRAGConfig(llm_provider="mock")
        shared_pool = SharedMemoryPool()

        analyzer = QueryAnalyzerAgent(config, shared_pool, "analyzer")
        RetrievalStrategyAgent(config, shared_pool, "strategy")

        # Analyzer writes
        query = "What are transformers?"
        analyzer.analyze(query)

        # Strategy reads
        insights = shared_pool.read_relevant(
            agent_id="strategy", tags=["query_analysis"], segments=["rag_pipeline"]
        )

        assert len(insights) > 0


class TestRetrievalStrategies:
    """Test different retrieval strategies."""

    def test_semantic_retrieval(self):
        """Test semantic retrieval strategy."""

        config = AgenticRAGConfig(llm_provider="mock", retrieval_strategy="semantic")
        agent = DocumentRetrieverAgent(config)

        result = agent.retrieve("transformers", "semantic")

        assert result is not None
        assert "documents" in result

    def test_keyword_retrieval(self):
        """Test keyword retrieval strategy."""

        config = AgenticRAGConfig(llm_provider="mock", retrieval_strategy="keyword")
        agent = DocumentRetrieverAgent(config)

        result = agent.retrieve("transformers", "keyword")

        assert result is not None
        assert "documents" in result

    def test_hybrid_retrieval(self):
        """Test hybrid retrieval strategy."""

        config = AgenticRAGConfig(llm_provider="mock", retrieval_strategy="hybrid")
        agent = DocumentRetrieverAgent(config)

        result = agent.retrieve("transformers", "hybrid")

        assert result is not None
        assert "documents" in result


class TestConfigurationOptions:
    """Test configuration options."""

    def test_default_config(self):
        """Test default configuration."""

        config = AgenticRAGConfig()

        assert config.llm_provider == "mock"
        assert config.model == "gpt-3.5-turbo"
        assert config.max_iterations == 3

    def test_custom_config(self):
        """Test custom configuration."""

        config = AgenticRAGConfig(
            llm_provider="openai",
            model="gpt-4",
            max_iterations=5,
            retrieval_strategy="hybrid",
            top_k=10,
            quality_threshold=0.8,
        )

        assert config.llm_provider == "openai"
        assert config.model == "gpt-4"
        assert config.max_iterations == 5
        assert config.retrieval_strategy == "hybrid"
        assert config.top_k == 10
        assert config.quality_threshold == 0.8

    def test_adaptive_config(self):
        """Test adaptive retrieval configuration."""

        config = AgenticRAGConfig(
            llm_provider="mock", adaptive_retrieval=True, max_iterations=5
        )

        assert config.adaptive_retrieval is True
        assert config.max_iterations == 5
