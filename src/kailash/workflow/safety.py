"""Cycle safety and resource management framework."""

import logging
import threading
import time
from contextlib import contextmanager

import psutil

from kailash.sdk_exceptions import WorkflowExecutionError

logger = logging.getLogger(__name__)


class CycleSafetyManager:
    """Manages cycle execution safety and resource limits."""

    def __init__(self):
        """Initialize cycle safety manager."""
        self.active_cycles: dict[str, "CycleMonitor"] = {}
        self.global_memory_limit = None  # MB
        self.global_timeout = None  # seconds
        self._lock = threading.Lock()

    def set_global_limits(
        self, memory_limit: int | None = None, timeout: float | None = None
    ) -> None:
        """Set global resource limits.

        Args:
            memory_limit: Global memory limit in MB
            timeout: Global timeout in seconds
        """
        self.global_memory_limit = memory_limit
        self.global_timeout = timeout

    def start_monitoring(
        self,
        cycle_id: str,
        max_iterations: int | None = None,
        timeout: float | None = None,
        memory_limit: int | None = None,
    ) -> "CycleMonitor":
        """Start monitoring a cycle.

        Args:
            cycle_id: Cycle identifier
            max_iterations: Maximum iterations allowed
            timeout: Timeout in seconds
            memory_limit: Memory limit in MB

        Returns:
            CycleMonitor instance
        """
        with self._lock:
            if cycle_id in self.active_cycles:
                logger.warning(f"Cycle {cycle_id} already being monitored")
                return self.active_cycles[cycle_id]

            # Use global limits if not specified
            if timeout is None:
                timeout = self.global_timeout
            if memory_limit is None:
                memory_limit = self.global_memory_limit

            monitor = CycleMonitor(
                cycle_id=cycle_id,
                max_iterations=max_iterations,
                timeout=timeout,
                memory_limit=memory_limit,
            )

            self.active_cycles[cycle_id] = monitor
            monitor.start()

            return monitor

    def stop_monitoring(self, cycle_id: str) -> None:
        """Stop monitoring a cycle.

        Args:
            cycle_id: Cycle identifier
        """
        with self._lock:
            if cycle_id in self.active_cycles:
                monitor = self.active_cycles[cycle_id]
                monitor.stop()
                del self.active_cycles[cycle_id]

    def check_all_cycles(self) -> dict[str, bool]:
        """Check all active cycles for violations.

        Returns:
            Dict mapping cycle_id to violation status
        """
        violations = {}

        with self._lock:
            for cycle_id, monitor in self.active_cycles.items():
                violations[cycle_id] = monitor.check_violations()

        return violations

    def get_cycle_status(self, cycle_id: str) -> dict[str, any] | None:
        """Get status of a specific cycle.

        Args:
            cycle_id: Cycle identifier

        Returns:
            Status dict or None if not found
        """
        with self._lock:
            if cycle_id in self.active_cycles:
                return self.active_cycles[cycle_id].get_status()
        return None

    def detect_deadlocks(self) -> set[str]:
        """Detect potential deadlocks in active cycles.

        Returns:
            Set of cycle IDs that may be deadlocked
        """
        deadlocked = set()

        with self._lock:
            for cycle_id, monitor in self.active_cycles.items():
                if monitor.is_potentially_deadlocked():
                    deadlocked.add(cycle_id)

        return deadlocked


