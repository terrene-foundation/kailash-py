"""Scaffolding Template 2: AI Agent Backend - Validation Tests.

Validates the AI Agent template from the codegen decision tree.
Tests agent handler patterns (no actual LLM calls).
"""

import pytest
from nexus import Nexus

from kailash.nodes.handler import make_handler_workflow
from kailash.runtime import AsyncLocalRuntime


class TestAIAgentTemplate:
    """Validate AI Agent Backend Template patterns."""

    def test_chat_handler_registration(self):
        """Chat handler registers on Nexus."""
        app = Nexus(auto_discovery=False)

        @app.handler("chat", description="Send a chat message")
        async def chat(
            message: str,
            session_id: str = "default",
            context: str = "",
        ) -> dict:
            return {
                "response": f"Echo: {message}",
                "session_id": session_id,
            }

        assert "chat" in app._handler_registry

    @pytest.mark.asyncio
    async def test_chat_handler_execution(self):
        """Chat handler executes and returns structured response."""

        async def chat(
            message: str,
            session_id: str = "default",
            context: str = "",
        ) -> dict:
            return {
                "response": f"Analysis of: {message}",
                "session_id": session_id,
                "confidence": 0.9,
            }

        workflow = make_handler_workflow(chat, node_id="chat")
        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(
            workflow,
            inputs={"message": "What is revenue?", "session_id": "s-123"},
        )

        assert "Analysis of:" in results["chat"]["response"]
        assert results["chat"]["session_id"] == "s-123"
        assert results["chat"]["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_analysis_handler_execution(self):
        """Analysis handler returns structured output."""

        async def analyze(document: str, question: str) -> dict:
            return {
                "answer": f"Answer about: {question}",
                "citations": [document[:50]],
                "confidence": 0.85,
            }

        workflow = make_handler_workflow(analyze, node_id="analyze")
        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(
            workflow,
            inputs={
                "document": "Revenue grew 15% in Q1 2024.",
                "question": "What was Q1 growth?",
            },
        )

        assert "Answer about:" in results["analyze"]["answer"]
        assert isinstance(results["analyze"]["citations"], list)
        assert results["analyze"]["confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_summarize_handler_execution(self):
        """Summarize handler returns summary and key points."""

        async def summarize(document: str, max_length: int = 500) -> dict:
            words = document.split()
            return {
                "summary": " ".join(words[:max_length]),
                "key_points": ["Point 1", "Point 2"],
                "word_count": len(words),
            }

        workflow = make_handler_workflow(summarize, node_id="summarize")
        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(
            workflow,
            inputs={"document": "This is a long document about AI agents."},
        )

        assert "summary" in results["summarize"]
        assert isinstance(results["summarize"]["key_points"], list)

    def test_multiple_agent_handlers_same_app(self):
        """Multiple agent handlers coexist on same Nexus app."""
        app = Nexus(auto_discovery=False)

        @app.handler("chat", description="Chat with AI")
        async def chat(message: str) -> dict:
            return {"response": message}

        @app.handler("analyze", description="Analyze document")
        async def analyze(document: str, question: str) -> dict:
            return {"answer": "result"}

        @app.handler("summarize", description="Summarize document")
        async def summarize(document: str) -> dict:
            return {"summary": "summary"}

        assert len(app._handler_registry) == 3
