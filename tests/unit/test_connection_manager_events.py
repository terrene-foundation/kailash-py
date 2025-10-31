"""Comprehensive tests for ConnectionManager event methods added in TODO-111."""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from kailash.middleware.communication.events import (
    BaseEvent,
    EventFilter,
    EventPriority,
    EventType,
)
from kailash.middleware.communication.realtime import ConnectionManager


class MockEvent:
    """Mock event for testing."""

    def __init__(
        self,
        event_type=EventType.SYSTEM_STATUS,
        data=None,
        session_id=None,
        user_id=None,
    ):
        self.id = str(uuid.uuid4())
        self.type = event_type  # BaseEvent uses 'type' not 'event_type'
        self.event_type = event_type  # Keep for compatibility
        self.timestamp = datetime.now(timezone.utc)
        self.priority = EventPriority.NORMAL
        self.source = None
        self.target = None
        self.session_id = session_id
        self.user_id = user_id
        self.metadata = data or {}
        self.data = data or {}  # Keep for compatibility


class TestEventFiltering:
    """Test event filtering methods."""

    def test_filter_events_no_filter(self):
        """Test filter_events with no filter returns all events."""
        manager = ConnectionManager()

        events = [
            MockEvent(data={"id": 1}),
            MockEvent(data={"id": 2}),
            MockEvent(data={"id": 3}),
        ]

        filtered = manager.filter_events(events)

        assert len(filtered) == 3
        assert filtered == events

    def test_filter_events_by_session(self):
        """Test filtering events by session ID."""
        manager = ConnectionManager()

        events = [
            MockEvent(session_id="session1", data={"id": 1}),
            MockEvent(session_id="session2", data={"id": 2}),
            MockEvent(session_id="session1", data={"id": 3}),
        ]

        event_filter = EventFilter(session_id="session1")
        filtered = manager.filter_events(events, event_filter)

        assert len(filtered) == 2
        assert all(e.session_id == "session1" for e in filtered)

    def test_filter_events_by_user(self):
        """Test filtering events by user ID."""
        manager = ConnectionManager()

        events = [
            MockEvent(user_id="user1", data={"id": 1}),
            MockEvent(user_id="user2", data={"id": 2}),
            MockEvent(user_id="user1", data={"id": 3}),
        ]

        event_filter = EventFilter(user_id="user1")
        filtered = manager.filter_events(events, event_filter)

        assert len(filtered) == 2
        assert all(e.user_id == "user1" for e in filtered)

    def test_filter_events_by_type(self):
        """Test filtering events by event type."""
        manager = ConnectionManager()

        events = [
            MockEvent(event_type=EventType.SYSTEM_STATUS, data={"id": 1}),
            MockEvent(event_type=EventType.WORKFLOW_PROGRESS, data={"id": 2}),
            MockEvent(event_type=EventType.SYSTEM_STATUS, data={"id": 3}),
        ]

        event_filter = EventFilter(event_types=[EventType.SYSTEM_STATUS])
        filtered = manager.filter_events(events, event_filter)

        assert len(filtered) == 2
        assert all(e.event_type == EventType.SYSTEM_STATUS for e in filtered)

    def test_filter_events_combined_criteria(self):
        """Test filtering with multiple criteria."""
        manager = ConnectionManager()

        events = [
            MockEvent(
                session_id="s1", user_id="u1", event_type=EventType.SYSTEM_STATUS
            ),
            MockEvent(
                session_id="s1", user_id="u2", event_type=EventType.SYSTEM_STATUS
            ),
            MockEvent(
                session_id="s2", user_id="u1", event_type=EventType.SYSTEM_STATUS
            ),
            MockEvent(
                session_id="s1", user_id="u1", event_type=EventType.WORKFLOW_PROGRESS
            ),
        ]

        # Filter for session s1, user u1, and SYSTEM_STATUS type
        event_filter = EventFilter(
            session_id="s1", user_id="u1", event_types=[EventType.SYSTEM_STATUS]
        )
        filtered = manager.filter_events(events, event_filter)

        assert len(filtered) == 1
        assert filtered[0].session_id == "s1"
        assert filtered[0].user_id == "u1"
        assert filtered[0].event_type == EventType.SYSTEM_STATUS

    def test_event_filter_alias_method(self):
        """Test event_filter alias method works correctly."""
        manager = ConnectionManager()

        events = [MockEvent(session_id="test"), MockEvent(session_id="other")]
        event_filter = EventFilter(session_id="test")

        # Test alias method
        filtered = manager.event_filter(events, event_filter)

        assert len(filtered) == 1
        assert filtered[0].session_id == "test"


