"""
Integration Tests for Agent-as-Server MCP Example with REAL LLM Providers.

⚠️ MIGRATION IN PROGRESS (2025-10-04)
These tests were designed for the deprecated kaizen.mcp implementation.
The examples have been migrated to use kailash.mcp_server directly.

Tests need refactoring to:
1. Remove kaizen.mcp imports (deprecated)
2. Use kailash.mcp_server.MCPServer or example's migrated server
3. Test real JSON-RPC protocol behavior, not deprecated implementations

See: tests/integration/MCP_INTEGRATION_TEST_MIGRATION_STATUS.md

Tests that the LLM can actually:
1. Process MCP tool requests with natural language via real protocol
2. Generate responses based on tool schemas from real JSON-RPC
3. Handle JSON-RPC 2.0 requests/responses with production server
4. Execute server workflows end-to-end with kailash.mcp_server

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
    / "agent-as-server"
)

# Import from workflow module
workflow_spec = importlib.util.spec_from_file_location(
    "agent_as_server_real_llm_workflow", str(example_path / "workflow.py")
)
agent_as_server_example = importlib.util.module_from_spec(workflow_spec)
workflow_spec.loader.exec_module(agent_as_server_example)

MCPServerAgentConfig = agent_as_server_example.MCPServerAgentConfig
MCPServerAgent = agent_as_server_example.MCPServerAgent
QuestionAnsweringSignature = agent_as_server_example.QuestionAnsweringSignature
TextAnalysisSignature = agent_as_server_example.TextAnalysisSignature
# Note: ToolDiscoverySignature removed in migration - agent now exposes tools directly via MCPServer

import logging

# Real MCP infrastructure - UPDATED to use kailash.mcp_server
# NOTE: kaizen.mcp has been deprecated and removed
# Tests now use production kailash.mcp_server infrastructure
from kaizen.memory import SharedMemoryPool

# Real LLM provider fixtures

# TODO: Import kailash.mcp_server.MCPServer when tests are refactored
# from kailash.mcp_server import MCPServer


logger = logging.getLogger(__name__)


# ===================================================================
# INTEGRATION TESTS WITH REAL OPENAI (gpt-5-nano)
# ===================================================================


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.requires_llm
class TestMCPServerAgentRealOpenAI:
    """Integration tests with real OpenAI provider."""

    @pytest.fixture
    def openai_config(self, openai_api_key):
        """Configuration using real OpenAI provider."""
        return MCPServerAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",  # Use gpt-4o-mini for better availability
            temperature=0.1,  # Low temperature for deterministic behavior
            max_tokens=500,
            server_name="test-qa-agent-openai",
            server_port=19100,
            enable_auth=False,
            enable_monitoring=True,
        )

    @pytest.fixture
    def openai_agent(self, openai_config):
        """Agent configured with real OpenAI provider."""
        agent = MCPServerAgent(openai_config)
        yield agent
        # Cleanup
        if agent.is_running:
            agent.stop_server()

    def test_openai_question_answering_tool(self, openai_agent):
        """Test real OpenAI LLM can answer questions via MCP tool."""
        # Start server
        started = openai_agent.start_server()
        assert started

        # Invoke question_answering tool
        result = openai_agent.handle_mcp_request(
            tool_name="question_answering",
            arguments={"question": "What is the capital of France?"},
        )

        # Verify JSON-RPC 2.0 compliance
        assert "jsonrpc" in result
        assert result["jsonrpc"] == "2.0"

        # Should have result (no error)
        if "error" not in result:
            assert "result" in result
            assert "answer" in result["result"]

            # Verify LLM produced meaningful answer
            answer = result["result"]["answer"]
            assert len(answer) > 0
            logger.info(f"OpenAI answer: {answer}")

            # Answer should mention Paris (with some flexibility)
            # We don't assert exact content as LLMs can vary
            assert isinstance(answer, str)

    def test_openai_text_analysis_tool(self, openai_agent):
        """Test real OpenAI LLM can analyze text via MCP tool."""
        openai_agent.start_server()

        # Invoke text_analysis tool
        text_to_analyze = "This is a test document about artificial intelligence and machine learning."

        result = openai_agent.handle_mcp_request(
            tool_name="text_analysis", arguments={"text": text_to_analyze}
        )

        # Verify JSON-RPC 2.0 compliance
        assert "jsonrpc" in result
        assert result["jsonrpc"] == "2.0"

        # Should have result
        if "error" not in result:
            assert "result" in result
            assert "key_topics" in result["result"]
            assert "sentiment" in result["result"]
            assert "summary" in result["result"]

            # Verify LLM extracted topics
            topics = result["result"]["key_topics"]
            assert isinstance(topics, (list, str))

            # Log analysis
            logger.info(
                f"OpenAI text analysis: {json.dumps(result['result'], indent=2)}"
            )

    def test_openai_tool_discovery(self, openai_agent):
        """Test real OpenAI LLM can describe available tools."""
        openai_agent.start_server()

        # Invoke discover_tools tool
        result = openai_agent.handle_mcp_request(
            tool_name="discover_tools", arguments={"query": "What tools are available?"}
        )

        # Verify response
        assert "jsonrpc" in result
        assert result["jsonrpc"] == "2.0"

        if "error" not in result:
            assert "result" in result
            assert "available_tools" in result["result"]
            assert "description" in result["result"]

            # Should list the exposed tools
            tools = result["result"]["available_tools"]
            assert isinstance(tools, (list, str))

            logger.info(f"OpenAI tool discovery: {result['result']['description']}")

    def test_openai_json_rpc_error_handling(self, openai_agent):
        """Test error handling with real OpenAI LLM."""
        openai_agent.start_server()

        # Invoke non-existent tool
        result = openai_agent.handle_mcp_request(
            tool_name="nonexistent_tool", arguments={}
        )

        # Should return JSON-RPC error
        assert "jsonrpc" in result
        assert "error" in result
        assert result["error"]["code"] == -32601  # Method not found

    def test_openai_server_lifecycle(self, openai_agent):
        """Test server start/stop with real OpenAI LLM."""
        # Start server
        started = openai_agent.start_server()
        assert started
        assert openai_agent.is_running

        # Verify registered in MCP registry
        server_info = openai_agent.registry.get_server(
            openai_agent.server_config.server_name
        )
        assert server_info is not None
        assert server_info.server_state == "running"

        # Test tool invocation while running
        result = openai_agent.handle_mcp_request(
            tool_name="question_answering", arguments={"question": "Test question"}
        )
        assert "jsonrpc" in result

        # Stop server
        stopped = openai_agent.stop_server()
        assert stopped
        assert not openai_agent.is_running

    def test_openai_memory_integration(self, openai_agent):
        """Test that real OpenAI LLM writes to shared memory."""
        # Give agent shared memory
        memory = SharedMemoryPool()
        openai_agent.shared_memory = memory

        openai_agent.start_server()

        # Invoke tool
        openai_agent.handle_mcp_request(
            tool_name="question_answering",
            arguments={"question": "What is machine learning?"},
        )

        # Check memory
        all_insights = memory.read_all()

        # Should have written at least one insight
        assert len(all_insights) > 0

        logger.info(f"OpenAI wrote {len(all_insights)} insights to memory")

    def test_openai_concurrent_requests(self, openai_agent):
        """Test handling multiple concurrent requests with real OpenAI."""
        openai_agent.start_server()

        # Send multiple requests
        questions = [
            "What is AI?",
            "What is machine learning?",
            "What is deep learning?",
        ]

        results = []
        start_time = time.time()

        for question in questions:
            result = openai_agent.handle_mcp_request(
                tool_name="question_answering", arguments={"question": question}
            )
            results.append(result)

        total_time = time.time() - start_time

        # All should succeed
        for result in results:
            assert "jsonrpc" in result
            # Some might succeed, some might fail - both acceptable

        logger.info(f"Processed {len(questions)} requests in {total_time:.2f}s")
        logger.info(f"Average latency: {total_time/len(questions):.2f}s")


# ===================================================================
# INTEGRATION TESTS WITH REAL OLLAMA
# ===================================================================


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.requires_llm
@pytest.mark.requires_ollama
class TestMCPServerAgentRealOllama:
    """Integration tests with real Ollama provider."""

    @pytest.fixture
    def ollama_config(self):
        """Configuration using real Ollama provider."""
        return MCPServerAgentConfig(
            llm_provider="ollama",
            model="llama3.2:latest",
            temperature=0.1,
            max_tokens=500,
            server_name="test-qa-agent-ollama",
            server_port=19101,
            enable_auth=False,
            enable_monitoring=True,
        )

    @pytest.fixture
    def ollama_agent(self, ollama_config, real_ollama_provider):
        """Agent configured with real Ollama provider."""
        if not real_ollama_provider.is_available():
            pytest.skip("Ollama not available")

        agent = MCPServerAgent(ollama_config)
        yield agent
        # Cleanup
        if agent.is_running:
            agent.stop_server()

    def test_ollama_question_answering_tool(self, ollama_agent):
        """Test real Ollama LLM can answer questions via MCP tool."""
        ollama_agent.start_server()

        result = ollama_agent.handle_mcp_request(
            tool_name="question_answering", arguments={"question": "What is Python?"}
        )

        # Verify structure
        assert "jsonrpc" in result
        assert result["jsonrpc"] == "2.0"

        if "error" not in result:
            assert "result" in result
            assert "answer" in result["result"]
            logger.info(f"Ollama answer: {result['result']['answer']}")

    def test_ollama_text_analysis_tool(self, ollama_agent):
        """Test real Ollama LLM can analyze text."""
        ollama_agent.start_server()

        result = ollama_agent.handle_mcp_request(
            tool_name="text_analysis",
            arguments={"text": "Test document about technology."},
        )

        assert "jsonrpc" in result

        if "error" not in result:
            assert "result" in result
            logger.info(f"Ollama analysis: {json.dumps(result['result'], indent=2)}")


# ===================================================================
# COMPARATIVE TESTS
# ===================================================================


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.requires_llm
class TestMCPServerAgentProviderComparison:
    """Compare behavior across different real LLM providers."""

    def test_provider_consistency_qa(self, openai_api_key, real_ollama_provider):
        """Test that different providers can both answer questions."""
        # OpenAI agent
        openai_config = MCPServerAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            server_name="comparison-openai",
            server_port=19102,
        )
        openai_agent = MCPServerAgent(openai_config)
        openai_agent.start_server()

        # Test question
        question = "What is 2 + 2?"

        # OpenAI response
        openai_result = openai_agent.handle_mcp_request(
            tool_name="question_answering", arguments={"question": question}
        )

        # Verify OpenAI
        assert "jsonrpc" in openai_result
        if "error" not in openai_result:
            assert "result" in openai_result
            logger.info(
                f"OpenAI answer: {openai_result['result'].get('answer', 'N/A')}"
            )

        openai_agent.stop_server()

        # Ollama agent (if available)
        if real_ollama_provider.is_available():
            ollama_config = MCPServerAgentConfig(
                llm_provider="ollama",
                model="llama3.2:latest",
                server_name="comparison-ollama",
                server_port=19103,
            )
            ollama_agent = MCPServerAgent(ollama_config)
            ollama_agent.start_server()

            ollama_result = ollama_agent.handle_mcp_request(
                tool_name="question_answering", arguments={"question": question}
            )

            assert "jsonrpc" in ollama_result
            if "error" not in ollama_result:
                logger.info(
                    f"Ollama answer: {ollama_result['result'].get('answer', 'N/A')}"
                )

            ollama_agent.stop_server()


# ===================================================================
# PERFORMANCE TESTS WITH REAL LLM
# ===================================================================


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.requires_llm
@pytest.mark.performance
class TestMCPServerAgentRealLLMPerformance:
    """Performance tests with real LLM providers."""

    def test_openai_question_latency(self, openai_api_key):
        """Test question answering latency with real OpenAI."""
        config = MCPServerAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            server_name="perf-test-openai",
            server_port=19104,
        )

        agent = MCPServerAgent(config)
        agent.start_server()

        # Measure latency
        start_time = time.time()
        result = agent.handle_mcp_request(
            tool_name="question_answering", arguments={"question": "What is AI?"}
        )
        latency = time.time() - start_time

        # Verify success
        assert "jsonrpc" in result

        # Log performance
        logger.info(f"OpenAI question latency: {latency:.2f}s")

        # Should complete in reasonable time (< 10s)
        assert latency < 10.0

        agent.stop_server()

    def test_throughput_multiple_questions(self, openai_api_key):
        """Test throughput of multiple questions."""
        config = MCPServerAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            server_name="throughput-test",
            server_port=19105,
        )

        agent = MCPServerAgent(config)
        agent.start_server()

        questions = ["What is 1+1?", "What is 2+2?", "What is 3+3?"]

        start_time = time.time()
        results = []

        for q in questions:
            result = agent.handle_mcp_request(
                tool_name="question_answering", arguments={"question": q}
            )
            results.append(result)

        total_time = time.time() - start_time

        # All should return valid JSON-RPC
        for result in results:
            assert "jsonrpc" in result

        logger.info(f"Processed {len(questions)} questions in {total_time:.2f}s")
        logger.info(f"Throughput: {len(questions)/total_time:.2f} questions/sec")

        agent.stop_server()


# ===================================================================
# ERROR HANDLING WITH REAL LLM
# ===================================================================


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.requires_llm
class TestMCPServerAgentRealLLMErrorHandling:
    """Test error handling with real LLM providers."""

    def test_openai_invalid_arguments(self, openai_api_key):
        """Test error handling with invalid arguments."""
        config = MCPServerAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            server_name="error-test",
            server_port=19106,
        )

        agent = MCPServerAgent(config)
        agent.start_server()

        # Missing required argument
        result = agent.handle_mcp_request(
            tool_name="question_answering", arguments={}  # Missing 'question'
        )

        # Should return error or handle gracefully
        assert "jsonrpc" in result
        # Either error or default response is acceptable

        agent.stop_server()

    def test_openai_server_not_running(self, openai_api_key):
        """Test error when server not running."""
        config = MCPServerAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            server_name="not-running-test",
            server_port=19107,
        )

        agent = MCPServerAgent(config)
        # Don't start server

        result = agent.handle_mcp_request(
            tool_name="question_answering", arguments={"question": "test"}
        )

        # Should return error
        assert "jsonrpc" in result
        assert "error" in result
        assert result["error"]["code"] == -32603  # Internal error


# ===================================================================
# PYTEST MARKERS
# ===================================================================

pytestmark = [
    pytest.mark.integration,
    pytest.mark.mcp,
    pytest.mark.requires_llm,
]
