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
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from openai import AsyncOpenAI

    from kaizen_agents.delegate.compact import CompactionResult
    from kaizen_agents.delegate.tools.hydrator import ToolHydrator

from kaizen_agents.delegate.adapters.openai_stream import StreamResult
from kaizen_agents.delegate.adapters.protocol import StreamingChatAdapter
from kaizen_agents.delegate.config.loader import KzConfig
from kaizen_agents.delegate.events import DelegateEvent, ToolCallEnd, ToolCallStart

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

    def add_assistant(
        self, content: str, tool_calls: list[dict[str, Any]] | None = None
    ) -> None:
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

    def compact(self, preserve_recent: int = 4) -> CompactionResult:
        """Compact the conversation by pruning older messages.

        Preserves the system message (always first), the last
        ``preserve_recent`` turn pairs, and replaces everything in between
        with a single summary message.

        Parameters
        ----------
        preserve_recent:
            Number of recent user/assistant turn pairs to keep verbatim.

        Returns
        -------
        :class:`~kaizen_agents.delegate.compact.CompactionResult` with
        before/after statistics.
        """
        from kaizen_agents.delegate.compact import compact_conversation

        return compact_conversation(self.messages, preserve_recent=preserve_recent)


# ---------------------------------------------------------------------------
# AgentLoop — the core loop
# ---------------------------------------------------------------------------


