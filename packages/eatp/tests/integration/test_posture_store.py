# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests for SQLitePostureStore.

Tier 2 tests using real SQLite (NO MOCKING).
Uses tmp_path pytest fixture for temp directories.
"""

from __future__ import annotations

import os
import platform
import stat
import sqlite3

import pytest

from eatp.posture_store import SQLitePostureStore, validate_agent_id
from eatp.postures import (
    PostureTransition,
    TrustPosture,
    TransitionResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path):
    """Return a path for a temporary SQLite database file."""
    return str(tmp_path / "posture.db")


@pytest.fixture
def store(db_path):
    """Create and return a SQLitePostureStore, closing it after the test."""
    s = SQLitePostureStore(db_path)
    yield s
    s.close()


# ---------------------------------------------------------------------------
# 1. test_create_store
# ---------------------------------------------------------------------------


def test_create_store(db_path):
    """Creating a store should produce the DB file and required tables."""
    store = SQLitePostureStore(db_path)
    try:
        assert os.path.exists(db_path), "Database file was not created"

        # Verify both tables exist by querying sqlite_master
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        table_names = sorted(row[0] for row in cursor.fetchall())
        conn.close()

        assert "postures" in table_names, "postures table missing"
        assert "transitions" in table_names, "transitions table missing"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# 2. test_set_and_get_posture
# ---------------------------------------------------------------------------


def test_set_and_get_posture(store):
    """Setting a posture and retrieving it should return the same value."""
    store.set_posture("agent-001", TrustPosture.SUPERVISED)
    result = store.get_posture("agent-001")
    assert result == TrustPosture.SUPERVISED


# ---------------------------------------------------------------------------
# 3. test_get_posture_default
# ---------------------------------------------------------------------------


def test_get_posture_default(store):
    """An unknown agent should return SUPERVISED as the safe default."""
    result = store.get_posture("nonexistent-agent")
    assert result == TrustPosture.SUPERVISED


# ---------------------------------------------------------------------------
# 4. test_record_and_get_history
# ---------------------------------------------------------------------------


def test_record_and_get_history(store):
    """Recording transitions and retrieving history should return them in reverse order."""
    transitions = [
        TransitionResult(
            success=True,
            from_posture=TrustPosture.SUPERVISED,
            to_posture=TrustPosture.SHARED_PLANNING,
            transition_type=PostureTransition.UPGRADE,
            reason="Initial upgrade",
            metadata={"agent_id": "agent-001"},
        ),
        TransitionResult(
            success=True,
            from_posture=TrustPosture.SHARED_PLANNING,
            to_posture=TrustPosture.CONTINUOUS_INSIGHT,
            transition_type=PostureTransition.UPGRADE,
            reason="Second upgrade",
            metadata={"agent_id": "agent-001"},
        ),
        TransitionResult(
            success=False,
            from_posture=TrustPosture.CONTINUOUS_INSIGHT,
            to_posture=TrustPosture.DELEGATED,
            transition_type=PostureTransition.UPGRADE,
            reason="Blocked by guard",
            blocked_by="approval_guard",
            metadata={"agent_id": "agent-001"},
        ),
    ]
    for t in transitions:
        store.record_transition("agent-001", t)

    history = store.get_history("agent-001")
    assert len(history) == 3

    # History is returned in reverse chronological order (newest first)
    assert history[0].reason == "Blocked by guard"
    assert history[0].blocked_by == "approval_guard"
    assert history[0].success is False
    assert history[1].reason == "Second upgrade"
    assert history[2].reason == "Initial upgrade"


# ---------------------------------------------------------------------------
# 5. test_history_limit
# ---------------------------------------------------------------------------


def test_history_limit(store):
    """get_history with limit should return at most that many entries."""
    for i in range(10):
        store.record_transition(
            "agent-002",
            TransitionResult(
                success=True,
                from_posture=TrustPosture.SUPERVISED,
                to_posture=TrustPosture.SHARED_PLANNING,
                transition_type=PostureTransition.UPGRADE,
                reason=f"transition-{i}",
                metadata={"agent_id": "agent-002"},
            ),
        )

    history = store.get_history("agent-002", limit=3)
    assert len(history) == 3

    # Should be the 3 most recent (newest first)
    assert history[0].reason == "transition-9"
    assert history[1].reason == "transition-8"
    assert history[2].reason == "transition-7"


# ---------------------------------------------------------------------------
# 6. test_persistence_across_restarts
# ---------------------------------------------------------------------------


def test_persistence_across_restarts(db_path):
    """Data should persist when the store is closed and reopened."""
    # First session: write data
    store1 = SQLitePostureStore(db_path)
    store1.set_posture("agent-persist", TrustPosture.DELEGATED)
    store1.record_transition(
        "agent-persist",
        TransitionResult(
            success=True,
            from_posture=TrustPosture.SUPERVISED,
            to_posture=TrustPosture.DELEGATED,
            transition_type=PostureTransition.UPGRADE,
            reason="Persistence test",
            metadata={"agent_id": "agent-persist"},
        ),
    )
    store1.close()

    # Second session: read data
    store2 = SQLitePostureStore(db_path)
    try:
        posture = store2.get_posture("agent-persist")
        assert posture == TrustPosture.DELEGATED

        history = store2.get_history("agent-persist")
        assert len(history) == 1
        assert history[0].reason == "Persistence test"
    finally:
        store2.close()


# ---------------------------------------------------------------------------
# 7. test_file_permissions_posix
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    platform.system() == "Windows",
    reason="File permissions not applicable on Windows",
)
def test_file_permissions_posix(db_path):
    """On POSIX, the DB file should have 0o600 permissions (owner read/write only)."""
    store = SQLitePostureStore(db_path)
    try:
        file_mode = os.stat(db_path).st_mode & 0o777
        assert (
            file_mode == 0o600
        ), f"Expected file permissions 0o600, got {oct(file_mode)}"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# 8. test_reject_path_traversal
# ---------------------------------------------------------------------------


def test_reject_path_traversal(tmp_path):
    """Paths containing '..' components should be rejected."""
    bad_path = str(tmp_path / ".." / "etc" / "posture.db")
    with pytest.raises(ValueError, match="path traversal"):
        SQLitePostureStore(bad_path)


# ---------------------------------------------------------------------------
# 9. test_reject_null_bytes
# ---------------------------------------------------------------------------


def test_reject_null_bytes(tmp_path):
    """Paths containing null bytes should be rejected."""
    bad_path = str(tmp_path / "posture\x00.db")
    with pytest.raises(ValueError, match="null byte"):
        SQLitePostureStore(bad_path)


# ---------------------------------------------------------------------------
# 10. test_reject_symlink
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    platform.system() == "Windows",
    reason="Symlink behavior differs on Windows",
)
def test_reject_symlink(tmp_path):
    """If the db_path is a symlink, the store should reject it."""
    real_file = tmp_path / "real.db"
    real_file.touch()
    link_path = tmp_path / "link.db"
    link_path.symlink_to(real_file)

    with pytest.raises(ValueError, match="symlink"):
        SQLitePostureStore(str(link_path))


# ---------------------------------------------------------------------------
# 11. test_validate_agent_id
# ---------------------------------------------------------------------------


class TestValidateAgentId:
    """Tests for validate_agent_id function."""

    def test_valid_ids(self):
        """Valid agent IDs should pass validation without error."""
        valid_ids = [
            "agent-001",
            "agent_001",
            "AgentAlpha",
            "a",
            "123",
            "my-agent-v2",
            "UPPER_CASE_ID",
        ]
        for agent_id in valid_ids:
            validate_agent_id(agent_id)  # Should not raise

    def test_empty_id_rejected(self):
        """Empty string should be rejected."""
        with pytest.raises(ValueError, match="agent_id"):
            validate_agent_id("")

    def test_path_traversal_rejected(self):
        """IDs with path traversal characters should be rejected."""
        with pytest.raises(ValueError, match="agent_id"):
            validate_agent_id("../bad")

    def test_slash_rejected(self):
        """IDs with slashes should be rejected."""
        with pytest.raises(ValueError, match="agent_id"):
            validate_agent_id("bad/id")

    def test_null_byte_rejected(self):
        """IDs with null bytes should be rejected."""
        with pytest.raises(ValueError, match="agent_id"):
            validate_agent_id("bad\x00id")

    def test_space_rejected(self):
        """IDs with spaces should be rejected."""
        with pytest.raises(ValueError, match="agent_id"):
            validate_agent_id("bad id")

    def test_dot_rejected(self):
        """IDs with dots should be rejected."""
        with pytest.raises(ValueError, match="agent_id"):
            validate_agent_id("bad.id")


# ---------------------------------------------------------------------------
# 12. test_context_manager
# ---------------------------------------------------------------------------


def test_context_manager(db_path):
    """SQLitePostureStore should work as a context manager."""
    with SQLitePostureStore(db_path) as store:
        store.set_posture("agent-ctx", TrustPosture.CONTINUOUS_INSIGHT)
        posture = store.get_posture("agent-ctx")
        assert posture == TrustPosture.CONTINUOUS_INSIGHT

    # After exiting the context, the connection should be closed.
    # Verify by opening a new store and checking data persisted.
    with SQLitePostureStore(db_path) as store2:
        posture = store2.get_posture("agent-ctx")
        assert posture == TrustPosture.CONTINUOUS_INSIGHT


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------


def test_set_posture_upsert(store):
    """Setting posture for an existing agent should update, not duplicate."""
    store.set_posture("agent-upsert", TrustPosture.SUPERVISED)
    store.set_posture("agent-upsert", TrustPosture.DELEGATED)
    result = store.get_posture("agent-upsert")
    assert result == TrustPosture.DELEGATED


def test_history_for_nonexistent_agent(store):
    """History for a nonexistent agent should return an empty list."""
    history = store.get_history("no-such-agent")
    assert history == []


def test_history_limit_bounded_to_max(store):
    """Requesting a limit > 10000 should be capped at 10000."""
    # Just verify it doesn't error -- we don't need 10000+ rows
    history = store.get_history("agent-bounded", limit=99999)
    assert isinstance(history, list)


def test_record_transition_with_metadata(store):
    """Transition metadata should be preserved through round-trip."""
    tr = TransitionResult(
        success=True,
        from_posture=TrustPosture.SUPERVISED,
        to_posture=TrustPosture.SHARED_PLANNING,
        transition_type=PostureTransition.UPGRADE,
        reason="With metadata",
        metadata={"agent_id": "agent-meta", "custom_key": "custom_value"},
    )
    store.record_transition("agent-meta", tr)

    history = store.get_history("agent-meta")
    assert len(history) == 1
    assert history[0].metadata["custom_key"] == "custom_value"
    assert history[0].metadata["agent_id"] == "agent-meta"
