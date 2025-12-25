"""Unit tests for MCPClient resources and prompts functionality.

This test file covers:
- list_resources(): List available resources from MCP server
- read_resource(): Read specific resource content
- list_prompts(): List available prompts from MCP server
- get_prompt(): Get prompt with messages

Following TDD approach: Tests written BEFORE implementation.
"""

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from kailash.mcp_server.client import MCPClient


class MockResource:
    """Mock MCP resource object."""

    def __init__(
        self, uri: str, name: str, description: str = "", mime_type: str = "text/plain"
    ):
        self.uri = uri
        self.name = name
        self.description = description
        self.mimeType = mime_type


class MockResourceContent:
    """Mock resource content object."""

    def __init__(self, content_type: str, data: Any):
        if content_type == "text":
            self.text = data
        elif content_type == "blob":
            self.blob = data


class MockResourceResult:
    """Mock result from read_resource call."""

    def __init__(self, contents: List[MockResourceContent]):
        self.contents = contents


class MockPromptArgument:
    """Mock prompt argument object."""

    def __init__(self, name: str, description: str = "", required: bool = False):
        self.name = name
        self.description = description
        self.required = required


class MockPrompt:
    """Mock MCP prompt object."""

    def __init__(
        self,
        name: str,
        description: str = "",
        arguments: List[MockPromptArgument] = None,
    ):
        self.name = name
        self.description = description
        self.arguments = arguments or []


class MockPromptMessage:
    """Mock prompt message object."""

    def __init__(self, role: str, content_text: str):
        self.role = role
        self.content = Mock(text=content_text)


class MockPromptResult:
    """Mock result from get_prompt call."""

    def __init__(self, messages: List[MockPromptMessage]):
        self.messages = messages


class TestListResources:
    """Test list_resources functionality."""

    @pytest.mark.asyncio
    async def test_list_resources_success(self):
        """Test successful resource listing."""
        client = MCPClient()

        # Create mock session
        mock_session = AsyncMock()
        mock_resources = [
            MockResource(
                uri="file:///test/resource1.txt",
                name="Resource 1",
                description="First test resource",
                mime_type="text/plain",
            ),
            MockResource(
                uri="file:///test/resource2.json",
                name="Resource 2",
                description="Second test resource",
                mime_type="application/json",
            ),
        ]

        mock_result = Mock(resources=mock_resources)
        mock_session.list_resources = AsyncMock(return_value=mock_result)

        # Execute
        resources = await client.list_resources(mock_session)

        # Verify
        assert len(resources) == 2
        assert resources[0]["uri"] == "file:///test/resource1.txt"
        assert resources[0]["name"] == "Resource 1"
        assert resources[0]["description"] == "First test resource"
        assert resources[0]["mimeType"] == "text/plain"
        assert resources[1]["uri"] == "file:///test/resource2.json"
        assert resources[1]["name"] == "Resource 2"
        mock_session.list_resources.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_resources_empty(self):
        """Test listing when no resources available."""
        client = MCPClient()

        mock_session = AsyncMock()
        mock_result = Mock(resources=[])
        mock_session.list_resources = AsyncMock(return_value=mock_result)

        resources = await client.list_resources(mock_session)

        assert resources == []
        mock_session.list_resources.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_resources_error_handling(self):
        """Test error handling during resource listing."""
        client = MCPClient()

        mock_session = AsyncMock()
        mock_session.list_resources = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        # Should return empty list on error, not raise
        resources = await client.list_resources(mock_session)

        assert resources == []


