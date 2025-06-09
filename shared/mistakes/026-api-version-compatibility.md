# Mistake #026: API Version Compatibility

## Problem
Breaking changes in API interfaces without version management.

### Bad Example
```python
# BAD - Breaking change
def old_method(self, param1):
    pass

def new_method(self, param1, param2):  # Breaking change
    pass

# GOOD - Backward compatibility
def new_method(self, param1, param2=None):  # Backward compatible
    if param2 is None:
        # Handle old behavior
    pass

```

## Solution


## Lesson Learned
Maintain backward compatibility or use proper versioning.

## Categories
api-design

---
