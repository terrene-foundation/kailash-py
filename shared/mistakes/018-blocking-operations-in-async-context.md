# Mistake #018: Blocking Operations in Async Context

## Problem
Using synchronous operations in async functions.

### Bad Example
```python
# BAD - Blocking in async context
async def async_process():
    time.sleep(1)  # Blocks event loop
    return result

# GOOD - Proper async operations
async def async_process():
    await asyncio.sleep(1)  # Non-blocking
    return result

```

## Solution


## Fixed In
Async node implementations

---

## Configuration & Dependencies

## Categories
async

---
