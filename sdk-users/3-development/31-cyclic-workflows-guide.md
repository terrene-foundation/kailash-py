# Cyclic Workflows Guide

⚠️ **PLANNED FEATURE - NOT YET IMPLEMENTED**

This documentation describes a planned feature for cyclic workflows that is not yet available in the current SDK version. The implementation is planned for a future release.

## What This Would Be

Cyclic workflows would enable iterative processing patterns including optimization loops, retry mechanisms, data quality cycles, and training workflows. When implemented, the Kailash SDK would provide comprehensive cycle management with state persistence, convergence detection, safety mechanisms, and performance optimization.

**Current Status**: Planned but not implemented
**Target Release**: TBD

## Overview

*Note: The following describes the planned implementation. None of these features are currently available.*

Cyclic workflows would enable iterative processing patterns including optimization loops, retry mechanisms, data quality cycles, and training workflows. The Kailash SDK would provide comprehensive cycle management with state persistence, convergence detection, safety mechanisms, and performance optimization.

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

# Create parameter optimization workflow using working SDK patterns
workflow = WorkflowBuilder()

# Parameter optimizer using PythonCodeNode
workflow.add_node("PythonCodeNode", "optimizer", {
    "code": """
import random

# Get parameters or initialize
try:
    params = input_data.get('parameters', {})
    iteration = input_data.get('iteration', 0)
    best_quality = input_data.get('best_quality', 0.0)
except:
    params = {'learning_rate': 0.01, 'batch_size': 32, 'regularization': 0.001}
    iteration = 0
    best_quality = 0.0

# Optimize parameters (gradient descent simulation)
learning_rate = params.get('learning_rate', 0.01) * (0.95 ** iteration)
new_params = {}
for key, value in params.items():
    # Simulate gradient-based update
    gradient = random.uniform(-0.1, 0.1)
    new_params[key] = value - learning_rate * gradient

# Evaluate quality (simulate with noise)
quality = min(0.99, 0.5 + 0.4 * (iteration / 50) + random.uniform(-0.05, 0.05))

# Update best if improved
if quality > best_quality:
    best_quality = quality

result = {
    'parameters': new_params,
    'quality': quality,
    'best_quality': best_quality,
    'iteration': iteration + 1,
    'converged': quality > 0.95 or iteration >= 50
}
"""
})

# Build workflow and create cycle
built_workflow = workflow.build()

# Create optimization cycle using the working CycleBuilder API
optimization_cycle = built_workflow.create_cycle("parameter_optimization")
# CRITICAL: Use "result." prefix for PythonCodeNode in mapping
optimization_cycle.connect("optimizer", "optimizer", mapping={
    "result.parameters": "input_data",
    "result.quality": "quality",
    "result.best_quality": "best_quality",
    "result.iteration": "iteration"
}) \
                  .max_iterations(50) \
                  .converge_when("converged == True") \
                  .timeout(300) \
                  .build()

# Execute the optimization
runtime = LocalRuntime()
results, run_id = runtime.execute(built_workflow)

print(f"Optimization completed in {results['optimizer']['result']['iteration']} iterations")
print(f"Final quality: {results['optimizer']['result']['quality']:.3f}")
print(f"Best quality achieved: {results['optimizer']['result']['best_quality']:.3f}")
```

### CycleState Management

Comprehensive state management across cycle iterations.

```python
# State Management Using PythonCodeNode with Persistent Variables

workflow = WorkflowBuilder()

