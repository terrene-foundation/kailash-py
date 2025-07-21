# Advanced Developer Tools

*Professional cycle debugging and performance analysis*

## 🔍 Quick Setup

### CycleDebugger
```python
from kailash.workflow import CycleDebugger

# Create debugger
debugger = CycleDebugger(
    debug_level="detailed",
    enable_profiling=True,
    output_directory="./debug_output"
)

# Start debugging
trace = debugger.start_cycle(
    cycle_id="optimization_cycle",
    workflow_id="my_workflow",
    max_iterations=100
)

# Track iterations
input_data = {"value": 10.0, "target": 100.0}
iteration = debugger.start_iteration(trace, input_data)
output_data = {"value": 25.0, "error": 0.75}
debugger.end_iteration(trace, iteration, output_data)

# Generate report
report = debugger.generate_report(trace)
print(f"Efficiency: {report['performance']['efficiency_score']:.3f}")

```

### CycleProfiler
```python
from kailash.workflow import CycleProfiler

# Create profiler
profiler = CycleProfiler(enable_advanced_metrics=True)

# Add traces for comparison
profiler.add_trace(trace1)  # Fast execution
profiler.add_trace(trace2)  # Slow execution

# Analyze performance
metrics = profiler.analyze_performance()
print(f"Average cycle time: {metrics.avg_cycle_time:.3f}s")
print(f"Bottlenecks: {metrics.bottlenecks}")

# Get optimization recommendations
recommendations = profiler.get_optimization_recommendations()
for rec in recommendations:
    print(f"[{rec['priority']}] {rec['description']}")

```

### CycleAnalyzer
```python
from kailash.workflow import CycleAnalyzer

# Create comprehensive analyzer
analyzer = CycleAnalyzer(
    analysis_level="comprehensive",
    enable_profiling=True,
    enable_debugging=True
)

# Start analysis session
session = analyzer.start_analysis_session("optimization_study")

# Analyze cycle
trace = analyzer.start_cycle_analysis(
    "experiment_1", "optimization_workflow", max_iterations=50
)

# Track iterations automatically
for iteration_data in workflow_execution_iterator():
    analyzer.track_iteration(
        trace, iteration_data['input'], iteration_data['output']
    )

    # Real-time health monitoring
    health = analyzer.get_real_time_metrics(trace)
    if health['health_score'] < 0.5:
        print("⚠️ Performance issue detected!")
        break

# Generate reports
cycle_report = analyzer.generate_cycle_report(trace)
session_report = analyzer.generate_session_report()

```

## 🛠️ Practical Patterns

### Development Optimization
```python
def optimize_during_development(workflow):
    """Optimize cycle performance during development."""
    from kailash.workflow import CycleAnalyzer

    def execute_workflow_with_tracking(wf, trace):
        """Mock function for workflow execution."""
        return {"results": "processed", "iterations": 5}

    def apply_optimizations(wf, recommendations):
        """Mock function for applying optimizations."""
        return wf  # Return optimized workflow

    analyzer = CycleAnalyzer(analysis_level="comprehensive")
    session = analyzer.start_analysis_session("development")

    # Run baseline
    trace_baseline = analyzer.start_cycle_analysis("baseline", workflow.workflow_id)
    results_baseline = execute_workflow_with_tracking(workflow, trace_baseline)
    baseline_report = analyzer.generate_cycle_report(trace_baseline)

    print(f"Baseline efficiency: {baseline_report['performance']['efficiency_score']:.3f}")

    # Apply optimizations
    recommendations = baseline_report['recommendations']
    optimized_workflow = apply_optimizations(workflow, recommendations)

    # Test optimized version
    trace_optimized = analyzer.start_cycle_analysis("optimized", optimized_workflow.workflow_id)
    results_optimized = execute_workflow_with_tracking(optimized_workflow, trace_optimized)
    optimized_report = analyzer.generate_cycle_report(trace_optimized)

    improvement = (optimized_report['performance']['efficiency_score'] -
                  baseline_report['performance']['efficiency_score']) * 100

    print(f"Improvement: {improvement:.1f}%")
    return optimized_workflow

```

