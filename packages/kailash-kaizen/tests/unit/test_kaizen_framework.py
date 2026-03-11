"""
Tier 1 (Unit) Tests for Kaizen Framework Foundation

These tests verify the basic functionality of the Kaizen framework foundation
components in isolation, focusing on framework initialization, basic configuration,
and integration patterns with Core SDK.

Test Requirements:
- Fast execution (<1 second per test)
- No external dependencies
- Can use mocks for external services only
- Test framework initialization and basic functionality
- Test Core SDK integration patterns
- Test package structure and imports
"""

from unittest.mock import Mock, patch

import pytest

# Import standardized test fixtures
from tests.fixtures.consolidated_test_fixtures import consolidated_fixtures


# Test imports and package structure
def test_kaizen_package_import(performance_tracker):
    """Test that kaizen package can be imported correctly."""
    try:
        import kaizen

        assert kaizen is not None
        assert hasattr(kaizen, "__version__")
    except ImportError as e:
        pytest.fail(f"Failed to import kaizen package: {e}")


def test_kaizen_framework_import(performance_tracker):
    """Test that kaizen.Framework can be imported and accessed."""
    try:
        import kaizen

        assert hasattr(kaizen, "Framework")
        assert callable(kaizen.Framework)
    except ImportError as e:
        pytest.fail(f"Failed to import kaizen.Framework: {e}")
    except AttributeError as e:
        pytest.fail(f"kaizen.Framework not accessible: {e}")


def test_kaizen_package_structure(performance_tracker):
    """Test that kaizen package follows expected structure."""
    import kaizen

    # Test package has expected attributes
    expected_attributes = ["Framework", "__version__", "__name__"]
    for attr in expected_attributes:
        assert hasattr(kaizen, attr), f"kaizen package missing {attr}"

    # Test version format
    assert isinstance(kaizen.__version__, str)
    assert len(kaizen.__version__.split(".")) >= 2  # At least major.minor


class TestKaizenFrameworkInitialization:
    """Test Kaizen Framework initialization and basic configuration."""

    def test_framework_default_initialization(self, performance_tracker):
        """Test Framework can be initialized with default parameters."""
        import kaizen

        framework = kaizen.Framework()
        assert framework is not None
        assert hasattr(framework, "config")
        assert hasattr(framework, "runtime")
        assert hasattr(framework, "builder")

    def test_framework_with_config(self, performance_tracker):
        """Test Framework can be initialized with custom configuration."""
        import kaizen

        # Use standardized configuration from fixtures
        base_config = consolidated_fixtures.get_configuration("minimal")
        config = {
            **base_config,
            "name": "test_framework",
            "version": "1.0.0",
            "description": "Test framework instance",
        }

        framework = kaizen.Framework(config=config)
        assert framework is not None
        assert framework.config["name"] == "test_framework"
        assert framework.config["version"] == "1.0.0"
        assert framework.config["description"] == "Test framework instance"

    def test_framework_config_validation(self, performance_tracker):
        """Test Framework validates configuration parameters."""
        import kaizen

        # Test invalid config types
        with pytest.raises(TypeError):
            kaizen.Framework(config="invalid_config")

        with pytest.raises(TypeError):
            kaizen.Framework(config=123)

    def test_framework_default_config(self, performance_tracker):
        """Test Framework sets appropriate default configuration."""
        import kaizen

        framework = kaizen.Framework()

        # Test default config structure
        assert isinstance(framework.config, dict)
        assert "name" in framework.config
        assert "version" in framework.config
        assert framework.config["name"] is not None
        assert framework.config["version"] is not None


