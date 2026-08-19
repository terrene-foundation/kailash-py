---
name: runtime-lifecycle
description: "Runtime lifecycle management with ref counting, acquire/release pattern, context managers, and proper cleanup. Use when asking about 'runtime close', 'runtime cleanup', 'runtime lifecycle', 'ref counting', 'acquire release', 'runtime leak', 'connection pool leak', 'ResourceWarning', 'runtime sharing', 'shared runtime', or 'runtime injection'."
---

# Runtime Lifecycle Management

Runtime lifecycle management with reference-counted sharing, context managers, and proper cleanup.

> **Skill Metadata**
> Category: `core-sdk`
> Priority: `CRITICAL`
> SDK Version: `2.1.0+`
> Issue: terrene-foundation/kailash-py#71

## The Problem

Every `LocalRuntime()` or `AsyncLocalRuntime()` creates an event loop and connection pool (7-16 connections). Without lifecycle management, runtimes leak — a single `DataFlow(auto_migrate=True)` consumed 28-64 connections, and a full Kaizen app consumed ~98 connections.

## Quick Reference

### Context Manager (Recommended for Local Variables)

```python
from kailash.runtime.local import LocalRuntime

# Sync — context manager ensures cleanup
with LocalRuntime() as runtime:
    results, run_id = runtime.execute(workflow.build())

# Async — try/finally since async with may not be available
from kailash.runtime import AsyncLocalRuntime

runtime = AsyncLocalRuntime()
try:
    results, run_id = await runtime.execute_workflow_async(workflow.build())
finally:
    runtime.close()
```

### Runtime Injection (For Classes)

```python
class MySubsystem:
    def __init__(self, ..., runtime=None):
        if runtime is not None:
            self.runtime = runtime.acquire()  # Increment ref count
            self._owns_runtime = False
        else:
            self.runtime = LocalRuntime()
            self._owns_runtime = True

    def close(self):
        """Release runtime reference. Actual cleanup at ref_count=0."""
        if hasattr(self, "runtime") and self.runtime is not None:
            self.runtime.release()
            self.runtime = None

    def __del__(self):
        if getattr(self, "runtime", None) is not None:
            import warnings
            warnings.warn(
                f"Unclosed {self.__class__.__name__}. Call close() explicitly.",
                ResourceWarning,
                source=self,
            )
            try:
                self.close()
            except Exception:
                pass
```

## Ref Counting API

```python
runtime = LocalRuntime()   # ref_count = 1 (creator)
runtime.acquire()          # ref_count = 2 (returns self)
runtime.release()          # ref_count = 1 (alias for close())
runtime.close()            # ref_count = 0 → actual cleanup

# Properties
runtime.ref_count          # Current count (read-only)

# Safety
runtime.acquire()          # RuntimeError if ref_count <= 0
runtime.close()            # No-op if ref_count already <= 0
runtime.close()            # Safe to call multiple times
```

## Lifecycle Diagram

```
Creator (DataFlow):
    runtime = LocalRuntime()          # ref_count = 1
    registry = ModelRegistry(
        runtime=runtime               # .acquire() → ref_count = 2
    )
    migrator = AutoMigrationSystem(
        runtime=runtime               # .acquire() → ref_count = 3
    )

Shutdown (any order is safe):
    registry.close()                  # .release() → ref_count = 2
    migrator.close()                  # .release() → ref_count = 1
    runtime.close()                   # .release() → ref_count = 0 → CLEANUP

Safe against double-close:
    registry.close()                  # .release() → ref_count = 2
    registry.close()                  # self.runtime is None → no-op
```

## Connection Budget After Fix

| Scenario                        | Before            | After            |
| ------------------------------- | ----------------- | ---------------- |
| DataFlow(auto_migrate=True)     | 28-64 connections | 7-16 connections |
| Full Kaizen app with governance | ~98 connections   | 7-16 connections |
| MCP server (N requests)         | 7N connections    | 7-16 connections |
| Test suite (50 files)           | 350+ connections  | ~50 connections  |

## MUST Rules

1. **Never create bare `LocalRuntime()` without lifecycle management** — use context manager, `try/finally`, or inject via `runtime=None` parameter
2. **Every class with `self.runtime` MUST have `close()` and `__del__`** — close() releases, **del** warns
3. **Every `acquire()` MUST have a matching `release()` or `close()`** — ref count must reach 0
4. **Close subsystems before runtime** — cascade: children first, then parent owner

## MUST NOT Rules

1. **MUST NOT create runtime per-request** — share server-level runtime across handlers
2. **MUST NOT reach into subsystem.runtime directly** — call subsystem.close() instead
3. **MUST NOT force `_ref_count = 0`** — always go through close() which respects ref counting

## Cross-References

- `rules/dataflow-pool.md` Rule 6 — No orphan runtimes
- `.claude/hooks/validate-workflow.js` — Lint detection for unmanaged runtimes
- `tests/integration/runtime/test_runtime_connection_budget.py` — 15 integration tests
- `src/kailash/runtime/local.py:1365-1420` — Ref counting implementation
