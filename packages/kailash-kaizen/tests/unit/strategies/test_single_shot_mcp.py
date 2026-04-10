"""
Regression tests for #377: sync SingleShotStrategy lacks MCP tool-call execution loop.

SingleShotStrategy must detect tool_calls in the LLM response,
execute them via the agent's MCP client, and re-submit the conversation
with tool results until the LLM produces a final response without
tool_calls (or the round limit is reached).

Mirror of test_async_single_shot_tool_calls.py for the sync variant.
"""

import json
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kaizen.strategies.single_shot import _TOOL_NAME_RE, SingleShotStrategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workflow_result(
    content: str = "Final answer.",
    tool_calls: list | None = None,
) -> Dict[str, Any]:
    """Build a result dict shaped like ``runtime.execute()`` output."""
    response: Dict[str, Any] = {
        "content": content,
        "role": "assistant",
        "model": "mock-model",
        "tool_calls": tool_calls or [],
        "finish_reason": "tool_calls" if tool_calls else "stop",
    }
    return {
        "agent_exec": {
            "success": True,
            "response": response,
        }
    }


def _make_tool_call(
    tool_id: str = "call_001",
    name: str = "mcp__test_server__lookup",
    arguments: dict | None = None,
) -> Dict[str, Any]:
    return {
        "id": tool_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments or {}),
        },
    }


def _make_mock_agent(has_mcp: bool = True) -> MagicMock:
    """Return a mock agent with the attributes SingleShotStrategy needs."""
    agent = MagicMock()

    # Signature with input/output fields
    agent.signature.input_fields = {
        "question": {"desc": "Question to answer"},
    }
    agent.signature.output_fields = {
        "answer": {"desc": "Answer", "type": str},
    }

    # Config
    agent.config = MagicMock()
    agent.config.response_format = None

    # Workflow generator -- returns a mock workflow builder each time
    mock_workflow = MagicMock()
    mock_workflow.build.return_value = MagicMock()
    agent.workflow_generator.generate_signature_workflow.return_value = mock_workflow

    # MCP support
    if has_mcp:
        agent.has_mcp_support.return_value = True
        agent.execute_mcp_tool = AsyncMock(
            return_value={"result": "tool-output", "success": True}
        )
    else:
        agent.has_mcp_support.return_value = False
        # No execute_mcp_tool attribute
        if hasattr(agent, "execute_mcp_tool"):
            del agent.execute_mcp_tool

    return agent


# ---------------------------------------------------------------------------
# Tests: Tool name validation regex
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.regression
class TestToolNameRegex:
    """Verify _TOOL_NAME_RE accepts valid names and rejects injection payloads."""

    def test_valid_mcp_tool_name(self):
        assert _TOOL_NAME_RE.match("mcp__srv__search")

    def test_valid_name_with_dots_colons_dashes(self):
        assert _TOOL_NAME_RE.match("my.tool:v2-beta")

    def test_rejects_empty_string(self):
        assert not _TOOL_NAME_RE.match("")

    def test_rejects_leading_digit(self):
        assert not _TOOL_NAME_RE.match("123_tool")

    def test_rejects_spaces(self):
        assert not _TOOL_NAME_RE.match("my tool")

    def test_rejects_path_traversal(self):
        assert not _TOOL_NAME_RE.match("../../etc/passwd")

    def test_rejects_semicolon_injection(self):
        assert not _TOOL_NAME_RE.match("tool; rm -rf /")


# ---------------------------------------------------------------------------
# Tests: Helper methods
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.regression
class TestExtractToolCalls:
    """Verify _extract_tool_calls handles various result shapes."""

    def test_extracts_tool_calls_from_valid_result(self):
        strategy = SingleShotStrategy()
        tc = [_make_tool_call()]
        results = _make_workflow_result(tool_calls=tc)
        assert strategy._extract_tool_calls(results) == tc

    def test_returns_empty_when_no_tool_calls(self):
        strategy = SingleShotStrategy()
        results = _make_workflow_result(content="No tools needed.")
        assert strategy._extract_tool_calls(results) == []

    def test_returns_empty_for_missing_agent_exec(self):
        strategy = SingleShotStrategy()
        assert strategy._extract_tool_calls({}) == []

    def test_returns_empty_for_non_dict_response(self):
        strategy = SingleShotStrategy()
        results = {"agent_exec": {"response": "plain-string"}}
        assert strategy._extract_tool_calls(results) == []


