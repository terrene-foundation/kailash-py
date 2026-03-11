"""
Unit Tests for SkillTool (Tier 1)

Tests the SkillTool which invokes registered skills dynamically.
Part of TODO-203 Task/Skill Tools implementation.

Coverage:
- Tool attributes and schema
- Skill invocation and content loading
- Progressive disclosure
- Additional file loading
- Event emission
- Error handling
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from kaizen.execution.events import EventType, SkillCompleteEvent, SkillInvokeEvent
from kaizen.execution.subagent_result import SkillResult
from kaizen.tools.native.skill_tool import SkillTool
from kaizen.tools.types import DangerLevel, ToolCategory


@dataclass
class MockSkill:
    """Mock skill for testing."""

    name: str
    description: str = "Test skill"
    location: str = "/path/to/skill"
    source: str = "test"
    is_loaded: bool = False
    skill_content: Optional[str] = None
    additional_files: Dict[str, str] = field(default_factory=dict)


class MockAdapter:
    """Mock LocalKaizenAdapter for testing."""

    def __init__(
        self,
        skills: Optional[Dict[str, MockSkill]] = None,
    ):
        self._skills = skills or {
            "python-patterns": MockSkill(
                name="python-patterns",
                description="Python design patterns",
                skill_content="# Python Patterns\n\nUse these patterns...",
            ),
            "testing-guide": MockSkill(
                name="testing-guide",
                description="Testing best practices",
                skill_content="# Testing Guide\n\nAlways test...",
                additional_files={
                    "examples.md": "# Examples\n\nHere are examples...",
                    "tips.md": "# Tips\n\nRemember to...",
                },
            ),
        }

    def get_skill(self, name: str) -> Optional[MockSkill]:
        return self._skills.get(name)

    def list_skills(self) -> List[str]:
        return list(self._skills.keys())

    def load_skill_content(self, skill: MockSkill) -> MockSkill:
        """Simulate loading skill content."""
        skill.is_loaded = True
        return skill


class TestSkillToolAttributes:
    """Test SkillTool attributes and schema."""

    def test_tool_name(self):
        """Test tool has correct name."""
        tool = SkillTool()
        assert tool.name == "skill"

    def test_tool_description(self):
        """Test tool has meaningful description."""
        tool = SkillTool()
        assert "skill" in tool.description.lower()
        assert "knowledge" in tool.description.lower()

    def test_danger_level(self):
        """Test tool has SAFE danger level."""
        tool = SkillTool()
        assert tool.danger_level == DangerLevel.SAFE

    def test_category(self):
        """Test tool has DATA category."""
        tool = SkillTool()
        assert tool.category == ToolCategory.DATA

    def test_get_schema(self):
        """Test schema is correct."""
        tool = SkillTool()
        schema = tool.get_schema()

        assert schema["type"] == "object"
        assert "skill_name" in schema["properties"]
        assert "load_additional_files" in schema["properties"]

        # skill_name is required
        assert "skill_name" in schema["required"]

        # load_additional_files has default
        assert schema["properties"]["load_additional_files"].get("default") is True

    def test_initialization_defaults(self):
        """Test default initialization values."""
        tool = SkillTool()

        assert tool._adapter is None
        assert tool._agent_id.startswith("agent_")
        assert tool._session_id.startswith("session_")
        assert tool._on_event is None

    def test_initialization_with_params(self):
        """Test initialization with custom parameters."""
        adapter = MockAdapter()
        callback = MagicMock()

        tool = SkillTool(
            adapter=adapter,
            agent_id="agent-123",
            on_event=callback,
            session_id="session-456",
        )

        assert tool._adapter is adapter
        assert tool._agent_id == "agent-123"
        assert tool._on_event is callback
        assert tool._session_id == "session-456"


class TestSkillToolExecution:
    """Test SkillTool execution."""

    @pytest.mark.asyncio
    async def test_execute_without_adapter_returns_error(self):
        """Test execution without adapter returns error."""
        tool = SkillTool()

        result = await tool.execute(skill_name="python-patterns")

        assert result.success is False
        assert "adapter" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_unknown_skill_returns_error(self):
        """Test execution with unknown skill returns error."""
        adapter = MockAdapter()
        tool = SkillTool(adapter=adapter)

        result = await tool.execute(skill_name="unknown-skill")

        assert result.success is False
        assert "not found" in result.error.lower()
        assert "python-patterns" in result.error  # Lists available

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Test successful skill invocation."""
        adapter = MockAdapter()
        tool = SkillTool(adapter=adapter)

        result = await tool.execute(skill_name="python-patterns")

        assert result.success is True
        assert result.output is not None
        assert isinstance(result.output, SkillResult)
        assert result.output.success is True
        assert "Python Patterns" in result.output.content

    @pytest.mark.asyncio
    async def test_execute_returns_skill_metadata(self):
        """Test execution returns skill metadata."""
        adapter = MockAdapter()
        tool = SkillTool(adapter=adapter)

        result = await tool.execute(skill_name="python-patterns")

        assert result.success is True
        skill_result = result.output
        assert skill_result.skill_name == "python-patterns"
        assert skill_result.description == "Python design patterns"
        assert skill_result.location == "/path/to/skill"
        assert skill_result.source == "test"

    @pytest.mark.asyncio
    async def test_execute_with_additional_files(self):
        """Test execution loads additional files."""
        adapter = MockAdapter()
        tool = SkillTool(adapter=adapter)

        result = await tool.execute(
            skill_name="testing-guide",
            load_additional_files=True,
        )

        assert result.success is True
        skill_result = result.output
        assert skill_result.has_additional_files
        assert "examples.md" in skill_result.additional_files
        assert "tips.md" in skill_result.additional_files

    @pytest.mark.asyncio
    async def test_execute_without_additional_files(self):
        """Test execution skips additional files when requested."""
        adapter = MockAdapter()
        tool = SkillTool(adapter=adapter)

        result = await tool.execute(
            skill_name="testing-guide",
            load_additional_files=False,
        )

        assert result.success is True
        skill_result = result.output
        # Should not load additional files
        assert not skill_result.has_additional_files

    @pytest.mark.asyncio
    async def test_execute_metadata_includes_content_size(self):
        """Test result metadata includes content size."""
        adapter = MockAdapter()
        tool = SkillTool(adapter=adapter)

        result = await tool.execute(skill_name="python-patterns")

        assert result.success is True
        assert "content_size" in result.metadata
        assert result.metadata["content_size"] > 0

    @pytest.mark.asyncio
    async def test_execute_metadata_includes_additional_files_list(self):
        """Test result metadata includes additional files list."""
        adapter = MockAdapter()
        tool = SkillTool(adapter=adapter)

        result = await tool.execute(skill_name="testing-guide")

        assert result.success is True
        assert "additional_files" in result.metadata
        assert "examples.md" in result.metadata["additional_files"]
        assert "tips.md" in result.metadata["additional_files"]


