"""
Hook manager for orchestrating hook registration and execution.

Manages the lifecycle of hooks, including registration, execution, error handling,
and performance tracking.
"""

import importlib.util
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Awaitable, Callable

import anyio

from .protocol import BaseHook, HookHandler
from .types import HookContext, HookEvent, HookPriority, HookResult

logger = logging.getLogger(__name__)


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

        handler_name = getattr(handler, "name", repr(handler))
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
                handler_name = getattr(handler, "name", repr(handler))
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
        handler_name = getattr(handler, "name", repr(handler))

        try:
            # Execute with timeout
            with anyio.fail_after(timeout):
                start_time = time.perf_counter()
                result = await handler.handle(context)
                result.duration_ms = (time.perf_counter() - start_time) * 1000

                # Track stats
                self._update_stats(handler_name, result.duration_ms, success=True)

                return result

        except TimeoutError:
            error_msg = f"Hook timeout: {handler_name}"
            logger.error(error_msg)
            self._update_stats(handler_name, timeout * 1000, success=False)
            return HookResult(
                success=False, error=error_msg, duration_ms=timeout * 1000
            )

        except Exception as e:
            error_msg = f"Hook error: {str(e)}"
            logger.exception(f"Hook failed: {handler_name}")
            self._update_stats(handler_name, 0, success=False)

            # Call error handler if available
            if hasattr(handler, "on_error"):
                try:
                    await handler.on_error(e, context)
                except Exception as err_e:
                    logger.error(f"Error handler failed: {err_e}")

            return HookResult(success=False, error=error_msg, duration_ms=0.0)

    def _update_stats(
        self, handler_name: str, duration_ms: float, success: bool
    ) -> None:
        """
        Track hook performance statistics.

        Args:
            handler_name: Name of the hook
            duration_ms: Execution duration in milliseconds
            success: Whether execution succeeded
        """
        if handler_name not in self._hook_stats:
            self._hook_stats[handler_name] = {
                "call_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "total_duration_ms": 0.0,
                "avg_duration_ms": 0.0,
                "max_duration_ms": 0.0,
            }

        stats = self._hook_stats[handler_name]
        stats["call_count"] += 1
        stats["success_count" if success else "failure_count"] += 1
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
                        logger.error(f"Failed to instantiate hook {attr_name}: {e}")

            except Exception as e:
                logger.error(f"Failed to load hook file {hook_file}: {e}")

        logger.info(f"Discovered {discovered_count} hooks from {hooks_dir}")
        return discovered_count


# Export all public types
__all__ = [
    "HookManager",
    "FunctionHookAdapter",
]