class TestEventFilterManagement:
    """Test set/get event filter methods."""

    def test_set_event_filter(self):
        """Test setting event filter for a connection."""
        manager = ConnectionManager()

        # Add a connection
        manager.connections["conn1"] = {
            "websocket": Mock(),
            "session_id": "session1",
            "user_id": "user1",
            "event_filter": EventFilter(),
        }

        # Set new filter
        new_filter = EventFilter(session_id="session2")
        manager.set_event_filter("conn1", new_filter)

        assert manager.connections["conn1"]["event_filter"] is new_filter

    def test_set_event_filter_nonexistent_connection(self):
        """Test setting filter for non-existent connection does nothing."""
        manager = ConnectionManager()

        # Should not raise error
        manager.set_event_filter("nonexistent", EventFilter())

        # Connections should remain empty
        assert len(manager.connections) == 0

    def test_get_event_filter(self):
        """Test getting event filter for a connection."""
        manager = ConnectionManager()

        # Add connection with filter
        test_filter = EventFilter(user_id="test_user")
        manager.connections["conn1"] = {
            "websocket": Mock(),
            "event_filter": test_filter,
        }

        retrieved_filter = manager.get_event_filter("conn1")

        assert retrieved_filter is test_filter

    def test_get_event_filter_nonexistent(self):
        """Test getting filter for non-existent connection returns None."""
        manager = ConnectionManager()

        result = manager.get_event_filter("nonexistent")

        assert result is None


class TestEventHandling:
    """Test async event handling methods."""

    @pytest.mark.asyncio
    async def test_on_event_calls_handle_event(self):
        """Test on_event delegates to handle_event."""
        manager = ConnectionManager()
        event = MockEvent(data={"test": "data"})

        # Mock handle_event
        manager.handle_event = AsyncMock()

        await manager.on_event(event)

        manager.handle_event.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_handle_event_calls_process_event(self):
        """Test handle_event delegates to process_event."""
        manager = ConnectionManager()
        event = MockEvent(data={"test": "data"})

        # Mock process_event
        manager.process_event = AsyncMock()

        await manager.handle_event(event)

        manager.process_event.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_process_event_broadcasts_to_connections(self):
        """Test process_event broadcasts to matching connections."""
        manager = ConnectionManager()

        # Add connections
        manager.connections = {
            "conn1": {
                "websocket": AsyncMock(),
                "session_id": "session1",
                "user_id": "user1",
                "event_filter": EventFilter(session_id="session1"),
                "messages_sent": 0,
            },
            "conn2": {
                "websocket": AsyncMock(),
                "session_id": "session2",
                "user_id": "user2",
                "event_filter": EventFilter(session_id="session2"),
                "messages_sent": 0,
            },
        }

        # Mock send_to_connection
        manager.send_to_connection = AsyncMock()

        # Create event for session1
        event = MockEvent(
            session_id="session1", user_id="user1", data={"message": "test"}
        )

        await manager.process_event(event)

        # Check which connections received the event
        call_count = manager.send_to_connection.call_count
        assert call_count >= 1  # At least one connection should receive it

        # Find the call for conn1
        conn1_called = False
        for call in manager.send_to_connection.call_args_list:
            if call[0][0] == "conn1":
                conn1_called = True
                call_args = call
                break

        assert conn1_called, "conn1 should have received the event"

        # Verify message format
        message = call_args[0][1]
        assert message["type"] == "event"
        assert message["data"]["message"] == "test"
        assert "timestamp" in message

    @pytest.mark.asyncio
    async def test_process_event_filters_correctly(self):
        """Test process_event applies filters correctly."""
        manager = ConnectionManager()

        # Add connections with different filters
        manager.connections = {
            "conn1": {
                "websocket": AsyncMock(),
                "session_id": "session1",
                "user_id": "user1",
                "event_filter": EventFilter(
                    session_id="session1", event_types=[EventType.SYSTEM_STATUS]
                ),
                "messages_sent": 0,
            },
            "conn2": {
                "websocket": AsyncMock(),
                "session_id": "session1",
                "user_id": "user2",
                "event_filter": EventFilter(
                    session_id="session1", event_types=[EventType.WORKFLOW_PROGRESS]
                ),
                "messages_sent": 0,
            },
        }

        manager.send_to_connection = AsyncMock()

        # Send SYSTEM_STATUS event
        event = MockEvent(
            event_type=EventType.SYSTEM_STATUS,
            session_id="session1",
            data={"status": "active"},
        )

        await manager.process_event(event)

        # Should only send to conn1 (matching event type)
        assert manager.send_to_connection.call_count == 1
        assert manager.send_to_connection.call_args[0][0] == "conn1"

    @pytest.mark.asyncio
    async def test_process_event_no_filter(self):
        """Test process_event sends to connections without filters."""
        manager = ConnectionManager()

        # Add connection without filter
        manager.connections = {
            "conn1": {
                "websocket": AsyncMock(),
                "session_id": "session1",
                "user_id": "user1",
                "event_filter": None,
                "messages_sent": 0,
            }
        }

        manager.send_to_connection = AsyncMock()

        event = MockEvent(data={"test": "data"})

        await manager.process_event(event)

        # Should send since no filter
        assert manager.send_to_connection.call_count == 1

    @pytest.mark.asyncio
    async def test_process_event_handles_event_type_value(self):
        """Test process_event handles event_type with .value attribute."""
        manager = ConnectionManager()

        # Mock event with enum event_type
        mock_enum = Mock()
        mock_enum.value = "test_event"

        event = MockEvent(data={"test": "data"})
        event.event_type = mock_enum

        manager.connections = {
            "conn1": {
                "websocket": AsyncMock(),
                "event_filter": None,
                "messages_sent": 0,
            }
        }

        manager.send_to_connection = AsyncMock()

        await manager.process_event(event)

        # Verify event_type.value was used
        message = manager.send_to_connection.call_args[0][1]
        assert message["event_type"] == "test_event"


