# Mistake #014: Type Validation Issues

## Problem
Inconsistent type checking and validation.

### Bad Example
```python
# BAD - No type validation
def process_data(data):
    return data.upper()  # Fails if data is not string

# GOOD - Proper validation
def process_data(data: str) -> str:
    if not isinstance(data, str):
        raise TypeError(f"Expected str, got {type(data)}")
    return data.upper()

```

## Solution


## Fixed In
Multiple sessions during validation improvements

## Categories
security

---
