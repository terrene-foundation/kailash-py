# Cyclic Workflows in Kailash SDK

## Overview

Cyclic workflows enable iterative processing patterns where data flows back through earlier nodes in the workflow graph. This powerful feature supports use cases like:

- **Iterative refinement**: Continuously improve results until they meet quality criteria
- **Convergence algorithms**: Iterate until a stable state is reached
- **Feedback loops**: Process data multiple times based on validation results
- **Self-improving systems**: AI agents that refine their outputs through multiple passes

## Key Concepts

### 1. Marked Cycles

Unlike traditional DAGs (Directed Acyclic Graphs), Kailash workflows support cycles when explicitly marked:

```python
# Creating a cycle requires explicit marking
workflow.connect("validator", "processor",
    cycle=True,                           # Required for cycles
    max_iterations=10,                    # Safety limit
    convergence_check="quality >= 0.9")   # Stop condition
```

### 2. Configuration vs Runtime Parameters

**Critical distinction** that causes most cyclic workflow issues:

- **Configuration parameters** (HOW): Define node behavior - code, models, file paths
- **Runtime parameters** (WHAT): Data that flows through connections

```python
# ❌ WRONG - Passing runtime data as configuration
workflow.add_node("processor", PythonCodeNode(),
    data=[1, 2, 3])  # Error: 'data' is not a config parameter!

# ✅ CORRECT - Configuration defines behavior
workflow.add_node("processor", PythonCodeNode(),
    code="result = [x * 2 for x in data]")  # HOW to process

# Data flows through connections or runtime parameters
workflow.connect("source", "processor", mapping={"output": "data"})
```

### 3. Cycle State Management

Nodes in cycles receive context about the current iteration:

```python
class IterativeProcessorNode(Node):
    def run(self, data, **kwargs):
        # Safe access to cycle state
        context = kwargs.get('context', {})
        cycle_info = context.get('cycle', {})

        # Always use 'or {}' pattern for safety
        prev_state = cycle_info.get('node_state') or {}
        iteration = cycle_info.get('iteration', 0)

        # Access previous iteration's data
        history = prev_state.get('history', [])

        # Process data with awareness of iteration
        if iteration == 0:
            result = self.initial_processing(data)
        else:
            result = self.refine_result(data, history[-1])

        # Return result with state for next iteration
        return {
            'result': result,
            'history': history + [result],
            'converged': self.check_convergence(result)
        }
```

## Basic Cycle Patterns

### 1. Simple Refinement Loop

```python
from kailash import Workflow, LocalRuntime
from kailash.nodes.transform import DataTransformerNode
from kailash.nodes.code import PythonCodeNode

# Create workflow
workflow = Workflow("refinement_loop", "Iterative refinement example")

# Add nodes
workflow.add_node("source", DataSourceNode())
workflow.add_node("processor", PythonCodeNode(),
    code="""
# Refine data based on feedback
if 'feedback' in locals():
    result = [x * 0.9 if feedback['adjust'] else x for x in data]
else:
    result = data
""")

workflow.add_node("validator", PythonCodeNode(),
    code="""
# Check if refinement is needed
quality = sum(result) / len(result)
feedback = {'adjust': quality > 100, 'quality': quality}
""")

# Connect with cycle
workflow.connect("source", "processor", mapping={"data": "data"})
workflow.connect("processor", "validator", mapping={"result": "result"})
workflow.connect("validator", "processor",
    mapping={"feedback": "feedback"},
    cycle=True,
    max_iterations=5,
    convergence_check="feedback['quality'] <= 100")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)
```

### 2. Multi-Node Cycle

