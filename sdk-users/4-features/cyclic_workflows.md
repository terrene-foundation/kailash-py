# ⚠️ CYCLIC WORKFLOWS - PLANNED FEATURE

> **STATUS**: This feature is planned but NOT YET IMPLEMENTED in the current SDK version (v0.9.31).
>
> Cyclic workflows (iterative processing, feedback loops) are under active development.
> The CycleBuilder API and patterns shown in this documentation represent the planned interface.
>
> **Current Alternatives**:
> - Manual iteration with Python loops around workflow execution
> - Recursive workflow calls with state management
> - Conditional routing with SwitchNode for state machines
> - Sequential executions with external iteration control

---

# Cyclic Workflows in Kailash SDK (PLANNED)

## Overview (Future Capability)

Cyclic workflows will enable iterative processing patterns where data flows back through earlier nodes in the workflow graph. This powerful feature will support use cases like:

- **Iterative refinement**: Continuously improve results until they meet quality criteria
- **Convergence algorithms**: Iterate until a stable state is reached
- **Feedback loops**: Process data multiple times based on validation results
- **Self-improving systems**: AI agents that refine their outputs through multiple passes

## Quick Start Example

```python
# Complete working example of a cyclic workflow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.code import PythonCodeNode

# Create workflow with iterative data refinement
workflow = WorkflowBuilder()

# Add nodes
workflow.add_node("PythonCodeNode", "data_source", {
    "code": "result = {'data': [110, 120, 130], 'iteration': 0}"
})

workflow.add_node("PythonCodeNode", "processor", {
    "code": """
try:
    data = input_data.get('data', [100])
    iteration = input_data.get('iteration', 0)
except NameError:
    # First iteration - no feedback yet
    data = [100]
    iteration = 0

# Process data (reduce by 10%)
processed_data = [x * 0.9 for x in data]
iteration += 1

result = {
    'data': processed_data,
    'iteration': iteration,
    'average': sum(processed_data) / len(processed_data)
}
"""
})

workflow.add_node("PythonCodeNode", "evaluator", {
    "code": """
# Get processed data
data = input_data.get('data', [])
iteration = input_data.get('iteration', 0)
average = input_data.get('average', 0)

# Check convergence
converged = average < 100
feedback = {
    'average': average,
    'needs_adjustment': not converged,
    'quality_score': 1.0 / (average / 100) if average > 0 else 1.0,
    'converged': converged,
    'iteration': iteration
}

result = feedback
"""
})

# Connect nodes
workflow.add_connection("data_source", "result", "processor", "input_data")
workflow.add_connection("processor", "result", "evaluator", "input_data")

# Build workflow first, then create cycle
built_workflow = workflow.build()

# CRITICAL: Create cycle using modern CycleBuilder API
# IMPORTANT: Use "result." prefix for PythonCodeNode outputs in mappings
cycle_builder = built_workflow.create_cycle("quality_improvement")
cycle_builder.connect("evaluator", "processor", mapping={"result.current_value": "input_data"}) \
             .max_iterations(10) \
             .converge_when("converged == True") \
             .timeout(300) \
             .build()

# Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(built_workflow)
print(f"Final results: {results}")
```

## Key Concepts

### 1. Marked Cycles

Unlike traditional DAGs (Directed Acyclic Graphs), Kailash workflows support cycles when explicitly marked:

```python
# Creating a cycle requires explicit marking
workflow = WorkflowBuilder()
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()   # Stop condition

```

### 2. Configuration vs Runtime Parameters

**Critical distinction** that causes most cyclic workflow issues:

- **Configuration parameters** (HOW): Define node behavior - code, models, file paths
- **Runtime parameters** (WHAT): Data that flows through connections

