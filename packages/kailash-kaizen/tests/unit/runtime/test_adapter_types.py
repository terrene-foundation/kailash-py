"""
Unit Tests for LocalKaizenAdapter Types (Tier 1)

Tests AutonomousPhase, AutonomousConfig, and ExecutionState dataclasses.

Coverage:
- Enum values and iteration
- Config creation with defaults
- Config validation with helpful errors
- ExecutionState creation and state tracking
- Serialization (to_dict, from_dict)
- State transition logic
"""

import json
from datetime import datetime
from typing import Any, Dict

import pytest

from kaizen.runtime.adapters.types import (
    AutonomousConfig,
    AutonomousPhase,
    ExecutionState,
    PermissionMode,
    PlanningStrategy,
)


class TestAutonomousPhase:
    """Test AutonomousPhase enum."""

    def test_all_phases_exist(self):
        """Test all expected phases are defined."""
        assert AutonomousPhase.THINK.value == "think"
        assert AutonomousPhase.ACT.value == "act"
        assert AutonomousPhase.OBSERVE.value == "observe"
        assert AutonomousPhase.DECIDE.value == "decide"

    def test_phase_count(self):
        """Test expected number of phases."""
        phases = list(AutonomousPhase)
        assert len(phases) == 4

    def test_phase_from_string(self):
        """Test creating phase from string value."""
        assert AutonomousPhase("think") == AutonomousPhase.THINK
        assert AutonomousPhase("act") == AutonomousPhase.ACT

    def test_phase_invalid_string(self):
        """Test invalid string raises ValueError."""
        with pytest.raises(ValueError):
            AutonomousPhase("invalid")


class TestPlanningStrategy:
    """Test PlanningStrategy enum."""

    def test_all_strategies_exist(self):
        """Test all expected strategies are defined."""
        assert PlanningStrategy.REACT.value == "react"
        assert PlanningStrategy.PEV.value == "pev"
        assert PlanningStrategy.TREE_OF_THOUGHTS.value == "tree_of_thoughts"

    def test_strategy_count(self):
        """Test expected number of strategies."""
        strategies = list(PlanningStrategy)
        assert len(strategies) == 3


class TestPermissionMode:
    """Test PermissionMode enum."""

    def test_all_modes_exist(self):
        """Test all expected modes are defined."""
        assert PermissionMode.AUTO.value == "auto"
        assert PermissionMode.CONFIRM_ALL.value == "confirm_all"
        assert PermissionMode.CONFIRM_DANGEROUS.value == "confirm_dangerous"
        assert PermissionMode.DENY_ALL.value == "deny_all"

    def test_mode_count(self):
        """Test expected number of modes."""
        modes = list(PermissionMode)
        assert len(modes) == 4


class TestAutonomousConfigDefaults:
    """Test AutonomousConfig default values."""

    def test_create_minimal_config(self):
        """Test creating config with no arguments uses defaults."""
        config = AutonomousConfig()

        # LLM defaults
        assert config.llm_provider == "openai"
        assert config.model == "gpt-4o"
        assert config.temperature == 0.7

        # Execution limits
        assert config.max_cycles == 50
        assert config.budget_limit_usd is None
        assert config.timeout_seconds is None

        # Checkpointing
        assert config.checkpoint_frequency == 10
        assert config.checkpoint_on_interrupt is True
        assert config.resume_from_checkpoint is None

        # Memory
        assert config.enable_learning is False
        assert config.memory_backend is None

        # Planning
        assert config.planning_strategy == PlanningStrategy.REACT

        # Permissions
        assert config.permission_mode == PermissionMode.CONFIRM_DANGEROUS

    def test_create_full_config(self):
        """Test creating config with all fields specified."""
        config = AutonomousConfig(
            llm_provider="anthropic",
            model="claude-3-opus",
            temperature=0.5,
            max_cycles=100,
            budget_limit_usd=1.0,
            timeout_seconds=300.0,
            checkpoint_frequency=5,
            checkpoint_on_interrupt=False,
            resume_from_checkpoint="checkpoint-123",
            enable_learning=True,
            memory_backend="redis",
            planning_strategy=PlanningStrategy.PEV,
            permission_mode=PermissionMode.AUTO,
            tools=["read_file", "bash_tool"],
            metadata={"project": "test"},
        )

        assert config.llm_provider == "anthropic"
        assert config.model == "claude-3-opus"
        assert config.budget_limit_usd == 1.0
        assert config.planning_strategy == PlanningStrategy.PEV
        assert "read_file" in config.tools


