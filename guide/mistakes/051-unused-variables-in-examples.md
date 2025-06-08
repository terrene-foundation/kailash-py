# Mistake #051: Unused Variables in Examples

## Problem
Examples had unused variables that confused users about their purpose.

### Bad Example
```python
# Bad - builder created but never used
builder = WorkflowBuilder("demo")
# ... rest of example doesn't use builder

```

### Good Example
```python
# Good - clear that it's for reference only
# builder = WorkflowBuilder("demo")  # Not used in this example, shown for reference

```

## Solution
Comment out with explanation or remove:
```python
# Good - clear that it's for reference only
# builder = WorkflowBuilder("demo")  # Not used in this example, shown for reference
```

## Impact
Confused users, failed linting checks

## Fixed In
Session 39

---