@pytest.mark.unit
@pytest.mark.regression
class TestExtractAssistantContent:
    """Verify _extract_assistant_content handles various result shapes."""

    def test_extracts_content_string(self):
        strategy = SingleShotStrategy()
        results = _make_workflow_result(content="Hello world.")
        assert strategy._extract_assistant_content(results) == "Hello world."

    def test_returns_empty_for_missing_content(self):
        strategy = SingleShotStrategy()
        results = {"agent_exec": {"response": {}}}
        assert strategy._extract_assistant_content(results) == ""

    def test_returns_empty_for_none_content(self):
        strategy = SingleShotStrategy()
        results = {"agent_exec": {"response": {"content": None}}}
        assert strategy._extract_assistant_content(results) == ""


# ---------------------------------------------------------------------------
# Tests: Tool-call execution loop (sync)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.regression
class TestSyncToolCallExecutionLoop:
    """Core regression tests for #377 -- sync SingleShotStrategy MCP tool loop."""

    def test_executes_tool_calls_and_resubmits(self):
        """When LLM returns tool_calls, the strategy must execute them
        and feed results back to the LLM."""
        strategy = SingleShotStrategy()
        agent = _make_mock_agent(has_mcp=True)

        # First LLM call returns a tool call; second returns final answer.
        first_result = _make_workflow_result(
            content="Let me look that up.",
            tool_calls=[
                _make_tool_call(name="mcp__srv__search", arguments={"q": "test"})
            ],
        )
        second_result = _make_workflow_result(content='{"answer": "42"}')

        with patch("kaizen.strategies.single_shot.LocalRuntime") as MockRuntime:
            mock_runtime_instance = MagicMock()
            mock_runtime_instance.execute = MagicMock(
                side_effect=[
                    (first_result, "run-1"),
                    (second_result, "run-2"),
                ]
            )
            mock_runtime_instance.__enter__ = MagicMock(
                return_value=mock_runtime_instance
            )
            mock_runtime_instance.__exit__ = MagicMock(return_value=False)
            MockRuntime.return_value = mock_runtime_instance

            result = strategy.execute(agent, {"question": "What is the answer?"})

        # Tool should have been executed once
        agent.execute_mcp_tool.assert_awaited_once_with(
            "mcp__srv__search", {"q": "test"}
        )

        # Final result should come from the second LLM call
        assert result.get("answer") == "42"

    def test_loop_terminates_when_no_more_tool_calls(self):
        """After one round of tool execution, if the LLM responds without
        tool_calls the loop must stop and return the final answer."""
        strategy = SingleShotStrategy()
        agent = _make_mock_agent(has_mcp=True)

        first_result = _make_workflow_result(
            content="Calling tool.",
            tool_calls=[_make_tool_call()],
        )
        final_result = _make_workflow_result(content='{"answer": "done"}')

        with patch("kaizen.strategies.single_shot.LocalRuntime") as MockRuntime:
            mock_runtime_instance = MagicMock()
            mock_runtime_instance.execute = MagicMock(
                side_effect=[
                    (first_result, "run-1"),
                    (final_result, "run-2"),
                ]
            )
            mock_runtime_instance.__enter__ = MagicMock(
                return_value=mock_runtime_instance
            )
            mock_runtime_instance.__exit__ = MagicMock(return_value=False)
            MockRuntime.return_value = mock_runtime_instance

            result = strategy.execute(agent, {"question": "test"})

        # Workflow executed exactly twice: initial + after tool results
        assert mock_runtime_instance.execute.call_count == 2
        assert result.get("answer") == "done"

    def test_skips_tool_execution_without_mcp_support(self):
        """If the agent has no MCP support, tool_calls in the response
        are ignored and the raw LLM response is returned."""
        strategy = SingleShotStrategy()
        agent = _make_mock_agent(has_mcp=False)

        result_with_tools = _make_workflow_result(
            content='{"answer": "partial"}',
            tool_calls=[_make_tool_call()],
        )

        with patch("kaizen.strategies.single_shot.LocalRuntime") as MockRuntime:
            mock_runtime_instance = MagicMock()
            mock_runtime_instance.execute = MagicMock(
                return_value=(result_with_tools, "run-1")
            )
            mock_runtime_instance.__enter__ = MagicMock(
                return_value=mock_runtime_instance
            )
            mock_runtime_instance.__exit__ = MagicMock(return_value=False)
            MockRuntime.return_value = mock_runtime_instance

            result = strategy.execute(agent, {"question": "test"})

        # Only one workflow call -- no re-submission
        assert mock_runtime_instance.execute.call_count == 1
        assert result.get("answer") == "partial"

    def test_max_tool_rounds_enforced(self):
        """The loop must not exceed max_tool_rounds (5)."""
        strategy = SingleShotStrategy()
        agent = _make_mock_agent(has_mcp=True)

        # Every LLM response keeps requesting tools -- should stop at 5 rounds
        never_ending_result = _make_workflow_result(
            content="Need more tools.",
            tool_calls=[_make_tool_call()],
        )

        with patch("kaizen.strategies.single_shot.LocalRuntime") as MockRuntime:
            mock_runtime_instance = MagicMock()
            # 1 initial + 5 re-submissions = 6 total calls, all return tool_calls
            mock_runtime_instance.execute = MagicMock(
                return_value=(never_ending_result, "run-n")
            )
            mock_runtime_instance.__enter__ = MagicMock(
                return_value=mock_runtime_instance
            )
            mock_runtime_instance.__exit__ = MagicMock(return_value=False)
            MockRuntime.return_value = mock_runtime_instance

            result = strategy.execute(agent, {"question": "test"})

        # 1 initial + 5 rounds = 6 workflow executions total
        assert mock_runtime_instance.execute.call_count == 6
        # Tool executed 5 times (once per round)
        assert agent.execute_mcp_tool.await_count == 5

    def test_tool_execution_error_is_reported_back(self):
        """If a tool raises an exception, the error is serialized and
        sent back to the LLM as a tool result."""
        strategy = SingleShotStrategy()
        agent = _make_mock_agent(has_mcp=True)
        agent.execute_mcp_tool = AsyncMock(
            side_effect=RuntimeError("connection refused")
        )

        first_result = _make_workflow_result(
            content="Let me try.",
            tool_calls=[_make_tool_call(name="mcp__srv__broken")],
        )
        final_result = _make_workflow_result(content='{"answer": "fallback"}')

        with patch("kaizen.strategies.single_shot.LocalRuntime") as MockRuntime:
            mock_runtime_instance = MagicMock()
            mock_runtime_instance.execute = MagicMock(
                side_effect=[
                    (first_result, "run-1"),
                    (final_result, "run-2"),
                ]
            )
            mock_runtime_instance.__enter__ = MagicMock(
                return_value=mock_runtime_instance
            )
            mock_runtime_instance.__exit__ = MagicMock(return_value=False)
            MockRuntime.return_value = mock_runtime_instance

            result = strategy.execute(agent, {"question": "test"})

        # Verify the error was passed to the LLM in the re-submission
        second_call_args = mock_runtime_instance.execute.call_args_list[1]
        workflow_params = second_call_args[1].get(
            "parameters",
            second_call_args[0][1] if len(second_call_args[0]) > 1 else {},
        )
        messages = workflow_params.get("agent_exec", {}).get("messages", [])

        # Find the tool result message
        tool_messages = [m for m in messages if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        tool_content = json.loads(tool_messages[0]["content"])
        assert "error" in tool_content
        assert tool_content["error"] == "Tool execution failed"

        # Final result should still be returned
        assert result.get("answer") == "fallback"

    def test_multiple_tool_calls_in_single_round(self):
        """When the LLM requests multiple tools in one response,
        all should be executed."""
        strategy = SingleShotStrategy()
        agent = _make_mock_agent(has_mcp=True)
        agent.execute_mcp_tool = AsyncMock(
            side_effect=[
                {"data": "result-a", "success": True},
                {"data": "result-b", "success": True},
            ]
        )

        first_result = _make_workflow_result(
            content="Running two tools.",
            tool_calls=[
                _make_tool_call(tool_id="call_1", name="mcp__srv__tool_a"),
                _make_tool_call(tool_id="call_2", name="mcp__srv__tool_b"),
            ],
        )
        final_result = _make_workflow_result(content='{"answer": "combined"}')

        with patch("kaizen.strategies.single_shot.LocalRuntime") as MockRuntime:
            mock_runtime_instance = MagicMock()
            mock_runtime_instance.execute = MagicMock(
                side_effect=[
                    (first_result, "run-1"),
                    (final_result, "run-2"),
                ]
            )
            mock_runtime_instance.__enter__ = MagicMock(
                return_value=mock_runtime_instance
            )
            mock_runtime_instance.__exit__ = MagicMock(return_value=False)
            MockRuntime.return_value = mock_runtime_instance

            result = strategy.execute(agent, {"question": "test"})

        # Both tools executed
        assert agent.execute_mcp_tool.await_count == 2
        assert result.get("answer") == "combined"

    def test_no_tool_calls_skips_loop_entirely(self):
        """When the LLM response has no tool_calls, the loop body
        never executes and the result is returned directly."""
        strategy = SingleShotStrategy()
        agent = _make_mock_agent(has_mcp=True)

        clean_result = _make_workflow_result(content='{"answer": "direct"}')

        with patch("kaizen.strategies.single_shot.LocalRuntime") as MockRuntime:
            mock_runtime_instance = MagicMock()
            mock_runtime_instance.execute = MagicMock(
                return_value=(clean_result, "run-1")
            )
            mock_runtime_instance.__enter__ = MagicMock(
                return_value=mock_runtime_instance
            )
            mock_runtime_instance.__exit__ = MagicMock(return_value=False)
            MockRuntime.return_value = mock_runtime_instance

            result = strategy.execute(agent, {"question": "test"})

        # Only one workflow call, no tool execution
        assert mock_runtime_instance.execute.call_count == 1
        agent.execute_mcp_tool.assert_not_awaited()
        assert result.get("answer") == "direct"

    def test_invalid_tool_name_rejected(self):
        """Tool names that fail the allowlist regex should be rejected
        with an error sent back to the LLM, not executed."""
        strategy = SingleShotStrategy()
        agent = _make_mock_agent(has_mcp=True)

        # Tool call with an invalid name (path traversal attempt)
        malicious_tc = _make_tool_call(
            tool_id="call_evil",
            name="../../etc/passwd",
        )
        first_result = _make_workflow_result(
            content="Running tool.",
            tool_calls=[malicious_tc],
        )
        final_result = _make_workflow_result(content='{"answer": "safe"}')

        with patch("kaizen.strategies.single_shot.LocalRuntime") as MockRuntime:
            mock_runtime_instance = MagicMock()
            mock_runtime_instance.execute = MagicMock(
                side_effect=[
                    (first_result, "run-1"),
                    (final_result, "run-2"),
                ]
            )
            mock_runtime_instance.__enter__ = MagicMock(
                return_value=mock_runtime_instance
            )
            mock_runtime_instance.__exit__ = MagicMock(return_value=False)
            MockRuntime.return_value = mock_runtime_instance

            result = strategy.execute(agent, {"question": "test"})

        # Tool should NOT have been executed
        agent.execute_mcp_tool.assert_not_awaited()

        # Verify the error message was sent to the LLM in re-submission
        second_call_args = mock_runtime_instance.execute.call_args_list[1]
        workflow_params = second_call_args[1].get(
            "parameters",
            second_call_args[0][1] if len(second_call_args[0]) > 1 else {},
        )
        messages = workflow_params.get("agent_exec", {}).get("messages", [])
        tool_messages = [m for m in messages if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        tool_content = json.loads(tool_messages[0]["content"])
        assert tool_content["error"] == "Invalid tool name"

        assert result.get("answer") == "safe"
