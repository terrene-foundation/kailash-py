"""
Unit Tests for AgentConfig (Tier 1)

Tests the expert configuration dataclass:
- AgentConfig creation
- Nested configs (CheckpointConfig, HookConfig, LLMRoutingConfig)
- Serialization
- Factory methods
"""

import pytest

from kaizen.api.config import (
    AgentConfig,
    CheckpointConfig,
    HookConfig,
    LLMRoutingConfig,
)
from kaizen.api.types import ExecutionMode, MemoryDepth, ToolAccess


class TestCheckpointConfig:
    """Tests for CheckpointConfig dataclass."""

    def test_create_default(self):
        """Test creating with defaults."""
        config = CheckpointConfig()

        assert config.enabled is True
        assert config.strategy == "periodic"
        assert config.interval_seconds == 60.0
        assert config.max_checkpoints == 10

    def test_create_custom(self):
        """Test creating with custom values."""
        config = CheckpointConfig(
            enabled=True,
            strategy="on_cycle",
            interval_cycles=5,
            storage_path="/tmp/checkpoints",
            compress=False,
        )

        assert config.strategy == "on_cycle"
        assert config.interval_cycles == 5
        assert config.storage_path == "/tmp/checkpoints"
        assert config.compress is False

    def test_to_dict(self):
        """Test to_dict method."""
        config = CheckpointConfig(strategy="manual", max_checkpoints=20)

        data = config.to_dict()

        assert data["strategy"] == "manual"
        assert data["max_checkpoints"] == 20


class TestHookConfig:
    """Tests for HookConfig dataclass."""

    def test_create_default(self):
        """Test creating with defaults."""
        config = HookConfig()

        assert config.on_start is None
        assert config.on_cycle is None
        assert config.on_error is None
        assert config.on_complete is None

    def test_create_with_hooks(self):
        """Test creating with hook functions."""

        def my_hook(ctx):
            pass

        config = HookConfig(
            on_start=my_hook,
            on_error=my_hook,
            on_complete=my_hook,
        )

        assert config.on_start is not None
        assert config.on_error is not None
        assert config.on_complete is not None

    def test_get_hooks(self):
        """Test get_hooks method."""

        def hook1(ctx):
            pass

        def hook2(ctx):
            pass

        config = HookConfig(on_start=hook1, on_error=hook2)

        hooks = config.get_hooks()

        assert hooks["on_start"] is hook1
        assert hooks["on_error"] is hook2
        assert hooks["on_cycle"] is None


class TestLLMRoutingConfig:
    """Tests for LLMRoutingConfig dataclass."""

    def test_create_default(self):
        """Test creating with defaults."""
        config = LLMRoutingConfig()

        assert config.enabled is False
        assert config.strategy == "balanced"
        assert config.task_model_mapping == {}
        assert config.fallback_chain == []

    def test_create_custom(self):
        """Test creating with custom values."""
        config = LLMRoutingConfig(
            enabled=True,
            strategy="cost_optimized",
            task_model_mapping={
                "simple": "gpt-3.5-turbo",
                "complex": "gpt-4",
            },
            fallback_chain=["gpt-4", "claude-3-opus"],
            max_retries=5,
        )

        assert config.enabled is True
        assert config.strategy == "cost_optimized"
        assert config.task_model_mapping["simple"] == "gpt-3.5-turbo"
        assert len(config.fallback_chain) == 2

    def test_to_dict(self):
        """Test to_dict method."""
        config = LLMRoutingConfig(
            enabled=True,
            task_model_mapping={"code": "codellama"},
        )

        data = config.to_dict()

        assert data["enabled"] is True
        assert data["task_model_mapping"]["code"] == "codellama"


class TestAgentConfigCreation:
    """Tests for AgentConfig creation."""

    def test_create_default(self):
        """Test creating with defaults."""
        config = AgentConfig()

        assert config.model == "gpt-4"
        assert config.execution_mode == ExecutionMode.SINGLE
        assert config.max_cycles == 100
        assert config.max_turns == 50
        assert config.tool_access == ToolAccess.NONE
        assert config.temperature == 0.7

    def test_create_full(self):
        """Test creating with all parameters."""
        config = AgentConfig(
            model="claude-3-opus",
            provider="anthropic",
            execution_mode=ExecutionMode.AUTONOMOUS,
            max_cycles=200,
            max_turns=100,
            max_tool_calls=500,
            timeout_seconds=600.0,
            memory="persistent",
            memory_path="/data/memory",
            tool_access=ToolAccess.CONSTRAINED,
            tools=[],
            allowed_tools=["read", "write"],
            temperature=0.5,
            system_prompt="You are a helpful assistant",
            name="MyAgent",
            description="Test agent",
            tags=["test", "dev"],
            metadata={"version": "1.0"},
        )

        assert config.model == "claude-3-opus"
        assert config.provider == "anthropic"
        assert config.execution_mode == ExecutionMode.AUTONOMOUS
        assert config.max_cycles == 200
        assert config.memory == "persistent"
        assert config.tool_access == ToolAccess.CONSTRAINED