# State management using PythonCodeNode with class-based persistence
workflow.add_node("PythonCodeNode", "state_manager", {
    "code": """
# Persistent state management using class variables
class OptimizationState:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.best_params = None
            cls._instance.best_quality = 0.0
            cls._instance.quality_history = []
            cls._instance.iteration = 0
        return cls._instance

    def initialize_state(self, initial_params):
        if self.best_params is None:
            self.best_params = initial_params.copy()
            self.best_quality = 0.0
            self.quality_history = []
            self.iteration = 0

    def update_state(self, params, quality):
        self.quality_history.append(quality)
        if quality > self.best_quality:
            self.best_params = params.copy()
            self.best_quality = quality
        self.iteration += 1

    def get_convergence_trend(self, window_size=5, threshold=0.001):
        if len(self.quality_history) < window_size:
            return False

        recent = self.quality_history[-window_size:]
        variance = sum((x - sum(recent)/len(recent))**2 for x in recent) / len(recent)
        return variance < threshold

# Initialize or get state
state = OptimizationState()

# Get input parameters
try:
    current_params = input_data.get('params', {'learning_rate': 0.01, 'momentum': 0.9})
    dataset = input_data.get('dataset', [])
except:
    current_params = {'learning_rate': 0.01, 'momentum': 0.9}
    dataset = []

# Initialize on first run
state.initialize_state(current_params)

# Optimize parameters
learning_rate = 0.01 * (0.95 ** state.iteration)
optimized_params = {}
for key, value in current_params.items():
    # Simulate gradient descent
    import random
    gradient = random.uniform(-0.1, 0.1)
    optimized_params[key] = value - learning_rate * gradient

# Evaluate quality (simulate)
base_quality = 0.5
for key, value in optimized_params.items():
    base_quality += 0.1 * (1 - abs(value))

# Add noise and iteration improvement
quality_score = min(0.99, base_quality + state.iteration * 0.01 + random.uniform(-0.05, 0.05))

# Update state
state.update_state(optimized_params, quality_score)

# Check convergence
convergence_trend = state.get_convergence_trend()
converged = quality_score > 0.95 or state.iteration >= 50 or convergence_trend

result = {
    'optimized_params': optimized_params,
    'quality_score': quality_score,
    'best_params': state.best_params,
    'best_quality': state.best_quality,
    'convergence_trend': convergence_trend,
    'iteration': state.iteration,
    'converged': converged,
    'quality_history': state.quality_history[-10:]  # Last 10 for brevity
}
"""
})
```

## Convergence Detection

Advanced convergence detection with multiple criteria and adaptive thresholds.

### ConvergenceCheckerNode

```python
# Convergence Detection Using PythonCodeNode

workflow = WorkflowBuilder()

# Multi-criteria convergence checker using PythonCodeNode
workflow.add_node("PythonCodeNode", "convergence_checker", {
    "code": """
# Multi-criteria convergence detection
def check_convergence(quality_score, iteration, quality_history, improvement_rate=None, stability_variance=None):
    convergence_results = {
        'converged': False,
        'reason': None,
        'criteria_met': [],
        'final_metrics': {}
    }

    # Threshold-based convergence
    if quality_score > 0.95:
        convergence_results['criteria_met'].append('quality_threshold')

    if improvement_rate is not None and improvement_rate < 0.001:
        convergence_results['criteria_met'].append('improvement_rate')

    if stability_variance is not None and stability_variance < 0.0001:
        convergence_results['criteria_met'].append('stability_variance')

    # Stability-based convergence (window analysis)
    if len(quality_history) >= 5:
        recent_scores = quality_history[-5:]
        window_mean = sum(recent_scores) / len(recent_scores)
        window_variance = sum((x - window_mean)**2 for x in recent_scores) / len(recent_scores)

        if window_variance < 0.001:
            convergence_results['criteria_met'].append('stability_window')

    # Improvement rate monitoring
    if len(quality_history) >= 3:
        recent_improvement = quality_history[-1] - quality_history[-3]
        if recent_improvement < 0.001:
            convergence_results['criteria_met'].append('min_improvement')

    # Custom expression conditions
    if quality_score > 0.9 and iteration > 10:
        convergence_results['criteria_met'].append('expression_1')

    if improvement_rate is not None and stability_variance is not None:
        if improvement_rate < 0.001 and stability_variance < 0.0001:
            convergence_results['criteria_met'].append('expression_2')

    if iteration > 30 and quality_score > 0.85:
        convergence_results['criteria_met'].append('expression_3')

    # Adaptive criteria (early stopping)
    adaptive_thresholds = {
        10: 0.7,
        25: 0.85,
        40: 0.95
    }

    for iter_threshold, quality_threshold in adaptive_thresholds.items():
        if iteration >= iter_threshold and quality_score >= quality_threshold:
            convergence_results['criteria_met'].append(f'adaptive_{iter_threshold}')

    # Overall convergence decision (require at least 2 criteria)
    if len(convergence_results['criteria_met']) >= 2:
        convergence_results['converged'] = True
        convergence_results['reason'] = f"Multiple criteria met: {convergence_results['criteria_met']}"
    elif quality_score > 0.95:  # Strong single criterion
        convergence_results['converged'] = True
        convergence_results['reason'] = "Quality threshold exceeded"
    elif iteration >= 100:  # Safety limit
        convergence_results['converged'] = True
        convergence_results['reason'] = "Maximum iterations reached"
    else:
        convergence_results['reason'] = "Convergence criteria not yet met"

    convergence_results['final_metrics'] = {
        'quality_score': quality_score,
        'iteration': iteration,
        'criteria_count': len(convergence_results['criteria_met'])
    }

    return convergence_results

# Get input data
quality_score = input_data.get('quality_score', 0.0)
iteration = input_data.get('iteration', 0)
quality_history = input_data.get('quality_history', [])
improvement_rate = input_data.get('improvement_rate')
stability_variance = input_data.get('stability_variance')

# Check convergence
result = check_convergence(
    quality_score=quality_score,
    iteration=iteration,
    quality_history=quality_history,
    improvement_rate=improvement_rate,
    stability_variance=stability_variance
)
"""
})

