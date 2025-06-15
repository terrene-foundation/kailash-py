#!/usr/bin/env python3
"""
Developer Tools Comprehensive Example - Phase 5.2 Implementation
===============================================================

This example demonstrates the comprehensive suite of developer tools introduced
in Phase 5.2, including cycle debugging, profiling, and analysis capabilities.
These tools provide deep insights into cycle behavior, performance optimization
opportunities, and comprehensive monitoring capabilities.

Key Features Demonstrated:
- CycleDebugger for detailed execution tracking
- CycleProfiler for performance analysis and bottleneck identification
- CycleAnalyzer for comprehensive analysis and reporting
- Real-time monitoring and health scoring
- Comparative analysis across multiple cycles
- Optimization recommendations and insights
- Data export capabilities for external analysis
"""

import random
import sys
import time
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
from examples.utils.data_paths import get_output_data_path
from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.local import LocalRuntime
from kailash.workflow import (
    CycleAnalyzer,
    CycleDebugger,
    CycleProfiler,
    CycleTemplates,
    Workflow,
)


class OptimizationNode(Node):
    """Node that simulates an optimization algorithm with variable performance."""

    def get_parameters(self):
        return {
            "value": NodeParameter(
                name="value", type=float, required=False, default=0.0
            ),
            "target": NodeParameter(
                name="target", type=float, required=False, default=100.0
            ),
            "iteration": NodeParameter(
                name="iteration", type=int, required=False, default=0
            ),
            "learning_rate": NodeParameter(
                name="learning_rate", type=float, required=False, default=0.1
            ),
            "noise_factor": NodeParameter(
                name="noise_factor", type=float, required=False, default=0.0
            ),
        }

    def run(self, context: Any = None, **inputs) -> dict[str, Any]:
        """Simulate optimization with configurable performance characteristics."""
        import random

        value = inputs.get("value", 0.0)
        target = inputs.get("target", 100.0)
        iteration = inputs.get("iteration", 0)
        learning_rate = inputs.get("learning_rate", 0.1)
        noise_factor = inputs.get("noise_factor", 0.0)

        # Simulate variable processing time
        if iteration > 10:
            time.sleep(0.02)  # Slower iterations later
        else:
            time.sleep(0.01)  # Faster initial iterations

        # Calculate improvement with noise
        error = target - value
        improvement = error * learning_rate

        # Add noise for realistic variability
        if noise_factor > 0:
            noise = random.uniform(-noise_factor, noise_factor) * improvement
            improvement += noise

        new_value = value + improvement
        quality = min(new_value / target, 1.0) if target > 0 else 0.0
        convergence_error = abs(target - new_value) / target if target > 0 else 0.0

        return {
            "value": new_value,
            "target": target,
            "iteration": iteration + 1,
            "learning_rate": learning_rate,
            "noise_factor": noise_factor,
            "quality": quality,
            "error": convergence_error,
            "improvement": improvement,
        }


def demonstrate_cycle_debugger():
    """Demonstrate CycleDebugger capabilities."""
    print("=== CycleDebugger Demonstration ===")

    # Create debugger with verbose logging
    debugger = CycleDebugger(debug_level="detailed", enable_profiling=True)

    # Start debugging a cycle
    trace = debugger.start_cycle(
        cycle_id="debug_demo_cycle",
        workflow_id="debug_demo_workflow",
        max_iterations=10,
        timeout=30.0,
        convergence_condition="error < 0.01",
    )

    print(f"Started debugging cycle: {trace.cycle_id}")

    # Simulate cycle execution with iterations
    value = 10.0
    target = 100.0

    for i in range(1, 8):  # Simulate 7 iterations
        input_data = {
            "value": value,
            "target": target,
            "iteration": i,
            "learning_rate": 0.2,
        }

        # Start iteration tracking
        iteration = debugger.start_iteration(trace, input_data)

        # Simulate processing (would be real node execution)
        time.sleep(0.01)
        error = target - value
        improvement = error * 0.2
        value += improvement
        quality = value / target
        convergence_error = abs(target - value) / target

        output_data = {
            "value": value,
            "quality": quality,
            "error": convergence_error,
            "improvement": improvement,
        }

        # End iteration tracking
        debugger.end_iteration(
            trace,
            iteration,
            output_data,
            convergence_value=convergence_error,
            node_executions=["optimization_node"],
        )

        print(f"  Iteration {i}: value={value:.2f}, error={convergence_error:.4f}")

        # Check convergence
        if convergence_error < 0.01:
            debugger.end_cycle(
                trace,
                converged=True,
                termination_reason="convergence",
                convergence_iteration=i,
            )
            break
    else:
        debugger.end_cycle(trace, converged=False, termination_reason="max_iterations")

    # Generate debugging report
    report = debugger.generate_report(trace)
    print("\nDebug Report Summary:")
    print(f"  Converged: {report['cycle_info']['converged']}")
    print(f"  Execution time: {report['cycle_info']['execution_time']:.3f}s")
    print(f"  Efficiency score: {report['performance']['efficiency_score']:.3f}")
    print(f"  Recommendations: {len(report['recommendations'])}")

    return trace


