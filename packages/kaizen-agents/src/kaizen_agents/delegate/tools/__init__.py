"""kz tool system — file operations, search, and shell execution."""

from __future__ import annotations

from typing import Any

from kaizen_agents.delegate.tools.base import Tool, ToolRegistry, ToolResult
from kaizen_agents.delegate.tools.bash_tool import BashTool
from kaizen_agents.delegate.tools.file_edit import FileEditTool
from kaizen_agents.delegate.tools.file_read import FileReadTool
from kaizen_agents.delegate.tools.file_write import FileWriteTool
from kaizen_agents.delegate.tools.glob_tool import GlobTool
from kaizen_agents.delegate.tools.grep_tool import GrepTool


def create_default_tools(*, permission_gate: Any | None = None) -> ToolRegistry:
    """Create a ToolRegistry pre-loaded with the standard kz tool set.

    Parameters
    ----------
    permission_gate:
        Required callback for BashTool. If not provided, BashTool is
        omitted from the registry. Use ``ExecPolicy.as_permission_gate()``
        to create one.
    """
    registry = ToolRegistry()
    registry.register(FileReadTool())
    registry.register(FileWriteTool())
    registry.register(FileEditTool())
    registry.register(GlobTool())
    registry.register(GrepTool())
    if permission_gate is not None:
        registry.register(BashTool(permission_gate=permission_gate))
    return registry


__all__ = [
    "BashTool",
    "FileEditTool",
    "FileReadTool",
    "FileWriteTool",
    "GlobTool",
    "GrepTool",
    "Tool",
    "ToolRegistry",
    "ToolResult",
    "create_default_tools",
]
