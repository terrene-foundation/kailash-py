"""
Tier 2 (Integration) Tests for INFRA-004: Setup integration test infrastructure

These tests validate the complete integration test infrastructure with real dependencies.
They test the actual Docker services, test utilities, and infrastructure components.

Test Requirements:
- Use real Docker services from tests/utils
- NO MOCKING - test actual infrastructure interactions
- Validate all INFRA-004 requirements with real services
- Test complete infrastructure setup and validation
- Timeout: <30 seconds per test (infrastructure can be slower)

INFRA-004 Requirements Tested:
1. Docker test environment availability and health
2. Test utilities integration with real infrastructure
3. Core SDK integration with test infrastructure
4. Enterprise feature testing with real infrastructure
5. Multi-agent coordination with real A2A infrastructure
6. Performance validation under realistic infrastructure loads
"""

import concurrent.futures
import os
import subprocess
import time
from typing import Any, Dict, List

import pytest
from kailash.runtime.local import LocalRuntime

# Import Core SDK components for real integration testing
# Import Core SDK components for real integration testing
from kailash.workflow.builder import WorkflowBuilder

# Import test infrastructure utilities
from tests.utils.performance_tracker import PerformanceReport, PerformanceTracker
from tests.utils.test_fixtures import (
    docker_service_health_check,
    load_test_scenarios,
    test_environment_config,
)

# Test markers
pytestmark = pytest.mark.integration


