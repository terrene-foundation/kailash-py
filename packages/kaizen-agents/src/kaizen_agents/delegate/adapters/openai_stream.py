"""Streaming handler for OpenAI chat completion responses.

Processes the SSE stream from the OpenAI API, yielding text chunks
and collecting tool calls as they arrive. The model drives the loop --
this module does not impose any structure on the model's output.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from openai import AsyncStream
from openai.types.chat import ChatCompletionChunk

logger = logging.getLogger(__name__)


@dataclass
class ToolCallAccumulator:
    """Accumulates a single tool call from streamed deltas.

    OpenAI streams tool calls as incremental deltas: the first delta
    carries the id, type, and function name; subsequent deltas append
    to the arguments string.
    """

    id: str = ""
    type: str = "function"
    name: str = ""
    arguments: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to the OpenAI tool call format used by the rest of the system."""
        return {
            "id": self.id,
            "type": self.type,
            "function": {
                "name": self.name,
                "arguments": self.arguments,
            },
        }

    def parsed_arguments(self) -> dict[str, Any]:
        """Parse the accumulated arguments JSON string.

        Returns an empty dict if parsing fails (the model may have
        produced malformed JSON).
        """
        if not self.arguments:
            return {}
        try:
            return json.loads(self.arguments)
        except json.JSONDecodeError:
            logger.warning("Failed to parse tool call arguments: %s", self.arguments[:200])
            return {}


@dataclass
class StreamResult:
    """The full result of processing a streamed response.

    Populated incrementally as chunks arrive. After the stream completes,
    this contains the complete assistant message content and any tool calls.
    """

    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)


async def process_stream(
    stream: AsyncStream[ChatCompletionChunk],
) -> AsyncIterator[tuple[str, StreamResult]]:
    """Process an OpenAI streaming response, yielding text chunks as they arrive.

    Yields tuples of (event_type, stream_result) where:
    - ("text", result): A text chunk arrived. result.content has the full text so far.
    - ("tool_call_start", result): A new tool call started.
    - ("tool_call_delta", result): Tool call arguments are being streamed.
    - ("done", result): Stream completed. result has final content, tool_calls, usage.

    The StreamResult is the SAME object throughout -- it is mutated as the stream
    progresses. Callers who need snapshots should copy.

    Parameters
    ----------
    stream:
        An async stream from openai.AsyncOpenAI().chat.completions.create(stream=True).

    Yields
    ------
    (event_type, stream_result) tuples.
    """
    result = StreamResult()
    tool_accumulators: dict[int, ToolCallAccumulator] = {}

    async for chunk in stream:
        if not chunk.choices:
            # Usage-only chunk (some models send this at the end)
            if chunk.usage:
                result.usage = {
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                    "total_tokens": chunk.usage.total_tokens,
                }
            continue

        if chunk.model:
            result.model = chunk.model

        choice = chunk.choices[0]
        delta = choice.delta

        # Text content
        if delta.content:
            result.content += delta.content
            yield ("text", result)

        # Tool calls (streamed as deltas)
        if delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index

                if idx not in tool_accumulators:
                    # New tool call starting
                    acc = ToolCallAccumulator()
                    tool_accumulators[idx] = acc

                    if tc_delta.id:
                        acc.id = tc_delta.id
                    if tc_delta.type:
                        acc.type = tc_delta.type
                    if tc_delta.function and tc_delta.function.name:
                        acc.name = tc_delta.function.name
                    if tc_delta.function and tc_delta.function.arguments:
                        acc.arguments += tc_delta.function.arguments

                    yield ("tool_call_start", result)
                else:
                    # Continuing an existing tool call (appending arguments)
                    acc = tool_accumulators[idx]
                    if tc_delta.function and tc_delta.function.arguments:
                        acc.arguments += tc_delta.function.arguments
                    yield ("tool_call_delta", result)

        # Finish reason
        if choice.finish_reason:
            result.finish_reason = choice.finish_reason

    # Finalize tool calls
    for idx in sorted(tool_accumulators.keys()):
        result.tool_calls.append(tool_accumulators[idx].to_dict())

    yield ("done", result)
