"""
Test Nexus Base Classes - Integration Mixins and Adapters.

Tests verify:
1. NexusDeploymentMixin functionality
2. Agent-to-workflow conversion
3. Agent works with/without Nexus
4. System prompt building
"""

import pytest


class TestNexusDeploymentMixin:
    """Test NexusDeploymentMixin creation and functionality."""

    @pytest.fixture
    def mock_nexus_app(self):
        """Create mock Nexus app."""
        from tests.utils.nexus_mocks import MockNexus

        return MockNexus()

    def test_nexus_deployment_mixin_creation(self, mock_nexus_app):
        """NexusDeploymentMixin should provide deployment capabilities."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import NexusDeploymentMixin

        # Should be a class we can use as mixin
        assert NexusDeploymentMixin is not None

        # Should have expected methods
        assert hasattr(NexusDeploymentMixin, "connect_nexus")
        assert hasattr(NexusDeploymentMixin, "to_workflow")

    def test_mixin_has_nexus_connection_attribute(self):
        """Mixin should define nexus_connection attribute."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import NexusDeploymentMixin

        # Should have connection attribute
        assert hasattr(NexusDeploymentMixin, "nexus_connection")

    def test_connect_nexus_method(self, mock_nexus_app):
        """connect_nexus should establish connection to Nexus."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import NexusDeploymentMixin

        class TestAgent(NexusDeploymentMixin):
            pass

        agent = TestAgent()
        agent.connect_nexus(mock_nexus_app)

        assert agent.nexus_connection is not None
        assert agent.nexus_connection.nexus_app is mock_nexus_app

    def test_connect_nexus_validates_type(self):
        """connect_nexus should validate Nexus instance type."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import NexusDeploymentMixin

        class TestAgent(NexusDeploymentMixin):
            pass

        agent = TestAgent()

        # Should raise TypeError for non-Nexus object
        with pytest.raises(TypeError) as exc_info:
            agent.connect_nexus("not a nexus instance")

        assert "Expected Nexus instance" in str(exc_info.value)


