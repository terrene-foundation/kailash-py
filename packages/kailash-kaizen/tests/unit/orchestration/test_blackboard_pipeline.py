"""
Unit tests for Blackboard Pipeline pattern.

Tests A2A specialist selection (iterative) with controller and graceful fallback.
Written BEFORE implementation (TDD approach).

Pattern:
    User Request → Blackboard → A2A Specialist Selection (iterative) → Controller → Result

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
    """Mock specialist agent for testing."""

    def __init__(self, agent_id: str, capability: str = "general"):
        """Initialize mock specialist with specific capability."""
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
        blackboard = inputs.get("blackboard", {})

        return {
            "output": f"{self.agent_id} insight: {inputs.get('input', '')}",
            "agent_id": self.agent_id,
            "capability": self.capability,
            "previous_insights": len(blackboard.get("insights", [])),
        }

    def to_a2a_card(self):
        """Generate mock A2A card."""
        card = Mock()
        card.primary_capabilities = [MockCapability(self.capability)]
        return card


class MockControllerAgent(BaseAgent):
    """Mock controller agent for blackboard."""

    def __init__(self, agent_id: str = "controller", max_iterations: int = 5):
        """Initialize mock controller."""
        super().__init__(
            config=BaseAgentConfig(llm_provider="mock", model="test"),
            signature=SimpleSignature(),
            agent_id=agent_id,
        )
        self._call_count = 0
        self.max_iterations = max_iterations

    def run(self, **inputs):
        """Mock controller decision - determine if solution complete."""
        self._call_count += 1
        blackboard = inputs.get("blackboard", {})
        insights = blackboard.get("insights", [])

        # Simple logic: complete if we have enough insights or reached max iterations
        is_complete = len(insights) >= 3 or len(insights) >= self.max_iterations

        return {
            "output": f"Controller: {'Complete' if is_complete else 'Continue'}",
            "is_complete": is_complete,
            "insight_count": len(insights),
            "next_needed_capability": "data_analysis" if not is_complete else None,
        }


class MockCapability:
    """Mock A2A capability."""

    def __init__(self, name: str):
        self.name = name

    def matches_requirement(self, task: str) -> float:
        """Calculate mock capability match score."""
        task_lower = task.lower()
        if self.name == "problem_solving" and any(
            kw in task_lower for kw in ["solve", "problem", "solution", "fix"]
        ):
            return 0.9
        elif self.name == "data_analysis" and any(
            kw in task_lower for kw in ["analyze", "data", "statistics", "metrics"]
        ):
            return 0.85
        elif self.name == "optimization" and any(
            kw in task_lower
            for kw in ["optimiz", "improve", "performance", "efficient"]
        ):
            return 0.8
        elif self.name == "validation" and any(
            kw in task_lower for kw in ["validate", "verify", "test", "check"]
        ):
            return 0.75
        elif self.name == "integration" and any(
            kw in task_lower for kw in ["integrate", "combine", "merge", "connect"]
        ):
            return 0.7
        elif self.name == "general":
            return 0.5
        else:
            return 0.1


@pytest.fixture
def mock_specialists():
    """Create diverse mock specialist agents."""
    return [
        MockAgent("problem_solver", capability="problem_solving"),
        MockAgent("data_analyst", capability="data_analysis"),
        MockAgent("optimizer", capability="optimization"),
        MockAgent("validator", capability="validation"),
        MockAgent("integrator", capability="integration"),
        MockAgent("generalist", capability="general"),
    ]


@pytest.fixture
def mock_controller():
    """Create mock controller agent."""
    return MockControllerAgent()


# ============================================================================
# Test Basic Blackboard Creation
# ============================================================================


class TestBlackboardCreation:
    """Test Blackboard Pipeline creation."""

    def test_blackboard_factory_method_exists(self):
        """Test that Pipeline.blackboard() factory method exists."""
        assert hasattr(
            Pipeline, "blackboard"
        ), "Pipeline.blackboard() factory method not found"
        assert callable(Pipeline.blackboard), "Pipeline.blackboard is not callable"

    def test_blackboard_creates_blackboard_pipeline(
        self, mock_specialists, mock_controller
    ):
        """Test that Pipeline.blackboard() creates BlackboardPipeline instance."""
        pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:3], controller=mock_controller
        )

        assert pipeline is not None
        assert hasattr(pipeline, "run"), "BlackboardPipeline must have run() method"
        assert isinstance(
            pipeline, Pipeline
        ), "BlackboardPipeline must inherit from Pipeline"

    def test_blackboard_requires_specialists_parameter(self, mock_controller):
        """Test that blackboard() requires specialists parameter."""
        with pytest.raises(TypeError):
            Pipeline.blackboard(
                controller=mock_controller
            )  # Missing required 'specialists'

    def test_blackboard_requires_controller_parameter(self, mock_specialists):
        """Test that blackboard() requires controller parameter."""
        with pytest.raises(TypeError):
            Pipeline.blackboard(
                specialists=mock_specialists
            )  # Missing required 'controller'

    def test_blackboard_rejects_empty_specialists_list(self, mock_controller):
        """Test that blackboard() rejects empty specialists list."""
        with pytest.raises(ValueError, match="specialists cannot be empty"):
            Pipeline.blackboard(specialists=[], controller=mock_controller)

    def test_blackboard_accepts_selection_mode_parameter(
        self, mock_specialists, mock_controller
    ):
        """Test that blackboard() accepts selection_mode parameter."""
        # Semantic mode (A2A)
        pipeline_semantic = Pipeline.blackboard(
            specialists=mock_specialists[:3],
            controller=mock_controller,
            selection_mode="semantic",
        )

        # Sequential mode
        pipeline_sequential = Pipeline.blackboard(
            specialists=mock_specialists[:3],
            controller=mock_controller,
            selection_mode="sequential",
        )

        assert pipeline_semantic is not None
        assert pipeline_sequential is not None

    def test_blackboard_accepts_max_iterations_parameter(
        self, mock_specialists, mock_controller
    ):
        """Test that blackboard() accepts max_iterations parameter."""
        pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:3],
            controller=mock_controller,
            max_iterations=10,
        )

        assert pipeline is not None


# ============================================================================
# Test A2A Specialist Selection (Iterative)
# ============================================================================


@pytest.mark.skipif(
    not A2A_AVAILABLE, reason="A2A module required for capability selection"
)
class TestA2ASpecialistSelection:
    """Test A2A capability-based specialist selection."""

    def test_blackboard_selects_specialist_via_a2a(
        self, mock_specialists, mock_controller
    ):
        """Test that blackboard selects best specialist based on A2A matching."""

        # Custom controller that requests problem_solving capability
        class ProblemSolvingController(MockControllerAgent):
            def run(self, **inputs):
                blackboard = inputs.get("blackboard", {})
                insights = blackboard.get("insights", [])
                # Complete after 1 specialist is called
                is_complete = len(insights) >= 1
                return {
                    "output": "Need problem solving",
                    "is_complete": is_complete,
                    "next_needed_capability": (
                        "problem_solving" if not is_complete else None
                    ),
                }

        controller = ProblemSolvingController()
        pipeline = Pipeline.blackboard(
            specialists=mock_specialists,
            controller=controller,
            selection_mode="semantic",
            max_iterations=1,  # Single iteration for testing
        )

        # Task requiring problem solving
        result = pipeline.run(task="Solve complex optimization problem", input="test")

        # Should select problem_solver first (highest A2A score for problem_solving capability)
        assert result is not None
        assert (
            mock_specialists[0]._call_count >= 1
        ), "problem_solver should be selected first"

    def test_blackboard_iterative_specialist_selection(self, mock_specialists):
        """Test that blackboard iteratively selects specialists based on evolving needs."""

        # Custom controller that tracks iterations
        class IterativeController(MockControllerAgent):
            def __init__(self):
                super().__init__()
                self.iteration = 0

            def run(self, **inputs):
                self.iteration += 1
                blackboard = inputs.get("blackboard", {})
                blackboard.get("insights", [])

                # First iteration: need data analysis
                # Second iteration: need optimization
                # Third iteration: complete
                is_complete = self.iteration >= 3

                next_capability = None
                if self.iteration == 1:
                    next_capability = "data_analysis"
                elif self.iteration == 2:
                    next_capability = "optimization"

                return {
                    "output": f"Iteration {self.iteration}",
                    "is_complete": is_complete,
                    "next_needed_capability": next_capability,
                }

        controller = IterativeController()
        pipeline = Pipeline.blackboard(
            specialists=mock_specialists,
            controller=controller,
            selection_mode="semantic",
            max_iterations=5,
        )

        pipeline.run(task="Complex task", input="test")

        # Should have 3 iterations
        assert controller.iteration >= 3, "Should iterate at least 3 times"

        # Different specialists should be called based on needs
        assert (
            mock_specialists[1]._call_count >= 1
        ), "data_analyst should be called (2nd iteration)"
        assert (
            mock_specialists[2]._call_count >= 1
        ), "optimizer should be called (3rd iteration)"

    def test_blackboard_specialist_selection_based_on_blackboard_state(
        self, mock_specialists, mock_controller
    ):
        """Test that specialist selection considers current blackboard state."""
        pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:4],
            controller=mock_controller,
            selection_mode="semantic",
            max_iterations=3,
        )

        pipeline.run(task="Analyze data, optimize, and validate results", input="test")

        # Multiple specialists should be called iteratively
        called_count = sum(s._call_count for s in mock_specialists[:4])
        assert called_count >= 2, "Multiple specialists should be called iteratively"


# ============================================================================
# Test Controller Integration
# ============================================================================


class TestControllerIntegration:
    """Test controller integration with blackboard."""

    def test_blackboard_controller_determines_completion(
        self, mock_specialists, mock_controller
    ):
        """Test that controller determines when solution is complete."""
        pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:3],
            controller=mock_controller,
            selection_mode="semantic",
            max_iterations=5,
        )

        result = pipeline.run(task="Test task", input="test")

        # Controller should have been called
        assert mock_controller._call_count >= 1, "Controller should be called"

        # Result should indicate completion
        assert result is not None
        assert "is_complete" in result

    def test_blackboard_stops_when_controller_signals_complete(self, mock_specialists):
        """Test that blackboard stops iterating when controller signals complete."""

        class EarlyController(MockControllerAgent):
            def run(self, **inputs):
                self._call_count += 1
                # Complete after first iteration
                return {
                    "output": "Complete immediately",
                    "is_complete": True,
                    "next_needed_capability": None,
                }

        controller = EarlyController()
        pipeline = Pipeline.blackboard(
            specialists=mock_specialists,
            controller=controller,
            selection_mode="semantic",
            max_iterations=10,
        )

        pipeline.run(task="Test task", input="test")

        # Should stop after 1 iteration (controller said complete)
        total_specialist_calls = sum(s._call_count for s in mock_specialists)
        assert (
            total_specialist_calls <= 2
        ), "Should stop early when controller signals complete"

    def test_blackboard_respects_max_iterations(self, mock_specialists):
        """Test that blackboard respects max_iterations limit."""

        class NeverCompleteController(MockControllerAgent):
            def run(self, **inputs):
                self._call_count += 1
                # Never says complete
                return {
                    "output": "Continue forever",
                    "is_complete": False,
                    "next_needed_capability": "general",
                }

        controller = NeverCompleteController()
        pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:2],
            controller=controller,
            selection_mode="semantic",
            max_iterations=3,
        )

        pipeline.run(task="Test task", input="test")

        # Should stop after max_iterations=3
        assert controller._call_count <= 3, "Should respect max_iterations"

    def test_blackboard_controller_receives_current_blackboard_state(
        self, mock_specialists, mock_controller
    ):
        """Test that controller receives current blackboard state."""
        pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:2],
            controller=mock_controller,
            selection_mode="semantic",
            max_iterations=2,
        )

        result = pipeline.run(task="Test task", input="test")

        # Controller should have been called and received blackboard state
        assert result is not None
        assert mock_controller._call_count >= 1, "Controller should be called"
        # Blackboard should contain accumulated insights
        assert "insights" in result
        assert len(result["insights"]) >= 1, "Should have at least one insight"


# ============================================================================
# Test Fallback Behavior
# ============================================================================


class TestBlackboardFallback:
    """Test blackboard fallback behavior when A2A unavailable or fails."""

    @patch("kaizen.orchestration.patterns.blackboard.A2A_AVAILABLE", False)
    def test_blackboard_fallback_when_a2a_unavailable(
        self, mock_specialists, mock_controller
    ):
        """Test that blackboard falls back to sequential when A2A unavailable."""
        pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:3],
            controller=mock_controller,
            selection_mode="semantic",
            max_iterations=2,
        )

        result = pipeline.run(task="Test task", input="test")

        # Should fall back to sequential specialist invocation
        assert result is not None
        # At least some specialists called
        total_calls = sum(s._call_count for s in mock_specialists[:3])
        assert total_calls >= 1, "Should fall back to sequential when A2A unavailable"

    def test_blackboard_sequential_selection_mode(
        self, mock_specialists, mock_controller
    ):
        """Test that blackboard with selection_mode='sequential' works."""
        pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:3],
            controller=mock_controller,
            selection_mode="sequential",
            max_iterations=2,
        )

        result = pipeline.run(task="Test task", input="test")

        # Should use sequential selection
        assert result is not None

    def test_blackboard_handles_no_matching_specialist(
        self, mock_specialists, mock_controller
    ):
        """Test that blackboard handles case when no specialist matches needed capability."""

        class SpecificController(MockControllerAgent):
            def run(self, **inputs):
                self._call_count += 1
                # Need non-existent capability
                return {
                    "output": "Need quantum computing",
                    "is_complete": self._call_count > 1,  # Complete after 2 iterations
                    "next_needed_capability": "quantum_computing",
                }

        controller = SpecificController()
        pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:3],
            controller=controller,
            selection_mode="semantic",
            max_iterations=3,
        )

        result = pipeline.run(task="Test task", input="test")

        # Should handle gracefully (fallback to first specialist or skip)
        assert result is not None


# ============================================================================
# Test Error Handling
# ============================================================================


class TestBlackboardErrorHandling:
    """Test blackboard error handling."""

    def test_blackboard_handles_specialist_failure_gracefully(
        self, mock_specialists, mock_controller
    ):
        """Test that blackboard handles specialist failure gracefully."""

        class FailingSpecialist(BaseAgent):
            def __init__(self):
                super().__init__(
                    config=BaseAgentConfig(llm_provider="mock", model="test"),
                    signature=SimpleSignature(),
                    agent_id="failing_specialist",
                )

            def run(self, **inputs):
                raise Exception("Specialist failure")

        pipeline = Pipeline.blackboard(
            specialists=[FailingSpecialist(), mock_specialists[0]],
            controller=mock_controller,
            selection_mode="sequential",
            max_iterations=2,
        )
        pipeline.error_handling = "graceful"

        result = pipeline.run(task="Test task", input="test")

        # Should continue with other specialists
        assert result is not None

    def test_blackboard_handles_controller_failure_gracefully(self, mock_specialists):
        """Test that blackboard handles controller failure gracefully."""

        class FailingController(BaseAgent):
            def __init__(self):
                super().__init__(
                    config=BaseAgentConfig(llm_provider="mock", model="test"),
                    signature=SimpleSignature(),
                    agent_id="failing_controller",
                )

            def run(self, **inputs):
                raise Exception("Controller failure")

        pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:2],
            controller=FailingController(),
            selection_mode="sequential",
            max_iterations=2,
        )
        pipeline.error_handling = "graceful"

        result = pipeline.run(task="Test task", input="test")

        # Should return error info (blackboard uses "controller_error" key)
        assert result is not None
        assert "controller_error" in result
        assert "Controller failure" in result["controller_error"]

    def test_blackboard_fail_fast_mode_raises_exception(self, mock_specialists):
        """Test that blackboard fail-fast mode raises exceptions."""

        class FailingController(BaseAgent):
            def __init__(self):
                super().__init__(
                    config=BaseAgentConfig(llm_provider="mock", model="test"),
                    signature=SimpleSignature(),
                    agent_id="failing_controller",
                )

            def run(self, **inputs):
                raise Exception("Controller failure")

        pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:2],
            controller=FailingController(),
            selection_mode="sequential",
            max_iterations=2,
        )
        pipeline.error_handling = "fail-fast"

        with pytest.raises(Exception, match="Controller failure"):
            pipeline.run(task="Test task", input="test")

    def test_blackboard_handles_missing_task_parameter(
        self, mock_specialists, mock_controller
    ):
        """Test that blackboard handles missing 'task' parameter gracefully."""
        pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:2],
            controller=mock_controller,
            selection_mode="semantic",
        )

        # Call without 'task' parameter
        result = pipeline.run(input="test_data")

        # Should still work (use fallback or default)
        assert result is not None


# ============================================================================
# Test Composability (.to_agent())
# ============================================================================


class TestBlackboardComposability:
    """Test that blackboard pipeline can be converted to agent."""

    def test_blackboard_pipeline_to_agent(self, mock_specialists, mock_controller):
        """Test that blackboard pipeline can be converted to agent via .to_agent()."""
        pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:3],
            controller=mock_controller,
            selection_mode="semantic",
        )

        agent = pipeline.to_agent(
            name="blackboard_agent", description="Blackboard as agent"
        )

        # Verify it's a BaseAgent
        assert isinstance(agent, BaseAgent)
        assert agent.agent_id == "blackboard_agent"
        assert agent.description == "Blackboard as agent"

    def test_blackboard_agent_executes_correctly(
        self, mock_specialists, mock_controller
    ):
        """Test that blackboard converted to agent executes correctly."""
        pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:3],
            controller=mock_controller,
            selection_mode="sequential",
        )
        agent = pipeline.to_agent()

        result = agent.run(task="Test task", input="test")

        # Should execute blackboard and return result
        assert result is not None

    def test_blackboard_agent_can_be_nested_in_pipeline(
        self, mock_specialists, mock_controller
    ):
        """Test that blackboard agent can be used in another pipeline."""
        from kaizen.orchestration.pipeline import SequentialPipeline

        # Create blackboard as agent
        blackboard_pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:2],
            controller=mock_controller,
            selection_mode="sequential",
            max_iterations=2,
        )
        blackboard_agent = blackboard_pipeline.to_agent(name="blackboard_step")

        # Use in sequential pipeline
        sequential = SequentialPipeline(agents=[blackboard_agent, mock_specialists[3]])

        result = sequential.run(task="Test task", input="test")

        # Should execute both steps
        assert result is not None
        assert "final_output" in result


# ============================================================================
# Test Blackboard State Management
# ============================================================================


class TestBlackboardStateManagement:
    """Test blackboard state accumulation and management."""

    def test_blackboard_accumulates_insights(self, mock_specialists, mock_controller):
        """Test that blackboard accumulates insights from specialists."""
        pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:3],
            controller=mock_controller,
            selection_mode="sequential",
            max_iterations=3,
        )

        result = pipeline.run(task="Test task", input="test")

        # Result should contain accumulated insights
        assert result is not None
        assert "insights" in result or "insight_count" in result

    def test_blackboard_maintains_state_across_iterations(self, mock_specialists):
        """Test that blackboard maintains state across iterations."""

        class StateTrackingController(MockControllerAgent):
            def run(self, **inputs):
                self._call_count += 1
                blackboard = inputs.get("blackboard", {})
                insights = blackboard.get("insights", [])

                # Verify state grows
                assert len(insights) == self._call_count - 1, "State should accumulate"

                return {
                    "output": f"Iteration {self._call_count}",
                    "is_complete": self._call_count >= 2,
                    "next_needed_capability": "general",
                }

        controller = StateTrackingController()
        pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:2],
            controller=controller,
            selection_mode="sequential",
            max_iterations=3,
        )

        result = pipeline.run(task="Test task", input="test")
        assert result is not None

    def test_blackboard_state_isolation_between_runs(
        self, mock_specialists, mock_controller
    ):
        """Test that blackboard state is isolated between different runs."""
        pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:2],
            controller=mock_controller,
            selection_mode="sequential",
            max_iterations=2,
        )

        # First run
        result1 = pipeline.run(task="Task 1", input="test1")

        # Second run (should have clean state)
        result2 = pipeline.run(task="Task 2", input="test2")

        # Both should succeed, states should not interfere
        assert result1 is not None
        assert result2 is not None


# ============================================================================
# Test Performance
# ============================================================================


class TestBlackboardPerformance:
    """Test blackboard performance characteristics."""

    def test_blackboard_executes_in_reasonable_time(
        self, mock_specialists, mock_controller
    ):
        """Test that blackboard executes within performance targets."""
        import time

        pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:3],
            controller=mock_controller,
            selection_mode="semantic",
            max_iterations=3,
        )

        start = time.time()
        result = pipeline.run(task="Test task", input="test")
        duration = time.time() - start

        # Should complete in <300ms (3 iterations max)
        assert duration < 0.3, f"Blackboard took {duration:.3f}s (target: <300ms)"
        assert result is not None

    def test_blackboard_specialist_selection_speed(
        self, mock_specialists, mock_controller
    ):
        """Test that specialist selection is fast."""
        import time

        # Many specialists
        many_specialists = [
            MockAgent(f"specialist_{i}", capability="general") for i in range(20)
        ]

        pipeline = Pipeline.blackboard(
            specialists=many_specialists,
            controller=mock_controller,
            selection_mode="semantic",
            max_iterations=2,
        )

        start = time.time()
        result = pipeline.run(task="Test task", input="test")
        duration = time.time() - start

        # Should be fast even with many specialists
        assert (
            duration < 0.2
        ), f"Specialist selection took {duration:.3f}s (target: <200ms)"
        assert result is not None


# ============================================================================
# Test Convergence Behavior
# ============================================================================


class TestBlackboardConvergence:
    """Test blackboard convergence behavior."""

    def test_blackboard_converges_to_solution(self, mock_specialists):
        """Test that blackboard converges to solution over iterations."""

        class ConvergingController(MockControllerAgent):
            def run(self, **inputs):
                self._call_count += 1
                blackboard = inputs.get("blackboard", {})
                insights = blackboard.get("insights", [])

                # Converge after accumulating enough insights
                is_complete = len(insights) >= 3

                return {
                    "output": "Converging to solution",
                    "is_complete": is_complete,
                    "next_needed_capability": "general" if not is_complete else None,
                }

        controller = ConvergingController()
        pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:4],
            controller=controller,
            selection_mode="sequential",
            max_iterations=10,
        )

        result = pipeline.run(task="Test task", input="test")

        # Should converge before max_iterations
        assert controller._call_count < 10, "Should converge before max_iterations"
        assert result is not None

    def test_blackboard_handles_non_convergence(self, mock_specialists):
        """Test that blackboard handles non-convergence gracefully."""

        class NonConvergingController(MockControllerAgent):
            def run(self, **inputs):
                self._call_count += 1
                # Never converges
                return {
                    "output": "Never complete",
                    "is_complete": False,
                    "next_needed_capability": "general",
                }

        controller = NonConvergingController()
        pipeline = Pipeline.blackboard(
            specialists=mock_specialists[:2],
            controller=controller,
            selection_mode="sequential",
            max_iterations=5,
        )

        result = pipeline.run(task="Test task", input="test")

        # Should stop at max_iterations
        assert controller._call_count == 5, "Should stop at max_iterations"
        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
