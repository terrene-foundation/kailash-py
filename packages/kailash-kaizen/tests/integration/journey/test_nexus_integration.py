"""
Integration tests for Journey Nexus Deployment (REQ-INT-005).

These are Tier 2 (Integration) tests that validate Journey deployment with Nexus.
NO MOCKING - tests use real OpenAI LLM for agent execution tests.

Infrastructure tests (session management, adapter creation) don't require LLM.
Agent execution tests require OPENAI_API_KEY to be set.

Prerequisites:
    - kailash-nexus installed: `pip install kailash-nexus`
    - For agent tests: OPENAI_API_KEY set in .env file

Usage:
    pytest tests/integration/journey/test_nexus_integration.py -v

References:
    - docs/plans/03-journey/06-integration.md
    - TODO-JO-005: Integration Requirements (REQ-INT-005)
"""

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import pytest
from dotenv import load_dotenv

from kaizen.core.base_agent import BaseAgent
from kaizen.journey import (
    Journey,
    JourneyConfig,
    JourneyNexusAdapter,
    JourneySessionManager,
    NexusSessionInfo,
    Pathway,
    deploy_journey_to_nexus,
)
from kaizen.journey.behaviors import ReturnToPrevious
from kaizen.signatures import InputField, OutputField, Signature

# Load environment variables from .env
load_dotenv()

# Check Nexus availability
try:
    from nexus import Nexus

    NEXUS_AVAILABLE = True
except ImportError:
    NEXUS_AVAILABLE = False
    Nexus = None


# ============================================================================
# OpenAI Availability Checks (for NO MOCKING compliance)
# ============================================================================

# Use OpenAI for integration tests (real LLM, fast responses)
# Use gpt-4o-mini which supports temperature parameter (gpt-5-nano doesn't)
OPENAI_MODEL = "gpt-4o-mini"  # Cost-effective, supports all parameters
OPENAI_PROVIDER = "openai"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def is_openai_available() -> bool:
    """Check if OpenAI API key is configured."""
    return bool(OPENAI_API_KEY)


OPENAI_AVAILABLE = is_openai_available()
OPENAI_SKIP_REASON = "OPENAI_API_KEY not set in environment"


# ============================================================================
# Test Fixtures - Journey Definition
# ============================================================================


class IntakeSignature(Signature):
    """Signature for intake pathway."""

    message: str = InputField(description="User message")
    response: str = OutputField(description="Agent response")
    customer_name: str = OutputField(description="Extracted customer name")


class ServiceSignature(Signature):
    """Signature for service pathway."""

    message: str = InputField(description="User message")
    customer_name: str = InputField(description="Customer name from context")
    response: str = OutputField(description="Service response")
    issue_type: str = OutputField(description="Type of issue")


class FAQSignature(Signature):
    """Signature for FAQ pathway."""

    message: str = InputField(description="User question")
    response: str = OutputField(description="FAQ answer")


@dataclass
class OpenAIAgentConfig:
    """Config for OpenAI agent (real LLM for Tier 2 integration tests)."""

    llm_provider: str = OPENAI_PROVIDER
    model: str = OPENAI_MODEL
    temperature: float = 0.7


class IntakeAgent(BaseAgent):
    """Intake agent for testing with real OpenAI."""

    def __init__(self, config: OpenAIAgentConfig):
        super().__init__(config=config, signature=IntakeSignature())

    def process(self, message: str) -> Dict[str, Any]:
        return self.run(message=message)


class ServiceAgent(BaseAgent):
    """Service agent for testing with real OpenAI."""

    def __init__(self, config: OpenAIAgentConfig):
        super().__init__(config=config, signature=ServiceSignature())


class FAQAgent(BaseAgent):
    """FAQ agent for testing with real OpenAI."""

    def __init__(self, config: OpenAIAgentConfig):
        super().__init__(config=config, signature=FAQSignature())


class CustomerServiceJourney(Journey):
    """Customer service journey for testing."""

    __entry_pathway__ = "intake"

    class IntakePath(Pathway):
        __name__ = "intake"
        __signature__ = IntakeSignature
        __agents__ = ["intake_agent"]
        __accumulate__ = ["customer_name"]
        __next__ = "service"

    class ServicePath(Pathway):
        __name__ = "service"
        __signature__ = ServiceSignature
        __agents__ = ["service_agent"]
        __accumulate__ = ["issue_type"]

    class FAQPath(Pathway):
        __name__ = "faq"
        __signature__ = FAQSignature
        __agents__ = ["faq_agent"]
        __return_behavior__ = ReturnToPrevious()


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def journey_class():
    """Get the test journey class."""
    return CustomerServiceJourney


