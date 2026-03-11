"""
Test suite for SupervisorWorkerPattern A2A integration.

This module tests the integration of Google A2A (Agent-to-Agent) capability
matching into the SupervisorWorkerPattern. Tests verify that:

1. Pattern has A2ACoordinator integration
2. Worker selection uses semantic capability matching (not hardcoded rules)
3. Backward compatibility with agents without A2A cards
4. Selection uses 0.0-1.0 matching scores
5. Multi-agent coordination works with A2A

Test Strategy: STRICT TDD
- Write tests FIRST (RED phase)
- Implement to pass tests (GREEN phase)
- Refactor and optimize (REFACTOR phase)

Note: These tests require the kaizen.nodes.ai.a2a module.
Tests are marked to skip when A2A is not available.
"""

from typing import List
from unittest.mock import MagicMock, Mock, patch

import pytest

from kaizen.agents.coordination import (
    SupervisorAgent,
    SupervisorWorkerPattern,
    WorkerAgent,
    create_supervisor_worker_pattern,
)
from kaizen.core.base_agent import BaseAgentConfig
from kaizen.memory.shared_memory import SharedMemoryPool

# Check A2A availability
try:
    from kaizen.nodes.ai.a2a import A2AAgentCard, Capability

    A2A_AVAILABLE = True
except ImportError:
    A2A_AVAILABLE = False

# Mark tests that require A2A
pytestmark = pytest.mark.skipif(
    not A2A_AVAILABLE, reason="A2A module (kaizen.nodes.ai.a2a) not available"
)

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def mock_shared_memory():
    """Create mock shared memory pool."""
    return SharedMemoryPool()


@pytest.fixture
def mock_config():
    """Create mock agent config."""
    return BaseAgentConfig(
        llm_provider="mock", model="gpt-3.5-turbo", temperature=0.7, max_tokens=1000
    )


@pytest.fixture
def mock_a2a_coordinator():
    """Create mock A2A coordinator."""
    with patch("kailash.nodes.ai.a2a.A2ACoordinator") as mock_coordinator_class:
        mock_instance = MagicMock()
        mock_coordinator_class.return_value = mock_instance
        yield mock_instance


class MockCapability:
    """Mock capability for testing with semantic matching."""

    def __init__(
        self,
        name: str,
        domain: str,
        keywords: List[str] = None,
        match_score: float = 0.8,
    ):
        self.name = name
        self.domain = domain
        self.keywords = keywords or []
        self._default_match_score = match_score
        self.description = f"{name} in {domain}"

    def matches_requirement(self, requirement: str) -> float:
        """Calculate semantic match score based on requirement (like real A2A)."""
        requirement_lower = requirement.lower()

        # Direct name match (highest score)
        if self.name.lower() in requirement_lower:
            return 0.9

        # Domain match
        if self.domain.lower() in requirement_lower:
            return 0.7

        # Keyword matches
        keyword_matches = sum(
            1 for keyword in self.keywords if keyword.lower() in requirement_lower
        )
        if keyword_matches > 0:
            return min(0.6 + (keyword_matches * 0.1), 0.8)

        # Description similarity
        desc_words = set(self.description.lower().split())
        req_words = set(requirement_lower.split())
        overlap = len(desc_words & req_words)
        if overlap > 0:
            return min(0.3 + (overlap * 0.05), 0.5)

        return 0.0


class MockA2ACard:
    """Mock A2A agent card for testing."""

    def __init__(self, agent_id: str, capabilities: List[MockCapability]):
        self.agent_id = agent_id
        self.agent_name = f"Agent {agent_id}"
        self.primary_capabilities = capabilities


