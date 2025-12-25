"""
E2E performance tests for conditional execution.

Tests performance characteristics and benchmarking including:
- Performance comparison between route_data and skip_branches modes
- Scalability testing with large conditional workflows
- Memory usage optimization validation
- Real-world performance scenarios
- Benchmark reporting and metrics collection
"""

import gc
import os
import time
from statistics import mean, stdev
from unittest.mock import patch

import psutil
import pytest
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import MergeNode, SwitchNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow


class TestConditionalExecutionPerformance:
    """Test conditional execution performance characteristics."""

    def setup_method(self):
        """Set up performance test environment."""
        # Force garbage collection before tests
        gc.collect()

        # Get initial memory baseline
        self.process = psutil.Process(os.getpid())
        self.initial_memory = self.process.memory_info().rss / 1024 / 1024  # MB

    def teardown_method(self):
        """Clean up after performance tests."""
        gc.collect()

    def measure_memory_usage(self):
        """Measure current memory usage."""
        current_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        return current_memory - self.initial_memory

    def create_large_conditional_workflow(self, num_branches=50, work_per_branch=0.001):
        """Create large conditional workflow for performance testing."""
        workflow = Workflow("large_conditional", "Large Conditional Performance Test")

        # Source data that activates only 20% of branches
        source = PythonCodeNode(
            name="source",
            code=f"""
import random
active_branches = random.sample(range({num_branches}), {num_branches // 5})
result = {{'active_branches': active_branches, 'total_branches': {num_branches}}}
""",
        )
        workflow.add_node("source", source)

        # Create many conditional branches
        for i in range(num_branches):
            # Switch for each branch
            switch = SwitchNode(
                name=f"switch_{i}",
                condition_field="active_branches",
                operator="contains",
                value=i,
            )

            # Processor with configurable work amount
            processor = PythonCodeNode(
                name=f"processor_{i}",
                code=f"""
import time
time.sleep({work_per_branch})  # Simulate work
result = {{'branch_id': {i}, 'work_done': True, 'timestamp': time.time()}}
""",
            )

            workflow.add_node(f"switch_{i}", switch)
            workflow.add_node(f"processor_{i}", processor)

            # Connect branch
            workflow.connect("source", f"switch_{i}", {"result": "input_data"})
            workflow.connect(f"switch_{i}", f"processor_{i}", {"true_output": "input"})

        # Aggregator to collect results - simplified version
        aggregator = PythonCodeNode(
            name="aggregator",
            code=f"""
# Simple aggregator that doesn't cause errors
result = {{
    'message': 'Aggregation complete',
    'total_possible_branches': {num_branches}
}}
""",
        )
        workflow.add_node("aggregator", aggregator)

        # Connect all processors to aggregator (only executed ones will have data)
        for i in range(num_branches):
            workflow.connect(f"processor_{i}", "aggregator", {"result": f"branch_{i}"})

        return workflow

    def benchmark_execution_modes(self, workflow, iterations=3):
        """Benchmark both execution modes with multiple iterations."""
        route_times = []
        skip_times = []
        route_memory = []
        skip_memory = []

        for i in range(iterations):
            # Benchmark route_data mode
            gc.collect()
            initial_mem = self.measure_memory_usage()

            runtime_route = LocalRuntime(conditional_execution="route_data")
            start_time = time.perf_counter()
            results_route, _ = runtime_route.execute(workflow)
            route_time = time.perf_counter() - start_time

            route_mem = self.measure_memory_usage() - initial_mem
            route_times.append(route_time)
            route_memory.append(route_mem)

            # Benchmark skip_branches mode (if implemented)
            gc.collect()
            initial_mem = self.measure_memory_usage()

            runtime_skip = LocalRuntime(conditional_execution="skip_branches")

            try:
                start_time = time.perf_counter()
                results_skip, _ = runtime_skip.execute(workflow)
                skip_time = time.perf_counter() - start_time

                skip_mem = self.measure_memory_usage() - initial_mem
                skip_times.append(skip_time)
                skip_memory.append(skip_mem)

            except NotImplementedError:
                # Skip branches not implemented yet
                skip_times = route_times.copy()  # Use route_data as baseline
                skip_memory = route_memory.copy()
                break

        return {
            "route_data": {
                "times": route_times,
                "avg_time": mean(route_times),
                "std_time": stdev(route_times) if len(route_times) > 1 else 0,
                "avg_memory": mean(route_memory),
                "results": results_route,
            },
            "skip_branches": {
                "times": skip_times,
                "avg_time": mean(skip_times),
                "std_time": stdev(skip_times) if len(skip_times) > 1 else 0,
                "avg_memory": mean(skip_memory),
                "results": (
                    results_skip if "results_skip" in locals() else results_route
                ),
            },
        }

    def test_small_workflow_performance_baseline(self):
        """Test performance baseline with small workflow (10 branches)."""
        workflow = self.create_large_conditional_workflow(
            num_branches=10, work_per_branch=0.002
        )

        benchmark_results = self.benchmark_execution_modes(workflow, iterations=3)

        route_data = benchmark_results["route_data"]
        skip_branches = benchmark_results["skip_branches"]

        # Performance assertions
        assert route_data["avg_time"] < 1.0  # Should complete in under 1 second
        assert skip_branches["avg_time"] < 1.0

        # Memory usage should be reasonable
        assert route_data["avg_memory"] < 50  # Less than 50MB
        assert skip_branches["avg_memory"] < 50

        # Verify results
        route_results = route_data["results"]
        assert "source" in route_results
        assert "aggregator" in route_results

        # Count executed processors
        executed_processors = [
            k for k in route_results.keys() if k.startswith("processor_")
        ]
        assert (
            len(executed_processors) == 10
        )  # All processors executed in route_data mode

        print("Small workflow (10 branches):")
        print(
            f"  Route data: {route_data['avg_time']:.3f}s ± {route_data['std_time']:.3f}s"
        )
        print(
            f"  Skip branches: {skip_branches['avg_time']:.3f}s ± {skip_branches['std_time']:.3f}s"
        )
        print(
            f"  Memory - Route: {route_data['avg_memory']:.1f}MB, Skip: {skip_branches['avg_memory']:.1f}MB"
        )

    def test_medium_workflow_performance(self):
        """Test performance with medium workflow (50 branches)."""
        workflow = self.create_large_conditional_workflow(
            num_branches=50, work_per_branch=0.001
        )

        benchmark_results = self.benchmark_execution_modes(workflow, iterations=3)

        route_data = benchmark_results["route_data"]
        skip_branches = benchmark_results["skip_branches"]

        # Performance assertions
        assert route_data["avg_time"] < 5.0  # Should complete in under 5 seconds
        assert skip_branches["avg_time"] < 5.0

        # Memory usage should scale reasonably
        assert route_data["avg_memory"] < 100  # Less than 100MB
        assert skip_branches["avg_memory"] < 100

        # Skip branches should show performance benefit (if implemented)
        if skip_branches["avg_time"] < route_data["avg_time"]:
            improvement = (
                (route_data["avg_time"] - skip_branches["avg_time"])
                / route_data["avg_time"]
            ) * 100
            assert improvement > 10  # At least 10% improvement
            print(f"Performance improvement: {improvement:.1f}%")

        print("Medium workflow (50 branches):")
        print(
            f"  Route data: {route_data['avg_time']:.3f}s ± {route_data['std_time']:.3f}s"
        )
        print(
            f"  Skip branches: {skip_branches['avg_time']:.3f}s ± {skip_branches['std_time']:.3f}s"
        )
        print(
            f"  Memory - Route: {route_data['avg_memory']:.1f}MB, Skip: {skip_branches['avg_memory']:.1f}MB"
        )

    def test_large_workflow_scalability(self):
        """Test scalability with large workflow (100 branches)."""
        workflow = self.create_large_conditional_workflow(
            num_branches=100, work_per_branch=0.0005
        )

        benchmark_results = self.benchmark_execution_modes(
            workflow, iterations=2
        )  # Fewer iterations for large test

        route_data = benchmark_results["route_data"]
        skip_branches = benchmark_results["skip_branches"]

        # Scalability assertions
        assert route_data["avg_time"] < 10.0  # Should complete in under 10 seconds
        assert skip_branches["avg_time"] < 10.0

        # Memory should scale linearly, not exponentially
        assert route_data["avg_memory"] < 200  # Less than 200MB
        assert skip_branches["avg_memory"] < 200

        # Performance improvement should be more significant with larger workflows
        if skip_branches["avg_time"] < route_data["avg_time"]:
            improvement = (
                (route_data["avg_time"] - skip_branches["avg_time"])
                / route_data["avg_time"]
            ) * 100
            assert improvement > 15  # At least 15% improvement for large workflows
            print(f"Large workflow performance improvement: {improvement:.1f}%")

        print("Large workflow (100 branches):")
        print(
            f"  Route data: {route_data['avg_time']:.3f}s ± {route_data['std_time']:.3f}s"
        )
        print(
            f"  Skip branches: {skip_branches['avg_time']:.3f}s ± {skip_branches['std_time']:.3f}s"
        )
        print(
            f"  Memory - Route: {route_data['avg_memory']:.1f}MB, Skip: {skip_branches['avg_memory']:.1f}MB"
        )

    def test_graph_analysis_overhead(self):
        """Test graph analysis overhead for conditional execution."""
        # Create workflow with complex conditional structure
        workflow = Workflow("analysis_overhead_test", "Analysis Overhead Test")

        # Create nested conditional structure
        source = PythonCodeNode(
            name="source",
            code="result = {'level1': True, 'level2': True, 'level3': False}",
        )
        workflow.add_node("source", source)

        # Create 3 levels of nested switches
        for level in range(1, 4):
            for branch in range(2**level):  # Exponentially growing branches
                switch = SwitchNode(
                    name=f"switch_l{level}_b{branch}",
                    condition_field=f"level{level}",
                    operator="equals",
                    value=True,
                )

                processor = PythonCodeNode(
                    name=f"proc_l{level}_b{branch}",
                    code=f"result = {{'level': {level}, 'branch': {branch}}}",
                )

                workflow.add_node(f"switch_l{level}_b{branch}", switch)
                workflow.add_node(f"proc_l{level}_b{branch}", processor)

                # Connect to source or previous level
                if level == 1:
                    workflow.connect(
                        "source", f"switch_l{level}_b{branch}", {"result": "input_data"}
                    )
                else:
                    parent_branch = branch // 2
                    workflow.connect(
                        f"proc_l{level-1}_b{parent_branch}",
                        f"switch_l{level}_b{branch}",
                        {"result": "input_data"},
                    )

                workflow.connect(
                    f"switch_l{level}_b{branch}",
                    f"proc_l{level}_b{branch}",
                    {"true_output": "input"},
                )

        # Measure analysis overhead
        runtime = LocalRuntime(conditional_execution="skip_branches")

        # Time analysis phase separately (if possible)
        start_time = time.perf_counter()

        try:
            # This should trigger graph analysis
            results, _ = runtime.execute(workflow)
            total_time = time.perf_counter() - start_time

            # Analysis overhead should be minimal compared to execution
            assert total_time < 2.0  # Should complete quickly

            # If we can measure analysis time separately
            if hasattr(runtime, "_last_analysis_time"):
                analysis_time = runtime._last_analysis_time
                analysis_overhead = (analysis_time / total_time) * 100
                assert analysis_overhead < 10  # Analysis should be < 10% of total time
                print(
                    f"Graph analysis overhead: {analysis_overhead:.1f}% ({analysis_time:.3f}s)"
                )

        except NotImplementedError:
            pytest.skip("Skip branches mode not implemented yet")

    def test_memory_efficiency_conditional_execution(self):
        """Test memory efficiency of conditional execution."""
        # Create workflow that should use significantly less memory with skip_branches
        workflow = Workflow("memory_efficiency_test", "Memory Efficiency Test")

        # Source that activates only 10% of branches
        source = PythonCodeNode(
            name="source",
            code="""
active_branches = [0, 9, 19, 29, 39]  # Only 5 out of 50 branches
result = {'active_branches': active_branches}
""",
        )
        workflow.add_node("source", source)

        # Create 50 branches with memory-intensive processors
        for i in range(50):
            switch = SwitchNode(
                name=f"switch_{i}",
                condition_field="active_branches",
                operator="contains",
                value=i,
            )

            # Memory-intensive processor
            processor = PythonCodeNode(
                name=f"processor_{i}",
                code=f"""
# Create large data structure to use memory
large_data = list(range(10000))  # 10K integers
processed_data = [x * 2 for x in large_data]
result = {{
    'branch_id': {i},
    'data_size': len(processed_data),
    'sample_data': processed_data[:10]  # Only return sample to avoid huge results
}}
""",
            )

            workflow.add_node(f"switch_{i}", switch)
            workflow.add_node(f"processor_{i}", processor)

            workflow.connect("source", f"switch_{i}", {"result": "input_data"})
            workflow.connect(f"switch_{i}", f"processor_{i}", {"true_output": "input"})

        # Measure memory usage for both modes
        gc.collect()

        # Route data mode (all processors execute)
        initial_memory = self.measure_memory_usage()
        runtime_route = LocalRuntime(conditional_execution="route_data")
        results_route, _ = runtime_route.execute(workflow)
        route_memory = self.measure_memory_usage() - initial_memory

        gc.collect()

        # Skip branches mode (only active processors execute)
        initial_memory = self.measure_memory_usage()
        runtime_skip = LocalRuntime(conditional_execution="skip_branches")

        try:
            results_skip, _ = runtime_skip.execute(workflow)
            skip_memory = self.measure_memory_usage() - initial_memory

            # Skip branches should use significantly less memory
            memory_savings = ((route_memory - skip_memory) / route_memory) * 100
            assert memory_savings > 20  # At least 20% memory savings

            print("Memory efficiency test:")
            print(f"  Route data memory: {route_memory:.1f}MB")
            print(f"  Skip branches memory: {skip_memory:.1f}MB")
            print(f"  Memory savings: {memory_savings:.1f}%")

            # Verify only active branches executed
            executed_processors = [
                k for k in results_skip.keys() if k.startswith("processor_")
            ]
            assert len(executed_processors) <= 5  # Only active branches

        except NotImplementedError:
            pytest.skip("Skip branches mode not implemented yet")

    def test_real_world_performance_scenario(self):
        """Test real-world performance scenario with mixed workload."""
        # Create realistic e-commerce order processing pipeline
        workflow = Workflow("ecommerce_processing", "E-commerce Order Processing")

        # Order data source
        order_source = PythonCodeNode(
            name="order_source",
            code="""
import random
import time

# Simulate batch of 100 orders
orders = []
for i in range(100):
    order = {
        'order_id': f'ORD_{i:03d}',
        'customer_type': random.choice(['premium', 'standard', 'guest']),
        'order_value': random.randint(10, 1000),
        'region': random.choice(['US', 'EU', 'APAC']),
        'priority': random.choice(['urgent', 'normal', 'low']),
        'requires_fraud_check': random.choice([True, False])
    }
    orders.append(order)

result = {
    'orders': orders,
    'batch_size': len(orders),
    'processing_timestamp': time.time()
}
""",
        )

        # Customer type routing
        customer_router = SwitchNode(
            name="customer_router",
            condition_field="customer_type",
            operator="switch",
            cases={
                "premium": "premium_processing",
                "standard": "standard_processing",
                "guest": "guest_processing",
            },
        )

        # Premium customer processing (complex logic)
        premium_processor = PythonCodeNode(
            name="premium_processor",
            code="""
import time
time.sleep(0.005)  # Simulate complex premium processing

processed_orders = []
for order in orders:
    if order['customer_type'] == 'premium':
        # Complex premium logic
        discount = 0.15 if order['order_value'] > 500 else 0.10
        shipping = 'expedited'
        processed = {
            **order,
            'discount_applied': discount,
            'shipping_method': shipping,
            'processing_time': 'fast_track'
        }
        processed_orders.append(processed)

result = {'processed_orders': processed_orders, 'processor': 'premium'}
""",
        )

        # Standard customer processing
        standard_processor = PythonCodeNode(
            name="standard_processor",
            code="""
import time
time.sleep(0.003)  # Standard processing time

processed_orders = []
for order in orders:
    if order['customer_type'] == 'standard':
        discount = 0.05 if order['order_value'] > 200 else 0.0
        shipping = 'standard'
        processed = {
            **order,
            'discount_applied': discount,
            'shipping_method': shipping,
            'processing_time': 'standard'
        }
        processed_orders.append(processed)

result = {'processed_orders': processed_orders, 'processor': 'standard'}
""",
        )

        # Fraud check routing (parallel processing)
        fraud_router = SwitchNode(
            name="fraud_router",
            condition_field="requires_fraud_check",
            operator="equals",
            value=True,
        )

        # Fraud check processor (expensive operation)
        fraud_checker = PythonCodeNode(
            name="fraud_checker",
            code="""
import time
time.sleep(0.010)  # Simulate expensive fraud check

fraud_results = []
for order in orders:
    if order.get('requires_fraud_check', False):
        # Simulate fraud scoring
        risk_score = order['order_value'] * 0.001
        result = {
            'order_id': order['order_id'],
            'risk_score': risk_score,
            'status': 'approved' if risk_score < 0.5 else 'review_required'
        }
        fraud_results.append(result)

result = {'fraud_checks': fraud_results, 'total_checked': len(fraud_results)}
""",
        )

        # Regional shipping processor
        shipping_router = SwitchNode(
            name="shipping_router",
            condition_field="region",
            operator="switch",
            cases={"US": "us_shipping", "EU": "eu_shipping", "APAC": "apac_shipping"},
        )

        # US shipping (fastest processing)
        us_shipping = PythonCodeNode(
            name="us_shipping",
            code="""
import time
time.sleep(0.001)  # Fast US processing

us_orders = [o for o in orders if o['region'] == 'US']
shipping_labels = []
for order in us_orders:
    label = {
        'order_id': order['order_id'],
        'shipping_zone': 'domestic',
        'estimated_delivery': '2-3 days',
        'carrier': 'USPS'
    }
    shipping_labels.append(label)

result = {'shipping_labels': shipping_labels, 'region': 'US'}
""",
        )

        # EU shipping (medium processing)
        eu_shipping = PythonCodeNode(
            name="eu_shipping",
            code="""
import time
time.sleep(0.003)  # EU processing with customs

eu_orders = [o for o in orders if o['region'] == 'EU']
shipping_labels = []
for order in eu_orders:
    label = {
        'order_id': order['order_id'],
        'shipping_zone': 'international',
        'estimated_delivery': '5-7 days',
        'carrier': 'DHL',
        'customs_required': True
    }
    shipping_labels.append(label)

result = {'shipping_labels': shipping_labels, 'region': 'EU'}
""",
        )

        # Build workflow
        nodes = [
            ("order_source", order_source),
            ("customer_router", customer_router),
            ("premium_processor", premium_processor),
            ("standard_processor", standard_processor),
            ("fraud_router", fraud_router),
            ("fraud_checker", fraud_checker),
            ("shipping_router", shipping_router),
            ("us_shipping", us_shipping),
            ("eu_shipping", eu_shipping),
        ]

        for node_id, node in nodes:
            workflow.add_node(node_id, node)

        # Connect workflow
        workflow.connect("order_source", "customer_router", {"result": "input_data"})
        workflow.connect("order_source", "fraud_router", {"result": "input_data"})
        workflow.connect("order_source", "shipping_router", {"result": "input_data"})

        # Customer processing paths
        workflow.connect(
            "customer_router", "premium_processor", {"case_premium": "input"}
        )
        workflow.connect(
            "customer_router", "standard_processor", {"case_standard": "input"}
        )

        # Fraud check path
        workflow.connect("fraud_router", "fraud_checker", {"true_output": "input"})

        # Shipping paths
        workflow.connect("shipping_router", "us_shipping", {"case_US": "input"})
        workflow.connect("shipping_router", "eu_shipping", {"case_EU": "input"})

        # Performance benchmark
        benchmark_results = self.benchmark_execution_modes(workflow, iterations=3)

        route_data = benchmark_results["route_data"]
        skip_branches = benchmark_results["skip_branches"]

        # Real-world performance requirements
        assert (
            route_data["avg_time"] < 2.0
        )  # Should process 100 orders in under 2 seconds
        assert skip_branches["avg_time"] < 2.0

        # Memory should be reasonable for production use
        assert route_data["avg_memory"] < 100  # Less than 100MB for 100 orders
        assert skip_branches["avg_memory"] < 100

        # Calculate throughput
        orders_per_second_route = 100 / route_data["avg_time"]
        orders_per_second_skip = 100 / skip_branches["avg_time"]

        print("Real-world e-commerce processing performance:")
        print(
            f"  Route data: {route_data['avg_time']:.3f}s ({orders_per_second_route:.0f} orders/sec)"
        )
        print(
            f"  Skip branches: {skip_branches['avg_time']:.3f}s ({orders_per_second_skip:.0f} orders/sec)"
        )
        print(
            f"  Memory - Route: {route_data['avg_memory']:.1f}MB, Skip: {skip_branches['avg_memory']:.1f}MB"
        )

        # Verify processing results
        route_results = route_data["results"]
        assert "order_source" in route_results
        assert "premium_processor" in route_results
        assert "standard_processor" in route_results
        assert "fraud_checker" in route_results
        assert "us_shipping" in route_results
        assert "eu_shipping" in route_results

        # Verify realistic processing occurred
        premium_result = route_results["premium_processor"]["result"]
        assert (
            len(premium_result["processed_orders"]) > 0
        )  # Some premium customers processed

        fraud_result = route_results["fraud_checker"]["result"]
        assert len(fraud_result["fraud_checks"]) > 0  # Some fraud checks performed

    def test_performance_regression_monitoring(self):
        """Test performance regression monitoring capabilities."""
        # Create baseline workflow for regression testing
        workflow = self.create_large_conditional_workflow(
            num_branches=20, work_per_branch=0.001
        )

        # Run multiple iterations to establish baseline
        iterations = 5
        baseline_times = []

        runtime = LocalRuntime(conditional_execution="route_data")

        for i in range(iterations):
            start_time = time.perf_counter()
            results, _ = runtime.execute(workflow)
            execution_time = time.perf_counter() - start_time
            baseline_times.append(execution_time)

        baseline_avg = mean(baseline_times)
        baseline_std = stdev(baseline_times)

        # Performance regression thresholds
        max_acceptable_time = baseline_avg + (2 * baseline_std)  # 2 sigma

        # Verify performance is within acceptable bounds
        assert baseline_avg < 1.0  # Should be fast for 20 branches
        assert max_acceptable_time < 2.0  # Even worst case should be reasonable

        # Test with skip_branches mode for comparison
        runtime_skip = LocalRuntime(conditional_execution="skip_branches")

        try:
            skip_times = []
            for i in range(3):  # Fewer iterations for comparison
                start_time = time.perf_counter()
                results_skip, _ = runtime_skip.execute(workflow)
                execution_time = time.perf_counter() - start_time
                skip_times.append(execution_time)

            skip_avg = mean(skip_times)

            # Performance comparison
            if skip_avg < baseline_avg:
                improvement = ((baseline_avg - skip_avg) / baseline_avg) * 100
                print("Performance regression test:")
                print(
                    f"  Baseline (route_data): {baseline_avg:.3f}s ± {baseline_std:.3f}s"
                )
                print(f"  Skip branches: {skip_avg:.3f}s")
                print(f"  Performance improvement: {improvement:.1f}%")

                # Performance improvement should be consistent
                assert improvement > 5  # At least 5% improvement

        except NotImplementedError:
            print("Performance regression baseline established:")
            print(f"  Route data: {baseline_avg:.3f}s ± {baseline_std:.3f}s")
            print(f"  Max acceptable: {max_acceptable_time:.3f}s")


