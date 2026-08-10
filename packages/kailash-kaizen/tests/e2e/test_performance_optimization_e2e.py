"""
Tier 3 (E2E) Performance Tests for PERF-001: Performance Crisis Resolution

These tests validate complete end-to-end performance scenarios that represent
real-world developer and production usage patterns.

E2E Performance Requirements:
- Complete development workflow: Import → Create → Execute < 3000ms
- Production deployment scenario: Framework ready for use < 2000ms
- Developer experience: Interactive development workflow < 1500ms
- Enterprise production load: Sustained performance under realistic loads

Test Strategy:
- Complete user workflows from start to finish
- Real infrastructure and data (no mocking)
- Test actual user scenarios and expectations
- Validate business requirements end-to-end
- Performance regression prevention for real-world usage
"""

import gc

# Core SDK imports for E2E testing
import os
import sys
import time

import psutil

# Ensure SDK is in path for testing
sdk_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
if sdk_root not in sys.path:
    sys.path.insert(0, sdk_root)

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestCompleteDevWorkflowPerformance:
    """End-to-end developer workflow performance validation."""

    def setup_method(self):
        """Setup for E2E tests with completely clean environment."""
        # Clear all kaizen-related imports
        modules_to_remove = [
            key for key in sys.modules.keys() if key.startswith("kaizen")
        ]
        for module in modules_to_remove:
            if module in sys.modules:
                del sys.modules[module]
        gc.collect()

    def test_complete_development_workflow_performance(self):
        """
        Complete development workflow: Import → Create → Execute

        This represents the critical path that developers experience:
        1. Import kaizen (must be <100ms)
        2. Create framework and agent (must be fast)
        3. Build and execute workflow (must work efficiently)

        Target: Complete workflow < 3000ms for good developer experience
        """
        workflow_start_time = time.perf_counter()

        # Step 1: Import kaizen (optimized import)
        import_start = time.perf_counter()
        import kaizen

        import_duration = (time.perf_counter() - import_start) * 1000

        # Step 2: Create framework and agent
        creation_start = time.perf_counter()
        framework = kaizen.Kaizen()
        framework.create_agent("dev_workflow_agent", {"model": "gpt-4"})
        creation_duration = (time.perf_counter() - creation_start) * 1000

        # Step 3: Build workflow with Core SDK
        build_start = time.perf_counter()
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "dev_processor",
            {
                "code": """
result = {
    'message': f'Hello from development workflow!',
    'input_received': input_data,
    'processed_at': str(time.time()),
    'workflow_type': 'development'
}
                """.strip(),
                "input_schema": {"input_data": "dict"},
                "output_schema": {"result": "dict"},
            },
        )
        built_workflow = workflow.build()
        build_duration = (time.perf_counter() - build_start) * 1000

        # Step 4: Execute workflow
        execution_start = time.perf_counter()
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            built_workflow,
            inputs={"input_data": {"developer": "testing", "framework": "kaizen"}},
        )
        execution_duration = (time.perf_counter() - execution_start) * 1000

        total_workflow_duration = (time.perf_counter() - workflow_start_time) * 1000

        # Verify complete workflow success
        assert results is not None, "Development workflow must produce results"
        assert run_id is not None, "Development workflow must return run_id"
        assert "dev_processor" in results, "Workflow must execute dev_processor node"

        # Performance assertions for each step
        assert import_duration < 100, (
            f"Import too slow for development: {import_duration:.1f}ms "
            f"(target: <100ms). Poor import performance hurts developer experience."
        )

        assert creation_duration < 500, (
            f"Framework/agent creation too slow: {creation_duration:.1f}ms "
            f"(target: <500ms). Developers need quick feedback."
        )

        assert build_duration < 1000, (
            f"Workflow building too slow: {build_duration:.1f}ms "
            f"(target: <1000ms). Interactive development requires fast builds."
        )

        assert execution_duration < 1500, (
            f"Workflow execution too slow: {execution_duration:.1f}ms "
            f"(target: <1500ms). Simple workflows must execute quickly."
        )

        # CRITICAL E2E ASSERTION: Total developer workflow performance
        assert total_workflow_duration < 3000, (
            f"Complete development workflow too slow: {total_workflow_duration:.1f}ms "
            f"(target: <3000ms). Developer experience requires fast end-to-end workflow.\n"
            f"Performance breakdown:\n"
            f"  - Import: {import_duration:.1f}ms\n"
            f"  - Creation: {creation_duration:.1f}ms\n"
            f"  - Build: {build_duration:.1f}ms\n"
            f"  - Execution: {execution_duration:.1f}ms"
        )

    def test_interactive_development_cycle_performance(self):
        """
        Interactive development cycle: Multiple iterations with same framework.

        Represents realistic development where developer keeps framework instance
        and creates multiple agents/workflows iteratively.

        Target: Each iteration < 1500ms after initial setup
        """
        import kaizen

        # Initial setup (one-time cost)
        setup_start = time.perf_counter()
        framework = kaizen.Kaizen()
        runtime = LocalRuntime()
        setup_duration = (time.perf_counter() - setup_start) * 1000

        iteration_times = []

        # Simulate 5 development iterations
        for iteration in range(5):
            iteration_start = time.perf_counter()

            # Create new agent for this iteration
            framework.create_agent(f"iteration_agent_{iteration}", {"model": "gpt-4"})

            # Build workflow for this iteration
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode",
                f"iteration_processor_{iteration}",
                {
                    "code": f"""
result = {{
    'iteration': {iteration},
    'message': f'Development iteration {{input_data.get("cycle", "unknown")}}',
    'timestamp': time.time()
}}
                    """.strip(),
                    "input_schema": {"input_data": "dict"},
                    "output_schema": {"result": "dict"},
                },
            )

            # Execute workflow
            results, run_id = runtime.execute(
                workflow.build(), inputs={"input_data": {"cycle": iteration}}
            )

            iteration_duration = (time.perf_counter() - iteration_start) * 1000
            iteration_times.append(iteration_duration)

            # Verify iteration success
            assert results is not None, f"Iteration {iteration} must succeed"
            assert (
                f"iteration_processor_{iteration}" in results
            ), f"Iteration {iteration} processor must execute"

        # Performance analysis
        avg_iteration_time = sum(iteration_times) / len(iteration_times)
        max_iteration_time = max(iteration_times)
        min_iteration_time = min(iteration_times)

        # ASSERTIONS: Interactive development performance
        assert setup_duration < 1000, (
            f"Initial setup too slow for interactive development: {setup_duration:.1f}ms "
            f"(target: <1000ms)"
        )

        assert avg_iteration_time < 1500, (
            f"Average iteration too slow: {avg_iteration_time:.1f}ms "
            f"(target: <1500ms). Interactive development needs fast iterations."
        )

        assert max_iteration_time < 2000, (
            f"Slowest iteration too slow: {max_iteration_time:.1f}ms "
            f"(target: <2000ms). All iterations must be reasonably fast."
        )

        # Performance consistency check
        variation = max_iteration_time - min_iteration_time
        assert variation < 500, (
            f"Iteration performance too variable: {variation:.1f}ms difference "
            f"(target: <500ms). Interactive performance should be consistent."
        )

    def test_cold_start_vs_warm_development_performance(self):
        """
        Compare cold start vs warm development performance.

        Cold start: First import and framework creation
        Warm: Subsequent operations with framework already loaded

        This validates caching and optimization effectiveness.
        """
        # Cold start measurement
        cold_start_time = time.perf_counter()
        import kaizen

        framework = kaizen.Kaizen()
        framework.create_agent("cold_start_agent", {"model": "gpt-4"})

        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "cold_start_processor",
            {
                "code": "result = {'cold_start': True, 'data': input_data}",
                "input_schema": {"input_data": "dict"},
                "output_schema": {"result": "dict"},
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow.build(), inputs={"input_data": {"test": "cold_start"}}
        )

        cold_start_duration = (time.perf_counter() - cold_start_time) * 1000

        # Warm operations (framework already loaded)
        warm_start_time = time.perf_counter()
        framework.create_agent("warm_agent", {"model": "gpt-4"})

        warm_workflow = WorkflowBuilder()
        warm_workflow.add_node(
            "PythonCodeNode",
            "warm_processor",
            {
                "code": "result = {'warm_start': True, 'data': input_data}",
                "input_schema": {"input_data": "dict"},
                "output_schema": {"result": "dict"},
            },
        )

        warm_results, warm_run_id = runtime.execute(
            warm_workflow.build(), inputs={"input_data": {"test": "warm_start"}}
        )

        warm_duration = (time.perf_counter() - warm_start_time) * 1000

        # Verify both operations succeeded
        assert (
            results is not None and warm_results is not None
        ), "Both operations must succeed"

        # Performance comparison
        performance_improvement = (
            (cold_start_duration - warm_duration) / cold_start_duration
        ) * 100

        # ASSERTIONS: Cold vs warm performance
        assert cold_start_duration < 3000, (
            f"Cold start too slow: {cold_start_duration:.1f}ms "
            f"(target: <3000ms). First-time usage must be acceptable."
        )

        assert warm_duration < 1500, (
            f"Warm operations too slow: {warm_duration:.1f}ms "
            f"(target: <1500ms). Subsequent operations should be faster."
        )

        # Document performance characteristics
        print("\nCold vs Warm Performance Analysis:")
        print(f"  Cold start: {cold_start_duration:.1f}ms")
        print(f"  Warm operations: {warm_duration:.1f}ms")
        print(f"  Performance improvement: {performance_improvement:.1f}%")


