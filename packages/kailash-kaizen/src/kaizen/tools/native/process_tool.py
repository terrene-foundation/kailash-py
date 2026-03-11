"""Process Management Tools - Background task control for autonomous agents.

Implements KillShell and TaskOutput tools that allow agents to manage
background processes, matching Claude Code's process management functionality.

See: TODO-207 ClaudeCodeAgent Full Tool Parity

Example:
    >>> from kaizen.tools.native import KillShellTool, TaskOutputTool
    >>> from kaizen.tools.native import KaizenToolRegistry
    >>>
    >>> registry = KaizenToolRegistry()
    >>> registry.register(KillShellTool(process_manager=my_pm))
    >>> registry.register(TaskOutputTool(process_manager=my_pm))
    >>>
    >>> # Kill a background shell
    >>> result = await registry.execute("kill_shell", {
    ...     "shell_id": "shell-abc123"
    ... })
    >>>
    >>> # Get task output
    >>> result = await registry.execute("task_output", {
    ...     "task_id": "task-xyz789",
    ...     "block": True,
    ...     "timeout": 30000
    ... })
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

from kaizen.tools.native.base import BaseTool, NativeToolResult
from kaizen.tools.types import DangerLevel, ToolCategory

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    """Type of background task."""

    SHELL = "shell"
    AGENT = "agent"
    REMOTE = "remote"


@dataclass
class TaskInfo:
    """Information about a background task.

    Attributes:
        task_id: Unique task identifier
        task_type: Type of task (shell, agent, remote)
        status: Current task status
        created_at: When the task was created
        output: Task output content
        error: Error message if failed
        metadata: Additional task metadata
    """

    task_id: str
    task_type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    output: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
        }


class ProcessManager:
    """Manages background processes and tasks.

    This class provides a centralized way to track and manage background
    tasks including shells, agents, and remote sessions.

    Example:
        >>> pm = ProcessManager()
        >>> task = pm.register_task("shell-001", TaskType.SHELL)
        >>> pm.update_output("shell-001", "Running...")
        >>> pm.complete_task("shell-001", "Done!")
    """

    def __init__(self):
        """Initialize ProcessManager."""
        self._tasks: Dict[str, TaskInfo] = {}
        self._processes: Dict[str, asyncio.subprocess.Process] = {}
        self._events: Dict[str, asyncio.Event] = {}

    @property
    def tasks(self) -> Dict[str, TaskInfo]:
        """Get all tasks."""
        return self._tasks.copy()

    def register_task(
        self,
        task_id: str,
        task_type: TaskType,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskInfo:
        """Register a new task.

        Args:
            task_id: Unique task identifier
            task_type: Type of task
            metadata: Optional metadata

        Returns:
            Created TaskInfo
        """
        task = TaskInfo(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            metadata=metadata or {},
        )
        self._tasks[task_id] = task
        self._events[task_id] = asyncio.Event()
        logger.debug(f"Registered task: {task_id}")
        return task

    def start_task(self, task_id: str) -> bool:
        """Mark task as running.

        Args:
            task_id: Task identifier

        Returns:
            True if successful, False if task not found
        """
        if task_id not in self._tasks:
            return False
        self._tasks[task_id].status = TaskStatus.RUNNING
        logger.debug(f"Started task: {task_id}")
        return True

    def update_output(self, task_id: str, output: str, append: bool = True) -> bool:
        """Update task output.

        Args:
            task_id: Task identifier
            output: Output content
            append: Whether to append to existing output

        Returns:
            True if successful, False if task not found
        """
        if task_id not in self._tasks:
            return False
        if append:
            self._tasks[task_id].output += output
        else:
            self._tasks[task_id].output = output
        return True

    def complete_task(
        self,
        task_id: str,
        output: Optional[str] = None,
        error: Optional[str] = None,
    ) -> bool:
        """Mark task as completed.

        Args:
            task_id: Task identifier
            output: Final output
            error: Error message if failed

        Returns:
            True if successful, False if task not found
        """
        if task_id not in self._tasks:
            return False

        task = self._tasks[task_id]
        task.completed_at = datetime.now(timezone.utc).isoformat()

        if error:
            task.status = TaskStatus.FAILED
            task.error = error
        else:
            task.status = TaskStatus.COMPLETED

        if output:
            task.output = output

        # Signal completion
        if task_id in self._events:
            self._events[task_id].set()

        logger.debug(f"Completed task: {task_id}")
        return True

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task.

        Args:
            task_id: Task identifier

        Returns:
            True if successful, False if task not found
        """
        if task_id not in self._tasks:
            return False

        task = self._tasks[task_id]
        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.now(timezone.utc).isoformat()

        # Kill process if exists
        if task_id in self._processes:
            try:
                self._processes[task_id].kill()
            except ProcessLookupError:
                pass  # Already dead
            del self._processes[task_id]

        # Signal completion
        if task_id in self._events:
            self._events[task_id].set()

        logger.debug(f"Cancelled task: {task_id}")
        return True

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """Get task info.

        Args:
            task_id: Task identifier

        Returns:
            TaskInfo if found, None otherwise
        """
        return self._tasks.get(task_id)

    async def wait_for_task(
        self,
        task_id: str,
        timeout: Optional[float] = None,
    ) -> Optional[TaskInfo]:
        """Wait for task completion.

        Args:
            task_id: Task identifier
            timeout: Maximum wait time in seconds

        Returns:
            TaskInfo if completed, None if timeout or not found
        """
        if task_id not in self._tasks:
            return None

        if task_id not in self._events:
            return self._tasks[task_id]

        try:
            await asyncio.wait_for(
                self._events[task_id].wait(),
                timeout=timeout,
            )
            return self._tasks[task_id]
        except asyncio.TimeoutError:
            return self._tasks[task_id]

    def register_process(
        self,
        task_id: str,
        process: asyncio.subprocess.Process,
    ) -> None:
        """Register a process for a task.

        Args:
            task_id: Task identifier
            process: The subprocess
        """
        self._processes[task_id] = process

    def remove_task(self, task_id: str) -> bool:
        """Remove a task from tracking.

        Args:
            task_id: Task identifier

        Returns:
            True if removed, False if not found
        """
        if task_id not in self._tasks:
            return False

        del self._tasks[task_id]
        self._events.pop(task_id, None)
        self._processes.pop(task_id, None)
        return True


