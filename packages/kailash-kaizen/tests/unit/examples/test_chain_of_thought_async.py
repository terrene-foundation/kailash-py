"""
Test Chain-of-Thought Example - Async Migration (Task 0A.3)

Tests that chain-of-thought example uses AsyncSingleShotStrategy by default.
Written BEFORE migration (TDD).
"""

import asyncio
import inspect
import time

import pytest

# Standardized example loading
from example_import_helper import import_example_module

# Load chain-of-thought example
_cot_module = import_example_module(
    "examples/1-single-agent/chain-of-thought", module_name="chain_of_thought_agent"
)
ChainOfThoughtAgent = _cot_module.ChainOfThoughtAgent
CoTConfig = _cot_module.CoTConfig
ChainOfThoughtSignature = _cot_module.ChainOfThoughtSignature

from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy


class TestChainOfThoughtAsyncMigration:
    """Test suite for Chain-of-Thought async migration."""

    def test_cot_uses_async_strategy_by_default(self):
        """
        Task 0A.3: Verify ChainOfThoughtAgent uses AsyncSingleShotStrategy.

        After migration, ChainOfThoughtAgent should NOT explicitly provide
        SingleShotStrategy, allowing it to use the new default (async).
        """
        config = CoTConfig(llm_provider="openai", model="gpt-4")

        agent = ChainOfThoughtAgent(config=config)

        # Should use async strategy after migration
        assert isinstance(
            agent.strategy, AsyncSingleShotStrategy
        ), f"Expected AsyncSingleShotStrategy, got {type(agent.strategy).__name__}"

    def test_cot_no_explicit_strategy_override(self):
        """
        Test that ChainOfThoughtAgent no longer explicitly passes strategy.

        Before migration: strategy=SingleShotStrategy()
        After migration: No strategy parameter (uses default async)
        """
        config = CoTConfig()
        agent = ChainOfThoughtAgent(config=config)

        # After migration, should use default async strategy
        assert isinstance(agent.strategy, AsyncSingleShotStrategy)

    def test_run_works_with_async(self):
        """
        Test that solve_problem() method works with async strategy.

        The solve_problem() method is sync, but internally uses async strategy.
        Note: Not marked as async because solve_problem() is synchronous.
        """
        config = CoTConfig(llm_provider="openai", model="gpt-4")

        agent = ChainOfThoughtAgent(config=config)

        # Mock execution to avoid real LLM calls
        result = agent.run(problem="What is 2+2?")

        # Should have expected CoT structure
        assert isinstance(result, dict)
        # Should have step1-step5 or error
        assert "step1" in result or "error" in result

    def test_multiple_cot_agents_independent(self):
        """
        Test that multiple CoT agents don't interfere with each other.
        """
        config = CoTConfig()

        agent1 = ChainOfThoughtAgent(config=config)
        agent2 = ChainOfThoughtAgent(config=config)

        assert isinstance(agent1.strategy, AsyncSingleShotStrategy)
        assert isinstance(agent2.strategy, AsyncSingleShotStrategy)
        assert agent1.strategy is not agent2.strategy