class TestProductionDeploymentPerformance:
    """Production deployment scenario performance validation."""

    def test_production_framework_initialization_performance(self):
        """
        Production deployment scenario: Framework ready for production use.

        Simulates server startup where Kaizen framework must be ready quickly
        for incoming requests.

        Target: Production-ready framework < 2000ms
        """
        # Simulate clean production environment
        modules_to_remove = [
            key for key in sys.modules.keys() if key.startswith("kaizen")
        ]
        for module in modules_to_remove:
            if module in sys.modules:
                del sys.modules[module]
        gc.collect()

        production_start = time.perf_counter()

        # Production framework initialization
        import kaizen

        # Production configuration
        production_config = {
            "signature_programming_enabled": True,
            "memory_system_enabled": True,
            "auto_optimization_enabled": True,
            "enterprise_features_enabled": True,
            "production_mode": True,  # If supported
        }

        framework = kaizen.Kaizen(config=production_config)

        # Create pool of agents for production (typical setup)
        agent_pool = []
        for i in range(10):  # Typical production agent pool
            agent = framework.create_agent(f"prod_agent_{i}", {"model": "gpt-4"})
            agent_pool.append(agent)

        # Pre-build common workflows (production optimization)
        common_workflows = []
        workflow_templates = [
            ("data_processor", "result = {'processed': input_data}"),
            ("validator", "result = {'valid': True, 'data': input_data}"),
            ("transformer", "result = {'transformed': input_data}"),
        ]

        for name, code in workflow_templates:
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode",
                name,
                {
                    "code": code,
                    "input_schema": {"input_data": "dict"},
                    "output_schema": {"result": "dict"},
                },
            )
            common_workflows.append(workflow.build())

        # Initialize runtime
        runtime = LocalRuntime()

        production_ready_duration = (time.perf_counter() - production_start) * 1000

        # Verify production setup
        assert framework is not None, "Production framework must be initialized"
        assert len(agent_pool) == 10, "Production agent pool must be ready"
        assert len(common_workflows) == 3, "Common workflows must be pre-built"
        assert runtime is not None, "Production runtime must be ready"

        # CRITICAL PRODUCTION ASSERTION
        assert production_ready_duration < 2000, (
            f"Production deployment too slow: {production_ready_duration:.1f}ms "
            f"(target: <2000ms). Production servers need fast startup times."
        )

    def test_production_load_handling_performance(self):
        """
        Production load handling: Sustained performance under realistic load.

        Simulates production scenario with multiple concurrent requests
        and sustained throughput requirements.

        Target: Maintain performance under production load
        """
        import concurrent.futures

        import kaizen

        # Production framework setup
        framework = kaizen.Kaizen(config={"enterprise_features_enabled": True})
        runtime = LocalRuntime()

        # Pre-build production workflow
        production_workflow = WorkflowBuilder()
        production_workflow.add_node(
            "PythonCodeNode",
            "production_processor",
            {
                "code": """
import time
result = {
    'request_id': input_data.get('request_id'),
    'processed_at': time.time(),
    'status': 'success',
    'data': input_data.get('payload', {})
}
                """.strip(),
                "input_schema": {"input_data": "dict"},
                "output_schema": {"result": "dict"},
            },
        )
        built_workflow = production_workflow.build()

        def process_production_request(request_id):
            """Process a single production request."""
            start_time = time.perf_counter()

            # Create agent for request (production pattern)
            framework.create_agent(f"req_agent_{request_id}", {"model": "gpt-4"})

            # Execute workflow
            results, run_id = runtime.execute(
                built_workflow,
                inputs={
                    "input_data": {
                        "request_id": request_id,
                        "payload": {"data": f"request_{request_id}"},
                    }
                },
            )

            duration = (time.perf_counter() - start_time) * 1000
            return results, duration, request_id

        # Simulate production load with concurrent requests
        load_start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # Submit 50 concurrent requests (realistic production load)
            futures = [
                executor.submit(process_production_request, i) for i in range(50)
            ]
            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        total_load_duration = (time.perf_counter() - load_start) * 1000

        # Analyze results
        successful_requests = [r for r in results if r[0] is not None]
        request_durations = [r[1] for r in results]

        avg_request_duration = sum(request_durations) / len(request_durations)
        max_request_duration = max(request_durations)
        min(request_durations)
        requests_per_second = len(results) / (total_load_duration / 1000)

        # Verify production load handling
        assert len(successful_requests) == 50, "All production requests must succeed"

        # PRODUCTION PERFORMANCE ASSERTIONS
        assert avg_request_duration < 2000, (
            f"Average request duration too slow: {avg_request_duration:.1f}ms "
            f"(target: <2000ms). Production requests must be processed quickly."
        )

        assert max_request_duration < 5000, (
            f"Slowest request too slow: {max_request_duration:.1f}ms "
            f"(target: <5000ms). Even worst-case requests must be reasonable."
        )

        assert requests_per_second > 5, (
            f"Throughput too low: {requests_per_second:.1f} req/s "
            f"(target: >5 req/s). Production systems need adequate throughput."
        )

        assert total_load_duration < 30000, (
            f"Total load processing too slow: {total_load_duration:.1f}ms "
            f"(target: <30000ms). 50 concurrent requests should complete quickly."
        )

    def test_production_memory_stability(self):
        """
        Production memory stability: Memory usage under sustained load.

        Critical for production deployment - memory leaks or excessive growth
        can cause production outages.

        Target: Stable memory usage under sustained production load
        """
        import kaizen

        process = psutil.Process()
        kaizen.Kaizen(config={"enterprise_features_enabled": True})
        runtime = LocalRuntime()

        # Production workflow template
        workflow_template = WorkflowBuilder()
        workflow_template.add_node(
            "PythonCodeNode",
            "memory_stable_processor",
            {
                "code": """
result = {
    'batch': input_data.get('batch', 0),
    'processed_items': input_data.get('items', []),
    'memory_test': 'x' * 100  # Small memory allocation
}
                """.strip(),
                "input_schema": {"input_data": "dict"},
                "output_schema": {"result": "dict"},
            },
        )

        # Measure memory at different stages
        gc.collect()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        memory_measurements = []

        # Sustained production simulation (10 batches of 20 requests each)
        for batch in range(10):
            batch_start_memory = process.memory_info().rss / 1024 / 1024

            # Process batch of requests
            for item in range(20):
                results, run_id = runtime.execute(
                    workflow_template.build(),
                    inputs={
                        "input_data": {
                            "batch": batch,
                            "items": [f"item_{i}" for i in range(item + 1)],
                        }
                    },
                )
                assert results is not None, f"Batch {batch} item {item} must succeed"

            # Cleanup and measure
            gc.collect()
            batch_end_memory = process.memory_info().rss / 1024 / 1024
            memory_measurements.append((batch, batch_start_memory, batch_end_memory))

        final_memory = process.memory_info().rss / 1024 / 1024
        total_memory_growth = final_memory - initial_memory

        # Analyze memory stability
        batch_growths = [end - start for _, start, end in memory_measurements]
        max_batch_growth = max(batch_growths) if batch_growths else 0
        avg_batch_growth = (
            sum(batch_growths) / len(batch_growths) if batch_growths else 0
        )

        # CRITICAL PRODUCTION MEMORY ASSERTIONS
        assert total_memory_growth < 100, (
            f"Total memory growth too high: {total_memory_growth:.1f}MB "
            f"(target: <100MB). Production systems must have stable memory usage."
        )

        assert max_batch_growth < 20, (
            f"Maximum batch memory growth too high: {max_batch_growth:.1f}MB "
            f"(target: <20MB). Individual batches should not cause memory spikes."
        )

        assert avg_batch_growth < 5, (
            f"Average batch memory growth too high: {avg_batch_growth:.1f}MB "
            f"(target: <5MB). Sustained processing should not leak memory."
        )

        # Log memory analysis for debugging
        print("\nProduction Memory Stability Analysis:")
        print(f"  Initial memory: {initial_memory:.1f}MB")
        print(f"  Final memory: {final_memory:.1f}MB")
        print(f"  Total growth: {total_memory_growth:.1f}MB")
        print(f"  Average batch growth: {avg_batch_growth:.1f}MB")
        print(f"  Maximum batch growth: {max_batch_growth:.1f}MB")


