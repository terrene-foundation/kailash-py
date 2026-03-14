# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP hook system for trust-native lifecycle events.

Provides a protocol-based hook registry with priority ordering, fail-closed
abort semantics, and timeout enforcement for extending EATP enforcement
pipelines.

Hook Types:
    Only 4 trust-native events are defined. This is intentional:

    - ``PRE_DELEGATION`` / ``POST_DELEGATION``: Intercept delegation creation.
    - ``PRE_VERIFICATION`` / ``POST_VERIFICATION``: Intercept verification.

    Omitted events and rationale (ADR-002):

    - ESTABLISH hooks: Genesis is a one-time bootstrap operation with no
      enforcement decision to intercept.
    - AUDIT hooks: Audit is read-only — intercepting it would compromise
      audit integrity.
    - PRE_TOOL_USE / POST_TOOL_USE / SUBAGENT_SPAWN: Orchestration concerns
      that belong in kailash-kaizen, not the trust protocol layer.

Abort Semantics:
    Any hook returning ``allow=False`` immediately aborts the remaining hook
    chain (fail-closed). This means a single deny hook prevents the action.

Crash Handling:
    If a hook raises an exception or times out, the result is
    ``HookResult(allow=False)`` — fail-closed. This prevents a buggy hook
    from silently allowing an action.

Relationship to Decorators:
    Hooks complement the ``@verified`` / ``@audited`` / ``@shadow`` decorators.
    Decorators provide 3-line integration for functions; hooks provide
    fine-grained lifecycle interception for the enforcement pipeline itself.
    Both are needed in production deployments.

Cross-SDK Alignment:
    Hook types and abort semantics align with the shared EATP spec addendum.
    The Rust SDK implements equivalent hooks via trait objects.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class HookType(str, Enum):
    """Trust-native lifecycle events for hook interception.

    Only 4 events are defined — see module docstring for rationale on
    why ESTABLISH, AUDIT, and orchestration events are excluded.
    """

    PRE_DELEGATION = "pre_delegation"
    POST_DELEGATION = "post_delegation"
    PRE_VERIFICATION = "pre_verification"
    POST_VERIFICATION = "post_verification"


@dataclass
class HookContext:
    """Context passed to hooks during execution.

    Attributes:
        agent_id: The agent involved in the operation.
        action: The action being performed.
        hook_type: Which lifecycle event triggered this hook.
        metadata: Arbitrary key-value data for hook consumption.
            Hooks may read this to make decisions. Modified context
            from a hook's result is merged back into metadata for
            subsequent hooks in the chain.
        timestamp: When the hook context was created.
    """

    agent_id: str
    action: str
    hook_type: HookType
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class HookResult:
    """Result returned by a hook execution.

    Attributes:
        allow: Whether the operation should proceed. If False, the
            hook chain is aborted immediately (fail-closed).
        reason: Human-readable reason for the decision. Required
            when allow=False for audit trail.
        modified_context: Optional dict to merge into HookContext.metadata
            for subsequent hooks. Only applied when allow=True.
    """

    allow: bool
    reason: Optional[str] = None
    modified_context: Optional[Dict[str, Any]] = None


class EATPHook(ABC):
    """Abstract base class for EATP lifecycle hooks.

    Subclass this to create hooks that intercept trust operations.
    Each hook declares which event types it handles and is called
    in priority order (lower number = earlier execution).

    Example:
        >>> class RateLimitHook(EATPHook):
        ...     @property
        ...     def name(self) -> str:
        ...         return "rate_limiter"
        ...
        ...     @property
        ...     def event_types(self) -> List[HookType]:
        ...         return [HookType.PRE_VERIFICATION]
        ...
        ...     @property
        ...     def priority(self) -> int:
        ...         return 50  # Run early
        ...
        ...     async def __call__(self, context: HookContext) -> HookResult:
        ...         if self._is_rate_limited(context.agent_id):
        ...             return HookResult(allow=False, reason="Rate limited")
        ...         return HookResult(allow=True)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this hook."""
        ...

    @property
    @abstractmethod
    def event_types(self) -> List[HookType]:
        """Which lifecycle events this hook handles."""
        ...

    @property
    def priority(self) -> int:
        """Execution priority. Lower number = earlier execution. Default: 100."""
        return 100

    @abstractmethod
    async def __call__(self, context: HookContext) -> HookResult:
        """Execute the hook logic.

        Args:
            context: The hook context with agent, action, and metadata.

        Returns:
            HookResult indicating whether to proceed or abort.
        """
        ...


