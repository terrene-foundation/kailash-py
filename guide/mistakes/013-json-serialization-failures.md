# Mistake #013: JSON Serialization Failures

## Problem
Attempting to serialize non-serializable objects.

### Bad Example
```python
# BAD - datetime and set objects not JSON serializable
data = {
    "timestamp": datetime.now(),  # Not serializable
    "tags": {"tag1", "tag2"}      # Set not serializable
}
json.dumps(data)  # Fails

# GOOD - Proper serialization handling
data = {
    "timestamp": datetime.now().isoformat(),
    "tags": list({"tag1", "tag2"})
}

```

## Solution


## Fixed In
Session 26 - Performance visualization

---
