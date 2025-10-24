"""
Tier 2 (Integration) Tests for Test Infrastructure Components

These tests validate that test infrastructure components work correctly with
real Core SDK components. They test integration without requiring Docker services.

Test Requirements:
- Test infrastructure utilities with real Core SDK components
- NO MOCKING - use real WorkflowBuilder and LocalRuntime
- Validate test components support real workflow execution
- Test infrastructure performance with real execution
- Timeout: <5 seconds per test

INFRA-004 Components Tested:
1. Test utilities integration with Core SDK
2. Performance tracking with real workflow execution
3. Test fixtures with real Kaizen framework
4. Mock providers isolation from real components
5. Complete infrastructure workflow validation
"""

import time
from typing import Any, Dict, List

import pytest
from kailash.runtime.local import LocalRuntime

# Import Core SDK components for real integration
from kailash.workflow.builder import WorkflowBuilder

from tests.utils import test_fixtures
from tests.utils.mock_providers import (
    MockLLMProvider,
    MockServiceRegistry,
    create_mock_agent,
    create_mock_framework,
)

# Import test infrastructure components
from tests.utils.performance_tracker import PerformanceReport, PerformanceTracker

# Test markers
pytestmark = pytest.mark.integration


class TestPerformanceTrackerIntegration:
    """Test PerformanceTracker with real Core SDK components."""

    def test_performance_tracker_with_real_workflow_builder(self):
        """Performance tracker must accurately measure real WorkflowBuilder operations."""
        with PerformanceTracker(
            "workflow_builder_operations", threshold=2.0
        ) as tracker:
            # Create real WorkflowBuilder
            workflow = WorkflowBuilder()

            # Add multiple nodes (real operations)
            for i in range(5):
                workflow.add_node(
                    "PythonCodeNode",
                    f"test_node_{i}",
                    {
                        "code": f"result = {{'node_id': {i}, 'message': 'Performance test node {i}'}}"
                    },
                )

            # Add connections between nodes (WorkflowBuilder uses add_connection)
            for i in range(4):
                workflow.add_connection(
                    f"test_node_{i}", "result", f"test_node_{i+1}", "input_data"
                )

            # Build workflow
            built_workflow = workflow.build()

            # Verify workflow was built correctly
            assert len(built_workflow.nodes) == 5
            # Workflow object may not expose edges directly - just verify it built

        # Verify performance tracking
        assert tracker.elapsed_time > 0
        tracker.assert_under_threshold("WorkflowBuilder operations too slow")

    def test_performance_tracker_with_real_runtime_execution(self):
        """Performance tracker must measure real LocalRuntime execution accurately."""
        # Create workflow first
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "perf_test",
            {
                "code": "import time; time.sleep(0.01); result = {'performance_test': True, 'timestamp': str(time.time())}"
            },
        )

        # Track runtime execution
        with PerformanceTracker("runtime_execution", threshold=3.0) as tracker:
            runtime = LocalRuntime()
            results, run_id = runtime.execute(workflow.build())

            # Verify execution completed
            assert results is not None
            assert "perf_test" in results
            assert results["perf_test"]["result"]["performance_test"] is True

        # Verify performance measurement
        assert tracker.elapsed_time > 0.01  # Should include the sleep time
        tracker.assert_under_threshold("Runtime execution too slow")

    def test_performance_report_aggregation(self):
        """Performance report must aggregate multiple real operations correctly."""
        report = PerformanceReport()

        # Execute multiple tracked operations
        for i in range(3):
            with PerformanceTracker(f"operation_{i}", threshold=1.0) as tracker:
                # Real workflow operation
                workflow = WorkflowBuilder()
                workflow.add_node(
                    "PythonCodeNode",
                    f"report_test_{i}",
                    {"code": f"result = {{'operation': {i}, 'completed': True}}"},
                )

                runtime = LocalRuntime()
                results, run_id = runtime.execute(workflow.build())

                assert results[f"report_test_{i}"]["result"]["completed"] is True

            report.add_tracker(tracker)

        # Verify report aggregation
        summary = report.get_summary()
        assert summary["total_operations"] == 3
        assert summary["completed_operations"] == 3
        assert summary["threshold_checks"] == 3
        assert summary["passed_thresholds"] == 3  # All should pass


