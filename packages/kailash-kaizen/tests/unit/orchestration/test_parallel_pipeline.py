"""
Unit tests for Parallel Pipeline pattern.

Tests concurrent execution with asyncio, result aggregation, and error handling.
Written BEFORE implementation (TDD approach).
"""

import time

import pytest
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.orchestration.pipeline import Pipeline
from kaizen.signatures import InputField, OutputField, Signature

# ============================================================================
# Test Fixtures
# ============================================================================


class SimpleSignature(Signature):
    """Simple signature for test agents."""

    input: str = InputField(description="Input data")
    output: str = OutputField(description="Output data")


class MockAgent(BaseAgent):
    """Mock agent for testing."""

    def __init__(self, agent_id: str, delay: float = 0.0):
        """Initialize mock agent with optional execution delay."""
        super().__init__(
            config=BaseAgentConfig(llm_provider="mock", model="test"),
            signature=SimpleSignature(),
            agent_id=agent_id,
        )
        self.delay = delay
        self._call_count = 0
        self._execution_times = []

    def run(self, **inputs):
        """Mock run method with optional delay."""
        import time

        start = time.time()
        self._call_count += 1

        # Simulate processing time
        if self.delay > 0:
            time.sleep(self.delay)

        duration = time.time() - start
        self._execution_times.append(duration)

        return {
            "output": f"{self.agent_id} processed: {inputs.get('input', '')}",
            "agent_id": self.agent_id,
            "execution_time": duration,
        }


class FailingAgent(BaseAgent):
    """Mock agent that fails on execution."""

    def __init__(self, agent_id: str):
        super().__init__(
            config=BaseAgentConfig(llm_provider="mock", model="test"),
            signature=SimpleSignature(),
            agent_id=agent_id,
        )

    def run(self, **inputs):
        raise Exception(f"{self.agent_id} intentional failure")


@pytest.fixture
def mock_agents():
    """Create mock agents for testing."""
    return [
        MockAgent("agent_1", delay=0.1),
        MockAgent("agent_2", delay=0.1),
        MockAgent("agent_3", delay=0.1),
        MockAgent("agent_4", delay=0.1),
    ]


# ============================================================================
# Test Basic Parallel Pipeline Creation
# ============================================================================


class TestParallelCreation:
    """Test Parallel Pipeline creation."""

    def test_parallel_factory_method_exists(self):
        """Test that Pipeline.parallel() factory method exists."""
        assert hasattr(
            Pipeline, "parallel"
        ), "Pipeline.parallel() factory method not found"
        assert callable(Pipeline.parallel), "Pipeline.parallel is not callable"

    def test_parallel_creates_parallel_pipeline(self, mock_agents):
        """Test that Pipeline.parallel() creates ParallelPipeline instance."""
        pipeline = Pipeline.parallel(agents=mock_agents[:2])

        assert pipeline is not None
        assert hasattr(pipeline, "run"), "ParallelPipeline must have run() method"
        assert isinstance(
            pipeline, Pipeline
        ), "ParallelPipeline must inherit from Pipeline"

    def test_parallel_requires_agents_parameter(self):
        """Test that parallel() requires agents parameter."""
        with pytest.raises(TypeError):
            Pipeline.parallel()  # Missing required 'agents' parameter

    def test_parallel_rejects_empty_agents_list(self):
        """Test that parallel() rejects empty agents list."""
        with pytest.raises(ValueError, match="agents cannot be empty"):
            Pipeline.parallel(agents=[])

    def test_parallel_accepts_optional_parameters(self, mock_agents):
        """Test that parallel() accepts optional parameters."""
        # Should not raise
        pipeline_with_aggregator = Pipeline.parallel(
            agents=mock_agents[:2], aggregator=lambda results: {"combined": results}
        )

        pipeline_with_max_workers = Pipeline.parallel(
            agents=mock_agents[:2], max_workers=5
        )

        assert pipeline_with_aggregator is not None
        assert pipeline_with_max_workers is not None


# ============================================================================
# Test Concurrent Execution
# ============================================================================


class TestParallelConcurrentExecution:
    """Test parallel concurrent execution."""

    def test_parallel_executes_all_agents(self, mock_agents):
        """Test that parallel pipeline executes all agents."""
        pipeline = Pipeline.parallel(agents=mock_agents)

        result = pipeline.run(input="test_data")

        # All agents should be executed
        assert all(
            agent._call_count == 1 for agent in mock_agents
        ), "All agents should be executed once"

        # Result should contain all outputs
        assert "results" in result
        assert len(result["results"]) == len(mock_agents)

    def test_parallel_executes_concurrently(self, mock_agents):
        """Test that agents execute concurrently, not sequentially."""
        # Each agent has 0.1s delay
        # Sequential: 4 * 0.1 = 0.4s
        # Parallel: ~0.1s (concurrent)

        pipeline = Pipeline.parallel(agents=mock_agents)

        start = time.time()
        result = pipeline.run(input="test_data")
        duration = time.time() - start

        # Should complete in ~0.1s (parallel), not 0.4s (sequential)
        assert (
            duration < 0.2
        ), f"Execution took {duration:.3f}s (should be <0.2s for parallel)"
        assert duration > 0.09, "Execution should take at least 0.1s (agent delay)"

        # Verify all agents executed
        assert len(result["results"]) == len(mock_agents)

    def test_parallel_preserves_agent_order_in_results(self, mock_agents):
        """Test that results maintain agent order."""
        pipeline = Pipeline.parallel(agents=mock_agents)

        result = pipeline.run(input="test_data")

        # Results should be in same order as agents
        for i, agent_result in enumerate(result["results"]):
            expected_agent_id = f"agent_{i+1}"
            assert agent_result["agent_id"] == expected_agent_id

    def test_parallel_passes_inputs_to_all_agents(self, mock_agents):
        """Test that all agents receive the same inputs."""
        pipeline = Pipeline.parallel(agents=mock_agents[:2])

        result = pipeline.run(input="shared_data", extra_param="value")

        # All results should show agents received inputs
        for agent_result in result["results"]:
            assert "shared_data" in agent_result["output"]


