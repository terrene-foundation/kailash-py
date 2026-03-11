"""
Unit Tests for Native Tool Registry (Tier 1)

Tests the KaizenToolRegistry class for tool management, discovery,
and execution.

Coverage:
- Tool registration and validation
- Category-based registration
- Tool discovery and listing
- Schema generation for LLM
- Tool execution and error handling
"""

import pytest

from kaizen.tools.native.base import BaseTool, NativeToolResult
from kaizen.tools.native.registry import KaizenToolRegistry
from kaizen.tools.types import DangerLevel, ToolCategory


def create_mock_tool(name: str = "mock_tool", danger: DangerLevel = DangerLevel.SAFE):
    """Factory function to create mock tools with unique class definitions."""

    class DynamicMockTool(BaseTool):
        description = "A mock tool for testing"
        category = ToolCategory.CUSTOM

        async def execute(self, text: str = "") -> NativeToolResult:
            return NativeToolResult.from_success(f"Processed: {text}")

        def get_schema(self):
            return {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Input text"},
                },
                "required": [],
            }

    DynamicMockTool.name = name
    DynamicMockTool.danger_level = danger
    return DynamicMockTool()


# For backward compatibility in tests
def MockTool(name: str = "mock_tool", danger: DangerLevel = DangerLevel.SAFE):
    """Create a mock tool with given name and danger level."""
    return create_mock_tool(name, danger)


class TestKaizenToolRegistryBasics:
    """Test basic registry operations."""

    def test_create_empty_registry(self):
        """Test creating an empty registry."""
        registry = KaizenToolRegistry()

        assert len(registry) == 0
        assert list(registry) == []

    def test_register_single_tool(self):
        """Test registering a single tool."""
        registry = KaizenToolRegistry()
        tool = MockTool("test_tool")

        registry.register(tool)

        assert len(registry) == 1
        assert "test_tool" in registry
        assert registry.has_tool("test_tool")

    def test_register_duplicate_raises_error(self):
        """Test registering duplicate tool name raises ValueError."""
        registry = KaizenToolRegistry()
        tool1 = MockTool("duplicate")
        tool2 = MockTool("duplicate")

        registry.register(tool1)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(tool2)

    def test_register_non_tool_raises_error(self):
        """Test registering non-BaseTool raises TypeError."""
        registry = KaizenToolRegistry()

        with pytest.raises(TypeError, match="Expected BaseTool"):
            registry.register("not a tool")

        with pytest.raises(TypeError, match="Expected BaseTool"):
            registry.register({"name": "fake_tool"})

    def test_unregister_tool(self):
        """Test unregistering a tool."""
        registry = KaizenToolRegistry()
        tool = MockTool("removable")
        registry.register(tool)

        assert "removable" in registry

        result = registry.unregister("removable")

        assert result is True
        assert "removable" not in registry

    def test_unregister_nonexistent_returns_false(self):
        """Test unregistering nonexistent tool returns False."""
        registry = KaizenToolRegistry()

        result = registry.unregister("does_not_exist")

        assert result is False

    def test_get_tool(self):
        """Test getting a tool by name."""
        registry = KaizenToolRegistry()
        tool = MockTool("gettable")
        registry.register(tool)

        retrieved = registry.get_tool("gettable")

        assert retrieved is tool

    def test_get_nonexistent_returns_none(self):
        """Test getting nonexistent tool returns None."""
        registry = KaizenToolRegistry()

        result = registry.get_tool("missing")

        assert result is None


class TestKaizenToolRegistryListing:
    """Test registry listing operations."""

    def test_list_tools_empty(self):
        """Test listing tools on empty registry."""
        registry = KaizenToolRegistry()

        tools = registry.list_tools()

        assert tools == []

    def test_list_tools_sorted(self):
        """Test tools are listed in sorted order."""
        registry = KaizenToolRegistry()
        registry.register(MockTool("zebra"))
        registry.register(MockTool("alpha"))
        registry.register(MockTool("middle"))

        tools = registry.list_tools()

        assert tools == ["alpha", "middle", "zebra"]

    def test_list_tools_by_category(self):
        """Test listing tools by category."""

        class FileTool(BaseTool):
            name = "file_tool"
            description = "File tool"
            danger_level = DangerLevel.SAFE
            category = ToolCategory.SYSTEM

            async def execute(self, **kwargs):
                return NativeToolResult.from_success("ok")

            def get_schema(self):
                return {"type": "object", "properties": {}}

        class DataTool(BaseTool):
            name = "data_tool"
            description = "Data tool"
            danger_level = DangerLevel.SAFE
            category = ToolCategory.DATA

            async def execute(self, **kwargs):
                return NativeToolResult.from_success("ok")

            def get_schema(self):
                return {"type": "object", "properties": {}}

        registry = KaizenToolRegistry()
        registry.register(FileTool())
        registry.register(DataTool())

        system_tools = registry.list_tools_by_category(ToolCategory.SYSTEM)
        data_tools = registry.list_tools_by_category(ToolCategory.DATA)
        network_tools = registry.list_tools_by_category(ToolCategory.NETWORK)

        assert system_tools == ["file_tool"]
        assert data_tools == ["data_tool"]
        assert network_tools == []

    def test_list_safe_tools(self):
        """Test listing safe tools only."""
        registry = KaizenToolRegistry()
        registry.register(MockTool("safe_tool", DangerLevel.SAFE))
        registry.register(MockTool("low_tool", DangerLevel.LOW))
        registry.register(MockTool("high_tool", DangerLevel.HIGH))

        safe_tools = registry.list_safe_tools()

        assert "safe_tool" in safe_tools
        assert "low_tool" in safe_tools
        assert "high_tool" not in safe_tools


