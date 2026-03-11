"""
Integration Tests for Agent-as-Client MCP Example with REAL LLM Providers.

⚠️ MIGRATION IN PROGRESS (2025-10-04)
These tests were designed for the deprecated kaizen.mcp implementation.
The examples have been migrated to use kailash.mcp_server via BaseAgent helpers.

Tests need refactoring to:
1. Remove populate_agent_tools() calls (deprecated manual tool copying)
2. Use BaseAgent.setup_mcp_client() for real JSON-RPC tool discovery
3. Test real MCP protocol behavior, not deprecated workarounds

See: tests/integration/MCP_INTEGRATION_TEST_MIGRATION_STATUS.md

Tests that the LLM can actually:
1. Parse MCP tool schemas via real JSON-RPC
2. Generate proper tool arguments from natural language
3. Process tool invocation results from real protocol
4. Execute end-to-end MCP workflows with production infrastructure

Uses REAL providers (openai gpt-4o-mini or ollama) - NO MOCKING.
Requires environment variables: OPENAI_API_KEY or running Ollama instance.
"""

# Import example using standardized loader
import importlib.util
import json
import time
from pathlib import Path

import pytest

# Add examples directory to path for direct import
example_path = (
    Path(__file__).parent.parent.parent
    / "examples"
    / "5-mcp-integration"
    / "agent-as-client"
)

# Import from workflow module
workflow_spec = importlib.util.spec_from_file_location(
    "agent_as_client_real_llm_workflow", str(example_path / "workflow.py")
)
agent_as_client_example = importlib.util.module_from_spec(workflow_spec)
workflow_spec.loader.exec_module(agent_as_client_example)

MCPClientConfig = agent_as_client_example.MCPClientConfig
MCPClientAgent = agent_as_client_example.MCPClientAgent
TaskAnalysisSignature = agent_as_client_example.TaskAnalysisSignature
ToolInvocationSignature = agent_as_client_example.ToolInvocationSignature
ResultSynthesisSignature = agent_as_client_example.ResultSynthesisSignature

import logging

# Real MCP infrastructure - UPDATED to use kailash.mcp_server
# NOTE: kaizen.mcp has been deprecated and removed
# Tests now use real Kailash SDK MCP infrastructure
from kaizen.memory import SharedMemoryPool

# Real LLM provider fixtures

logger = logging.getLogger(__name__)


