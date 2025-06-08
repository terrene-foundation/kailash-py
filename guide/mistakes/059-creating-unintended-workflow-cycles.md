# Mistake #059: Creating Unintended Workflow Cycles

## Problem
Accidentally creating cycles without proper marking.

### Bad Example
```python
# BAD - Uncontrolled cycle
workflow.connect("processor", "validator")
workflow.connect("validator", "processor")  # Creates unmarked cycle!

# GOOD - Marked cycle with safety limits
workflow.connect("validator", "processor",
    cycle=True,                           # Mark as cycle
    max_iterations=10,                    # Safety limit
    convergence_check="quality >= 0.9",   # Stop condition
    cycle_id="refinement_loop")          # Unique identifier

```

## Solution
Always mark intentional cycles with cycle=True

## Impact
WorkflowValidationError: "Workflow contains unmarked cycles"

## Lesson Learned
Cycles require explicit marking and safety controls

## Fixed In
Session 28 - Cycle detection implementation

## Categories
workflow, cyclic-workflow

---