_DEFAULT_SYSTEM_PROMPT = """\
You are kz, a PACT-governed autonomous agent CLI. You help users accomplish \
tasks by using the tools available to you. Be direct and concise. When you \
need to take action, use tools. When you have the answer, respond with text.

If the active tool set is missing a tool you need, you may call \
``search_tools(query=...)`` to discover it. When you already know the tool \
name you want to reach, you can emit ``search_tools`` and the real tool call \
in the same tool-call batch — the framework will hydrate first then execute, \
saving a round-trip."""


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
        adapter: StreamingChatAdapter | None = None,
        system_prompt: str | None = None,
        budget_check: Callable[[], bool] | None = None,
        hydrator: ToolHydrator | None = None,
    ) -> None:
        """Initialise the agent loop.

        Parameters
        ----------
        config:
            Resolved kz configuration (model, tokens, turns, etc.).
        tools:
            Registry of tools available to the agent.
        client:
            Optional AsyncOpenAI client override (for testing / backward
            compat).  When provided, the loop wraps it in a legacy
            streaming path.  Prefer ``adapter`` for new code.
        adapter:
            A :class:`StreamingChatAdapter` instance for multi-provider
            support.  When provided, ``client`` is ignored.  If neither
            ``adapter`` nor ``client`` is provided, an adapter is created
            automatically from ``config.provider``.
        system_prompt:
            Override the default system prompt. If None, uses the built-in
            default. In production, this will be assembled from KZ.md context.
        budget_check:
            Optional callback that returns True if budget is available, False
            if exhausted. When provided, the loop checks budget before each
            LLM call and stops early if exhausted.
        hydrator:
            Optional :class:`~kaizen_agents.delegate.tools.hydrator.ToolHydrator`
            for large tool sets. When provided, the loop delegates tool
            selection and discovery to the hydrator. When ``None`` and the
            tool count exceeds the hydrator's default threshold, a hydrator
            is created automatically.
        """
        self._config = config
        self._tools = tools

        # Resolve the streaming adapter.
        # Priority: explicit adapter > explicit client (legacy) > auto-detect
        if adapter is not None:
            self._adapter: StreamingChatAdapter | None = adapter
            self._client: Any = None
        elif client is not None:
            # Legacy backward-compat path: wrap the raw AsyncOpenAI client
            self._adapter = None
            self._client = client
        else:
            self._adapter = self._build_adapter()
            self._client = None

        self._conversation = Conversation()
        self._usage = UsageTracker()
        self._interrupted = False
        self._budget_check = budget_check

        # Optional callback for tool-call lifecycle events.
        # When set, ToolCallStart/ToolCallEnd events are pushed to this
        # callback as they occur instead of only being stored on
        # ``_last_tool_events``.  Used by Delegate to yield events inline.
        self._event_callback: Callable[[DelegateEvent], None] | None = None

        # Tool hydration: set up when tool count exceeds threshold
        self._hydrator = hydrator
        self._setup_hydration()

        # Set system prompt
        prompt = system_prompt if system_prompt is not None else _DEFAULT_SYSTEM_PROMPT
        self._conversation.add_system(prompt)

    def _setup_hydration(self) -> None:
        """Initialise tool hydration if the tool count warrants it.

        When a hydrator is provided or the tool count exceeds the default
        threshold, the hydrator is loaded with the full tool set and the
        ``search_tools`` meta-tool is injected into the registry.
        """
        from kaizen_agents.delegate.tools.hydrator import ToolHydrator
        from kaizen_agents.delegate.tools.search import (
            SEARCH_TOOLS_SCHEMA,
            create_search_tools_executor,
        )

        tool_count = len(self._tools.tool_names)

        if self._hydrator is None:
            # Auto-create a hydrator only if the tool count exceeds the threshold
            default_threshold = ToolHydrator().threshold
            if tool_count <= default_threshold:
                return
            self._hydrator = ToolHydrator()

        # Register the search_tools meta-tool into the ToolRegistry so it
        # appears in the tool definitions sent to the LLM
        if not self._tools.has_tool("search_tools"):
            search_executor = create_search_tools_executor(self._hydrator)
            func_def = SEARCH_TOOLS_SCHEMA["function"]
            self._tools.register(
                name="search_tools",
                description=func_def["description"],
                parameters=func_def["parameters"],
                executor=search_executor,
            )

        # Load all tool defs and executors into the hydrator
        all_defs: dict[str, Any] = {}
        all_executors: dict[str, Any] = {}
        for tool_def in self._tools._tools.values():
            openai_fmt = tool_def.to_openai_format()
            all_defs[tool_def.name] = openai_fmt
            all_executors[tool_def.name] = self._tools._executors[tool_def.name]

        self._hydrator.load_tools(all_defs, all_executors)

    @property
    def hydrator(self) -> ToolHydrator | None:
        """The tool hydrator, if active."""
        return self._hydrator

    def _build_adapter(self) -> StreamingChatAdapter:
        """Build a streaming adapter from config.

        Provider selection is configuration branching (permitted deterministic
        logic), not agent reasoning.
        """
        from kaizen_agents.delegate.adapters.registry import get_adapter_for_model

        model = self._config.model or os.environ.get("DEFAULT_LLM_MODEL", "")
        return get_adapter_for_model(
            model=model,
            provider=self._config.provider,
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
        )

    def _build_client(self) -> Any:
        """Build an AsyncOpenAI client from environment variables (legacy).

        Kept for backward compatibility when ``client`` is passed directly.
        API key comes from .env (single source of truth).
        """
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "No OpenAI API key found. Set OPENAI_API_KEY in your .env file."
            )

        import httpx
        from openai import AsyncOpenAI

        base_url = os.environ.get("OPENAI_BASE_URL")
        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "timeout": httpx.Timeout(connect=10, read=120, write=30, pool=10),
        }
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

    async def run_turn(self, user_message: str) -> AsyncGenerator[str, None]:
        """Run one turn of the agent loop.

        A "turn" starts with a user message and continues until the model
        produces a text-only response (no tool calls) or max turns is reached.
        Yields text chunks incrementally.  Tool-call lifecycle events are
        stored on :attr:`last_tool_events` so higher-level wrappers (e.g.
        :class:`Delegate`) can forward them without polluting the text stream.

        Parameters
        ----------
        user_message:
            The user's input.

        Yields
        ------
        ``str``
            Text delta strings from the model's response.
        """
        self._interrupted = False
        self._last_tool_events: list[DelegateEvent] = []
        self._conversation.add_user(user_message)

        # Pre-hydrate the active tool set from the user's input (issue #579).
        # BM25 retrieval — not routing: the LLM still decides which tool to
        # call. This collapses the common-case 2-turn discovery tax to 0 by
        # letting the LLM see candidate tools on turn 1 instead of forcing
        # a dedicated ``search_tools`` meta-call.
        if self._hydrator is not None and self._hydrator.is_active:
            self._hydrator.pre_hydrate_from_query(user_message, top_k=5)

        inner_turns = 0

        while inner_turns < self._config.max_turns:
            if self._interrupted:
                return

            inner_turns += 1
            self._usage.increment_turn()

            # Check budget before making an LLM call
            if self._budget_check and not self._budget_check():
                logger.warning("Budget exhausted — stopping before LLM call")
                yield "[Budget exhausted — stopping.]"
                return

            # Stream the LLM response incrementally
            stream_result = StreamResult()
            has_tool_calls = False
            content_cursor = 0  # tracks how much text we have already yielded

            async for event_type, stream_result in self._stream_completion():
                if self._interrupted:
                    return

                if event_type == "text":
                    # Yield the new text delta (the portion we haven't yielded yet)
                    new_text = stream_result.content[content_cursor:]
                    if new_text:
                        yield new_text
                        content_cursor = len(stream_result.content)

                elif event_type == "tool_call_start":
                    has_tool_calls = True

            if self._interrupted:
                return

            # Track usage
            if stream_result.usage:
                self._usage.add(stream_result.usage)

            # If no tool calls, this turn is done -- the model chose to respond with text
            if not has_tool_calls:
                # Record the assistant message
                self._conversation.add_assistant(stream_result.content)
                return

            # Tool-call turn: record assistant message with tool calls, execute, loop back.
            # Any pre-tool-call text (reasoning/thinking) was already yielded above.
            self._conversation.add_assistant(
                stream_result.content,
                tool_calls=stream_result.tool_calls,
            )

            tool_events = await self._execute_tool_calls(stream_result.tool_calls)
            self._last_tool_events.extend(tool_events)
            if self._event_callback is not None:
                for event in tool_events:
                    self._event_callback(event)

        # Max turns reached -- we ran out of turns without a text-only response
        logger.warning("Max turns (%d) reached in run_turn", self._config.max_turns)

    @property
    def last_tool_events(self) -> list[DelegateEvent]:
        """Tool-call lifecycle events from the most recent :meth:`run_turn`.

        Returns a list of :class:`ToolCallStart` and :class:`ToolCallEnd`
        events.  The list is cleared at the start of each ``run_turn`` call.
        """
        return getattr(self, "_last_tool_events", [])

    async def _stream_completion(
        self,
    ) -> AsyncGenerator[tuple[str, StreamResult], None]:
        """Make a streaming completion request and yield events incrementally.

        Yields (event_type, stream_result) tuples as they arrive from the
        underlying streaming adapter (or legacy OpenAI client).

        The StreamResult is the SAME mutable object throughout -- it
        accumulates content, tool_calls, and usage as the stream progresses.

        Event types
        -----------
        ``"text"``
            A text chunk arrived. ``stream_result.content`` has the full text so far.
        ``"tool_call_start"``
            A new tool call started being streamed.
        ``"tool_call_delta"``
            Tool call arguments are being streamed.
        ``"done"``
            The stream completed.  ``stream_result`` is final.
        """
        # Use hydrator for tool selection when active, otherwise all tools
        if self._hydrator is not None and self._hydrator.is_active:
            tools = self._hydrator.get_active_tool_defs()
        else:
            tools = self._tools.get_openai_tools()

        model = self._config.model or os.environ.get("DEFAULT_LLM_MODEL", "")

        if self._adapter is not None:
            # New adapter-based path: provider-agnostic streaming
            async for event in self._adapter.stream_chat(
                messages=self._conversation.messages,
                tools=tools or None,
                model=model,
                temperature=self._config.temperature,
                max_tokens=self._config.max_tokens,
            ):
                if self._interrupted:
                    break

                # Convert StreamEvent -> (event_type, StreamResult) for
                # backward compatibility with the rest of the loop
                result = StreamResult(
                    content=event.content,
                    tool_calls=event.tool_calls,
                    finish_reason=event.finish_reason,
                    model=event.model,
                    usage=event.usage,
                )

                # Map adapter event types to legacy event types
                if event.event_type == "text_delta":
                    yield ("text", result)
                elif event.event_type == "tool_call_start":
                    yield ("tool_call_start", result)
                elif event.event_type == "tool_call_delta":
                    yield ("tool_call_delta", result)
                elif event.event_type == "done":
                    yield ("done", result)
        else:
            # Legacy path: direct AsyncOpenAI client (backward compat)
            from kaizen_agents.delegate.adapters.openai_stream import process_stream

            _GPT5_AND_REASONING = ("o1", "o3", "gpt-5")
            is_new_api = any(model.startswith(p) for p in _GPT5_AND_REASONING)

            kwargs: dict[str, Any] = {
                "model": model,
                "messages": self._conversation.messages,
                "stream": True,
                "stream_options": {"include_usage": True},
            }

            if not is_new_api:
                kwargs["temperature"] = self._config.temperature

            if is_new_api:
                kwargs["max_completion_tokens"] = self._config.max_tokens
            else:
                kwargs["max_tokens"] = self._config.max_tokens

            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            stream = await self._client.chat.completions.create(**kwargs)

            async for event_type, result in process_stream(stream):
                if self._interrupted:
                    break
                yield event_type, result

    async def _execute_tool_calls(
        self, tool_calls: list[dict[str, Any]]
    ) -> list[DelegateEvent]:
        """Execute tool calls from the model's response.

        Independent tool calls are executed in parallel. Results are
        appended to the conversation as tool messages. Returns a list of
        :class:`ToolCallStart` and :class:`ToolCallEnd` events for each
        tool call.

        Parameters
        ----------
        tool_calls:
            List of tool call dicts in OpenAI format.

        Returns
        -------
        List of ``ToolCallStart`` and ``ToolCallEnd`` events in order:
        all starts first, then all ends (matching ``tool_calls`` list order).
        """
        if not tool_calls:
            return []

        events: list[DelegateEvent] = []

        # Emit ToolCallStart for each tool before execution begins
        for tc in tool_calls:
            events.append(ToolCallStart(call_id=tc["id"], name=tc["function"]["name"]))

        async def _run_single(tc: dict[str, Any]) -> tuple[str, str, str]:
            """Execute a single tool call. Returns (tool_call_id, name, result)."""
            tc_id = tc["id"]
            func = tc["function"]
            name = func["name"]

            try:
                arguments = json.loads(func["arguments"]) if func["arguments"] else {}
            except json.JSONDecodeError:
                error_msg = f"Failed to parse arguments: {func['arguments'][:200]}"
                logger.warning(
                    "Tool call argument parse error for %s: %s", name, error_msg
                )
                return tc_id, name, json.dumps({"error": error_msg})

            try:
                # When hydration is active, the tool may have been just
                # hydrated by a search_tools call in this same batch of
                # tool calls. Use the hydrator's force-lookup which
                # bypasses the active-set check.
                if self._hydrator is not None and self._hydrator.is_active:
                    executor = self._hydrator.get_executor_force(name)
                    if executor is None:
                        raise KeyError(f"Unknown tool: {name}")
                    result = await executor(**arguments)
                else:
                    result = await self._tools.execute(name, arguments)
                return tc_id, name, result
            except KeyError:
                error_msg = f"Unknown tool: {name}"
                logger.warning(error_msg)
                return tc_id, name, json.dumps({"error": error_msg})
            except Exception as exc:
                logger.error("Tool %s failed: %s", name, exc, exc_info=True)
                safe_msg = f"Tool '{name}' failed with {type(exc).__name__}"
                return tc_id, name, json.dumps({"error": safe_msg})

        # Execute all tool calls in parallel
        tasks = [_run_single(tc) for tc in tool_calls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for idx, result in enumerate(results):
            if isinstance(result, BaseException):
                # Inject a synthetic error result so the conversation stays valid.
                # The model sent tool_calls but needs matching tool results for
                # every call — missing results cause API errors on the next turn.
                logger.error("Unexpected error in parallel tool execution: %s", result)
                tc = tool_calls[idx]
                tc_id = tc["id"]
                tc_name = tc["function"]["name"]
                self._conversation.add_tool_result(
                    tc_id,
                    tc_name,
                    json.dumps({"error": "Tool execution was interrupted"}),
                )
                events.append(
                    ToolCallEnd(
                        call_id=tc_id,
                        name=tc_name,
                        error="Tool execution was interrupted",
                    )
                )
                continue

            tc_id, name, content = result
            self._conversation.add_tool_result(tc_id, name, content)
            events.append(ToolCallEnd(call_id=tc_id, name=name, result=content))

        return events

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

        display.show_welcome(self._config.model or "gpt-5-chat-latest")

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
                        if not isinstance(chunk, str):
                            continue
                        display.append_text(chunk)
                        full_text += chunk

                    display.finish_streaming()

                except Exception as exc:
                    display.finish_streaming()
                    display.show_error(f"Turn failed ({type(exc).__name__})")
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
            if not isinstance(chunk, str):
                continue
            full_text += chunk
        return full_text
