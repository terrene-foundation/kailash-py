# Mistake #030: Mock Leakage Between Tests

## Problem
Mock configurations persisting between tests.

### Bad Example
```python
# BAD - Mock persists
@patch('module.function')
def test_a(mock_func):
    mock_func.return_value = "test"
    # Mock continues to affect other tests

# GOOD - Proper mock cleanup
def test_a():
    with patch('module.function') as mock_func:
        mock_func.return_value = "test"
        # Mock automatically cleaned up

```

## Solution


## Fixed In
Test suite refactoring

---

## Code Organization Issues

## Categories
testing

---
