# Cyclic Workflows Guide

*Advanced workflow patterns with state persistence, convergence detection, and safety mechanisms*

## Overview

Cyclic workflows enable iterative processing patterns including optimization loops, retry mechanisms, data quality cycles, and training workflows. The Kailash SDK provides comprehensive cycle management with state persistence, convergence detection, safety mechanisms, and performance optimization.

## Prerequisites

- Completed [Edge Computing Guide](30-edge-computing-guide.md)
- Understanding of iterative algorithms and convergence concepts
- Familiarity with workflow builder patterns

## Core Cyclic Workflow Features

### CyclicWorkflowExecutor

The main execution engine for cyclic workflows with hybrid DAG/Cycle execution.

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.cyclic_runner import CyclicWorkflowExecutor
from kailash.workflow.cycle_state import CycleState
from kailash.workflow.cycle_config import CycleConfig

# Initialize cyclic workflow executor
cyclic_executor = CyclicWorkflowExecutor(
    name="optimization_workflow",

    # Safety configuration
    max_iterations=100,
    timeout_seconds=300,
    memory_limit_mb=1024,

    # Performance settings
    enable_monitoring=True,
    enable_profiling=True,
    enable_debugging=True,

    # State management
    state_persistence=True,
    state_compression=True
)

# Define cycle configuration
cycle_config = CycleConfig(
    cycle_name="parameter_optimization",
    max_iterations=50,
    timeout_seconds=120,

    # Convergence criteria
    convergence_conditions=[
        {"type": "expression", "condition": "quality > 0.95"},
        {"type": "max_iterations", "value": 50},
        {"type": "stability", "metric": "quality", "threshold": 0.001, "window": 5}
    ],

    # Resource limits
    memory_limit_mb=512,
    cpu_time_limit_seconds=60,

    # Parameter configuration
    initial_parameters={
        "learning_rate": 0.01,
        "batch_size": 32,
        "regularization": 0.001
    },

    parameter_# mapping removed,
        "previous_iteration.quality_score": "current_iteration.target_quality"
    }
)

# Execute cyclic workflow
execution_result = await cyclic_executor.execute_cycle(
    cycle_config=cycle_config,
    initial_data={
        "dataset": training_data,
        "model_config": model_configuration,
        "optimization_target": "minimize_loss"
    }
)

print(f"Cycle completed in {execution_result.total_iterations} iterations")
print(f"Final convergence: {execution_result.converged}")
print(f"Best quality achieved: {execution_result.best_quality}")
```

### CycleState Management

Comprehensive state management across cycle iterations.

```python
from kailash.workflow.cycle_state import CycleState, CycleStateManager

# Initialize cycle state
cycle_state = CycleState(
    cycle_id="optimization_cycle_001",
    iteration=0,
    max_iterations=50
)

