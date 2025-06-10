# Cycle Debugging & Troubleshooting

## 🔧 Phase 5.2 Developer Tools (NEW)

### CycleDebugger - Real-time Execution Tracking
```python
from kailash.workflow import CycleDebugger

# Create debugger with detailed tracking
debugger = CycleDebugger(debug_level="detailed", enable_profiling=True)

# Start debugging a cycle
trace = debugger.start_cycle(
    cycle_id="optimization_cycle",
    workflow_id="my_workflow",
    max_iterations=100,
    convergence_condition="error < 0.01"
)

# During cycle execution - track each iteration
input_data = {"value": 10.0, "target": 100.0}
iteration = debugger.start_iteration(trace, input_data)

# After iteration completes
output_data = {"value": 25.0, "error": 0.75}
debugger.end_iteration(trace, iteration, output_data, convergence_value=0.75)

# Complete cycle analysis
debugger.end_cycle(trace, converged=True, termination_reason="convergence")

# Generate comprehensive report
report = debugger.generate_report(trace)
print(f"Efficiency: {report['performance']['efficiency_score']:.3f}")
```

### CycleProfiler - Performance Analysis
```python
from kailash.workflow import CycleProfiler

# Create profiler for performance analysis
profiler = CycleProfiler(enable_advanced_metrics=True)

# Add multiple traces for comparative analysis
profiler.add_trace(trace1)  # Fast cycle
profiler.add_trace(trace2)  # Slow cycle
profiler.add_trace(trace3)  # Failed cycle

# Analyze performance across all cycles
metrics = profiler.analyze_performance()
print(f"Average cycle time: {metrics.avg_cycle_time:.3f}s")
print(f"Bottlenecks: {metrics.bottlenecks}")

# Compare specific cycles
comparison = profiler.compare_cycles(["fast_cycle", "slow_cycle"])
print(f"Best cycle: {comparison['best_cycle']}")

# Get optimization recommendations
recommendations = profiler.get_optimization_recommendations()
for rec in recommendations:
    print(f"[{rec['priority']}] {rec['description']}")
```

### CycleAnalyzer - Comprehensive Analysis Framework
```python
from kailash.workflow import CycleAnalyzer

# Create analyzer with comprehensive analysis
analyzer = CycleAnalyzer(
    analysis_level="comprehensive",
    enable_profiling=True,
    enable_debugging=True,
    output_directory="./analysis_output"
)

# Start analysis session
session = analyzer.start_analysis_session("optimization_study")

# Analyze cycle with automatic tracking
trace = analyzer.start_cycle_analysis("cycle_1", "workflow_1", max_iterations=50)

# Track iterations (integrated with workflow execution)
analyzer.track_iteration(trace, input_data, output_data, convergence_value=0.05)

# Get real-time health metrics
health = analyzer.get_real_time_metrics(trace)
if health['health_score'] < 0.5:
    print("⚠️ Cycle performance issue detected!")

# Complete analysis with comprehensive reporting
analyzer.complete_cycle_analysis(trace, converged=True, termination_reason="convergence")

# Generate session report with insights
session_report = analyzer.generate_session_report()
print(f"Session quality: {session_report['insights']['session_quality']}")

# Export all analysis data
analyzer.export_analysis_data("comprehensive_analysis.json")
```

## 🎯 Developer Tools Integration Patterns

### Pattern 1: Development-Time Cycle Optimization
```python
def optimize_cycle_performance(workflow, cycle_config):
    """Optimize cycle using developer tools."""

    # 1. Start with comprehensive analysis
    analyzer = CycleAnalyzer(analysis_level="comprehensive")
    session = analyzer.start_analysis_session("optimization")

    # 2. Run cycle with analysis
    trace = analyzer.start_cycle_analysis("target_cycle", workflow.workflow_id)

    # Execute workflow with tracking...
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow, parameters=initial_params)

    # 3. Analyze results and get recommendations
    cycle_report = analyzer.generate_cycle_report(trace)

    if cycle_report['performance']['efficiency_score'] < 0.5:
        print("⚠️ Poor performance detected - applying optimizations...")

        # Apply recommended optimizations
        recommendations = cycle_report['recommendations']
        optimized_config = apply_optimizations(cycle_config, recommendations)
        return optimized_config

    return cycle_config
```

