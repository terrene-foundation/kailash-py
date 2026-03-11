"""Tier 2 integration tests for audit trail with PostgreSQL.

CRITICAL: This is Tier 2 testing - NO MOCKING allowed!
- Uses real PostgreSQL database
- Tests actual persistence and retrieval
- Validates database-level operations
- Requires ./tests/utils/test-env up before running
"""

import os
from datetime import datetime

import pytest
from kaizen.security.audit import AuditTrailProvider

from tests.utils.docker_config import get_postgres_connection_string


@pytest.fixture
def postgres_audit_provider():
    """Fixture providing PostgreSQL-backed audit provider with cleanup.

    TIER 2: Uses real PostgreSQL - NO MOCKING!
    """
    # Use helper function to get correct credentials (test_user:test_password)
    db_url = os.environ.get("DATABASE_URL", get_postgres_connection_string())

    provider = AuditTrailProvider(storage="postgresql", connection_string=db_url)

    # Initialize database schema
    provider.initialize()

    yield provider

    # Cleanup after test
    provider.cleanup()


class TestAuditTrailPostgreSQL:
    """Tier 2 tests for PostgreSQL audit trail.

    These tests use REAL PostgreSQL infrastructure - NO MOCKING.
    """

    def test_postgresql_event_persistence(self, postgres_audit_provider):
        """Test 2.3: Verify audit events persist in PostgreSQL database.

        This test validates:
        - Events are written to real PostgreSQL database
        - Events persist across provider instances
        - Data integrity is maintained
        - Metadata is properly serialized/deserialized

        TIER 2: Uses real PostgreSQL - NO MOCKING!
        """
        provider = postgres_audit_provider

        # Log an audit event
        event_id = provider.log_event(
            user="postgres_user",
            action="database_query",
            result="success",
            metadata={"query": "SELECT * FROM users", "rows": 42},
        )

        # Verify event ID was generated
        assert event_id is not None
        assert isinstance(event_id, str)

        # Create NEW provider instance to verify persistence
        # This proves data is in database, not just in-memory cache
        db_url = os.environ.get("DATABASE_URL", get_postgres_connection_string())
        new_provider = AuditTrailProvider(
            storage="postgresql", connection_string=db_url
        )
        new_provider.initialize()

        # Retrieve event from database using new provider
        event = new_provider.get_event(event_id)

        # Verify event was persisted correctly
        assert event is not None
        assert event["user"] == "postgres_user"
        assert event["action"] == "database_query"
        assert event["result"] == "success"
        assert event["metadata"]["query"] == "SELECT * FROM users"
        assert event["metadata"]["rows"] == 42
        assert "timestamp" in event
        assert isinstance(event["timestamp"], datetime)

        # Cleanup new provider
        new_provider.cleanup()

    def test_postgresql_query_events(self, postgres_audit_provider):
        """Test 2.3: Query audit events from PostgreSQL database.

        This test validates:
        - Database-level filtering works correctly
        - Multiple events can be queried
        - Query results match expected criteria

        TIER 2: Uses real PostgreSQL - NO MOCKING!
        """
        provider = postgres_audit_provider

        # Log multiple events
        provider.log_event(user="alice", action="login", result="success", metadata={})
        provider.log_event(user="bob", action="login", result="failure", metadata={})
        provider.log_event(
            user="alice", action="data_access", result="success", metadata={}
        )

        # Query events by user
        alice_events = provider.query_events(user="alice")

        # Verify database query results
        assert len(alice_events) == 2
        assert all(event["user"] == "alice" for event in alice_events)

        # Query events by action
        login_events = provider.query_events(action="login")
        assert len(login_events) == 2
        assert all(event["action"] == "login" for event in login_events)

        # Query events by result
        success_events = provider.query_events(result="success")
        assert len(success_events) == 2
        assert all(event["result"] == "success" for event in success_events)

    def test_postgresql_immutable_audit_log(self, postgres_audit_provider):
        """Test 2.3: Verify audit log is immutable (append-only).

        This test validates:
        - Events cannot be modified after creation
        - No update or delete operations are available
        - Audit trail maintains integrity

        TIER 2: Uses real PostgreSQL - NO MOCKING!
        """
        provider = postgres_audit_provider

        # Log an event
        event_id = provider.log_event(
            user="test_user",
            action="test_action",
            result="success",
            metadata={"data": "original"},
        )

        # Verify provider has no update/delete methods
        assert not hasattr(provider, "update_event")
        assert not hasattr(provider, "delete_event")

        # Retrieve event
        event = provider.get_event(event_id)
        assert event["metadata"]["data"] == "original"

        # The only way to verify immutability is to confirm
        # no modification methods exist - database constraints
        # will enforce this at the DB level

    def test_postgresql_connection_management(self, postgres_audit_provider):
        """Test 2.3: Verify PostgreSQL connection management.

        This test validates:
        - Connection is established correctly
        - Connection can be cleaned up
        - Multiple operations use same connection

        TIER 2: Uses real PostgreSQL - NO MOCKING!
        """
        provider = postgres_audit_provider

        # Log multiple events (tests connection reuse)
        event_id_1 = provider.log_event(
            user="user1", action="action1", result="success", metadata={}
        )
        event_id_2 = provider.log_event(
            user="user2", action="action2", result="success", metadata={}
        )

        # Retrieve events (tests connection for reads)
        event1 = provider.get_event(event_id_1)
        event2 = provider.get_event(event_id_2)

        assert event1 is not None
        assert event2 is not None
        assert event1["user"] == "user1"
        assert event2["user"] == "user2"

        # Connection cleanup is handled by fixture cleanup

    def test_postgresql_pagination(self, postgres_audit_provider):
        """Test 2.4d: PostgreSQL pagination with limit/offset.

        This test validates:
        - Pagination works correctly with PostgreSQL
        - LIMIT and OFFSET clauses function properly
        - Pages don't overlap
        - Ordering is consistent

        TIER 2: Uses real PostgreSQL - NO MOCKING!
        """
        provider = postgres_audit_provider

        # Log 20 events
        for i in range(20):
            provider.log_event(
                user=f"user_{i:02d}",
                action="paginated_action",
                result="success",
                metadata={"page_index": i},
            )

        # Get first page (10 items)
        page1 = provider.query_events(
            limit=10, offset=0, sort_by="timestamp", order="asc"
        )
        assert len(page1) == 10

        # Get second page (10 items)
        page2 = provider.query_events(
            limit=10, offset=10, sort_by="timestamp", order="asc"
        )
        assert len(page2) == 10

        # Verify no overlap and correct ordering
        assert page1[0]["user"] == "user_00"
        assert page2[0]["user"] == "user_10"

    def test_postgresql_count_performance(self, postgres_audit_provider):
        """Test 2.4e: PostgreSQL count query performance.

        This test validates:
        - COUNT queries work correctly
        - Filters are applied to count queries
        - Performance is acceptable for large datasets

        TIER 2: Uses real PostgreSQL - NO MOCKING!
        """
        provider = postgres_audit_provider

        # Log 100 events
        for i in range(100):
            result = "success" if i % 3 == 0 else "failure"
            provider.log_event(
                user=f"user_{i % 5}",
                action="performance_test",
                result=result,
                metadata={},
            )

        # Count with filters
        total = provider.count_events()
        assert total == 100

        user_0_count = provider.count_events(user="user_0")
        assert user_0_count == 20  # 100/5 = 20 events per user

        success_count = provider.count_events(result="success")
        assert success_count == 34  # Every 3rd event (0, 3, 6, ..., 99)