# Node-specific state management
class OptimizationNode(CycleAwareNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = kwargs.get('name', 'optimization_node')

    async def run(self, **inputs):
        # Get current iteration information
        iteration = self.get_iteration()
        is_first = self.is_first_iteration()
        is_last = self.is_last_iteration()

        print(f"Processing iteration {iteration}")

        if is_first:
            # Initialize optimization state
            self.set_cycle_state("best_params", inputs.get("initial_params"))
            self.set_cycle_state("best_quality", 0.0)
            self.set_cycle_state("quality_history", [])
        else:
            # Retrieve previous state
            best_params = self.get_previous_state("best_params")
            best_quality = self.get_previous_state("best_quality")
            quality_history = self.get_previous_state("quality_history", [])

        # Perform optimization step
        current_params = self.optimize_parameters(
            current_params=inputs.get("params", best_params),
            previous_quality=best_quality,
            iteration=iteration
        )

        # Evaluate current parameters
        quality_score = await self.evaluate_parameters(current_params, inputs["dataset"])

        # Update state if improved
        if quality_score > best_quality:
            self.set_cycle_state("best_params", current_params)
            self.set_cycle_state("best_quality", quality_score)

        # Track quality history
        quality_history.append(quality_score)
        self.set_cycle_state("quality_history", quality_history)

        # Detect convergence trend
        convergence_trend = self.detect_convergence_trend(
            values=quality_history,
            window_size=5,
            threshold=0.001
        )

        return {
            "optimized_params": current_params,
            "quality_score": quality_score,
            "best_params": self.get_cycle_state("best_params"),
            "best_quality": self.get_cycle_state("best_quality"),
            "convergence_trend": convergence_trend,
            "iteration_progress": self.get_cycle_progress()
        }

    def optimize_parameters(self, current_params, previous_quality, iteration):
        """Implement your optimization algorithm here."""
        # Example: Simple gradient-based optimization
        learning_rate = 0.01 * (0.95 ** iteration)  # Decay learning rate

        # Simulate parameter updates (replace with actual optimization)
        optimized_params = {}
        for key, value in current_params.items():
            # Add some optimization logic
            gradient = self.compute_gradient(key, value, previous_quality)
            optimized_params[key] = value - learning_rate * gradient

        return optimized_params

    def compute_gradient(self, param_name, param_value, previous_quality):
        """Compute gradient for parameter (placeholder implementation)."""
        import random
        return random.uniform(-0.1, 0.1)  # Replace with actual gradient computation

    async def evaluate_parameters(self, params, dataset):
        """Evaluate parameter quality (placeholder implementation)."""
        import random
        import asyncio

        # Simulate evaluation time
        await asyncio.sleep(0.1)

        # Simulate quality score calculation
        base_quality = 0.5
        for key, value in params.items():
            # Simple quality function (replace with actual evaluation)
            base_quality += 0.1 * (1 - abs(value))

        # Add some noise to simulate real optimization
        noise = random.uniform(-0.05, 0.05)
        return max(0.0, min(1.0, base_quality + noise))
```

## Convergence Detection

Advanced convergence detection with multiple criteria and adaptive thresholds.

### ConvergenceCheckerNode

```python
from kailash.nodes.convergence.convergence_checker import ConvergenceCheckerNode
from kailash.workflow.convergence import ConvergenceCondition, ExpressionCondition

# Initialize convergence checker
convergence_checker = ConvergenceCheckerNode(
    name="convergence_checker",

    # Convergence criteria
    convergence_mode="multi_criteria",

    # Threshold-based convergence
    threshold_conditions={
        "quality_score": {"operator": ">", "value": 0.95},
        "improvement_rate": {"operator": "<", "value": 0.001},
        "stability_variance": {"operator": "<", "value": 0.0001}
    },

    # Stability-based convergence
    stability_config={
        "window_size": 5,
        "variance_threshold": 0.001,
        "metrics": ["quality_score", "loss_value"]
    },

    # Improvement rate monitoring
    improvement_config={
        "min_improvement": 0.001,
        "window_size": 3,
        "consecutive_failures": 5
    },

    # Custom expression conditions
    expression_conditions=[
        "quality_score > 0.9 and iteration > 10",
        "improvement_rate < 0.001 and stability_variance < 0.0001",
        "iteration > 30 and quality_score > 0.85"
    ],

    # Adaptive criteria (changes over time)
    adaptive_criteria={
        "early_stopping": {
            "iterations": [10, 25, 40],
            "quality_thresholds": [0.7, 0.85, 0.95]
        }
    }
)

# Use in cycle workflow
convergence_result = await convergence_checker.run(
    quality_score=current_quality,
    iteration=current_iteration,
    quality_history=quality_history,
    improvement_rate=improvement_rate,
    stability_variance=stability_variance
)

if convergence_result["converged"]:
    print(f"Convergence achieved: {convergence_result['reason']}")
    print(f"Final quality: {convergence_result['final_metrics']}")
else:
    print(f"Continue iteration: {convergence_result['continue_reason']}")
```

### Multi-Criteria Convergence

```python
from kailash.nodes.convergence.multi_criteria_convergence import MultiCriteriaConvergenceNode

# Advanced multi-dimensional convergence
multi_criteria_checker = MultiCriteriaConvergenceNode(
    name="multi_criteria_convergence",

    # Define multiple metrics to track
    convergence_metrics={
        "accuracy": {
            "target": 0.95,
            "weight": 0.4,
            "direction": "maximize",
            "tolerance": 0.001
        },
        "loss": {
            "target": 0.05,
            "weight": 0.3,
            "direction": "minimize",
            "tolerance": 0.001
        },
        "f1_score": {
            "target": 0.9,
            "weight": 0.2,
            "direction": "maximize",
            "tolerance": 0.002
        },
        "training_time": {
            "target": 60.0,  # seconds
            "weight": 0.1,
            "direction": "minimize",
            "tolerance": 5.0
        }
    },

    # Convergence strategy
    convergence_strategy="weighted_score",  # "all_criteria", "majority", "weighted_score"
    min_weighted_score=0.85,

    # Stability requirements
    stability_window=5,
    stability_threshold=0.002,

    # Early stopping conditions
    early_stopping={
        "min_iterations": 10,
        "max_iterations_without_improvement": 15,
        "absolute_targets": {
            "accuracy": 0.99,  # Stop immediately if accuracy > 99%
            "loss": 0.01       # Stop immediately if loss < 1%
        }
    }
)

# Multi-dimensional convergence check
multi_result = await multi_criteria_checker.run(
    metrics={
        "accuracy": current_accuracy,
        "loss": current_loss,
        "f1_score": current_f1,
        "training_time": training_time
    },
    iteration=current_iteration,
    metric_history=metric_history
)

print(f"Overall convergence score: {multi_result['weighted_score']:.3f}")
print(f"Individual criteria met: {multi_result['criteria_met']}")
print(f"Converged: {multi_result['converged']}")
```

## Cycle Building and Templates

Fluent API for creating cyclic workflows with pre-built templates.

### CycleBuilder

```python
from kailash.workflow.cycle_builder import CycleBuilder
from kailash.workflow.cycle_config import CycleTemplates

# Fluent cycle building
optimization_cycle = (CycleBuilder(workflow, "optimization_loop")
    .add_node("data_preprocessor", "DataPreprocessorNode", {
        "normalization": True,
        "feature_selection": True
    })
    .add_node("model_trainer", "ModelTrainerNode", {
        "algorithm": "gradient_descent",
        "learning_rate": 0.01
    })
    .add_node("evaluator", "ModelEvaluatorNode", {
        "metrics": ["accuracy", "loss", "f1_score"]
    })
    .add_node("optimizer", "ParameterOptimizerNode", {
        "optimization_strategy": "adaptive"
    })
    .add_node("convergence_checker", "ConvergenceCheckerNode", {
        "convergence_mode": "multi_criteria"
    })

    # Define cycle connections
    .connect("data_preprocessor", "model_trainer", {"processed_data": "training_data"})
    .connect("model_trainer", "evaluator", {"trained_model": "model"})
    .connect("evaluator", "optimizer", {"metrics": "current_metrics"})
    .connect("optimizer", "model_trainer", {"optimized_params": "hyperparameters"})
    .connect("evaluator", "convergence_checker", {"metrics": "current_metrics"})

    # Cycle configuration
    .max_iterations(100)
    .timeout(600)  # 10 minutes
    .memory_limit(2048)  # 2GB

    # Convergence conditions
    .converge_when("accuracy > 0.95")
    .converge_when("loss < 0.05")
    .converge_when("stability_variance < 0.001")

    # State preservation
    .preserve_state(["best_model", "best_metrics", "optimization_history"])

    # Safety mechanisms
    .enable_safety_monitoring()
    .detect_infinite_loops()
    .monitor_resource_usage()

    .build()
)

# Execute the cycle
cycle_result = await workflow.execute_cycle(optimization_cycle)
```

### Cycle Templates

```python
# Pre-built cycle templates
training_loop = CycleTemplates.training_loop(
    max_epochs=100,
    early_stopping_patience=10,
    learning_rate_decay=0.95,
    convergence_threshold=0.001
)

data_quality_cycle = CycleTemplates.data_quality_cycle(
    quality_threshold=0.95,
    max_cleaning_iterations=20,
    validation_split=0.2
)

optimization_loop = CycleTemplates.optimization_loop(
    algorithm="genetic_algorithm",
    population_size=50,
    max_generations=100,
    mutation_rate=0.1
)

retry_cycle = CycleTemplates.retry_cycle(
    max_retries=5,
    backoff_strategy="exponential",
    base_delay=1.0,
    max_delay=60.0
)

# Use template in workflow
workflow.add_cycle(training_loop)
await runtime.execute(workflow.build(), )
```

## Safety and Resource Management

Comprehensive safety mechanisms and resource monitoring.

### CycleSafetyManager

```python
from kailash.workflow.safety import CycleSafetyManager, CycleMonitor

# Initialize safety manager
safety_manager = CycleSafetyManager(
    # Global limits
    max_concurrent_cycles=5,
    global_memory_limit_mb=4096,
    global_cpu_time_limit_seconds=3600,

    # Monitoring configuration
    monitoring_interval_seconds=5,
    alert_threshold_memory=0.8,  # 80% of limit
    alert_threshold_cpu=0.9,     # 90% of limit

    # Safety actions
    auto_terminate_on_violation=True,
    graceful_shutdown_timeout=30,

    # Deadlock detection
    deadlock_detection_enabled=True,
    deadlock_timeout_seconds=60,

    # Resource leak detection
    memory_leak_detection=True,
    memory_growth_threshold=0.1  # 10% growth per iteration
)

# Configure cycle-specific monitor
cycle_monitor = CycleMonitor(
    cycle_id="optimization_cycle_001",

    # Resource limits
    memory_limit_mb=1024,
    cpu_time_limit_seconds=300,
    iteration_limit=100,

    # Monitoring settings
    track_memory_growth=True,
    track_cpu_usage=True,
    track_iteration_time=True,

    # Violation actions
    on_memory_violation="terminate",
    on_cpu_violation="warn_and_continue",
    on_iteration_violation="terminate",

    # Health scoring
    enable_health_scoring=True,
    health_check_interval=10
)

# Monitor cycle execution
async def monitored_cycle_execution():
    """Execute cycle with comprehensive monitoring."""

    try:
        # Start monitoring
        await safety_manager.start_monitoring()
        await cycle_monitor.start()

        # Execute cycle with monitoring
        async for iteration_result in cyclic_executor.execute_with_monitoring(
            cycle_config=cycle_config,
            monitor=cycle_monitor
        ):
            # Check safety conditions
            safety_status = await safety_manager.check_safety()

            if safety_status.violations:
                print(f"Safety violations detected: {safety_status.violations}")
                if safety_status.should_terminate:
                    print("Terminating cycle due to safety violations")
                    break

            # Display monitoring metrics
            metrics = await cycle_monitor.get_current_metrics()
            print(f"Iteration {iteration_result.iteration}:")
            print(f"  Memory usage: {metrics.memory_usage_mb:.1f} MB")
            print(f"  CPU usage: {metrics.cpu_usage_percent:.1f}%")
            print(f"  Health score: {metrics.health_score:.2f}")

            # Check for performance degradation
            if metrics.health_score < 0.5:
                print("Performance degradation detected - considering termination")

    finally:
        # Cleanup monitoring
        await cycle_monitor.stop()
        await safety_manager.stop_monitoring()

# Execute with monitoring
await monitored_cycle_execution()
```

### Resource Usage Analysis

```python
# Analyze resource usage patterns
resource_analysis = await cycle_monitor.analyze_resource_usage()

print("Resource Usage Analysis:")
print(f"Peak memory usage: {resource_analysis.peak_memory_mb:.1f} MB")
print(f"Average CPU usage: {resource_analysis.avg_cpu_percent:.1f}%")
print(f"Total execution time: {resource_analysis.total_time_seconds:.1f}s")
print(f"Memory efficiency: {resource_analysis.memory_efficiency:.2f}")

# Performance recommendations
recommendations = await cycle_monitor.get_optimization_recommendations()
for rec in recommendations:
    print(f"Recommendation: {rec.description}")
    print(f"  Impact: {rec.estimated_improvement}")
    print(f"  Implementation: {rec.implementation_steps}")
```

## Debugging and Performance Analysis

Comprehensive debugging and performance analysis tools.

### CycleDebugger

```python
from kailash.workflow.cycle_debugger import CycleDebugger
from kailash.workflow.cycle_profiler import CycleProfiler
from kailash.workflow.cycle_analyzer import CycleAnalyzer

# Initialize debugger
cycle_debugger = CycleDebugger(
    cycle_id="optimization_cycle_001",

    # Debug configuration
    capture_node_parameters=True,
    capture_node_outputs=True,
    capture_state_changes=True,
    capture_convergence_data=True,

    # Performance tracking
    track_execution_time=True,
    track_memory_usage=True,
    track_cpu_usage=True,

    # Error handling
    capture_exceptions=True,
    capture_stack_traces=True,
    continue_on_errors=False,

    # Output configuration
    debug_log_level="INFO",
    save_debug_data=True,
    debug_output_path="/tmp/cycle_debug"
)

# Execute with debugging
debug_result = await cyclic_executor.execute_with_debugging(
    cycle_config=cycle_config,
    debugger=cycle_debugger
)

# Analyze debug data
debug_analysis = cycle_debugger.analyze_execution()

print("Debug Analysis:")
print(f"Total iterations: {debug_analysis.total_iterations}")
print(f"Failed iterations: {debug_analysis.failed_iterations}")
print(f"Average iteration time: {debug_analysis.avg_iteration_time_ms:.1f}ms")
print(f"Convergence trend: {debug_analysis.convergence_trend}")

# Detailed iteration analysis
for iteration_debug in debug_analysis.iteration_details:
    print(f"\nIteration {iteration_debug.iteration}:")
    print(f"  Duration: {iteration_debug.duration_ms:.1f}ms")
    print(f"  Memory peak: {iteration_debug.peak_memory_mb:.1f}MB")
    print(f"  Nodes executed: {len(iteration_debug.node_executions)}")

    if iteration_debug.errors:
        print(f"  Errors: {iteration_debug.errors}")

    # Node-level debugging
    for node_debug in iteration_debug.node_executions:
        print(f"    {node_debug.node_name}: {node_debug.duration_ms:.1f}ms")
        if node_debug.state_changes:
            print(f"      State changes: {node_debug.state_changes}")
```

### Performance Profiling

```python
# Initialize profiler
cycle_profiler = CycleProfiler(
    cycle_id="optimization_cycle_001",

    # Profiling configuration
    profile_cpu=True,
    profile_memory=True,
    profile_io=True,
    profile_network=False,

    # Sampling configuration
    sampling_interval_ms=100,
    memory_sampling_enabled=True,

    # Analysis configuration
    generate_hotspots=True,
    identify_bottlenecks=True,
    track_resource_trends=True,

    # Output configuration
    generate_reports=True,
    report_formats=["json", "html", "csv"],
    profile_output_path="/tmp/cycle_profiling"
)

# Execute with profiling
profiling_result = await cyclic_executor.execute_with_profiling(
    cycle_config=cycle_config,
    profiler=cycle_profiler
)

# Generate performance analysis
performance_analysis = cycle_profiler.generate_analysis()

print("Performance Analysis:")
print(f"Execution efficiency: {performance_analysis.efficiency_score:.2f}")
print(f"Resource utilization: {performance_analysis.resource_utilization:.2f}")
print(f"Bottlenecks identified: {len(performance_analysis.bottlenecks)}")

# Bottleneck analysis
for bottleneck in performance_analysis.bottlenecks:
    print(f"\nBottleneck: {bottleneck.location}")
    print(f"  Type: {bottleneck.type}")
    print(f"  Impact: {bottleneck.impact_score:.2f}")
    print(f"  Recommendation: {bottleneck.optimization_suggestion}")

# Resource trend analysis
trends = performance_analysis.resource_trends
print(f"\nResource Trends:")
print(f"  Memory growth rate: {trends.memory_growth_rate:.3f} MB/iteration")
print(f"  CPU usage trend: {trends.cpu_trend}")
print(f"  Execution time trend: {trends.time_trend}")
```

## Production Patterns

### Complete Optimization Workflow

```python
async def create_production_optimization_workflow():
    """Create a production-ready optimization workflow with full monitoring."""

    # Initialize components
    workflow = WorkflowBuilder()

    # Add optimization nodes
    workflow.add_node("DataLoaderNode", "data_loader", {
        "data_source": "production_dataset",
        "batch_size": 1000,
        "validation_split": 0.2
    })

    workflow.add_node("FeatureEngineerNode", "feature_engineer", {
        "feature_selection": True,
        "normalization": "standard",
        "encoding": "one_hot"
    })

    workflow.add_node("ModelTrainerNode", "model_trainer", {
        "algorithm": "xgboost",
        "objective": "binary:logistic",
        "max_depth": 6
    })

    workflow.add_node("ModelEvaluatorNode", "model_evaluator", {
        "metrics": ["accuracy", "precision", "recall", "f1", "auc"],
        "cross_validation": True,
        "cv_folds": 5
    })

    workflow.add_node("HyperparameterOptimizerNode", "hyperopt", {
        "optimization_algorithm": "tpe",
        "search_space": {
            "max_depth": {"type": "int", "low": 3, "high": 10},
            "learning_rate": {"type": "float", "low": 0.01, "high": 0.3},
            "n_estimators": {"type": "int", "low": 50, "high": 500}
        },
        "optimization_metric": "f1"
    })

    workflow.add_node("ConvergenceCheckerNode", "convergence", {
        "convergence_mode": "multi_criteria",
        "threshold_conditions": {
            "f1_score": {"operator": ">", "value": 0.9},
            "auc": {"operator": ">", "value": 0.95}
        },
        "stability_config": {
            "window_size": 5,
            "variance_threshold": 0.001
        },
        "early_stopping": {
            "patience": 10,
            "min_improvement": 0.001
        }
    })

    # Connect workflow nodes
    workflow.add_connection("data_loader", "feature_engineer", "dataset", "raw_data")
    workflow.add_connection("feature_engineer", "model_trainer", "features", "training_data")
    workflow.add_connection("model_trainer", "model_evaluator", "model", "trained_model")
    workflow.add_connection("model_evaluator", "hyperopt", "metrics", "current_performance")
    workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
    workflow.add_connection("model_evaluator", "convergence", "metrics", "current_metrics")

    # Configure optimization cycle
    optimization_cycle = (workflow.create_cycle("model_optimization")
        .max_iterations(50)
        .timeout(1800)  # 30 minutes
        .memory_limit(4096)  # 4GB
        .converge_when("f1_score > 0.9 and auc > 0.95")
        .converge_when("stability_variance < 0.001")
        .preserve_state(["best_model", "best_hyperparams", "performance_history"])
        .enable_safety_monitoring()
        .enable_debugging()
        .enable_profiling()
        .build()
    )

    # Initialize safety and monitoring
    safety_manager = CycleSafetyManager(
        max_concurrent_cycles=1,
        global_memory_limit_mb=8192,
        monitoring_interval_seconds=10,
        auto_terminate_on_violation=True
    )

    cycle_monitor = CycleMonitor(
        cycle_id=optimization_cycle.cycle_id,
        memory_limit_mb=4096,
        cpu_time_limit_seconds=1800,
        iteration_limit=50,
        enable_health_scoring=True
    )

    debugger = CycleDebugger(
        cycle_id=optimization_cycle.cycle_id,
        capture_node_outputs=True,
        track_execution_time=True,
        save_debug_data=True
    )

    profiler = CycleProfiler(
        cycle_id=optimization_cycle.cycle_id,
        profile_cpu=True,
        profile_memory=True,
        generate_reports=True
    )

    return {
        "workflow": workflow,
        "optimization_cycle": optimization_cycle,
        "safety_manager": safety_manager,
        "monitor": cycle_monitor,
        "debugger": debugger,
        "profiler": profiler
    }

# Execute production optimization
async def run_production_optimization():
    """Run production optimization workflow with full monitoring."""

    # Create workflow
    components = await create_production_optimization_workflow()

    try:
        # Start monitoring
        await components["safety_manager"].start_monitoring()
        await components["monitor"].start()

        # Execute optimization cycle
        result = await components["workflow"].execute_cycle_with_monitoring(
            cycle=components["optimization_cycle"],
            monitor=components["monitor"],
            debugger=components["debugger"],
            profiler=components["profiler"]
        )

        # Analyze results
        print(f"Optimization completed:")
        print(f"  Iterations: {result.total_iterations}")
        print(f"  Converged: {result.converged}")
        print(f"  Best F1 score: {result.best_metrics['f1_score']:.4f}")
        print(f"  Best AUC: {result.best_metrics['auc']:.4f}")
        print(f"  Total time: {result.execution_time_seconds:.1f}s")

        # Performance analysis
        performance = await components["profiler"].generate_analysis()
        print(f"  Efficiency score: {performance.efficiency_score:.2f}")
        print(f"  Resource utilization: {performance.resource_utilization:.2f}")

        return result

    finally:
        # Cleanup
        await components["monitor"].stop()
        await components["safety_manager"].stop_monitoring()

# Run the optimization
optimization_result = await run_production_optimization()
```

## Best Practices

### 1. State Management

```python
# Effective state management patterns
class StatefulOptimizationNode(CycleAwareNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = kwargs.get('name', 'stateful_node')

    async def run(self, **inputs):
        # Always check iteration context
        iteration = self.get_iteration()
        is_first = self.is_first_iteration()

        # Initialize state on first iteration
        if is_first:
            self.initialize_state(inputs)

        # Always preserve critical state
        self.preserve_critical_state()

        # Use accumulated values for trending
        self.accumulate_values("performance_metrics", current_metrics)

        # Detect convergence trends
        trend = self.detect_convergence_trend(
            values=self.get_cycle_state("performance_history", []),
            window_size=5
        )

        return {"results": results, "trend": trend}

    def preserve_critical_state(self):
        """Preserve state that must survive across iterations."""
        critical_state = {
            "best_model": self.best_model,
            "optimization_history": self.optimization_history,
            "performance_baseline": self.performance_baseline
        }

        for key, value in critical_state.items():
            self.set_cycle_state(key, value)
```

### 2. Convergence Strategy

```python
# Multi-layered convergence strategy
def create_robust_convergence_strategy():
    """Create robust convergence detection strategy."""

    return {
        # Primary convergence criteria
        "primary_criteria": [
            {"type": "threshold", "metric": "accuracy", "operator": ">", "value": 0.95},
            {"type": "threshold", "metric": "loss", "operator": "<", "value": 0.05}
        ],

        # Secondary criteria for stability
        "stability_criteria": [
            {"type": "variance", "metric": "accuracy", "window": 5, "threshold": 0.001},
            {"type": "improvement_rate", "metric": "loss", "window": 3, "threshold": 0.0001}
        ],

        # Safety criteria
        "safety_criteria": [
            {"type": "max_iterations", "value": 100},
            {"type": "timeout", "value": 1800},
            {"type": "no_improvement", "patience": 15}
        ],

        # Adaptive criteria
        "adaptive_criteria": [
            {"iterations": [20, 50, 80], "accuracy_targets": [0.8, 0.9, 0.95]}
        ]
    }
```

### 3. Resource Optimization

```python
# Resource usage optimization
async def optimize_cycle_resources():
    """Optimize cycle resource usage."""

    # Memory optimization
    memory_config = {
        "enable_garbage_collection": True,
        "gc_frequency": "per_iteration",
        "memory_monitoring": True,
        "memory_limit_mb": 2048,
        "memory_growth_threshold": 0.1
    }

    # CPU optimization
    cpu_config = {
        "enable_parallel_processing": True,
        "max_workers": 4,
        "cpu_monitoring": True,
        "cpu_limit_percent": 80
    }

    # I/O optimization
    io_config = {
        "batch_size": 1000,
        "async_io": True,
        "cache_strategy": "lru",
        "cache_size": 100
    }

    return {
        "memory": memory_config,
        "cpu": cpu_config,
        "io": io_config
    }
```

## Related Guides

**Prerequisites:**
- [Edge Computing Guide](30-edge-computing-guide.md) - Edge deployment
- [Durable Gateway Guide](29-durable-gateway-guide.md) - Gateway durability

**Next Steps:**
- [MCP Node Development Guide](32-mcp-node-development-guide.md) - Custom MCP nodes
- [Database Integration Guide](33-database-integration-guide.md) - Database patterns

---

**Master iterative workflows with advanced cycle management and intelligent convergence detection!**