@pytest.fixture
def openai_config():
    """Create Ollama agent config for real LLM tests."""
    return OpenAIAgentConfig()


@pytest.fixture
def intake_agent(openai_config):
    """Create intake agent with real OpenAI."""
    return IntakeAgent(openai_config)


@pytest.fixture
def service_agent(openai_config):
    """Create service agent with real OpenAI."""
    return ServiceAgent(openai_config)


@pytest.fixture
def faq_agent(openai_config):
    """Create FAQ agent with real OpenAI."""
    return FAQAgent(openai_config)


@pytest.fixture
def all_agents(intake_agent, service_agent, faq_agent):
    """Get all agents as dict (requires Ollama)."""
    return {
        "intake_agent": intake_agent,
        "service_agent": service_agent,
        "faq_agent": faq_agent,
    }


@pytest.fixture
def journey_adapter(journey_class):
    """Create journey adapter."""
    return JourneyNexusAdapter(
        journey_class=journey_class,
        workflow_name="customer_service",
        description="Customer service journey for testing",
    )


@pytest.fixture
def session_manager():
    """Create session manager."""
    return JourneySessionManager()


# ============================================================================
# Session Manager Tests
# ============================================================================


class TestJourneySessionManager:
    """Integration tests for JourneySessionManager."""

    def test_create_session(self, session_manager):
        """Test session creation."""
        session_id = session_manager.create_session(
            user_id="user-123",
            channel="api",
            journey_class_name="CustomerServiceJourney",
        )

        assert session_id is not None
        assert len(session_id) > 0

    def test_get_session(self, session_manager):
        """Test session retrieval."""
        session_id = session_manager.create_session(
            user_id="user-456",
            channel="cli",
            journey_class_name="CustomerServiceJourney",
        )

        session = session_manager.get_session(session_id)

        assert session is not None
        assert isinstance(session, NexusSessionInfo)
        assert session.session_id == session_id
        assert session.user_id == "user-456"
        assert session.channel == "cli"

    def test_get_user_sessions(self, session_manager):
        """Test getting all sessions for a user."""
        user_id = "multi-session-user"

        # Create multiple sessions
        session1 = session_manager.create_session(
            user_id=user_id,
            channel="api",
            journey_class_name="CustomerServiceJourney",
        )
        session2 = session_manager.create_session(
            user_id=user_id,
            channel="cli",
            journey_class_name="CustomerServiceJourney",
        )

        # Get all sessions
        sessions = session_manager.get_user_sessions(user_id)

        assert len(sessions) == 2
        assert session1 in sessions
        assert session2 in sessions

    def test_cleanup_session(self, session_manager):
        """Test session cleanup."""
        session_id = session_manager.create_session(
            user_id="cleanup-user",
            channel="api",
            journey_class_name="CustomerServiceJourney",
        )

        # Verify session exists
        assert session_manager.get_session(session_id) is not None

        # Cleanup
        result = session_manager.cleanup_session(session_id)

        assert result is True
        assert session_manager.get_session(session_id) is None

    def test_cleanup_user_sessions(self, session_manager):
        """Test cleanup of all user sessions."""
        user_id = "cleanup-all-user"

        # Create multiple sessions
        session_manager.create_session(
            user_id=user_id,
            channel="api",
            journey_class_name="CustomerServiceJourney",
        )
        session_manager.create_session(
            user_id=user_id,
            channel="cli",
            journey_class_name="CustomerServiceJourney",
        )

        # Cleanup all
        count = session_manager.cleanup_user_sessions(user_id)

        assert count == 2
        assert len(session_manager.get_user_sessions(user_id)) == 0

    def test_session_with_metadata(self, session_manager):
        """Test session creation with metadata."""
        session_id = session_manager.create_session(
            user_id="metadata-user",
            channel="mcp",
            journey_class_name="CustomerServiceJourney",
            metadata={"source": "test", "priority": "high"},
        )

        session = session_manager.get_session(session_id)

        assert session.metadata["source"] == "test"
        assert session.metadata["priority"] == "high"

    def test_session_last_accessed_updated(self, session_manager):
        """Test that last_accessed is updated on get."""
        session_id = session_manager.create_session(
            user_id="access-user",
            channel="api",
            journey_class_name="CustomerServiceJourney",
        )

        session1 = session_manager.get_session(session_id)
        first_access = session1.last_accessed

        # Wait a tiny bit and access again
        import time

        time.sleep(0.01)

        session2 = session_manager.get_session(session_id)
        second_access = session2.last_accessed

        assert second_access >= first_access