### Production Monitoring
```python
def monitor_production_cycles():
    """Monitor cycle health in production."""
    from kailash.workflow import CycleDebugger
    from kailash.runtime.local import LocalRuntime

    def send_alerts(alerts, report):
        """Mock function for sending alerts."""
        print(f"ALERT: {alerts}")

    debugger = CycleDebugger(
        debug_level="basic",  # Minimal overhead
        enable_profiling=True
    )

    # Define thresholds
    SLOW_THRESHOLD = 5.0  # seconds
    LOW_EFFICIENCY = 0.3
    HIGH_MEMORY = 1000    # MB

    def monitor_execution(workflow, parameters):
        trace = debugger.start_cycle("prod_cycle", workflow.workflow_id)

        try:
            runtime = LocalRuntime()
            results, run_id = runtime.execute(workflow, parameters=parameters)

            # Check health
            report = debugger.generate_report(trace)
            efficiency = report['performance']['efficiency_score']
            avg_time = report['statistics']['avg_iteration_time']
            max_memory = report['statistics'].get('max_memory_mb', 0)

            # Generate alerts
            alerts = []
            if efficiency < LOW_EFFICIENCY:
                alerts.append(f"Low efficiency: {efficiency:.3f}")
            if avg_time > SLOW_THRESHOLD:
                alerts.append(f"Slow iterations: {avg_time:.3f}s")
            if max_memory > HIGH_MEMORY:
                alerts.append(f"High memory: {max_memory:.1f}MB")

            if alerts:
                send_alerts(alerts, report)

            return results, {'health_score': efficiency, 'alerts': alerts}

        except Exception as e:
            debugger.end_cycle(trace, converged=False, termination_reason=f"error: {e}")
            raise

    return monitor_execution

```

### A/B Testing
```python
def ab_test_cycle_variants():
    """A/B test different cycle implementations."""
    from kailash.workflow import CycleProfiler

    def create_baseline_cycle():
        """Mock function to create baseline cycle."""
        from kailash import Workflow
        return Workflow("baseline")

    def create_optimized_v1():
        """Mock function to create optimized v1."""
        from kailash import Workflow
        return Workflow("optimized_v1")

    def create_optimized_v2():
        """Mock function to create optimized v2."""
        from kailash import Workflow
        return Workflow("optimized_v2")

    def execute_workflow_with_profiling(workflow):
        """Mock function for profiled execution."""
        return {"trace_id": workflow.workflow_id, "performance": 0.75}

    profiler = CycleProfiler(enable_advanced_metrics=True)

    # Define variants
    cycle_variants = {
        "baseline": create_baseline_cycle(),
        "optimized_v1": create_optimized_v1(),
        "optimized_v2": create_optimized_v2()
    }

    test_results = {}

    # Test each variant
    for variant_name, workflow in cycle_variants.items():
        print(f"Testing {variant_name}...")

        # Run multiple times for statistical significance
        variant_traces = []
        for run in range(5):
            trace = execute_workflow_with_profiling(workflow)
            variant_traces.append(trace)
            profiler.add_trace(trace)

        # Calculate statistics
        performance_stats = profiler.analyze_variant_performance(variant_traces)
        test_results[variant_name] = performance_stats

        print(f"  Avg efficiency: {performance_stats['avg_efficiency']:.3f}")

    # Generate comparison
    comparison_report = profiler.compare_variants(test_results)
    best_variant = comparison_report['best_variant']

    print(f"\n🏆 Best variant: {best_variant['name']}")
    print(f"   Efficiency: {best_variant['efficiency']:.3f}")
    print(f"   Improvement: {best_variant['improvement_percentage']:.1f}%")

    return comparison_report

```

## 🚀 Advanced Features