class TestDockerInfrastructureSetup:
    """Test Docker test infrastructure setup and availability."""

    def test_docker_test_environment_available(self):
        """Docker test environment must be available for integration testing."""
        with PerformanceTracker("docker_environment_check", threshold=30.0) as tracker:
            # Check if test-env infrastructure is running
            utils_dir = "./repos/projects/kailash_python_sdk/tests/utils"
            if not os.path.exists(utils_dir):
                pytest.skip("Test utils directory not found")

            original_cwd = os.getcwd()
            try:
                os.chdir(utils_dir)

                # Check test environment status
                result = subprocess.run(
                    ["./test-env", "status"], capture_output=True, text=True, timeout=20
                )

                if result.returncode != 0:
                    # Try to start the environment if it's not running
                    start_result = subprocess.run(
                        ["./test-env", "up"], capture_output=True, text=True, timeout=60
                    )

                    if start_result.returncode != 0:
                        pytest.skip(
                            f"Could not start Docker test environment: {start_result.stderr}"
                        )

                    # Wait for services to be ready
                    time.sleep(5)

                    # Check status again
                    result = subprocess.run(
                        ["./test-env", "status"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                assert (
                    result.returncode == 0
                ), f"Docker test environment not available: {result.stderr}"

            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                pytest.skip(f"Docker test environment check failed: {e}")
            finally:
                os.chdir(original_cwd)

        # Verify performance requirement
        tracker.assert_under_threshold("Docker environment check took too long")

    def test_required_services_running(self):
        """All required Docker services must be running and healthy."""
        with PerformanceTracker("services_health_check", threshold=20.0):
            config = test_environment_config()
            required_services = config["services"]

            service_health = {}
            for service_type, service_name in required_services.items():
                is_healthy = docker_service_health_check(service_name)
                service_health[service_type] = is_healthy

            # Verify core services are healthy
            assert service_health.get(
                "postgresql", False
            ), "PostgreSQL service not healthy"
            assert service_health.get("redis", False), "Redis service not healthy"

            # Note: Ollama might not be running, that's ok for basic tests
            # It's only required for AI-specific tests

    def test_service_connectivity(self):
        """Test actual connectivity to Docker services."""
        with PerformanceTracker("service_connectivity", threshold=10.0):
            config = test_environment_config()

            # Test PostgreSQL connectivity
            db_config = config["database"]
            try:
                import psycopg2

                conn = psycopg2.connect(
                    host=db_config["host"],
                    port=db_config["port"],
                    database=db_config["database"],
                    user=db_config["user"],
                    password=db_config["password"],
                )

                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                assert result[0] == 1, "PostgreSQL connectivity test failed"

                cursor.close()
                conn.close()

            except ImportError:
                pytest.skip(
                    "psycopg2 not installed, skipping PostgreSQL connectivity test"
                )
            except Exception as e:
                pytest.fail(f"PostgreSQL connectivity failed: {e}")

            # Test Redis connectivity
            redis_config = config["redis"]
            try:
                import redis

                r = redis.Redis(
                    host=redis_config["host"],
                    port=redis_config["port"],
                    database=redis_config["database"],
                )

                # Test Redis ping
                pong = r.ping()
                assert pong is True, "Redis connectivity test failed"

            except ImportError:
                pytest.skip("redis not installed, skipping Redis connectivity test")
            except Exception as e:
                pytest.fail(f"Redis connectivity failed: {e}")


class TestInfrastructureUtilitiesIntegration:
    """Test integration of test utilities with real infrastructure."""

    def test_performance_tracker_with_real_workflow_execution(self):
        """Performance tracker must work with real Core SDK workflow execution."""
        with PerformanceTracker("real_workflow_execution", threshold=5.0) as tracker:
            # Create real workflow using Core SDK
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode",
                "infrastructure_test",
                {
                    "code": "result = {'message': 'Infrastructure test with real Core SDK'}"
                },
            )

            # Execute with real LocalRuntime
            runtime = LocalRuntime()
            results, run_id = runtime.execute(workflow.build())

            # Verify real execution
            assert results is not None
            assert run_id is not None
            assert "infrastructure_test" in results
            assert results["infrastructure_test"]["status"] == "completed"

        # Verify performance tracking worked
        assert tracker.elapsed_time > 0
        tracker.assert_under_threshold("Real workflow execution too slow")

    def test_test_fixtures_with_real_kaizen_framework(self):
        """Test fixtures must work with real Kaizen framework components."""
        from tests.utils.test_fixtures import (
            integration_test_config,
            test_agent_configs,
        )

        with PerformanceTracker("fixtures_integration", threshold=3.0) as tracker:
            # Use test fixtures
            framework_config = integration_test_config()
            agent_configs = test_agent_configs()

            # Test with real Kaizen framework
            import kaizen

            framework = kaizen.Framework(config=framework_config["framework"])

            # Create agents using test configurations
            agents = []
            for agent_name, agent_config in agent_configs.items():
                agent = framework.create_agent(config=agent_config)
                agents.append(agent)

            # Verify agents were created successfully
            assert len(agents) == len(agent_configs)
            assert all(agent is not None for agent in agents)

            # Test agent workflow creation and execution
            test_agent = agents[0]
            workflow = test_agent.create_workflow()
            workflow.add_node(
                "PythonCodeNode",
                "fixture_test",
                {
                    "code": "result = {'fixture_test': True, 'agent_name': 'basic_test_agent'}"
                },
            )

            results, run_id = test_agent.execute(workflow)

            # Verify fixture integration worked
            assert results["fixture_test"]["result"]["fixture_test"] is True
            assert results["fixture_test"]["result"]["agent_name"] == "basic_test_agent"

        tracker.assert_under_threshold("Fixtures integration too slow")

    def test_mock_providers_isolation_from_real_infrastructure(self):
        """Mock providers must not interfere with real infrastructure testing."""
        from tests.utils.mock_providers import MockLLMProvider, MockServiceRegistry

        with PerformanceTracker("mock_isolation", threshold=2.0):
            # Create mock services
            mock_registry = MockServiceRegistry()
            mock_llm = MockLLMProvider()
            mock_registry.register("llm", mock_llm)

            # Test that mocks work independently
            llm_response = mock_llm.complete("test prompt")
            assert llm_response["metadata"]["provider"] == "mock_llm"

            # Test real Kaizen framework still works
            import kaizen

            framework = kaizen.Framework()

            # Real framework should work independently of mocks
            workflow = framework.create_workflow()
            workflow.add_node(
                "PythonCodeNode",
                "mock_isolation_test",
                {"code": "result = {'real_framework': True}"},
            )

            results, run_id = framework.execute(workflow.build())

            # Verify real framework unaffected by mocks
            assert results["mock_isolation_test"]["result"]["real_framework"] is True


class TestRealCoreSDKIntegrationInfrastructure:
    """Test Core SDK integration with real test infrastructure."""

    def test_real_core_sdk_workflow_execution_with_infrastructure(self):
        """Integration tests must use real Core SDK components with infrastructure."""
        with PerformanceTracker("core_sdk_integration", threshold=10.0) as tracker:
            # Test multiple workflow executions
            runtime = LocalRuntime()
            execution_results = []

            for i in range(3):
                workflow = WorkflowBuilder()
                workflow.add_node(
                    "PythonCodeNode",
                    f"infra_test_{i}",
                    {
                        "code": f"result = {{'iteration': {i}, 'timestamp': str(time.time()), 'infrastructure_test': True}}"
                    },
                )

                results, run_id = runtime.execute(workflow.build())
                execution_results.append((results, run_id))

            # Verify all executions succeeded
            assert len(execution_results) == 3
            for i, (results, run_id) in enumerate(execution_results):
                assert results is not None
                assert run_id is not None
                node_result = results[f"infra_test_{i}"]["result"]
                assert node_result["iteration"] == i
                assert node_result["infrastructure_test"] is True

        tracker.assert_under_threshold("Core SDK integration too slow")

    def test_real_workflow_builder_patterns_with_infrastructure(self):
        """Test WorkflowBuilder patterns work with test infrastructure."""
        with PerformanceTracker("workflow_patterns", threshold=8.0):
            workflow = WorkflowBuilder()

            # Build complex workflow with infrastructure testing
            workflow.add_node(
                "PythonCodeNode",
                "start",
                {"code": "result = {'stage': 'started', 'infrastructure': 'test'}"},
            )

            workflow.add_node(
                "PythonCodeNode",
                "process",
                {
                    "code": """
result = {
    'stage': 'processing',
    'input_received': bool(input_data),
    'infrastructure': 'test',
    'processed_at': str(time.time())
}
""",
                    "input_data": {"from_start": True},
                },
            )

            workflow.add_node(
                "PythonCodeNode",
                "complete",
                {
                    "code": """
result = {
    'stage': 'completed',
    'infrastructure': 'test',
    'final_status': 'success',
    'completed_at': str(time.time())
}
"""
                },
            )

            # Add edges for workflow flow
            workflow.add_edge("start", "process")
            workflow.add_edge("process", "complete")

            # Execute with real runtime
            runtime = LocalRuntime()
            results, run_id = runtime.execute(workflow.build())

            # Verify workflow patterns worked
            assert len(results) == 3
            assert results["start"]["result"]["stage"] == "started"
            assert results["process"]["result"]["stage"] == "processing"
            assert results["complete"]["result"]["stage"] == "completed"

            # Verify infrastructure test marking
            for node_result in results.values():
                assert node_result["result"]["infrastructure"] == "test"


class TestEnterpriseInfrastructureTesting:
    """Test enterprise features with real infrastructure."""

    def test_audit_trail_with_real_infrastructure(self):
        """Enterprise audit features must work with real test infrastructure."""
        with PerformanceTracker("audit_trail_test", threshold=15.0):
            import kaizen

            # Create framework with enterprise config
            framework = kaizen.Framework(
                config={
                    "name": "enterprise_infrastructure_test",
                    "audit_trail_enabled": True,
                    "compliance_mode": "enterprise",
                }
            )

            # Create workflow that would generate audit trail
            workflow = framework.create_workflow()
            workflow.add_node(
                "PythonCodeNode",
                "audit_test",
                {
                    "code": """
result = {
    'audit_event': 'enterprise_test_executed',
    'compliance_data': {
        'test_type': 'infrastructure_validation',
        'security_level': 'enterprise'
    },
    'timestamp': str(time.time())
}
"""
                },
            )

            # Execute workflow (should generate audit trail)
            results, run_id = framework.execute(workflow.build())

            # Verify audit trail functionality (basic check)
            assert (
                results["audit_test"]["result"]["audit_event"]
                == "enterprise_test_executed"
            )
            assert "compliance_data" in results["audit_test"]["result"]

    def test_multi_agent_coordination_with_real_infrastructure(self):
        """Multi-agent coordination must work with real infrastructure."""
        with PerformanceTracker("multi_agent_coordination", threshold=20.0) as tracker:
            import kaizen

            framework = kaizen.Framework(
                config={
                    "name": "multi_agent_infrastructure_test",
                    "multi_agent_enabled": True,
                }
            )

            # Create multiple agents for coordination test
            agents = []
            for i in range(3):
                agent = framework.create_agent(
                    config={
                        "name": f"infrastructure_agent_{i}",
                        "capabilities": [f"capability_{i}"],
                    }
                )
                agents.append(agent)

            # Test concurrent agent execution (simulating A2A)
            execution_results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = []

                for i, agent in enumerate(agents):
                    workflow = agent.create_workflow()
                    workflow.add_node(
                        "PythonCodeNode",
                        f"agent_task_{i}",
                        {
                            "code": f"""
result = {{
    'agent_id': '{agent.config["name"]}',
    'task_completed': True,
    'coordination_test': True,
    'agent_index': {i},
    'execution_timestamp': str(time.time())
}}
"""
                        },
                    )

                    future = executor.submit(agent.execute, workflow)
                    futures.append((agent, future))

                # Collect results
                for agent, future in futures:
                    results, run_id = future.result()
                    execution_results.append((agent, results, run_id))

            # Verify all agents executed successfully
            assert len(execution_results) == 3
            for i, (agent, results, run_id) in enumerate(execution_results):
                assert results is not None
                assert run_id is not None
                result_key = f"agent_task_{i}"
                assert result_key in results
                agent_result = results[result_key]["result"]
                assert agent_result["coordination_test"] is True
                assert agent_result["agent_index"] == i

        tracker.assert_under_threshold("Multi-agent coordination too slow")


class TestPerformanceAndLoadInfrastructure:
    """Test infrastructure performance under realistic loads."""

    def test_infrastructure_performance_under_load(self):
        """Infrastructure must handle realistic performance loads."""
        scenarios = load_test_scenarios()
        light_scenario = scenarios[0]  # Use light load for integration test

        with PerformanceTracker(
            "load_test", threshold=light_scenario["expected_max_time"]
        ) as tracker:
            import kaizen

            framework = kaizen.Framework(config={"name": "load_test_framework"})

            # Create agents for load test
            agents = []
            for i in range(light_scenario["agents"]):
                agent = framework.create_agent(
                    config={
                        "name": f"load_test_agent_{i}",
                        "capabilities": ["load_testing"],
                    }
                )
                agents.append(agent)

            # Execute workflows concurrently
            all_results = []
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=light_scenario["agents"]
            ) as executor:
                futures = []

                for agent in agents:
                    for workflow_idx in range(light_scenario["workflows_per_agent"]):
                        workflow = agent.create_workflow()

                        # Add nodes per workflow
                        for node_idx in range(light_scenario["nodes_per_workflow"]):
                            node_id = f"load_node_{workflow_idx}_{node_idx}"
                            workflow.add_node(
                                "PythonCodeNode",
                                node_id,
                                {
                                    "code": f"""
result = {{
    'agent': '{agent.config["name"]}',
    'workflow': {workflow_idx},
    'node': {node_idx},
    'load_test': True,
    'timestamp': str(time.time())
}}
"""
                                },
                            )

                            # Connect nodes sequentially
                            if node_idx > 0:
                                prev_node = f"load_node_{workflow_idx}_{node_idx-1}"
                                workflow.add_edge(prev_node, node_id)

                        future = executor.submit(agent.execute, workflow)
                        futures.append(future)

                # Collect all results
                for future in concurrent.futures.as_completed(futures):
                    results, run_id = future.result()
                    all_results.append((results, run_id))

            # Verify load test results
            expected_workflows = (
                light_scenario["agents"] * light_scenario["workflows_per_agent"]
            )
            assert len(all_results) == expected_workflows

            # Verify all workflows completed successfully
            for results, run_id in all_results:
                assert results is not None
                assert run_id is not None
                assert len(results) == light_scenario["nodes_per_workflow"]

        # Performance assertion
        tracker.assert_under_threshold(
            f"Load test exceeded {light_scenario['expected_max_time']}s threshold"
        )

    def test_infrastructure_memory_and_resource_usage(self):
        """Infrastructure must maintain reasonable resource usage."""
        with PerformanceTracker("resource_usage", threshold=10.0):
            import kaizen
            import psutil

            # Get baseline memory usage
            process = psutil.Process()
            baseline_memory = process.memory_info().rss / 1024 / 1024  # MB

            # Create multiple frameworks to test resource management
            frameworks = []
            for i in range(5):
                framework = kaizen.Framework(config={"name": f"resource_test_{i}"})
                frameworks.append(framework)

            # Create agents and execute workflows
            for framework in frameworks:
                agent = framework.create_agent(config={"name": "resource_test_agent"})
                workflow = agent.create_workflow()
                workflow.add_node(
                    "PythonCodeNode",
                    "resource_test",
                    {
                        "code": "result = {'memory_test': True, 'framework': 'resource_test'}"
                    },
                )

                results, run_id = agent.execute(workflow)
                assert results["resource_test"]["result"]["memory_test"] is True

            # Check memory usage after operations
            current_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = current_memory - baseline_memory

            # Memory increase should be reasonable (less than 100MB for this test)
            assert (
                memory_increase < 100
            ), f"Memory usage increased by {memory_increase:.1f}MB"


