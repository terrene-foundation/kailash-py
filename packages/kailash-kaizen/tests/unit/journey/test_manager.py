"""
Unit tests for enhanced PathwayManager (TODO-JO-004).

Tests cover:
- REQ-PM-001: PathwayManager with full session management
- JourneyResponse dataclass
- Global transition handling
- Pathway switching with stack
- Context accumulation integration
- Return behavior handling

These are Tier 1 (Unit) tests that use mock agents and don't make real LLM calls.
"""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen.journey import (
    Journey,
    JourneyConfig,
    Pathway,
    PathwayContext,
    PathwayResult,
    ReturnToPrevious,
    ReturnToSpecific,
)
from kaizen.journey.errors import (
    MaxPathwayDepthError,
    PathwayNotFoundError,
    SessionNotStartedError,
)
from kaizen.journey.manager import JourneyResponse, PathwayManager
from kaizen.journey.transitions import IntentTrigger, Transition
from kaizen.signatures import InputField, OutputField, Signature

# ============================================================================
# Test Fixtures
# ============================================================================


class SimpleSignature(Signature):
    """Simple test signature."""

    message: str = InputField(desc="User message")
    response: str = OutputField(desc="Agent response")


class IntakeSignature(Signature):
    """Intake pathway signature."""

    message: str = InputField(desc="User message")
    response: str = OutputField(desc="Agent response")
    customer_name: str = OutputField(desc="Customer name")


class BookingSignature(Signature):
    """Booking pathway signature."""

    request: str = InputField(desc="Booking request")
    response: str = OutputField(desc="Response")
    booking_id: str = OutputField(desc="Booking ID")


class FAQSignature(Signature):
    """FAQ pathway signature."""

    question: str = InputField(desc="FAQ question")
    answer: str = OutputField(desc="FAQ answer")


@pytest.fixture
def config():
    """Create default JourneyConfig."""
    return JourneyConfig()


@pytest.fixture
def mock_agent():
    """Create a mock agent for testing."""
    agent = MagicMock()
    agent.run = MagicMock(return_value={"response": "Test response"})
    return agent


@pytest.fixture
def mock_async_agent():
    """Create a mock async agent for testing."""
    agent = MagicMock()
    agent.run = AsyncMock(return_value={"response": "Async response"})
    return agent


def create_simple_journey():
    """Create a simple journey for testing."""

    class SimpleJourney(Journey):
        __entry_pathway__ = "main"

        class MainPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["main_agent"]

    return SimpleJourney


def create_multi_pathway_journey():
    """Create journey with multiple pathways."""

    class MultiJourney(Journey):
        __entry_pathway__ = "intake"

        class IntakePath(Pathway):
            __signature__ = IntakeSignature
            __agents__ = ["intake_agent"]
            __accumulate__ = ["customer_name"]
            __next__ = "booking"

        class BookingPath(Pathway):
            __signature__ = BookingSignature
            __agents__ = ["booking_agent"]
            __accumulate__ = ["booking_id"]

        class FAQPath(Pathway):
            __signature__ = FAQSignature
            __agents__ = ["faq_agent"]
            __return_behavior__ = ReturnToPrevious()

    return MultiJourney


def create_journey_with_transitions():
    """Create journey with global transitions."""

    class TransitionJourney(Journey):
        __entry_pathway__ = "main"
        __transitions__ = [
            Transition(
                trigger=IntentTrigger(patterns=["help", "faq"]),
                from_pathway="*",
                to_pathway="faq",
                priority=10,
            ),
            Transition(
                trigger=IntentTrigger(patterns=["cancel"]),
                from_pathway="*",
                to_pathway="cancellation",
                priority=5,
            ),
        ]

        class MainPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["main_agent"]

        class FAQPath(Pathway):
            __signature__ = FAQSignature
            __agents__ = ["faq_agent"]
            __return_behavior__ = ReturnToPrevious()

        class CancellationPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["cancel_agent"]

    return TransitionJourney


# ============================================================================
# JourneyResponse Tests
# ============================================================================


class TestJourneyResponse:
    """Tests for JourneyResponse dataclass."""

    def test_create_response(self):
        """Test creating JourneyResponse."""
        response = JourneyResponse(
            message="Hello!",
            pathway_id="intake",
            pathway_changed=False,
            accumulated_context={"name": "Alice"},
            metadata={"key": "value"},
        )

        assert response.message == "Hello!"
        assert response.pathway_id == "intake"
        assert response.pathway_changed is False
        assert response.accumulated_context["name"] == "Alice"
        assert response.metadata["key"] == "value"

    def test_response_default_metadata(self):
        """Test JourneyResponse with default metadata."""
        response = JourneyResponse(
            message="Test",
            pathway_id="main",
            pathway_changed=True,
            accumulated_context={},
        )

        assert response.metadata == {}


