# Cyclic Workflows Basics

## Basic Cycle Setup

```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.code import PythonCodeNode

# Create workflow with cycle
workflow = Workflow("cycle-001", name="basic_cycle")

# Add nodes
workflow.add_node("counter", PythonCodeNode(), code='''
try:
    current_count = count  # Receive from previous iteration
except:
    current_count = 0      # Default for first iteration

# Increment and create result
current_count += 1
result = {
    "count": current_count,
    "done": current_count >= 5
}
''')

# Connect with cycle - ONLY mark closing edge as cycle=True
workflow.connect("counter", "counter",
    mapping={"result.count": "count"},  # Use nested path for PythonCodeNode
    cycle=True,
    max_iterations=10,
    convergence_check="done == True")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)
```

## Parameter Mapping Patterns

### ✅ Correct: Nested Path Mapping for PythonCodeNode
```python
# PythonCodeNode returns nested structure
workflow.connect("nodeA", "nodeB",
    mapping={"result.count": "count"},      # Access nested field
    cycle=True,
    max_iterations=10)
```

### ✅ Correct: Direct Field Mapping for Regular Nodes
```python
# Regular nodes return flat structure
workflow.connect("nodeA", "nodeB",
    mapping={"count": "count"},             # Direct field access
    cycle=True,
    max_iterations=10)
```

### ❌ Wrong: Flat mapping for nested structure
```python
# This won't work with PythonCodeNode
workflow.connect("nodeA", "nodeB",
    mapping={"count": "count"},             # Missing nested path
    cycle=True)
```

## PythonCodeNode Cycle Parameter Access

### Always Use Try/Except Pattern
```python
code = '''
# ALWAYS wrap cycle parameters in try/except
try:
    # Access parameters from previous iteration
    current_value = value
    iteration_data = data
    quality_score = quality
    print(f"Received: value={current_value}, quality={quality_score}")
except NameError as e:
    # Provide defaults for first iteration
    current_value = 0
    iteration_data = []
    quality_score = 0.0
    print(f"First iteration, using defaults: {e}")

# Process data
current_value += 1
processed_data = iteration_data + [current_value]
quality_score = min(1.0, quality_score + 0.1)

# Create result with proper structure
result = {
    "value": current_value,
    "data": processed_data,
    "quality": quality_score,
    "done": current_value >= 5
}
'''
```

## Multi-Node Cycle Edge Marking

### ✅ Correct: Only Mark Closing Edge
```python
# For cycle: A → B → C → A
workflow.add_node("nodeA", ProcessorA())
workflow.add_node("nodeB", ProcessorB())
workflow.add_node("nodeC", ProcessorC())

# Regular connections
workflow.connect("nodeA", "nodeB")        # Regular edge
workflow.connect("nodeB", "nodeC")        # Regular edge

# ONLY mark the closing edge as cycle
workflow.connect("nodeC", "nodeA",        # Closing edge
    cycle=True,
    max_iterations=10,
    convergence_check="done == True")
```

### ❌ Wrong: Marking multiple edges
```python
# Don't mark multiple edges as cycle=True
workflow.connect("nodeA", "nodeB", cycle=True)  # ❌ Wrong
workflow.connect("nodeB", "nodeC", cycle=True)  # ❌ Wrong
workflow.connect("nodeC", "nodeA", cycle=True)  # ❌ Wrong
```

## Convergence Conditions

### Expression-Based Convergence
```python
# Simple boolean condition
workflow.connect("processor", "processor",
    cycle=True,
    max_iterations=20,
    convergence_check="done == True")

# Numeric threshold
workflow.connect("optimizer", "optimizer",
    cycle=True,
    max_iterations=50,
    convergence_check="error < 0.01")

# Multiple conditions
workflow.connect("analyzer", "analyzer",
    cycle=True,
    max_iterations=30,
    convergence_check="quality >= 0.95 and stable == True")
```

### Callback-Based Convergence
```python
def custom_convergence(iteration, outputs, context):
    """Custom convergence logic"""
    last_output = outputs.get("processor", {})
    error = last_output.get("error", float('inf'))

    # Converge if error is small or improvement stopped
    if error < 0.001:
        return True, "Error threshold reached"

    if iteration > 5:
        prev_error = context.get("previous_error", float('inf'))
        improvement = (prev_error - error) / prev_error if prev_error > 0 else 0

        if improvement < 0.01:  # Less than 1% improvement
            return True, "Improvement too small"

    # Store for next iteration
    context["previous_error"] = error
    return False, f"Continuing (error: {error:.4f})"

workflow.connect("processor", "processor",
    cycle=True,
    max_iterations=100,
    convergence_callback=custom_convergence)
```

## Data Flow Patterns

### Data Entry Patterns for Cycles

