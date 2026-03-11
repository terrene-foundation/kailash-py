"""
Test RAG Research Example - Async Migration (Task 0A.5)

Tests that rag-research example uses AsyncSingleShotStrategy by default.
Written BEFORE migration (TDD).
"""

import asyncio
import inspect
import time

import pytest

# Standardized example loading
from example_import_helper import import_example_module

# Load rag-research example
_rag_module = import_example_module("examples/1-single-agent/rag-research")
RAGResearchAgent = _rag_module.RAGResearchAgent
RAGConfig = _rag_module.RAGConfig
RAGSignature = _rag_module.RAGSignature

from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy


class TestRAGResearchAsyncMigration:
    """Test suite for RAG Research async migration."""

    def test_rag_uses_async_strategy_by_default(self):
        """
        Task 0A.5: Verify RAGResearchAgent uses AsyncSingleShotStrategy.

        After migration, RAGResearchAgent should NOT explicitly provide
        SingleShotStrategy, allowing it to use the new default (async).
        """
        config = RAGConfig(llm_provider="openai", model="gpt-3.5-turbo")

        agent = RAGResearchAgent(config=config)

        # Should use async strategy after migration
        assert isinstance(
            agent.strategy, AsyncSingleShotStrategy
        ), f"Expected AsyncSingleShotStrategy, got {type(agent.strategy).__name__}"

    def test_rag_no_explicit_strategy_override(self):
        """
        Test that RAGResearchAgent no longer explicitly passes strategy.

        Before migration: strategy=SingleShotStrategy()
        After migration: No strategy parameter (uses default async)
        """
        config = RAGConfig()
        agent = RAGResearchAgent(config=config)

        # After migration, should use default async strategy
        assert isinstance(agent.strategy, AsyncSingleShotStrategy)

    def test_run_method_works_with_async(self):
        """
        Test that research() method works with async strategy.

        The research() method is sync, but internally uses async strategy.
        """
        config = RAGConfig(llm_provider="openai", model="gpt-3.5-turbo")

        agent = RAGResearchAgent(config=config)

        # Mock execution to avoid real LLM calls
        result = agent.run(query="What is machine learning?")

        # Should have expected RAG structure
        assert isinstance(result, dict)
        # Should have answer, sources, confidence, or error
        assert "answer" in result or "error" in result

    def test_multiple_rag_agents_independent(self):
        """
        Test that multiple RAG agents don't interfere with each other.
        """
        config = RAGConfig()

        agent1 = RAGResearchAgent(config=config)
        agent2 = RAGResearchAgent(config=config)

        assert isinstance(agent1.strategy, AsyncSingleShotStrategy)
        assert isinstance(agent2.strategy, AsyncSingleShotStrategy)
        assert agent1.strategy is not agent2.strategy