# Example usage in a workflow
runtime = LocalRuntime()
convergence_data = {
    'quality_score': 0.92,
    'iteration': 25,
    'quality_history': [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.91, 0.92],
    'improvement_rate': 0.01,
    'stability_variance': 0.0005
}

results, run_id = runtime.execute(workflow.build(), parameters={'convergence_checker': convergence_data})
convergence_result = results['convergence_checker']['result']

if convergence_result["converged"]:
    print(f"Convergence achieved: {convergence_result['reason']}")
    print(f"Final quality: {convergence_result['final_metrics']}")
else:
    print(f"Continue iteration: {convergence_result['reason']}")
```

### Multi-Criteria Convergence

```python
# Multi-Criteria Convergence Using PythonCodeNode

workflow = WorkflowBuilder()

# Advanced multi-dimensional convergence checker
workflow.add_node("PythonCodeNode", "multi_criteria_checker", {
    "code": """
def multi_criteria_convergence_check(metrics, iteration, metric_history=None):
    # Define convergence criteria
    convergence_config = {
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
    }

    results = {
        'weighted_score': 0.0,
        'criteria_met': {},
        'converged': False,
        'individual_scores': {},
        'convergence_details': {}
    }

    total_weight = 0
    weighted_sum = 0

    # Calculate individual criteria scores
    for metric_name, config in convergence_config.items():
        if metric_name not in metrics:
            continue

        current_value = metrics[metric_name]
        target = config['target']
        weight = config['weight']
        direction = config['direction']
        tolerance = config['tolerance']

        # Calculate score based on direction
        if direction == "maximize":
            # Score is how close we are to target (capped at 1.0)
            score = min(1.0, current_value / target)
            target_met = current_value >= (target - tolerance)
        else:  # minimize
            # Score is inverse - lower values are better
            if current_value <= target:
                score = 1.0
            else:
                score = max(0.0, target / current_value)
            target_met = current_value <= (target + tolerance)

        results['individual_scores'][metric_name] = score
        results['criteria_met'][metric_name] = target_met
        results['convergence_details'][metric_name] = {
            'current': current_value,
            'target': target,
            'met': target_met,
            'score': score,
            'weight': weight
        }

        # Add to weighted sum
        weighted_sum += score * weight
        total_weight += weight

    # Calculate overall weighted score
    if total_weight > 0:
        results['weighted_score'] = weighted_sum / total_weight

    # Convergence strategies
    min_weighted_score = 0.85

    # Strategy 1: Weighted score threshold
    weighted_converged = results['weighted_score'] >= min_weighted_score

    # Strategy 2: All criteria met
    all_criteria_met = all(results['criteria_met'].values()) if results['criteria_met'] else False

    # Strategy 3: Majority of criteria met
    criteria_count = len(results['criteria_met'])
    met_count = sum(results['criteria_met'].values())
    majority_met = met_count > (criteria_count / 2) if criteria_count > 0 else False

    # Strategy 4: Early stopping (absolute targets)
    early_stop = False
    if 'accuracy' in metrics and metrics['accuracy'] >= 0.99:
        early_stop = True
        results['convergence_details']['early_stop'] = 'accuracy >= 0.99'
    elif 'loss' in metrics and metrics['loss'] <= 0.01:
        early_stop = True
        results['convergence_details']['early_stop'] = 'loss <= 0.01'

    # Strategy 5: Stability check
    stability_converged = False
    if metric_history and len(metric_history) >= 5:
        # Check stability across recent iterations
        recent_scores = [h.get('weighted_score', 0) for h in metric_history[-5:]]
        if len(recent_scores) == 5:
            variance = sum((x - sum(recent_scores)/5)**2 for x in recent_scores) / 5
            stability_converged = variance < 0.002
            results['convergence_details']['stability_variance'] = variance

    # Final convergence decision (using weighted score strategy)
    results['converged'] = (
        weighted_converged or
        early_stop or
        (all_criteria_met and majority_met) or
        iteration >= 100  # Safety limit
    )

    results['convergence_reasons'] = []
    if weighted_converged:
        results['convergence_reasons'].append(f"Weighted score {results['weighted_score']:.3f} >= {min_weighted_score}")
    if early_stop:
        results['convergence_reasons'].append("Early stopping condition met")
    if all_criteria_met:
        results['convergence_reasons'].append("All criteria targets achieved")
    if stability_converged:
        results['convergence_reasons'].append("Stability achieved")

    return results

# Get input data
metrics = input_data.get('metrics', {})
iteration = input_data.get('iteration', 0)
metric_history = input_data.get('metric_history', [])

# Run multi-criteria check
result = multi_criteria_convergence_check(metrics, iteration, metric_history)
"""
})