```python
# Complex cycle with multiple nodes
workflow = Workflow("complex_cycle", "Multi-node iterative process")

# Add nodes for complex processing
workflow.add_node("input", DataSourceNode())
workflow.add_node("preprocessor", TransformNode())
workflow.add_node("analyzer", AnalysisNode())
workflow.add_node("optimizer", OptimizationNode())
workflow.add_node("evaluator", EvaluationNode())

# Create cycle through multiple nodes
workflow.connect("input", "preprocessor")
workflow.connect("preprocessor", "analyzer")
workflow.connect("analyzer", "optimizer")
workflow.connect("optimizer", "evaluator")
workflow.connect("evaluator", "preprocessor",
    cycle=True,
    cycle_id="optimization_loop",
    max_iterations=10,
    convergence_check="score >= 0.95")
```

## Advanced Patterns

### 1. Nested Cycles

```python
# Workflow with nested cycles
workflow = Workflow("nested_cycles", "Hierarchical iterative process")

# Outer cycle for major iterations
workflow.connect("outer_validator", "outer_processor",
    cycle=True,
    cycle_id="outer_loop",
    max_iterations=5)

# Inner cycle for fine-tuning
workflow.connect("inner_validator", "inner_processor",
    cycle=True,
    cycle_id="inner_loop",
    max_iterations=20,
    convergence_check="error < 0.01")
```

### 2. Conditional Cycles

```python
# Cycle that only activates under certain conditions
workflow.add_node("conditional_router", SwitchNode(),
    conditions=[
        {"expression": "needs_refinement", "output": "refine"},
        {"expression": "not needs_refinement", "output": "complete"}
    ])

# Cycle only when refinement is needed
workflow.connect("conditional_router", "refiner",
    source_port="refine")
workflow.connect("refiner", "processor",
    cycle=True,
    max_iterations=10)
```

### 3. Parallel Cycles

```python
# Multiple independent cycles running in parallel
workflow = Workflow("parallel_cycles", "Parallel iterative processes")

# Branch A with its own cycle
workflow.connect("validator_a", "processor_a",
    cycle=True,
    cycle_id="cycle_a",
    max_iterations=10)

# Branch B with different convergence criteria
workflow.connect("validator_b", "processor_b",
    cycle=True,
    cycle_id="cycle_b",
    convergence_check="variance < 0.1")

# Merge results after both cycles complete
workflow.add_node("merger", MergeNode())
workflow.connect("processor_a", "merger", target_port="input_a")
workflow.connect("processor_b", "merger", target_port="input_b")
```

## Convergence Strategies

### 1. Expression-Based Convergence

```python
# Simple expression
workflow.connect("validator", "processor",
    cycle=True,
    convergence_check="quality >= 0.9")

# Complex expression
workflow.connect("validator", "processor",
    cycle=True,
    convergence_check="quality >= 0.9 and error < 0.01 and iterations > 2")
```

### 2. Callback-Based Convergence

```python
def custom_convergence(results, iteration, cycle_state):
    """Custom convergence logic."""
    if iteration < 2:
        return False  # Minimum iterations

    current = results.get('score', 0)
    history = cycle_state.get('score_history', [])

    if not history:
        return False

    # Check if improvement is slowing down
    improvement = abs(current - history[-1])
    return improvement < 0.001

workflow.connect("validator", "processor",
    cycle=True,
    convergence_callback=custom_convergence)
```

### 3. Multi-Criteria Convergence

```python
# Combine multiple convergence criteria
workflow.connect("validator", "processor",
    cycle=True,
    max_iterations=100,
    convergence_check="converged or quality >= 0.95",
    timeout=300.0)  # 5-minute timeout
```

## Best Practices

### 1. Always Set Safety Limits

```python
# ❌ BAD - No safety limits
workflow.connect("a", "b", cycle=True)

# ✅ GOOD - Multiple safety mechanisms
workflow.connect("a", "b",
    cycle=True,
    max_iterations=100,      # Iteration limit
    timeout=600.0,          # Time limit
    convergence_check="converged")  # Exit condition
```

### 2. Handle First Iteration Gracefully

```python
class CycleAwareNode(Node):
    def run(self, **kwargs):
        cycle_info = kwargs.get('context', {}).get('cycle', {})
        iteration = cycle_info.get('iteration', 0)

        if iteration == 0:
            # First iteration - initialize
            return self.initialize_processing(kwargs.get('data'))
        else:
            # Subsequent iterations - refine
            prev_state = cycle_info.get('node_state') or {}
            return self.refine_processing(kwargs.get('data'), prev_state)
```

