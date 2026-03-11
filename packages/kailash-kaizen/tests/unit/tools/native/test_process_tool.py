"""
Unit Tests for Process Management Tools (Tier 1)

Tests KillShellTool and TaskOutputTool for autonomous agents.
Part of TODO-207 ClaudeCodeAgent Full Tool Parity.
"""

import asyncio
from typing import List

import pytest

from kaizen.tools.native.process_tool import (
    KillShellTool,
    ProcessManager,
    TaskInfo,
    TaskOutputTool,
    TaskStatus,
    TaskType,
)
from kaizen.tools.types import DangerLevel, ToolCategory


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_task_status_values(self):
        """Test all task status values exist."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"

    def test_task_status_from_string(self):
        """Test creating task status from string."""
        assert TaskStatus("pending") == TaskStatus.PENDING
        assert TaskStatus("running") == TaskStatus.RUNNING
        assert TaskStatus("completed") == TaskStatus.COMPLETED

    def test_invalid_task_status_raises(self):
        """Test invalid task status raises ValueError."""
        with pytest.raises(ValueError):
            TaskStatus("invalid")


class TestTaskType:
    """Tests for TaskType enum."""

    def test_task_type_values(self):
        """Test all task type values exist."""
        assert TaskType.SHELL.value == "shell"
        assert TaskType.AGENT.value == "agent"
        assert TaskType.REMOTE.value == "remote"

    def test_task_type_from_string(self):
        """Test creating task type from string."""
        assert TaskType("shell") == TaskType.SHELL
        assert TaskType("agent") == TaskType.AGENT
        assert TaskType("remote") == TaskType.REMOTE


class TestTaskInfo:
    """Tests for TaskInfo dataclass."""

    def test_create_task_info(self):
        """Test creating task info."""
        task = TaskInfo(task_id="task-001", task_type=TaskType.SHELL)
        assert task.task_id == "task-001"
        assert task.task_type == TaskType.SHELL
        assert task.status == TaskStatus.PENDING
        assert task.created_at is not None
        assert task.output == ""

    def test_task_info_with_values(self):
        """Test task info with all values."""
        task = TaskInfo(
            task_id="task-002",
            task_type=TaskType.AGENT,
            status=TaskStatus.COMPLETED,
            output="Done!",
            error=None,
            metadata={"key": "value"},
        )
        assert task.task_id == "task-002"
        assert task.status == TaskStatus.COMPLETED
        assert task.output == "Done!"

    def test_to_dict(self):
        """Test converting to dictionary."""
        task = TaskInfo(
            task_id="task-003",
            task_type=TaskType.SHELL,
            status=TaskStatus.RUNNING,
            output="Running...",
        )
        d = task.to_dict()
        assert d["task_id"] == "task-003"
        assert d["task_type"] == "shell"
        assert d["status"] == "running"
        assert d["output"] == "Running..."


class TestProcessManager:
    """Tests for ProcessManager class."""

    def test_create_manager(self):
        """Test creating process manager."""
        pm = ProcessManager()
        assert len(pm.tasks) == 0

    def test_register_task(self):
        """Test registering a task."""
        pm = ProcessManager()
        task = pm.register_task("task-001", TaskType.SHELL)
        assert task.task_id == "task-001"
        assert task.status == TaskStatus.PENDING
        assert "task-001" in pm.tasks

    def test_register_task_with_metadata(self):
        """Test registering task with metadata."""
        pm = ProcessManager()
        task = pm.register_task(
            "task-002",
            TaskType.AGENT,
            metadata={"description": "test agent"},
        )
        assert task.metadata["description"] == "test agent"

    def test_start_task(self):
        """Test starting a task."""
        pm = ProcessManager()
        pm.register_task("task-001", TaskType.SHELL)
        result = pm.start_task("task-001")
        assert result is True
        assert pm.get_task("task-001").status == TaskStatus.RUNNING

    def test_start_nonexistent_task(self):
        """Test starting nonexistent task."""
        pm = ProcessManager()
        result = pm.start_task("nonexistent")
        assert result is False

    def test_update_output_append(self):
        """Test updating output with append."""
        pm = ProcessManager()
        pm.register_task("task-001", TaskType.SHELL)
        pm.update_output("task-001", "Line 1\n")
        pm.update_output("task-001", "Line 2\n")
        assert pm.get_task("task-001").output == "Line 1\nLine 2\n"

    def test_update_output_replace(self):
        """Test updating output with replace."""
        pm = ProcessManager()
        pm.register_task("task-001", TaskType.SHELL)
        pm.update_output("task-001", "Old output")
        pm.update_output("task-001", "New output", append=False)
        assert pm.get_task("task-001").output == "New output"

    def test_update_output_nonexistent(self):
        """Test updating nonexistent task."""
        pm = ProcessManager()
        result = pm.update_output("nonexistent", "output")
        assert result is False

    def test_complete_task(self):
        """Test completing a task."""
        pm = ProcessManager()
        pm.register_task("task-001", TaskType.SHELL)
        pm.start_task("task-001")
        result = pm.complete_task("task-001", output="Done!")

        assert result is True
        task = pm.get_task("task-001")
        assert task.status == TaskStatus.COMPLETED
        assert task.output == "Done!"
        assert task.completed_at is not None

    def test_complete_task_with_error(self):
        """Test completing a task with error."""
        pm = ProcessManager()
        pm.register_task("task-001", TaskType.SHELL)
        pm.complete_task("task-001", error="Something went wrong")

        task = pm.get_task("task-001")
        assert task.status == TaskStatus.FAILED
        assert task.error == "Something went wrong"

    def test_complete_nonexistent_task(self):
        """Test completing nonexistent task."""
        pm = ProcessManager()
        result = pm.complete_task("nonexistent")
        assert result is False

    def test_cancel_task(self):
        """Test cancelling a task."""
        pm = ProcessManager()
        pm.register_task("task-001", TaskType.SHELL)
        result = pm.cancel_task("task-001")

        assert result is True
        task = pm.get_task("task-001")
        assert task.status == TaskStatus.CANCELLED

    def test_cancel_nonexistent_task(self):
        """Test cancelling nonexistent task."""
        pm = ProcessManager()
        result = pm.cancel_task("nonexistent")
        assert result is False

    def test_get_task(self):
        """Test getting a task."""
        pm = ProcessManager()
        pm.register_task("task-001", TaskType.SHELL)
        task = pm.get_task("task-001")
        assert task is not None
        assert task.task_id == "task-001"

    def test_get_nonexistent_task(self):
        """Test getting nonexistent task."""
        pm = ProcessManager()
        task = pm.get_task("nonexistent")
        assert task is None

    @pytest.mark.asyncio
    async def test_wait_for_task_already_complete(self):
        """Test waiting for already completed task."""
        pm = ProcessManager()
        pm.register_task("task-001", TaskType.SHELL)
        pm.complete_task("task-001", output="Done")

        task = await pm.wait_for_task("task-001", timeout=1.0)
        assert task is not None
        assert task.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_wait_for_task_completion(self):
        """Test waiting for task to complete."""
        pm = ProcessManager()
        pm.register_task("task-001", TaskType.SHELL)

        async def complete_later():
            await asyncio.sleep(0.05)
            pm.complete_task("task-001", output="Completed!")

        asyncio.create_task(complete_later())
        task = await pm.wait_for_task("task-001", timeout=1.0)

        assert task is not None
        assert task.status == TaskStatus.COMPLETED
        assert task.output == "Completed!"

    @pytest.mark.asyncio
    async def test_wait_for_task_timeout(self):
        """Test waiting for task with timeout."""
        pm = ProcessManager()
        pm.register_task("task-001", TaskType.SHELL)
        pm.start_task("task-001")

        task = await pm.wait_for_task("task-001", timeout=0.05)
        assert task is not None
        assert task.status == TaskStatus.RUNNING  # Still running

    @pytest.mark.asyncio
    async def test_wait_for_nonexistent_task(self):
        """Test waiting for nonexistent task."""
        pm = ProcessManager()
        task = await pm.wait_for_task("nonexistent", timeout=0.1)
        assert task is None

    def test_remove_task(self):
        """Test removing a task."""
        pm = ProcessManager()
        pm.register_task("task-001", TaskType.SHELL)
        result = pm.remove_task("task-001")

        assert result is True
        assert pm.get_task("task-001") is None

    def test_remove_nonexistent_task(self):
        """Test removing nonexistent task."""
        pm = ProcessManager()
        result = pm.remove_task("nonexistent")
        assert result is False


class TestKillShellTool:
    """Tests for KillShellTool class."""

    def test_tool_attributes(self):
        """Test tool has required attributes."""
        tool = KillShellTool()
        assert tool.name == "kill_shell"
        assert tool.description != ""
        assert tool.danger_level == DangerLevel.MEDIUM
        assert tool.category == ToolCategory.SYSTEM

    def test_get_schema(self):
        """Test schema generation."""
        tool = KillShellTool()
        schema = tool.get_schema()
        assert schema["type"] == "object"
        assert "shell_id" in schema["properties"]
        assert "shell_id" in schema["required"]

    def test_get_full_schema(self):
        """Test full schema for LLM."""
        tool = KillShellTool()
        schema = tool.get_full_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "kill_shell"

    @pytest.mark.asyncio
    async def test_execute_missing_shell_id(self):
        """Test error when shell_id is missing."""
        tool = KillShellTool()
        result = await tool.execute(shell_id="")

        assert result.success is False
        assert "required" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_nonexistent_shell(self):
        """Test error when shell doesn't exist."""
        pm = ProcessManager()
        tool = KillShellTool(process_manager=pm)

        result = await tool.execute(shell_id="nonexistent")
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_wrong_task_type(self):
        """Test error when task is not a shell."""
        pm = ProcessManager()
        pm.register_task("agent-001", TaskType.AGENT)
        tool = KillShellTool(process_manager=pm)

        result = await tool.execute(shell_id="agent-001")
        assert result.success is False
        assert "not a shell" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_already_terminated(self):
        """Test killing already terminated shell."""
        pm = ProcessManager()
        pm.register_task("shell-001", TaskType.SHELL)
        pm.complete_task("shell-001", output="Done")
        tool = KillShellTool(process_manager=pm)

        result = await tool.execute(shell_id="shell-001")
        assert result.success is True
        assert "already terminated" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_kill_running_shell(self):
        """Test killing a running shell."""
        pm = ProcessManager()
        pm.register_task("shell-001", TaskType.SHELL)
        pm.start_task("shell-001")
        tool = KillShellTool(process_manager=pm)

        result = await tool.execute(shell_id="shell-001")
        assert result.success is True
        assert "killed successfully" in result.output.lower()
        assert pm.get_task("shell-001").status == TaskStatus.CANCELLED

    def test_process_manager_property(self):
        """Test process manager property."""
        pm = ProcessManager()
        tool = KillShellTool(process_manager=pm)
        assert tool.process_manager is pm

    def test_set_process_manager(self):
        """Test setting process manager."""
        pm1 = ProcessManager()
        pm2 = ProcessManager()
        tool = KillShellTool(process_manager=pm1)
        tool.set_process_manager(pm2)
        assert tool.process_manager is pm2


