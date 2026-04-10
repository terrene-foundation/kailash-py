"""
SPEC-10: Multi-Agent Patterns Migration Tests

Tests for:
- TASK-10-01: BaseMultiAgentPattern updates (shared_memory defaults, get_agent_names)
- TASK-10-40: 11 deprecated subclasses emit DeprecationWarning
- TASK-10-50: max_total_delegations cap on SupervisorAgent (S10.1)
- Pattern containers accept plain BaseAgent instances
- Factory functions remain backward-compatible
- All exports importable
"""

import warnings

import pytest

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.memory.shared_memory import SharedMemoryPool

# ============================================================================
# Helpers
# ============================================================================


def _mock_config(**overrides) -> BaseAgentConfig:
    """Create a BaseAgentConfig with mock provider for unit tests."""
    defaults = {
        "llm_provider": "mock",
        "model": "mock-model",
        "temperature": 0.7,
        "max_tokens": 100,
    }
    defaults.update(overrides)
    return BaseAgentConfig(**defaults)


# ============================================================================
# TASK-10-01: BaseMultiAgentPattern updates
# ============================================================================


class TestBaseMultiAgentPatternUpdates:
    """Test BaseMultiAgentPattern base class updates."""

    def test_shared_memory_defaults_to_new_pool(self):
        """shared_memory field auto-creates a SharedMemoryPool when omitted."""
        from kaizen_agents.patterns.patterns import create_supervisor_worker_pattern

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            pattern = create_supervisor_worker_pattern()

        # The factory creates shared_memory; verify it's a SharedMemoryPool
        assert isinstance(pattern.shared_memory, SharedMemoryPool)

    def test_get_agent_names_returns_names(self):
        """get_agent_names returns names for all agents in pattern."""
        from kaizen_agents.patterns.patterns import create_supervisor_worker_pattern

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            pattern = create_supervisor_worker_pattern(num_workers=2)

        names = pattern.get_agent_names()
        assert len(names) == 4  # supervisor + 2 workers + coordinator
        # Should include agent_id fallbacks
        assert "supervisor_1" in names
        assert "coordinator_1" in names

    def test_get_agent_names_empty_pattern(self):
        """get_agent_names handles patterns with no agents gracefully."""
        from kaizen_agents.patterns.patterns import SequentialPipelinePattern

        pipeline = SequentialPipelinePattern(shared_memory=SharedMemoryPool())
        names = pipeline.get_agent_names()
        assert names == []


# ============================================================================
# TASK-10-40: 11 deprecated subclasses emit DeprecationWarning
# ============================================================================