# ============================================================================
# Test Result Aggregation
# ============================================================================


class TestParallelResultAggregation:
    """Test parallel result aggregation."""

    def test_parallel_default_aggregation(self, mock_agents):
        """Test parallel pipeline default aggregation (list of results)."""
        pipeline = Pipeline.parallel(agents=mock_agents[:3])

        result = pipeline.run(input="test")

        # Default aggregation: list of all results
        assert "results" in result
        assert isinstance(result["results"], list)
        assert len(result["results"]) == 3

    def test_parallel_custom_aggregator(self, mock_agents):
        """Test parallel pipeline with custom aggregator function."""

        def custom_aggregator(results):
            """Combine all outputs into single string."""
            combined = " | ".join(r["output"] for r in results)
            return {"combined_output": combined, "count": len(results)}

        pipeline = Pipeline.parallel(
            agents=mock_agents[:2], aggregator=custom_aggregator
        )

        result = pipeline.run(input="test")

        # Custom aggregation applied
        assert "combined_output" in result
        assert "count" in result
        assert result["count"] == 2
        assert "|" in result["combined_output"]

    def test_parallel_aggregator_receives_all_results(self, mock_agents):
        """Test that aggregator receives results from all agents."""
        received_results = []

        def tracking_aggregator(results):
            received_results.extend(results)
            return {"total": len(results)}

        pipeline = Pipeline.parallel(agents=mock_agents, aggregator=tracking_aggregator)

        result = pipeline.run(input="test")

        # Aggregator should receive all 4 results
        assert len(received_results) == 4
        assert result["total"] == 4


# ============================================================================
# Test Error Handling
# ============================================================================


class TestParallelErrorHandling:
    """Test parallel pipeline error handling."""

    def test_parallel_handles_agent_failure_gracefully(self, mock_agents):
        """Test that parallel handles individual agent failures gracefully."""
        # Mix successful and failing agents
        agents = [mock_agents[0], FailingAgent("failing_agent"), mock_agents[1]]

        pipeline = Pipeline.parallel(agents=agents)
        pipeline.error_handling = "graceful"

        result = pipeline.run(input="test")

        # Should return results with error for failing agent
        assert "results" in result
        assert len(result["results"]) == 3

        # Check that failing agent result contains error
        failing_result = result["results"][1]
        assert "error" in failing_result
        assert "intentional failure" in str(failing_result["error"])

        # Check that other agents succeeded
        assert "error" not in result["results"][0]
        assert "error" not in result["results"][2]

    def test_parallel_partial_results_on_failures(self, mock_agents):
        """Test that parallel returns partial results when some agents fail."""
        agents = [
            FailingAgent("fail_1"),
            mock_agents[0],
            FailingAgent("fail_2"),
            mock_agents[1],
        ]

        pipeline = Pipeline.parallel(agents=agents)
        pipeline.error_handling = "graceful"

        result = pipeline.run(input="test")

        # Should have 4 results (2 errors + 2 successes)
        assert len(result["results"]) == 4

        # Count successful vs failed
        successful = [r for r in result["results"] if "error" not in r]
        failed = [r for r in result["results"] if "error" in r]

        assert len(successful) == 2
        assert len(failed) == 2

    def test_parallel_fail_fast_mode_raises_first_error(self, mock_agents):
        """Test that parallel fail-fast mode raises first error encountered."""
        agents = [mock_agents[0], FailingAgent("failing_agent"), mock_agents[1]]

        pipeline = Pipeline.parallel(agents=agents)
        pipeline.error_handling = "fail-fast"

        with pytest.raises(Exception, match="intentional failure"):
            pipeline.run(input="test")

    def test_parallel_continues_on_timeout(self, mock_agents):
        """Test that parallel continues when one agent times out."""

        class SlowAgent(BaseAgent):
            def __init__(self):
                super().__init__(
                    config=BaseAgentConfig(llm_provider="mock", model="test"),
                    signature=SimpleSignature(),
                    agent_id="slow_agent",
                )

            def run(self, **inputs):
                time.sleep(2.0)  # 2 second delay
                return {"output": "slow result"}

        agents = [mock_agents[0], SlowAgent(), mock_agents[1]]

        pipeline = Pipeline.parallel(agents=agents, max_workers=10)
        pipeline.timeout = 0.5  # 500ms timeout

        result = pipeline.run(input="test")

        # Should have results from fast agents, timeout error for slow agent
        assert len(result["results"]) == 3
        # Note: Actual timeout implementation may vary


