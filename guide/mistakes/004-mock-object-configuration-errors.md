# Mistake #004: Mock Object Configuration Errors

## Problem
Incorrect mock configuration causing test failures.

### Bad Example
```python
# BAD - Mock doesn't match real object structure
mock_psutil.AccessDenied = Exception  # Wrong - not a proper exception class

# GOOD - Proper mock exception class
mock_psutil.AccessDenied = type('AccessDenied', (Exception,), {})

```

## Solution


## Fixed In
Session 27 - Metrics collector tests

## Categories
testing, configuration

---