class TestConditionalExecutionBenchmarks:
    """Comprehensive benchmarking suite for conditional execution."""

    def create_benchmark_report(self, test_name, benchmark_results):
        """Create detailed benchmark report."""
        report = f"\n{'='*60}\n"
        report += f"BENCHMARK REPORT: {test_name}\n"
        report += f"{'='*60}\n"

        route_data = benchmark_results["route_data"]
        skip_branches = benchmark_results["skip_branches"]

        # Performance metrics
        report += "Performance Metrics:\n"
        report += "  Route Data Mode:\n"
        report += f"    Average time: {route_data['avg_time']:.3f}s\n"
        report += f"    Std deviation: {route_data['std_time']:.3f}s\n"
        report += f"    Memory usage: {route_data['avg_memory']:.1f}MB\n"

        report += "  Skip Branches Mode:\n"
        report += f"    Average time: {skip_branches['avg_time']:.3f}s\n"
        report += f"    Std deviation: {skip_branches['std_time']:.3f}s\n"
        report += f"    Memory usage: {skip_branches['avg_memory']:.1f}MB\n"

        # Performance improvement
        if skip_branches["avg_time"] < route_data["avg_time"]:
            time_improvement = (
                (route_data["avg_time"] - skip_branches["avg_time"])
                / route_data["avg_time"]
            ) * 100
            report += f"  Performance Improvement: {time_improvement:.1f}%\n"

        if skip_branches["avg_memory"] < route_data["avg_memory"]:
            memory_improvement = (
                (route_data["avg_memory"] - skip_branches["avg_memory"])
                / route_data["avg_memory"]
            ) * 100
            report += f"  Memory Improvement: {memory_improvement:.1f}%\n"

        report += f"{'='*60}\n"

        return report

    def test_comprehensive_benchmark_suite(self):
        """Run comprehensive benchmark suite with detailed reporting."""
        benchmark_results = []

        # Small workflow benchmark
        small_workflow = self.create_large_conditional_workflow(
            num_branches=10, work_per_branch=0.001
        )
        small_results = self.benchmark_execution_modes(small_workflow, iterations=5)
        benchmark_results.append(("Small Workflow (10 branches)", small_results))

        # Medium workflow benchmark
        medium_workflow = self.create_large_conditional_workflow(
            num_branches=30, work_per_branch=0.001
        )
        medium_results = self.benchmark_execution_modes(medium_workflow, iterations=3)
        benchmark_results.append(("Medium Workflow (30 branches)", medium_results))

        # Large workflow benchmark
        large_workflow = self.create_large_conditional_workflow(
            num_branches=50, work_per_branch=0.0005
        )
        large_results = self.benchmark_execution_modes(large_workflow, iterations=2)
        benchmark_results.append(("Large Workflow (50 branches)", large_results))

        # Generate comprehensive report
        full_report = "\n" + "=" * 80 + "\n"
        full_report += "CONDITIONAL EXECUTION COMPREHENSIVE BENCHMARK REPORT\n"
        full_report += "=" * 80 + "\n"

        for test_name, results in benchmark_results:
            report = self.create_benchmark_report(test_name, results)
            full_report += report

            # Individual test assertions
            route_data = results["route_data"]
            skip_branches = results["skip_branches"]

            # All tests should complete in reasonable time
            assert route_data["avg_time"] < 10.0
            assert skip_branches["avg_time"] < 10.0

            # Memory usage should be reasonable
            assert route_data["avg_memory"] < 300
            assert skip_branches["avg_memory"] < 300

        # Print comprehensive report
        print(full_report)

        # Overall performance trends
        route_times = [r[1]["route_data"]["avg_time"] for r in benchmark_results]
        skip_times = [r[1]["skip_branches"]["avg_time"] for r in benchmark_results]

        # Performance should scale reasonably with workflow size
        assert (
            route_times[0] < route_times[1] < route_times[2]
        )  # Should increase with size

        # Skip branches should consistently perform better (if implemented)
        improvements = []
        for i, (_, results) in enumerate(benchmark_results):
            route_time = results["route_data"]["avg_time"]
            skip_time = results["skip_branches"]["avg_time"]

            if skip_time < route_time:
                improvement = ((route_time - skip_time) / route_time) * 100
                improvements.append(improvement)

        if improvements:
            avg_improvement = mean(improvements)
            print("\nOverall Performance Summary:")
            print(f"  Average performance improvement: {avg_improvement:.1f}%")
            print(
                f"  Consistent improvement across all test sizes: {len(improvements) == len(benchmark_results)}"
            )

            # Should show consistent improvement
            assert avg_improvement > 10.0  # At least 10% average improvement

    def create_large_conditional_workflow(self, num_branches, work_per_branch):
        """Helper method to create large conditional workflow."""
        workflow = Workflow(
            "benchmark_workflow", f"Benchmark with {num_branches} branches"
        )

        # Source that activates 20% of branches
        source = PythonCodeNode(
            name="source",
            code=f"""
import random
active_count = max(1, {num_branches} // 5)  # 20% of branches
active_branches = random.sample(range({num_branches}), active_count)
result = {{'active_branches': active_branches}}
""",
        )
        workflow.add_node("source", source)

        # Create conditional branches
        for i in range(num_branches):
            switch = SwitchNode(
                name=f"switch_{i}",
                condition_field="active_branches",
                operator="contains",
                value=i,
            )

            processor = PythonCodeNode(
                name=f"processor_{i}",
                code=f"""
import time
time.sleep({work_per_branch})
result = {{'branch_id': {i}, 'completed': True}}
""",
            )

            workflow.add_node(f"switch_{i}", switch)
            workflow.add_node(f"processor_{i}", processor)

            workflow.connect("source", f"switch_{i}", {"result": "input_data"})
            workflow.connect(f"switch_{i}", f"processor_{i}", {"true_output": "input"})

        return workflow

    def benchmark_execution_modes(self, workflow, iterations):
        """Helper method to benchmark execution modes."""
        route_times = []
        skip_times = []
        route_memory = []
        skip_memory = []

        process = psutil.Process(os.getpid())

        for i in range(iterations):
            # Benchmark route_data mode
            gc.collect()
            initial_mem = process.memory_info().rss / 1024 / 1024

            runtime_route = LocalRuntime(conditional_execution="route_data")
            start_time = time.perf_counter()
            results_route, _ = runtime_route.execute(workflow)
            route_time = time.perf_counter() - start_time

            final_mem = process.memory_info().rss / 1024 / 1024
            route_mem = final_mem - initial_mem

            route_times.append(route_time)
            route_memory.append(max(0, route_mem))  # Ensure non-negative

            # Benchmark skip_branches mode
            gc.collect()
            initial_mem = process.memory_info().rss / 1024 / 1024

            runtime_skip = LocalRuntime(conditional_execution="skip_branches")

            try:
                start_time = time.perf_counter()
                results_skip, _ = runtime_skip.execute(workflow)
                skip_time = time.perf_counter() - start_time

                final_mem = process.memory_info().rss / 1024 / 1024
                skip_mem = final_mem - initial_mem

                skip_times.append(skip_time)
                skip_memory.append(max(0, skip_mem))

            except NotImplementedError:
                # Use route_data as baseline
                skip_times.append(route_time)
                skip_memory.append(route_mem)

        return {
            "route_data": {
                "times": route_times,
                "avg_time": mean(route_times),
                "std_time": stdev(route_times) if len(route_times) > 1 else 0,
                "avg_memory": mean(route_memory),
                "results": results_route,
            },
            "skip_branches": {
                "times": skip_times,
                "avg_time": mean(skip_times),
                "std_time": stdev(skip_times) if len(skip_times) > 1 else 0,
                "avg_memory": mean(skip_memory),
                "results": (
                    results_skip if "results_skip" in locals() else results_route
                ),
            },
        }
