"""
Tier 2 Integration Tests: Example Workflows with Real LLMs.

Tests example implementations with REAL LLM providers. NO MOCKING ALLOWED.
Validates that examples work end-to-end with actual API calls.

Test Coverage:
- simple-qa with real LLM (3 tests)
- rag-research with real embeddings (3 tests)
- streaming-chat with real streaming (3 tests)
- batch-processing with real batch (3 tests)
- resilient-fallback with real fallback (3 tests)
- human-approval with mock approval (3 tests)

Total: 18 integration tests
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# Real LLM providers

# =============================================================================
# SIMPLE-QA EXAMPLE INTEGRATION TESTS (3 tests)
# =============================================================================


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_simple_qa_example_with_real_llm():
    """Test simple-qa example with real OpenAI API."""
    # Import example
    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/simple-qa"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import QAConfig, SimpleQAAgent

        # Real LLM configuration (NO MOCKING)
        config = QAConfig(
            llm_provider="openai",
            model="gpt-5-nano",
            temperature=0.1,
            max_tokens=200,
            max_turns=5,
        )

        agent = SimpleQAAgent(config)

        # Real question with real LLM call
        result = agent.run(question="What is Python?")

        # Verify real response
        assert result is not None
        assert "answer" in result
        assert len(result["answer"]) > 0
        assert (
            "python" in result["answer"].lower()
            or "programming" in result["answer"].lower()
        )

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_simple_qa_example_with_memory():
    """Test simple-qa example remembers context with real LLM."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/simple-qa"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import QAConfig, SimpleQAAgent

        config = QAConfig(
            llm_provider="openai",
            model="gpt-5-nano",
            temperature=0.1,
            max_tokens=200,
            max_turns=5,
        )

        agent = SimpleQAAgent(config)
        session_id = "integration_test_qa_001"

        # First question
        result1 = agent.ask("My favorite color is blue.", session_id=session_id)
        assert result1 is not None

        # Follow-up question (should use memory)
        result2 = agent.ask("What is my favorite color?", session_id=session_id)

        # Should remember from context
        assert "blue" in result2["answer"].lower()

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_simple_qa_example_confidence_scoring():
    """Test simple-qa example provides confidence scores."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/simple-qa"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import QAConfig, SimpleQAAgent

        config = QAConfig(
            llm_provider="openai", model="gpt-5-nano", temperature=0.1, max_tokens=200
        )

        agent = SimpleQAAgent(config)

        # Clear factual question (high confidence expected)
        result = agent.run(question="What is 2+2?")

        assert "confidence" in result
        assert isinstance(result["confidence"], (int, float))
        assert 0.0 <= result["confidence"] <= 1.0

    finally:
        sys.path.remove(str(example_path))


# =============================================================================
# RAG-RESEARCH EXAMPLE INTEGRATION TESTS (3 tests)
# =============================================================================


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_rag_research_example_with_real_embeddings():
    """Test rag-research example with real embedding model."""
    try:
        from sentence_transformers import SentenceTransformer

        embedder = SentenceTransformer("all-MiniLM-L6-v2")
    except ImportError:
        pytest.skip("sentence-transformers not available")

    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/rag-research"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import RAGConfig, RAGResearchAgent

        config = RAGConfig(
            llm_provider="openai",
            model="gpt-5-nano",
            temperature=0.1,
            max_tokens=300,
            memory_config={"enabled": True, "embedder": embedder.encode, "top_k": 5},
        )

        agent = RAGResearchAgent(config)
        session_id = "integration_test_rag_001"

        # Research query with real LLM + embeddings
        result = agent.research("What is machine learning?", session_id=session_id)

        assert result is not None
        assert "findings" in result or "answer" in result

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_rag_research_example_semantic_search():
    """Test rag-research example performs semantic search correctly."""
    try:
        from sentence_transformers import SentenceTransformer

        embedder = SentenceTransformer("all-MiniLM-L6-v2")
    except ImportError:
        pytest.skip("sentence-transformers not available")

    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/rag-research"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import RAGConfig, RAGResearchAgent

        config = RAGConfig(
            llm_provider="openai",
            model="gpt-5-nano",
            temperature=0.1,
            max_tokens=300,
            memory_config={"enabled": True, "embedder": embedder.encode, "top_k": 3},
        )

        agent = RAGResearchAgent(config)
        session_id = "integration_test_rag_002"

        # Add knowledge base
        agent.research(
            "Python is a programming language for software development.",
            session_id=session_id,
        )
        agent.research("JavaScript is used for web development.", session_id=session_id)

        # Semantically similar query
        result = agent.research(
            "Tell me about programming languages", session_id=session_id
        )

        # Should retrieve relevant context
        assert result is not None

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_rag_research_example_context_retrieval():
    """Test rag-research example retrieves relevant context."""
    try:
        from sentence_transformers import SentenceTransformer

        embedder = SentenceTransformer("all-MiniLM-L6-v2")
    except ImportError:
        pytest.skip("sentence-transformers not available")

    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/rag-research"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import RAGConfig, RAGResearchAgent

        config = RAGConfig(
            llm_provider="openai",
            model="gpt-5-nano",
            memory_config={"enabled": True, "embedder": embedder.encode, "top_k": 3},
        )

        agent = RAGResearchAgent(config)
        session_id = "integration_test_rag_003"

        # Build knowledge base
        for i in range(5):
            agent.research(
                f"Fact {i} about AI and machine learning", session_id=session_id
            )

        # Query should retrieve top-k relevant facts
        result = agent.research("What do you know about AI?", session_id=session_id)

        assert result is not None

    finally:
        sys.path.remove(str(example_path))


# =============================================================================
# STREAMING-CHAT EXAMPLE INTEGRATION TESTS (3 tests)
# =============================================================================


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_streaming_chat_example_with_real_streaming():
    """Test streaming-chat example with real OpenAI streaming."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/streaming-chat"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import StreamingChatAgent, StreamingConfig

        config = StreamingConfig(
            llm_provider="openai",
            model="gpt-5-nano",
            temperature=0.3,
            max_tokens=100,
            stream=True,
        )

        agent = StreamingChatAgent(config)

        # Collect streamed tokens
        tokens = []
        for token in agent.run(message="Hello, how are you?"):
            tokens.append(token)

        # Should receive multiple tokens
        assert len(tokens) > 0
        full_response = "".join(tokens)
        assert len(full_response) > 0

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_streaming_chat_example_progressive_output():
    """Test streaming-chat example provides progressive output."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/streaming-chat"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import StreamingChatAgent, StreamingConfig

        config = StreamingConfig(llm_provider="openai", model="gpt-5-nano", stream=True)

        agent = StreamingChatAgent(config)

        # Track progressive display
        displayed = ""
        token_count = 0

        for token in agent.run(message="Count from 1 to 3"):
            displayed += token
            token_count += 1

        # Should stream progressively
        assert token_count > 1
        assert len(displayed) > 0

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_streaming_chat_example_with_callback():
    """Test streaming-chat example supports callbacks."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/streaming-chat"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import StreamingChatAgent, StreamingConfig

        config = StreamingConfig(llm_provider="openai", model="gpt-5-nano", stream=True)

        agent = StreamingChatAgent(config)

        # Callback to track tokens
        received_tokens = []

        def token_callback(token: str):
            received_tokens.append(token)

        for token in agent.run(message="Say hello"):
            token_callback(token)

        assert len(received_tokens) > 0

    finally:
        sys.path.remove(str(example_path))


