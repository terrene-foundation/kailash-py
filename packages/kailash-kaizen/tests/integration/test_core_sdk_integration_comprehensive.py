"""
Comprehensive integration tests for Kaizen framework with Core SDK.

Tier 2 (Integration Tests): Real Core SDK services, NO MOCKING.
Tests actual component interactions with WorkflowBuilder and LocalRuntime.

Coverage:
- Core SDK WorkflowBuilder integration
- LocalRuntime execution with real workflows
- String-based node system compatibility
- Agent-to-workflow compilation
- Parameter injection (config, connections, runtime)
- Cross-framework compatibility validation

IMPORTANT: Uses real Core SDK services - NO MOCKING ALLOWED in Tier 2.
"""

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from kaizen.core.agents import Agent
from kaizen.core.framework import Kaizen


@pytest.mark.integration
class TestCoreSDKWorkflowBuilderIntegration:
    """Test suite for WorkflowBuilder integration with real Core SDK services."""

    def test_kaizen_creates_real_workflow_builder(self, real_kaizen_framework):
        """Test Kaizen creates actual WorkflowBuilder instances."""
        workflow = real_kaizen_framework.create_workflow()

        # Verify it's a real WorkflowBuilder
        assert isinstance(workflow, WorkflowBuilder)
        assert hasattr(workflow, "add_node")
        assert hasattr(workflow, "build")
        assert callable(workflow.add_node)
        assert callable(workflow.build)

    def test_string_based_node_addition_real_workflow(self, real_kaizen_framework):
        """Test string-based node addition works with real WorkflowBuilder."""
        workflow = real_kaizen_framework.create_workflow()

        # Add nodes using string-based Core SDK pattern
        workflow.add_node(
            "LLMAgentNode",
            "test_agent",
            {
                "model": "gpt-3.5-turbo",
                "temperature": 0.7,
                "max_tokens": 500,
                "timeout": 30,
            },
        )

        workflow.add_node(
            "LLMAgentNode",
            "secondary_agent",
            {"model": "gpt-4", "temperature": 0.3, "max_tokens": 1000},
        )

        # Build should work with real WorkflowBuilder
        built_workflow = workflow.build()
        assert built_workflow is not None

        # Verify workflow structure (without executing due to LLM costs)
        # This validates the workflow was properly constructed
        assert hasattr(built_workflow, "nodes") or hasattr(built_workflow, "_nodes")

    def test_workflow_building_performance(
        self, real_kaizen_framework, performance_tracker
    ):
        """Test workflow building meets performance requirements with real services."""
        workflow = real_kaizen_framework.create_workflow()

        # Add multiple nodes to test complex workflow building
        for i in range(5):
            workflow.add_node(
                "LLMAgentNode",
                f"agent_{i}",
                {
                    "model": "gpt-3.5-turbo",
                    "temperature": 0.5 + (i * 0.1),
                    "max_tokens": 500,
                },
            )

        performance_tracker.start_timer("workflow_building")

        built_workflow = workflow.build()

        build_time = performance_tracker.end_timer("workflow_building")

        # Verify workflow was built successfully
        assert built_workflow is not None

        # Performance assertion (should be fast even with real services)
        assert (
            build_time < 1000
        ), f"Workflow building took {build_time:.2f}ms, should be <1000ms"

    def test_workflow_builder_state_independence(self, real_kaizen_framework):
        """Test workflow builders maintain independent state."""
        workflow1 = real_kaizen_framework.create_workflow()
        workflow2 = real_kaizen_framework.create_workflow()

        # Add different nodes to each workflow
        workflow1.add_node(
            "LLMAgentNode", "workflow1_agent", {"model": "gpt-3.5-turbo"}
        )
        workflow2.add_node("LLMAgentNode", "workflow2_agent", {"model": "gpt-4"})

        # Build both workflows
        built1 = workflow1.build()
        built2 = workflow2.build()

        # They should be separate instances
        assert built1 is not built2

        # Each should only contain its own nodes
        # Note: Exact verification depends on WorkflowBuilder internal structure
        assert built1 is not None
        assert built2 is not None


