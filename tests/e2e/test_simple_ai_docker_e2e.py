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
response_text = llm_response.get("response", "")
word_count = len(response_text.split())

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

        result = runtime.execute_workflow(workflow, inputs)

        # Verify basic functionality
        assert result["status"] == "success"
        assert "simple_llm" in result["results"]
        assert "process_response" in result["results"]

        # Verify response processing
        processed = result["results"]["process_response"]
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
analysis_text = llm_response.get("response", "")

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

            result = runtime.execute_workflow(workflow, inputs)

            # Verify workflow success
            assert result["status"] == "success"
            assert len(result["errors"]) == 0

            # Verify data was read
            read_result = result["results"]["read_data"]
            assert len(read_result["data"]) == 3  # 3 people

            # Verify AI analysis
            ai_result = result["results"]["analyze_data"]
            assert "response" in ai_result
            assert len(ai_result["response"]) > 0

            # Verify formatted analysis
            formatted = result["results"]["format_analysis"]
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
first_response = first_ai_response.get("response", "")
second_response = second_ai_response.get("response", "")

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

        result = runtime.execute_workflow(workflow, inputs)

        # Verify conversation worked
        assert result["status"] == "success"
        assert len(result["errors"]) == 0

        # Verify both AI responses
        first_ai = result["results"]["first_ai"]
        second_ai = result["results"]["second_ai"]

        assert "response" in first_ai
        assert "response" in second_ai
        assert len(first_ai["response"]) > 0
        assert len(second_ai["response"]) > 0

        # Verify combination
        combined = result["results"]["combine_responses"]
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
    response_text = ai_result.get("response", "")
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

        result = runtime.execute_workflow(workflow, inputs)

        # Workflow should complete regardless of AI success/failure
        assert result["status"] == "success"

        # Check error handling
        handler_result = result["results"]["handle_result"]

        # Either success or proper error handling
        if handler_result["success"]:
            assert handler_result["response_valid"] is True
            assert len(handler_result["response"]) > 0
        else:
            assert handler_result["error_handled"] is True
            assert handler_result["fallback_response"] == "AI service unavailable"