# ============================================================================
# PathwayManager Initialization Tests
# ============================================================================


class TestPathwayManagerInit:
    """Tests for PathwayManager initialization."""

    def test_init(self, config):
        """Test PathwayManager initialization."""
        JourneyClass = create_simple_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)

        assert manager.journey is journey
        assert manager.session_id == "test"
        assert manager.config is config
        assert manager._agents == {}
        assert manager._session is None


# ============================================================================
# Agent Registration Tests
# ============================================================================


class TestAgentRegistration:
    """Tests for agent registration."""

    def test_register_agent(self, config, mock_agent):
        """Test registering an agent."""
        JourneyClass = create_simple_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)

        manager.register_agent("main_agent", mock_agent)

        assert manager.get_agent("main_agent") is mock_agent

    def test_get_unregistered_agent(self, config):
        """Test getting unregistered agent returns None."""
        JourneyClass = create_simple_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)

        assert manager.get_agent("unknown") is None

    def test_list_agents(self, config, mock_agent):
        """Test listing registered agents."""
        JourneyClass = create_simple_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)

        manager.register_agent("agent1", mock_agent)
        manager.register_agent("agent2", mock_agent)

        agents = manager.list_agents()

        assert len(agents) == 2
        assert "agent1" in agents
        assert "agent2" in agents


# ============================================================================
# Session Management Tests
# ============================================================================


class TestSessionManagement:
    """Tests for session management."""

    @pytest.mark.asyncio
    async def test_start_session(self, config):
        """Test starting a session."""
        JourneyClass = create_simple_journey()
        journey = JourneyClass(session_id="test-123")
        manager = PathwayManager(journey, "test-123", config)

        session = await manager.start_session()

        assert session.session_id == "test-123"
        assert session.current_pathway_id == "main"
        assert session.pathway_stack == ["main"]

    @pytest.mark.asyncio
    async def test_start_session_with_initial_context(self, config):
        """Test starting session with initial context."""
        JourneyClass = create_simple_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)

        initial_ctx = {"user_id": "user-123", "locale": "en-US"}
        session = await manager.start_session(initial_context=initial_ctx)

        assert session.accumulated_context["user_id"] == "user-123"
        assert session.accumulated_context["locale"] == "en-US"

    @pytest.mark.asyncio
    async def test_get_session_state(self, config):
        """Test getting session state."""
        JourneyClass = create_simple_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)

        # Before start
        state = await manager.get_session_state()
        assert state is None

        # After start
        await manager.start_session()
        state = await manager.get_session_state()
        assert state is not None
        assert state.session_id == "test"


# ============================================================================
# Process Message Tests
# ============================================================================


class TestProcessMessage:
    """Tests for process_message method."""

    @pytest.mark.asyncio
    async def test_process_message_without_session_raises(self, config):
        """Test that process_message raises before session start."""
        JourneyClass = create_simple_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)

        with pytest.raises(SessionNotStartedError):
            await manager.process_message("Hello")

    @pytest.mark.asyncio
    async def test_process_message_basic(self, config, mock_agent):
        """Test basic message processing."""
        JourneyClass = create_simple_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)
        manager.register_agent("main_agent", mock_agent)

        await manager.start_session()

        # Mock pathway execution
        with patch.object(manager, "_execute_current_pathway") as mock_exec:
            mock_exec.return_value = PathwayResult(
                outputs={"response": "Hello there!"},
                accumulated={},
                next_pathway=None,
                is_complete=True,
            )

            response = await manager.process_message("Hello")

        assert response.message == "Hello there!"
        assert response.pathway_id == "main"
        assert response.pathway_changed is False

    @pytest.mark.asyncio
    async def test_process_message_adds_to_history(self, config, mock_agent):
        """Test that process_message adds to conversation history."""
        JourneyClass = create_simple_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)
        manager.register_agent("main_agent", mock_agent)

        await manager.start_session()

        with patch.object(manager, "_execute_current_pathway") as mock_exec:
            mock_exec.return_value = PathwayResult(
                outputs={"response": "Hi!"},
                accumulated={},
                next_pathway=None,
                is_complete=True,
            )

            await manager.process_message("Hello")

        session = await manager.get_session_state()

        # Should have user message and assistant response
        assert len(session.conversation_history) == 2
        assert session.conversation_history[0]["role"] == "user"
        assert session.conversation_history[0]["content"] == "Hello"
        assert session.conversation_history[1]["role"] == "assistant"
        assert session.conversation_history[1]["content"] == "Hi!"


