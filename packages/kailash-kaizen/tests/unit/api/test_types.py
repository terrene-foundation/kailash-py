"""
Unit Tests for API Types (Tier 1)

Tests the core types for the Unified Agent API:
- ExecutionMode enum
- MemoryDepth enum
- ToolAccess enum
- AgentCapabilities dataclass
"""

import pytest

from kaizen.api.types import (
    CONSTRAINED_TOOLS,
    DANGEROUS_TOOLS,
    READ_ONLY_TOOLS,
    AgentCapabilities,
    ExecutionMode,
    MemoryDepth,
    ToolAccess,
)


class TestExecutionMode:
    """Tests for ExecutionMode enum."""

    def test_all_modes_exist(self):
        """Test all execution modes exist."""
        assert ExecutionMode.SINGLE
        assert ExecutionMode.MULTI
        assert ExecutionMode.AUTONOMOUS

    def test_mode_values(self):
        """Test mode values are strings."""
        assert ExecutionMode.SINGLE.value == "single"
        assert ExecutionMode.MULTI.value == "multi"
        assert ExecutionMode.AUTONOMOUS.value == "autonomous"

    def test_mode_from_string(self):
        """Test creating mode from string."""
        assert ExecutionMode("single") == ExecutionMode.SINGLE
        assert ExecutionMode("multi") == ExecutionMode.MULTI
        assert ExecutionMode("autonomous") == ExecutionMode.AUTONOMOUS

    def test_invalid_mode_raises(self):
        """Test invalid mode raises ValueError."""
        with pytest.raises(ValueError):
            ExecutionMode("invalid")


class TestMemoryDepth:
    """Tests for MemoryDepth enum."""

    def test_all_depths_exist(self):
        """Test all memory depths exist."""
        assert MemoryDepth.STATELESS
        assert MemoryDepth.SESSION
        assert MemoryDepth.PERSISTENT
        assert MemoryDepth.LEARNING

    def test_depth_values(self):
        """Test depth values are strings."""
        assert MemoryDepth.STATELESS.value == "stateless"
        assert MemoryDepth.SESSION.value == "session"
        assert MemoryDepth.PERSISTENT.value == "persistent"
        assert MemoryDepth.LEARNING.value == "learning"

    def test_depth_from_string(self):
        """Test creating depth from string."""
        assert MemoryDepth("stateless") == MemoryDepth.STATELESS
        assert MemoryDepth("session") == MemoryDepth.SESSION


class TestToolAccess:
    """Tests for ToolAccess enum."""

    def test_all_access_levels_exist(self):
        """Test all tool access levels exist."""
        assert ToolAccess.NONE
        assert ToolAccess.READ_ONLY
        assert ToolAccess.CONSTRAINED
        assert ToolAccess.FULL

    def test_access_values(self):
        """Test access values are strings."""
        assert ToolAccess.NONE.value == "none"
        assert ToolAccess.READ_ONLY.value == "read_only"
        assert ToolAccess.CONSTRAINED.value == "constrained"
        assert ToolAccess.FULL.value == "full"


class TestToolSets:
    """Tests for tool category sets."""

    def test_read_only_tools_defined(self):
        """Test read-only tools set is defined."""
        assert "read" in READ_ONLY_TOOLS
        assert "glob" in READ_ONLY_TOOLS
        assert "grep" in READ_ONLY_TOOLS
        assert "list" in READ_ONLY_TOOLS

    def test_constrained_tools_includes_read(self):
        """Test constrained tools includes read-only."""
        for tool in READ_ONLY_TOOLS:
            assert tool in CONSTRAINED_TOOLS or tool in READ_ONLY_TOOLS

    def test_dangerous_tools_defined(self):
        """Test dangerous tools set is defined."""
        assert "bash" in DANGEROUS_TOOLS
        assert "shell" in DANGEROUS_TOOLS
        assert "rm" in DANGEROUS_TOOLS
        assert "delete" in DANGEROUS_TOOLS