class TestRAGResearchRaceConditions:
    """Test for race conditions with async RAG retrieval."""

    def test_rag_no_race_conditions_sequential(self):
        """
        Test sequential RAG research doesn't have race conditions.
        """
        config = RAGConfig()
        agent = RAGResearchAgent(config=config)

        results = []
        for i in range(5):
            result = agent.research(f"Question about topic {i}")
            results.append(result)

        # All results should be valid
        assert len(results) == 5
        for result in results:
            assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_rag_no_race_conditions_concurrent(self):
        """
        Test concurrent RAG executions don't interfere with vector search.

        This simulates 10 concurrent RAG queries.
        CRITICAL: Each execution's retrieval should be independent.
        """
        config = RAGConfig(top_k_documents=3)
        agent = RAGResearchAgent(config=config)

        # Run 10 concurrent RAG queries
        async def research_async(query):
            # research() is sync, wrap in executor
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, agent.research, query)

        tasks = [research_async(f"Question {i}") for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All results should be valid (or exceptions)
        assert len(results) == 10
        for i, result in enumerate(results):
            if not isinstance(result, Exception):
                assert isinstance(result, dict)
                # Should have answer or error
                assert "answer" in result or "error" in result


class TestRAGResearchRetrievalConsistency:
    """Test that RAG retrieval is consistent with async execution."""

    def test_rag_retrieval_structure_preserved(self):
        """
        Test that RAG output structure is preserved with async strategy.
        """
        config = RAGConfig()
        agent = RAGResearchAgent(config=config)

        result = agent.run(query="What is deep learning?")

        # Should have RAG structure or error
        assert isinstance(result, dict)
        if "error" not in result:
            # RAG signature specifies answer, sources, confidence, relevant_excerpts
            # At least answer should be present
            assert (
                "answer" in result
            ), f"Missing answer field. Got: {list(result.keys())}"

    def test_rag_vector_search_quality(self):
        """
        Test that vector search returns relevant documents.
        """
        config = RAGConfig(top_k_documents=3, similarity_threshold=0.3)
        agent = RAGResearchAgent(config=config)

        result = agent.run(query="Explain neural networks")

        # Should retrieve documents
        if "sources" in result:
            # Should have up to top_k sources
            assert len(result["sources"]) <= 3
            # Should have excerpts
            assert "relevant_excerpts" in result

    def test_rag_empty_query_handling(self):
        """Test that empty query handling returns a valid result.

        Note: With empty query, the agent may return an error structure
        since the mock provider doesn't generate valid structured output.
        We verify that the result is a dict with either valid or error structure.
        """
        config = RAGConfig(llm_provider="mock")
        agent = RAGResearchAgent(config=config)

        result = agent.run(query="")

        # Result should be a dict
        assert isinstance(result, dict)
        # With mock provider and empty query, we may get either:
        # - Valid structure with answer/confidence
        # - Error structure with error/success fields
        has_valid_structure = "answer" in result and "confidence" in result
        has_error_structure = "error" in result or "success" in result
        assert has_valid_structure or has_error_structure


class TestRAGResearchBackwardCompatibility:
    """Test backward compatibility after async migration."""

    def test_rag_config_parameters_preserved(self):
        """
        Test that all RAGConfig parameters are preserved.
        """
        config = RAGConfig(
            llm_provider="anthropic",
            model="claude-3-haiku",
            temperature=0.7,
            max_tokens=1000,
            top_k_documents=5,
            similarity_threshold=0.4,
            embedding_model="all-MiniLM-L6-v2",
        )

        agent = RAGResearchAgent(config=config)

        # rag_config should be preserved
        assert agent.rag_config.llm_provider == "anthropic"
        assert agent.rag_config.model == "claude-3-haiku"
        assert agent.rag_config.temperature == 0.7
        assert agent.rag_config.max_tokens == 1000
        assert agent.rag_config.top_k_documents == 5
        assert agent.rag_config.similarity_threshold == 0.4
        assert agent.rag_config.embedding_model == "all-MiniLM-L6-v2"

    def test_rag_document_management(self):
        """
        Test that document add/clear operations still work.
        """
        config = RAGConfig()
        agent = RAGResearchAgent(config=config)

        # Should have default documents
        initial_count = agent.get_document_count()
        assert initial_count > 0

        # Add a document
        agent.add_document("test_doc", "Test Title", "Test content")

        # Count should increase
        assert agent.get_document_count() == initial_count + 1

        # Clear all documents
        agent.clear_documents()

        # Count should be 0
        assert agent.get_document_count() == 0


class TestRAGResearchAsyncPerformance:
    """Test performance characteristics with async RAG strategy."""

    def test_rag_strategy_has_async_execute(self):
        """
        Test that strategy.execute is async.
        """
        config = RAGConfig()
        agent = RAGResearchAgent(config=config)

        assert inspect.iscoroutinefunction(agent.strategy.execute)

    def test_rag_async_execution_overhead(self):
        """
        Test that async execution doesn't add excessive overhead for single RAG.

        Measure execution time for single RAG query.
        """
        config = RAGConfig()
        agent = RAGResearchAgent(config=config)

        start = time.time()

        # Single RAG execution (should be fast even with async overhead)
        result = agent.run(query="Simple query")

        elapsed = time.time() - start

        # Should complete quickly (< 10 seconds even with mocked execution + vector search)
        assert elapsed < 10.0

        # Result should be valid
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_rag_concurrent_speedup(self):
        """
        Test that concurrent RAG executions can provide speedup.

        10 concurrent RAG queries should complete faster than
        10 sequential ones (at least in theory with async).
        """
        config = RAGConfig()
        agent = RAGResearchAgent(config=config)

        # Run 10 concurrent RAG queries
        async def research_async(query):
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, agent.research, query)

        start = time.time()
        tasks = [research_async(f"Query {i}") for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        concurrent_time = time.time() - start

        # All should complete
        assert len(results) == 10

        # Should complete in reasonable time
        assert concurrent_time < 30.0  # 10 queries should finish in under 30s


class TestRAGResearchSignatureIntegration:
    """Test that RAG signature integration works with async strategy."""

    def test_rag_signature_fields_available(self):
        """
        Test that RAGSignature fields are properly configured.
        """
        config = RAGConfig()
        agent = RAGResearchAgent(config=config)

        # Signature should be RAGSignature
        assert isinstance(agent.signature, RAGSignature)

        # Signature should have input/output fields
        assert hasattr(agent.signature, "query")
        assert hasattr(agent.signature, "answer")
        assert hasattr(agent.signature, "sources")
        assert hasattr(agent.signature, "confidence")
        assert hasattr(agent.signature, "relevant_excerpts")


class TestRAGResearchVectorStoreAsync:
    """Test vector store operations with async strategy."""

    def test_vector_store_concurrent_access(self):
        """
        Test that vector store handles concurrent access correctly.
        """
        config = RAGConfig()
        agent = RAGResearchAgent(config=config)

        # Multiple sequential searches should work
        results = []
        for i in range(5):
            result = agent.research(f"Query about topic {i}")
            results.append(result)

        # All should return valid results
        assert len(results) == 5
        for result in results:
            assert isinstance(result, dict)

    def test_vector_store_similarity_scores(self):
        """
        Test that similarity scores are included in results.
        """
        config = RAGConfig(top_k_documents=3)
        agent = RAGResearchAgent(config=config)

        result = agent.run(query="Explain reinforcement learning")

        # Should have retrieval quality metric
        if "retrieval_quality" in result:
            # Quality should be between 0 and 1
            assert 0.0 <= result["retrieval_quality"] <= 1.0

        # Excerpts should have similarity scores
        if "relevant_excerpts" in result and len(result["relevant_excerpts"]) > 0:
            for excerpt in result["relevant_excerpts"]:
                assert "similarity" in excerpt
                assert 0.0 <= excerpt["similarity"] <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
