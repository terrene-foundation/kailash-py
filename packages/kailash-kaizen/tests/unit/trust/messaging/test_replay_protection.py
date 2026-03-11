"""
Unit tests for Replay Protection.

Tests cover the intent of replay protection:
- Detecting and preventing message replay attacks
- Tracking seen nonces
- Cleaning up expired nonces
- Thread-safety for concurrent checks

Note: These are unit tests (Tier 1), no external dependencies.
"""

import asyncio
import secrets
from datetime import datetime, timedelta, timezone

import pytest

from kaizen.trust.messaging.replay_protection import InMemoryReplayProtection


class TestInMemoryReplayProtection:
    """Tests for InMemoryReplayProtection."""

    @pytest.fixture
    def protection(self):
        """Create replay protection instance."""
        return InMemoryReplayProtection()

    @pytest.mark.asyncio
    async def test_new_nonce_returns_true(self, protection):
        """New nonce passes check (returns True)."""
        nonce = secrets.token_hex(32)

        result = await protection.check_nonce(
            "msg-1", nonce, datetime.now(timezone.utc)
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_duplicate_nonce_returns_false(self, protection):
        """Duplicate nonce fails check (returns False)."""
        nonce = secrets.token_hex(32)

        # First check passes
        await protection.check_nonce("msg-1", nonce, datetime.now(timezone.utc))

        # Second check with same nonce fails
        result = await protection.check_nonce(
            "msg-1", nonce, datetime.now(timezone.utc)
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_different_nonces_both_pass(self, protection):
        """Different nonces both pass."""
        nonce1 = secrets.token_hex(32)
        nonce2 = secrets.token_hex(32)

        result1 = await protection.check_nonce(
            "msg-1", nonce1, datetime.now(timezone.utc)
        )
        result2 = await protection.check_nonce(
            "msg-2", nonce2, datetime.now(timezone.utc)
        )

        assert result1 is True
        assert result2 is True

    @pytest.mark.asyncio
    async def test_nonce_count_increases(self, protection):
        """Nonce count increases with new nonces."""
        assert protection.get_nonce_count() == 0

        for i in range(5):
            nonce = secrets.token_hex(32)
            await protection.check_nonce(f"msg-{i}", nonce, datetime.now(timezone.utc))

        assert protection.get_nonce_count() == 5

    @pytest.mark.asyncio
    async def test_cleanup_removes_old_nonces(self, protection):
        """Cleanup removes nonces older than TTL."""
        # Add some nonces with old timestamps
        old_time = datetime.now(timezone.utc) - timedelta(seconds=100)
        for i in range(3):
            nonce = f"old-nonce-{i}"
            await protection.check_nonce(f"old-msg-{i}", nonce, old_time)

        # Add some fresh nonces
        for i in range(2):
            nonce = f"new-nonce-{i}"
            await protection.check_nonce(
                f"new-msg-{i}", nonce, datetime.now(timezone.utc)
            )

        assert protection.get_nonce_count() == 5

        # Cleanup with 50 second TTL (old nonces are 100 seconds old)
        removed = await protection.cleanup_expired_nonces(ttl_seconds=50)

        assert removed == 3
        assert protection.get_nonce_count() == 2

    @pytest.mark.asyncio
    async def test_cleanup_returns_zero_when_nothing_expired(self, protection):
        """Cleanup returns 0 when no nonces are expired."""
        # Add fresh nonces
        for i in range(3):
            nonce = secrets.token_hex(32)
            await protection.check_nonce(f"msg-{i}", nonce, datetime.now(timezone.utc))

        # Cleanup with long TTL
        removed = await protection.cleanup_expired_nonces(ttl_seconds=3600)

        assert removed == 0
        assert protection.get_nonce_count() == 3

    @pytest.mark.asyncio
    async def test_clear_removes_all_nonces(self, protection):
        """Clear removes all tracked nonces."""
        for i in range(5):
            nonce = secrets.token_hex(32)
            await protection.check_nonce(f"msg-{i}", nonce, datetime.now(timezone.utc))

        assert protection.get_nonce_count() == 5

        await protection.clear()

        assert protection.get_nonce_count() == 0

    @pytest.mark.asyncio
    async def test_concurrent_checks_are_thread_safe(self, protection):
        """Concurrent checks don't corrupt state."""
        nonces = [secrets.token_hex(32) for _ in range(100)]

        async def check_nonce(i):
            return await protection.check_nonce(
                f"msg-{i}", nonces[i], datetime.now(timezone.utc)
            )

        # Run 100 concurrent checks
        results = await asyncio.gather(*[check_nonce(i) for i in range(100)])

        # All should pass (all unique nonces)
        assert all(results)
        assert protection.get_nonce_count() == 100

    @pytest.mark.asyncio
    async def test_replay_detection_is_immediate(self, protection):
        """Replay is detected immediately after first check."""
        nonce = secrets.token_hex(32)

        # First check
        result1 = await protection.check_nonce(
            "msg-1", nonce, datetime.now(timezone.utc)
        )

        # Immediate replay attempt
        result2 = await protection.check_nonce(
            "msg-1", nonce, datetime.now(timezone.utc)
        )

        assert result1 is True
        assert result2 is False

    @pytest.mark.asyncio
    async def test_same_nonce_different_message_id_still_detected(self, protection):
        """Replay with different message_id is still detected."""
        nonce = secrets.token_hex(32)

        # First check with msg-1
        result1 = await protection.check_nonce(
            "msg-1", nonce, datetime.now(timezone.utc)
        )

        # Same nonce with different message_id
        result2 = await protection.check_nonce(
            "msg-2", nonce, datetime.now(timezone.utc)
        )

        assert result1 is True
        assert result2 is False