# ============================================================================
# Journey Adapter Tests
# ============================================================================


class TestJourneyNexusAdapter:
    """Integration tests for JourneyNexusAdapter."""

    def test_adapter_creation(self, journey_adapter, journey_class):
        """Test adapter creation."""
        assert journey_adapter.journey_class == journey_class
        assert journey_adapter.workflow_name == "customer_service"
        assert "Customer service" in journey_adapter.description

    def test_register_agent(self, journey_adapter, intake_agent):
        """Test agent registration."""
        journey_adapter.register_agent("intake_agent", intake_agent)

        assert "intake_agent" in journey_adapter._agents
        assert journey_adapter._agents["intake_agent"] == intake_agent

    def test_to_workflow(self, journey_adapter):
        """Test workflow definition generation."""
        workflow_def = journey_adapter.to_workflow()

        assert workflow_def["name"] == "customer_service"
        assert callable(workflow_def["handler"])
        assert "description" in workflow_def
        assert "input_schema" in workflow_def
        assert "output_schema" in workflow_def

    def test_workflow_input_schema(self, journey_adapter):
        """Test workflow input schema structure."""
        workflow_def = journey_adapter.to_workflow()
        input_schema = workflow_def["input_schema"]

        assert input_schema["type"] == "object"
        assert "message" in input_schema["properties"]
        assert "session_id" in input_schema["properties"]
        assert "user_id" in input_schema["properties"]
        assert "channel" in input_schema["properties"]
        assert "message" in input_schema["required"]

    def test_workflow_output_schema(self, journey_adapter):
        """Test workflow output schema structure."""
        workflow_def = journey_adapter.to_workflow()
        output_schema = workflow_def["output_schema"]

        assert output_schema["type"] == "object"
        assert "response" in output_schema["properties"]
        assert "session_id" in output_schema["properties"]
        assert "pathway_id" in output_schema["properties"]
        assert "pathway_changed" in output_schema["properties"]

    def test_create_rest_endpoint(self, journey_adapter):
        """Test REST endpoint definition generation."""
        endpoint = journey_adapter.create_rest_endpoint()

        assert endpoint["path"] == "/journeys/customer_service"
        assert endpoint["method"] == "POST"
        assert callable(endpoint["handler"])
        assert "request_model" in endpoint
        assert "response_model" in endpoint

    def test_create_cli_command(self, journey_adapter):
        """Test CLI command definition generation."""
        cmd = journey_adapter.create_cli_command()

        assert cmd["name"] == "customer_service"
        assert callable(cmd["handler"])
        assert len(cmd["args"]) > 0

        # Check required message arg
        message_arg = next((a for a in cmd["args"] if a["name"] == "message"), None)
        assert message_arg is not None
        assert message_arg["required"] is True

    def test_create_mcp_tool(self, journey_adapter):
        """Test MCP tool definition generation."""
        tool = journey_adapter.create_mcp_tool()

        assert tool["name"] == "customer_service"
        assert "description" in tool
        assert "inputSchema" in tool
        assert callable(tool["handler"])

    def test_pre_process_hook(self, journey_adapter):
        """Test pre-processing hook registration."""
        hook_calls = []

        def pre_hook(request):
            hook_calls.append(request)
            request["user_id"] = "hooked-user"
            return request

        journey_adapter.add_pre_process_hook(pre_hook)

        assert len(journey_adapter._pre_process_hooks) == 1

    def test_post_process_hook(self, journey_adapter):
        """Test post-processing hook registration."""
        hook_calls = []

        def post_hook(response):
            hook_calls.append(response)
            response["hooked"] = True
            return response

        journey_adapter.add_post_process_hook(post_hook)

        assert len(journey_adapter._post_process_hooks) == 1

    def test_snake_case_conversion(self):
        """Test CamelCase to snake_case conversion."""
        assert (
            JourneyNexusAdapter._to_snake_case("CustomerServiceJourney")
            == "customer_service_journey"
        )
        assert JourneyNexusAdapter._to_snake_case("FAQ") == "faq"
        assert JourneyNexusAdapter._to_snake_case("HTTPClient") == "http_client"

    def test_default_workflow_name(self, journey_class):
        """Test default workflow name from class name."""
        adapter = JourneyNexusAdapter(journey_class=journey_class)

        assert adapter.workflow_name == "customer_service_journey"


