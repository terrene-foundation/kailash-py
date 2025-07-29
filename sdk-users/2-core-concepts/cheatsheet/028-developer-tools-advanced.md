# Advanced Developer Tools

*Professional cycle debugging and performance analysis*

## 🔍 Quick Setup

### CycleDebugger
```python
from kailash.workflow import CycleDebugger

# Create debugger
debugger = CycleDebugger()

# Start debugging
trace = debugger.start_cycle(
    cycle_id="optimization_cycle",
    workflow_id="my_workflow"
)

# Track iterations
input_data = {"value": 10.0, "target": 100.0}
iteration = debugger.start_iteration(trace, input_data)
output_data = {"value": 25.0, "error": 0.75}
debugger.end_iteration(trace, iteration, output_data)

# Generate report
report = debugger.generate_report(trace)
print(f"Performance: {report['performance']}")
print(f"Statistics: {report['statistics']}")

```

### CycleProfiler
```python
from kailash.workflow import CycleProfiler, CycleDebugger

# Create profiler and debugger
profiler = CycleProfiler()
debugger = CycleDebugger()

# Create traces using debugger
trace1 = debugger.start_cycle("fast_cycle", "test_workflow")
iter1 = debugger.start_iteration(trace1, {"input": "data1"})
debugger.end_iteration(trace1, iter1, {"output": "result1"})

trace2 = debugger.start_cycle("slow_cycle", "test_workflow")
iter2 = debugger.start_iteration(trace2, {"input": "data2"})
debugger.end_iteration(trace2, iter2, {"output": "result2"})

# Add traces for comparison
profiler.add_trace(trace1)
profiler.add_trace(trace2)

# Analyze performance
metrics = profiler.analyze_performance()
print(f"Performance metrics: {metrics}")

# Get optimization recommendations
recommendations = profiler.get_optimization_recommendations()
for rec in recommendations:
    print(f"Recommendation: {rec}")

```

### CycleAnalyzer
```python
from kailash.workflow import CycleAnalyzer

# Create analyzer
analyzer = CycleAnalyzer()

# Start analysis session
session = analyzer.start_analysis_session("optimization_study")

# Analyze cycle
trace = analyzer.start_cycle_analysis(
    cycle_id="experiment_1",
    workflow_id="optimization_workflow"
)

# Track iterations
analyzer.track_iteration(
    trace,
    input_data={"value": 10},
    output_data={"value": 15}
)

# Real-time health monitoring
health = analyzer.get_real_time_metrics(trace)
if health.get('health_score', 1.0) < 0.5:
    print("⚠️ Performance issue detected!")

# Generate reports
cycle_report = analyzer.generate_cycle_report(trace)
session_report = analyzer.generate_session_report()

```

## 🛠️ Practical Patterns

### Development Optimization
```python
from kailash.workflow import CycleAnalyzer
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

def optimize_during_development(workflow):
    """Optimize cycle performance during development."""

    analyzer = CycleAnalyzer()
    session = analyzer.start_analysis_session("development")

    # Run baseline analysis
    trace_baseline = analyzer.start_cycle_analysis("baseline", "test_workflow")

    # Simulate workflow execution tracking
    analyzer.track_iteration(trace_baseline, {"input": "test"}, {"output": "processed"})

    baseline_report = analyzer.generate_cycle_report(trace_baseline)
    print(f"Baseline analysis: {baseline_report}")

    # Compare with optimized version
    trace_optimized = analyzer.start_cycle_analysis("optimized", "test_workflow_v2")
    analyzer.track_iteration(trace_optimized, {"input": "test"}, {"output": "optimized"})

    optimized_report = analyzer.generate_cycle_report(trace_optimized)
    print(f"Optimized analysis: {optimized_report}")

    return {"baseline": baseline_report, "optimized": optimized_report}

```

