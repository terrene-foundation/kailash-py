"""
Regression tests for #339: BaseAgent MCP tools discovered but never executed.

AsyncSingleShotStrategy must detect tool_calls in the LLM response,
execute them via the agent's MCP client, and re-submit the conversation
with tool results until the LLM produces a final response without
tool_calls (or the round limit is reached).
"""

import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workflow_result(
    content: str = "Final answer.",
    tool_calls: list | None = None,
) -> Dict[str, Any]:
    """Build a result dict shaped like ``runtime.execute_workflow_async()`` output."""
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
    """Return a mock agent with the attributes AsyncSingleShotStrategy needs."""
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
# Tests: Helper methods
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractToolCalls:
    """Verify _extract_tool_calls handles various result shapes."""

    def test_extracts_tool_calls_from_valid_result(self):
        strategy = AsyncSingleShotStrategy()
        tc = [_make_tool_call()]
        results = _make_workflow_result(tool_calls=tc)
        assert strategy._extract_tool_calls(results) == tc

    def test_returns_empty_when_no_tool_calls(self):
        strategy = AsyncSingleShotStrategy()
        results = _make_workflow_result(content="No tools needed.")
        assert strategy._extract_tool_calls(results) == []

    def test_returns_empty_for_missing_agent_exec(self):
        strategy = AsyncSingleShotStrategy()
        assert strategy._extract_tool_calls({}) == []

    def test_returns_empty_for_non_dict_response(self):
        strategy = AsyncSingleShotStrategy()
        results = {"agent_exec": {"response": "plain-string"}}
        assert strategy._extract_tool_calls(results) == []


@pytest.mark.unit
class TestExtractAssistantContent:
    """Verify _extract_assistant_content handles various result shapes."""

    def test_extracts_content_string(self):
        strategy = AsyncSingleShotStrategy()
        results = _make_workflow_result(content="Hello world.")
        assert strategy._extract_assistant_content(results) == "Hello world."

    def test_returns_empty_for_missing_content(self):
        strategy = AsyncSingleShotStrategy()
        results = {"agent_exec": {"response": {}}}
        assert strategy._extract_assistant_content(results) == ""

    def test_returns_empty_for_none_content(self):
        strategy = AsyncSingleShotStrategy()
        results = {"agent_exec": {"response": {"content": None}}}
        assert strategy._extract_assistant_content(results) == ""


