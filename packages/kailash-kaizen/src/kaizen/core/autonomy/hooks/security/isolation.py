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
import os
import pickle
import sys
import time
from queue import Empty as QueueEmpty
from typing import Any

from kaizen.utils.credential_scrub import scrub_local_error, scrub_remote_error

from ..manager import HookEvent, HookManager, HookPriority, safe_handler_name
from ..protocol import HookHandler
from ..types import HookContext, HookResult

logger = logging.getLogger(__name__)

#: Start method used for hook isolation, selected EXPLICITLY rather than
#: inherited from the platform default (issue #2014).
#:
#: ``spawn`` is the default on macOS and Windows and is available everywhere;
#: ``fork`` is the default only on Linux. Pinning ``spawn`` on every platform
#: means the picklability requirement below is uniform instead of
#: platform-dependent -- a hook that isolates on the developer's Linux box now
#: isolates identically on the operator's macOS box, or fails loudly on both.
_ISOLATION_START_METHOD = "spawn"

#: Wall-clock budget for the child interpreter to boot, import the handler's
#: module, and signal readiness. This is deliberately NOT charged against the
#: caller's hook timeout: under ``spawn`` the child pays a full interpreter
#: startup plus import cost, which routinely exceeds the sub-second per-hook
#: timeouts ``HookManager.trigger`` defaults to.
DEFAULT_STARTUP_TIMEOUT = 30.0

#: Queue poll granularity while waiting for a child message.
_POLL_INTERVAL = 0.02

#: Grace period to drain a message the child wrote immediately before exiting.
_DRAIN_TIMEOUT = 0.5

#: Grace period for a terminated child to actually die.
_REAP_TIMEOUT = 1.0