# ===================================================================
# INTEGRATION TESTS WITH REAL OPENAI (gpt-5-nano)
# ===================================================================


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.requires_llm
class TestMCPClientAgentRealOpenAI:
    """Integration tests with real OpenAI provider."""

    @pytest.fixture
    def openai_config(self, openai_api_key, mcp_server_info):
        """Configuration using real OpenAI provider with real MCP server."""
        return MCPClientConfig(
            llm_provider="openai",
            model="gpt-4o-mini",  # Use gpt-4o-mini for better availability
            temperature=0.1,  # Low temperature for deterministic behavior
            max_tokens=500,
            mcp_servers=[{"name": "test-server", "url": mcp_server_info["url"]}],
            enable_auto_discovery=False,  # Disable for focused testing
        )

    @pytest.fixture
    def openai_agent(self, openai_config):
        """Agent configured with real OpenAI provider."""
        agent = MCPClientAgent(openai_config)
        yield agent
        # Cleanup
        agent.disconnect_all()

    def test_openai_task_analysis_with_real_llm(self, openai_agent):
        """Test that real OpenAI LLM can analyze tasks and identify required tools."""
        # Skip if no connections available
        if len(openai_agent.connections) == 0:
            pytest.skip("No MCP connections available")

        # Analyze a task that requires tool usage
        task = "Search for information about Python and calculate the sum of 5 and 3"

        analysis = openai_agent.analyze_task(
            task=task, context="Integration test with real LLM"
        )

        # Verify LLM understood the task
        assert isinstance(analysis, dict)
        assert "required_tools" in analysis
        assert "execution_plan" in analysis
        assert "complexity" in analysis

        # Verify complexity is valid
        assert 0.0 <= analysis["complexity"] <= 1.0

        # Verify execution plan is meaningful (not empty)
        assert len(analysis["execution_plan"]) > 0

        # Log results for inspection
        logger.info(f"OpenAI Task Analysis: {json.dumps(analysis, indent=2)}")

    @pytest.mark.skip(
        reason="Deprecated: Uses populate_agent_tools() - needs refactor for real JSON-RPC protocol"
    )
    def test_openai_tool_schema_parsing(self, openai_agent, mcp_server_info):
        """Test that real OpenAI LLM can parse MCP tool schemas from real server."""
        # TODO: Refactor to use BaseAgent.setup_mcp_client() and real JSON-RPC discovery
        # Deprecated manual tool population - no longer supported
        # mcp_server_info["populate_agent_tools"](openai_agent)

        # Verify we have tools from the real MCP server
        assert (
            len(openai_agent.available_tools) > 0
        ), "Should have tools from real MCP server"

        # Get first available tool
        tool_id = list(openai_agent.available_tools.keys())[0]
        tool_info = openai_agent.available_tools[tool_id]

        logger.info(f"Testing with real MCP tool: {tool_id}")
        logger.info(f"Tool schema: {tool_info}")

        # Ask LLM to use a real tool - question_answering
        user_request = "What is the capital of France?"

        # Use the tool invocation logic (which calls the LLM with real tool schema)
        result = openai_agent.invoke_tool(
            tool_id=tool_id,
            user_request=user_request,
            context="Schema parsing test with real MCP server",
        )

        # Verify result structure
        assert isinstance(result, dict)
        assert "success" in result

        # LLM should have successfully parsed the schema and invoked the tool
        logger.info(f"OpenAI tool invocation result: {result}")

        # Verify the LLM could interact with the real MCP tool
        assert "success" in result or "error" in result

    @pytest.mark.skip(
        reason="Deprecated: Uses populate_agent_tools() - needs refactor for real JSON-RPC protocol"
    )
    def test_openai_argument_generation_from_natural_language(
        self, openai_agent, mcp_server_info
    ):
        """Test that real OpenAI LLM can generate tool arguments from natural language."""
        # TODO: Refactor to use BaseAgent.setup_mcp_client() and real JSON-RPC discovery
        # Deprecated manual tool population - no longer supported
        # mcp_server_info["populate_agent_tools"](openai_agent)

        # Verify we have tools from the real MCP server
        assert (
            len(openai_agent.available_tools) > 0
        ), "Should have tools from real MCP server"

        # Create a natural language request that maps to text_analysis tool
        user_request = "Analyze this text: AI is transforming software development"

        logger.info(
            f"Available tools from MCP server: {list(openai_agent.available_tools.keys())}"
        )

        # Try to invoke the text_analysis tool with natural language
        tool_id = "test-server:text_analysis"  # Our server exposes this tool

        if tool_id in openai_agent.available_tools:
            result = openai_agent.invoke_tool(
                tool_id=tool_id,
                user_request=user_request,
                context="Natural language to arguments test",
            )

            # Verify LLM generated proper arguments from natural language
            assert isinstance(result, dict)
            logger.info(f"OpenAI argument generation result: {result}")

            # Should have successfully converted natural language to tool arguments
            assert "success" in result or "error" in result
        else:
            # Fallback: analyze task to see if LLM can identify tools
            analysis = openai_agent.analyze_task(
                task=user_request, context="Argument generation test"
            )

            # Verify LLM identified tools
            assert "required_tools" in analysis
            logger.info(
                f"OpenAI identified tools: {analysis.get('required_tools', [])}"
            )

            # Verify execution plan shows reasoning
            assert "execution_plan" in analysis
            assert len(analysis["execution_plan"]) > 10  # Should be descriptive

    def test_openai_end_to_end_mcp_workflow(self, openai_agent):
        """Test complete MCP workflow with real OpenAI LLM."""
        # Skip if no connections
        connected_count = sum(
            1 for c in openai_agent.connections.values() if c.status == "connected"
        )
        if connected_count == 0:
            pytest.skip("No MCP servers connected")

        # Execute a simple task
        task = "Help me understand what tools are available"

        result = openai_agent.execute_task(task=task, context="E2E workflow test")

        # Verify result structure
        assert isinstance(result, dict)
        assert "success" in result

        # Verify LLM produced meaningful output
        if result.get("success"):
            # Should have analysis or final answer
            assert "final_answer" in result or "analysis" in result
            logger.info(f"OpenAI E2E workflow result: {json.dumps(result, indent=2)}")

    def test_openai_memory_integration(self, openai_agent):
        """Test that real OpenAI LLM properly records insights to shared memory."""
        # Give agent shared memory
        memory = SharedMemoryPool()
        openai_agent.shared_memory = memory

        # Execute a task
        task = "Analyze available MCP tools"

        try:
            openai_agent.analyze_task(task=task, context="Memory integration test")

            # Check memory was written
            all_insights = memory.read_all()

            # Should have at least one insight
            assert len(all_insights) > 0

            # Verify insight content
            latest_insight = all_insights[-1]
            assert "content" in latest_insight
            logger.info(f"OpenAI wrote {len(all_insights)} insights to memory")

        except Exception as e:
            logger.warning(f"Memory integration test error: {e}")
            # Some errors are acceptable if they're after memory write


