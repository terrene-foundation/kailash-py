# Mistake #057: Missing Cycle Flag

## Category
Cycles

## Severity
High

## Problem
Creating a connection that forms a cycle in the workflow but forgetting to set `cycle=True`, causing validation to fail.

## Symptoms
- Error message: `WorkflowValidationError: Cycle detected in workflow`
- Error message: `Workflow contains cycles but no cycle=True connections`
- Workflow validation fails before execution
- Legitimate feedback loops are rejected

## Example
```python
# ❌ WRONG - Cycle without marking it
workflow = Workflow(name="iterative_improvement")
workflow.add_node("generator", LLMAgentNode(), ...)
workflow.add_node("validator", PythonCodeNode(), ...)
workflow.connect("generator", "validator")
workflow.connect("validator", "generator")  # Creates cycle but not marked!

# ✅ CORRECT - Explicitly mark the cycle
workflow = Workflow(name="iterative_improvement")
workflow.add_node("generator", LLMAgentNode(), ...)
workflow.add_node("validator", PythonCodeNode(), ...)
workflow.connect("generator", "validator")
workflow.connect("validator", "generator",
    cycle=True,                        # Required for cycles
    max_iterations=10,                 # Safety limit
    convergence_check="score >= 0.9"   # Stop condition
)
```

## Root Cause
Kailash requires explicit cycle marking to:
1. Prevent accidental infinite loops
2. Enable cycle-specific safety features
3. Optimize execution for iterative patterns

This mistake happens because:
- Developers expect cycles to "just work"
- The validation error doesn't suggest the solution
- It's not obvious that cycles need special handling

## Solution
1. Identify the connection that completes the cycle
2. Add `cycle=True` to that connection
3. Add `max_iterations` for safety
4. Consider adding `convergence_check` for early stopping

## Prevention
- Always use `cycle=True` when creating feedback loops
- Set reasonable `max_iterations` (default is 100)
- Add convergence checks for efficiency
- Use workflow visualization to spot cycles

## Related Mistakes
- [#058 - Unsafe State Access](058-unsafe-state-access.md)
- [#059 - Convergence Check Format](059-convergence-check-format.md)
- [#060 - Rigid Test Assertions](060-rigid-test-assertions.md)

## Fixed In
- Session: 2024-01-07 - Cyclic workflow implementation Phase 1
- ADR: [ADR-0036](../adr/0036-universal-hybrid-cyclic-graph-architecture.md)

## References
- [Cyclic Workflows Guide](../features/cyclic_workflows.md)
- [Workflow API](../reference/api-registry.yaml#workflow-connect)
- [Examples](../../examples/workflow_examples/workflow_iterative_refinement.py)