class TestSkillToolListAndInfo:
    """Test SkillTool list and info methods."""

    def test_list_skills_without_adapter(self):
        """Test list_skills returns empty without adapter."""
        tool = SkillTool()

        result = tool.list_skills()

        assert result == []

    def test_list_skills_with_adapter(self):
        """Test list_skills returns available skills."""
        adapter = MockAdapter()
        tool = SkillTool(adapter=adapter)

        result = tool.list_skills()

        assert "python-patterns" in result
        assert "testing-guide" in result

    def test_get_skill_info_without_adapter(self):
        """Test get_skill_info returns None without adapter."""
        tool = SkillTool()

        result = tool.get_skill_info("python-patterns")

        assert result is None

    def test_get_skill_info_unknown_skill(self):
        """Test get_skill_info returns None for unknown skill."""
        adapter = MockAdapter()
        tool = SkillTool(adapter=adapter)

        result = tool.get_skill_info("unknown-skill")

        assert result is None

    def test_get_skill_info_returns_metadata(self):
        """Test get_skill_info returns skill metadata."""
        adapter = MockAdapter()
        tool = SkillTool(adapter=adapter)

        result = tool.get_skill_info("python-patterns")

        assert result is not None
        assert result["name"] == "python-patterns"
        assert result["description"] == "Python design patterns"
        assert result["location"] == "/path/to/skill"
        assert result["source"] == "test"
        assert "is_loaded" in result


