"""
Tests for External Runtime Adapters

Tests ClaudeCodeAdapter, OpenAICodexAdapter, and GeminiCLIAdapter.
These tests use mocking for the external APIs to allow testing
without API keys or network access.
"""

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen.runtime.adapters.claude_code import (
    ClaudeCodeAdapter,
    is_claude_code_available,
)
from kaizen.runtime.adapters.gemini_cli import GeminiCLIAdapter, is_gemini_available
from kaizen.runtime.adapters.openai_codex import OpenAICodexAdapter, is_openai_available
from kaizen.runtime.context import ExecutionContext, ExecutionResult, ExecutionStatus

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def execution_context() -> ExecutionContext:
    """Create a basic execution context."""
    return ExecutionContext(
        task="List files in /tmp",
        session_id="test-session-123",
    )


@pytest.fixture
def context_with_tools() -> ExecutionContext:
    """Create context with custom tools."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_files",
                "description": "Search for files",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Search pattern"}
                    },
                    "required": ["pattern"],
                },
            },
        }
    ]
    return ExecutionContext(
        task="Search for Python files",
        session_id="test-session-456",
        tools=tools,
    )


# =============================================================================
# ClaudeCodeAdapter Tests
# =============================================================================


class TestClaudeCodeAdapter:
    """Tests for ClaudeCodeAdapter."""

    def test_initialization_defaults(self):
        """Test adapter initializes with defaults."""
        adapter = ClaudeCodeAdapter()

        assert adapter.model == "claude-sonnet-4-20250514"
        assert adapter.max_tokens == 8192
        assert adapter.timeout_seconds == 300
        assert adapter.custom_tools == []

    def test_initialization_custom_params(self):
        """Test adapter with custom parameters."""
        adapter = ClaudeCodeAdapter(
            working_directory="/custom/path",
            model="claude-opus-4-20250514",
            max_tokens=16384,
            custom_tools=[{"name": "test"}],
        )

        assert adapter.working_directory == "/custom/path"
        assert adapter.model == "claude-opus-4-20250514"
        assert adapter.max_tokens == 16384
        assert len(adapter.custom_tools) == 1

    def test_capabilities(self):
        """Test capabilities reporting."""
        adapter = ClaudeCodeAdapter()
        caps = adapter.capabilities

        assert caps.runtime_name == "claude_code"
        assert caps.provider == "anthropic"
        assert caps.supports_streaming is True
        assert caps.supports_tool_calling is True
        assert caps.supports_code_execution is True
        assert caps.supports_file_access is True
        assert "Read" in caps.native_tools
        assert "Bash" in caps.native_tools

    def test_map_tools(self):
        """Test tool mapping to MCP format."""
        adapter = ClaudeCodeAdapter()

        kaizen_tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "A test tool",
                    "parameters": {
                        "type": "object",
                        "properties": {"arg1": {"type": "string"}},
                    },
                },
            }
        ]

        mcp_tools = adapter.map_tools(kaizen_tools)

        assert len(mcp_tools) == 1
        assert mcp_tools[0]["name"] == "test_tool"
        assert "inputSchema" in mcp_tools[0]

    def test_normalize_result_string(self):
        """Test result normalization from string."""
        adapter = ClaudeCodeAdapter()

        result = adapter.normalize_result("Task completed successfully")

        assert isinstance(result, ExecutionResult)
        assert result.output == "Task completed successfully"
        assert result.status == ExecutionStatus.COMPLETE
        assert result.runtime_name == "claude_code"

    def test_normalize_result_dict(self):
        """Test result normalization from dict."""
        adapter = ClaudeCodeAdapter()

        result = adapter.normalize_result(
            {
                "output": "Result output",
                "status": "complete",
            }
        )

        assert isinstance(result, ExecutionResult)
        assert result.output == "Result output"

    @pytest.mark.asyncio
    async def test_execute_success(self, execution_context):
        """Test successful execution."""
        adapter = ClaudeCodeAdapter()

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Mock successful subprocess
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(
                return_value=(b"Files listed:\n- file1.txt\n- file2.txt", b"")
            )
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await adapter.execute(execution_context)

            assert result.status == ExecutionStatus.COMPLETE
            assert "file1.txt" in result.output

    @pytest.mark.asyncio
    async def test_execute_error(self, execution_context):
        """Test execution error handling."""
        adapter = ClaudeCodeAdapter()

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Mock failed subprocess
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(
                return_value=(b"", b"Command not found")
            )
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            result = await adapter.execute(execution_context)

            assert result.status == ExecutionStatus.ERROR
            assert (
                "Command not found" in result.error_message
                or "Exit code" in result.error_message
            )

    @pytest.mark.asyncio
    async def test_interrupt(self, execution_context):
        """Test interrupt functionality."""
        adapter = ClaudeCodeAdapter()

        # Set up active session
        adapter._current_session_id = execution_context.session_id
        mock_process = MagicMock()
        adapter._current_process = mock_process

        result = await adapter.interrupt(execution_context.session_id, mode="graceful")

        assert result is True
        mock_process.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_interrupt_wrong_session(self, execution_context):
        """Test interrupt with wrong session ID."""
        adapter = ClaudeCodeAdapter()
        adapter._current_session_id = "different-session"

        result = await adapter.interrupt(execution_context.session_id)

        assert result is False


# =============================================================================
# OpenAICodexAdapter Tests
# =============================================================================


class TestOpenAICodexAdapter:
    """Tests for OpenAICodexAdapter."""

    def test_initialization_defaults(self):
        """Test adapter initializes with defaults."""
        adapter = OpenAICodexAdapter(api_key="test-key")

        assert adapter.model == "gpt-4o"
        assert adapter.enable_code_interpreter is True
        assert adapter.enable_file_search is False
        assert adapter.temperature == 0.7

    def test_initialization_custom_params(self):
        """Test adapter with custom parameters."""
        adapter = OpenAICodexAdapter(
            api_key="test-key",
            model="gpt-4o-mini",
            enable_code_interpreter=True,
            enable_file_search=True,
            temperature=0.5,
        )

        assert adapter.model == "gpt-4o-mini"
        assert adapter.enable_code_interpreter is True
        assert adapter.enable_file_search is True
        assert adapter.temperature == 0.5

    def test_capabilities(self):
        """Test capabilities reporting."""
        adapter = OpenAICodexAdapter(
            api_key="test-key",
            enable_code_interpreter=True,
        )
        caps = adapter.capabilities

        assert caps.runtime_name == "openai_codex"
        assert caps.provider == "openai"
        assert caps.supports_streaming is True
        assert caps.supports_code_execution is True
        assert "code_interpreter" in caps.native_tools

    def test_capabilities_without_code_interpreter(self):
        """Test capabilities without code interpreter."""
        adapter = OpenAICodexAdapter(
            api_key="test-key",
            enable_code_interpreter=False,
        )
        caps = adapter.capabilities

        assert caps.supports_code_execution is False
        assert "code_interpreter" not in caps.native_tools

    def test_map_tools(self, context_with_tools):
        """Test tool mapping."""
        adapter = OpenAICodexAdapter(
            api_key="test-key",
            enable_code_interpreter=True,
        )

        tools = adapter.map_tools(context_with_tools.tools)

        # Should include custom function + code_interpreter
        types = [t.get("type") for t in tools]
        assert "function" in types
        assert "code_interpreter" in types

    def test_normalize_result_string(self):
        """Test result normalization."""
        adapter = OpenAICodexAdapter(api_key="test-key")

        result = adapter.normalize_result("Analysis complete")

        assert isinstance(result, ExecutionResult)
        assert result.output == "Analysis complete"
        assert result.runtime_name == "openai_codex"

    @pytest.mark.asyncio
    async def test_execute_success(self, execution_context):
        """Test successful execution with mocked API."""
        adapter = OpenAICodexAdapter(api_key="test-key")

        # Mock OpenAI client
        mock_response = MagicMock()
        mock_response.output = [MagicMock(text="Files found: file1.txt, file2.txt")]
        mock_response.usage = MagicMock(total_tokens=150)

        mock_client = AsyncMock()
        mock_client.responses.create = AsyncMock(return_value=mock_response)

        adapter._client = mock_client
        adapter._is_initialized = True

        result = await adapter.execute(execution_context)

        assert result.status == ExecutionStatus.COMPLETE
        assert "file1.txt" in result.output

    @pytest.mark.asyncio
    async def test_execute_error(self, execution_context):
        """Test error handling."""
        adapter = OpenAICodexAdapter(api_key="test-key")

        # Mock client that raises
        mock_client = AsyncMock()
        mock_client.responses.create = AsyncMock(side_effect=Exception("API Error"))

        adapter._client = mock_client
        adapter._is_initialized = True

        result = await adapter.execute(execution_context)

        assert result.status == ExecutionStatus.ERROR
        assert "API Error" in result.error_message

    def test_build_tools_with_code_interpreter(self, execution_context):
        """Test tools list includes code interpreter."""
        adapter = OpenAICodexAdapter(
            api_key="test-key",
            enable_code_interpreter=True,
        )

        tools = adapter._build_tools(execution_context)

        types = [t.get("type") for t in tools]
        assert "code_interpreter" in types


# =============================================================================
# GeminiCLIAdapter Tests
# =============================================================================


class TestGeminiCLIAdapter:
    """Tests for GeminiCLIAdapter."""

    def test_initialization_defaults(self):
        """Test adapter initializes with defaults."""
        adapter = GeminiCLIAdapter(api_key="test-key")

        assert adapter.model == "gemini-1.5-pro"
        assert adapter.enable_code_execution is False
        assert adapter.temperature == 0.7

    def test_initialization_custom_params(self):
        """Test adapter with custom parameters."""
        adapter = GeminiCLIAdapter(
            api_key="test-key",
            model="gemini-1.5-flash",
            enable_code_execution=True,
            temperature=0.3,
        )

        assert adapter.model == "gemini-1.5-flash"
        assert adapter.enable_code_execution is True
        assert adapter.temperature == 0.3

    def test_capabilities_1_5_model(self):
        """Test capabilities for Gemini 1.5."""
        adapter = GeminiCLIAdapter(
            api_key="test-key",
            model="gemini-1.5-pro",
        )
        caps = adapter.capabilities

        assert caps.runtime_name == "gemini_cli"
        assert caps.provider == "google"
        assert caps.max_context_tokens == 1000000  # 1M context
        assert caps.supports_vision is True
        assert caps.supports_audio is True

    def test_capabilities_1_0_model(self):
        """Test capabilities for Gemini 1.0."""
        adapter = GeminiCLIAdapter(
            api_key="test-key",
            model="gemini-1.0-pro",
        )
        caps = adapter.capabilities

        assert caps.max_context_tokens == 32000  # 32K context

    def test_map_tools(self, context_with_tools):
        """Test tool mapping to Gemini format."""
        adapter = GeminiCLIAdapter(api_key="test-key")

        tools = adapter.map_tools(context_with_tools.tools)

        assert len(tools) == 1
        tool = tools[0]
        assert tool["name"] == "search_files"
        # Gemini uses uppercase types
        assert tool["parameters"]["type"] == "OBJECT"

    def test_normalize_result_string(self):
        """Test result normalization."""
        adapter = GeminiCLIAdapter(api_key="test-key")

        result = adapter.normalize_result("Generation complete")

        assert isinstance(result, ExecutionResult)
        assert result.output == "Generation complete"
        assert result.runtime_name == "gemini_cli"

    @pytest.mark.asyncio
    async def test_execute_success(self, execution_context):
        """Test successful execution with mocked API."""
        adapter = GeminiCLIAdapter(api_key="test-key")

        # Mock Gemini response
        mock_response = MagicMock()
        mock_response.text = "Files found: file1.txt, file2.txt"
        mock_response.usage_metadata = MagicMock(total_token_count=100)

        # Mock generative model
        mock_model = MagicMock()
        mock_model.generate_content = MagicMock(return_value=mock_response)

        adapter._generative_model = mock_model
        adapter._client = MagicMock()
        adapter._is_initialized = True

        result = await adapter.execute(execution_context)

        assert result.status == ExecutionStatus.COMPLETE
        assert "file1.txt" in result.output

    @pytest.mark.asyncio
    async def test_execute_error(self, execution_context):
        """Test error handling."""
        adapter = GeminiCLIAdapter(api_key="test-key")

        # Mock model that raises
        mock_model = MagicMock()
        mock_model.generate_content = MagicMock(side_effect=Exception("API Error"))

        adapter._generative_model = mock_model
        adapter._client = MagicMock()
        adapter._is_initialized = True

        result = await adapter.execute(execution_context)

        assert result.status == ExecutionStatus.ERROR
        assert "API Error" in result.error_message

    def test_extract_output_with_text(self):
        """Test output extraction from text response."""
        adapter = GeminiCLIAdapter(api_key="test-key")

        mock_response = MagicMock()
        mock_response.text = "Direct text output"

        output = adapter._extract_output(mock_response)

        assert output == "Direct text output"

    def test_extract_output_with_candidates(self):
        """Test output extraction from candidates structure."""
        adapter = GeminiCLIAdapter(api_key="test-key")

        # Mock complex response structure
        mock_part = MagicMock()
        mock_part.text = "Output from candidate"

        mock_content = MagicMock()
        mock_content.parts = [mock_part]

        mock_candidate = MagicMock()
        mock_candidate.content = mock_content

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]
        # Remove text attribute to force candidates path
        del mock_response.text

        output = adapter._extract_output(mock_response)

        assert "Output from candidate" in output


# =============================================================================
# Availability Check Tests
# =============================================================================


class TestAvailabilityChecks:
    """Tests for adapter availability checks."""

    @pytest.mark.asyncio
    async def test_claude_code_not_available(self):
        """Test Claude Code availability when CLI not installed."""
        with patch("asyncio.create_subprocess_exec") as mock:
            mock.side_effect = FileNotFoundError("claude not found")

            result = await is_claude_code_available()

            assert result is False

    @pytest.mark.asyncio
    async def test_openai_not_available(self):
        """Test OpenAI availability with invalid key."""
        adapter = OpenAICodexAdapter(api_key="invalid-key")

        # Mock failed initialization
        with patch.object(
            adapter, "ensure_initialized", side_effect=Exception("Invalid API key")
        ):
            result = await adapter.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_gemini_not_available(self):
        """Test Gemini availability with invalid key."""
        adapter = GeminiCLIAdapter(api_key="invalid-key")

        # Mock failed initialization
        with patch.object(
            adapter, "ensure_initialized", side_effect=Exception("Invalid API key")
        ):
            result = await adapter.health_check()

        assert result is False


# =============================================================================
# Integration Tests (Adapter Interface Compliance)
# =============================================================================


class TestAdapterInterfaceCompliance:
    """Test that all adapters implement the RuntimeAdapter interface correctly."""

    @pytest.fixture
    def adapters(self):
        """Create all adapter instances."""
        return [
            ClaudeCodeAdapter(),
            OpenAICodexAdapter(api_key="test-key"),
            GeminiCLIAdapter(api_key="test-key"),
        ]

    def test_all_have_capabilities(self, adapters):
        """All adapters should have capabilities property."""
        for adapter in adapters:
            caps = adapter.capabilities
            assert caps.runtime_name is not None
            assert caps.provider is not None
            assert isinstance(caps.supports_streaming, bool)
            assert isinstance(caps.supports_tool_calling, bool)

    def test_all_have_map_tools(self, adapters):
        """All adapters should implement map_tools."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test",
                    "description": "Test",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        for adapter in adapters:
            mapped = adapter.map_tools(tools)
            assert isinstance(mapped, list)

    def test_all_have_normalize_result(self, adapters):
        """All adapters should implement normalize_result."""
        for adapter in adapters:
            result = adapter.normalize_result("test output")
            assert isinstance(result, ExecutionResult)
            assert result.output == "test output"

    def test_all_have_repr(self, adapters):
        """All adapters should have meaningful repr."""
        for adapter in adapters:
            repr_str = repr(adapter)
            assert "Adapter" in repr_str
            assert "model" in repr_str.lower() or "claude_code" in repr_str.lower()
