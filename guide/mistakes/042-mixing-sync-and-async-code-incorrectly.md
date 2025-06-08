# Mistake #042: Mixing Sync and Async Code Incorrectly

## Problem
Calling async functions from sync context without proper handling.

### Bad Example
```python
# BAD - Can't await in sync function
def sync_function():
    result = await async_function()  # SyntaxError

# GOOD - Use asyncio.run or make function async
def sync_function():
    result = asyncio.run(async_function())
    return result

```

## Solution


## Fixed In
Runtime execution improvements

---

## Advanced Testing Issues

## Categories
async

---