### Pattern 2: Production Health Monitoring
```python
def monitor_cycle_health(workflow_execution):
    """Monitor cycle health in production."""

    debugger = CycleDebugger(debug_level="basic", enable_profiling=True)

    # Start monitoring
    trace = debugger.start_cycle("prod_cycle", "production_workflow")

    # During execution, check health periodically
    for iteration_data in workflow_execution:
        iteration = debugger.start_iteration(trace, iteration_data['input'])

        # Simulate processing...

        debugger.end_iteration(trace, iteration, iteration_data['output'])

        # Check for issues
        if iteration.execution_time > 5.0:
            alert_slow_iteration(iteration)

        if iteration.memory_usage_mb > 1000:
            alert_high_memory(iteration)

    # Generate health report
    report = debugger.generate_report(trace)
    return report['performance']['efficiency_score']
```

### Pattern 3: Comparative Cycle Analysis
```python
def compare_cycle_implementations(cycle_variants):
    """Compare different cycle implementations."""

    profiler = CycleProfiler(enable_advanced_metrics=True)

    # Test each variant
    for variant_name, cycle_workflow in cycle_variants.items():
        print(f"Testing {variant_name}...")

        # Execute and profile
        trace = execute_and_profile(cycle_workflow)
        profiler.add_trace(trace)

    # Generate comparative analysis
    performance_report = profiler.generate_performance_report()

    best_cycle = performance_report['cycle_comparisons']['best_cycle']
    print(f"Best performing cycle: {best_cycle['id']} (score: {best_cycle['score']:.3f})")

    return performance_report
```

## Safe State Access Patterns

### ✅ Correct: Use .get() with defaults
```python
def run(self, context, **kwargs):
    # Always use .get() with default for cycle state
    cycle_info = context.get("cycle", {})
    iteration = cycle_info.get("iteration", 0)
    node_state = cycle_info.get("node_state") or {}

    # Safe access to nested state
    prev_error = node_state.get("error", float('inf'))
    learning_rate = node_state.get("learning_rate", 0.5)

    return {"result": processed_data}
```

### ❌ Wrong: Direct key access
```python
def run(self, context, **kwargs):
    # This will cause KeyError in cycles
    cycle_info = context["cycle"]              # KeyError if no cycle
    iteration = cycle_info["iteration"]        # KeyError if missing
    node_state = cycle_info["node_state"]      # KeyError if None

    return {"result": processed_data}
```

## Common Cycle Errors and Fixes

### 1. Parameter Propagation Issues

**Error**: Values don't propagate between iterations
```python
# ❌ Problem: Parameters revert to defaults each iteration
class ProcessorNode(Node):
    def run(self, context, **kwargs):
        quality = kwargs.get("quality", 0.0)  # Always gets 0.0!
        return {"quality": quality + 0.2}
```

**✅ Solution**: Use cycle state or correct mapping
```python
# Option 1: Use cycle state
class ProcessorNode(Node):
    def run(self, context, **kwargs):
        cycle_info = context.get("cycle", {})
        node_state = cycle_info.get("node_state") or {}

        # Get from cycle state if available
        quality = node_state.get("quality", kwargs.get("quality", 0.0))

        new_quality = quality + 0.2

        return {
            "quality": new_quality,
            "_cycle_state": {"quality": new_quality}
        }

# Option 2: Check parameter mapping
workflow.connect("processor", "processor",
    mapping={"quality": "quality"},  # Ensure correct mapping
    cycle=True)
```

### 2. PythonCodeNode Parameter Access

**Error**: `NameError: name 'count' is not defined`
```python
# ❌ Problem: Direct parameter access without try/except
code = '''
current_count = count  # NameError on first iteration
result = {"count": current_count + 1}
'''
```

**✅ Solution**: Always use try/except pattern
```python
code = '''
try:
    current_count = count  # From previous iteration
    print(f"Received count: {current_count}")
except NameError:
    current_count = 0      # Default for first iteration
    print("First iteration, starting at 0")

# Process
current_count += 1
done = current_count >= 5

result = {
    "count": current_count,
    "done": done
}
'''
```

### 3. None Value Security Errors

**Error**: `SecurityError: Input type not allowed: <class 'NoneType'>`
```python
# ❌ Problem: Passing None values to security-validated nodes
def run(self, context, **kwargs):
    cycle_state = context.get("cycle", {}).get("node_state")  # Could be None
    return {"state": cycle_state}  # Security error if None
```

**✅ Solution**: Filter None values
```python
def run(self, context, **kwargs):
    cycle_info = context.get("cycle", {})
    node_state = cycle_info.get("node_state") or {}  # Default to empty dict

    # Filter None values from output
    result = {"processed": True}
    if node_state:  # Only include if not empty
        result["previous_state"] = {k: v for k, v in node_state.items() if v is not None}

    return result
```

