"""
Tests for self-correcting-rag advanced RAG example.

This test suite validates:
1. Individual agent behavior (AnswerGeneratorAgent, ErrorDetectorAgent, CorrectionStrategyAgent, AnswerRefinerAgent, ValidationAgent)
2. Error detection in generated answers
3. Self-correction strategies
4. Answer refinement and validation
5. Shared memory for correction coordination

Following TDD methodology - these tests are written BEFORE implementation.
"""

# Standardized example loading
from example_import_helper import import_example_module

# Load self-correcting-rag example
_self_correcting_module = import_example_module(
    "examples/4-advanced-rag/self-correcting-rag"
)
AnswerGeneratorAgent = _self_correcting_module.AnswerGeneratorAgent
ErrorDetectorAgent = _self_correcting_module.ErrorDetectorAgent
CorrectionStrategyAgent = _self_correcting_module.CorrectionStrategyAgent
AnswerRefinerAgent = _self_correcting_module.AnswerRefinerAgent
ValidationAgent = _self_correcting_module.ValidationAgent
SelfCorrectingRAGConfig = _self_correcting_module.SelfCorrectingRAGConfig
self_correcting_rag_workflow = _self_correcting_module.self_correcting_rag_workflow


class TestSelfCorrectingRAGAgents:
    """Test individual agent behavior."""

    def test_answer_generator_generates_answer(self):
        """Test AnswerGeneratorAgent generates initial answer."""

        config = SelfCorrectingRAGConfig(llm_provider="mock")
        agent = AnswerGeneratorAgent(config)

        query = "What are transformers?"
        documents = [{"content": "Transformers are neural networks"}]

        result = agent.generate(query, documents)

        assert result is not None
        assert "answer" in result
        assert "confidence" in result

    def test_error_detector_detects_errors(self):
        """Test ErrorDetectorAgent detects errors in answer."""

        config = SelfCorrectingRAGConfig(llm_provider="mock")
        agent = ErrorDetectorAgent(config)

        query = "What are transformers?"
        answer = "Transformers are cars"
        documents = [{"content": "Transformers are neural networks"}]

        result = agent.detect(query, answer, documents)

        assert result is not None
        assert "has_errors" in result
        assert "error_types" in result

    def test_correction_strategy_selects_strategy(self):
        """Test CorrectionStrategyAgent selects correction strategy."""

        config = SelfCorrectingRAGConfig(llm_provider="mock")
        agent = CorrectionStrategyAgent(config)

        error_analysis = {"has_errors": True, "error_types": ["factual_error"]}

        result = agent.select_strategy(error_analysis)

        assert result is not None
        assert "strategy" in result
        assert "reasoning" in result

    def test_answer_refiner_refines_answer(self):
        """Test AnswerRefinerAgent refines answer."""

        config = SelfCorrectingRAGConfig(llm_provider="mock")
        agent = AnswerRefinerAgent(config)

        query = "What are transformers?"
        original_answer = "Transformers are cars"
        documents = [{"content": "Transformers are neural networks"}]
        strategy = "replace_with_evidence"

        result = agent.refine(query, original_answer, documents, strategy)

        assert result is not None
        assert "refined_answer" in result
        assert "corrections_made" in result

    def test_validation_agent_validates_answer(self):
        """Test ValidationAgent validates final answer."""

        config = SelfCorrectingRAGConfig(llm_provider="mock")
        agent = ValidationAgent(config)

        query = "What are transformers?"
        answer = "Transformers are neural networks"
        documents = [{"content": "Transformers are neural networks"}]

        result = agent.validate(query, answer, documents)

        assert result is not None
        assert "is_valid" in result
        assert "validation_score" in result


class TestSelfCorrectingRAGWorkflow:
    """Test self-correcting RAG workflow."""

    def test_single_query_processing(self):
        """Test processing a single query with self-correction."""

        config = SelfCorrectingRAGConfig(llm_provider="mock")

        query = "What are transformers in deep learning?"
        documents = [{"content": "Transformers are neural network architectures"}]

        result = self_correcting_rag_workflow(query, documents, config)

        assert result is not None
        assert "initial_answer" in result
        assert "error_detection" in result
        assert "final_answer" in result
        assert "validation" in result

    def test_error_detection_and_correction(self):
        """Test error detection triggers correction."""

        config = SelfCorrectingRAGConfig(llm_provider="mock", max_corrections=3)

        query = "What are transformers?"
        documents = [{"content": "Transformers are neural networks"}]

        result = self_correcting_rag_workflow(query, documents, config)

        assert "corrections" in result
        assert "correction_count" in result

    def test_iterative_refinement(self):
        """Test iterative refinement until valid."""

        config = SelfCorrectingRAGConfig(llm_provider="mock", max_corrections=5)

        query = "Complex question"
        documents = [{"content": "Answer data"}]

        result = self_correcting_rag_workflow(query, documents, config)

        assert "correction_count" in result
        assert result["correction_count"] <= config.max_corrections