class HookRegistry:
    """Registry for managing and executing EATP lifecycle hooks.

    Hooks are registered by name (unique) and executed in priority order
    for each hook type. The registry enforces fail-closed semantics:
    any hook returning ``allow=False``, timing out, or crashing will
    abort the operation.

    Example:
        >>> registry = HookRegistry(timeout_seconds=5.0)
        >>> registry.register(my_hook)
        >>> result = await registry.execute(
        ...     HookType.PRE_VERIFICATION,
        ...     HookContext(agent_id="agent-001", action="read", hook_type=HookType.PRE_VERIFICATION),
        ... )
        >>> if not result.allow:
        ...     print(f"Blocked: {result.reason}")
    """

    def __init__(self, timeout_seconds: float = 5.0):
        """Initialize the hook registry.

        Args:
            timeout_seconds: Maximum time a single hook may execute
                before being aborted (fail-closed). Default: 5.0s.
        """
        if timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be positive, got {timeout_seconds}")
        self._hooks: Dict[str, EATPHook] = {}
        self._timeout = timeout_seconds

    @property
    def timeout_seconds(self) -> float:
        """Get the configured timeout for hook execution."""
        return self._timeout

    def register(self, hook: EATPHook) -> None:
        """Register a hook.

        Args:
            hook: The hook to register.

        Raises:
            ValueError: If a hook with the same name is already registered.
        """
        if hook.name in self._hooks:
            raise ValueError(
                f"Hook '{hook.name}' is already registered. "
                f"Unregister it first to replace."
            )
        self._hooks[hook.name] = hook
        logger.debug(
            f"Registered hook '{hook.name}' for events: "
            f"{[e.value for e in hook.event_types]} (priority: {hook.priority})"
        )

    def unregister(self, hook_name: str) -> None:
        """Unregister a hook by name.

        No-op if the hook is not registered.

        Args:
            hook_name: The name of the hook to remove.
        """
        if hook_name in self._hooks:
            del self._hooks[hook_name]
            logger.debug(f"Unregistered hook '{hook_name}'")

    async def execute(
        self,
        hook_type: HookType,
        context: HookContext,
    ) -> HookResult:
        """Execute all hooks registered for a given event type.

        Hooks are executed in priority order (lower number first).
        The chain aborts immediately if any hook returns ``allow=False``,
        times out, or raises an exception (fail-closed).

        Args:
            hook_type: The lifecycle event to execute hooks for.
            context: The hook context to pass to each hook.

        Returns:
            HookResult. ``allow=True`` if all hooks passed (or none registered).
            ``allow=False`` with reason if any hook denied/crashed/timed out.
        """
        relevant = [h for h in self._hooks.values() if hook_type in h.event_types]
        if not relevant:
            return HookResult(allow=True)

        # Sort by priority (lower = earlier)
        relevant.sort(key=lambda h: h.priority)

        for hook in relevant:
            try:
                result = await asyncio.wait_for(hook(context), timeout=self._timeout)
            except asyncio.TimeoutError:
                reason = (
                    f"Hook '{hook.name}' timed out after "
                    f"{self._timeout}s (fail-closed)"
                )
                logger.warning(f"[HOOK] {reason}")
                return HookResult(allow=False, reason=reason)
            except Exception as exc:
                reason = f"Hook '{hook.name}' crashed (fail-closed)"
                logger.warning(f"[HOOK] {reason}: {type(exc).__name__}: {exc}")
                return HookResult(allow=False, reason=reason)

            # Validate return type (fail-closed on bad return)
            if not isinstance(result, HookResult):
                reason = (
                    f"Hook '{hook.name}' returned {type(result).__name__}, "
                    f"expected HookResult (fail-closed)"
                )
                logger.warning(f"[HOOK] {reason}")
                return HookResult(allow=False, reason=reason)

            if not result.allow:
                logger.info(
                    f"[HOOK] Hook '{hook.name}' denied {hook_type.value} "
                    f"for agent '{context.agent_id}': {result.reason}"
                )
                return result

            # Merge modified context for subsequent hooks
            if result.modified_context:
                for key in result.modified_context:
                    if key in context.metadata:
                        logger.debug(
                            f"[HOOK] Hook '{hook.name}' overwrites "
                            f"metadata key '{key}'"
                        )
                context.metadata.update(result.modified_context)

        return HookResult(allow=True)

    def execute_sync(
        self,
        hook_type: HookType,
        context: HookContext,
    ) -> HookResult:
        """Synchronous wrapper for execute().

        Uses the same event-loop detection pattern as the enforcement
        decorators: tries ``asyncio.run()`` first, falls back to a
        ThreadPoolExecutor if already inside an event loop.

        Args:
            hook_type: The lifecycle event to execute hooks for.
            context: The hook context to pass to each hook.

        Returns:
            HookResult from the async execute() call.
        """
        coro = self.execute(hook_type, context)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        else:
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()

    def list_hooks(self, hook_type: Optional[HookType] = None) -> List[EATPHook]:
        """List registered hooks, optionally filtered by event type.

        Args:
            hook_type: If provided, only return hooks handling this event.
                If None, return all registered hooks.

        Returns:
            List of hooks sorted by priority (lower first).
        """
        if hook_type is None:
            hooks = list(self._hooks.values())
        else:
            hooks = [h for h in self._hooks.values() if hook_type in h.event_types]
        hooks.sort(key=lambda h: h.priority)
        return hooks


__all__ = [
    "HookType",
    "HookContext",
    "HookResult",
    "EATPHook",
    "HookRegistry",
]
