"""
Tier 3 (E2E) Tests for INFRA-004: Complete Infrastructure Validation

These tests validate the complete end-to-end test infrastructure capabilities.
They test complete workflows from infrastructure setup through validation.

Test Requirements:
- Complete infrastructure validation scenarios
- Test all INFRA-004 requirements end-to-end
- Real infrastructure components working together
- Complete test utilities workflow validation
- Timeout: <30 seconds per test (E2E can be slower)

INFRA-004 E2E Validation:
1. Complete test infrastructure setup and teardown
2. End-to-end test utilities workflow execution
3. Full framework integration with test infrastructure
4. Performance validation under realistic test loads
5. Complete error handling and recovery validation
6. Infrastructure scaling and reliability testing
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

import pytest
from kailash.runtime.local import LocalRuntime

# Import Core SDK components
# Import Core SDK components
from kailash.workflow.builder import WorkflowBuilder

from tests.utils import test_fixtures
from tests.utils.mock_providers import (
    MockLLMProvider,
    MockServiceRegistry,
    create_mock_framework,
)

# Import complete test infrastructure
from tests.utils.performance_tracker import PerformanceReport, PerformanceTracker

# Test markers
pytestmark = pytest.mark.e2e


class TestCompleteInfrastructureValidation:
    """Test complete test infrastructure validation end-to-end."""

    def test_complete_infra004_requirements_validation(self):
        """Validate all INFRA-004 requirements are met end-to-end."""
        main_report = PerformanceReport()

        # Requirement 1: Test utilities must be available and functional
        with PerformanceTracker(
            "utilities_validation", threshold=5.0
        ) as utilities_tracker:
            # Performance tracker validation
            perf_tracker = PerformanceTracker("nested_test", threshold=1.0)
            with perf_tracker:
                time.sleep(0.1)

            assert perf_tracker.elapsed_time > 0.05
            assert perf_tracker.is_under_threshold()

            # Test fixtures validation
            config = test_fixtures.integration_test_config()
            assert config["framework"]["name"] == "integration_test_framework"

            agents_config = test_fixtures.test_agent_configs()
            assert len(agents_config) >= 4

            data_samples = test_fixtures.test_data_samples()
            assert "simple_data" in data_samples
            assert "complex_data" in data_samples

            # Mock providers validation
            mock_llm = MockLLMProvider()
            response = mock_llm.complete("test prompt")
            assert response["metadata"]["provider"] == "mock_llm"

        main_report.add_tracker(utilities_tracker)

        # Requirement 2: Core SDK integration must work completely
        with PerformanceTracker("core_sdk_integration", threshold=10.0) as sdk_tracker:
            import kaizen

            # Create real framework
            framework = kaizen.Framework(config=config["framework"])

            # Create multiple agents
            agents = []
            for agent_name, agent_config in agents_config.items():
                agent = framework.create_agent(config=agent_config)
                agents.append(agent)

            # Execute workflows with all agents
            all_results = []
            for agent in agents:
                workflow = agent.create_workflow()
                workflow.add_node(
                    "PythonCodeNode",
                    "sdk_integration_test",
                    {
                        "code": """
result = {
    'agent_name': agent_config['name'],
    'sdk_integration': True,
    'test_data_processed': len(test_data),
    'timestamp': str(time.time())
}
""",
                        "agent_config": agent.config,
                        "test_data": data_samples,
                    },
                )

                results, run_id = agent.execute(workflow)
                all_results.append((agent, results, run_id))

            # Verify all SDK integrations worked
            assert len(all_results) == len(agents_config)
            for agent, results, run_id in all_results:
                assert (
                    results["sdk_integration_test"]["result"]["sdk_integration"] is True
                )

        main_report.add_tracker(sdk_tracker)

        # Requirement 3: Performance tracking must work under load
        with PerformanceTracker(
            "performance_under_load", threshold=15.0
        ) as load_tracker:
            load_scenarios = test_fixtures.load_test_scenarios()
            light_scenario = load_scenarios[0]  # Use light scenario for E2E

            performance_report = PerformanceReport()

            # Execute multiple workflows concurrently
            runtime = LocalRuntime()

            def execute_test_workflow(workflow_id):
                with PerformanceTracker(
                    f"workflow_{workflow_id}", threshold=3.0
                ) as w_tracker:
                    workflow = WorkflowBuilder()
                    workflow.add_node(
                        "PythonCodeNode",
                        f"load_test_{workflow_id}",
                        {
                            "code": f"""
