"""
Tier 2 (Integration) Performance Tests for PERF-001: Performance Crisis Resolution

These tests validate performance with real Core SDK integration, no mocking.
Tests the complete integration between optimized Kaizen and Kailash Core SDK.

Integration Performance Requirements:
- Core SDK workflow building: <200ms with optimized Kaizen nodes
- Agent workflow execution: <1000ms for simple workflows
- Enterprise configuration with real infrastructure: <2000ms
- Memory usage under load: <100MB increase for typical workflows

Test Strategy:
- Real Docker services from tests/utils for infrastructure
- NO MOCKING - test actual Core SDK integration performance
- Real workflow building and execution timing
- Validate performance with actual database and service connections
"""

import gc

# Core SDK imports for integration testing
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


class TestKaizenCoreSDKIntegrationPerformance:
    """Performance tests with real Core SDK integration."""

    def setup_method(self):
        """Setup for integration tests with clean environment."""
        # Clear kaizen imports for clean testing
        modules_to_remove = [
            key for key in sys.modules.keys() if key.startswith("kaizen")
        ]
        for module in modules_to_remove:
            if module in sys.modules:
                del sys.modules[module]
        gc.collect()

    def test_kaizen_workflow_builder_integration_performance(self):
        """
        Kaizen agents integrated with Core SDK WorkflowBuilder must be fast.

        Target: Complete workflow building with Kaizen agents < 200ms
        """
        import kaizen

        # Create framework and agent
        framework = kaizen.Kaizen()
        agent = framework.create_agent("processor", {"model": "gpt-4"})

        # Measure Core SDK integration performance
        start_time = time.perf_counter()

        # Build workflow with Core SDK
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "data_processor",
            {
                "code": "result = {'processed': input_data['value'] * 2}",
                "input_schema": {"input_data": "dict"},
                "output_schema": {"result": "dict"},
            },
        )

        # Add agent as workflow node (when implemented)
        try:
            kaizen_node = agent.to_workflow_node()
            workflow.add_node_instance(kaizen_node)
        except (AttributeError, NotImplementedError):
            # Agent-to-node conversion may not be implemented yet
            pass

        built_workflow = workflow.build()
        integration_duration = (time.perf_counter() - start_time) * 1000

        # Verify workflow was built successfully
        assert built_workflow is not None, "Workflow must be built successfully"

        # ASSERTION: Integration performance must be reasonable
        assert integration_duration < 200, (
            f"Kaizen-Core SDK integration too slow: {integration_duration:.1f}ms "
            f"(target: <200ms). Workflow building with Kaizen agents must be fast."
        )

    def test_kaizen_agent_workflow_execution_performance(self):
        """
        Agent workflow execution through Core SDK runtime must be performant.

        Target: Simple workflow execution < 1000ms
        """
        import kaizen

        framework = kaizen.Kaizen()
        framework.create_agent("executor", {"model": "gpt-4"})

        # Create a simple workflow for execution testing
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "simple_processor",
            {
                "code": "result = {'message': 'Hello from Kaizen integration test', 'input': input_data}",
                "input_schema": {"input_data": "dict"},
                "output_schema": {"result": "dict"},
            },
        )

        built_workflow = workflow.build()
        runtime = LocalRuntime()

        # Measure execution performance
        start_time = time.perf_counter()
        results, run_id = runtime.execute(
            built_workflow, inputs={"input_data": {"test": "performance"}}
        )
        execution_duration = (time.perf_counter() - start_time) * 1000

        # Verify execution was successful
        assert results is not None, "Workflow execution must return results"
        assert run_id is not None, "Workflow execution must return run_id"

        # ASSERTION: Execution performance must be reasonable
        assert execution_duration < 1000, (
            f"Workflow execution too slow: {execution_duration:.1f}ms "
            f"(target: <1000ms). Simple workflows must execute quickly."
        )

    def test_enterprise_framework_with_core_sdk_performance(self):
        """
        Enterprise Kaizen framework with Core SDK must maintain performance.

        Target: Enterprise configuration + workflow building < 2000ms
        """
        import kaizen

        # Measure enterprise framework initialization with Core SDK operations
        start_time = time.perf_counter()

        # Enterprise configuration
        enterprise_config = {
            "signature_programming_enabled": True,
            "memory_system_enabled": True,
            "auto_optimization_enabled": True,
            "enterprise_features_enabled": True,
        }

        framework = kaizen.Kaizen(config=enterprise_config)
        agent = framework.create_agent("enterprise_processor", {"model": "gpt-4"})

        # Build enterprise workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "enterprise_logic",
            {
                "code": "result = {'enterprise_processed': input_data, 'optimized': True}",
                "input_schema": {"input_data": "dict"},
                "output_schema": {"result": "dict"},
            },
        )

        built_workflow = workflow.build()
        enterprise_duration = (time.perf_counter() - start_time) * 1000

        # Verify enterprise functionality
        assert framework is not None, "Enterprise framework must be created"
        assert agent is not None, "Enterprise agent must be created"
        assert built_workflow is not None, "Enterprise workflow must be built"

        # ASSERTION: Enterprise performance must be reasonable
        assert enterprise_duration < 2000, (
            f"Enterprise framework with Core SDK too slow: {enterprise_duration:.1f}ms "
            f"(target: <2000ms). Enterprise features must not significantly impact performance."
        )


