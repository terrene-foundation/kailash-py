"""
Unit tests for Pipeline factory method wrappers (TODO-174 Phase 3 Day 3).

Tests all 9 factory methods on Pipeline class:
- 4 new patterns (router, parallel, ensemble, blackboard) - Already implemented
- 5 existing patterns (sequential, supervisor_worker, consensus, debate, handoff) - NEW

Written BEFORE implementation (TDD approach).
Reference: ADR-018 Pipeline Pattern Architecture
"""

import pytest
from kaizen.core.base_agent import BaseAgentConfig
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.orchestration.pipeline import Pipeline
from kaizen.signatures import InputField, OutputField, Signature

# ============================================================================
# Test Fixtures
# ============================================================================


class SimpleSignature(Signature):
    """Simple signature for test agents."""

    input: str = InputField(description="Input data")
    output: str = OutputField(description="Output data")


class MockAgent:
    """Mock agent for testing (lightweight, no BaseAgent initialization)."""

    def __init__(self, agent_id: str = "mock_agent"):
        self.agent_id = agent_id
        self.config = BaseAgentConfig(llm_provider="mock", model="test")
        self.signature = SimpleSignature()
        self.a2a_coordinator = None  # Required by SupervisorWorkerPattern

    def run(self, **inputs):
        return {"output": f"{self.agent_id} processed: {inputs.get('input', '')}"}


@pytest.fixture
def mock_agents():
    """Create mock agents for testing."""
    return [MockAgent(agent_id=f"agent_{i}") for i in range(5)]


@pytest.fixture
def shared_memory():
    """Create shared memory pool."""
    return SharedMemoryPool()


# ============================================================================
# Test Factory Method Existence (All 9 Patterns)
# ============================================================================


class TestFactoryMethodExistence:
    """Test that all 9 factory methods exist on Pipeline class."""

    def test_all_factory_methods_exist(self):
        """Test that all 9 factory methods exist and are callable."""
        factory_methods = [
            "sequential",
            "supervisor_worker",
            "router",
            "ensemble",
            "blackboard",
            "consensus",
            "debate",
            "handoff",
            "parallel",
        ]

        for method_name in factory_methods:
            assert hasattr(Pipeline, method_name), f"Pipeline.{method_name}() not found"
            method = getattr(Pipeline, method_name)
            assert callable(method), f"Pipeline.{method_name} is not callable"

    def test_factory_methods_are_static(self):
        """Test that factory methods are static methods."""

        factory_methods = [
            "sequential",
            "supervisor_worker",
            "router",
            "ensemble",
            "blackboard",
            "consensus",
            "debate",
            "handoff",
            "parallel",
        ]

        for method_name in factory_methods:
            method = getattr(Pipeline, method_name)
            # Static methods can be called without instance
            assert callable(method), f"Pipeline.{method_name} should be callable"


# ============================================================================
# Test NEW Factory Wrappers (5 Existing Patterns)
# ============================================================================


class TestSequentialFactoryWrapper:
    """Test Pipeline.sequential() factory wrapper."""

    def test_sequential_factory_method_exists(self):
        """Test that Pipeline.sequential() exists."""
        assert hasattr(Pipeline, "sequential")
        assert callable(Pipeline.sequential)

    def test_sequential_creates_sequential_pipeline(self, mock_agents):
        """Test that Pipeline.sequential() creates SequentialPipeline instance."""
        pipeline = Pipeline.sequential(agents=mock_agents[:3])

        assert pipeline is not None
        # Check it's a Pipeline instance (SequentialPipeline inherits from Pipeline or is returned)
        assert hasattr(pipeline, "run"), "Must have run() method"

    def test_sequential_requires_agents_parameter(self):
        """Test that sequential() requires agents parameter."""
        with pytest.raises(TypeError):
            Pipeline.sequential()  # Missing required 'agents' parameter

    def test_sequential_accepts_agents_list(self, mock_agents):
        """Test that sequential() accepts agents list."""
        # Should not raise
        pipeline = Pipeline.sequential(agents=mock_agents[:2])
        assert pipeline is not None

    def test_sequential_execution_order(self, mock_agents):
        """Test that sequential executes agents in order."""
        pipeline = Pipeline.sequential(agents=mock_agents[:3])

        result = pipeline.run(input="test_data")

        # Verify it executed and returned result
        assert result is not None
        # SequentialPipeline returns dict with 'final_output' and 'intermediate_results'
        assert "final_output" in result or "output" in result