### Custom Analysis Hooks
```python
import time
from kailash import Workflow
from kailash.workflow import CycleAnalyzer

class CustomCycleAnalyzer(CycleAnalyzer):
    """Extended analyzer with custom metrics."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.custom_metrics = {}

    def _calculate_trend(self, values):
        """Calculate trend from values."""
        if len(values) < 2:
            return "insufficient_data"
        return "increasing" if values[-1] > values[0] else "decreasing"

    def track_custom_metric(self, trace, metric_name, value):
        """Track custom business metrics."""
        if trace.cycle_id not in self.custom_metrics:
            self.custom_metrics[trace.cycle_id] = {}

        if metric_name not in self.custom_metrics[trace.cycle_id]:
            self.custom_metrics[trace.cycle_id][metric_name] = []

        self.custom_metrics[trace.cycle_id][metric_name].append({
            'iteration': len(self.custom_metrics[trace.cycle_id][metric_name]),
            'value': value,
            'timestamp': time.time()
        })

    def generate_custom_report(self, trace):
        """Generate report with custom metrics."""
        base_report = super().generate_cycle_report(trace)

        if trace.cycle_id in self.custom_metrics:
            base_report['custom_metrics'] = self.custom_metrics[trace.cycle_id]

            # Ensure insights key exists
            if 'insights' not in base_report:
                base_report['insights'] = {}

            # Calculate trends
            for metric_name, values in self.custom_metrics[trace.cycle_id].items():
                trend = self._calculate_trend([v['value'] for v in values])
                base_report['insights'][f'{metric_name}_trend'] = trend

        return base_report

# Usage
analyzer = CustomCycleAnalyzer(analysis_level="comprehensive")
trace = analyzer.start_cycle_analysis("custom_test", "test_workflow")

# Track custom metrics
analyzer.track_custom_metric(trace, "customer_satisfaction", 0.85)
analyzer.track_custom_metric(trace, "processing_cost", 12.50)

# Generate enhanced report
custom_report = analyzer.generate_custom_report(trace)
print(f"Customer satisfaction trend: {custom_report['insights']['customer_satisfaction_trend']}")

```

### Export and Visualization
```python
def export_analysis_data(analyzer):
    """Export analysis data for external tools."""
    from kailash.workflow import CycleAnalyzer

    # Export formats
    exports = {
        'jupyter': analyzer.export_for_jupyter("analysis.ipynb"),
        'excel': analyzer.export_for_excel("analysis.xlsx"),
        'visualization': analyzer.export_for_visualization("viz_data.json")
    }

    # Generate interactive HTML report
    html_report = analyzer.generate_interactive_report(
        include_charts=True,
        template="comprehensive"
    )

    with open("cycle_analysis_report.html", "w") as f:
        f.write(html_report)

    return exports

```

## 📋 Best Practices

1. **Choose Right Analysis Level**
   - Development: `analysis_level="comprehensive"`
   - Testing: `analysis_level="standard"`
   - Production: `analysis_level="basic"`

2. **Use Progressive Analysis**
   - Start with basic debugging
   - Upgrade to detailed only when needed
   - Sample high-frequency cycles

3. **Monitor Key Metrics**
   - Efficiency score < 0.5 = performance issue
   - Iteration time > 5s = slow performance
   - Memory growth > 10MB = memory leak

## 🚀 Quick Reference

### Key Tools
- **CycleDebugger**: Real-time execution tracking
- **CycleProfiler**: Performance analysis & recommendations
- **CycleAnalyzer**: Comprehensive analysis framework

### Common Workflows
1. **Development**: Analyze → optimize → test → deploy
2. **Production**: Monitor → alert → investigate
3. **Research**: Compare → analyze → report

### Alert Thresholds
- Efficiency < 0.3 = critical issue
- Iteration time > 5s = performance warning
- Memory > 1GB = resource warning

---
*Related: [021-cycle-aware-nodes.md](021-cycle-aware-nodes.md), [022-cycle-debugging-troubleshooting.md](022-cycle-debugging-troubleshooting.md)*
