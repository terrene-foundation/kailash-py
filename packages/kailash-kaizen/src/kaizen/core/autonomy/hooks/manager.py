"""
Hook manager for orchestrating hook registration and execution.

Manages the lifecycle of hooks, including registration, execution, error handling,
and performance tracking.
"""

import functools
import importlib.util
import logging
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Awaitable, Callable

import anyio

from kaizen.utils.credential_scrub import scrub_remote_error

from .protocol import BaseHook, HookHandler
from .types import HookContext, HookEvent, HookPriority, HookResult

logger = logging.getLogger(__name__)

# Bound on how far ``safe_handler_name`` will unwrap a partial chain. Deep
# nesting is pathological, not idiomatic; the bound keeps the helper O(1) and
# terminating on any custom ``partial`` subclass without changing the result
# for real handlers.
_MAX_PARTIAL_UNWRAP_DEPTH = 8

# Budget for a handler's ``on_error`` callback. ``on_error`` is CALLER-SUPPLIED
# code awaited from inside the agent loop, so it is the same hang surface
# "SECURITY FIX #10" bounds for ``handle`` -- it was previously awaited with no
# bound at all, which meant a hook could evade the timeout guard entirely by
# hanging in its error handler instead of its body.
_ON_ERROR_TIMEOUT_S = 0.5


def safe_handler_name(handler: object) -> str:
    """Return a diagnostic identifier for a handler that cannot carry its state.

    Every hook sink in this package logs WHICH handler it is acting on, which
    is the whole diagnostic and is deliberately not scrubbed. The identifier
    MUST therefore be one that cannot carry a payload in the first place --
    ``repr(handler)`` is not, because ``handler`` is CALLER-SUPPLIED:

    * ``functools.partial(post, url="https://u:pw@host")`` renders its bound
      kwargs verbatim.
    * a callable object with a dataclass-generated ``__repr__`` renders EVERY
      field, including a credential one, without the call or the exception
      ever mentioning it.

    Resolution order:

    1. ``functools.partial`` wrappers are unwrapped, because ``partial`` is the
       idiomatic way to register a handler that needs bound config -- i.e. the
       exact shape whose identity matters most -- and ``type(p).__name__`` is
       the constant ``"partial"`` for every one of them, which would make them
       mutually indistinguishable in a log.
    2. ``__qualname__``, when present AND a string. A ``__qualname__`` is a
       SOURCE-level identifier fixed at ``def``/``class`` time, not runtime
       state, so unlike ``repr`` it cannot pick up a bound credential. It is
       the same trust level as the ``handler.name`` these sites already read
       and log unscrubbed.
    3. ``type(handler).__name__``, which cannot carry a payload by
       construction.

    Preferred over scrubbing the repr because the credential scrubber's
    coverage is porous by its own measurement (a prefix-less 32-39 char key,
    ``token=``, a %40-encoded ``@`` all survive it), so a scrub here would be a
    second porous surface rather than a closed one.

    Args:
        handler: Any callable or hook object, including caller-supplied ones.

    Returns:
        A short identifier such as ``"MyHook"``, ``"my_hook_fn"`` or
        ``"partial(my_hook_fn)"``.
    """
    inner = handler
    unwrapped = 0
    while (
        isinstance(inner, functools.partial) and unwrapped < _MAX_PARTIAL_UNWRAP_DEPTH
    ):
        inner = inner.func
        unwrapped += 1

    qualname = getattr(inner, "__qualname__", None)
    base = qualname if isinstance(qualname, str) else type(inner).__name__
    return f"partial({base})" if unwrapped else base


class FunctionHookAdapter(BaseHook):
    """Adapter to use plain async functions as hooks"""

    def __init__(
        self,
        func: Callable[[HookContext], Awaitable[HookResult]],
        name: str | None = None,
    ):
        super().__init__(name=name or func.__name__)
        self._func = func

    async def handle(self, context: HookContext) -> HookResult:
        return await self._func(context)


