# Mistake #019: Missing Optional Dependencies

## Problem
Code failing when optional dependencies not installed.

### Bad Example
```python
# BAD - Hard dependency on optional package
import fastapi  # Fails if not installed

# GOOD - Graceful handling
try:
    import fastapi
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

if not FASTAPI_AVAILABLE:
    raise ImportError("FastAPI required for this functionality")

```

## Solution


## Fixed In
API server implementations

---
