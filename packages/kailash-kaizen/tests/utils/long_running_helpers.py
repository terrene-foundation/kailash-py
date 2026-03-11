"""
Long-running test helpers for multi-hour autonomous sessions.

Provides:
- Progress heartbeat monitoring (every 10 minutes)
- Timeout guards (max 5 hours)
- Session state snapshots
- Interrupt/resume validation
"""

import signal
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Optional


@dataclass
class SessionSnapshot:
    """Snapshot of long-running session state."""

    timestamp: datetime
    iteration: int
    memory_count: int
    checkpoint_count: int
    total_tokens: int
    cost_usd: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"SessionSnapshot(time={self.timestamp.strftime('%H:%M:%S')}, "
            f"iter={self.iteration}, mem={self.memory_count}, "
            f"ckpt={self.checkpoint_count}, tokens={self.total_tokens}, "
            f"cost=${self.cost_usd:.4f})"
        )


class ProgressMonitor:
    """Monitor progress of long-running tests with heartbeats."""

    def __init__(
        self,
        heartbeat_interval: int = 600,  # 10 minutes
        max_duration: int = 18000,  # 5 hours
    ):
        """Initialize progress monitor.

        Args:
            heartbeat_interval: Seconds between heartbeat messages
            max_duration: Maximum test duration in seconds
        """
        self.heartbeat_interval = heartbeat_interval
        self.max_duration = max_duration
        self.start_time: Optional[float] = None
        self.last_heartbeat: Optional[float] = None
        self.snapshots: list[SessionSnapshot] = []
        self.iteration = 0

    def start(self):
        """Start monitoring."""
        self.start_time = time.time()
        self.last_heartbeat = self.start_time
        print(f"\n{'=' * 80}")
        print("PROGRESS MONITOR STARTED")
        print(
            f"Heartbeat interval: {self.heartbeat_interval}s ({self.heartbeat_interval // 60} min)"
        )
        print(f"Max duration: {self.max_duration}s ({self.max_duration // 3600} hours)")
        print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'=' * 80}\n")

    def check(
        self,
        memory_count: int = 0,
        checkpoint_count: int = 0,
        total_tokens: int = 0,
        cost_usd: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Check progress and emit heartbeat if needed.

        Args:
            memory_count: Current memory entry count
            checkpoint_count: Current checkpoint count
            total_tokens: Total tokens consumed
            cost_usd: Total cost in USD
            metadata: Additional metadata to track

        Raises:
            TimeoutError: If max duration exceeded
        """
        if self.start_time is None:
            raise RuntimeError("Monitor not started. Call start() first.")

        self.iteration += 1
        current_time = time.time()
        elapsed = current_time - self.start_time

        # Check timeout
        if elapsed > self.max_duration:
            raise TimeoutError(
                f"Test exceeded max duration: {elapsed:.0f}s > {self.max_duration}s"
            )

        # Check if heartbeat needed
        if current_time - self.last_heartbeat >= self.heartbeat_interval:
            self._emit_heartbeat(
                elapsed,
                memory_count,
                checkpoint_count,
                total_tokens,
                cost_usd,
                metadata,
            )
            self.last_heartbeat = current_time

    def _emit_heartbeat(
        self,
        elapsed: float,
        memory_count: int,
        checkpoint_count: int,
        total_tokens: int,
        cost_usd: float,
        metadata: Optional[Dict[str, Any]],
    ):
        """Emit progress heartbeat."""
        snapshot = SessionSnapshot(
            timestamp=datetime.now(),
            iteration=self.iteration,
            memory_count=memory_count,
            checkpoint_count=checkpoint_count,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            metadata=metadata or {},
        )
        self.snapshots.append(snapshot)

        elapsed_min = elapsed / 60
        remaining_sec = self.max_duration - elapsed
        remaining_min = remaining_sec / 60

        print(f"\n{'─' * 80}")
        print(
            f"HEARTBEAT #{len(self.snapshots)} @ {snapshot.timestamp.strftime('%H:%M:%S')}"
        )
        print(f"{'─' * 80}")
        print(f"Elapsed: {elapsed_min:.1f} min | Remaining: {remaining_min:.1f} min")
        print(f"Iteration: {self.iteration}")
        print(f"Memory entries: {memory_count}")
        print(f"Checkpoints: {checkpoint_count}")
        print(f"Total tokens: {total_tokens:,}")
        print(f"Total cost: ${cost_usd:.4f}")
        if metadata:
            print(f"Metadata: {metadata}")
        print(f"{'─' * 80}\n")

    def summary(self):
        """Print final summary."""
        if self.start_time is None:
            print("Monitor was not started.")
            return

        total_elapsed = time.time() - self.start_time
        print(f"\n{'=' * 80}")
        print("PROGRESS MONITOR SUMMARY")
        print(f"{'=' * 80}")
        print(
            f"Total duration: {total_elapsed / 60:.1f} min ({total_elapsed / 3600:.2f} hours)"
        )
        print(f"Total iterations: {self.iteration}")
        print(f"Heartbeats emitted: {len(self.snapshots)}")

        if self.snapshots:
            final = self.snapshots[-1]
            print("\nFinal state:")
            print(f"  Memory entries: {final.memory_count}")
            print(f"  Checkpoints: {final.checkpoint_count}")
            print(f"  Total tokens: {final.total_tokens:,}")
            print(f"  Total cost: ${final.cost_usd:.4f}")

        print(f"{'=' * 80}\n")


class TimeoutGuard:
    """Timeout guard for async operations using SIGALRM."""

    def __init__(self, timeout_seconds: int):
        """Initialize timeout guard.

        Args:
            timeout_seconds: Timeout in seconds
        """
        self.timeout_seconds = timeout_seconds
        self._old_handler = None

    def __enter__(self):
        """Start timeout guard."""

        def timeout_handler(signum, frame):
            raise TimeoutError(f"Operation exceeded timeout: {self.timeout_seconds}s")

        self._old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(self.timeout_seconds)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop timeout guard."""
        signal.alarm(0)
        if self._old_handler is not None:
            signal.signal(signal.SIGALRM, self._old_handler)


async def run_with_periodic_checks(
    async_func: Callable,
    monitor: ProgressMonitor,
    check_interval: int = 100,
    get_state_func: Optional[Callable[[], Dict[str, Any]]] = None,
):
    """Run async function with periodic progress checks.

    Args:
        async_func: Async function to run
        monitor: Progress monitor
        check_interval: Iterations between progress checks
        get_state_func: Function to get current state for snapshot

    Returns:
        Result from async_func

    Example:
        async def long_task():
            for i in range(1000):
                await do_work()
                if i % 100 == 0:
                    monitor.check(memory_count=i, total_tokens=i*10)

        result = await run_with_periodic_checks(
            long_task,
            monitor,
            check_interval=100
        )
    """
    monitor.start()

    try:
        # Run the async function
        result = await async_func()
        return result
    finally:
        monitor.summary()


def require_long_running_enabled():
    """Decorator to skip long-running tests unless explicitly enabled.

    Set environment variable: KAIZEN_ENABLE_LONG_RUNNING=1

    Example:
        @require_long_running_enabled()
        def test_multi_hour_session():
            pass
    """
    import os

    import pytest

    def decorator(func):
        def wrapper(*args, **kwargs):
            if not os.getenv("KAIZEN_ENABLE_LONG_RUNNING"):
                pytest.skip(
                    "Long-running tests disabled. "
                    "Set KAIZEN_ENABLE_LONG_RUNNING=1 to enable."
                )
            return func(*args, **kwargs)

        return wrapper

    return decorator
