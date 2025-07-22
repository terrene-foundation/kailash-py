#!/usr/bin/env python3
"""
Performance benchmark for parameter validation and debugging features.

This script benchmarks the performance impact of enhanced parameter validation
to ensure no significant regressions were introduced.
"""
import sys
import os
import time
import statistics
from typing import Dict, List, Any
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.base import Node, NodeParameter, NodeRegistry
from kailash.runtime.parameter_debugger import ParameterDebugger

# Ensure clean registry
NodeRegistry._nodes.clear()

# Benchmark test node
class BenchmarkNode(Node):
    """Simple node for performance benchmarking."""
    
    def get_parameters(self):
        return {
            "param1": NodeParameter(name="param1", type=str, required=False),
            "param2": NodeParameter(name="param2", type=int, required=False),
            "param3": NodeParameter(name="param3", type=dict, required=False),
            "param4": NodeParameter(name="param4", type=list, required=False),
            "param5": NodeParameter(name="param5", type=str, required=False),
        }
    
    def run(self, **kwargs):
        return {"processed": len(kwargs), "params": list(kwargs.keys())}

# Register benchmark node
NodeRegistry.register(BenchmarkNode, "BenchmarkNode")

def create_benchmark_workflow(num_nodes: int = 5) -> WorkflowBuilder:
    """Create a workflow with specified number of nodes for benchmarking."""
    workflow = WorkflowBuilder()
    
    for i in range(num_nodes):
        node_id = f"node_{i}"
        workflow.add_node("BenchmarkNode", node_id, {})
        
        # Add connections between nodes
        if i > 0:
            prev_node = f"node_{i-1}"
            workflow.add_connection(prev_node, "processed", node_id, "param1")
    
    return workflow

def create_benchmark_parameters(num_nodes: int = 5, params_per_node: int = 5) -> Dict[str, Any]:
    """Create runtime parameters for benchmarking."""
    parameters = {}
    
    # Node-specific parameters
    for i in range(num_nodes):
        node_id = f"node_{i}"
        parameters[node_id] = {}
        for j in range(params_per_node):
            param_name = f"param{j+1}"
            if j == 0:
                parameters[node_id][param_name] = f"value_{i}_{j}"
            elif j == 1:
                parameters[node_id][param_name] = i * j + 10
            elif j == 2:
                parameters[node_id][param_name] = {"nested": f"dict_{i}_{j}"}
            elif j == 3:
                parameters[node_id][param_name] = [f"item_{i}_{j}", i, j]
            else:
                parameters[node_id][param_name] = f"extra_{i}_{j}"
    
    # Workflow-level parameters
    parameters["global_param"] = "global_value"
    parameters["shared_config"] = {"shared": True, "version": 1}
    
    return parameters

def benchmark_execution(
    validation_mode: str, 
    num_nodes: int = 5, 
    num_iterations: int = 100,
    enable_debugging: bool = False
) -> Dict[str, float]:
    """Benchmark workflow execution with specified validation mode."""
    
    workflow = create_benchmark_workflow(num_nodes)
    parameters = create_benchmark_parameters(num_nodes)
    
    runtime = LocalRuntime(
        debug=False,  # Disable debug output for cleaner benchmarks
        parameter_validation=validation_mode,
        enable_parameter_debugging=enable_debugging
    )
    
    built_workflow = workflow.build()
    
    # Warmup runs
    for _ in range(5):
        try:
            runtime.execute(built_workflow, parameters=parameters)
        except Exception:
            pass  # Ignore errors during warmup
    
    # Benchmark runs
    execution_times = []
    successful_runs = 0
    
    for i in range(num_iterations):
        start_time = time.perf_counter()
        try:
            results, run_id = runtime.execute(built_workflow, parameters=parameters)
            success = True
        except Exception as e:
            success = False
            
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        
        if success:
            execution_times.append(execution_time)
            successful_runs += 1
    
    if not execution_times:
        return {
            "mean": 0,
            "median": 0,
            "min": 0,
            "max": 0,
            "std_dev": 0,
            "success_rate": 0,
            "total_runs": num_iterations
        }
    
    return {
        "mean": statistics.mean(execution_times),
        "median": statistics.median(execution_times),
        "min": min(execution_times),
        "max": max(execution_times),
        "std_dev": statistics.stdev(execution_times) if len(execution_times) > 1 else 0,
        "success_rate": successful_runs / num_iterations,
        "total_runs": num_iterations,
        "successful_runs": successful_runs
    }

def benchmark_parameter_debugging(
    workflow_sizes: List[int] = [5, 10, 20],
    num_iterations: int = 50
) -> Dict[str, Any]:
    """Benchmark parameter debugging performance."""
    
    debugger = ParameterDebugger()
    debug_times = {}
    
    for num_nodes in workflow_sizes:
        workflow = create_benchmark_workflow(num_nodes)
        parameters = create_benchmark_parameters(num_nodes)
        built_workflow = workflow.build()
        
        node_configs = {
            f"node_{i}": {"config_param": f"config_value_{i}"}
            for i in range(num_nodes)
        }
        
        times = []
        
        for _ in range(num_iterations):
            start_time = time.perf_counter()
            
            report = debugger.trace_parameter_flow(
                workflow=built_workflow,
                runtime_parameters=parameters,
                node_configs=node_configs
            )
            
            end_time = time.perf_counter()
            times.append(end_time - start_time)
        
        debug_times[f"{num_nodes}_nodes"] = {
            "mean": statistics.mean(times),
            "median": statistics.median(times),
            "min": min(times),
            "max": max(times),
            "std_dev": statistics.stdev(times) if len(times) > 1 else 0
        }
    
    return debug_times

