# Cyclic Workflows in Kailash SDK

## Overview

Cyclic workflows enable iterative processing patterns where data flows back through earlier nodes in the workflow graph. This powerful feature supports use cases like:

- **Iterative refinement**: Continuously improve results until they meet quality criteria
- **Convergence algorithms**: Iterate until a stable state is reached
- **Feedback loops**: Process data multiple times based on validation results
- **Self-improving systems**: AI agents that refine their outputs through multiple passes

## Quick Start Example

```python
# Complete working example of a cyclic workflow
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.code import PythonCodeNode

# Create workflow with iterative data refinement
workflow = Workflow("cyclic_example", "Simple cyclic workflow example")

# Add nodes
workflow.add_node("data_source", PythonCodeNode(code="result = [110, 120, 130, 90, 80]"))
workflow.add_node("processor", PythonCodeNode(code="""
# Process data, applying feedback if available
if 'feedback' in locals() and feedback.get('needs_adjustment', False):
    result = [x * 0.9 for x in data]
else:
    result = data
"""))
workflow.add_node("evaluator", PythonCodeNode(code="""
# Evaluate if data needs further refinement
average = sum(result) / len(result) if result else 0
feedback = {
    'average': average,
    'needs_adjustment': average > 100,
    'quality_score': 1.0 / (average / 100) if average > 0 else 1.0
}
"""))

# Connect nodes with cycle
workflow.add_connection("data_source", "processor", "result", "data")
workflow.add_connection("processor", "evaluator", "result", "result")
workflow.add_connection("evaluator", "processor", "feedback", "feedback",
    cycle=True,
    max_iterations=5,
    convergence_check="average <= 100")

# Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)
print(f"Final results: {results}")
```

## Key Concepts

### 1. Marked Cycles

Unlike traditional DAGs (Directed Acyclic Graphs), Kailash workflows support cycles when explicitly marked:

```python
# Creating a cycle requires explicit marking
workflow = Workflow("example", name="Example")
workflow.add_connection("validator", "processor", "output", "input",
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
# workflow.add_node("processor", PythonCodeNode(),
#     data=[1, 2, 3])  # Error: 'data' is not a config parameter!

# ✅ CORRECT - Configuration defines behavior
workflow = Workflow("example", name="Example")
workflow.add_node("processor", PythonCodeNode(code="result = [x * 2 for x in data]"))  # HOW to process

# Data flows through connections or runtime parameters
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, 
    parameters={"processor": {"data": [1, 2, 3]}})

```

### 3. Cycle State Management

Nodes in cycles receive context about the current iteration:

```python
class IterativeProcessorNode(Node):
    def __init__(self, node_id=None):
        super().__init__(node_id)
        
    def run(self, data=None, **kwargs):
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
            result = self.refine_result(data, history[-1] if history else data)

        # Return result with state for next iteration
        return {
            'result': result,
            'history': history + [result],
            'converged': self.check_convergence(result)
        }
    
    def initial_processing(self, data):
        # Implement initial processing logic
        return data if data else []
    
    def refine_result(self, data, previous_result):
        # Implement refinement logic
        return [x * 0.9 for x in (data if isinstance(data, list) else [data])]
    
    def check_convergence(self, result):
        # Simple convergence check
        return isinstance(result, list) and len(result) > 0 and all(x < 10 for x in result)

```

## Basic Cycle Patterns

### 1. Simple Refinement Loop

```python
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.code import PythonCodeNode

# Create workflow
workflow = Workflow("refinement_loop", "Iterative refinement example")

# Add nodes
workflow.add_node("source", PythonCodeNode(code="result = [110, 120, 130, 90, 80]"))
workflow.add_node("processor", PythonCodeNode(code="""
# Refine data based on feedback
if 'feedback' in locals():
    result = [x * 0.9 if feedback.get('adjust', False) else x for x in data]
else:
    result = data
"""))

workflow.add_node("validator", PythonCodeNode(code="""
# Check if refinement is needed
quality = sum(result) / len(result) if result else 0
feedback = {'adjust': quality > 100, 'quality': quality}
"""))

# Connect with cycle
workflow.add_connection("source", "processor", "result", "data")
workflow.add_connection("processor", "validator", "result", "result")
workflow.add_connection("validator", "processor", "feedback", "feedback",
    cycle=True,
    max_iterations=5,
    convergence_check="feedback.get('quality', 999) <= 100")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

```

