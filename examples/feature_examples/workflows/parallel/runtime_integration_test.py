#!/usr/bin/env python3
"""
Enhanced Runtime Integration Examples

This module demonstrates the enhanced runtime capabilities for the Kailash SDK,
showcasing automatic cycle detection, parallel execution, and performance comparisons.

Examples:
1. LocalRuntime with automatic cycle detection
2. ParallelCyclicRuntime for concurrent execution
3. Performance benchmarking across different runtimes
4. Runtime configuration and customization options
5. Mixed workflow execution (DAG + Cycles)

Key Features Demonstrated:
- Automatic workflow type detection (DAG vs Cyclic)
- Parallel execution of independent node groups
- Runtime performance metrics and comparison
- Flexible runtime configuration options
- Seamless integration with existing tracking systems
"""

import time

from examples.utils.data_paths import get_input_data_path, get_output_data_path
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.data.writers import CSVWriterNode
from kailash.nodes.transform.processors import FilterNode
from kailash.runtime.local import LocalRuntime
from kailash.runtime.parallel_cyclic import ParallelCyclicRuntime
from kailash.tracking.manager import TaskManager
from kailash.workflow.graph import Workflow


def increment(data=None, **kwargs):
    """Auto-converted from PythonCodeNode string code."""
    # PythonCodeNode passes connected inputs into namespace
    # When connected via {"result": "data"}, the input comes as 'data'
    try:
        counter = data.get("counter", 0)
        sum = data.get("sum", 0)
    except:
        counter = 0
        sum = 0

    new_counter = counter + 1
    new_sum = sum + new_counter
    print(f"Iteration {new_counter}: sum = {new_sum}")
    should_continue = new_counter < 5

    result = {
        "counter": new_counter,
        "sum": new_sum,
        "should_continue": should_continue,
    }

    return result


def output(data=None, **kwargs):
    """Auto-converted from PythonCodeNode string code."""
    # PythonCodeNode passes connected inputs into namespace
    try:
        counter = data.get("counter", 0)
        sum = data.get("sum", 0)
    except:
        counter = 0
        sum = 0

    print(f"Final result: counter={counter}, sum={sum}")
    result = {"final_counter": counter, "final_sum": sum}

    return result


def process_1(input_data: dict, **kwargs):
    """Auto-converted from PythonCodeNode string code."""
    import time

    time.sleep(0.05)  # Simulate work
    # When connected via {"result": "data"}, input is 'data'
    data = kwargs.get("data", {})
    input_data = data.get("data", []) if isinstance(data, dict) else []
    processed = [x * 2 for x in input_data[:50]] if input_data else []
    result = {"processed": processed, "branch": "1"}

    return result


def process_2(input_data: dict, **kwargs):
    """Auto-converted from PythonCodeNode string code."""
    import time

    time.sleep(0.05)  # Simulate work
    # When connected via {"result": "data"}, input is 'data'
    data = kwargs.get("data", {})
    input_data = data.get("data", []) if isinstance(data, dict) else []
    processed = [x**2 for x in input_data[50:]] if input_data else []
    result = {"processed": processed, "branch": "2"}

    return result


def process_3(**kwargs):
    """Auto-converted from PythonCodeNode string code."""
    import time

    time.sleep(0.02)  # Simulate lighter work
    # When connected via {"result": "metadata"}, input is 'metadata'
    metadata = kwargs.get("metadata", {})
    input_metadata = metadata.get("metadata", {}) if isinstance(metadata, dict) else {}
    if input_metadata:
        enhanced = {**input_metadata, "processed_at": "runtime"}
    else:
        enhanced = {"processed_at": "runtime"}
    result = {"enhanced_metadata": enhanced}

    return result


def aggregate(**kwargs):
    """Auto-converted from PythonCodeNode string code."""
    combined = []
    processed_1 = kwargs.get("processed_1", {})
    processed_2 = kwargs.get("processed_2", {})
    enhanced_metadata = kwargs.get("enhanced_metadata", {})

    # Extract 'processed' from the result dict
    p1_data = processed_1.get("processed", []) if isinstance(processed_1, dict) else []
    if p1_data:
        combined.extend(p1_data)

    # Extract 'processed' from the result dict
    p2_data = processed_2.get("processed", []) if isinstance(processed_2, dict) else []
    if p2_data:
        combined.extend(p2_data)

    # Extract 'enhanced_metadata' from the result dict
    metadata_val = (
        enhanced_metadata.get("enhanced_metadata", {})
        if isinstance(enhanced_metadata, dict)
        else {}
    )

    result = {
        "combined_data": combined,
        "total_items": len(combined),
        "metadata": metadata_val,
    }

    return result


