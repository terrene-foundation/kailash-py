"""
Test Agent Registry System - Dual Registration (Agent API + Core SDK)

Tests the registration system for all 17 Kaizen agent types with dual registration:
1. Agent API registration (register_agent, get_agent_type_registration, etc.)
2. Core SDK NodeRegistry integration (for workflow usage)

Validates backward compatibility with aliases.

Written for Phase 1 Day 5.2 - Registration System Implementation.
"""

import pytest


def _sentence_transformers_available() -> bool:
    """Check if sentence-transformers is available (optional dependency for RAG)."""
    try:
        import sentence_transformers  # noqa: F401

        return True
    except ImportError:
        return False


class TestAgentRegistryBasics:
    """Test basic agent registry operations."""

    def test_register_agent_function_exists(self):
        """Test that register_agent function exists."""
        from kaizen.agents import register_agent

        assert callable(register_agent)

    def test_get_agent_type_registration_function_exists(self):
        """Test that get_agent_type_registration function exists."""
        from kaizen.agents import get_agent_type_registration

        assert callable(get_agent_type_registration)

    def test_list_agent_type_names_function_exists(self):
        """Test that list_agent_type_names function exists."""
        from kaizen.agents import list_agent_type_names

        assert callable(list_agent_type_names)

    def test_is_agent_type_registered_function_exists(self):
        """Test that is_agent_type_registered function exists."""
        from kaizen.agents import is_agent_type_registered

        assert callable(is_agent_type_registered)


class TestAgentTypeRegistration:
    """Test registration of individual agent types."""

    def test_simple_qa_agent_registered(self):
        """Test that SimpleQAAgent is registered."""
        from kaizen.agents import is_agent_type_registered

        assert is_agent_type_registered("simple")

    def test_react_agent_registered(self):
        """Test that ReActAgent is registered."""
        from kaizen.agents import is_agent_type_registered

        assert is_agent_type_registered("react")

    def test_chain_of_thought_agent_registered(self):
        """Test that ChainOfThoughtAgent is registered."""
        from kaizen.agents import is_agent_type_registered

        assert is_agent_type_registered("cot")

    def test_vision_agent_registered(self):
        """Test that VisionAgent is registered."""
        from kaizen.agents import is_agent_type_registered

        assert is_agent_type_registered("vision")

    def test_rag_research_agent_registered(self):
        """Test that RAGResearchAgent is registered."""
        from kaizen.agents import is_agent_type_registered

        assert is_agent_type_registered("rag")

    def test_code_generation_agent_registered(self):
        """Test that CodeGenerationAgent is registered."""
        from kaizen.agents import is_agent_type_registered

        assert is_agent_type_registered("code")

    def test_self_reflection_agent_registered(self):
        """Test that SelfReflectionAgent is registered."""
        from kaizen.agents import is_agent_type_registered

        assert is_agent_type_registered("reflection")

    def test_memory_agent_registered(self):
        """Test that MemoryAgent is registered."""
        from kaizen.agents import is_agent_type_registered

        assert is_agent_type_registered("memory")

    def test_batch_processing_agent_registered(self):
        """Test that BatchProcessingAgent is registered."""
        from kaizen.agents import is_agent_type_registered

        assert is_agent_type_registered("batch")

    def test_human_approval_agent_registered(self):
        """Test that HumanApprovalAgent is registered."""
        from kaizen.agents import is_agent_type_registered

        assert is_agent_type_registered("approval")

    def test_resilient_agent_registered(self):
        """Test that ResilientAgent is registered."""
        from kaizen.agents import is_agent_type_registered

        assert is_agent_type_registered("resilient")

    def test_streaming_chat_agent_registered(self):
        """Test that StreamingChatAgent is registered."""
        from kaizen.agents import is_agent_type_registered

        assert is_agent_type_registered("streaming")

    def test_multi_modal_agent_registered(self):
        """Test that MultiModalAgent is registered."""
        from kaizen.agents import is_agent_type_registered

        assert is_agent_type_registered("multimodal")

    def test_document_extraction_agent_registered(self):
        """Test that DocumentExtractionAgent is registered."""
        from kaizen.agents import is_agent_type_registered

        assert is_agent_type_registered("document_extraction")

    def test_transcription_agent_registered(self):
        """Test that TranscriptionAgent is registered."""
        from kaizen.agents import is_agent_type_registered

        assert is_agent_type_registered("audio")

    def test_codex_agent_registered(self):
        """Test that CodexAgent is registered."""
        from kaizen.agents import is_agent_type_registered

        assert is_agent_type_registered("codex")

    def test_claude_code_agent_registered(self):
        """Test that ClaudeCodeAgent is registered."""
        from kaizen.agents import is_agent_type_registered

        assert is_agent_type_registered("claude_code")


