"""
Test suite to validate the MCP OpenAI Pydantic model fix in LLMAgentNode.

This test ensures that the fix for the OpenAI v1.97.1+ compatibility issue
works correctly for both Pydantic models and legacy dictionary formats.
"""

import json
from unittest.mock import AsyncMock, Mock

import pytest
from kaizen.nodes.ai.llm_agent import LLMAgentNode
from openai.types.chat import ChatCompletionMessageToolCall
from openai.types.chat.chat_completion_message_tool_call import Function


class TestMCPPydanticFix:
    """Test the MCP Pydantic model compatibility fix."""

    def test_extract_tool_call_info_pydantic_model(self):
        """Test that _extract_tool_call_info handles OpenAI Pydantic models correctly."""
        node = LLMAgentNode()

        # Create OpenAI Pydantic model
        tool_call = ChatCompletionMessageToolCall(
            id="call_test_123",
            type="function",
            function=Function(
                name="test_tool", arguments='{"param": "value", "number": 42}'
            ),
        )

        result = node._extract_tool_call_info(tool_call)

        assert result["id"] == "call_test_123"
        assert result["name"] == "test_tool"
        assert result["arguments"] == '{"param": "value", "number": 42}'
        assert result["arguments_dict"] == {"param": "value", "number": 42}

    def test_extract_tool_call_info_legacy_dict(self):
        """Test that _extract_tool_call_info handles legacy dictionary format correctly."""
        node = LLMAgentNode()

        # Create legacy dictionary format
        tool_call = {
            "id": "call_legacy_456",
            "type": "function",
            "function": {
                "name": "legacy_tool",
                "arguments": '{"old_param": "old_value"}',
            },
        }

        result = node._extract_tool_call_info(tool_call)

        assert result["id"] == "call_legacy_456"
        assert result["name"] == "legacy_tool"
        assert result["arguments"] == '{"old_param": "old_value"}'
        assert result["arguments_dict"] == {"old_param": "old_value"}

    def test_extract_tool_call_info_empty_arguments(self):
        """Test handling of empty or missing arguments."""
        node = LLMAgentNode()

        # Test with Pydantic model with empty arguments
        tool_call = ChatCompletionMessageToolCall(
            id="call_empty_123",
            type="function",
            function=Function(name="empty_tool", arguments=""),
        )

        result = node._extract_tool_call_info(tool_call)

        assert result["id"] == "call_empty_123"
        assert result["name"] == "empty_tool"
        assert result["arguments"] == "{}"  # Empty string becomes "{}"
        assert result["arguments_dict"] == {}

    def test_extract_tool_call_info_malformed_json(self):
        """Test handling of malformed JSON in arguments."""
        node = LLMAgentNode()

        # Test with malformed JSON - should raise informative error
        tool_call = ChatCompletionMessageToolCall(
            id="call_malformed_123",
            type="function",
            function=Function(name="malformed_tool", arguments='{"incomplete": '),
        )

        # Should raise JSONDecodeError with informative message
        with pytest.raises(json.JSONDecodeError) as exc_info:
            node._extract_tool_call_info(tool_call)

        assert "Invalid JSON in tool 'malformed_tool' arguments" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_mcp_tool_call_with_pydantic(self):
        """Test that _execute_mcp_tool_call works with OpenAI Pydantic models."""
        node = LLMAgentNode()

        # Create Pydantic tool call
        tool_call = ChatCompletionMessageToolCall(
            id="call_mcp_123",
            type="function",
            function=Function(
                name="mcp_test_tool", arguments='{"query": "test query"}'
            ),
        )

        # Create mock MCP tools
        mcp_tools = [
            {
                "type": "function",
                "function": {
                    "name": "mcp_test_tool",
                    "description": "Test MCP tool",
                    "mcp_server_config": {
                        "name": "test_server",
                        "command": "echo",
                        "args": ["test"],
                    },
                },
            }
        ]

        # Mock the MCP client to avoid actual server calls
        mock_client = AsyncMock()
        mock_client.call_tool.return_value = {
            "status": "success",
            "result": "test result",
        }
        node._mcp_client = mock_client

        result = await node._execute_mcp_tool_call(tool_call, mcp_tools)

        # Should successfully extract tool info and attempt MCP call
        assert result["success"] is True
        assert result["tool_name"] == "mcp_test_tool"
        assert "result" in result

        # Verify MCP client was called with correct parameters
        mock_client.call_tool.assert_called_once()
        call_args = mock_client.call_tool.call_args
        assert call_args[0][1] == "mcp_test_tool"  # tool_name
        assert call_args[0][2] == {"query": "test query"}  # tool_args

    def test_execute_tool_calls_with_mixed_formats(self):
        """Test that _execute_tool_calls handles mixed Pydantic and dict formats."""
        node = LLMAgentNode()

        # Mix of Pydantic and dictionary tool calls
        tool_calls = [
            ChatCompletionMessageToolCall(
                id="call_pydantic_123",
                type="function",
                function=Function(
                    name="pydantic_tool", arguments='{"param": "pydantic_value"}'
                ),
            ),
            {
                "id": "call_dict_456",
                "type": "function",
                "function": {
                    "name": "dict_tool",
                    "arguments": '{"param": "dict_value"}',
                },
            },
        ]

        available_tools = []
        mcp_tools = []

        # This should not raise AttributeError
        results = node._execute_tool_calls(tool_calls, available_tools, mcp_tools)

        # Should return results for both tool calls
        assert len(results) == 2
        assert results[0]["tool_call_id"] == "call_pydantic_123"
        assert results[1]["tool_call_id"] == "call_dict_456"

    def test_execute_regular_tool_with_pydantic(self):
        """Test that _execute_regular_tool works with OpenAI Pydantic models."""
        node = LLMAgentNode()

        # Create Pydantic tool call
        tool_call = ChatCompletionMessageToolCall(
            id="call_regular_123",
            type="function",
            function=Function(name="regular_tool", arguments='{"input": "test input"}'),
        )

        available_tools = []

        result = node._execute_regular_tool(tool_call, available_tools)

        # Should successfully extract tool info and return mock result
        assert result["status"] == "success"
        assert result["tool"] == "regular_tool"
        assert "test input" in result["result"]

    def test_backward_compatibility_preserved(self):
        """Test that the fix doesn't break existing dictionary-based code."""
        node = LLMAgentNode()

        # Test with legacy dictionary format (should still work)
        legacy_tool_call = {
            "id": "call_legacy_test",
            "type": "function",
            "function": {
                "name": "legacy_test_tool",
                "arguments": '{"legacy": "format"}',
            },
        }

        # This should work exactly as before
        result = node._execute_regular_tool(legacy_tool_call, [])

        assert result["status"] == "success"
        assert result["tool"] == "legacy_test_tool"
        assert "legacy" in result["result"]

    def test_error_handling_robustness(self):
        """Test that error handling is robust for both formats."""
        node = LLMAgentNode()

        # Test with None - should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            node._extract_tool_call_info(None)
        assert "tool_call cannot be None" in str(exc_info.value)

        # Test with missing required fields - should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            node._extract_tool_call_info({"not_a_valid": "tool_call"})
        assert "missing required 'id' field" in str(exc_info.value)

        # Test with missing function name - should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            node._extract_tool_call_info({"id": "test", "function": {}})
        assert "missing required 'function.name' field" in str(exc_info.value)

        # Test with wrong type - should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            node._extract_tool_call_info("not a dict or pydantic")
        assert "Unrecognized tool_call format" in str(exc_info.value)

    def test_type_detection_accuracy(self):
        """Test that the type detection correctly identifies Pydantic vs dict."""
        node = LLMAgentNode()

        # Test Pydantic detection
        pydantic_call = ChatCompletionMessageToolCall(
            id="test_id",
            type="function",
            function=Function(name="test", arguments="{}"),
        )

        # Test dictionary detection
        dict_call = {"id": "test_id", "function": {"name": "test", "arguments": "{}"}}

        # Both should be handled correctly
        pydantic_result = node._extract_tool_call_info(pydantic_call)
        dict_result = node._extract_tool_call_info(dict_call)

        # Results should be structurally equivalent
        assert pydantic_result["id"] == dict_result["id"]
        assert pydantic_result["name"] == dict_result["name"]
        assert pydantic_result["arguments"] == dict_result["arguments"]
        assert pydantic_result["arguments_dict"] == dict_result["arguments_dict"]

    def test_edge_cases_comprehensive(self):
        """Test comprehensive edge cases identified by review."""
        node = LLMAgentNode()

        # Test 1: Very large JSON string
        large_args = json.dumps({"data": "x" * 10000})
        tool_call = ChatCompletionMessageToolCall(
            id="large_123",
            type="function",
            function=Function(name="large_tool", arguments=large_args),
        )
        result = node._extract_tool_call_info(tool_call)
        assert result["name"] == "large_tool"
        assert len(result["arguments_dict"]["data"]) == 10000

        # Test 2: Unicode characters
        unicode_args = '{"text": "Hello 世界 🌍"}'
        tool_call = ChatCompletionMessageToolCall(
            id="unicode_123",
            type="function",
            function=Function(name="unicode_tool", arguments=unicode_args),
        )
        result = node._extract_tool_call_info(tool_call)
        assert result["arguments_dict"]["text"] == "Hello 世界 🌍"

        # Test 3: Nested JSON structures
        nested_args = json.dumps({"level1": {"level2": {"level3": "value"}}})
        tool_call = ChatCompletionMessageToolCall(
            id="nested_123",
            type="function",
            function=Function(name="nested_tool", arguments=nested_args),
        )
        result = node._extract_tool_call_info(tool_call)
        assert result["arguments_dict"]["level1"]["level2"]["level3"] == "value"

        # Test 4: None and null handling
        null_args = '{"value": null}'
        tool_call = ChatCompletionMessageToolCall(
            id="null_123",
            type="function",
            function=Function(name="null_tool", arguments=null_args),
        )
        result = node._extract_tool_call_info(tool_call)
        assert result["arguments_dict"]["value"] is None

        # Test 5: Special characters in JSON
        special_args = '{"path": "C:\\\\Users\\\\test", "regex": ".*\\\\.txt"}'
        tool_call = ChatCompletionMessageToolCall(
            id="special_123",
            type="function",
            function=Function(name="special_tool", arguments=special_args),
        )
        result = node._extract_tool_call_info(tool_call)
        assert result["arguments_dict"]["path"] == "C:\\Users\\test"
        assert result["arguments_dict"]["regex"] == ".*\\.txt"

    def test_concurrent_access_safety(self):
        """Test that concurrent access doesn't cause issues."""
        import threading
        import time

        node = LLMAgentNode()
        results = []
        errors = []

        def extract_info(tool_call, index):
            try:
                time.sleep(0.001)  # Small delay to increase chance of race conditions
                result = node._extract_tool_call_info(tool_call)
                results.append((index, result))
            except Exception as e:
                errors.append((index, str(e)))

        # Create mixed tool calls
        tool_calls = []
        for i in range(10):
            if i % 2 == 0:
                # Pydantic model
                tool_calls.append(
                    ChatCompletionMessageToolCall(
                        id=f"call_{i}",
                        type="function",
                        function=Function(
                            name=f"tool_{i}", arguments=f'{{"index": {i}}}'
                        ),
                    )
                )
            else:
                # Dictionary
                tool_calls.append(
                    {
                        "id": f"call_{i}",
                        "function": {
                            "name": f"tool_{i}",
                            "arguments": f'{{"index": {i}}}',
                        },
                    }
                )

        # Run extractions concurrently
        threads = []
        for i, tool_call in enumerate(tool_calls):
            thread = threading.Thread(target=extract_info, args=(tool_call, i))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Verify no errors and all results are correct
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 10

        # Verify each result is correct
        results.sort(key=lambda x: x[0])  # Sort by index
        for index, result in results:
            assert result["name"] == f"tool_{index}"
            assert result["arguments_dict"]["index"] == index

    def test_graceful_failure_in_workflow(self):
        """Test that extraction errors are handled gracefully in actual workflow."""
        node = LLMAgentNode()

        # Mix of valid and invalid tool calls
        tool_calls = [
            # Valid Pydantic
            ChatCompletionMessageToolCall(
                id="valid_1",
                type="function",
                function=Function(name="valid_tool", arguments='{"valid": true}'),
            ),
            # Invalid JSON
            ChatCompletionMessageToolCall(
                id="invalid_json",
                type="function",
                function=Function(name="bad_json_tool", arguments='{"bad": '),
            ),
            # Valid dict
            {
                "id": "valid_2",
                "function": {"name": "dict_tool", "arguments": '{"valid": true}'},
            },
            # Missing fields
            {"id": "invalid_3", "function": {}},
        ]

        available_tools = []
        mcp_tools = []

        # Execute tool calls - should handle errors gracefully
        results = node._execute_tool_calls(tool_calls, available_tools, mcp_tools)

        # Should have results for all tool calls
        assert len(results) == 4

        # Check that valid ones succeeded
        assert results[0]["tool_call_id"] == "valid_1"
        assert "error" not in json.loads(results[0]["content"])

        assert results[2]["tool_call_id"] == "valid_2"
        assert "error" not in json.loads(results[2]["content"])

        # Check that invalid ones have error messages
        assert results[1]["tool_call_id"] == "invalid_json"
        error_content = json.loads(results[1]["content"])
        assert "error" in error_content
        assert "Invalid JSON" in error_content["error"]

        assert results[3]["tool_call_id"] == "invalid_3"
        error_content = json.loads(results[3]["content"])
        assert "error" in error_content
        assert "missing required" in error_content["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