class KillShellTool(BaseTool):
    """Kill a running background shell.

    The KillShell tool terminates a background shell process by its ID.
    Use this when you need to stop a long-running shell command.

    Example:
        >>> tool = KillShellTool(process_manager=pm)
        >>> result = await tool.execute(shell_id="shell-abc123")
        >>> print(result.output)  # "Shell shell-abc123 killed successfully"
    """

    name = "kill_shell"
    description = (
        "Kills a running background shell by its ID. "
        "Returns success or failure status. "
        "Use this to terminate long-running shell commands."
    )
    danger_level = DangerLevel.MEDIUM
    category = ToolCategory.SYSTEM

    def __init__(self, process_manager: Optional[ProcessManager] = None):
        """Initialize KillShellTool.

        Args:
            process_manager: Process manager for task tracking
        """
        super().__init__()
        self._pm = process_manager or ProcessManager()

    @property
    def process_manager(self) -> ProcessManager:
        """Get process manager."""
        return self._pm

    def set_process_manager(self, pm: ProcessManager) -> None:
        """Set process manager."""
        self._pm = pm

    async def execute(
        self,
        shell_id: str,
        **kwargs,
    ) -> NativeToolResult:
        """Kill a background shell.

        Args:
            shell_id: The ID of the background shell to kill

        Returns:
            NativeToolResult with success or failure status

        Example:
            >>> result = await tool.execute(shell_id="shell-123")
        """
        try:
            if not shell_id:
                return NativeToolResult.from_error("shell_id is required")

            task = self._pm.get_task(shell_id)
            if task is None:
                return NativeToolResult.from_error(f"Shell not found: {shell_id}")

            if task.task_type != TaskType.SHELL:
                return NativeToolResult.from_error(
                    f"Task {shell_id} is not a shell (type: {task.task_type.value})"
                )

            if task.status in (
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            ):
                return NativeToolResult.from_success(
                    output=f"Shell {shell_id} already terminated (status: {task.status.value})",
                    shell_id=shell_id,
                    status=task.status.value,
                )

            success = self._pm.cancel_task(shell_id)

            if success:
                logger.info(f"Killed shell: {shell_id}")
                return NativeToolResult.from_success(
                    output=f"Shell {shell_id} killed successfully",
                    shell_id=shell_id,
                    status="cancelled",
                )
            else:
                return NativeToolResult.from_error(f"Failed to kill shell: {shell_id}")

        except Exception as e:
            logger.error(f"KillShell failed: {e}")
            return NativeToolResult.from_exception(e)

    def get_schema(self) -> Dict[str, Any]:
        """Get JSON Schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "shell_id": {
                    "type": "string",
                    "description": "The ID of the background shell to kill",
                },
            },
            "required": ["shell_id"],
            "additionalProperties": False,
        }


class TaskOutputTool(BaseTool):
    """Retrieve output from a background task.

    The TaskOutput tool retrieves output from a running or completed task
    including background shells, agents, and remote sessions.

    Example:
        >>> tool = TaskOutputTool(process_manager=pm)
        >>> result = await tool.execute(
        ...     task_id="task-xyz789",
        ...     block=True,
        ...     timeout=30000,
        ... )
        >>> print(result.output)
    """

    name = "task_output"
    description = (
        "Retrieves output from a running or completed task (background shell, agent, or remote session). "
        "Use block=true to wait for completion, block=false for non-blocking check."
    )
    danger_level = DangerLevel.SAFE
    category = ToolCategory.SYSTEM

    def __init__(self, process_manager: Optional[ProcessManager] = None):
        """Initialize TaskOutputTool.

        Args:
            process_manager: Process manager for task tracking
        """
        super().__init__()
        self._pm = process_manager or ProcessManager()

    @property
    def process_manager(self) -> ProcessManager:
        """Get process manager."""
        return self._pm

    def set_process_manager(self, pm: ProcessManager) -> None:
        """Set process manager."""
        self._pm = pm

    async def execute(
        self,
        task_id: str,
        block: bool = True,
        timeout: float = 30000,
        **kwargs,
    ) -> NativeToolResult:
        """Get task output.

        Args:
            task_id: The task ID to get output from
            block: Whether to wait for completion (default True)
            timeout: Max wait time in milliseconds (default 30000, max 600000)

        Returns:
            NativeToolResult with task output and status

        Example:
            >>> result = await tool.execute(
            ...     task_id="task-123",
            ...     block=True,
            ...     timeout=30000,
            ... )
        """
        try:
            if not task_id:
                return NativeToolResult.from_error("task_id is required")

            # Validate timeout
            if timeout < 0:
                return NativeToolResult.from_error("timeout must be non-negative")
            if timeout > 600000:
                return NativeToolResult.from_error("timeout must not exceed 600000ms")

            task = self._pm.get_task(task_id)
            if task is None:
                return NativeToolResult.from_error(f"Task not found: {task_id}")

            # If blocking and task is still running, wait for completion
            if block and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                timeout_seconds = timeout / 1000  # Convert ms to seconds
                task = await self._pm.wait_for_task(task_id, timeout=timeout_seconds)

            if task is None:
                return NativeToolResult.from_error(
                    f"Task not found after wait: {task_id}"
                )

            logger.debug(f"Retrieved output for task: {task_id}")

            return NativeToolResult.from_success(
                output=task.output or "(no output)",
                task_id=task_id,
                task_type=task.task_type.value,
                status=task.status.value,
                error=task.error,
                created_at=task.created_at,
                completed_at=task.completed_at,
            )

        except Exception as e:
            logger.error(f"TaskOutput failed: {e}")
            return NativeToolResult.from_exception(e)

    def get_schema(self) -> Dict[str, Any]:
        """Get JSON Schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task ID to get output from",
                },
                "block": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to wait for completion",
                },
                "timeout": {
                    "type": "number",
                    "default": 30000,
                    "minimum": 0,
                    "maximum": 600000,
                    "description": "Max wait time in milliseconds",
                },
            },
            "required": ["task_id"],
            "additionalProperties": False,
        }
