# Mistake #006: Lambda Closure Issues in Tests

## Problem
Lambda functions in loops capturing wrong variable values.

### Bad Example
```python
# BAD - All lambdas capture the same 'i' value
nodes = [lambda: process(i) for i in range(3)]  # All use i=2

# GOOD - Proper closure capture
nodes = [lambda x=i: process(x) for i in range(3)]

```

## Solution


## Fixed In
Session 27 - Parallel execution tests

## Categories
testing

---
