# Mistake #015: Schema Mismatch Issues

## Problem
Output schemas not matching actual node outputs.

### Bad Example
```python
# BAD - Schema doesn't match output
def get_output_schema(self):
    return {"result": str}

def run(self):
    return {"data": "value"}  # Key mismatch: 'data' vs 'result'

# GOOD - Matching schema and output
def get_output_schema(self):
    return {"data": str}

def run(self):
    return {"data": "value"}

```

## Solution


## Fixed In
Schema validation improvements

---

## Performance Issues

---