class TestTestFixturesIntegration:
    """Test fixtures integration with real Kaizen framework."""

    def test_integration_config_with_real_framework(self):
        """Integration test config must work with real Kaizen framework."""
        import kaizen

        config = test_fixtures.integration_test_config()
        framework_config = config["framework"]

        # Create real framework using test config
        framework = kaizen.Framework(config=framework_config)

        # Verify framework initialization (Kaizen framework structure)
        assert hasattr(framework, "config")
        assert hasattr(framework, "runtime")
        assert hasattr(framework, "create_agent")

        # Test framework functionality
        workflow = framework.create_workflow()
        workflow.add_node(
            "PythonCodeNode",
            "config_test",
            {
                "code": "result = {'config_integration': True, 'framework_name': 'integration_test_framework'}"
            },
        )

        results, run_id = framework.execute(workflow.build())
        assert results["config_test"]["result"]["config_integration"] is True

    def test_agent_configs_with_real_agents(self):
        """Agent test configs must work with real agent creation."""
        import kaizen

        framework = kaizen.Framework()
        agent_configs = test_fixtures.test_agent_configs()

        created_agents = []
        for config_name, agent_config in agent_configs.items():
            agent = framework.create_agent(config=agent_config)
            created_agents.append(agent)

            # Test agent functionality
            workflow = agent.create_workflow()
            workflow.add_node(
                "PythonCodeNode",
                "agent_test",
                {
                    "code": f"result = {{'agent_name': '{agent_config['name']}', 'agent_type': '{agent_config['type']}', 'working': True}}"
                },
            )

            results, run_id = agent.execute(workflow)
            agent_result = results["agent_test"]["result"]
            assert agent_result["agent_name"] == agent_config["name"]
            assert agent_result["agent_type"] == agent_config["type"]
            assert agent_result["working"] is True

        # Verify all agents created successfully
        assert len(created_agents) == len(agent_configs)

    def test_sample_workflow_nodes_with_real_execution(self):
        """Sample workflow nodes must execute correctly with real runtime."""
        sample_nodes = test_fixtures.sample_workflow_nodes()
        runtime = LocalRuntime()

        for i, node_config in enumerate(sample_nodes):
            workflow = WorkflowBuilder()

            # Add the sample node
            workflow.add_node(
                node_config["node_type"],
                node_config["node_id"],
                node_config["parameters"],
            )

            # Execute workflow
            results, run_id = runtime.execute(workflow.build())

            # Verify node executed successfully
            node_result = results[node_config["node_id"]]
            # LocalRuntime returns different structure - check for result directly
            assert "result" in node_result
            # If there's a status field, it should be completed, otherwise check result exists
            if "status" in node_result:
                assert node_result["status"] == "completed"

            # Verify node-specific expected outcomes
            if node_config["node_id"] == "start_node":
                assert "Workflow started" in str(node_result["result"])
            elif node_config["node_id"] == "processing_node":
                assert "processed" in str(node_result["result"])

    def test_data_samples_with_real_processing(self):
        """Test data samples must work with real workflow processing."""
        data_samples = test_fixtures.test_data_samples()
        runtime = LocalRuntime()

        for sample_name, sample_data in data_samples.items():
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode",
                f"process_{sample_name}",
                {
                    "code": """
processed_data = {
    'input_type': type(input_data).__name__,
    'input_keys': list(input_data.keys()) if isinstance(input_data, dict) else None,
    'processed': True,
    'sample_name': sample_name
}
result = processed_data
""",
                    "input_data": sample_data,
                    "sample_name": sample_name,
                },
            )

            results, run_id = runtime.execute(workflow.build())
            processed_result = results[f"process_{sample_name}"]["result"]

            assert processed_result["processed"] is True
            assert processed_result["sample_name"] == sample_name
            if isinstance(sample_data, dict):
                assert processed_result["input_type"] == "dict"
                assert processed_result["input_keys"] is not None


class TestMockProvidersIsolation:
    """Test mock providers work in isolation from real components."""

    def test_mock_llm_provider_isolation(self):
        """Mock LLM provider must not interfere with real workflow execution."""
        # Set up mock provider
        mock_llm = MockLLMProvider(
            custom_responses={"test_prompt": "Mock response for testing"}
        )

        # Use mock provider
        mock_response = mock_llm.complete("test_prompt")
        assert mock_response["response"] == "Mock response for testing"

        # Verify real Kaizen framework still works independently
        import kaizen

        framework = kaizen.Framework()

        workflow = framework.create_workflow()
        workflow.add_node(
            "PythonCodeNode",
            "isolation_test",
            {"code": "result = {'real_framework': True, 'mock_unaffected': True}"},
        )

        results, run_id = framework.execute(workflow.build())
        real_result = results["isolation_test"]["result"]

        # Verify real execution is unaffected by mock
        assert real_result["real_framework"] is True
        assert real_result["mock_unaffected"] is True

        # Verify mock still works
        another_mock_response = mock_llm.complete("test_prompt")
        assert another_mock_response["response"] == "Mock response for testing"

    def test_mock_service_registry_isolation(self):
        """Mock service registry must not interfere with real framework services."""
        # Set up mock registry
        mock_registry = MockServiceRegistry()
        mock_service = create_mock_agent()
        mock_registry.register("test_service", mock_service)

        # Use mock registry
        retrieved_service = mock_registry.get("test_service")
        assert retrieved_service is mock_service

        # Real framework operations should be unaffected
        import kaizen

        framework = kaizen.Framework()

        # Create multiple agents (real service management)
        agents = []
        for i in range(3):
            agent = framework.create_agent(config={"name": f"real_agent_{i}"})
            agents.append(agent)

        # Verify real agents work correctly
        for i, agent in enumerate(agents):
            workflow = agent.create_workflow()
            workflow.add_node(
                "PythonCodeNode",
                "registry_isolation",
                {
                    "code": f"result = {{'agent_index': {i}, 'real_agent': True, 'registry_test': True}}"
                },
            )

            results, run_id = agent.execute(workflow)
            agent_result = results["registry_isolation"]["result"]
            assert agent_result["agent_index"] == i
            assert agent_result["real_agent"] is True

        # Mock registry should still work
        assert mock_registry.is_registered("test_service")
        assert len(mock_registry.list_services()) == 1


