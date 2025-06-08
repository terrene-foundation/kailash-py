# Mistake #009: File Path Inconsistencies

## Problem
Hardcoded file paths and inconsistent output directory usage.

### Bad Example
```python
# BAD - Hardcoded paths
output_path = "/tmp/output.csv"  # Platform-specific
output_path = "examples/output.csv"  # Relative path issues

# GOOD - Consistent path handling
output_path = Path.cwd() / "outputs" / "output.csv"

```

## Solution


## Lesson Learned
Always use pathlib and consistent directory structures.

## Fixed In
Session 27 - File reorganization

---
