"""Validation test for Migration Guide Pattern 4: AI/Kaizen Agent Calls.

Validates the handler structure for AI integration patterns.
Since we don't have API keys in CI, this validates the handler
function structure and parameter handling (not actual AI calls).

Pattern 4 demonstrates: Legacy pattern BROKEN by sandbox -> Handler with full Kaizen access.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../src"))

from kailash.nodes.handler import (
    HandlerNode,
    _derive_params_from_signature,
    make_handler_workflow,
)
from kailash.runtime import AsyncLocalRuntime

# --- Handler functions from migration guide Pattern 4 ---
# Adapted to not require actual AI API calls


async def analyze_text(
    text: str,
    analysis_type: str = "sentiment",
    include_summary: bool = True,
) -> dict:
    """Analyze text using Kaizen AI agent (simulated for testing)."""
    # In production: result = await analyst.run(prompt)
    result = f"Analysis ({analysis_type}): {text[:50]}..."

    return {
        "analysis": result,
        "analysis_type": analysis_type,
        "text_length": len(text),
    }


async def summarize_document(
    document: str,
    max_length: int = 200,
    style: str = "professional",
) -> dict:
    """Generate document summary (simulated for testing)."""
    # In production: summary = await analyst.run(prompt)
    summary = document[:max_length]

    return {
        "summary": summary,
        "original_length": len(document.split()),
        "style": style,
    }


# --- Tests ---


class TestPattern4Kaizen:
    """Validate Pattern 4: AI/Kaizen Agent handler structure."""

    @pytest.mark.asyncio
    async def test_analyze_text_handler(self):
        """Handler analyzes text and returns correct structure."""
        workflow = make_handler_workflow(analyze_text, "handler")
        runtime = AsyncLocalRuntime()

        results, run_id = await runtime.execute_workflow_async(
            workflow,
            inputs={
                "text": "This is a great product with excellent features.",
                "analysis_type": "sentiment",
            },
        )

        assert run_id is not None
        handler_result = next(iter(results.values()), {})
        assert "analysis" in handler_result
        assert handler_result["analysis_type"] == "sentiment"
        assert handler_result["text_length"] == len(
            "This is a great product with excellent features."
        )

    @pytest.mark.asyncio
    async def test_analyze_text_default_type(self):
        """Handler uses default analysis type."""
        workflow = make_handler_workflow(analyze_text, "handler")
        runtime = AsyncLocalRuntime()

        results, _ = await runtime.execute_workflow_async(
            workflow, inputs={"text": "Hello world"}
        )

        handler_result = next(iter(results.values()), {})
        assert handler_result["analysis_type"] == "sentiment"

    @pytest.mark.asyncio
    async def test_summarize_document_handler(self):
        """Handler summarizes document and returns correct structure."""
        workflow = make_handler_workflow(summarize_document, "handler")
        runtime = AsyncLocalRuntime()

        document = "This is a long document about financial markets. " * 20

        results, _ = await runtime.execute_workflow_async(
            workflow,
            inputs={
                "document": document,
                "max_length": 50,
                "style": "executive",
            },
        )

        handler_result = next(iter(results.values()), {})
        assert len(handler_result["summary"]) <= 50
        assert handler_result["style"] == "executive"
        assert handler_result["original_length"] > 0

    @pytest.mark.asyncio
    async def test_multiple_handlers_share_agent(self):
        """Multiple handler workflows can execute sequentially (simulating shared agent)."""
        analyze_wf = make_handler_workflow(analyze_text, "analyze")
        summarize_wf = make_handler_workflow(summarize_document, "summarize")
        runtime = AsyncLocalRuntime()

        results1, _ = await runtime.execute_workflow_async(
            analyze_wf, inputs={"text": "Test text"}
        )
        results2, _ = await runtime.execute_workflow_async(
            summarize_wf, inputs={"document": "Test document content"}
        )

        assert "analysis" in next(iter(results1.values()), {})
        assert "summary" in next(iter(results2.values()), {})

    def test_handler_signature_params(self):
        """Verify handler parameters are correctly derived from signature."""
        params = _derive_params_from_signature(analyze_text)

        assert "text" in params
        assert params["text"].required is True
        assert params["text"].type is str

        assert "analysis_type" in params
        assert params["analysis_type"].required is False
        assert params["analysis_type"].default == "sentiment"

        assert "include_summary" in params
        assert params["include_summary"].required is False
        assert params["include_summary"].type is bool
