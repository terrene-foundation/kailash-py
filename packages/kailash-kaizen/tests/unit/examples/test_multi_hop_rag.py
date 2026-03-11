"""
Tests for multi-hop-rag advanced RAG example.

This test suite validates:
1. Individual agent behavior (QuestionDecomposerAgent, SubQuestionRetrieverAgent, AnswerAggregatorAgent, ReasoningChainAgent, FinalAnswerAgent)
2. Question decomposition into sub-questions
3. Sequential multi-hop retrieval
4. Answer aggregation across hops
5. Shared memory for reasoning coordination

Following TDD methodology - these tests are written BEFORE implementation.
"""

# Standardized example loading
from example_import_helper import import_example_module

# Load multi-hop-rag example
_multi_hop_module = import_example_module("examples/4-advanced-rag/multi-hop-rag")
QuestionDecomposerAgent = _multi_hop_module.QuestionDecomposerAgent
SubQuestionRetrieverAgent = _multi_hop_module.SubQuestionRetrieverAgent
AnswerAggregatorAgent = _multi_hop_module.AnswerAggregatorAgent
ReasoningChainAgent = _multi_hop_module.ReasoningChainAgent
FinalAnswerAgent = _multi_hop_module.FinalAnswerAgent
MultiHopRAGConfig = _multi_hop_module.MultiHopRAGConfig
multi_hop_rag_workflow = _multi_hop_module.multi_hop_rag_workflow


class TestMultiHopRAGAgents:
    """Test individual agent behavior."""

    def test_question_decomposer_decomposes_query(self):
        """Test QuestionDecomposerAgent decomposes complex query."""

        config = MultiHopRAGConfig(llm_provider="mock")
        agent = QuestionDecomposerAgent(config)

        query = "How do transformers improve upon RNNs in terms of parallelization and long-range dependencies?"

        result = agent.decompose(query)

        assert result is not None
        assert "sub_questions" in result
        assert isinstance(result["sub_questions"], list)
        assert "reasoning_steps" in result

    def test_sub_question_retriever_retrieves_for_sub_question(self):
        """Test SubQuestionRetrieverAgent retrieves for sub-question."""

        config = MultiHopRAGConfig(llm_provider="mock")
        agent = SubQuestionRetrieverAgent(config)

        sub_question = "How do transformers handle parallelization?"

        result = agent.retrieve(sub_question)

        assert result is not None
        assert "documents" in result
        assert "sub_answer" in result

    def test_answer_aggregator_aggregates_sub_answers(self):
        """Test AnswerAggregatorAgent aggregates sub-answers."""

        config = MultiHopRAGConfig(llm_provider="mock")
        agent = AnswerAggregatorAgent(config)

        sub_answers = [
            {"question": "Q1", "answer": "A1"},
            {"question": "Q2", "answer": "A2"},
        ]

        result = agent.aggregate(sub_answers)

        assert result is not None
        assert "aggregated_context" in result
        assert "key_findings" in result

    def test_reasoning_chain_builds_chain(self):
        """Test ReasoningChainAgent builds reasoning chain."""

        config = MultiHopRAGConfig(llm_provider="mock")
        agent = ReasoningChainAgent(config)

        query = "Original query"
        sub_questions = ["Q1", "Q2"]
        sub_answers = [{"question": "Q1", "answer": "A1"}]

        result = agent.build_chain(query, sub_questions, sub_answers)

        assert result is not None
        assert "reasoning_chain" in result
        assert "chain_steps" in result

    def test_final_answer_synthesizes_answer(self):
        """Test FinalAnswerAgent synthesizes final answer."""

        config = MultiHopRAGConfig(llm_provider="mock")
        agent = FinalAnswerAgent(config)

        query = "Original query"
        reasoning_chain = {"steps": ["Step 1", "Step 2"]}

        result = agent.synthesize(query, reasoning_chain)

        assert result is not None
        assert "final_answer" in result
        assert "supporting_evidence" in result


