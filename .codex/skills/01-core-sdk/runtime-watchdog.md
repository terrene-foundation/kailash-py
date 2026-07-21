# Event Loop Watchdog

EventLoopWatchdog detects asyncio event loop stalls — situations where the loop
stops processing callbacks within a configurable threshold. This is the primary
diagnostic tool for hung workflows in LocalRuntime.

## Architecture

Two-part design:

1. **Heartbeat coroutine** (inside the event loop) — posts timestamps at regular intervals.
2. **Watchdog thread** (outside the event loop) — checks whether heartbeats arrive on time.

When the gap between heartbeats exceeds the stall threshold, the watchdog captures
task stack traces and fires an `on_stall` callback with a structured `StallReport`.

## API Surface

```python
from kailash.runtime.watchdog import EventLoopWatchdog, StallReport

# StallReport (dataclass)
report.stall_duration_s   # float — how long the loop has been unresponsive
report.loop_id            # int — id() of the event loop
report.task_count         # int — number of tasks in the loop
report.task_stacks        # list[str] — stack traces of running tasks
report.timestamp          # datetime — when the stall was detected

# EventLoopWatchdog
wd = EventLoopWatchdog(
    loop=asyncio.get_event_loop(),
    heartbeat_interval_s=1.0,     # how often the heartbeat fires
    stall_threshold_s=5.0,        # gap that triggers a stall report
    on_stall=my_callback,         # Callable[[StallReport], None]
)
await wd.start()
# ... run workflow ...
await wd.stop()

# Properties
wd.is_stalled       # bool — is the loop currently stalled?
wd.stall_reports    # deque[StallReport] — historical stall reports
```

## Recommended Usage (Context Manager)

```python
async with EventLoopWatchdog(
    stall_threshold_s=3.0,
    on_stall=lambda r: logger.warning("loop.stall", duration=r.stall_duration_s),
) as wd:
    results, run_id = await runtime.execute_workflow_async(workflow.build())
    if wd.is_stalled:
        logger.error("Loop stalled during execution", stacks=wd.stall_reports[-1].task_stacks)
```

## Resource Cleanup

EventLoopWatchdog implements `__del__` with `ResourceWarning` per `rules/patterns.md`.
If `stop()` is not called before garbage collection, a warning is emitted and the
watchdog thread receives a best-effort stop signal.

## When to Use

- **Production monitoring**: Detect blocked event loops in Docker/Nexus deployments
- **CI diagnostics**: Add to integration tests that occasionally hang to capture what's blocking
- **Development**: Wrap long-running workflow executions to catch accidental sync calls in async nodes