# Example usage
runtime = LocalRuntime()
test_data = {
    'metrics': {
        "accuracy": 0.94,
        "loss": 0.06,
        "f1_score": 0.89,
        "training_time": 58.0
    },
    'iteration': 25,
    'metric_history': [
        {'weighted_score': 0.80},
        {'weighted_score': 0.82},
        {'weighted_score': 0.84},
        {'weighted_score': 0.85},
        {'weighted_score': 0.86}
    ]
}

results, run_id = runtime.execute(workflow.build(), parameters={'multi_criteria_checker': test_data})
multi_result = results['multi_criteria_checker']['result']

print(f"Overall convergence score: {multi_result['weighted_score']:.3f}")
print(f"Individual criteria met: {multi_result['criteria_met']}")
print(f"Converged: {multi_result['converged']}")
```

## Cycle Building and Templates

Fluent API for creating cyclic workflows with pre-built templates.

### CycleBuilder

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create workflow with comprehensive machine learning cycle
workflow = WorkflowBuilder()

# Add processing nodes
workflow.add_node("PythonCodeNode", "data_preprocessor", {
    "code": """
import random

# Get input data or initialize
try:
    data = input_data.get('data', [])
    params = input_data.get('params', {})
    iteration = input_data.get('iteration', 0)
except:
    data = [random.uniform(0, 1) for _ in range(100)]
    params = {'learning_rate': 0.01}
    iteration = 0

# Preprocess data
normalized_data = [(x - 0.5) * 2 for x in data]  # Normalize to [-1, 1]
processed_data = normalized_data[:50]  # Feature selection

result = {
    'data': processed_data,
    'params': params,
    'iteration': iteration + 1,
    'preprocessed': True
}
"""
})

workflow.add_node("PythonCodeNode", "model_trainer", {
    "code": """
import random

# Extract training data and parameters
data = input_data.get('data', [])
params = input_data.get('params', {'learning_rate': 0.01})
iteration = input_data.get('iteration', 0)

# Simulate model training
learning_rate = params.get('learning_rate', 0.01)
loss = max(0.01, 1.0 / (iteration + 1) + random.uniform(-0.1, 0.1))
accuracy = min(0.99, 0.5 + 0.4 * (iteration / 20))

trained_model = {
    'weights': [random.random() for _ in range(10)],
    'loss': loss,
    'accuracy': accuracy,
    'learning_rate': learning_rate
}

result = {
    'model': trained_model,
    'metrics': {'loss': loss, 'accuracy': accuracy},
    'iteration': iteration,
    'data': data
}
"""
})

workflow.add_node("PythonCodeNode", "evaluator", {
    "code": """
# Evaluate model performance
model = input_data.get('model', {})
iteration = input_data.get('iteration', 0)

loss = model.get('loss', 1.0)
accuracy = model.get('accuracy', 0.5)

# Calculate improvement metrics
improvement = max(0, accuracy - 0.9) if iteration > 0 else 0
converged = accuracy > 0.95 and loss < 0.05

result = {
    'model': model,
    'metrics': {
        'loss': loss,
        'accuracy': accuracy,
        'improvement': improvement
    },
    'iteration': iteration,
    'converged': converged,
    'needs_optimization': not converged
}
"""
})

# Connect nodes in the workflow
workflow.add_connection("data_preprocessor", "result", "model_trainer", "input_data")
workflow.add_connection("model_trainer", "result", "evaluator", "input_data")

# Build workflow and create cycle using modern API
built_workflow = workflow.build()

# Create optimization cycle
optimization_cycle = built_workflow.create_cycle("ml_optimization")
# CRITICAL: Use "result." prefix for PythonCodeNode in mapping
optimization_cycle.connect("evaluator", "data_preprocessor", mapping={
    "result.model": "input_data",
    "result.metrics": "metrics",
    "result.iteration": "iteration"
}) \
                  .max_iterations(50) \
                  .converge_when("converged == True") \
                  .timeout(600) \
                  .build()

# Execute the cycle
runtime = LocalRuntime()
results, run_id = runtime.execute(built_workflow)

print(f"ML Training completed with {results['evaluator']['result']['iteration']} iterations")
print(f"Final accuracy: {results['evaluator']['result']['metrics']['accuracy']:.3f}")
print(f"Final loss: {results['evaluator']['result']['metrics']['loss']:.3f}")
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
# Safety and Resource Management Using PythonCodeNode

workflow = WorkflowBuilder()

# Resource monitoring using PythonCodeNode
workflow.add_node("PythonCodeNode", "resource_monitor", {
    "code": """
# Safety and resource monitoring implementation
import psutil
import time
import threading
from datetime import datetime

class CycleSafetyMonitor:
    def __init__(self):
        self.start_time = time.time()
        self.iteration_count = 0
        self.memory_readings = []
        self.cpu_readings = []
        self.violations = []

        # Safety limits
        self.max_iterations = 100
        self.max_memory_mb = 1024
        self.max_cpu_time_seconds = 300
        self.memory_growth_threshold = 0.1  # 10%

        # Alert thresholds
        self.alert_threshold_memory = 0.8  # 80%
        self.alert_threshold_cpu = 0.9     # 90%

    def check_resource_limits(self):
        current_time = time.time()
        elapsed_time = current_time - self.start_time

        # Memory check
        try:
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            cpu_percent = process.cpu_percent()

            self.memory_readings.append(memory_mb)
            self.cpu_readings.append(cpu_percent)

            # Keep only recent readings
            if len(self.memory_readings) > 50:
                self.memory_readings = self.memory_readings[-50:]
                self.cpu_readings = self.cpu_readings[-50:]

        except:
            # Fallback if psutil fails
            memory_mb = 100  # Assume reasonable default
            cpu_percent = 10

        safety_status = {
            'safe': True,
            'violations': [],
            'warnings': [],
            'metrics': {
                'elapsed_time': elapsed_time,
                'memory_mb': memory_mb,
                'cpu_percent': cpu_percent,
                'iteration_count': self.iteration_count
            }
        }

        # Check violations
        if memory_mb > self.max_memory_mb:
            safety_status['safe'] = False
            safety_status['violations'].append(f'Memory limit exceeded: {memory_mb:.1f}MB > {self.max_memory_mb}MB')

        if elapsed_time > self.max_cpu_time_seconds:
            safety_status['safe'] = False
            safety_status['violations'].append(f'Time limit exceeded: {elapsed_time:.1f}s > {self.max_cpu_time_seconds}s')

        if self.iteration_count > self.max_iterations:
            safety_status['safe'] = False
            safety_status['violations'].append(f'Iteration limit exceeded: {self.iteration_count} > {self.max_iterations}')

        # Check warnings
        if memory_mb > (self.max_memory_mb * self.alert_threshold_memory):
            safety_status['warnings'].append(f'Memory usage high: {memory_mb:.1f}MB ({memory_mb/self.max_memory_mb*100:.1f}%)')

        if cpu_percent > (100 * self.alert_threshold_cpu):
            safety_status['warnings'].append(f'CPU usage high: {cpu_percent:.1f}%')

        # Check memory growth
        if len(self.memory_readings) >= 10:
            recent_avg = sum(self.memory_readings[-5:]) / 5
            earlier_avg = sum(self.memory_readings[-10:-5]) / 5
            growth_rate = (recent_avg - earlier_avg) / earlier_avg if earlier_avg > 0 else 0

            if growth_rate > self.memory_growth_threshold:
                safety_status['warnings'].append(f'Memory growth detected: {growth_rate*100:.1f}% per 5 iterations')

        return safety_status

    def increment_iteration(self):
        self.iteration_count += 1
        return self.check_resource_limits()

# Initialize or get monitor
if 'safety_monitor' not in globals():
    safety_monitor = CycleSafetyMonitor()

# Increment iteration and check safety
safety_status = safety_monitor.increment_iteration()

# Get current cycle data
cycle_data = input_data.get('cycle_data', {})
iteration = cycle_data.get('iteration', 0)

result = {
    'safety_status': safety_status,
    'continue_cycle': safety_status['safe'],
    'iteration': iteration,
    'monitoring_active': True,
    'resource_metrics': safety_status['metrics']
}
"""
})

# Monitored cycle execution using working SDK patterns
def create_monitored_cycle_workflow():
    """Create a workflow with built-in monitoring."""
    workflow = WorkflowBuilder()

    # Main processing node with monitoring
    workflow.add_node("PythonCodeNode", "monitored_processor", {
        "code": """
# Monitored cycle execution
import time
import random

# Get monitoring data
monitoring_data = input_data.get('monitoring', {})
iteration = monitoring_data.get('iteration', 0)
start_time = monitoring_data.get('start_time', time.time())

# Simulate processing work
processing_result = {
    'data_processed': random.randint(100, 1000),
    'quality_score': min(0.99, 0.5 + iteration * 0.02),
    'iteration': iteration + 1
}

# Check safety conditions with the monitor we created
cycle_data = {'iteration': iteration + 1}
safety_check = {'cycle_data': cycle_data}

# Simple inline safety check (could use the monitor node)
elapsed_time = time.time() - start_time
memory_estimate = 100 + iteration * 5  # Simulate memory growth

safety_status = {
    'safe': elapsed_time < 300 and memory_estimate < 1024 and iteration < 100,
    'violations': [],
    'metrics': {
        'elapsed_time': elapsed_time,
        'memory_estimate': memory_estimate,
        'iteration': iteration + 1
    }
}

if elapsed_time >= 300:
    safety_status['violations'].append('Time limit exceeded')
if memory_estimate >= 1024:
    safety_status['violations'].append('Memory limit exceeded')
if iteration >= 100:
    safety_status['violations'].append('Iteration limit exceeded')

# Determine if cycle should continue
continue_cycle = safety_status['safe'] and processing_result['quality_score'] < 0.95

result = {
    'processing_result': processing_result,
    'safety_status': safety_status,
    'continue_cycle': continue_cycle,
    'monitoring': {
        'iteration': iteration + 1,
        'start_time': start_time
    },
    'converged': not continue_cycle
}

# Display monitoring info
print(f"Iteration {iteration + 1}:")
print(f"  Elapsed time: {elapsed_time:.1f}s")
print(f"  Memory estimate: {memory_estimate} MB")
print(f"  Quality score: {processing_result['quality_score']:.3f}")
if safety_status['violations']:
    print(f"  Safety violations: {safety_status['violations']}")
"""
    })

    # Build and create cycle
    built_workflow = workflow.build()
    cycle = built_workflow.create_cycle("monitored_cycle")
    # CRITICAL: Use "result." prefix for PythonCodeNode in mapping
    cycle.connect("monitored_processor", "monitored_processor", mapping={
        "result.processing_result": "input_data",
        "result.monitoring": "monitoring"
    }) \
         .max_iterations(100) \
         .converge_when("converged == True") \
         .timeout(300) \
         .build()

    return built_workflow

# Execute monitored cycle
runtime = LocalRuntime()
monitored_workflow = create_monitored_cycle_workflow()
results, run_id = runtime.execute(monitored_workflow)

print("\\nMonitored cycle execution completed:")
final_result = results['monitored_processor']['result']
print(f"Final iteration: {final_result['monitoring']['iteration']}")
print(f"Safety status: {'SAFE' if final_result['safety_status']['safe'] else 'VIOLATIONS DETECTED'}")
print(f"Final quality: {final_result['processing_result']['quality_score']:.3f}")
```

