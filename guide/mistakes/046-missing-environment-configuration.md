# Mistake #046: Missing Environment Configuration

## Problem
Hardcoded configuration instead of environment variables.

### Bad Example
```python
# BAD - Hardcoded config
DATABASE_URL = "postgresql://localhost:5432/db"

# GOOD - Environment-based config
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/db")

```

## Solution


## Fixed In
Configuration management improvements

---

## Process & Methodology Issues

## Categories
configuration

---
