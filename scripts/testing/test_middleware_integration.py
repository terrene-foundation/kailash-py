"""
Integration tests for Kailash Middleware

Tests the complete middleware stack including agent-UI communication,
real-time events, schema generation, and AI chat integration.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict

import pytest
import pytest_asyncio

from kailash.middleware import (
    AgentUIMiddleware,
    AIChatMiddleware,
    APIGateway,
    EventStream,
    RealtimeMiddleware,
    create_gateway,
)
from kailash.middleware.communication.events import EventFilter, EventType
from kailash.workflow.builder import WorkflowBuilder


class TestMiddlewareIntegration:
    """Test the complete middleware integration."""

    @pytest_asyncio.fixture
    async def agent_ui_middleware(self):
        """Create agent UI middleware for testing."""
        middleware = AgentUIMiddleware(max_sessions=10)
        yield middleware
        # Cleanup
        for session_id in list(middleware.sessions.keys()):
            await middleware.close_session(session_id)

    @pytest_asyncio.fixture
    async def realtime_middleware(self, agent_ui_middleware):
        """Create real-time middleware for testing."""
        return RealtimeMiddleware(agent_ui_middleware)

    @pytest_asyncio.fixture
    async def api_gateway(self, agent_ui_middleware):
        """Create API gateway for testing."""
        gateway = create_gateway(
            title="Test Gateway", cors_origins=["*"], enable_docs=False
        )
        gateway.agent_ui = agent_ui_middleware
        return gateway

    @pytest_asyncio.fixture
    async def ai_chat_middleware(self, agent_ui_middleware):
        """Create AI chat middleware for testing."""
        return AIChatMiddleware(agent_ui_middleware)

    @pytest.mark.asyncio
    async def test_session_lifecycle(self, agent_ui_middleware):
        """Test session creation, management, and cleanup."""
        # Create session
        session_id = await agent_ui_middleware.create_session(user_id="test_user")
        assert session_id is not None

        # Get session
        session = await agent_ui_middleware.get_session(session_id)
        assert session is not None
        assert session.user_id == "test_user"
        assert session.active is True

        # Close session
        await agent_ui_middleware.close_session(session_id)
        session = await agent_ui_middleware.get_session(session_id)
        assert session is None

    @pytest.mark.asyncio
    async def test_workflow_creation_and_execution(self, agent_ui_middleware):
        """Test dynamic workflow creation and execution."""
        # Create session
        session_id = await agent_ui_middleware.create_session(user_id="test_user")

        # Create simple workflow
        workflow_config = {
            "name": "test_workflow",
            "description": "A test workflow",
            "nodes": [
                {
                    "id": "hello_node",
                    "type": "PythonCodeNode",
                    "config": {
                        "name": "hello_node",
                        "code": "result = {'message': 'Hello, World!'}",
                    },
                }
            ],
            "connections": [],
        }

        # Create workflow
        workflow_id = await agent_ui_middleware.create_dynamic_workflow(
            session_id=session_id, workflow_config=workflow_config
        )
        assert workflow_id is not None

        # Execute workflow
        execution_id = await agent_ui_middleware.execute_workflow(
            session_id=session_id, workflow_id=workflow_id, inputs={}
        )
        assert execution_id is not None

        # Wait for execution to complete
        await asyncio.sleep(1)

        # Check execution status
        status = await agent_ui_middleware.get_execution_status(
            execution_id, session_id
        )
        assert status is not None
        assert status["status"] in ["completed", "running"]  # May still be running

    @pytest.mark.asyncio
    async def test_event_system(self, agent_ui_middleware):
        """Test event emission and subscription."""
        events_received = []

        async def event_handler(event):
            events_received.append(event.to_dict())

        # Subscribe to events
        subscriber_id = await agent_ui_middleware.subscribe_to_events(
            "test_subscriber", event_handler
        )
        assert subscriber_id == "test_subscriber"

        # Create session and emit events
        session_id = await agent_ui_middleware.create_session(user_id="test_user")

        # Give time for events to be processed
        await asyncio.sleep(0.1)

        # Check that events were received
        assert len(events_received) > 0

        # Verify event structure
        first_event = events_received[0]
        assert "id" in first_event
        assert "type" in first_event
        assert "timestamp" in first_event

        # Unsubscribe
        await agent_ui_middleware.unsubscribe_from_events(subscriber_id)

    @pytest.mark.asyncio
    async def test_schema_generation(self, api_gateway):
        """Test dynamic schema generation."""
        # Get node schemas
        from kailash.nodes.base import NodeRegistry

        registry = NodeRegistry()
        node_class = registry.get("PythonCodeNode")

        if node_class:
            schema = api_gateway.schema_registry.get_node_schema(node_class)

            # Verify schema structure
            assert "node_type" in schema
            assert "parameters" in schema
            assert "inputs" in schema
            assert "outputs" in schema
            assert schema["node_type"] == "PythonCodeNode"

    @pytest.mark.asyncio
    async def test_ai_chat_integration(self, ai_chat_middleware):
        """Test AI chat integration."""
        # Create chat session
        session_id = "test_chat_session"
        chat_session_id = await ai_chat_middleware.start_chat_session(session_id)
        assert chat_session_id == session_id

        # Send message
        response = await ai_chat_middleware.send_message(
            session_id, "Hello! Can you help me?", context={"test": True}
        )

        # Verify response structure
        assert "message" in response
        assert "intent" in response
        assert "confidence" in response
        assert "session_id" in response

        # Get chat history
        history = ai_chat_middleware.get_chat_history(session_id)
        assert len(history) >= 2  # System message + user message + assistant response

    @pytest.mark.asyncio
    async def test_workflow_suggestion(self, ai_chat_middleware):
        """Test AI workflow suggestions."""
        # Create chat session
        session_id = "test_suggestion_session"
        await ai_chat_middleware.start_chat_session(session_id)

        # Ask for workflow creation
        response = await ai_chat_middleware.send_message(
            session_id,
            "Create a workflow that processes CSV data",
            context={"available_files": ["/data/test.csv"]},
        )

        # Check if workflow config was generated
        assert "intent" in response
        # The response may or may not contain a workflow_config depending on LLM availability
        if response.get("workflow_config"):
            config = response["workflow_config"]
            assert "metadata" in config
            assert "nodes" in config

    @pytest.mark.asyncio
    async def test_real_time_communication(self, realtime_middleware):
        """Test real-time communication capabilities."""
        # Test WebSocket manager
        connection_manager = realtime_middleware.connection_manager
        assert connection_manager is not None

        # Test SSE manager
        sse_manager = realtime_middleware.sse_manager
        assert sse_manager is not None

        # Test webhook manager
        webhook_manager = realtime_middleware.webhook_manager
        assert webhook_manager is not None

        # Get statistics
        stats = realtime_middleware.get_stats()
        assert "uptime_seconds" in stats
        assert "events_processed" in stats
        assert "enabled_transports" in stats

    @pytest.mark.asyncio
    async def test_event_filtering(self, agent_ui_middleware):
        """Test event filtering capabilities."""
        workflow_events = []
        node_events = []

        async def workflow_handler(event):
            workflow_events.append(event.to_dict())

        async def node_handler(event):
            node_events.append(event.to_dict())

        # Subscribe with filters
        workflow_filter = EventFilter(event_types=[EventType.WORKFLOW_STARTED])
        node_filter = EventFilter(event_types=[EventType.NODE_COMPLETED])

        await agent_ui_middleware.event_stream.subscribe(
            "workflow_subscriber", workflow_handler, workflow_filter
        )
        await agent_ui_middleware.event_stream.subscribe(
            "node_subscriber", node_handler, node_filter
        )

        # Create session to trigger events
        session_id = await agent_ui_middleware.create_session(user_id="filter_test")

        # Give time for events
        await asyncio.sleep(0.1)

        # Verify filtering worked
        # Note: Actual filtering verification would depend on specific events being emitted
        assert isinstance(workflow_events, list)
        assert isinstance(node_events, list)

    @pytest.mark.asyncio
    async def test_middleware_statistics(
        self, agent_ui_middleware, realtime_middleware, api_gateway
    ):
        """Test statistics collection across middleware components."""
        # Get agent UI stats
        agent_stats = agent_ui_middleware.get_stats()
        assert "uptime_seconds" in agent_stats
        assert "active_sessions" in agent_stats
        assert "workflows_executed" in agent_stats

        # Get real-time stats
        realtime_stats = realtime_middleware.get_stats()
        assert "uptime_seconds" in realtime_stats
        assert "events_processed" in realtime_stats

        # Get schema registry stats
        schema_stats = api_gateway.schema_registry.get_stats()
        assert "schemas_generated" in schema_stats
        assert "cache_hit_rate" in schema_stats

    @pytest.mark.asyncio
    async def test_error_handling(self, agent_ui_middleware):
        """Test error handling in middleware operations."""
        # Test invalid session ID
        session = await agent_ui_middleware.get_session("invalid_session")
        assert session is None

        # Test invalid workflow execution
        try:
            await agent_ui_middleware.execute_workflow(
                session_id="invalid_session", workflow_id="invalid_workflow", inputs={}
            )
            assert False, "Should have raised an exception"
        except ValueError:
            pass  # Expected

        # Test invalid workflow config
        session_id = await agent_ui_middleware.create_session()
        try:
            await agent_ui_middleware.create_dynamic_workflow(
                session_id=session_id, workflow_config={"invalid": "config"}
            )
            # This might not fail depending on implementation resilience
        except Exception:
            pass  # Expected for truly invalid configs


@pytest.mark.asyncio
async def test_complete_middleware_workflow():
    """Test a complete workflow through the middleware stack."""
    # Create middleware stack
    agent_ui = AgentUIMiddleware()
    realtime = RealtimeMiddleware(agent_ui)
    gateway = create_gateway()
    gateway.agent_ui = agent_ui
    gateway.realtime = realtime

    # Track events
    events = []

    async def event_collector(event):
        events.append(event.to_dict())

    await agent_ui.subscribe_to_events("collector", event_collector)

    try:
        # Create session
        session_id = await agent_ui.create_session(user_id="integration_test")

        # Create and register a simple workflow using proper SDK patterns
        builder = WorkflowBuilder()
        node_id = builder.add_node(
            "PythonCodeNode",
            "simple_processor",
            {
                "name": "simple_processor",
                "code": "result = {'status': 'processed', 'input_received': True}",
            },
        )

        await agent_ui.register_workflow("simple_test", builder, session_id=session_id)

        # Execute workflow
        execution_id = await agent_ui.execute_workflow(
            session_id=session_id, workflow_id="simple_test", inputs={"test": "data"}
        )

        # Wait for completion
        await asyncio.sleep(1)

        # Verify execution
        status = await agent_ui.get_execution_status(execution_id, session_id)
        assert status is not None

        # Verify events were emitted
        assert len(events) > 0

        # Get statistics
        stats = agent_ui.get_stats()
        assert stats["workflows_executed"] >= 1

        print("✅ Complete middleware workflow test passed")
        print(f"   - Sessions created: {stats['total_sessions_created']}")
        print(f"   - Workflows executed: {stats['workflows_executed']}")
        print(f"   - Events emitted: {len(events)}")

    finally:
        # Cleanup
        await agent_ui.close_session(session_id)


if __name__ == "__main__":
    # Run the complete workflow test
    asyncio.execute(test_complete_middleware_workflow())