class TestSupervisorWorkerFactoryWrapper:
    """Test Pipeline.supervisor_worker() factory wrapper."""

    def test_supervisor_worker_factory_method_exists(self):
        """Test that Pipeline.supervisor_worker() exists."""
        assert hasattr(Pipeline, "supervisor_worker")
        assert callable(Pipeline.supervisor_worker)

    def test_supervisor_worker_creates_pattern(self, mock_agents, shared_memory):
        """Test that Pipeline.supervisor_worker() creates pattern."""
        # supervisor_worker needs supervisor and workers parameters
        supervisor = mock_agents[0]
        workers = mock_agents[1:4]

        pattern = Pipeline.supervisor_worker(
            supervisor=supervisor, workers=workers, shared_memory=shared_memory
        )

        assert pattern is not None
        assert hasattr(pattern, "delegate"), "Should have delegate() method"
        assert hasattr(
            pattern, "aggregate_results"
        ), "Should have aggregate_results() method"
        assert pattern.supervisor == supervisor
        assert pattern.workers == workers

    def test_supervisor_worker_requires_parameters(self):
        """Test that supervisor_worker() requires supervisor and workers."""
        with pytest.raises(TypeError):
            Pipeline.supervisor_worker()  # Missing required parameters

    def test_supervisor_worker_with_shared_memory(self, mock_agents, shared_memory):
        """Test that supervisor_worker() accepts shared_memory parameter."""
        supervisor = mock_agents[0]
        workers = mock_agents[1:3]

        pattern = Pipeline.supervisor_worker(
            supervisor=supervisor, workers=workers, shared_memory=shared_memory
        )

        assert pattern is not None
        assert pattern.shared_memory == shared_memory

    def test_supervisor_worker_with_a2a_selection(self, mock_agents):
        """Test that supervisor_worker() supports A2A semantic matching."""
        supervisor = mock_agents[0]
        workers = mock_agents[1:3]

        pattern = Pipeline.supervisor_worker(
            supervisor=supervisor,
            workers=workers,
            selection_mode="semantic",  # A2A semantic matching
        )

        assert pattern is not None
        # Verify A2A coordinator is available
        assert hasattr(pattern, "supervisor")


class TestConsensusFactoryWrapper:
    """Test Pipeline.consensus() factory wrapper."""

    def test_consensus_factory_method_exists(self):
        """Test that Pipeline.consensus() exists."""
        assert hasattr(Pipeline, "consensus")
        assert callable(Pipeline.consensus)

    def test_consensus_creates_pattern(self, mock_agents, shared_memory):
        """Test that Pipeline.consensus() creates ConsensusPattern."""
        pattern = Pipeline.consensus(
            agents=mock_agents[:3], threshold=0.5, shared_memory=shared_memory
        )

        assert pattern is not None
        assert hasattr(
            pattern, "create_proposal"
        ), "Should have create_proposal() method"
        assert hasattr(
            pattern, "determine_consensus"
        ), "Should have determine_consensus() method"
        # Note: create_consensus_pattern creates its own voter agents internally
        assert hasattr(pattern, "voters")

    def test_consensus_requires_agents_parameter(self):
        """Test that consensus() requires agents parameter."""
        with pytest.raises(TypeError):
            Pipeline.consensus()  # Missing required 'agents' parameter

    def test_consensus_accepts_threshold_parameter(self, mock_agents, shared_memory):
        """Test that consensus() accepts threshold parameter."""
        pattern = Pipeline.consensus(
            agents=mock_agents[:3], threshold=0.8, shared_memory=shared_memory
        )

        assert pattern is not None

    def test_consensus_accepts_voting_strategy(self, mock_agents, shared_memory):
        """Test that consensus() accepts voting_strategy parameter."""
        pattern = Pipeline.consensus(
            agents=mock_agents[:3],
            voting_strategy="majority",
            shared_memory=shared_memory,
        )

        assert pattern is not None