### 2. Multi-Node Cycle

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Complex cycle with multiple nodes
workflow = Workflow("complex_cycle", "Multi-node iterative process")

# Add nodes for complex processing
workflow.add_node("input", PythonCodeNode(code="result = {'data': [1, 2, 3, 4, 5], 'score': 0.1}"))
workflow.add_node("preprocessor", PythonCodeNode(code="""
# Preprocess input data
processed_data = [x * 1.1 for x in data.get('data', [])]
result = {'data': processed_data, 'preprocessed': True}
"""))
workflow.add_node("analyzer", PythonCodeNode(code="""
# Analyze processed data
analysis_score = sum(data.get('data', [])) / len(data.get('data', [1]))
result = dict(data, **{'analysis_score': analysis_score})
"""))
workflow.add_node("optimizer", PythonCodeNode(code="""
# Optimize based on analysis
optimized_data = [x * 0.95 for x in data.get('data', [])]
result = dict(data, **{'data': optimized_data, 'optimized': True})
"""))
workflow.add_node("evaluator", PythonCodeNode(code="""
# Evaluate optimization results
score = min(0.95, data.get('analysis_score', 0) * 1.1)
result = dict(data, **{'score': score, 'converged': score >= 0.9})
"""))

# Create cycle through multiple nodes
workflow.add_connection("input", "preprocessor", "result", "data")
workflow.add_connection("preprocessor", "analyzer", "result", "data")
workflow.add_connection("analyzer", "optimizer", "result", "data")
workflow.add_connection("optimizer", "evaluator", "result", "data")
workflow.add_connection("evaluator", "preprocessor", "result", "data",
    cycle=True,
    cycle_id="optimization_loop",
    max_iterations=10,
    convergence_check="data.get('score', 0) >= 0.9")

```

## Advanced Patterns

### 1. Nested Cycles

```python
# Workflow with nested cycles
workflow = Workflow("nested_cycles", "Hierarchical iterative process")

# Outer cycle for major iterations
workflow.add_connection("outer_validator", "outer_processor", "feedback", "input",
    cycle=True,
    cycle_id="outer_loop",
    max_iterations=5)

# Inner cycle for fine-tuning
workflow.add_connection("inner_validator", "inner_processor", "refinement", "input",
    cycle=True,
    cycle_id="inner_loop",
    max_iterations=20,
    convergence_check="error < 0.01")

```

### 2. Conditional Cycles

```python
# Cycle that only activates under certain conditions
from kailash.nodes.logic import SwitchNode

workflow = Workflow("conditional_cycle", "Conditional refinement cycle")
workflow.add_node("conditional_router", SwitchNode(conditions=[
    {"expression": "needs_refinement", "output": "refine"},
    {"expression": "not needs_refinement", "output": "complete"}
]))

# Add refinement nodes
workflow.add_node("refiner", PythonCodeNode(code="result = {'refined': True, 'data': data}"))
workflow.add_node("processor", PythonCodeNode(code="result = process_data(data)"))

# Cycle only when refinement is needed
workflow.add_connection("conditional_router", "refiner", "refine", "input")
workflow.add_connection("refiner", "processor", "result", "data",
    cycle=True,
    max_iterations=10)

```

### 3. Parallel Cycles

```python
# Multiple independent cycles running in parallel
from kailash.nodes.logic import MergeNode

workflow = Workflow("parallel_cycles", "Parallel iterative processes")

# Branch A with its own cycle
workflow.add_connection("validator_a", "processor_a", "feedback_a", "input",
    cycle=True,
    cycle_id="cycle_a",
    max_iterations=10)

