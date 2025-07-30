# Conditional Execution Migration Guide

## Overview

This guide helps you migrate from traditional data routing (`conditional_execution="route_data"`) to true conditional execution (`conditional_execution="skip_branches"`) for improved performance and industry-standard behavior.

## Migration Benefits

- **20-50% Performance Improvement**: Skip unreachable nodes entirely
- **Reduced Resource Usage**: Lower CPU and memory consumption
- **Industry-Standard Behavior**: True if/else conditional execution
- **Better Debugging**: Clearer execution paths in logs

## Migration Strategy

### Phase 1: Assessment and Planning

#### 1.1: Identify Conditional Workflows

```python
# Audit your workflows to identify conditional patterns
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

def audit_workflow_for_conditionals(workflow):
    """Check if workflow contains conditional logic."""
    conditional_nodes = []

    # Check for SwitchNodes
    for node_id, node_data in workflow.graph.nodes(data=True):
        node_instance = node_data.get('node') or node_data.get('instance')
        if hasattr(node_instance, '__class__') and 'Switch' in node_instance.__class__.__name__:
            conditional_nodes.append(node_id)

    return {
        'has_conditionals': len(conditional_nodes) > 0,
        'switch_nodes': conditional_nodes,
        'total_nodes': len(workflow.graph.nodes),
        'migration_potential': len(conditional_nodes) / len(workflow.graph.nodes)
    }

# Example usage
workflow = your_existing_workflow
audit_result = audit_workflow_for_conditionals(workflow)
print(f"Migration potential: {audit_result['migration_potential']:.2%}")
```

#### 1.2: Performance Baseline

```python
import time
from typing import Dict, Any

def measure_baseline_performance(workflow, test_data: Dict[str, Any], iterations: int = 5):
    """Measure current performance with traditional execution."""
    runtime = LocalRuntime(conditional_execution="route_data")

    times = []
    for _ in range(iterations):
        start_time = time.time()
        results, _ = runtime.execute(workflow, parameters=test_data)
        execution_time = time.time() - start_time
        times.append(execution_time)

    avg_time = sum(times) / len(times)
    node_count = len(results)

    return {
        'average_time': avg_time,
        'node_count': node_count,
        'times': times,
        'baseline_established': True
    }

# Establish baseline
baseline = measure_baseline_performance(workflow, your_test_data)
print(f"Baseline: {baseline['average_time']:.3f}s, {baseline['node_count']} nodes")
```

### Phase 2: Migration Patterns

#### 2.1: Simple Switch Migration

**Before (Traditional)**:
```python
# Traditional approach - all nodes execute
workflow = WorkflowBuilder()

workflow.add_node("DataSourceNode", "data_source", {
    "data": {"user_type": "premium"}
})

workflow.add_node("SwitchNode", "user_switch", {
    "condition_field": "user_type",
    "operator": "==",
    "value": "premium"
})

workflow.add_node("PythonCodeNode", "premium_processor", {
    "code": "result = {'features': ['all'], 'discount': 30}"
})

workflow.add_node("PythonCodeNode", "basic_processor", {
    "code": "result = {'features': ['basic'], 'discount': 5}"
})

workflow.add_connection("data_source", "result", "user_switch", "input_data")
workflow.add_connection("user_switch", "true_output", "premium_processor", "input")
workflow.add_connection("user_switch", "false_output", "basic_processor", "input")

# Traditional execution - ALL nodes execute
runtime = LocalRuntime(conditional_execution="route_data")
results, _ = runtime.execute(workflow.build())
print(f"Traditional: {len(results)} nodes executed")  # Output: 4 nodes
```

**After (Conditional)**:
```python
# Same workflow structure, different runtime configuration
runtime = LocalRuntime(conditional_execution="skip_branches")
results, _ = runtime.execute(workflow.build())
print(f"Conditional: {len(results)} nodes executed")  # Output: 3 nodes

# Validate results are equivalent for your business logic
assert results['premium_processor'] is not None  # Premium path executed
assert 'basic_processor' not in results or results['basic_processor'] is None  # Basic path skipped
```

#### 2.2: Complex Hierarchical Migration

