"""Golden Pattern 7: Kaizen Agent Pattern - Validation Tests.

Validates AI agent creation with BaseAgent and signatures.
Tests structure only (no LLM calls) since we're validating patterns.
"""

import pytest

from kailash.nodes.handler import HandlerNode, make_handler_workflow
from kailash.runtime import AsyncLocalRuntime


class TestGoldenPattern7KaizenAgent:
    """Validate Pattern 7: Kaizen Agent Pattern (structural)."""

    @pytest.mark.asyncio
    async def test_handler_wrapping_agent_logic(self):
        """Handler can wrap agent-like logic."""

        async def analyze_text(text: str, analysis_type: str = "sentiment") -> dict:
            """Simulated agent analysis."""
            word_count = len(text.split())
            return {
                "analysis_type": analysis_type,
                "word_count": word_count,
                "text_length": len(text),
                "summary": f"Analyzed {word_count} words for {analysis_type}",
            }

        workflow = make_handler_workflow(analyze_text, node_id="analyze")
        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(
            workflow,
            inputs={"text": "This is a great product", "analysis_type": "sentiment"},
        )

        assert results["analyze"]["analysis_type"] == "sentiment"
        assert results["analyze"]["word_count"] == 5
        assert "Analyzed 5 words" in results["analyze"]["summary"]

    @pytest.mark.asyncio
    async def test_agent_with_default_analysis_type(self):
        """Agent uses default analysis_type when not provided."""

        async def analyze(text: str, analysis_type: str = "general") -> dict:
            return {
                "analysis_type": analysis_type,
                "result": f"Analyzed: {text[:50]}",
            }

        workflow = make_handler_workflow(analyze, node_id="analyze")
        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(
            workflow,
            inputs={"text": "Revenue increased by 15% year over year."},
        )

        assert results["analyze"]["analysis_type"] == "general"

    @pytest.mark.asyncio
    async def test_structured_output_from_agent(self):
        """Agent returns structured output matching signature pattern."""

        async def document_qa(document: str, question: str) -> dict:
            """Simulated document Q&A agent."""
            # Simulate structured output
            return {
                "answer": f"Based on the document, the answer relates to: {question}",
                "confidence": 0.85,
                "citations": [document[:100]],
            }

        workflow = make_handler_workflow(document_qa, node_id="qa")
        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(
            workflow,
            inputs={
                "document": "Q1 revenue was $10M, up 15% from Q4.",
                "question": "What was Q1 revenue?",
            },
        )

        assert "answer" in results["qa"]
        assert "confidence" in results["qa"]
        assert results["qa"]["confidence"] == 0.85
        assert isinstance(results["qa"]["citations"], list)

    @pytest.mark.asyncio
    async def test_multiple_agent_handlers(self):
        """Multiple agent handlers can be registered."""

        async def chat_agent(message: str, session_id: str = "default") -> dict:
            return {"response": f"Reply to: {message}", "session_id": session_id}

        async def analysis_agent(document: str, question: str) -> dict:
            return {"answer": "Analysis result", "confidence": 0.9}

        wf1 = make_handler_workflow(chat_agent, node_id="chat")
        wf2 = make_handler_workflow(analysis_agent, node_id="analyze")

        runtime = AsyncLocalRuntime()

        r1, _ = await runtime.execute_workflow_async(wf1, inputs={"message": "Hello"})
        r2, _ = await runtime.execute_workflow_async(
            wf2, inputs={"document": "Test doc", "question": "Q?"}
        )

        assert r1["chat"]["response"] == "Reply to: Hello"
        assert r2["analyze"]["confidence"] == 0.9


class TestKaizenImports:
    """Validate that Kaizen imports from Pattern 7 documentation resolve."""

    def test_base_agent_import(self):
        """BaseAgent import from kaizen.core.base_agent resolves."""
        from kaizen.core.base_agent import BaseAgent

        assert BaseAgent is not None
        assert callable(BaseAgent)

    def test_signature_imports(self):
        """Signature, InputField, OutputField imports resolve."""
        from kaizen.signatures import InputField, OutputField, Signature

        assert Signature is not None
        assert InputField is not None
        assert OutputField is not None