class TestDeprecatedSubclasses:
    """All 11 pattern-specific subclasses emit DeprecationWarning."""

    def _make_shared_memory(self):
        return SharedMemoryPool()

    def test_supervisor_agent_emits_warning(self):
        from kaizen_agents.patterns.patterns.supervisor_worker import SupervisorAgent

        sm = self._make_shared_memory()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = SupervisorAgent(
                config=_mock_config(), shared_memory=sm, agent_id="s1"
            )
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
            assert "SupervisorAgent" in str(dep_warnings[0].message)
            assert isinstance(agent, BaseAgent)

    def test_worker_agent_emits_warning(self):
        from kaizen_agents.patterns.patterns.supervisor_worker import WorkerAgent

        sm = self._make_shared_memory()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = WorkerAgent(config=_mock_config(), shared_memory=sm, agent_id="w1")
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
            assert "WorkerAgent" in str(dep_warnings[0].message)
            assert isinstance(agent, BaseAgent)

    def test_coordinator_agent_emits_warning(self):
        from kaizen_agents.patterns.patterns.supervisor_worker import CoordinatorAgent

        sm = self._make_shared_memory()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = CoordinatorAgent(
                config=_mock_config(), shared_memory=sm, agent_id="c1"
            )
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
            assert "CoordinatorAgent" in str(dep_warnings[0].message)
            assert isinstance(agent, BaseAgent)

    def test_pipeline_stage_agent_emits_warning(self):
        from kaizen_agents.patterns.patterns.sequential import PipelineStageAgent

        sm = self._make_shared_memory()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = PipelineStageAgent(
                config=_mock_config(),
                shared_memory=sm,
                agent_id="p1",
                stage_name="extract",
            )
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
            assert "PipelineStageAgent" in str(dep_warnings[0].message)
            assert isinstance(agent, BaseAgent)

    def test_proponent_agent_emits_warning(self):
        from kaizen_agents.patterns.patterns.debate import ProponentAgent

        sm = self._make_shared_memory()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = ProponentAgent(
                config=_mock_config(), shared_memory=sm, agent_id="pro1"
            )
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
            assert "ProponentAgent" in str(dep_warnings[0].message)
            assert isinstance(agent, BaseAgent)

    def test_opponent_agent_emits_warning(self):
        from kaizen_agents.patterns.patterns.debate import OpponentAgent

        sm = self._make_shared_memory()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = OpponentAgent(
                config=_mock_config(), shared_memory=sm, agent_id="opp1"
            )
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
            assert "OpponentAgent" in str(dep_warnings[0].message)
            assert isinstance(agent, BaseAgent)

    def test_judge_agent_emits_warning(self):
        from kaizen_agents.patterns.patterns.debate import JudgeAgent

        sm = self._make_shared_memory()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = JudgeAgent(
                config=_mock_config(), shared_memory=sm, agent_id="judge1"
            )
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
            assert "JudgeAgent" in str(dep_warnings[0].message)
            assert isinstance(agent, BaseAgent)

    def test_proposer_agent_emits_warning(self):
        from kaizen_agents.patterns.patterns.consensus import ProposerAgent

        sm = self._make_shared_memory()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = ProposerAgent(
                config=_mock_config(), shared_memory=sm, agent_id="prop1"
            )
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
            assert "ProposerAgent" in str(dep_warnings[0].message)
            assert isinstance(agent, BaseAgent)

    def test_voter_agent_emits_warning(self):
        from kaizen_agents.patterns.patterns.consensus import VoterAgent

        sm = self._make_shared_memory()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = VoterAgent(
                config=_mock_config(), shared_memory=sm, agent_id="voter1"
            )
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
            assert "VoterAgent" in str(dep_warnings[0].message)
            assert isinstance(agent, BaseAgent)

    def test_aggregator_agent_emits_warning(self):
        from kaizen_agents.patterns.patterns.consensus import AggregatorAgent

        sm = self._make_shared_memory()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = AggregatorAgent(
                config=_mock_config(), shared_memory=sm, agent_id="agg1"
            )
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
            assert "AggregatorAgent" in str(dep_warnings[0].message)
            assert isinstance(agent, BaseAgent)

    def test_handoff_agent_emits_warning(self):
        from kaizen_agents.patterns.patterns.handoff import HandoffAgent

        sm = self._make_shared_memory()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = HandoffAgent(
                config=_mock_config(), shared_memory=sm, agent_id="h1", tier_level=1
            )
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
            assert "HandoffAgent" in str(dep_warnings[0].message)
            assert isinstance(agent, BaseAgent)

    def test_all_11_are_still_isinstance_base_agent(self):
        """All deprecated subclasses are still valid BaseAgent instances."""
        from kaizen_agents.patterns.patterns.consensus import (
            AggregatorAgent,
            ProposerAgent,
            VoterAgent,
        )
        from kaizen_agents.patterns.patterns.debate import (
            JudgeAgent,
            OpponentAgent,
            ProponentAgent,
        )
        from kaizen_agents.patterns.patterns.handoff import HandoffAgent
        from kaizen_agents.patterns.patterns.sequential import PipelineStageAgent
        from kaizen_agents.patterns.patterns.supervisor_worker import (
            CoordinatorAgent,
            SupervisorAgent,
            WorkerAgent,
        )

        sm = self._make_shared_memory()
        cfg = _mock_config()

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)

            agents = [
                SupervisorAgent(config=cfg, shared_memory=sm, agent_id="s"),
                WorkerAgent(config=cfg, shared_memory=sm, agent_id="w"),
                CoordinatorAgent(config=cfg, shared_memory=sm, agent_id="c"),
                PipelineStageAgent(
                    config=cfg, shared_memory=sm, agent_id="p", stage_name="test"
                ),
                ProponentAgent(config=cfg, shared_memory=sm, agent_id="pro"),
                OpponentAgent(config=cfg, shared_memory=sm, agent_id="opp"),
                JudgeAgent(config=cfg, shared_memory=sm, agent_id="j"),
                ProposerAgent(config=cfg, shared_memory=sm, agent_id="pr"),
                VoterAgent(config=cfg, shared_memory=sm, agent_id="v"),
                AggregatorAgent(config=cfg, shared_memory=sm, agent_id="a"),
                HandoffAgent(config=cfg, shared_memory=sm, agent_id="h", tier_level=1),
            ]

        for agent in agents:
            assert isinstance(
                agent, BaseAgent
            ), f"{type(agent).__name__} is not a BaseAgent instance"


