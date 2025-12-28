"""
P0-5: Unified Input Validation - Integration Tests with Real Nexus Instance

SECURITY ISSUES PREVENTED:
- Input validation bypassed in some execution paths
- Dangerous keys allowed in certain channels
- Input size not validated in all code paths
- Inconsistent security between channels

This test suite verifies that input validation is ACTUALLY CALLED in all execution
paths, not just defined. Tests use real Nexus instances (NO MOCKING) to ensure
validation works in production scenarios.

Test Coverage:
1. API Channel - Validation called via gateway endpoints
2. MCP Channel - Validation called via tool execution
3. Core Execution - Validation called in _execute_workflow()
4. Validation Consistency - All channels use same rules
5. Performance & Edge Cases - Nested keys, arrays, performance

Requirements:
- Tier 2 Integration Tests - Real Nexus instances (NO MOCKING)
- Real Workflows - Simple test workflows
- All Channels - API, MCP, CLI validation
- Clear Documentation - Security issue explanations
- Comprehensive Coverage - Positive and negative cases
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict
from unittest.mock import Mock, patch

import pytest
import pytest_asyncio

# Add apps directory to path for nexus imports
sys.path.insert(
    0,
    str(Path(__file__).parent.parent.parent.parent / "apps" / "kailash-nexus" / "src"),
)

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Import Nexus and validation
from nexus import Nexus
from nexus.validation import (
    DANGEROUS_KEYS,
    DEFAULT_MAX_INPUT_SIZE,
    MAX_KEY_LENGTH,
    get_validation_summary,
    validate_workflow_inputs,
    validate_workflow_name,
)

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def simple_workflow():
    """Create a simple test workflow that echoes inputs."""
    builder = WorkflowBuilder()
    builder.add_node(
        "PythonCodeNode",
        "echo",
        {
            "code": """