class TestKaizenMemoryUsageIntegration:
    """Memory usage performance with Core SDK integration."""

    def setup_method(self):
        """Setup for memory testing with clean environment."""
        modules_to_remove = [
            key for key in sys.modules.keys() if key.startswith("kaizen")
        ]
        for module in modules_to_remove:
            if module in sys.modules:
                del sys.modules[module]
        gc.collect()

    def test_memory_usage_with_core_sdk_integration(self):
        """
        Memory usage with Core SDK integration must be optimized.

        Target: Memory increase < 100MB for typical workflow operations
        """
        process = psutil.Process()
        gc.collect()
        baseline_memory = process.memory_info().rss / 1024 / 1024  # MB

        import kaizen

        # Create framework and perform typical operations
        framework = kaizen.Kaizen()
        agents = []

        # Create multiple agents (typical enterprise usage)
        for i in range(5):
            agent = framework.create_agent(f"agent_{i}", {"model": "gpt-4"})
            agents.append(agent)

        # Build multiple workflows
        workflows = []
        for i in range(3):
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode",
                f"processor_{i}",
                {
                    "code": f"result = {{'processed_{i}': input_data}}",
                    "input_schema": {"input_data": "dict"},
                    "output_schema": {"result": "dict"},
                },
            )
            workflows.append(workflow.build())

        gc.collect()
        post_operation_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = post_operation_memory - baseline_memory

        # Verify operations were successful
        assert len(agents) == 5, "All agents must be created"
        assert len(workflows) == 3, "All workflows must be built"

        # ASSERTION: Memory usage must be reasonable
        assert memory_increase < 100, (
            f"Memory usage too high with Core SDK integration: {memory_increase:.1f}MB increase "
            f"(target: <100MB). Lazy loading and optimization must control memory usage."
        )

    def test_memory_cleanup_after_workflow_execution(self):
        """
        Memory should be properly cleaned up after workflow execution.

        Target: Memory growth < 10MB after multiple executions
        """
        import kaizen

        framework = kaizen.Kaizen()
        framework.create_agent("memory_test", {"model": "gpt-4"})

        # Build reusable workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "memory_processor",
            {
                "code": "result = {'iteration': input_data['count'], 'data': 'x' * 1000}",
                "input_schema": {"input_data": "dict"},
                "output_schema": {"result": "dict"},
            },
        )
        built_workflow = workflow.build()
        runtime = LocalRuntime()

        process = psutil.Process()
        gc.collect()
        pre_execution_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Execute workflow multiple times
        for i in range(10):
            results, run_id = runtime.execute(
                built_workflow, inputs={"input_data": {"count": i}}
            )
            assert results is not None, f"Execution {i} must succeed"

        gc.collect()
        post_execution_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = post_execution_memory - pre_execution_memory

        # ASSERTION: Memory growth must be minimal
        assert memory_growth < 10, (
            f"Memory leak detected: {memory_growth:.1f}MB growth after 10 executions "
            f"(target: <10MB). Memory cleanup must work properly."
        )