class TestKaizenToolRegistryDefaults:
    """Test default tool registration.

    Note: These tests use fresh imports within each test to avoid
    test isolation issues when running the full test suite.
    """

    def _get_fresh_registry(self):
        """Get a fresh registry with fresh module imports.

        This ensures consistent BaseTool class across all imports,
        avoiding isinstance failures when modules are reloaded by
        other tests.
        """
        import sys

        # Clear cached modules to force fresh imports
        modules_to_clear = [
            "kaizen.tools.native.base",
            "kaizen.tools.native.registry",
            "kaizen.tools.native.file_tools",
            "kaizen.tools.native.bash_tools",
            "kaizen.tools.native.search_tools",
        ]

        for mod in modules_to_clear:
            if mod in sys.modules:
                del sys.modules[mod]

        # Now import fresh
        from kaizen.tools.native.registry import KaizenToolRegistry

        return KaizenToolRegistry()

    def test_register_defaults_all(self):
        """Test registering all default tools."""
        registry = self._get_fresh_registry()

        count = registry.register_defaults()

        # Should register file (7) + bash (1) + search (2) = 10 tools
        assert count == 10
        assert len(registry) == 10

        # Check file tools exist
        assert "read_file" in registry
        assert "write_file" in registry
        assert "edit_file" in registry
        assert "glob" in registry
        assert "grep" in registry
        assert "list_directory" in registry
        assert "file_exists" in registry

        # Check bash tool exists
        assert "bash_command" in registry

        # Check search tools exist
        assert "web_search" in registry
        assert "web_fetch" in registry

    def test_register_defaults_file_only(self):
        """Test registering only file tools."""
        registry = self._get_fresh_registry()

        count = registry.register_defaults(categories=["file"])

        assert count == 7
        assert "read_file" in registry
        assert "bash_command" not in registry
        assert "web_search" not in registry

    def test_register_defaults_bash_only(self):
        """Test registering only bash tool."""
        registry = self._get_fresh_registry()

        count = registry.register_defaults(categories=["bash"])

        assert count == 1
        assert "bash_command" in registry
        assert "read_file" not in registry

    def test_register_defaults_search_only(self):
        """Test registering only search tools."""
        registry = self._get_fresh_registry()

        count = registry.register_defaults(categories=["search"])

        assert count == 2
        assert "web_search" in registry
        assert "web_fetch" in registry
        assert "read_file" not in registry

    def test_register_defaults_unknown_category_skipped(self):
        """Test unknown category is skipped with warning."""
        registry = self._get_fresh_registry()

        count = registry.register_defaults(categories=["unknown_category"])

        assert count == 0

    def test_register_defaults_idempotent(self):
        """Test registering defaults twice doesn't duplicate."""
        registry = self._get_fresh_registry()

        count1 = registry.register_defaults(categories=["file"])
        count2 = registry.register_defaults(categories=["file"])

        assert count1 == 7
        assert count2 == 0  # Already registered
        assert len(registry) == 7