**Before (Traditional)**:
```python
# Complex nested conditions - all branches execute regardless
workflow = WorkflowBuilder()

# Data with multiple decision points
workflow.add_node("DataSourceNode", "data_source", {
    "data": {
        "user_type": "premium",
        "region": "US",
        "subscription_status": "active",
        "payment_method": "credit_card"
    }
})

# Multiple switches (all currently execute)
workflow.add_node("SwitchNode", "type_switch", {"condition_field": "user_type", "operator": "==", "value": "premium"})
workflow.add_node("SwitchNode", "region_switch", {"condition_field": "region", "operator": "==", "value": "US"})
workflow.add_node("SwitchNode", "status_switch", {"condition_field": "subscription_status", "operator": "==", "value": "active"})
workflow.add_node("SwitchNode", "payment_switch", {"condition_field": "payment_method", "operator": "==", "value": "credit_card"})

# Many processors (all currently execute even if not needed)
processors = [
    ("us_premium_active_cc", "US Premium Active with Credit Card"),
    ("us_premium_active_other", "US Premium Active with Other Payment"),
    ("us_premium_inactive", "US Premium Inactive"),
    ("intl_premium", "International Premium"),
    ("basic_user", "Basic User")
]

for proc_id, description in processors:
    workflow.add_node("PythonCodeNode", proc_id, {
        "code": f"result = {{'description': '{description}', 'processed': True}}"
    })

# Traditional execution
runtime_traditional = LocalRuntime(conditional_execution="route_data")
results_traditional, _ = runtime_traditional.execute(workflow.build())
print(f"Traditional: {len(results_traditional)} total nodes executed")
```

**After (Conditional)**:
```python
# Same workflow, conditional execution
runtime_conditional = LocalRuntime(conditional_execution="skip_branches")
results_conditional, _ = runtime_conditional.execute(workflow.build())
print(f"Conditional: {len(results_conditional)} total nodes executed")

# Performance comparison
node_reduction = (len(results_traditional) - len(results_conditional)) / len(results_traditional)
print(f"Node reduction: {node_reduction:.1%}")  # Expected: 60-70% reduction

# Only the reachable path executes:
# data_source → type_switch → region_switch → status_switch → payment_switch → us_premium_active_cc
```

#### 2.3: Merge Node Migration

**Before (Traditional)**:
```python
from kailash.nodes.logic.operations import MergeNode

# Workflow with merge patterns
workflow = WorkflowBuilder()

workflow.add_node("DataSourceNode", "data_source", {
    "data": {"process_a": True, "process_b": False, "process_c": True}
})

# Traditional: All processors execute, many produce None
for branch in ['a', 'b', 'c']:
    workflow.add_node("SwitchNode", f"switch_{branch}", {
        "condition_field": f"process_{branch}",
        "operator": "==",
        "value": True
    })

    workflow.add_node("PythonCodeNode", f"processor_{branch}", {
        "code": f"result = {{'branch': '{branch}', 'value': {ord(branch)}}} if input else None"
    })

# Merge handles many None values
workflow.add_node("MergeNode", "merge_results", {
    "merge_type": "merge_dict",
    "skip_none": True
})

runtime_traditional = LocalRuntime(conditional_execution="route_data")
results_traditional, _ = runtime_traditional.execute(workflow.build())
print(f"Traditional merge: {len(results_traditional)} nodes, many with None values")
```

**After (Conditional)**:
```python
# Same workflow structure
runtime_conditional = LocalRuntime(conditional_execution="skip_branches")
results_conditional, _ = runtime_conditional.execute(workflow.build())
print(f"Conditional merge: {len(results_conditional)} nodes, only active branches")

# MergeNode now receives only actual data, no None values
# processor_b is never executed, so merge only gets data from a and c
```

### Phase 3: Validation and Testing

#### 3.1: Automated Validation Framework

