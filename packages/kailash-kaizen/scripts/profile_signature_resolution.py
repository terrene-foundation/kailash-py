#!/usr/bin/env python3
"""
Signature Resolution Performance Profiling Script

Purpose: Profile signature parsing, compilation, and resolution to identify bottlenecks
Target: <100ms p95 latency for signature resolution
Context: TODO-151 Phase 1 - Signature Resolution Optimization

Usage:
    python scripts/profile_signature_resolution.py
    python scripts/profile_signature_resolution.py --output profiling-results.json
    python scripts/profile_signature_resolution.py --visualize
"""

import argparse
import cProfile
import io
import json
import pstats
import statistics
import sys
import time
import tracemalloc
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from kaizen.signatures import (
    InputField,
    OutputField,
    Signature,
    SignatureCompiler,
    SignatureParser,
    SignatureValidator,
)
from kaizen.signatures.enterprise import MultiModalSignature


@dataclass
class ProfilingResult:
    """Single profiling measurement result."""

    operation: str
    signature_type: str
    execution_time_ms: float
    memory_allocated_kb: float
    peak_memory_kb: float
    function_calls: int
    primitive_calls: int
    top_functions: List[Dict[str, Any]]


@dataclass
class ProfilingReport:
    """Complete profiling report."""

    total_samples: int
    overall_stats: Dict[str, Any]
    operation_results: List[ProfilingResult]
    bottlenecks: List[Dict[str, Any]]
    recommendations: List[str]