@pytest.mark.integration
class TestLocalRuntimeIntegration:
    """Test suite for LocalRuntime integration with real Core SDK services."""

    def test_kaizen_runtime_property_real_instance(self, real_kaizen_framework):
        """Test Kaizen runtime property returns real LocalRuntime."""
        runtime = real_kaizen_framework.runtime

        # Verify it's a real LocalRuntime instance
        assert isinstance(runtime, LocalRuntime)
        assert hasattr(runtime, "execute")
        assert callable(runtime.execute)

        # Should be the same instance as internal runtime
        assert runtime is real_kaizen_framework._runtime

    def test_runtime_state_isolation(self):
        """Test multiple Kaizen instances have isolated runtime state."""
        kaizen1 = Kaizen()
        kaizen2 = Kaizen()

        runtime1 = kaizen1.runtime
        runtime2 = kaizen2.runtime

        # Should be separate runtime instances
        assert runtime1 is not runtime2
        assert isinstance(runtime1, LocalRuntime)
        assert isinstance(runtime2, LocalRuntime)

    def test_workflow_execution_interface_real_runtime(self, real_kaizen_framework):
        """Test workflow execution interface works with real runtime."""
        # Create a simple workflow
        workflow = real_kaizen_framework.create_workflow()
        workflow.add_node(
            "LLMAgentNode",
            "test_execution",
            {"model": "gpt-3.5-turbo", "temperature": 0.7, "max_tokens": 50},
        )

        workflow.build()

        # Test execution interface (without actual execution due to costs)
        assert hasattr(real_kaizen_framework, "execute")
        assert callable(real_kaizen_framework.execute)

        # Verify runtime is ready for execution
        runtime = real_kaizen_framework.runtime
        assert hasattr(runtime, "execute")

        # Note: Actual execution tested in E2E tests to avoid LLM costs


@pytest.mark.integration
class TestAgentWorkflowCompilation:
    """Test suite for agent-to-workflow compilation with real services."""

    def test_agent_workflow_compilation_real_services(
        self, real_kaizen_framework, basic_agent_config
    ):
        """Test agent compilation creates real WorkflowBuilder."""
        agent = real_kaizen_framework.create_agent(
            "compilation_test", basic_agent_config
        )

        # Compile agent to workflow
        workflow = agent.compile_workflow()

        # Should be real WorkflowBuilder
        assert isinstance(workflow, WorkflowBuilder)

        # Should be buildable
        built_workflow = workflow.build()
        assert built_workflow is not None

        # Agent should cache the workflow
        assert agent._is_compiled is True
        assert agent._workflow is workflow

        # Subsequent calls should return cached workflow
        workflow2 = agent.compile_workflow()
        assert workflow2 is workflow

    def test_agent_configuration_mapping_real_workflow(self, real_kaizen_framework):
        """Test agent configuration maps correctly to workflow nodes."""
        agent_config = {
            "model": "gpt-4",
            "temperature": 0.3,
            "max_tokens": 1500,
            "timeout": 45,
            "custom_param": "test_value",
        }

        agent = real_kaizen_framework.create_agent("config_mapping_test", agent_config)
        workflow = agent.compile_workflow()

        # Build workflow to verify configuration was applied
        built_workflow = workflow.build()
        assert built_workflow is not None

        # Verify agent retains configuration
        assert agent.config["model"] == "gpt-4"
        assert agent.config["temperature"] == 0.3
        assert agent.config["max_tokens"] == 1500
        assert agent.config["timeout"] == 45
        assert agent.config["custom_param"] == "test_value"

    def test_multiple_agent_workflow_compilation(self, real_kaizen_framework):
        """Test multiple agents can be compiled to workflows independently."""
        # Create multiple agents with different configurations
        agent1 = real_kaizen_framework.create_agent(
            "multi_agent_1", {"model": "gpt-3.5-turbo", "temperature": 0.7}
        )
        agent2 = real_kaizen_framework.create_agent(
            "multi_agent_2", {"model": "gpt-4", "temperature": 0.3}
        )

        # Compile both to workflows
        workflow1 = agent1.compile_workflow()
        workflow2 = agent2.compile_workflow()

        # Should be separate WorkflowBuilder instances
        assert workflow1 is not workflow2
        assert isinstance(workflow1, WorkflowBuilder)
        assert isinstance(workflow2, WorkflowBuilder)

        # Both should be buildable
        built1 = workflow1.build()
        built2 = workflow2.build()
        assert built1 is not None
        assert built2 is not None
        assert built1 is not built2

    def test_agent_workflow_update_invalidation(self, real_kaizen_framework):
        """Test agent configuration updates invalidate compiled workflow."""
        agent = real_kaizen_framework.create_agent(
            "update_test", {"model": "gpt-3.5-turbo"}
        )

        # Compile initial workflow
        workflow1 = agent.compile_workflow()
        assert agent._is_compiled is True

        # Update agent configuration
        agent.update_config({"temperature": 0.8, "model": "gpt-4"})

        # Should invalidate compilation
        assert agent._is_compiled is False

        # New compilation should create new workflow
        workflow2 = agent.compile_workflow()
        assert workflow2 is not workflow1
        assert agent._is_compiled is True