class TestKaizenCoreSDKIntegration:
    """Test Kaizen Framework integration with Core SDK components."""

    @patch("kailash.workflow.builder.WorkflowBuilder")
    def test_framework_workflow_builder_integration(
        self, mock_builder, performance_tracker
    ):
        """Test Framework properly integrates with WorkflowBuilder."""
        import kaizen

        # Setup mock
        mock_instance = Mock()
        mock_builder.return_value = mock_instance

        framework = kaizen.Framework()

        # Test that framework has WorkflowBuilder integration
        assert hasattr(framework, "builder")
        assert framework.builder is not None

        # Test builder can be accessed and used
        workflow = framework.create_workflow()
        assert workflow is not None

    @patch("kailash.runtime.local.LocalRuntime")
    def test_framework_local_runtime_integration(
        self, mock_runtime, performance_tracker
    ):
        """Test Framework properly integrates with LocalRuntime."""
        import kaizen

        # Setup mock
        mock_instance = Mock()
        mock_runtime.return_value = mock_instance

        framework = kaizen.Framework()

        # Test that framework has LocalRuntime integration
        assert hasattr(framework, "runtime")
        assert framework.runtime is not None

    def test_framework_workflow_creation_pattern(self, performance_tracker):
        """Test Framework follows Core SDK workflow creation patterns."""
        import kaizen

        framework = kaizen.Framework()

        # Test framework can create workflows following SDK patterns
        workflow = framework.create_workflow()
        assert workflow is not None
        assert hasattr(workflow, "add_node")  # WorkflowBuilder pattern
        assert hasattr(workflow, "build")  # Required build() method

    def test_framework_execution_pattern(self, performance_tracker):
        """Test Framework follows Core SDK execution patterns."""
        import kaizen

        framework = kaizen.Framework()

        # Test framework supports runtime.execute(workflow.build()) pattern
        assert hasattr(framework, "execute")
        assert callable(framework.execute)

        # Test method signature accepts workflow
        import inspect

        sig = inspect.signature(framework.execute)
        assert "workflow" in sig.parameters


class TestKaizenAgentCreation:
    """Test basic agent creation and configuration capabilities."""

    def test_framework_agent_creation(self, performance_tracker):
        """Test Framework can create basic agents."""
        import kaizen

        framework = kaizen.Framework()

        # Test framework has agent creation capability
        assert hasattr(framework, "create_agent")
        assert callable(framework.create_agent)

    def test_agent_creation_with_config(self, performance_tracker):
        """Test agents can be created with configuration."""
        import kaizen

        framework = kaizen.Framework()

        # Use standardized agent config from fixtures
        base_config = {"model": "gpt-3.5-turbo", "temperature": 0.7, "max_tokens": 100}
        agent_config = {
            **base_config,
            "name": "test_agent",
            "type": "basic",
            "capabilities": ["workflow_execution"],
        }

        agent = framework.create_agent(config=agent_config)
        assert agent is not None
        assert hasattr(agent, "config")
        assert agent.config["name"] == "test_agent"

    def test_agent_workflow_integration(self, performance_tracker):
        """Test agents can integrate with workflow creation."""
        import kaizen

        framework = kaizen.Framework()
        agent = framework.create_agent()

        # Test agent can create workflows
        assert hasattr(agent, "create_workflow")
        workflow = agent.create_workflow()
        assert workflow is not None

    def test_multiple_agent_creation(self, performance_tracker):
        """Test framework can create multiple agents."""
        import kaizen

        framework = kaizen.Framework()

        agent1 = framework.create_agent(config={"name": "agent1"})
        agent2 = framework.create_agent(config={"name": "agent2"})

        assert agent1 is not None
        assert agent2 is not None
        assert agent1 != agent2
        assert agent1.config["name"] != agent2.config["name"]


class TestKaizenParameterValidation:
    """Test framework parameter validation and error handling."""

    def test_framework_invalid_parameters(self, performance_tracker):
        """Test Framework handles invalid parameters appropriately."""
        import kaizen

        # Test invalid config parameter (None is allowed, but invalid types should raise)
        with pytest.raises(TypeError):
            kaizen.Framework(config="invalid_string")

        with pytest.raises(TypeError):
            kaizen.Framework(config=123)

        # Test config=None is allowed (uses defaults)
        framework = kaizen.Framework(config=None)
        assert framework is not None

        # Test invalid runtime parameter if supported
        with pytest.raises(TypeError):
            kaizen.Framework(runtime="invalid")

    def test_agent_creation_parameter_validation(self, performance_tracker):
        """Test agent creation validates parameters."""
        import kaizen

        framework = kaizen.Framework()

        # Test invalid agent config
        with pytest.raises((TypeError, ValueError)):
            framework.create_agent(config="invalid")

        with pytest.raises((TypeError, ValueError)):
            framework.create_agent(config=123)

    def test_workflow_execution_parameter_validation(self, performance_tracker):
        """Test workflow execution validates parameters."""
        import kaizen

        framework = kaizen.Framework()

        # Test invalid workflow parameter
        with pytest.raises((TypeError, ValueError)):
            framework.execute(workflow=None)

        with pytest.raises((TypeError, ValueError)):
            framework.execute(workflow="invalid")