result = {{
    'workflow_id': {workflow_id},
    'load_test': True,
    'performance_validation': True,
    'timestamp': str(time.time())
}}
"""
                        },
                    )

                    results, run_id = runtime.execute(workflow.build())
                    return w_tracker, results, run_id

            # Execute workflows concurrently
            with ThreadPoolExecutor(max_workers=light_scenario["agents"]) as executor:
                futures = [
                    executor.submit(execute_test_workflow, i)
                    for i in range(
                        light_scenario["agents"] * light_scenario["workflows_per_agent"]
                    )
                ]

                all_workflow_results = []
                for future in as_completed(futures):
                    w_tracker, results, run_id = future.result()
                    performance_report.add_tracker(w_tracker)
                    all_workflow_results.append((results, run_id))

            # Verify performance under load
            summary = performance_report.get_summary()
            assert summary["passed_thresholds"] == summary["threshold_checks"]
            assert (
                len(all_workflow_results)
                == light_scenario["agents"] * light_scenario["workflows_per_agent"]
            )

        main_report.add_tracker(load_tracker)

        # Requirement 4: Error handling and recovery must work
        with PerformanceTracker("error_handling", threshold=8.0) as error_tracker:
            # Test error handling in workflows
            error_workflow = WorkflowBuilder()
            error_workflow.add_node(
                "PythonCodeNode",
                "intentional_error",
                {
                    "code": "raise ValueError('Intentional test error for infrastructure validation')"
                },
            )

            recovery_workflow = WorkflowBuilder()
            recovery_workflow.add_node(
                "PythonCodeNode",
                "recovery_test",
                {
                    "code": "result = {'recovery_successful': True, 'error_handling_validated': True}"
                },
            )

            # Execute error workflow (should handle gracefully)
            error_results, error_run_id = runtime.execute(error_workflow.build())

            # Verify error was handled (LocalRuntime may use different error structure)
            error_node_result = error_results["intentional_error"]
            # Check for either status field or exception presence
            if "status" in error_node_result:
                assert error_node_result["status"] == "failed"
            else:
                # Alternative: check for exception or error field
                assert (
                    "exception" in error_node_result
                    or "error" in error_node_result
                    or not error_node_result.get("result", {}).get("success", True)
                )

            # Execute recovery workflow (should work normally)
            recovery_results, recovery_run_id = runtime.execute(
                recovery_workflow.build()
            )

            # Verify recovery worked
            assert (
                recovery_results["recovery_test"]["result"]["recovery_successful"]
                is True
            )

            # Verify different run IDs
            assert error_run_id != recovery_run_id

        main_report.add_tracker(error_tracker)

        # Final validation: Complete infrastructure report
        final_summary = main_report.get_summary()
        assert final_summary["passed_thresholds"] == final_summary["threshold_checks"]
        assert final_summary["total_operations"] == 4

    def test_infrastructure_scaling_and_reliability(self):
        """Test infrastructure can scale and remain reliable under stress."""
        with PerformanceTracker("scaling_reliability", threshold=25.0) as main_tracker:
            import kaizen

            # Create framework for scaling test
            framework = kaizen.Framework(
                config={"name": "scaling_reliability_test", "version": "1.0.0"}
            )

            # Test parameters for reliability
            num_frameworks = 3
            agents_per_framework = 4
            workflows_per_agent = 2

            frameworks = []
            all_agents = []

            # Create multiple frameworks (simulate multi-tenant)
            for f_idx in range(num_frameworks):
                fw = kaizen.Framework(
                    config={
                        "name": f"reliability_framework_{f_idx}",
                        "version": "1.0.0",
                    }
                )
                frameworks.append(fw)

                # Create agents per framework
                for a_idx in range(agents_per_framework):
                    agent = fw.create_agent(
                        config={
                            "name": f"reliability_agent_{f_idx}_{a_idx}",
                            "framework_id": f_idx,
                            "agent_id": a_idx,
                        }
                    )
                    all_agents.append((fw, agent, f_idx, a_idx))

            # Execute workflows concurrently across all frameworks
            def execute_reliability_workflow(fw, agent, f_idx, a_idx, w_idx):
                workflow = agent.create_workflow()
                workflow.add_node(
                    "PythonCodeNode",
                    "reliability_test",
                    {
                        "code": f"""
