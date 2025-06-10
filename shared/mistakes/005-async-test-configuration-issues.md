# Mistake #005: Async Test Configuration Issues

## Problem
Async tests not properly configured with pytest-asyncio.

### Bad Example
```python
# BAD - Missing async marker
def test_async_function():  # Should be async def
    await some_async_function()

# GOOD - Proper async test
@pytest.mark.asyncio
async def test_async_function():
    await some_async_function()

```

## Solution


## Lesson Learned
Properly configure async testing framework from the start.

## Status
Some async tests still skipped due to missing pytest-asyncio configuration

## Categories
testing, async, configuration

---