class TestReadResource:
    """Test read_resource functionality."""

    @pytest.mark.asyncio
    async def test_read_resource_text_content(self):
        """Test reading resource with text content."""
        client = MCPClient()

        mock_session = AsyncMock()
        mock_contents = [
            MockResourceContent("text", "Line 1 content"),
            MockResourceContent("text", "Line 2 content"),
        ]
        mock_result = MockResourceResult(mock_contents)
        mock_session.read_resource = AsyncMock(return_value=mock_result)

        content = await client.read_resource(mock_session, "file:///test/resource.txt")

        assert len(content) == 2
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "Line 1 content"
        assert content[1]["type"] == "text"
        assert content[1]["text"] == "Line 2 content"
        mock_session.read_resource.assert_called_once_with(
            uri="file:///test/resource.txt"
        )

    @pytest.mark.asyncio
    async def test_read_resource_blob_content(self):
        """Test reading resource with blob content."""
        client = MCPClient()

        mock_session = AsyncMock()
        mock_contents = [
            MockResourceContent("blob", b"\x89PNG\r\n\x1a\n"),
        ]
        mock_result = MockResourceResult(mock_contents)
        mock_session.read_resource = AsyncMock(return_value=mock_result)

        content = await client.read_resource(mock_session, "file:///test/image.png")

        assert len(content) == 1
        assert content[0]["type"] == "blob"
        assert content[0]["data"] == b"\x89PNG\r\n\x1a\n"

    @pytest.mark.asyncio
    async def test_read_resource_mixed_content(self):
        """Test reading resource with mixed content types."""
        client = MCPClient()

        mock_session = AsyncMock()
        mock_contents = [
            MockResourceContent("text", "Header text"),
            MockResourceContent("blob", b"\x00\x01\x02"),
            MockResourceContent("text", "Footer text"),
        ]
        mock_result = MockResourceResult(mock_contents)
        mock_session.read_resource = AsyncMock(return_value=mock_result)

        content = await client.read_resource(mock_session, "file:///test/mixed.dat")

        assert len(content) == 3
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "blob"
        assert content[2]["type"] == "text"

    @pytest.mark.asyncio
    async def test_read_resource_error_handling(self):
        """Test error handling during resource read."""
        client = MCPClient()

        mock_session = AsyncMock()
        mock_session.read_resource = AsyncMock(
            side_effect=Exception("Resource not found")
        )

        # Should raise exception on error
        with pytest.raises(Exception) as exc_info:
            await client.read_resource(mock_session, "file:///invalid/resource.txt")

        assert "Resource not found" in str(exc_info.value)


class TestListPrompts:
    """Test list_prompts functionality."""

    @pytest.mark.asyncio
    async def test_list_prompts_success(self):
        """Test successful prompt listing."""
        client = MCPClient()

        mock_session = AsyncMock()
        mock_prompts = [
            MockPrompt(
                name="greeting",
                description="Generate a greeting message",
                arguments=[
                    MockPromptArgument("name", "Person's name", required=True),
                    MockPromptArgument("formal", "Use formal tone", required=False),
                ],
            ),
            MockPrompt(
                name="summary",
                description="Summarize text",
                arguments=[
                    MockPromptArgument("text", "Text to summarize", required=True),
                ],
            ),
        ]

        mock_result = Mock(prompts=mock_prompts)
        mock_session.list_prompts = AsyncMock(return_value=mock_result)

        prompts = await client.list_prompts(mock_session)

        assert len(prompts) == 2
        assert prompts[0]["name"] == "greeting"
        assert prompts[0]["description"] == "Generate a greeting message"
        assert len(prompts[0]["arguments"]) == 2
        assert prompts[0]["arguments"][0]["name"] == "name"
        assert prompts[0]["arguments"][0]["required"] is True
        assert prompts[1]["name"] == "summary"
        assert len(prompts[1]["arguments"]) == 1
        mock_session.list_prompts.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_prompts_no_arguments(self):
        """Test listing prompts without arguments."""
        client = MCPClient()

        mock_session = AsyncMock()
        mock_prompts = [
            MockPrompt(name="simple", description="Simple prompt", arguments=[]),
        ]

        mock_result = Mock(prompts=mock_prompts)
        mock_session.list_prompts = AsyncMock(return_value=mock_result)

        prompts = await client.list_prompts(mock_session)

        assert len(prompts) == 1
        assert prompts[0]["name"] == "simple"
        assert prompts[0]["arguments"] == []

    @pytest.mark.asyncio
    async def test_list_prompts_empty(self):
        """Test listing when no prompts available."""
        client = MCPClient()

        mock_session = AsyncMock()
        mock_result = Mock(prompts=[])
        mock_session.list_prompts = AsyncMock(return_value=mock_result)

        prompts = await client.list_prompts(mock_session)

        assert prompts == []

    @pytest.mark.asyncio
    async def test_list_prompts_error_handling(self):
        """Test error handling during prompt listing."""
        client = MCPClient()

        mock_session = AsyncMock()
        mock_session.list_prompts = AsyncMock(side_effect=Exception("Server error"))

        # Should return empty list on error
        prompts = await client.list_prompts(mock_session)

        assert prompts == []


