"""Tests for the session management system.

Covers:
- SessionManager: save, load, list, fork, delete, auto_save
- Session format: JSON with messages, usage stats, config snapshot
- Path sanitization for session names
"""

from __future__ import annotations

import json

import pytest

from kaizen_agents.delegate.loop import Conversation, UsageTracker
from kaizen_agents.delegate.config.effort import EffortLevel
from kaizen_agents.delegate.config.loader import KzConfig
from kaizen_agents.delegate.session import SessionManager


@pytest.fixture()
def sessions_dir(tmp_path):
    """Create a temporary sessions directory."""
    d = tmp_path / "sessions"
    d.mkdir()
    return d


@pytest.fixture()
def manager(sessions_dir):
    return SessionManager(sessions_dir)


@pytest.fixture()
def conversation():
    conv = Conversation()
    conv.add_system("You are kz.")
    conv.add_user("Hello")
    conv.add_assistant("Hi there!")
    conv.add_user("What can you do?")
    conv.add_assistant("I can help with many tasks.")
    return conv


@pytest.fixture()
def usage():
    tracker = UsageTracker()
    tracker.prompt_tokens = 1200
    tracker.completion_tokens = 400
    tracker.total_tokens = 1600
    tracker.turns = 4
    return tracker


@pytest.fixture()
def config():
    return KzConfig(
        model="gpt-4o",
        effort_level=EffortLevel.MEDIUM,
        max_turns=50,
        max_tokens=16384,
        temperature=0.4,
    )


# -----------------------------------------------------------------------
# Save
# -----------------------------------------------------------------------


class TestSaveSession:
    def test_save_creates_file(self, manager, conversation, usage, config):
        path = manager.save_session("test-session", conversation, usage, config)
        assert path.exists()
        assert path.suffix == ".json"

    def test_save_content_structure(self, manager, conversation, usage, config):
        manager.save_session("test-session", conversation, usage, config)
        path = manager.sessions_dir / "test-session.json"
        data = json.loads(path.read_text())

        assert data["name"] == "test-session"
        assert "timestamp" in data
        assert data["turn_count"] == 2  # two user messages
        assert data["message_count"] == 5  # system + 2 user + 2 assistant
        assert isinstance(data["messages"], list)
        assert len(data["messages"]) == 5

        assert data["usage"]["prompt_tokens"] == 1200
        assert data["usage"]["completion_tokens"] == 400
        assert data["usage"]["total_tokens"] == 1600
        assert data["usage"]["turns"] == 4

        assert data["config"]["model"] == "gpt-4o"
        assert data["config"]["effort_level"] == "medium"

    def test_save_overwrites_existing(self, manager, conversation, usage, config):
        manager.save_session("dup", conversation, usage, config)
        conversation.add_user("Extra message")
        manager.save_session("dup", conversation, usage, config)

        data = json.loads((manager.sessions_dir / "dup.json").read_text())
        assert data["message_count"] == 6

    def test_save_with_none_args(self, manager):
        path = manager.save_session("empty")
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["messages"] == []
        assert data["usage"]["prompt_tokens"] == 0

    def test_save_sanitizes_name(self, manager, conversation, usage, config):
        path = manager.save_session("../../etc/passwd", conversation, usage, config)
        # Should NOT escape the sessions directory
        assert manager.sessions_dir in path.parents or path.parent == manager.sessions_dir
        assert ".." not in path.name


# -----------------------------------------------------------------------
# Load
# -----------------------------------------------------------------------


class TestLoadSession:
    def test_load_round_trip(self, manager, conversation, usage, config):
        manager.save_session("rt", conversation, usage, config)
        loaded = manager.load_session("rt")

        assert loaded is not None
        assert loaded["name"] == "rt"
        assert len(loaded["messages"]) == 5
        assert loaded["usage"]["total_tokens"] == 1600

    def test_load_nonexistent_returns_none(self, manager):
        assert manager.load_session("nope") is None

    def test_load_corrupt_json_returns_none(self, manager):
        bad = manager.sessions_dir / "corrupt.json"
        bad.write_text("not json at all {{{", encoding="utf-8")
        assert manager.load_session("corrupt") is None


# -----------------------------------------------------------------------
# List
# -----------------------------------------------------------------------


