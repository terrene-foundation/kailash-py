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
from kailash.runtime.local import LocalRuntime
from kailash.nodes.code import PythonCodeNode

# Create workflow with iterative data refinement
workflow = Workflow("cyclic_example", "Simple cyclic workflow example")

# Add nodes
workflow.add_node("data_source", PythonCodeNode(code="result = [110, 120, 130, 90, 80]"))
workflow.add_node("processor", PythonCodeNode(code="""
# Process data, applying feedback if available
try:
    if feedback and feedback.get('needs_adjustment', False):
        result = [x * 0.9 for x in data]
    else:
        result = data
except NameError:
    # First iteration - no feedback yet
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
# Must set result for PythonCodeNode
result = feedback
"""))

# Connect nodes with cycle
workflow.connect("data_source", "processor", mapping={"result": "data"})
workflow.connect("processor", "evaluator", mapping={"result": "result"})
workflow.connect("evaluator", "processor", mapping={"result": "feedback"},
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
workflow.connect("validator", "processor", mapping={"output": "input"},
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
from kailash.runtime.local import LocalRuntime
from kailash.nodes.code import PythonCodeNode

# Create workflow
workflow = Workflow("refinement_loop", "Iterative refinement example")

# Add nodes
workflow.add_node("source", PythonCodeNode(code="result = [110, 120, 130, 90, 80]"))
workflow.add_node("processor", PythonCodeNode(code="""
# Refine data based on feedback
try:
    if feedback and feedback.get('adjust', False):
        result = [x * 0.9 for x in data]
    else:
        result = data
except NameError:
    # First iteration - no feedback yet
    result = data
"""))

workflow.add_node("validator", PythonCodeNode(code="""
# Check if refinement is needed
quality = sum(result) / len(result) if result else 0
feedback = {'adjust': quality > 100, 'quality': quality}
# Must set result for PythonCodeNode
result = feedback
"""))

# Connect with cycle
workflow.connect("source", "processor", mapping={"result": "data"})
workflow.connect("processor", "validator", mapping={"result": "result"})
workflow.connect("validator", "processor", mapping={"result": "feedback"},
    cycle=True,
    max_iterations=5,
    convergence_check="quality <= 100")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

```

### 2. Multi-Node Cycle

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
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
workflow.connect("input", "preprocessor", mapping={"result": "data"})
workflow.connect("preprocessor", "analyzer", mapping={"result": "data"})
workflow.connect("analyzer", "optimizer", mapping={"result": "data"})
workflow.connect("optimizer", "evaluator", mapping={"result": "data"})
workflow.connect("evaluator", "preprocessor", mapping={"result": "data"},
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
workflow.connect("outer_validator", "outer_processor", mapping={"feedback": "input"},
    cycle=True,
    cycle_id="outer_loop",
    max_iterations=5)

# Inner cycle for fine-tuning
workflow.connect("inner_validator", "inner_processor", mapping={"refinement": "input"},
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
workflow.connect("conditional_router", "refiner", mapping={"refine": "input"})
workflow.connect("refiner", "processor", mapping={"result": "data"},
    cycle=True,
    max_iterations=10)

```

### 3. Parallel Cycles

```python
# Multiple independent cycles running in parallel
from kailash.nodes.logic import MergeNode

workflow = Workflow("parallel_cycles", "Parallel iterative processes")

# Branch A with its own cycle
workflow.connect("validator_a", "processor_a", mapping={"feedback_a": "input"},
    cycle=True,
    cycle_id="cycle_a",
    max_iterations=10)

# Branch B with different convergence criteria
workflow.connect("validator_b", "processor_b", mapping={"feedback_b": "input"},
    cycle=True,
    cycle_id="cycle_b",
    convergence_check="variance < 0.1")

# Merge results after both cycles complete
workflow.add_node("merger", MergeNode())
workflow.connect("processor_a", "merger", mapping={"result": "input_a"})
workflow.connect("processor_b", "merger", mapping={"result": "input_b"})

```

## Convergence Strategies

### 1. Expression-Based Convergence

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
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
workflow.connect("validator", "processor", mapping={"feedback": "data"},
    cycle=True,
    convergence_callback=custom_convergence)

```

### 3. Multi-Criteria Convergence

```python
# Combine multiple convergence criteria
workflow = Workflow("multi_criteria", "Multi-criteria convergence example")
workflow.connect("validator", "processor", mapping={"feedback": "data"},
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
workflow.connect("a", "b", mapping={"output": "input"}, cycle=True)

# ✅ GOOD - Multiple safety mechanisms
workflow = Workflow("safe_cycle", "Safe cycle example")
workflow.connect("a", "b", mapping={"output": "input"},
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
    'quality': globals().get('quality', 0)
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
workflow.connect("a", "b", mapping={"output": "input"})
workflow.connect("b", "c", mapping={"output": "input"})
# workflow.connect("c", "a", mapping={"output": "input"})  # Error: Unmarked cycle!

# ✅ CORRECT - Mark the cycle
workflow = Workflow("marked_cycle", "Properly marked cycle")
workflow.connect("a", "b", mapping={"output": "input"})
workflow.connect("b", "c", mapping={"output": "input"})
workflow.connect("c", "a", mapping={"output": "input"},
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
workflow.connect("validator", "processor", mapping={"feedback": "data"},
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
workflow.connect("data_loader", "trainer", mapping={"result": "data"})
workflow.connect("trainer", "validator", mapping={"result": "model"})
workflow.connect("validator", "trainer", mapping={"result": "validation"},
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
workflow.connect("llm", "evaluator", mapping={"result": "document"})
workflow.connect("evaluator", "llm", mapping={"result": "feedback"},
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
workflow.connect("cleaner", "quality_checker", mapping={"result": "data"})
workflow.connect("quality_checker", "cleaner", mapping={"result": "data"},
    cycle=True,
    max_iterations=10,
    convergence_check="overall_quality > 0.95")

```

### 4. Production-Ready Text Processing Pipeline

```python
"""
Production-ready cyclic workflow for iterative text cleaning and validation.
Demonstrates best practices without external dependencies.
"""

from kailash import Workflow
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime

# Create production workflow
workflow = Workflow("text_processing_pipeline", "Production text cleaning with validation")

# Text cleaning node with iterative improvements
workflow.add_node("text_cleaner", PythonCodeNode(code="""
import re

# Handle input data
try:
    text = data.get('text', '') if isinstance(data, dict) else str(data)
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
workflow.add_node("text_validator", PythonCodeNode(code="""
# Get cleaned text and metadata
text = data.get('text', '')
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
workflow.connect("text_cleaner", "text_validator", mapping={"result": "data"})
workflow.connect("text_validator", "text_cleaner", mapping={"result": "data"},
    cycle=True,
    max_iterations=5,
    convergence_check="converged == True")

# Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

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
workflow = Workflow("refine_data", "Data refinement workflow")

# Add nodes
workflow.add_node("processor", PythonCodeNode(
    code="result = [x * 0.9 for x in data]"))
workflow.add_node("evaluator", PythonCodeNode(
    code="quality = sum(result) / len(result) if result else 0; result = quality"))

# Create cycle
workflow.connect("processor", "evaluator", mapping={"result": "result"})
workflow.connect("evaluator", "processor", mapping={"quality": "feedback"},
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
