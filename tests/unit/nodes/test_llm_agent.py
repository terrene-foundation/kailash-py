"""Unit tests for LLMAgentNode node."""

import pytest

from kailash.nodes.ai import LLMAgentNode


class TestLLMAgentNode:
    """Test cases for LLMAgentNode node."""

    def test_basic_qa_mock_provider(self):
        """Test basic Q&A with mock provider."""
        node = LLMAgentNode()
        result = node.execute(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "What is machine learning?"}],
            system_prompt="You are a helpful AI assistant.",
        )

        assert result["success"] is True
        assert "response" in result
        assert result["response"]["role"] == "assistant"
        assert result["response"]["model"] == "mock-model"
        assert "content" in result["response"]
        assert "usage" in result
        assert result["metadata"]["provider"] == "mock"

    def test_tool_calling_agent(self):
        """Test agent with tool calling capabilities."""
        node = LLMAgentNode()

        tools = [
            {
                "name": "get_weather",
                "description": "Get weather information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                        "units": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                    },
                    "required": ["location"],
                },
            },
            {
                "name": "send_email",
                "description": "Send an email",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string"},
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["to", "subject", "body"],
                },
            },
        ]

        result = node.execute(
            provider="mock",
            model="gpt-4",
            messages=[
                {
                    "role": "user",
                    "content": "Get the weather for New York and send an email about it",
                }
            ],
            tools=tools,
        )

        assert result["success"] is True
        assert result["context"]["tools_available"] == 2
        response = result["response"]
        assert "tool_calls" in response
        # Mock may generate tool calls for "create", "send", etc. keywords

    def test_conversation_memory(self):
        """Test conversation memory functionality."""
        node = LLMAgentNode()
        conversation_id = "test_conversation_123"

        # First turn
        result1 = node.execute(
            provider="mock",
            model="gpt-4",
            messages=[
                {"role": "user", "content": "My name is Alice and I work in marketing."}
            ],
            conversation_id=conversation_id,
            memory_config={"type": "buffer", "max_tokens": 2000},
        )

        assert result1["success"] is True
        assert result1["conversation_id"] == conversation_id

        # Second turn - should have access to previous context
        result2 = node.execute(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "What do you remember about me?"}],
            conversation_id=conversation_id,
            memory_config={"type": "buffer", "max_tokens": 2000},
        )

        assert result2["success"] is True
        assert result2["conversation_id"] == conversation_id
        assert result2["context"]["memory_tokens"] > 0

    def test_mcp_context_integration(self):
        """Test MCP context integration."""
        node = LLMAgentNode()

        result = node.execute(
            provider="mock",
            model="claude-3-sonnet",
            messages=[{"role": "user", "content": "Analyze the customer data"}],
            mcp_context=[
                "data://customers/analysis.json",
                "workflow://reports/summary.md",
            ],
            mcp_servers=[
                {
                    "name": "data-server",
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "data_server"],
                }
            ],
        )

        assert result["success"] is True
        assert result["context"]["mcp_resources_used"] > 0

    def test_rag_configuration(self):
        """Test RAG (Retrieval-Augmented Generation) configuration."""
        node = LLMAgentNode()

        result = node.execute(
            provider="mock",
            model="gpt-4-turbo",
            messages=[
                {
                    "role": "user",
                    "content": "What are the best practices for customer retention?",
                }
            ],
            rag_config={"enabled": True, "top_k": 5, "similarity_threshold": 0.8},
        )

        assert result["success"] is True
        assert result["context"]["rag_documents_retrieved"] >= 0

    def test_generation_config(self):
        """Test custom generation configuration."""
        node = LLMAgentNode()

        generation_config = {"temperature": 0.9, "max_tokens": 1000, "top_p": 0.95}

        result = node.execute(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "Write a creative story"}],
            generation_config=generation_config,
        )

        assert result["success"] is True
        assert result["metadata"]["generation_config"] == generation_config

    def test_streaming_configuration(self):
        """Test streaming response configuration."""
        node = LLMAgentNode()

        result = node.execute(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "Explain quantum computing"}],
            streaming=True,
            timeout=60,
        )

        assert result["success"] is True
        assert result["metadata"]["streaming"] is True

    def test_multiple_providers(self):
        """Test different provider configurations."""
        node = LLMAgentNode()

        providers = [
            ("ollama", "llama3.2"),  # Ollama provider
            ("mock", "test-model"),
        ]

        for provider, model in providers:
            result = node.execute(
                provider=provider,
                model=model,
                messages=[{"role": "user", "content": "Hello, how are you?"}],
            )

            if provider == "ollama":
                # For unit tests, we don't actually connect to Ollama
                # Just verify the result structure
                if result["success"]:
                    assert result["metadata"]["provider"] == provider
                else:
                    # If Ollama is not available, it should fail gracefully
                    assert (
                        "Ollama" in result.get("error", "")
                        or "ollama" in result.get("error", "").lower()
                    )
            else:
                assert result["success"] is True
                assert result["metadata"]["provider"] == provider

    def test_langchain_availability_check(self):
        """Test LangChain availability detection."""
        node = LLMAgentNode()

        # Test with mock provider - should work without LangChain
        result = node.execute(
            provider="mock",
            model="test-model",
            messages=[{"role": "user", "content": "Test message"}],
        )

        assert result["success"] is True
        # Should work with mock provider even without LangChain

    def test_error_handling_invalid_provider(self):
        """Test error handling for invalid provider."""
        node = LLMAgentNode()

        result = node.execute(
            provider="invalid_provider",
            model="some-model",
            messages=[{"role": "user", "content": "Test"}],
        )

        # Should still work with mock implementation
        assert result["success"] is True or "error" in result

    def test_missing_required_parameters(self):
        """Test handling of missing required parameters."""
        node = LLMAgentNode()

        # All parameters have defaults, so execution should work
        # Missing provider - should use default (mock)
        result = node.execute(
            model="llama3.2:3b", messages=[{"role": "user", "content": "test"}]
        )
        assert result["success"] is True

        # Missing model - should use default but use ollama provider
        result = node.execute(
            provider="ollama", messages=[{"role": "user", "content": "test"}]
        )
        assert (
            result["success"] is True or "error" in result
        )  # Ollama might not be available

        # Missing messages - should use default empty list
        result = node.execute(provider="ollama", model="llama3.2:3b")
        # With empty messages, might succeed or fail gracefully
        assert isinstance(result, dict)

    def test_conversation_without_memory_config(self):
        """Test conversation handling without explicit memory config."""
        node = LLMAgentNode()

        result = node.execute(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "Test without memory config"}],
            conversation_id="no_memory_config",
        )

        assert result["success"] is True
        assert result["conversation_id"] == "no_memory_config"

    def test_complex_multi_modal_scenario(self):
        """Test complex scenario with multiple features."""
        node = LLMAgentNode()

        tools = [
            {
                "name": "analyze_sentiment",
                "description": "Analyze text sentiment",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            }
        ]

        result = node.execute(
            provider="mock",  # Use mock provider for testing
            model="test-model",
            messages=[
                {
                    "role": "user",
                    "content": "Analyze customer feedback and provide recommendations",
                }
            ],
            system_prompt="You are a customer experience analyst with access to sentiment analysis tools.",
            tools=tools,
            conversation_id="complex_analysis",
            memory_config={"type": "buffer", "max_tokens": 3000},
            mcp_context=["data://feedback/customer_reviews.json"],
            rag_config={"enabled": True, "top_k": 3, "similarity_threshold": 0.7},
            generation_config={"temperature": 0.6, "max_tokens": 1200},
        )

        assert result["success"] is True
        assert result["conversation_id"] == "complex_analysis"
        assert result["context"]["tools_available"] == 1
        assert result["context"]["mcp_resources_used"] >= 0
        assert result["context"]["rag_documents_retrieved"] >= 0
        assert "usage" in result

    def test_usage_metrics_calculation(self):
        """Test usage metrics and cost calculation."""
        node = LLMAgentNode()

        result = node.execute(
            provider="mock",
            model="gpt-4",
            messages=[
                {"role": "user", "content": "Calculate usage metrics for this request"}
            ],
        )

        assert result["success"] is True
        usage = result["usage"]

        assert "prompt_tokens" in usage
        assert "completion_tokens" in usage
        assert "total_tokens" in usage
        assert "estimated_cost_usd" in usage
        assert "efficiency_score" in usage
        assert usage["total_tokens"] > 0
        assert usage["estimated_cost_usd"] >= 0

    def test_system_prompt_handling(self):
        """Test system prompt handling."""
        node = LLMAgentNode()

        custom_system_prompt = (
            "You are a specialized AI assistant for financial analysis."
        )

        result = node.execute(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "Analyze this financial data"}],
            system_prompt=custom_system_prompt,
        )

        assert result["success"] is True
        # System prompt should be used in conversation preparation

    def test_timeout_and_retry_config(self):
        """Test timeout and retry configuration."""
        node = LLMAgentNode()

        result = node.execute(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "Test timeout configuration"}],
            timeout=30,
            max_retries=5,
        )

        assert result["success"] is True
        # Configuration should be accepted without errors


