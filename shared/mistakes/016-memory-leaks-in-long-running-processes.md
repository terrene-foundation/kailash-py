# Mistake #016: Memory Leaks in Long-Running Processes

## Problem
Unbounded data accumulation in monitoring components.

### Bad Example
```python
# BAD - Unbounded growth
class Dashboard:
    def __init__(self):
        self.metrics_history = []  # Grows infinitely

    def add_metrics(self, metrics):
        self.metrics_history.append(metrics)

# GOOD - Bounded collections
class Dashboard:
    def __init__(self, max_points=100):
        self.metrics_history = []
        self.max_points = max_points

    def add_metrics(self, metrics):
        self.metrics_history.append(metrics)
        if len(self.metrics_history) > self.max_points:
            self.metrics_history.pop(0)

```

## Solution


## Fixed In
Dashboard implementation

## Categories
performance

---