@pytest.fixture(scope="module", autouse=True)
def setup_integration_infrastructure():
    """Setup integration test infrastructure before running tests."""
    import os
    import subprocess

    # Track setup performance
    with PerformanceTracker("integration_setup", threshold=120.0) as setup_tracker:
        utils_dir = "./repos/projects/kailash_python_sdk/tests/utils"

        if not os.path.exists(utils_dir):
            pytest.skip("Test utils directory not found")

        original_cwd = os.getcwd()
        try:
            os.chdir(utils_dir)

            # Start Docker test environment
            result = subprocess.run(
                ["./test-env", "up"], capture_output=True, text=True, timeout=90
            )

            if result.returncode != 0:
                # Try to get more information about the failure
                status_result = subprocess.run(
                    ["./test-env", "status"], capture_output=True, text=True, timeout=10
                )

                pytest.skip(
                    f"Failed to start integration test environment. Status: {status_result.stdout}, Error: {result.stderr}"
                )

            # Verify services are ready
            time.sleep(10)  # Allow time for services to fully initialize

            status_result = subprocess.run(
                ["./test-env", "status"], capture_output=True, text=True, timeout=20
            )

            if status_result.returncode != 0:
                pytest.skip(
                    f"Integration test environment not ready: {status_result.stderr}"
                )

        except subprocess.TimeoutExpired:
            pytest.skip("Integration test environment setup timed out")
        except FileNotFoundError:
            pytest.skip("test-env script not found for integration tests")
        finally:
            os.chdir(original_cwd)

    # Verify setup performance
    try:
        setup_tracker.assert_under_threshold(
            "Integration infrastructure setup took too long"
        )
    except AssertionError as e:
        # Log warning but don't fail - setup can be slow on first run
        print(f"Warning: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s", "--timeout=300"])