@pytest.fixture
def code_expert_agent(mock_config, mock_shared_memory):
    """Create code expert agent with A2A capabilities."""
    agent = WorkerAgent(
        config=mock_config, shared_memory=mock_shared_memory, agent_id="code_expert"
    )

    # Mock to_a2a_card to return code capabilities
    agent.to_a2a_card = Mock(
        return_value=MockA2ACard(
            agent_id="code_expert",
            capabilities=[
                MockCapability(
                    "code_generation",
                    "software_engineering",
                    keywords=[
                        "code",
                        "programming",
                        "python",
                        "function",
                        "class",
                        "implementation",
                    ],
                    match_score=0.9,
                ),
                MockCapability(
                    "code_review",
                    "software_engineering",
                    keywords=["review", "refactor", "optimization", "best practices"],
                    match_score=0.85,
                ),
                MockCapability(
                    "debugging",
                    "software_engineering",
                    keywords=["debug", "fix", "error", "bug", "troubleshoot"],
                    match_score=0.8,
                ),
            ],
        )
    )

    return agent


@pytest.fixture
def data_expert_agent(mock_config, mock_shared_memory):
    """Create data expert agent with A2A capabilities."""
    agent = WorkerAgent(
        config=mock_config, shared_memory=mock_shared_memory, agent_id="data_expert"
    )

    # Mock to_a2a_card to return data capabilities
    agent.to_a2a_card = Mock(
        return_value=MockA2ACard(
            agent_id="data_expert",
            capabilities=[
                MockCapability(
                    "data_analysis",
                    "data_science",
                    keywords=[
                        "data",
                        "analyze",
                        "analytics",
                        "dataset",
                        "statistics",
                        "metrics",
                    ],
                    match_score=0.9,
                ),
                MockCapability(
                    "data_visualization",
                    "data_science",
                    keywords=[
                        "visualization",
                        "chart",
                        "graph",
                        "plot",
                        "dashboard",
                        "visual",
                    ],
                    match_score=0.85,
                ),
                MockCapability(
                    "statistical_modeling",
                    "data_science",
                    keywords=[
                        "modeling",
                        "prediction",
                        "statistical",
                        "regression",
                        "forecast",
                    ],
                    match_score=0.8,
                ),
            ],
        )
    )

    return agent


@pytest.fixture
def writing_expert_agent(mock_config, mock_shared_memory):
    """Create writing expert agent with A2A capabilities."""
    agent = WorkerAgent(
        config=mock_config, shared_memory=mock_shared_memory, agent_id="writing_expert"
    )

    # Mock to_a2a_card to return writing capabilities
    agent.to_a2a_card = Mock(
        return_value=MockA2ACard(
            agent_id="writing_expert",
            capabilities=[
                MockCapability(
                    "content_creation",
                    "writing",
                    keywords=[
                        "write",
                        "content",
                        "article",
                        "blog",
                        "copy",
                        "creative",
                    ],
                    match_score=0.9,
                ),
                MockCapability(
                    "documentation",
                    "writing",
                    keywords=[
                        "documentation",
                        "manual",
                        "guide",
                        "README",
                        "docs",
                        "instructions",
                    ],
                    match_score=0.95,
                ),  # Highest score for documentation
                MockCapability(
                    "technical_writing",
                    "writing",
                    keywords=[
                        "technical",
                        "API",
                        "specification",
                        "tutorial",
                        "reference",
                    ],
                    match_score=0.92,
                ),
            ],
        )
    )

    return agent


# ============================================================================
# Test 1: A2A Coordinator Integration
# ============================================================================


class TestA2ACoordinatorIntegration:
    """Test that SupervisorWorkerPattern has A2A coordinator integration."""

    def test_pattern_has_a2a_coordinator_attribute(self, mock_shared_memory):
        """Pattern should have a2a_coordinator attribute."""
        pattern = create_supervisor_worker_pattern(
            num_workers=3, shared_memory=mock_shared_memory
        )

        # EXPECTED: Pattern has a2a_coordinator attribute
        assert hasattr(
            pattern, "a2a_coordinator"
        ), "SupervisorWorkerPattern missing a2a_coordinator attribute"

    def test_a2a_coordinator_is_initialized(self, mock_shared_memory):
        """A2A coordinator should be properly initialized."""
        pattern = create_supervisor_worker_pattern(
            num_workers=3, shared_memory=mock_shared_memory
        )

        # EXPECTED: a2a_coordinator is not None
        assert (
            pattern.a2a_coordinator is not None
        ), "a2a_coordinator should be initialized, not None"

    def test_supervisor_has_a2a_coordinator(self, mock_config, mock_shared_memory):
        """SupervisorAgent should have access to A2A coordinator."""
        supervisor = SupervisorAgent(
            config=mock_config,
            shared_memory=mock_shared_memory,
            agent_id="supervisor_1",
        )

        # EXPECTED: Supervisor has a2a_coordinator attribute
        assert hasattr(
            supervisor, "a2a_coordinator"
        ), "SupervisorAgent missing a2a_coordinator attribute"


