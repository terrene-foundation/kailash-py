# Mistake #034: Circular Dependencies

## Problem
Modules importing each other creating circular dependencies.

### Bad Example
```python
# BAD - Circular imports
# module_a.py
from module_b import B

# module_b.py
from module_a import A

# GOOD - Dependency injection or restructuring
# module_a.py
def create_a(b_instance):
    return A(b_instance)

# module_b.py
class B:
    pass

```

## Solution


## Fixed In
Module restructuring throughout development

---

## Security Issues

## Categories
architecture

---
