# Mistake #012: Registry Pattern Misuse

## Problem
Incorrect node registration causing discovery issues.

### Bad Example
```python
# BAD - Missing registration decorator
class MyNode(Node):
    pass  # Not discoverable by registry

# GOOD - Proper registration
@register_node()
class MyNode(Node):
    pass

```

## Solution


## Fixed In
Various sessions during node development

---

## Data Handling Issues

---