def iterate(iteration=None, **kwargs):
    """Auto-converted from PythonCodeNode string code."""
    # Access inputs from namespace - use try/except for safety
    value = kwargs.get("value", 10)
    target = kwargs.get("target", 100)
    current_value = value
    current_target = target

    # Access context for cycle info
    context = kwargs.get("context", {})
    cycle_info = context.get("cycle", {}) if isinstance(context, dict) else {}
    iteration = cycle_info.get("iteration", 0)

    # Process
    new_value = current_value * 1.2
    converged = new_value >= current_target

    result = {
        "value": new_value,
        "target": current_target,
        "converged": converged,
        "iteration": iteration,
    }

    return result


def finalize(**kwargs):
    """Auto-converted from PythonCodeNode string code."""
    # Access inputs from namespace
    value = kwargs.get("value", 0)
    target = kwargs.get("target", 100)
    final_value = value
    final_target = target

    # Calculate final results
    result = {
        "result": final_value,
        "achieved_target": final_value >= final_target,
        "overshoot": max(0, final_value - final_target),
    }

    return result


def create_simple_dag_workflow() -> Workflow:
    """Create a simple DAG workflow for testing."""
    workflow = Workflow(workflow_id="dag_test", name="DAG Test Workflow")

    # Add nodes
    workflow.add_node(
        "reader", CSVReaderNode(file_path=str(get_input_data_path("customers.csv")))
    )

    workflow.add_node("processor", FilterNode(field="age", operator=">=", value=25))

    workflow.add_node(
        "writer",
        CSVWriterNode(file_path="outputs/runtime_dag_output.csv"),
    )

    # Connect nodes
    workflow.connect("reader", "processor", {"data": "data"})
    workflow.connect("processor", "writer", {"filtered_data": "data"})

    return workflow


def create_simple_cyclic_workflow() -> Workflow:
    """Create a simple cyclic workflow for testing."""
    workflow = Workflow(workflow_id="cyclic_test", name="Cyclic Test Workflow")

    # Add nodes - using result-based output pattern
    workflow.add_node(
        "init",
        PythonCodeNode(
            name="init",
            code="""
result = {"counter": 0, "sum": 0}
""",
        ),
    )

    workflow.add_node(
        "increment",
        PythonCodeNode.from_function(func=increment, name="increment"),
    )

    workflow.add_node(
        "output",
        PythonCodeNode.from_function(func=output, name="output"),
    )

    # Connect with cycle - use result mapping
    workflow.connect("init", "increment", {"result": "data"})
    workflow.connect(
        "increment", "increment", {"result": "data"}, cycle=True, max_iterations=5
    )
    workflow.connect("increment", "output", {"result": "data"})

    return workflow


def create_parallel_dag_workflow() -> Workflow:
    """Create a DAG workflow with parallel execution opportunities."""
    workflow = Workflow(
        workflow_id="parallel_dag_test", name="Parallel DAG Test Workflow"
    )

    # Create source node - simpler version that just returns result
    workflow.add_node(
        "source",
        PythonCodeNode(
            name="source",
            code="""
data = list(range(100))
metadata = {"source": "generated"}
result = {"data": data, "metadata": metadata}
""",
        ),
    )

    # Create parallel processing branches
    workflow.add_node(
        "process_1",
        PythonCodeNode.from_function(func=process_1, name="process_1"),
    )

    workflow.add_node(
        "process_2",
        PythonCodeNode.from_function(func=process_2, name="process_2"),
    )

    workflow.add_node(
        "process_3",
        PythonCodeNode.from_function(func=process_3, name="process_3"),
    )

    # Create aggregation node
    workflow.add_node(
        "aggregate",
        PythonCodeNode.from_function(func=aggregate, name="aggregate"),
    )

    # Connect nodes (parallel opportunities exist)
    # Source node outputs 'result' with 'data' and 'metadata' keys
    workflow.connect("source", "process_1", {"result": "data"})
    workflow.connect("source", "process_2", {"result": "data"})
    workflow.connect("source", "process_3", {"result": "metadata"})
    workflow.connect("process_1", "aggregate", {"result": "processed_1"})
    workflow.connect("process_2", "aggregate", {"result": "processed_2"})
    workflow.connect("process_3", "aggregate", {"result": "enhanced_metadata"})

    return workflow


def create_mixed_workflow() -> Workflow:
    """Create a workflow with both DAG and cyclic components."""
    workflow = Workflow(workflow_id="mixed_workflow", name="Mixed Workflow")

    # DAG preparation phase
    workflow.add_node(
        "prepare",
        PythonCodeNode(
            name="prepare",
            code="""
# Direct code execution - no function definition
result = {"initial_value": 10, "target": 100}
""",
        ),
    )

    # Cyclic processing phase
    workflow.add_node(
        "iterate",
        PythonCodeNode.from_function(func=iterate, name="iterate"),
    )

    # DAG finalization phase
    workflow.add_node(
        "finalize",
        PythonCodeNode.from_function(func=finalize, name="finalize"),
    )

    # Connect DAG -> Cycle -> DAG
    workflow.connect(
        "prepare", "iterate", {"initial_value": "value", "target": "target"}
    )
    workflow.connect(
        "iterate",
        "iterate",
        {"value": "value", "target": "target"},
        cycle=True,
        convergence_check="converged == True",
        max_iterations=10,
    )
    workflow.connect("iterate", "finalize", {"value": "value", "target": "target"})

    return workflow