class TestAutonomousConfigValidation:
    """Test AutonomousConfig validation."""

    def test_valid_temperature_range(self):
        """Test temperature accepts valid range."""
        config = AutonomousConfig(temperature=0.0)
        assert config.temperature == 0.0

        config = AutonomousConfig(temperature=1.0)
        assert config.temperature == 1.0

        config = AutonomousConfig(temperature=2.0)
        assert config.temperature == 2.0

    def test_invalid_temperature_raises(self):
        """Test invalid temperature raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            AutonomousConfig(temperature=-0.1)
        assert "temperature" in str(exc_info.value).lower()

        with pytest.raises(ValueError) as exc_info:
            AutonomousConfig(temperature=2.1)
        assert "temperature" in str(exc_info.value).lower()

    def test_valid_max_cycles(self):
        """Test max_cycles accepts valid values."""
        config = AutonomousConfig(max_cycles=1)
        assert config.max_cycles == 1

        config = AutonomousConfig(max_cycles=1000)
        assert config.max_cycles == 1000

    def test_invalid_max_cycles_raises(self):
        """Test invalid max_cycles raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            AutonomousConfig(max_cycles=0)
        assert "max_cycles" in str(exc_info.value).lower()

        with pytest.raises(ValueError) as exc_info:
            AutonomousConfig(max_cycles=-1)
        assert "max_cycles" in str(exc_info.value).lower()

    def test_valid_budget(self):
        """Test budget accepts valid values."""
        config = AutonomousConfig(budget_limit_usd=0.01)
        assert config.budget_limit_usd == 0.01

        config = AutonomousConfig(budget_limit_usd=None)
        assert config.budget_limit_usd is None

    def test_invalid_budget_raises(self):
        """Test invalid budget raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            AutonomousConfig(budget_limit_usd=0.0)
        assert "budget" in str(exc_info.value).lower()

        with pytest.raises(ValueError) as exc_info:
            AutonomousConfig(budget_limit_usd=-1.0)
        assert "budget" in str(exc_info.value).lower()

    def test_valid_timeout(self):
        """Test timeout accepts valid values."""
        config = AutonomousConfig(timeout_seconds=1.0)
        assert config.timeout_seconds == 1.0

        config = AutonomousConfig(timeout_seconds=None)
        assert config.timeout_seconds is None

    def test_invalid_timeout_raises(self):
        """Test invalid timeout raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            AutonomousConfig(timeout_seconds=0.0)
        assert "timeout" in str(exc_info.value).lower()

    def test_valid_checkpoint_frequency(self):
        """Test checkpoint_frequency accepts valid values."""
        config = AutonomousConfig(checkpoint_frequency=1)
        assert config.checkpoint_frequency == 1

    def test_invalid_checkpoint_frequency_raises(self):
        """Test invalid checkpoint_frequency raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            AutonomousConfig(checkpoint_frequency=0)
        assert "checkpoint" in str(exc_info.value).lower()


class TestAutonomousConfigSerialization:
    """Test AutonomousConfig serialization."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        config = AutonomousConfig(
            llm_provider="anthropic",
            model="claude-3",
            max_cycles=100,
            planning_strategy=PlanningStrategy.PEV,
        )

        data = config.to_dict()

        assert data["llm_provider"] == "anthropic"
        assert data["model"] == "claude-3"
        assert data["max_cycles"] == 100
        assert data["planning_strategy"] == "pev"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "llm_provider": "openai",
            "model": "gpt-4o",
            "max_cycles": 50,
            "planning_strategy": "react",
            "permission_mode": "auto",
        }

        config = AutonomousConfig.from_dict(data)

        assert config.llm_provider == "openai"
        assert config.model == "gpt-4o"
        assert config.max_cycles == 50
        assert config.planning_strategy == PlanningStrategy.REACT
        assert config.permission_mode == PermissionMode.AUTO

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        original = AutonomousConfig(
            llm_provider="anthropic",
            model="claude-3",
            temperature=0.5,
            max_cycles=75,
            budget_limit_usd=2.5,
            planning_strategy=PlanningStrategy.PEV,
            tools=["read_file", "bash_tool"],
        )

        data = original.to_dict()
        restored = AutonomousConfig.from_dict(data)

        assert restored.llm_provider == original.llm_provider
        assert restored.model == original.model
        assert restored.temperature == original.temperature
        assert restored.max_cycles == original.max_cycles
        assert restored.budget_limit_usd == original.budget_limit_usd
        assert restored.planning_strategy == original.planning_strategy
        assert restored.tools == original.tools

    def test_to_json(self):
        """Test JSON serialization."""
        config = AutonomousConfig(model="gpt-4o")

        json_str = json.dumps(config.to_dict())
        restored_data = json.loads(json_str)

        assert restored_data["model"] == "gpt-4o"


