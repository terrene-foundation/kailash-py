"""
Unit tests for Journey and Pathway Core Classes (TODO-JO-002).

Tests cover:
- REQ-JC-001: JourneyMeta metaclass
- REQ-JC-002: Journey base class
- REQ-JC-003: PathwayMeta metaclass
- REQ-JC-004: Pathway base class
- REQ-JC-005: Data classes
- REQ-JC-006: ReturnBehavior classes

These are Tier 1 (Unit) tests that use mock agents and don't make real LLM calls.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen.journey import (
    Journey,
    JourneyConfig,
    JourneyMeta,
    JourneyResponse,
    JourneySession,
    Pathway,
    PathwayContext,
    PathwayManager,
    PathwayMeta,
    PathwayResult,
    ReturnBehavior,
    ReturnToPrevious,
    ReturnToSpecific,
    SessionNotStartedError,
)
from kaizen.signatures import InputField, OutputField, Signature

# ============================================================================
# Test Fixtures
# ============================================================================


class SimpleSignature(Signature):
    """Simple test signature."""

    question: str = InputField(desc="User question")
    answer: str = OutputField(desc="Agent answer")


class IntakeSignature(Signature):
    """Intake pathway signature."""

    message: str = InputField(desc="User message")
    response: str = OutputField(desc="Agent response")
    customer_name: str = OutputField(desc="Customer name")


class BookingSignature(Signature):
    """Booking pathway signature."""

    request: str = InputField(desc="Booking request")
    confirmation: str = OutputField(desc="Booking confirmation")
    booking_id: str = OutputField(desc="Booking ID")


class FAQSignature(Signature):
    """FAQ pathway signature."""

    question: str = InputField(desc="FAQ question")
    answer: str = OutputField(desc="FAQ answer")


@pytest.fixture
def mock_agent():
    """Create a mock agent for testing."""
    agent = MagicMock()
    agent.run = MagicMock(return_value={"answer": "Test answer"})
    return agent


@pytest.fixture
def mock_async_agent():
    """Create a mock async agent for testing."""
    agent = MagicMock()
    agent.run = AsyncMock(return_value={"answer": "Test async answer"})
    return agent


def create_test_manager():
    """Create a minimal PathwayManager for testing."""

    class MinimalJourney(Journey):
        __entry_pathway__ = "test"

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["test_agent"]

    journey = MinimalJourney(session_id="test-session")
    return journey.manager


# ============================================================================
# REQ-JC-001: JourneyMeta Metaclass Tests
# ============================================================================


class TestJourneyMeta:
    """Tests for JourneyMeta metaclass (REQ-JC-001)."""

    def test_journey_extracts_pathways(self):
        """Test that JourneyMeta extracts nested Pathway classes."""

        class TestJourney(Journey):
            __entry_pathway__ = "first"

            class FirstPath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["agent1"]

            class SecondPath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["agent2"]

        assert "first" in TestJourney._pathways
        assert "second" in TestJourney._pathways
        assert TestJourney._entry_pathway == "first"

    def test_invalid_entry_pathway_raises(self):
        """Test that invalid entry pathway raises ValueError."""
        with pytest.raises(ValueError, match="not found"):

            class BadJourney(Journey):
                __entry_pathway__ = "nonexistent"

                class OnlyPath(Pathway):
                    __signature__ = SimpleSignature
                    __agents__ = ["agent1"]

    def test_pathway_id_conversion_with_path_suffix(self):
        """Test snake_case conversion for PathClassName."""
        assert JourneyMeta._to_pathway_id("IntakePath") == "intake"
        assert JourneyMeta._to_pathway_id("BookingPath") == "booking"

    def test_pathway_id_conversion_with_pathway_suffix(self):
        """Test snake_case conversion for PathwayClassName."""
        assert JourneyMeta._to_pathway_id("IntakePathway") == "intake"
        assert JourneyMeta._to_pathway_id("BookingPathway") == "booking"

    def test_pathway_id_conversion_multi_word(self):
        """Test snake_case conversion for multi-word names."""
        assert JourneyMeta._to_pathway_id("UserRegistrationPath") == "user_registration"
        assert JourneyMeta._to_pathway_id("PaymentConfirmationPath") == (
            "payment_confirmation"
        )

    def test_pathway_id_conversion_acronyms(self):
        """Test snake_case conversion with acronyms."""
        assert JourneyMeta._to_pathway_id("FAQPath") == "faq"
        assert JourneyMeta._to_pathway_id("APIPath") == "api"

    def test_default_entry_pathway_when_not_specified(self):
        """Test that first pathway becomes default entry when not specified."""

        class TestJourney(Journey):
            class OnlyPath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["agent1"]

        assert TestJourney._entry_pathway == "only"

    def test_transitions_extracted(self):
        """Test that __transitions__ are extracted."""

        class TestJourney(Journey):
            __entry_pathway__ = "main"
            __transitions__ = [{"trigger": "help", "to_pathway": "faq"}]

            class MainPath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["agent1"]

        assert len(TestJourney._transitions) == 1
        assert TestJourney._transitions[0]["to_pathway"] == "faq"


# ============================================================================
# REQ-JC-002: Journey Base Class Tests
# ============================================================================


class TestJourneyClass:
    """Tests for Journey base class (REQ-JC-002)."""

    def test_journey_init_with_default_config(self):
        """Test Journey initialization with default config."""

        class TestJourney(Journey):
            __entry_pathway__ = "main"

            class MainPath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["agent1"]

        journey = TestJourney(session_id="test-123")
        assert journey.session_id == "test-123"
        assert isinstance(journey.config, JourneyConfig)
        assert journey.manager is not None

    def test_journey_init_with_custom_config(self):
        """Test Journey initialization with custom config."""

        class TestJourney(Journey):
            __entry_pathway__ = "main"

            class MainPath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["agent1"]

        config = JourneyConfig(
            intent_detection_model="gpt-4",
            max_pathway_depth=20,
        )
        journey = TestJourney(session_id="test-123", config=config)
        assert journey.config.intent_detection_model == "gpt-4"
        assert journey.config.max_pathway_depth == 20

    def test_journey_pathways_property_returns_copy(self):
        """Test that pathways property returns a copy."""

        class TestJourney(Journey):
            __entry_pathway__ = "main"

            class MainPath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["agent1"]

        journey = TestJourney(session_id="test")
        pathways1 = journey.pathways
        pathways2 = journey.pathways
        assert pathways1 is not pathways2
        assert pathways1 == pathways2

    def test_journey_entry_pathway_property(self):
        """Test entry_pathway property."""

        class TestJourney(Journey):
            __entry_pathway__ = "intake"

            class IntakePath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["agent1"]

        journey = TestJourney(session_id="test")
        assert journey.entry_pathway == "intake"

    def test_journey_transitions_property_returns_copy(self):
        """Test that transitions property returns a copy."""

        class TestJourney(Journey):
            __entry_pathway__ = "main"
            __transitions__ = [{"trigger": "help"}]

            class MainPath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["agent1"]

        journey = TestJourney(session_id="test")
        transitions1 = journey.transitions
        transitions2 = journey.transitions
        assert transitions1 is not transitions2
        assert transitions1 == transitions2

    def test_journey_register_agent(self, mock_agent):
        """Test agent registration."""

        class TestJourney(Journey):
            __entry_pathway__ = "main"

            class MainPath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["my_agent"]

        journey = TestJourney(session_id="test")
        journey.register_agent("my_agent", mock_agent)
        assert journey.manager.get_agent("my_agent") is mock_agent

    @pytest.mark.asyncio
    async def test_journey_start_returns_session(self):
        """Test that start() returns JourneySession."""

        class TestJourney(Journey):
            __entry_pathway__ = "main"

            class MainPath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["agent1"]

        journey = TestJourney(session_id="test-session")
        session = await journey.start()

        assert isinstance(session, JourneySession)
        assert session.session_id == "test-session"
        assert session.current_pathway_id == "main"

    @pytest.mark.asyncio
    async def test_journey_start_with_initial_context(self):
        """Test start() with initial context."""

        class TestJourney(Journey):
            __entry_pathway__ = "main"

            class MainPath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["agent1"]

        journey = TestJourney(session_id="test")
        initial_ctx = {"user_id": "user-123", "locale": "en-US"}
        session = await journey.start(initial_context=initial_ctx)

        assert session.accumulated_context["user_id"] == "user-123"
        assert session.accumulated_context["locale"] == "en-US"


# ============================================================================
# REQ-JC-003: PathwayMeta Metaclass Tests
# ============================================================================


class TestPathwayMeta:
    """Tests for PathwayMeta metaclass (REQ-JC-003)."""

    def test_pathway_extracts_signature(self):
        """Test that PathwayMeta extracts __signature__."""

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["agent1"]

        assert TestPath._signature is SimpleSignature

    def test_pathway_extracts_agents(self):
        """Test that PathwayMeta extracts __agents__."""

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["agent1", "agent2"]

        assert TestPath._agents == ["agent1", "agent2"]

    def test_pathway_extracts_pipeline_type(self):
        """Test that PathwayMeta extracts __pipeline__."""

        class ParallelPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["a1", "a2"]
            __pipeline__ = "parallel"

        assert ParallelPath._pipeline == "parallel"

    def test_pathway_default_pipeline_is_sequential(self):
        """Test that default pipeline type is sequential."""

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["agent1"]

        assert TestPath._pipeline == "sequential"

    def test_pathway_extracts_accumulate(self):
        """Test that PathwayMeta extracts __accumulate__."""

        class AccumulatingPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["agent1"]
            __accumulate__ = ["field1", "field2"]

        assert AccumulatingPath._accumulate == ["field1", "field2"]

    def test_pathway_extracts_next(self):
        """Test that PathwayMeta extracts __next__."""

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["agent1"]
            __next__ = "booking"

        assert TestPath._next == "booking"

    def test_pathway_extracts_guidelines(self):
        """Test that PathwayMeta extracts __guidelines__."""

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["agent1"]
            __guidelines__ = ["Be helpful", "Be concise"]

        assert TestPath._guidelines == ["Be helpful", "Be concise"]

    def test_pathway_extracts_return_behavior(self):
        """Test that PathwayMeta extracts __return_behavior__."""

        class DetourPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["agent1"]
            __return_behavior__ = ReturnToPrevious()

        assert isinstance(DetourPath._return_behavior, ReturnToPrevious)

    def test_pathway_invalid_signature_raises(self):
        """Test that invalid __signature__ raises TypeError."""
        with pytest.raises(TypeError, match="must be a Signature class"):

            class BadPath(Pathway):
                __signature__ = "not_a_class"
                __agents__ = ["agent1"]


# ============================================================================
# REQ-JC-004: Pathway Base Class Tests
# ============================================================================


class TestPathwayClass:
    """Tests for Pathway base class (REQ-JC-004)."""

    def test_pathway_init(self):
        """Test Pathway initialization."""

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["agent1"]

        manager = create_test_manager()
        pathway = TestPath(manager)

        assert pathway.manager is manager
        assert pathway._signature_instance is None

    def test_pathway_signature_property_lazy_instantiation(self):
        """Test that signature property lazily instantiates."""

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["agent1"]

        manager = create_test_manager()
        pathway = TestPath(manager)

        # Before access
        assert pathway._signature_instance is None

        # After access
        sig = pathway.signature
        assert sig is not None
        assert pathway._signature_instance is sig

    def test_pathway_agent_ids_returns_copy(self):
        """Test that agent_ids returns a copy."""

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["agent1", "agent2"]

        manager = create_test_manager()
        pathway = TestPath(manager)

        ids1 = pathway.agent_ids
        ids2 = pathway.agent_ids
        assert ids1 is not ids2
        assert ids1 == ["agent1", "agent2"]

    def test_pathway_accumulate_fields_returns_copy(self):
        """Test that accumulate_fields returns a copy."""

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["agent1"]
            __accumulate__ = ["field1", "field2"]

        manager = create_test_manager()
        pathway = TestPath(manager)

        fields1 = pathway.accumulate_fields
        fields2 = pathway.accumulate_fields
        assert fields1 is not fields2
        assert fields1 == ["field1", "field2"]

    def test_pathway_pipeline_type_property(self):
        """Test pipeline_type property."""

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["agent1"]
            __pipeline__ = "router"

        manager = create_test_manager()
        pathway = TestPath(manager)
        assert pathway.pipeline_type == "router"

    def test_pathway_next_pathway_property(self):
        """Test next_pathway property."""

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["agent1"]
            __next__ = "booking"

        manager = create_test_manager()
        pathway = TestPath(manager)
        assert pathway.next_pathway == "booking"

    def test_pathway_return_behavior_property(self):
        """Test return_behavior property."""

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["agent1"]
            __return_behavior__ = ReturnToPrevious(max_depth=3)

        manager = create_test_manager()
        pathway = TestPath(manager)
        assert isinstance(pathway.return_behavior, ReturnToPrevious)
        assert pathway.return_behavior.max_depth == 3

    def test_pathway_resolve_agents_unregistered_raises(self):
        """Test that resolving unregistered agent raises ValueError."""

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["unknown_agent"]

        manager = create_test_manager()
        pathway = TestPath(manager)

        with pytest.raises(ValueError, match="Agent 'unknown_agent' not registered"):
            pathway._resolve_agents()

    def test_pathway_resolve_agents_success(self, mock_agent):
        """Test successful agent resolution."""

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["my_agent"]

        manager = create_test_manager()
        manager.register_agent("my_agent", mock_agent)
        pathway = TestPath(manager)

        agents = pathway._resolve_agents()
        assert len(agents) == 1
        assert agents[0] is mock_agent

    def test_pathway_build_pipeline_no_agents_raises(self, mock_agent):
        """Test that building pipeline with no agents raises ValueError."""

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = []

        manager = create_test_manager()
        pathway = TestPath(manager)

        with pytest.raises(ValueError, match="requires at least one agent"):
            pathway._build_pipeline([])

    def test_pathway_build_pipeline_unknown_type_raises(self, mock_agent):
        """Test that unknown pipeline type raises ValueError."""

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = [
                "agent1",
                "agent2",
            ]  # Need multiple agents to use pipeline type
            __pipeline__ = "unknown_type"

        manager = create_test_manager()
        manager.register_agent("agent1", mock_agent)
        manager.register_agent("agent2", mock_agent)
        pathway = TestPath(manager)

        with pytest.raises(ValueError, match="Unknown pipeline type"):
            pathway._build_pipeline([mock_agent, mock_agent])

    def test_pathway_extract_accumulated_fields(self):
        """Test field accumulation extraction."""

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["agent1"]
            __accumulate__ = ["name", "email"]

        manager = create_test_manager()
        pathway = TestPath(manager)

        result = {
            "name": "Alice",
            "email": "alice@example.com",
            "extra": "ignored",
        }
        accumulated = pathway._extract_accumulated_fields(result)

        assert accumulated == {"name": "Alice", "email": "alice@example.com"}
        assert "extra" not in accumulated

    def test_pathway_extract_accumulated_fields_skips_none(self):
        """Test that None values are not accumulated."""

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["agent1"]
            __accumulate__ = ["name", "email"]

        manager = create_test_manager()
        pathway = TestPath(manager)

        result = {"name": "Alice", "email": None}
        accumulated = pathway._extract_accumulated_fields(result)

        assert accumulated == {"name": "Alice"}
        assert "email" not in accumulated

    @pytest.mark.asyncio
    async def test_pathway_execute_success(self, mock_agent):
        """Test successful pathway execution."""

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["test_agent"]
            __accumulate__ = ["answer"]
            __next__ = "next_pathway"

        manager = create_test_manager()
        manager.register_agent("test_agent", mock_agent)
        pathway = TestPath(manager)

        context = PathwayContext(
            session_id="test",
            pathway_id="test",
            user_message="Hello",
            accumulated_context={},
            conversation_history=[],
        )

        # Mock the pipeline execution - use spec to limit attributes
        with patch.object(pathway, "_build_pipeline") as mock_build:
            # Create a pipeline mock that only has 'run' method (no 'execute')
            # This ensures the sync path is taken
            mock_pipeline = MagicMock(spec=["run"])
            mock_pipeline.run = MagicMock(return_value={"answer": "Test answer"})
            mock_build.return_value = mock_pipeline

            result = await pathway.execute(context)

        assert result.is_complete is True
        assert result.next_pathway == "next_pathway"
        assert result.accumulated == {"answer": "Test answer"}
        assert result.error is None

    @pytest.mark.asyncio
    async def test_pathway_execute_handles_error(self, mock_agent):
        """Test that pathway execution handles errors gracefully."""

        class TestPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["test_agent"]

        manager = create_test_manager()
        manager.register_agent("test_agent", mock_agent)
        pathway = TestPath(manager)

        context = PathwayContext(
            session_id="test",
            pathway_id="test",
            user_message="Hello",
            accumulated_context={},
            conversation_history=[],
        )

        # Mock the pipeline to raise an error
        with patch.object(pathway, "_build_pipeline") as mock_build:
            mock_build.side_effect = RuntimeError("Pipeline failed")

            result = await pathway.execute(context)

        assert result.is_complete is False
        assert result.error == "Pipeline failed"
        assert result.outputs == {}


# ============================================================================
# REQ-JC-005: Data Classes Tests
# ============================================================================


class TestDataClasses:
    """Tests for data classes (REQ-JC-005)."""

    def test_journey_config_defaults(self):
        """Test JourneyConfig default values."""
        config = JourneyConfig()

        assert config.intent_detection_model == "gpt-4o-mini"
        assert config.intent_confidence_threshold == 0.7
        assert config.intent_cache_ttl_seconds == 300
        assert config.max_pathway_depth == 10
        assert config.pathway_timeout_seconds == 60.0
        assert config.max_context_size_bytes == 1024 * 1024
        assert config.context_persistence == "memory"
        assert config.error_recovery == "graceful"
        assert config.max_retries == 3

    def test_journey_config_custom_values(self):
        """Test JourneyConfig with custom values."""
        config = JourneyConfig(
            intent_detection_model="gpt-4",
            max_pathway_depth=20,
            error_recovery="fail_fast",
        )

        assert config.intent_detection_model == "gpt-4"
        assert config.max_pathway_depth == 20
        assert config.error_recovery == "fail_fast"

    def test_pathway_context_to_input_dict(self):
        """Test PathwayContext.to_input_dict() method."""
        context = PathwayContext(
            session_id="test-session",
            pathway_id="intake",
            user_message="Hello world",
            accumulated_context={"name": "Alice"},
            conversation_history=[{"role": "user", "content": "Hi"}],
        )

        input_dict = context.to_input_dict()

        assert input_dict["message"] == "Hello world"
        assert input_dict["context"] == {"name": "Alice"}
        assert input_dict["history"] == [{"role": "user", "content": "Hi"}]

    def test_pathway_result_success(self):
        """Test PathwayResult for successful execution."""
        result = PathwayResult(
            outputs={"answer": "Test"},
            accumulated={"name": "Alice"},
            next_pathway="booking",
            is_complete=True,
        )

        assert result.is_complete is True
        assert result.error is None
        assert result.outputs["answer"] == "Test"
        assert result.accumulated["name"] == "Alice"
        assert result.next_pathway == "booking"

    def test_pathway_result_failure(self):
        """Test PathwayResult for failed execution."""
        result = PathwayResult(
            outputs={},
            accumulated={},
            next_pathway=None,
            is_complete=False,
            error="Something went wrong",
        )

        assert result.is_complete is False
        assert result.error == "Something went wrong"

    def test_journey_session(self):
        """Test JourneySession dataclass."""
        session = JourneySession(
            session_id="session-123",
            journey_class=None,  # Can be None for testing
            current_pathway_id="intake",
            accumulated_context={"user_id": "user-456"},
            pathway_stack=["intake"],
        )

        assert session.session_id == "session-123"
        assert session.current_pathway_id == "intake"
        assert session.accumulated_context["user_id"] == "user-456"
        assert session.pathway_stack == ["intake"]

    def test_journey_response(self):
        """Test JourneyResponse dataclass."""
        result = PathwayResult(
            outputs={"answer": "Test"},
            accumulated={},
            next_pathway="booking",
            is_complete=True,
        )
        response = JourneyResponse(
            pathway_id="intake",
            result=result,
            next_pathway_id="booking",
            accumulated_context={"name": "Alice"},
        )

        assert response.pathway_id == "intake"
        assert response.result.is_complete is True
        assert response.next_pathway_id == "booking"
        assert response.accumulated_context["name"] == "Alice"


# ============================================================================
# REQ-JC-006: ReturnBehavior Tests
# ============================================================================


class TestReturnBehaviors:
    """Tests for ReturnBehavior classes (REQ-JC-006)."""

    def test_return_behavior_base_class(self):
        """Test ReturnBehavior base class."""
        behavior = ReturnBehavior()
        assert behavior is not None

    def test_return_to_previous_defaults(self):
        """Test ReturnToPrevious default values."""
        behavior = ReturnToPrevious()

        assert behavior.preserve_context is True
        assert behavior.max_depth == 5

    def test_return_to_previous_custom_values(self):
        """Test ReturnToPrevious with custom values."""
        behavior = ReturnToPrevious(preserve_context=False, max_depth=3)

        assert behavior.preserve_context is False
        assert behavior.max_depth == 3

    def test_return_to_specific_defaults(self):
        """Test ReturnToSpecific default values."""
        behavior = ReturnToSpecific()

        assert behavior.target_pathway == ""
        assert behavior.preserve_context is True

    def test_return_to_specific_custom_values(self):
        """Test ReturnToSpecific with custom values."""
        behavior = ReturnToSpecific(
            target_pathway="confirmation", preserve_context=False
        )

        assert behavior.target_pathway == "confirmation"
        assert behavior.preserve_context is False


# ============================================================================
# PathwayManager Tests
# ============================================================================


class TestPathwayManager:
    """Tests for PathwayManager class."""

    def test_manager_register_and_get_agent(self, mock_agent):
        """Test agent registration and retrieval."""
        manager = create_test_manager()
        manager.register_agent("my_agent", mock_agent)

        assert manager.get_agent("my_agent") is mock_agent
        assert manager.get_agent("unknown") is None

    @pytest.mark.asyncio
    async def test_manager_get_current_pathway_after_start(self):
        """Test that _get_current_pathway returns pathway after session start."""

        class TestJourney(Journey):
            __entry_pathway__ = "main"

            class MainPath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["agent1"]

        journey = TestJourney(session_id="test")
        manager = journey.manager

        # Before session start, returns None
        pathway_before = manager._get_current_pathway()
        assert pathway_before is None

        # After session start, returns current pathway
        await manager.start_session()
        pathway = manager._get_current_pathway()
        assert pathway is not None
        assert isinstance(pathway, Pathway)

    @pytest.mark.asyncio
    async def test_manager_get_current_pathway_returns_same_instance(self):
        """Test that _get_current_pathway returns same instance on repeated calls."""

        class TestJourney(Journey):
            __entry_pathway__ = "main"

            class MainPath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["agent1"]

        journey = TestJourney(session_id="test")
        manager = journey.manager

        await manager.start_session()
        pathway1 = manager._get_current_pathway()
        pathway2 = manager._get_current_pathway()
        assert pathway1 is pathway2

    @pytest.mark.asyncio
    async def test_manager_get_current_pathway_before_start_returns_none(self):
        """Test that _get_current_pathway returns None before session start."""
        manager = create_test_manager()
        assert manager._get_current_pathway() is None

    @pytest.mark.asyncio
    async def test_manager_start_session(self):
        """Test starting a session."""

        class TestJourney(Journey):
            __entry_pathway__ = "intake"

            class IntakePath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["agent1"]

        journey = TestJourney(session_id="test-123")
        session = await journey.manager.start_session()

        assert session.session_id == "test-123"
        assert session.current_pathway_id == "intake"
        assert session.pathway_stack == ["intake"]

    @pytest.mark.asyncio
    async def test_manager_start_session_with_context(self):
        """Test starting a session with initial context."""

        class TestJourney(Journey):
            __entry_pathway__ = "main"

            class MainPath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["agent1"]

        journey = TestJourney(session_id="test")
        initial = {"user_id": "user-123"}
        session = await journey.manager.start_session(initial_context=initial)

        assert session.accumulated_context["user_id"] == "user-123"


# ============================================================================
# Integration Tests (Pathway execution with mock agents)
# ============================================================================


class TestPathwayExecution:
    """Integration tests for pathway execution with mock agents."""

    @pytest.mark.asyncio
    async def test_pathway_executes_single_agent(self, mock_agent):
        """Test pathway execution with single agent."""

        class TestJourney(Journey):
            __entry_pathway__ = "test"

            class TestPath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["test_agent"]

        journey = TestJourney(session_id="test")
        journey.register_agent("test_agent", mock_agent)

        # Start session
        await journey.start()

        # Create context manually for testing
        context = PathwayContext(
            session_id="test",
            pathway_id="test",
            user_message="Hello",
            accumulated_context={},
            conversation_history=[],
        )

        # Get current pathway via the enhanced manager's internal method
        pathway = journey.manager._get_current_pathway()

        # Mock the pipeline - use spec to ensure only 'run' method exists (sync path)
        with patch.object(pathway, "_build_pipeline") as mock_build:
            mock_pipeline = MagicMock(spec=["run"])
            mock_pipeline.run = MagicMock(return_value={"answer": "Test response"})
            mock_build.return_value = mock_pipeline

            result = await pathway.execute(context)

        assert result.is_complete is True

    @pytest.mark.asyncio
    async def test_complete_journey_flow(self, mock_agent):
        """Test complete journey flow with multiple pathways."""

        class BookingJourney(Journey):
            __entry_pathway__ = "intake"

            class IntakePath(Pathway):
                __signature__ = IntakeSignature
                __agents__ = ["intake_agent"]
                __accumulate__ = ["customer_name"]
                __next__ = "booking"

            class BookingPath(Pathway):
                __signature__ = BookingSignature
                __agents__ = ["booking_agent"]

        journey = BookingJourney(session_id="test")

        # Register agents
        journey.register_agent("intake_agent", mock_agent)
        journey.register_agent("booking_agent", mock_agent)

        # Start session
        session = await journey.start()
        assert session.current_pathway_id == "intake"
        assert "intake" in journey.pathways
        assert "booking" in journey.pathways


# ============================================================================
# Guidelines Merge Tests
# ============================================================================


class TestGuidelinesMerge:
    """Tests for guidelines merging between signature and pathway."""

    def test_pathway_merges_guidelines(self):
        """Test that pathway guidelines are merged with signature guidelines."""

        class TestSig(Signature):
            """Test signature with guidelines."""

            __guidelines__ = ["Sig guideline"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        class TestPath(Pathway):
            __signature__ = TestSig
            __guidelines__ = ["Pathway guideline"]
            __agents__ = ["agent1"]

        manager = create_test_manager()
        pathway = TestPath(manager)
        sig = pathway.signature

        # Check both guidelines are present
        assert "Sig guideline" in sig.guidelines
        assert "Pathway guideline" in sig.guidelines

    def test_pathway_without_guidelines(self):
        """Test pathway without additional guidelines."""

        class TestSig(Signature):
            """Test signature with guidelines."""

            __guidelines__ = ["Only sig guideline"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        class TestPath(Pathway):
            __signature__ = TestSig
            __agents__ = ["agent1"]
            # No __guidelines__ defined

        manager = create_test_manager()
        pathway = TestPath(manager)
        sig = pathway.signature

        # Original guidelines preserved
        assert "Only sig guideline" in sig.guidelines


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_journey_with_no_pathways(self):
        """Test that Journey with no pathways works (edge case)."""

        class EmptyJourney(Journey):
            pass

        journey = EmptyJourney(session_id="test")
        assert journey.pathways == {}
        assert journey.entry_pathway is None

    def test_pathway_with_no_signature(self):
        """Test pathway with no signature defined."""

        class NoSigPath(Pathway):
            __agents__ = ["agent1"]
            # No __signature__ defined

        manager = create_test_manager()
        pathway = NoSigPath(manager)

        assert pathway.signature is None
        assert pathway._signature is None

    def test_pathway_with_multiple_agents(self, mock_agent):
        """Test pathway with multiple agents."""

        class MultiAgentPath(Pathway):
            __signature__ = SimpleSignature
            __agents__ = ["agent1", "agent2", "agent3"]
            __pipeline__ = "sequential"

        manager = create_test_manager()
        for i in range(1, 4):
            manager.register_agent(f"agent{i}", mock_agent)

        pathway = MultiAgentPath(manager)
        agents = pathway._resolve_agents()

        assert len(agents) == 3

    @pytest.mark.asyncio
    async def test_process_message_without_start_raises(self):
        """Test that process_message before start raises error."""

        class TestJourney(Journey):
            __entry_pathway__ = "main"

            class MainPath(Pathway):
                __signature__ = SimpleSignature
                __agents__ = ["agent1"]

        journey = TestJourney(session_id="test")

        with pytest.raises(SessionNotStartedError):
            await journey.process_message("Hello")
