# Mistake #027: Database Connection Management

## Problem
Not properly managing database connections.

### Bad Example
```python
# BAD - Connection leak
def query_data():
    conn = get_connection()
    return conn.execute("SELECT * FROM table")
    # Connection not closed

# GOOD - Proper connection management
def query_data():
    with get_connection() as conn:
        return conn.execute("SELECT * FROM table")

```

## Solution


## Fixed In
Storage backend implementations

---

## Testing Strategy Issues

## Categories
workflow

---
