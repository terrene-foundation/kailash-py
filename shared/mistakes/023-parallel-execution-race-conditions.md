# Mistake #023: Parallel Execution Race Conditions

## Problem
Race conditions in parallel task execution.

### Bad Example
```python
# BAD - Shared mutable state
shared_counter = 0

async def task():
    global shared_counter
    shared_counter += 1  # Race condition

# GOOD - Thread-safe operations
async def task(counter: asyncio.Lock):
    async with counter:
        # Thread-safe increment

```

## Solution


## Lesson Learned
Always consider thread safety in parallel execution.

---

## Documentation Issues

---
