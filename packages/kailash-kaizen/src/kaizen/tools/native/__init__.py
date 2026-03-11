"""
Kaizen Native Tool System

Provides native tool implementations for autonomous agents that work with ANY LLM provider.
These tools are used internally by LocalKaizenAdapter for the Think-Act-Observe-Decide loop.

Key Components:
- BaseTool: Abstract base class for all native tools
- KaizenToolRegistry: Tool registration, discovery, and execution
- File Tools: ReadFileTool, WriteFileTool, EditFileTool, GlobTool, GrepTool, etc.
- Bash Tools: BashTool with sandboxed execution
- Search Tools: WebSearchTool, WebFetchTool

Unlike MCP tools (used by BaseAgent for external LLM access), native tools are designed
for direct programmatic execution within the LocalKaizenAdapter's autonomous loop.

Example:
    >>> from kaizen.tools.native import KaizenToolRegistry, ReadFileTool
    >>>
    >>> registry = KaizenToolRegistry()
    >>> registry.register(ReadFileTool())
    >>> registry.register_defaults(categories=["file", "bash"])
    >>>
    >>> result = await registry.execute("read_file", {"path": "data.txt"})
    >>> print(result.output)
"""

from kaizen.tools.native.base import BaseTool, NativeToolResult

# Bash tools
from kaizen.tools.native.bash_tools import BashTool

# File tools
from kaizen.tools.native.file_tools import (
    EditFileTool,
    FileExistsTool,
    GlobTool,
    GrepTool,
    ListDirectoryTool,
    ReadFileTool,
    WriteFileTool,
)
from kaizen.tools.native.interaction_tool import (
    AskUserQuestionTool,
    Question,
    QuestionAnswer,
    QuestionOption,
)
from kaizen.tools.native.notebook_tool import CellType, EditMode, NotebookEditTool
from kaizen.tools.native.planning_tool import (
    AllowedPrompt,
    EnterPlanModeTool,
    ExitPlanModeTool,
    PlanMode,
    PlanModeManager,
    PlanState,
)
from kaizen.tools.native.process_tool import (
    KillShellTool,
    ProcessManager,
    TaskInfo,
    TaskOutputTool,
    TaskStatus,
    TaskType,
)
from kaizen.tools.native.registry import KaizenToolRegistry

# Search tools
from kaizen.tools.native.search_tools import WebFetchTool, WebSearchTool

# Agent tools (TODO-203)
from kaizen.tools.native.skill_tool import SkillTool
from kaizen.tools.native.task_tool import TaskTool

# Interaction tools (TODO-207)
from kaizen.tools.native.todo_tool import TodoItem, TodoList, TodoStatus, TodoWriteTool

__all__ = [
    # Base
    "BaseTool",
    "NativeToolResult",
    "KaizenToolRegistry",
    # File tools
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "GlobTool",
    "GrepTool",
    "ListDirectoryTool",
    "FileExistsTool",
    # Bash tools
    "BashTool",
    # Search tools
    "WebSearchTool",
    "WebFetchTool",
    # Agent tools (TODO-203)
    "TaskTool",
    "SkillTool",
    # Interaction tools (TODO-207)
    "TodoWriteTool",
    "TodoItem",
    "TodoList",
    "TodoStatus",
    "NotebookEditTool",
    "CellType",
    "EditMode",
    "AskUserQuestionTool",
    "Question",
    "QuestionAnswer",
    "QuestionOption",
    # Planning tools (TODO-207)
    "EnterPlanModeTool",
    "ExitPlanModeTool",
    "PlanMode",
    "PlanState",
    "AllowedPrompt",
    "PlanModeManager",
    # Process management tools (TODO-207)
    "KillShellTool",
    "TaskOutputTool",
    "ProcessManager",
    "TaskInfo",
    "TaskStatus",
    "TaskType",
]