```python

# ❌ WRONG - Passing runtime data as configuration
# workflow.add_node("PythonCodeNode", "processor", {}),
#     data=[1, 2, 3])  # Error: 'data' is not a config parameter!

# ✅ CORRECT - Configuration defines behavior
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "processor", {}))  # HOW to process

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
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.code import PythonCodeNode

# Create workflow
workflow = WorkflowBuilder()

# Add nodes
workflow.add_node("PythonCodeNode", "source", {
    "code": "result = {'data': [120, 150, 110], 'iteration': 0}"
})

workflow.add_node("PythonCodeNode", "processor", {
    "code": """
try:
    data = input_data.get('data', [100])
    iteration = input_data.get('iteration', 0)
except NameError:
    data = [100]
    iteration = 0

# Process data - reduce by 10%
processed_data = [x * 0.9 for x in data]
iteration += 1

result = {
    'data': processed_data,
    'iteration': iteration,
    'quality': sum(processed_data) / len(processed_data)
}
"""
})

workflow.add_node("PythonCodeNode", "validator", {
    "code": """
data = input_data.get('data', [])
iteration = input_data.get('iteration', 0)
quality = input_data.get('quality', 0)

converged = quality <= 100
result = {
    'data': data,
    'iteration': iteration,
    'quality': quality,
    'converged': converged
}
"""
})

# Connect nodes
workflow.add_connection("source", "result", "processor", "input_data")
workflow.add_connection("processor", "result", "validator", "input_data")

# Build workflow and create cycle
built_workflow = workflow.build()
cycle_builder = built_workflow.create_cycle("refinement_cycle")
# CRITICAL: Use "result." prefix for PythonCodeNode outputs
cycle_builder.connect("validator", "processor", mapping={"result.data": "input_data"}) \
             .max_iterations(15) \
             .converge_when("converged == True") \
             .timeout(300) \
             .build()

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(built_workflow)

```

### 2. Multi-Node Cycle

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Complex cycle with multiple nodes
workflow = WorkflowBuilder()

# Add nodes for complex processing
workflow.add_node("PythonCodeNode", "input", {}))
workflow.add_node("PythonCodeNode", "preprocessor", {})]
result = {'data': processed_data, 'preprocessed': True}
"""))
workflow.add_node("PythonCodeNode", "analyzer", {})) / len(data.get('data', [1]))
result = dict(data, **{'analysis_score': analysis_score})
"""))
workflow.add_node("PythonCodeNode", "optimizer", {})]
result = dict(data, **{'data': optimized_data, 'optimized': True})
"""))
workflow.add_node("PythonCodeNode", "evaluator", {}) * 1.1)
result = dict(data, **{'score': score, 'converged': score >= 0.9})
"""))

# Create cycle through multiple nodes
workflow.add_connection("input", "preprocessor", "result", "data")
workflow.add_connection("preprocessor", "analyzer", "result", "data")
workflow.add_connection("analyzer", "optimizer", "result", "data")
workflow.add_connection("optimizer", "evaluator", "result", "data")
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build() >= 0.9")

```

## Advanced Patterns

### 1. Nested Cycles

```python
# Workflow with nested cycles
workflow = WorkflowBuilder()

# Outer cycle for major iterations
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

# Inner cycle for fine-tuning
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

```

### 2. Conditional Cycles

```python
# Cycle that only activates under certain conditions
from kailash.nodes.logic import SwitchNode

workflow = WorkflowBuilder()
workflow.add_node("SwitchNode", "conditional_router", {}))

# Add refinement nodes
workflow.add_node("PythonCodeNode", "refiner", {}))
workflow.add_node("PythonCodeNode", "processor", {})"))

# Cycle only when refinement is needed
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

```

### 3. Parallel Cycles

```python
# Multiple independent cycles running in parallel
from kailash.nodes.logic import MergeNode

workflow = WorkflowBuilder()

# Branch A with its own cycle
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

# Branch B with different convergence criteria
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

# Merge results after both cycles complete
workflow.add_node("MergeNode", "merger", {}))
workflow.add_connection("processor_a", "merger", "result", "input_a")
workflow.add_connection("processor_b", "merger", "result", "input_b")

```

## Convergence Strategies

### 1. Expression-Based Convergence

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Simple expression
workflow = WorkflowBuilder()
# Workflow setup goes here  # Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

# Complex expression
workflow = WorkflowBuilder()
# Workflow setup goes here  # Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

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

workflow = WorkflowBuilder()
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

```

### 3. Multi-Criteria Convergence

```python
# Combine multiple convergence criteria
workflow = WorkflowBuilder()
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()  # 5-minute timeout

```

## Best Practices

### 1. Always Set Safety Limits

```python
# ❌ BAD - No safety limits
workflow = WorkflowBuilder()
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

# ✅ GOOD - Multiple safety mechanisms
workflow = WorkflowBuilder()
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()  # Exit condition

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
    results, run_id = runtime.execute(workflow.build())

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
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "monitor", {})
iteration = cycle_info.get('iteration', 0)

if iteration == 0:
    metrics = {'start_time': time.time(), 'iterations': []}
else:
    metrics = context['cycle']['node_state'].get('metrics', {})

metrics['iterations'].append({
    'iteration': iteration,
    'timestamp': time.time(),
    'quality': globals().get('quality', 0)
})

result = {'metrics': metrics}
"""))

```

