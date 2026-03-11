"""
Unit tests for Ensemble Pipeline pattern.

Tests A2A agent discovery (top-k selection) with synthesizer and graceful fallback.
Written BEFORE implementation (TDD approach).

Pattern:
    User Request → Ensemble → A2A Discovery (top-k) → Multiple Agents → Synthesizer → Result

Author: Kaizen Framework Team
Created: 2025-10-27 (Phase 3, Day 2, TODO-174)
Reference: ADR-018, docs/testing/pipeline-edge-case-test-matrix.md
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
            "output": f"{self.agent_id} perspective: {inputs.get('input', '')}",
            "agent_id": self.agent_id,
            "capability": self.capability,
        }

    def to_a2a_card(self):
        """Generate mock A2A card."""
        card = Mock()
        card.primary_capabilities = [MockCapability(self.capability)]
        return card


class MockSynthesizerAgent(BaseAgent):
    """Mock synthesizer agent for ensemble."""

    def __init__(self, agent_id: str = "synthesizer"):
        """Initialize mock synthesizer."""
        super().__init__(
            config=BaseAgentConfig(llm_provider="mock", model="test"),
            signature=SimpleSignature(),
            agent_id=agent_id,
        )
        self._call_count = 0

    def run(self, **inputs):
        """Mock synthesis - combine perspectives."""
        self._call_count += 1
        perspectives = inputs.get("perspectives", [])
        task = inputs.get("task", "unknown task")

        # Synthesize all perspectives
        combined = " | ".join([str(p) for p in perspectives])

        return {
            "output": f"Synthesized from {len(perspectives)} perspectives: {combined}",
            "perspective_count": len(perspectives),
            "task": task,
        }


class MockCapability:
    """Mock A2A capability."""

    def __init__(self, name: str):
        self.name = name

    def matches_requirement(self, task: str) -> float:
        """Calculate mock capability match score."""
        task_lower = task.lower()
        if self.name == "coding" and any(
            kw in task_lower for kw in ["code", "python", "function", "program"]
        ):
            return 0.9
        elif self.name == "data_analysis" and any(
            kw in task_lower for kw in ["analyze", "data", "statistics", "chart"]
        ):
            return 0.8
        elif self.name == "writing" and any(
            kw in task_lower for kw in ["write", "article", "document", "essay"]
        ):
            return 0.85
        elif self.name == "research" and any(
            kw in task_lower for kw in ["research", "study", "investigate", "find"]
        ):
            return 0.75
        elif self.name == "design" and any(
            kw in task_lower for kw in ["design", "ui", "ux", "interface"]
        ):
            return 0.7
        elif self.name == "general":
            return 0.5
        else:
            return 0.1


@pytest.fixture
def mock_agents():
    """Create diverse mock agents with different capabilities."""
    return [
        MockAgent("code_expert", capability="coding"),
        MockAgent("data_expert", capability="data_analysis"),
        MockAgent("writing_expert", capability="writing"),
        MockAgent("research_expert", capability="research"),
        MockAgent("design_expert", capability="design"),
        MockAgent("general_agent", capability="general"),
    ]


@pytest.fixture
def mock_synthesizer():
    """Create mock synthesizer agent."""
    return MockSynthesizerAgent()


# ============================================================================
# Test Basic Ensemble Creation
# ============================================================================


class TestEnsembleCreation:
    """Test Ensemble Pipeline creation."""

    def test_ensemble_factory_method_exists(self):
        """Test that Pipeline.ensemble() factory method exists."""
        assert hasattr(
            Pipeline, "ensemble"
        ), "Pipeline.ensemble() factory method not found"
        assert callable(Pipeline.ensemble), "Pipeline.ensemble is not callable"

    def test_ensemble_creates_ensemble_pipeline(self, mock_agents, mock_synthesizer):
        """Test that Pipeline.ensemble() creates EnsemblePipeline instance."""
        pipeline = Pipeline.ensemble(
            agents=mock_agents[:3], synthesizer=mock_synthesizer
        )

        assert pipeline is not None
        assert hasattr(pipeline, "run"), "EnsemblePipeline must have run() method"
        assert isinstance(
            pipeline, Pipeline
        ), "EnsemblePipeline must inherit from Pipeline"

    def test_ensemble_requires_agents_parameter(self, mock_synthesizer):
        """Test that ensemble() requires agents parameter."""
        with pytest.raises(TypeError):
            Pipeline.ensemble(synthesizer=mock_synthesizer)  # Missing required 'agents'

    def test_ensemble_requires_synthesizer_parameter(self, mock_agents):
        """Test that ensemble() requires synthesizer parameter."""
        with pytest.raises(TypeError):
            Pipeline.ensemble(agents=mock_agents)  # Missing required 'synthesizer'

    def test_ensemble_rejects_empty_agents_list(self, mock_synthesizer):
        """Test that ensemble() rejects empty agents list."""
        with pytest.raises(ValueError, match="agents cannot be empty"):
            Pipeline.ensemble(agents=[], synthesizer=mock_synthesizer)

    def test_ensemble_accepts_discovery_mode_parameter(
        self, mock_agents, mock_synthesizer
    ):
        """Test that ensemble() accepts discovery_mode parameter."""
        # A2A mode
        pipeline_a2a = Pipeline.ensemble(
            agents=mock_agents[:3], synthesizer=mock_synthesizer, discovery_mode="a2a"
        )

        # All agents mode
        pipeline_all = Pipeline.ensemble(
            agents=mock_agents[:3], synthesizer=mock_synthesizer, discovery_mode="all"
        )

        assert pipeline_a2a is not None
        assert pipeline_all is not None

    def test_ensemble_accepts_top_k_parameter(self, mock_agents, mock_synthesizer):
        """Test that ensemble() accepts top_k parameter."""
        pipeline = Pipeline.ensemble(
            agents=mock_agents, synthesizer=mock_synthesizer, top_k=3
        )

        assert pipeline is not None


# ============================================================================
# Test A2A Agent Discovery (Top-K Selection)
# ============================================================================


@pytest.mark.skipif(
    not A2A_AVAILABLE, reason="A2A module required for capability discovery"
)
class TestA2AAgentDiscovery:
    """Test A2A capability-based agent discovery."""

    def test_ensemble_selects_top_k_agents_via_a2a(self, mock_agents, mock_synthesizer):
        """Test that ensemble selects top-k best agents based on A2A scores."""
        pipeline = Pipeline.ensemble(
            agents=mock_agents,
            synthesizer=mock_synthesizer,
            discovery_mode="a2a",
            top_k=3,
        )

        # Task requiring coding, data analysis, and research
        # (avoiding "Write" to prevent writing_expert match)
        result = pipeline.run(
            task="Create Python code to analyze data and research best practices",
            input="test",
        )

        # Should select top 3 agents: code_expert (0.9), data_expert (0.8), research_expert (0.75)
        assert result is not None
        assert "perspective_count" in result
        assert result["perspective_count"] == 3, "Should use exactly 3 agents (top_k=3)"

        # Verify correct agents were called
        assert (
            mock_agents[0]._call_count == 1
        ), "code_expert should be selected (top score)"
        assert mock_agents[1]._call_count == 1, "data_expert should be selected (2nd)"
        assert (
            mock_agents[3]._call_count == 1
        ), "research_expert should be selected (3rd)"

        # Verify other agents NOT called
        assert mock_agents[2]._call_count == 0, "writing_expert should NOT be selected"
        assert mock_agents[4]._call_count == 0, "design_expert should NOT be selected"
        assert mock_agents[5]._call_count == 0, "general_agent should NOT be selected"

    def test_ensemble_respects_top_k_limit(self, mock_agents, mock_synthesizer):
        """Test that ensemble respects top_k limit."""
        # top_k=2 should select only 2 agents
        pipeline = Pipeline.ensemble(
            agents=mock_agents,
            synthesizer=mock_synthesizer,
            discovery_mode="a2a",
            top_k=2,
        )

        result = pipeline.run(task="Code and analyze data", input="test")

        assert result is not None
        assert result["perspective_count"] == 2, "Should use exactly 2 agents (top_k=2)"

    def test_ensemble_handles_top_k_larger_than_agent_count(
        self, mock_agents, mock_synthesizer
    ):
        """Test that ensemble handles top_k larger than available agents."""
        # Only 3 agents, but top_k=10
        pipeline = Pipeline.ensemble(
            agents=mock_agents[:3],
            synthesizer=mock_synthesizer,
            discovery_mode="a2a",
            top_k=10,
        )

        result = pipeline.run(task="Test task", input="test")

        # Should use all 3 available agents
        assert result is not None
        assert result["perspective_count"] == 3, "Should use all 3 available agents"

    def test_ensemble_discovery_prioritizes_highest_scores(
        self, mock_agents, mock_synthesizer
    ):
        """Test that ensemble prioritizes agents with highest A2A scores."""
        pipeline = Pipeline.ensemble(
            agents=mock_agents,
            synthesizer=mock_synthesizer,
            discovery_mode="a2a",
            top_k=1,
        )

        # Task specifically for coding (highest score: 0.9)
        pipeline.run(task="Write Python function", input="test")

        # Only code_expert should be selected (highest score)
        assert (
            mock_agents[0]._call_count == 1
        ), "code_expert should be selected (highest score)"
        assert (
            sum(a._call_count for a in mock_agents[1:]) == 0
        ), "Other agents should NOT be selected"


# ============================================================================
# Test Synthesizer Integration
# ============================================================================


class TestSynthesizerIntegration:
    """Test synthesizer integration with ensemble."""

    def test_ensemble_passes_perspectives_to_synthesizer(
        self, mock_agents, mock_synthesizer
    ):
        """Test that ensemble passes all agent perspectives to synthesizer."""
        pipeline = Pipeline.ensemble(
            agents=mock_agents[:3],
            synthesizer=mock_synthesizer,
            discovery_mode="all",  # Use all agents
        )

        result = pipeline.run(task="Test task", input="test")

        # Synthesizer should have been called
        assert mock_synthesizer._call_count == 1, "Synthesizer should be called once"

        # Result should contain synthesized output
        assert result is not None
        assert "output" in result
        assert "Synthesized" in result["output"]

    def test_ensemble_synthesizer_receives_correct_perspective_count(
        self, mock_agents, mock_synthesizer
    ):
        """Test that synthesizer receives correct number of perspectives."""
        pipeline = Pipeline.ensemble(
            agents=mock_agents[:4],
            synthesizer=mock_synthesizer,
            discovery_mode="a2a",
            top_k=3,
        )

        result = pipeline.run(task="Code and write documentation", input="test")

        # Synthesizer should receive 3 perspectives
        assert result["perspective_count"] == 3

    def test_ensemble_passes_task_to_synthesizer(self, mock_agents, mock_synthesizer):
        """Test that ensemble passes original task to synthesizer."""
        pipeline = Pipeline.ensemble(
            agents=mock_agents[:2], synthesizer=mock_synthesizer, discovery_mode="all"
        )

        task = "Specific task description"
        result = pipeline.run(task=task, input="test")

        # Synthesizer should receive original task
        assert "task" in result
        assert result["task"] == task

    def test_ensemble_handles_synthesizer_failure_gracefully(self, mock_agents):
        """Test that ensemble handles synthesizer failure gracefully."""

        class FailingSynthesizer(BaseAgent):
            def __init__(self):
                super().__init__(
                    config=BaseAgentConfig(llm_provider="mock", model="test"),
                    signature=SimpleSignature(),
                    agent_id="failing_synthesizer",
                )

            def run(self, **inputs):
                raise Exception("Synthesizer failure")

        pipeline = Pipeline.ensemble(
            agents=mock_agents[:2],
            synthesizer=FailingSynthesizer(),
            discovery_mode="all",
        )
        pipeline.error_handling = "graceful"

        result = pipeline.run(task="Test task", input="test")

        # Should return error info, not raise
        assert result is not None
        assert "error" in result
        assert "Synthesizer failure" in str(result["error"])


# ============================================================================
# Test Fallback Behavior
# ============================================================================


class TestEnsembleFallback:
    """Test ensemble fallback behavior when A2A unavailable or fails."""

    @patch("kaizen.orchestration.patterns.ensemble.A2A_AVAILABLE", False)
    def test_ensemble_fallback_when_a2a_unavailable(
        self, mock_agents, mock_synthesizer
    ):
        """Test that ensemble falls back to all agents when A2A unavailable."""
        pipeline = Pipeline.ensemble(
            agents=mock_agents[:3],
            synthesizer=mock_synthesizer,
            discovery_mode="a2a",
            top_k=2,
        )

        result = pipeline.run(task="Test task", input="test")

        # Should use all 3 agents (not just top_k=2) when A2A unavailable
        assert result is not None
        # Fallback uses all agents
        total_calls = sum(a._call_count for a in mock_agents[:3])
        assert total_calls >= 2, "Should fall back to using agents when A2A unavailable"

    def test_ensemble_uses_all_agents_with_discovery_mode_all(
        self, mock_agents, mock_synthesizer
    ):
        """Test that ensemble uses all agents with discovery_mode='all'."""
        pipeline = Pipeline.ensemble(
            agents=mock_agents[:4],
            synthesizer=mock_synthesizer,
            discovery_mode="all",  # Explicit: use all agents
        )

        result = pipeline.run(task="Test task", input="test")

        # Should use all 4 agents
        assert result is not None
        assert result["perspective_count"] == 4


# ============================================================================
# Test Error Handling
# ============================================================================


class TestEnsembleErrorHandling:
    """Test ensemble error handling."""

    def test_ensemble_handles_agent_failure_gracefully(
        self, mock_agents, mock_synthesizer
    ):
        """Test that ensemble handles individual agent failures gracefully."""

        class FailingAgent(BaseAgent):
            def __init__(self):
                super().__init__(
                    config=BaseAgentConfig(llm_provider="mock", model="test"),
                    signature=SimpleSignature(),
                    agent_id="failing_agent",
                )

            def run(self, **inputs):
                raise Exception("Agent failure")

        pipeline = Pipeline.ensemble(
            agents=[FailingAgent(), mock_agents[0], mock_agents[1]],
            synthesizer=mock_synthesizer,
            discovery_mode="all",
        )
        pipeline.error_handling = "graceful"

        result = pipeline.run(task="Test task", input="test")

        # Should still synthesize from successful agents
        assert result is not None
        # At least 2 perspectives from successful agents
        assert result.get("perspective_count", 0) >= 2

    def test_ensemble_fail_fast_mode_raises_exception(
        self, mock_agents, mock_synthesizer
    ):
        """Test that ensemble fail-fast mode raises exceptions."""

        class FailingAgent(BaseAgent):
            def __init__(self):
                super().__init__(
                    config=BaseAgentConfig(llm_provider="mock", model="test"),
                    signature=SimpleSignature(),
                    agent_id="failing_agent",
                )

            def run(self, **inputs):
                raise Exception("Agent failure")

        pipeline = Pipeline.ensemble(
            agents=[FailingAgent()], synthesizer=mock_synthesizer, discovery_mode="all"
        )
        pipeline.error_handling = "fail-fast"

        with pytest.raises(Exception, match="Agent failure"):
            pipeline.run(task="Test task", input="test")

    def test_ensemble_handles_missing_task_parameter(
        self, mock_agents, mock_synthesizer
    ):
        """Test that ensemble handles missing 'task' parameter gracefully."""
        pipeline = Pipeline.ensemble(
            agents=mock_agents[:2], synthesizer=mock_synthesizer, discovery_mode="a2a"
        )

        # Call without 'task' parameter
        result = pipeline.run(input="test_data")

        # Should still work (use fallback or default)
        assert result is not None


# ============================================================================
# Test Composability (.to_agent())
# ============================================================================


class TestEnsembleComposability:
    """Test that ensemble pipeline can be converted to agent."""

    def test_ensemble_pipeline_to_agent(self, mock_agents, mock_synthesizer):
        """Test that ensemble pipeline can be converted to agent via .to_agent()."""
        pipeline = Pipeline.ensemble(
            agents=mock_agents[:3], synthesizer=mock_synthesizer, discovery_mode="a2a"
        )

        agent = pipeline.to_agent(
            name="ensemble_agent", description="Ensemble as agent"
        )

        # Verify it's a BaseAgent
        assert isinstance(agent, BaseAgent)
        assert agent.agent_id == "ensemble_agent"
        assert agent.description == "Ensemble as agent"

    def test_ensemble_agent_executes_correctly(self, mock_agents, mock_synthesizer):
        """Test that ensemble converted to agent executes correctly."""
        pipeline = Pipeline.ensemble(
            agents=mock_agents[:3], synthesizer=mock_synthesizer, discovery_mode="all"
        )
        agent = pipeline.to_agent()

        result = agent.run(task="Test task", input="test")

        # Should execute ensemble and return synthesized result
        assert result is not None
        assert "output" in result

    def test_ensemble_agent_can_be_nested_in_pipeline(
        self, mock_agents, mock_synthesizer
    ):
        """Test that ensemble agent can be used in another pipeline."""
        from kaizen.orchestration.pipeline import SequentialPipeline

        # Create ensemble as agent
        ensemble_pipeline = Pipeline.ensemble(
            agents=mock_agents[:2], synthesizer=mock_synthesizer, discovery_mode="all"
        )
        ensemble_agent = ensemble_pipeline.to_agent(name="ensemble_step")

        # Use in sequential pipeline
        sequential = SequentialPipeline(agents=[ensemble_agent, mock_agents[3]])

        result = sequential.run(task="Test task", input="test")

        # Should execute both steps
        assert result is not None
        assert "final_output" in result


# ============================================================================
# Test Diversity and Quality
# ============================================================================


class TestEnsembleDiversityQuality:
    """Test ensemble diversity and quality features."""

    def test_ensemble_provides_diverse_perspectives(
        self, mock_agents, mock_synthesizer
    ):
        """Test that ensemble selects agents with diverse capabilities."""
        pipeline = Pipeline.ensemble(
            agents=mock_agents,
            synthesizer=mock_synthesizer,
            discovery_mode="a2a",
            top_k=3,
        )

        # Task requiring multiple capabilities
        result = pipeline.run(
            task="Code, analyze, and document the results", input="test"
        )

        # Should select 3 different experts (not duplicates)
        assert result is not None
        called_agents = [a for a in mock_agents if a._call_count > 0]
        assert len(called_agents) == 3, "Should select 3 different agents"

        # Verify they have different capabilities
        capabilities = set(a.capability for a in called_agents)
        assert len(capabilities) == 3, "Should select agents with diverse capabilities"

    def test_ensemble_prefers_specialists_over_generalists(
        self, mock_agents, mock_synthesizer
    ):
        """Test that ensemble prefers specialist agents over generalists."""
        pipeline = Pipeline.ensemble(
            agents=mock_agents,
            synthesizer=mock_synthesizer,
            discovery_mode="a2a",
            top_k=3,
        )

        pipeline.run(task="Write code and analyze data", input="test")

        # Specialists should be selected over general_agent
        assert (
            mock_agents[5]._call_count == 0
        ), "general_agent should NOT be selected when specialists available"

    def test_ensemble_with_single_agent_works(self, mock_agents, mock_synthesizer):
        """Test that ensemble works with just one agent."""
        pipeline = Pipeline.ensemble(
            agents=[mock_agents[0]], synthesizer=mock_synthesizer, discovery_mode="all"
        )

        result = pipeline.run(task="Test task", input="test")

        # Should work with 1 perspective
        assert result is not None
        assert result["perspective_count"] == 1


# ============================================================================
# Test Performance
# ============================================================================


class TestEnsemblePerformance:
    """Test ensemble performance characteristics."""

    def test_ensemble_executes_in_reasonable_time(self, mock_agents, mock_synthesizer):
        """Test that ensemble executes within performance targets."""
        import time

        pipeline = Pipeline.ensemble(
            agents=mock_agents[:3],
            synthesizer=mock_synthesizer,
            discovery_mode="a2a",
            top_k=3,
        )

        start = time.time()
        result = pipeline.run(task="Test task", input="test")
        duration = time.time() - start

        # Should complete in <200ms (3 agents + synthesizer + A2A)
        assert duration < 0.2, f"Ensemble took {duration:.3f}s (target: <200ms)"
        assert result is not None

    def test_ensemble_a2a_discovery_speed(self, mock_agents, mock_synthesizer):
        """Test that A2A agent discovery completes quickly."""
        import time

        # Create ensemble with many agents (stress test)
        many_agents = [MockAgent(f"agent_{i}", capability="general") for i in range(20)]

        pipeline = Pipeline.ensemble(
            agents=many_agents,
            synthesizer=mock_synthesizer,
            discovery_mode="a2a",
            top_k=5,
        )

        start = time.time()
        result = pipeline.run(task="Test task", input="test")
        duration = time.time() - start

        # A2A discovery should complete quickly even with 20 agents
        assert duration < 0.1, f"A2A discovery took {duration:.3f}s (target: <100ms)"
        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