def benchmark_runtime_performance():
    """Benchmark different runtime approaches."""
    print("🚀 Runtime Performance Benchmark")
    print("=" * 50)

    # Create test workflows
    dag_workflow = create_parallel_dag_workflow()
    cyclic_workflow = create_simple_cyclic_workflow()
    mixed_workflow = create_mixed_workflow()

    workflows = [
        ("DAG Workflow", dag_workflow),
        ("Cyclic Workflow", cyclic_workflow),
        ("Mixed Workflow", mixed_workflow),
    ]

    # Test different runtimes
    runtimes = [
        ("LocalRuntime", LocalRuntime(debug=False)),
        ("LocalRuntime (No Cycles)", LocalRuntime(debug=False, enable_cycles=False)),
        ("ParallelCyclicRuntime", ParallelCyclicRuntime(debug=False, max_workers=4)),
        (
            "ParallelCyclicRuntime (2 Workers)",
            ParallelCyclicRuntime(debug=False, max_workers=2),
        ),
    ]

    results = {}

    for workflow_name, workflow in workflows:
        print(f"\n📊 Testing: {workflow_name}")
        print("-" * 30)

        results[workflow_name] = {}

        for runtime_name, runtime in runtimes:
            # Skip incompatible combinations
            if "No Cycles" in runtime_name and workflow.has_cycles():
                print(f"⏭️  {runtime_name}: Skipped (cycles not supported)")
                continue

            try:
                start_time = time.time()

                # Execute workflow
                if hasattr(runtime, "execute"):
                    workflow_results, run_id = runtime.execute(workflow)
                else:
                    # Fallback for older runtime interface
                    workflow_results = runtime.run(workflow)
                    run_id = "unknown"

                end_time = time.time()
                execution_time = end_time - start_time

                results[workflow_name][runtime_name] = {
                    "execution_time": execution_time,
                    "success": True,
                    "result_keys": (
                        list(workflow_results.keys()) if workflow_results else []
                    ),
                    "run_id": run_id,
                }

                print(f"✅ {runtime_name}: {execution_time:.3f}s")

            except Exception as e:
                results[workflow_name][runtime_name] = {
                    "execution_time": None,
                    "success": False,
                    "error": str(e),
                }
                print(f"❌ {runtime_name}: Failed - {e}")

    # Print summary
    print("\n📈 Performance Summary")
    print("=" * 50)

    for workflow_name, workflow_results in results.items():
        print(f"\n{workflow_name}:")
        successful_times = [
            (name, result["execution_time"])
            for name, result in workflow_results.items()
            if result["success"] and result["execution_time"] is not None
        ]

        if successful_times:
            successful_times.sort(key=lambda x: x[1])
            fastest = successful_times[0]
            print(f"  🏆 Fastest: {fastest[0]} ({fastest[1]:.3f}s)")

            for name, exec_time in successful_times[1:]:
                speedup = exec_time / fastest[1]
                print(f"     {name}: {exec_time:.3f}s ({speedup:.1f}x slower)")

    return results


def demonstrate_automatic_detection():
    """Demonstrate automatic workflow type detection."""
    print("🔍 Automatic Workflow Type Detection")
    print("=" * 40)

    # Create different workflow types
    workflows = [
        ("Simple DAG", create_simple_dag_workflow()),
        ("Simple Cyclic", create_simple_cyclic_workflow()),
        ("Mixed Workflow", create_mixed_workflow()),
    ]

    # Create runtime with cycle support
    runtime = LocalRuntime(debug=True, enable_cycles=True)

    for workflow_name, workflow in workflows:
        print(f"\n📋 Testing: {workflow_name}")
        print(f"   Has cycles: {workflow.has_cycles()}")

        try:
            start_time = time.time()
            results, run_id = runtime.execute(workflow)
            execution_time = time.time() - start_time

            print(f"   ✅ Executed successfully in {execution_time:.3f}s")
            print(f"   📊 Results: {len(results)} nodes completed")
            print(f"   🆔 Run ID: {run_id}")

        except Exception as e:
            print(f"   ❌ Execution failed: {e}")