# Branch B with different convergence criteria
workflow.add_connection("validator_b", "processor_b", "feedback_b", "input",
    cycle=True,
    cycle_id="cycle_b",
    convergence_check="variance < 0.1")

# Merge results after both cycles complete
workflow.add_node("merger", MergeNode())
workflow.add_connection("processor_a", "merger", "result", "input_a")
workflow.add_connection("processor_b", "merger", "result", "input_b")

```

## Convergence Strategies

### 1. Expression-Based Convergence

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Simple expression
workflow = Workflow("example", name="Example")
workflow.workflow.connect("validator", "processor",
    cycle=True,
    convergence_check="quality >= 0.9")

# Complex expression
workflow = Workflow("example", name="Example")
workflow.workflow.connect("validator", "processor",
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

workflow = Workflow("convergence_example", "Custom convergence example")
workflow.add_connection("validator", "processor", "feedback", "data",
    cycle=True,
    convergence_callback=custom_convergence)

```

### 3. Multi-Criteria Convergence

```python
# Combine multiple convergence criteria
workflow = Workflow("multi_criteria", "Multi-criteria convergence example")
workflow.add_connection("validator", "processor", "feedback", "data",
    cycle=True,
    max_iterations=100,
    convergence_check="converged or quality >= 0.95",
    timeout=300.0)  # 5-minute timeout

```

## Best Practices

### 1. Always Set Safety Limits

```python
# ❌ BAD - No safety limits
workflow = Workflow("unsafe_cycle", "Unsafe cycle example")
workflow.add_connection("a", "b", "output", "input", cycle=True)

# ✅ GOOD - Multiple safety mechanisms
workflow = Workflow("safe_cycle", "Safe cycle example")
workflow.add_connection("a", "b", "output", "input",
    cycle=True,
    max_iterations=100,      # Iteration limit
    timeout=600.0,          # Time limit
    convergence_check="converged")  # Exit condition

```

### 2. Handle First Iteration Gracefully

```python
class CycleAwareNode(Node):
    def __init__(self, node_id=None):
        super().__init__(node_id)
        
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
    
    def initialize_processing(self, data):
        # Initialize processing for first iteration
        return {'result': data, 'initialized': True}
    
    def refine_processing(self, data, prev_state):
        # Refine processing for subsequent iterations
        return {'result': data, 'refined': True, 'iteration': prev_state.get('iteration', 0) + 1}

```

### 3. Design for Testability

```python
# Use flexible assertions for non-deterministic iteration counts
def test_cyclic_workflow():
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow)

    # ❌ BAD - Too specific
    # assert results['processor']['iteration_count'] == 5

    # ✅ GOOD - Flexible assertions
    processor_result = results.get('processor', {})
    if isinstance(processor_result, dict):
        iteration_count = processor_result.get('iteration_count', 0)
        assert 1 <= iteration_count <= 10
        assert processor_result.get('converged', False) is True
        assert processor_result.get('quality', 0) >= 0.9

```

### 4. Monitor Cycle Performance

```python
import time

# Add monitoring to track cycle behavior
workflow = Workflow("monitored_cycle", "Cycle with performance monitoring")
workflow.add_node("monitor", PythonCodeNode(code="""
import time
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
    'quality': locals().get('quality', 0)
})

result = {'metrics': metrics}
"""))

```

## Common Pitfalls and Solutions

### 1. Configuration vs Runtime Data

```python
# ❌ WRONG - Common mistake
# workflow.add_node("proc", PythonCodeNode(
#     data=[1, 2, 3],  # Error: 'data' is not a config parameter!
#     initial_value=10))  # Error: runtime data as config!

# ✅ CORRECT - Proper separation
workflow = Workflow("config_runtime_example", "Configuration vs Runtime Data")
workflow.add_node("proc", PythonCodeNode(
    code="result = [x * 2 for x in data]"))  # Config: HOW to process

# Pass runtime data through connections or parameters
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow,
    parameters={"proc": {"data": [1, 2, 3]}})

```

