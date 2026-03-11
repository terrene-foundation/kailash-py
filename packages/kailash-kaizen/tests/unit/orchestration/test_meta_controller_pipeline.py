"""
Unit tests for Meta-Controller (Router) Pipeline pattern.

Tests capability-based routing with A2A integration and graceful fallback.
Written BEFORE implementation (TDD approach).
"""

from unittest.mock import Mock, patch

import pytest

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.orchestration.pipeline import Pipeline
from kaizen.signatures import InputField, OutputField, Signature

# Check A2A availability
try:
    from kaizen.nodes.ai.a2a import A2AAgentCard

    A2A_AVAILABLE = True
except ImportError:
    A2A_AVAILABLE = False

# ============================================================================
# Test Fixtures
# ============================================================================


class SimpleSignature(Signature):
    """Simple signature for test agents."""

    input: str = InputField(description="Input data")
    output: str = OutputField(description="Output data")


class MockAgent(BaseAgent):
    """Mock agent for testing."""

    def __init__(self, agent_id: str, capability: str = "general"):
        """Initialize mock agent with specific capability."""
        super().__init__(
            config=BaseAgentConfig(llm_provider="mock", model="test"),
            signature=SimpleSignature(),
            agent_id=agent_id,
        )
        self.capability = capability
        self._call_count = 0

    def run(self, **inputs):
        """Mock run method."""
        self._call_count += 1
        return {
            "output": f"{self.agent_id} processed: {inputs.get('input', '')}",
            "agent_id": self.agent_id,
            "capability": self.capability,
        }

    def to_a2a_card(self):
        """Generate mock A2A card."""

        card = Mock()
        card.primary_capabilities = [MockCapability(self.capability)]
        return card


class MockCapability:
    """Mock A2A capability."""

    def __init__(self, name: str):
        self.name = name

    def matches_requirement(self, task: str) -> float:
        """Calculate mock capability match score."""
        # Simple keyword matching for testing
        task_lower = task.lower()
        if self.name == "coding" and any(
            kw in task_lower for kw in ["code", "python", "function", "program"]
        ):
            return 0.9
        elif self.name == "data_analysis" and any(
            kw in task_lower for kw in ["analyze", "data", "statistics", "chart"]
        ):
            return 0.9
        elif self.name == "writing" and any(
            kw in task_lower for kw in ["write", "article", "document", "essay"]
        ):
            return 0.9
        elif self.name == "general":
            return 0.5
        else:
            return 0.1


@pytest.fixture
def mock_agents():
    """Create mock agents with different capabilities."""
    return [
        MockAgent("code_expert", capability="coding"),
        MockAgent("data_expert", capability="data_analysis"),
        MockAgent("writing_expert", capability="writing"),
        MockAgent("general_agent", capability="general"),
    ]


# ============================================================================
# Test Basic Router Creation
# ============================================================================


class TestRouterCreation:
    """Test Meta-Controller (Router) Pipeline creation."""

    def test_router_factory_method_exists(self):
        """Test that Pipeline.router() factory method exists."""
        assert hasattr(Pipeline, "router"), "Pipeline.router() factory method not found"
        assert callable(Pipeline.router), "Pipeline.router is not callable"

    def test_router_creates_meta_controller_pipeline(self, mock_agents):
        """Test that Pipeline.router() creates MetaControllerPipeline instance."""
        pipeline = Pipeline.router(agents=mock_agents[:2])

        assert pipeline is not None
        assert hasattr(pipeline, "run"), "MetaControllerPipeline must have run() method"
        assert isinstance(
            pipeline, Pipeline
        ), "MetaControllerPipeline must inherit from Pipeline"

    def test_router_requires_agents_parameter(self):
        """Test that router() requires agents parameter."""
        with pytest.raises(TypeError):
            Pipeline.router()  # Missing required 'agents' parameter

    def test_router_rejects_empty_agents_list(self):
        """Test that router() rejects empty agents list."""
        with pytest.raises(ValueError, match="agents cannot be empty"):
            Pipeline.router(agents=[])

    def test_router_accepts_routing_strategy_parameter(self, mock_agents):
        """Test that router() accepts routing_strategy parameter."""
        # Should not raise
        pipeline_semantic = Pipeline.router(
            agents=mock_agents[:2], routing_strategy="semantic"
        )
        pipeline_roundrobin = Pipeline.router(
            agents=mock_agents[:2], routing_strategy="round-robin"
        )

        assert pipeline_semantic is not None
        assert pipeline_roundrobin is not None


# ============================================================================
# Test A2A Semantic Routing
# ============================================================================