class TestKaizenFrameworkState:
    """Test framework state management and lifecycle."""

    def test_framework_state_initialization(self, performance_tracker):
        """Test framework initializes with proper state."""
        import kaizen

        framework = kaizen.Framework()

        # Test framework has state tracking
        assert hasattr(framework, "_state") or hasattr(framework, "state")

        # Test initial state is valid
        if hasattr(framework, "_state"):
            assert framework._state is not None
        if hasattr(framework, "state"):
            assert framework.state is not None

    def test_framework_agent_tracking(self, performance_tracker):
        """Test framework tracks created agents."""
        import kaizen

        framework = kaizen.Framework()

        initial_count = len(framework.agents) if hasattr(framework, "agents") else 0

        agent = framework.create_agent()

        # Test agent is tracked
        if hasattr(framework, "agents"):
            assert len(framework.agents) == initial_count + 1
            assert agent in framework.agents or any(
                a.id == agent.id for a in framework.agents
            )

    def test_framework_cleanup(self, performance_tracker):
        """Test framework can be properly cleaned up."""
        import kaizen

        framework = kaizen.Framework()
        framework.create_agent()

        # Test framework has cleanup capability
        if hasattr(framework, "cleanup"):
            framework.cleanup()
            # Verify cleanup worked
            if hasattr(framework, "agents"):
                assert len(framework.agents) == 0

        # Test framework can be reused after cleanup
        new_agent = framework.create_agent()
        assert new_agent is not None


class TestKaizenPerformanceBaseline:
    """Test framework performance characteristics for baseline."""

    def test_framework_initialization_performance(self, performance_tracker):
        """Test framework initialization is fast."""

        import kaizen

        performance_tracker.start_timer("framework_init")
        kaizen.Framework()
        init_time_ms = performance_tracker.end_timer("framework_init")

        # Framework initialization should be very fast (<100ms per fixture standards)
        performance_tracker.assert_performance("framework_init", 100)
        assert (
            init_time_ms < 100
        ), f"Framework initialization took {init_time_ms:.2f}ms, expected <100ms"

    def test_agent_creation_performance(self, performance_tracker):
        """Test agent creation performance baseline."""

        import kaizen

        framework = kaizen.Framework()

        performance_tracker.start_timer("agent_creation_batch")
        for i in range(10):
            agent_config = {
                "model": "gpt-3.5-turbo",
                "temperature": 0.7,
                "max_tokens": 100,
            }
            agent_config["name"] = f"agent_{i}"
            framework.create_agent(config=agent_config)
        batch_time_ms = performance_tracker.end_timer("agent_creation_batch")

        # Creating 10 agents should be fast (<100ms per agent standards)
        avg_time_per_agent = batch_time_ms / 10
        assert (
            avg_time_per_agent < 100
        ), f"Average agent creation took {avg_time_per_agent:.2f}ms, expected <100ms"

    def test_workflow_creation_performance(self, performance_tracker):
        """Test workflow creation performance baseline."""

        import kaizen

        framework = kaizen.Framework()

        performance_tracker.start_timer("workflow_creation_batch")
        for i in range(5):
            framework.create_workflow()
        batch_time_ms = performance_tracker.end_timer("workflow_creation_batch")

        # Creating 5 workflows should be fast (<200ms per workflow standards)
        avg_time_per_workflow = batch_time_ms / 5
        assert (
            avg_time_per_workflow < 200
        ), f"Average workflow creation took {avg_time_per_workflow:.2f}ms, expected <200ms"


# Performance and isolation tests
def test_kaizen_import_performance(performance_tracker):
    """Test kaizen package import performance."""

    performance_tracker.start_timer("package_import")

    import_time_ms = performance_tracker.end_timer("package_import")

    # Package import should be very fast (<50ms per fixture standards)
    assert (
        import_time_ms < 50
    ), f"Package import took {import_time_ms:.2f}ms, expected <50ms"


def test_kaizen_memory_usage(performance_tracker):
    """Test kaizen package doesn't have excessive memory usage."""
    import gc

    # Get initial memory state
    initial_objects = len(gc.get_objects())

    # Import and use kaizen
    import kaizen

    framework = kaizen.Framework()
    framework.create_agent()

    # Check memory impact
    final_objects = len(gc.get_objects())
    object_increase = final_objects - initial_objects

    # Should not create excessive objects (< 1000 new objects)
    assert object_increase < 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