```python
import json
from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class MigrationTestCase:
    name: str
    workflow: Any
    test_data: Dict[str, Any]
    expected_business_outcome: Any

class ConditionalMigrationValidator:
    """Validates migration from traditional to conditional execution."""

    def __init__(self):
        self.test_cases: List[MigrationTestCase] = []

    def add_test_case(self, name: str, workflow: Any, test_data: Dict[str, Any], expected_outcome: Any):
        """Add a test case for validation."""
        self.test_cases.append(MigrationTestCase(name, workflow, test_data, expected_outcome))

    def validate_migration(self) -> Dict[str, Any]:
        """Run comprehensive migration validation."""
        results = {
            'total_tests': len(self.test_cases),
            'passed': 0,
            'failed': 0,
            'performance_improvements': [],
            'issues': []
        }

        for test_case in self.test_cases:
            try:
                # Test traditional execution
                runtime_traditional = LocalRuntime(conditional_execution="route_data")
                start_time = time.time()
                results_traditional, _ = runtime_traditional.execute(test_case.workflow, parameters=test_case.test_data)
                traditional_time = time.time() - start_time

                # Test conditional execution
                runtime_conditional = LocalRuntime(conditional_execution="skip_branches")
                start_time = time.time()
                results_conditional, _ = runtime_conditional.execute(test_case.workflow, parameters=test_case.test_data)
                conditional_time = time.time() - start_time

                # Validate business outcome
                traditional_outcome = self._extract_business_outcome(results_traditional)
                conditional_outcome = self._extract_business_outcome(results_conditional)

                if traditional_outcome == conditional_outcome == test_case.expected_business_outcome:
                    results['passed'] += 1

                    # Calculate performance improvement
                    improvement = (traditional_time - conditional_time) / traditional_time * 100
                    results['performance_improvements'].append({
                        'test': test_case.name,
                        'improvement_percent': improvement,
                        'traditional_nodes': len(results_traditional),
                        'conditional_nodes': len(results_conditional)
                    })
                else:
                    results['failed'] += 1
                    results['issues'].append({
                        'test': test_case.name,
                        'issue': 'Business outcome mismatch',
                        'expected': test_case.expected_business_outcome,
                        'traditional': traditional_outcome,
                        'conditional': conditional_outcome
                    })

            except Exception as e:
                results['failed'] += 1
                results['issues'].append({
                    'test': test_case.name,
                    'issue': 'Execution error',
                    'error': str(e)
                })

        return results

    def _extract_business_outcome(self, execution_results: Dict[str, Any]) -> Any:
        """Extract business-relevant outcome from execution results."""
        # Implement your business logic here
        # Focus on final outputs, ignore intermediate None values
        final_nodes = [k for k in execution_results.keys() if 'final' in k or 'result' in k]
        if final_nodes:
            return execution_results[final_nodes[-1]]
        return execution_results

# Usage example
validator = ConditionalMigrationValidator()

# Add your test cases
validator.add_test_case(
    "premium_user_workflow",
    premium_workflow,
    {"user_type": "premium", "region": "US"},
    {"discount": 30, "features": ["all"]}
)

validator.add_test_case(
    "basic_user_workflow",
    basic_workflow,
    {"user_type": "basic", "region": "US"},
    {"discount": 5, "features": ["basic"]}
)

# Run validation
validation_results = validator.validate_migration()
print(f"Tests passed: {validation_results['passed']}/{validation_results['total_tests']}")
print(f"Average performance improvement: {sum(p['improvement_percent'] for p in validation_results['performance_improvements']) / len(validation_results['performance_improvements']):.1f}%")
```

#### 3.2: Edge Case Testing

```python
def test_edge_cases():
    """Test edge cases that commonly cause migration issues."""

    edge_cases = [
        {
            'name': 'all_false_conditions',
            'data': {'user_type': 'guest', 'region': 'unknown'},
            'description': 'All conditions evaluate to false'
        },
        {
            'name': 'missing_condition_fields',
            'data': {'other_field': 'value'},
            'description': 'Condition fields missing from input data'
        },
        {
            'name': 'null_condition_values',
            'data': {'user_type': None, 'region': 'US'},
            'description': 'Null values in condition fields'
        },
        {
            'name': 'empty_input_data',
            'data': {},
            'description': 'Empty input data'
        }
    ]

    for case in edge_cases:
        print(f"\nTesting: {case['description']}")

        try:
            # Traditional execution
            runtime_traditional = LocalRuntime(conditional_execution="route_data")
            results_traditional, _ = runtime_traditional.execute(workflow, parameters=case['data'])

            # Conditional execution
            runtime_conditional = LocalRuntime(conditional_execution="skip_branches")
            results_conditional, _ = runtime_conditional.execute(workflow, parameters=case['data'])

            print(f"✅ {case['name']}: Both modes handled gracefully")
            print(f"   Traditional: {len(results_traditional)} nodes")
            print(f"   Conditional: {len(results_conditional)} nodes")

        except Exception as e:
            print(f"❌ {case['name']}: Error - {e}")

test_edge_cases()
```