class HookManager:
    """
    Manages hook registration and execution.

    Handles async execution, error isolation, timeouts, and statistics tracking.
    """

    def __init__(self):
        """Initialize empty hook registry"""
        self._hooks: dict[HookEvent, list[tuple[HookPriority, HookHandler]]] = (
            defaultdict(list)
        )
        self._hook_stats: dict[str, dict[str, Any]] = {}
        # Handlers whose ``timeout_seconds`` override was rejected. Warned once
        # each rather than per trigger: ``AuditTrailHook`` alone subscribes to
        # every event in the enum, so a per-call warning would be log spam.
        self._rejected_timeout_overrides: set[str] = set()

    def register(
        self,
        event_type: HookEvent | str,
        handler: HookHandler | Callable[[HookContext], Awaitable[HookResult]],
        priority: HookPriority = HookPriority.NORMAL,
    ) -> None:
        """
        Register a hook handler for an event.

        Args:
            event_type: Event to trigger hook on
            handler: Hook handler (HookHandler or async callable)
            priority: Execution priority (lower = earlier)

        Raises:
            ValueError: If event_type is invalid
        """
        # Convert string to HookEvent
        if isinstance(event_type, str):
            try:
                event_type = HookEvent(event_type)
            except ValueError:
                raise ValueError(f"Invalid event type: {event_type}")

        # Wrap callable in adapter if needed
        if callable(handler) and not isinstance(handler, HookHandler):
            handler = FunctionHookAdapter(handler)

        # Add to registry with priority
        self._hooks[event_type].append((priority, handler))

        # Sort hooks by priority (stable sort preserves registration order within priority)
        self._hooks[event_type].sort(key=lambda x: x[0].value)

        handler_name = getattr(handler, "name", safe_handler_name(handler))
        logger.info(
            f"Registered hook for {event_type.value}: {handler_name} (priority={priority.name})"
        )

    def register_hook(
        self,
        hook: BaseHook,
        priority: HookPriority = HookPriority.NORMAL,
    ) -> None:
        """
        Register a hook for all events it declares.

        Convenience method that automatically registers a hook for all events
        specified in its 'events' attribute.

        Args:
            hook: Hook instance to register
            priority: Execution priority (lower = earlier)

        Raises:
            ValueError: If hook doesn't have 'events' attribute

        Example:
            >>> from kaizen.core.autonomy.hooks.builtin.tracing_hook import TracingHook
            >>> from kaizen.core.autonomy.observability.tracing_manager import TracingManager
            >>>
            >>> manager = TracingManager(service_name="my-service")
            >>> tracing_hook = TracingHook(tracing_manager=manager)
            >>>
            >>> hook_manager = HookManager()
            >>> hook_manager.register_hook(tracing_hook)
        """
        # Check hook has events attribute
        if not hasattr(hook, "events"):
            raise ValueError(
                f"Hook {hook.__class__.__name__} must have 'events' attribute"
            )

        # Get events (handle both list and single event)
        events = hook.events
        if not isinstance(events, list):
            events = [events]

        # Register for each event
        for event in events:
            self.register(event, hook, priority)

        hook_name = getattr(hook, "name", hook.__class__.__name__)
        logger.info(f"Registered hook {hook_name} for {len(events)} events")

    def registered_hook_names(self) -> set[str]:
        """
        Names of every handler currently registered, across all events.

        Registration was previously only inspectable through the private
        ``_hooks`` mapping -- ``get_stats()`` reports EXECUTION counts, so a
        manager that had registered nothing at all was indistinguishable from
        one whose hooks had simply not fired yet. That blind spot is how four
        observability subsystems shipped advertising themselves as enabled
        while registering nothing (#2084): no caller, banner, or test could
        ask what was actually installed.

        Returns:
            Set of handler names (deduplicated -- a hook registered for all 12
            events appears once).

        Example:
            >>> manager.register_hook(LoggingHook())
            >>> manager.registered_hook_names()
            {'logging_hook'}
        """
        return {
            getattr(handler, "name", safe_handler_name(handler))
            for handlers in self._hooks.values()
            for _priority, handler in handlers
        }

    def unregister(
        self, event_type: HookEvent | str, handler: HookHandler | None = None
    ) -> int:
        """
        Unregister hook(s) for an event.

        Args:
            event_type: Event type to unregister from
            handler: Specific handler to remove (None = remove all for event)

        Returns:
            Number of hooks removed

        Raises:
            ValueError: If event_type is invalid
        """
        # Convert string to HookEvent
        if isinstance(event_type, str):
            try:
                event_type = HookEvent(event_type)
            except ValueError:
                raise ValueError(f"Invalid event type: {event_type}")

        if handler is None:
            # Remove all hooks for this event
            count = len(self._hooks.get(event_type, []))
            if event_type in self._hooks:
                del self._hooks[event_type]
            logger.info(
                f"Unregistered all hooks for {event_type.value} (count={count})"
            )
            return count
        else:
            # Remove specific handler
            if event_type not in self._hooks:
                return 0

            original_count = len(self._hooks[event_type])
            self._hooks[event_type] = [
                (p, h) for p, h in self._hooks[event_type] if h != handler
            ]
            removed = original_count - len(self._hooks[event_type])

            if removed > 0:
                handler_name = getattr(handler, "name", safe_handler_name(handler))
                logger.info(f"Unregistered hook for {event_type.value}: {handler_name}")

            return removed

    async def trigger(
        self,
        event_type: HookEvent | str,
        agent_id: str,
        data: dict[str, Any],
        timeout: float = 0.5,  # Reduced from 5.0 to 0.5 seconds (SECURITY FIX #10)
        metadata: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> list[HookResult]:
        """
        Trigger all hooks for an event type.

        Executes hooks in priority order with error isolation and timeout.

        Args:
            event_type: Event that occurred
            agent_id: ID of agent triggering the event
            data: Event-specific data
            timeout: Max execution time per hook in seconds
            metadata: Optional additional metadata
            trace_id: Distributed tracing ID (auto-generated if None)

        Returns:
            List of HookResult from each executed hook

        Raises:
            ValueError: If event_type is invalid
        """
        # Convert string to HookEvent
        if isinstance(event_type, str):
            try:
                event_type = HookEvent(event_type)
            except ValueError:
                raise ValueError(f"Invalid event type: {event_type}")

        # Generate trace_id if not provided
        if trace_id is None:
            import uuid

            trace_id = str(uuid.uuid4())

        # Get hooks for this event (sorted by priority)
        hooks_with_priority = self._hooks.get(event_type, [])
        if not hooks_with_priority:
            return []

        # Create context
        context = HookContext(
            event_type=event_type,
            agent_id=agent_id,
            timestamp=time.time(),
            data=data,
            metadata=metadata or {},
            trace_id=trace_id,
        )

        # Execute all hooks
        results = []
        for priority, handler in hooks_with_priority:
            result = await self._execute_hook(handler, context, timeout)
            results.append(result)

        return results

    async def _execute_hook(
        self, handler: HookHandler, context: HookContext, timeout: float
    ) -> HookResult:
        """
        Execute a single hook with error handling and timeout.

        Args:
            handler: Hook to execute
            context: Hook context
            timeout: Max execution time in seconds

        Returns:
            HookResult with success/failure status
        """
        # ``handler_name`` reaches THREE sinks below -- two log lines, the
        # returned ``HookResult.error``, and ``_update_stats``, where it
        # becomes a dict KEY returned verbatim by the public ``get_stats()``.
        # It must not be able to carry caller state; see ``safe_handler_name``.
        handler_name = getattr(handler, "name", safe_handler_name(handler))
        effective_timeout = self._resolve_timeout(handler, timeout, handler_name)

        try:
            # Execute with timeout
            with anyio.fail_after(effective_timeout):
                start_time = time.perf_counter()
                result = await handler.handle(context)
                result.duration_ms = (time.perf_counter() - start_time) * 1000

                # Track stats
                self._update_stats(handler_name, result.duration_ms, success=True)

                return result

        except TimeoutError as timeout_exc:
            error_msg = f"Hook timeout: {handler_name}"
            # Structured, not a bare string. A timeout means the hook's work was
            # ABANDONED, and for a compliance hook that is a lost record -- so
            # the signal has to name WHICH event vanished, under WHICH handler,
            # at WHICH budget, in fields an alert can match on.
            logger.error(
                "hook.timeout handler=%s event=%s agent_id=%s timeout_s=%.3f "
                "trace_id=%s",
                handler_name,
                context.event_type.value,
                context.agent_id,
                effective_timeout,
                context.trace_id,
                extra={
                    "hook_handler": handler_name,
                    "hook_event": context.event_type.value,
                    "hook_agent_id": context.agent_id,
                    "hook_timeout_s": effective_timeout,
                    "hook_trace_id": context.trace_id,
                },
            )
            self._update_stats(
                handler_name, effective_timeout * 1000, success=False, timed_out=True
            )

            # A timeout is a hook FAILURE, and the handler's own failure path
            # must see it. Previously only ``except Exception`` reached
            # ``on_error``, and because ``TimeoutError`` is matched by the
            # branch above it never got there -- so a hook that implemented
            # on_error specifically to surface dropped work was bypassed in the
            # one case where the work was guaranteed lost.
            await self._invoke_on_error(handler, timeout_exc, context, handler_name)

            return HookResult(
                success=False,
                error=error_msg,
                duration_ms=effective_timeout * 1000,
                data={
                    "timeout": True,
                    "handler": handler_name,
                    "event": context.event_type.value,
                    "timeout_s": effective_timeout,
                },
            )

        except Exception as e:
            # BOTH halves: `error_msg` is returned to the caller in the
            # HookResult below AND `logger.exception` always sets exc_info,
            # so the raw hook exception reached a return value and a
            # traceback. Hooks are user-registered code holding their own
            # credentials. `handler_name` is retained -- it names WHICH hook
            # failed and is not exception-derived.
            error_msg = f"Hook error: {scrub_remote_error(e)}"
            logger.error("Hook failed: %s: %s", handler_name, scrub_remote_error(e))
            self._update_stats(handler_name, 0, success=False)

            # Call error handler if available
            await self._invoke_on_error(handler, e, context, handler_name)

            return HookResult(success=False, error=error_msg, duration_ms=0.0)

    def _resolve_timeout(
        self, handler: HookHandler, default: float, handler_name: str
    ) -> float:
        """
        Resolve the execution budget for one handler.

        A handler MAY declare ``timeout_seconds`` to opt onto a budget other
        than the caller's shared one. This exists because the builtin hooks are
        not alike: three are best-effort observability, where dropping the
        work costs a gap in a graph, while ``AuditTrailHook`` writes a
        compliance record whose whole value is that it is complete.

        The override selects a DIFFERENT finite bound; it can never remove one.
        A missing, non-numeric, non-positive, infinite or NaN value falls back
        to the shared default, so "SECURITY FIX #10" cannot be disabled by
        setting an attribute -- including by a caller-supplied hook loaded off
        the filesystem by :meth:`discover_filesystem_hooks`.

        Args:
            handler: Hook whose budget is being resolved.
            default: Shared budget supplied by the ``trigger`` caller.
            handler_name: Diagnostic name, already made payload-safe.

        Returns:
            A finite, positive timeout in seconds.
        """
        override = getattr(handler, "timeout_seconds", None)
        if override is None:
            return default

        # ``bool`` is an ``int`` subclass; ``timeout_seconds = True`` would
        # otherwise silently become a 1-second budget.
        if isinstance(override, bool) or not isinstance(override, (int, float)):
            self._warn_rejected_timeout(handler_name, override, "not a number")
            return default

        value = float(override)
        if not math.isfinite(value) or value <= 0:
            self._warn_rejected_timeout(
                handler_name, override, "not finite and positive"
            )
            return default

        return value

    def _warn_rejected_timeout(
        self, handler_name: str, override: object, reason: str
    ) -> None:
        """Warn once per handler that its timeout override was refused."""
        if handler_name in self._rejected_timeout_overrides:
            return
        self._rejected_timeout_overrides.add(handler_name)
        # ``override`` is caller-supplied, so only its TYPE is rendered -- a
        # value here could carry state, the same channel ``safe_handler_name``
        # closes for the handler itself.
        logger.warning(
            "hook.timeout_override_rejected handler=%s type=%s reason=%s "
            "falling back to the shared budget",
            handler_name,
            type(override).__name__,
            reason,
            extra={
                "hook_handler": handler_name,
                "hook_timeout_override_type": type(override).__name__,
                "hook_timeout_override_reason": reason,
            },
        )

    async def _invoke_on_error(
        self,
        handler: HookHandler,
        error: BaseException,
        context: HookContext,
        handler_name: str,
    ) -> None:
        """
        Run a handler's ``on_error`` callback under its own bound.

        ``on_error`` is caller-supplied code awaited from inside the agent
        loop, so it is bounded for the same reason ``handle`` is: without a
        bound, a hook that hangs in its error handler hangs the loop, which is
        the exact failure "SECURITY FIX #10" exists to prevent.
        """
        if not hasattr(handler, "on_error"):
            return

        try:
            with anyio.fail_after(_ON_ERROR_TIMEOUT_S):
                await handler.on_error(error, context)
        except TimeoutError:
            logger.error(
                "hook.on_error_timeout handler=%s event=%s timeout_s=%.3f",
                handler_name,
                context.event_type.value,
                _ON_ERROR_TIMEOUT_S,
                extra={
                    "hook_handler": handler_name,
                    "hook_event": context.event_type.value,
                    "hook_timeout_s": _ON_ERROR_TIMEOUT_S,
                },
            )
        except Exception as err_e:
            # ``handler.on_error`` is caller-supplied, same as the handler
            # itself; its failure carries whatever that code touched.
            logger.error("Error handler failed: %s", scrub_remote_error(err_e))

    def _update_stats(
        self,
        handler_name: str,
        duration_ms: float,
        success: bool,
        timed_out: bool = False,
    ) -> None:
        """
        Track hook performance statistics.

        Args:
            handler_name: Name of the hook
            duration_ms: Execution duration in milliseconds
            success: Whether execution succeeded
            timed_out: Whether the failure was a timeout, i.e. the hook's work
                was abandoned rather than attempted and refused. Counted
                separately from ``failure_count`` so a consumer can alert on
                DROPPED work -- for an audit hook that is a missing compliance
                record, which is not the same event as an append that raised.
        """
        if handler_name not in self._hook_stats:
            self._hook_stats[handler_name] = {
                "call_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "timeout_count": 0,
                "total_duration_ms": 0.0,
                "avg_duration_ms": 0.0,
                "max_duration_ms": 0.0,
            }

        stats = self._hook_stats[handler_name]
        stats["call_count"] += 1
        stats["success_count" if success else "failure_count"] += 1
        if timed_out:
            stats["timeout_count"] += 1
        stats["total_duration_ms"] += duration_ms
        stats["avg_duration_ms"] = stats["total_duration_ms"] / stats["call_count"]
        stats["max_duration_ms"] = max(stats["max_duration_ms"], duration_ms)

    def get_stats(self) -> dict[str, dict[str, Any]]:
        """
        Get hook performance statistics.

        Returns:
            Dictionary mapping hook names to their stats
        """
        return self._hook_stats.copy()

    async def discover_filesystem_hooks(self, hooks_dir: Path) -> int:
        """
        Discover and load hooks from filesystem.

        Loads all .py files from hooks_dir that define hook classes or functions.

        Args:
            hooks_dir: Directory containing hook files (.py)

        Returns:
            Number of hooks discovered and registered

        Raises:
            OSError: If hooks_dir doesn't exist or isn't readable
        """
        if not hooks_dir.exists():
            raise OSError(f"Hooks directory not found: {hooks_dir}")

        if not hooks_dir.is_dir():
            raise OSError(f"Not a directory: {hooks_dir}")

        discovered_count = 0

        # Find all .py files (excluding __init__.py)
        hook_files = [f for f in hooks_dir.glob("*.py") if f.name != "__init__.py"]

        for hook_file in hook_files:
            try:
                # Load module dynamically
                module_name = f"kaizen_hooks_{hook_file.stem}"
                spec = importlib.util.spec_from_file_location(module_name, hook_file)
                if spec is None or spec.loader is None:
                    logger.warning(f"Could not load hook file: {hook_file}")
                    continue

                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                # Look for hook classes (subclasses of BaseHook)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)

                    # Skip if not a class
                    if not isinstance(attr, type):
                        continue

                    # Skip if not a BaseHook subclass (or BaseHook itself)
                    if not issubclass(attr, BaseHook) or attr is BaseHook:
                        continue

                    # Try to instantiate and register
                    try:
                        hook_instance = attr()

                        # Hook must define which events it handles
                        if not hasattr(hook_instance, "events"):
                            logger.warning(
                                f"Hook {attr_name} missing 'events' attribute, skipping"
                            )
                            continue

                        # Register for each event
                        events = hook_instance.events
                        if not isinstance(events, list):
                            events = [events]

                        for event in events:
                            self.register(event, hook_instance)
                            discovered_count += 1

                        logger.info(f"Loaded hook from {hook_file}: {attr_name}")

                    except Exception as e:
                        # Hook INSTANTIATION runs a caller-supplied class's
                        # ``__init__`` -- arbitrary code, which may open a DB
                        # connection or an HTTP client, so a driver error
                        # here carries a DSN or an endpoint credential. This
                        # is the same channel the EXECUTION sink above cites;
                        # 90899764a fixed that one and missed this, because
                        # the grep that drove it looked for exc_info and
                        # logger.exception, and this line has neither.
                        logger.error(
                            "Failed to instantiate hook %s: %s",
                            attr_name,
                            scrub_remote_error(e),
                        )

            except Exception as e:
                # Loading imports a caller-supplied module, so module-level
                # side effects run here. Sibling of the instantiate guard
                # above; fixed in lockstep so the loading path cannot end up
                # half-swept the way the file already was once.
                logger.error(
                    "Failed to load hook file %s: %s",
                    hook_file,
                    scrub_remote_error(e),
                )

        logger.info(f"Discovered {discovered_count} hooks from {hooks_dir}")
        return discovered_count


# Export all public types
__all__ = [
    "HookManager",
    "FunctionHookAdapter",
    "safe_handler_name",
]
