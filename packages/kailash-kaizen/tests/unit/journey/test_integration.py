"""
Unit tests for Journey Orchestration Integration Features (TODO-JO-005).

Tests integration components:
- REQ-INT-001: Signature Integration (guideline merging, output validation)
- REQ-INT-002: Pipeline Pattern Integration (__pipeline_config__)
- REQ-INT-004: DataFlow Models (JourneySessionModel, etc.)
- REQ-INT-005: Nexus Deployment (JourneyNexusAdapter)
- REQ-INT-007: Hooks System (JourneyHookEvent, registration, triggering)

Test Categories:
- Signature Integration Tests
- Pipeline Configuration Tests
- DataFlow Model Tests
- Nexus Adapter Tests
- Hooks System Tests
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============================================================================
# Signature Integration Tests (REQ-INT-001)
# ============================================================================


class TestSignatureIntegration:
    """Tests for REQ-INT-001: Signature Integration."""

    def test_pathway_guidelines_property(self):
        """Test that pathway.guidelines returns merged guidelines."""
        from kaizen.journey.core import Pathway, PathwayMeta
        from kaizen.signatures import InputField, OutputField, Signature

        # Create a signature with guidelines
        class TestSignature(Signature):
            __guidelines__ = ["Be helpful", "Be concise"]
            message: str = InputField(description="User message")
            response: str = OutputField(description="Response")

        # Create pathway with additional guidelines
        class TestPathway(Pathway):
            __signature__ = TestSignature
            __agents__ = ["test_agent"]
            __guidelines__ = ["Pathway specific", "Another guideline"]

        # Mock manager
        mock_manager = MagicMock()
        mock_manager.get_agent.return_value = MagicMock()

        pathway = TestPathway(mock_manager)

        # Get guidelines
        guidelines = pathway.guidelines

        # Should have signature guidelines + pathway guidelines
        assert "Pathway specific" in guidelines
        assert "Another guideline" in guidelines

    def test_pathway_validate_outputs(self):
        """Test output validation against signature contract."""
        from kaizen.journey.core import Pathway, PathwayMeta
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            message: str = InputField(description="Input")
            response: str = OutputField(description="Response")
            confidence: float = OutputField(description="Confidence score")

        class TestPathway(Pathway):
            __signature__ = TestSignature
            __agents__ = ["test_agent"]

        mock_manager = MagicMock()
        pathway = TestPathway(mock_manager)

        # Test with valid result
        result = {"response": "Hello", "confidence": 0.9}
        validation = pathway.validate_outputs(result)

        assert validation.get("response") is True
        assert validation.get("confidence") is True

    def test_pathway_validate_outputs_missing_fields(self):
        """Test output validation detects missing fields."""
        from kaizen.journey.core import Pathway
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            message: str = InputField(description="Input")
            response: str = OutputField(description="Response")
            confidence: float = OutputField(description="Confidence")

        class TestPathway(Pathway):
            __signature__ = TestSignature
            __agents__ = ["test_agent"]

        mock_manager = MagicMock()
        pathway = TestPathway(mock_manager)

        # Test with missing field
        result = {"response": "Hello"}  # Missing confidence
        validation = pathway.validate_outputs(result)

        assert validation.get("response") is True
        assert validation.get("confidence") is False

    def test_pathway_get_missing_outputs(self):
        """Test get_missing_outputs helper method."""
        from kaizen.journey.core import Pathway
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            message: str = InputField(description="Input")
            response: str = OutputField(description="Response")
            confidence: float = OutputField(description="Confidence")

        class TestPathway(Pathway):
            __signature__ = TestSignature
            __agents__ = ["test_agent"]

        mock_manager = MagicMock()
        pathway = TestPathway(mock_manager)

        # Test with missing fields
        result = {"response": "Hello"}
        missing = pathway.get_missing_outputs(result)

        assert "confidence" in missing
        assert "response" not in missing


# ============================================================================
# Pipeline Configuration Tests (REQ-INT-002)
# ============================================================================


class TestPipelineConfiguration:
    """Tests for REQ-INT-002: Pipeline Pattern Integration."""

    def test_pipeline_config_extraction(self):
        """Test that __pipeline_config__ is extracted from pathway class."""
        from kaizen.journey.core import Pathway
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            message: str = InputField(description="Input")
            response: str = OutputField(description="Output")

        class TestPathway(Pathway):
            __signature__ = TestSignature
            __agents__ = ["agent1", "agent2"]
            __pipeline__ = "router"
            __pipeline_config__ = {
                "routing_strategy": "semantic",
                "error_handling": "graceful",
            }

        assert TestPathway._pipeline == "router"
        assert TestPathway._pipeline_config == {
            "routing_strategy": "semantic",
            "error_handling": "graceful",
        }

    def test_pipeline_config_property(self):
        """Test pipeline_config property returns copy of config."""
        from kaizen.journey.core import Pathway
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            message: str = InputField(description="Input")
            response: str = OutputField(description="Output")

        class TestPathway(Pathway):
            __signature__ = TestSignature
            __agents__ = ["agent1"]
            __pipeline_config__ = {"key": "value"}

        mock_manager = MagicMock()
        pathway = TestPathway(mock_manager)

        config = pathway.pipeline_config
        assert config == {"key": "value"}

        # Should be a copy
        config["new_key"] = "new_value"
        assert "new_key" not in pathway.pipeline_config

    def test_pipeline_config_default_empty(self):
        """Test that pipeline_config defaults to empty dict."""
        from kaizen.journey.core import Pathway
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            message: str = InputField(description="Input")
            response: str = OutputField(description="Output")

        class TestPathway(Pathway):
            __signature__ = TestSignature
            __agents__ = ["agent1"]
            # No __pipeline_config__ specified

        mock_manager = MagicMock()
        pathway = TestPathway(mock_manager)

        assert pathway.pipeline_config == {}


# ============================================================================
# DataFlow Models Tests (REQ-INT-004)
# ============================================================================


class TestDataFlowModels:
    """Tests for REQ-INT-004: DataFlow Models."""

    def test_journey_session_model_structure(self):
        """Test JourneySessionModel has correct fields."""
        from kaizen.journey.models import JourneySessionModel

        session = JourneySessionModel(
            id="session-123",
            journey_class="myapp.journeys.BookingJourney",
            current_pathway_id="intake",
            pathway_stack="[]",
            accumulated_context="{}",
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )

        assert session.id == "session-123"
        assert session.journey_class == "myapp.journeys.BookingJourney"
        assert session.current_pathway_id == "intake"

    def test_journey_conversation_model_structure(self):
        """Test JourneyConversationModel has correct fields."""
        from kaizen.journey.models import JourneyConversationModel

        turn = JourneyConversationModel(
            id="turn-001",
            session_id="session-123",
            turn_number=1,
            role="user",
            content="Hello",
            pathway_id="intake",
            timestamp="2024-01-01T00:00:00",
        )

        assert turn.id == "turn-001"
        assert turn.session_id == "session-123"
        assert turn.turn_number == 1
        assert turn.role == "user"

    def test_intent_cache_model_structure(self):
        """Test IntentCacheModel has correct fields."""
        from kaizen.journey.models import IntentCacheModel

        cache = IntentCacheModel(
            id="cache-key",
            session_id="session-123",
            input_hash="abc123",
            intent="booking",
            confidence=0.95,
            model="gpt-4o-mini",
            created_at="2024-01-01T00:00:00",
            expires_at="2024-01-01T00:05:00",
        )

        assert cache.id == "cache-key"
        assert cache.intent == "booking"
        assert cache.confidence == 0.95


class TestEnhancedDataFlowStateBackend:
    """Tests for EnhancedDataFlowStateBackend."""

    @pytest.mark.asyncio
    async def test_save_session(self):
        """Test saving session data."""
        from kaizen.journey.models import EnhancedDataFlowStateBackend

        # Mock DataFlow
        mock_db = MagicMock()
        mock_db.express.read = AsyncMock(return_value=None)
        mock_db.express.create = AsyncMock()

        backend = EnhancedDataFlowStateBackend(mock_db)

        await backend.save_session(
            "session-123",
            {
                "journey_class": "MyJourney",
                "current_pathway_id": "intake",
                "pathway_stack": ["intake"],
                "accumulated_context": {"key": "value"},
            },
        )

        mock_db.express.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_session(self):
        """Test loading session data."""
        from kaizen.journey.models import EnhancedDataFlowStateBackend

        mock_db = MagicMock()
        mock_db.express.read = AsyncMock(
            return_value={
                "id": "session-123",
                "journey_class": "MyJourney",
                "current_pathway_id": "intake",
                "pathway_stack": "[]",
                "accumulated_context": "{}",
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00",
            }
        )

        backend = EnhancedDataFlowStateBackend(mock_db)

        data = await backend.load_session("session-123")

        assert data["session_id"] == "session-123"
        assert data["current_pathway_id"] == "intake"
        assert data["pathway_stack"] == []

    @pytest.mark.asyncio
    async def test_tenant_isolation(self):
        """Test multi-tenant isolation."""
        from kaizen.journey.models import EnhancedDataFlowStateBackend

        mock_db = MagicMock()
        mock_db.express.read = AsyncMock(
            return_value={
                "id": "session-123",
                "tenant_id": "tenant-other",  # Different tenant
                "journey_class": "",
                "current_pathway_id": "",
                "pathway_stack": "[]",
                "accumulated_context": "{}",
            }
        )

        # Backend configured for specific tenant
        backend = EnhancedDataFlowStateBackend(mock_db, tenant_id="tenant-001")

        data = await backend.load_session("session-123")

        # Should return None due to tenant mismatch
        assert data is None


# ============================================================================
# Nexus Adapter Tests (REQ-INT-005)
# ============================================================================


class TestJourneyNexusAdapter:
    """Tests for REQ-INT-005: Nexus Deployment Integration."""

    def test_adapter_initialization(self):
        """Test adapter initialization with journey class."""
        from kaizen.journey.core import Journey, Pathway
        from kaizen.journey.nexus import JourneyNexusAdapter
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            message: str = InputField(description="Input")
            response: str = OutputField(description="Output")

        class TestJourney(Journey):
            __entry_pathway__ = "test"

            class TestPath(Pathway):
                __signature__ = TestSignature
                __agents__ = ["test_agent"]

        adapter = JourneyNexusAdapter(TestJourney, workflow_name="test_journey")

        assert adapter.journey_class == TestJourney
        assert adapter.workflow_name == "test_journey"

    def test_adapter_snake_case_conversion(self):
        """Test automatic snake_case workflow name conversion."""
        from kaizen.journey.core import Journey, Pathway
        from kaizen.journey.nexus import JourneyNexusAdapter
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            message: str = InputField(description="Input")
            response: str = OutputField(description="Output")

        class BookingJourney(Journey):
            __entry_pathway__ = "test"

            class TestPath(Pathway):
                __signature__ = TestSignature
                __agents__ = ["test_agent"]

        adapter = JourneyNexusAdapter(BookingJourney)

        assert adapter.workflow_name == "booking_journey"

    def test_agent_registration(self):
        """Test registering agents with adapter."""
        from kaizen.journey.core import Journey, Pathway
        from kaizen.journey.nexus import JourneyNexusAdapter
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            message: str = InputField(description="Input")
            response: str = OutputField(description="Output")

        class TestJourney(Journey):
            __entry_pathway__ = "test"

            class TestPath(Pathway):
                __signature__ = TestSignature
                __agents__ = ["test_agent"]

        adapter = JourneyNexusAdapter(TestJourney)

        mock_agent = MagicMock()
        adapter.register_agent("test_agent", mock_agent)

        assert "test_agent" in adapter._agents
        assert adapter._agents["test_agent"] == mock_agent

    def test_to_workflow(self):
        """Test workflow definition generation."""
        from kaizen.journey.core import Journey, Pathway
        from kaizen.journey.nexus import JourneyNexusAdapter
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            message: str = InputField(description="Input")
            response: str = OutputField(description="Output")

        class TestJourney(Journey):
            __entry_pathway__ = "test"

            class TestPath(Pathway):
                __signature__ = TestSignature
                __agents__ = ["test_agent"]

        adapter = JourneyNexusAdapter(TestJourney)
        workflow_def = adapter.to_workflow()

        assert workflow_def["name"] == "test_journey"
        assert "handler" in workflow_def
        assert callable(workflow_def["handler"])
        assert "input_schema" in workflow_def
        assert "output_schema" in workflow_def

    def test_create_rest_endpoint(self):
        """Test REST endpoint definition creation."""
        from kaizen.journey.core import Journey, Pathway
        from kaizen.journey.nexus import JourneyNexusAdapter
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            message: str = InputField(description="Input")
            response: str = OutputField(description="Output")

        class TestJourney(Journey):
            __entry_pathway__ = "test"

            class TestPath(Pathway):
                __signature__ = TestSignature
                __agents__ = ["test_agent"]

        adapter = JourneyNexusAdapter(TestJourney)
        endpoint = adapter.create_rest_endpoint()

        assert endpoint["path"] == "/journeys/test_journey"
        assert endpoint["method"] == "POST"

    def test_create_mcp_tool(self):
        """Test MCP tool definition creation."""
        from kaizen.journey.core import Journey, Pathway
        from kaizen.journey.nexus import JourneyNexusAdapter
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            message: str = InputField(description="Input")
            response: str = OutputField(description="Output")

        class TestJourney(Journey):
            __entry_pathway__ = "test"

            class TestPath(Pathway):
                __signature__ = TestSignature
                __agents__ = ["test_agent"]

        adapter = JourneyNexusAdapter(TestJourney)
        tool = adapter.create_mcp_tool()

        assert tool["name"] == "test_journey"
        assert "inputSchema" in tool


class TestJourneySessionManager:
    """Tests for JourneySessionManager."""

    def test_create_session(self):
        """Test session creation."""
        from kaizen.journey.nexus import JourneySessionManager

        manager = JourneySessionManager()
        session_id = manager.create_session(
            user_id="user-123",
            channel="api",
            journey_class_name="TestJourney",
        )

        assert session_id is not None
        session = manager.get_session(session_id)
        assert session.user_id == "user-123"
        assert session.channel == "api"

    def test_get_user_sessions(self):
        """Test getting all sessions for a user."""
        from kaizen.journey.nexus import JourneySessionManager

        manager = JourneySessionManager()

        # Create multiple sessions for same user
        session1 = manager.create_session("user-123", "api", "Journey1")
        session2 = manager.create_session("user-123", "cli", "Journey2")

        sessions = manager.get_user_sessions("user-123")

        assert session1 in sessions
        assert session2 in sessions

    def test_cleanup_session(self):
        """Test session cleanup."""
        from kaizen.journey.nexus import JourneySessionManager

        manager = JourneySessionManager()
        session_id = manager.create_session("user-123", "api", "TestJourney")

        assert manager.get_session(session_id) is not None

        result = manager.cleanup_session(session_id)
        assert result is True
        assert manager.get_session(session_id) is None


# ============================================================================
# Hooks System Tests (REQ-INT-007)
# ============================================================================


class TestJourneyHookEvent:
    """Tests for JourneyHookEvent enum."""

    def test_hook_events_defined(self):
        """Test all required hook events are defined."""
        from kaizen.journey.manager import JourneyHookEvent

        # Session lifecycle
        assert JourneyHookEvent.PRE_SESSION_START
        assert JourneyHookEvent.POST_SESSION_START
        assert JourneyHookEvent.PRE_SESSION_RESTORE
        assert JourneyHookEvent.POST_SESSION_RESTORE

        # Pathway execution
        assert JourneyHookEvent.PRE_PATHWAY_EXECUTE
        assert JourneyHookEvent.POST_PATHWAY_EXECUTE

        # Pathway transitions
        assert JourneyHookEvent.PRE_PATHWAY_TRANSITION
        assert JourneyHookEvent.POST_PATHWAY_TRANSITION

        # Message processing
        assert JourneyHookEvent.PRE_MESSAGE_PROCESS
        assert JourneyHookEvent.POST_MESSAGE_PROCESS


class TestJourneyHookContext:
    """Tests for JourneyHookContext."""

    def test_context_creation(self):
        """Test hook context creation."""
        import time

        from kaizen.journey.manager import JourneyHookContext, JourneyHookEvent

        context = JourneyHookContext(
            event_type=JourneyHookEvent.PRE_PATHWAY_EXECUTE,
            session_id="session-123",
            pathway_id="intake",
            timestamp=time.time(),
            data={"message": "Hello"},
        )

        assert context.event_type == JourneyHookEvent.PRE_PATHWAY_EXECUTE
        assert context.session_id == "session-123"
        assert context.pathway_id == "intake"


class TestJourneyHookResult:
    """Tests for JourneyHookResult."""

    def test_success_result(self):
        """Test successful hook result."""
        from kaizen.journey.manager import JourneyHookResult

        result = JourneyHookResult(
            success=True,
            data={"logged": True},
        )

        assert result.success is True
        assert result.data == {"logged": True}

    def test_failure_result(self):
        """Test failed hook result."""
        from kaizen.journey.manager import JourneyHookResult

        result = JourneyHookResult(
            success=False,
            error="Hook timed out",
        )

        assert result.success is False
        assert result.error == "Hook timed out"


class TestPathwayManagerHooks:
    """Tests for PathwayManager hooks integration."""

    def test_register_hook(self):
        """Test hook registration."""
        from kaizen.journey.core import Journey, JourneyConfig, Pathway
        from kaizen.journey.manager import (
            JourneyHookContext,
            JourneyHookEvent,
            JourneyHookResult,
        )
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            message: str = InputField(description="Input")
            response: str = OutputField(description="Output")

        class TestJourney(Journey):
            __entry_pathway__ = "test"

            class TestPath(Pathway):
                __signature__ = TestSignature
                __agents__ = ["test_agent"]

        journey = TestJourney(session_id="test-session")

        async def my_hook(context: JourneyHookContext) -> JourneyHookResult:
            return JourneyHookResult(success=True)

        # Register hook
        journey.manager.register_hook(JourneyHookEvent.PRE_PATHWAY_EXECUTE, my_hook)

        assert my_hook in journey.manager._hooks[JourneyHookEvent.PRE_PATHWAY_EXECUTE]

    def test_unregister_hook(self):
        """Test hook unregistration."""
        from kaizen.journey.core import Journey, JourneyConfig, Pathway
        from kaizen.journey.manager import (
            JourneyHookContext,
            JourneyHookEvent,
            JourneyHookResult,
        )
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            message: str = InputField(description="Input")
            response: str = OutputField(description="Output")

        class TestJourney(Journey):
            __entry_pathway__ = "test"

            class TestPath(Pathway):
                __signature__ = TestSignature
                __agents__ = ["test_agent"]

        journey = TestJourney(session_id="test-session")

        async def my_hook(context: JourneyHookContext) -> JourneyHookResult:
            return JourneyHookResult(success=True)

        # Register and then unregister
        journey.manager.register_hook(JourneyHookEvent.PRE_PATHWAY_EXECUTE, my_hook)
        count = journey.manager.unregister_hook(
            JourneyHookEvent.PRE_PATHWAY_EXECUTE, my_hook
        )

        assert count == 1
        assert (
            my_hook not in journey.manager._hooks[JourneyHookEvent.PRE_PATHWAY_EXECUTE]
        )

    @pytest.mark.asyncio
    async def test_trigger_hooks(self):
        """Test hook triggering."""
        from kaizen.journey.core import Journey, JourneyConfig, Pathway
        from kaizen.journey.manager import (
            JourneyHookContext,
            JourneyHookEvent,
            JourneyHookResult,
        )
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            message: str = InputField(description="Input")
            response: str = OutputField(description="Output")

        class TestJourney(Journey):
            __entry_pathway__ = "test"

            class TestPath(Pathway):
                __signature__ = TestSignature
                __agents__ = ["test_agent"]

        journey = TestJourney(session_id="test-session")

        hook_called = []

        async def my_hook(context: JourneyHookContext) -> JourneyHookResult:
            hook_called.append(context.event_type)
            return JourneyHookResult(success=True)

        journey.manager.register_hook(JourneyHookEvent.PRE_PATHWAY_EXECUTE, my_hook)

        # Trigger hooks
        results = await journey.manager._trigger_hooks(
            JourneyHookEvent.PRE_PATHWAY_EXECUTE,
            pathway_id="test",
            data={"message": "test"},
        )

        assert len(results) == 1
        assert results[0].success is True
        assert JourneyHookEvent.PRE_PATHWAY_EXECUTE in hook_called

    @pytest.mark.asyncio
    async def test_hook_error_isolation(self):
        """Test that hook errors don't affect other hooks."""
        from kaizen.journey.core import Journey, Pathway
        from kaizen.journey.manager import (
            JourneyHookContext,
            JourneyHookEvent,
            JourneyHookResult,
        )
        from kaizen.signatures import InputField, OutputField, Signature

        class TestSignature(Signature):
            message: str = InputField(description="Input")
            response: str = OutputField(description="Output")

        class TestJourney(Journey):
            __entry_pathway__ = "test"

            class TestPath(Pathway):
                __signature__ = TestSignature
                __agents__ = ["test_agent"]

        journey = TestJourney(session_id="test-session")

        async def failing_hook(context: JourneyHookContext) -> JourneyHookResult:
            raise Exception("Hook failed!")

        async def success_hook(context: JourneyHookContext) -> JourneyHookResult:
            return JourneyHookResult(success=True, data={"executed": True})

        # Register both hooks
        journey.manager.register_hook(
            JourneyHookEvent.PRE_PATHWAY_EXECUTE, failing_hook
        )
        journey.manager.register_hook(
            JourneyHookEvent.PRE_PATHWAY_EXECUTE, success_hook
        )

        # Trigger hooks - should not raise
        results = await journey.manager._trigger_hooks(
            JourneyHookEvent.PRE_PATHWAY_EXECUTE,
            pathway_id="test",
        )

        assert len(results) == 2
        # First hook failed
        assert results[0].success is False
        assert "failed" in results[0].error.lower()
        # Second hook succeeded
        assert results[1].success is True


# ============================================================================
# Module Exports Tests
# ============================================================================


class TestModuleExports:
    """Tests for module exports."""

    def test_journey_module_exports(self):
        """Test that all integration components are exported."""
        from kaizen.journey import (  # Hook types; DataFlow models; Nexus integration
            EnhancedDataFlowStateBackend,
            IntentCacheModel,
            JourneyConversationModel,
            JourneyHookContext,
            JourneyHookEvent,
            JourneyHookResult,
            JourneyNexusAdapter,
            JourneySessionManager,
            JourneySessionModel,
            NexusSessionInfo,
            deploy_journey_to_nexus,
            register_journey_models,
        )

        # All imports should succeed without error
        assert JourneyHookEvent is not None
        assert JourneySessionModel is not None
        assert JourneyNexusAdapter is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