### 4. Multi-Node Cycle Detection

**Error**: Nodes in middle of cycle not detected
```python
# ❌ Problem: Only A and C detected in A → B → C → A cycle
workflow.connect("A", "B")          # Regular
workflow.connect("B", "C")          # Regular
workflow.connect("C", "A", cycle=True)  # Only closing edge marked
# Result: B is treated as separate DAG node
```

**✅ Solution**: Mark only closing edge, ensure proper grouping
```python
# Current workaround: Use direct cycles when possible
workflow.connect("A", "B")
workflow.connect("B", "A", cycle=True)  # Simple 2-node cycle

# For complex multi-node cycles, verify detection
# Check workflow.graph.detect_cycles() output
cycles = workflow.graph.detect_cycles()
print(f"Detected cycles: {cycles}")
```

### 5. Infinite Cycles

**Error**: `Warning: Cycle exceeded max_iterations`
```python
# ❌ Problem: Convergence condition never satisfied
workflow.connect("processor", "processor",
    cycle=True,
    max_iterations=10,
    convergence_check="done == True")  # 'done' never becomes True
```

**✅ Solution**: Debug convergence conditions
```python
# Add debugging node before convergence check
class DebugNode(Node):
    def run(self, context, **kwargs):
        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        print(f"Iteration {iteration}: {kwargs}")

        # Check convergence field
        done = kwargs.get("done", False)
        print(f"Convergence field 'done': {done} (type: {type(done)})")

        return kwargs  # Pass through

workflow.add_node("debug", DebugNode())
workflow.connect("processor", "debug")
workflow.connect("debug", "processor",
    cycle=True,
    max_iterations=10,
    convergence_check="done == True")
```

## Debugging Techniques

### 1. Add Logging Nodes
```python
class CycleLoggerNode(Node):
    """Logs cycle state for debugging."""

    def run(self, context, **kwargs):
        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        print(f"=== Iteration {iteration} ===")
        print(f"Context: {context}")
        print(f"Parameters: {kwargs}")
        print(f"Node state: {cycle_info.get('node_state', {})}")
        print("=" * 30)

        return kwargs  # Pass through unchanged

# Insert into cycle for debugging
workflow.add_node("logger", CycleLoggerNode())
workflow.connect("processor", "logger")
workflow.connect("logger", "processor", cycle=True)
```

### 2. Monitor Parameter Flow
```python
class ParameterMonitorNode(Node):
    """Monitors parameter propagation between iterations."""

    def run(self, context, **kwargs):
        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        # Track which parameters are received
        received_params = list(kwargs.keys())

        # Track parameter values
        param_values = {k: v for k, v in kwargs.items() if isinstance(v, (int, float, str, bool))}

        print(f"Iteration {iteration}:")
        print(f"  Received parameters: {received_params}")
        print(f"  Parameter values: {param_values}")

        # Check for expected parameters
        expected = ["data", "quality", "threshold"]
        missing = [p for p in expected if p not in kwargs]
        if missing:
            print(f"  WARNING: Missing expected parameters: {missing}")

        return kwargs
```

### 3. Validate Convergence Logic
```python
class ConvergenceValidatorNode(Node):
    """Validates convergence conditions."""

    def run(self, context, **kwargs):
        # Check convergence fields
        convergence_fields = ["done", "converged", "should_continue", "quality_sufficient"]
        found_fields = [f for f in convergence_fields if f in kwargs]

        print(f"Convergence fields found: {found_fields}")

        for field in found_fields:
            value = kwargs[field]
            print(f"  {field}: {value} (type: {type(value)})")

            # Validate boolean fields
            if field in ["done", "converged", "should_continue", "quality_sufficient"]:
                if not isinstance(value, bool):
                    print(f"    WARNING: {field} should be boolean, got {type(value)}")

        return kwargs
```

## Testing Patterns for Cycles

### Flexible Assertions
```python
import pytest

def test_cycle_execution():
    """Test cycle with flexible assertions."""
    workflow = create_cycle_workflow()
    runtime = LocalRuntime()

    results, run_id = runtime.execute(workflow, parameters={
        "processor": {"data": [1, 2, 3], "target": 10}
    })

    # ✅ Good: Use ranges for iteration counts
    final_result = results.get("processor", {})
    iteration = final_result.get("iteration", 0)

    # Allow for some variation in iteration count
    assert 3 <= iteration <= 7, f"Expected 3-7 iterations, got {iteration}"

    # ❌ Avoid: Exact iteration assertions
    # assert iteration == 5  # Too rigid, can fail due to implementation details

    # ✅ Good: Check convergence was achieved
    converged = final_result.get("converged", False)
    assert converged, "Cycle should have converged"

    # ✅ Good: Check final quality is in acceptable range
    quality = final_result.get("quality", 0)
    assert 0.8 <= quality <= 1.0, f"Quality {quality} not in expected range"
```

