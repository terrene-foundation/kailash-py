# Mistake #008: Run ID Management Conflicts

## Problem
Tests pre-creating runs but runtime creates its own runs.

### Bad Example
```python
# BAD - Conflicting run creation
run_id = task_manager.create_run("test")  # Pre-created
results = runtime.execute(workflow, task_manager)  # Creates its own run

# GOOD - Let runtime manage runs
results, run_id = runtime.execute(workflow, task_manager)

```

## Solution


## Fixed In
Session 27 - Integration tests

---

## Architecture & Design Issues

---