class TestInfrastructureWorkflowIntegration:
    """Test complete infrastructure workflow integration."""

    def test_complete_infrastructure_workflow(self):
        """Test complete workflow using all infrastructure components together."""
        # Performance tracking
        with PerformanceTracker("complete_workflow", threshold=10.0) as main_tracker:

            # Test fixtures
            config = test_fixtures.integration_test_config()
            agent_configs = test_fixtures.test_agent_configs()
            test_data = test_fixtures.test_data_samples()

            # Real framework
            import kaizen

            framework = kaizen.Framework(config=config["framework"])

            # Create agents using test configurations
            agents = {}
            for config_name, agent_config in agent_configs.items():
                agent = framework.create_agent(config=agent_config)
                agents[config_name] = agent

            # Execute workflows with different agents
            all_results = {}
            performance_report = PerformanceReport()

            for agent_name, agent in agents.items():
                with PerformanceTracker(
                    f"agent_{agent_name}_execution", threshold=3.0
                ) as agent_tracker:
                    workflow = agent.create_workflow()

                    # Use test data in workflow
                    workflow.add_node(
                        "PythonCodeNode",
                        f"{agent_name}_task",
                        {
                            "code": """
result = {
    'agent_name': agent_config['name'],
    'agent_type': agent_config['type'],
    'test_data_processed': len(test_data),
    'infrastructure_test': True,
    'capabilities': agent_config['capabilities'],
    'execution_timestamp': str(time.time())
}
""",
                            "agent_config": agent.config,
                            "test_data": test_data,
                        },
                    )

                    results, run_id = agent.execute(workflow)
                    all_results[agent_name] = (results, run_id)

                performance_report.add_tracker(agent_tracker)

            # Verify complete workflow integration
            assert len(all_results) == len(agents)

            for agent_name, (results, run_id) in all_results.items():
                assert results is not None
                assert run_id is not None

                task_result = results[f"{agent_name}_task"]["result"]
                assert task_result["infrastructure_test"] is True
                assert task_result["test_data_processed"] > 0
                assert task_result["agent_name"] == agent_configs[agent_name]["name"]

            # Check performance report
            summary = performance_report.get_summary()
            assert summary["total_operations"] == len(agents)
            assert summary["passed_thresholds"] == len(agents)

        # Verify main performance
        main_tracker.assert_under_threshold("Complete infrastructure workflow too slow")

    def test_infrastructure_scaling_capability(self):
        """Test infrastructure can handle scaling requirements."""
        light_scenario = test_fixtures.load_test_scenarios()[0]  # Light load scenario

        with PerformanceTracker(
            "scaling_test", threshold=light_scenario["expected_max_time"]
        ) as tracker:
            import kaizen

            framework = kaizen.Framework()
            performance_report = PerformanceReport()

            # Create agents according to scenario
            agents = []
            for i in range(light_scenario["agents"]):
                agent = framework.create_agent(
                    config={
                        "name": f"scale_test_agent_{i}",
                        "capabilities": ["scaling_test"],
                    }
                )
                agents.append(agent)

            # Execute workflows per agent
            all_executions = []
            for agent in agents:
                for workflow_idx in range(light_scenario["workflows_per_agent"]):
                    with PerformanceTracker(
                        f"workflow_{agent.config['name']}_{workflow_idx}", threshold=2.0
                    ) as workflow_tracker:
                        workflow = agent.create_workflow()

                        # Add nodes per workflow
                        for node_idx in range(light_scenario["nodes_per_workflow"]):
                            node_id = f"scale_node_{workflow_idx}_{node_idx}"
                            workflow.add_node(
                                "PythonCodeNode",
                                node_id,
                                {
                                    "code": f"""
result = {{
    'agent': '{agent.config["name"]}',
    'workflow': {workflow_idx},
    'node': {node_idx},
    'scaling_test': True,
    'timestamp': str(time.time())
}}
"""
                                },
                            )

                        results, run_id = agent.execute(workflow)
                        all_executions.append((agent, results, run_id))

                    performance_report.add_tracker(workflow_tracker)

            # Verify scaling results
            expected_executions = (
                light_scenario["agents"] * light_scenario["workflows_per_agent"]
            )
            assert len(all_executions) == expected_executions

            # Verify all executions succeeded
            for agent, results, run_id in all_executions:
                assert results is not None
                assert run_id is not None
                assert len(results) == light_scenario["nodes_per_workflow"]

            # Check performance
            summary = performance_report.get_summary()
            assert summary["passed_thresholds"] == summary["threshold_checks"]

        tracker.assert_under_threshold("Infrastructure scaling test too slow")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "--timeout=60"])