class TestSharedMemoryIntegration:
    """Test shared memory usage in self-correcting RAG."""

    def test_answer_generation_writes_to_memory(self):
        """Test AnswerGeneratorAgent writes to shared memory."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = SelfCorrectingRAGConfig(llm_provider="mock")
        shared_pool = SharedMemoryPool()
        agent = AnswerGeneratorAgent(config, shared_pool, "generator")

        query = "What are transformers?"
        documents = [{"content": "Neural networks"}]
        agent.generate(query, documents)

        # Check shared memory
        insights = shared_pool.read_relevant(
            agent_id="detector",
            tags=["answer_generation"],
            segments=["correction_pipeline"],
        )

        assert len(insights) > 0
        assert insights[0]["agent_id"] == "generator"

    def test_error_detection_reads_from_memory(self):
        """Test ErrorDetectorAgent reads from memory."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = SelfCorrectingRAGConfig(llm_provider="mock")
        shared_pool = SharedMemoryPool()

        generator = AnswerGeneratorAgent(config, shared_pool, "generator")
        ErrorDetectorAgent(config, shared_pool, "detector")

        # Generator writes
        query = "What are transformers?"
        documents = [{"content": "Neural networks"}]
        generator.generate(query, documents)

        # Detector reads
        insights = shared_pool.read_relevant(
            agent_id="detector",
            tags=["answer_generation"],
            segments=["correction_pipeline"],
        )

        assert len(insights) > 0


class TestErrorDetection:
    """Test error detection capabilities."""

    def test_factual_error_detection(self):
        """Test detection of factual errors."""

        config = SelfCorrectingRAGConfig(llm_provider="mock")
        agent = ErrorDetectorAgent(config)

        query = "What are transformers?"
        answer = "Transformers are vehicles"
        documents = [{"content": "Transformers are neural networks"}]

        result = agent.detect(query, answer, documents)

        assert "has_errors" in result
        assert "error_types" in result

    def test_consistency_error_detection(self):
        """Test detection of consistency errors."""

        config = SelfCorrectingRAGConfig(llm_provider="mock")
        agent = ErrorDetectorAgent(config)

        query = "What are transformers?"
        answer = "Transformers use attention. They don't use attention."
        documents = [{"content": "Transformers use attention mechanisms"}]

        result = agent.detect(query, answer, documents)

        assert "has_errors" in result

    def test_relevance_error_detection(self):
        """Test detection of relevance errors."""

        config = SelfCorrectingRAGConfig(llm_provider="mock")
        agent = ErrorDetectorAgent(config)

        query = "What are transformers?"
        answer = "The weather is nice today"
        documents = [{"content": "Transformers are neural networks"}]

        result = agent.detect(query, answer, documents)

        assert "has_errors" in result


class TestConfigurationOptions:
    """Test configuration options."""

    def test_default_config(self):
        """Test default configuration."""

        config = SelfCorrectingRAGConfig()

        assert config.llm_provider == "mock"
        assert config.model == "gpt-3.5-turbo"
        assert config.max_corrections == 3

    def test_custom_config(self):
        """Test custom configuration."""

        config = SelfCorrectingRAGConfig(
            llm_provider="openai",
            model="gpt-4",
            max_corrections=5,
            validation_threshold=0.9,
            enable_self_critique=True,
        )

        assert config.llm_provider == "openai"
        assert config.model == "gpt-4"
        assert config.max_corrections == 5
        assert config.validation_threshold == 0.9
        assert config.enable_self_critique is True

    def test_correction_config(self):
        """Test correction-specific configuration."""

        config = SelfCorrectingRAGConfig(
            llm_provider="mock", max_corrections=5, enable_self_critique=True
        )

        assert config.max_corrections == 5
        assert config.enable_self_critique is True