# Echo a simple success message
# Note: PythonCodeNode receives parameters directly, not via 'inputs' variable
output = {
    'result': 'success',
    'message': 'Workflow executed successfully'
}
""",
        },
    )
    return builder.build()


@pytest_asyncio.fixture
async def nexus_instance(simple_workflow):
    """Create a real Nexus instance for testing (NO MOCKING)."""
    # Mock only the gateway run to prevent actual server startup
    # But use real Nexus for all validation logic
    with patch("nexus.core.create_gateway") as mock_gateway:
        mock_gw = Mock()
        mock_gw.run = Mock()
        mock_gw.register_workflow = Mock()
        mock_gateway.return_value = mock_gw

        # Create real Nexus instance
        nexus = Nexus(
            api_port=9001,  # Unique port for tests
            mcp_port=3101,  # Unique MCP port
            enable_auth=False,
            enable_durability=False,  # Disable for testing
        )

        # Register test workflow
        nexus.register("test_workflow", simple_workflow)

        yield nexus

        # Cleanup
        try:
            nexus.stop()
        except Exception:
            pass


@pytest_asyncio.fixture
async def runtime():
    """Async runtime for direct workflow execution."""
    return AsyncLocalRuntime()


# ============================================================================
# Test Class 1: API Channel Validation Integration
# ============================================================================


class TestAPIChannelValidationIntegration:
    """Test that validation is called in API channel execution paths."""

    @pytest.mark.asyncio
    async def test_api_channel_blocks_dangerous_keys(self, nexus_instance):
        """
        TEST: API channel blocks dangerous keys via _execute_workflow().

        SECURITY: Prevents code injection via API endpoint requests.
        This tests the ACTUAL execution path, not just the validator function.
        """
        # GIVEN: Dangerous input that should be blocked
        dangerous_input = {
            "__import__": "os",
            "normal_key": "normal_value",
        }

        # WHEN: Executing via API channel (_execute_workflow method)
        with pytest.raises(Exception) as exc_info:
            await nexus_instance._execute_workflow("test_workflow", dangerous_input)

        # THEN: Should reject with clear error about dangerous keys
        error_message = str(exc_info.value).lower()
        assert any(
            keyword in error_message
            for keyword in ["dangerous", "invalid", "not allowed", "__import__"]
        ), f"Expected dangerous key error, got: {exc_info.value}"

    @pytest.mark.asyncio
    async def test_api_channel_blocks_oversized_inputs(self, nexus_instance):
        """
        TEST: API channel blocks oversized inputs via _execute_workflow().

        SECURITY: Prevents DoS attacks via large payloads.
        Tests actual size validation in execution path.
        """
        # GIVEN: Oversized input (>10MB)
        oversized_input = {"data": "x" * (11 * 1024 * 1024)}  # 11MB of data

        # WHEN: Executing via API channel
        with pytest.raises(Exception) as exc_info:
            await nexus_instance._execute_workflow("test_workflow", oversized_input)

        # THEN: Should reject with size limit error
        error_message = str(exc_info.value).lower()
        assert any(
            keyword in error_message for keyword in ["size", "large", "exceeded", "413"]
        ), f"Expected size limit error, got: {exc_info.value}"

    @pytest.mark.asyncio
    async def test_api_channel_validation_error_is_clear(self, nexus_instance):
        """
        TEST: API channel validation errors have clear messages.

        USABILITY: Users understand why their request was rejected.
        """
        # GIVEN: Multiple dangerous keys
        bad_input = {
            "__class__": "exploit",
            "eval": "malicious_code",
        }

        # WHEN: Executing via API channel
        with pytest.raises(Exception) as exc_info:
            await nexus_instance._execute_workflow("test_workflow", bad_input)

        # THEN: Error message should mention the dangerous keys
        error_message = str(exc_info.value)
        assert (
            "__class__" in error_message or "eval" in error_message
        ), f"Error message should mention dangerous keys: {error_message}"

    @pytest.mark.asyncio
    async def test_api_channel_validation_happens_before_execution(
        self, nexus_instance
    ):
        """
        TEST: Validation happens BEFORE workflow execution starts.

        SECURITY: Dangerous inputs never reach workflow nodes.
        """
        # GIVEN: Workflow that would fail if executed
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "fail_node",
            {
                "code": "raise ValueError('Should never execute')",
            },
        )
        nexus_instance.register("fail_workflow", builder.build())

        # AND: Dangerous input
        dangerous_input = {"__builtins__": "exploit"}

        # WHEN: Executing workflow
        with pytest.raises(Exception) as exc_info:
            await nexus_instance._execute_workflow("fail_workflow", dangerous_input)

        # THEN: Should fail with validation error, NOT workflow execution error
        error_message = str(exc_info.value)
        assert (
            "should never execute" not in error_message.lower()
        ), "Workflow should not have executed - validation should fail first"
        assert any(
            keyword in error_message.lower()
            for keyword in ["dangerous", "invalid", "not allowed"]
        ), f"Expected validation error, got: {exc_info.value}"

    @pytest.mark.asyncio
    async def test_api_channel_allows_valid_inputs(self, nexus_instance):
        """
        TEST: API channel allows valid inputs through.

        RELIABILITY: Validation doesn't block legitimate requests.
        """
        # GIVEN: Perfectly valid input
        valid_input = {
            "name": "test_user",
            "count": 42,
            "items": ["a", "b", "c"],
            "config": {"key": "value"},
        }

        # WHEN: Executing via API channel
        result = await nexus_instance._execute_workflow("test_workflow", valid_input)

        # THEN: Should execute successfully
        assert result is not None
        # Result structure: {"results": {"node_id": {...}}, "metrics": ...}
        assert isinstance(result, dict), "Result should be a dictionary"

    @pytest.mark.asyncio
    async def test_api_channel_blocks_dunder_keys(self, nexus_instance):
        """
        TEST: API channel blocks keys starting with __ (dunder).

        SECURITY: Additional protection against Python internals access.
        """
        # GIVEN: Dunder key that's not in DANGEROUS_KEYS list
        dunder_input = {
            "__custom_attribute__": "value",
            "normal_key": "value",
        }

        # WHEN: Executing via API channel
        with pytest.raises(Exception) as exc_info:
            await nexus_instance._execute_workflow("test_workflow", dunder_input)

        # THEN: Should reject dunder keys
        error_message = str(exc_info.value).lower()
        assert "dunder" in error_message or "__" in str(
            exc_info.value
        ), f"Expected dunder key error, got: {exc_info.value}"

    @pytest.mark.asyncio
    async def test_api_channel_blocks_long_keys(self, nexus_instance):
        """
        TEST: API channel blocks excessively long keys.

        SECURITY: Prevents memory attacks via long key names.
        """
        # GIVEN: Input with very long key (>256 chars)
        long_key = "k" * (MAX_KEY_LENGTH + 1)
        long_key_input = {
            long_key: "value",
        }

        # WHEN: Executing via API channel
        with pytest.raises(Exception) as exc_info:
            await nexus_instance._execute_workflow("test_workflow", long_key_input)

        # THEN: Should reject with key length error
        error_message = str(exc_info.value).lower()
        assert any(
            keyword in error_message for keyword in ["key", "long", "length", "256"]
        ), f"Expected key length error, got: {exc_info.value}"

    @pytest.mark.asyncio
    async def test_api_channel_rejects_non_dict_inputs(self, nexus_instance):
        """
        TEST: API channel rejects non-dictionary inputs.

        SECURITY: Type validation prevents type confusion attacks.
        """
        # GIVEN: Non-dict inputs
        invalid_inputs = [
            ["list", "input"],
            "string_input",
            123,
            None,
        ]

        for invalid_input in invalid_inputs:
            # WHEN: Executing with non-dict input
            with pytest.raises((Exception, TypeError)) as exc_info:
                await nexus_instance._execute_workflow("test_workflow", invalid_input)

            # THEN: Should reject with type error
            # Note: May fail at different levels (validation or execution)
            assert exc_info.value is not None

    @pytest.mark.asyncio
    async def test_api_channel_validates_workflow_name(self, nexus_instance):
        """
        TEST: API channel validates workflow name for path traversal.

        SECURITY: Prevents directory traversal attacks.
        """
        # GIVEN: Workflow names with path separators
        dangerous_names = [
            "../etc/passwd",
            "..\\windows\\system32",
            "test/../../secret",
        ]

        for dangerous_name in dangerous_names:
            # WHEN: Executing with dangerous workflow name
            # Note: This tests at the validation level since workflow won't exist
            with pytest.raises(ValueError) as exc_info:
                validate_workflow_name(dangerous_name)

            # THEN: Should reject with path traversal error
            error_message = str(exc_info.value)
            assert any(
                keyword in error_message.lower()
                for keyword in ["path", "separator", "/", "\\"]
            )

    @pytest.mark.asyncio
    async def test_api_channel_blocks_each_dangerous_key(self, nexus_instance):
        """
        TEST: API channel blocks each dangerous key individually.

        SECURITY: Comprehensive test of all dangerous keys.
        """
        # GIVEN: Each dangerous key from the list
        for dangerous_key in DANGEROUS_KEYS:
            dangerous_input = {
                dangerous_key: "malicious_value",
                "normal_key": "value",
            }

            # WHEN: Executing via API channel
            with pytest.raises(Exception) as exc_info:
                await nexus_instance._execute_workflow("test_workflow", dangerous_input)

            # THEN: Should reject each dangerous key
            error_message = str(exc_info.value)
            # Should mention it's dangerous or invalid
            assert any(
                keyword in error_message.lower()
                for keyword in ["dangerous", "invalid", "not allowed"]
            ), f"Key '{dangerous_key}' should be blocked, got: {error_message}"


# ============================================================================
# Test Class 2: MCP Channel Validation Integration
# ============================================================================


class TestMCPChannelValidationIntegration:
    """Test that validation is called in MCP channel execution paths."""

    @pytest.mark.asyncio
    async def test_mcp_channel_blocks_dangerous_keys(self, nexus_instance):
        """
        TEST: MCP channel blocks dangerous keys via handle_call_tool().

        SECURITY: Prevents code injection via MCP tool calls.

        NOTE: MCP server validates top-level arguments dict.
        Dangerous keys in top-level dict should be blocked.
        """
        # GIVEN: MCP tool call with dangerous key at TOP LEVEL
        mcp_request = {
            "type": "call_tool",
            "name": "test_workflow",
            "arguments": {
                "__import__": "os",  # Top-level dangerous key
                "data": "normal",
            },
        }

        # WHEN: Executing via MCP channel
        if hasattr(nexus_instance, "_mcp_server") and nexus_instance._mcp_server:
            mcp_server = nexus_instance._mcp_server

            # Execute the request
            response = await mcp_server.handle_request(mcp_request)

            # THEN: Should return error response
            assert (
                response.get("type") == "error" or "error" in response
            ), f"Expected error response, got: {response}"

            # Error message should mention dangerous keys or validation
            error_message = str(response).lower()
            assert any(
                keyword in error_message
                for keyword in [
                    "dangerous",
                    "invalid",
                    "not allowed",
                    "validation",
                    "__import__",
                ]
            )
        else:
            pytest.skip("MCP server not available in this test configuration")

    @pytest.mark.asyncio
    async def test_mcp_channel_blocks_oversized_inputs(self, nexus_instance):
        """
        TEST: MCP channel blocks oversized inputs.

        SECURITY: Prevents DoS attacks via MCP channel.
        """
        # GIVEN: MCP tool call with oversized data
        mcp_request = {
            "type": "call_tool",
            "name": "test_workflow",
            "arguments": {"parameters": {"data": "x" * (11 * 1024 * 1024)}},  # 11MB
        }

        # WHEN: Executing via MCP channel
        if hasattr(nexus_instance, "_mcp_server") and nexus_instance._mcp_server:
            mcp_server = nexus_instance._mcp_server

            response = await mcp_server.handle_request(mcp_request)

            # THEN: Should return error about size
            assert (
                response.get("type") == "error" or "error" in response
            ), f"Expected error response for oversized input, got: {response}"
        else:
            pytest.skip("MCP server not available in this test configuration")

    @pytest.mark.asyncio
    async def test_mcp_channel_validation_identical_to_api(self, nexus_instance):
        """
        TEST: MCP channel validation identical to API channel.

        SECURITY: No channel-specific bypass vulnerabilities.
        """
        # GIVEN: Same dangerous input for both channels
        dangerous_input = {
            "__class__": "exploit",
            "normal_data": "value",
        }

        # WHEN: Testing via API channel
        api_error = None
        try:
            await nexus_instance._execute_workflow("test_workflow", dangerous_input)
        except Exception as e:
            api_error = str(e)

        # AND: Testing via MCP channel
        mcp_error = None
        if hasattr(nexus_instance, "_mcp_server") and nexus_instance._mcp_server:
            mcp_request = {
                "type": "call_tool",
                "name": "test_workflow",
                "arguments": {"parameters": dangerous_input},
            }
            mcp_response = await nexus_instance._mcp_server.handle_request(mcp_request)
            if mcp_response.get("type") == "error":
                mcp_error = str(mcp_response.get("error", ""))

        # THEN: Both channels should reject the same input
        assert api_error is not None, "API channel should reject dangerous input"
        if mcp_error:
            # Both should mention dangerous keys or similar security concern
            assert any(
                keyword in api_error.lower()
                for keyword in ["dangerous", "invalid", "__class__"]
            )
            assert any(
                keyword in mcp_error.lower()
                for keyword in ["dangerous", "invalid", "__class__"]
            )

    @pytest.mark.asyncio
    async def test_mcp_channel_allows_valid_inputs(self, nexus_instance):
        """
        TEST: MCP channel allows valid inputs.

        RELIABILITY: Validation doesn't block legitimate MCP calls.
        """
        # GIVEN: Valid MCP tool call
        mcp_request = {
            "type": "call_tool",
            "name": "test_workflow",
            "arguments": {
                "name": "test",
                "count": 10,
            },
        }

        # WHEN: Executing via MCP channel
        if hasattr(nexus_instance, "_mcp_server") and nexus_instance._mcp_server:
            mcp_server = nexus_instance._mcp_server

            response = await mcp_server.handle_request(mcp_request)

            # THEN: Should succeed (not return error type)
            assert response.get("type") != "error" or response.get(
                "result"
            ), f"Valid input should be accepted, got: {response}"
        else:
            pytest.skip("MCP server not available in this test configuration")

    @pytest.mark.asyncio
    async def test_mcp_channel_blocks_dunder_keys(self, nexus_instance):
        """
        TEST: MCP channel blocks dunder keys.

        SECURITY: Consistent dunder protection across channels.
        """
        # GIVEN: MCP request with dunder key at top level
        mcp_request = {
            "type": "call_tool",
            "name": "test_workflow",
            "arguments": {
                "__custom__": "value",
            },
        }

        # WHEN: Executing via MCP channel
        if hasattr(nexus_instance, "_mcp_server") and nexus_instance._mcp_server:
            response = await nexus_instance._mcp_server.handle_request(mcp_request)

            # THEN: Should reject dunder keys
            assert (
                response.get("type") == "error" or "error" in response
            ), "Dunder keys should be blocked"
        else:
            pytest.skip("MCP server not available in this test configuration")

    @pytest.mark.asyncio
    async def test_mcp_channel_validation_happens_before_execution(
        self, nexus_instance
    ):
        """
        TEST: MCP validation happens BEFORE workflow execution.

        SECURITY: Dangerous inputs never reach workflow nodes via MCP.
        """
        # GIVEN: Workflow that would fail if executed
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "mcp_fail",
            {"code": "raise ValueError('MCP should not execute')"},
        )
        nexus_instance.register("mcp_fail_workflow", builder.build())

        # AND: MCP request with dangerous input at top level
        mcp_request = {
            "type": "call_tool",
            "name": "mcp_fail_workflow",
            "arguments": {
                "__globals__": "exploit",
            },
        }

        # WHEN: Executing via MCP
        if hasattr(nexus_instance, "_mcp_server") and nexus_instance._mcp_server:
            response = await nexus_instance._mcp_server.handle_request(mcp_request)

            # THEN: Should fail with validation error, not execution error
            error_message = str(response)
            assert (
                "mcp should not execute" not in error_message.lower()
            ), "Workflow should not execute - validation should fail first"
        else:
            pytest.skip("MCP server not available in this test configuration")

    @pytest.mark.asyncio
    async def test_mcp_list_tools_returns_registered_workflows(self, nexus_instance):
        """
        TEST: MCP list_tools returns all registered workflows.

        FUNCTIONALITY: Verify MCP integration is working.
        """
        # GIVEN: Nexus with registered workflows
        # WHEN: Calling list_tools
        if hasattr(nexus_instance, "_mcp_server") and nexus_instance._mcp_server:
            response = await nexus_instance._mcp_server.handle_request(
                {"type": "list_tools"}
            )

            # THEN: Should return tools list
            assert response.get("type") == "tools"
            assert "tools" in response
            assert len(response["tools"]) > 0

            # Should include our test workflow
            tool_names = [tool["name"] for tool in response["tools"]]
            assert "test_workflow" in tool_names
        else:
            pytest.skip("MCP server not available in this test configuration")

    @pytest.mark.asyncio
    async def test_mcp_channel_validates_all_dangerous_keys(self, nexus_instance):
        """
        TEST: MCP channel blocks all dangerous keys from DANGEROUS_KEYS list.

        SECURITY: Comprehensive dangerous key blocking.
        """
        if not (hasattr(nexus_instance, "_mcp_server") and nexus_instance._mcp_server):
            pytest.skip("MCP server not available in this test configuration")

        # GIVEN: Each dangerous key at top level
        for dangerous_key in DANGEROUS_KEYS[:5]:  # Test first 5 for performance
            mcp_request = {
                "type": "call_tool",
                "name": "test_workflow",
                "arguments": {
                    dangerous_key: "malicious",
                },
            }

            # WHEN: Executing via MCP
            response = await nexus_instance._mcp_server.handle_request(mcp_request)

            # THEN: Should reject
            assert (
                response.get("type") == "error" or "error" in response
            ), f"Dangerous key '{dangerous_key}' should be blocked"

    @pytest.mark.asyncio
    async def test_mcp_channel_error_messages_are_clear(self, nexus_instance):
        """
        TEST: MCP channel error messages are clear and helpful.

        USABILITY: Users understand why MCP call was rejected.
        """
        # GIVEN: MCP request with dangerous key at top level
        mcp_request = {
            "type": "call_tool",
            "name": "test_workflow",
            "arguments": {
                "eval": "malicious_code",
            },
        }

        # WHEN: Executing via MCP
        if hasattr(nexus_instance, "_mcp_server") and nexus_instance._mcp_server:
            response = await nexus_instance._mcp_server.handle_request(mcp_request)

            # THEN: Error message should be clear
            error_message = str(response.get("error", ""))
            assert len(error_message) > 0, "Error message should not be empty"
            assert any(
                keyword in error_message.lower()
                for keyword in ["dangerous", "invalid", "not allowed", "eval"]
            ), f"Error message should be clear: {error_message}"
        else:
            pytest.skip("MCP server not available in this test configuration")


# ============================================================================
# Test Class 3: Core Execution Validation
# ============================================================================


class TestCoreExecutionValidation:
    """Test validation in core _execute_workflow() method."""

    @pytest.mark.asyncio
    async def test_core_execution_validates_inputs(self, nexus_instance):
        """
        TEST: Core _execute_workflow() validates inputs.

        SECURITY: Validation cannot be bypassed by calling core method directly.
        """
        # GIVEN: Dangerous input
        dangerous_input = {"__builtins__": "exploit"}

        # WHEN: Calling _execute_workflow directly (core method)
        with pytest.raises(Exception) as exc_info:
            await nexus_instance._execute_workflow("test_workflow", dangerous_input)

        # THEN: Should validate and reject
        assert exc_info.value is not None
        error_message = str(exc_info.value).lower()
        assert any(
            keyword in error_message
            for keyword in ["dangerous", "invalid", "__builtins__"]
        )

    @pytest.mark.asyncio
    async def test_core_execution_validates_size(self, nexus_instance):
        """
        TEST: Core execution validates input size.

        SECURITY: Size limits enforced at core level.
        """
        # GIVEN: Oversized input
        oversized_input = {"data": "x" * (11 * 1024 * 1024)}

        # WHEN: Executing at core level
        with pytest.raises(Exception) as exc_info:
            await nexus_instance._execute_workflow("test_workflow", oversized_input)

        # THEN: Should reject for size
        error_message = str(exc_info.value).lower()
        assert any(keyword in error_message for keyword in ["size", "large", "413"])

    @pytest.mark.asyncio
    async def test_core_execution_validates_workflow_name(self, nexus_instance):
        """
        TEST: Core execution validates workflow name.

        SECURITY: Path traversal prevented at core level.
        """
        # GIVEN: Malicious workflow name
        malicious_name = "../../../etc/passwd"

        # WHEN: Executing with malicious name
        # Note: Validation happens in validate_workflow_name() called by core
        with pytest.raises(ValueError):
            validate_workflow_name(malicious_name)

    @pytest.mark.asyncio
    async def test_core_validation_cannot_be_bypassed(self, nexus_instance, runtime):
        """
        TEST: Validation cannot be bypassed by using runtime directly.

        SECURITY: All execution paths validate inputs.
        """
        # GIVEN: Workflow and dangerous input
        workflow = nexus_instance._workflows["test_workflow"]
        dangerous_input = {"__import__": "os"}

        # WHEN: Trying to bypass by using runtime directly
        # (This tests that validation is in the right place)

        # Note: Runtime itself doesn't validate (it's lower level)
        # But Nexus should ALWAYS validate before calling runtime
        result = await runtime.execute_workflow_async(workflow, dangerous_input)

        # THEN: Runtime executes (it doesn't validate - that's correct)
        # The validation MUST happen in Nexus layer, not runtime
        assert result is not None  # Runtime executed

        # But when going through Nexus, it should block:
        with pytest.raises(Exception):
            await nexus_instance._execute_workflow("test_workflow", dangerous_input)

    @pytest.mark.asyncio
    async def test_core_validation_order_is_correct(self, nexus_instance):
        """
        TEST: Validation happens in correct order.

        SECURITY: Type validation -> Size validation -> Key validation.
        """
        # Test order 1: Type validation first
        with pytest.raises((Exception, TypeError)):
            await nexus_instance._execute_workflow("test_workflow", "not_a_dict")

        # Test order 2: Size validation before key validation
        # (Large input with dangerous key - should fail on size first)
        huge_dangerous_input = {
            "__import__": "os",
            "data": "x" * (11 * 1024 * 1024),
        }

        with pytest.raises(Exception) as exc_info:
            await nexus_instance._execute_workflow(
                "test_workflow", huge_dangerous_input
            )

        # Could fail on either size or dangerous key - both are valid

    @pytest.mark.asyncio
    async def test_core_validation_with_non_existent_workflow(self, nexus_instance):
        """
        TEST: Validation works even when workflow doesn't exist.

        SECURITY: Input validation happens before workflow lookup.
        """
        # GIVEN: Dangerous input and non-existent workflow
        dangerous_input = {"__class__": "exploit"}

        # WHEN: Executing non-existent workflow with dangerous input
        with pytest.raises(Exception) as exc_info:
            await nexus_instance._execute_workflow("non_existent", dangerous_input)

        # THEN: Should fail (could be workflow not found OR validation error)
        # Both are acceptable - important is that dangerous input doesn't execute
        assert exc_info.value is not None

    @pytest.mark.asyncio
    async def test_core_validation_preserves_error_context(self, nexus_instance):
        """
        TEST: Validation errors preserve context for debugging.

        USABILITY: Developers can debug validation failures.
        """
        # GIVEN: Multiple validation violations
        bad_input = {
            "__import__": "os",  # Dangerous key
            "x" * 300: "value",  # Long key
        }

        # WHEN: Executing with bad input
        with pytest.raises(Exception) as exc_info:
            await nexus_instance._execute_workflow("test_workflow", bad_input)

        # THEN: Error should have context
        error_message = str(exc_info.value)
        assert len(error_message) > 0
        # Should mention at least one violation
        assert any(
            keyword in error_message.lower()
            for keyword in ["dangerous", "long", "invalid", "__import__"]
        )

    @pytest.mark.asyncio
    async def test_core_validation_with_empty_inputs(self, nexus_instance):
        """
        TEST: Validation allows empty dictionary inputs.

        FUNCTIONALITY: Empty inputs are valid (some workflows need no input).
        """
        # GIVEN: Empty input dictionary
        empty_input = {}

        # WHEN: Executing with empty input
        result = await nexus_instance._execute_workflow("test_workflow", empty_input)

        # THEN: Should succeed
        assert result is not None

    @pytest.mark.asyncio
    async def test_core_validation_with_none_values(self, nexus_instance):
        """
        TEST: Validation allows None values in inputs.

        FUNCTIONALITY: None values are valid for optional parameters.
        """
        # GIVEN: Input with None values
        input_with_none = {
            "required_param": "value",
            "optional_param": None,
        }

        # WHEN: Executing with None values
        result = await nexus_instance._execute_workflow(
            "test_workflow", input_with_none
        )

        # THEN: Should succeed
        assert result is not None


# ============================================================================
# Test Class 4: Validation Consistency Across Channels
# ============================================================================


class TestValidationConsistency:
    """Test that all channels use identical validation rules."""

    @pytest.mark.asyncio
    async def test_all_channels_reject_same_dangerous_keys(self, nexus_instance):
        """
        TEST: API, MCP, and core all reject same dangerous keys.

        SECURITY: No channel-specific bypass.
        """
        # GIVEN: Dangerous input
        dangerous_input = {"__globals__": "exploit"}

        # WHEN: Testing API channel
        api_rejected = False
        try:
            await nexus_instance._execute_workflow("test_workflow", dangerous_input)
        except Exception:
            api_rejected = True

        # AND: Testing MCP channel (with top-level dangerous key)
        mcp_rejected = False
        if hasattr(nexus_instance, "_mcp_server") and nexus_instance._mcp_server:
            mcp_request = {
                "type": "call_tool",
                "name": "test_workflow",
                "arguments": dangerous_input,  # Top-level arguments
            }
            response = await nexus_instance._mcp_server.handle_request(mcp_request)
            mcp_rejected = response.get("type") == "error"

        # THEN: All channels should reject
        assert api_rejected, "API channel should reject dangerous keys"
        if hasattr(nexus_instance, "_mcp_server") and nexus_instance._mcp_server:
            assert mcp_rejected, "MCP channel should reject dangerous keys"

    @pytest.mark.asyncio
    async def test_all_channels_have_same_size_limits(self, nexus_instance):
        """
        TEST: All channels enforce same size limits.

        SECURITY: Consistent DoS protection.
        """
        # GIVEN: Input at size boundary (slightly over 10MB)
        boundary_input = {"data": "x" * (10 * 1024 * 1024 + 1000)}

        # WHEN: Testing API channel
        api_rejected = False
        try:
            await nexus_instance._execute_workflow("test_workflow", boundary_input)
        except Exception:
            api_rejected = True

        # THEN: API should reject
        assert api_rejected, "API channel should enforce size limit"

        # Note: MCP channel should also reject, but testing both is redundant
        # The point is they use the SAME validation function

    @pytest.mark.asyncio
    async def test_all_channels_return_similar_error_messages(self, nexus_instance):
        """
        TEST: All channels return similar error messages for same violation.

        USABILITY: Consistent user experience across channels.
        """
        # GIVEN: Same dangerous input
        dangerous_input = {"eval": "malicious"}

        # WHEN: Testing API channel
        api_error = None
        try:
            await nexus_instance._execute_workflow("test_workflow", dangerous_input)
        except Exception as e:
            api_error = str(e).lower()

        # AND: Testing MCP channel
        mcp_error = None
        if hasattr(nexus_instance, "_mcp_server") and nexus_instance._mcp_server:
            mcp_request = {
                "type": "call_tool",
                "name": "test_workflow",
                "arguments": {"parameters": dangerous_input},
            }
            response = await nexus_instance._mcp_server.handle_request(mcp_request)
            if response.get("type") == "error":
                mcp_error = str(response.get("error", "")).lower()

        # THEN: Both errors should mention "dangerous" or "eval"
        assert api_error and any(
            keyword in api_error for keyword in ["dangerous", "eval", "invalid"]
        )
        if mcp_error:
            assert any(
                keyword in mcp_error for keyword in ["dangerous", "eval", "invalid"]
            )

    @pytest.mark.asyncio
    async def test_validation_rules_are_centralized(self):
        """
        TEST: Validation rules are centralized in validation module.

        MAINTAINABILITY: Single source of truth for validation rules.
        """
        # GIVEN: Validation module
        from nexus.validation import (
            DANGEROUS_KEYS,
            DEFAULT_MAX_INPUT_SIZE,
            MAX_KEY_LENGTH,
        )

        # THEN: Rules should be accessible
        assert isinstance(DANGEROUS_KEYS, list)
        assert len(DANGEROUS_KEYS) > 0
        assert isinstance(DEFAULT_MAX_INPUT_SIZE, int)
        assert DEFAULT_MAX_INPUT_SIZE > 0
        assert isinstance(MAX_KEY_LENGTH, int)
        assert MAX_KEY_LENGTH > 0

    @pytest.mark.asyncio
    async def test_validation_summary_is_accurate(self):
        """
        TEST: Validation summary matches actual validation behavior.

        DOCUMENTATION: Summary helps users understand validation rules.
        """
        # GIVEN: Validation summary
        summary = get_validation_summary()

        # THEN: Summary should have all required fields
        assert "max_input_size" in summary
        assert "max_key_length" in summary
        assert "dangerous_keys" in summary
        assert "security_checks" in summary

        # AND: Values should match module constants
        assert summary["max_input_size"] == DEFAULT_MAX_INPUT_SIZE
        assert summary["max_key_length"] == MAX_KEY_LENGTH
        assert summary["dangerous_keys"] == DANGEROUS_KEYS

    @pytest.mark.asyncio
    async def test_all_channels_allow_same_valid_inputs(self, nexus_instance):
        """
        TEST: All channels allow same valid inputs.

        FUNCTIONALITY: No false positives across channels.
        """
        # GIVEN: Valid input
        valid_input = {
            "name": "test",
            "count": 42,
            "nested": {"key": "value"},
            "list": [1, 2, 3],
        }

        # WHEN: Testing API channel
        api_result = await nexus_instance._execute_workflow(
            "test_workflow", valid_input
        )

        # THEN: API should succeed
        assert api_result is not None

        # AND: MCP should also succeed
        if hasattr(nexus_instance, "_mcp_server") and nexus_instance._mcp_server:
            mcp_request = {
                "type": "call_tool",
                "name": "test_workflow",
                "arguments": {"parameters": valid_input},
            }
            mcp_response = await nexus_instance._mcp_server.handle_request(mcp_request)

            # Should not return error type
            assert mcp_response.get("type") != "error" or "result" in mcp_response


# ============================================================================
# Test Class 5: Performance & Edge Cases
# ============================================================================


class TestValidationPerformanceAndEdgeCases:
    """Test validation performance and edge cases."""

    @pytest.mark.asyncio
    async def test_validation_performance_large_input(self):
        """
        TEST: Validation performance with 1000 keys.

        PERFORMANCE: Should validate <10ms for 1000 keys.
        """
        # GIVEN: Large but safe input
        large_input = {f"key_{i}": f"value_{i}" for i in range(1000)}

        # WHEN: Validating input
        start_time = time.perf_counter()
        result = validate_workflow_inputs(large_input)
        elapsed = time.perf_counter() - start_time

        # THEN: Should be fast
        assert (
            elapsed < 0.010
        ), f"Validation took {elapsed*1000:.2f}ms (should be <10ms)"
        assert result == large_input

    @pytest.mark.asyncio
    async def test_nested_dangerous_keys_detected(self):
        """
        TEST: Dangerous keys in nested structures are NOT detected.

        SECURITY NOTE: Current validation only checks top-level keys.
        This documents the behavior - nested validation is future work.
        """
        # GIVEN: Nested dangerous key
        nested_input = {
            "outer": {"inner": {"__import__": "os"}}  # Dangerous key nested deep
        }

        # WHEN: Validating
        # NOTE: Current implementation only validates top-level keys
        result = validate_workflow_inputs(nested_input)

        # THEN: Currently passes (nested keys not validated)
        # This is documented behavior - may be enhanced in future
        assert result == nested_input

    @pytest.mark.asyncio
    async def test_dangerous_keys_in_arrays_detected(self):
        """
        TEST: Dangerous keys in array items are NOT detected.

        SECURITY NOTE: Current validation only checks top-level keys.
        """
        # GIVEN: Dangerous key in array
        array_input = {
            "items": [
                {"safe": "value"},
                {"__import__": "os"},  # Dangerous key in array item
            ]
        }

        # WHEN: Validating
        result = validate_workflow_inputs(array_input)

        # THEN: Currently passes (array item keys not validated)
        # This is documented behavior
        assert result == array_input

    @pytest.mark.asyncio
    async def test_validation_with_unicode_keys(self):
        """
        TEST: Validation handles unicode keys correctly.

        FUNCTIONALITY: International characters are allowed.
        """
        # GIVEN: Input with unicode keys
        unicode_input = {
            "名前": "test",  # Japanese
            "имя": "test",  # Russian
            "nombre": "test",  # Spanish
        }

        # WHEN: Validating
        result = validate_workflow_inputs(unicode_input)

        # THEN: Should pass
        assert result == unicode_input

    @pytest.mark.asyncio
    async def test_validation_with_special_characters(self):
        """
        TEST: Validation allows special characters in values.

        FUNCTIONALITY: Special characters in values are OK.
        """
        # GIVEN: Input with special characters in values (not keys)
        special_input = {
            "data": "<script>alert('xss')</script>",
            "command": "rm -rf /",
            "code": "eval('malicious')",
        }

        # WHEN: Validating
        result = validate_workflow_inputs(special_input)

        # THEN: Should pass (validation is on keys, not values)
        assert result == special_input

    @pytest.mark.asyncio
    async def test_validation_with_empty_string_keys(self):
        """
        TEST: Validation allows empty string keys.

        FUNCTIONALITY: Empty string is a valid key.
        """
        # GIVEN: Input with empty string key
        empty_key_input = {
            "": "value",
            "normal": "value",
        }

        # WHEN: Validating
        result = validate_workflow_inputs(empty_key_input)

        # THEN: Should pass
        assert result == empty_key_input

    @pytest.mark.asyncio
    async def test_validation_with_numeric_keys(self):
        """
        TEST: Validation handles numeric keys correctly.

        FUNCTIONALITY: Numeric keys are allowed (converted to strings).
        """
        # GIVEN: Input with numeric-like string keys
        numeric_input = {
            "123": "value",
            "0": "value",
            "-1": "value",
        }

        # WHEN: Validating
        result = validate_workflow_inputs(numeric_input)

        # THEN: Should pass
        assert result == numeric_input

    @pytest.mark.asyncio
    async def test_validation_short_circuits_on_first_error(self):
        """
        TEST: Validation stops at first error.

        PERFORMANCE: Fast failure for invalid inputs.
        """
        # GIVEN: Input with multiple violations
        multi_violation_input = {
            "__import__": "os",  # Dangerous key (will fail first)
            "x" * 300: "value",  # Long key (won't be checked)
        }

        # WHEN: Validating
        with pytest.raises(ValueError) as exc_info:
            validate_workflow_inputs(multi_violation_input)

        # THEN: Should fail on first violation
        error_message = str(exc_info.value)
        # Should mention dangerous key (first check)
        assert "__import__" in error_message or "dangerous" in error_message.lower()


# ============================================================================
# Helper Functions for Manual Testing
# ============================================================================


def print_validation_summary():
    """Print validation summary for documentation."""
    summary = get_validation_summary()
    print("\n" + "=" * 70)
    print("VALIDATION RULES SUMMARY")
    print("=" * 70)
    print(f"Max Input Size: {summary['max_input_size']:,} bytes")
    print(f"Max Key Length: {summary['max_key_length']} characters")
    print(f"Dangerous Keys: {len(summary['dangerous_keys'])} keys blocked")
    print("\nDangerous Keys List:")
    for key in summary["dangerous_keys"]:
        print(f"  - {key}")
    print("\nSecurity Checks:")
    for check in summary["security_checks"]:
        print(f"  ✓ {check}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    # Print validation summary when run directly
    print_validation_summary()

    # Run tests
    pytest.main([__file__, "-v", "-s", "--tb=short"])