### Resource Usage Analysis

```python
# Resource analysis using PythonCodeNode
workflow = WorkflowBuilder()

workflow.add_node("PythonCodeNode", "resource_analyzer", {
    "code": """
# Resource usage analysis implementation
import time
import random

def analyze_resource_usage(execution_history):
    \"\"\"Analyze resource usage patterns from execution history.\"\"\"

    if not execution_history:
        return {
            'peak_memory_mb': 0,
            'avg_cpu_percent': 0,
            'total_time_seconds': 0,
            'memory_efficiency': 0,
            'recommendations': []
        }

    # Extract metrics from history
    memory_readings = [h.get('memory_mb', 100) for h in execution_history]
    cpu_readings = [h.get('cpu_percent', 10) for h in execution_history]
    time_readings = [h.get('elapsed_time', 0) for h in execution_history]

    analysis = {
        'peak_memory_mb': max(memory_readings) if memory_readings else 0,
        'avg_cpu_percent': sum(cpu_readings) / len(cpu_readings) if cpu_readings else 0,
        'total_time_seconds': max(time_readings) if time_readings else 0,
        'memory_efficiency': 0.8,  # Simulated efficiency score
        'recommendations': []
    }

    # Generate recommendations
    if analysis['peak_memory_mb'] > 800:
        analysis['recommendations'].append({
            'description': 'Consider reducing batch size to lower memory usage',
            'estimated_improvement': '20-30% memory reduction',
            'implementation_steps': ['Adjust batch_size parameter', 'Use streaming processing']
        })

    if analysis['avg_cpu_percent'] < 50:
        analysis['recommendations'].append({
            'description': 'CPU utilization is low - consider parallel processing',
            'estimated_improvement': '40-60% speed improvement',
            'implementation_steps': ['Enable parallel processing', 'Increase worker count']
        })

    if len(execution_history) > 50:
        analysis['recommendations'].append({
            'description': 'Long-running cycle detected - consider convergence tuning',
            'estimated_improvement': '10-20% faster convergence',
            'implementation_steps': ['Adjust convergence criteria', 'Implement early stopping']
        })

    return analysis

# Simulate execution history
execution_history = []
for i in range(10):
    execution_history.append({
        'iteration': i,
        'memory_mb': 100 + i * 20 + random.uniform(-10, 10),
        'cpu_percent': 30 + random.uniform(-10, 20),
        'elapsed_time': i * 2.5
    })

# Analyze resource usage
resource_analysis = analyze_resource_usage(execution_history)

result = {
    'analysis': resource_analysis,
    'execution_history': execution_history
}
"""
})

# Execute analysis
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
resource_analysis = results['resource_analyzer']['result']['analysis']

print("Resource Usage Analysis:")
print(f"Peak memory usage: {resource_analysis['peak_memory_mb']:.1f} MB")
print(f"Average CPU usage: {resource_analysis['avg_cpu_percent']:.1f}%")
print(f"Total execution time: {resource_analysis['total_time_seconds']:.1f}s")
print(f"Memory efficiency: {resource_analysis['memory_efficiency']:.2f}")

# Performance recommendations
for rec in resource_analysis['recommendations']:
    print(f"\\nRecommendation: {rec['description']}")
    print(f"  Impact: {rec['estimated_improvement']}")
    print(f"  Implementation: {', '.join(rec['implementation_steps'])}")
```

