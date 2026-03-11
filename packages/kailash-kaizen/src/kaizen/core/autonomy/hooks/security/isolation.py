"""
Hook execution isolation (SECURITY FIX #5).

Provides resource limits and process isolation for hook execution to prevent:
- Resource exhaustion (memory, CPU)
- Agent crashes from malicious hooks
- Cross-hook interference

SECURITY: CWE-265 (Privilege Issues)
"""

import asyncio
import logging
import multiprocessing
import sys
import time
from typing import Any

from ..manager import HookEvent, HookManager, HookPriority
from ..protocol import HookHandler
from ..types import HookContext, HookResult

logger = logging.getLogger(__name__)


class ResourceLimits:
    """
    Resource limits for hook execution (SECURITY FIX #5).

    Applies OS-level resource limits to prevent resource exhaustion:
    - Memory limit (prevents OOM attacks)
    - CPU time limit (prevents infinite loops)
    - File size limit (prevents disk exhaustion)

    Note: Resource limits are Unix-specific. On Windows, only process isolation
    is provided (no resource limits).

    Example:
        >>> from kaizen.core.autonomy.hooks.security import ResourceLimits
        >>>
        >>> # Create resource limits
        >>> limits = ResourceLimits(
        >>>     max_memory_mb=100,      # 100MB memory limit
        >>>     max_cpu_seconds=5,      # 5 second CPU limit
        >>>     max_file_size_mb=10     # 10MB file size limit
        >>> )
        >>>
        >>> # Apply limits (Unix only)
        >>> limits.apply()  # Raises warning on Windows

    SECURITY FIX #5:
    - Prevents memory exhaustion attacks (OOM)
    - Prevents CPU exhaustion (infinite loops)
    - Prevents disk exhaustion (large file writes)
    """

    def __init__(
        self,
        max_memory_mb: int = 100,
        max_cpu_seconds: int = 5,
        max_file_size_mb: int = 10,
    ):
        """
        Initialize resource limits.

        Args:
            max_memory_mb: Maximum memory in MB (default: 100MB)
            max_cpu_seconds: Maximum CPU seconds (default: 5 seconds)
            max_file_size_mb: Maximum file size in MB (default: 10MB)

        Example:
            >>> limits = ResourceLimits(max_memory_mb=50, max_cpu_seconds=3)
        """
        self.max_memory_mb = max_memory_mb
        self.max_cpu_seconds = max_cpu_seconds
        self.max_file_size_mb = max_file_size_mb

    def apply(self) -> None:
        """
        Apply resource limits to current process.

        Uses resource.setrlimit() on Unix systems. On Windows, logs a warning
        as resource limits are not supported.

        Raises:
            ImportError: If resource module is not available (Windows)
            OSError: If setrlimit fails (insufficient privileges)

        Example:
            >>> limits = ResourceLimits(max_memory_mb=100)
            >>> limits.apply()  # Applies limits on Unix, warns on Windows
        """
        # Check platform support
        if sys.platform == "win32":
            logger.warning(
                "SECURITY: Resource limits not supported on Windows. "
                "Process isolation will be used without resource limits."
            )
            return

        try:
            import resource

            # Memory limit (virtual address space)
            max_memory_bytes = self.max_memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (max_memory_bytes, max_memory_bytes))
            logger.debug(f"Applied memory limit: {self.max_memory_mb}MB")

            # CPU time limit
            resource.setrlimit(
                resource.RLIMIT_CPU, (self.max_cpu_seconds, self.max_cpu_seconds)
            )
            logger.debug(f"Applied CPU limit: {self.max_cpu_seconds} seconds")

            # File size limit
            max_file_bytes = self.max_file_size_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_FSIZE, (max_file_bytes, max_file_bytes))
            logger.debug(f"Applied file size limit: {self.max_file_size_mb}MB")

        except ImportError:
            logger.warning(
                "SECURITY: resource module not available. "
                "Resource limits cannot be applied."
            )
        except OSError as e:
            logger.error(f"SECURITY: Failed to apply resource limits: {e}")
            raise