class TestGetPrompt:
    """Test get_prompt functionality."""

    @pytest.mark.asyncio
    async def test_get_prompt_success(self):
        """Test successful prompt retrieval."""
        client = MCPClient()

        mock_session = AsyncMock()
        mock_messages = [
            MockPromptMessage("system", "You are a helpful assistant."),
            MockPromptMessage("user", "Hello, my name is Alice."),
        ]
        mock_result = MockPromptResult(mock_messages)
        mock_session.get_prompt = AsyncMock(return_value=mock_result)

        arguments = {"name": "Alice", "formal": False}
        prompt = await client.get_prompt(mock_session, "greeting", arguments)

        assert prompt["name"] == "greeting"
        assert prompt["arguments"] == arguments
        assert len(prompt["messages"]) == 2
        assert prompt["messages"][0]["role"] == "system"
        assert prompt["messages"][0]["content"] == "You are a helpful assistant."
        assert prompt["messages"][1]["role"] == "user"
        assert prompt["messages"][1]["content"] == "Hello, my name is Alice."
        mock_session.get_prompt.assert_called_once_with(
            name="greeting", arguments=arguments
        )

    @pytest.mark.asyncio
    async def test_get_prompt_no_messages(self):
        """Test prompt with no messages."""
        client = MCPClient()

        mock_session = AsyncMock()
        mock_result = MockPromptResult([])
        mock_session.get_prompt = AsyncMock(return_value=mock_result)

        prompt = await client.get_prompt(mock_session, "empty", {})

        assert prompt["name"] == "empty"
        assert prompt["messages"] == []

    @pytest.mark.asyncio
    async def test_get_prompt_empty_arguments(self):
        """Test prompt with empty arguments."""
        client = MCPClient()

        mock_session = AsyncMock()
        mock_messages = [
            MockPromptMessage("user", "Simple prompt"),
        ]
        mock_result = MockPromptResult(mock_messages)
        mock_session.get_prompt = AsyncMock(return_value=mock_result)

        prompt = await client.get_prompt(mock_session, "simple", {})

        assert prompt["name"] == "simple"
        assert prompt["arguments"] == {}
        assert len(prompt["messages"]) == 1

    @pytest.mark.asyncio
    async def test_get_prompt_error_handling(self):
        """Test error handling during prompt retrieval."""
        client = MCPClient()

        mock_session = AsyncMock()
        mock_session.get_prompt = AsyncMock(side_effect=Exception("Prompt not found"))

        # Should raise exception on error
        with pytest.raises(Exception) as exc_info:
            await client.get_prompt(mock_session, "invalid", {})

        assert "Prompt not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_prompt_complex_arguments(self):
        """Test prompt with complex argument types."""
        client = MCPClient()

        mock_session = AsyncMock()
        mock_messages = [
            MockPromptMessage("user", "Process this data"),
        ]
        mock_result = MockPromptResult(mock_messages)
        mock_session.get_prompt = AsyncMock(return_value=mock_result)

        arguments = {
            "text": "Sample text",
            "max_length": 100,
            "include_metadata": True,
            "filters": ["filter1", "filter2"],
        }
        prompt = await client.get_prompt(mock_session, "process", arguments)

        assert prompt["arguments"] == arguments