## Debugging and Performance Analysis

Comprehensive debugging and performance analysis tools.

### CycleDebugger

```python
# Debugging Using PythonCodeNode with Logging

workflow = WorkflowBuilder()

# Debug and profiling node
workflow.add_node("PythonCodeNode", "cycle_debugger", {
    "code": """
# Comprehensive cycle debugging implementation
import time
import traceback
import logging
from datetime import datetime

class CycleDebugger:
    def __init__(self):
        self.start_time = time.time()
        self.iterations = []
        self.errors = []
        self.node_executions = []

        # Configuration
        self.capture_node_parameters = True
        self.capture_node_outputs = True
        self.track_execution_time = True
        self.track_memory_usage = True

    def log_iteration(self, iteration_data):
        current_time = time.time()

        iteration_info = {
            'iteration': len(self.iterations) + 1,
            'timestamp': datetime.now().isoformat(),
            'duration_ms': (current_time - self.start_time) * 1000,
            'data': iteration_data,
            'memory_estimate': 100 + len(self.iterations) * 10,  # Simulated
            'cpu_estimate': 20 + len(self.iterations) * 2,  # Simulated
            'errors': []
        }

        # Capture node execution details
        if self.capture_node_outputs and 'result' in iteration_data:
            iteration_info['node_outputs'] = {
                'keys': list(iteration_data['result'].keys()) if isinstance(iteration_data['result'], dict) else str(type(iteration_data['result']))
            }

        self.iterations.append(iteration_info)
        return iteration_info

    def analyze_execution(self):
        if not self.iterations:
            return {
                'total_iterations': 0,
                'failed_iterations': 0,
                'avg_iteration_time_ms': 0,
                'convergence_trend': 'No data',
                'iteration_details': []
            }

        total_iterations = len(self.iterations)
        failed_iterations = len([i for i in self.iterations if i['errors']])

        durations = [i['duration_ms'] for i in self.iterations]
        avg_iteration_time = sum(durations) / len(durations) if durations else 0

        # Analyze convergence trend
        if total_iterations >= 3:
            recent_times = durations[-3:]
            if all(recent_times[i] <= recent_times[i+1] for i in range(len(recent_times)-1)):
                convergence_trend = "Slowing down"
            elif all(recent_times[i] >= recent_times[i+1] for i in range(len(recent_times)-1)):
                convergence_trend = "Speeding up"
            else:
                convergence_trend = "Variable"
        else:
            convergence_trend = "Insufficient data"

        return {
            'total_iterations': total_iterations,
            'failed_iterations': failed_iterations,
            'avg_iteration_time_ms': avg_iteration_time,
            'convergence_trend': convergence_trend,
            'iteration_details': self.iterations,
            'memory_trend': [i['memory_estimate'] for i in self.iterations],
            'cpu_trend': [i['cpu_estimate'] for i in self.iterations]
        }

# Initialize or get debugger
if 'cycle_debugger' not in globals():
    cycle_debugger = CycleDebugger()

# Get current iteration data
current_data = input_data.get('cycle_data', {})
iteration_info = cycle_debugger.log_iteration(current_data)

# Analyze execution
debug_analysis = cycle_debugger.analyze_execution()

result = {
    'current_iteration': iteration_info,
    'debug_analysis': debug_analysis,
    'debugger_active': True
}
"""
})

# Execute debugging workflow
runtime = LocalRuntime()
debug_data = {'cycle_data': {'iteration': 5, 'quality': 0.8, 'result': {'processed': True}}}
results, run_id = runtime.execute(workflow.build(), parameters={'cycle_debugger': debug_data})

debug_analysis = results['cycle_debugger']['result']['debug_analysis']

print("Debug Analysis:")
print(f"Total iterations: {debug_analysis['total_iterations']}")
print(f"Failed iterations: {debug_analysis['failed_iterations']}")
print(f"Average iteration time: {debug_analysis['avg_iteration_time_ms']:.1f}ms")
print(f"Convergence trend: {debug_analysis['convergence_trend']}")

# Detailed iteration analysis
for iteration_debug in debug_analysis['iteration_details']:
    print(f"\\nIteration {iteration_debug['iteration']}:")
    print(f"  Duration: {iteration_debug['duration_ms']:.1f}ms")
    print(f"  Memory estimate: {iteration_debug['memory_estimate']:.1f}MB")
    print(f"  CPU estimate: {iteration_debug['cpu_estimate']:.1f}%")

    if iteration_debug['errors']:
        print(f"  Errors: {iteration_debug['errors']}")

    if 'node_outputs' in iteration_debug:
        print(f"  Node outputs: {iteration_debug['node_outputs']}")
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