### Production Monitoring
```python
from kailash.workflow import CycleDebugger
from kailash.runtime.local import LocalRuntime

def monitor_production_cycles(workflow, parameters):
    """Monitor cycle health in production."""

    debugger = CycleDebugger()

    # Define thresholds
    SLOW_THRESHOLD = 5.0  # seconds

    def monitor_execution():
        trace = debugger.start_cycle("prod_cycle", "production_workflow")

        try:
            # Simulate workflow execution
            iteration = debugger.start_iteration(trace, parameters)

            # Execute workflow
            runtime = LocalRuntime()
            results, run_id = runtime.execute(workflow, parameters=parameters)

            debugger.end_iteration(trace, iteration, results)

            # Check health
            report = debugger.generate_report(trace)

            # Generate alerts based on performance
            alerts = []
            avg_time = report['statistics'].get('avg_iteration_time', 0)

            if avg_time > SLOW_THRESHOLD:
                alerts.append(f"Slow iterations: {avg_time:.3f}s")

            if alerts:
                print(f"ALERTS: {alerts}")

            return results, {'health_report': report, 'alerts': alerts}

        except Exception as e:
            print(f"Execution failed: {e}")
            raise

    return monitor_execution()

```

### Performance Comparison
```python
from kailash.workflow import CycleProfiler, CycleDebugger

def compare_cycle_variants():
    """Compare different cycle implementations."""

    profiler = CycleProfiler()
    debugger = CycleDebugger()

    # Test baseline variant
    trace_baseline = debugger.start_cycle("baseline", "baseline_workflow")
    iter_baseline = debugger.start_iteration(trace_baseline, {"test": "data"})
    debugger.end_iteration(trace_baseline, iter_baseline, {"result": "baseline"})

    # Test optimized variant
    trace_optimized = debugger.start_cycle("optimized", "optimized_workflow")
    iter_optimized = debugger.start_iteration(trace_optimized, {"test": "data"})
    debugger.end_iteration(trace_optimized, iter_optimized, {"result": "optimized"})

    # Add traces to profiler
    profiler.add_trace(trace_baseline)
    profiler.add_trace(trace_optimized)

    # Analyze performance
    metrics = profiler.analyze_performance()
    recommendations = profiler.get_optimization_recommendations()

    print(f"Performance comparison:")
    print(f"  Metrics: {metrics}")
    print(f"  Recommendations: {len(recommendations)} items")

    return {"metrics": metrics, "recommendations": recommendations}

```

## 🚀 Advanced Features

### Custom Analysis
```python
from kailash.workflow import CycleAnalyzer

def advanced_cycle_analysis():
    """Perform advanced cycle analysis with custom metrics."""

    analyzer = CycleAnalyzer()
    session = analyzer.start_analysis_session("advanced_study")

    # Start comprehensive analysis
    trace = analyzer.start_cycle_analysis("advanced_test", "complex_workflow")

    # Track multiple iterations with custom data
    for i in range(3):
        analyzer.track_iteration(
            trace,
            input_data={"iteration": i, "data": f"input_{i}"},
            output_data={"iteration": i, "result": f"output_{i}"}
        )

        # Monitor real-time metrics
        health = analyzer.get_real_time_metrics(trace)
        print(f"Iteration {i+1} health: {health}")

    # Generate comprehensive reports
    cycle_report = analyzer.generate_cycle_report(trace)
    session_report = analyzer.generate_session_report()

    print(f"Cycle analysis complete:")
    print(f"  Cycle report keys: {list(cycle_report.keys())}")
    print(f"  Session report keys: {list(session_report.keys())}")

    return {"cycle": cycle_report, "session": session_report}

```

## 📋 Best Practices

1. **Choose Right Analysis Level**
   - Development: Use `CycleAnalyzer` for comprehensive analysis
   - Testing: Use `CycleProfiler` for performance comparison
   - Production: Use `CycleDebugger` for minimal overhead monitoring

2. **Use Progressive Analysis**
   - Start with basic debugging
   - Add profiling when performance issues detected
   - Use comprehensive analysis only during optimization

3. **Monitor Key Metrics**
   - Track iteration time and memory usage
   - Monitor convergence patterns
   - Alert on performance degradation

## 🚀 Quick Reference

### Key Tools
- **CycleDebugger**: Real-time execution tracking and reporting
- **CycleProfiler**: Performance analysis and optimization recommendations
- **CycleAnalyzer**: Comprehensive analysis framework with sessions

### Common Workflows
1. **Development**: Debug → profile → analyze → optimize
2. **Production**: Monitor → alert → investigate
3. **Research**: Compare → analyze → report

### Performance Indicators
- Monitor iteration time trends
- Track memory usage patterns
- Analyze convergence behavior
- Compare variant performance

---
*Related: [021-cycle-aware-nodes.md](021-cycle-aware-nodes.md), [022-cycle-debugging-troubleshooting.md](022-cycle-debugging-troubleshooting.md)*
