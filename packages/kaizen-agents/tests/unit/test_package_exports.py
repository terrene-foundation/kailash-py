"""Test that pattern classes are properly exported from top-level."""

import pytest


class TestPatternExports:
    """Verify all pattern classes are importable from kaizen_agents."""

    def test_supervisor_worker_pattern(self) -> None:
        from kaizen_agents import SupervisorWorkerPattern

        assert SupervisorWorkerPattern is not None

    def test_consensus_pattern(self) -> None:
        from kaizen_agents import ConsensusPattern

        assert ConsensusPattern is not None

    def test_debate_pattern(self) -> None:
        from kaizen_agents import DebatePattern

        assert DebatePattern is not None

    def test_handoff_pattern(self) -> None:
        from kaizen_agents import HandoffPattern

        assert HandoffPattern is not None

    def test_sequential_pipeline_pattern(self) -> None:
        from kaizen_agents import SequentialPipelinePattern

        assert SequentialPipelinePattern is not None

    def test_base_multi_agent_pattern(self) -> None:
        from kaizen_agents import BaseMultiAgentPattern

        assert BaseMultiAgentPattern is not None

    def test_factory_functions(self) -> None:
        from kaizen_agents import (
            create_consensus_pattern,
            create_debate_pattern,
            create_handoff_pattern,
            create_sequential_pipeline,
            create_supervisor_worker_pattern,
        )

        assert create_supervisor_worker_pattern is not None
        assert create_consensus_pattern is not None
        assert create_debate_pattern is not None
        assert create_handoff_pattern is not None
        assert create_sequential_pipeline is not None

    def test_patterns_also_in_patterns_module(self) -> None:
        from kaizen_agents.patterns import SupervisorWorkerPattern

        assert SupervisorWorkerPattern is not None

    def test_patterns_also_in_patterns_patterns_module(self) -> None:
        from kaizen_agents.patterns.patterns import SupervisorWorkerPattern

        assert SupervisorWorkerPattern is not None

    def test_deprecated_coordination_removed(self) -> None:
        """Verify the deprecated coordination module is removed."""
        with pytest.raises(ImportError):
            from kaizen_agents.agents.coordination import SupervisorWorkerPattern  # noqa: F401
