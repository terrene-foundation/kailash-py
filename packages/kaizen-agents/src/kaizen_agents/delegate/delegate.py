# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Delegate facade -- the single entry point for autonomous AI execution.

Composes a wrapper stack (SPEC-05) instead of containing parallel
implementation.  Internally constructs:

    AgentLoop (via _LoopAgent) -> [L3GovernedAgent] -> [MonitoredAgent]

Only wrappers whose parameters are supplied are stacked.

The user-facing API is byte-identical to v2.x:

Layer 1 (simple)::

    delegate = Delegate(model="claude-sonnet-4-20250514")
    async for event in delegate.run("what files are here?"):
        print(event)

Layer 2 (configured)::

    delegate = Delegate(
        model="claude-sonnet-4-20250514",
        tools=["read_file", "grep", "bash"],
        system_prompt="You are a code reviewer.",
    )

Layer 3 (governed)::

    delegate = Delegate(
        model="claude-sonnet-4-20250514",
        budget_usd=10.0,
    )
    # Budget tracking is automatic; yields BudgetExhausted when exceeded.

The ``run()`` method yields typed :class:`DelegateEvent` instances,
giving consumers structured data to pattern-match on rather than raw
strings.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
from collections.abc import AsyncGenerator, Callable
from typing import TYPE_CHECKING, Any

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import InputField, OutputField, Signature
from kaizen_agents.delegate.config.loader import KzConfig
from kaizen_agents.delegate.events import (
    BudgetExhausted,
    DelegateEvent,
    ErrorEvent,
    TextDelta,
    TurnComplete,
)
from kaizen_agents.delegate.loop import AgentLoop, ToolRegistry

if TYPE_CHECKING:
    from kailash.trust.envelope import ConstraintEnvelope
    from kaizen_agents.delegate.adapters.protocol import StreamingChatAdapter
    from kaizen_agents.governed_agent import L3GovernedAgent
    from kaizen_agents.monitored_agent import MonitoredAgent

logger = logging.getLogger(__name__)

__all__ = ["Delegate", "ConstructorIOError", "ToolRegistryCollisionError"]


# ---------------------------------------------------------------------------
# Exceptions (SPEC-05 SS9.1, SS9.3)
# ---------------------------------------------------------------------------


class ConstructorIOError(RuntimeError):
    """Raised when an outbound IO call is detected inside Delegate.__init__.

    The Delegate constructor MUST be synchronous and free of any network,
    filesystem, or subprocess calls.  MCP server discovery is deferred to
    the first ``run()`` call via ``_ensure_mcp_configured()``.

    See SPEC-05 SS9.1 for the full constructor security model.
    """

    def __init__(self, operation: str) -> None:
        self.operation = operation
        super().__init__(
            f"Outbound IO detected in Delegate constructor: {operation}. "
            f"IO is banned in __init__ to prevent deadlocks and credential "
            f"leaks during construction. Use the deferred MCP pattern: pass "
            f"mcp_servers= and let run() trigger discovery. "
            f"See SPEC-05 SS9.1."
        )


class ToolRegistryCollisionError(ValueError):
    """Raised when two tools with the same name are registered.

    Attributes:
        tool_name: The colliding tool name.
        sources: The source identifiers that both registered the name.
    """

    def __init__(self, tool_name: str, sources: list[str]) -> None:
        self.tool_name = tool_name
        self.sources = sources
        super().__init__(
            f"Tool name collision: '{tool_name}' is registered by multiple "
            f"sources: {sources}. Use distinct tool names or namespaced "
            f"server names to avoid collisions."
        )


# ---------------------------------------------------------------------------
# Cost model constants (conservative estimates per 1M tokens)
# ---------------------------------------------------------------------------

_COST_PER_1M_INPUT: dict[str, float] = {
    "claude-": 3.0,
    "gpt-4o": 2.5,
    "gpt-4": 30.0,
    "gpt-5": 10.0,
    "o1": 15.0,
    "o3": 12.0,
    "o4": 12.0,
    "gemini-": 1.25,
}