# ============================================================================
# TASK-10-50: Delegation cap (S10.1)
# ============================================================================


class TestDelegationCap:
    """max_total_delegations limits delegation depth."""

    def test_default_cap_is_20(self):
        from kaizen_agents.patterns.patterns.supervisor_worker import SupervisorAgent

        sm = SharedMemoryPool()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            agent = SupervisorAgent(
                config=_mock_config(), shared_memory=sm, agent_id="s1"
            )

        assert agent.max_total_delegations == 20

    def test_custom_cap(self):
        from kaizen_agents.patterns.patterns.supervisor_worker import SupervisorAgent

        sm = SharedMemoryPool()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            agent = SupervisorAgent(
                config=_mock_config(),
                shared_memory=sm,
                agent_id="s1",
                max_total_delegations=5,
            )

        assert agent.max_total_delegations == 5

    def test_raises_at_cap(self):
        from kaizen_agents.patterns.patterns.supervisor_worker import (
            DelegationCapExceeded,
            SupervisorAgent,
        )

        sm = SharedMemoryPool()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            agent = SupervisorAgent(
                config=_mock_config(),
                shared_memory=sm,
                agent_id="s1",
                max_total_delegations=2,
            )

        # First two delegations should work (they may fail on LLM call with
        # mock provider, but the cap check happens first)
        # We need to simulate by incrementing the counter directly
        agent._delegation_count = 2

        with pytest.raises(DelegationCapExceeded) as exc_info:
            agent.delegate("test request", num_tasks=1)

        assert exc_info.value.cap == 2
        assert exc_info.value.count == 3

    def test_delegation_cap_exceeded_is_runtime_error(self):
        from kaizen_agents.patterns.patterns.supervisor_worker import (
            DelegationCapExceeded,
        )

        err = DelegationCapExceeded(cap=10, count=11)
        assert isinstance(err, RuntimeError)
        assert "10" in str(err)
        assert "11" in str(err)


# ============================================================================
# Pattern containers accept plain BaseAgent
# ============================================================================


class TestPlainBaseAgentAcceptance:
    """Pattern containers accept plain BaseAgent instances."""

    def test_supervisor_worker_pattern_accepts_base_agent(self):
        from kaizen_agents.patterns.patterns import SupervisorWorkerPattern

        cfg = _mock_config()
        sm = SharedMemoryPool()

        from kaizen.signatures import InputField, OutputField, Signature

        class MySig(Signature):
            request: str = InputField(desc="Request")
            result: str = OutputField(desc="Result")

        supervisor = BaseAgent(
            config=cfg, signature=MySig(), shared_memory=sm, agent_id="supervisor_1"
        )
        worker = BaseAgent(
            config=cfg, signature=MySig(), shared_memory=sm, agent_id="worker_1"
        )
        coordinator = BaseAgent(
            config=cfg, signature=MySig(), shared_memory=sm, agent_id="coordinator_1"
        )

        pattern = SupervisorWorkerPattern(
            supervisor=supervisor,
            workers=[worker],
            coordinator=coordinator,
            shared_memory=sm,
        )

        assert pattern.supervisor is supervisor
        assert pattern.workers == [worker]
        assert pattern.coordinator is coordinator
        agents = pattern.get_agents()
        assert len(agents) == 3

    def test_sequential_pipeline_accepts_plain_base_agent(self):
        from kaizen_agents.patterns.patterns import SequentialPipelinePattern

        cfg = _mock_config()
        sm = SharedMemoryPool()

        from kaizen.signatures import InputField, OutputField, Signature

        class MySig(Signature):
            stage_input: str = InputField(desc="Input")
            stage_output: str = OutputField(desc="Output")

        agent1 = BaseAgent(
            config=cfg, signature=MySig(), shared_memory=sm, agent_id="stage_1"
        )
        agent2 = BaseAgent(
            config=cfg, signature=MySig(), shared_memory=sm, agent_id="stage_2"
        )

        pipeline = SequentialPipelinePattern(shared_memory=sm)
        pipeline.add_stage(agent1)
        pipeline.add_stage(agent2)

        assert len(pipeline.stages) == 2
        # Verify stage_name and stage_index were set
        assert agent1.stage_index == 0
        assert agent2.stage_index == 1
        assert agent1.stage_name == "stage_1"  # falls back to agent_id
        assert agent2.stage_name == "stage_2"

    def test_sequential_pipeline_get_agents(self):
        from kaizen_agents.patterns.patterns import SequentialPipelinePattern

        cfg = _mock_config()
        sm = SharedMemoryPool()

        from kaizen.signatures import InputField, OutputField, Signature

        class MySig(Signature):
            stage_input: str = InputField(desc="Input")
            stage_output: str = OutputField(desc="Output")

        agent1 = BaseAgent(
            config=cfg, signature=MySig(), shared_memory=sm, agent_id="s1"
        )

        pipeline = SequentialPipelinePattern(shared_memory=sm)
        pipeline.add_stage(agent1)

        agents = pipeline.get_agents()
        assert len(agents) == 1
        assert agents[0] is agent1