class TestSkillToolEventEmission:
    """Test SkillTool event emission."""

    @pytest.mark.asyncio
    async def test_emits_invoke_event(self):
        """Test execution emits SkillInvokeEvent."""
        events = []

        async def capture_event(event):
            events.append(event)

        adapter = MockAdapter()
        tool = SkillTool(
            adapter=adapter,
            on_event=capture_event,
            agent_id="agent-123",
        )

        await tool.execute(skill_name="python-patterns")

        invoke_events = [e for e in events if isinstance(e, SkillInvokeEvent)]
        assert len(invoke_events) == 1

        invoke_event = invoke_events[0]
        assert invoke_event.skill_name == "python-patterns"
        assert invoke_event.agent_id == "agent-123"
        assert invoke_event.event_type == EventType.SKILL_INVOKE

    @pytest.mark.asyncio
    async def test_emits_complete_event_on_success(self):
        """Test execution emits SkillCompleteEvent on success."""
        events = []

        async def capture_event(event):
            events.append(event)

        adapter = MockAdapter()
        tool = SkillTool(adapter=adapter, on_event=capture_event)

        await tool.execute(skill_name="python-patterns")

        complete_events = [e for e in events if isinstance(e, SkillCompleteEvent)]
        assert len(complete_events) == 1

        complete_event = complete_events[0]
        assert complete_event.skill_name == "python-patterns"
        assert complete_event.success is True
        assert complete_event.content_loaded is True
        assert complete_event.content_size > 0
        assert complete_event.event_type == EventType.SKILL_COMPLETE

    @pytest.mark.asyncio
    async def test_emits_complete_event_on_error(self):
        """Test execution emits SkillCompleteEvent with error on failure."""
        events = []

        async def capture_event(event):
            events.append(event)

        adapter = MockAdapter()
        tool = SkillTool(adapter=adapter, on_event=capture_event)

        await tool.execute(skill_name="unknown-skill")

        complete_events = [e for e in events if isinstance(e, SkillCompleteEvent)]
        assert len(complete_events) == 1

        complete_event = complete_events[0]
        assert complete_event.success is False
        assert complete_event.error_message is not None

    @pytest.mark.asyncio
    async def test_sync_event_callback_works(self):
        """Test sync event callbacks work correctly."""
        events = []

        def sync_callback(event):
            events.append(event)

        adapter = MockAdapter()
        tool = SkillTool(adapter=adapter, on_event=sync_callback)

        await tool.execute(skill_name="python-patterns")

        assert len(events) >= 2  # At least invoke and complete

    @pytest.mark.asyncio
    async def test_event_callback_error_doesnt_break_execution(self):
        """Test that event callback errors don't break execution."""

        def bad_callback(event):
            raise ValueError("Callback error")

        adapter = MockAdapter()
        tool = SkillTool(adapter=adapter, on_event=bad_callback)

        result = await tool.execute(skill_name="python-patterns")

        # Execution should still succeed despite callback error
        assert result.success is True


class TestSkillToolErrorHandling:
    """Test SkillTool error handling."""

    @pytest.mark.asyncio
    async def test_handles_load_content_exception(self):
        """Test handles exceptions during content loading."""

        class FailingAdapter(MockAdapter):
            def load_skill_content(self, skill):
                raise RuntimeError("Failed to load content")

        adapter = FailingAdapter()
        tool = SkillTool(adapter=adapter)

        result = await tool.execute(skill_name="python-patterns")

        assert result.success is False
        assert "failed to load" in result.error.lower()

    @pytest.mark.asyncio
    async def test_error_result_includes_skill_result(self):
        """Test error result includes SkillResult in metadata."""

        class FailingAdapter(MockAdapter):
            def load_skill_content(self, skill):
                raise ValueError("Load error")

        adapter = FailingAdapter()
        tool = SkillTool(adapter=adapter)

        result = await tool.execute(skill_name="python-patterns")

        assert result.success is False
        assert "skill_result" in result.metadata

    @pytest.mark.asyncio
    async def test_handles_empty_content(self):
        """Test handles skill with empty content."""
        skills = {
            "empty-skill": MockSkill(
                name="empty-skill",
                skill_content="",
            ),
        }
        adapter = MockAdapter(skills=skills)
        tool = SkillTool(adapter=adapter)

        result = await tool.execute(skill_name="empty-skill")

        assert result.success is True
        skill_result = result.output
        assert skill_result.content == ""

    @pytest.mark.asyncio
    async def test_handles_none_content(self):
        """Test handles skill with None content."""
        skills = {
            "null-skill": MockSkill(
                name="null-skill",
                skill_content=None,
            ),
        }
        adapter = MockAdapter(skills=skills)
        tool = SkillTool(adapter=adapter)

        result = await tool.execute(skill_name="null-skill")

        assert result.success is True
        skill_result = result.output
        assert skill_result.content == ""


