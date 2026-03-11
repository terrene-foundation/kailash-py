"""
Tier 1 Unit Tests for BaseAgent MCP Tool Approval Workflow

Tests the integration of danger levels with BaseAgent's execute_mcp_tool method.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import InputField, OutputField, Signature


class TestSignature(Signature):
    """Simple test signature."""

    input: str = InputField(description="Test input")
    output: str = OutputField(description="Test output")


class TestMCPToolApprovalWorkflow:
    """Test BaseAgent MCP tool execution with approval workflow."""

    @pytest.mark.asyncio
    async def test_safe_tool_executes_without_approval(self):
        """Test SAFE tools execute without approval request."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        agent = BaseAgent(config=config, signature=TestSignature())

        # Mock MCPClient.call_tool with proper MCP response structure
        with patch.object(
            agent._mcp_client, "call_tool", new_callable=AsyncMock
        ) as mock_call:
            # Mock response must match _convert_mcp_result_to_dict expectations
            mock_result_obj = MagicMock()
            mock_result_obj.structuredContent = {
                "content": "file contents",
                "exists": True,
            }
            mock_call.return_value = {"success": True, "result": mock_result_obj}

            # Execute SAFE tool (should NOT request approval)
            result = await agent.execute_mcp_tool(
                "mcp__kaizen_builtin__read_file", {"path": "/data.txt"}
            )

            # Note: 'content' is JSON-encoded structured_content for file tools
            # Individual fields are flattened (except 'content' which is reserved)
            assert result["exists"] is True  # Flattened from structuredContent
            assert result["structured_content"]["content"] == "file contents"
            mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_medium_tool_without_control_protocol_raises_error(self):
        """Test MEDIUM tool without control_protocol raises PermissionError."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        agent = BaseAgent(config=config, signature=TestSignature())

        # Mock permission_policy to return (None, None) - ask user for approval
        # This triggers the approval workflow which requires control_protocol
        agent.permission_policy.check_permission = Mock(return_value=(None, None))

        # MEDIUM tool without control_protocol should raise
        with pytest.raises(PermissionError) as exc_info:
            await agent.execute_mcp_tool(
                "mcp__kaizen_builtin__write_file",
                {"path": "/output.txt", "content": "data"},
            )

        assert "write_file" in str(exc_info.value)
        assert "danger=medium" in str(exc_info.value)
        assert "control_protocol not configured" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_high_tool_without_control_protocol_raises_error(self):
        """Test HIGH tool without control_protocol raises PermissionError."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        agent = BaseAgent(config=config, signature=TestSignature())

        # Mock permission_policy to return (None, None) - ask user for approval
        agent.permission_policy.check_permission = Mock(return_value=(None, None))

        # HIGH tool without control_protocol should raise
        with pytest.raises(PermissionError) as exc_info:
            await agent.execute_mcp_tool(
                "mcp__kaizen_builtin__bash_command", {"command": "ls"}
            )

        assert "bash_command" in str(exc_info.value)
        assert "danger=high" in str(exc_info.value)
        assert "control_protocol not configured" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_medium_tool_with_approval_granted_executes(self):
        """Test MEDIUM tool executes when approval granted."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        # Create mock control protocol
        mock_protocol = MagicMock()
        mock_transport = MagicMock()
        mock_protocol._transport = mock_transport

        agent = BaseAgent(
            config=config, signature=TestSignature(), control_protocol=mock_protocol
        )

        # Mock permission_policy to return (None, None) - ask user for approval
        agent.permission_policy.check_permission = Mock(return_value=(None, None))

        # Mock approval manager to grant approval
        agent.approval_manager.request_approval = AsyncMock(return_value=True)

        # Mock MCPClient.call_tool with proper MCP response structure
        with patch.object(
            agent._mcp_client, "call_tool", new_callable=AsyncMock
        ) as mock_call:
            mock_result_obj = MagicMock()
            mock_result_obj.structuredContent = {"written": True, "path": "/output.txt"}
            mock_call.return_value = {"success": True, "result": mock_result_obj}

            # Execute MEDIUM tool (approval granted)
            result = await agent.execute_mcp_tool(
                "mcp__kaizen_builtin__write_file",
                {"path": "/output.txt", "content": "data"},
            )

            # Flattened from structuredContent
            assert result["written"] is True
            # Verify approval was requested
            agent.approval_manager.request_approval.assert_called_once()
            call_args = agent.approval_manager.request_approval.call_args
            assert call_args.kwargs["tool_name"] == "write_file"
            assert call_args.kwargs["tool_input"] == {
                "path": "/output.txt",
                "content": "data",
            }

    @pytest.mark.asyncio
    async def test_medium_tool_with_approval_denied_raises_error(self):
        """Test MEDIUM tool raises error when approval denied."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        # Create mock control protocol
        mock_protocol = MagicMock()
        mock_transport = MagicMock()
        mock_protocol._transport = mock_transport

        agent = BaseAgent(
            config=config, signature=TestSignature(), control_protocol=mock_protocol
        )

        # Mock permission_policy to return (None, None) - ask user for approval
        agent.permission_policy.check_permission = Mock(return_value=(None, None))

        # Mock approval manager to deny approval
        agent.approval_manager.request_approval = AsyncMock(return_value=False)

        # Execute MEDIUM tool (approval denied)
        with pytest.raises(PermissionError) as exc_info:
            await agent.execute_mcp_tool(
                "mcp__kaizen_builtin__write_file",
                {"path": "/output.txt", "content": "data"},
            )

        assert "User denied approval" in str(exc_info.value)
        assert "write_file" in str(exc_info.value)
        assert "danger=medium" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_high_tool_with_approval_granted_executes(self):
        """Test HIGH tool executes when approval granted."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        # Create mock control protocol
        mock_protocol = MagicMock()
        mock_transport = MagicMock()
        mock_protocol._transport = mock_transport

        agent = BaseAgent(
            config=config, signature=TestSignature(), control_protocol=mock_protocol
        )

        # Mock permission_policy to return (None, None) - ask user for approval
        agent.permission_policy.check_permission = Mock(return_value=(None, None))

        # Mock approval manager to grant approval
        agent.approval_manager.request_approval = AsyncMock(return_value=True)

        # Mock MCPClient.call_tool with proper MCP response structure
        with patch.object(
            agent._mcp_client, "call_tool", new_callable=AsyncMock
        ) as mock_call:
            mock_result_obj = MagicMock()
            mock_result_obj.structuredContent = {"stdout": "file list", "exit_code": 0}
            mock_call.return_value = {"success": True, "result": mock_result_obj}

            # Execute HIGH tool (approval granted)
            result = await agent.execute_mcp_tool(
                "mcp__kaizen_builtin__bash_command", {"command": "ls"}
            )

            assert result["stdout"] == "file list"
            # Verify approval was requested
            agent.approval_manager.request_approval.assert_called_once()

    @pytest.mark.asyncio
    async def test_high_tool_with_approval_denied_raises_error(self):
        """Test HIGH tool raises error when approval denied."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        # Create mock control protocol
        mock_protocol = MagicMock()
        mock_transport = MagicMock()
        mock_protocol._transport = mock_transport

        agent = BaseAgent(
            config=config, signature=TestSignature(), control_protocol=mock_protocol
        )

        # Mock permission_policy to return (None, None) - ask user for approval
        agent.permission_policy.check_permission = Mock(return_value=(None, None))

        # Mock approval manager to deny approval
        agent.approval_manager.request_approval = AsyncMock(return_value=False)

        # Execute HIGH tool (approval denied)
        with pytest.raises(PermissionError) as exc_info:
            await agent.execute_mcp_tool(
                "mcp__kaizen_builtin__bash_command", {"command": "rm -rf /"}
            )

        assert "User denied approval" in str(exc_info.value)
        assert "bash_command" in str(exc_info.value)
        assert "danger=high" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_unknown_builtin_tool_treated_as_medium(self):
        """Test unknown builtin tool treated as MEDIUM danger by default."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        # Create mock control protocol
        mock_protocol = MagicMock()
        mock_transport = MagicMock()
        mock_protocol._transport = mock_transport

        agent = BaseAgent(
            config=config, signature=TestSignature(), control_protocol=mock_protocol
        )

        # Mock permission_policy to return (None, None) - ask user for approval
        agent.permission_policy.check_permission = Mock(return_value=(None, None))

        # Mock approval manager to grant approval
        agent.approval_manager.request_approval = AsyncMock(return_value=True)

        # Mock MCPClient.call_tool with proper MCP response structure
        with patch.object(
            agent._mcp_client, "call_tool", new_callable=AsyncMock
        ) as mock_call:
            mock_result_obj = MagicMock()
            mock_result_obj.structuredContent = {"result": "success"}
            mock_call.return_value = {"success": True, "result": mock_result_obj}

            # Execute unknown tool (should request approval)
            await agent.execute_mcp_tool(
                "mcp__kaizen_builtin__unknown_tool", {"param": "value"}
            )

            # Should have requested approval (unknown = MEDIUM)
            agent.approval_manager.request_approval.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_builtin_server_skips_approval_check(self):
        """Test non-builtin MCP servers skip danger level checking."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        # Add custom MCP server
        custom_servers = [
            {
                "name": "custom_server",
                "command": "custom-mcp",
                "transport": "stdio",
            }
        ]
        agent = BaseAgent(
            config=config, signature=TestSignature(), mcp_servers=custom_servers
        )

        # Mock MCPClient.call_tool with proper MCP response structure
        with patch.object(
            agent._mcp_client, "call_tool", new_callable=AsyncMock
        ) as mock_call:
            mock_result_obj = MagicMock()
            mock_result_obj.structuredContent = {"result": "custom"}
            mock_call.return_value = {"success": True, "result": mock_result_obj}

            # Execute custom server tool (no approval check)
            result = await agent.execute_mcp_tool(
                "mcp__custom_server__custom_tool", {"param": "value"}
            )

            # Flattened from structuredContent
            assert result["result"] == "custom"
            # No approval manager created (control_protocol=None)
            assert agent.approval_manager is None