class TestExecutionStateCreation:
    """Test ExecutionState creation and initialization."""

    def test_create_minimal_state(self):
        """Test creating state with minimal fields."""
        state = ExecutionState(task="Test task")

        assert state.task == "Test task"
        assert state.session_id != ""  # Auto-generated
        assert state.current_cycle == 0
        assert state.phase == AutonomousPhase.THINK
        assert state.messages == []
        assert state.status == "running"

    def test_create_full_state(self):
        """Test creating state with all fields."""
        state = ExecutionState(
            task="Full test task",
            session_id="session-123",
            current_cycle=5,
            phase=AutonomousPhase.ACT,
            messages=[{"role": "user", "content": "hello"}],
            plan=["step1", "step2"],
            plan_index=0,
            pending_tool_calls=[{"name": "read_file"}],
            tool_results=[{"tool": "bash", "result": "ok"}],
            working_memory={"context": "data"},
            learned_patterns=["pattern1"],
            tokens_used=1000,
            cost_usd=0.05,
            status="running",
            result=None,
            error=None,
        )

        assert state.task == "Full test task"
        assert state.session_id == "session-123"
        assert state.current_cycle == 5
        assert state.phase == AutonomousPhase.ACT
        assert len(state.messages) == 1
        assert state.tokens_used == 1000
        assert state.cost_usd == 0.05


class TestExecutionStateProperties:
    """Test ExecutionState computed properties."""

    def test_is_complete_false_running(self):
        """Test is_complete returns False when running."""
        state = ExecutionState(task="Test", status="running")
        assert state.is_complete is False

    def test_is_complete_true_completed(self):
        """Test is_complete returns True when completed."""
        state = ExecutionState(task="Test", status="completed")
        assert state.is_complete is True

    def test_is_complete_true_error(self):
        """Test is_complete returns True on error."""
        state = ExecutionState(task="Test", status="error")
        assert state.is_complete is True

    def test_is_complete_true_interrupted(self):
        """Test is_complete returns True when interrupted."""
        state = ExecutionState(task="Test", status="interrupted")
        assert state.is_complete is True

    def test_is_success_property(self):
        """Test is_success property."""
        state = ExecutionState(task="Test", status="completed")
        assert state.is_success is True

        state = ExecutionState(task="Test", status="error")
        assert state.is_success is False

    def test_is_error_property(self):
        """Test is_error property."""
        state = ExecutionState(task="Test", status="error")
        assert state.is_error is True

        state = ExecutionState(task="Test", status="completed")
        assert state.is_error is False


class TestExecutionStateMethods:
    """Test ExecutionState methods."""

    def test_advance_cycle(self):
        """Test advancing cycle counter."""
        state = ExecutionState(task="Test")
        assert state.current_cycle == 0

        state.advance_cycle()
        assert state.current_cycle == 1

        state.advance_cycle()
        assert state.current_cycle == 2

    def test_set_phase(self):
        """Test setting execution phase."""
        state = ExecutionState(task="Test")
        assert state.phase == AutonomousPhase.THINK

        state.set_phase(AutonomousPhase.ACT)
        assert state.phase == AutonomousPhase.ACT

        state.set_phase(AutonomousPhase.OBSERVE)
        assert state.phase == AutonomousPhase.OBSERVE

    def test_add_message(self):
        """Test adding messages to history."""
        state = ExecutionState(task="Test")
        assert len(state.messages) == 0

        state.add_message({"role": "user", "content": "hello"})
        assert len(state.messages) == 1
        assert state.messages[0]["role"] == "user"

        state.add_message({"role": "assistant", "content": "hi"})
        assert len(state.messages) == 2

    def test_add_tool_call(self):
        """Test adding pending tool calls."""
        state = ExecutionState(task="Test")
        assert len(state.pending_tool_calls) == 0

        state.add_tool_call({"name": "read_file", "args": {"path": "/tmp"}})
        assert len(state.pending_tool_calls) == 1

    def test_add_tool_result(self):
        """Test adding tool results."""
        state = ExecutionState(task="Test")
        assert len(state.tool_results) == 0

        state.add_tool_result({"tool": "read_file", "output": "content"})
        assert len(state.tool_results) == 1

    def test_clear_pending_tool_calls(self):
        """Test clearing pending tool calls."""
        state = ExecutionState(task="Test")
        state.add_tool_call({"name": "tool1"})
        state.add_tool_call({"name": "tool2"})
        assert len(state.pending_tool_calls) == 2

        state.clear_pending_tool_calls()
        assert len(state.pending_tool_calls) == 0

    def test_update_budget(self):
        """Test updating token and cost tracking."""
        state = ExecutionState(task="Test")
        assert state.tokens_used == 0
        assert state.cost_usd == 0.0

        state.update_budget(tokens=100, cost=0.01)
        assert state.tokens_used == 100
        assert state.cost_usd == 0.01

        state.update_budget(tokens=200, cost=0.02)
        assert state.tokens_used == 300
        assert state.cost_usd == pytest.approx(0.03)

    def test_complete_success(self):
        """Test marking as completed successfully."""
        state = ExecutionState(task="Test")

        state.complete(result="Task done")

        assert state.status == "completed"
        assert state.result == "Task done"
        assert state.is_complete is True
        assert state.is_success is True

    def test_complete_error(self):
        """Test marking as error."""
        state = ExecutionState(task="Test")

        state.fail(error="Something went wrong")

        assert state.status == "error"
        assert state.error == "Something went wrong"
        assert state.is_complete is True
        assert state.is_error is True

    def test_interrupt(self):
        """Test marking as interrupted."""
        state = ExecutionState(task="Test")

        state.interrupt()

        assert state.status == "interrupted"
        assert state.is_complete is True