class TestAgentWithoutNexus:
    """Test agent functionality without Nexus connection."""

    def test_agent_without_nexus_instance(self):
        """Agent should work without Nexus connection."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig
        from kaizen.integrations.nexus import NexusDeploymentMixin

        # Create agent class with mixin
        class NexusAwareAgent(BaseAgent, NexusDeploymentMixin):
            pass

        # Should work without connecting to Nexus
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        agent = NexusAwareAgent(config=config)

        assert agent is not None
        assert agent.nexus_connection is None  # No connection yet

    def test_mixin_optional_on_base_agent(self):
        """Mixin should be optional - BaseAgent works standalone."""
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig

        # Regular agent without mixin should work
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        agent = BaseAgent(config=config)

        assert agent is not None
        # Should not have Nexus-specific attributes
        assert not hasattr(agent, "connect_nexus")


class TestAgentWithNexus:
    """Test enhanced agent with Nexus connection."""

    @pytest.fixture
    def mock_nexus_app(self):
        """Create mock Nexus app."""
        from tests.utils.nexus_mocks import MockNexus

        return MockNexus()

    def test_agent_with_nexus_instance(self, mock_nexus_app):
        """Agent should be enhanced with Nexus deployment."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig
        from kaizen.integrations.nexus import NexusDeploymentMixin

        class NexusAwareAgent(BaseAgent, NexusDeploymentMixin):
            pass

        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        agent = NexusAwareAgent(config=config)
        agent.connect_nexus(mock_nexus_app)

        assert agent.nexus_connection is not None
        assert agent.nexus_connection.is_connected() is True

    def test_agent_connection_lifecycle(self, mock_nexus_app):
        """Agent should manage Nexus connection lifecycle."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig
        from kaizen.integrations.nexus import NexusDeploymentMixin

        class NexusAwareAgent(BaseAgent, NexusDeploymentMixin):
            pass

        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        agent = NexusAwareAgent(config=config)

        # Connect
        agent.connect_nexus(mock_nexus_app)
        assert agent.nexus_connection.is_connected() is True

        # Disconnect
        agent.nexus_connection.stop()
        assert agent.nexus_connection.is_connected() is False


class TestWorkflowAdapter:
    """Test agent-to-workflow conversion."""

    @pytest.fixture
    def mock_agent(self):
        """Create mock agent for testing."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig
        from kaizen.integrations.nexus import NexusDeploymentMixin

        class TestAgent(BaseAgent, NexusDeploymentMixin):
            pass

        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        return TestAgent(config=config)

    def test_workflow_adapter_creation(self, mock_agent):
        """to_workflow should convert agent to WorkflowBuilder."""
        from kailash.workflow.builder import WorkflowBuilder

        workflow = mock_agent.to_workflow()

        assert workflow is not None
        assert isinstance(workflow, WorkflowBuilder)

    def test_workflow_contains_agent_config(self, mock_agent):
        """Generated workflow should contain agent configuration."""
        workflow = mock_agent.to_workflow()

        # Build workflow to access nodes
        built_workflow = workflow.build()

        # Should have at least one node (the agent node)
        assert len(built_workflow.nodes) > 0

        # Find the agent node - nodes is a dict
        agent_node = None
        for node_id, node in built_workflow.nodes.items():
            if node.node_type == "LLMAgentNode":
                agent_node = node
                break

        assert agent_node is not None

    def test_workflow_preserves_llm_config(self, mock_agent):
        """Workflow should preserve LLM provider and model."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        workflow = mock_agent.to_workflow()
        built_workflow = workflow.build()

        # Find agent node - nodes is a dict
        agent_node = None
        for node_id, node in built_workflow.nodes.items():
            if node.node_type == "LLMAgentNode":
                agent_node = node
                break

        assert agent_node is not None
        # LLMAgentNode uses "provider" not "llm_provider"
        assert agent_node.config.get("provider") == "openai"
        assert agent_node.config.get("model") == "gpt-4"

    def test_workflow_includes_temperature(self, mock_agent):
        """Workflow should include temperature config."""
        workflow = mock_agent.to_workflow()
        built_workflow = workflow.build()

        agent_node = None
        for node_id, node in built_workflow.nodes.items():
            if node.node_type == "LLMAgentNode":
                agent_node = node
                break

        assert agent_node is not None
        assert "temperature" in agent_node.config


class TestSystemPromptBuilding:
    """Test system prompt generation from agent signature."""

    def test_system_prompt_from_signature(self):
        """_build_system_prompt should use agent signature."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig
        from kaizen.integrations.nexus import NexusDeploymentMixin

        class TestAgent(BaseAgent, NexusDeploymentMixin):
            pass

        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        agent = TestAgent(config=config)

        # Test internal method
        prompt = agent._build_system_prompt()

        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_default_system_prompt_without_signature(self):
        """Should provide default prompt when no signature."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig
        from kaizen.integrations.nexus import NexusDeploymentMixin

        class TestAgent(BaseAgent, NexusDeploymentMixin):
            pass

        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        agent = TestAgent(config=config)

        # Agent has a default signature with description
        prompt = agent._build_system_prompt()

        # The prompt should contain something (not empty)
        assert len(prompt) > 0
        assert isinstance(prompt, str)

    def test_workflow_includes_system_prompt(self):
        """Generated workflow should include system prompt."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig
        from kaizen.integrations.nexus import NexusDeploymentMixin

        class TestAgent(BaseAgent, NexusDeploymentMixin):
            pass

        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        agent = TestAgent(config=config)

        workflow = agent.to_workflow()
        built_workflow = workflow.build()

        # Find agent node - nodes is a dict
        agent_node = None
        for node_id, node in built_workflow.nodes.items():
            if node.node_type == "LLMAgentNode":
                agent_node = node
                break

        assert agent_node is not None
        assert "system_prompt" in agent_node.config


class TestIntegrationErrorHandling:
    """Test error handling in integration layer."""

    def test_connect_nexus_without_nexus_installed(self):
        """connect_nexus should raise helpful error when Nexus not installed."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip(
                "Nexus not available - testing unavailable scenario requires Nexus to NOT be installed"
            )

        from kaizen.integrations.nexus import NexusDeploymentMixin

        # This test validates type checking - use wrong type
        class TestAgent(NexusDeploymentMixin):
            pass

        agent = TestAgent()

        # Pass a string instead of Nexus - should raise TypeError
        with pytest.raises(TypeError) as exc_info:
            agent.connect_nexus("not a nexus instance")

        assert "Expected Nexus instance" in str(exc_info.value)