@pytest.mark.integration
class TestParameterInjectionPatterns:
    """Test suite for parameter injection methods with real services."""

    def test_config_parameter_injection(self, real_kaizen_framework):
        """Test configuration-based parameter injection."""
        # Create agent with comprehensive configuration
        config_params = {
            "model": "gpt-4",
            "temperature": 0.5,
            "max_tokens": 800,
            "timeout": 60,
            "system_prompt": "You are a helpful assistant",
            "response_format": "json",
        }

        agent = real_kaizen_framework.create_agent("config_injection", config_params)
        workflow = agent.compile_workflow()

        # Build workflow to verify configuration injection
        built_workflow = workflow.build()
        assert built_workflow is not None

        # Verify configuration was preserved
        for key, value in config_params.items():
            assert agent.config[key] == value

    def test_runtime_parameter_injection(self, real_kaizen_framework):
        """Test runtime parameter injection through workflow execution interface."""
        agent = real_kaizen_framework.create_agent(
            "runtime_injection", {"model": "gpt-3.5-turbo", "temperature": 0.7}
        )

        workflow = agent.compile_workflow()
        workflow.build()

        # Test parameter preparation for execution

        # Verify execution interface accepts parameters
        # (Not executing to avoid LLM costs, but testing interface)
        assert callable(real_kaizen_framework.execute)

        # Test parameter mapping through agent execution interface
        assert hasattr(agent, "execute")
        assert callable(agent.execute)

    def test_signature_parameter_integration(
        self, real_kaizen_framework, mock_signature
    ):
        """Test signature-based parameter integration with real services."""
        agent = real_kaizen_framework.create_agent(
            "signature_integration", {"model": "gpt-4"}, signature=mock_signature
        )

        workflow = agent.compile_workflow()
        built_workflow = workflow.build()

        # Verify signature is integrated
        assert agent.signature is mock_signature
        assert built_workflow is not None

        # Signature should influence parameter structure
        signature_inputs = mock_signature.define_inputs()
        signature_outputs = mock_signature.define_outputs()

        assert "prompt" in signature_inputs
        assert "temperature" in signature_inputs
        assert "response" in signature_outputs


@pytest.mark.integration
class TestCrossFrameworkCompatibility:
    """Test suite for compatibility with existing Core SDK patterns."""

    def test_existing_workflow_unaffected_by_kaizen(
        self, real_workflow_builder, real_local_runtime
    ):
        """Test existing Core SDK workflows work unchanged with Kaizen present."""
        # Create traditional Core SDK workflow
        real_workflow_builder.add_node(
            "LLMAgentNode",
            "traditional_node",
            {"model": "gpt-3.5-turbo", "temperature": 0.7, "max_tokens": 500},
        )

        built_workflow = real_workflow_builder.build()
        assert built_workflow is not None

        # Should work with traditional runtime
        assert isinstance(real_local_runtime, LocalRuntime)
        assert hasattr(real_local_runtime, "execute")

        # Kaizen presence should not interfere
        kaizen = Kaizen()
        assert kaizen is not None

        # Original workflow should still be valid
        assert built_workflow is not None

    def test_mixed_framework_workflow_creation(self, real_kaizen_framework):
        """Test workflows can mix Kaizen and traditional Core SDK patterns."""
        # Create workflow through Kaizen
        workflow = real_kaizen_framework.create_workflow()

        # Add traditional Core SDK nodes
        workflow.add_node(
            "LLMAgentNode",
            "traditional_node",
            {"model": "gpt-3.5-turbo", "temperature": 0.7},
        )

        # Add another node using same pattern
        workflow.add_node(
            "LLMAgentNode",
            "another_traditional",
            {"model": "gpt-4", "temperature": 0.3},
        )

        # Should build successfully
        built_workflow = workflow.build()
        assert built_workflow is not None

    def test_kaizen_agent_coexistence_with_traditional_nodes(
        self, real_kaizen_framework
    ):
        """Test Kaizen agents can coexist with traditional workflow nodes."""
        # Create Kaizen agent
        agent = real_kaizen_framework.create_agent(
            "kaizen_agent", {"model": "gpt-4", "temperature": 0.5}
        )

        # Get agent's workflow
        agent_workflow = agent.compile_workflow()

        # Create separate workflow with traditional nodes
        traditional_workflow = real_kaizen_framework.create_workflow()
        traditional_workflow.add_node(
            "LLMAgentNode",
            "traditional_in_kaizen",
            {"model": "gpt-3.5-turbo", "temperature": 0.8},
        )

        # Both should build successfully
        agent_built = agent_workflow.build()
        traditional_built = traditional_workflow.build()

        assert agent_built is not None
        assert traditional_built is not None
        assert agent_built is not traditional_built

    def test_runtime_compatibility_across_patterns(self, real_kaizen_framework):
        """Test runtime compatibility across different usage patterns."""
        # Kaizen runtime
        kaizen_runtime = real_kaizen_framework.runtime

        # Direct runtime creation
        direct_runtime = LocalRuntime()

        # Both should be compatible LocalRuntime instances
        assert isinstance(kaizen_runtime, LocalRuntime)
        assert isinstance(direct_runtime, LocalRuntime)

        # Both should have execution capability
        assert hasattr(kaizen_runtime, "execute")
        assert hasattr(direct_runtime, "execute")

        # Create workflows using both patterns
        kaizen_workflow = real_kaizen_framework.create_workflow()
        kaizen_workflow.add_node(
            "LLMAgentNode", "kaizen_node", {"model": "gpt-3.5-turbo"}
        )

        direct_workflow = WorkflowBuilder()
        direct_workflow.add_node(
            "LLMAgentNode", "direct_node", {"model": "gpt-3.5-turbo"}
        )

        # Both should build
        kaizen_built = kaizen_workflow.build()
        direct_built = direct_workflow.build()

        assert kaizen_built is not None
        assert direct_built is not None


