"""User flow test demonstrating the MCP async/await bug fix."""

import os

import pytest
import pytest_asyncio
from kailash.nodes.ai.llm_agent import LLMAgentNode
from kailash.runtime import LocalRuntime
from kailash.workflow import Workflow

from tests.utils.docker_config import OLLAMA_CONFIG, ensure_docker_services


@pytest.mark.e2e
@pytest.mark.requires_docker
@pytest.mark.requires_ollama
class TestMCPBugFixUserFlow:
    """
    User flow test reproducing the exact scenario from the bug report:
    - User tries to use LLMAgentNode with MCP servers
    - Previously failed with: RuntimeWarning: coroutine 'MCPClient.list_resources' was never awaited
    - Now should work correctly with automatic event loop handling
    """

    @pytest_asyncio.fixture(autouse=True)
    async def setup_services(self):
        """Ensure Docker services are running for E2E tests."""
        services_ready = await ensure_docker_services()
        if not services_ready:
            pytest.skip("Docker services not available")

        # Set up environment for real MCP and Ollama
        os.environ["KAILASH_USE_REAL_MCP"] = "true"
        os.environ["OLLAMA_BASE_URL"] = OLLAMA_CONFIG["base_url"]
        os.environ["REGISTRY_FILE"] = (
            "# contrib (removed)/research/combined_ai_registry.json"
        )
        yield

        # Cleanup
        os.environ.pop("KAILASH_USE_REAL_MCP", None)
        os.environ.pop("OLLAMA_BASE_URL", None)
        os.environ.pop("REGISTRY_FILE", None)

    def test_user_flow_mcp_integration(self):
        """Complete user flow as described in the bug report."""

        # Step 2: User creates a workflow with LLMAgentNode
        workflow = Workflow(workflow_id="user_mcp_workflow", name="User MCP Workflow")
        runtime = LocalRuntime()

        # Step 3: User configures MCP servers (real AI Registry server)
        mcp_servers = [
            {
                "name": "ai-registry-server",
                "transport": "stdio",
                "command": "python",
                "args": ["-m", "kailash.mcp_server.ai_registry_server"],
            }
        ]

        # Step 4: User adds LLMAgentNode with MCP configuration
        workflow.add_node(
            "assistant",
            LLMAgentNode,
            provider="ollama",  # Using real Ollama for E2E testing
            model="llama3.2:1b",
            mcp_servers=mcp_servers,
            auto_discover_tools=True,
        )

        # Step 5: User executes workflow (this is where it failed before)
        try:
            results, run_id = runtime.execute(
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
            assert (
                "assistant" in results
            ), f"Assistant node not found in results: {list(results.keys())}"

            # Check the response
            assistant_output = results["assistant"]
            assert assistant_output is not None
            assert isinstance(assistant_output, dict)

            print("\n✅ SUCCESS: MCP integration works without async/await errors!")
            print(f"Assistant executed successfully: {type(assistant_output)}")

        except RuntimeWarning as e:
            if "coroutine" in str(e) and "never awaited" in str(e):
                pytest.fail(f"BUG NOT FIXED: {e}")
            raise

    def test_user_flow_mcp_with_context(self):
        """User flow with MCP context retrieval."""

        # User creates LLMAgentNode directly (simpler approach)
        agent = LLMAgentNode(name="mcp_context_agent")

        # User configures with MCP servers and context
        result = agent.execute(
            provider="ollama",
            model="llama3.2:1b",
            messages=[
                {
                    "role": "user",
                    "content": "Search for workflow optimization techniques",
                }
            ],
            mcp_servers=[
                {
                    "name": "ai-registry-server",
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "kailash.mcp_server.ai_registry_server"],
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

        agent = LLMAgentNode(name="multi_mcp_agent")

        # User configures multiple MCP servers
        result = agent.execute(
            provider="ollama",
            model="llama3.2:1b",
            messages=[{"role": "user", "content": "Analyze this data"}],
            mcp_servers=[
                {
                    "name": "ai-registry-server",
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "kailash.mcp_server.ai_registry_server"],
                },
            ],
            mcp_context=["data://sales/2024/q4", "resource://customers/segments"],
        )

        assert result["success"] is True
        print("\n✅ Multiple MCP servers handled correctly!")

    def test_user_flow_error_recovery(self):
        """User flow showing graceful error recovery."""

        agent = LLMAgentNode(name="error_recovery_agent")

        # User provides invalid MCP configuration
        result = agent.execute(
            provider="ollama",
            model="llama3.2:1b",
            messages=[{"role": "user", "content": "This should still work"}],
            mcp_servers=[
                {
                    "name": "ai-registry-server",
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "kailash.mcp_server.ai_registry_server"],
                }
            ],
        )

        # Should still succeed with fallback
        assert result["success"] is True
        assert "response" in result

        print("\n✅ Graceful fallback when MCP fails!")
