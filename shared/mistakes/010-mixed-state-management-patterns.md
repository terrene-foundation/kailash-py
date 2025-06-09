# Mistake #010: Mixed State Management Patterns

## Problem
Inconsistent approaches to state management across nodes.

### Bad Example
```python
# BAD - Mutable state in nodes
class BadNode(Node):
    def __init__(self):
        self.cache = {}  # Shared mutable state

# GOOD - Immutable patterns
class GoodNode(Node):
    def execute(self, **kwargs):
        # Create new state for each execution
        local_state = {}

```

## Solution


## Lesson Learned
Maintain consistency in state management approaches.

---