def demonstrate_cycle_profiler():
    """Demonstrate CycleProfiler capabilities."""
    print("\n=== CycleProfiler Demonstration ===")

    profiler = CycleProfiler(enable_advanced_metrics=True)

    # Create multiple traces for comparative analysis
    traces = []

    # Trace 1: Fast convergence
    trace1 = create_sample_trace(
        "fast_cycle", iterations=5, avg_time=0.01, converged=True
    )
    profiler.add_trace(trace1)
    traces.append(trace1)

    # Trace 2: Slow convergence
    trace2 = create_sample_trace(
        "slow_cycle", iterations=15, avg_time=0.05, converged=True
    )
    profiler.add_trace(trace2)
    traces.append(trace2)

    # Trace 3: Failed convergence
    trace3 = create_sample_trace(
        "failed_cycle", iterations=20, avg_time=0.03, converged=False
    )
    profiler.add_trace(trace3)
    traces.append(trace3)

    print(f"Added {len(traces)} traces for analysis")

    # Perform performance analysis
    metrics = profiler.analyze_performance()
    print("\nPerformance Analysis:")
    print(f"  Total cycles: {metrics.total_cycles}")
    print(f"  Total iterations: {metrics.total_iterations}")
    print(f"  Avg cycle time: {metrics.avg_cycle_time:.3f}s")
    print(f"  Avg iteration time: {metrics.avg_iteration_time:.3f}s")
    print(f"  Bottlenecks identified: {len(metrics.bottlenecks)}")

    # Compare specific cycles
    comparison = profiler.compare_cycles(["fast_cycle", "slow_cycle", "failed_cycle"])
    print("\nCycle Comparison:")
    print(f"  Best cycle: {comparison['best_cycle']}")
    print(f"  Worst cycle: {comparison['worst_cycle']}")
    print(f"  Performance ranking: {comparison['performance_ranking']}")

    # Get optimization recommendations
    recommendations = profiler.get_optimization_recommendations()
    print(f"\nOptimization Recommendations ({len(recommendations)}):")
    for i, rec in enumerate(recommendations[:3], 1):  # Show top 3
        print(f"  {i}. [{rec['priority']}] {rec['description']}")
        print(f"     Suggestion: {rec['suggestion']}")

    return profiler


