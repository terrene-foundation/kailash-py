# Mistake #045: Platform-Specific Code

## Problem
Code working only on specific platforms.

### Bad Example
```python
# BAD - Unix-specific
file_path = "/tmp/data.csv"  # Fails on Windows

# GOOD - Cross-platform
file_path = Path.home() / "temp" / "data.csv"

```

## Solution


## Fixed In
File path standardization with pathlib

---