### 2. Unmarked Cycles

```python
# ❌ WRONG - Creates illegal cycle
workflow = Workflow("illegal_cycle", "Unmarked cycle example")
workflow.add_connection("a", "b", "output", "input")
workflow.add_connection("b", "c", "output", "input")
# workflow.add_connection("c", "a", "output", "input")  # Error: Unmarked cycle!

# ✅ CORRECT - Mark the cycle
workflow = Workflow("marked_cycle", "Properly marked cycle")
workflow.add_connection("a", "b", "output", "input")
workflow.add_connection("b", "c", "output", "input")
workflow.add_connection("c", "a", "output", "input",
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
import statistics

class EfficientNode(Node):
    def __init__(self, node_id=None):
        super().__init__(node_id)
        
    def run(self, data=None, **kwargs):
        # Process data efficiently
        processed_data = [x * 1.1 for x in (data if isinstance(data, list) else [])]
        converged = len(processed_data) > 0 and statistics.mean(processed_data) < 100
        
        # Don't store entire datasets
        return {
            'result': processed_data,
            'summary': {  # Small state object
                'count': len(processed_data),
                'mean': statistics.mean(processed_data) if processed_data else 0,
                'converged': converged
            }
        }

```

### 2. Early Exit Strategies

```python
# Check multiple convergence criteria for early exit
workflow = Workflow("early_exit", "Early exit strategies example")
workflow.add_connection("validator", "processor", "feedback", "data",
    cycle=True,
    convergence_check=(
        "quality >= target_quality or "
        "improvement < 0.001 or "
        "iteration > min_iterations and quality > acceptable_quality"
    ))

```

### 3. Parallel Cycle Execution

```python
# Use LocalRuntime which supports parallel execution of independent cycles
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)  # Independent cycles can run in parallel

# Monitor execution performance
print(f"Workflow execution completed with run_id: {run_id}")
for node_id, result in results.items():
    print(f"Node {node_id}: {type(result).__name__}")

```

## Real-World Examples

### 1. Machine Learning Model Training

```python
# Iterative model training with early stopping
workflow = Workflow("ml_training", "Iterative model training")

# Use PythonCodeNode to simulate ML training components
workflow.add_node("data_loader", PythonCodeNode(code="""
# Load training data
result = {'data': list(range(1000)), 'labels': list(range(1000))}
"""))

workflow.add_node("trainer", PythonCodeNode(code="""
# Train model iteration
import random
epoch = context.get('cycle', {}).get('iteration', 0)
loss = max(0.1, 1.0 / (epoch + 1) + random.uniform(-0.1, 0.1))
model_state = {'weights': [random.random() for _ in range(10)], 'loss': loss}
result = {'model': model_state, 'loss': loss}
"""))

workflow.add_node("validator", PythonCodeNode(code="""
# Validate model performance
val_loss = model.get('loss', 1.0) + 0.05
val_loss_improved = val_loss < context.get('cycle', {}).get('node_state', {}).get('prev_loss', 999)
result = {'val_loss': val_loss, 'val_loss_improved': val_loss_improved, 'prev_loss': val_loss}
"""))

# Training cycle with early stopping
workflow.add_connection("data_loader", "trainer", "result", "data")
workflow.add_connection("trainer", "validator", "result", "model")
workflow.add_connection("validator", "trainer", "result", "validation",
    cycle=True,
    max_iterations=100,
    convergence_check="val_loss < 0.15")

```

### 2. Document Refinement with LLM