def demonstrate_cycle_analyzer():
    """Demonstrate CycleAnalyzer comprehensive capabilities."""
    print("\n=== CycleAnalyzer Demonstration ===")

    # Create analyzer with comprehensive analysis
    analyzer = CycleAnalyzer(
        analysis_level="comprehensive",
        enable_profiling=True,
        enable_debugging=True,
        output_directory=str(
            get_output_data_path("cycle_analysis", file_type="json").parent
        ),
    )

    # Start analysis session
    session_id = analyzer.start_analysis_session("developer_tools_demo")
    print(f"Started analysis session: {session_id}")

    # Analyze multiple cycles with different characteristics
    cycle_configs = [
        ("efficient_cycle", {"max_iterations": 10, "learning_rate": 0.3, "noise": 0.0}),
        ("noisy_cycle", {"max_iterations": 15, "learning_rate": 0.2, "noise": 0.1}),
        ("slow_cycle", {"max_iterations": 20, "learning_rate": 0.1, "noise": 0.05}),
    ]

    for cycle_id, config in cycle_configs:
        print(f"\nAnalyzing {cycle_id}...")

        # Start cycle analysis
        trace = analyzer.start_cycle_analysis(
            cycle_id=cycle_id,
            workflow_id="analyzer_demo",
            max_iterations=config["max_iterations"],
            timeout=60.0,
            convergence_condition="error < 0.01",
        )

        # Simulate cycle execution
        value = 10.0
        target = 100.0

        for i in range(1, config["max_iterations"] + 1):
            input_data = {
                "value": value,
                "target": target,
                "iteration": i,
                "learning_rate": config["learning_rate"],
                "noise_factor": config["noise"],
            }

            # Simulate processing with variable performance
            time.sleep(0.005 if "efficient" in cycle_id else 0.02)

            error = target - value
            improvement = error * config["learning_rate"]

            # Add noise
            if config["noise"] > 0:

                noise = random.uniform(-config["noise"], config["noise"]) * improvement
                improvement += noise

            value += improvement
            convergence_error = abs(target - value) / target

            output_data = {
                "value": value,
                "error": convergence_error,
                "improvement": improvement,
            }

            # Track iteration
            analyzer.track_iteration(
                trace,
                input_data,
                output_data,
                convergence_value=convergence_error,
                node_executions=["optimization_node"],
            )

            # Get real-time metrics
            if i % 5 == 0:  # Check every 5 iterations
                real_time_metrics = analyzer.get_real_time_metrics(trace)
                print(
                    f"  Real-time health score: {real_time_metrics['health_score']:.3f}"
                )
                if real_time_metrics["alerts"]:
                    print(f"  Alerts: {real_time_metrics['alerts']}")

            # Check convergence
            if convergence_error < 0.01:
                analyzer.complete_cycle_analysis(
                    trace,
                    converged=True,
                    termination_reason="convergence",
                    convergence_iteration=i,
                )
                print(f"  Converged at iteration {i}")
                break
        else:
            analyzer.complete_cycle_analysis(
                trace, converged=False, termination_reason="max_iterations"
            )
            print(f"  Failed to converge in {config['max_iterations']} iterations")

        # Generate individual cycle report
        cycle_report = analyzer.generate_cycle_report(trace)
        efficiency = cycle_report.get("performance", {}).get("efficiency_score", 0)
        print(f"  Cycle efficiency: {efficiency:.3f}")

    # Generate comprehensive session report
    session_report = analyzer.generate_session_report()
    print("\nSession Report Summary:")
    print(f"  Cycles analyzed: {session_report['summary']['total_cycles']}")
    print(
        f"  Overall convergence rate: {session_report['summary']['convergence_rate']:.3f}"
    )
    print(f"  Average cycle time: {session_report['summary']['avg_cycle_time']:.3f}s")

    if "comparative_analysis" in session_report:
        comp = session_report["comparative_analysis"]
        print(f"  Best performing cycle: {comp.get('best_cycle', 'N/A')}")
        print(f"  Performance ranking: {comp.get('performance_ranking', [])}")

    if "insights" in session_report:
        insights = session_report["insights"]
        print(f"  Session quality: {insights.get('session_quality', 'unknown')}")
        print(
            f"  Performance consistency: {insights.get('performance_consistency', 0):.3f}"
        )

    # Export analysis data
    analyzer.export_analysis_data(format="json", include_traces=True)
    print("\nAnalysis data exported to files")

    return analyzer


