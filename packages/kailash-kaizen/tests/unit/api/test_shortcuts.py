"""
Unit Tests for String Shortcuts (Tier 1)

Tests the shortcut resolution for progressive configuration:
- Memory shortcuts
- Runtime shortcuts
- Tool access shortcuts
- Execution mode shortcuts
- Model aliases
"""

import pytest

from kaizen.api.shortcuts import (
    MEMORY_SHORTCUTS,
    MODEL_ALIASES,
    RUNTIME_SHORTCUTS,
    get_available_shortcuts,
    resolve_execution_mode,
    resolve_memory_shortcut,
    resolve_model_shortcut,
    resolve_runtime_shortcut,
    resolve_tool_access_shortcut,
)
from kaizen.api.types import ExecutionMode, MemoryDepth, ToolAccess


class TestMemoryShortcuts:
    """Tests for memory shortcut resolution."""

    def test_stateless_shortcut(self):
        """Test stateless memory shortcut."""
        memory = resolve_memory_shortcut("stateless")
        assert memory is not None

    def test_session_shortcut(self):
        """Test session memory shortcut."""
        memory = resolve_memory_shortcut("session")
        assert memory is not None

    def test_memory_depth_enum(self):
        """Test MemoryDepth enum resolution."""
        memory = resolve_memory_shortcut(MemoryDepth.SESSION)
        assert memory is not None

    def test_none_defaults_to_stateless(self):
        """Test None defaults to stateless."""
        memory = resolve_memory_shortcut(None)
        assert memory is not None

    def test_passthrough_instance(self):
        """Test passing existing instance."""

        class MockMemory:
            pass

        mock = MockMemory()
        memory = resolve_memory_shortcut(mock)
        assert memory is mock

    def test_invalid_shortcut_raises(self):
        """Test invalid shortcut raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            resolve_memory_shortcut("invalid_memory")

        assert "Unknown memory shortcut" in str(exc_info.value)
        assert "stateless" in str(exc_info.value)  # Suggestion

    def test_case_insensitive(self):
        """Test shortcuts are case-insensitive."""
        memory1 = resolve_memory_shortcut("SESSION")
        memory2 = resolve_memory_shortcut("Session")
        assert memory1 is not None
        assert memory2 is not None

    def test_all_shortcuts_registered(self):
        """Test all shortcuts are in registry."""
        assert "stateless" in MEMORY_SHORTCUTS
        assert "session" in MEMORY_SHORTCUTS
        assert "persistent" in MEMORY_SHORTCUTS
        assert "learning" in MEMORY_SHORTCUTS


class TestRuntimeShortcuts:
    """Tests for runtime shortcut resolution."""

    def test_local_shortcut(self):
        """Test local runtime shortcut."""
        runtime = resolve_runtime_shortcut("local")
        assert runtime is not None

    def test_kaizen_alias(self):
        """Test kaizen alias for local."""
        runtime = resolve_runtime_shortcut("kaizen")
        assert runtime is not None

    def test_none_defaults_to_local(self):
        """Test None defaults to local runtime."""
        runtime = resolve_runtime_shortcut(None)
        assert runtime is not None

    def test_passthrough_instance(self):
        """Test passing existing instance."""

        class MockRuntime:
            pass

        mock = MockRuntime()
        runtime = resolve_runtime_shortcut(mock)
        assert runtime is mock

    def test_invalid_shortcut_raises(self):
        """Test invalid shortcut raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            resolve_runtime_shortcut("invalid_runtime")

        assert "Unknown runtime shortcut" in str(exc_info.value)

    def test_claude_code_runtime_available(self):
        """Test claude_code runtime resolves correctly."""
        # ClaudeCodeAdapter is now implemented
        runtime = resolve_runtime_shortcut("claude_code")

        # Should return a valid runtime adapter
        assert runtime is not None
        # Verify it's the ClaudeCodeAdapter (or has expected methods)
        assert hasattr(runtime, "execute") or hasattr(runtime, "run")