result = {{
    'framework_id': {f_idx},
    'agent_id': {a_idx},
    'workflow_id': {w_idx},
    'reliability_test': True,
    'scaling_validated': True,
    'execution_timestamp': str(time.time())
}}
"""
                    },
                )

                return agent.execute(workflow)

            # Execute all workflows concurrently
            all_executions = []
            with ThreadPoolExecutor(
                max_workers=num_frameworks * agents_per_framework
            ) as executor:
                futures = []

                for fw, agent, f_idx, a_idx in all_agents:
                    for w_idx in range(workflows_per_agent):
                        future = executor.submit(
                            execute_reliability_workflow, fw, agent, f_idx, a_idx, w_idx
                        )
                        futures.append((future, f_idx, a_idx, w_idx))

                # Collect all results
                for future, f_idx, a_idx, w_idx in futures:
                    results, run_id = future.result()
                    all_executions.append((results, run_id, f_idx, a_idx, w_idx))

            # Verify scaling and reliability
            expected_executions = (
                num_frameworks * agents_per_framework * workflows_per_agent
            )
            assert len(all_executions) == expected_executions

            # Verify all executions succeeded
            framework_results = {}
            for results, run_id, f_idx, a_idx, w_idx in all_executions:
                assert results["reliability_test"]["result"]["reliability_test"] is True
                assert (
                    results["reliability_test"]["result"]["scaling_validated"] is True
                )

                if f_idx not in framework_results:
                    framework_results[f_idx] = []
                framework_results[f_idx].append((results, run_id))

            # Verify each framework handled its load correctly
            for f_idx in range(num_frameworks):
                framework_executions = framework_results[f_idx]
                expected_per_framework = agents_per_framework * workflows_per_agent
                assert len(framework_executions) == expected_per_framework

                # Verify unique run IDs per framework
                run_ids = [run_id for _, run_id in framework_executions]
                assert len(set(run_ids)) == len(run_ids)  # All unique

        # Verify scaling performance
        main_tracker.assert_under_threshold(
            "Infrastructure scaling test exceeded threshold"
        )

    def test_infrastructure_integration_with_existing_tests(self):
        """Test infrastructure integrates properly with existing test patterns."""
        with PerformanceTracker("integration_compatibility", threshold=10.0) as tracker:
            # Test integration with existing Kaizen framework tests
            import kaizen

            # Use existing test patterns from the codebase
            framework = kaizen.Framework()

            # Test 1: Framework initialization (existing pattern)
            assert hasattr(framework, "runtime")
            assert hasattr(framework, "create_agent")
            assert hasattr(framework, "create_workflow")

            # Test 2: Agent creation (existing pattern)
            agent = framework.create_agent(config={"name": "integration_test_agent"})
            assert agent.config["name"] == "integration_test_agent"

            # Test 3: Workflow execution (existing pattern)
            workflow = agent.create_workflow()
            workflow.add_node(
                "PythonCodeNode",
                "integration_node",
                {
                    "code": "result = {'integration_test': True, 'existing_pattern': True}"
                },
            )

            results, run_id = agent.execute(workflow)

            # Verify existing patterns still work
            assert results["integration_node"]["result"]["integration_test"] is True
            assert results["integration_node"]["result"]["existing_pattern"] is True

            # Test 4: Performance tracking integration
            perf_tracker = PerformanceTracker("existing_pattern_test", threshold=2.0)
            with perf_tracker:
                # Execute another workflow to test performance integration
                workflow2 = agent.create_workflow()
                workflow2.add_node(
                    "PythonCodeNode",
                    "perf_test",
                    {"code": "result = {'performance_integration': True}"},
                )

                results2, run_id2 = agent.execute(workflow2)

            # Verify performance integration
            assert perf_tracker.elapsed_time > 0
            assert perf_tracker.is_under_threshold()
            assert results2["perf_test"]["result"]["performance_integration"] is True

            # Test 5: Test fixtures integration
            config = test_fixtures.integration_test_config()
            sample_nodes = test_fixtures.sample_workflow_nodes()

            # Use fixtures in workflow
            for node_config in sample_nodes[:2]:  # Use first 2 nodes
                test_workflow = framework.create_workflow()
                test_workflow.add_node(
                    node_config["node_type"],
                    f"fixture_{node_config['node_id']}",
                    node_config["parameters"],
                )

                fixture_results, fixture_run_id = framework.execute(
                    test_workflow.build()
                )
                assert "result" in fixture_results[f"fixture_{node_config['node_id']}"]

        tracker.assert_under_threshold(
            "Infrastructure integration compatibility test too slow"
        )

    def test_complete_infrastructure_documentation_validation(self):
        """Validate infrastructure provides complete testing capabilities."""
        capabilities_report = {
            "performance_tracking": False,
            "test_fixtures": False,
            "mock_providers": False,
            "core_sdk_integration": False,
            "kaizen_framework_integration": False,
            "error_handling": False,
            "scaling_support": False,
            "concurrent_execution": False,
        }

        with PerformanceTracker("capabilities_validation", threshold=15.0):
            # Validate performance tracking capability
            try:
                tracker = PerformanceTracker("capability_test", threshold=1.0)
                with tracker:
                    time.sleep(0.1)

                assert tracker.elapsed_time > 0
                capabilities_report["performance_tracking"] = True
            except Exception:
                pass

            # Validate test fixtures capability
            try:
                config = test_fixtures.integration_test_config()
                agents = test_fixtures.test_agent_configs()
                data = test_fixtures.test_data_samples()

                assert len(config) > 0
                assert len(agents) > 0
                assert len(data) > 0
                capabilities_report["test_fixtures"] = True
            except Exception:
                pass

            # Validate mock providers capability
            try:
                mock_llm = MockLLMProvider()
                mock_registry = MockServiceRegistry()

                response = mock_llm.complete("test")
                mock_registry.register("test", mock_llm)

                assert len(response["response"]) > 0
                assert mock_registry.is_registered("test")
                capabilities_report["mock_providers"] = True
            except Exception:
                pass

            # Validate Core SDK integration capability
            try:
                workflow = WorkflowBuilder()
                workflow.add_node(
                    "PythonCodeNode",
                    "sdk_test",
                    {"code": "result = {'sdk_integration': True}"},
                )

                runtime = LocalRuntime()
                results, run_id = runtime.execute(workflow.build())

                assert results["sdk_test"]["result"]["sdk_integration"] is True
                capabilities_report["core_sdk_integration"] = True
            except Exception:
                pass

            # Validate Kaizen framework integration capability
            try:
                import kaizen

                framework = kaizen.Framework()
                agent = framework.create_agent(config={"name": "capability_test"})

                workflow = agent.create_workflow()
                workflow.add_node(
                    "PythonCodeNode",
                    "framework_test",
                    {"code": "result = {'framework_integration': True}"},
                )

                results, run_id = agent.execute(workflow)
                assert (
                    results["framework_test"]["result"]["framework_integration"] is True
                )
                capabilities_report["kaizen_framework_integration"] = True
            except Exception:
                pass

            # Validate error handling capability
            try:
                error_workflow = WorkflowBuilder()
                error_workflow.add_node(
                    "PythonCodeNode",
                    "error_test",
                    {"code": "raise ValueError('Test error')"},
                )

                runtime = LocalRuntime()
                error_results, error_run_id = runtime.execute(error_workflow.build())

                # Should handle error gracefully
                error_node = error_results["error_test"]
                # Check for error handling (status field or exception presence)
                error_handled = (
                    ("status" in error_node and error_node["status"] == "failed")
                    or ("exception" in error_node)
                    or ("error" in error_node)
                    or (not error_node.get("result", {}).get("success", True))
                )
                assert error_handled, "Error not handled properly"
                capabilities_report["error_handling"] = True
            except Exception:
                pass

            # Validate scaling support capability
            try:
                runtime = LocalRuntime()
                workflows = []

                # Create multiple workflows
                for i in range(5):
                    workflow = WorkflowBuilder()
                    workflow.add_node(
                        "PythonCodeNode",
                        f"scale_test_{i}",
                        {
                            "code": f"result = {{'workflow_id': {i}, 'scaling_test': True}}"
                        },
                    )
                    workflows.append(workflow)

                # Execute all workflows
                all_results = []
                for workflow in workflows:
                    results, run_id = runtime.execute(workflow.build())
                    all_results.append(results)

                assert len(all_results) == 5
                capabilities_report["scaling_support"] = True
            except Exception:
                pass

            # Validate concurrent execution capability
            try:

                def execute_concurrent_workflow(workflow_id):
                    workflow = WorkflowBuilder()
                    workflow.add_node(
                        "PythonCodeNode",
                        f"concurrent_{workflow_id}",
                        {
                            "code": f"result = {{'workflow_id': {workflow_id}, 'concurrent': True}}"
                        },
                    )

                    runtime = LocalRuntime()
                    return runtime.execute(workflow.build())

                with ThreadPoolExecutor(max_workers=3) as executor:
                    futures = [
                        executor.submit(execute_concurrent_workflow, i)
                        for i in range(3)
                    ]
                    concurrent_results = [future.result() for future in futures]

                assert len(concurrent_results) == 3
                capabilities_report["concurrent_execution"] = True
            except Exception:
                pass

        # Verify all capabilities are available
        failed_capabilities = [
            cap for cap, status in capabilities_report.items() if not status
        ]

        if failed_capabilities:
            pytest.fail(f"Infrastructure missing capabilities: {failed_capabilities}")

        # All capabilities should be available
        assert all(
            capabilities_report.values()
        ), f"Missing capabilities: {failed_capabilities}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "--timeout=300", "-s"])