class TestEventHandlingEdgeCases:
    """Test edge cases in event handling."""

    @pytest.mark.asyncio
    async def test_process_event_missing_attributes(self):
        """Test process_event handles events missing optional attributes."""
        manager = ConnectionManager()

        # Create event without session_id or user_id
        event = MockEvent(data={"content": "test"})
        delattr(event, "session_id")
        delattr(event, "user_id")

        manager.connections = {
            "conn1": {
                "websocket": AsyncMock(),
                "event_filter": None,
                "messages_sent": 0,
            }
        }

        manager.send_to_connection = AsyncMock()

        await manager.process_event(event)

        # Should still send
        message = manager.send_to_connection.call_args[0][1]
        assert message["session_id"] is None
        assert message["user_id"] is None

    @pytest.mark.asyncio
    async def test_process_event_empty_connections(self):
        """Test process_event with no connections."""
        manager = ConnectionManager()
        manager.send_to_connection = AsyncMock()

        event = MockEvent(data={"test": "data"})

        # Should not error with empty connections
        await manager.process_event(event)

        # No sends should occur
        manager.send_to_connection.assert_not_called()

    @pytest.mark.asyncio
    async def test_event_chain_integration(self):
        """Test full event handling chain integration."""
        manager = ConnectionManager()

        # Setup connection
        manager.connections = {
            "test_conn": {
                "websocket": AsyncMock(),
                "session_id": "test_session",
                "event_filter": EventFilter(session_id="test_session"),
                "messages_sent": 0,
            }
        }

        # Mock the final send
        original_send = manager.send_to_connection
        manager.send_to_connection = AsyncMock(return_value=True)

        # Create matching event
        event = MockEvent(session_id="test_session", data={"action": "test_action"})

        # Test full chain: on_event -> handle_event -> process_event
        await manager.on_event(event)

        # Verify send was called
        assert manager.send_to_connection.called
        message = manager.send_to_connection.call_args[0][1]
        assert message["data"]["action"] == "test_action"
