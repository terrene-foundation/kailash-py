#!/usr/bin/env python3
"""
Quick performance benchmark for parameter validation features.
Focused on measuring overhead with minimal test iterations.
"""
import sys
import os
import time
import statistics

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.base import Node, NodeParameter, NodeRegistry
from kailash.runtime.parameter_debugger import ParameterDebugger

# Ensure clean registry
NodeRegistry._nodes.clear()

class QuickBenchmarkNode(Node):
    """Simple node for performance testing."""
    
    def get_parameters(self):
        return {
            "param1": NodeParameter(name="param1", type=str, required=False),
            "param2": NodeParameter(name="param2", type=int, required=False),
            "param3": NodeParameter(name="param3", type=dict, required=False),
        }
    
    def run(self, **kwargs):
        return {"result": len(kwargs)}

NodeRegistry.register(QuickBenchmarkNode, "QuickBenchmarkNode")

def quick_benchmark():
    """Run focused performance benchmark."""
    print("⚡ QUICK PARAMETER VALIDATION PERFORMANCE TEST")
    print("=" * 55)
    
    # Create simple test workflow
    workflow = WorkflowBuilder()
    workflow.add_node("QuickBenchmarkNode", "node1", {})
    workflow.add_node("QuickBenchmarkNode", "node2", {})
    workflow.add_connection("node1", "result", "node2", "param2")
    
    # Test parameters
    parameters = {
        "node1": {"param1": "test", "param3": {"nested": "data"}},
        "node2": {"param1": "test2"},
        "global_param": "workflow_level"
    }
    
    built_workflow = workflow.build()
    
    # Test different validation modes
    modes = ["off", "warn", "strict"]
    iterations = 10  # Reduced for speed
    
    results = {}
    
    for mode in modes:
        print(f"\n📊 Testing {mode.upper()} mode...")
        
        runtime = LocalRuntime(
            debug=False,
            parameter_validation=mode,
            enable_parameter_debugging=False
        )
        
        # Warmup
        for _ in range(2):
            try:
                runtime.execute(built_workflow, parameters=parameters)
            except:
                pass
        
        # Benchmark
        times = []
        successes = 0
        
        for _ in range(iterations):
            start = time.perf_counter()
            try:
                results_data, run_id = runtime.execute(built_workflow, parameters=parameters)
                successes += 1
            except Exception as e:
                pass  # Count failures
            end = time.perf_counter()
            times.append(end - start)
        
        if times:
            avg_time = statistics.mean(times)
            success_rate = successes / iterations
            
            results[mode] = {
                "avg_time": avg_time,
                "success_rate": success_rate,
                "times": times
            }
            
            print(f"   Average time: {avg_time:.4f}s")
            print(f"   Success rate: {success_rate:.1%}")
        else:
            print("   No successful runs")
            results[mode] = {"avg_time": 0, "success_rate": 0}
    
    # Parameter debugging benchmark
    print(f"\n🔍 Testing Parameter Debugging Performance...")
    debugger = ParameterDebugger()
    
    debug_times = []
    for _ in range(5):  # Reduced iterations
        start = time.perf_counter()
        report = debugger.trace_parameter_flow(
            workflow=built_workflow,
            runtime_parameters=parameters,
            node_configs={"node1": {}, "node2": {}}
        )
        end = time.perf_counter()
        debug_times.append(end - start)
    
    debug_avg = statistics.mean(debug_times) if debug_times else 0
    print(f"   Debug analysis time: {debug_avg:.4f}s")
    
    # Analysis
    print(f"\n📈 PERFORMANCE ANALYSIS")
    print("-" * 25)
    
    if "off" in results and "strict" in results:
        baseline = results["off"]["avg_time"]
        strict_time = results["strict"]["avg_time"]
        
        if baseline > 0:
            overhead = ((strict_time - baseline) / baseline) * 100
            overhead_ms = (strict_time - baseline) * 1000
            
            print(f"Baseline (off):    {baseline:.4f}s")
            print(f"Strict mode:       {strict_time:.4f}s")
            print(f"Overhead:          +{overhead:.1f}% (+{overhead_ms:.2f}ms)")
            
            if overhead < 10:
                print("✅ Minimal performance impact - safe for production")
            elif overhead < 25:
                print("📍 Moderate overhead - acceptable for development")
            else:
                print("⚠️  Significant overhead - use selectively")
        
    print(f"Debug overhead:    {debug_avg*1000:.1f}ms (use sparingly)")
    
    return results

if __name__ == "__main__":
    try:
        results = quick_benchmark()
        print("\n🎉 Quick benchmark completed!")
        
    except Exception as e:
        print(f"❌ Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)