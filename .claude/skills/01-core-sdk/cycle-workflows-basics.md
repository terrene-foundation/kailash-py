---
name: cycle-workflows-basics
description: "Cyclic workflow patterns using CycleBuilder API with convergence checking, timeouts, and nested cycles. Use when asking 'cyclic workflow', 'cycles', 'loops', 'iteration', 'convergence', 'max_iterations', 'CycleBuilder', 'workflow loops', or 'iterative processing'."
globs: ["**/*.py"]
---

# Cyclic Workflows

Cyclic workflows are fully implemented. Use the `CycleBuilder` fluent API (v1.0+).

## CycleBuilder API

```python
from kailash.workflow.graph import Workflow

workflow = Workflow("optimization", "Optimization Loop")
workflow.add_node("PythonCodeNode", "processor", {"code": "..."})
workflow.add_node("PythonCodeNode", "evaluator", {"code": "..."})

# Fluent cycle creation (the only supported API)
workflow.create_cycle("quality_improvement") \
    .connect("evaluator", "processor", {"result": "input_data"}) \
    .max_iterations(50) \
    .converge_when("quality > 0.9") \
    .timeout(300) \
    .build()
```

**Note**: Direct `cycle=True` in `workflow.connect()` was removed in v1.0. Use `create_cycle()`.

## CycleBuilder Methods

| Method                               | Purpose                                                                   |
| ------------------------------------ | ------------------------------------------------------------------------- |
| `.connect(source, target, mapping?)` | Set cycle connection (required)                                           |
| `.max_iterations(n)`                 | Safety limit on iterations (required unless converge_when or timeout set) |
| `.converge_when(expr)`               | Early termination condition (e.g. `"error < 0.01"`)                       |
| `.timeout(seconds)`                  | Time-based safety limit                                                   |
| `.memory_limit(mb)`                  | Memory usage limit                                                        |
| `.when(condition)`                   | Conditional cycle execution                                               |
| `.nested_in(parent_id)`              | Nest inside another cycle                                                 |
| `.build()`                           | Finalize and add cycle to workflow                                        |

At least one termination condition (`max_iterations`, `converge_when`, or `timeout`) is required.

## CycleConfig Templates

```python
from kailash.workflow.cycle_config import CycleConfig, CycleTemplates

# Pre-built templates
config = CycleTemplates.optimization_loop(max_iterations=200, convergence_threshold=0.001)
config = CycleTemplates.retry_cycle(max_retries=3, timeout_per_retry=30.0)
config = CycleTemplates.data_quality_cycle(quality_threshold=0.95)
config = CycleTemplates.training_loop(max_epochs=100, early_stopping_patience=10)

# Apply template to builder
from kailash.workflow.cycle_builder import CycleBuilder
builder = CycleBuilder.from_config(workflow, config)
builder.connect("optimizer", "evaluator").build()
```

## ConvergenceCheckerNode

```python
from kailash.nodes.logic.convergence import ConvergenceCheckerNode

# Declarative convergence detection node
workflow.add_node("ConvergenceCheckerNode", "checker", {
    "threshold": 0.8,
    "mode": "threshold"  # checks if value meets threshold
})
```

## Runtime Configuration

Cycles are enabled by default (`enable_cycles=True` in BaseRuntime). Execution uses `CyclicWorkflowExecutor` internally.

## Related

- `skills/06-cheatsheets/cyclic-patterns-advanced.md` — advanced patterns
- `skills/06-cheatsheets/cycle-debugging.md` — debugging cycles
- `skills/14-code-templates/template-cyclic-workflow.md` — starter template