# ---------------------------------------------------------------------------
# Tests: Tool-call execution loop
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
class TestToolCallExecutionLoop:
    """Core regression tests for #339."""

    async def test_executes_tool_calls_and_resubmits(self):
        """When LLM returns tool_calls, the strategy must execute them
        and feed results back to the LLM."""
        strategy = AsyncSingleShotStrategy()
        agent = _make_mock_agent(has_mcp=True)

        # First LLM call returns a tool call; second returns final answer.
        first_result = _make_workflow_result(
            content="Let me look that up.",
            tool_calls=[
                _make_tool_call(name="mcp__srv__search", arguments={"q": "test"})
            ],
        )
        second_result = _make_workflow_result(content='{"answer": "42"}')

        with patch(
            "kaizen.strategies.async_single_shot.AsyncLocalRuntime"
        ) as MockRuntime:
            mock_runtime_instance = MagicMock()
            mock_runtime_instance.execute_workflow_async = AsyncMock(
                side_effect=[
                    (first_result, "run-1"),
                    (second_result, "run-2"),
                ]
            )
            mock_runtime_instance.close = MagicMock()
            MockRuntime.return_value = mock_runtime_instance

            result = await strategy.execute(agent, {"question": "What is the answer?"})

        # Tool should have been executed once
        agent.execute_mcp_tool.assert_awaited_once_with(
            "mcp__srv__search", {"q": "test"}
        )

        # Final result should come from the second LLM call
        assert result.get("answer") == "42"

    async def test_loop_terminates_when_no_more_tool_calls(self):
        """After one round of tool execution, if the LLM responds without
        tool_calls the loop must stop and return the final answer."""
        strategy = AsyncSingleShotStrategy()
        agent = _make_mock_agent(has_mcp=True)

        first_result = _make_workflow_result(
            content="Calling tool.",
            tool_calls=[_make_tool_call()],
        )
        final_result = _make_workflow_result(content='{"answer": "done"}')

        with patch(
            "kaizen.strategies.async_single_shot.AsyncLocalRuntime"
        ) as MockRuntime:
            mock_runtime_instance = MagicMock()
            mock_runtime_instance.execute_workflow_async = AsyncMock(
                side_effect=[
                    (first_result, "run-1"),
                    (final_result, "run-2"),
                ]
            )
            mock_runtime_instance.close = MagicMock()
            MockRuntime.return_value = mock_runtime_instance

            result = await strategy.execute(agent, {"question": "test"})

        # Workflow executed exactly twice: initial + after tool results
        assert mock_runtime_instance.execute_workflow_async.await_count == 2
        assert result.get("answer") == "done"

    async def test_skips_tool_execution_without_mcp_support(self):
        """If the agent has no MCP support, tool_calls in the response
        are ignored and the raw LLM response is returned."""
        strategy = AsyncSingleShotStrategy()
        agent = _make_mock_agent(has_mcp=False)

        result_with_tools = _make_workflow_result(
            content='{"answer": "partial"}',
            tool_calls=[_make_tool_call()],
        )

        with patch(
            "kaizen.strategies.async_single_shot.AsyncLocalRuntime"
        ) as MockRuntime:
            mock_runtime_instance = MagicMock()
            mock_runtime_instance.execute_workflow_async = AsyncMock(
                return_value=(result_with_tools, "run-1")
            )
            mock_runtime_instance.close = MagicMock()
            MockRuntime.return_value = mock_runtime_instance

            result = await strategy.execute(agent, {"question": "test"})

        # Only one workflow call -- no re-submission
        assert mock_runtime_instance.execute_workflow_async.await_count == 1
        assert result.get("answer") == "partial"

    async def test_max_tool_rounds_enforced(self):
        """The loop must not exceed max_tool_rounds (5)."""
        strategy = AsyncSingleShotStrategy()
        agent = _make_mock_agent(has_mcp=True)

        # Every LLM response keeps requesting tools -- should stop at 5 rounds
        never_ending_result = _make_workflow_result(
            content="Need more tools.",
            tool_calls=[_make_tool_call()],
        )

        with patch(
            "kaizen.strategies.async_single_shot.AsyncLocalRuntime"
        ) as MockRuntime:
            mock_runtime_instance = MagicMock()
            # 1 initial + 5 re-submissions = 6 total calls, all return tool_calls
            mock_runtime_instance.execute_workflow_async = AsyncMock(
                return_value=(never_ending_result, "run-n")
            )
            mock_runtime_instance.close = MagicMock()
            MockRuntime.return_value = mock_runtime_instance

            result = await strategy.execute(agent, {"question": "test"})

        # 1 initial + 5 rounds = 6 workflow executions total
        assert mock_runtime_instance.execute_workflow_async.await_count == 6
        # Tool executed 5 times (once per round)
        assert agent.execute_mcp_tool.await_count == 5

    async def test_tool_execution_error_is_reported_back(self):
        """If a tool raises an exception, the error is serialized and
        sent back to the LLM as a tool result."""
        strategy = AsyncSingleShotStrategy()
        agent = _make_mock_agent(has_mcp=True)
        agent.execute_mcp_tool = AsyncMock(
            side_effect=RuntimeError("connection refused")
        )

        first_result = _make_workflow_result(
            content="Let me try.",
            tool_calls=[_make_tool_call(name="mcp__srv__broken")],
        )
        final_result = _make_workflow_result(content='{"answer": "fallback"}')

        with patch(
            "kaizen.strategies.async_single_shot.AsyncLocalRuntime"
        ) as MockRuntime:
            mock_runtime_instance = MagicMock()
            mock_runtime_instance.execute_workflow_async = AsyncMock(
                side_effect=[
                    (first_result, "run-1"),
                    (final_result, "run-2"),
                ]
            )
            mock_runtime_instance.close = MagicMock()
            MockRuntime.return_value = mock_runtime_instance

            result = await strategy.execute(agent, {"question": "test"})

        # Verify the error was passed to the LLM in the re-submission
        second_call_args = mock_runtime_instance.execute_workflow_async.call_args_list[
            1
        ]
        workflow_params = second_call_args[1].get(
            "inputs", second_call_args[0][1] if len(second_call_args[0]) > 1 else {}
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

    async def test_multiple_tool_calls_in_single_round(self):
        """When the LLM requests multiple tools in one response,
        all should be executed."""
        strategy = AsyncSingleShotStrategy()
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

        with patch(
            "kaizen.strategies.async_single_shot.AsyncLocalRuntime"
        ) as MockRuntime:
            mock_runtime_instance = MagicMock()
            mock_runtime_instance.execute_workflow_async = AsyncMock(
                side_effect=[
                    (first_result, "run-1"),
                    (final_result, "run-2"),
                ]
            )
            mock_runtime_instance.close = MagicMock()
            MockRuntime.return_value = mock_runtime_instance

            result = await strategy.execute(agent, {"question": "test"})

        # Both tools executed
        assert agent.execute_mcp_tool.await_count == 2
        assert result.get("answer") == "combined"

    async def test_no_tool_calls_skips_loop_entirely(self):
        """When the LLM response has no tool_calls, the loop body
        never executes and the result is returned directly."""
        strategy = AsyncSingleShotStrategy()
        agent = _make_mock_agent(has_mcp=True)

        clean_result = _make_workflow_result(content='{"answer": "direct"}')

        with patch(
            "kaizen.strategies.async_single_shot.AsyncLocalRuntime"
        ) as MockRuntime:
            mock_runtime_instance = MagicMock()
            mock_runtime_instance.execute_workflow_async = AsyncMock(
                return_value=(clean_result, "run-1")
            )
            mock_runtime_instance.close = MagicMock()
            MockRuntime.return_value = mock_runtime_instance

            result = await strategy.execute(agent, {"question": "test"})

        # Only one workflow call, no tool execution
        assert mock_runtime_instance.execute_workflow_async.await_count == 1
        agent.execute_mcp_tool.assert_not_awaited()
        assert result.get("answer") == "direct"