def demonstrate_real_world_workflow_analysis():
    """Demonstrate analysis of actual workflow execution."""
    print("\n=== Real Workflow Analysis ===")

    # Create workflow with optimization cycle
    workflow = Workflow("analysis_demo", "Analysis Demo Workflow")
    workflow.add_node("optimizer", OptimizationNode())

    # Create analyzer for the workflow
    analyzer = CycleAnalyzer(
        analysis_level="standard", enable_profiling=True, enable_debugging=True
    )

    analyzer.start_analysis_session("real_workflow_demo")

    # Configure cycle with optimization template
    config = CycleTemplates.optimization_loop(
        max_iterations=15, convergence_threshold=0.02
    )

    # Add cycle to workflow
    workflow.create_cycle("optimization_loop").connect(
        "optimizer",
        "optimizer",
        {
            "value": "value",
            "target": "target",
            "iteration": "iteration",
            "learning_rate": "learning_rate",
        },
    ).max_iterations(config.max_iterations).converge_when("error < 0.02").timeout(
        30.0
    ).build()

    print("Created workflow with optimization cycle")

    # Start analysis
    trace = analyzer.start_cycle_analysis(
        cycle_id="optimization_loop",
        workflow_id=workflow.workflow_id,
        max_iterations=config.max_iterations,
        convergence_condition="error < 0.02",
    )

    # Execute workflow with runtime
    runtime = LocalRuntime()
    print("Executing workflow with analysis tracking...")

    # Note: This is a simplified simulation since we can't easily hook into
    # the actual runtime execution for this demo
    results, run_id = runtime.execute(
        workflow,
        parameters={
            "value": 15.0,
            "target": 100.0,
            "iteration": 0,
            "learning_rate": 0.25,
        },
    )

    # Simulate analysis tracking (in real integration, this would be automatic)
    final_result = results["optimizer"]
    simulated_iterations = final_result.get("iteration", 10)

    for i in range(1, simulated_iterations + 1):
        # Simulate iteration data
        iter_value = 15.0 + (85.0 * i / simulated_iterations)
        error = abs(100.0 - iter_value) / 100.0

        analyzer.track_iteration(
            trace,
            {"value": iter_value, "iteration": i},
            {"value": iter_value, "error": error},
            convergence_value=error,
        )

    # Complete analysis
    converged = final_result.get("error", 1.0) < 0.02
    analyzer.complete_cycle_analysis(
        trace,
        converged=converged,
        termination_reason="convergence" if converged else "max_iterations",
    )

    # Generate comprehensive report
    cycle_report = analyzer.generate_cycle_report(trace)

    print("Workflow Analysis Results:")
    print(f"  Final value: {final_result.get('value', 0):.2f}")
    print(f"  Final error: {final_result.get('error', 1):.4f}")
    print(f"  Iterations: {final_result.get('iteration', 0)}")
    print(
        f"  Analysis efficiency score: {cycle_report.get('performance', {}).get('efficiency_score', 0):.3f}"
    )

    return results


def create_sample_trace(
    cycle_id: str, iterations: int, avg_time: float, converged: bool
):
    """Create a sample execution trace for testing."""
    from datetime import datetime, timedelta

    from kailash.workflow.cycle_debugger import CycleExecutionTrace, CycleIteration

    # Create trace
    trace = CycleExecutionTrace(
        cycle_id=cycle_id,
        workflow_id="sample_workflow",
        start_time=datetime.now() - timedelta(seconds=iterations * avg_time),
        max_iterations_configured=iterations + 5,
        timeout_configured=60.0,
        convergence_condition="error < 0.01",
    )

    # Add iterations
    value = 10.0
    target = 100.0

    for i in range(1, iterations + 1):
        iteration = CycleIteration(
            iteration_number=i,
            start_time=datetime.now() - timedelta(seconds=(iterations - i) * avg_time),
            input_data={"value": value, "target": target},
        )

        # Simulate processing
        error = target - value
        improvement = error * 0.2
        value += improvement
        convergence_error = abs(target - value) / target

        iteration.complete(
            {"value": value, "error": convergence_error},
            convergence_value=convergence_error,
        )

        iteration.execution_time = avg_time
        iteration.memory_usage_mb = 50 + i * 2  # Simulate memory growth
        iteration.cpu_usage_percent = 30 + (i % 3) * 10  # Simulate CPU variation

        trace.add_iteration(iteration)

        if converged and convergence_error < 0.01:
            trace.complete(True, "convergence", i)
            break
    else:
        trace.complete(converged, "convergence" if converged else "max_iterations")

    return trace


if __name__ == "__main__":
    print("Developer Tools Comprehensive Example - Phase 5.2")
    print("=" * 65)

    # Demonstrate individual components
    debug_trace = demonstrate_cycle_debugger()
    profiler = demonstrate_cycle_profiler()
    analyzer = demonstrate_cycle_analyzer()

    # Demonstrate real workflow integration
    workflow_results = demonstrate_real_world_workflow_analysis()

    print("\n" + "=" * 65)
    print("✅ All developer tools demonstrations completed!")
    print("\nKey Benefits of Phase 5.2:")
    print("• Comprehensive cycle debugging with detailed execution tracking")
    print("• Advanced performance profiling and bottleneck identification")
    print("• Unified analysis framework with real-time monitoring")
    print("• Comparative analysis and optimization recommendations")
    print("• Export capabilities for external analysis and reporting")
    print("• Integration with workflow execution for production monitoring")
    print("• Health scoring and alerting for proactive issue detection")
