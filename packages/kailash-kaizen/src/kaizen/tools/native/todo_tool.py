"""TodoWriteTool - Structured task list management for autonomous agents.

Implements the TodoWrite tool that manages structured task lists during execution,
matching Claude Code's TodoWrite functionality. Enables agents to track progress,
organize complex tasks, and demonstrate thoroughness.

See: TODO-207 ClaudeCodeAgent Full Tool Parity

Example:
    >>> from kaizen.tools.native import TodoWriteTool, KaizenToolRegistry
    >>>
    >>> todo_tool = TodoWriteTool()
    >>> registry = KaizenToolRegistry()
    >>> registry.register(todo_tool)
    >>>
    >>> result = await registry.execute("todo_write", {
    ...     "todos": [
    ...         {"content": "Implement feature", "status": "in_progress", "activeForm": "Implementing feature"},
    ...         {"content": "Write tests", "status": "pending", "activeForm": "Writing tests"},
    ...     ]
    ... })
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from kaizen.tools.native.base import BaseTool, NativeToolResult
from kaizen.tools.types import DangerLevel, ToolCategory

if TYPE_CHECKING:
    from kaizen.session.manager import KaizenSessionManager

logger = logging.getLogger(__name__)


class TodoStatus(str, Enum):
    """Valid todo item statuses."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass
class TodoItem:
    """A single todo item in the task list.

    Attributes:
        content: The task description (imperative form, e.g., "Run tests")
        status: Current status (pending, in_progress, completed)
        active_form: Present continuous form shown during execution (e.g., "Running tests")
        created_at: ISO 8601 timestamp when item was created
        updated_at: ISO 8601 timestamp when item was last updated
    """

    content: str
    status: TodoStatus
    active_form: str
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

        # Ensure status is a TodoStatus enum
        if isinstance(self.status, str):
            self.status = TodoStatus(self.status)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "content": self.content,
            "status": self.status.value,
            "activeForm": self.active_form,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TodoItem":
        """Create TodoItem from dictionary."""
        return cls(
            content=data["content"],
            status=TodoStatus(data["status"]),
            active_form=data.get("activeForm", data.get("active_form", "")),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    def update_status(self, new_status: TodoStatus) -> None:
        """Update the status and timestamp."""
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc).isoformat()


@dataclass
class TodoList:
    """Manages a list of todo items.

    Provides operations for adding, updating, and querying todo items
    with proper validation and state management.
    """

    items: List[TodoItem] = field(default_factory=list)
    last_modified: str = ""

    def __post_init__(self):
        if not self.last_modified:
            self.last_modified = datetime.now(timezone.utc).isoformat()

    def update(self, todos: List[Dict[str, Any]]) -> None:
        """Replace the todo list with new items.

        Args:
            todos: List of todo dictionaries with content, status, activeForm
        """
        self.items = [TodoItem.from_dict(todo) for todo in todos]
        self.last_modified = datetime.now(timezone.utc).isoformat()

    def add(self, item: TodoItem) -> None:
        """Add a new todo item."""
        self.items.append(item)
        self.last_modified = datetime.now(timezone.utc).isoformat()

    def mark_completed(self, content: str) -> bool:
        """Mark a todo item as completed by content match.

        Returns:
            True if item was found and updated, False otherwise
        """
        for item in self.items:
            if item.content == content:
                item.update_status(TodoStatus.COMPLETED)
                self.last_modified = datetime.now(timezone.utc).isoformat()
                return True
        return False

    def mark_in_progress(self, content: str) -> bool:
        """Mark a todo item as in_progress by content match.

        Returns:
            True if item was found and updated, False otherwise
        """
        for item in self.items:
            if item.content == content:
                item.update_status(TodoStatus.IN_PROGRESS)
                self.last_modified = datetime.now(timezone.utc).isoformat()
                return True
        return False

    def get_pending(self) -> List[TodoItem]:
        """Get all pending items."""
        return [item for item in self.items if item.status == TodoStatus.PENDING]

    def get_in_progress(self) -> List[TodoItem]:
        """Get all in-progress items."""
        return [item for item in self.items if item.status == TodoStatus.IN_PROGRESS]

    def get_completed(self) -> List[TodoItem]:
        """Get all completed items."""
        return [item for item in self.items if item.status == TodoStatus.COMPLETED]

    def get_current(self) -> Optional[TodoItem]:
        """Get the current in-progress item (should be only one)."""
        in_progress = self.get_in_progress()
        return in_progress[0] if in_progress else None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "items": [item.to_dict() for item in self.items],
            "last_modified": self.last_modified,
            "summary": {
                "total": len(self.items),
                "pending": len(self.get_pending()),
                "in_progress": len(self.get_in_progress()),
                "completed": len(self.get_completed()),
            },
        }

    def to_display_string(self) -> str:
        """Format todo list for display to user."""
        if not self.items:
            return "No tasks in todo list."

        lines = ["Todo List:"]
        for i, item in enumerate(self.items, 1):
            status_icon = {
                TodoStatus.PENDING: "⏳",
                TodoStatus.IN_PROGRESS: "🔄",
                TodoStatus.COMPLETED: "✅",
            }.get(item.status, "•")
            lines.append(f"  {i}. [{status_icon}] {item.content}")

        summary = self.to_dict()["summary"]
        lines.append(f"\nProgress: {summary['completed']}/{summary['total']} completed")

        return "\n".join(lines)