class IsolatedHookExecutor:
    """
    Execute hooks in isolated processes with resource limits (SECURITY FIX #5).

    Features:
    - Process isolation (separate address space)
    - Resource limits (memory, CPU, file size)
    - Timeout enforcement
    - Graceful failure handling
    - Cross-platform support (Unix + Windows)

    Example:
        >>> from kaizen.core.autonomy.hooks.security import IsolatedHookExecutor, ResourceLimits
        >>> from kaizen.core.autonomy.hooks.types import HookContext, HookResult
        >>>
        >>> # Create executor with resource limits
        >>> limits = ResourceLimits(max_memory_mb=100, max_cpu_seconds=5)
        >>> executor = IsolatedHookExecutor(limits=limits)
        >>>
        >>> # Execute hook in isolated process
        >>> context = HookContext(...)
        >>> result = await executor.execute_isolated(my_hook, context, timeout=10.0)
        >>>
        >>> if result.success:
        >>>     print("Hook executed successfully")
        >>> else:
        >>>     print(f"Hook failed: {result.error}")

    SECURITY FIX #5:
    - Prevents malicious hooks from crashing agent
    - Prevents resource exhaustion attacks
    - Isolates hook execution from main process
    """

    def __init__(self, limits: ResourceLimits):
        """
        Initialize isolated hook executor.

        Args:
            limits: Resource limits to apply in child process

        Example:
            >>> limits = ResourceLimits(max_memory_mb=50)
            >>> executor = IsolatedHookExecutor(limits=limits)
        """
        self.limits = limits

    async def execute_isolated(
        self,
        handler: HookHandler,
        context: HookContext,
        timeout: float,
    ) -> HookResult:
        """
        Execute hook in isolated process with resource limits.

        Creates a child process, applies resource limits, executes hook, and
        returns result. If hook times out or crashes, returns error result.

        Args:
            handler: Hook handler to execute
            context: Hook context (must be picklable)
            timeout: Maximum execution time in seconds

        Returns:
            HookResult with success/failure status and metadata

        Example:
            >>> result = await executor.execute_isolated(
            >>>     handler=my_hook,
            >>>     context=context,
            >>>     timeout=5.0
            >>> )
            >>> print(f"Success: {result.success}, Duration: {result.duration_ms}ms")

        SECURITY FIX #5:
        - Hook runs in separate process (isolated address space)
        - Resource limits prevent exhaustion attacks
        - Timeout prevents infinite loops
        - Graceful failure handling prevents agent crashes
        """
        handler_name = getattr(handler, "name", repr(handler))

        # Create queue for inter-process communication
        queue: multiprocessing.Queue = multiprocessing.Queue()

        # Define worker function (runs in child process)
        def _run_hook():
            """
            Worker function that runs in isolated child process.

            Applies resource limits and executes hook.
            """
            try:
                # STEP 1: Apply resource limits
                self.limits.apply()

                # STEP 2: Execute hook
                start_time = time.perf_counter()
                result = asyncio.run(handler.handle(context))
                duration_ms = (time.perf_counter() - start_time) * 1000

                # STEP 3: Add timing metadata
                result.duration_ms = duration_ms

                # STEP 4: Send result to parent process
                queue.put(("success", result))

            except Exception as e:
                # Send error to parent process
                error_msg = f"Hook error: {str(e)}"
                queue.put(("error", error_msg))

        # Start isolated process
        process = multiprocessing.Process(target=_run_hook)
        process.start()

        # Wait for completion with timeout
        process.join(timeout=timeout)

        # Check if process is still running (timeout)
        if process.is_alive():
            logger.warning(
                f"SECURITY: Hook timeout in isolated process - {handler_name}"
            )
            process.terminate()
            process.join(timeout=1.0)  # Give it 1 second to terminate gracefully

            # Force kill if still alive
            if process.is_alive():
                process.kill()
                process.join()

            return HookResult(
                success=False,
                error=f"Hook timeout in isolated process: {handler_name}",
                duration_ms=timeout * 1000,
            )

        # Check exit code
        if process.exitcode != 0:
            logger.error(
                f"SECURITY: Hook process crashed - {handler_name} (exit code: {process.exitcode})"
            )
            return HookResult(
                success=False,
                error=f"Hook process crashed (exit code: {process.exitcode})",
                duration_ms=0.0,
            )

        # Get result from queue
        try:
            if not queue.empty():
                status, result = queue.get(timeout=1.0)

                if status == "success":
                    logger.debug(
                        f"Hook executed successfully in isolated process: {handler_name}"
                    )
                    return result
                else:
                    # Error result
                    logger.error(f"Hook failed in isolated process: {result}")
                    return HookResult(success=False, error=result, duration_ms=0.0)
            else:
                # Queue empty - hook did not return result
                logger.error(f"SECURITY: Hook did not return result - {handler_name}")
                return HookResult(
                    success=False,
                    error="Hook did not return result",
                    duration_ms=0.0,
                )

        except Exception as e:
            logger.error(f"SECURITY: Failed to retrieve hook result: {e}")
            return HookResult(
                success=False, error=f"Failed to retrieve result: {e}", duration_ms=0.0
            )