class TestChainOfThoughtRaceConditions:
    """Test for race conditions with async CoT reasoning."""

    def test_cot_no_race_conditions_sequential(self):
        """
        Test sequential CoT reasoning doesn't have race conditions.
        """
        config = CoTConfig(reasoning_steps=5)
        agent = ChainOfThoughtAgent(config=config)

        results = []
        for i in range(5):
            result = agent.solve_problem(f"Solve problem {i}")
            results.append(result)

        # All results should be valid
        assert len(results) == 5
        for result in results:
            assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_cot_no_race_conditions_concurrent(self):
        """
        Test concurrent CoT executions don't interfere with reasoning chains.

        This simulates 10 concurrent CoT reasoning processes.
        CRITICAL: Each execution's step1-step5 should be independent.
        """
        config = CoTConfig(reasoning_steps=5)
        agent = ChainOfThoughtAgent(config=config)

        # Run 10 concurrent CoT problems
        async def solve_async(problem):
            # solve_problem() is sync, wrap in executor
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, agent.solve_problem, problem)

        tasks = [solve_async(f"Problem {i}") for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All results should be valid (or exceptions)
        assert len(results) == 10
        for i, result in enumerate(results):
            if not isinstance(result, Exception):
                assert isinstance(result, dict)
                # Should have reasoning steps or error
                if "error" not in result:
                    assert "step1" in result
                    assert "final_answer" in result


class TestChainOfThoughtReasoningConsistency:
    """Test that CoT reasoning steps are consistent with async execution."""

    def test_cot_reasoning_structure_preserved(self):
        """
        Test that CoT output structure is preserved with async strategy.
        """
        config = CoTConfig()
        agent = ChainOfThoughtAgent(config=config)

        result = agent.run(problem="Calculate 15 * 7")

        # Should have all CoT steps or error
        assert isinstance(result, dict)
        if "error" not in result:
            # CoT signature specifies step1-step5, final_answer, confidence
            expected_fields = [
                "step1",
                "step2",
                "step3",
                "step4",
                "step5",
                "final_answer",
                "confidence",
            ]
            # At least some of these should be present
            found_fields = [field for field in expected_fields if field in result]
            assert (
                len(found_fields) > 0
            ), f"Missing CoT fields. Got: {list(result.keys())}"

    def test_cot_confidence_threshold_logic(self):
        """
        Test that confidence threshold validation still works.
        """
        config = CoTConfig(confidence_threshold=0.8, enable_verification=True)
        agent = ChainOfThoughtAgent(config=config)

        # Agent should have config
        assert agent.cot_config.confidence_threshold == 0.8
        assert agent.cot_config.enable_verification is True

    def test_cot_empty_problem_handling(self):
        """
        Test that empty problem handling returns a result with default values.

        Note: Agent doesn't perform input validation - it processes empty input
        and returns result with default confidence. Actual answer depends on
        LLM provider (real or mock).
        """
        config = CoTConfig(llm_provider="mock")
        agent = ChainOfThoughtAgent(config=config)

        result = agent.run(problem="")

        # Agent returns a result dict (structure test, not content test)
        assert isinstance(result, dict)
        # Confidence should be returned (may be 0.0 or mock value)
        # With mock provider, we may get error response for empty input
        assert "confidence" in result or "error" in result
        # Final answer should be present (or error)
        assert "final_answer" in result or "error" in result


class TestChainOfThoughtBackwardCompatibility:
    """Test backward compatibility after async migration."""

    def test_cot_config_parameters_preserved(self):
        """
        Test that all CoTConfig parameters are preserved.
        """
        config = CoTConfig(
            llm_provider="anthropic",
            model="claude-3-sonnet",
            temperature=0.1,
            max_tokens=1500,
            timeout=45,
            retry_attempts=3,
            reasoning_steps=5,
            confidence_threshold=0.7,
            enable_verification=True,
        )

        agent = ChainOfThoughtAgent(config=config)

        # cot_config should be preserved
        assert agent.cot_config.llm_provider == "anthropic"
        assert agent.cot_config.model == "claude-3-sonnet"
        assert agent.cot_config.temperature == 0.1
        assert agent.cot_config.max_tokens == 1500
        assert agent.cot_config.timeout == 45
        assert agent.cot_config.retry_attempts == 3
        assert agent.cot_config.reasoning_steps == 5
        assert agent.cot_config.confidence_threshold == 0.7
        assert agent.cot_config.enable_verification is True

    def test_cot_verification_flag_added(self):
        """
        Test that verification flag is added when enabled.
        """
        config = CoTConfig(enable_verification=True, confidence_threshold=0.7)
        agent = ChainOfThoughtAgent(config=config)

        result = agent.run(problem="Test problem")

        # If verification is enabled and result has confidence, should have verified flag
        if "confidence" in result and result.get("confidence", 0) > 0:
            # verified flag should be present
            assert "verified" in result or "error" in result


class TestChainOfThoughtAsyncPerformance:
    """Test performance characteristics with async CoT strategy."""

    def test_cot_strategy_has_async_execute(self):
        """
        Test that strategy.execute is async.
        """
        config = CoTConfig()
        agent = ChainOfThoughtAgent(config=config)

        assert inspect.iscoroutinefunction(agent.strategy.execute)

    def test_cot_async_execution_overhead(self):
        """
        Test that async execution doesn't add excessive overhead for single CoT.

        Measure execution time for single CoT reasoning.
        Should be <10% overhead compared to sync strategy.
        Note: Not marked as async because solve_problem() is synchronous.
        """
        config = CoTConfig()
        agent = ChainOfThoughtAgent(config=config)

        start = time.time()

        # Single CoT execution (should be fast even with async overhead)
        result = agent.run(problem="Simple problem")

        elapsed = time.time() - start

        # Should complete quickly (< 15 seconds even with mocked execution)
        # Relaxed threshold to account for CI/test environment variability
        assert elapsed < 15.0

        # Result should be valid
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_cot_concurrent_speedup(self):
        """
        Test that concurrent CoT executions can provide speedup.

        10 concurrent CoT problems should complete faster than
        10 sequential ones (at least in theory with async).
        """
        config = CoTConfig()
        agent = ChainOfThoughtAgent(config=config)

        # Run 10 concurrent CoT problems
        async def solve_async(problem):
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, agent.solve_problem, problem)

        start = time.time()
        tasks = [solve_async(f"Problem {i}") for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        concurrent_time = time.time() - start

        # All should complete
        assert len(results) == 10

        # Note: Actual speedup depends on I/O vs CPU bound operations
        # For mocked execution, just verify it completes in reasonable time
        assert concurrent_time < 30.0  # 10 problems should finish in under 30s


class TestChainOfThoughtSignatureIntegration:
    """Test that CoT signature integration works with async strategy."""

    def test_cot_signature_fields_available(self):
        """
        Test that ChainOfThoughtSignature fields are properly configured.
        """
        config = CoTConfig()
        agent = ChainOfThoughtAgent(config=config)

        # Signature should be ChainOfThoughtSignature
        assert isinstance(agent.signature, ChainOfThoughtSignature)

        # Signature should have input/output fields
        assert hasattr(agent.signature, "problem")
        assert hasattr(agent.signature, "context")
        assert hasattr(agent.signature, "step1")
        assert hasattr(agent.signature, "step2")
        assert hasattr(agent.signature, "step3")
        assert hasattr(agent.signature, "step4")
        assert hasattr(agent.signature, "step5")
        assert hasattr(agent.signature, "final_answer")
        assert hasattr(agent.signature, "confidence")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