class TestMCPToolApprovalTimeout:
    """Test timeout handling in approval workflow."""

    @pytest.mark.asyncio
    async def test_approval_timeout_passed_to_manager(self):
        """Test timeout parameter passed to approval manager."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        # Create mock control protocol
        mock_protocol = MagicMock()
        mock_transport = MagicMock()
        mock_protocol._transport = mock_transport

        agent = BaseAgent(
            config=config, signature=TestSignature(), control_protocol=mock_protocol
        )

        # Mock permission_policy to return (None, None) - ask user for approval
        agent.permission_policy.check_permission = Mock(return_value=(None, None))

        # Mock approval manager to grant approval
        agent.approval_manager.request_approval = AsyncMock(return_value=True)

        # Mock MCPClient.call_tool with proper MCP response structure
        with patch.object(
            agent._mcp_client, "call_tool", new_callable=AsyncMock
        ) as mock_call:
            mock_result_obj = MagicMock()
            mock_result_obj.structuredContent = {"written": True}
            mock_call.return_value = {"success": True, "result": mock_result_obj}

            # Execute with custom timeout
            await agent.execute_mcp_tool(
                "mcp__kaizen_builtin__write_file",
                {"path": "/output.txt", "content": "data"},
                timeout=30.0,
            )

            # Verify timeout passed to approval manager
            call_args = agent.approval_manager.request_approval.call_args
            assert call_args.kwargs["timeout"] == 30.0

    @pytest.mark.asyncio
    async def test_approval_default_timeout_60_seconds(self):
        """Test default timeout is 60 seconds if not specified."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        # Create mock control protocol
        mock_protocol = MagicMock()
        mock_transport = MagicMock()
        mock_protocol._transport = mock_transport

        agent = BaseAgent(
            config=config, signature=TestSignature(), control_protocol=mock_protocol
        )

        # Mock permission_policy to return (None, None) - ask user for approval
        agent.permission_policy.check_permission = Mock(return_value=(None, None))

        # Mock approval manager to grant approval
        agent.approval_manager.request_approval = AsyncMock(return_value=True)

        # Mock MCPClient.call_tool with proper MCP response structure
        with patch.object(
            agent._mcp_client, "call_tool", new_callable=AsyncMock
        ) as mock_call:
            mock_result_obj = MagicMock()
            mock_result_obj.structuredContent = {"written": True}
            mock_call.return_value = {"success": True, "result": mock_result_obj}

            # Execute without timeout (should use default)
            await agent.execute_mcp_tool(
                "mcp__kaizen_builtin__write_file",
                {"path": "/output.txt", "content": "data"},
            )

            # Verify default 60.0 timeout used
            call_args = agent.approval_manager.request_approval.call_args
            assert call_args.kwargs["timeout"] == 60.0