def demonstrate_parallel_execution():
    """Demonstrate parallel execution capabilities."""
    print("⚡ Parallel Execution Demonstration")
    print("=" * 40)

    # Create workflow with parallel opportunities
    workflow = create_parallel_dag_workflow()

    print(f"📋 Workflow: {workflow.name}")
    print(f"   Nodes: {len(workflow.graph.nodes())}")
    print(f"   Edges: {len(workflow.graph.edges())}")
    print(f"   Has cycles: {workflow.has_cycles()}")

    # Test with different worker counts
    worker_counts = [1, 2, 4, 8]

    for workers in worker_counts:
        print(f"\n🔧 Testing with {workers} worker(s)")

        runtime = ParallelCyclicRuntime(
            debug=False, max_workers=workers, enable_cycles=True
        )

        try:
            start_time = time.time()
            results, run_id = runtime.execute(workflow)
            execution_time = time.time() - start_time

            print(f"   ✅ Completed in {execution_time:.3f}s")
            print(f"   📊 Results: {len(results)} nodes")

        except Exception as e:
            print(f"   ❌ Failed: {e}")


def demonstrate_runtime_configuration():
    """Demonstrate various runtime configuration options."""
    print("⚙️  Runtime Configuration Options")
    print("=" * 40)

    # Create test workflow
    workflow = create_mixed_workflow()

    # Test different configurations
    configs = [
        {"name": "Default LocalRuntime", "runtime": LocalRuntime()},
        {"name": "Debug LocalRuntime", "runtime": LocalRuntime(debug=True)},
        {
            "name": "LocalRuntime (Cycles Disabled)",
            "runtime": LocalRuntime(enable_cycles=False),
        },
        {"name": "ParallelCyclicRuntime (Default)", "runtime": ParallelCyclicRuntime()},
        {
            "name": "ParallelCyclicRuntime (High Performance)",
            "runtime": ParallelCyclicRuntime(
                max_workers=8, enable_cycles=True, enable_async=True
            ),
        },
        {
            "name": "ParallelCyclicRuntime (Conservative)",
            "runtime": ParallelCyclicRuntime(
                max_workers=2, enable_cycles=True, enable_async=False
            ),
        },
    ]

    for config in configs:
        print(f"\n🔧 Testing: {config['name']}")

        # Skip incompatible configurations
        if "Cycles Disabled" in config["name"] and workflow.has_cycles():
            print("   ⏭️  Skipped (workflow has cycles)")
            continue

        try:
            start_time = time.time()
            results, run_id = config["runtime"].execute(workflow)
            execution_time = time.time() - start_time

            print(f"   ✅ Success: {execution_time:.3f}s")
            print(f"   📊 Nodes executed: {len(results)}")

        except Exception as e:
            print(f"   ❌ Failed: {e}")


def demonstrate_tracking_integration():
    """Demonstrate integration with task tracking system."""
    print("📊 Task Tracking Integration")
    print("=" * 40)

    # Create task manager
    task_manager = TaskManager()

    # Create workflow
    workflow = create_mixed_workflow()

    # Test with different runtimes
    runtimes = [
        ("LocalRuntime", LocalRuntime(debug=False)),
        ("ParallelCyclicRuntime", ParallelCyclicRuntime(debug=False, max_workers=4)),
    ]

    for runtime_name, runtime in runtimes:
        print(f"\n🔧 Testing: {runtime_name}")

        try:
            start_time = time.time()
            results, run_id = runtime.execute(workflow, task_manager=task_manager)
            execution_time = time.time() - start_time

            print(f"   ✅ Success: {execution_time:.3f}s")
            print(f"   🆔 Run ID: {run_id}")

            # Get run metrics
            if run_id:
                run_data = task_manager.get_run(run_id)
                if run_data:
                    print(f"   📊 Run status: {run_data.status}")
                    print(f"   ⏱️  Started: {run_data.started_at}")
                    if run_data.ended_at:
                        print(f"   🏁 Ended: {run_data.ended_at}")

                # Get task metrics
                tasks = task_manager.get_run_tasks(run_id)
                print(f"   📋 Tasks tracked: {len(tasks)}")

                for task in tasks[:3]:  # Show first 3 tasks
                    print(f"      • {task.node_id}: {task.status}")

        except Exception as e:
            print(f"   ❌ Failed: {e}")


def main():
    """Run all enhanced runtime integration examples."""
    print("🚀 Enhanced Runtime Integration Examples")
    print("=" * 50)
    print()

    # Run demonstrations
    try:
        demonstrate_automatic_detection()
        print("\n" + "=" * 50 + "\n")

        demonstrate_parallel_execution()
        print("\n" + "=" * 50 + "\n")

        demonstrate_runtime_configuration()
        print("\n" + "=" * 50 + "\n")

        demonstrate_tracking_integration()
        print("\n" + "=" * 50 + "\n")

        benchmark_runtime_performance()

        print("\n🎉 All enhanced runtime integration examples completed successfully!")

    except Exception as e:
        print(f"\n❌ Example failed: {e}")
        import traceback

        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