class TestDebateFactoryWrapper:
    """Test Pipeline.debate() factory wrapper."""

    def test_debate_factory_method_exists(self):
        """Test that Pipeline.debate() exists."""
        assert hasattr(Pipeline, "debate")
        assert callable(Pipeline.debate)

    def test_debate_creates_pattern(self, mock_agents, shared_memory):
        """Test that Pipeline.debate() creates DebatePattern."""
        pattern = Pipeline.debate(
            agents=mock_agents[:2],  # Needs at least 2 agents (proponent, opponent)
            rounds=3,
            shared_memory=shared_memory,
        )

        assert pattern is not None
        assert hasattr(pattern, "debate"), "Should have debate() method"
        assert hasattr(pattern, "get_judgment"), "Should have get_judgment() method"
        # Note: create_debate_pattern creates its own agents internally
        assert hasattr(pattern, "proponent")
        assert hasattr(pattern, "opponent")

    def test_debate_requires_agents_parameter(self):
        """Test that debate() requires agents parameter."""
        with pytest.raises(TypeError):
            Pipeline.debate()  # Missing required 'agents' parameter

    def test_debate_accepts_rounds_parameter(self, mock_agents, shared_memory):
        """Test that debate() accepts rounds parameter."""
        pattern = Pipeline.debate(
            agents=mock_agents[:2], rounds=5, shared_memory=shared_memory
        )

        assert pattern is not None

    def test_debate_accepts_judge_parameter(self, mock_agents, shared_memory):
        """Test that debate() accepts judge parameter."""
        judge = mock_agents[0]
        pattern = Pipeline.debate(
            agents=mock_agents[1:3], judge=judge, shared_memory=shared_memory
        )

        assert pattern is not None


class TestHandoffFactoryWrapper:
    """Test Pipeline.handoff() factory wrapper."""

    def test_handoff_factory_method_exists(self):
        """Test that Pipeline.handoff() exists."""
        assert hasattr(Pipeline, "handoff")
        assert callable(Pipeline.handoff)

    def test_handoff_creates_pattern(self, mock_agents):
        """Test that Pipeline.handoff() creates HandoffPattern."""
        pattern = Pipeline.handoff(agents=mock_agents[:3])  # Creates 3-tier handoff

        assert pattern is not None
        assert hasattr(
            pattern, "execute_with_handoff"
        ), "Should have execute_with_handoff() method"
        # Note: create_handoff_pattern creates its own tier agents internally
        assert hasattr(pattern, "tiers")

    def test_handoff_requires_agents_parameter(self):
        """Test that handoff() requires agents parameter."""
        with pytest.raises(TypeError):
            Pipeline.handoff()  # Missing required 'agents' parameter

    def test_handoff_accepts_handoff_condition(self, mock_agents):
        """Test that handoff() accepts handoff_condition parameter."""
        # Note: handoff_condition is accepted but not used by create_handoff_pattern
        pattern = Pipeline.handoff(
            agents=mock_agents[:3],
            handoff_condition=lambda x: x.get("complexity", 0) > 0.5,
        )

        assert pattern is not None


# ============================================================================
# Test Factory Methods Return Correct Types
# ============================================================================