```python
from kailash.nodes.ai import LLMAgentNode

# Iterative document improvement
workflow = Workflow("doc_refinement", "LLM-based document refinement")

workflow.add_node("llm", LLMAgentNode(
    model="gpt-4",
    system_prompt="You are a document editor. Refine the document based on feedback."))

workflow.add_node("evaluator", PythonCodeNode(code="""
# Evaluate document quality
import random
clarity_score = random.uniform(0.7, 1.0)
completeness_score = random.uniform(0.6, 1.0)
accuracy_score = random.uniform(0.8, 1.0)

overall_score = (clarity_score + completeness_score + accuracy_score) / 3
feedback = {
    'clarity': clarity_score,
    'completeness': completeness_score,
    'accuracy': accuracy_score,
    'overall': overall_score,
    'needs_refinement': overall_score < 0.9
}
result = feedback
"""))

# Refinement cycle
workflow.add_connection("llm", "evaluator", "result", "document")
workflow.add_connection("evaluator", "llm", "result", "feedback",
    cycle=True,
    max_iterations=5,
    convergence_check="overall >= 0.9")")

```

### 3. Data Quality Improvement

```python
# Iterative data cleaning and validation
workflow = Workflow("data_quality", "Iterative data quality improvement")

workflow.add_node("cleaner", PythonCodeNode(code="""
# Clean data iteratively
import random

# Simulate data cleaning improvements
data_quality = data.get('quality', 0.5)
cleaned_data = {
    'records': [{'id': i, 'value': random.randint(1, 100)} for i in range(100)],
    'quality': min(1.0, data_quality + 0.1),
    'duplicates_removed': True,
    'formats_fixed': True
}
result = cleaned_data
"""))

workflow.add_node("quality_checker", PythonCodeNode(code="""
# Check data quality metrics
completeness = len([r for r in data['records'] if r.get('value') is not None]) / len(data['records'])
consistency = data.get('quality', 0)
accuracy = min(1.0, completeness * consistency)

quality_metrics = {
    'completeness': completeness,
    'consistency': consistency,
    'accuracy': accuracy,
    'overall_quality': (completeness + consistency + accuracy) / 3,
    'quality': data.get('quality', 0)
}
result = quality_metrics
"""))

# Quality improvement cycle
workflow.add_connection("cleaner", "quality_checker", "result", "data")
workflow.add_connection("quality_checker", "cleaner", "result", "data",
    cycle=True,
    max_iterations=10,
    convergence_check="overall_quality > 0.95")

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
workflow.add_node("processor", PythonCodeNode(
    code="result = [x * 0.9 for x in data]"))
workflow.add_node("evaluator", PythonCodeNode(
    code="quality = sum(result) / len(result) if result else 0"))

# Create cycle
workflow.add_connection("processor", "evaluator", "result", "result")
workflow.add_connection("evaluator", "processor", "quality", "feedback",
    cycle=True,
    max_iterations=10,
    convergence_check="quality >= 0.9")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow,
    parameters={"processor": {"data": [110, 120, 130, 90, 80]}})

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
workflow = Workflow("debug_cycle", "Cycle debugging example")
workflow.add_node("debugger", PythonCodeNode(code="""
print(f"Iteration: {context.get('cycle', {}).get('iteration', 0)}")
print(f"Previous state: {context.get('cycle', {}).get('node_state')}")
result = data  # Pass through
"""))

```

### 3. Visualize Cycle Execution

```python
# Use runtime execution to understand cycle behavior
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

# Analyze cycle results
for node_id, node_result in results.items():
    if isinstance(node_result, dict) and 'iteration' in str(node_result):
        print(f"Node {node_id} completed with results: {node_result}")
        
# Access execution metadata if available
if hasattr(runtime, 'get_execution_metadata'):
    metadata = runtime.get_execution_metadata(run_id)
    print(f"Execution metadata: {metadata}")

```

## Summary

Cyclic workflows in Kailash SDK provide powerful iterative processing capabilities while maintaining the safety and structure of workflow-based systems. Key points to remember:

1. **Always mark cycles explicitly** with `cycle=True`
2. **Separate configuration from runtime data** - config defines HOW, runtime is WHAT
3. **Use safety limits** - max_iterations, timeouts, convergence checks
4. **Handle state safely** with the `or {}` pattern
5. **Write flexible tests** that don't depend on exact iteration counts

With these patterns and practices, you can build sophisticated iterative workflows that handle complex processing requirements while remaining maintainable and testable.