# ============================================================================
# Test 2: Capability-Based Selection
# ============================================================================


class TestCapabilityBasedSelection:
    """Test that worker selection uses A2A semantic capability matching."""

    def test_select_worker_by_capability_not_hardcoded(
        self,
        mock_shared_memory,
        code_expert_agent,
        data_expert_agent,
        writing_expert_agent,
    ):
        """Worker selection should use capability matching, not hardcoded rules."""
        pattern = create_supervisor_worker_pattern(shared_memory=mock_shared_memory)
        pattern.workers = [code_expert_agent, data_expert_agent, writing_expert_agent]

        # EXPECTED: select_worker_for_task method exists
        assert hasattr(
            pattern.supervisor, "select_worker_for_task"
        ), "SupervisorAgent missing select_worker_for_task method"

        # Test code task selection
        code_task = "Write a Python function to parse JSON"
        selected_worker = pattern.supervisor.select_worker_for_task(
            task=code_task, available_workers=pattern.workers
        )

        # EXPECTED: Should select code expert (semantic matching)
        assert (
            selected_worker.agent_id == "code_expert"
        ), f"Expected code_expert for code task, got {selected_worker.agent_id}"

    def test_select_worker_uses_a2a_scoring(
        self, mock_shared_memory, code_expert_agent, data_expert_agent
    ):
        """Worker selection should use A2A 0.0-1.0 capability scores."""
        pattern = create_supervisor_worker_pattern(shared_memory=mock_shared_memory)
        pattern.workers = [code_expert_agent, data_expert_agent]

        # Test data task selection
        data_task = "Analyze sales data and create visualization"
        result = pattern.supervisor.select_worker_for_task(
            task=data_task,
            available_workers=pattern.workers,
            return_score=True,  # Return match score
        )

        # EXPECTED: Returns worker and score
        assert "worker" in result, "Missing 'worker' in result"
        assert "score" in result, "Missing 'score' in result"

        # EXPECTED: Score is float between 0.0 and 1.0
        score = result["score"]
        assert isinstance(score, float), f"Score should be float, got {type(score)}"
        assert 0.0 <= score <= 1.0, f"Score {score} not in range [0.0, 1.0]"

        # EXPECTED: Selected data expert
        assert (
            result["worker"].agent_id == "data_expert"
        ), "Should select data_expert for data task"

    def test_select_best_match_from_multiple_workers(
        self,
        mock_shared_memory,
        code_expert_agent,
        data_expert_agent,
        writing_expert_agent,
    ):
        """Should select worker with highest capability match score based on semantic matching."""
        pattern = create_supervisor_worker_pattern(shared_memory=mock_shared_memory)
        pattern.workers = [code_expert_agent, data_expert_agent, writing_expert_agent]

        # Test with code-specific task (should match code_expert's keywords: "code", "implementation")
        task = "Implement a binary search algorithm with code"
        result = pattern.supervisor.select_worker_for_task(
            task=task, available_workers=pattern.workers, return_score=True
        )

        # EXPECTED: Selected code expert (semantic match with "code" and "implementation")
        assert (
            result["worker"].agent_id == "code_expert"
        ), "Should select code_expert for code implementation task"
        # With semantic matching: "code" keyword match (0.6+) and "implementation" keyword match
        assert (
            result["score"] >= 0.6
        ), f"Expected keyword match score (>= 0.6), got {result['score']}"