def run_comprehensive_benchmark():
    """Run comprehensive performance benchmarks."""
    
    print("🚀 PARAMETER VALIDATION PERFORMANCE BENCHMARK")
    print("=" * 60)
    print()
    
    # Test configurations
    validation_modes = ["off", "warn", "strict", "debug"]
    workflow_sizes = [5, 10, 20]
    iterations = 100
    
    results = {
        "benchmark_config": {
            "validation_modes": validation_modes,
            "workflow_sizes": workflow_sizes,
            "iterations_per_test": iterations,
            "timestamp": time.time()
        },
        "execution_benchmarks": {},
        "debugging_benchmarks": {},
        "performance_analysis": {}
    }
    
    # Execution benchmarks
    print("📊 EXECUTION PERFORMANCE BY VALIDATION MODE")
    print("-" * 50)
    
    baseline_times = {}
    
    for mode in validation_modes:
        mode_results = {}
        
        for size in workflow_sizes:
            print(f"Testing {mode} mode with {size} nodes... ", end="", flush=True)
            
            benchmark_result = benchmark_execution(
                validation_mode=mode,
                num_nodes=size,
                num_iterations=iterations,
                enable_debugging=(mode == "debug")
            )
            
            mode_results[f"{size}_nodes"] = benchmark_result
            
            mean_time = benchmark_result["mean"]
            success_rate = benchmark_result["success_rate"]
            
            print(f"✅ {mean_time:.4f}s avg ({success_rate:.1%} success)")
            
            # Track baseline (off mode) for comparison
            if mode == "off":
                baseline_times[size] = mean_time
        
        results["execution_benchmarks"][mode] = mode_results
        print()
    
    # Parameter debugging benchmarks
    print("🔍 PARAMETER DEBUGGING PERFORMANCE")
    print("-" * 40)
    
    debug_results = benchmark_parameter_debugging(workflow_sizes, iterations)
    results["debugging_benchmarks"] = debug_results
    
    for size_key, metrics in debug_results.items():
        print(f"Debug analysis for {size_key}: {metrics['mean']:.4f}s avg")
    
    print()
    
    # Performance analysis
    print("📈 PERFORMANCE ANALYSIS")
    print("-" * 30)
    
    analysis = {}
    
    # Calculate overhead percentages
    for mode in ["warn", "strict", "debug"]:
        mode_overhead = {}
        
        for size in workflow_sizes:
            baseline = baseline_times.get(size, 0)
            current = results["execution_benchmarks"][mode][f"{size}_nodes"]["mean"]
            
            if baseline > 0:
                overhead_pct = ((current - baseline) / baseline) * 100
                mode_overhead[f"{size}_nodes"] = {
                    "baseline_time": baseline,
                    "current_time": current,
                    "overhead_ms": (current - baseline) * 1000,
                    "overhead_percent": overhead_pct
                }
                
                print(f"{mode.upper()} mode ({size} nodes): +{overhead_pct:.1f}% (+{(current - baseline)*1000:.2f}ms)")
        
        analysis[f"{mode}_overhead"] = mode_overhead
    
    results["performance_analysis"] = analysis
    
    print()
    print("💡 PERFORMANCE RECOMMENDATIONS")
    print("-" * 35)
    
    # Generate recommendations
    recommendations = []
    
    # Check for significant overhead
    for mode in ["warn", "strict", "debug"]:
        for size in workflow_sizes:
            overhead_data = analysis.get(f"{mode}_overhead", {}).get(f"{size}_nodes", {})
            overhead_pct = overhead_data.get("overhead_percent", 0)
            
            if overhead_pct > 50:  # More than 50% overhead
                recommendations.append(
                    f"⚠️  {mode.upper()} mode shows {overhead_pct:.1f}% overhead with {size} nodes - consider using 'warn' mode in production"
                )
            elif overhead_pct > 20:  # 20-50% overhead
                recommendations.append(
                    f"📍 {mode.upper()} mode shows {overhead_pct:.1f}% overhead with {size} nodes - acceptable for development/debugging"
                )
            elif overhead_pct < 10:  # Less than 10% overhead
                recommendations.append(
                    f"✅ {mode.upper()} mode shows minimal {overhead_pct:.1f}% overhead with {size} nodes - safe for production use"
                )
    
    # Debug analysis overhead
    debug_times_20_nodes = debug_results.get("20_nodes", {}).get("mean", 0)
    if debug_times_20_nodes > 0.1:  # More than 100ms
        recommendations.append(
            f"🔍 Parameter debugging takes {debug_times_20_nodes*1000:.1f}ms for 20 nodes - use sparingly in production"
        )
    else:
        recommendations.append(
            f"🔍 Parameter debugging is fast ({debug_times_20_nodes*1000:.1f}ms for 20 nodes) - safe for development use"
        )
    
    for rec in recommendations:
        print(rec)
    
    # Save detailed results
    results_file = "parameter_validation_benchmark_results.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print()
    print(f"📄 Detailed results saved to: {results_file}")
    
    return results

if __name__ == "__main__":
    try:
        results = run_comprehensive_benchmark()
        print()
        print("🎉 Benchmark completed successfully!")
        
        # Quick summary
        baseline = results["execution_benchmarks"]["off"]["5_nodes"]["mean"]
        strict = results["execution_benchmarks"]["strict"]["5_nodes"]["mean"]
        overhead = ((strict - baseline) / baseline) * 100 if baseline > 0 else 0
        
        print(f"📊 Quick Summary (5 nodes):")
        print(f"   Baseline (off): {baseline:.4f}s")
        print(f"   Strict mode: {strict:.4f}s (+{overhead:.1f}%)")
        
    except Exception as e:
        print(f"❌ Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)