### Mock-Free Cycle Testing
```python
def test_cycle_without_mocks():
    """Test real cycle execution without mocks."""

    # Create real workflow
    workflow = Workflow("test-cycle", "Test Cycle")

    # Use simple, predictable nodes
    workflow.add_node("counter", PythonCodeNode(), code='''
try:
    count = count
except:
    count = 0

count += 1
result = {"count": count, "done": count >= 3}
''')

    # Simple cycle
    workflow.connect("counter", "counter",
        mapping={"result.count": "count"},
        cycle=True,
        max_iterations=10,
        convergence_check="done == True")

    # Execute and verify
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow)

    final_result = results.get("counter", {})
    assert final_result.get("result", {}).get("count") == 3
    assert final_result.get("result", {}).get("done") is True
```

## Performance Debugging

### Memory Usage Monitoring
```python
import psutil
import os

class MemoryMonitorNode(Node):
    """Monitors memory usage during cycles."""

    def run(self, context, **kwargs):
        # Get current process memory
        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / 1024 / 1024

        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        # Track memory growth
        node_state = cycle_info.get("node_state") or {}
        prev_memory = node_state.get("memory_mb", 0)
        memory_growth = memory_mb - prev_memory if prev_memory > 0 else 0

        # Warning for memory growth
        if memory_growth > 10:  # More than 10MB growth
            print(f"WARNING: Memory grew by {memory_growth:.1f}MB in iteration {iteration}")

        print(f"Iteration {iteration}: Memory usage {memory_mb:.1f}MB")

        return {
            **kwargs,
            "_cycle_state": {"memory_mb": memory_mb}
        }
```

### Execution Time Monitoring
```python
import time

class TimingMonitorNode(Node):
    """Monitors execution time per iteration."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.start_time = None

    def run(self, context, **kwargs):
        current_time = time.time()
        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        if iteration == 0:
            self.start_time = current_time
            iteration_time = 0
        else:
            node_state = cycle_info.get("node_state") or {}
            prev_time = node_state.get("last_time", self.start_time)
            iteration_time = current_time - prev_time

        total_time = current_time - self.start_time if self.start_time else 0

        print(f"Iteration {iteration}: {iteration_time:.3f}s (total: {total_time:.3f}s)")

        # Warning for slow iterations
        if iteration_time > 5.0:  # More than 5 seconds
            print(f"WARNING: Slow iteration {iteration}: {iteration_time:.3f}s")

        return {
            **kwargs,
            "_cycle_state": {"last_time": current_time}
        }
```

## Best Practices for Cycle Debugging

### 1. Start Simple
```python
# ✅ Good: Start with minimal cycle
workflow.add_node("simple", PythonCodeNode(), code='''
try:
    count = count
except:
    count = 0

count += 1
result = {"count": count, "done": count >= 3}
''')

workflow.connect("simple", "simple",
    mapping={"result.count": "count"},
    cycle=True, max_iterations=5)
```

### 2. Add Debugging Incrementally
```python
# Add one debugging feature at a time
# 1. Start with basic logging
# 2. Add parameter monitoring
# 3. Add convergence validation
# 4. Add performance monitoring
```

### 3. Use Descriptive Names
```python
# ✅ Good: Clear field names for debugging
return {
    "processed_data": data,
    "current_quality_score": quality,
    "convergence_threshold_met": quality >= threshold,
    "should_continue_processing": not converged,
    "debug_iteration_count": iteration
}

# ❌ Avoid: Ambiguous names
return {"data": data, "q": quality, "done": converged}
```

### 4. Validate Early and Often
```python
def run(self, context, **kwargs):
    # Validate inputs early
    data = kwargs.get("data")
    if data is None:
        raise ValueError("Data parameter is required")

    if not isinstance(data, list):
        raise TypeError(f"Data must be list, got {type(data)}")

    # Process...

    # Validate outputs before returning
    result = process_data(data)
    if not isinstance(result, dict):
        raise TypeError(f"Result must be dict, got {type(result)}")

    return result
```
