# Mistake #050: Bare Except Clauses

## Problem
Using bare `except:` throughout the codebase catching all exceptions indiscriminately.

### Bad Example
```python
# Bad - catches SystemExit, KeyboardInterrupt, etc.
try:
    value = float(old_version) + 0.1
except:
    # This catches EVERYTHING including system signals
    value = "default"

```

### Good Example
```python
# Good - catches only expected exceptions
try:
    value = float(old_version) + 0.1
except (ValueError, TypeError):
    value = "default"

```

## Solution
Always catch specific exceptions:
```python
# Good - catches only expected exceptions
try:
    value = float(old_version) + 0.1
except (ValueError, TypeError):
    value = "default"
```

## Impact
Security vulnerabilities, hidden bugs, poor error handling

## Fixed In
Session 39 - Replaced all bare except clauses

---
