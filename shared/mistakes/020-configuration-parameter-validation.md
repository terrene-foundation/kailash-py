# Mistake #020: Configuration Parameter Validation

## Problem
Missing validation for configuration parameters.

### Bad Example
```python
# BAD - No validation
def __init__(self, update_interval):
    self.update_interval = update_interval  # Could be negative

# GOOD - Parameter validation
def __init__(self, update_interval):
    if update_interval <= 0:
        raise ValueError("update_interval must be positive")
    self.update_interval = update_interval

```

## Solution


## Lesson Learned
Always validate configuration parameters.

---

## Workflow & Execution Issues

## Categories
api-design, configuration, security

---
