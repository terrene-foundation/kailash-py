# Mistake #025: Missing Error Documentation

## Problem
Not documenting possible exceptions.

### Bad Example
```python
# BAD - No exception documentation
def risky_operation(value):
    """Do something with value."""
    return 1 / value  # Can raise ZeroDivisionError

# GOOD - Document exceptions
def risky_operation(value):
    """Do something with value.

    Raises:
        ZeroDivisionError: If value is zero.
    """
    return 1 / value

```

## Solution


## Lesson Learned
Always document possible exceptions in docstrings.

---

## Integration Issues

---