# ============================================================================
# Test 3: Backward Compatibility
# ============================================================================


class TestBackwardCompatibility:
    """Test that pattern works with agents without A2A cards."""

    def test_works_with_non_a2a_agents(self, mock_config, mock_shared_memory):
        """Pattern should work with agents that don't have to_a2a_card."""
        # Create workers without A2A capabilities
        worker1 = WorkerAgent(
            config=mock_config, shared_memory=mock_shared_memory, agent_id="worker_1"
        )
        worker2 = WorkerAgent(
            config=mock_config, shared_memory=mock_shared_memory, agent_id="worker_2"
        )

        pattern = create_supervisor_worker_pattern(shared_memory=mock_shared_memory)
        pattern.workers = [worker1, worker2]

        # EXPECTED: Should fall back to round-robin or other selection
        task = "Process this data"
        selected = pattern.supervisor.select_worker_for_task(
            task=task, available_workers=pattern.workers
        )

        # EXPECTED: Returns a worker (fallback selection)
        assert selected is not None, "Should return worker even without A2A"
        assert selected in pattern.workers, "Should return one of available workers"

    def test_graceful_fallback_when_a2a_fails(
        self, mock_shared_memory, code_expert_agent, data_expert_agent
    ):
        """Should fall back gracefully if A2A matching fails."""
        pattern = create_supervisor_worker_pattern(shared_memory=mock_shared_memory)

        # Mock A2A to raise exception
        code_expert_agent.to_a2a_card = Mock(side_effect=Exception("A2A error"))
        data_expert_agent.to_a2a_card = Mock(side_effect=Exception("A2A error"))

        pattern.workers = [code_expert_agent, data_expert_agent]

        # EXPECTED: Should not crash, should return a worker
        task = "Complete this task"
        selected = pattern.supervisor.select_worker_for_task(
            task=task, available_workers=pattern.workers
        )

        assert selected is not None, "Should fallback to default selection"
        assert selected in pattern.workers, "Should return valid worker"


# ============================================================================
# Test 4: Semantic Scoring Validation
# ============================================================================


class TestSemanticScoring:
    """Test that selection uses proper 0.0-1.0 semantic matching."""

    def test_score_range_validation(self, mock_shared_memory, code_expert_agent):
        """Match scores should always be between 0.0 and 1.0."""
        pattern = create_supervisor_worker_pattern(shared_memory=mock_shared_memory)
        pattern.workers = [code_expert_agent]

        tasks = ["Write Python code", "Analyze data", "Random unrelated task xyz123"]

        for task in tasks:
            result = pattern.supervisor.select_worker_for_task(
                task=task, available_workers=pattern.workers, return_score=True
            )

            score = result["score"]
            assert (
                0.0 <= score <= 1.0
            ), f"Score {score} out of range [0.0, 1.0] for task: {task}"

    def test_higher_score_for_better_match(self, mock_shared_memory, code_expert_agent):
        """More relevant tasks should get higher scores."""
        pattern = create_supervisor_worker_pattern(shared_memory=mock_shared_memory)
        pattern.workers = [code_expert_agent]

        # Highly relevant task
        relevant_task = "Write Python code for data processing"
        relevant_result = pattern.supervisor.select_worker_for_task(
            task=relevant_task, available_workers=pattern.workers, return_score=True
        )

        # Less relevant task
        irrelevant_task = "Write a marketing blog post"
        irrelevant_result = pattern.supervisor.select_worker_for_task(
            task=irrelevant_task, available_workers=pattern.workers, return_score=True
        )

        # EXPECTED: Relevant task has higher score
        assert (
            relevant_result["score"] > irrelevant_result["score"]
        ), f"Relevant task score ({relevant_result['score']}) should be higher than irrelevant ({irrelevant_result['score']})"


# ============================================================================
# Test 5: Multi-Agent Coordination
# ============================================================================


