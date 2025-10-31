"""Simple AI Docker E2E Tests

These tests validate basic AI functionality with Docker services,
focusing on simple scenarios that should work reliably.

Key functionality tested:
- Basic LLM integration with Ollama
- Simple AI workflows with real data
- Docker service connectivity
- Fundamental AI node functionality
"""

import asyncio
from pathlib import Path
from typing import Any, Dict

import pytest

from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow import WorkflowBuilder
from tests.utils.docker_config import OLLAMA_CONFIG

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.requires_docker,
    pytest.mark.requires_ollama,
    pytest.mark.ai,
]


class TestSimpleAIDocker:
    """Simple AI Docker E2E test scenarios."""

    def test_basic_ollama_connectivity(self):
        """Test basic connection to Ollama service."""
        builder = WorkflowBuilder()

        # Simple LLM test
        builder.add_node(
            "LLMAgentNode",
            "simple_llm",
            {
                "model": "llama3.2:1b",
                "base_url": OLLAMA_CONFIG["base_url"],
                "temperature": 0.1,
                "timeout": 30,
            },
        )

        builder.add_node(
            "PythonCodeNode",
            "process_response",
            {
                "code": """
# Simple response processing
# Handle both dict and string responses
if isinstance(llm_response, dict):
    # Try different fields where the response might be
    response_text = llm_response.get("response", "") or llm_response.get("content", "") or llm_response.get("message", "")
elif isinstance(llm_response, str):
    response_text = llm_response
else:
    response_text = str(llm_response)

word_count = len(response_text.split()) if response_text else 0

result = {
    "response": response_text,
    "word_count": word_count,
    "success": len(response_text) > 0
}
"""
            },
        )

        builder.add_connection(
            "simple_llm", "response", "process_response", "llm_response"
        )

        workflow = builder.build()
        runtime = LocalRuntime()

        # Simple prompt test
        inputs = {
            "simple_llm": {"prompt": "Say hello in exactly 3 words.", "max_tokens": 10}
        }

        result, run_id = runtime.execute(workflow, inputs)

        # Verify basic functionality
        assert "simple_llm" in result
        assert "process_response" in result

        # Verify response processing
        processed = result["process_response"]["result"]
        assert processed["success"] is True
        assert processed["word_count"] > 0

    def test_ai_data_processing_workflow(self):
        """Test AI processing of simple CSV data."""
        builder = WorkflowBuilder()

        # Create test data
        test_data = """name,age,city
Alice,25,New York
Bob,30,San Francisco
Charlie,35,Chicago"""

        test_file = Path("/tmp/test_simple_ai_data.csv")
        test_file.write_text(test_data)

        try:
            # Read CSV data
            builder.add_node(
                "CSVReaderNode", "read_data", {"file_path": str(test_file)}
            )

            # Process with AI
            builder.add_node(
                "LLMAgentNode",
                "analyze_data",
                {
                    "model": "llama3.2:1b",
                    "base_url": OLLAMA_CONFIG["base_url"],
                    "temperature": 0.1,
                    "timeout": 45,
                },
            )

            # Format AI analysis
            builder.add_node(
                "PythonCodeNode",
                "format_analysis",
                {
                    "code": """
import json

# Extract AI analysis
analysis_text = llm_response.get("response", "") or llm_response.get("content", "")

# Simple analysis formatting
result = {
    "analysis": analysis_text,
    "data_points_analyzed": len(csv_data) if isinstance(csv_data, list) else 0,
    "analysis_length": len(analysis_text),
    "has_insights": "age" in analysis_text.lower() or "city" in analysis_text.lower()
}
"""
                },
            )

            # Connect the workflow
            builder.add_connection("read_data", "data", "analyze_data", "context")
            builder.add_connection("read_data", "data", "format_analysis", "csv_data")
            builder.add_connection(
                "analyze_data", "response", "format_analysis", "llm_response"
            )

            workflow = builder.build()
            runtime = LocalRuntime()

            # Execute with AI prompt
            inputs = {
                "analyze_data": {
                    "prompt": "Analyze this CSV data. What patterns do you see? Be brief.",
                    "max_tokens": 50,
                }
            }

            result, run_id = runtime.execute(workflow, inputs)

            # Verify workflow completed
            assert "read_data" in result
            assert "analyze_data" in result
            assert "format_analysis" in result

            # Verify data was read
            read_result = result["read_data"]
            assert len(read_result["data"]) == 3  # 3 people

            # Verify AI analysis
            ai_result = result["analyze_data"]
            assert "response" in ai_result
            assert len(ai_result["response"]) > 0

            # Verify formatted analysis
            formatted = result["format_analysis"]["result"]
            assert formatted["data_points_analyzed"] == 3
            assert formatted["analysis_length"] > 0

        finally:
            # Cleanup
            if test_file.exists():
                test_file.unlink()

    def test_simple_ai_conversation_chain(self):
        """Test simple AI conversation with context passing."""
        builder = WorkflowBuilder()

        # First AI interaction
        builder.add_node(
            "LLMAgentNode",
            "first_ai",
            {
                "model": "llama3.2:1b",
                "base_url": OLLAMA_CONFIG["base_url"],
                "temperature": 0.2,
                "timeout": 30,
            },
        )

        # Second AI interaction with context
        builder.add_node(
            "LLMAgentNode",
            "second_ai",
            {
                "model": "llama3.2:1b",
                "base_url": OLLAMA_CONFIG["base_url"],
                "temperature": 0.2,
                "timeout": 30,
            },
        )

        # Combine responses
        builder.add_node(
            "PythonCodeNode",
            "combine_responses",
            {
                "code": """
# Combine AI responses
first_response = first_ai_response.get("response", "") or first_ai_response.get("content", "")
second_response = second_ai_response.get("response", "") or second_ai_response.get("content", "")

result = {
    "first_response": first_response,
    "second_response": second_response,
    "total_length": len(first_response) + len(second_response),
    "conversation_complete": len(first_response) > 0 and len(second_response) > 0
}
"""
            },
        )

        # Connect the conversation chain
        builder.add_connection("first_ai", "response", "second_ai", "context")
        builder.add_connection(
            "first_ai", "response", "combine_responses", "first_ai_response"
        )
        builder.add_connection(
            "second_ai", "response", "combine_responses", "second_ai_response"
        )

        workflow = builder.build()
        runtime = LocalRuntime()

        # Execute conversation
        inputs = {
            "first_ai": {"prompt": "What is Python programming?", "max_tokens": 30},
            "second_ai": {
                "prompt": "Based on the previous response, give one example.",
                "max_tokens": 20,
            },
        }

        result, run_id = runtime.execute(workflow, inputs)

        # Verify conversation worked
        assert "first_ai" in result
        assert "second_ai" in result
        assert "combine_responses" in result

        # Verify both AI responses
        first_ai = result["first_ai"]
        second_ai = result["second_ai"]

        assert "response" in first_ai
        assert "response" in second_ai
        assert len(first_ai["response"]) > 0
        assert len(second_ai["response"]) > 0

        # Verify combination
        combined = result["combine_responses"]["result"]
        assert combined["conversation_complete"] is True
        assert combined["total_length"] > 0

    def test_ai_with_error_handling(self):
        """Test AI workflow with proper error handling."""
        builder = WorkflowBuilder()

        # AI node with potential timeout
        builder.add_node(
            "LLMAgentNode",
            "ai_with_timeout",
            {
                "model": "llama3.2:1b",
                "base_url": OLLAMA_CONFIG["base_url"],
                "temperature": 0.1,
                "timeout": 10,  # Short timeout for testing
                "retry_attempts": 2,
            },
        )

        # Error handling node
        builder.add_node(
            "PythonCodeNode",
            "handle_result",
            {
                "code": """
# Handle AI response or error
if "error" in ai_result:
    result = {
        "success": False,
        "error_handled": True,
        "error_type": "ai_timeout_or_failure",
        "fallback_response": "AI service unavailable"
    }
else:
    response_text = ai_result.get("response", "") or ai_result.get("content", "")
    result = {
        "success": True,
        "error_handled": False,
        "response": response_text,
        "response_valid": len(response_text) > 0
    }
"""
            },
        )

        builder.add_connection(
            "ai_with_timeout", "response", "handle_result", "ai_result"
        )

        workflow = builder.build()
        runtime = LocalRuntime()

        # Execute with simple prompt
        inputs = {"ai_with_timeout": {"prompt": "Count to 3.", "max_tokens": 10}}

        result, run_id = runtime.execute(workflow, inputs)

        # Workflow should complete
        assert "ai_with_timeout" in result
        assert "handle_result" in result

        # Check error handling
        handler_result = result["handle_result"]["result"]

        # Either success or proper error handling
        if handler_result["success"]:
            assert handler_result["response_valid"] is True
            assert len(handler_result["response"]) > 0
        else:
            assert handler_result["error_handled"] is True
            assert handler_result["fallback_response"] == "AI service unavailable"
