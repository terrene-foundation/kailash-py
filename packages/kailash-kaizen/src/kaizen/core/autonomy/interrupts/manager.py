"""
Interrupt manager for graceful shutdown coordination.

Manages interrupt signals, shutdown callbacks, and checkpoint integration.
"""

import logging
import signal
from typing import Any, Awaitable, Callable

import anyio

from .types import InterruptMode, InterruptReason, InterruptSource, InterruptStatus

logger = logging.getLogger(__name__)


class InterruptManager:
    """
    Manages interrupt signals and graceful shutdown.

    Handles OS signals (SIGINT, SIGTERM), programmatic interrupts,
    and coordinates shutdown sequence with checkpointing.
    """

    def __init__(self):
        """Initialize interrupt manager"""
        self._interrupted = anyio.Event()
        self._interrupt_reason: InterruptReason | None = None
        self._shutdown_callbacks: list[Callable[[], Awaitable[None]]] = []
        self._signal_handlers_installed = False
        self._original_handlers: dict[int, Any] = {}
        self._child_managers: list["InterruptManager"] = (
            []
        )  # For propagation (TODO-169 Day 3)
        self.hook_manager: Any = (
            None  # Optional HookManager for lifecycle events (TODO-169 Day 4)
        )

    def install_signal_handlers(self) -> None:
        """
        Install OS signal handlers (SIGINT, SIGTERM, SIGUSR1).

        Idempotent - can be called multiple times safely.
        """
        if self._signal_handlers_installed:
            logger.debug("Signal handlers already installed")
            return

        # Handle Ctrl+C (SIGINT)
        self._original_handlers[signal.SIGINT] = signal.signal(
            signal.SIGINT, self._handle_signal
        )

        # Handle termination (SIGTERM)
        self._original_handlers[signal.SIGTERM] = signal.signal(
            signal.SIGTERM, self._handle_signal
        )

        # Handle user signal 1 (SIGUSR1) - optional, for custom interrupts
        try:
            self._original_handlers[signal.SIGUSR1] = signal.signal(
                signal.SIGUSR1, self._handle_signal
            )
        except (AttributeError, ValueError):
            # SIGUSR1 not available on Windows
            logger.debug("SIGUSR1 not available on this platform")

        self._signal_handlers_installed = True
        logger.info("Signal handlers installed (SIGINT, SIGTERM, SIGUSR1)")

    def uninstall_signal_handlers(self) -> None:
        """
        Restore original signal handlers.

        Call during cleanup or testing.
        """
        if not self._signal_handlers_installed:
            return

        for signum, handler in self._original_handlers.items():
            if handler is not None:
                signal.signal(signum, handler)

        self._signal_handlers_installed = False
        self._original_handlers.clear()
        logger.info("Signal handlers uninstalled")

    def _handle_signal(self, signum: int, frame) -> None:
        """
        Signal handler (called by OS).

        Must be thread-safe and non-blocking.
        """
        try:
            signal_name = signal.Signals(signum).name
        except ValueError:
            signal_name = f"Signal-{signum}"

        logger.warning(f"Received {signal_name}, requesting graceful shutdown")

        # Request graceful interrupt
        # Note: Can't use async in signal handler, so we use thread-safe Event
        self.request_interrupt(
            mode=InterruptMode.GRACEFUL,
            source=InterruptSource.SIGNAL,
            message=f"Interrupted by signal {signal_name}",
            metadata={"signal": signum, "signal_name": signal_name},
        )

    def request_interrupt(
        self,
        mode: InterruptMode,
        source: InterruptSource,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Request interrupt (thread-safe).

        Can be called from signal handlers, async code, or other threads.

        Args:
            mode: How to handle interrupt (GRACEFUL or IMMEDIATE)
            source: Source of interrupt
            message: Human-readable reason
            metadata: Additional context
        """
        # Don't allow overwriting an existing interrupt
        if self._interrupt_reason is not None:
            logger.debug("Interrupt already requested, ignoring duplicate request")
            return

        self._interrupt_reason = InterruptReason(
            source=source,
            mode=mode,
            message=message,
            metadata=metadata or {},
        )

        # Set interrupt flag (thread-safe)
        # anyio.Event.set() works from any context (sync or async)
        self._interrupted.set()

        logger.warning(
            f"Interrupt requested: {message} "
            f"(mode={mode.value}, source={source.value})"
        )

    def is_interrupted(self) -> bool:
        """
        Check if interrupt has been requested (non-blocking).

        Returns:
            True if interrupt requested
        """
        return self._interrupted.is_set()

    async def wait_for_interrupt(
        self, timeout: float | None = None
    ) -> InterruptReason | None:
        """
        Wait for interrupt signal (blocking).

        Args:
            timeout: Maximum time to wait (None = wait forever)

        Returns:
            InterruptReason if interrupted, None if timeout
        """
        try:
            if timeout:
                with anyio.fail_after(timeout):
                    await self._interrupted.wait()
            else:
                await self._interrupted.wait()

            return self._interrupt_reason

        except TimeoutError:
            return None

    def register_shutdown_callback(
        self, callback: Callable[[], Awaitable[None]]
    ) -> None:
        """
        Register callback to run before shutdown.

        Callbacks are executed in registration order during shutdown.

        Args:
            callback: Async function to call during shutdown
        """
        self._shutdown_callbacks.append(callback)
        logger.debug(f"Registered shutdown callback: {callback.__name__}")

    async def execute_shutdown_callbacks(self) -> None:
        """
        Execute all shutdown callbacks.

        Continues execution even if callbacks fail.
        """
        if not self._shutdown_callbacks:
            return

        logger.info(f"Executing {len(self._shutdown_callbacks)} shutdown callbacks...")

        for i, callback in enumerate(self._shutdown_callbacks):
            try:
                await callback()
                logger.debug(f"Shutdown callback {i+1} completed")
            except Exception as e:
                logger.error(f"Shutdown callback {i+1} failed: {e}", exc_info=True)

        logger.info("All shutdown callbacks executed")

    async def execute_shutdown(
        self, state_manager: Any = None, agent_state: Any = None
    ) -> InterruptStatus:
        """
        Execute graceful shutdown sequence.

        1. Execute shutdown callbacks
        2. Save checkpoint (if state_manager provided)
        3. Return interrupt status

        Args:
            state_manager: Optional StateManager for checkpointing
            agent_state: Optional AgentState to checkpoint

        Returns:
            InterruptStatus with checkpoint information
        """
        if not self._interrupt_reason:
            raise RuntimeError("No interrupt reason set")

        logger.info(f"Starting graceful shutdown: {self._interrupt_reason.message}")

        # Execute shutdown callbacks
        await self.execute_shutdown_callbacks()

        # Save checkpoint if state manager available
        checkpoint_id = None
        if state_manager and agent_state:
            try:
                logger.info("Saving checkpoint before shutdown...")

                # Mark state as interrupted
                agent_state.status = "interrupted"
                agent_state.metadata["interrupt_reason"] = (
                    self._interrupt_reason.to_dict()
                )

                # Save checkpoint
                checkpoint_id = await state_manager.save_checkpoint(
                    agent_state, force=True
                )

                logger.info(f"Checkpoint saved: {checkpoint_id}")

            except Exception as e:
                logger.error(f"Failed to save checkpoint: {e}", exc_info=True)

        # Create interrupt status
        status = InterruptStatus(
            interrupted=True,
            reason=self._interrupt_reason,
            checkpoint_id=checkpoint_id,
        )

        logger.info(
            f"Graceful shutdown complete " f"(checkpoint={checkpoint_id or 'none'})"
        )

        return status

    def reset(self) -> None:
        """
        Reset interrupt state.

        Use for testing or when resuming execution.
        """
        self._interrupted = anyio.Event()
        self._interrupt_reason = None
        logger.debug("Interrupt state reset")

    def get_interrupt_reason(self) -> InterruptReason | None:
        """
        Get current interrupt reason.

        Returns:
            InterruptReason if interrupted, None otherwise
        """
        return self._interrupt_reason

    def add_child_manager(self, child_manager: "InterruptManager") -> None:
        """
        Add child interrupt manager for propagation (TODO-169 Day 3).

        When parent is interrupted, interrupt will propagate to all children.

        Args:
            child_manager: Child InterruptManager to track

        Example:
            >>> parent = InterruptManager()
            >>> child = InterruptManager()
            >>> parent.add_child_manager(child)
            >>> parent.request_interrupt(InterruptMode.GRACEFUL, ...)
            >>> parent.propagate_to_children()  # Interrupts child
        """
        if child_manager not in self._child_managers:
            self._child_managers.append(child_manager)
            logger.debug(
                f"Added child interrupt manager (total={len(self._child_managers)})"
            )

    def remove_child_manager(self, child_manager: "InterruptManager") -> None:
        """
        Remove child interrupt manager from tracking (TODO-169 Day 3).

        Args:
            child_manager: Child InterruptManager to remove

        Example:
            >>> parent.remove_child_manager(child)
        """
        if child_manager in self._child_managers:
            self._child_managers.remove(child_manager)
            logger.debug(
                f"Removed child interrupt manager (total={len(self._child_managers)})"
            )

    def propagate_to_children(self) -> None:
        """
        Propagate interrupt to all child managers (TODO-169 Day 3).

        Interrupts all tracked child managers with same mode and updated message.
        Safe to call even if no children tracked.

        Example:
            >>> # Parent interrupted by user
            >>> parent.request_interrupt(InterruptMode.GRACEFUL, InterruptSource.USER, "User Ctrl+C")
            >>> # Propagate to all children (workers, specialists)
            >>> parent.propagate_to_children()
        """
        if not self._interrupted.is_set():
            logger.debug("Parent not interrupted, skipping propagation")
            return

        if not self._child_managers:
            logger.debug("No child managers to propagate to")
            return

        reason = self._interrupt_reason
        if not reason:
            logger.warning("Parent interrupted but no reason set, skipping propagation")
            return

        logger.info(f"Propagating interrupt to {len(self._child_managers)} children...")

        for i, child in enumerate(self._child_managers):
            # Check if child already interrupted
            if child.is_interrupted():
                logger.debug(f"Child {i+1} already interrupted, skipping")
                continue

            # Propagate interrupt with updated message
            propagation_message = f"Propagated from parent: {reason.message}"
            propagation_metadata = {
                **reason.metadata,
                "propagated": True,
                "parent_source": reason.source.value,
            }

            child.request_interrupt(
                mode=reason.mode,
                source=reason.source,
                message=propagation_message,
                metadata=propagation_metadata,
            )

            logger.debug(
                f"Propagated interrupt to child {i+1} (mode={reason.mode.value})"
            )

        logger.info(f"Propagated interrupt to {len(self._child_managers)} children")

    async def request_interrupt_with_hooks(
        self,
        mode: InterruptMode,
        source: InterruptSource,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Request interrupt with PRE_INTERRUPT hook support (TODO-169 Day 4).

        Triggers PRE_INTERRUPT hooks before setting interrupt. Hooks can block
        the interrupt by returning success=False.

        Args:
            mode: How to handle interrupt (GRACEFUL or IMMEDIATE)
            source: Source of interrupt
            message: Human-readable reason
            metadata: Additional context

        Returns:
            True if interrupt was set, False if blocked by hook

        Example:
            >>> # Hook can block critical operations
            >>> result = await manager.request_interrupt_with_hooks(...)
            >>> if result:
            ...     print("Interrupt set successfully")
            ... else:
            ...     print("Interrupt blocked by hook")
        """
        if not self.hook_manager:
            # No hooks, fall back to standard request
            self.request_interrupt(mode, source, message, metadata)
            return True

        # Import here to avoid circular dependency
        from kaizen.core.autonomy.hooks.types import HookEvent

        # Execute hooks
        try:
            results = await self.hook_manager.trigger(
                event_type=HookEvent.PRE_INTERRUPT,
                agent_id="interrupt_manager",
                data={
                    "interrupt_mode": mode,
                    "interrupt_source": source,
                    "interrupt_message": message,
                    "interrupt_metadata": metadata or {},
                },
            )

            # Check if any hook blocked the interrupt
            for result in results:
                if not result.success:
                    logger.warning(
                        f"Interrupt blocked by hook: {result.error or 'No reason provided'}"
                    )
                    return False

        except Exception as e:
            logger.error(f"Error executing PRE_INTERRUPT hooks: {e}", exc_info=True)
            # Continue with interrupt even if hooks fail
            pass

        # No hooks blocked, proceed with interrupt
        self.request_interrupt(mode, source, message, metadata)
        return True

    async def execute_shutdown_with_hooks(
        self, state_manager: Any = None, agent_state: Any = None
    ) -> InterruptStatus:
        """
        Execute shutdown with POST_INTERRUPT hook support (TODO-169 Day 4).

        Triggers POST_INTERRUPT hooks after shutdown completion.

        Args:
            state_manager: Optional StateManager for checkpointing
            agent_state: Optional AgentState to checkpoint

        Returns:
            InterruptStatus with checkpoint information

        Example:
            >>> status = await manager.execute_shutdown_with_hooks(...)
            >>> print(f"Shutdown complete: checkpoint={status.checkpoint_id}")
        """
        # Execute normal shutdown
        status = await self.execute_shutdown(state_manager, agent_state)

        # Trigger POST_INTERRUPT hooks
        if self.hook_manager:
            # Import here to avoid circular dependency
            from kaizen.core.autonomy.hooks.types import HookEvent

            try:
                await self.hook_manager.trigger(
                    event_type=HookEvent.POST_INTERRUPT,
                    agent_id="interrupt_manager",
                    data={
                        "interrupted": status.interrupted,
                        "checkpoint_id": status.checkpoint_id,
                        "interrupt_reason": (
                            status.reason.to_dict() if status.reason else None
                        ),
                    },
                )
            except Exception as e:
                logger.error(
                    f"Error executing POST_INTERRUPT hooks: {e}", exc_info=True
                )
                # Don't fail shutdown if hooks fail

        return status


# Export all public types
__all__ = [
    "InterruptManager",
]
