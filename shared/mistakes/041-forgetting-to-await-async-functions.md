# Mistake #041: Forgetting to Await Async Functions

## Problem
Not awaiting async functions properly.

### Bad Example
```python
# BAD - Not awaiting
async def main():
    result = async_function()  # Returns coroutine, not result
    print(result)  # Prints <coroutine object>

# GOOD - Proper awaiting
async def main():
    result = await async_function()
    print(result)  # Prints actual result

```

## Solution


## Fixed In
Async node implementations

## Categories
async

---