class TestAgentConfigGetCapabilities:
    """Tests for get_capabilities method."""

    def test_get_capabilities(self):
        """Test get_capabilities method."""
        config = AgentConfig(
            execution_mode=ExecutionMode.AUTONOMOUS,
            max_cycles=75,
            max_turns=40,
            tool_access=ToolAccess.CONSTRAINED,
            allowed_tools=["read", "write"],
            timeout_seconds=450.0,
        )

        caps = config.get_capabilities()

        assert caps.execution_modes == [ExecutionMode.AUTONOMOUS]
        assert caps.tool_access == ToolAccess.CONSTRAINED
        assert caps.max_cycles == 75
        assert caps.max_turns == 40
        assert caps.allowed_tools == ["read", "write"]


class TestAgentConfigSerialization:
    """Tests for serialization."""

    def test_to_dict(self):
        """Test to_dict method."""
        config = AgentConfig(
            model="gpt-4",
            execution_mode=ExecutionMode.MULTI,
            max_turns=75,
            tool_access=ToolAccess.READ_ONLY,
            temperature=0.5,
        )

        data = config.to_dict()

        assert data["model"] == "gpt-4"
        assert data["execution_mode"] == "multi"
        assert data["max_turns"] == 75
        assert data["tool_access"] == "read_only"
        assert data["temperature"] == 0.5

    def test_from_dict(self):
        """Test from_dict method."""
        data = {
            "model": "claude-3-opus",
            "execution_mode": "autonomous",
            "max_cycles": 150,
            "tool_access": "constrained",
        }

        config = AgentConfig.from_dict(data)

        assert config.model == "claude-3-opus"
        assert config.execution_mode == ExecutionMode.AUTONOMOUS
        assert config.max_cycles == 150
        assert config.tool_access == ToolAccess.CONSTRAINED

    def test_roundtrip(self):
        """Test roundtrip serialization."""
        original = AgentConfig(
            model="gpt-4",
            execution_mode=ExecutionMode.AUTONOMOUS,
            max_cycles=100,
            tool_access=ToolAccess.FULL,
            allowed_tools=["read", "write", "bash"],
            temperature=0.3,
        )

        data = original.to_dict()
        restored = AgentConfig.from_dict(data)

        assert restored.model == original.model
        assert restored.execution_mode == original.execution_mode
        assert restored.max_cycles == original.max_cycles
        assert restored.tool_access == original.tool_access


class TestAgentConfigFromPreset:
    """Tests for from_preset class method."""

    def test_from_preset_developer(self):
        """Test from_preset with developer preset."""
        config = AgentConfig.from_preset("developer")

        assert config.execution_mode == ExecutionMode.AUTONOMOUS
        assert config.tool_access == ToolAccess.CONSTRAINED
        assert config.max_cycles == 100

    def test_from_preset_with_overrides(self):
        """Test from_preset with overrides."""
        config = AgentConfig.from_preset("developer", max_cycles=200)

        assert config.max_cycles == 200

    def test_from_preset_qa_assistant(self):
        """Test from_preset with qa_assistant preset."""
        config = AgentConfig.from_preset("qa_assistant")

        assert config.execution_mode == ExecutionMode.SINGLE
        assert config.tool_access == ToolAccess.NONE


class TestAgentConfigMergeWith:
    """Tests for merge_with method."""

    def test_merge_basic(self):
        """Test basic merge."""
        config = AgentConfig(model="gpt-4", max_cycles=50)

        merged = config.merge_with(max_cycles=100, temperature=0.5)

        assert merged.model == "gpt-4"  # Preserved
        assert merged.max_cycles == 100  # Overridden
        assert merged.temperature == 0.5  # Added

    def test_merge_preserves_original(self):
        """Test merge doesn't modify original."""
        config = AgentConfig(model="gpt-4", max_cycles=50)

        merged = config.merge_with(max_cycles=100)

        assert config.max_cycles == 50  # Original unchanged
        assert merged.max_cycles == 100  # Merged has new value


class TestAgentConfigString:
    """Tests for string representation."""

    def test_str(self):
        """Test __str__ method."""
        config = AgentConfig(
            model="claude-3-opus",
            execution_mode=ExecutionMode.AUTONOMOUS,
            tool_access=ToolAccess.CONSTRAINED,
        )

        s = str(config)

        assert "claude-3-opus" in s
        assert "autonomous" in s
        assert "constrained" in s