class TestSkillToolProgressiveDisclosure:
    """Test SkillTool progressive disclosure behavior."""

    @pytest.mark.asyncio
    async def test_metadata_available_before_content(self):
        """Test skill metadata is available without loading content."""
        adapter = MockAdapter()
        tool = SkillTool(adapter=adapter)

        # Get info without executing (no content load)
        info = tool.get_skill_info("python-patterns")

        assert info is not None
        assert info["name"] == "python-patterns"
        assert info["description"] == "Python design patterns"
        assert info["is_loaded"] is False

    @pytest.mark.asyncio
    async def test_content_loaded_on_execute(self):
        """Test content is loaded during execute."""
        adapter = MockAdapter()
        tool = SkillTool(adapter=adapter)

        # Before execute, skill is not loaded
        skill_before = adapter.get_skill("python-patterns")
        assert skill_before.is_loaded is False

        # Execute loads the skill
        result = await tool.execute(skill_name="python-patterns")

        assert result.success is True
        # After execute, skill is loaded
        skill_after = adapter.get_skill("python-patterns")
        assert skill_after.is_loaded is True


class TestSkillToolRegistryIntegration:
    """Test SkillTool integration with KaizenToolRegistry."""

    def test_register_in_registry(self):
        """Test SkillTool can be registered in registry."""
        from kaizen.tools.native.registry import KaizenToolRegistry
        from kaizen.tools.native.skill_tool import SkillTool as FreshSkillTool

        registry = KaizenToolRegistry()
        tool = FreshSkillTool()

        registry.register(tool)

        assert "skill" in registry
        assert registry.get_tool("skill") is tool

    def test_register_defaults_agent_category(self):
        """Test register_defaults includes agent tools."""
        from kaizen.tools.native.registry import KaizenToolRegistry

        registry = KaizenToolRegistry()
        count = registry.register_defaults(categories=["agent"])

        assert count == 2  # TaskTool and SkillTool
        assert "skill" in registry
        assert "task" in registry

    @pytest.mark.asyncio
    async def test_execute_via_registry(self):
        """Test executing SkillTool through registry."""
        from kaizen.tools.native.registry import KaizenToolRegistry
        from kaizen.tools.native.skill_tool import SkillTool as FreshSkillTool

        adapter = MockAdapter()
        tool = FreshSkillTool(adapter=adapter)

        registry = KaizenToolRegistry()
        registry.register(tool)

        result = await registry.execute(
            "skill",
            {"skill_name": "python-patterns"},
        )

        assert result.success is True

    def test_tool_info_in_registry(self):
        """Test SkillTool info is available in registry."""
        from kaizen.tools.native.registry import KaizenToolRegistry
        from kaizen.tools.native.skill_tool import SkillTool as FreshSkillTool

        registry = KaizenToolRegistry()
        tool = FreshSkillTool()
        registry.register(tool)

        info = registry.get_tool_info()
        skill_info = next(i for i in info if i["name"] == "skill")

        assert skill_info["danger_level"] == "safe"
        assert skill_info["category"] == "data"
        assert skill_info["requires_approval"] is False

    def test_skill_tool_is_safe(self):
        """Test SkillTool is classified as safe."""
        from kaizen.tools.native.registry import KaizenToolRegistry
        from kaizen.tools.native.skill_tool import SkillTool as FreshSkillTool

        registry = KaizenToolRegistry()
        tool = FreshSkillTool()
        registry.register(tool)

        safe_tools = registry.list_safe_tools()
        assert "skill" in safe_tools

    def test_task_tool_not_in_safe_list(self):
        """Test TaskTool is NOT in safe tools list."""
        from kaizen.tools.native.registry import KaizenToolRegistry
        from kaizen.tools.native.skill_tool import SkillTool as FreshSkillTool
        from kaizen.tools.native.task_tool import TaskTool as FreshTaskTool

        registry = KaizenToolRegistry()
        registry.register(FreshTaskTool())
        registry.register(FreshSkillTool())

        safe_tools = registry.list_safe_tools()
        assert "skill" in safe_tools
        assert "task" not in safe_tools  # MEDIUM danger level


class TestSkillToolSerialization:
    """Test SkillResult serialization."""

    @pytest.mark.asyncio
    async def test_skill_result_to_dict(self):
        """Test SkillResult can be serialized to dict."""
        adapter = MockAdapter()
        tool = SkillTool(adapter=adapter)

        result = await tool.execute(skill_name="python-patterns")

        assert result.success is True
        skill_result = result.output

        data = skill_result.to_dict()

        assert data["skill_name"] == "python-patterns"
        assert data["success"] is True
        assert "content" in data
        assert "description" in data
        assert "additional_files" in data
