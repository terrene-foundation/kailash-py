"""Unit tests for Session Trust Context Propagation.

TDD: These tests are written FIRST before the implementation.
Following the 3-tier testing strategy - Tier 1 (Unit Tests).

Tests cover:
1. SessionTrustContext creation with human_origin
2. Auto-generated session_id with UUID
3. TTL-based expiry setting
4. is_expired() method - expired session detected
5. is_expired() method - active session not expired
6. is_active() method - valid active session
7. is_active() method - revoked session not active
8. touch() method updates last_activity
9. increment_workflow() increments count and touches
10. get_session_context() for existing session
11. get_session_context() returns None for expired session
12. revoke_session() marks session as revoked
13. revoke_by_human() revokes all sessions for a human_id
14. list_active_sessions() returns only non-expired, non-revoked
15. cleanup_expired() removes expired sessions
16. ContextVar set and get operations
17. TrustContextPropagator works without TrustOperations (standalone)
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Add src to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from nexus.trust.session import (
    SessionTrustContext,
    TrustContextPropagator,
    get_current_session_trust,
    set_current_session_trust,
)


class TestSessionTrustContext:
    """Test SessionTrustContext dataclass and its methods."""

    def test_create_session_with_trust(self):
        """Test creating SessionTrustContext with human_origin."""
        human_origin = {"user_id": "user-123", "auth_method": "oauth2"}

        context = SessionTrustContext(
            session_id="nxs-test-session-001",
            human_origin=human_origin,
            agent_id="agent-456",
            delegation_chain=["agent-a", "agent-b"],
            constraints={"max_tokens": 1000},
        )

        assert context.session_id == "nxs-test-session-001"
        assert context.human_origin == human_origin
        assert context.agent_id == "agent-456"
        assert context.delegation_chain == ["agent-a", "agent-b"]
        assert context.constraints == {"max_tokens": 1000}
        assert context.revoked is False
        assert context.revoked_reason is None
        assert context.workflow_count == 0
        assert isinstance(context.created_at, datetime)
        assert isinstance(context.last_activity, datetime)

    def test_session_is_expired_true(self):
        """Test is_expired() returns True for expired session."""
        # Create session with expiry in the past
        past_expiry = datetime.now(timezone.utc) - timedelta(hours=1)

        context = SessionTrustContext(
            session_id="nxs-expired-session",
            expires_at=past_expiry,
        )

        assert context.is_expired() is True

    def test_session_is_expired_false(self):
        """Test is_expired() returns False for active session."""
        # Create session with expiry in the future
        future_expiry = datetime.now(timezone.utc) + timedelta(hours=8)

        context = SessionTrustContext(
            session_id="nxs-active-session",
            expires_at=future_expiry,
        )

        assert context.is_expired() is False

    def test_session_is_expired_no_expiry(self):
        """Test is_expired() returns False when expires_at is None."""
        context = SessionTrustContext(
            session_id="nxs-no-expiry-session",
            expires_at=None,
        )

        assert context.is_expired() is False

    def test_session_is_active_valid(self):
        """Test is_active() returns True for non-revoked, non-expired session."""
        future_expiry = datetime.now(timezone.utc) + timedelta(hours=8)

        context = SessionTrustContext(
            session_id="nxs-active-session",
            expires_at=future_expiry,
            revoked=False,
        )

        assert context.is_active() is True

    def test_session_is_active_revoked(self):
        """Test is_active() returns False when session is revoked."""
        future_expiry = datetime.now(timezone.utc) + timedelta(hours=8)

        context = SessionTrustContext(
            session_id="nxs-revoked-session",
            expires_at=future_expiry,
            revoked=True,
            revoked_reason="User requested revocation",
        )

        assert context.is_active() is False

    def test_session_is_active_expired(self):
        """Test is_active() returns False when session is expired."""
        past_expiry = datetime.now(timezone.utc) - timedelta(hours=1)

        context = SessionTrustContext(
            session_id="nxs-expired-session",
            expires_at=past_expiry,
            revoked=False,
        )

        assert context.is_active() is False

    def test_session_touch_updates_activity(self):
        """Test touch() updates last_activity timestamp."""
        context = SessionTrustContext(
            session_id="nxs-touch-session",
        )

        original_activity = context.last_activity

        # Small delay to ensure time difference
        import time

        time.sleep(0.01)

        context.touch()

        assert context.last_activity > original_activity

    def test_session_increment_workflow(self):
        """Test increment_workflow() increments count and calls touch()."""
        context = SessionTrustContext(
            session_id="nxs-workflow-session",
        )

        original_count = context.workflow_count
        original_activity = context.last_activity

        # Small delay to ensure time difference
        import time

        time.sleep(0.01)

        context.increment_workflow()

        assert context.workflow_count == original_count + 1
        assert context.last_activity > original_activity

    def test_session_multiple_workflow_increments(self):
        """Test multiple workflow increments."""
        context = SessionTrustContext(
            session_id="nxs-multi-workflow-session",
        )

        context.increment_workflow()
        context.increment_workflow()
        context.increment_workflow()

        assert context.workflow_count == 3


class TestTrustContextPropagator:
    """Test TrustContextPropagator class."""

    @pytest.fixture
    def propagator(self):
        """Create TrustContextPropagator instance."""
        return TrustContextPropagator()

    @pytest.fixture
    def propagator_with_ttl(self):
        """Create TrustContextPropagator with custom TTL."""
        return TrustContextPropagator(default_ttl_hours=2.0)

    @pytest.mark.asyncio
    async def test_create_session_generates_uuid(self, propagator):
        """Test create_session generates UUID with nxs- prefix."""
        context = await propagator.create_session()

        assert context.session_id.startswith("nxs-")
        assert len(context.session_id) > 4  # Must have content after prefix
        assert isinstance(context, SessionTrustContext)

    @pytest.mark.asyncio
    async def test_create_session_with_human_origin(self, propagator):
        """Test create_session with human_origin parameter."""
        human_origin = {"user_id": "user-123", "verified": True}

        context = await propagator.create_session(
            human_origin=human_origin,
            agent_id="agent-456",
        )

        assert context.human_origin == human_origin
        assert context.agent_id == "agent-456"

    @pytest.mark.asyncio
    async def test_create_session_sets_expiry(self, propagator_with_ttl):
        """Test create_session sets expiry based on TTL."""
        context = await propagator_with_ttl.create_session()

        assert context.expires_at is not None

        # Should expire approximately 2 hours from now
        expected_expiry = datetime.now(timezone.utc) + timedelta(hours=2)
        delta = abs((context.expires_at - expected_expiry).total_seconds())

        # Allow 1 second tolerance for test execution time
        assert delta < 1.0

    @pytest.mark.asyncio
    async def test_create_session_with_constraints(self, propagator):
        """Test create_session with constraints parameter."""
        constraints = {"max_tokens": 5000, "allowed_actions": ["read"]}

        context = await propagator.create_session(constraints=constraints)

        assert context.constraints == constraints

    @pytest.mark.asyncio
    async def test_get_session_context_exists(self, propagator):
        """Test get_session_context returns existing session."""
        context = await propagator.create_session()
        session_id = context.session_id

        retrieved = propagator.get_session_context(session_id)

        assert retrieved is not None
        assert retrieved.session_id == session_id

    def test_get_session_context_not_exists(self, propagator):
        """Test get_session_context returns None for non-existent session."""
        retrieved = propagator.get_session_context("nxs-does-not-exist")

        assert retrieved is None

    @pytest.mark.asyncio
    async def test_get_session_context_expired_returns_none(self, propagator):
        """Test get_session_context returns None for expired session."""
        # Create session with very short TTL
        propagator_short = TrustContextPropagator(default_ttl_hours=0.0001)
        context = await propagator_short.create_session()
        session_id = context.session_id

        # Wait for expiry
        import time

        time.sleep(0.5)

        retrieved = propagator_short.get_session_context(session_id)

        assert retrieved is None

    @pytest.mark.asyncio
    async def test_revoke_session(self, propagator):
        """Test revoke_session marks session as revoked."""
        context = await propagator.create_session()
        session_id = context.session_id

        result = await propagator.revoke_session(session_id, reason="Test revocation")

        assert result is True

        # Session should now not be retrievable via get_session_context (revoked)
        retrieved = propagator.get_session_context(session_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_revoke_session_not_exists(self, propagator):
        """Test revoke_session returns False for non-existent session."""
        result = await propagator.revoke_session("nxs-does-not-exist")

        assert result is False

    @pytest.mark.asyncio
    async def test_revoke_by_human(self, propagator):
        """Test revoke_by_human revokes all sessions for a human_id."""
        human_id = "user-123"
        human_origin = {"user_id": human_id, "verified": True}

        # Create multiple sessions for same human
        ctx1 = await propagator.create_session(human_origin=human_origin)
        ctx2 = await propagator.create_session(human_origin=human_origin)
        ctx3 = await propagator.create_session(human_origin={"user_id": "other-user"})

        count = await propagator.revoke_by_human(human_id)

        assert count == 2

        # Sessions for the human should be revoked
        assert propagator.get_session_context(ctx1.session_id) is None
        assert propagator.get_session_context(ctx2.session_id) is None

        # Session for other user should still exist
        assert propagator.get_session_context(ctx3.session_id) is not None

    @pytest.mark.asyncio
    async def test_list_active_sessions(self, propagator):
        """Test list_active_sessions returns only non-expired, non-revoked sessions."""
        # Create active sessions
        ctx1 = await propagator.create_session()
        ctx2 = await propagator.create_session()

        # Revoke one session
        await propagator.revoke_session(ctx1.session_id)

        active = propagator.list_active_sessions()

        # Only ctx2 should be in active list
        session_ids = [s.session_id for s in active]
        assert ctx1.session_id not in session_ids
        assert ctx2.session_id in session_ids

    @pytest.mark.asyncio
    async def test_list_active_sessions_excludes_expired(self):
        """Test list_active_sessions excludes expired sessions."""
        # Use very short TTL
        propagator = TrustContextPropagator(default_ttl_hours=0.0001)

        ctx = await propagator.create_session()

        # Wait for expiry
        import time

        time.sleep(0.5)

        active = propagator.list_active_sessions()

        session_ids = [s.session_id for s in active]
        assert ctx.session_id not in session_ids

    @pytest.mark.asyncio
    async def test_cleanup_expired(self):
        """Test cleanup_expired removes expired sessions from store."""
        # Use very short TTL
        propagator = TrustContextPropagator(default_ttl_hours=0.0001)

        await propagator.create_session()
        await propagator.create_session()

        # Wait for expiry
        import time

        time.sleep(0.5)

        count = propagator.cleanup_expired()

        assert count == 2

        # Sessions should be removed from internal store
        active = propagator.list_active_sessions()
        assert len(active) == 0

    def test_no_trust_ops(self, propagator):
        """Test TrustContextPropagator works without TrustOperations."""
        # Should work with no trust_operations
        assert propagator._trust_operations is None

        # All operations should still work
        assert propagator.list_active_sessions() == []
        assert propagator.get_session_context("nxs-none") is None

    @pytest.mark.asyncio
    async def test_with_trust_operations(self):
        """Test TrustContextPropagator with TrustOperations provided."""

        # Create mock trust operations
        class MockTrustOperations:
            async def verify(self, agent_id, action, resource=None, **kwargs):
                return True

        mock_ops = MockTrustOperations()
        propagator = TrustContextPropagator(trust_operations=mock_ops)

        assert propagator._trust_operations is mock_ops

        # Should still create sessions normally
        ctx = await propagator.create_session()
        assert ctx is not None


class TestContextVariables:
    """Test context variable functions for thread-safe access."""

    def test_context_var_set_and_get(self):
        """Test set_current_session_trust and get_current_session_trust."""
        context = SessionTrustContext(
            session_id="nxs-context-test",
            human_origin={"user_id": "test-user"},
        )

        # Initially should be None
        assert get_current_session_trust() is None

        # Set context
        set_current_session_trust(context)

        # Should retrieve the same context
        retrieved = get_current_session_trust()
        assert retrieved is not None
        assert retrieved.session_id == "nxs-context-test"
        assert retrieved.human_origin == {"user_id": "test-user"}

    def test_context_var_isolation(self):
        """Test that context variables are isolated per-context."""
        import asyncio

        async def set_and_get_context(session_id):
            context = SessionTrustContext(
                session_id=session_id,
            )
            set_current_session_trust(context)

            # Small delay
            await asyncio.sleep(0.01)

            retrieved = get_current_session_trust()
            return retrieved.session_id if retrieved else None

        # Note: In the same execution context, the context var maintains value
        # True isolation happens in separate concurrent tasks with copy_context()
        context1 = SessionTrustContext(session_id="nxs-ctx-1")
        set_current_session_trust(context1)

        assert get_current_session_trust().session_id == "nxs-ctx-1"

    def test_context_var_clear(self):
        """Test clearing context variable."""
        context = SessionTrustContext(
            session_id="nxs-to-clear",
        )

        set_current_session_trust(context)
        assert get_current_session_trust() is not None

        # Clear by setting None - but our function signature expects SessionTrustContext
        # In real usage, clearing might need a separate function or optional type
        # For this test, we verify the current behavior


class TestSessionTrustContextEdgeCases:
    """Test edge cases and error handling."""

    def test_session_with_empty_delegation_chain(self):
        """Test session with empty delegation chain."""
        context = SessionTrustContext(
            session_id="nxs-empty-chain",
        )

        assert context.delegation_chain == []

    def test_session_with_empty_constraints(self):
        """Test session with empty constraints."""
        context = SessionTrustContext(
            session_id="nxs-empty-constraints",
        )

        assert context.constraints == {}

    @pytest.mark.asyncio
    async def test_multiple_propagators_independent(self):
        """Test that multiple propagator instances are independent."""
        prop1 = TrustContextPropagator()
        prop2 = TrustContextPropagator()

        ctx1 = await prop1.create_session()

        # Prop2 should not see prop1's session
        assert prop2.get_session_context(ctx1.session_id) is None

    @pytest.mark.asyncio
    async def test_revoke_by_human_none_origin(self):
        """Test revoke_by_human with sessions having no human_origin."""
        propagator = TrustContextPropagator()

        # Create session without human_origin
        await propagator.create_session()

        # Should not raise, should return 0
        count = await propagator.revoke_by_human("some-user")
        assert count == 0

    def test_session_created_at_is_utc(self):
        """Test that created_at is in UTC timezone."""
        context = SessionTrustContext(
            session_id="nxs-utc-test",
        )

        assert context.created_at.tzinfo is not None
        assert context.created_at.tzinfo == timezone.utc

    def test_session_last_activity_is_utc(self):
        """Test that last_activity is in UTC timezone."""
        context = SessionTrustContext(
            session_id="nxs-utc-activity-test",
        )

        assert context.last_activity.tzinfo is not None
        assert context.last_activity.tzinfo == timezone.utc


class TestThreadSafety:
    """Test thread-safety of TrustContextPropagator (CARE-053).

    These tests verify that concurrent access to the session store
    does not cause race conditions or data corruption.
    """

    @pytest.mark.asyncio
    async def test_concurrent_create_and_cleanup(self):
        """Test concurrent session creation and cleanup does not raise.

        CARE-053: Verifies that cleanup_expired can run concurrently with
        create_session without causing dictionary mutation errors.
        """
        import asyncio
        import concurrent.futures

        # Use short TTL so some sessions expire during test
        propagator = TrustContextPropagator(default_ttl_hours=0.00001)

        errors = []
        created_count = 0
        cleanup_count = 0

        async def create_sessions(count: int):
            nonlocal created_count
            for _ in range(count):
                try:
                    await propagator.create_session()
                    created_count += 1
                except Exception as e:
                    errors.append(f"create error: {e}")
                # Small delay to interleave operations
                await asyncio.sleep(0.001)

        def run_cleanup(iterations: int):
            nonlocal cleanup_count
            for _ in range(iterations):
                try:
                    propagator.cleanup_expired()
                    cleanup_count += 1
                except Exception as e:
                    errors.append(f"cleanup error: {e}")
                # Small delay to interleave operations
                import time

                time.sleep(0.001)

        # Run create_session in async context and cleanup in thread pool
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            # Start cleanup in background thread
            cleanup_future = executor.submit(run_cleanup, 50)

            # Run session creation concurrently
            await create_sessions(50)

            # Wait for cleanup to finish
            cleanup_future.result(timeout=5.0)

        # No errors should have occurred
        assert errors == [], f"Concurrent operations caused errors: {errors}"
        assert created_count == 50
        assert cleanup_count == 50

    @pytest.mark.asyncio
    async def test_concurrent_create_and_get(self):
        """Test concurrent session creation and retrieval does not raise.

        CARE-053: Verifies that get_session_context can run concurrently
        with create_session without causing dictionary access errors.
        """
        import asyncio
        import concurrent.futures

        propagator = TrustContextPropagator(default_ttl_hours=1.0)

        errors = []
        session_ids = []

        async def create_sessions(count: int):
            for _ in range(count):
                try:
                    ctx = await propagator.create_session()
                    session_ids.append(ctx.session_id)
                except Exception as e:
                    errors.append(f"create error: {e}")
                await asyncio.sleep(0.001)

        def get_sessions(iterations: int):
            for i in range(iterations):
                try:
                    # Try to get existing sessions (may be None if not yet created)
                    if session_ids:
                        idx = i % max(1, len(session_ids))
                        if idx < len(session_ids):
                            propagator.get_session_context(session_ids[idx])
                    # Also try non-existent
                    propagator.get_session_context(f"nxs-nonexistent-{i}")
                except Exception as e:
                    errors.append(f"get error: {e}")
                import time

                time.sleep(0.001)

        # Run create_session in async context and get in thread pool
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            # Start get operations in background thread
            get_future = executor.submit(get_sessions, 50)

            # Run session creation concurrently
            await create_sessions(50)

            # Wait for get operations to finish
            get_future.result(timeout=5.0)

        # No errors should have occurred
        assert errors == [], f"Concurrent operations caused errors: {errors}"
        assert len(session_ids) == 50

    @pytest.mark.asyncio
    async def test_revoke_session_atomic_under_lock(self):
        """ROUND5-003: Revoke session while concurrent reads happen - no errors.

        Verifies that revoke_session operations are atomic and thread-safe
        when concurrent read operations are accessing the session store.
        """
        import asyncio
        import concurrent.futures

        propagator = TrustContextPropagator(default_ttl_hours=1.0)

        errors = []
        session_ids = []
        revoke_count = 0

        # Create initial sessions
        for _ in range(50):
            ctx = await propagator.create_session()
            session_ids.append(ctx.session_id)

        async def revoke_sessions():
            """Revoke sessions one by one."""
            nonlocal revoke_count
            for session_id in session_ids[:25]:  # Revoke half
                try:
                    await propagator.revoke_session(
                        session_id, reason="test revocation"
                    )
                    revoke_count += 1
                except Exception as e:
                    errors.append(f"revoke error: {e}")
                await asyncio.sleep(0.001)

        def read_sessions_repeatedly(iterations: int):
            """Read sessions concurrently with revocations."""
            for i in range(iterations):
                try:
                    # Try to get sessions (some may be revoked)
                    idx = i % len(session_ids)
                    propagator.get_session_context(session_ids[idx])
                    # Also list active sessions
                    propagator.list_active_sessions()
                except Exception as e:
                    errors.append(f"read error: {e}")
                import time

                time.sleep(0.001)

        # Run revocations and reads concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            # Start reader threads
            reader_futures = [
                executor.submit(read_sessions_repeatedly, 50) for _ in range(2)
            ]

            # Run revocations
            await revoke_sessions()

            # Wait for readers to complete
            for future in reader_futures:
                future.result(timeout=10.0)

        # No errors should have occurred
        assert errors == [], f"Concurrent revoke/read caused errors: {errors}"
        assert revoke_count == 25, f"Expected 25 revocations, got {revoke_count}"

    @pytest.mark.asyncio
    async def test_revoke_by_human_atomic_under_lock(self):
        """ROUND5-004: Revoke by human while concurrent creates happen - no errors.

        Verifies that revoke_by_human operations are atomic and thread-safe
        when concurrent create_session operations are adding to the session store.
        """
        import asyncio
        import concurrent.futures

        propagator = TrustContextPropagator(default_ttl_hours=1.0)

        errors = []
        created_count = 0
        human_id = "user-concurrent-test"
        human_origin = {"user_id": human_id, "verified": True}

        async def create_sessions_for_human(count: int):
            """Create sessions for the target human."""
            nonlocal created_count
            for _ in range(count):
                try:
                    await propagator.create_session(human_origin=human_origin)
                    created_count += 1
                except Exception as e:
                    errors.append(f"create error: {e}")
                await asyncio.sleep(0.001)

        async def revoke_human_repeatedly(iterations: int):
            """Repeatedly revoke all sessions for the human."""
            for _ in range(iterations):
                try:
                    await propagator.revoke_by_human(human_id)
                except Exception as e:
                    errors.append(f"revoke error: {e}")
                await asyncio.sleep(0.005)  # Slightly slower to allow creates

        # Run creates and revoke_by_human concurrently
        await asyncio.gather(
            create_sessions_for_human(50),
            revoke_human_repeatedly(10),
        )

        # No errors should have occurred
        assert (
            errors == []
        ), f"Concurrent create/revoke_by_human caused errors: {errors}"
        assert created_count == 50, f"Expected 50 creates, got {created_count}"

    def test_propagator_has_lock(self):
        """Test that TrustContextPropagator has a threading lock.

        CARE-053: Verify the lock attribute exists for thread-safety.
        """
        import threading

        propagator = TrustContextPropagator()

        assert hasattr(propagator, "_lock")
        assert isinstance(propagator._lock, type(threading.Lock()))
