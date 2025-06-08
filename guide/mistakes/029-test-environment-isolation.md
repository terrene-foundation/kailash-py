# Mistake #029: Test Environment Isolation

## Problem
Tests affecting each other due to shared state.

### Bad Example
```python
# BAD - Shared global state
global_cache = {}

def test_a():
    global_cache["key"] = "value"
    assert process_with_cache() == "expected"

def test_b():  # Might fail due to test_a's state
    assert process_with_cache() == "other_expected"

# GOOD - Isolated test environment
@pytest.fixture
def isolated_cache():
    return {}

def test_a(isolated_cache):
    isolated_cache["key"] = "value"
    assert process_with_cache(isolated_cache) == "expected"

```

## Solution


## Lesson Learned
Ensure test isolation to prevent cascading failures.

## Categories
testing

---
