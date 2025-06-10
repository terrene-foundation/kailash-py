# Mistake #003: Test Parameter Mismatch

## Problem
Tests using incorrect constructor parameters that don't match actual implementation.

### Bad Example
```python
# BAD - Wrong parameters
task_manager = TaskManager(storage_path="/tmp")  # storage_path doesn't exist

# GOOD - Correct parameters
storage = FileSystemStorage(base_path="/tmp")
task_manager = TaskManager(storage_backend=storage)

```

## Solution
Updated all tests to use correct TaskManager constructor pattern.

## Lesson Learned
Keep tests synchronized with API changes.

## Fixed In
Session 27 - Test suite resolution

---

## Test-Related Issues

## Categories
testing, api-design, configuration

---