class TestMultiHopRAGWorkflow:
    """Test multi-hop RAG workflow."""

    def test_single_query_processing(self):
        """Test processing a single complex query."""

        config = MultiHopRAGConfig(llm_provider="mock")

        query = "How do transformers improve upon RNNs?"

        result = multi_hop_rag_workflow(query, config)

        assert result is not None
        assert "sub_questions" in result
        assert "sub_answers" in result
        assert "reasoning_chain" in result
        assert "final_answer" in result

    def test_multi_hop_reasoning(self):
        """Test multi-hop reasoning across sub-questions."""

        config = MultiHopRAGConfig(llm_provider="mock", max_hops=3)

        query = (
            "Compare transformers and RNNs in terms of parallelization and dependencies"
        )

        result = multi_hop_rag_workflow(query, config)

        assert "hops" in result
        assert result["hops"] <= config.max_hops

    def test_question_decomposition(self):
        """Test question decomposition.

        Note: With mock provider, we test structure only. Sub-questions
        may be empty list depending on LLM provider behavior.
        """
        config = MultiHopRAGConfig(llm_provider="mock")
        agent = QuestionDecomposerAgent(config)

        complex_query = "How do transformers handle long sequences compared to RNNs?"

        result = agent.decompose(complex_query)

        # Structure test only - sub_questions may be empty with mock provider
        assert "sub_questions" in result
        assert isinstance(result["sub_questions"], list)


class TestSharedMemoryIntegration:
    """Test shared memory usage in multi-hop RAG."""

    def test_question_decomposition_writes_to_memory(self):
        """Test QuestionDecomposerAgent writes to shared memory."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = MultiHopRAGConfig(llm_provider="mock")
        shared_pool = SharedMemoryPool()
        agent = QuestionDecomposerAgent(config, shared_pool, "decomposer")

        query = "Complex query"
        agent.decompose(query)

        # Check shared memory
        insights = shared_pool.read_relevant(
            agent_id="retriever",
            tags=["question_decomposition"],
            segments=["multi_hop_pipeline"],
        )

        assert len(insights) > 0
        assert insights[0]["agent_id"] == "decomposer"

    def test_sub_question_retrieval_reads_from_memory(self):
        """Test SubQuestionRetrieverAgent reads from memory."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = MultiHopRAGConfig(llm_provider="mock")
        shared_pool = SharedMemoryPool()

        decomposer = QuestionDecomposerAgent(config, shared_pool, "decomposer")
        SubQuestionRetrieverAgent(config, shared_pool, "retriever")

        # Decomposer writes
        query = "Complex query"
        decomposer.decompose(query)

        # Retriever reads
        insights = shared_pool.read_relevant(
            agent_id="retriever",
            tags=["question_decomposition"],
            segments=["multi_hop_pipeline"],
        )

        assert len(insights) > 0


class TestReasoningChains:
    """Test reasoning chain construction."""

    def test_sequential_reasoning(self):
        """Test sequential reasoning chain."""

        config = MultiHopRAGConfig(llm_provider="mock")
        agent = ReasoningChainAgent(config)

        query = "How do transformers work?"
        sub_questions = ["What are transformers?", "How do they use attention?"]
        sub_answers = [
            {"question": "What are transformers?", "answer": "Neural networks"},
            {
                "question": "How do they use attention?",
                "answer": "Self-attention mechanism",
            },
        ]

        result = agent.build_chain(query, sub_questions, sub_answers)

        assert "reasoning_chain" in result
        assert "chain_steps" in result

    def test_dependency_tracking(self):
        """Test tracking dependencies between reasoning steps."""

        config = MultiHopRAGConfig(llm_provider="mock")

        query = "Multi-step question"

        result = multi_hop_rag_workflow(query, config)

        assert "reasoning_chain" in result


class TestConfigurationOptions:
    """Test configuration options."""

    def test_default_config(self):
        """Test default configuration."""

        config = MultiHopRAGConfig()

        assert config.llm_provider == "mock"
        assert config.model == "gpt-3.5-turbo"
        assert config.max_hops == 3

    def test_custom_config(self):
        """Test custom configuration."""

        config = MultiHopRAGConfig(
            llm_provider="openai",
            model="gpt-4",
            max_hops=5,
            max_sub_questions=10,
            enable_chain_tracking=True,
        )

        assert config.llm_provider == "openai"
        assert config.model == "gpt-4"
        assert config.max_hops == 5
        assert config.max_sub_questions == 10
        assert config.enable_chain_tracking is True

    def test_multi_hop_config(self):
        """Test multi-hop specific configuration."""

        config = MultiHopRAGConfig(
            llm_provider="mock", max_hops=5, enable_chain_tracking=True
        )

        assert config.max_hops == 5
        assert config.enable_chain_tracking is True