class TestExecutionStateSerialization:
    """Test ExecutionState serialization."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        state = ExecutionState(
            task="Serialize test",
            session_id="sess-123",
            current_cycle=3,
            phase=AutonomousPhase.OBSERVE,
            messages=[{"role": "user", "content": "hi"}],
            tokens_used=500,
            cost_usd=0.025,
            status="running",
        )

        data = state.to_dict()

        assert data["task"] == "Serialize test"
        assert data["session_id"] == "sess-123"
        assert data["current_cycle"] == 3
        assert data["phase"] == "observe"
        assert len(data["messages"]) == 1
        assert data["tokens_used"] == 500
        assert data["cost_usd"] == 0.025
        assert data["status"] == "running"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "task": "Deserialize test",
            "session_id": "sess-456",
            "current_cycle": 7,
            "phase": "decide",
            "messages": [{"role": "assistant", "content": "done"}],
            "plan": ["step1"],
            "plan_index": 0,
            "pending_tool_calls": [],
            "tool_results": [],
            "working_memory": {},
            "learned_patterns": [],
            "tokens_used": 1000,
            "cost_usd": 0.05,
            "status": "completed",
            "result": "Success",
            "error": None,
        }

        state = ExecutionState.from_dict(data)

        assert state.task == "Deserialize test"
        assert state.session_id == "sess-456"
        assert state.current_cycle == 7
        assert state.phase == AutonomousPhase.DECIDE
        assert state.status == "completed"
        assert state.result == "Success"

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        original = ExecutionState(
            task="Roundtrip test",
            session_id="sess-789",
            current_cycle=10,
            phase=AutonomousPhase.ACT,
            messages=[
                {"role": "user", "content": "do something"},
                {"role": "assistant", "content": "ok"},
            ],
            plan=["step1", "step2"],
            plan_index=1,
            pending_tool_calls=[{"name": "bash"}],
            tool_results=[{"tool": "read", "output": "data"}],
            working_memory={"key": "value"},
            learned_patterns=["pattern1"],
            tokens_used=2000,
            cost_usd=0.10,
            status="running",
        )

        data = original.to_dict()
        restored = ExecutionState.from_dict(data)

        assert restored.task == original.task
        assert restored.session_id == original.session_id
        assert restored.current_cycle == original.current_cycle
        assert restored.phase == original.phase
        assert restored.messages == original.messages
        assert restored.plan == original.plan
        assert restored.plan_index == original.plan_index
        assert restored.pending_tool_calls == original.pending_tool_calls
        assert restored.tool_results == original.tool_results
        assert restored.working_memory == original.working_memory
        assert restored.learned_patterns == original.learned_patterns
        assert restored.tokens_used == original.tokens_used
        assert restored.cost_usd == pytest.approx(original.cost_usd)
        assert restored.status == original.status

    def test_to_json(self):
        """Test JSON serialization."""
        state = ExecutionState(
            task="JSON test",
            messages=[{"role": "user", "content": "test"}],
        )

        json_str = json.dumps(state.to_dict())
        restored_data = json.loads(json_str)

        assert restored_data["task"] == "JSON test"
        assert len(restored_data["messages"]) == 1


class TestExecutionStateEdgeCases:
    """Test ExecutionState edge cases."""

    def test_session_id_auto_generated(self):
        """Test session_id is auto-generated if not provided."""
        state1 = ExecutionState(task="Test 1")
        state2 = ExecutionState(task="Test 2")

        assert state1.session_id != ""
        assert state2.session_id != ""
        assert state1.session_id != state2.session_id

    def test_empty_collections_default(self):
        """Test empty collections are properly initialized."""
        state = ExecutionState(task="Test")

        assert state.messages == []
        assert state.plan == []
        assert state.pending_tool_calls == []
        assert state.tool_results == []
        assert state.working_memory == {}
        assert state.learned_patterns == []

    def test_none_values_allowed(self):
        """Test None values are allowed for optional fields."""
        state = ExecutionState(
            task="Test",
            result=None,
            error=None,
        )

        assert state.result is None
        assert state.error is None
