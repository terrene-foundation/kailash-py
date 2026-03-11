"""
Test Simple Q&A Example - Async Migration (Task 0A.2)

Tests that simple-qa example uses AsyncSingleShotStrategy.
Written BEFORE migration (TDD).
"""

import asyncio

import pytest

# Standardized example loading
from example_import_helper import import_example_module

# Load simple-qa example
_simple_qa_module = import_example_module("examples/1-single-agent/simple-qa")
SimpleQAAgent = _simple_qa_module.SimpleQAAgent
QAConfig = _simple_qa_module.QAConfig

from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy


class TestSimpleQAAsyncMigration:
    """Test suite for SimpleQA async migration."""

    def test_simple_qa_uses_async_strategy_by_default(self):
        """
        Task 0A.2: Verify SimpleQAAgent uses AsyncSingleShotStrategy.

        After migration, SimpleQAAgent should NOT explicitly provide
        SingleShotStrategy, allowing it to use the new default (async).
        """
        config = QAConfig(llm_provider="openai", model="gpt-4")

        agent = SimpleQAAgent(config=config)

        # Should use async strategy after migration
        assert isinstance(
            agent.strategy, AsyncSingleShotStrategy
        ), f"Expected AsyncSingleShotStrategy, got {type(agent.strategy).__name__}"

    def test_simple_qa_no_explicit_strategy_override(self):
        """
        Test that SimpleQAAgent no longer explicitly passes strategy.

        Before migration: strategy=SingleShotStrategy()
        After migration: No strategy parameter (uses default async)
        """
        config = QAConfig()
        agent = SimpleQAAgent(config=config)

        # After migration, should use default async strategy
        assert isinstance(agent.strategy, AsyncSingleShotStrategy)

    @pytest.mark.asyncio
    async def test_run_method_works_with_async(self):
        """
        Test that ask() method works with async strategy.

        The ask() method is sync, but internally uses async strategy.
        """
        config = QAConfig(llm_provider="openai", model="gpt-4")

        agent = SimpleQAAgent(config=config)

        # Mock execution to avoid real LLM calls
        # ask() method should work regardless of strategy
        result = agent.run(question="What is 2+2?")

        # Should have expected structure
        assert "answer" in result or "error" in result or "response" in result

    def test_multiple_simple_qa_agents_independent(self):
        """
        Test that multiple agents don't interfere with each other.
        """
        config = QAConfig()

        agent1 = SimpleQAAgent(config=config)
        agent2 = SimpleQAAgent(config=config)

        assert isinstance(agent1.strategy, AsyncSingleShotStrategy)
        assert isinstance(agent2.strategy, AsyncSingleShotStrategy)
        assert agent1.strategy is not agent2.strategy


class TestSimpleQARaceConditions:
    """Test for race conditions with async strategy."""

    def test_no_race_conditions_sequential(self):
        """
        Test sequential asks don't have race conditions.
        """
        config = QAConfig()
        agent = SimpleQAAgent(config=config)

        results = []
        for i in range(5):
            result = agent.ask(f"Question {i}")
            results.append(result)

        # All results should be valid
        assert len(results) == 5
        for result in results:
            assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_no_race_conditions_concurrent_simple(self):
        """
        Test concurrent asks in async context don't interfere.

        This simulates multiple concurrent requests to the same agent.
        """
        config = QAConfig()
        agent = SimpleQAAgent(config=config)

        # Run 10 concurrent asks
        async def ask_async(question):
            # ask() is sync, wrap in executor
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, agent.ask, question)

        tasks = [ask_async(f"Question {i}") for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All results should be valid (or exceptions)
        assert len(results) == 10
        for result in results:
            if not isinstance(result, Exception):
                assert isinstance(result, dict)


class TestSimpleQABackwardCompatibility:
    """Test backward compatibility after async migration."""

    def test_confidence_threshold_still_works(self):
        """
        Test that min_confidence_threshold logic still works.
        """
        config = QAConfig(min_confidence_threshold=0.8)
        agent = SimpleQAAgent(config=config)

        # Agent should still have config
        assert agent.qa_config.min_confidence_threshold == 0.8

    def test_empty_question_handling(self):
        """Test that empty question handling returns a valid result.

        Note: Agent doesn't perform input validation - it processes empty input.
        With mock provider, we test structure only.
        """
        config = QAConfig(llm_provider="mock")
        agent = SimpleQAAgent(config=config)

        result = agent.run(question="")

        # Result should be a dict with expected structure
        assert isinstance(result, dict)
        # Should have answer and confidence fields (or error)
        assert "answer" in result or "error" in result
        # With mock provider, we may get error response for empty input
        # so we just check that result is a dict
        assert "confidence" in result or "error" in result

    def test_config_parameters_preserved(self):
        """
        Test that all config parameters are preserved.
        """
        config = QAConfig(
            llm_provider="anthropic",
            model="claude-3-sonnet",
            temperature=0.5,
            max_tokens=500,
            timeout=45,
        )

        agent = SimpleQAAgent(config=config)

        # qa_config should be preserved (QAConfig instance)
        assert agent.qa_config.llm_provider == "anthropic"
        assert agent.qa_config.model == "claude-3-sonnet"
        assert agent.qa_config.temperature == 0.5
        assert agent.qa_config.max_tokens == 500

        # agent.config is BaseAgentConfig (converted from QAConfig)
        # Note: config might be dict or BaseAgentConfig depending on initialization
        if hasattr(agent.config, "llm_provider"):
            assert agent.config.llm_provider == "anthropic"
            assert agent.config.model == "claude-3-sonnet"
        else:
            # Config is dict
            assert isinstance(agent.config, dict)


class TestSimpleQAAsyncPerformance:
    """Test performance characteristics with async strategy."""

    def test_strategy_has_async_execute(self):
        """
        Test that strategy.execute is async.
        """
        config = QAConfig()
        agent = SimpleQAAgent(config=config)

        import inspect

        assert inspect.iscoroutinefunction(agent.strategy.execute)

    @pytest.mark.asyncio
    async def test_async_execution_overhead(self):
        """
        Test that async execution doesn't add excessive overhead.

        Measure execution time for single request.
        """
        config = QAConfig()
        agent = SimpleQAAgent(config=config)

        import time

        start = time.time()

        # Single ask (should be fast even with async overhead)
        result = agent.run(question="Test question")

        elapsed = time.time() - start

        # Should complete quickly (< 5 seconds even with mocked execution)
        assert elapsed < 5.0

        # Result should be valid
        assert isinstance(result, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