# ============================================================================
# Nexus Integration Tests (Requires Nexus)
# ============================================================================


@pytest.mark.skipif(not NEXUS_AVAILABLE, reason="Nexus not available")
class TestNexusIntegration:
    """Integration tests requiring Nexus."""

    @pytest.fixture
    def nexus_app(self):
        """Create Nexus app for testing."""
        return Nexus(auto_discovery=False)

    def test_register_with_nexus(self, journey_adapter, all_agents, nexus_app):
        """Test registering journey with Nexus."""
        # Register agents
        for agent_id, agent in all_agents.items():
            journey_adapter.register_agent(agent_id, agent)

        # Register with Nexus
        journey_adapter.register_with_nexus(nexus_app)

        # Verify registration (depends on Nexus internals)
        # Basic check - no exception raised

    def test_deploy_journey_to_nexus(self, journey_class, all_agents, nexus_app):
        """Test convenience deployment function."""
        adapter = deploy_journey_to_nexus(
            journey_class=journey_class,
            nexus=nexus_app,
            agents=all_agents,
            workflow_name="test_journey",
        )

        assert adapter is not None
        assert adapter.workflow_name == "test_journey"
        assert len(adapter._agents) == 3


# ============================================================================
# Multi-Channel Session Tests
# ============================================================================


class TestMultiChannelSessions:
    """Tests for multi-channel session management."""

    def test_session_across_channels(self, session_manager):
        """Test session accessible across channels."""
        # Create session via API
        session_id = session_manager.create_session(
            user_id="cross-channel-user",
            channel="api",
            journey_class_name="CustomerServiceJourney",
        )

        # Access from CLI (simulated)
        session = session_manager.get_session(session_id)
        assert session.channel == "api"  # Original channel preserved

        # Access from MCP (simulated)
        session = session_manager.get_session(session_id)
        assert session is not None

    def test_user_sessions_across_channels(self, session_manager):
        """Test user can have sessions across channels."""
        user_id = "multi-channel-user"

        # Create sessions on different channels
        api_session = session_manager.create_session(
            user_id=user_id,
            channel="api",
            journey_class_name="CustomerServiceJourney",
        )
        cli_session = session_manager.create_session(
            user_id=user_id,
            channel="cli",
            journey_class_name="CustomerServiceJourney",
        )
        mcp_session = session_manager.create_session(
            user_id=user_id,
            channel="mcp",
            journey_class_name="CustomerServiceJourney",
        )

        # Get all user sessions
        all_sessions = session_manager.get_user_sessions(user_id)

        assert len(all_sessions) == 3
        assert api_session in all_sessions
        assert cli_session in all_sessions
        assert mcp_session in all_sessions


# ============================================================================
# Workflow Handler Tests (Requires OpenAI for real agent execution)
# ============================================================================