### Phase 4: Production Deployment

#### 4.1: Gradual Rollout Strategy

```python
import random
from enum import Enum

class ExecutionMode(Enum):
    TRADITIONAL = "route_data"
    CONDITIONAL = "skip_branches"

class ConditionalExecutionRollout:
    """Manages gradual rollout of conditional execution."""

    def __init__(self, rollout_percentage: float = 0.0):
        self.rollout_percentage = rollout_percentage

    def should_use_conditional_execution(self, user_id: str = None) -> bool:
        """Determine if request should use conditional execution."""
        if user_id:
            # Consistent assignment based on user ID
            hash_value = hash(user_id) % 100
            return hash_value < self.rollout_percentage
        else:
            # Random assignment
            return random.random() * 100 < self.rollout_percentage

    def get_runtime(self, user_id: str = None) -> LocalRuntime:
        """Get appropriate runtime based on rollout strategy."""
        mode = ExecutionMode.CONDITIONAL if self.should_use_conditional_execution(user_id) else ExecutionMode.TRADITIONAL

        return LocalRuntime(
            conditional_execution=mode.value,
            enable_monitoring=True,  # Always monitor during rollout
            debug=mode == ExecutionMode.CONDITIONAL  # Debug conditional execution
        )

# Week 1: 5% rollout
rollout = ConditionalExecutionRollout(rollout_percentage=5.0)

# Week 2: 15% rollout
# rollout = ConditionalExecutionRollout(rollout_percentage=15.0)

# Week 3: 50% rollout
# rollout = ConditionalExecutionRollout(rollout_percentage=50.0)

# Week 4: 100% rollout
# rollout = ConditionalExecutionRollout(rollout_percentage=100.0)

# Usage in your application
def process_workflow(workflow, parameters, user_id=None):
    runtime = rollout.get_runtime(user_id)

    try:
        results, run_id = runtime.execute(workflow, parameters=parameters)

        # Collect metrics
        analytics = runtime.get_execution_analytics()
        log_execution_metrics(analytics, runtime.conditional_execution)

        return results

    except Exception as e:
        # Log error with execution mode context
        log_error(f"Execution failed with mode {runtime.conditional_execution}: {e}")

        # Fallback to traditional execution
        if runtime.conditional_execution == "skip_branches":
            fallback_runtime = LocalRuntime(conditional_execution="route_data")
            return fallback_runtime.execute(workflow, parameters=parameters)
        raise

def log_execution_metrics(analytics, mode):
    """Log execution metrics for monitoring."""
    print(f"Mode: {mode}")
    print(f"Performance improvement: {analytics.get('conditional_execution_stats', {}).get('average_performance_improvement', 0):.2%}")
    print(f"Fallback rate: {analytics.get('conditional_execution_stats', {}).get('fallback_rate', 0):.2%}")
```

#### 4.2: Monitoring and Alerting