class TestTaskOutputTool:
    """Tests for TaskOutputTool class."""

    def test_tool_attributes(self):
        """Test tool has required attributes."""
        tool = TaskOutputTool()
        assert tool.name == "task_output"
        assert tool.description != ""
        assert tool.danger_level == DangerLevel.SAFE
        assert tool.category == ToolCategory.SYSTEM

    def test_get_schema(self):
        """Test schema generation."""
        tool = TaskOutputTool()
        schema = tool.get_schema()
        assert schema["type"] == "object"
        assert "task_id" in schema["properties"]
        assert "block" in schema["properties"]
        assert "timeout" in schema["properties"]

    def test_get_full_schema(self):
        """Test full schema for LLM."""
        tool = TaskOutputTool()
        schema = tool.get_full_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "task_output"

    @pytest.mark.asyncio
    async def test_execute_missing_task_id(self):
        """Test error when task_id is missing."""
        tool = TaskOutputTool()
        result = await tool.execute(task_id="")

        assert result.success is False
        assert "required" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_nonexistent_task(self):
        """Test error when task doesn't exist."""
        pm = ProcessManager()
        tool = TaskOutputTool(process_manager=pm)

        result = await tool.execute(task_id="nonexistent")
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_get_completed_output(self):
        """Test getting output from completed task."""
        pm = ProcessManager()
        pm.register_task("task-001", TaskType.SHELL)
        pm.complete_task("task-001", output="Task completed!")
        tool = TaskOutputTool(process_manager=pm)

        result = await tool.execute(task_id="task-001")
        assert result.success is True
        assert "Task completed!" in result.output

    @pytest.mark.asyncio
    async def test_execute_non_blocking(self):
        """Test non-blocking output retrieval."""
        pm = ProcessManager()
        pm.register_task("task-001", TaskType.SHELL)
        pm.start_task("task-001")
        pm.update_output("task-001", "Still running...")
        tool = TaskOutputTool(process_manager=pm)

        result = await tool.execute(task_id="task-001", block=False)
        assert result.success is True
        assert "Still running..." in result.output
        assert result.metadata["status"] == "running"

    @pytest.mark.asyncio
    async def test_execute_blocking_with_completion(self):
        """Test blocking wait for task completion."""
        pm = ProcessManager()
        pm.register_task("task-001", TaskType.SHELL)
        pm.start_task("task-001")
        tool = TaskOutputTool(process_manager=pm)

        async def complete_later():
            await asyncio.sleep(0.05)
            pm.complete_task("task-001", output="Finally done!")

        asyncio.create_task(complete_later())
        result = await tool.execute(task_id="task-001", block=True, timeout=5000)

        assert result.success is True
        assert "Finally done!" in result.output
        assert result.metadata["status"] == "completed"

    @pytest.mark.asyncio
    async def test_execute_timeout_validation(self):
        """Test timeout validation."""
        tool = TaskOutputTool()

        # Negative timeout
        result = await tool.execute(task_id="task-001", timeout=-1)
        assert result.success is False
        assert "non-negative" in result.error.lower()

        # Timeout too large
        result = await tool.execute(task_id="task-001", timeout=700000)
        assert result.success is False
        assert "exceed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_returns_task_info(self):
        """Test result contains task info."""
        pm = ProcessManager()
        pm.register_task("task-001", TaskType.SHELL, metadata={"cmd": "ls"})
        pm.complete_task("task-001", output="file.txt")
        tool = TaskOutputTool(process_manager=pm)

        result = await tool.execute(task_id="task-001")
        assert result.metadata["task_id"] == "task-001"
        assert result.metadata["task_type"] == "shell"
        assert result.metadata["status"] == "completed"
        assert result.metadata["created_at"] is not None

    @pytest.mark.asyncio
    async def test_execute_empty_output(self):
        """Test handling empty output."""
        pm = ProcessManager()
        pm.register_task("task-001", TaskType.AGENT)
        pm.complete_task("task-001")
        tool = TaskOutputTool(process_manager=pm)

        result = await tool.execute(task_id="task-001")
        assert result.success is True
        assert "(no output)" in result.output

    @pytest.mark.asyncio
    async def test_execute_failed_task(self):
        """Test getting output from failed task."""
        pm = ProcessManager()
        pm.register_task("task-001", TaskType.SHELL)
        pm.complete_task("task-001", error="Command failed")
        tool = TaskOutputTool(process_manager=pm)

        result = await tool.execute(task_id="task-001")
        assert result.success is True  # Tool succeeded
        assert result.metadata["status"] == "failed"
        assert result.metadata["error"] == "Command failed"

    def test_process_manager_property(self):
        """Test process manager property."""
        pm = ProcessManager()
        tool = TaskOutputTool(process_manager=pm)
        assert tool.process_manager is pm

    def test_set_process_manager(self):
        """Test setting process manager."""
        pm1 = ProcessManager()
        pm2 = ProcessManager()
        tool = TaskOutputTool(process_manager=pm1)
        tool.set_process_manager(pm2)
        assert tool.process_manager is pm2

    def test_is_safe(self):
        """Test TaskOutputTool is marked as safe."""
        tool = TaskOutputTool()
        assert tool.is_safe


