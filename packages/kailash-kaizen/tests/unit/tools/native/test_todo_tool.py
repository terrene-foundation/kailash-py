"""
Unit Tests for TodoWriteTool (Tier 1)

Tests the todo list management tool for autonomous agents.
Part of TODO-207 ClaudeCodeAgent Full Tool Parity.
"""

import pytest

from kaizen.tools.native.todo_tool import TodoItem, TodoList, TodoStatus, TodoWriteTool
from kaizen.tools.types import DangerLevel, ToolCategory


class TestTodoStatus:
    """Tests for TodoStatus enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert TodoStatus.PENDING.value == "pending"
        assert TodoStatus.IN_PROGRESS.value == "in_progress"
        assert TodoStatus.COMPLETED.value == "completed"

    def test_status_from_string(self):
        """Test creating status from string."""
        assert TodoStatus("pending") == TodoStatus.PENDING
        assert TodoStatus("in_progress") == TodoStatus.IN_PROGRESS
        assert TodoStatus("completed") == TodoStatus.COMPLETED

    def test_invalid_status_raises(self):
        """Test invalid status raises ValueError."""
        with pytest.raises(ValueError):
            TodoStatus("invalid")


class TestTodoItem:
    """Tests for TodoItem dataclass."""

    def test_create_item(self):
        """Test creating a todo item."""
        item = TodoItem(
            content="Run tests",
            status=TodoStatus.PENDING,
            active_form="Running tests",
        )
        assert item.content == "Run tests"
        assert item.status == TodoStatus.PENDING
        assert item.active_form == "Running tests"
        assert item.created_at != ""
        assert item.updated_at != ""

    def test_create_item_with_string_status(self):
        """Test creating item with string status."""
        item = TodoItem(
            content="Run tests",
            status="pending",  # String instead of enum
            active_form="Running tests",
        )
        assert item.status == TodoStatus.PENDING

    def test_to_dict(self):
        """Test serialization to dict."""
        item = TodoItem(
            content="Run tests",
            status=TodoStatus.IN_PROGRESS,
            active_form="Running tests",
        )
        data = item.to_dict()
        assert data["content"] == "Run tests"
        assert data["status"] == "in_progress"
        assert data["activeForm"] == "Running tests"
        assert "created_at" in data
        assert "updated_at" in data

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "content": "Fix bug",
            "status": "completed",
            "activeForm": "Fixing bug",
        }
        item = TodoItem.from_dict(data)
        assert item.content == "Fix bug"
        assert item.status == TodoStatus.COMPLETED
        assert item.active_form == "Fixing bug"

    def test_from_dict_with_active_form_key(self):
        """Test from_dict with snake_case key."""
        data = {
            "content": "Fix bug",
            "status": "completed",
            "active_form": "Fixing bug",  # snake_case
        }
        item = TodoItem.from_dict(data)
        assert item.active_form == "Fixing bug"

    def test_update_status(self):
        """Test updating item status."""
        item = TodoItem(
            content="Run tests",
            status=TodoStatus.PENDING,
            active_form="Running tests",
        )
        original_updated = item.updated_at
        item.update_status(TodoStatus.COMPLETED)
        assert item.status == TodoStatus.COMPLETED
        assert item.updated_at != original_updated


class TestTodoList:
    """Tests for TodoList class."""

    def test_empty_list(self):
        """Test creating empty todo list."""
        todo_list = TodoList()
        assert len(todo_list.items) == 0
        assert todo_list.last_modified != ""

    def test_update_list(self):
        """Test updating todo list with new items."""
        todo_list = TodoList()
        todos = [
            {"content": "Task 1", "status": "pending", "activeForm": "Doing task 1"},
            {
                "content": "Task 2",
                "status": "in_progress",
                "activeForm": "Doing task 2",
            },
        ]
        todo_list.update(todos)
        assert len(todo_list.items) == 2
        assert todo_list.items[0].content == "Task 1"
        assert todo_list.items[1].status == TodoStatus.IN_PROGRESS

    def test_add_item(self):
        """Test adding single item."""
        todo_list = TodoList()
        item = TodoItem(
            content="New task",
            status=TodoStatus.PENDING,
            active_form="Working on new task",
        )
        todo_list.add(item)
        assert len(todo_list.items) == 1
        assert todo_list.items[0].content == "New task"

    def test_mark_completed(self):
        """Test marking item as completed."""
        todo_list = TodoList()
        todo_list.update(
            [
                {"content": "Task 1", "status": "pending", "activeForm": "Task 1"},
            ]
        )
        result = todo_list.mark_completed("Task 1")
        assert result is True
        assert todo_list.items[0].status == TodoStatus.COMPLETED

    def test_mark_completed_not_found(self):
        """Test marking nonexistent item."""
        todo_list = TodoList()
        result = todo_list.mark_completed("Nonexistent")
        assert result is False

    def test_mark_in_progress(self):
        """Test marking item as in_progress."""
        todo_list = TodoList()
        todo_list.update(
            [
                {"content": "Task 1", "status": "pending", "activeForm": "Task 1"},
            ]
        )
        result = todo_list.mark_in_progress("Task 1")
        assert result is True
        assert todo_list.items[0].status == TodoStatus.IN_PROGRESS

    def test_get_pending(self):
        """Test getting pending items."""
        todo_list = TodoList()
        todo_list.update(
            [
                {"content": "Task 1", "status": "pending", "activeForm": "Task 1"},
                {"content": "Task 2", "status": "in_progress", "activeForm": "Task 2"},
                {"content": "Task 3", "status": "completed", "activeForm": "Task 3"},
            ]
        )
        pending = todo_list.get_pending()
        assert len(pending) == 1
        assert pending[0].content == "Task 1"

    def test_get_in_progress(self):
        """Test getting in_progress items."""
        todo_list = TodoList()
        todo_list.update(
            [
                {"content": "Task 1", "status": "pending", "activeForm": "Task 1"},
                {"content": "Task 2", "status": "in_progress", "activeForm": "Task 2"},
            ]
        )
        in_progress = todo_list.get_in_progress()
        assert len(in_progress) == 1
        assert in_progress[0].content == "Task 2"

    def test_get_completed(self):
        """Test getting completed items."""
        todo_list = TodoList()
        todo_list.update(
            [
                {"content": "Task 1", "status": "completed", "activeForm": "Task 1"},
                {"content": "Task 2", "status": "completed", "activeForm": "Task 2"},
            ]
        )
        completed = todo_list.get_completed()
        assert len(completed) == 2

    def test_get_current(self):
        """Test getting current in_progress item."""
        todo_list = TodoList()
        todo_list.update(
            [
                {"content": "Task 1", "status": "pending", "activeForm": "Task 1"},
                {"content": "Task 2", "status": "in_progress", "activeForm": "Task 2"},
            ]
        )
        current = todo_list.get_current()
        assert current is not None
        assert current.content == "Task 2"

    def test_get_current_none(self):
        """Test get_current when no in_progress items."""
        todo_list = TodoList()
        todo_list.update(
            [
                {"content": "Task 1", "status": "pending", "activeForm": "Task 1"},
            ]
        )
        current = todo_list.get_current()
        assert current is None

    def test_to_dict(self):
        """Test serialization with summary."""
        todo_list = TodoList()
        todo_list.update(
            [
                {"content": "Task 1", "status": "pending", "activeForm": "Task 1"},
                {"content": "Task 2", "status": "in_progress", "activeForm": "Task 2"},
                {"content": "Task 3", "status": "completed", "activeForm": "Task 3"},
            ]
        )
        data = todo_list.to_dict()
        assert len(data["items"]) == 3
        assert data["summary"]["total"] == 3
        assert data["summary"]["pending"] == 1
        assert data["summary"]["in_progress"] == 1
        assert data["summary"]["completed"] == 1

    def test_to_display_string(self):
        """Test display formatting."""
        todo_list = TodoList()
        todo_list.update(
            [
                {"content": "Task 1", "status": "completed", "activeForm": "Task 1"},
                {"content": "Task 2", "status": "in_progress", "activeForm": "Task 2"},
            ]
        )
        display = todo_list.to_display_string()
        assert "Todo List:" in display
        assert "Task 1" in display
        assert "Task 2" in display
        assert "1/2 completed" in display

    def test_to_display_string_empty(self):
        """Test display for empty list."""
        todo_list = TodoList()
        display = todo_list.to_display_string()
        assert "No tasks" in display


class TestTodoWriteTool:
    """Tests for TodoWriteTool class."""

    def test_tool_attributes(self):
        """Test tool has required attributes."""
        tool = TodoWriteTool()
        assert tool.name == "todo_write"
        assert tool.description != ""
        assert tool.danger_level == DangerLevel.SAFE
        assert tool.category == ToolCategory.CUSTOM

    def test_get_schema(self):
        """Test schema generation."""
        tool = TodoWriteTool()
        schema = tool.get_schema()
        assert schema["type"] == "object"
        assert "todos" in schema["properties"]
        assert schema["properties"]["todos"]["type"] == "array"
        assert "required" in schema

    def test_get_full_schema(self):
        """Test full schema for LLM."""
        tool = TodoWriteTool()
        schema = tool.get_full_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "todo_write"
        assert "parameters" in schema["function"]

    @pytest.mark.asyncio
    async def test_execute_basic(self):
        """Test basic execute."""
        tool = TodoWriteTool()
        result = await tool.execute(
            todos=[
                {"content": "Task 1", "status": "pending", "activeForm": "Task 1"},
            ]
        )
        assert result.success is True
        assert "1 items" in result.output

    @pytest.mark.asyncio
    async def test_execute_multiple_items(self):
        """Test execute with multiple items."""
        tool = TodoWriteTool()
        result = await tool.execute(
            todos=[
                {"content": "Task 1", "status": "completed", "activeForm": "Task 1"},
                {"content": "Task 2", "status": "in_progress", "activeForm": "Task 2"},
                {"content": "Task 3", "status": "pending", "activeForm": "Task 3"},
            ]
        )
        assert result.success is True
        assert "3 items" in result.output
        assert "1 completed" in result.output
        assert "1 in progress" in result.output
        assert "1 pending" in result.output

    @pytest.mark.asyncio
    async def test_execute_empty_list_fails(self):
        """Test execute with empty list fails."""
        tool = TodoWriteTool()
        result = await tool.execute(todos=[])
        assert result.success is False
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_missing_content_fails(self):
        """Test execute with missing content fails."""
        tool = TodoWriteTool()
        result = await tool.execute(
            todos=[
                {"status": "pending", "activeForm": "Task 1"},  # Missing content
            ]
        )
        assert result.success is False
        assert "content" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_missing_status_fails(self):
        """Test execute with missing status fails."""
        tool = TodoWriteTool()
        result = await tool.execute(
            todos=[
                {"content": "Task 1", "activeForm": "Task 1"},  # Missing status
            ]
        )
        assert result.success is False
        assert "status" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_missing_activeForm_fails(self):
        """Test execute with missing activeForm fails."""
        tool = TodoWriteTool()
        result = await tool.execute(
            todos=[
                {"content": "Task 1", "status": "pending"},  # Missing activeForm
            ]
        )
        assert result.success is False
        assert "activeForm" in result.error

    @pytest.mark.asyncio
    async def test_execute_empty_content_fails(self):
        """Test execute with empty content fails."""
        tool = TodoWriteTool()
        result = await tool.execute(
            todos=[
                {"content": "   ", "status": "pending", "activeForm": "Task"},
            ]
        )
        assert result.success is False
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_invalid_status_fails(self):
        """Test execute with invalid status fails."""
        tool = TodoWriteTool()
        result = await tool.execute(
            todos=[
                {"content": "Task 1", "status": "invalid", "activeForm": "Task 1"},
            ]
        )
        assert result.success is False
        assert "invalid status" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_warns_multiple_in_progress(self):
        """Test warning for multiple in_progress items."""
        tool = TodoWriteTool()
        result = await tool.execute(
            todos=[
                {"content": "Task 1", "status": "in_progress", "activeForm": "Task 1"},
                {"content": "Task 2", "status": "in_progress", "activeForm": "Task 2"},
            ]
        )
        assert result.success is True
        assert "Warning" in result.output
        assert "2 tasks are in_progress" in result.output

    @pytest.mark.asyncio
    async def test_execute_updates_todo_list(self):
        """Test execute updates internal todo list."""
        tool = TodoWriteTool()
        await tool.execute(
            todos=[
                {"content": "Task 1", "status": "pending", "activeForm": "Task 1"},
            ]
        )
        assert len(tool.todo_list.items) == 1
        assert tool.todo_list.items[0].content == "Task 1"

    @pytest.mark.asyncio
    async def test_execute_replaces_todo_list(self):
        """Test execute replaces entire todo list."""
        tool = TodoWriteTool()
        await tool.execute(
            todos=[
                {"content": "Task 1", "status": "pending", "activeForm": "Task 1"},
            ]
        )
        await tool.execute(
            todos=[
                {"content": "Task 2", "status": "pending", "activeForm": "Task 2"},
            ]
        )
        assert len(tool.todo_list.items) == 1
        assert tool.todo_list.items[0].content == "Task 2"

    @pytest.mark.asyncio
    async def test_execute_returns_metadata(self):
        """Test execute returns metadata."""
        tool = TodoWriteTool()
        result = await tool.execute(
            todos=[
                {"content": "Task 1", "status": "pending", "activeForm": "Task 1"},
                {"content": "Task 2", "status": "completed", "activeForm": "Task 2"},
            ]
        )
        assert "todo_summary" in result.metadata
        assert result.metadata["todo_summary"]["total"] == 2
        assert "items" in result.metadata

    @pytest.mark.asyncio
    async def test_execute_trims_whitespace(self):
        """Test execute trims whitespace from content."""
        tool = TodoWriteTool()
        result = await tool.execute(
            todos=[
                {
                    "content": "  Task 1  ",
                    "status": "pending",
                    "activeForm": "  Task 1  ",
                },
            ]
        )
        assert result.success is True
        assert tool.todo_list.items[0].content == "Task 1"
        assert tool.todo_list.items[0].active_form == "Task 1"

    @pytest.mark.asyncio
    async def test_on_change_callback(self):
        """Test change callback is called."""
        changes = []

        def on_change(todo_list):
            changes.append(todo_list.to_dict())

        tool = TodoWriteTool(on_change=on_change)
        await tool.execute(
            todos=[
                {"content": "Task 1", "status": "pending", "activeForm": "Task 1"},
            ]
        )
        assert len(changes) == 1
        assert changes[0]["summary"]["total"] == 1

    @pytest.mark.asyncio
    async def test_on_change_callback_error_handled(self):
        """Test callback errors don't break execution."""

        def on_change(todo_list):
            raise ValueError("Callback error")

        tool = TodoWriteTool(on_change=on_change)
        result = await tool.execute(
            todos=[
                {"content": "Task 1", "status": "pending", "activeForm": "Task 1"},
            ]
        )
        # Should still succeed despite callback error
        assert result.success is True

    def test_get_display(self):
        """Test get_display returns formatted string."""
        tool = TodoWriteTool()
        tool._todo_list.update(
            [
                {"content": "Task 1", "status": "in_progress", "activeForm": "Task 1"},
            ]
        )
        display = tool.get_display()
        assert "Task 1" in display
        assert "Todo List:" in display

    def test_clear(self):
        """Test clear removes all todos."""
        tool = TodoWriteTool()
        tool._todo_list.update(
            [
                {"content": "Task 1", "status": "pending", "activeForm": "Task 1"},
            ]
        )
        tool.clear()
        assert len(tool.todo_list.items) == 0

    def test_set_session(self):
        """Test setting session ID."""
        tool = TodoWriteTool()
        tool.set_session("session-123")
        assert tool._session_id == "session-123"

    def test_is_safe(self):
        """Test tool is marked as safe."""
        tool = TodoWriteTool()
        assert tool.is_safe() is True

    def test_requires_approval(self):
        """Test tool doesn't require approval."""
        tool = TodoWriteTool()
        assert tool.requires_approval() is False

    @pytest.mark.asyncio
    async def test_execute_with_timing(self):
        """Test execute_with_timing adds metadata."""
        tool = TodoWriteTool()
        result = await tool.execute_with_timing(
            todos=[
                {"content": "Task 1", "status": "pending", "activeForm": "Task 1"},
            ]
        )
        assert "execution_time_ms" in result.metadata
        assert result.metadata["execution_time_ms"] >= 0
