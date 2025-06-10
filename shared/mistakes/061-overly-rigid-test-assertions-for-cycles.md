# Mistake #061: Overly Rigid Test Assertions for Cycles

## Problem
Testing exact iteration counts in cyclic workflows.

### Bad Example
```python
# BAD - Too specific for iterative processes
assert results["loop"]["iteration_count"] == 5  # May vary!

# GOOD - Flexible assertions
assert 1 <= results["loop"]["iteration_count"] <= 10
assert results["loop"]["converged"] is True
assert results["processor"]["quality"] >= 0.9

```

## Solution
Test ranges and convergence outcomes, not exact paths

## Impact
Flaky tests that fail due to timing/convergence variations

## Lesson Learned
Cyclic workflows have non-deterministic iteration counts

## Fixed In
Session 28 - Cyclic workflow tests

---

## Categories
testing, cyclic-workflow

---