class TestToolAccessShortcuts:
    """Tests for tool access shortcut resolution."""

    def test_none_shortcut(self):
        """Test none tool access shortcut."""
        policy = resolve_tool_access_shortcut("none")
        assert policy["enabled"] is False

    def test_read_only_shortcut(self):
        """Test read_only tool access shortcut."""
        policy = resolve_tool_access_shortcut("read_only")
        assert policy["enabled"] is True
        assert "read" in policy["allowed_tools"]
        assert "write" not in policy["allowed_tools"]

    def test_constrained_shortcut(self):
        """Test constrained tool access shortcut."""
        policy = resolve_tool_access_shortcut("constrained")
        assert policy["enabled"] is True
        assert "read" in policy["allowed_tools"]
        assert "write" in policy["allowed_tools"]
        assert policy["require_confirmation"] is True

    def test_full_shortcut(self):
        """Test full tool access shortcut."""
        policy = resolve_tool_access_shortcut("full")
        assert policy["enabled"] is True
        assert policy["allowed_tools"] is None  # All allowed
        assert policy["require_confirmation"] is False

    def test_tool_access_enum(self):
        """Test ToolAccess enum resolution."""
        policy = resolve_tool_access_shortcut(ToolAccess.READ_ONLY)
        assert policy["enabled"] is True

    def test_none_defaults(self):
        """Test None defaults to no access."""
        policy = resolve_tool_access_shortcut(None)
        assert policy["enabled"] is False

    def test_invalid_shortcut_raises(self):
        """Test invalid shortcut raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            resolve_tool_access_shortcut("invalid_access")

        assert "Unknown tool access level" in str(exc_info.value)


class TestExecutionModeShortcuts:
    """Tests for execution mode shortcut resolution."""

    def test_single_shortcut(self):
        """Test single mode shortcut."""
        mode = resolve_execution_mode("single")
        assert mode == ExecutionMode.SINGLE

    def test_multi_shortcut(self):
        """Test multi mode shortcut."""
        mode = resolve_execution_mode("multi")
        assert mode == ExecutionMode.MULTI

    def test_autonomous_shortcut(self):
        """Test autonomous mode shortcut."""
        mode = resolve_execution_mode("autonomous")
        assert mode == ExecutionMode.AUTONOMOUS

    def test_enum_passthrough(self):
        """Test enum passthrough."""
        mode = resolve_execution_mode(ExecutionMode.AUTONOMOUS)
        assert mode == ExecutionMode.AUTONOMOUS

    def test_none_defaults_to_single(self):
        """Test None defaults to single."""
        mode = resolve_execution_mode(None)
        assert mode == ExecutionMode.SINGLE

    def test_invalid_mode_raises(self):
        """Test invalid mode raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            resolve_execution_mode("invalid_mode")

        assert "Unknown execution mode" in str(exc_info.value)

    def test_case_insensitive(self):
        """Test shortcuts are case-insensitive."""
        mode1 = resolve_execution_mode("SINGLE")
        mode2 = resolve_execution_mode("Single")
        assert mode1 == ExecutionMode.SINGLE
        assert mode2 == ExecutionMode.SINGLE


class TestModelAliases:
    """Tests for model alias resolution."""

    def test_gpt4_alias(self):
        """Test gpt4 alias."""
        model = resolve_model_shortcut("gpt4")
        assert model == "gpt-4"

    def test_claude_alias(self):
        """Test claude alias."""
        model = resolve_model_shortcut("claude")
        assert model == "claude-3-sonnet"

    def test_sonnet_alias(self):
        """Test sonnet alias."""
        model = resolve_model_shortcut("sonnet")
        assert model == "claude-3-sonnet"

    def test_opus_alias(self):
        """Test opus alias."""
        model = resolve_model_shortcut("opus")
        assert model == "claude-3-opus"

    def test_gemini_alias(self):
        """Test gemini alias."""
        model = resolve_model_shortcut("gemini")
        assert model == "gemini-1.5-pro"

    def test_llama_alias(self):
        """Test llama alias."""
        model = resolve_model_shortcut("llama")
        assert model == "llama3.2"

    def test_passthrough_unknown(self):
        """Test unknown model passes through."""
        model = resolve_model_shortcut("custom-model-v2")
        assert model == "custom-model-v2"

    def test_exact_name_passthrough(self):
        """Test exact model name passes through."""
        model = resolve_model_shortcut("gpt-4")
        assert model == "gpt-4"

    def test_case_insensitive(self):
        """Test aliases are case-insensitive."""
        model1 = resolve_model_shortcut("GPT4")
        model2 = resolve_model_shortcut("Gpt4")
        assert model1 == "gpt-4"
        assert model2 == "gpt-4"


class TestGetAvailableShortcuts:
    """Tests for get_available_shortcuts function."""

    def test_returns_all_categories(self):
        """Test returns all shortcut categories."""
        shortcuts = get_available_shortcuts()

        assert "memory" in shortcuts
        assert "runtime" in shortcuts
        assert "tool_access" in shortcuts
        assert "execution_mode" in shortcuts
        assert "model_aliases" in shortcuts

    def test_memory_shortcuts_list(self):
        """Test memory shortcuts list."""
        shortcuts = get_available_shortcuts()
        memory = shortcuts["memory"]

        assert "stateless" in memory
        assert "session" in memory
        assert "persistent" in memory
        assert "learning" in memory

    def test_tool_access_shortcuts_list(self):
        """Test tool access shortcuts list."""
        shortcuts = get_available_shortcuts()
        access = shortcuts["tool_access"]

        assert "none" in access
        assert "read_only" in access
        assert "constrained" in access
        assert "full" in access

    def test_execution_mode_shortcuts_list(self):
        """Test execution mode shortcuts list."""
        shortcuts = get_available_shortcuts()
        modes = shortcuts["execution_mode"]

        assert "single" in modes
        assert "multi" in modes
        assert "autonomous" in modes

    def test_model_aliases_list(self):
        """Test model aliases list."""
        shortcuts = get_available_shortcuts()
        aliases = shortcuts["model_aliases"]

        assert "gpt4" in aliases
        assert "claude" in aliases
        assert "gemini" in aliases
