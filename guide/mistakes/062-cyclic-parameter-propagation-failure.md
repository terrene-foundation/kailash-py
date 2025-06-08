# Mistake 062: Cyclic Parameter Propagation Failure

## Problem
Runtime parameters don't propagate correctly through cycle iterations in cyclic workflows. Values that should flow from one iteration to the next via connection mappings revert to node defaults instead.

## Example
```python
# Node outputs quality=0.5 in iteration 0
class ProcessorNode(Node):
    def run(self, context, **kwargs):
        quality = kwargs.get("quality", 0.0)  # Gets 0.0 instead of 0.5!
        return {"quality": quality + 0.2}

# Mapping should pass quality to next iteration
workflow.connect("processor", "processor",
                mapping={"quality": "quality"},  # Doesn't work!
                cycle=True)
```

## Root Cause
The CyclicWorkflowExecutor doesn't correctly preserve and apply output values as inputs for the next cycle iteration. The connection mappings are not being honored for cyclic connections.

## Solution (Temporary Workaround)
Until the executor is fixed, use `_cycle_state` to preserve values:

```python
def run(self, context, **kwargs):
    cycle_info = context.get("cycle", {})
    prev_state = cycle_info.get("node_state") or {}

    # Get from cycle state if available
    quality = prev_state.get("saved_quality", kwargs.get("quality", 0.0))

    # Process
    new_quality = quality + 0.2

    # Save for next iteration
    return {
        "quality": new_quality,
        "_cycle_state": {"saved_quality": new_quality}
    }
```

## Proper Solution
Fix the CyclicWorkflowExecutor to:
1. Capture node outputs after each iteration
2. Apply connection mappings to create inputs for next iteration
3. Only use defaults for first iteration or truly missing values

## Related Mistakes
- [058](058-node-configuration-vs-runtime-parameters-confusion.md) - Config vs Runtime confusion
- [060](060-incorrect-cycle-state-access-patterns.md) - Cycle state access

## Session
Session 54 - Discovered during Phase 1 cyclic workflow implementation

## Impact
HIGH - Blocks practical use of cyclic workflows for anything beyond simple counters