```python
from dataclasses import dataclass
from typing import Optional
import time

@dataclass
class ExecutionMetrics:
    mode: str
    execution_time: float
    node_count: int
    success: bool
    error: Optional[str] = None
    performance_improvement: float = 0.0

class ConditionalExecutionMonitor:
    """Monitor conditional execution performance and health."""

    def __init__(self):
        self.metrics = []
        self.alerts = []

    def record_execution(self, metrics: ExecutionMetrics):
        """Record execution metrics."""
        self.metrics.append(metrics)
        self._check_alerts(metrics)

    def _check_alerts(self, metrics: ExecutionMetrics):
        """Check for alert conditions."""

        # Alert: Performance regression
        if metrics.mode == "skip_branches" and metrics.performance_improvement < 0:
            self.alerts.append({
                'type': 'performance_regression',
                'message': f'Conditional execution slower than traditional: {metrics.performance_improvement:.1%}',
                'timestamp': time.time()
            })

        # Alert: High error rate
        recent_executions = self.metrics[-100:]  # Last 100 executions
        conditional_executions = [m for m in recent_executions if m.mode == "skip_branches"]

        if len(conditional_executions) >= 10:
            error_rate = sum(1 for m in conditional_executions if not m.success) / len(conditional_executions)
            if error_rate > 0.05:  # 5% error rate threshold
                self.alerts.append({
                    'type': 'high_error_rate',
                    'message': f'Conditional execution error rate: {error_rate:.1%}',
                    'timestamp': time.time()
                })

    def get_health_report(self) -> Dict[str, Any]:
        """Generate health report."""
        if not self.metrics:
            return {'status': 'no_data'}

        recent_metrics = self.metrics[-1000:]  # Last 1000 executions

        traditional_metrics = [m for m in recent_metrics if m.mode == "route_data"]
        conditional_metrics = [m for m in recent_metrics if m.mode == "skip_branches"]

        report = {
            'total_executions': len(recent_metrics),
            'traditional_executions': len(traditional_metrics),
            'conditional_executions': len(conditional_metrics),
            'recent_alerts': len([a for a in self.alerts if time.time() - a['timestamp'] < 3600]),  # Last hour
        }

        if conditional_metrics:
            avg_improvement = sum(m.performance_improvement for m in conditional_metrics) / len(conditional_metrics)
            success_rate = sum(1 for m in conditional_metrics if m.success) / len(conditional_metrics)

            report.update({
                'conditional_success_rate': success_rate,
                'average_performance_improvement': avg_improvement,
                'status': 'healthy' if success_rate > 0.95 and avg_improvement > 0.15 else 'warning'
            })

        return report

# Usage
monitor = ConditionalExecutionMonitor()

def monitored_execution(workflow, parameters, user_id=None):
    """Execute workflow with monitoring."""
    rollout = ConditionalExecutionRollout(rollout_percentage=25.0)
    runtime = rollout.get_runtime(user_id)

    start_time = time.time()
    try:
        results, run_id = runtime.execute(workflow, parameters=parameters)
        execution_time = time.time() - start_time

        # Calculate performance improvement (simplified)
        performance_improvement = 0.3 if runtime.conditional_execution == "skip_branches" else 0.0

        monitor.record_execution(ExecutionMetrics(
            mode=runtime.conditional_execution,
            execution_time=execution_time,
            node_count=len(results),
            success=True,
            performance_improvement=performance_improvement
        ))

        return results

    except Exception as e:
        execution_time = time.time() - start_time

        monitor.record_execution(ExecutionMetrics(
            mode=runtime.conditional_execution,
            execution_time=execution_time,
            node_count=0,
            success=False,
            error=str(e)
        ))

        raise

# Regular health checks
def check_migration_health():
    """Regular health check for conditional execution migration."""
    health_report = monitor.get_health_report()

    if health_report['status'] == 'warning':
        print("⚠️ Warning: Conditional execution health issues detected")
        print(f"Success rate: {health_report.get('conditional_success_rate', 0):.1%}")
        print(f"Performance improvement: {health_report.get('average_performance_improvement', 0):.1%}")

        # Consider rolling back or reducing rollout percentage

    elif health_report['status'] == 'healthy':
        print("✅ Conditional execution performing well")
        print(f"Success rate: {health_report.get('conditional_success_rate', 0):.1%}")
        print(f"Performance improvement: {health_report.get('average_performance_improvement', 0):.1%}")
```

### Phase 5: Optimization and Best Practices

#### 5.1: Workflow Optimization for Conditional Execution

```python
def optimize_workflow_for_conditional_execution(workflow):
    """Optimize workflow structure for better conditional execution performance."""

    optimization_tips = []

    # Tip 1: Move SwitchNodes early in execution order
    switches = []
    other_nodes = []

    for node_id, node_data in workflow.graph.nodes(data=True):
        node_instance = node_data.get('node') or node_data.get('instance')
        if hasattr(node_instance, '__class__') and 'Switch' in node_instance.__class__.__name__:
            switches.append(node_id)
        else:
            other_nodes.append(node_id)

    if switches:
        optimization_tips.append(f"Found {len(switches)} SwitchNodes - ensure they execute early")

    # Tip 2: Identify expensive nodes that could be optimized
    expensive_nodes = []
    for node_id, node_data in workflow.graph.nodes(data=True):
        node_instance = node_data.get('node') or node_data.get('instance')

        # Heuristics for expensive operations
        if hasattr(node_instance, 'code') and any(keyword in str(node_instance.code) for keyword in ['api', 'database', 'http', 'file']):
            expensive_nodes.append(node_id)

    if expensive_nodes:
        optimization_tips.append(f"Found {len(expensive_nodes)} potentially expensive nodes: {expensive_nodes}")
        optimization_tips.append("Consider placing these behind conditional logic")

    # Tip 3: Check for merge node opportunities
    merge_candidates = []
    for node_id in other_nodes:
        predecessors = list(workflow.graph.predecessors(node_id))
        if len(predecessors) > 1:
            merge_candidates.append((node_id, len(predecessors)))

    if merge_candidates:
        optimization_tips.append(f"Nodes with multiple inputs (merge candidates): {merge_candidates}")
        optimization_tips.append("Consider using MergeNode with skip_none=True for conditional inputs")

    return optimization_tips

# Usage
optimization_tips = optimize_workflow_for_conditional_execution(your_workflow)
for tip in optimization_tips:
    print(f"💡 {tip}")
```