class SignatureProfiler:
    """Profiler for signature resolution operations."""

    def __init__(self, num_iterations: int = 100):
        """
        Initialize profiler.

        Args:
            num_iterations: Number of iterations for statistical profiling
        """
        self.num_iterations = num_iterations
        self.results: List[ProfilingResult] = []

    def profile_operation(
        self,
        operation_name: str,
        signature_type: str,
        operation_func: callable,
        *args,
        **kwargs,
    ) -> ProfilingResult:
        """
        Profile a single operation with cProfile and tracemalloc.

        Args:
            operation_name: Name of operation being profiled
            signature_type: Type of signature (simple, complex, multi_modal)
            operation_func: Function to profile
            *args, **kwargs: Arguments for operation_func

        Returns:
            ProfilingResult with timing and memory data
        """
        # Memory profiling
        tracemalloc.start()

        # Create profiler
        profiler = cProfile.Profile()

        # Start timing
        start_time = time.perf_counter()

        # Profile execution
        profiler.enable()
        result = operation_func(*args, **kwargs)
        profiler.disable()

        # End timing
        end_time = time.perf_counter()
        execution_time_ms = (end_time - start_time) * 1000

        # Get memory stats
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Get profiling stats
        stats_stream = io.StringIO()
        ps = pstats.Stats(profiler, stream=stats_stream)
        ps.sort_stats("cumulative")

        # Extract top functions
        stats_data = ps.stats
        top_functions = []

        for func_key, (cc, nc, tt, ct, callers) in list(stats_data.items())[:10]:
            filename, line, func_name = func_key
            top_functions.append(
                {
                    "function": func_name,
                    "file": Path(filename).name,
                    "line": line,
                    "calls": cc,
                    "cumulative_time": ct * 1000,  # Convert to ms
                    "total_time": tt * 1000,
                    "per_call": (ct / cc * 1000) if cc > 0 else 0,
                }
            )

        return ProfilingResult(
            operation=operation_name,
            signature_type=signature_type,
            execution_time_ms=execution_time_ms,
            memory_allocated_kb=current / 1024,
            peak_memory_kb=peak / 1024,
            function_calls=ps.total_calls,
            primitive_calls=ps.prim_calls,
            top_functions=top_functions,
        )

    def run_statistical_profile(
        self,
        operation_name: str,
        signature_type: str,
        operation_func: callable,
        *args,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Run operation multiple times for statistical analysis.

        Args:
            operation_name: Name of operation
            signature_type: Type of signature
            operation_func: Function to profile

        Returns:
            Statistical summary (mean, median, p95, p99)
        """
        execution_times = []
        memory_peaks = []

        for _ in range(self.num_iterations):
            result = self.profile_operation(
                operation_name, signature_type, operation_func, *args, **kwargs
            )
            execution_times.append(result.execution_time_ms)
            memory_peaks.append(result.peak_memory_kb)

        return {
            "operation": operation_name,
            "signature_type": signature_type,
            "samples": self.num_iterations,
            "execution_time": {
                "mean": statistics.mean(execution_times),
                "median": statistics.median(execution_times),
                "stdev": (
                    statistics.stdev(execution_times) if len(execution_times) > 1 else 0
                ),
                "min": min(execution_times),
                "max": max(execution_times),
                "p95": statistics.quantiles(execution_times, n=20)[
                    18
                ],  # 95th percentile
                "p99": statistics.quantiles(execution_times, n=100)[
                    98
                ],  # 99th percentile
            },
            "memory": {
                "mean_peak_kb": statistics.mean(memory_peaks),
                "max_peak_kb": max(memory_peaks),
            },
        }

    def profile_signature_parsing(self) -> None:
        """Profile signature parsing for various complexities."""
        test_signatures = {
            "simple": "question -> answer",
            "multi_input": "context, question -> answer",
            "multi_output": "question -> answer, confidence",
            "complex": "context, question, metadata -> reasoning, answer, confidence",
            "list_output": "topic -> [analysis1, analysis2], summary",
            "enterprise": "customer_data -> privacy_checked_analysis, audit_trail",
            "multi_modal": "text, image -> analysis, visual_description",
        }

        parser = SignatureParser()

        for sig_type, sig_text in test_signatures.items():
            print(f"Profiling parsing: {sig_type}")

            # Single detailed profile
            detailed_result = self.profile_operation(
                "parse_signature", sig_type, parser.parse, sig_text
            )
            self.results.append(detailed_result)

            # Statistical profile
            stats = self.run_statistical_profile(
                "parse_signature", sig_type, parser.parse, sig_text
            )

            print(
                f"  Mean: {stats['execution_time']['mean']:.2f}ms, "
                f"P95: {stats['execution_time']['p95']:.2f}ms"
            )

    def profile_signature_compilation(self) -> None:
        """Profile signature compilation to workflow parameters."""
        compiler = SignatureCompiler()

        # Test signatures
        test_signatures = {
            "simple": Signature(
                inputs=["question"], outputs=["answer"], signature_type="basic"
            ),
            "complex": Signature(
                inputs=["context", "question", "metadata"],
                outputs=["reasoning", "answer", "confidence"],
                signature_type="complex",
            ),
            "enterprise": Signature(
                inputs=["customer_data"],
                outputs=["analysis", "audit_trail"],
                signature_type="enterprise",
                requires_privacy_check=True,
                requires_audit_trail=True,
            ),
            "multi_modal": MultiModalSignature(
                inputs=["text", "image"],
                outputs=["analysis", "description"],
                signature_type="multi_modal",
                supports_multi_modal=True,
            ),
        }

        for sig_type, signature in test_signatures.items():
            print(f"Profiling compilation: {sig_type}")

            # Single detailed profile
            detailed_result = self.profile_operation(
                "compile_to_workflow_params",
                sig_type,
                compiler.compile_to_workflow_params,
                signature,
            )
            self.results.append(detailed_result)

            # Statistical profile
            stats = self.run_statistical_profile(
                "compile_to_workflow_params",
                sig_type,
                compiler.compile_to_workflow_params,
                signature,
            )

            print(
                f"  Mean: {stats['execution_time']['mean']:.2f}ms, "
                f"P95: {stats['execution_time']['p95']:.2f}ms"
            )

    def profile_signature_validation(self) -> None:
        """Profile signature validation."""
        validator = SignatureValidator()

        test_signatures = {
            "simple": Signature(
                inputs=["question"], outputs=["answer"], signature_type="basic"
            ),
            "with_types": Signature(
                inputs=["question"],
                outputs=["answer"],
                signature_type="basic",
                input_types={"question": "text"},
                output_types={"answer": "text"},
            ),
            "multi_modal": MultiModalSignature(
                inputs=["text", "image"],
                outputs=["analysis"],
                signature_type="multi_modal",
                supports_multi_modal=True,
                input_types={"text": "text", "image": "image"},
            ),
        }

        for sig_type, signature in test_signatures.items():
            print(f"Profiling validation: {sig_type}")

            # Single detailed profile
            detailed_result = self.profile_operation(
                "validate_signature", sig_type, validator.validate, signature
            )
            self.results.append(detailed_result)

            # Statistical profile
            stats = self.run_statistical_profile(
                "validate_signature", sig_type, validator.validate, signature
            )

            print(
                f"  Mean: {stats['execution_time']['mean']:.2f}ms, "
                f"P95: {stats['execution_time']['p95']:.2f}ms"
            )

    def profile_class_based_signatures(self) -> None:
        """Profile class-based signature creation (DSPy-style)."""

        def create_simple_signature():
            class QASignature(Signature):
                question: str = InputField(desc="Question")
                answer: str = OutputField(desc="Answer")

            return QASignature()

        def create_complex_signature():
            class ComplexSignature(Signature):
                context: str = InputField(desc="Context")
                question: str = InputField(desc="Question")
                metadata: str = InputField(desc="Metadata")
                reasoning: str = OutputField(desc="Reasoning")
                answer: str = OutputField(desc="Answer")
                confidence: float = OutputField(desc="Confidence")

            return ComplexSignature()

        print("Profiling class-based signature creation")

        # Simple signature
        result_simple = self.profile_operation(
            "create_class_signature", "simple", create_simple_signature
        )
        self.results.append(result_simple)

        # Complex signature
        result_complex = self.profile_operation(
            "create_class_signature", "complex", create_complex_signature
        )
        self.results.append(result_complex)

    def profile_end_to_end(self) -> None:
        """Profile complete signature resolution pipeline."""

        def resolve_signature(sig_text: str):
            parser = SignatureParser()
            compiler = SignatureCompiler()
            validator = SignatureValidator()

            # Parse
            parsed = parser.parse(sig_text)

            # Create signature
            sig = Signature(
                inputs=parsed.inputs,
                outputs=parsed.outputs,
                signature_type=parsed.signature_type,
            )

            # Validate
            validation = validator.validate(sig)

            # Compile
            compiled = compiler.compile_to_workflow_params(sig)

            return compiled

        test_cases = {
            "simple": "question -> answer",
            "complex": "context, question, metadata -> reasoning, answer, confidence",
            "multi_modal": "text, image -> analysis, visual_description",
        }

        for sig_type, sig_text in test_cases.items():
            print(f"Profiling end-to-end: {sig_type}")

            # Single detailed profile
            detailed_result = self.profile_operation(
                "end_to_end_resolution", sig_type, resolve_signature, sig_text
            )
            self.results.append(detailed_result)

            # Statistical profile
            stats = self.run_statistical_profile(
                "end_to_end_resolution", sig_type, resolve_signature, sig_text
            )

            print(
                f"  Mean: {stats['execution_time']['mean']:.2f}ms, "
                f"P95: {stats['execution_time']['p95']:.2f}ms, "
                f"P99: {stats['execution_time']['p99']:.2f}ms"
            )

    def analyze_bottlenecks(self) -> List[Dict[str, Any]]:
        """Analyze results to identify bottlenecks."""
        bottlenecks = []

        # Group by operation
        operations = {}
        for result in self.results:
            if result.operation not in operations:
                operations[result.operation] = []
            operations[result.operation].append(result)

        # Find slowest operations
        for operation, results in operations.items():
            avg_time = statistics.mean([r.execution_time_ms for r in results])
            max_time = max([r.execution_time_ms for r in results])

            # Identify functions consuming most time
            all_functions = {}
            for result in results:
                for func in result.top_functions:
                    func_key = f"{func['file']}:{func['function']}"
                    if func_key not in all_functions:
                        all_functions[func_key] = {
                            "function": func["function"],
                            "file": func["file"],
                            "total_time": 0,
                            "call_count": 0,
                        }
                    all_functions[func_key]["total_time"] += func["cumulative_time"]
                    all_functions[func_key]["call_count"] += func["calls"]

            # Sort by total time
            top_funcs = sorted(
                all_functions.values(), key=lambda x: x["total_time"], reverse=True
            )[:5]

            bottlenecks.append(
                {
                    "operation": operation,
                    "avg_time_ms": avg_time,
                    "max_time_ms": max_time,
                    "sample_count": len(results),
                    "top_functions": top_funcs,
                    "exceeds_target": max_time > 100,  # 100ms target
                }
            )

        return sorted(bottlenecks, key=lambda x: x["avg_time_ms"], reverse=True)

    def generate_recommendations(self, bottlenecks: List[Dict[str, Any]]) -> List[str]:
        """Generate optimization recommendations based on bottlenecks."""
        recommendations = []

        for bottleneck in bottlenecks:
            if bottleneck["avg_time_ms"] > 50:
                recommendations.append(
                    f"HIGH PRIORITY: {bottleneck['operation']} averages "
                    f"{bottleneck['avg_time_ms']:.2f}ms - consider caching or optimization"
                )

            # Check for regex compilation
            for func in bottleneck["top_functions"]:
                if (
                    "compile" in func["function"].lower()
                    and "regex" in func["file"].lower()
                ):
                    recommendations.append(
                        f"OPTIMIZATION: Pre-compile regex patterns in {func['file']} "
                        f"(saves ~{func['total_time']/bottleneck['sample_count']:.2f}ms per call)"
                    )

                # Check for repeated parsing
                if "parse" in func["function"].lower() and func["call_count"] > 100:
                    recommendations.append(
                        f"CACHING: {func['function']} called {func['call_count']} times - "
                        f"implement result caching"
                    )

        # General recommendations
        end_to_end = [b for b in bottlenecks if "end_to_end" in b["operation"]]
        if end_to_end and end_to_end[0]["avg_time_ms"] > 100:
            recommendations.append(
                "TARGET MISS: End-to-end resolution exceeds 100ms target - "
                "implement signature result caching"
            )

        return recommendations

    def generate_report(self) -> ProfilingReport:
        """Generate comprehensive profiling report."""
        bottlenecks = self.analyze_bottlenecks()
        recommendations = self.generate_recommendations(bottlenecks)

        # Overall statistics
        all_times = [r.execution_time_ms for r in self.results]
        all_memory = [r.peak_memory_kb for r in self.results]

        overall_stats = {
            "total_operations_profiled": len(self.results),
            "execution_time": {
                "mean": statistics.mean(all_times),
                "median": statistics.median(all_times),
                "min": min(all_times),
                "max": max(all_times),
                "p95": statistics.quantiles(all_times, n=20)[18],
                "p99": statistics.quantiles(all_times, n=100)[98],
            },
            "memory": {
                "mean_peak_kb": statistics.mean(all_memory),
                "max_peak_kb": max(all_memory),
            },
        }

        return ProfilingReport(
            total_samples=len(self.results),
            overall_stats=overall_stats,
            operation_results=self.results,
            bottlenecks=bottlenecks,
            recommendations=recommendations,
        )

    def save_report(self, output_file: str) -> None:
        """Save report to JSON file."""
        report = self.generate_report()

        # Convert to dict
        report_dict = {
            "total_samples": report.total_samples,
            "overall_stats": report.overall_stats,
            "operation_results": [asdict(r) for r in report.operation_results],
            "bottlenecks": report.bottlenecks,
            "recommendations": report.recommendations,
        }

        with open(output_file, "w") as f:
            json.dump(report_dict, f, indent=2)

        print(f"\nReport saved to: {output_file}")

    def print_summary(self) -> None:
        """Print summary report to console."""
        report = self.generate_report()

        print("\n" + "=" * 80)
        print("SIGNATURE RESOLUTION PROFILING REPORT")
        print("=" * 80)

        print(f"\nTotal operations profiled: {report.total_samples}")
        print("\nOverall Statistics:")
        print("  Execution Time (ms):")
        print(f"    Mean:   {report.overall_stats['execution_time']['mean']:.2f}")
        print(f"    Median: {report.overall_stats['execution_time']['median']:.2f}")
        print(f"    P95:    {report.overall_stats['execution_time']['p95']:.2f}")
        print(f"    P99:    {report.overall_stats['execution_time']['p99']:.2f}")
        print(f"    Min:    {report.overall_stats['execution_time']['min']:.2f}")
        print(f"    Max:    {report.overall_stats['execution_time']['max']:.2f}")

        print("\n  Memory Usage:")
        print(f"    Mean Peak: {report.overall_stats['memory']['mean_peak_kb']:.2f} KB")
        print(f"    Max Peak:  {report.overall_stats['memory']['max_peak_kb']:.2f} KB")

        print("\n" + "-" * 80)
        print("BOTTLENECKS (Top 5)")
        print("-" * 80)

        for i, bottleneck in enumerate(report.bottlenecks[:5], 1):
            status = "❌ EXCEEDS TARGET" if bottleneck["exceeds_target"] else "✅"
            print(f"\n{i}. {bottleneck['operation']} {status}")
            print(
                f"   Avg: {bottleneck['avg_time_ms']:.2f}ms, Max: {bottleneck['max_time_ms']:.2f}ms"
            )
            print("   Top functions:")
            for func in bottleneck["top_functions"][:3]:
                print(
                    f"     - {func['function']} ({func['file']}): "
                    f"{func['total_time']/bottleneck['sample_count']:.2f}ms avg"
                )

        print("\n" + "-" * 80)
        print("RECOMMENDATIONS")
        print("-" * 80)

        for i, rec in enumerate(report.recommendations, 1):
            print(f"{i}. {rec}")

        print("\n" + "=" * 80)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Profile signature resolution performance"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=100,
        help="Number of iterations for statistical profiling (default: 100)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="signature_profiling_results.json",
        help="Output JSON file for results (default: signature_profiling_results.json)",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("SIGNATURE RESOLUTION PERFORMANCE PROFILING")
    print("=" * 80)
    print(f"\nIterations per operation: {args.iterations}")
    print(f"Output file: {args.output}")
    print("")

    profiler = SignatureProfiler(num_iterations=args.iterations)

    # Run all profiling operations
    print("\n1. Profiling signature parsing...")
    profiler.profile_signature_parsing()

    print("\n2. Profiling signature compilation...")
    profiler.profile_signature_compilation()

    print("\n3. Profiling signature validation...")
    profiler.profile_signature_validation()

    print("\n4. Profiling class-based signatures...")
    profiler.profile_class_based_signatures()

    print("\n5. Profiling end-to-end resolution...")
    profiler.profile_end_to_end()

    # Generate and save report
    profiler.save_report(args.output)

    # Print summary
    profiler.print_summary()

    print(f"\nProfiling complete! Results saved to {args.output}")


if __name__ == "__main__":
    main()