# ============================================================================
# Transition Handling Tests
# ============================================================================


class TestTransitionHandling:
    """Tests for global transition handling."""

    @pytest.mark.asyncio
    async def test_transition_triggers_pathway_switch(self, config, mock_agent):
        """Test that matching transition triggers pathway switch."""
        JourneyClass = create_journey_with_transitions()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)
        manager.register_agent("main_agent", mock_agent)
        manager.register_agent("faq_agent", mock_agent)

        await manager.start_session()

        with patch.object(manager, "_execute_current_pathway") as mock_exec:
            # Return is_complete=False so ReturnToPrevious doesn't trigger
            mock_exec.return_value = PathwayResult(
                outputs={"answer": "FAQ answer"},
                accumulated={},
                next_pathway=None,
                is_complete=False,  # FAQ not complete yet
            )

            # "help" should trigger FAQ transition
            response = await manager.process_message("I need help")

        assert response.pathway_changed is True
        assert response.pathway_id == "faq"
        assert response.metadata["transition_triggered"] is True

    @pytest.mark.asyncio
    async def test_no_transition_when_no_match(self, config, mock_agent):
        """Test no transition when no pattern matches."""
        JourneyClass = create_journey_with_transitions()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)
        manager.register_agent("main_agent", mock_agent)

        await manager.start_session()

        with patch.object(manager, "_execute_current_pathway") as mock_exec:
            mock_exec.return_value = PathwayResult(
                outputs={"response": "Normal response"},
                accumulated={},
                next_pathway=None,
                is_complete=True,
            )

            response = await manager.process_message("Regular message")

        assert response.pathway_changed is False
        assert response.pathway_id == "main"
        assert response.metadata["transition_triggered"] is False


# ============================================================================
# Pathway Switching Tests
# ============================================================================


class TestPathwaySwitching:
    """Tests for pathway switching."""

    @pytest.mark.asyncio
    async def test_switch_pathway_pushes_to_stack(self, config, mock_agent):
        """Test that switch_pathway pushes current to stack."""
        JourneyClass = create_multi_pathway_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)

        await manager.start_session()

        await manager._switch_pathway("faq")

        session = await manager.get_session_state()
        assert session.current_pathway_id == "faq"
        assert "intake" in session.pathway_stack

    @pytest.mark.asyncio
    async def test_switch_to_nonexistent_pathway_raises(self, config):
        """Test switching to non-existent pathway raises."""
        JourneyClass = create_simple_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)

        await manager.start_session()

        with pytest.raises(PathwayNotFoundError) as exc_info:
            await manager._switch_pathway("nonexistent")

        assert "nonexistent" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_max_pathway_depth_raises(self, mock_agent):
        """Test that exceeding max pathway depth raises."""
        config = JourneyConfig(max_pathway_depth=2)
        JourneyClass = create_multi_pathway_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)

        await manager.start_session()

        # First switch OK (depth 2)
        await manager._switch_pathway("booking")

        # Second switch should exceed limit
        with pytest.raises(MaxPathwayDepthError) as exc_info:
            await manager._switch_pathway("faq")

        assert exc_info.value.max_depth == 2


# ============================================================================
# Context Accumulation Tests
# ============================================================================


class TestContextAccumulation:
    """Tests for context accumulation."""

    @pytest.mark.asyncio
    async def test_accumulate_from_pathway_result(self, config, mock_agent):
        """Test that pathway outputs are accumulated."""
        JourneyClass = create_multi_pathway_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)
        manager.register_agent("intake_agent", mock_agent)

        await manager.start_session()

        with patch.object(manager, "_execute_current_pathway") as mock_exec:
            mock_exec.return_value = PathwayResult(
                outputs={"response": "Welcome!"},
                accumulated={"customer_name": "Alice"},
                next_pathway=None,
                is_complete=True,
            )

            response = await manager.process_message("Hi, I'm Alice")

        assert response.accumulated_context["customer_name"] == "Alice"

    @pytest.mark.asyncio
    async def test_context_accumulator_property(self, config):
        """Test context_accumulator property."""
        JourneyClass = create_simple_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)

        accumulator = manager.context_accumulator
        assert accumulator is not None