#### 5.2: Performance Benchmarking

```python
import statistics
from typing import List

def comprehensive_performance_benchmark(workflow, test_datasets: List[Dict[str, Any]], iterations: int = 10):
    """Comprehensive performance comparison between execution modes."""

    results = {
        'traditional': {'times': [], 'node_counts': []},
        'conditional': {'times': [], 'node_counts': []},
        'datasets': []
    }

    for dataset_idx, test_data in enumerate(test_datasets):
        print(f"\nBenchmarking dataset {dataset_idx + 1}/{len(test_datasets)}")

        dataset_results = {'traditional': [], 'conditional': []}

        for iteration in range(iterations):
            # Traditional execution
            runtime_traditional = LocalRuntime(conditional_execution="route_data")
            start_time = time.time()
            results_traditional, _ = runtime_traditional.execute(workflow, parameters=test_data)
            traditional_time = time.time() - start_time

            # Conditional execution
            runtime_conditional = LocalRuntime(conditional_execution="skip_branches")
            start_time = time.time()
            results_conditional, _ = runtime_conditional.execute(workflow, parameters=test_data)
            conditional_time = time.time() - start_time

            dataset_results['traditional'].append((traditional_time, len(results_traditional)))
            dataset_results['conditional'].append((conditional_time, len(results_conditional)))

        # Calculate statistics for this dataset
        trad_times = [r[0] for r in dataset_results['traditional']]
        trad_nodes = [r[1] for r in dataset_results['traditional']]
        cond_times = [r[0] for r in dataset_results['conditional']]
        cond_nodes = [r[1] for r in dataset_results['conditional']]

        dataset_summary = {
            'dataset_idx': dataset_idx,
            'traditional_avg_time': statistics.mean(trad_times),
            'traditional_std_time': statistics.stdev(trad_times) if len(trad_times) > 1 else 0,
            'traditional_avg_nodes': statistics.mean(trad_nodes),
            'conditional_avg_time': statistics.mean(cond_times),
            'conditional_std_time': statistics.stdev(cond_times) if len(cond_times) > 1 else 0,
            'conditional_avg_nodes': statistics.mean(cond_nodes),
        }

        # Calculate improvements
        dataset_summary['time_improvement'] = (dataset_summary['traditional_avg_time'] - dataset_summary['conditional_avg_time']) / dataset_summary['traditional_avg_time'] * 100
        dataset_summary['node_reduction'] = (dataset_summary['traditional_avg_nodes'] - dataset_summary['conditional_avg_nodes']) / dataset_summary['traditional_avg_nodes'] * 100

        results['datasets'].append(dataset_summary)

        print(f"  Time improvement: {dataset_summary['time_improvement']:.1f}%")
        print(f"  Node reduction: {dataset_summary['node_reduction']:.1f}%")

        # Add to overall results
        results['traditional']['times'].extend(trad_times)
        results['traditional']['node_counts'].extend(trad_nodes)
        results['conditional']['times'].extend(cond_times)
        results['conditional']['node_counts'].extend(cond_nodes)

    # Overall statistics
    overall_time_improvement = (statistics.mean(results['traditional']['times']) - statistics.mean(results['conditional']['times'])) / statistics.mean(results['traditional']['times']) * 100
    overall_node_reduction = (statistics.mean(results['traditional']['node_counts']) - statistics.mean(results['conditional']['node_counts'])) / statistics.mean(results['traditional']['node_counts']) * 100

    results['overall'] = {
        'time_improvement': overall_time_improvement,
        'node_reduction': overall_node_reduction,
        'statistical_significance': len(results['traditional']['times']) >= 30  # Basic check
    }

    return results

# Usage
test_datasets = [
    {"user_type": "premium", "region": "US", "status": "active"},
    {"user_type": "basic", "region": "US", "status": "active"},
    {"user_type": "premium", "region": "EU", "status": "active"},
    {"user_type": "basic", "region": "EU", "status": "inactive"},
]

benchmark_results = comprehensive_performance_benchmark(your_workflow, test_datasets)
print(f"\n🎯 Overall Performance Improvement: {benchmark_results['overall']['time_improvement']:.1f}%")
print(f"🎯 Overall Node Reduction: {benchmark_results['overall']['node_reduction']:.1f}%")

if benchmark_results['overall']['time_improvement'] >= 20:
    print("✅ Excellent performance improvement - proceed with migration")
elif benchmark_results['overall']['time_improvement'] >= 10:
    print("✅ Good performance improvement - migration recommended")
else:
    print("⚠️ Limited performance improvement - review workflow structure")
```