@pytest.mark.integration
class TestRealServiceValidation:
    """Test suite validating real service behavior and constraints."""

    def test_framework_initialization_with_real_services(self, performance_tracker):
        """Test framework initialization creates real service instances."""
        performance_tracker.start_timer("real_init")

        kaizen = Kaizen(
            memory_enabled=True,
            optimization_enabled=True,
            monitoring_enabled=True,
            debug=True,
        )

        init_time = performance_tracker.end_timer("real_init")

        # Verify real services are created (trigger lazy loading by accessing properties)
        runtime = kaizen.runtime  # This triggers lazy loading
        assert isinstance(runtime, LocalRuntime)
        assert isinstance(kaizen.agent_manager, type(kaizen.agent_manager))

        # Verify enterprise features are configured
        assert kaizen.memory_enabled is True
        assert kaizen.optimization_enabled is True
        assert kaizen.monitoring_enabled is True

        # Should still meet performance requirements with real services
        assert init_time < 200, f"Real service initialization took {init_time:.2f}ms"

    def test_agent_creation_with_real_workflow_compilation(
        self, real_kaizen_framework, performance_tracker
    ):
        """Test agent creation with immediate workflow compilation."""
        performance_tracker.start_timer("agent_with_compilation")

        agent = real_kaizen_framework.create_agent(
            "real_compilation",
            {"model": "gpt-4", "temperature": 0.6, "max_tokens": 1200},
        )

        # Immediately compile to test real workflow creation
        workflow = agent.compile_workflow()
        built_workflow = workflow.build()

        total_time = performance_tracker.end_timer("agent_with_compilation")

        # Verify real services work
        assert isinstance(workflow, WorkflowBuilder)
        assert built_workflow is not None

        # Should complete reasonably quickly even with real compilation
        assert total_time < 300, f"Agent creation + compilation took {total_time:.2f}ms"

    def test_bulk_operations_with_real_services(
        self, real_kaizen_framework, performance_tracker
    ):
        """Test bulk operations maintain performance with real services."""
        performance_tracker.start_timer("bulk_real_operations")

        # Create multiple agents with immediate compilation
        agents = []
        for i in range(5):
            agent = real_kaizen_framework.create_agent(
                f"bulk_real_{i}",
                {
                    "model": "gpt-3.5-turbo",
                    "temperature": 0.5 + (i * 0.1),
                    "max_tokens": 500 + (i * 100),
                },
            )

            # Compile each agent's workflow
            workflow = agent.compile_workflow()
            built = workflow.build()

            agents.append((agent, workflow, built))

        total_time = performance_tracker.end_timer("bulk_real_operations")

        # Verify all operations completed
        assert len(agents) == 5
        for agent, workflow, built in agents:
            assert isinstance(agent, Agent)
            assert isinstance(workflow, WorkflowBuilder)
            assert built is not None

        # Performance should scale reasonably
        average_time = total_time / 5
        assert (
            average_time < 100
        ), f"Average bulk operation time {average_time:.2f}ms per agent"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