@pytest.mark.skipif(not OPENAI_AVAILABLE, reason=OPENAI_SKIP_REASON)
class TestWorkflowHandler:
    """Tests for workflow handler behavior. Requires OpenAI for real agent execution."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)  # LLM calls may take time
    async def test_workflow_handler_creates_session(self, journey_adapter, all_agents):
        """Test workflow handler creates session for new requests."""
        # Register agents
        for agent_id, agent in all_agents.items():
            journey_adapter.register_agent(agent_id, agent)

        workflow_def = journey_adapter.to_workflow()
        handler = workflow_def["handler"]

        # Call handler without session_id (should create new session)
        result = await handler(
            message="Hello, I need help",
            user_id="test-user",
            channel="api",
        )

        # Should have created session
        assert "session_id" in result

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)  # LLM calls may take time
    async def test_workflow_handler_uses_existing_session(
        self, journey_adapter, all_agents
    ):
        """Test workflow handler uses existing session."""
        # Register agents
        for agent_id, agent in all_agents.items():
            journey_adapter.register_agent(agent_id, agent)

        # Create session first
        session_id = journey_adapter.session_manager.create_session(
            user_id="existing-session-user",
            channel="api",
            journey_class_name="CustomerServiceJourney",
        )

        workflow_def = journey_adapter.to_workflow()
        handler = workflow_def["handler"]

        # Call handler with existing session_id
        result = await handler(
            message="Continue conversation",
            session_id=session_id,
            user_id="existing-session-user",
            channel="api",
        )

        # Should use same session
        assert result.get("session_id") == session_id

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)  # LLM calls may take time
    async def test_workflow_handler_invalid_session(self, journey_adapter, all_agents):
        """Test workflow handler handles invalid session gracefully."""
        # Register agents
        for agent_id, agent in all_agents.items():
            journey_adapter.register_agent(agent_id, agent)

        workflow_def = journey_adapter.to_workflow()
        handler = workflow_def["handler"]

        # Call handler with non-existent session_id
        result = await handler(
            message="Should fail",
            session_id="non-existent-session-123",
            channel="api",
        )

        # Should return error
        assert "error" in result

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)  # LLM calls may take time
    async def test_workflow_handler_pre_hook(self, journey_adapter, all_agents):
        """Test pre-process hook is called."""
        hook_calls = []

        def pre_hook(request):
            hook_calls.append(request.copy())
            return request

        journey_adapter.add_pre_process_hook(pre_hook)

        # Register agents
        for agent_id, agent in all_agents.items():
            journey_adapter.register_agent(agent_id, agent)

        workflow_def = journey_adapter.to_workflow()
        handler = workflow_def["handler"]

        await handler(
            message="Test message",
            user_id="hook-test-user",
            channel="api",
        )

        assert len(hook_calls) == 1
        assert hook_calls[0]["message"] == "Test message"

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)  # LLM calls may take time
    async def test_workflow_handler_post_hook(self, journey_adapter, all_agents):
        """Test post-process hook is called."""
        hook_calls = []

        def post_hook(response):
            hook_calls.append(response.copy())
            response["custom_field"] = "added"
            return response

        journey_adapter.add_post_process_hook(post_hook)

        # Register agents
        for agent_id, agent in all_agents.items():
            journey_adapter.register_agent(agent_id, agent)

        workflow_def = journey_adapter.to_workflow()
        handler = workflow_def["handler"]

        result = await handler(
            message="Test message",
            user_id="post-hook-user",
            channel="api",
        )

        assert len(hook_calls) == 1
        # Post hook should have been called and added field
        assert result.get("custom_field") == "added"


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_session_with_empty_user_id(self, session_manager):
        """Test anonymous session (empty user_id)."""
        session_id = session_manager.create_session(
            user_id="",
            channel="api",
            journey_class_name="CustomerServiceJourney",
        )

        session = session_manager.get_session(session_id)
        assert session is not None
        assert session.user_id == ""

    def test_cleanup_nonexistent_session(self, session_manager):
        """Test cleanup of non-existent session."""
        result = session_manager.cleanup_session("nonexistent-session-id")
        assert result is False

    def test_get_nonexistent_session(self, session_manager):
        """Test getting non-existent session returns None."""
        session = session_manager.get_session("nonexistent-session-id")
        assert session is None

    def test_get_sessions_for_unknown_user(self, session_manager):
        """Test getting sessions for unknown user returns empty list."""
        sessions = session_manager.get_user_sessions("unknown-user-id")
        assert sessions == []

    def test_adapter_with_custom_config(self, journey_class):
        """Test adapter with custom journey config."""
        config = JourneyConfig(
            max_pathway_depth=5,
            pathway_timeout_seconds=60.0,
        )

        adapter = JourneyNexusAdapter(
            journey_class=journey_class,
            config=config,
        )

        assert adapter.config == config

    @pytest.mark.skipif(not OPENAI_AVAILABLE, reason=OPENAI_SKIP_REASON)
    def test_multiple_agent_registration(
        self, journey_adapter, intake_agent, service_agent
    ):
        """Test registering multiple agents."""
        journey_adapter.register_agent("agent1", intake_agent)
        journey_adapter.register_agent("agent2", service_agent)

        assert len(journey_adapter._agents) == 2

    @pytest.mark.skipif(not OPENAI_AVAILABLE, reason=OPENAI_SKIP_REASON)
    def test_overwrite_agent_registration(
        self, journey_adapter, intake_agent, openai_config
    ):
        """Test overwriting agent registration."""
        agent1 = intake_agent
        agent2 = IntakeAgent(openai_config)  # Create second instance

        journey_adapter.register_agent("same_id", agent1)
        journey_adapter.register_agent("same_id", agent2)

        # Should overwrite
        assert journey_adapter._agents["same_id"] == agent2