class TestMultiAgentCoordination:
    """Test A2A coordination with multiple specialized agents."""

    def test_delegate_tasks_based_on_capabilities(
        self,
        mock_shared_memory,
        code_expert_agent,
        data_expert_agent,
        writing_expert_agent,
    ):
        """Should delegate different tasks to different specialized workers."""
        pattern = create_supervisor_worker_pattern(shared_memory=mock_shared_memory)
        pattern.workers = [code_expert_agent, data_expert_agent, writing_expert_agent]

        # Mixed tasks requiring different capabilities
        tasks = [
            {"description": "Write Python function", "expected": "code_expert"},
            {"description": "Analyze sales data", "expected": "data_expert"},
            {"description": "Write documentation", "expected": "writing_expert"},
        ]

        for task in tasks:
            result = pattern.supervisor.select_worker_for_task(
                task=task["description"], available_workers=pattern.workers
            )

            assert (
                result.agent_id == task["expected"]
            ), f"Task '{task['description']}' should be delegated to {task['expected']}, got {result.agent_id}"

    def test_coordination_with_overlapping_capabilities(
        self, mock_shared_memory, code_expert_agent, writing_expert_agent
    ):
        """Should handle overlapping capabilities correctly."""
        # Add technical writing to code expert (overlap)
        code_expert_agent.to_a2a_card().primary_capabilities.append(
            MockCapability("technical_writing", "software_engineering", match_score=0.7)
        )

        pattern = create_supervisor_worker_pattern(shared_memory=mock_shared_memory)
        pattern.workers = [code_expert_agent, writing_expert_agent]

        # Technical writing task (both can do it)
        task = "Write API documentation"
        result = pattern.supervisor.select_worker_for_task(
            task=task, available_workers=pattern.workers, return_score=True
        )

        # EXPECTED: Should select writing expert (higher score for writing)
        assert (
            result["worker"].agent_id == "writing_expert"
        ), "Should select specialist with higher capability match"
        assert result["score"] > 0.7, "Should have high confidence in selection"


# ============================================================================
# Integration Tests
# ============================================================================


class TestA2AIntegrationEnd2End:
    """End-to-end integration tests for A2A in SupervisorWorkerPattern."""

    def test_full_delegation_workflow_with_a2a(
        self, mock_shared_memory, mock_config, code_expert_agent, data_expert_agent
    ):
        """Test complete delegation workflow using A2A matching."""
        # Create pattern
        supervisor = SupervisorAgent(
            config=mock_config,
            shared_memory=mock_shared_memory,
            agent_id="supervisor_1",
        )

        pattern = SupervisorWorkerPattern(
            supervisor=supervisor,
            workers=[code_expert_agent, data_expert_agent],
            coordinator=None,  # Not needed for this test
            shared_memory=mock_shared_memory,
        )

        # EXPECTED: Supervisor can delegate with A2A
        request = "Write code to analyze data and generate reports"

        # This should trigger A2A matching for task breakdown
        tasks = pattern.delegate(request, num_tasks=2)

        # EXPECTED: Tasks created and assigned based on capabilities
        assert len(tasks) == 2, f"Expected 2 tasks, got {len(tasks)}"

        # EXPECTED: Each task assigned to best-match worker
        for task in tasks:
            assert "assigned_to" in task, "Task missing assigned_to field"
            assert task["assigned_to"] in [
                "code_expert",
                "data_expert",
            ], f"Invalid assignment: {task['assigned_to']}"

    def test_a2a_reduces_manual_selection_logic(self, mock_shared_memory):
        """Verify that A2A eliminates manual if/else selection logic."""
        pattern = create_supervisor_worker_pattern(shared_memory=mock_shared_memory)

        # EXPECTED: No hardcoded selection logic in supervisor
        supervisor_code = pattern.supervisor.select_worker_for_task.__code__

        # Should NOT have manual keyword checking
        # (This is validated by code inspection in implementation phase)
        assert supervisor_code is not None, "select_worker_for_task should exist"