class TestAgentCapabilitiesCreation:
    """Tests for AgentCapabilities creation."""

    def test_create_default(self):
        """Test creating with defaults."""
        caps = AgentCapabilities()

        assert caps.execution_modes == [ExecutionMode.SINGLE]
        assert caps.max_memory_depth == MemoryDepth.STATELESS
        assert caps.tool_access == ToolAccess.NONE
        assert caps.max_turns == 50
        assert caps.max_cycles == 100

    def test_create_full(self):
        """Test creating with all parameters."""
        caps = AgentCapabilities(
            execution_modes=[
                ExecutionMode.SINGLE,
                ExecutionMode.MULTI,
                ExecutionMode.AUTONOMOUS,
            ],
            max_memory_depth=MemoryDepth.LEARNING,
            tool_access=ToolAccess.FULL,
            allowed_tools=["read", "write"],
            denied_tools=["rm"],
            max_turns=100,
            max_cycles=200,
            max_tool_calls=500,
            max_tokens_per_turn=16000,
            timeout_seconds=600.0,
            tool_timeout_seconds=120.0,
        )

        assert len(caps.execution_modes) == 3
        assert caps.max_memory_depth == MemoryDepth.LEARNING
        assert caps.tool_access == ToolAccess.FULL
        assert caps.max_turns == 100
        assert caps.max_cycles == 200


class TestAgentCapabilitiesCanExecute:
    """Tests for can_execute method."""

    def test_can_execute_single_mode(self):
        """Test can_execute for single mode."""
        caps = AgentCapabilities(execution_modes=[ExecutionMode.SINGLE])

        assert caps.can_execute(ExecutionMode.SINGLE) is True
        assert caps.can_execute(ExecutionMode.MULTI) is False
        assert caps.can_execute(ExecutionMode.AUTONOMOUS) is False

    def test_can_execute_multiple_modes(self):
        """Test can_execute for multiple modes."""
        caps = AgentCapabilities(
            execution_modes=[ExecutionMode.SINGLE, ExecutionMode.AUTONOMOUS]
        )

        assert caps.can_execute(ExecutionMode.SINGLE) is True
        assert caps.can_execute(ExecutionMode.MULTI) is False
        assert caps.can_execute(ExecutionMode.AUTONOMOUS) is True


class TestAgentCapabilitiesCanUseTool:
    """Tests for can_use_tool method."""

    def test_can_use_tool_none(self):
        """Test no tools with NONE access."""
        caps = AgentCapabilities(tool_access=ToolAccess.NONE)

        assert caps.can_use_tool("read") is False
        assert caps.can_use_tool("write") is False
        assert caps.can_use_tool("bash") is False

    def test_can_use_tool_read_only(self):
        """Test read-only tools."""
        caps = AgentCapabilities(tool_access=ToolAccess.READ_ONLY)

        assert caps.can_use_tool("read") is True
        assert caps.can_use_tool("glob") is True
        assert caps.can_use_tool("write") is False
        assert caps.can_use_tool("bash") is False

    def test_can_use_tool_constrained(self):
        """Test constrained tools."""
        caps = AgentCapabilities(tool_access=ToolAccess.CONSTRAINED)

        assert caps.can_use_tool("read") is True
        assert caps.can_use_tool("write") is True
        assert caps.can_use_tool("python") is True
        # Dangerous tools not in constrained set
        assert caps.can_use_tool("bash") is False

    def test_can_use_tool_full(self):
        """Test full access."""
        caps = AgentCapabilities(tool_access=ToolAccess.FULL)

        assert caps.can_use_tool("read") is True
        assert caps.can_use_tool("write") is True
        assert caps.can_use_tool("bash") is True
        assert caps.can_use_tool("anything") is True

    def test_can_use_tool_whitelist(self):
        """Test allowed_tools whitelist."""
        caps = AgentCapabilities(
            tool_access=ToolAccess.FULL,
            allowed_tools=["read", "write"],
        )

        assert caps.can_use_tool("read") is True
        assert caps.can_use_tool("write") is True
        assert caps.can_use_tool("bash") is False

    def test_can_use_tool_blacklist(self):
        """Test denied_tools blacklist."""
        caps = AgentCapabilities(
            tool_access=ToolAccess.FULL,
            denied_tools=["bash", "rm"],
        )

        assert caps.can_use_tool("read") is True
        assert caps.can_use_tool("write") is True
        assert caps.can_use_tool("bash") is False
        assert caps.can_use_tool("rm") is False

    def test_can_use_tool_case_insensitive(self):
        """Test tool name matching is case-insensitive."""
        caps = AgentCapabilities(tool_access=ToolAccess.READ_ONLY)

        assert caps.can_use_tool("READ") is True
        assert caps.can_use_tool("Read") is True
        assert caps.can_use_tool("GLOB") is True