class IsolatedHookManager(HookManager):
    """
    HookManager with process isolation and resource limits (SECURITY FIX #5).

    Extends HookManager to execute hooks in isolated processes with resource
    limits. This prevents malicious or buggy hooks from:
    - Crashing the agent
    - Exhausting system resources
    - Interfering with other hooks

    Features:
    - Process isolation via multiprocessing
    - Configurable resource limits (memory, CPU, file size)
    - Optional isolation (can be disabled for backward compatibility)
    - Graceful degradation on Windows (no resource limits)
    - Comprehensive error handling

    Example:
        >>> from kaizen.core.autonomy.hooks.security import IsolatedHookManager, ResourceLimits
        >>> from kaizen.core.autonomy.hooks.types import HookEvent, HookPriority
        >>>
        >>> # Create manager with isolation and resource limits
        >>> limits = ResourceLimits(max_memory_mb=100, max_cpu_seconds=5)
        >>> manager = IsolatedHookManager(
        >>>     limits=limits,
        >>>     enable_isolation=True  # Enable process isolation
        >>> )
        >>>
        >>> # Register hooks (executed in isolated processes)
        >>> manager.register(
        >>>     HookEvent.POST_AGENT_LOOP,
        >>>     my_hook,
        >>>     priority=HookPriority.NORMAL
        >>> )
        >>>
        >>> # Trigger hooks (isolated execution)
        >>> results = await manager.trigger(HookEvent.POST_AGENT_LOOP, context)

    SECURITY FIX #5:
    - Prevents malicious hooks from compromising agent
    - Isolates hook execution in separate processes
    - Applies resource limits to prevent exhaustion attacks
    - Maintains backward compatibility with non-isolated mode
    """

    def __init__(
        self,
        limits: ResourceLimits | None = None,
        enable_isolation: bool = True,
    ):
        """
        Initialize isolated hook manager.

        Args:
            limits: Resource limits (default: 100MB memory, 5s CPU, 10MB file size)
            enable_isolation: Whether to enable process isolation (default: True)

        Example:
            >>> # With custom limits
            >>> limits = ResourceLimits(max_memory_mb=50, max_cpu_seconds=3)
            >>> manager = IsolatedHookManager(limits=limits, enable_isolation=True)
            >>>
            >>> # With default limits
            >>> manager = IsolatedHookManager()  # Uses defaults
            >>>
            >>> # Disable isolation (backward compatibility)
            >>> manager = IsolatedHookManager(enable_isolation=False)
        """
        super().__init__()
        self.limits = limits or ResourceLimits()
        self.enable_isolation = enable_isolation
        self.executor = IsolatedHookExecutor(self.limits)

        # Log isolation status
        if self.enable_isolation:
            logger.info(
                f"SECURITY: Hook isolation enabled - "
                f"Memory: {self.limits.max_memory_mb}MB, "
                f"CPU: {self.limits.max_cpu_seconds}s, "
                f"File: {self.limits.max_file_size_mb}MB"
            )
        else:
            logger.warning(
                "SECURITY: Hook isolation DISABLED - "
                "Hooks will execute with full agent privileges"
            )

    async def _execute_hook(
        self, handler: HookHandler, context: HookContext, timeout: float
    ) -> HookResult:
        """
        Execute hook with optional isolation (SECURITY FIX #5).

        Overrides HookManager._execute_hook to add process isolation.

        Args:
            handler: Hook handler to execute
            context: Hook context
            timeout: Maximum execution time in seconds

        Returns:
            HookResult with success/failure status

        SECURITY FIX #5:
        - Executes hook in isolated process if enable_isolation=True
        - Falls back to normal execution if isolation fails
        - Maintains backward compatibility with non-isolated mode
        """
        handler_name = getattr(handler, "name", repr(handler))

        # Check if isolation is enabled
        if not self.enable_isolation:
            # Use parent implementation (no isolation)
            return await super()._execute_hook(handler, context, timeout)

        # Execute in isolated process
        try:
            logger.debug(f"Executing hook in isolated process: {handler_name}")
            result = await self.executor.execute_isolated(handler, context, timeout)

            # Update stats
            self._update_stats(handler_name, result.duration_ms, success=result.success)

            return result

        except Exception as e:
            # Isolation failed - log error and fall back to normal execution
            logger.error(
                f"SECURITY: Hook isolation failed for {handler_name}, "
                f"falling back to normal execution: {e}"
            )

            # Fall back to parent implementation
            return await super()._execute_hook(handler, context, timeout)


# Export public API
__all__ = [
    "ResourceLimits",
    "IsolatedHookExecutor",
    "IsolatedHookManager",
]