class TestListSessions:
    def test_list_empty(self, manager):
        assert manager.list_sessions() == []

    def test_list_multiple(self, manager, conversation, usage, config):
        manager.save_session("alpha", conversation, usage, config)
        manager.save_session("beta", conversation, usage, config)
        manager.save_session("gamma", conversation, usage, config)

        sessions = manager.list_sessions()
        assert len(sessions) == 3
        names = [s["name"] for s in sessions]
        assert "alpha" in names
        assert "beta" in names
        assert "gamma" in names

    def test_list_includes_metadata(self, manager, conversation, usage, config):
        manager.save_session("meta", conversation, usage, config)
        sessions = manager.list_sessions()

        assert len(sessions) == 1
        info = sessions[0]
        assert info["name"] == "meta"
        assert "timestamp" in info
        assert info["turn_count"] == 2
        assert info["message_count"] == 5

    def test_list_sorted_newest_first(self, manager, conversation, usage, config):
        manager.save_session("first", conversation, usage, config)
        manager.save_session("second", conversation, usage, config)
        manager.save_session("third", conversation, usage, config)

        sessions = manager.list_sessions()
        timestamps = [s["timestamp"] for s in sessions]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_list_skips_corrupt_files(self, manager, conversation, usage, config):
        manager.save_session("good", conversation, usage, config)
        bad = manager.sessions_dir / "bad.json"
        bad.write_text("not json", encoding="utf-8")

        sessions = manager.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["name"] == "good"


# -----------------------------------------------------------------------
# Fork
# -----------------------------------------------------------------------


class TestForkSession:
    def test_fork_creates_copy(self, manager, conversation, usage, config):
        manager.save_session("original", conversation, usage, config)
        new_path = manager.fork_session("original", "forked")

        assert new_path is not None
        assert new_path.exists()

        original = manager.load_session("original")
        forked = manager.load_session("forked")

        assert forked["name"] == "forked"
        assert len(forked["messages"]) == len(original["messages"])
        assert forked["usage"] == original["usage"]

    def test_fork_updates_timestamp(self, manager, conversation, usage, config):
        manager.save_session("src", conversation, usage, config)
        manager.fork_session("src", "dst")

        src = manager.load_session("src")
        dst = manager.load_session("dst")

        # Forked session should have a different (newer or equal) timestamp
        assert dst["timestamp"] >= src["timestamp"]

    def test_fork_nonexistent_returns_none(self, manager):
        assert manager.fork_session("ghost", "new") is None

    def test_fork_independent_from_source(self, manager, conversation, usage, config):
        """Forked session should be independent — modifying source should not affect fork."""
        manager.save_session("src", conversation, usage, config)
        manager.fork_session("src", "fork")

        # Overwrite source with different content
        conversation.add_user("Extra")
        manager.save_session("src", conversation, usage, config)

        src = manager.load_session("src")
        fork = manager.load_session("fork")
        assert src["message_count"] != fork["message_count"]


# -----------------------------------------------------------------------
# Delete
# -----------------------------------------------------------------------


class TestDeleteSession:
    def test_delete_removes_file(self, manager, conversation, usage, config):
        manager.save_session("doomed", conversation, usage, config)
        assert manager.delete_session("doomed") is True
        assert manager.load_session("doomed") is None

    def test_delete_nonexistent_returns_false(self, manager):
        assert manager.delete_session("nope") is False

    def test_delete_then_list(self, manager, conversation, usage, config):
        manager.save_session("a", conversation, usage, config)
        manager.save_session("b", conversation, usage, config)
        manager.delete_session("a")

        sessions = manager.list_sessions()
        names = [s["name"] for s in sessions]
        assert "a" not in names
        assert "b" in names


# -----------------------------------------------------------------------
# Auto-save
# -----------------------------------------------------------------------


class TestAutoSave:
    def test_auto_save_creates_auto_file(self, manager, conversation, usage, config):
        path = manager.auto_save(conversation, usage, config)
        assert path.exists()
        assert path.name == "_auto.json"

    def test_auto_save_loadable(self, manager, conversation, usage, config):
        manager.auto_save(conversation, usage, config)
        data = manager.load_session("_auto")
        assert data is not None
        assert data["name"] == "_auto"
        assert len(data["messages"]) == 5


# -----------------------------------------------------------------------
# Directory creation
# -----------------------------------------------------------------------


class TestSessionManagerInit:
    def test_creates_directory_if_missing(self, tmp_path):
        new_dir = tmp_path / "deep" / "nested" / "sessions"
        assert not new_dir.exists()

        mgr = SessionManager(new_dir)
        assert new_dir.exists()
        assert mgr.sessions_dir == new_dir

    def test_accepts_string_path(self, tmp_path):
        mgr = SessionManager(str(tmp_path / "str-sessions"))
        assert mgr.sessions_dir.exists()