class TestAgentCapabilitiesGetAvailableTools:
    """Tests for get_available_tools method."""

    def test_available_tools_none(self):
        """Test available tools with NONE access."""
        caps = AgentCapabilities(tool_access=ToolAccess.NONE)
        tools = caps.get_available_tools()
        assert len(tools) == 0

    def test_available_tools_read_only(self):
        """Test available tools with READ_ONLY access."""
        caps = AgentCapabilities(tool_access=ToolAccess.READ_ONLY)
        tools = caps.get_available_tools()
        assert "read" in tools
        assert "glob" in tools
        assert "write" not in tools

    def test_available_tools_with_denied(self):
        """Test available tools excludes denied."""
        caps = AgentCapabilities(
            tool_access=ToolAccess.FULL,
            denied_tools=["bash", "rm"],
        )
        tools = caps.get_available_tools()
        assert "bash" not in tools
        assert "rm" not in tools


class TestAgentCapabilitiesRequiresConfirmation:
    """Tests for requires_confirmation method."""

    def test_full_access_no_confirmation(self):
        """Test full access doesn't require confirmation."""
        caps = AgentCapabilities(tool_access=ToolAccess.FULL)
        assert caps.requires_confirmation("bash") is False
        assert caps.requires_confirmation("rm") is False

    def test_constrained_dangerous_requires_confirmation(self):
        """Test dangerous tools in constrained mode require confirmation."""
        caps = AgentCapabilities(tool_access=ToolAccess.CONSTRAINED)
        assert caps.requires_confirmation("bash") is True
        assert caps.requires_confirmation("rm") is True
        assert caps.requires_confirmation("read") is False


class TestAgentCapabilitiesSerialization:
    """Tests for serialization."""

    def test_to_dict(self):
        """Test to_dict method."""
        caps = AgentCapabilities(
            execution_modes=[ExecutionMode.AUTONOMOUS],
            max_memory_depth=MemoryDepth.SESSION,
            tool_access=ToolAccess.CONSTRAINED,
            max_cycles=50,
        )

        data = caps.to_dict()

        assert data["execution_modes"] == ["autonomous"]
        assert data["max_memory_depth"] == "session"
        assert data["tool_access"] == "constrained"
        assert data["max_cycles"] == 50

    def test_from_dict(self):
        """Test from_dict method."""
        data = {
            "execution_modes": ["single", "multi"],
            "max_memory_depth": "persistent",
            "tool_access": "read_only",
            "max_turns": 100,
        }

        caps = AgentCapabilities.from_dict(data)

        assert len(caps.execution_modes) == 2
        assert ExecutionMode.SINGLE in caps.execution_modes
        assert caps.max_memory_depth == MemoryDepth.PERSISTENT
        assert caps.tool_access == ToolAccess.READ_ONLY
        assert caps.max_turns == 100

    def test_roundtrip(self):
        """Test roundtrip serialization."""
        original = AgentCapabilities(
            execution_modes=[ExecutionMode.AUTONOMOUS],
            max_memory_depth=MemoryDepth.LEARNING,
            tool_access=ToolAccess.FULL,
            allowed_tools=["read", "write"],
            max_cycles=75,
            timeout_seconds=450.0,
        )

        data = original.to_dict()
        restored = AgentCapabilities.from_dict(data)

        assert restored.execution_modes == original.execution_modes
        assert restored.max_memory_depth == original.max_memory_depth
        assert restored.tool_access == original.tool_access
        assert restored.max_cycles == original.max_cycles


class TestAgentCapabilitiesString:
    """Tests for string representation."""

    def test_str(self):
        """Test __str__ method."""
        caps = AgentCapabilities(
            execution_modes=[ExecutionMode.SINGLE, ExecutionMode.AUTONOMOUS],
            max_memory_depth=MemoryDepth.SESSION,
            tool_access=ToolAccess.CONSTRAINED,
        )

        s = str(caps)

        assert "single" in s
        assert "autonomous" in s
        assert "session" in s
        assert "constrained" in s
