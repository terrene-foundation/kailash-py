# Mistake #043: Flaky Tests Due to Timing

## Problem
Tests failing intermittently due to timing issues.

### Bad Example
```python
# BAD - Timing-dependent test
def test_async_operation():
    start_async_operation()
    time.sleep(0.1)  # Might not be enough
    assert operation_completed()

# GOOD - Proper waiting
def test_async_operation():
    start_async_operation()
    wait_for_condition(lambda: operation_completed(), timeout=5)
    assert operation_completed()

```

## Solution


## Lesson Learned
Make tests deterministic, not timing-dependent.

## Categories
testing

---