class HookIsolationError(RuntimeError):
    """
    Raised when hook process isolation cannot be established (issue #2014).

    This error means the SECURITY CONTROL is unavailable -- not that the hook
    failed. It is raised INSTEAD of running the hook, never alongside it: a
    caller that asked for isolation and cannot get it must be told, because the
    alternative (running caller-supplied hook code with full agent privileges
    while reporting success) is a silent downgrade of the control to OFF.

    Attributes:
        handler_name: Safe name of the hook whose isolation could not be set up
        reason: Why isolation could not be established

    Example:
        >>> try:
        >>>     await manager.trigger(HookEvent.PRE_AGENT_LOOP, "agent-1", {})
        >>> except HookIsolationError as e:
        >>>     print(f"{e.handler_name} cannot be isolated: {e.reason}")
    """

    def __init__(self, handler_name: str, reason: str):
        self.handler_name = handler_name
        self.reason = reason
        super().__init__(
            f"Hook isolation could not be established for {handler_name}: {reason}"
        )


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

    def apply(self) -> list[str]:
        """
        Apply resource limits to current process.

        Each limit is applied INDEPENDENTLY, because platform support is
        per-resource rather than all-or-nothing: macOS accepts ``RLIMIT_CPU``
        and ``RLIMIT_FSIZE`` but refuses ``RLIMIT_AS`` outright, so applying
        them as one block would discard the two limits the platform does
        enforce along with the one it does not.

        A requested cap that exceeds the environment's existing HARD limit is
        clamped down to that hard limit rather than treated as an error. The
        environment is already stricter than what was asked for, which satisfies
        the intent of the cap; refusing to run would break isolation inside
        exactly the hardened containers that most need it, and the workaround an
        operator would reach for is turning isolation off entirely.

        After that clamp every value is within the hard limit, so a refusal from
        the kernel means it does not implement the resource at all (macOS and
        ``RLIMIT_AS``). That is REPORTED rather than raised: the limits the
        platform does support still apply, and process isolation itself -- the
        primary control -- is unaffected by a missing cap.

        Both the soft and the hard limit are set. Lowering the hard limit is
        what prevents the hook's own code from raising its soft limit back up,
        and it is irreversible for the process that does it -- which is correct
        here, because the process that does it is a disposable child. Callers
        MUST NOT invoke this on a process they intend to keep using.

        Returns:
            Names of the limits that could NOT be enforced (empty list when all
            applied). The caller is expected to surface these: an unenforced
            limit is a security control that is OFF, and the child's own log
            records do not reach the parent's handlers under ``spawn``.

        Example:
            >>> limits = ResourceLimits(max_memory_mb=100)
            >>> unenforced = limits.apply()
            >>> if unenforced:
            >>>     print(f"NOT enforced on this platform: {unenforced}")
        """
        all_limits = ["max_memory_mb", "max_cpu_seconds", "max_file_size_mb"]

        # Check platform support
        if sys.platform == "win32":
            logger.warning(
                "SECURITY: Resource limits not supported on Windows. "
                "Process isolation will be used without resource limits."
            )
            return all_limits

        try:
            import resource
        except ImportError:
            logger.warning(
                "SECURITY: resource module not available. "
                "Resource limits cannot be applied."
            )
            return all_limits

        unenforced: list[str] = []

        for label, rlimit_name, value in (
            ("max_memory_mb", "RLIMIT_AS", self.max_memory_mb * 1024 * 1024),
            ("max_cpu_seconds", "RLIMIT_CPU", self.max_cpu_seconds),
            ("max_file_size_mb", "RLIMIT_FSIZE", self.max_file_size_mb * 1024 * 1024),
        ):
            rlimit = getattr(resource, rlimit_name, None)
            if rlimit is None:
                # The platform's resource module does not define this resource.
                unenforced.append(label)
                continue

            _soft, hard = resource.getrlimit(rlimit)

            # An environment that is ALREADY stricter than the requested cap
            # satisfies the intent of the cap, so clamp to it rather than
            # failing. Refusing to run here would mean isolation breaks inside
            # exactly the hardened containers that need it most, and the
            # workaround an operator would reach for is enable_isolation=False.
            requested = value
            if hard != resource.RLIM_INFINITY and value > hard:
                value = hard
                logger.info(
                    "Resource limit %s requested %s but the environment caps it "
                    "at %s; using the stricter environment value",
                    label,
                    requested,
                    hard,
                )

            try:
                # Both soft and hard are set: lowering the HARD limit is what
                # stops the hook's own code from raising its soft limit back up.
                # The child is disposable, so the irreversibility is intended.
                resource.setrlimit(rlimit, (value, value))
            except (OSError, ValueError) as e:
                # ``scrub_local_error``, not ``scrub_remote_error``: this comes
                # from ``resource.setrlimit``, an in-process OS call, so the
                # conservative preset is right -- it keeps the shape-only rules
                # OFF and preserves the errno text, which IS the diagnostic.
                #
                # The credential risk today is nil (setrlimit takes ints, not
                # caller strings). It is scrubbed anyway because the raw-
                # exception-in-a-log-argument SHAPE is one edit away from being
                # a leak: the moment this block covers a limit derived from a
                # caller-supplied value, the sink is already wrong and nothing
                # would flag it.
                #
                # The clamp above guarantees the value is within the hard limit,
                # so a refusal here means the kernel does not implement this
                # resource at all (macOS and RLIMIT_AS). That is reported, not
                # raised: the remaining limits still apply, and process
                # isolation itself -- the primary control -- is unaffected.
                unenforced.append(label)
                logger.warning(
                    "SECURITY: %s (%s) is not enforceable on this platform: %s",
                    label,
                    rlimit_name,
                    scrub_local_error(e),
                )
            else:
                logger.debug("Applied resource limit %s: %s", label, value)

        if unenforced:
            logger.warning(
                "SECURITY: Hook process isolation is ACTIVE, but these resource "
                "limits are NOT enforced on this platform: %s. The hook is "
                "confined to its own process but is not capped on those "
                "resources.",
                ", ".join(unenforced),
            )

        return unenforced