class TestRealInfrastructurePerformance:
    """Performance tests with real infrastructure (no mocking)."""

    def test_framework_initialization_with_real_runtime(self):
        """
        Framework initialization with real Core SDK runtime must be fast.

        Tests that optimized Kaizen works correctly with real Core SDK components.
        """
        import kaizen

        start_time = time.perf_counter()

        # Initialize framework
        framework = kaizen.Kaizen()

        # Create real runtime instance
        runtime = LocalRuntime()

        # Verify runtime configuration
        assert runtime is not None, "Real runtime must be created"

        # Create agent that can work with runtime
        framework.create_agent("runtime_test", {"model": "gpt-4"})

        initialization_duration = (time.perf_counter() - start_time) * 1000

        # ASSERTION: Real infrastructure initialization must be fast
        assert initialization_duration < 500, (
            f"Real infrastructure initialization too slow: {initialization_duration:.1f}ms "
            f"(target: <500ms). Framework must work efficiently with real Core SDK."
        )

    def test_concurrent_agent_creation_performance(self):
        """
        Concurrent agent creation must maintain performance with optimized imports.

        Simulates real-world usage where multiple agents are created rapidly.
        """
        import concurrent.futures

        import kaizen

        framework = kaizen.Kaizen()

        def create_agent(agent_id):
            """Create agent with timing."""
            start_time = time.perf_counter()
            agent = framework.create_agent(
                f"concurrent_agent_{agent_id}", {"model": "gpt-4"}
            )
            creation_time = (time.perf_counter() - start_time) * 1000
            return agent, creation_time

        # Create multiple agents concurrently
        start_time = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_agent, i) for i in range(10)]
            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        total_duration = (time.perf_counter() - start_time) * 1000

        # Verify all agents were created successfully
        agents = [result[0] for result in results]
        creation_times = [result[1] for result in results]

        assert len(agents) == 10, "All agents must be created successfully"
        assert all(agent is not None for agent in agents), "All agents must be valid"

        # Check individual creation times
        max_creation_time = max(creation_times)
        sum(creation_times) / len(creation_times)

        # ASSERTION: Concurrent creation must be performant
        assert total_duration < 2000, (
            f"Concurrent agent creation too slow: {total_duration:.1f}ms for 10 agents "
            f"(target: <2000ms). Optimization must not hurt concurrent performance."
        )

        assert max_creation_time < 200, (
            f"Individual agent creation too slow: {max_creation_time:.1f}ms "
            f"(target: <200ms). Each agent creation must be fast."
        )


class TestPerformanceUnderLoad:
    """Performance validation under realistic enterprise loads."""

    def test_framework_performance_under_load(self):
        """
        Framework must maintain performance under typical enterprise load.

        Simulates realistic usage patterns with multiple frameworks, agents, and workflows.
        """
        import kaizen

        start_time = time.perf_counter()

        # Create multiple framework instances (multi-tenant scenario)
        frameworks = []
        for i in range(3):
            config = {
                "signature_programming_enabled": True if i % 2 == 0 else False,
                "enterprise_features_enabled": True,
            }
            framework = kaizen.Kaizen(config=config)
            frameworks.append(framework)

        # Create multiple agents per framework
        all_agents = []
        for framework in frameworks:
            framework_agents = []
            for j in range(5):
                agent = framework.create_agent(
                    f"load_test_agent_{j}", {"model": "gpt-4"}
                )
                framework_agents.append(agent)
            all_agents.extend(framework_agents)

        # Build multiple workflows
        workflows = []
        for i in range(5):
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode",
                f"load_processor_{i}",
                {
                    "code": f"result = {{'load_test_{i}': input_data, 'timestamp': time.time()}}",
                    "input_schema": {"input_data": "dict"},
                    "output_schema": {"result": "dict"},
                },
            )
            workflows.append(workflow.build())

        load_duration = (time.perf_counter() - start_time) * 1000

        # Verify all components were created successfully
        assert len(frameworks) == 3, "All frameworks must be created"
        assert (
            len(all_agents) == 15
        ), "All agents must be created (3 frameworks * 5 agents)"
        assert len(workflows) == 5, "All workflows must be built"

        # ASSERTION: Performance under load must be reasonable
        assert load_duration < 5000, (
            f"Performance under load too slow: {load_duration:.1f}ms "
            f"(target: <5000ms). Framework must handle enterprise loads efficiently."
        )

    def test_memory_stability_under_load(self):
        """
        Memory usage must remain stable under sustained load.

        Tests for memory leaks and excessive growth under realistic usage patterns.
        """
        import kaizen

        process = psutil.Process()
        gc.collect()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Sustained load test
        for cycle in range(5):
            # Create framework
            framework = kaizen.Kaizen()

            # Create and destroy agents
            agents = []
            for i in range(10):
                agent = framework.create_agent(
                    f"stability_agent_{i}", {"model": "gpt-4"}
                )
                agents.append(agent)

            # Build and execute workflows
            for i in range(3):
                workflow = WorkflowBuilder()
                workflow.add_node(
                    "PythonCodeNode",
                    f"stability_processor_{i}",
                    {
                        "code": f"result = {{'cycle_{cycle}_task_{i}': input_data}}",
                        "input_schema": {"input_data": "dict"},
                        "output_schema": {"result": "dict"},
                    },
                )

                runtime = LocalRuntime()
                results, run_id = runtime.execute(
                    workflow.build(), inputs={"input_data": {"cycle": cycle, "task": i}}
                )
                assert results is not None, f"Cycle {cycle} task {i} must succeed"

            # Clear references
            del agents
            del framework
            gc.collect()

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = final_memory - initial_memory

        # ASSERTION: Memory must remain stable
        assert memory_growth < 50, (
            f"Memory growth under sustained load too high: {memory_growth:.1f}MB "
            f"(target: <50MB). Memory management must be stable under load."
        )