# ============================================================================
# Test Composability (.to_agent())
# ============================================================================


class TestParallelComposability:
    """Test that parallel pipeline can be converted to agent."""

    def test_parallel_pipeline_to_agent(self, mock_agents):
        """Test that parallel pipeline can be converted to agent via .to_agent()."""
        pipeline = Pipeline.parallel(agents=mock_agents[:2])

        agent = pipeline.to_agent(
            name="parallel_agent", description="Parallel execution as agent"
        )

        # Verify it's a BaseAgent
        assert isinstance(agent, BaseAgent)
        assert agent.agent_id == "parallel_agent"
        assert agent.description == "Parallel execution as agent"

    def test_parallel_agent_executes_correctly(self, mock_agents):
        """Test that parallel converted to agent executes correctly."""
        pipeline = Pipeline.parallel(agents=mock_agents[:3])
        agent = pipeline.to_agent()

        result = agent.run(input="test")

        # Should execute all agents in parallel
        assert result is not None
        assert "results" in result
        assert len(result["results"]) == 3

    def test_parallel_agent_can_be_nested(self, mock_agents):
        """Test that parallel agent can be nested in another pipeline."""
        from kaizen.orchestration.pipeline import SequentialPipeline

        # Create parallel as agent
        parallel_pipeline = Pipeline.parallel(agents=mock_agents[:2])
        parallel_agent = parallel_pipeline.to_agent(name="parallel_step")

        # Use in sequential pipeline
        sequential = SequentialPipeline(agents=[parallel_agent, mock_agents[2]])

        result = sequential.run(input="test")

        # Should execute parallel step, then final agent
        assert result is not None
        assert "final_output" in result


# ============================================================================
# Test Performance and Scalability
# ============================================================================


class TestParallelPerformance:
    """Test parallel pipeline performance characteristics."""

    def test_parallel_scales_with_many_agents(self):
        """Test that parallel handles many agents efficiently."""
        # Create 50 agents
        many_agents = [MockAgent(f"agent_{i}", delay=0.05) for i in range(50)]

        pipeline = Pipeline.parallel(agents=many_agents, max_workers=10)

        start = time.time()
        result = pipeline.run(input="test")
        duration = time.time() - start

        # With 10 workers, 50 agents should complete in ~0.25s (50/10 * 0.05)
        # Allow 2x buffer for overhead
        assert duration < 0.5, f"50 agents took {duration:.3f}s (should be <0.5s)"

        # All agents executed
        assert len(result["results"]) == 50

    def test_parallel_respects_max_workers_limit(self):
        """Test that parallel respects max_workers parameter."""
        # Create many agents
        agents = [MockAgent(f"agent_{i}") for i in range(20)]

        pipeline = Pipeline.parallel(agents=agents, max_workers=5)

        result = pipeline.run(input="test")

        # Should complete successfully with limited workers
        assert len(result["results"]) == 20

    def test_parallel_memory_usage_reasonable(self):
        """Test that parallel doesn't exhaust memory with many agents."""
        # Create 100 agents
        many_agents = [MockAgent(f"agent_{i}") for i in range(100)]

        pipeline = Pipeline.parallel(agents=many_agents, max_workers=10)

        # Should not raise MemoryError
        result = pipeline.run(input="test")

        assert len(result["results"]) == 100


# ============================================================================
# Test Edge Cases
# ============================================================================


class TestParallelEdgeCases:
    """Test parallel pipeline edge cases."""

    def test_parallel_with_single_agent(self, mock_agents):
        """Test that parallel works with single agent."""
        pipeline = Pipeline.parallel(agents=[mock_agents[0]])

        result = pipeline.run(input="test")

        # Should work, return single result
        assert "results" in result
        assert len(result["results"]) == 1

    def test_parallel_with_none_inputs(self, mock_agents):
        """Test that parallel handles None inputs gracefully."""
        pipeline = Pipeline.parallel(agents=mock_agents[:2])

        # Should not crash
        result = pipeline.run(input=None)

        assert result is not None
        assert "results" in result

    def test_parallel_with_agent_returning_none(self, mock_agents):
        """Test that parallel handles agents returning None."""

        class NoneReturningAgent(BaseAgent):
            def __init__(self):
                super().__init__(
                    config=BaseAgentConfig(llm_provider="mock", model="test"),
                    signature=SimpleSignature(),
                    agent_id="none_agent",
                )

            def run(self, **inputs):
                return None

        agents = [mock_agents[0], NoneReturningAgent(), mock_agents[1]]

        pipeline = Pipeline.parallel(agents=agents)

        result = pipeline.run(input="test")

        # Should handle None result gracefully
        assert len(result["results"]) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