class TestToolsShareProcessManager:
    """Tests for tools sharing process manager."""

    @pytest.mark.asyncio
    async def test_kill_and_output_share_state(self):
        """Test KillShellTool and TaskOutputTool share state."""
        pm = ProcessManager()
        kill_tool = KillShellTool(process_manager=pm)
        output_tool = TaskOutputTool(process_manager=pm)

        # Register and start a shell
        pm.register_task("shell-001", TaskType.SHELL)
        pm.start_task("shell-001")
        pm.update_output("shell-001", "Running...")

        # Get output
        result = await output_tool.execute(task_id="shell-001", block=False)
        assert result.success
        assert result.metadata["status"] == "running"

        # Kill it
        result = await kill_tool.execute(shell_id="shell-001")
        assert result.success

        # Get output again - should show cancelled
        result = await output_tool.execute(task_id="shell-001")
        assert result.success
        assert result.metadata["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_multiple_tasks(self):
        """Test managing multiple tasks."""
        pm = ProcessManager()
        kill_tool = KillShellTool(process_manager=pm)
        output_tool = TaskOutputTool(process_manager=pm)

        # Register multiple tasks
        pm.register_task("shell-001", TaskType.SHELL)
        pm.register_task("shell-002", TaskType.SHELL)
        pm.register_task("agent-001", TaskType.AGENT)

        pm.start_task("shell-001")
        pm.complete_task("shell-002", output="Shell 2 done")
        pm.start_task("agent-001")

        # Get shell-002 output
        result = await output_tool.execute(task_id="shell-002")
        assert "Shell 2 done" in result.output

        # Kill shell-001
        result = await kill_tool.execute(shell_id="shell-001")
        assert result.success

        # Agent should still be running
        result = await output_tool.execute(task_id="agent-001", block=False)
        assert result.metadata["status"] == "running"