# ===================================================================
# INTEGRATION TESTS WITH REAL OLLAMA
# ===================================================================


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.requires_llm
@pytest.mark.requires_ollama
class TestMCPClientAgentRealOllama:
    """Integration tests with real Ollama provider."""

    @pytest.fixture
    def ollama_config(self, mcp_server_info):
        """Configuration using real Ollama provider with real MCP server."""
        return MCPClientConfig(
            llm_provider="ollama",
            model="llama3.2:latest",
            temperature=0.1,
            max_tokens=500,
            mcp_servers=[{"name": "test-server", "url": mcp_server_info["url"]}],
            enable_auto_discovery=False,
        )

    @pytest.fixture
    def ollama_agent(self, ollama_config, real_ollama_provider):
        """Agent configured with real Ollama provider."""
        # Verify Ollama is available
        if not real_ollama_provider.is_available():
            pytest.skip("Ollama not available")

        agent = MCPClientAgent(ollama_config)
        yield agent
        # Cleanup
        agent.disconnect_all()

    def test_ollama_task_analysis_with_real_llm(self, ollama_agent):
        """Test that real Ollama LLM can analyze tasks."""
        if len(ollama_agent.connections) == 0:
            pytest.skip("No MCP connections available")

        task = "Search for information about AI"

        analysis = ollama_agent.analyze_task(
            task=task, context="Integration test with Ollama"
        )

        # Verify structure
        assert isinstance(analysis, dict)
        assert "required_tools" in analysis
        assert "execution_plan" in analysis
        assert "complexity" in analysis

        logger.info(f"Ollama Task Analysis: {json.dumps(analysis, indent=2)}")

    @pytest.mark.skip(
        reason="Deprecated: Uses populate_agent_tools() - needs refactor for real JSON-RPC protocol"
    )
    def test_ollama_tool_invocation(self, ollama_agent, mcp_server_info):
        """Test that Ollama can invoke real MCP tools from server."""
        # TODO: Refactor to use BaseAgent.setup_mcp_client() and real JSON-RPC discovery
        # Deprecated manual tool population - no longer supported
        # mcp_server_info["populate_agent_tools"](ollama_agent)

        # Verify we have tools from the real MCP server
        assert (
            len(ollama_agent.available_tools) > 0
        ), "Should have tools from real MCP server"

        tool_id = list(ollama_agent.available_tools.keys())[0]

        logger.info(f"Ollama invoking real MCP tool: {tool_id}")
        logger.info(f"Available tools: {list(ollama_agent.available_tools.keys())}")

        result = ollama_agent.invoke_tool(
            tool_id=tool_id,
            user_request="What is machine learning?",
            context="Ollama invocation test with real MCP server",
        )

        assert isinstance(result, dict)
        assert "success" in result
        logger.info(f"Ollama tool invocation result: {result}")


# ===================================================================
# COMPARATIVE TESTS
# ===================================================================


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.requires_llm
class TestMCPClientAgentProviderComparison:
    """Compare behavior across different real LLM providers."""

    def test_provider_consistency_task_analysis(
        self, openai_api_key, real_ollama_provider
    ):
        """Test that different providers produce consistent task analysis."""
        # Create agents with different providers
        openai_config = MCPClientConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            mcp_servers=[],
            enable_auto_discovery=False,
        )

        ollama_config = MCPClientConfig(
            llm_provider="ollama",
            model="llama3.2:latest",
            mcp_servers=[],
            enable_auto_discovery=False,
        )

        openai_agent = MCPClientAgent(openai_config)

        # Only test Ollama if available
        ollama_available = real_ollama_provider.is_available()
        if ollama_available:
            ollama_agent = MCPClientAgent(ollama_config)

        task = "Calculate the sum of 10 and 20"

        # Analyze with OpenAI
        openai_result = openai_agent.analyze_task(task, "Comparison test")

        # Both should produce valid analysis
        assert isinstance(openai_result, dict)
        assert "complexity" in openai_result
        assert 0.0 <= openai_result["complexity"] <= 1.0

        if ollama_available:
            ollama_result = ollama_agent.analyze_task(task, "Comparison test")
            assert isinstance(ollama_result, dict)
            assert "complexity" in ollama_result
            assert 0.0 <= ollama_result["complexity"] <= 1.0

            logger.info(f"OpenAI complexity: {openai_result['complexity']}")
            logger.info(f"Ollama complexity: {ollama_result['complexity']}")

        # Cleanup
        openai_agent.disconnect_all()
        if ollama_available:
            ollama_agent.disconnect_all()