_COST_PER_1M_OUTPUT: dict[str, float] = {
    "claude-": 15.0,
    "gpt-4o": 10.0,
    "gpt-4": 60.0,
    "gpt-5": 30.0,
    "o1": 60.0,
    "o3": 48.0,
    "o4": 48.0,
    "gemini-": 5.0,
}


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost for a completion based on model prefix heuristics.

    This is configuration-level cost estimation (permitted deterministic
    logic), not agent decision-making.  The costs are approximate and
    used only for budget tracking -- not for routing or classification.
    """
    input_rate = 3.0  # default
    output_rate = 15.0

    for prefix, rate in _COST_PER_1M_INPUT.items():
        if model.startswith(prefix):
            input_rate = rate
            break

    for prefix, rate in _COST_PER_1M_OUTPUT.items():
        if model.startswith(prefix):
            output_rate = rate
            break

    cost = (prompt_tokens / 1_000_000) * input_rate + (
        completion_tokens / 1_000_000
    ) * output_rate
    return cost


# ---------------------------------------------------------------------------
# _LoopAgent -- BaseAgent bridge for AgentLoop
# ---------------------------------------------------------------------------


class _DelegateSignature(Signature):
    """Minimal signature for the LoopAgent bridge.

    The Delegate's AgentLoop drives its own prompt/response cycle, so
    this signature is a placeholder that satisfies the BaseAgent contract
    without interfering with execution.
    """

    prompt: str = InputField(description="User prompt")
    response: str = OutputField(description="Agent response")


class _LoopAgent(BaseAgent):
    """Bridge that wraps :class:`AgentLoop` into the :class:`BaseAgent` interface.

    This adapter allows the ``AgentLoop`` (which has its own streaming
    interface) to participate in the SPEC-03 wrapper stack.  The wrappers
    call ``run_async()`` which collects the full loop turn into a result
    dict.  The Delegate's ``run()`` method bypasses this and streams
    from the loop directly for incremental output.
    """

    def __init__(self, loop: AgentLoop, model: str) -> None:
        # Create a minimal BaseAgentConfig for the BaseAgent contract
        config = BaseAgentConfig(
            llm_provider="mock",  # Not used -- loop has its own adapter
            model=model,
        )
        super().__init__(config=config, signature=_DelegateSignature())
        self._loop = loop

    @property
    def loop(self) -> AgentLoop:
        """The underlying AgentLoop."""
        return self._loop

    def run(self, **inputs: Any) -> dict[str, Any]:
        """Synchronous execution -- collects loop turn into a result dict."""
        prompt = inputs.get("prompt", "")

        async def _collect() -> str:
            parts: list[str] = []
            async for chunk in self._loop.run_turn(prompt):
                if isinstance(chunk, str):
                    parts.append(chunk)
            return "".join(parts)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _collect())
                text = future.result()
        else:
            text = asyncio.run(_collect())

        usage = self._loop.usage
        return {
            "text": text,
            "usage": {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            },
        }

    async def run_async(self, **inputs: Any) -> dict[str, Any]:
        """Async execution -- collects loop turn into a result dict."""
        prompt = inputs.get("prompt", "")
        parts: list[str] = []
        async for chunk in self._loop.run_turn(prompt):
            if isinstance(chunk, str):
                parts.append(chunk)
        text = "".join(parts)
        usage = self._loop.usage
        return {
            "text": text,
            "usage": {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            },
        }


# ---------------------------------------------------------------------------
# Delegate -- composition facade
# ---------------------------------------------------------------------------


class Delegate:
    """Facade composing a wrapper stack for autonomous AI execution.

    Internally constructs:

        AgentLoop (via _LoopAgent) -> [L3GovernedAgent] -> [MonitoredAgent]

    Only wrappers whose parameters are supplied are stacked.  The ``run()``
    method drives the ``AgentLoop`` directly for streaming, using the wrapper
    stack for governance validation and cost tracking.

    Progressive disclosure layers:

    **Layer 1** -- minimal::

        d = Delegate(model="claude-sonnet-4-20250514")

    **Layer 2** -- configured::

        d = Delegate(
            model="claude-sonnet-4-20250514",
            tools=["read_file", "grep"],
            system_prompt="You are a code reviewer.",
            max_turns=20,
        )

    **Layer 3** -- governed::

        d = Delegate(
            model="claude-sonnet-4-20250514",
            budget_usd=10.0,
        )

    Parameters
    ----------
    model:
        LLM model name (e.g., ``"claude-sonnet-4-20250514"``).
        Falls back to ``DEFAULT_LLM_MODEL`` env var if empty.
    signature:
        Optional Signature class for structured I/O.  When provided,
        enables structured outputs on the inner BaseAgent.
    tools:
        List of tool names or a pre-built :class:`ToolRegistry`.
        When a list of strings is given, the Delegate creates an empty
        registry (tools must be registered separately).
    system_prompt:
        Override the default system prompt.
    temperature:
        Optional LLM temperature override.
    max_tokens:
        Optional max completion tokens override.
    max_turns:
        Maximum tool-calling loops per ``run()`` call.
    mcp_servers:
        Optional list of MCP server configurations.  Discovery is
        deferred to the first ``run()`` call (no IO in constructor).
    budget_usd:
        Optional USD budget cap.  When set, the Delegate tracks
        estimated cost per turn and yields :class:`BudgetExhausted`
        when the budget is exceeded.
    envelope:
        Optional :class:`ConstraintEnvelope` for L3 governance.
        When provided, wraps the inner agent with :class:`L3GovernedAgent`.
    api_key:
        Optional API key for the LLM provider.  Read from env if not set.
    base_url:
        Optional base URL override for the LLM provider endpoint.
    inner_agent:
        Optional pre-built :class:`BaseAgent` escape hatch.  When provided,
        the Delegate wraps this agent directly instead of constructing one.
    adapter:
        Optional pre-built :class:`StreamingChatAdapter`.
    config:
        Optional pre-built :class:`KzConfig`.  When provided, ``model``,
        ``max_turns``, and other config fields are ignored.
    """

    def __init__(
        self,
        model: str = "",
        *,
        signature: type[Signature] | None = None,
        tools: ToolRegistry | list[str] | None = None,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_turns: int = 50,
        mcp_servers: list[dict[str, Any]] | None = None,
        budget_usd: float | None = None,
        envelope: ConstraintEnvelope | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        inner_agent: BaseAgent | None = None,
        adapter: StreamingChatAdapter | None = None,
        config: KzConfig | None = None,
    ) -> None:
        # Validate budget (safety guard -- permitted deterministic logic)
        if budget_usd is not None:
            if not math.isfinite(budget_usd):
                raise ValueError("budget_usd must be finite")
            if budget_usd < 0:
                raise ValueError("budget_usd must be non-negative")

        # Store new parameters for wrapper/introspection access
        self._signature = signature
        self._api_key = api_key
        self._base_url = base_url
        self._inner_agent = inner_agent

        # Deferred MCP configuration -- no IO in constructor (SPEC-05 SS9.1)
        self._deferred_mcp = list(mcp_servers) if mcp_servers else None
        self._mcp_configured = False

        # Resolve model from env if not provided
        resolved_model = model or os.environ.get("DEFAULT_LLM_MODEL", "")

        # Build config
        if config is not None:
            self._config = config
        else:
            self._config = KzConfig(
                model=resolved_model,
                max_turns=max_turns,
            )

        # Build tool registry
        if isinstance(tools, ToolRegistry):
            self._tool_registry = tools
        else:
            self._tool_registry = ToolRegistry()

        # Budget tracking
        self._budget_usd = budget_usd
        self._consumed_usd: float = 0.0

        # Build the budget check callback for the loop
        budget_check: Callable[[], bool] | None = None
        if budget_usd is not None:
            budget_check = self._check_budget

        # Create the core loop (the execution engine)
        self._loop = AgentLoop(
            config=self._config,
            tools=self._tool_registry,
            adapter=adapter,
            system_prompt=system_prompt,
            budget_check=budget_check,
        )

        # ---- SPEC-05: Compose wrapper stack ----
        # Build the BaseAgent-compatible bridge
        self._loop_agent: BaseAgent = _LoopAgent(self._loop, resolved_model)

        # Stack L3GovernedAgent if envelope provided
        self._governed: L3GovernedAgent | None = None
        if envelope is not None:
            try:
                from kaizen_agents.governed_agent import L3GovernedAgent as _Gov

                self._governed = _Gov(self._loop_agent, envelope=envelope)
                self._loop_agent = self._governed
            except ImportError:
                logger.debug(
                    "L3GovernedAgent unavailable (missing trust.envelope); "
                    "envelope parameter ignored"
                )

        # Stack MonitoredAgent if budget provided and the wrapper is available.
        # When kaizen.providers.cost is not installed, the Delegate's own
        # budget tracking (_consumed_usd / _estimate_cost) handles budget
        # enforcement directly.
        self._monitored: MonitoredAgent | None = None
        if budget_usd is not None:
            try:
                from kaizen_agents.monitored_agent import MonitoredAgent as _Mon

                self._monitored = _Mon(
                    self._loop_agent,
                    budget_usd=budget_usd,
                    model=resolved_model,
                )
                self._loop_agent = self._monitored
            except ImportError:
                logger.debug(
                    "MonitoredAgent unavailable (missing kaizen.providers.cost); "
                    "using Delegate-level budget tracking"
                )

        self._closed = False

    def _check_budget(self) -> bool:
        """Return True if budget is still available, False if exhausted.

        This is a safety guard (permitted deterministic logic), not
        agent decision-making.
        """
        if self._budget_usd is None:
            return True
        return self._consumed_usd < self._budget_usd

    def _record_usage(self, usage: dict[str, int]) -> None:
        """Record token usage and update cost estimate."""
        if not usage:
            return
        model = self._config.model or ""
        prompt = usage.get("prompt_tokens", 0)
        completion = usage.get("completion_tokens", 0)
        cost = _estimate_cost(model, prompt, completion)
        self._consumed_usd += cost

    @property
    def loop(self) -> AgentLoop:
        """The underlying AgentLoop (Layer 3 access)."""
        return self._loop

    @property
    def tool_registry(self) -> ToolRegistry:
        """The tool registry."""
        return self._tool_registry

    @property
    def budget_usd(self) -> float | None:
        """The configured budget cap, or None if no budget set."""
        return self._budget_usd

    @property
    def consumed_usd(self) -> float:
        """Estimated USD consumed so far."""
        return self._consumed_usd

    @property
    def budget_remaining(self) -> float | None:
        """Estimated USD remaining, or None if no budget set."""
        if self._budget_usd is None:
            return None
        return max(0.0, self._budget_usd - self._consumed_usd)

    @property
    def wrapper_stack(self) -> BaseAgent:
        """The outermost agent in the wrapper stack (Layer 3 access).

        This is the composed wrapper stack:
        ``_LoopAgent -> [L3GovernedAgent] -> [MonitoredAgent]``
        """
        return self._loop_agent

    async def run(self, prompt: str) -> AsyncGenerator[DelegateEvent, None]:
        """Run the Delegate on a user prompt, yielding typed events.

        This is the primary entry point.  It wraps ``AgentLoop.run_turn()``
        and converts raw string chunks into structured :class:`DelegateEvent`
        instances.

        Parameters
        ----------
        prompt:
            The user's input.

        Yields
        ------
        :class:`DelegateEvent` subclass instances:

        - :class:`TextDelta` -- incremental text from the model
        - :class:`ToolCallStart` -- a tool call has begun
        - :class:`ToolCallEnd` -- a tool call has completed
        - :class:`TurnComplete` -- the model finished responding
        - :class:`BudgetExhausted` -- budget cap exceeded
        - :class:`ErrorEvent` -- an error occurred
        """
        if self._closed:
            yield ErrorEvent(error="Delegate has been closed")
            return

        if not prompt:
            yield ErrorEvent(error="Empty prompt")
            return

        # Check budget before starting
        if self._budget_usd is not None and self._consumed_usd >= self._budget_usd:
            yield BudgetExhausted(
                budget_usd=self._budget_usd,
                consumed_usd=self._consumed_usd,
            )
            return

        # If MonitoredAgent is in the stack, let it validate budget too
        if self._monitored is not None:
            from kaizen_agents.monitored_agent import BudgetExhaustedError

            try:
                self._monitored._check_budget()
            except BudgetExhaustedError as exc:
                yield BudgetExhausted(
                    budget_usd=exc.budget_usd,
                    consumed_usd=exc.consumed_usd,
                )
                return

        accumulated_text = ""

        # Buffer for tool-call lifecycle events.  The loop invokes our
        # callback synchronously inside ``_execute_tool_calls``; we drain
        # the buffer after each text chunk so events appear at the correct
        # point in the stream (between tool execution and the next LLM turn).
        _pending_events: list[DelegateEvent] = []
        self._loop._event_callback = _pending_events.append

        try:
            async for chunk in self._loop.run_turn(prompt):
                # Drain any tool-call events that accumulated before this
                # text chunk (they were pushed by _execute_tool_calls).
                while _pending_events:
                    yield _pending_events.pop(0)

                # Check if this is the budget-exhausted sentinel
                if chunk == "[Budget exhausted — stopping.]":
                    yield BudgetExhausted(
                        budget_usd=self._budget_usd or 0.0,
                        consumed_usd=self._consumed_usd,
                    )
                    return

                accumulated_text += chunk
                yield TextDelta(text=chunk)

            # Drain any remaining events (e.g. from the last tool-call turn
            # when there was no subsequent text chunk).
            while _pending_events:
                yield _pending_events.pop(0)

        except Exception as exc:
            logger.error("Delegate run failed: %s", exc, exc_info=True)
            yield ErrorEvent(
                error=f"Delegate execution failed ({type(exc).__name__})",
                details={"exception_type": type(exc).__name__},
            )
            return
        finally:
            self._loop._event_callback = None

        # Record usage from the loop's tracker
        usage = self._loop.usage
        usage_dict = {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
        }

        # Update budget tracking with latest usage delta
        self._record_usage(usage_dict)

        # If MonitoredAgent is in the stack, record usage there too
        if self._monitored is not None:
            self._monitored._record_usage({"usage": usage_dict})

        yield TurnComplete(text=accumulated_text, usage=usage_dict)

    def run_sync(self, prompt: str) -> str:
        """Synchronous convenience wrapper around ``run()``.

        Collects all text deltas and returns the complete response string.
        Blocks the calling thread until the response is complete.

        Parameters
        ----------
        prompt:
            The user's input.

        Returns
        -------
        The complete text response.

        Raises
        ------
        RuntimeError:
            If the Delegate has been closed or budget is exhausted.
        """

        async def _collect() -> str:
            text_parts: list[str] = []
            async for event in self.run(prompt):
                if isinstance(event, TextDelta):
                    text_parts.append(event.text)
                elif isinstance(event, BudgetExhausted):
                    raise RuntimeError(
                        f"Budget exhausted: ${event.consumed_usd:.4f} of "
                        f"${event.budget_usd:.2f} used"
                    )
                elif isinstance(event, ErrorEvent):
                    raise RuntimeError(event.error)
            return "".join(text_parts)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            raise RuntimeError(
                "Delegate.run_sync() cannot be called from inside a running "
                "event loop (Jupyter, FastAPI handler, Nexus channel, async "
                "test). Use `async for event in delegate.run(...)` instead."
            )

        return asyncio.run(_collect())

    def interrupt(self) -> None:
        """Signal the Delegate to stop after the current operation."""
        self._loop.interrupt()

    def close(self) -> None:
        """Mark the Delegate as closed. Subsequent ``run()`` calls will fail."""
        self._closed = True

    # ------------------------------------------------------------------
    # Introspection (SPEC-05 SS5 public API surface)
    # ------------------------------------------------------------------

    @property
    def core_agent(self) -> BaseAgent:
        """The innermost BaseAgent (or user-provided inner_agent)."""
        # Walk the wrapper stack via _loop_agent to the bottom
        agent = self._loop_agent
        while hasattr(agent, "_inner"):
            agent = agent._inner
        return agent

    @property
    def signature(self) -> type[Signature] | None:
        """The Signature class passed to the constructor, or None."""
        return self._signature

    @property
    def model(self) -> str:
        """The resolved model name."""
        return self._config.model or ""

    def __repr__(self) -> str:
        budget_str = (
            f", budget=${self._budget_usd:.2f}" if self._budget_usd is not None else ""
        )
        return f"Delegate(model={self._config.model!r}{budget_str})"