@pytest.mark.skipif(
    not A2A_AVAILABLE, reason="A2A module required for semantic routing"
)
class TestA2ASemanticRouting:
    """Test A2A capability-based semantic routing."""

    def test_router_selects_best_agent_via_a2a(self, mock_agents):
        """Test that router selects best agent based on A2A capability matching."""
        pipeline = Pipeline.router(agents=mock_agents, routing_strategy="semantic")

        # Task requiring coding capability
        result = pipeline.run(
            task="Write a Python function to sort a list", input="test"
        )

        # Should select code_expert (highest A2A score for coding task)
        assert result is not None
        assert "agent_id" in result or "output" in result
        # Verify code_expert was used
        assert mock_agents[0]._call_count == 1, "code_expert should be selected"
        assert mock_agents[1]._call_count == 0, "data_expert should NOT be selected"
        assert mock_agents[2]._call_count == 0, "writing_expert should NOT be selected"

    def test_router_selects_data_agent_for_analysis_task(self, mock_agents):
        """Test that router selects data agent for analysis task."""
        pipeline = Pipeline.router(agents=mock_agents, routing_strategy="semantic")

        # Task requiring data analysis capability
        result = pipeline.run(
            task="Analyze sales data and create chart", input="sales.csv"
        )

        # Should select data_expert
        assert result is not None
        assert mock_agents[1]._call_count == 1, "data_expert should be selected"
        assert mock_agents[0]._call_count == 0, "code_expert should NOT be selected"

    def test_router_selects_writing_agent_for_writing_task(self, mock_agents):
        """Test that router selects writing agent for writing task."""
        pipeline = Pipeline.router(agents=mock_agents, routing_strategy="semantic")

        # Task requiring writing capability
        result = pipeline.run(task="Write an article about AI", input="AI topic")

        # Should select writing_expert
        assert result is not None
        assert mock_agents[2]._call_count == 1, "writing_expert should be selected"

    def test_router_returns_agent_execution_result(self, mock_agents):
        """Test that router returns selected agent's execution result."""
        pipeline = Pipeline.router(agents=mock_agents[:2], routing_strategy="semantic")

        result = pipeline.run(task="Code task", input="test_data")

        # Result should contain agent output
        assert "output" in result
        assert "code_expert processed: test_data" in result["output"]


# ============================================================================
# Test Fallback Behavior
# ============================================================================


class TestRouterFallback:
    """Test router fallback behavior when A2A unavailable or fails."""

    @patch("kaizen.orchestration.patterns.meta_controller.A2A_AVAILABLE", False)
    def test_router_fallback_when_a2a_unavailable(self, mock_agents):
        """Test that router falls back to first agent when A2A unavailable."""
        pipeline = Pipeline.router(agents=mock_agents, routing_strategy="semantic")

        result = pipeline.run(task="Any task", input="test")

        # Should fall back to first agent (code_expert)
        assert result is not None
        assert (
            mock_agents[0]._call_count == 1
        ), "Should fall back to first agent when A2A unavailable"

    def test_router_fallback_on_zero_a2a_scores(self, mock_agents):
        """Test router fallback when no agent matches task (all scores = 0)."""
        # Use only specific agents (no general agent) to ensure fallback
        specific_agents = mock_agents[:3]  # code, data, writing experts only
        pipeline = Pipeline.router(agents=specific_agents, routing_strategy="semantic")

        # Task with no matching capabilities
        result = pipeline.run(
            task="Perform quantum physics calculation", input="quantum_data"
        )

        # Should fall back to first agent (code_expert)
        assert result is not None
        assert (
            specific_agents[0]._call_count == 1
        ), "Should fall back to first agent when no capability match"

    def test_router_fallback_round_robin_strategy(self, mock_agents):
        """Test router with explicit round-robin fallback strategy."""
        pipeline = Pipeline.router(
            agents=mock_agents[:3], routing_strategy="round-robin"
        )

        # First call - agent 0
        _result1 = pipeline.run(task="Task 1", input="data1")
        assert mock_agents[0]._call_count == 1

        # Second call - agent 1
        _result2 = pipeline.run(task="Task 2", input="data2")
        assert mock_agents[1]._call_count == 1

        # Third call - agent 2
        _result3 = pipeline.run(task="Task 3", input="data3")
        assert mock_agents[2]._call_count == 1


# ============================================================================
# Test Error Handling
# ============================================================================