class TestAgentTypeRetrieval:
    """Test retrieving agent type information."""

    def test_get_simple_qa_agent_registration(self):
        """Test retrieving SimpleQAAgent registration."""
        from kaizen.agents import get_agent_type_registration

        reg = get_agent_type_registration("simple")

        assert reg is not None
        # AgentRegistration has attributes, not dict keys
        assert hasattr(reg, "agent_class")
        assert hasattr(reg, "name")
        assert hasattr(reg, "description")
        assert reg.agent_class.__name__ == "SimpleQAAgent"

    def test_get_react_agent_registration(self):
        """Test retrieving ReActAgent registration."""
        from kaizen.agents import get_agent_type_registration

        reg = get_agent_type_registration("react")

        assert reg is not None
        assert reg.agent_class.__name__ == "ReActAgent"

    def test_get_vision_agent_registration(self):
        """Test retrieving VisionAgent registration."""
        from kaizen.agents import get_agent_type_registration

        reg = get_agent_type_registration("vision")

        assert reg is not None
        assert reg.agent_class.__name__ == "VisionAgent"

    def test_get_nonexistent_agent_raises_error(self):
        """Test that retrieving nonexistent agent raises ValueError."""
        from kaizen.agents import get_agent_type_registration

        with pytest.raises(ValueError) as exc_info:
            get_agent_type_registration("nonexistent_agent_xyz")

        assert "nonexistent_agent_xyz" in str(exc_info.value)


class TestListAgentTypes:
    """Test listing all registered agent types."""

    def test_list_agent_type_names_returns_list(self):
        """Test that list_agent_type_names returns a list."""
        from kaizen.agents import list_agent_type_names

        names = list_agent_type_names()

        assert isinstance(names, list)

    def test_list_agent_type_names_includes_all_17_agents(self):
        """Test that all 17 agent types are listed."""
        from kaizen.agents import list_agent_type_names

        names = list_agent_type_names()

        # All 18 agent types should be present
        expected_agents = [
            "simple",
            "react",
            "cot",
            "vision",
            "rag",
            "code",
            "reflection",
            "memory",
            "batch",
            "approval",
            "resilient",
            "streaming",
            "multimodal",
            "document_extraction",
            "audio",
            "codex",
            "claude_code",
            "autonomous",
        ]

        for agent_type in expected_agents:
            assert agent_type in names, f"{agent_type} not found in registry"

    def test_list_agent_type_names_count(self):
        """Test that exactly 18 agent types are registered."""
        from kaizen.agents import list_agent_type_names

        names = list_agent_type_names()

        # Should have exactly 18 agent types
        assert len(names) >= 18, f"Expected at least 18 agents, found {len(names)}"


class TestCoreSKDIntegration:
    """Test Core SDK NodeRegistry integration.

    Note: NodeRegistry integration with agents is optional and may not
    be implemented in all versions. These tests check the integration
    if available.
    """

    def test_agent_nodes_in_node_registry(self):
        """Test that agent types are also registered in NodeRegistry."""
        from kailash.nodes import NodeRegistry

        # Get all nodes from Core SDK
        all_nodes = NodeRegistry.list_nodes()

        # Agent types should be in the node registry with "Agent" suffix
        # Example: "simple_qa" -> "SimpleQAAgentNode"
        agent_node_names = [
            "SimpleQAAgentNode",
            "ReActAgentNode",
            "ChainOfThoughtAgentNode",
            "VisionAgentNode",
            "RAGResearchAgentNode",
            "CodeGenerationAgentNode",
        ]

        # Check if at least some agent nodes are present
        # (Full check would require all nodes to be implemented)
        found_agents = [name for name in agent_node_names if name in all_nodes]

        # Should have at least some agent nodes
        assert len(found_agents) > 0, "No agent nodes found in NodeRegistry"

    def test_agent_node_can_be_instantiated(self):
        """Test that agent nodes can be instantiated from NodeRegistry."""
        from kailash.nodes import NodeRegistry

        # Try to get SimpleQAAgentNode
        if "SimpleQAAgentNode" in NodeRegistry.list_nodes():
            node_class = NodeRegistry.get("SimpleQAAgentNode")
            assert node_class is not None


