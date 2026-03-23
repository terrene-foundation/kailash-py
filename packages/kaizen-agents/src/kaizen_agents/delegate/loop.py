"""Core agent loop for kz CLI.

The autonomous model-driven loop: the model decides what to do, tool
calling is native, there is no structured thought extraction. This
module implements the loop described in the architecture spec:

    LOOP:
      1. Assemble prompt (system + context + conversation + tool defs)
      2. Stream LLM response
      3. If tool calls -> execute tools (parallel for independent) -> append -> loop
      4. If text only -> yield to user
      5. Repeat until user exits

Architectural invariant: the kz core loop MUST NOT use Kaizen Pipeline
primitives. Pipelines are for user-space application construction, not
core orchestration.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Awaitable

from openai import AsyncOpenAI

from kaizen_agents.delegate.adapters.openai_stream import StreamResult, process_stream
from kaizen_agents.delegate.config.loader import KzConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool registry protocol
# ---------------------------------------------------------------------------


@dataclass
class ToolDef:
    """A single tool definition in OpenAI function-calling format."""

    name: str
    description: str
    parameters: dict[str, Any]

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to the dict format expected by the OpenAI API."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Registry of tools available to the agent.

    Tools are registered with a name, schema, and async executor function.
    The loop queries the registry for OpenAI-format definitions and dispatches
    tool calls through it.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}
        self._executors: dict[str, Callable[..., Awaitable[str]]] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        executor: Callable[..., Awaitable[str]],
    ) -> None:
        """Register a tool.

        Parameters
        ----------
        name:
            Unique tool name (used in function calling).
        description:
            Human-readable description for the model.
        parameters:
            JSON Schema for the tool's parameters.
        executor:
            Async callable that executes the tool. Receives keyword arguments
            matching the schema. Returns a string result.
        """
        self._tools[name] = ToolDef(
            name=name,
            description=description,
            parameters=parameters,
        )
        self._executors[name] = executor

    def get_openai_tools(self) -> list[dict[str, Any]]:
        """Return all tools in OpenAI function-calling format."""
        return [tool.to_openai_format() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool by name with the given arguments.

        Parameters
        ----------
        name:
            The tool name.
        arguments:
            Keyword arguments parsed from the model's tool call.

        Returns
        -------
        The tool's string result.

        Raises
        ------
        KeyError:
            If the tool name is not registered.
        """
        if name not in self._executors:
            raise KeyError(f"Unknown tool: {name}")
        return await self._executors[name](**arguments)

    def has_tool(self, name: str) -> bool:
        """Check whether a tool is registered."""
        return name in self._tools

    @property
    def tool_names(self) -> list[str]:
        """List of registered tool names."""
        return list(self._tools.keys())


# ---------------------------------------------------------------------------
# Token / cost tracking
# ---------------------------------------------------------------------------


