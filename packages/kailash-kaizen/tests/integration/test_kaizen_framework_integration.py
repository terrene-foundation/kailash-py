"""
Tier 2 (Integration) Tests for Kaizen Framework Foundation

These tests verify the Kaizen framework foundation integrates correctly with real
Core SDK components and infrastructure. All external services are real (NO MOCKING).

Test Requirements:
- Use real Docker services from tests/utils
- Run: ./tests/utils/test-env up && ./tests/utils/test-env status before tests
- NO MOCKING - test actual component interactions
- Test framework with real WorkflowBuilder and LocalRuntime
- Test complete workflow creation and execution
- Timeout: <5 seconds per test

Setup Requirements:
1. Docker services must be running
2. Real Core SDK components
3. Actual workflow execution with runtime
"""

import pytest

from kailash.runtime.local import LocalRuntime

# Import Core SDK components (real, not mocked)
from kailash.workflow.builder import WorkflowBuilder

# Test markers
pytestmark = pytest.mark.integration


class TestKaizenCoreSDKIntegration:
    """Test Kaizen Framework integration with real Core SDK components."""

    def test_framework_with_real_workflow_builder(self):
        """Test Framework integrates with real WorkflowBuilder."""
        import kaizen

        framework = kaizen.Framework()

        # Test framework creates real WorkflowBuilder instances
        workflow = framework.create_workflow()
        assert isinstance(workflow, WorkflowBuilder)

        # Test WorkflowBuilder functionality works through framework
        workflow.add_node(
            "PythonCodeNode",
            "print_test",
            {"code": "result = {'message': 'test integration'}"},
        )
        built_workflow = workflow.build()

        assert built_workflow is not None
        assert len(built_workflow.nodes) == 1

    def test_framework_with_real_local_runtime(self):
        """Test Framework integrates with real LocalRuntime."""
        import kaizen

        framework = kaizen.Framework()

        # Test framework uses real LocalRuntime
        assert isinstance(framework.runtime, LocalRuntime)

        # Test runtime functionality works through framework
        workflow = framework.create_workflow()
        workflow.add_node(
            "PythonCodeNode",
            "print_test",
            {"code": "result = {'message': 'integration test'}"},
        )

        # Execute workflow through framework
        results, run_id = framework.execute(workflow.build())

        assert results is not None
        assert run_id is not None
        assert isinstance(results, dict)
        assert "print_test" in results
        assert "result" in results["print_test"]

    def test_framework_workflow_execution_patterns(self):
        """Test Framework follows Core SDK execution patterns."""
        import kaizen

        framework = kaizen.Framework()

        # Test runtime.execute(workflow.build()) pattern
        workflow = framework.create_workflow()
        workflow.add_node(
            "PythonCodeNode",
            "test_node",
            {"code": "result = {'message': 'pattern test'}"},
        )

        # Test framework execute method follows SDK pattern
        results, run_id = framework.execute(workflow.build())

        # Verify results follow SDK patterns
        assert isinstance(results, dict)
        assert "test_node" in results
        assert "result" in results[list(results.keys())[0]]

    def test_framework_multiple_workflow_execution(self):
        """Test Framework can execute multiple workflows with real runtime."""
        import kaizen

        framework = kaizen.Framework()

        results_list = []

        # Execute multiple workflows
        for i in range(3):
            workflow = framework.create_workflow()
            workflow.add_node(
                "PythonCodeNode",
                f"node_{i}",
                {"code": f"result = {{'message': 'test {i}'}}"},
            )

            results, run_id = framework.execute(workflow.build())
            results_list.append((results, run_id))

        # Verify all executions succeeded
        assert len(results_list) == 3
        for results, run_id in results_list:
            assert results is not None
            assert run_id is not None


class TestKaizenAgentWorkflowIntegration:
    """Test agent-workflow integration with real SDK components."""

    def test_agent_creates_real_workflows(self):
        """Test agents create real WorkflowBuilder instances."""
        import kaizen

        framework = kaizen.Framework()
        agent = framework.create_agent(config={"name": "test_agent"})

        # Test agent creates real workflows
        workflow = agent.create_workflow()
        assert isinstance(workflow, WorkflowBuilder)

        # Test workflow functions correctly
        workflow.add_node(
            "PythonCodeNode",
            "agent_test",
            {"code": "result = {'message': 'agent workflow'}"},
        )
        built_workflow = workflow.build()

        assert built_workflow is not None
        assert len(built_workflow.nodes) == 1

    def test_agent_workflow_execution(self):
        """Test agents can execute workflows through framework runtime."""
        import kaizen

        framework = kaizen.Framework()
        agent = framework.create_agent(config={"name": "executor_agent"})

        # Create and execute workflow through agent
        workflow = agent.create_workflow()
        workflow.add_node(
            "PythonCodeNode",
            "agent_exec",
            {"code": "result = {'message': 'agent execution'}"},
        )

        # Execute through agent (should use framework runtime)
        results, run_id = agent.execute(workflow)

        assert results is not None
        assert run_id is not None
        assert "agent_exec" in results
        assert "result" in results[list(results.keys())[0]]

    def test_multiple_agents_workflow_execution(self):
        """Test multiple agents can execute workflows simultaneously."""
        import kaizen

        framework = kaizen.Framework()

        # Create multiple agents
        agents = [
            framework.create_agent(config={"name": f"agent_{i}"}) for i in range(3)
        ]

        execution_results = []

        # Each agent executes a workflow
        for i, agent in enumerate(agents):
            workflow = agent.create_workflow()
            workflow.add_node(
                "PythonCodeNode",
                f"multi_agent_{i}",
                {"code": f"result = {{'message': 'agent {i} execution'}}"},
            )

            results, run_id = agent.execute(workflow)
            execution_results.append((agent, results, run_id))

        # Verify all agent executions succeeded
        assert len(execution_results) == 3
        for agent, results, run_id in execution_results:
            assert results is not None
            assert run_id is not None
            assert len(results) == 1  # One node executed


@pytest.fixture(scope="module", autouse=False)
def setup_test_environment():
    """Setup test environment before running integration tests."""
    import os
    import subprocess

    # Change to tests/utils directory
    utils_dir = "./repos/projects/kailash_python_sdk/tests/utils"

    if os.path.exists(utils_dir):
        os.chdir(utils_dir)

        # Start test environment
        try:
            result = subprocess.run(
                ["./test-env", "up"], capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                pytest.skip(f"Failed to start test environment: {result.stderr}")

            # Check status
            result = subprocess.run(
                ["./test-env", "status"], capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                pytest.skip(f"Test environment not ready: {result.stderr}")

        except subprocess.TimeoutExpired:
            pytest.skip("Test environment setup timed out")
        except FileNotFoundError:
            pytest.skip("test-env script not found")
    else:
        pytest.skip("Test utils directory not found")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