# Type alias for todo change callback
TodoChangeCallback = Callable[[TodoList], None]


class TodoWriteTool(BaseTool):
    """Manage structured task lists during autonomous execution.

    The TodoWrite tool enables agents to:
    - Track progress on multi-step tasks
    - Organize complex work into manageable items
    - Show visibility into execution progress
    - Demonstrate thoroughness to users

    Each todo item has:
    - content: What needs to be done (imperative form)
    - status: pending, in_progress, or completed
    - activeForm: Present continuous form for display

    Task Management Rules:
    1. Only ONE task should be in_progress at a time
    2. Mark tasks completed IMMEDIATELY after finishing
    3. Create specific, actionable items
    4. Use clear, descriptive task names

    Example:
        >>> tool = TodoWriteTool()
        >>> result = await tool.execute(todos=[
        ...     {"content": "Run tests", "status": "in_progress", "activeForm": "Running tests"},
        ...     {"content": "Fix errors", "status": "pending", "activeForm": "Fixing errors"},
        ... ])
        >>> print(result.output)  # Confirmation message
    """

    name = "todo_write"
    description = (
        "Create and manage a structured task list for the current session. "
        "Use this to track progress on complex, multi-step tasks and give "
        "visibility into your work. Each todo has content (what to do), "
        "status (pending/in_progress/completed), and activeForm (display text)."
    )
    danger_level = DangerLevel.SAFE  # Writing todos is safe
    category = ToolCategory.CUSTOM

    def __init__(
        self,
        session_manager: Optional["KaizenSessionManager"] = None,
        on_change: Optional[TodoChangeCallback] = None,
    ):
        """Initialize TodoWriteTool.

        Args:
            session_manager: Optional session manager for persistence
            on_change: Optional callback when todo list changes
        """
        super().__init__()
        self._todo_list = TodoList()
        self._session_manager = session_manager
        self._on_change = on_change
        self._session_id: Optional[str] = None

    @property
    def todo_list(self) -> TodoList:
        """Get the current todo list."""
        return self._todo_list

    def set_session(self, session_id: str) -> None:
        """Associate with a session for persistence."""
        self._session_id = session_id

    async def execute(
        self,
        todos: List[Dict[str, Any]],
        **kwargs,
    ) -> NativeToolResult:
        """Update the todo list with new items.

        Args:
            todos: List of todo items, each with:
                - content (str): Task description (imperative form)
                - status (str): "pending", "in_progress", or "completed"
                - activeForm (str): Present continuous form for display

        Returns:
            NativeToolResult with success status and todo list summary

        Example:
            >>> result = await tool.execute(todos=[
            ...     {"content": "Implement feature", "status": "in_progress", "activeForm": "Implementing feature"},
            ...     {"content": "Write tests", "status": "pending", "activeForm": "Writing tests"},
            ... ])
        """
        try:
            # Validate todos
            if not todos:
                return NativeToolResult.from_error("todos list cannot be empty")

            validated_todos = []
            for i, todo in enumerate(todos):
                # Validate required fields
                if "content" not in todo:
                    return NativeToolResult.from_error(
                        f"Todo item {i} missing required 'content' field"
                    )
                if "status" not in todo:
                    return NativeToolResult.from_error(
                        f"Todo item {i} missing required 'status' field"
                    )
                if "activeForm" not in todo:
                    return NativeToolResult.from_error(
                        f"Todo item {i} missing required 'activeForm' field"
                    )

                # Validate content is non-empty
                if not todo["content"].strip():
                    return NativeToolResult.from_error(
                        f"Todo item {i} has empty 'content'"
                    )

                # Validate status value
                try:
                    status = TodoStatus(todo["status"])
                except ValueError:
                    return NativeToolResult.from_error(
                        f"Todo item {i} has invalid status '{todo['status']}'. "
                        f"Must be one of: pending, in_progress, completed"
                    )

                validated_todos.append(
                    {
                        "content": todo["content"].strip(),
                        "status": status.value,
                        "activeForm": todo["activeForm"].strip(),
                    }
                )

            # Check for multiple in_progress items (warning, not error)
            in_progress_count = sum(
                1 for t in validated_todos if t["status"] == "in_progress"
            )
            warnings = []
            if in_progress_count > 1:
                warnings.append(
                    f"Warning: {in_progress_count} tasks are in_progress. "
                    "Ideally only one task should be in_progress at a time."
                )

            # Update the todo list
            self._todo_list.update(validated_todos)

            # Call change callback if provided
            if self._on_change:
                try:
                    self._on_change(self._todo_list)
                except Exception as e:
                    logger.warning(f"Todo change callback failed: {e}")

            # Persist to session if available
            if self._session_manager and self._session_id:
                try:
                    await self._persist_to_session()
                except Exception as e:
                    logger.warning(f"Failed to persist todos to session: {e}")

            # Build response
            summary = self._todo_list.to_dict()["summary"]
            message = (
                f"Todos updated: {summary['total']} items "
                f"({summary['completed']} completed, "
                f"{summary['in_progress']} in progress, "
                f"{summary['pending']} pending)"
            )

            if warnings:
                message = "\n".join([message] + warnings)

            logger.info(
                f"TodoWrite: {summary['total']} items, "
                f"{summary['in_progress']} in progress"
            )

            return NativeToolResult.from_success(
                output=message,
                todo_summary=summary,
                items=[item.to_dict() for item in self._todo_list.items],
            )

        except Exception as e:
            logger.error(f"TodoWrite failed: {e}")
            return NativeToolResult.from_exception(e)

    async def _persist_to_session(self) -> None:
        """Persist todo list to session state."""
        if not self._session_manager or not self._session_id:
            return

        # TODO: Integrate with KaizenSessionManager metadata
        # For now, this is a placeholder for session persistence
        pass

    def get_schema(self) -> Dict[str, Any]:
        """Get JSON Schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "description": "The updated todo list",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "minLength": 1,
                                "description": "Task description (imperative form, e.g., 'Run tests')",
                            },
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                                "description": "Task status",
                            },
                            "activeForm": {
                                "type": "string",
                                "minLength": 1,
                                "description": "Present continuous form (e.g., 'Running tests')",
                            },
                        },
                        "required": ["content", "status", "activeForm"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["todos"],
            "additionalProperties": False,
        }

    def get_display(self) -> str:
        """Get formatted todo list for display."""
        return self._todo_list.to_display_string()

    def clear(self) -> None:
        """Clear all todos."""
        self._todo_list = TodoList()
        if self._on_change:
            try:
                self._on_change(self._todo_list)
            except Exception as e:
                logger.warning(f"Todo change callback failed on clear: {e}")
