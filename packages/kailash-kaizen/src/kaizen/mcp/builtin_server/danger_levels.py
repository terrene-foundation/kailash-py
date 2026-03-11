"""
Danger level classifications for builtin MCP tools.

This module defines the danger level for each builtin MCP tool,
enabling BaseAgent's approval workflow to require user confirmation
for potentially dangerous operations.
"""

from kaizen.tools.types import DangerLevel

# Danger level mapping for all 12 builtin MCP tools
TOOL_DANGER_LEVELS = {
    # SAFE tools (read-only, non-destructive operations)
    # These tools do not modify state and are safe to execute without approval
    "read_file": DangerLevel.SAFE,
    "file_exists": DangerLevel.SAFE,
    "list_directory": DangerLevel.SAFE,
    "fetch_url": DangerLevel.SAFE,
    "extract_links": DangerLevel.SAFE,
    "http_get": DangerLevel.SAFE,
    # MEDIUM tools (writes, mutations)
    # These tools modify state but are generally safe with validation
    "write_file": DangerLevel.MEDIUM,
    "http_post": DangerLevel.MEDIUM,
    "http_put": DangerLevel.MEDIUM,
    # HIGH tools (destructive, requires approval every time)
    # These tools can cause data loss or system changes
    "delete_file": DangerLevel.HIGH,
    "http_delete": DangerLevel.HIGH,
    "bash_command": DangerLevel.HIGH,  # shell=True, command injection risk
}


def get_tool_danger_level(tool_name: str) -> DangerLevel:
    """
    Get the danger level for a given tool name.

    Args:
        tool_name: Name of the MCP tool

    Returns:
        DangerLevel enum value for the tool

    Raises:
        ValueError: If tool_name is not recognized
    """
    if tool_name not in TOOL_DANGER_LEVELS:
        raise ValueError(
            f"Unknown MCP tool: {tool_name}. "
            f"Valid tools: {sorted(TOOL_DANGER_LEVELS.keys())}"
        )

    return TOOL_DANGER_LEVELS[tool_name]


def is_tool_safe(tool_name: str) -> bool:
    """
    Check if a tool is safe to execute without approval.

    Args:
        tool_name: Name of the MCP tool

    Returns:
        True if tool is SAFE level, False otherwise
    """
    try:
        return get_tool_danger_level(tool_name) == DangerLevel.SAFE
    except ValueError:
        # Unknown tools are considered unsafe by default
        return False


def requires_approval(
    tool_name: str, danger_threshold: DangerLevel = DangerLevel.MEDIUM
) -> bool:
    """
    Check if a tool requires approval based on danger threshold.

    Args:
        tool_name: Name of the MCP tool
        danger_threshold: Minimum danger level requiring approval

    Returns:
        True if tool's danger level meets or exceeds threshold
    """
    try:
        tool_level = get_tool_danger_level(tool_name)
    except ValueError:
        # Unknown tools require approval by default
        return True

    # Define danger level ordering
    danger_order = [
        DangerLevel.SAFE,
        DangerLevel.LOW,
        DangerLevel.MEDIUM,
        DangerLevel.HIGH,
        DangerLevel.CRITICAL,
    ]

    tool_index = danger_order.index(tool_level)
    threshold_index = danger_order.index(danger_threshold)

    return tool_index >= threshold_index