### 3. Design for Testability

```python
# Use flexible assertions for non-deterministic iteration counts
def test_cyclic_workflow():
    results, run_id = runtime.execute(workflow)

    # ❌ BAD - Too specific
    assert results['processor']['iteration_count'] == 5

    # ✅ GOOD - Flexible assertions
    assert 1 <= results['processor']['iteration_count'] <= 10
    assert results['processor']['converged'] is True
    assert results['processor']['quality'] >= 0.9
```

### 4. Monitor Cycle Performance

```python
# Add monitoring to track cycle behavior
workflow.add_node("monitor", PythonCodeNode(),
    code="""
# Track cycle metrics
cycle_info = context.get('cycle', {})
iteration = cycle_info.get('iteration', 0)

if iteration == 0:
    metrics = {'start_time': time.time(), 'iterations': []}
else:
    metrics = context['cycle']['node_state'].get('metrics', {})

metrics['iterations'].append({
    'iteration': iteration,
    'timestamp': time.time(),
    'quality': quality
})

result = {'metrics': metrics}
""")
```

## Common Pitfalls and Solutions

### 1. Configuration vs Runtime Data

```python
# ❌ WRONG - Common mistake
workflow.add_node("proc", PythonCodeNode(),
    data=[1, 2, 3],  # Error: 'data' is not a config parameter!
    initial_value=10)  # Error: runtime data as config!

# ✅ CORRECT - Proper separation
workflow.add_node("proc", PythonCodeNode(),
    code="result = process_data(data)")  # Config: HOW to process

# Pass runtime data through connections or parameters
runtime.execute(workflow, parameters={
    "proc": {"data": [1, 2, 3], "initial_value": 10}
})
```

### 2. Unmarked Cycles

```python
# ❌ WRONG - Creates illegal cycle
workflow.connect("a", "b")
workflow.connect("b", "c")
workflow.connect("c", "a")  # Error: Unmarked cycle!

# ✅ CORRECT - Mark the cycle
workflow.connect("c", "a",
    cycle=True,
    max_iterations=10)
```

### 3. State Access Without Safety

```python
# ❌ WRONG - Can cause AttributeError
prev_state = context['cycle']['node_state']
history = prev_state['history']  # Error if prev_state is None!

# ✅ CORRECT - Safe access pattern
cycle_info = context.get('cycle', {})
prev_state = cycle_info.get('node_state') or {}
history = prev_state.get('history', [])
```

## Performance Considerations

### 1. Minimize State Size

```python
# Keep only essential state between iterations
class EfficientNode(Node):
    def run(self, **kwargs):
        # Don't store entire datasets
        return {
            'result': processed_data,
            'summary': {  # Small state object
                'count': len(processed_data),
                'mean': statistics.mean(processed_data),
                'converged': converged
            }
        }
```

### 2. Early Exit Strategies

```python
# Check multiple convergence criteria for early exit
workflow.connect("validator", "processor",
    cycle=True,
    convergence_check=(
        "quality >= target_quality or "
        "improvement < 0.001 or "
        "iteration > min_iterations and quality > acceptable_quality"
    ))
```

### 3. Parallel Cycle Execution

```python
# Use parallel runtime for independent cycles
from kailash.runtime import ParallelRuntime

runtime = ParallelRuntime(max_workers=4)
results, run_id = runtime.execute(workflow)  # Cycles run in parallel
```

## Real-World Examples

### 1. Machine Learning Model Training

```python
# Iterative model training with early stopping
workflow = Workflow("ml_training", "Iterative model training")

workflow.add_node("data_loader", DataLoaderNode())
workflow.add_node("trainer", ModelTrainerNode(),
    model_type="neural_network",
    learning_rate=0.001)
workflow.add_node("validator", ModelValidatorNode(),
    validation_split=0.2)

# Training cycle with early stopping
workflow.connect("validator", "trainer",
    cycle=True,
    max_iterations=100,
    convergence_check="val_loss_improved == False for 5 iterations")
```