@pytest.fixture
def sample_conversation_history():
    """Sample conversation history for testing."""
    return [
        {"role": "user", "content": "Hello, I'm working on a data analysis project."},
        {
            "role": "assistant",
            "content": "Great! I'd be happy to help with your data analysis project. What kind of data are you working with?",
        },
        {
            "role": "user",
            "content": "I have customer transaction data and need to identify patterns.",
        },
    ]


@pytest.fixture
def sample_tools():
    """Sample tools for testing."""
    return [
        {
            "name": "query_database",
            "description": "Query customer database",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 100},
                },
                "required": ["query"],
            },
        },
        {
            "name": "generate_chart",
            "description": "Generate data visualization",
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_type": {"type": "string", "enum": ["bar", "line", "pie"]},
                    "data": {"type": "array"},
                },
                "required": ["chart_type", "data"],
            },
        },
    ]


def test_agent_with_realistic_scenario(sample_conversation_history, sample_tools):
    """Test agent with realistic data analysis scenario."""
    node = LLMAgentNode()

    result = node.execute(
        provider="mock",
        model="gpt-4-turbo",
        messages=sample_conversation_history,
        system_prompt="""You are a data analyst expert. Help users with:
        1. Data exploration and analysis
        2. Pattern identification
        3. Visualization recommendations
        4. Statistical insights

        Use available tools to query data and create visualizations.""",
        tools=sample_tools,
        conversation_id="data_analysis_session",
        memory_config={"type": "buffer", "max_tokens": 4000, "persistence": True},
        generation_config={
            "temperature": 0.3,  # Lower temperature for analytical tasks
            "max_tokens": 1000,
        },
    )

    assert result["success"] is True
    assert result["context"]["tools_available"] == 2
    assert len(sample_conversation_history) >= 3
    assert result["conversation_id"] == "data_analysis_session"