#### ✅ Correct: Use Source Nodes for Multi-Node Cycles
```python
# For cycles with multiple nodes, ALWAYS use source nodes
class DataSourceNode(CycleAwareNode):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[])
        }

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        return {"data": kwargs.get("data", [])}

workflow = Workflow("multi-node-cycle", "Multi Node Cycle")
workflow.add_node("data_source", DataSourceNode())  # Entry point
workflow.add_node("processor", ProcessorNode())
workflow.add_node("switch", SwitchNode())

# Connect source to cycle
workflow.connect("data_source", "processor", mapping={"data": "data"})
workflow.connect("processor", "switch", mapping={"output": "input_data"})
workflow.connect("switch", "processor", cycle=True, max_iterations=5)

# Use node-specific parameters
runtime.execute(workflow, parameters={
    "data_source": {"data": [1, 2, 3, 4]}  # Node-specific format
})
```

#### ✅ Correct: Direct Parameters for Simple Self-Loops
```python
# For single-node cycles, direct parameters work
workflow.add_node("processor", PythonCodeNode(name="processor", code=code))
workflow.connect("processor", "processor", cycle=True, max_iterations=5)

# Direct parameter passing
runtime.execute(workflow, parameters={
    "value": 10,      # Direct parameters for simple cycles
    "target": 100
})
```

#### ❌ Wrong: Workflow-Level Parameters for Multi-Node Cycles
```python
# This DOESN'T work for multi-node cycles
workflow.add_node("processor", ProcessorNode())
workflow.add_node("switch", SwitchNode())
workflow.connect("processor", "switch")
workflow.connect("switch", "processor", cycle=True)

# Wrong - parameters won't reach cycle nodes
runtime.execute(workflow, parameters={
    "data": [1, 2, 3, 4]  # This doesn't reach cycle nodes
})
# Result: ValueError: Required parameter 'data' not provided
```

### Pass Initial Data to Cycles
```python
# Option 1: Via node-specific parameters (recommended for cycles)
runtime.execute(workflow, parameters={
    "processor": {"data": [1, 2, 3], "threshold": 0.8}
})

# Option 2: Via source node + parameter override
workflow.add_node("reader", CSVReaderNode(), file_path="data.csv")
workflow.connect("reader", "processor")
runtime.execute(workflow, parameters={
    "reader": {"file_path": "custom_data.csv"}  # Override at runtime
})
```

### Preserve Data Across Iterations
```python
class DataProcessorNode(Node):
    def run(self, context, **kwargs):
        # Get cycle context
        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        # Get data (from previous iteration or initial)
        data = kwargs.get("data", [])

        # Process data
        processed = [x * 1.1 for x in data]  # 10% improvement each iteration

        # Determine convergence
        improvement = sum(processed) - sum(data) if data else 0
        done = improvement < 0.01 or iteration >= 20

        return {
            "data": processed,
            "improvement": improvement,
            "done": done,
            "iteration": iteration
        }
```

## Cycle Safety and Limits

### Always Set Safety Limits
```python
workflow.connect("processor", "processor",
    cycle=True,
    max_iterations=50,              # Prevent infinite loops
    timeout=300.0,                  # 5 minute timeout
    convergence_check="done == True")
```

### Memory Management in Cycles
```python
class MemoryEfficientNode(Node):
    def run(self, context, **kwargs):
        data = kwargs.get("data", [])

        # Process in chunks to avoid memory buildup
        chunk_size = 1000
        results = []

        for i in range(0, len(data), chunk_size):
            chunk = data[i:i+chunk_size]
            processed_chunk = self.process_chunk(chunk)
            results.extend(processed_chunk)

            # Clear intermediate results
            del chunk, processed_chunk

        return {"data": results, "count": len(results)}
```

## Common Cycle Patterns

### Quality Improvement Loop
```python
workflow = Workflow("quality-loop", "Quality Improvement")

workflow.add_node("processor", QualityProcessorNode())
workflow.add_node("validator", QualityValidatorNode())

# Process → Validate → Process (if not good enough)
workflow.connect("processor", "validator")
workflow.connect("validator", "processor",
    mapping={"data": "data", "feedback": "feedback"},
    cycle=True,
    max_iterations=20,
    convergence_check="quality_sufficient == True")
```

### Iterative Optimization
```python
workflow = Workflow("optimization", "Parameter Optimization")

workflow.add_node("optimizer", ParameterOptimizerNode())
workflow.add_node("evaluator", ModelEvaluatorNode())

# Optimize → Evaluate → Optimize (until converged)
workflow.connect("optimizer", "evaluator")
workflow.connect("evaluator", "optimizer",
    mapping={"parameters": "parameters", "score": "feedback"},
    cycle=True,
    max_iterations=100,
    convergence_check="score_improvement < 0.001")
```

### Data Cleaning Loop
```python
workflow = Workflow("cleaning-loop", "Iterative Data Cleaning")

workflow.add_node("cleaner", DataCleanerNode())
workflow.add_node("checker", QualityCheckerNode())

# Clean → Check → Clean (until clean enough)
workflow.connect("cleaner", "checker")
workflow.connect("checker", "cleaner",
    mapping={"data": "data", "issues": "issues_found"},
    cycle=True,
    max_iterations=10,
    convergence_check="issues_found == 0")
```
