"""
Unit Tests for Unified Agent Class (Tier 1)

Tests the main Agent class:
- Agent creation with progressive configuration
- Property access
- State management
- Mode switching
- Configuration validation
"""

import pytest

from kaizen.api.agent import Agent
from kaizen.api.config import AgentConfig
from kaizen.api.types import ExecutionMode, ToolAccess
from kaizen.api.validation import ConfigurationError


class TestAgentCreation:
    """Tests for Agent creation."""

    def test_create_minimal(self):
        """Test creating with minimal configuration."""
        agent = Agent(model="gpt-4")

        assert agent.model == "gpt-4"
        assert agent.execution_mode == ExecutionMode.SINGLE

    def test_create_with_execution_mode(self):
        """Test creating with execution mode."""
        agent = Agent(model="gpt-4", execution_mode="autonomous")

        assert agent.execution_mode == ExecutionMode.AUTONOMOUS

    def test_create_with_memory(self):
        """Test creating with memory configuration."""
        agent = Agent(model="gpt-4", memory="session")

        assert agent._memory is not None

    def test_create_with_tool_access(self):
        """Test creating with tool access."""
        agent = Agent(model="gpt-4", tool_access="read_only")

        assert agent._tool_access == ToolAccess.READ_ONLY

    def test_create_with_multiple_options(self):
        """Test creating with multiple options."""
        agent = Agent(
            model="gpt-4",
            execution_mode="autonomous",
            max_cycles=75,
            memory="session",
            tool_access="constrained",
            timeout_seconds=600.0,
            temperature=0.5,
        )

        assert agent.model == "gpt-4"
        assert agent.execution_mode == ExecutionMode.AUTONOMOUS
        assert agent._max_cycles == 75
        assert agent._tool_access == ToolAccess.CONSTRAINED
        assert agent._timeout_seconds == 600.0
        assert agent._temperature == 0.5


class TestAgentCreationFromConfig:
    """Tests for Agent creation from AgentConfig."""

    def test_create_from_config(self):
        """Test creating from AgentConfig."""
        config = AgentConfig(
            model="claude-3-opus",
            execution_mode=ExecutionMode.AUTONOMOUS,
            max_cycles=100,
            tool_access=ToolAccess.CONSTRAINED,
        )

        agent = Agent(config=config)

        assert agent.model == "claude-3-opus"
        assert agent.execution_mode == ExecutionMode.AUTONOMOUS
        assert agent._max_cycles == 100
        assert agent._tool_access == ToolAccess.CONSTRAINED

    def test_config_overrides_params(self):
        """Test config overrides other parameters."""
        config = AgentConfig(model="gpt-4", max_cycles=200)

        # These should be ignored when config is provided
        agent = Agent(
            model="claude-3-opus",  # Ignored
            max_cycles=50,  # Ignored
            config=config,
        )

        assert agent.model == "gpt-4"  # From config
        assert agent._max_cycles == 200  # From config


class TestAgentCreationValidation:
    """Tests for Agent creation validation."""

    def test_missing_model_raises(self):
        """Test missing model raises error."""
        with pytest.raises(ConfigurationError) as exc_info:
            Agent(model=None)

        assert "Model is required" in str(exc_info.value)

    def test_invalid_execution_mode_raises(self):
        """Test invalid execution mode raises error."""
        with pytest.raises(ConfigurationError) as exc_info:
            Agent(model="gpt-4", execution_mode="invalid_mode")

        assert "execution_mode" in str(exc_info.value).lower()

    def test_invalid_model_runtime_raises(self):
        """Test invalid model-runtime combination raises error."""
        with pytest.raises(ConfigurationError) as exc_info:
            Agent(model="gpt-4", runtime="claude_code")

        assert "not compatible" in str(exc_info.value)


class TestAgentProperties:
    """Tests for Agent properties."""

    def test_model_property(self):
        """Test model property."""
        agent = Agent(model="gpt-4")
        assert agent.model == "gpt-4"

    def test_execution_mode_property(self):
        """Test execution_mode property."""
        agent = Agent(model="gpt-4", execution_mode="multi")
        assert agent.execution_mode == ExecutionMode.MULTI

    def test_capabilities_property(self):
        """Test capabilities property."""
        agent = Agent(
            model="gpt-4",
            execution_mode="autonomous",
            tool_access="constrained",
        )

        caps = agent.capabilities
        assert caps.can_execute(ExecutionMode.AUTONOMOUS)
        assert caps.tool_access == ToolAccess.CONSTRAINED

    def test_session_id_property(self):
        """Test session_id property."""
        agent = Agent(model="gpt-4")
        assert agent.session_id is not None
        assert len(agent.session_id) > 0

    def test_is_running_property(self):
        """Test is_running property."""
        agent = Agent(model="gpt-4")
        assert agent.is_running is False

    def test_is_paused_property(self):
        """Test is_paused property."""
        agent = Agent(model="gpt-4")
        assert agent.is_paused is False


