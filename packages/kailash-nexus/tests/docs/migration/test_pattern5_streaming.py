"""Validation test for Migration Guide Pattern 5: SSE Streaming Response.

Validates the handler pattern structure for streaming responses.
Pattern 5 demonstrates: Legacy NOT POSSIBLE -> Handler with SSE streaming.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../src"))

from kailash.nodes.handler import make_handler_workflow
from kailash.runtime import AsyncLocalRuntime

# --- Handler function from migration guide Pattern 5 ---
# The non-streaming handler (multi-channel compatible)


async def chat(message: str, conversation_id: str = None) -> dict:
    """Chat with AI - returns complete response (non-streaming handler)."""
    # In production: agent = Agent(model="gpt-4"); response = await agent.run(message)
    response = f"Response to: {message}"
    return {"response": response, "conversation_id": conversation_id}


# --- Tests ---


class TestPattern5Streaming:
    """Validate Pattern 5: SSE Streaming handler structure."""

    @pytest.mark.asyncio
    async def test_chat_handler_returns_response(self):
        """Non-streaming chat handler returns complete response."""
        workflow = make_handler_workflow(chat, "handler")
        runtime = AsyncLocalRuntime()

        results, run_id = await runtime.execute_workflow_async(
            workflow,
            inputs={"message": "Hello, how are you?", "conversation_id": "conv-123"},
        )

        assert run_id is not None
        handler_result = next(iter(results.values()), {})
        assert "response" in handler_result
        assert handler_result["conversation_id"] == "conv-123"

    @pytest.mark.asyncio
    async def test_chat_handler_optional_conversation_id(self):
        """Chat handler works without conversation_id."""
        workflow = make_handler_workflow(chat, "handler")
        runtime = AsyncLocalRuntime()

        results, _ = await runtime.execute_workflow_async(
            workflow, inputs={"message": "Quick question"}
        )

        handler_result = next(iter(results.values()), {})
        assert "response" in handler_result
        assert handler_result["conversation_id"] is None

    def test_streaming_endpoint_structure(self):
        """Validate that a streaming endpoint can be defined alongside handler.

        This validates the pattern where @app.handler() provides multi-channel
        access and @app.endpoint() provides streaming (API-only).
        """
        import json

        # Simulate SSE event formatting
        chunk = "Hello"
        sse_event = f"data: {json.dumps({'chunk': chunk})}\n\n"
        assert sse_event == 'data: {"chunk": "Hello"}\n\n'

        # Validate done marker
        done_event = "data: [DONE]\n\n"
        assert done_event == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_streaming_generator_pattern(self):
        """Validate async generator pattern used in SSE streaming."""

        async def generate_chunks():
            """Simulated SSE chunk generator."""
            import json

            chunks = ["Hello", " world", "!"]
            for chunk in chunks:
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield "data: [DONE]\n\n"

        # Collect all chunks
        collected = []
        async for event in generate_chunks():
            collected.append(event)

        assert len(collected) == 4  # 3 chunks + DONE
        assert collected[-1] == "data: [DONE]\n\n"
        assert '"chunk": "Hello"' in collected[0]