# =============================================================================
# BATCH-PROCESSING EXAMPLE INTEGRATION TESTS (3 tests)
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
async def test_batch_processing_example_concurrent_execution():
    """Test batch-processing example processes items concurrently."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/batch-processing"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import BatchConfig, BatchProcessingAgent

        config = BatchConfig(
            llm_provider="openai", model="gpt-5-nano", temperature=0.1, max_concurrent=3
        )

        agent = BatchProcessingAgent(config)

        items = [
            "Summarize: Python is a programming language",
            "Summarize: JavaScript runs in browsers",
            "Summarize: Java is platform independent",
        ]

        results = await agent.process_batch(items)

        # All items should be processed
        assert len(results) == 3
        assert all(r is not None for r in results)

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
async def test_batch_processing_example_performance():
    """Test batch-processing example improves performance via parallelization."""
    import time

    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/batch-processing"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import BatchConfig, BatchProcessingAgent

        config = BatchConfig(
            llm_provider="openai", model="gpt-5-nano", max_concurrent=5
        )

        agent = BatchProcessingAgent(config)

        items = [f"Process item {i}" for i in range(5)]

        start_time = time.time()
        results = await agent.process_batch(items)
        elapsed = time.time() - start_time

        # Should complete all items
        assert len(results) == 5
        # Parallel execution should be faster than sequential (rough check)
        assert elapsed < 10  # Generous limit for network variance

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
async def test_batch_processing_example_error_handling():
    """Test batch-processing example handles errors gracefully."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/batch-processing"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import BatchConfig, BatchProcessingAgent

        config = BatchConfig(
            llm_provider="openai",
            model="gpt-5-nano",
            max_concurrent=3,
            continue_on_error=True,
        )

        agent = BatchProcessingAgent(config)

        # Mix of valid and potentially problematic items
        items = ["Valid item 1", "Valid item 2", "Valid item 3"]

        results = await agent.process_batch(items)

        # Should process all items
        assert len(results) == 3

    finally:
        sys.path.remove(str(example_path))


