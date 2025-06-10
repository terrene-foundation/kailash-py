# Mistake #036: Path Traversal Vulnerabilities

## Problem
Not validating file paths.

### Bad Example
```python
# BAD - Path traversal possible
def read_file(filename):
    with open(f"data/{filename}") as f:  # ../../../etc/passwd
        return f.read()

# GOOD - Path validation
def read_file(filename):
    safe_path = Path("data") / filename
    if not safe_path.resolve().is_relative_to(Path("data").resolve()):
        raise ValueError("Invalid file path")
    with open(safe_path) as f:
        return f.read()

```

## Solution


## Status
Security review needed

---

## Performance Optimization Issues

## Categories
security

---
