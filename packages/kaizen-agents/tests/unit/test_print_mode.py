"""Tests for kaizen_agents.delegate.print_mode — non-interactive print mode.

Tests cover:
- Text output formatting
- JSON output formatting
- Stdin prompt reading
- Exit codes (0 success, 1 error)
- Empty prompt handling
- Tools-used extraction from conversation
- PrintRunner with mocked agent loop
"""

from __future__ import annotations

import json
import sys
from collections.abc import AsyncIterator
from io import StringIO
from unittest.mock import AsyncMock, patch

import pytest

from kaizen_agents.delegate.config.loader import KzConfig
from kaizen_agents.delegate.print_mode import (
    PrintResult,
    PrintRunner,
    read_prompt,
    run_print_mode,
)

# ---------------------------------------------------------------------------
# PrintResult
# ---------------------------------------------------------------------------


class TestPrintResult:
    def test_success_result(self) -> None:
        r = PrintResult(
            result="Hello, world!",
            tools_used=["bash", "file_read"],
            tokens={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            cost=0.01,
        )
        assert r.result == "Hello, world!"
        assert not r.is_error
        assert len(r.tools_used) == 2
        assert r.tokens["total_tokens"] == 150

    def test_error_result(self) -> None:
        r = PrintResult(
            result="",
            is_error=True,
            error_message="API key missing",
        )
        assert r.is_error
        assert r.error_message == "API key missing"
        assert r.result == ""


# ---------------------------------------------------------------------------
# PrintRunner — formatting
# ---------------------------------------------------------------------------


class TestPrintRunnerMaxTurnsOverridePreservesClient:
    """Regression for the #1918 red-team INVEST-NOW finding.

    The ``max_turns`` override in ``PrintRunner.__init__`` rebuilds ``KzConfig``
    field-by-field, and previously omitted ``base_url`` + ``api_key`` — silently
    dropping a #1899 deployment client. Combined with the #1918 provider-default
    fix, a claude-* model pinned to a custom ``base_url`` would then re-infer to
    the prefix provider's real wire (api.anthropic.com) instead of the caller's
    deployment. The reconstruction MUST preserve every field.
    """

    def test_max_turns_override_preserves_base_url_and_api_key(self) -> None:
        from kaizen_agents.delegate.loop import ToolRegistry

        cfg = KzConfig(
            model="claude-3-5-sonnet",
            base_url="https://my-deployment.example.com/v1",
            api_key="sk-fake-not-real-test-only",
        )
        # mock client → no adapter/governance construction; the reconstruction
        # under the max_turns override is what we assert on (runner._config).
        runner = PrintRunner(
            config=cfg,
            tools=ToolRegistry(),
            client=AsyncMock(),
            max_turns=5,
        )
        assert runner._config.base_url == "https://my-deployment.example.com/v1"
        assert runner._config.api_key == "sk-fake-not-real-test-only"
        # the override itself + the previously-preserved fields still hold
        assert runner._config.max_turns == 5
        assert runner._config.model == "claude-3-5-sonnet"
        assert runner._config.provider == cfg.provider

    def test_no_override_passes_config_through_untouched(self) -> None:
        from kaizen_agents.delegate.loop import ToolRegistry

        cfg = KzConfig(
            model="claude-3-5-sonnet",
            base_url="https://my-deployment.example.com/v1",
            api_key="sk-fake-not-real-test-only",
        )
        runner = PrintRunner(config=cfg, tools=ToolRegistry(), client=AsyncMock())
        # no max_turns override → the same config object flows through unchanged
        assert runner._config is cfg
        assert runner._config.base_url == "https://my-deployment.example.com/v1"
        assert runner._config.api_key == "sk-fake-not-real-test-only"


class TestPrintRunnerFormatting:
    def _make_runner(self) -> PrintRunner:
        """Create a PrintRunner with a mock client to avoid API key checks."""
        config = KzConfig()
        from kaizen_agents.delegate.loop import ToolRegistry

        tools = ToolRegistry()
        mock_client = AsyncMock()
        return PrintRunner(config=config, tools=tools, client=mock_client)

    def test_format_text_success(self) -> None:
        runner = self._make_runner()
        result = PrintResult(result="Hello world")
        text = runner.format_text(result)
        assert text == "Hello world\n"

    def test_format_text_with_trailing_newline(self) -> None:
        runner = self._make_runner()
        result = PrintResult(result="Hello world\n")
        text = runner.format_text(result)
        assert text == "Hello world\n"

    def test_format_text_error(self) -> None:
        runner = self._make_runner()
        result = PrintResult(result="", is_error=True, error_message="Something broke")
        text = runner.format_text(result)
        assert "Error:" in text
        assert "Something broke" in text

    def test_format_json_success(self) -> None:
        runner = self._make_runner()
        result = PrintResult(
            result="output text",
            tools_used=["bash"],
            tokens={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            cost=0.001,
        )
        json_str = runner.format_json(result)
        data = json.loads(json_str)

        assert data["result"] == "output text"
        assert data["tools_used"] == ["bash"]
        assert data["tokens"]["total_tokens"] == 15
        assert data["cost"] == 0.001
        assert "error" not in data

    def test_format_json_error(self) -> None:
        runner = self._make_runner()
        result = PrintResult(
            result="",
            is_error=True,
            error_message="API failure",
        )
        json_str = runner.format_json(result)
        data = json.loads(json_str)

        assert data["error"] == "API failure"
        assert data["result"] == ""


# ---------------------------------------------------------------------------
# PrintRunner — execution with mocked loop
# ---------------------------------------------------------------------------


class TestPrintRunnerExecution:
    @pytest.mark.asyncio
    async def test_run_success(self) -> None:
        """Successful execution returns result text."""
        config = KzConfig()
        from kaizen_agents.delegate.loop import ToolRegistry

        tools = ToolRegistry()
        mock_client = AsyncMock()

        runner = PrintRunner(config=config, tools=tools, client=mock_client)

        # Mock the agent loop's run_turn to yield text
        async def fake_run_turn(prompt: str) -> AsyncIterator[str]:
            yield "Hello "
            yield "world!"

        runner._loop.run_turn = fake_run_turn  # type: ignore[assignment]

        result = await runner.run("test prompt")
        assert result.result == "Hello world!"
        assert not result.is_error

    @pytest.mark.asyncio
    async def test_run_empty_prompt(self) -> None:
        """Empty prompt returns error result."""
        config = KzConfig()
        from kaizen_agents.delegate.loop import ToolRegistry

        tools = ToolRegistry()
        mock_client = AsyncMock()

        runner = PrintRunner(config=config, tools=tools, client=mock_client)

        result = await runner.run("")
        assert result.is_error
        assert "Empty prompt" in result.error_message

    @pytest.mark.asyncio
    async def test_run_whitespace_only_prompt(self) -> None:
        """Whitespace-only prompt returns error result."""
        config = KzConfig()
        from kaizen_agents.delegate.loop import ToolRegistry

        tools = ToolRegistry()
        mock_client = AsyncMock()

        runner = PrintRunner(config=config, tools=tools, client=mock_client)

        result = await runner.run("   \n  \t  ")
        assert result.is_error

    @pytest.mark.asyncio
    async def test_run_exception_returns_error(self) -> None:
        """Exception during execution returns error result."""
        config = KzConfig()
        from kaizen_agents.delegate.loop import ToolRegistry

        tools = ToolRegistry()
        mock_client = AsyncMock()

        runner = PrintRunner(config=config, tools=tools, client=mock_client)

        async def failing_run_turn(prompt: str) -> AsyncIterator[str]:
            raise ValueError("Model API unavailable")
            yield ""  # Make it an async generator

        runner._loop.run_turn = failing_run_turn  # type: ignore[assignment]

        result = await runner.run("test")
        assert result.is_error
        assert "Model API unavailable" in result.error_message

    @pytest.mark.asyncio
    async def test_tools_used_extraction(self) -> None:
        """Tools used should be extracted from conversation history."""
        config = KzConfig()
        from kaizen_agents.delegate.loop import ToolRegistry

        tools = ToolRegistry()
        mock_client = AsyncMock()

        runner = PrintRunner(config=config, tools=tools, client=mock_client)

        # Manually populate conversation with tool calls
        runner._loop.conversation.add_assistant(
            "Let me check that.",
            tool_calls=[
                {
                    "id": "tc1",
                    "type": "function",
                    "function": {"name": "bash", "arguments": "{}"},
                },
                {
                    "id": "tc2",
                    "type": "function",
                    "function": {"name": "file_read", "arguments": "{}"},
                },
            ],
        )
        runner._loop.conversation.add_tool_result("tc1", "bash", "output")
        runner._loop.conversation.add_tool_result("tc2", "file_read", "content")

        tools_used = runner._extract_tools_used()
        assert tools_used == ["bash", "file_read"]

    @pytest.mark.asyncio
    async def test_max_turns_override(self) -> None:
        """max_turns should be applied to the config."""
        config = KzConfig(max_turns=50)
        from kaizen_agents.delegate.loop import ToolRegistry

        tools = ToolRegistry()
        mock_client = AsyncMock()

        runner = PrintRunner(
            config=config, tools=tools, max_turns=5, client=mock_client
        )
        assert runner._loop._config.max_turns == 5


# ---------------------------------------------------------------------------
# read_prompt
# ---------------------------------------------------------------------------


class TestReadPrompt:
    def test_from_cli_arg(self) -> None:
        assert read_prompt("hello world") == "hello world"

    def test_cli_arg_takes_priority(self) -> None:
        assert read_prompt("from arg") == "from arg"

    def test_none_when_no_input(self) -> None:
        """When no CLI arg and stdin is a tty, returns None."""
        with patch.object(sys.stdin, "isatty", return_value=True):
            assert read_prompt(None) is None

    def test_from_stdin(self) -> None:
        """When no CLI arg and stdin has data, reads from stdin."""
        fake_stdin = StringIO("piped input\n")
        fake_stdin.isatty = lambda: False  # type: ignore[assignment]
        with patch("kaizen_agents.delegate.print_mode.sys.stdin", fake_stdin):
            result = read_prompt(None)
            assert result == "piped input"

    def test_empty_stdin_returns_none(self) -> None:
        """When stdin is empty (pipe with no content), returns None."""
        fake_stdin = StringIO("")
        fake_stdin.isatty = lambda: False  # type: ignore[assignment]
        with patch("kaizen_agents.delegate.print_mode.sys.stdin", fake_stdin):
            result = read_prompt(None)
            assert result is None


# ---------------------------------------------------------------------------
# run_print_mode — end-to-end
# ---------------------------------------------------------------------------


class TestRunPrintMode:
    @pytest.mark.asyncio
    async def test_text_output(self) -> None:
        """Text mode writes plain text to stdout."""
        config = KzConfig()
        from kaizen_agents.delegate.loop import ToolRegistry

        tools = ToolRegistry()
        mock_client = AsyncMock()

        captured = StringIO()

        # We need to mock the agent loop's internal streaming
        with (
            patch("kaizen_agents.delegate.print_mode.sys.stdout", captured),
            patch(
                "kaizen_agents.delegate.print_mode.PrintRunner.run",
                new_callable=AsyncMock,
                return_value=PrintResult(result="Test output"),
            ),
        ):
            exit_code = await run_print_mode(
                config,
                tools,
                "test prompt",
                client=mock_client,
            )

        assert exit_code == 0
        assert "Test output" in captured.getvalue()

    @pytest.mark.asyncio
    async def test_json_output(self) -> None:
        """JSON mode writes valid JSON to stdout."""
        config = KzConfig()
        from kaizen_agents.delegate.loop import ToolRegistry

        tools = ToolRegistry()
        mock_client = AsyncMock()

        captured = StringIO()

        with (
            patch("kaizen_agents.delegate.print_mode.sys.stdout", captured),
            patch(
                "kaizen_agents.delegate.print_mode.PrintRunner.run",
                new_callable=AsyncMock,
                return_value=PrintResult(
                    result="JSON output",
                    tools_used=["bash"],
                    tokens={
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                ),
            ),
        ):
            exit_code = await run_print_mode(
                config,
                tools,
                "test prompt",
                json_output=True,
                client=mock_client,
            )

        assert exit_code == 0
        data = json.loads(captured.getvalue())
        assert data["result"] == "JSON output"
        assert data["tools_used"] == ["bash"]

    @pytest.mark.asyncio
    async def test_error_exit_code(self) -> None:
        """Error results should produce exit code 1."""
        config = KzConfig()
        from kaizen_agents.delegate.loop import ToolRegistry

        tools = ToolRegistry()
        mock_client = AsyncMock()

        captured = StringIO()

        with (
            patch("kaizen_agents.delegate.print_mode.sys.stdout", captured),
            patch(
                "kaizen_agents.delegate.print_mode.PrintRunner.run",
                new_callable=AsyncMock,
                return_value=PrintResult(
                    result="",
                    is_error=True,
                    error_message="Failed",
                ),
            ),
        ):
            exit_code = await run_print_mode(
                config,
                tools,
                "test prompt",
                client=mock_client,
            )

        assert exit_code == 1
