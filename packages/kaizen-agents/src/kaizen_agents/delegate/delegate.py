# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Delegate facade -- the single entry point for autonomous AI execution.

Composes :class:`AgentLoop` with optional :class:`GovernedSupervisor` to
provide a progressive-disclosure API:

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
import time
from typing import Any, AsyncGenerator, Callable, Awaitable, TYPE_CHECKING

from kaizen_agents.delegate.config.loader import KzConfig
from kaizen_agents.delegate.events import (
    BudgetExhausted,
    DelegateEvent,
    ErrorEvent,
    TextDelta,
    ToolCallEnd,
    ToolCallStart,
    TurnComplete,
)
from kaizen_agents.delegate.loop import AgentLoop, ToolRegistry

if TYPE_CHECKING:
    from kaizen_agents.delegate.adapters.protocol import StreamingChatAdapter
    from kaizen_agents.supervisor import GovernedSupervisor

logger = logging.getLogger(__name__)

__all__ = ["Delegate"]


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

    cost = (prompt_tokens / 1_000_000) * input_rate + (completion_tokens / 1_000_000) * output_rate
    return cost


class Delegate:
    """Facade composing AgentLoop + optional governance for autonomous AI execution.

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
    tools:
        List of tool names or a pre-built :class:`ToolRegistry`.
        When a list of strings is given, the Delegate creates an empty
        registry (tools must be registered separately).
    system_prompt:
        Override the default system prompt.
    max_turns:
        Maximum tool-calling loops per ``run()`` call.
    budget_usd:
        Optional USD budget cap.  When set, the Delegate tracks
        estimated cost per turn and yields :class:`BudgetExhausted`
        when the budget is exceeded.
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
        tools: ToolRegistry | list[str] | None = None,
        system_prompt: str | None = None,
        max_turns: int = 50,
        budget_usd: float | None = None,
        adapter: StreamingChatAdapter | None = None,
        config: KzConfig | None = None,
    ) -> None:
        # Validate budget
        if budget_usd is not None:
            if not math.isfinite(budget_usd):
                raise ValueError("budget_usd must be finite")
            if budget_usd < 0:
                raise ValueError("budget_usd must be non-negative")

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

        # Build the budget check callback
        budget_check: Callable[[], bool] | None = None
        if budget_usd is not None:
            budget_check = self._check_budget

        # Create the core loop
        self._loop = AgentLoop(
            config=self._config,
            tools=self._tool_registry,
            adapter=adapter,
            system_prompt=system_prompt,
            budget_check=budget_check,
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

        accumulated_text = ""

        try:
            async for chunk in self._loop.run_turn(prompt):
                # Tool call events from the loop — yield as-is
                if isinstance(chunk, DelegateEvent):
                    yield chunk
                    continue

                # str chunks — text deltas
                # Check if this is the budget-exhausted sentinel
                if chunk == "[Budget exhausted — stopping.]":
                    yield BudgetExhausted(
                        budget_usd=self._budget_usd or 0.0,
                        consumed_usd=self._consumed_usd,
                    )
                    return

                accumulated_text += chunk
                yield TextDelta(text=chunk)

        except Exception as exc:
            logger.error("Delegate run failed: %s", exc, exc_info=True)
            yield ErrorEvent(
                error=f"Delegate execution failed ({type(exc).__name__})",
                details={"exception_type": type(exc).__name__},
            )
            return

        # Record usage from the loop's tracker
        usage = self._loop.usage
        usage_dict = {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
        }

        # Update budget tracking with latest usage delta
        # The loop tracks cumulative usage; we need the delta since last recording
        self._record_usage(usage_dict)

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
            # Already in an async context -- cannot use asyncio.run()
            # Use a background thread instead
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _collect())
                return future.result()
        else:
            return asyncio.run(_collect())

    def interrupt(self) -> None:
        """Signal the Delegate to stop after the current operation."""
        self._loop.interrupt()

    def close(self) -> None:
        """Mark the Delegate as closed. Subsequent ``run()`` calls will fail."""
        self._closed = True

    def __repr__(self) -> str:
        budget_str = f", budget=${self._budget_usd:.2f}" if self._budget_usd is not None else ""
        return f"Delegate(model={self._config.model!r}{budget_str})"