# ============================================================================
# TASK-10-41: All exports importable
# ============================================================================


class TestPatternExports:
    """All expected exports are importable from patterns package."""

    def test_all_exports_importable(self):
        from kaizen_agents.patterns.patterns import (
            BaseMultiAgentPattern,
            DelegationCapExceeded,
            SupervisorWorkerPattern,
            TaskDelegationSignature,
            TaskEvaluationSignature,
            TaskExecutionSignature,
        )

        # Verify they are not None
        assert BaseMultiAgentPattern is not None
        assert SupervisorWorkerPattern is not None
        assert DelegationCapExceeded is not None
        assert TaskDelegationSignature is not None
        assert TaskExecutionSignature is not None
        assert TaskEvaluationSignature is not None

    def test_top_level_kaizen_agents_exports(self):
        """Multi-agent patterns importable from kaizen_agents top-level."""
        from kaizen_agents import ConsensusPattern, SupervisorWorkerPattern

        assert SupervisorWorkerPattern is not None
        assert ConsensusPattern is not None


# ============================================================================
# Factory backward compatibility
# ============================================================================


class TestFactoryBackwardCompat:
    """Factory functions still produce working patterns."""

    def test_create_supervisor_worker_still_works(self):
        from kaizen_agents.patterns.patterns import create_supervisor_worker_pattern

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            pattern = create_supervisor_worker_pattern(num_workers=2)

        assert pattern is not None
        assert pattern.supervisor is not None
        assert len(pattern.workers) == 2
        assert pattern.coordinator is not None
        assert pattern.shared_memory is not None

    def test_create_sequential_pipeline_still_works(self):
        from kaizen_agents.patterns.patterns import create_sequential_pipeline

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            pipeline = create_sequential_pipeline()

        assert pipeline is not None
        assert isinstance(pipeline.shared_memory, SharedMemoryPool)

    def test_create_debate_pattern_still_works(self):
        from kaizen_agents.patterns.patterns import create_debate_pattern

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            pattern = create_debate_pattern()

        assert pattern is not None
        assert pattern.proponent is not None
        assert pattern.opponent is not None
        assert pattern.judge is not None

    def test_create_consensus_pattern_still_works(self):
        from kaizen_agents.patterns.patterns import create_consensus_pattern

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            pattern = create_consensus_pattern()

        assert pattern is not None
        assert pattern.proposer is not None
        assert len(pattern.voters) > 0
        assert pattern.aggregator is not None

    def test_create_handoff_pattern_still_works(self):
        from kaizen_agents.patterns.patterns import create_handoff_pattern

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            pattern = create_handoff_pattern()

        assert pattern is not None
        assert len(pattern.tiers) > 0

    def test_supervisor_worker_separate_configs(self):
        """Separate configs per agent type still work."""
        from kaizen_agents.patterns.patterns import create_supervisor_worker_pattern

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            pattern = create_supervisor_worker_pattern(
                num_workers=2,
                supervisor_config={"model": "gpt-4"},
                worker_config={"model": "gpt-3.5-turbo"},
            )

        assert pattern.supervisor.config.model == "gpt-4"
        for worker in pattern.workers:
            assert worker.config.model == "gpt-3.5-turbo"