def _isolated_hook_worker(
    limits: ResourceLimits,
    handler: HookHandler,
    context: HookContext,
    result_queue: Any,
) -> None:
    """
    Entry point executed inside the isolated child process (issue #2014).

    MUST stay at MODULE SCOPE. Under the ``spawn`` start method the child is a
    fresh interpreter, so ``multiprocessing`` transfers the target by pickling
    it -- and pickle stores a function by its ``module.qualname``, not its code.
    A nested or closure worker cannot be pickled at all, which is precisely how
    isolation used to fail: ``Process.start()`` raised
    ``Can't get local object 'IsolatedHookExecutor.execute_isolated.<locals>._run_hook'``
    and the caller swallowed it and ran the hook in-process instead.

    The worker speaks a 3-tuple protocol on ``result_queue``:
    ``(status, payload, worker_pid)`` where status is one of
    ``ready`` / ``success`` / ``error``. ``ready`` is sent once the sandbox is
    fully in place and BEFORE any caller-supplied code runs, so the parent can
    (a) confirm a real child is alive, (b) charge interpreter startup to a
    separate budget instead of the hook's timeout, and (c) learn which resource
    limits this platform refused to enforce.

    The ``ready`` payload carries that unenforced-limit list because the child's
    own ``logger`` records do NOT reach the parent's handlers: under ``spawn``
    the child is a fresh interpreter with a default, unconfigured logging setup,
    so a warning emitted here would be written to nothing. The parent re-logs
    it against its own handlers instead.

    Args:
        limits: Resource limits to apply before running any hook code
        handler: Hook handler to execute
        context: Hook context to pass to the handler
        result_queue: Queue back to the parent process
    """
    worker_pid = os.getpid()

    try:
        unenforced = limits.apply()
    except Exception as e:
        # Reported INSTEAD of ``ready``: the sandbox was not established, so the
        # parent must treat this as an isolation failure and never run the hook.
        # ``scrub_local_error`` matches ``ResourceLimits.apply``: this is an
        # in-process OS call whose errno text IS the diagnostic.
        result_queue.put(
            (
                "error",
                f"Resource limits could not be applied: {scrub_local_error(e)}",
                worker_pid,
            )
        )
        return

    # Sent before any caller-supplied code runs: it is the parent's proof that a
    # distinct process exists and that the sandbox is established.
    result_queue.put(("ready", unenforced, worker_pid))

    try:
        start_time = time.perf_counter()
        result = asyncio.run(handler.handle(context))
        result.duration_ms = (time.perf_counter() - start_time) * 1000
    except Exception as e:
        # ``handler.handle`` is CALLER-SUPPLIED code, so ``e`` is whatever it
        # raised -- an HTTP client, a DB driver, an SDK -- and this string
        # crosses the process boundary into BOTH a parent log line and the
        # returned ``HookResult.error``. Scrubbed here, at the point it is
        # built, so neither consumer can re-leak it.
        result_queue.put(("error", f"Hook error: {scrub_remote_error(e)}", worker_pid))
        return

    try:
        # Pickled explicitly rather than left to the queue's feeder thread: a
        # feeder-thread pickling failure surfaces as a traceback on the child's
        # stderr and a SILENTLY dropped item, which the parent would then
        # report as the unrelated "did not return a result".
        pickle.dumps(result)
    except Exception as e:
        result_queue.put(
            (
                "error",
                f"Hook result cannot cross the process boundary: {scrub_remote_error(e)}",
                worker_pid,
            )
        )
        return

    result_queue.put(("success", result, worker_pid))


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

    def __init__(
        self,
        limits: ResourceLimits,
        startup_timeout: float = DEFAULT_STARTUP_TIMEOUT,
    ):
        """
        Initialize isolated hook executor.

        Args:
            limits: Resource limits to apply in child process
            startup_timeout: Seconds allowed for the child interpreter to boot
                and signal readiness, charged SEPARATELY from the per-hook
                timeout (default: 30s)

        Example:
            >>> limits = ResourceLimits(max_memory_mb=50)
            >>> executor = IsolatedHookExecutor(limits=limits)
        """
        self.limits = limits
        self.startup_timeout = startup_timeout

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
            handler: Hook handler to execute. MUST be picklable, which under the
                ``spawn`` start method means its class must be importable at
                module scope -- a lambda, a closure, or a locally-defined
                function cannot be isolated.
            context: Hook context (must be picklable)
            timeout: Maximum hook execution time in seconds, measured from the
                moment the child signals readiness (interpreter startup is
                charged to ``startup_timeout`` instead)

        Returns:
            HookResult with success/failure status and metadata

        Raises:
            HookIsolationError: If the isolated process cannot be started, does
                not signal readiness, or reports the parent's own PID. The hook
                is NOT executed in that case -- see issue #2014.

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
        # ``handler_name`` reaches the log lines below AND the returned
        # ``HookResult.error`` on the timeout and crash paths, so it must not be
        # able to carry caller state; see ``safe_handler_name``.
        handler_name = getattr(handler, "name", safe_handler_name(handler))
        parent_pid = os.getpid()

        # Explicit context, never the platform default: see
        # ``_ISOLATION_START_METHOD``. The queue must come from the SAME context
        # as the process that receives it.
        mp_context = multiprocessing.get_context(_ISOLATION_START_METHOD)
        result_queue = mp_context.Queue()

        process = mp_context.Process(
            target=_isolated_hook_worker,
            args=(self.limits, handler, context, result_queue),
            name=f"kaizen-isolated-hook-{handler_name}",
        )

        try:
            # Under ``spawn`` the handler, context and limits are pickled HERE,
            # before the child is launched, so an unpicklable handler raises
            # synchronously and leaves no orphan process behind.
            process.start()
        except Exception as e:
            result_queue.close()
            raise HookIsolationError(
                handler_name,
                f"the isolated process could not be started under the "
                f"'{_ISOLATION_START_METHOD}' start method "
                f"({scrub_remote_error(e)}). The handler and context must be "
                f"picklable: define the handler class at module scope rather "
                f"than as a lambda, closure, or locally-defined function.",
            ) from e

        try:
            # The supervision loop blocks on a queue and on process reaping;
            # running it in a worker thread keeps the caller's event loop free.
            return await asyncio.to_thread(
                self._supervise,
                process,
                result_queue,
                handler_name,
                timeout,
                parent_pid,
            )
        finally:
            self._reap(process)
            result_queue.close()

    def _supervise(
        self,
        process: Any,
        result_queue: Any,
        handler_name: str,
        timeout: float,
        parent_pid: int,
    ) -> HookResult:
        """
        Supervise the isolated process from the parent (runs in a worker thread).

        Two phases with separate budgets: readiness (``startup_timeout``) then
        the hook itself (``timeout``).

        Raises:
            HookIsolationError: If readiness never arrives or the worker reports
                the parent's PID -- both mean the control is not in place.
        """
        # PHASE 1: readiness. Absence here means no isolated process is running
        # our worker, so there is nothing to fall back to except the very
        # in-process execution this control exists to prevent.
        message, reason = self._receive(process, result_queue, self.startup_timeout)
        if message is None:
            raise HookIsolationError(
                handler_name,
                f"the isolated process did not signal readiness within "
                f"{self.startup_timeout}s (reason: {reason}, "
                f"exit code: {process.exitcode})",
            )

        status, payload, worker_pid = message
        if status == "error":
            # The child reached its entry point but could not establish the
            # sandbox (resource limits refused). The control is not in place, so
            # the hook must not run.
            raise HookIsolationError(
                handler_name,
                f"the isolated process could not establish its sandbox: {payload}",
            )
        if status != "ready":
            raise HookIsolationError(
                handler_name,
                f"the isolated process sent {status!r} before signalling "
                f"readiness (isolation protocol violation)",
            )
        if worker_pid == parent_pid:
            # Belt and braces: if this ever holds, the hook is running with full
            # agent privileges and the control is OFF.
            raise HookIsolationError(
                handler_name,
                f"the hook worker reported the parent PID ({parent_pid}); "
                f"the hook is NOT isolated",
            )

        logger.debug(
            "Hook %s isolated in process %s (parent %s)",
            handler_name,
            worker_pid,
            parent_pid,
        )

        if payload:
            # Re-logged HERE rather than left to the child: under ``spawn`` the
            # child's logging is unconfigured, so its own warning went nowhere.
            logger.warning(
                "SECURITY: Hook %s is isolated in process %s, but these resource "
                "limits are NOT enforced on this platform: %s",
                handler_name,
                worker_pid,
                ", ".join(payload),
            )

        # PHASE 2: the hook's own result.
        message, reason = self._receive(process, result_queue, timeout)

        if message is None and reason == "timeout":
            logger.warning(
                "SECURITY: Hook timeout in isolated process - %s", handler_name
            )
            return HookResult(
                success=False,
                error=f"Hook timeout in isolated process: {handler_name}",
                duration_ms=timeout * 1000,
            )

        if message is None:
            # Child exited without a result: crash, kill, or resource limit.
            process.join(timeout=_REAP_TIMEOUT)
            logger.error(
                "SECURITY: Hook process exited without a result - %s (exit code: %s)",
                handler_name,
                process.exitcode,
            )
            return HookResult(
                success=False,
                error=(
                    f"Hook process exited without returning a result "
                    f"(exit code: {process.exitcode})"
                ),
                duration_ms=0.0,
            )

        status, payload, _worker_pid = message

        if status == "success":
            logger.debug(
                "Hook executed successfully in isolated process: %s", handler_name
            )
            return payload

        logger.error("Hook failed in isolated process: %s", payload)
        return HookResult(success=False, error=payload, duration_ms=0.0)

    @staticmethod
    def _receive(
        process: Any, result_queue: Any, budget: float
    ) -> tuple[tuple[str, Any, int] | None, str]:
        """
        Wait up to ``budget`` seconds for one message from the child.

        Polls rather than blocking on ``Queue.get(timeout=budget)`` so that a
        child which dies without writing is noticed immediately instead of
        after the full budget. Reads BEFORE joining, so a result larger than the
        pipe buffer cannot deadlock the child inside its own flush.

        Returns:
            ``(message, "message")`` on success, or ``(None, "timeout")`` /
            ``(None, "exited")`` when no message arrived.
        """
        deadline = time.monotonic() + budget

        while True:
            try:
                return result_queue.get(timeout=_POLL_INTERVAL), "message"
            except QueueEmpty:
                pass

            if not process.is_alive():
                # Last chance: the child may have written just before exiting.
                try:
                    return result_queue.get(timeout=_DRAIN_TIMEOUT), "message"
                except QueueEmpty:
                    return None, "exited"

            if time.monotonic() >= deadline:
                return None, "timeout"

    @staticmethod
    def _reap(process: Any) -> None:
        """Terminate, kill, and release the child process. Never raises."""
        if process.is_alive():
            process.terminate()
            process.join(timeout=_REAP_TIMEOUT)

        if process.is_alive():
            process.kill()
            process.join(timeout=_REAP_TIMEOUT)

        if process.exitcode is not None:
            # ``close()`` releases the process handle/fds; it is only legal once
            # the child has actually been reaped.
            process.close()


