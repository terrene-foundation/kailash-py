# Mistake #060: Incorrect Cycle State Access Patterns

## Problem
Trying to access cycle state without handling None.

### Bad Example
```python
# BAD - Will fail if node_state is None
cycle_info = context.get("cycle", {})
prev_state = cycle_info.get("node_state")
history = prev_state.get("history", [])  # AttributeError if prev_state is None!

# GOOD - Safe access pattern
cycle_info = context.get("cycle", {})
prev_state = cycle_info.get("node_state") or {}  # Always have a dict
history = prev_state.get("history", [])

```

## Solution
Use the "or {}" pattern for safe dict access

## Impact
AttributeError when accessing cycle state

## Fixed In
Session 28 - Cyclic workflow examples

## Categories
cyclic-workflow

---