### 2. Document Refinement with LLM

```python
# Iterative document improvement
workflow = Workflow("doc_refinement", "LLM-based document refinement")

workflow.add_node("llm", LLMAgentNode(),
    model="gpt-4",
    system_prompt="You are a document editor. Refine the document based on feedback.")

workflow.add_node("evaluator", DocumentEvaluatorNode(),
    criteria=["clarity", "completeness", "accuracy"])

# Refinement cycle
workflow.connect("evaluator", "llm",
    mapping={"feedback": "feedback", "document": "document"},
    cycle=True,
    max_iterations=5,
    convergence_check="all(score >= 0.8 for score in quality_scores.values())")
```

### 3. Data Quality Improvement

```python
# Iterative data cleaning and validation
workflow = Workflow("data_quality", "Iterative data quality improvement")

workflow.add_node("cleaner", DataCleanerNode(),
    cleaning_rules=["remove_duplicates", "fix_formats", "impute_missing"])

workflow.add_node("quality_checker", DataQualityNode(),
    checks=["completeness", "consistency", "accuracy"])

# Quality improvement cycle
workflow.connect("quality_checker", "cleaner",
    mapping={"issues": "issues_to_fix"},
    cycle=True,
    max_iterations=10,
    convergence_check="len(issues) == 0 or iteration > 5")
```

## Migration Guide: From Python Loops to Workflow Cycles

### Before: Traditional Python Loop

```python
# Traditional iterative processing
def refine_data(data, max_iterations=10, target_quality=0.9):
    result = data
    for i in range(max_iterations):
        result = process(result)
        quality = evaluate(result)
        if quality >= target_quality:
            break
    return result
```

### After: Workflow Cycle

```python
# Same logic as a workflow
workflow = Workflow("refine_data", "Data refinement workflow")

# Add nodes
workflow.add_node("processor", PythonCodeNode(),
    code="result = process(data)")
workflow.add_node("evaluator", PythonCodeNode(),
    code="quality = evaluate(result)")

# Create cycle
workflow.connect("evaluator", "processor",
    mapping={"result": "data"},
    cycle=True,
    max_iterations=10,
    convergence_check="quality >= 0.9")

# Execute
results, run_id = runtime.execute(workflow,
    parameters={"processor": {"data": initial_data}})
```

## Debugging Cyclic Workflows

### 1. Enable Verbose Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Execution will show cycle details
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)
```

### 2. Track Cycle State

```python
# Add debug node to monitor cycle state
workflow.add_node("debugger", PythonCodeNode(),
    code="""
print(f"Iteration: {context.get('cycle', {}).get('iteration', 0)}")
print(f"Previous state: {context.get('cycle', {}).get('node_state')}")
result = data  # Pass through
""")
```

### 3. Visualize Cycle Execution

```python
# Use tracking to understand cycle behavior
from kailash.tracking import TaskTracker

tracker = TaskTracker()
results, run_id = runtime.execute(workflow, task_tracker=tracker)

# Analyze cycle metrics
run_data = tracker.get_run(run_id)
for task in run_data['tasks']:
    if 'cycle' in task['metadata']:
        print(f"Node {task['node_id']} - Iteration {task['metadata']['cycle']['iteration']}")
```

## Summary

Cyclic workflows in Kailash SDK provide powerful iterative processing capabilities while maintaining the safety and structure of workflow-based systems. Key points to remember:

1. **Always mark cycles explicitly** with `cycle=True`
2. **Separate configuration from runtime data** - config defines HOW, runtime is WHAT
3. **Use safety limits** - max_iterations, timeouts, convergence checks
4. **Handle state safely** with the `or {}` pattern
5. **Write flexible tests** that don't depend on exact iteration counts

With these patterns and practices, you can build sophisticated iterative workflows that handle complex processing requirements while remaining maintainable and testable.