## Common Migration Issues and Solutions

### Issue 1: Unexpected Results

**Problem**: Different outputs between execution modes

**Root Cause**: Logic that depends on `None` values from skipped branches

**Solution**:
```python
# ❌ Problematic pattern
workflow.add_node("PythonCodeNode", "problematic", {
    "code": """
# This assumes None values from conditional branches
if premium_data is None:
    result = default_processing(basic_data)
else:
    result = premium_processing(premium_data)
"""
})

# ✅ Fixed pattern
workflow.add_node("SwitchNode", "explicit_switch", {
    "condition_field": "user_type",
    "operator": "==",
    "value": "premium"
})

workflow.add_node("PythonCodeNode", "premium_path", {
    "code": "result = premium_processing(input_data)"
})

workflow.add_node("PythonCodeNode", "basic_path", {
    "code": "result = default_processing(input_data)"
})
```

### Issue 2: Performance Regression

**Problem**: Conditional execution slower than traditional

**Root Cause**: Analysis overhead exceeds benefit for simple workflows

**Solution**:
```python
# Check workflow complexity before enabling conditional execution
def should_use_conditional_execution(workflow) -> bool:
    node_count = len(workflow.graph.nodes)
    switch_count = len([n for n in workflow.graph.nodes(data=True)
                       if 'Switch' in str(type(n[1].get('node', '')))])

    # Only beneficial for workflows with multiple switches or many nodes
    return switch_count >= 2 or (switch_count >= 1 and node_count >= 5)

if should_use_conditional_execution(workflow):
    runtime = LocalRuntime(conditional_execution="skip_branches")
else:
    runtime = LocalRuntime(conditional_execution="route_data")
```

### Issue 3: Merge Node Issues

**Problem**: MergeNode expecting inputs that are now skipped

**Solution**:
```python
# Configure MergeNode to handle partial inputs
workflow.add_node("MergeNode", "intelligent_merge", {
    "merge_type": "merge_dict",
    "skip_none": True,        # Skip None inputs
    "require_all": False,     # Don't require all inputs
    "default_values": {       # Provide defaults for missing inputs
        "data1": {},
        "data2": {},
        "data3": {}
    }
})
```

## Success Criteria

### Migration is successful when:

1. **Performance**: 20-50% improvement in execution time
2. **Correctness**: Business outcomes identical between modes
3. **Stability**: <5% error rate increase
4. **Monitoring**: Clear visibility into performance and health

### Rollback triggers:

1. Performance regression (conditional slower than traditional)
2. Error rate increase >10%
3. Business outcome differences detected
4. Resource usage increase >20%

## Next Steps

1. **Identify** workflows with conditional logic
2. **Measure** baseline performance
3. **Test** migration with validation framework
4. **Deploy** with gradual rollout
5. **Monitor** performance and health
6. **Optimize** workflow structure for maximum benefit

## Related Documentation

- [Conditional Execution Guide](../2-core-concepts/conditional-execution-guide.md) - Complete feature documentation
- [Performance Optimization](./performance-optimization.md) - General performance tuning
- [Error Handling](./error-handling.md) - Handling migration issues
- [Monitoring and Observability](./monitoring-observability.md) - Production monitoring