class TestRouterErrorHandling:
    """Test router error handling."""

    def test_router_handles_agent_failure_gracefully(self, mock_agents):
        """Test that router handles agent execution failure gracefully."""

        class FailingAgent(BaseAgent):
            def __init__(self):
                super().__init__(
                    config=BaseAgentConfig(llm_provider="mock", model="test"),
                    signature=SimpleSignature(),
                    agent_id="failing_agent",
                )

            def run(self, **inputs):
                raise Exception("Intentional failure for testing")

        pipeline = Pipeline.router(agents=[FailingAgent()], routing_strategy="semantic")
        pipeline.error_handling = "graceful"  # Set graceful mode

        result = pipeline.run(task="Test task", input="test")

        # Should return error info, not raise
        assert result is not None
        assert "error" in result
        assert "Intentional failure" in str(result["error"])

    def test_router_fail_fast_mode_raises_exception(self, mock_agents):
        """Test that router fail-fast mode raises exceptions."""

        class FailingAgent(BaseAgent):
            def __init__(self):
                super().__init__(
                    config=BaseAgentConfig(llm_provider="mock", model="test"),
                    signature=SimpleSignature(),
                    agent_id="failing_agent",
                )

            def run(self, **inputs):
                raise Exception("Intentional failure")

        pipeline = Pipeline.router(agents=[FailingAgent()], routing_strategy="semantic")
        pipeline.error_handling = "fail-fast"  # Set fail-fast mode

        with pytest.raises(Exception, match="Intentional failure"):
            pipeline.run(task="Test task", input="test")

    def test_router_handles_missing_task_parameter(self, mock_agents):
        """Test that router handles missing 'task' parameter gracefully."""
        pipeline = Pipeline.router(agents=mock_agents[:2], routing_strategy="semantic")

        # Call without 'task' parameter
        result = pipeline.run(input="test_data")

        # Should still work (use fallback or input as task)
        assert result is not None


# ============================================================================
# Test Composability (.to_agent())
# ============================================================================


class TestRouterComposability:
    """Test that router pipeline can be converted to agent."""

    def test_router_pipeline_to_agent(self, mock_agents):
        """Test that router pipeline can be converted to agent via .to_agent()."""
        pipeline = Pipeline.router(agents=mock_agents[:2], routing_strategy="semantic")

        agent = pipeline.to_agent(name="router_agent", description="Router as agent")

        # Verify it's a BaseAgent
        assert isinstance(agent, BaseAgent)
        assert agent.agent_id == "router_agent"
        assert agent.description == "Router as agent"

    def test_router_agent_executes_correctly(self, mock_agents):
        """Test that router converted to agent executes correctly."""
        pipeline = Pipeline.router(agents=mock_agents[:2], routing_strategy="semantic")
        agent = pipeline.to_agent()

        result = agent.run(task="Code task", input="test")

        # Should route to code_expert and return result
        assert result is not None
        assert "output" in result

    def test_router_agent_can_be_nested_in_pipeline(self, mock_agents):
        """Test that router agent can be used in another pipeline."""
        from kaizen.orchestration.pipeline import SequentialPipeline

        # Create router as agent
        router_pipeline = Pipeline.router(
            agents=mock_agents[:2], routing_strategy="semantic"
        )
        router_agent = router_pipeline.to_agent(name="router_step")

        # Use in sequential pipeline
        sequential = SequentialPipeline(agents=[router_agent, mock_agents[3]])

        result = sequential.run(task="Code task", input="test")

        # Should execute both steps
        assert result is not None
        assert "final_output" in result


# ============================================================================
# Test Performance
# ============================================================================


class TestRouterPerformance:
    """Test router performance characteristics."""

    def test_router_executes_in_reasonable_time(self, mock_agents):
        """Test that router executes within performance targets."""
        import time

        pipeline = Pipeline.router(agents=mock_agents, routing_strategy="semantic")

        start = time.time()
        result = pipeline.run(task="Test task", input="test")
        duration = time.time() - start

        # Should complete in <100ms (target from ADR-018)
        assert duration < 0.1, f"Router took {duration:.3f}s (target: <100ms)"
        assert result is not None

    def test_router_a2a_matching_speed(self, mock_agents):
        """Test that A2A matching completes quickly."""
        import time

        # Create router with many agents (stress test)
        many_agents = [MockAgent(f"agent_{i}", capability="general") for i in range(20)]

        pipeline = Pipeline.router(agents=many_agents, routing_strategy="semantic")

        start = time.time()
        result = pipeline.run(task="Test task", input="test")
        duration = time.time() - start

        # A2A matching should complete in <50ms even with 20 agents (ADR-018 target)
        assert duration < 0.05, f"A2A matching took {duration:.3f}s (target: <50ms)"
        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