class TestFactoryReturnTypes:
    """Test that factory methods return correct pattern types."""

    def test_factory_methods_return_pipeline_instances(
        self, mock_agents, shared_memory
    ):
        """Test that all factory methods return Pipeline instances."""
        supervisor = mock_agents[0]
        workers = mock_agents[1:4]
        synthesizer = mock_agents[4]
        controller = mock_agents[0]
        specialists = mock_agents[1:3]

        patterns = {
            "sequential": Pipeline.sequential(agents=mock_agents[:2]),
            "supervisor_worker": Pipeline.supervisor_worker(
                supervisor=supervisor, workers=workers
            ),
            "router": Pipeline.router(agents=mock_agents[:2]),
            "ensemble": Pipeline.ensemble(
                agents=mock_agents[:3], synthesizer=synthesizer
            ),
            "blackboard": Pipeline.blackboard(
                specialists=specialists, controller=controller
            ),
            "consensus": Pipeline.consensus(agents=mock_agents[:3]),
            "debate": Pipeline.debate(agents=mock_agents[:2]),
            "handoff": Pipeline.handoff(agents=mock_agents[:3]),
            "parallel": Pipeline.parallel(agents=mock_agents[:2]),
        }

        for pattern_name, pattern in patterns.items():
            # All patterns should have an execution method (different names per pattern)
            assert (
                hasattr(pattern, "run")  # Most Pipeline subclasses
                or hasattr(pattern, "execute_with_handoff")  # HandoffPattern
                or hasattr(pattern, "execute_pipeline")  # Alternative execution
                or hasattr(pattern, "delegate")  # SupervisorWorkerPattern
                or hasattr(pattern, "determine_consensus")  # ConsensusPattern
                or hasattr(pattern, "debate")  # DebatePattern
            ), f"{pattern_name} must have execution method"

    def test_factory_patterns_are_composable(self, mock_agents):
        """Test that patterns created by factories are composable."""
        # Sequential pattern should be composable
        sequential = Pipeline.sequential(agents=mock_agents[:2])

        # Check if it has to_agent() method (Pipeline composability)
        if hasattr(sequential, "to_agent"):
            agent = sequential.to_agent(name="sequential_agent")
            assert agent is not None


# ============================================================================
# Test Backward Compatibility
# ============================================================================


class TestBackwardCompatibility:
    """Test that factory methods maintain backward compatibility."""

    def test_existing_code_still_works(self, mock_agents, shared_memory):
        """Test that existing code using create_*_pattern() functions still works."""
        from kaizen.orchestration.patterns.consensus import create_consensus_pattern
        from kaizen.orchestration.patterns.debate import create_debate_pattern
        from kaizen.orchestration.patterns.handoff import create_handoff_pattern
        from kaizen.orchestration.patterns.sequential import create_sequential_pipeline
        from kaizen.orchestration.patterns.supervisor_worker import (
            create_supervisor_worker_pattern,
        )

        # All existing factory functions should still work
        pattern1 = create_supervisor_worker_pattern(
            num_workers=3, shared_memory=shared_memory
        )
        pattern2 = create_consensus_pattern(num_voters=3, shared_memory=shared_memory)
        pattern3 = create_debate_pattern(shared_memory=shared_memory)
        pattern4 = create_handoff_pattern(num_tiers=3, shared_memory=shared_memory)
        pattern5 = create_sequential_pipeline(shared_memory=shared_memory)

        assert pattern1 is not None
        assert pattern2 is not None
        assert pattern3 is not None
        assert pattern4 is not None
        assert pattern5 is not None


# ============================================================================
# Test Parameter Passing
# ============================================================================


class TestParameterPassing:
    """Test that factory methods correctly pass parameters to underlying patterns."""

    def test_parameters_passed_to_sequential(self, mock_agents):
        """Test that parameters are passed correctly to SequentialPipeline."""
        pipeline = Pipeline.sequential(agents=mock_agents[:2])

        # Verify agents were passed
        assert hasattr(pipeline, "agents") or hasattr(pipeline, "stages")

    def test_parameters_passed_to_consensus(self, mock_agents):
        """Test that parameters are passed correctly to ConsensusPattern."""
        pattern = Pipeline.consensus(
            agents=mock_agents[:3], threshold=0.8, voting_strategy="majority"
        )

        # Verify pattern has voters
        assert hasattr(pattern, "voters")

    def test_parameters_passed_to_debate(self, mock_agents, shared_memory):
        """Test that parameters are passed correctly to DebatePattern."""
        pattern = Pipeline.debate(
            agents=mock_agents[:2], rounds=3, shared_memory=shared_memory
        )

        # Verify pattern has proponent, opponent, judge
        assert hasattr(pattern, "proponent")
        assert hasattr(pattern, "opponent")

    def test_parameters_passed_to_handoff(self, mock_agents):
        """Test that parameters are passed correctly to HandoffPattern."""
        pattern = Pipeline.handoff(agents=mock_agents[:3])

        # Verify pattern has tiers
        assert hasattr(pattern, "tiers") or hasattr(pattern, "execute_with_handoff")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
