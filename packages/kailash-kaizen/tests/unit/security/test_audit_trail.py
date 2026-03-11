"""Tier 1 unit tests for audit trail system."""

from datetime import datetime

from kaizen.security.audit import AuditTrailProvider


class TestAuditTrailProvider:
    """Test suite for AuditTrailProvider (Tier 1 - Unit Tests)."""

    def test_log_audit_event(self):
        """Test 2.1: Log basic audit event and verify storage."""
        # Initialize audit provider
        provider = AuditTrailProvider()

        # Log an audit event
        event_data = {
            "user": "test_user",
            "action": "authentication",
            "result": "success",
            "metadata": {"ip_address": "192.168.1.1"},
        }

        event_id = provider.log_event(**event_data)

        # Verify event was stored
        assert event_id is not None

        # Retrieve the event
        event = provider.get_event(event_id)

        # Verify event structure
        assert event["user"] == "test_user"
        assert event["action"] == "authentication"
        assert event["result"] == "success"
        assert event["metadata"]["ip_address"] == "192.168.1.1"
        assert "timestamp" in event
        assert isinstance(event["timestamp"], datetime)

    def test_query_events_by_user(self):
        """Test 2.2: Query audit events by user."""
        provider = AuditTrailProvider()

        # Log events for different users
        provider.log_event(user="alice", action="login", result="success", metadata={})
        provider.log_event(user="bob", action="login", result="success", metadata={})
        provider.log_event(user="alice", action="logout", result="success", metadata={})

        # Query events for alice
        alice_events = provider.query_events(user="alice")

        # Verify results
        assert len(alice_events) == 2
        assert all(event["user"] == "alice" for event in alice_events)
        assert any(event["action"] == "login" for event in alice_events)
        assert any(event["action"] == "logout" for event in alice_events)

    def test_query_events_by_action(self):
        """Test 2.2: Query audit events by action."""
        provider = AuditTrailProvider()

        # Log events with different actions
        provider.log_event(user="alice", action="login", result="success", metadata={})
        provider.log_event(
            user="bob", action="data_access", result="success", metadata={}
        )
        provider.log_event(
            user="charlie", action="login", result="success", metadata={}
        )

        # Query events for login action
        login_events = provider.query_events(action="login")

        # Verify results
        assert len(login_events) == 2
        assert all(event["action"] == "login" for event in login_events)
        assert any(event["user"] == "alice" for event in login_events)
        assert any(event["user"] == "charlie" for event in login_events)

    def test_query_events_by_time_range(self):
        """Test 2.2: Query audit events by time range."""

        provider = AuditTrailProvider()

        # Log events at different times
        event1_id = provider.log_event(
            user="alice", action="login", result="success", metadata={}
        )
        event1 = provider.get_event(event1_id)
        start_time = event1["timestamp"]

        provider.log_event(
            user="bob", action="data_access", result="success", metadata={}
        )

        event3_id = provider.log_event(
            user="charlie", action="logout", result="success", metadata={}
        )
        event3 = provider.get_event(event3_id)
        end_time = event3["timestamp"]

        # Query events within time range
        events = provider.query_events(start_time=start_time, end_time=end_time)

        # Verify all events are within range
        assert len(events) == 3
        for event in events:
            assert event["timestamp"] >= start_time
            assert event["timestamp"] <= end_time

    def test_query_events_by_result(self):
        """Test 2.2: Filter audit events by result (success/failure)."""
        provider = AuditTrailProvider()

        # Log events with different results
        provider.log_event(user="alice", action="login", result="success", metadata={})
        provider.log_event(user="bob", action="login", result="failure", metadata={})
        provider.log_event(
            user="charlie", action="data_access", result="success", metadata={}
        )
        provider.log_event(
            user="dave", action="data_access", result="failure", metadata={}
        )

        # Query successful events
        success_events = provider.query_events(result="success")
        assert len(success_events) == 2
        assert all(event["result"] == "success" for event in success_events)

        # Query failed events
        failure_events = provider.query_events(result="failure")
        assert len(failure_events) == 2
        assert all(event["result"] == "failure" for event in failure_events)

    def test_query_events_combined_filters(self):
        """Test 2.2: Query audit events with multiple combined filters."""
        provider = AuditTrailProvider()

        # Log various events
        provider.log_event(user="alice", action="login", result="success", metadata={})
        provider.log_event(user="alice", action="login", result="failure", metadata={})
        provider.log_event(
            user="alice", action="data_access", result="success", metadata={}
        )
        provider.log_event(user="bob", action="login", result="success", metadata={})

        # Query with combined filters: alice's successful logins
        events = provider.query_events(user="alice", action="login", result="success")

        # Verify results
        assert len(events) == 1
        assert events[0]["user"] == "alice"
        assert events[0]["action"] == "login"
        assert events[0]["result"] == "success"

    def test_query_events_no_matches(self):
        """Test 2.2: Query audit events with no matching results."""
        provider = AuditTrailProvider()

        # Log some events
        provider.log_event(user="alice", action="login", result="success", metadata={})
        provider.log_event(user="bob", action="logout", result="success", metadata={})

        # Query for non-existent user
        events = provider.query_events(user="charlie")

        # Verify empty result
        assert len(events) == 0
        assert events == []

    def test_query_events_with_pagination(self):
        """Test 2.4a: Query events with limit and offset pagination."""
        provider = AuditTrailProvider()

        # Log 10 events
        for i in range(10):
            provider.log_event(
                user=f"user_{i}",
                action="test_action",
                result="success",
                metadata={"index": i},
            )

        # Query first 3 events
        page1 = provider.query_events(limit=3, offset=0)
        assert len(page1) == 3

        # Query next 3 events
        page2 = provider.query_events(limit=3, offset=3)
        assert len(page2) == 3

        # Verify pages don't overlap
        page1_users = {e["user"] for e in page1}
        page2_users = {e["user"] for e in page2}
        assert len(page1_users & page2_users) == 0  # No overlap

    def test_query_events_with_sorting(self):
        """Test 2.4b: Query events with sorting by timestamp."""
        import time

        provider = AuditTrailProvider()

        # Log events with delays to ensure different timestamps
        provider.log_event(user="user3", action="action", result="success", metadata={})
        time.sleep(0.01)
        provider.log_event(user="user1", action="action", result="success", metadata={})
        time.sleep(0.01)
        provider.log_event(user="user2", action="action", result="success", metadata={})

        # Query sorted by timestamp ascending (oldest first)
        events_asc = provider.query_events(sort_by="timestamp", order="asc")
        assert events_asc[0]["user"] == "user3"  # First logged
        assert events_asc[1]["user"] == "user1"
        assert events_asc[2]["user"] == "user2"  # Last logged

        # Query sorted by timestamp descending (newest first)
        events_desc = provider.query_events(sort_by="timestamp", order="desc")
        assert events_desc[0]["user"] == "user2"  # Last logged
        assert events_desc[1]["user"] == "user1"
        assert events_desc[2]["user"] == "user3"  # First logged

    def test_count_events(self):
        """Test 2.4c: Count events matching filters."""
        provider = AuditTrailProvider()

        # Log events with different results
        for i in range(7):
            provider.log_event(
                user="user", action="action", result="success", metadata={}
            )
        for i in range(3):
            provider.log_event(
                user="user", action="action", result="failure", metadata={}
            )

        # Count total events
        total = provider.count_events()
        assert total == 10

        # Count success events
        success_count = provider.count_events(result="success")
        assert success_count == 7

        # Count failure events
        failure_count = provider.count_events(result="failure")
        assert failure_count == 3