class IsolatedHookManager(HookManager):
    """
    HookManager with process isolation and resource limits (SECURITY FIX #5).

    Extends HookManager to execute hooks in isolated processes with resource
    limits. This prevents malicious or buggy hooks from:
    - Crashing the agent
    - Exhausting system resources
    - Interfering with other hooks

    Features:
    - Process isolation via multiprocessing, under an explicitly-pinned
      ``spawn`` start method on every platform
    - Configurable resource limits (memory, CPU, file size), each applied
      independently and each reported when the platform refuses to enforce it
    - Optional isolation, disabled only by explicit ``enable_isolation=False``
    - Fails CLOSED: if isolation cannot be established the hook is not run and
      ``HookIsolationError`` is raised (issue #2014)

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
    - Never downgrades itself to non-isolated execution (issue #2014)

    Note:
        Handlers registered on an isolating manager MUST be picklable, because
        ``spawn`` transfers them to a fresh interpreter by pickle. In practice
        that means the handler is a class or function defined at MODULE scope.
        A lambda, a closure, or a function defined inside a test body cannot be
        isolated and will raise ``HookIsolationError`` rather than silently
        running unisolated.
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

        Raises:
            HookIsolationError: If isolation was requested but could not be
                established. The hook is NOT executed in that case.

        SECURITY FIX #5:
        - Executes hook in isolated process if enable_isolation=True
        - Fails CLOSED if isolation cannot be established (issue #2014)
        - Non-isolated execution remains available, but only by explicit opt-out
        """
        handler_name = getattr(handler, "name", safe_handler_name(handler))

        # Check if isolation is enabled
        if not self.enable_isolation:
            # Use parent implementation (no isolation)
            return await super()._execute_hook(handler, context, timeout)

        # Execute in isolated process.
        #
        # There is deliberately NO fallback to ``super()._execute_hook`` here
        # (issue #2014). Running the hook in-process when isolation fails is not
        # a degraded mode of this control -- it is the control switched OFF,
        # applied to the exact code the control exists to contain, while the
        # caller is handed a successful-looking HookResult. The failure it hid
        # was total: under the ``spawn`` start method the old closure-based
        # worker could never be pickled, so isolation failed on EVERY call on
        # macOS and Windows and every hook ran with full agent privileges.
        #
        # A caller that genuinely wants non-isolated execution asks for it by
        # constructing the manager with ``enable_isolation=False``, which is
        # visible at the call site and logged as a warning at construction.
        try:
            logger.debug(f"Executing hook in isolated process: {handler_name}")
            result = await self.executor.execute_isolated(handler, context, timeout)
        except HookIsolationError as e:
            # Already typed and already scrubbed at construction; re-logged so
            # the operator sees WHICH control failed, then propagated.
            logger.error(
                "SECURITY: Hook isolation could not be established for %s; "
                "the hook was NOT executed: %s",
                handler_name,
                e.reason,
            )
            self._update_stats(handler_name, 0, success=False)
            raise
        except Exception as e:
            # Anything else from ``execute_isolated`` is an isolation-machinery
            # failure rather than a hook failure (hook exceptions come back as
            # an unsuccessful HookResult, not as a raise). It is converted to
            # the typed error so callers have ONE exception type to handle, and
            # scrubbed because ``execute_isolated`` drives CALLER-SUPPLIED hook
            # code and this text reaches both a log line and the raised message.
            logger.error(
                "SECURITY: Hook isolation failed for %s; the hook was NOT "
                "executed: %s",
                handler_name,
                scrub_remote_error(e),
            )
            self._update_stats(handler_name, 0, success=False)
            raise HookIsolationError(
                handler_name,
                f"the isolation machinery failed: {scrub_remote_error(e)}",
            ) from e

        # Update stats
        self._update_stats(handler_name, result.duration_ms, success=result.success)

        return result


# Export public API
__all__ = [
    "DEFAULT_STARTUP_TIMEOUT",
    "HookIsolationError",
    "ResourceLimits",
    "IsolatedHookExecutor",
    "IsolatedHookManager",
]