@dataclass
class UsageTracker:
    """Tracks cumulative token usage and cost across a session."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    turns: int = 0

    def add(self, usage: dict[str, int]) -> None:
        """Add a usage dict from a single completion."""
        self.prompt_tokens += usage.get("prompt_tokens", 0)
        self.completion_tokens += usage.get("completion_tokens", 0)
        self.total_tokens += usage.get("total_tokens", 0)

    def increment_turn(self) -> None:
        """Increment the turn counter."""
        self.turns += 1


# ---------------------------------------------------------------------------
# Conversation history
# ---------------------------------------------------------------------------


@dataclass
class Conversation:
    """Manages the conversation message history.

    The conversation is a flat list of messages in OpenAI format. The loop
    appends user, assistant, and tool messages as the conversation progresses.
    """

    messages: list[dict[str, Any]] = field(default_factory=list)

    def add_system(self, content: str) -> None:
        """Set or replace the system message."""
        # Remove existing system message if any
        self.messages = [m for m in self.messages if m.get("role") != "system"]
        if content:
            self.messages.insert(0, {"role": "system", "content": content})

    def add_user(self, content: str) -> None:
        """Append a user message."""
        self.messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str, tool_calls: list[dict[str, Any]] | None = None) -> None:
        """Append an assistant message, optionally with tool calls."""
        msg: dict[str, Any] = {"role": "assistant"}
        if content:
            msg["content"] = content
        if tool_calls:
            msg["tool_calls"] = tool_calls
        # OpenAI requires either content or tool_calls (or both)
        if not content and not tool_calls:
            msg["content"] = ""
        self.messages.append(msg)

    def add_tool_result(self, tool_call_id: str, name: str, content: str) -> None:
        """Append a tool result message."""
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": name,
                "content": content,
            }
        )


# ---------------------------------------------------------------------------
# AgentLoop — the core loop
# ---------------------------------------------------------------------------


_DEFAULT_SYSTEM_PROMPT = """\
You are kz, a PACT-governed autonomous agent CLI. You help users accomplish \
tasks by using the tools available to you. Be direct and concise. When you \
need to take action, use tools. When you have the answer, respond with text."""


class AgentLoop:
    """The autonomous agent loop that drives kz interactive sessions.

    The model decides what to do. Tool calling is native. No structured
    thought extraction. The loop simply:
    1. Assembles the prompt (system + conversation + tool defs)
    2. Streams the LLM response
    3. If tool calls: executes them (parallel for independent), appends results, loops
    4. If text only: returns the text to the caller
    5. Repeats until the user exits or max turns is reached

    Usage::

        loop = AgentLoop(config=my_config, tools=my_registry)
        async for chunk in loop.run_turn("What files are in this directory?"):
            print(chunk, end="")

    Or for interactive mode::

        await loop.run_interactive()
    """

    def __init__(
        self,
        config: KzConfig,
        tools: ToolRegistry,
        *,
        client: AsyncOpenAI | None = None,
        system_prompt: str | None = None,
    ) -> None:
        """Initialise the agent loop.

        Parameters
        ----------
        config:
            Resolved kz configuration (model, tokens, turns, etc.).
        tools:
            Registry of tools available to the agent.
        client:
            Optional AsyncOpenAI client override (for testing).
        system_prompt:
            Override the default system prompt. If None, uses the built-in
            default. In production, this will be assembled from KZ.md context.
        """
        self._config = config
        self._tools = tools
        self._client = client or self._build_client()
        self._conversation = Conversation()
        self._usage = UsageTracker()
        self._interrupted = False

        # Set system prompt
        prompt = system_prompt if system_prompt is not None else _DEFAULT_SYSTEM_PROMPT
        self._conversation.add_system(prompt)

    def _build_client(self) -> AsyncOpenAI:
        """Build an AsyncOpenAI client from environment variables.

        API key comes from .env (single source of truth).
        """
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("No OpenAI API key found. Set OPENAI_API_KEY in your .env file.")

        base_url = os.environ.get("OPENAI_BASE_URL")
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        return AsyncOpenAI(**kwargs)

    @property
    def usage(self) -> UsageTracker:
        """Current session usage statistics."""
        return self._usage

    @property
    def conversation(self) -> Conversation:
        """The conversation history."""
        return self._conversation

    def interrupt(self) -> None:
        """Signal the loop to stop after the current operation."""
        self._interrupted = True

    async def run_turn(self, user_message: str) -> AsyncIterator[str]:
        """Run one turn of the agent loop.

        A "turn" starts with a user message and continues until the model
        produces a text-only response (no tool calls) or max turns is reached.
        Yields text chunks as they stream from the model.

        Parameters
        ----------
        user_message:
            The user's input.

        Yields
        ------
        Text chunks from the model's response, as they stream.
        """
        self._interrupted = False
        self._conversation.add_user(user_message)

        inner_turns = 0

        while inner_turns < self._config.max_turns:
            if self._interrupted:
                return

            inner_turns += 1
            self._usage.increment_turn()

            # Stream the LLM response
            stream_result = await self._stream_completion()

            if self._interrupted:
                return

            # Yield any text content
            if stream_result.content:
                yield stream_result.content

            # Track usage
            if stream_result.usage:
                self._usage.add(stream_result.usage)

            # If no tool calls, this turn is done -- the model chose to respond with text
            if not stream_result.tool_calls:
                # Record the assistant message
                self._conversation.add_assistant(stream_result.content)
                return

            # Tool calls: record assistant message with tool calls, execute, loop back
            self._conversation.add_assistant(
                stream_result.content,
                tool_calls=stream_result.tool_calls,
            )

            await self._execute_tool_calls(stream_result.tool_calls)

        # Max turns reached -- we ran out of turns without a text-only response
        logger.warning("Max turns (%d) reached in run_turn", self._config.max_turns)

    async def _stream_completion(self) -> StreamResult:
        """Make a streaming completion request and collect the result.

        Returns the fully assembled StreamResult after the stream completes.
        """
        tools = self._tools.get_openai_tools()

        kwargs: dict[str, Any] = {
            "model": self._config.model or "gpt-4o",
            "messages": self._conversation.messages,
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        stream = await self._client.chat.completions.create(**kwargs)

        result = StreamResult()
        async for _event_type, result in process_stream(stream):
            if self._interrupted:
                break

        return result

    async def _execute_tool_calls(self, tool_calls: list[dict[str, Any]]) -> None:
        """Execute tool calls from the model's response.

        Independent tool calls are executed in parallel. Results are
        appended to the conversation as tool messages.

        Parameters
        ----------
        tool_calls:
            List of tool call dicts in OpenAI format.
        """
        if not tool_calls:
            return

        async def _run_single(tc: dict[str, Any]) -> tuple[str, str, str]:
            """Execute a single tool call. Returns (tool_call_id, name, result)."""
            tc_id = tc["id"]
            func = tc["function"]
            name = func["name"]

            try:
                arguments = json.loads(func["arguments"]) if func["arguments"] else {}
            except json.JSONDecodeError:
                error_msg = f"Failed to parse arguments: {func['arguments'][:200]}"
                logger.warning("Tool call argument parse error for %s: %s", name, error_msg)
                return tc_id, name, json.dumps({"error": error_msg})

            try:
                result = await self._tools.execute(name, arguments)
                return tc_id, name, result
            except KeyError:
                error_msg = f"Unknown tool: {name}"
                logger.warning(error_msg)
                return tc_id, name, json.dumps({"error": error_msg})
            except Exception as exc:
                error_msg = f"Tool execution error: {exc}"
                logger.error("Tool %s failed: %s", name, exc, exc_info=True)
                return tc_id, name, json.dumps({"error": error_msg})

        # Execute all tool calls in parallel
        tasks = [_run_single(tc) for tc in tool_calls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, BaseException):
                # This should not happen since _run_single catches exceptions,
                # but handle it defensively.
                logger.error("Unexpected error in parallel tool execution: %s", result)
                continue

            tc_id, name, content = result
            self._conversation.add_tool_result(tc_id, name, content)

    async def run_interactive(
        self,
        *,
        display: Any = None,
    ) -> None:
        """Run the interactive prompt loop.

        Prompts the user for input, runs turns, displays results, and
        repeats until the user exits (Ctrl+C or Ctrl+D).

        Parameters
        ----------
        display:
            A Display instance for terminal output. If None, creates one.
        """
        # Import here to avoid circular imports and keep display optional
        from kaizen_agents.delegate.display import Display  # type: ignore[import]

        if display is None:
            display = Display()

        display.show_welcome(self._config.model or "gpt-4o")

        while True:
            try:
                user_input = display.get_user_input()
                if user_input is None:
                    # EOF (Ctrl+D)
                    break

                user_input = user_input.strip()
                if not user_input:
                    continue

                if user_input.lower() in ("exit", "quit"):
                    break

                # Run the turn with streaming display
                display.start_streaming()

                try:
                    full_text = ""
                    async for chunk in self.run_turn(user_input):
                        display.append_text(chunk)
                        full_text += chunk

                    display.finish_streaming()

                except Exception as exc:
                    display.finish_streaming()
                    display.show_error(str(exc))
                    logger.error("Turn failed: %s", exc, exc_info=True)

            except KeyboardInterrupt:
                self.interrupt()
                display.show_interrupt()
                # Reset interrupted flag for next turn
                self._interrupted = False
                continue

        # Show session summary
        display.show_cost_summary(
            total_tokens=self._usage.total_tokens,
            prompt_tokens=self._usage.prompt_tokens,
            completion_tokens=self._usage.completion_tokens,
            turns=self._usage.turns,
        )

    async def run_print(self, prompt: str) -> str:
        """Run a single prompt in non-interactive (print) mode.

        Returns the complete text response.

        Parameters
        ----------
        prompt:
            The user's prompt.

        Returns
        -------
        The complete assistant response text.
        """
        full_text = ""
        async for chunk in self.run_turn(prompt):
            full_text += chunk
        return full_text
