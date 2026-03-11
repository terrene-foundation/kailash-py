"""
Tier 1 Unit Tests for MCP Tool Danger Levels

Tests the TOOL_DANGER_LEVELS mapping and danger level utility functions.
"""

import pytest
from kaizen.mcp.builtin_server.danger_levels import (
    TOOL_DANGER_LEVELS,
    get_tool_danger_level,
    is_tool_safe,
    requires_approval,
)
from kaizen.tools.types import DangerLevel


class TestToolDangerLevelsMapping:
    """Test TOOL_DANGER_LEVELS constant has correct mappings."""

    def test_all_12_tools_mapped(self):
        """Test all 12 builtin tools have danger level mappings."""
        assert len(TOOL_DANGER_LEVELS) == 12

    def test_safe_tools_mapped(self):
        """Test SAFE level tools are mapped correctly."""
        safe_tools = [
            "read_file",
            "file_exists",
            "list_directory",
            "fetch_url",
            "extract_links",
            "http_get",
        ]
        for tool in safe_tools:
            assert (
                TOOL_DANGER_LEVELS[tool] == DangerLevel.SAFE
            ), f"{tool} should be SAFE"

    def test_medium_tools_mapped(self):
        """Test MEDIUM level tools are mapped correctly."""
        medium_tools = ["write_file", "http_post", "http_put"]
        for tool in medium_tools:
            assert (
                TOOL_DANGER_LEVELS[tool] == DangerLevel.MEDIUM
            ), f"{tool} should be MEDIUM"

    def test_high_tools_mapped(self):
        """Test HIGH level tools are mapped correctly."""
        high_tools = ["delete_file", "http_delete", "bash_command"]
        for tool in high_tools:
            assert (
                TOOL_DANGER_LEVELS[tool] == DangerLevel.HIGH
            ), f"{tool} should be HIGH"

    def test_no_low_or_critical_tools(self):
        """Test no tools use LOW or CRITICAL levels."""
        for danger in TOOL_DANGER_LEVELS.values():
            assert danger != DangerLevel.LOW
            assert danger != DangerLevel.CRITICAL

    def test_bash_command_is_high(self):
        """Test bash_command is HIGH danger (shell=True, command injection risk)."""
        assert TOOL_DANGER_LEVELS["bash_command"] == DangerLevel.HIGH


class TestGetToolDangerLevel:
    """Test get_tool_danger_level() function."""

    def test_get_safe_tool_level(self):
        """Test getting danger level for SAFE tool."""
        assert get_tool_danger_level("read_file") == DangerLevel.SAFE

    def test_get_medium_tool_level(self):
        """Test getting danger level for MEDIUM tool."""
        assert get_tool_danger_level("write_file") == DangerLevel.MEDIUM

    def test_get_high_tool_level(self):
        """Test getting danger level for HIGH tool."""
        assert get_tool_danger_level("bash_command") == DangerLevel.HIGH

    def test_unknown_tool_raises_error(self):
        """Test unknown tool raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            get_tool_danger_level("unknown_tool")

        assert "Unknown MCP tool: unknown_tool" in str(exc_info.value)
        assert "Valid tools:" in str(exc_info.value)

    def test_error_message_lists_valid_tools(self):
        """Test error message includes list of valid tools."""
        with pytest.raises(ValueError) as exc_info:
            get_tool_danger_level("invalid")

        error_msg = str(exc_info.value)
        # Should contain some of the valid tool names
        assert "read_file" in error_msg or "write_file" in error_msg


class TestIsToolSafe:
    """Test is_tool_safe() function."""

    def test_safe_tools_return_true(self):
        """Test SAFE level tools return True."""
        safe_tools = [
            "read_file",
            "file_exists",
            "list_directory",
            "fetch_url",
            "extract_links",
            "http_get",
        ]
        for tool in safe_tools:
            assert is_tool_safe(tool) is True, f"{tool} should be safe"

    def test_medium_tools_return_false(self):
        """Test MEDIUM level tools return False."""
        medium_tools = ["write_file", "http_post", "http_put"]
        for tool in medium_tools:
            assert is_tool_safe(tool) is False, f"{tool} should not be safe"

    def test_high_tools_return_false(self):
        """Test HIGH level tools return False."""
        high_tools = ["delete_file", "http_delete", "bash_command"]
        for tool in high_tools:
            assert is_tool_safe(tool) is False, f"{tool} should not be safe"

    def test_unknown_tool_returns_false(self):
        """Test unknown tool returns False (safe default)."""
        assert is_tool_safe("unknown_tool") is False


class TestRequiresApproval:
    """Test requires_approval() function."""

    def test_safe_tool_no_approval_with_medium_threshold(self):
        """Test SAFE tool doesn't require approval with MEDIUM threshold."""
        assert requires_approval("read_file", DangerLevel.MEDIUM) is False

    def test_medium_tool_requires_approval_with_medium_threshold(self):
        """Test MEDIUM tool requires approval with MEDIUM threshold."""
        assert requires_approval("write_file", DangerLevel.MEDIUM) is True

    def test_high_tool_requires_approval_with_medium_threshold(self):
        """Test HIGH tool requires approval with MEDIUM threshold."""
        assert requires_approval("bash_command", DangerLevel.MEDIUM) is True

    def test_medium_tool_no_approval_with_high_threshold(self):
        """Test MEDIUM tool doesn't require approval with HIGH threshold."""
        assert requires_approval("write_file", DangerLevel.HIGH) is False

    def test_high_tool_requires_approval_with_high_threshold(self):
        """Test HIGH tool requires approval with HIGH threshold."""
        assert requires_approval("bash_command", DangerLevel.HIGH) is True

    def test_safe_tool_requires_approval_with_safe_threshold(self):
        """Test SAFE tool requires approval with SAFE threshold (at threshold)."""
        assert requires_approval("read_file", DangerLevel.SAFE) is True

    def test_medium_tool_requires_approval_with_safe_threshold(self):
        """Test MEDIUM tool requires approval with SAFE threshold."""
        assert requires_approval("write_file", DangerLevel.SAFE) is True

    def test_unknown_tool_requires_approval(self):
        """Test unknown tool requires approval by default (safe default)."""
        assert requires_approval("unknown_tool", DangerLevel.MEDIUM) is True


class TestDangerLevelOrdering:
    """Test danger level ordering logic."""

    def test_safe_is_lowest(self):
        """Test SAFE is the lowest danger level (no lower threshold exists)."""
        # SAFE tools don't require approval with LOW threshold
        # (because there's no danger level lower than SAFE)
        assert not requires_approval("read_file", DangerLevel.LOW)

    def test_high_is_highest_in_builtin(self):
        """Test HIGH is the highest danger level in builtin tools."""
        # All tools should require approval with CRITICAL threshold except CRITICAL itself
        assert requires_approval("bash_command", DangerLevel.CRITICAL) is False

    def test_ordering_safe_low_medium_high_critical(self):
        """Test danger level ordering: SAFE < LOW < MEDIUM < HIGH < CRITICAL."""
        # MEDIUM tool with different thresholds
        tool = "write_file"  # MEDIUM level
        assert not requires_approval(tool, DangerLevel.HIGH)  # Below threshold
        assert requires_approval(tool, DangerLevel.MEDIUM)  # At threshold
        assert requires_approval(tool, DangerLevel.SAFE)  # Above threshold
