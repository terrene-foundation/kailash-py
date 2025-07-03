"""E2E test for MCP integration with FastMCP server scenario."""

import asyncio
import json
import os
import subprocess
import time
from typing import Any, Dict

import pytest
import requests

from kailash.nodes.ai.llm_agent import LLMAgentNode
from kailash.runtime import LocalRuntime
from kailash.workflow import Workflow


@pytest.mark.e2e
@pytest.mark.slow
class TestMCPFastMCPIntegration:
    """Test the exact scenario reported in the bug with FastMCP."""

    @classmethod
    def setup_class(cls):
        """Set up mock MCP server for testing."""
        cls.server_process = None
        cls.server_port = 8891

        # Create a simple mock MCP server script
        cls.mock_server_code = """
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

class MCPHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        request = json.loads(post_data)

        # Simple MCP protocol responses
        response = {
            "jsonrpc": "2.0",
            "id": request.get("id", 1)
        }

        method = request.get("method", "")

        if method == "initialize":
            response["result"] = {
                "protocolVersion": "0.1.0",
                "capabilities": {
                    "tools": {"listChanged": True},
                    "resources": {"subscribe": True}
                }
            }
        elif method == "tools/list":
            response["result"] = {
                "tools": [
                    {
                        "name": "test_tool",
                        "description": "A test tool",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string"}
                            }
                        }
                    }
                ]
            }
        elif method == "resources/list":
            response["result"] = {
                "resources": [
                    {
                        "uri": "test://resource",
                        "name": "Test Resource",
                        "mimeType": "text/plain"
                    }
                ]
            }
        elif method == "resources/read":
            response["result"] = {
                "contents": [
                    {
                        "uri": request["params"]["uri"],
                        "mimeType": "text/plain",
                        "text": "Test resource content"
                    }
                ]
            }
        else:
            response["error"] = {
                "code": -32601,
                "message": "Method not found"
            }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def log_message(self, format, *args):
        pass  # Suppress logs

if __name__ == "__main__":
    server = HTTPServer(("localhost", 8891), MCPHandler)
    print("Mock MCP server running on http://localhost:8891")
    server.serve_forever()
"""

        # Write and start the mock server
        with open("/tmp/mock_mcp_server.py", "w") as f:
            f.write(cls.mock_server_code)

        cls.server_process = subprocess.Popen(
            ["python", "/tmp/mock_mcp_server.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for server to start
        time.sleep(2)

        # Verify server is running
        try:
            response = requests.post(
                f"http://localhost:{cls.server_port}/mcp/",
                json={"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 1},
            )
            assert response.status_code == 200
        except Exception as e:
            pytest.skip(f"Mock MCP server failed to start: {e}")

    @classmethod
    def teardown_class(cls):
        """Stop the mock MCP server."""
        if cls.server_process:
            cls.server_process.terminate()
            cls.server_process.wait()

        # Clean up
        if os.path.exists("/tmp/mock_mcp_server.py"):
            os.remove("/tmp/mock_mcp_server.py")

    def setup_method(self):
        """Set up for each test."""
        os.environ["KAILASH_USE_REAL_MCP"] = "true"

    def teardown_method(self):
        """Clean up after each test."""
        os.environ.pop("KAILASH_USE_REAL_MCP", None)

    def test_exact_bug_scenario(self):
        """Test the exact scenario from the bug report."""
        # Create LLMAgentNode
        agent = LLMAgentNode(name="mcp_agent")

        # Configuration as reported in bug
        mcp_servers = [f"http://localhost:{self.server_port}"]

        # This is what was failing with the async/await error
        result = agent.run(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello MCP"}],
            mcp_servers=mcp_servers,
            auto_discover_tools=True,
        )

        # Should succeed without RuntimeWarning
        assert result["success"] is True
        assert "response" in result

    def test_workflow_with_mcp(self):
        """Test MCP in a workflow context."""
        workflow = Workflow(name="mcp_workflow")
        runtime = LocalRuntime()

        # Add MCP-enabled LLM agent
        workflow.add_node(
            "LLMAgentNode",
            "agent",
            provider="mock",
            model="gpt-4",
            mcp_servers=[
                {
                    "name": "workflow-mcp",
                    "transport": "http",
                    "url": f"http://localhost:{self.server_port}",
                }
            ],
            auto_discover_tools=True,
        )

        # Execute workflow
        result = runtime.execute(
            workflow,
            parameters={
                "agent": {"messages": [{"role": "user", "content": "Test workflow"}]}
            },
        )

        assert result.successful
        agent_result = result.node_outputs["agent"]["result"]
        assert agent_result["success"] is True

    def test_mcp_context_retrieval(self):
        """Test MCP context retrieval functionality."""
        agent = LLMAgentNode(name="context_agent")

        result = agent.run(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "Use context"}],
            mcp_servers=[
                {
                    "name": "context-server",
                    "transport": "http",
                    "url": f"http://localhost:{self.server_port}",
                }
            ],
            mcp_context=["test://resource"],
        )

        assert result["success"] is True

        # Check that context was retrieved
        if "context" in result:
            assert result["context"]["mcp_resources_used"] > 0

    def test_mcp_tool_discovery(self):
        """Test MCP tool discovery functionality."""
        agent = LLMAgentNode(name="tool_agent")

        # Test tool discovery
        tools = agent._discover_mcp_tools(
            [
                {
                    "name": "tool-server",
                    "transport": "http",
                    "url": f"http://localhost:{self.server_port}",
                }
            ]
        )

        # Should discover at least one tool
        assert len(tools) > 0
        assert tools[0]["type"] == "function"
        assert "test_tool" in tools[0]["function"]["name"]

    def test_jupyter_notebook_simulation(self):
        """Simulate the Jupyter notebook scenario where event loop exists."""

        # This simulates what happens in Jupyter
        async def notebook_cell():
            agent = LLMAgentNode(name="notebook_agent")

            # In Jupyter, this would be called with existing event loop
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                agent.run,
                "mock",  # provider
                "gpt-4",  # model
                [{"role": "user", "content": "Notebook test"}],  # messages
                None,  # system_prompt
                None,  # conversation_id
                None,  # memory_config
                [],  # tools
                None,  # rag_config
                [
                    {  # mcp_servers
                        "name": "notebook-server",
                        "transport": "http",
                        "url": f"http://localhost:{self.server_port}",
                    }
                ],
                ["test://resource"],  # mcp_context
                True,  # auto_discover_tools
            )

            assert result["success"] is True
            return result

        # Run in event loop (simulating Jupyter)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(notebook_cell())
            assert result is not None
        finally:
            loop.close()

    def test_performance_impact(self):
        """Test that the fix doesn't significantly impact performance."""
        agent = LLMAgentNode(name="perf_agent")

        # Time without MCP
        start = time.time()
        result1 = agent.run(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "No MCP"}],
        )
        time_without_mcp = time.time() - start

        # Time with MCP
        start = time.time()
        result2 = agent.run(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "With MCP"}],
            mcp_servers=[
                {
                    "name": "perf-server",
                    "transport": "http",
                    "url": f"http://localhost:{self.server_port}",
                }
            ],
            auto_discover_tools=True,
        )
        time_with_mcp = time.time() - start

        assert result1["success"] is True
        assert result2["success"] is True

        # MCP shouldn't add more than 2 seconds overhead
        assert time_with_mcp - time_without_mcp < 2.0