class TestRealWorldUsageScenarios:
    """Real-world usage scenario performance validation."""

    def test_enterprise_multi_tenant_performance(self):
        """
        Enterprise multi-tenant scenario: Multiple isolated framework instances.

        Common in enterprise deployments where multiple tenants/customers
        share the same infrastructure but need isolated processing.

        Target: Multiple tenants with independent performance
        """
        import kaizen

        # Simulate 5 enterprise tenants
        tenant_configs = [
            {"tenant_id": "tenant_a", "signature_programming_enabled": True},
            {"tenant_id": "tenant_b", "memory_system_enabled": True},
            {"tenant_id": "tenant_c", "auto_optimization_enabled": True},
            {"tenant_id": "tenant_d", "enterprise_features_enabled": True},
            {
                "tenant_id": "tenant_e",
                "signature_programming_enabled": True,
                "enterprise_features_enabled": True,
            },
        ]

        tenant_start_time = time.perf_counter()

        # Create isolated frameworks for each tenant
        tenant_frameworks = {}
        tenant_agents = {}
        tenant_runtimes = {}

        for config in tenant_configs:
            tenant_id = config["tenant_id"]

            # Create isolated framework
            framework = kaizen.Kaizen(config=config)
            tenant_frameworks[tenant_id] = framework

            # Create tenant-specific agents
            agents = []
            for i in range(3):  # 3 agents per tenant
                agent = framework.create_agent(
                    f"{tenant_id}_agent_{i}", {"model": "gpt-4"}
                )
                agents.append(agent)
            tenant_agents[tenant_id] = agents

            # Create tenant runtime
            tenant_runtimes[tenant_id] = LocalRuntime()

        tenant_setup_duration = (time.perf_counter() - tenant_start_time) * 1000

        # Test concurrent tenant operations
        def process_tenant_workload(tenant_id):
            """Process workload for specific tenant."""
            start_time = time.perf_counter()

            tenant_frameworks[tenant_id]
            runtime = tenant_runtimes[tenant_id]

            # Build tenant-specific workflow
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode",
                f"{tenant_id}_processor",
                {
                    "code": f"""
result = {{
    'tenant_id': '{tenant_id}',
    'processed_data': input_data,
    'timestamp': time.time(),
    'isolation_verified': True
}}
                    """.strip(),
                    "input_schema": {"input_data": "dict"},
                    "output_schema": {"result": "dict"},
                },
            )

            # Execute tenant workflow
            results, run_id = runtime.execute(
                workflow.build(), inputs={"input_data": {"tenant_request": tenant_id}}
            )

            duration = (time.perf_counter() - start_time) * 1000
            return tenant_id, results, duration

        # Process all tenants concurrently
        import concurrent.futures

        concurrent_start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            tenant_futures = [
                executor.submit(process_tenant_workload, config["tenant_id"])
                for config in tenant_configs
            ]
            tenant_results = [
                future.result()
                for future in concurrent.futures.as_completed(tenant_futures)
            ]

        concurrent_duration = (time.perf_counter() - concurrent_start) * 1000

        # Verify multi-tenant performance
        successful_tenants = [r for r in tenant_results if r[1] is not None]
        tenant_durations = [r[2] for r in tenant_results]

        avg_tenant_duration = sum(tenant_durations) / len(tenant_durations)
        max_tenant_duration = max(tenant_durations)

        # MULTI-TENANT PERFORMANCE ASSERTIONS
        assert len(successful_tenants) == 5, "All tenant workloads must succeed"

        assert tenant_setup_duration < 10000, (
            f"Multi-tenant setup too slow: {tenant_setup_duration:.1f}ms "
            f"(target: <10000ms). Enterprise deployment needs reasonable setup time."
        )

        assert avg_tenant_duration < 3000, (
            f"Average tenant processing too slow: {avg_tenant_duration:.1f}ms "
            f"(target: <3000ms). Each tenant must have good performance."
        )

        assert max_tenant_duration < 5000, (
            f"Slowest tenant too slow: {max_tenant_duration:.1f}ms "
            f"(target: <5000ms). No tenant should have poor performance."
        )

        assert concurrent_duration < 8000, (
            f"Concurrent tenant processing too slow: {concurrent_duration:.1f}ms "
            f"(target: <8000ms). Multi-tenant concurrency must be efficient."
        )

    def test_developer_productivity_workflow(self):
        """
        Developer productivity workflow: Realistic development session.

        Simulates a developer working on multiple features, testing,
        and iterating - the complete development experience.

        Target: Productive development experience with fast feedback loops
        """
        import kaizen

        productivity_start = time.perf_counter()

        # Developer session setup
        framework = kaizen.Kaizen()
        runtime = LocalRuntime()

        # Phase 1: Initial development (create multiple features)
        phase1_start = time.perf_counter()
        feature_agents = {}
        feature_workflows = {}

        features = ["user_auth", "data_processing", "reporting", "notifications"]
        for feature in features:
            # Create feature agent
            agent = framework.create_agent(f"{feature}_agent", {"model": "gpt-4"})
            feature_agents[feature] = agent

            # Build feature workflow
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode",
                f"{feature}_logic",
                {
                    "code": f"""
result = {{
    'feature': '{feature}',
    'status': 'implemented',
    'data': input_data,
    'version': '1.0'
}}
                    """.strip(),
                    "input_schema": {"input_data": "dict"},
                    "output_schema": {"result": "dict"},
                },
            )
            feature_workflows[feature] = workflow.build()

        phase1_duration = (time.perf_counter() - phase1_start) * 1000

        # Phase 2: Testing phase (run all features)
        phase2_start = time.perf_counter()
        test_results = {}

        for feature in features:
            results, run_id = runtime.execute(
                feature_workflows[feature],
                inputs={"input_data": {"test": True, "feature": feature}},
            )
            test_results[feature] = results

        phase2_duration = (time.perf_counter() - phase2_start) * 1000

        # Phase 3: Iteration phase (modify and re-test)
        phase3_start = time.perf_counter()

        # Simulate developer making changes to 2 features
        iteration_features = ["user_auth", "data_processing"]
        for feature in iteration_features:
            # Create updated workflow
            updated_workflow = WorkflowBuilder()
            updated_workflow.add_node(
                "PythonCodeNode",
                f"{feature}_logic_v2",
                {
                    "code": f"""
result = {{
    'feature': '{feature}',
    'status': 'updated',
    'data': input_data,
    'version': '2.0',
    'improvements': ['performance', 'reliability']
}}
                    """.strip(),
                    "input_schema": {"input_data": "dict"},
                    "output_schema": {"result": "dict"},
                },
            )

            # Test updated workflow
            updated_results, updated_run_id = runtime.execute(
                updated_workflow.build(),
                inputs={"input_data": {"iteration": True, "feature": feature}},
            )
            test_results[f"{feature}_v2"] = updated_results

        phase3_duration = (time.perf_counter() - phase3_start) * 1000
        total_productivity_duration = (time.perf_counter() - productivity_start) * 1000

        # Verify development session success
        assert len(feature_agents) == 4, "All feature agents must be created"
        assert len(feature_workflows) == 4, "All feature workflows must be built"
        assert len(test_results) == 6, "All tests (original + iterations) must complete"

        # Verify all tests passed
        for feature, results in test_results.items():
            assert results is not None, f"Feature {feature} test must succeed"

        # DEVELOPER PRODUCTIVITY ASSERTIONS
        assert phase1_duration < 5000, (
            f"Initial development phase too slow: {phase1_duration:.1f}ms "
            f"(target: <5000ms). Feature creation must be fast for productivity."
        )

        assert phase2_duration < 3000, (
            f"Testing phase too slow: {phase2_duration:.1f}ms "
            f"(target: <3000ms). Testing all features must be quick."
        )

        assert phase3_duration < 2000, (
            f"Iteration phase too slow: {phase3_duration:.1f}ms "
            f"(target: <2000ms). Quick iterations are essential for productivity."
        )

        assert total_productivity_duration < 10000, (
            f"Complete development session too slow: {total_productivity_duration:.1f}ms "
            f"(target: <10000ms). Overall development experience must be efficient."
        )

        # Document productivity metrics
        print("\nDeveloper Productivity Analysis:")
        print(f"  Phase 1 (Initial Development): {phase1_duration:.1f}ms")
        print(f"  Phase 2 (Testing): {phase2_duration:.1f}ms")
        print(f"  Phase 3 (Iteration): {phase3_duration:.1f}ms")
        print(f"  Total Session: {total_productivity_duration:.1f}ms")
        print(f"  Features Developed: {len(features)}")
        print(f"  Tests Executed: {len(test_results)}")