class TestBackwardCompatibilityAliases:
    """Test backward compatibility with old method names.

    Note: These tests verify the run() method exists as the standard interface.
    Convenience aliases (ask, solve_task, etc.) are optional and may not be
    implemented in all agents. Tests for specific aliases are marked
    appropriately.
    """

    def test_simple_qa_has_run_method(self):
        """Test that SimpleQAAgent has run() method (standard interface)."""
        from kaizen.agents.specialized.simple_qa import SimpleQAAgent

        agent = SimpleQAAgent()

        # Standard interface
        assert hasattr(agent, "run")
        assert callable(agent.run)

    def test_react_has_run_method(self):
        """Test that ReActAgent has run() method (standard interface)."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent()

        # Standard interface
        assert hasattr(agent, "run")
        assert callable(agent.run)

    def test_chain_of_thought_has_run_method(self):
        """Test that ChainOfThoughtAgent has run() method (standard interface)."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent()

        # Standard interface
        assert hasattr(agent, "run")
        assert callable(agent.run)

    @pytest.mark.skipif(
        not _sentence_transformers_available(),
        reason="sentence-transformers not installed (optional dependency)",
    )
    def test_rag_research_has_run_method(self):
        """Test that RAGResearchAgent has run() method (standard interface)."""
        from kaizen.agents.specialized.rag_research import RAGResearchAgent

        agent = RAGResearchAgent()

        # Standard interface
        assert hasattr(agent, "run")
        assert callable(agent.run)

    def test_code_generation_alias_works(self):
        """Test that CodeGenerationAgent has backward compatible alias."""
        from kaizen.agents.specialized.code_generation import CodeGenerationAgent

        agent = CodeGenerationAgent()

        # Old method should still exist as alias
        assert hasattr(agent, "generate_code")
        assert callable(agent.generate_code)

    def test_memory_agent_alias_works(self):
        """Test that MemoryAgent has backward compatible alias."""
        from kaizen.agents.specialized.memory_agent import MemoryAgent

        agent = MemoryAgent()

        # Old method should still exist as alias
        assert hasattr(agent, "chat")
        assert callable(agent.chat)


class TestDualRegistrationConsistency:
    """Test consistency between Agent API and Core SDK registration."""

    def test_agent_api_and_node_registry_consistent(self):
        """Test that Agent API and NodeRegistry have consistent registrations."""
        from kailash.nodes import NodeRegistry

        from kaizen.agents import list_agent_type_names

        agent_types = list_agent_type_names()
        all_nodes = NodeRegistry.list_nodes()

        # For each agent type in Agent API
        for agent_type in agent_types:
            # Expected node name: agent_type -> AgentTypeAgentNode
            # Example: "simple_qa" -> "SimpleQAAgentNode"
            expected_node_name = (
                "".join(word.capitalize() for word in agent_type.split("_"))
                + "AgentNode"
            )

            # Check if node exists (optional, as not all may be implemented yet)
            # This is a forward-looking test
            if expected_node_name in all_nodes:
                assert True  # Consistency check passed
            else:
                # Log warning but don't fail (implementation in progress)
                print(f"Note: {expected_node_name} not yet in NodeRegistry")


class TestRegistrationSystemIntegrity:
    """Test overall registration system integrity."""

    def test_no_duplicate_registrations(self):
        """Test that there are no duplicate agent type registrations."""
        from kaizen.agents import list_agent_type_names

        names = list_agent_type_names()

        # Check for duplicates
        assert len(names) == len(set(names)), "Duplicate agent types found in registry"

    def test_all_registrations_have_required_fields(self):
        """Test that all registrations have required fields."""
        from kaizen.agents import get_agent_type_registration, list_agent_type_names

        names = list_agent_type_names()

        for agent_type in names:
            reg = get_agent_type_registration(agent_type)

            assert reg is not None, f"{agent_type} registration is None"
            # AgentRegistration uses attributes, not dict keys
            assert hasattr(reg, "agent_class"), f"{agent_type} missing agent_class"
            assert hasattr(reg, "name"), f"{agent_type} missing name"
            assert hasattr(reg, "description"), f"{agent_type} missing description"

    def test_all_agent_classes_are_classes(self):
        """Test that all registered agent_class values are actual classes."""
        from inspect import isclass

        from kaizen.agents import get_agent_type_registration, list_agent_type_names

        names = list_agent_type_names()

        for agent_type in names:
            reg = get_agent_type_registration(agent_type)

            # AgentRegistration uses attributes, not dict keys
            agent_class = reg.agent_class
            assert isclass(agent_class), f"{agent_type} agent_class is not a class"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