# ============================================================================
# Return Behavior Tests
# ============================================================================


class TestReturnBehavior:
    """Tests for return behavior handling."""

    @pytest.mark.asyncio
    async def test_return_to_previous_pops_stack(self, config, mock_agent):
        """Test ReturnToPrevious pops from stack."""
        JourneyClass = create_multi_pathway_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)
        manager.register_agent("intake_agent", mock_agent)
        manager.register_agent("faq_agent", mock_agent)

        await manager.start_session()

        # Switch to FAQ (pushes intake to stack)
        await manager._switch_pathway("faq")

        # Simulate FAQ completion with return behavior
        faq_pathway = manager._get_current_pathway()
        assert isinstance(faq_pathway.return_behavior, ReturnToPrevious)

        result = PathwayResult(
            outputs={"answer": "Here is the answer"},
            accumulated={},
            next_pathway=None,
            is_complete=True,
        )

        await manager._handle_return_behavior(faq_pathway, result)

        session = await manager.get_session_state()
        assert session.current_pathway_id == "intake"

    @pytest.mark.asyncio
    async def test_return_to_specific(self, config):
        """Test ReturnToSpecific navigates to target."""

        class SpecificReturnJourney(Journey):
            __entry_pathway__ = "main"

            class MainPath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["agent"]

            class ProcessPath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["agent"]
                __return_behavior__ = ReturnToSpecific(target_pathway="confirmation")

            class ConfirmationPath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["agent"]

        journey = SpecificReturnJourney(session_id="test")
        manager = PathwayManager(journey, "test", config)

        await manager.start_session()
        await manager._switch_pathway("process")

        process_pathway = manager._get_current_pathway()
        result = PathwayResult(
            outputs={},
            accumulated={},
            next_pathway=None,
            is_complete=True,
        )

        await manager._handle_return_behavior(process_pathway, result)

        session = await manager.get_session_state()
        assert session.current_pathway_id == "confirmation"


# ============================================================================
# Component Access Tests
# ============================================================================


class TestComponentAccess:
    """Tests for component access properties."""

    def test_state_manager_property(self, config):
        """Test state_manager property."""
        JourneyClass = create_simple_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)

        state_mgr = manager.state_manager
        assert state_mgr is not None

    def test_get_intent_detector(self, config):
        """Test get_intent_detector method."""
        JourneyClass = create_simple_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)

        detector = manager.get_intent_detector()
        assert detector is not None

        # Should return same instance
        detector2 = manager.get_intent_detector()
        assert detector is detector2


# ============================================================================
# Pathway Execution Tests
# ============================================================================


class TestPathwayExecution:
    """Tests for pathway execution."""

    @pytest.mark.asyncio
    async def test_execute_current_pathway_not_found(self, config):
        """Test execute with non-existent pathway."""
        JourneyClass = create_simple_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)

        await manager.start_session()

        # Manually set to non-existent pathway
        manager._session.current_pathway_id = "nonexistent"

        result = await manager._execute_current_pathway("test")

        assert result.is_complete is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_get_current_pathway_caches(self, config):
        """Test that _get_current_pathway caches instances."""
        JourneyClass = create_simple_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)

        await manager.start_session()

        pathway1 = manager._get_current_pathway()
        pathway2 = manager._get_current_pathway()

        assert pathway1 is pathway2


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_session_not_started_error(self, config):
        """Test SessionNotStartedError is raised properly."""
        JourneyClass = create_simple_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)

        with pytest.raises(SessionNotStartedError) as exc_info:
            await manager.process_message("Hello")

        assert "Session not started" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_pathway_not_found_error(self, config):
        """Test PathwayNotFoundError is raised properly."""
        JourneyClass = create_simple_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)

        await manager.start_session()

        with pytest.raises(PathwayNotFoundError) as exc_info:
            await manager._switch_pathway("nonexistent")

        assert "nonexistent" in str(exc_info.value)
        assert "main" in str(exc_info.value.available)

    @pytest.mark.asyncio
    async def test_max_pathway_depth_error(self):
        """Test MaxPathwayDepthError is raised properly."""
        config = JourneyConfig(max_pathway_depth=1)
        JourneyClass = create_multi_pathway_journey()
        journey = JourneyClass(session_id="test")
        manager = PathwayManager(journey, "test", config)

        await manager.start_session()

        with pytest.raises(MaxPathwayDepthError) as exc_info:
            await manager._switch_pathway("booking")

        assert exc_info.value.depth == 2
        assert exc_info.value.max_depth == 1