class TestAgentStateManagement:
    """Tests for Agent state management."""

    def test_reset_creates_new_session(self):
        """Test reset creates new session."""
        agent = Agent(model="gpt-4")
        original_session = agent.session_id

        agent.reset()

        assert agent.session_id != original_session

    def test_pause_sets_flag(self):
        """Test pause sets flag."""
        agent = Agent(model="gpt-4", execution_mode="autonomous")
        agent.pause()
        assert agent.is_paused is True

    def test_resume_clears_flag(self):
        """Test resume clears flag."""
        agent = Agent(model="gpt-4", execution_mode="autonomous")
        agent.pause()
        agent.resume()
        assert agent.is_paused is False

    def test_stop_clears_flags(self):
        """Test stop clears all flags."""
        agent = Agent(model="gpt-4", execution_mode="autonomous")
        agent.pause()
        agent.stop()
        assert agent.is_paused is False
        assert agent.is_running is False


class TestAgentModeSwitch:
    """Tests for Agent mode switching."""

    def test_set_mode_string(self):
        """Test set_mode with string."""
        agent = Agent(model="gpt-4")
        agent.set_mode("autonomous")

        assert agent.execution_mode == ExecutionMode.AUTONOMOUS

    def test_set_mode_enum(self):
        """Test set_mode with enum."""
        agent = Agent(model="gpt-4")
        agent.set_mode(ExecutionMode.MULTI)

        assert agent.execution_mode == ExecutionMode.MULTI

    def test_set_mode_returns_self(self):
        """Test set_mode returns self for chaining."""
        agent = Agent(model="gpt-4")
        result = agent.set_mode("multi")

        assert result is agent


class TestAgentString:
    """Tests for Agent string representation."""

    def test_str(self):
        """Test __str__ method."""
        agent = Agent(
            model="gpt-4",
            execution_mode="autonomous",
            tool_access="constrained",
        )

        s = str(agent)

        assert "gpt-4" in s
        assert "autonomous" in s
        assert "constrained" in s

    def test_repr(self):
        """Test __repr__ method."""
        agent = Agent(model="claude-3-opus")

        r = repr(agent)

        assert "claude-3-opus" in r


class TestAgentModelAliases:
    """Tests for model alias resolution."""

    def test_gpt4_alias(self):
        """Test gpt4 alias resolved."""
        agent = Agent(model="gpt4")
        assert agent.model == "gpt-4"

    def test_claude_alias(self):
        """Test claude alias resolved."""
        agent = Agent(model="sonnet")
        assert agent.model == "claude-3-sonnet"


class TestAgentRuntimeShortcuts:
    """Tests for runtime shortcut resolution."""

    def test_local_runtime_default(self):
        """Test local runtime is default."""
        agent = Agent(model="gpt-4")
        # Runtime is lazily initialized
        assert agent._runtime_spec == "local"

    def test_explicit_local_runtime(self):
        """Test explicit local runtime."""
        agent = Agent(model="gpt-4", runtime="local")
        assert agent._runtime_spec == "local"


class TestAgentCapabilityBuilding:
    """Tests for capability building."""

    def test_capabilities_reflect_config(self):
        """Test capabilities reflect configuration."""
        agent = Agent(
            model="gpt-4",
            execution_mode="autonomous",
            max_cycles=75,
            max_turns=40,
            tool_access="constrained",
            allowed_tools=["read", "write"],
            timeout_seconds=450.0,
        )

        caps = agent.capabilities

        assert caps.can_execute(ExecutionMode.AUTONOMOUS)
        assert caps.tool_access == ToolAccess.CONSTRAINED
        assert caps.max_cycles == 75
        assert caps.max_turns == 40
        assert caps.timeout_seconds == 450.0

    def test_capabilities_can_use_tool(self):
        """Test capabilities tool checking."""
        agent = Agent(
            model="gpt-4",
            tool_access="read_only",
        )

        caps = agent.capabilities

        assert caps.can_use_tool("read") is True
        assert caps.can_use_tool("write") is False
