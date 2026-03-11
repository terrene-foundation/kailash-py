"""
Kaizen Tool Registry

Manages registration, discovery, and execution of native tools.
The registry is the central point for tool management in LocalKaizenAdapter.

Key Features:
- Tool registration with validation
- Category-based default registration
- LLM-compatible schema generation
- Safe tool execution with error handling
- Danger level filtering and approval workflow support
"""

import logging
from typing import Any, Dict, List, Optional, Set

from kaizen.tools.native.base import BaseTool, NativeToolResult
from kaizen.tools.types import DangerLevel, ToolCategory

logger = logging.getLogger(__name__)


class KaizenToolRegistry:
    """
    Registry for managing native tools.

    The registry provides:
    - Tool registration and validation
    - Category-based bulk registration
    - Tool discovery and schema generation
    - Safe tool execution with error handling

    Example:
        >>> registry = KaizenToolRegistry()
        >>>
        >>> # Register individual tools
        >>> registry.register(ReadFileTool())
        >>> registry.register(BashTool())
        >>>
        >>> # Or register defaults by category
        >>> registry.register_defaults(categories=["file", "bash", "search"])
        >>>
        >>> # Get tool schemas for LLM
        >>> schemas = registry.get_tool_schemas()
        >>>
        >>> # Execute a tool
        >>> result = await registry.execute("read_file", {"path": "data.txt"})
    """

    def __init__(self):
        """Initialize an empty tool registry."""
        self._tools: Dict[str, BaseTool] = {}
        self._categories: Dict[ToolCategory, Set[str]] = {
            cat: set() for cat in ToolCategory
        }

    def register(self, tool: BaseTool) -> None:
        """
        Register a tool in the registry.

        Args:
            tool: Tool instance to register

        Raises:
            ValueError: If tool with same name already registered
            TypeError: If tool is not a BaseTool instance
        """
        if not isinstance(tool, BaseTool):
            raise TypeError(f"Expected BaseTool instance, got {type(tool).__name__}")

        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")

        self._tools[tool.name] = tool
        self._categories[tool.category].add(tool.name)
        logger.debug(
            f"Registered tool: {tool.name} (category={tool.category.value}, danger={tool.danger_level.value})"
        )

    def unregister(self, tool_name: str) -> bool:
        """
        Unregister a tool from the registry.

        Args:
            tool_name: Name of tool to unregister

        Returns:
            True if tool was unregistered, False if not found
        """
        if tool_name not in self._tools:
            return False

        tool = self._tools.pop(tool_name)
        self._categories[tool.category].discard(tool_name)
        logger.debug(f"Unregistered tool: {tool_name}")
        return True

    def register_defaults(self, categories: Optional[List[str]] = None) -> int:
        """
        Register default tools by category.

        Args:
            categories: List of category names to register. Options:
                - "file": File tools (read, write, edit, glob, grep, list, exists)
                - "bash": Bash tool (sandboxed command execution)
                - "search": Search tools (web search, web fetch)
                - "agent": Agent tools (task spawning, skill invocation)
                - "interaction": User interaction tools (ask_user_question, todo_write, notebook_edit)
                - "planning": Plan mode tools (enter_plan_mode, exit_plan_mode)
                - "process": Process management tools (kill_shell, task_output)
                If None, registers file, bash, and search (not agent/interaction/planning/process).

        Returns:
            Number of tools registered

        Example:
            >>> registry.register_defaults(categories=["file", "bash"])
            8  # 7 file tools + 1 bash tool
            >>> registry.register_defaults(categories=["interaction", "planning", "process"])
            7  # 3 interaction + 2 planning + 2 process tools
        """
        # Import here to avoid circular imports
        from kaizen.tools.native.bash_tools import BashTool
        from kaizen.tools.native.file_tools import (
            EditFileTool,
            FileExistsTool,
            GlobTool,
            GrepTool,
            ListDirectoryTool,
            ReadFileTool,
            WriteFileTool,
        )
        from kaizen.tools.native.interaction_tool import AskUserQuestionTool
        from kaizen.tools.native.notebook_tool import NotebookEditTool
        from kaizen.tools.native.planning_tool import (
            EnterPlanModeTool,
            ExitPlanModeTool,
            PlanModeManager,
        )
        from kaizen.tools.native.process_tool import (
            KillShellTool,
            ProcessManager,
            TaskOutputTool,
        )
        from kaizen.tools.native.search_tools import WebFetchTool, WebSearchTool
        from kaizen.tools.native.skill_tool import SkillTool
        from kaizen.tools.native.task_tool import TaskTool

        # TODO-207: Claude Code parity tools
        from kaizen.tools.native.todo_tool import TodoWriteTool

        if categories is None:
            categories = ["file", "bash", "search"]

        # Create shared managers for planning and process tools
        plan_manager = PlanModeManager()
        process_manager = ProcessManager()

        tool_map = {
            "file": [
                ReadFileTool(),
                WriteFileTool(),
                EditFileTool(),
                GlobTool(),
                GrepTool(),
                ListDirectoryTool(),
                FileExistsTool(),
            ],
            "bash": [BashTool()],
            "search": [WebSearchTool(), WebFetchTool()],
            "agent": [TaskTool(), SkillTool()],
            # TODO-207: Claude Code parity categories
            "interaction": [
                TodoWriteTool(),
                NotebookEditTool(),
                AskUserQuestionTool(),
            ],
            "planning": [
                plan_manager.create_enter_tool(),
                plan_manager.create_exit_tool(),
            ],
            "process": [
                KillShellTool(process_manager=process_manager),
                TaskOutputTool(process_manager=process_manager),
            ],
        }

        count = 0
        for category in categories:
            if category not in tool_map:
                logger.warning(f"Unknown category '{category}', skipping")
                continue

            for tool in tool_map[category]:
                if tool.name not in self._tools:
                    self.register(tool)
                    count += 1

        return count

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """
        Get a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def list_tools(self) -> List[str]:
        """
        Get list of all registered tool names.

        Returns:
            Sorted list of tool names
        """
        return sorted(self._tools.keys())

    def list_tools_by_category(self, category: ToolCategory) -> List[str]:
        """
        Get list of tool names in a category.

        Args:
            category: Tool category

        Returns:
            Sorted list of tool names in the category
        """
        return sorted(self._categories.get(category, set()))

    def list_safe_tools(self) -> List[str]:
        """
        Get list of tools that don't require approval.

        Returns:
            List of tool names with SAFE or LOW danger level
        """
        return sorted(name for name, tool in self._tools.items() if tool.is_safe())

    def get_tool_schemas(
        self, filter_category: Optional[ToolCategory] = None
    ) -> List[Dict[str, Any]]:
        """
        Get LLM-compatible schemas for all tools.

        Args:
            filter_category: Optionally filter by category

        Returns:
            List of tool schemas in OpenAI function calling format
        """
        schemas = []
        for name, tool in sorted(self._tools.items()):
            if filter_category and tool.category != filter_category:
                continue
            schemas.append(tool.get_full_schema())
        return schemas

    def get_tool_info(self) -> List[Dict[str, Any]]:
        """
        Get detailed info about all registered tools.

        Returns:
            List of dicts with tool metadata
        """
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "category": tool.category.value,
                "danger_level": tool.danger_level.value,
                "requires_approval": tool.requires_approval(),
            }
            for tool in sorted(self._tools.values(), key=lambda t: t.name)
        ]

    def format_for_prompt(self) -> str:
        """
        Format tool documentation for LLM prompts.

        Returns:
            Human-readable tool documentation string
        """
        lines = ["## Available Tools\n"]

        # Group by category
        for category in ToolCategory:
            tools_in_category = [
                self._tools[name]
                for name in sorted(self._categories.get(category, set()))
            ]
            if not tools_in_category:
                continue

            lines.append(f"### {category.value.upper()} Tools\n")
            for tool in tools_in_category:
                danger_badge = f"[{tool.danger_level.value.upper()}]"
                lines.append(f"- **{tool.name}** {danger_badge}")
                lines.append(f"  {tool.description}")

                # Add parameter info
                schema = tool.get_schema()
                if "properties" in schema:
                    lines.append("  Parameters:")
                    for param_name, param_info in schema["properties"].items():
                        required = param_name in schema.get("required", [])
                        req_mark = "*" if required else ""
                        param_desc = param_info.get("description", "No description")
                        param_type = param_info.get("type", "any")
                        lines.append(
                            f"    - `{param_name}`{req_mark} ({param_type}): {param_desc}"
                        )
                lines.append("")

        return "\n".join(lines)

    async def execute(self, tool_name: str, params: Dict[str, Any]) -> NativeToolResult:
        """
        Execute a tool by name.

        Args:
            tool_name: Name of tool to execute
            params: Parameters to pass to tool

        Returns:
            NativeToolResult with execution result

        Note:
            This method does NOT check approval - that's the responsibility
            of the caller (LocalKaizenAdapter) based on danger level.
        """
        tool = self._tools.get(tool_name)
        if not tool:
            return NativeToolResult.from_error(
                f"Unknown tool: {tool_name}. Available tools: {', '.join(self.list_tools())}"
            )

        try:
            result = await tool.execute_with_timing(**params)
            logger.debug(f"Tool '{tool_name}' executed: success={result.success}")
            return result
        except Exception as e:
            logger.error(
                f"Tool '{tool_name}' raised unexpected exception: {e}", exc_info=True
            )
            return NativeToolResult.from_exception(e)

    def __len__(self) -> int:
        """Return number of registered tools."""
        return len(self._tools)

    def __contains__(self, tool_name: str) -> bool:
        """Check if tool is registered."""
        return tool_name in self._tools

    def __iter__(self):
        """Iterate over tool names."""
        return iter(sorted(self._tools.keys()))

    def __repr__(self) -> str:
        return f"KaizenToolRegistry(tools={len(self._tools)})"
