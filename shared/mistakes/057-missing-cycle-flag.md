# Mistake #057: Using Deprecated cycle=True Pattern Instead of CycleBuilder API

## Category
Cycles

## Severity
High

## Problem
Using the deprecated `cycle=True` parameter instead of the modern CycleBuilder API for creating cyclic workflows.

## Symptoms
- Error message: `TypeError: unexpected keyword argument 'cycle'`
- Error message: `WorkflowValidationError: Cycle detected in workflow`
- Workflow validation fails when using old cycle patterns
- Cannot create properly converging cycles

## Example
```python
# ❌ WRONG - Deprecated cycle=True approach
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "generator", {"model": "gpt-4"})
workflow.add_node("PythonCodeNode", "validator", {"code": "result = {'score': 0.8}"})
workflow.add_connection("generator", "result", "validator", "input")
workflow.add_connection("validator", "result", "generator", "input", cycle=True)  # DEPRECATED!

# ✅ CORRECT - Use CycleBuilder API
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "generator", {
    "code": """
try:
    iteration = feedback.get("iteration", 0)
    score = feedback.get("score", 0.5)
except NameError:
    iteration = 0
    score = 0.5

new_iteration = iteration + 1
improved_score = min(score + 0.1, 1.0)

result = {
    "iteration": new_iteration,
    "score": improved_score,
    "converged": improved_score >= 0.9
}
"""
})

# Build workflow first
built_workflow = workflow.build()

# Create cycle using CycleBuilder API
cycle_builder = built_workflow.create_cycle('improvement_cycle')
cycle_builder.connect('generator', 'generator', mapping={'result': 'feedback'})
cycle_builder.max_iterations(10)
cycle_builder.converge_when('converged == True')
cycle_builder.build()

# Execute with runtime
runtime = LocalRuntime()
results, run_id = runtime.execute(built_workflow)
```

## Root Cause
The `cycle=True` pattern was deprecated in favor of the CycleBuilder API which provides:
1. Better control over cycle configuration
2. Proper convergence conditions
3. Clear separation between workflow building and cycle creation
4. Runtime-based execution instead of direct node execution

This mistake happens because:
- Old documentation still shows `cycle=True` examples
- Developers use outdated patterns from earlier versions
- The new CycleBuilder API requires different workflow structure

## Solution
1. Build the workflow first using `workflow.build()`
2. Create cycles using `built_workflow.create_cycle('name')`
3. Configure cycles with `.connect()`, `.max_iterations()`, `.converge_when()`
4. Execute using `runtime.execute(built_workflow)`

## Prevention
- Always use CycleBuilder API for cycles: `built_workflow.create_cycle()`
- Build workflow before creating cycles: `workflow.build()`
- Use runtime execution: `runtime.execute(workflow)`
- Set proper convergence conditions with `.converge_when()`

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