## Common Pitfalls and Solutions

### 1. Configuration vs Runtime Data

```python
# ❌ WRONG - Common mistake
# workflow.add_node("PythonCodeNode", "proc", {}))  # Error: runtime data as config!

# ✅ CORRECT - Proper separation
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "proc", {}))  # Config: HOW to process

# Pass runtime data through connections or parameters
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow,
    parameters={"proc": {"data": [1, 2, 3]}})

```

### 2. Unmarked Cycles

```python
# ❌ WRONG - Creates illegal cycle
workflow = WorkflowBuilder()
workflow.add_connection("a", "b", "output", "input")
workflow.add_connection("b", "c", "output", "input")
# workflow.add_connection("c", "a", "output", "input")  # Error: Unmarked cycle!

# ✅ CORRECT - Mark the cycle
workflow = WorkflowBuilder()
workflow.add_connection("a", "b", "output", "input")
workflow.add_connection("b", "c", "output", "input")
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

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
workflow = WorkflowBuilder()
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build())

```

### 3. Parallel Cycle Execution

```python
# Use LocalRuntime which supports parallel execution of independent cycles
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())  # Independent cycles can run in parallel

# Monitor execution performance
print(f"Workflow execution completed with run_id: {run_id}")
for node_id, result in results.items():
    print(f"Node {node_id}: {type(result).__name__}")

```

## Real-World Examples

### 1. Machine Learning Model Training

```python
# Iterative model training with early stopping
workflow = WorkflowBuilder()

# Use PythonCodeNode to simulate ML training components
workflow.add_node("PythonCodeNode", "data_loader", {})), 'labels': list(range(1000))}
"""))

workflow.add_node("PythonCodeNode", "trainer", {}).get('iteration', 0)
loss = max(0.1, 1.0 / (epoch + 1) + random.uniform(-0.1, 0.1))
model_state = {'weights': [random.random() for _ in range(10)], 'loss': loss}
result = {'model': model_state, 'loss': loss}
"""))

workflow.add_node("PythonCodeNode", "validator", {}) + 0.05
val_loss_improved = val_loss < context.get('cycle', {}).get('node_state', {}).get('prev_loss', 999)
result = {'val_loss': val_loss, 'val_loss_improved': val_loss_improved, 'prev_loss': val_loss}
"""))

# Training cycle with early stopping
workflow.add_connection("data_loader", "trainer", "result", "data")
workflow.add_connection("trainer", "validator", "result", "model")
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

```

### 2. Document Refinement with LLM

```python
from kailash.nodes.ai import LLMAgentNode

# Iterative document improvement
workflow = WorkflowBuilder()

workflow.add_node("LLMAgentNode", "llm", {}))

workflow.add_node("PythonCodeNode", "evaluator", {})
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
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()")

```

### 3. Data Quality Improvement

```python
# Iterative data cleaning and validation
workflow = WorkflowBuilder()

workflow.add_node("PythonCodeNode", "cleaner", {})
cleaned_data = {
    'records': [{'id': i, 'value': random.randint(1, 100)} for i in range(100)],
    'quality': min(1.0, data_quality + 0.1),
    'duplicates_removed': True,
    'formats_fixed': True
}
result = cleaned_data
"""))

workflow.add_node("PythonCodeNode", "quality_checker", {}) is not None]) / len(data['records'])
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
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

```

### 4. Production-Ready Text Processing Pipeline