class CycleMonitor:
    """Monitors a single cycle for safety violations."""

    def __init__(
        self,
        cycle_id: str,
        max_iterations: int | None = None,
        timeout: float | None = None,
        memory_limit: int | None = None,
    ):
        """Initialize cycle monitor.

        Args:
            cycle_id: Cycle identifier
            max_iterations: Maximum iterations allowed
            timeout: Timeout in seconds
            memory_limit: Memory limit in MB
        """
        self.cycle_id = cycle_id
        self.max_iterations = max_iterations or float("inf")
        self.timeout = timeout
        self.memory_limit = memory_limit

        self.start_time = None
        self.end_time = None
        self.iteration_count = 0
        self.last_progress_time = None
        self.initial_memory = None
        self.peak_memory = 0
        self.violations = []
        self.is_active = False

        self._monitor_thread = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start monitoring."""
        self.start_time = time.time()
        self.last_progress_time = self.start_time
        self.is_active = True

        # Get initial memory usage
        process = psutil.Process()
        self.initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Start monitoring thread if we have limits
        if self.timeout or self.memory_limit:
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop, daemon=True
            )
            self._monitor_thread.start()

        logger.info(f"Started monitoring cycle: {self.cycle_id}")

    def stop(self) -> None:
        """Stop monitoring."""
        self.end_time = time.time()
        self.is_active = False
        self._stop_event.set()

        if self._monitor_thread:
            self._monitor_thread.join(timeout=1)

        logger.info(f"Stopped monitoring cycle: {self.cycle_id}")

    def record_iteration(self) -> None:
        """Record that an iteration occurred."""
        self.iteration_count += 1
        self.last_progress_time = time.time()

        # Check iteration limit
        if self.iteration_count > self.max_iterations:
            violation = f"Exceeded max iterations: {self.iteration_count} > {self.max_iterations}"
            self.violations.append(violation)
            raise WorkflowExecutionError(f"Cycle {self.cycle_id}: {violation}")

    def check_violations(self) -> bool:
        """Check for any safety violations.

        Returns:
            True if violations detected
        """
        if not self.is_active:
            return False

        current_time = time.time()

        # Check timeout
        if self.timeout and (current_time - self.start_time) > self.timeout:
            violation = f"Timeout exceeded: {current_time - self.start_time:.1f}s > {self.timeout}s"
            self.violations.append(violation)
            return True

        # Check memory limit
        if self.memory_limit:
            process = psutil.Process()
            current_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = current_memory - self.initial_memory

            if memory_increase > self.memory_limit:
                violation = f"Memory limit exceeded: {memory_increase:.1f}MB > {self.memory_limit}MB"
                self.violations.append(violation)
                return True

            # Track peak memory
            self.peak_memory = max(self.peak_memory, memory_increase)

        return False

    def is_potentially_deadlocked(self, stall_threshold: float = 60.0) -> bool:
        """Check if cycle might be deadlocked.

        Args:
            stall_threshold: Seconds without progress to consider deadlock

        Returns:
            True if potentially deadlocked
        """
        if not self.is_active or not self.last_progress_time:
            return False

        time_since_progress = time.time() - self.last_progress_time
        return time_since_progress > stall_threshold

    def get_status(self) -> dict[str, any]:
        """Get current monitor status.

        Returns:
            Status dictionary
        """
        status = {
            "cycle_id": self.cycle_id,
            "is_active": self.is_active,
            "iteration_count": self.iteration_count,
            "elapsed_time": time.time() - self.start_time if self.start_time else 0,
            "violations": self.violations,
        }

        if self.timeout:
            status["timeout"] = self.timeout
            status["time_remaining"] = max(0, self.timeout - status["elapsed_time"])

        if self.memory_limit:
            process = psutil.Process()
            current_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = current_memory - self.initial_memory

            status["memory_limit"] = self.memory_limit
            status["memory_used"] = memory_increase
            status["memory_remaining"] = max(0, self.memory_limit - memory_increase)
            status["peak_memory"] = self.peak_memory

        if self.max_iterations != float("inf"):
            status["max_iterations"] = self.max_iterations
            status["iterations_remaining"] = max(
                0, self.max_iterations - self.iteration_count
            )

        return status

    def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        check_interval = 1.0  # seconds

        while not self._stop_event.is_set() and self.is_active:
            try:
                if self.check_violations():
                    logger.error(
                        f"Cycle {self.cycle_id} safety violation: {self.violations[-1]}"
                    )
                    # Could implement automatic termination here

                self._stop_event.wait(check_interval)

            except Exception as e:
                logger.error(f"Error in monitor loop for cycle {self.cycle_id}: {e}")


@contextmanager
def monitored_cycle(safety_manager: CycleSafetyManager, cycle_id: str, **limits):
    """Context manager for monitored cycle execution.

    Args:
        safety_manager: CycleSafetyManager instance
        cycle_id: Cycle identifier
        **limits: Resource limits (max_iterations, timeout, memory_limit)

    Yields:
        CycleMonitor instance
    """
    monitor = safety_manager.start_monitoring(cycle_id, **limits)

    try:
        yield monitor
    finally:
        safety_manager.stop_monitoring(cycle_id)


class TimeoutHandler:
    """Handles timeout for cycle execution."""

    def __init__(self, timeout: float):
        """Initialize timeout handler.

        Args:
            timeout: Timeout in seconds
        """
        self.timeout = timeout
        self.timer = None
        self.timed_out = False

    def __enter__(self):
        """Start timeout timer."""

        def timeout_handler():
            self.timed_out = True
            logger.error(f"Cycle execution timed out after {self.timeout}s")

        self.timer = threading.Timer(self.timeout, timeout_handler)
        self.timer.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cancel timeout timer."""
        if self.timer:
            self.timer.cancel()

        if self.timed_out and exc_type is None:
            raise WorkflowExecutionError(
                f"Cycle execution timed out after {self.timeout}s"
            )