class TestKaizenToolRegistrySchemas:
    """Test schema generation for LLM integration."""

    def test_get_tool_schemas_empty(self):
        """Test getting schemas from empty registry."""
        registry = KaizenToolRegistry()

        schemas = registry.get_tool_schemas()

        assert schemas == []

    def test_get_tool_schemas_format(self):
        """Test schema format is LLM-compatible."""
        registry = KaizenToolRegistry()
        registry.register(MockTool("schema_tool"))

        schemas = registry.get_tool_schemas()

        assert len(schemas) == 1
        schema = schemas[0]

        assert schema["type"] == "function"
        assert "function" in schema
        assert schema["function"]["name"] == "schema_tool"
        assert "description" in schema["function"]
        assert "parameters" in schema["function"]

    def test_get_tool_schemas_filter_by_category(self):
        """Test filtering schemas by category."""

        class SystemTool(BaseTool):
            name = "sys_tool"
            description = "System"
            danger_level = DangerLevel.LOW
            category = ToolCategory.SYSTEM

            async def execute(self, **kwargs):
                return NativeToolResult.from_success("ok")

            def get_schema(self):
                return {"type": "object", "properties": {}}

        class DataTool(BaseTool):
            name = "dat_tool"
            description = "Data"
            danger_level = DangerLevel.SAFE
            category = ToolCategory.DATA

            async def execute(self, **kwargs):
                return NativeToolResult.from_success("ok")

            def get_schema(self):
                return {"type": "object", "properties": {}}

        registry = KaizenToolRegistry()
        registry.register(SystemTool())
        registry.register(DataTool())

        # All schemas
        all_schemas = registry.get_tool_schemas()
        assert len(all_schemas) == 2

        # System only
        system_schemas = registry.get_tool_schemas(filter_category=ToolCategory.SYSTEM)
        assert len(system_schemas) == 1
        assert system_schemas[0]["function"]["name"] == "sys_tool"

        # Data only
        data_schemas = registry.get_tool_schemas(filter_category=ToolCategory.DATA)
        assert len(data_schemas) == 1
        assert data_schemas[0]["function"]["name"] == "dat_tool"

    def test_get_tool_info(self):
        """Test getting detailed tool info."""
        registry = KaizenToolRegistry()
        registry.register(MockTool("info_tool", DangerLevel.HIGH))

        info = registry.get_tool_info()

        assert len(info) == 1
        tool_info = info[0]

        assert tool_info["name"] == "info_tool"
        assert tool_info["description"] == "A mock tool for testing"
        assert tool_info["category"] == "custom"
        assert tool_info["danger_level"] == "high"
        assert tool_info["requires_approval"] is True

    def test_format_for_prompt(self):
        """Test formatting tools for LLM prompt."""
        registry = KaizenToolRegistry()
        registry.register(MockTool("prompt_tool"))

        formatted = registry.format_for_prompt()

        assert "## Available Tools" in formatted
        assert "prompt_tool" in formatted
        assert "SAFE" in formatted or "safe" in formatted.lower()


class TestKaizenToolRegistryExecution:
    """Test tool execution through registry."""

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Test successful tool execution."""
        registry = KaizenToolRegistry()
        registry.register(MockTool("exec_tool"))

        result = await registry.execute("exec_tool", {"text": "hello"})

        assert result.success is True
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        """Test executing unknown tool returns error."""
        registry = KaizenToolRegistry()

        result = await registry.execute("unknown_tool", {})

        assert result.success is False
        assert "Unknown tool" in result.error
        assert "unknown_tool" in result.error

    @pytest.mark.asyncio
    async def test_execute_with_exception(self):
        """Test execution handles tool exceptions."""

        class FailingTool(BaseTool):
            name = "failing_tool"
            description = "Tool that fails"
            danger_level = DangerLevel.SAFE
            category = ToolCategory.CUSTOM

            async def execute(self, **kwargs):
                raise ValueError("Intentional failure")

            def get_schema(self):
                return {"type": "object", "properties": {}}

        registry = KaizenToolRegistry()
        registry.register(FailingTool())

        result = await registry.execute("failing_tool", {})

        assert result.success is False
        assert "Intentional failure" in result.error


class TestKaizenToolRegistryDunder:
    """Test dunder methods."""

    def test_len(self):
        """Test __len__."""
        registry = KaizenToolRegistry()
        assert len(registry) == 0

        registry.register(MockTool("tool1"))
        assert len(registry) == 1

        registry.register(MockTool("tool2"))
        assert len(registry) == 2

    def test_contains(self):
        """Test __contains__."""
        registry = KaizenToolRegistry()
        registry.register(MockTool("present"))

        assert "present" in registry
        assert "absent" not in registry

    def test_iter(self):
        """Test __iter__."""
        registry = KaizenToolRegistry()
        registry.register(MockTool("c_tool"))
        registry.register(MockTool("a_tool"))
        registry.register(MockTool("b_tool"))

        tools = list(registry)

        # Should be sorted
        assert tools == ["a_tool", "b_tool", "c_tool"]

    def test_repr(self):
        """Test __repr__."""
        registry = KaizenToolRegistry()
        registry.register(MockTool("repr_tool"))

        repr_str = repr(registry)

        assert "KaizenToolRegistry" in repr_str
        assert "1" in repr_str