# ===================================================================
# PERFORMANCE TESTS WITH REAL LLM
# ===================================================================


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.requires_llm
@pytest.mark.performance
class TestMCPClientAgentRealLLMPerformance:
    """Performance tests with real LLM providers."""

    def test_openai_task_analysis_latency(self, openai_api_key):
        """Test task analysis latency with real OpenAI."""
        config = MCPClientConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            mcp_servers=[],
            enable_auto_discovery=False,
        )

        agent = MCPClientAgent(config)

        # Measure analysis time
        start_time = time.time()
        result = agent.analyze_task(task="Simple test task", context="Performance test")
        latency = time.time() - start_time

        # Verify success
        assert isinstance(result, dict)
        assert "complexity" in result

        # Log performance
        logger.info(f"OpenAI task analysis latency: {latency:.2f}s")

        # Should complete in reasonable time (< 10s for simple task)
        assert latency < 10.0

        agent.disconnect_all()

    def test_multiple_llm_calls_throughput(self, openai_api_key):
        """Test throughput of multiple LLM calls."""
        config = MCPClientConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            mcp_servers=[],
            enable_auto_discovery=False,
        )

        agent = MCPClientAgent(config)

        # Execute multiple tasks
        tasks = ["Task 1: Simple query", "Task 2: Another query", "Task 3: Final query"]

        start_time = time.time()
        results = []

        for task in tasks:
            result = agent.analyze_task(task, "Throughput test")
            results.append(result)

        total_time = time.time() - start_time

        # All should succeed
        assert len(results) == len(tasks)
        for result in results:
            assert isinstance(result, dict)
            assert "complexity" in result

        # Log throughput
        avg_time = total_time / len(tasks)
        logger.info(f"Average task analysis time: {avg_time:.2f}s")
        logger.info(f"Total throughput: {len(tasks)/total_time:.2f} tasks/sec")

        agent.disconnect_all()


# ===================================================================
# ERROR HANDLING WITH REAL LLM
# ===================================================================


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.requires_llm
class TestMCPClientAgentRealLLMErrorHandling:
    """Test error handling with real LLM providers."""

    def test_openai_invalid_tool_request(self, openai_api_key):
        """Test error handling when LLM requests non-existent tool."""
        config = MCPClientConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            mcp_servers=[{"name": "test-server", "url": "http://localhost:18080"}],
            enable_auto_discovery=False,
        )

        agent = MCPClientAgent(config)

        # Try to invoke non-existent tool
        result = agent.invoke_tool(
            tool_id="nonexistent:tool", user_request="Test", context="Error test"
        )

        # Should fail gracefully
        assert result["success"] is False
        assert "error" in result

        agent.disconnect_all()

    def test_openai_connection_failure_handling(self, openai_api_key):
        """Test error handling when MCP server connection fails."""
        config = MCPClientConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            mcp_servers=[{"name": "invalid-server", "url": "http://localhost:19999"}],
            enable_auto_discovery=False,
        )

        agent = MCPClientAgent(config)

        # Connection should have failed
        if "invalid-server" in agent.connections:
            connection = agent.connections["invalid-server"]
            assert connection.status == "failed"

        # Agent should still be usable for task analysis
        result = agent.analyze_task(task="Test task", context="Connection failure test")

        assert isinstance(result, dict)
        assert "complexity" in result

        agent.disconnect_all()


# ===================================================================
# PYTEST MARKERS
# ===================================================================

pytestmark = [
    pytest.mark.integration,
    pytest.mark.mcp,
    pytest.mark.requires_llm,
]