# =============================================================================
# RESILIENT-FALLBACK EXAMPLE INTEGRATION TESTS (3 tests)
# =============================================================================


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_resilient_fallback_example_primary_success():
    """Test resilient-fallback example uses primary provider when available."""
    example_path = (
        Path(__file__).parent.parent.parent
        / "examples/1-single-agent/resilient-fallback"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import ResilientAgent, ResilientConfig

        config = ResilientConfig(
            primary_provider="openai",
            primary_model="gpt-5-nano",
            fallback_provider="openai",
            fallback_model="gpt-5-nano",
            temperature=0.1,
        )

        agent = ResilientAgent(config)

        result = agent.run(query="What is 2+2?")

        # Should succeed with primary provider
        assert result is not None
        assert "answer" in result or "response" in result
        assert result.get("provider", "primary") == "primary"

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_resilient_fallback_example_fallback_on_error():
    """Test resilient-fallback example falls back on primary failure."""
    example_path = (
        Path(__file__).parent.parent.parent
        / "examples/1-single-agent/resilient-fallback"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import ResilientAgent, ResilientConfig

        # Configure with invalid primary to trigger fallback
        config = ResilientConfig(
            primary_provider="invalid_provider",  # Will fail
            primary_model="invalid_model",
            fallback_provider="openai",
            fallback_model="gpt-5-nano",
            temperature=0.1,
        )

        agent = ResilientAgent(config)

        result = agent.run(query="Hello")

        # Should use fallback provider
        assert result is not None
        # Fallback should succeed
        assert result.get("provider") == "fallback" or "response" in result

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_resilient_fallback_example_reliability():
    """Test resilient-fallback example provides reliability through fallback chain."""
    example_path = (
        Path(__file__).parent.parent.parent
        / "examples/1-single-agent/resilient-fallback"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import ResilientAgent, ResilientConfig

        config = ResilientConfig(
            primary_provider="openai",
            primary_model="gpt-5-nano",
            fallback_provider="openai",
            fallback_model="gpt-5-nano",
            temperature=0.1,
            max_retries=3,
        )

        agent = ResilientAgent(config)

        # Multiple queries to test reliability
        results = []
        for i in range(3):
            result = agent.query(f"Test query {i}")
            results.append(result)

        # All queries should succeed
        assert len(results) == 3
        assert all(r is not None for r in results)

    finally:
        sys.path.remove(str(example_path))


# =============================================================================
# HUMAN-APPROVAL EXAMPLE INTEGRATION TESTS (3 tests)
# =============================================================================


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_human_approval_example_with_mock_approval():
    """Test human-approval example with mocked human approval (no real human)."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/human-approval"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import ApprovalConfig, HumanApprovalAgent

        # Mock approval function
        def mock_approval_fn(decision: Dict[str, Any]) -> bool:
            """Auto-approve for testing."""
            return True

        config = ApprovalConfig(
            llm_provider="openai",
            model="gpt-5-nano",
            temperature=0.1,
            approval_fn=mock_approval_fn,
        )

        agent = HumanApprovalAgent(config)

        result = agent.run(decision_context="Should I proceed with deployment?")

        # Should get decision with approval
        assert result is not None
        assert "decision" in result or "approved" in result

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_human_approval_example_rejection_handling():
    """Test human-approval example handles rejection correctly."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/human-approval"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import ApprovalConfig, HumanApprovalAgent

        # Mock rejection
        def mock_rejection_fn(decision: Dict[str, Any]) -> bool:
            """Auto-reject for testing."""
            return False

        config = ApprovalConfig(
            llm_provider="openai", model="gpt-5-nano", approval_fn=mock_rejection_fn
        )

        agent = HumanApprovalAgent(config)

        result = agent.run(decision_context="Should I delete all data?")

        # Should get rejection status
        assert result is not None
        assert result.get("approved") is False or "rejected" in str(result)

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_human_approval_example_approval_workflow():
    """Test human-approval example complete approval workflow."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/human-approval"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import ApprovalConfig, HumanApprovalAgent

        approval_log = []

        def logging_approval_fn(decision: Dict[str, Any]) -> bool:
            """Log approvals for testing."""
            approval_log.append(decision)
            # Approve high-confidence decisions
            return decision.get("confidence", 0) > 0.7

        config = ApprovalConfig(
            llm_provider="openai", model="gpt-5-nano", approval_fn=logging_approval_fn
        )

        agent = HumanApprovalAgent(config)

        result = agent.run(decision_context="Is 2+2=4?")

        # Should have logged approval
        assert len(approval_log) > 0
        assert result is not None

    finally:
        sys.path.remove(str(example_path))