```python
"""
Production-ready cyclic workflow for iterative text cleaning and validation.
Demonstrates best practices without external dependencies.
"""

from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime

# Create production workflow
workflow = WorkflowBuilder()

# Text cleaning node with iterative improvements
workflow.add_node("PythonCodeNode", "text_cleaner", {}) if isinstance(data, dict) else str(data)
    iteration = context.get('cycle', {}).get('iteration', 0)
except:
    # First iteration
    text = "  Hello,   WORLD!  This is a TEST...   with BAD formatting!!!  "
    iteration = 0

print(f"\\nText Cleaning Iteration {iteration + 1}")
print(f"Input: '{text}'")

# Perform cleaning operations
cleaned = text

# 1. Strip whitespace
cleaned = cleaned.strip()

# 2. Normalize spaces
cleaned = re.sub(r'\\s+', ' ', cleaned)

# 3. Fix punctuation spacing
cleaned = re.sub(r'\\s+([.,!?])', r'\\1', cleaned)
cleaned = re.sub(r'([.,!?])([A-Za-z])', r'\\1 \\2', cleaned)

# 4. Normalize case (if too much uppercase)
words = cleaned.split()
uppercase_count = sum(1 for w in words if w.isupper() and len(w) > 1)
if uppercase_count > len(words) * 0.3:  # More than 30% uppercase
    cleaned = ' '.join(w.capitalize() if w.isupper() else w for w in words)

# Calculate quality improvement
original_issues = 0
if text != text.strip(): original_issues += 1
if '  ' in text: original_issues += 1
if uppercase_count > len(words) * 0.3: original_issues += 1

quality_score = 1.0 - (original_issues * 0.25)
quality_score = max(0.0, min(1.0, quality_score))

print(f"Output: '{cleaned}'")
print(f"Quality Score: {quality_score:.2f}")

result = {
    'text': cleaned,
    'quality_score': quality_score,
    'iteration': iteration + 1,
    'improvements': original_issues
}
"""))

# Text validation node
workflow.add_node("PythonCodeNode", "text_validator", {})
quality_score = data.get('quality_score', 0.0)
iteration = data.get('iteration', 0)

print(f"\\nValidating Text - Iteration {iteration}")

# Validation checks
issues = []

# Check for remaining issues
if text != text.strip():
    issues.append("Leading/trailing whitespace")
if '  ' in text:
    issues.append("Multiple spaces")
if '...' in text and '...' not in text.replace('...', ''):
    issues.append("Excessive ellipsis")
if text.count('!') > 2:
    issues.append("Excessive exclamation marks")

# Calculate validation score
validation_score = 1.0 - (len(issues) * 0.2)
validation_score = max(0.0, min(1.0, validation_score))

# Determine if another iteration is needed
needs_improvement = len(issues) > 0 and iteration < 5
converged = validation_score >= 0.95 or iteration >= 5

print(f"Validation Score: {validation_score:.2f}")
print(f"Issues Found: {len(issues)}")
if issues:
    for issue in issues:
        print(f"  - {issue}")
print(f"Converged: {converged}")

result = {
    'text': text,
    'validation_score': validation_score,
    'issues': issues,
    'needs_improvement': needs_improvement,
    'converged': converged,
    'iteration': iteration,
    'quality_score': quality_score
}
"""))

# Connect nodes with cycle
workflow.add_connection("text_cleaner", "text_validator", "result", "data")
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

# Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Display final results
final_result = results.get('text_validator', {})
print(f"\\n{'='*60}")
print(f"FINAL RESULTS - Run ID: {run_id}")
print(f"{'='*60}")
print(f"Original Text: '  Hello,   WORLD!  This is a TEST...   with BAD formatting!!!  '")
print(f"Final Text: '{final_result.get('text', '')}'")
print(f"Final Quality Score: {final_result.get('quality_score', 0):.2f}")
print(f"Final Validation Score: {final_result.get('validation_score', 0):.2f}")
print(f"Total Iterations: {final_result.get('iteration', 0)}")
```

This production example demonstrates:
- **Error handling**: Graceful handling of missing or malformed input
- **Progressive improvement**: Each iteration addresses specific issues
- **Quality metrics**: Quantifiable improvement tracking
- **Convergence criteria**: Multiple conditions for termination
- **Debugging output**: Clear visibility into each iteration
- **No external dependencies**: Uses only built-in Python capabilities

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
workflow = WorkflowBuilder()

# Add nodes
workflow.add_node("PythonCodeNode", "processor", {}))
workflow.add_node("PythonCodeNode", "evaluator", {}) / len(result) if result else 0; result = quality"))

# Create cycle
workflow.add_connection("processor", "evaluator", "result", "result")
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

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
results, run_id = runtime.execute(workflow.build())

```

### 2. Track Cycle State

```python
# Add debug node to monitor cycle state
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "debugger", {}).get('iteration', 0)}")
print(f"Previous state: {context.get('cycle', {}).get('node_state')}")
result = data  # Pass through
"""))

```

### 3. Visualize Cycle Execution

```python
# Use runtime execution to understand cycle behavior
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

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

1. **Always mark cycles explicitly** with `# Use CycleBuilder API instead`
2. **Separate configuration from runtime data** - config defines HOW, runtime is WHAT
3. **Use safety limits** - max_iterations, timeouts, convergence checks
4. **Handle state safely** with the `or {}` pattern
5. **Write flexible tests** that don't depend on exact iteration counts

With these patterns and practices, you can build sophisticated iterative workflows that handle complex processing requirements while remaining maintainable and testable.
