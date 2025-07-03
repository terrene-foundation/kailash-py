"""User flow test demonstrating the MCP async/await bug fix."""

import os

import pytest

from kailash.nodes.ai.llm_agent import LLMAgentNode
from kailash.runtime import LocalRuntime
from kailash.workflow import Workflow


@pytest.mark.e2e
class TestMCPBugFixUserFlow:
    """
    User flow test reproducing the exact scenario from the bug report:
    - User tries to use LLMAgentNode with MCP servers
    - Previously failed with: RuntimeWarning: coroutine 'MCPClient.list_resources' was never awaited
    - Now should work correctly with automatic event loop handling
    """

    def test_user_flow_mcp_integration(self):
        """Complete user flow as described in the bug report."""

        # Step 1: User sets up environment as instructed
        os.environ["KAILASH_USE_REAL_MCP"] = "true"

        # Step 2: User creates a workflow with LLMAgentNode
        workflow = Workflow(name="user_mcp_workflow")
        runtime = LocalRuntime()

        # Step 3: User configures MCP servers (as in bug report)
        mcp_servers = ["http://localhost:8891"]  # FastMCP server URL

        # Step 4: User adds LLMAgentNode with MCP configuration
        workflow.add_node(
            "LLMAgentNode",
            "assistant",
            provider="mock",  # Using mock for testing
            model="gpt-4",
            mcp_servers=mcp_servers,
            auto_discover_tools=True,
        )

        # Step 5: User executes workflow (this is where it failed before)
        try:
            result = runtime.execute(
                workflow,
                parameters={
                    "assistant": {
                        "messages": [
                            {
                                "role": "user",
                                "content": "Help me implement yank mode for vim",
                            }
                        ]
                    }
                },
            )

            # Verify success
            assert result.successful, f"Workflow failed: {result.errors}"

            # Check the response
            assistant_output = result.node_outputs["assistant"]["result"]
            assert assistant_output["success"] is True
            assert "response" in assistant_output

            print("\n✅ SUCCESS: MCP integration works without async/await errors!")
            print(
                f"Assistant response: {assistant_output['response']['content'][:200]}..."
            )

        except RuntimeWarning as e:
            if "coroutine" in str(e) and "never awaited" in str(e):
                pytest.fail(f"BUG NOT FIXED: {e}")
            raise

    def test_user_flow_mcp_with_context(self):
        """User flow with MCP context retrieval."""

        os.environ["KAILASH_USE_REAL_MCP"] = "true"

        # User creates LLMAgentNode directly (simpler approach)
        agent = LLMAgentNode(name="mcp_context_agent")

        # User configures with MCP servers and context
        result = agent.run(
            provider="mock",
            model="gpt-4",
            messages=[
                {
                    "role": "user",
                    "content": "Search for workflow optimization techniques",
                }
            ],
            mcp_servers=[
                {
                    "name": "knowledge-base",
                    "transport": "http",
                    "url": "http://localhost:8891",
                }
            ],
            mcp_context=["resource://workflows/optimization"],
            auto_discover_tools=True,
        )

        # Verify it works
        assert result["success"] is True
        assert "response" in result

        print("\n✅ MCP context retrieval works correctly!")

    def test_user_flow_multiple_mcp_servers(self):
        """User flow with multiple MCP servers."""

        os.environ["KAILASH_USE_REAL_MCP"] = "true"

        agent = LLMAgentNode(name="multi_mcp_agent")

        # User configures multiple MCP servers
        result = agent.run(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "Analyze this data"}],
            mcp_servers=[
                {
                    "name": "data-server",
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "mcp_data_server"],
                },
                {
                    "name": "api-server",
                    "transport": "http",
                    "url": "https://mcp.example.com",
                },
            ],
            mcp_context=["data://sales/2024/q4", "resource://customers/segments"],
        )

        assert result["success"] is True
        print("\n✅ Multiple MCP servers handled correctly!")

    def test_user_flow_error_recovery(self):
        """User flow showing graceful error recovery."""

        os.environ["KAILASH_USE_REAL_MCP"] = "true"

        agent = LLMAgentNode(name="error_recovery_agent")

        # User provides invalid MCP configuration
        result = agent.run(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "This should still work"}],
            mcp_servers=[
                {
                    "name": "broken-server",
                    "transport": "stdio",
                    "command": "/nonexistent/command",
                }
            ],
        )

        # Should still succeed with fallback
        assert result["success"] is True
        assert "response" in result

        print("\n✅ Graceful fallback when MCP fails!")
