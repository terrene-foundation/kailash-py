# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for shadow mode observer: ShadowObserver, ShadowStore, and CLI."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from trustplane.models import (
    ConstraintEnvelope,
    DataAccessConstraints,
    OperationalConstraints,
)
from trustplane.shadow import (
    ShadowObserver,
    ShadowSession,
    ShadowToolCall,
    _classify_category,
    generate_report,
    generate_report_json,
    infer_constraints,
)
from trustplane.shadow_store import ShadowStore


# ---------------------------------------------------------------------------
# ShadowToolCall dataclass
# ---------------------------------------------------------------------------


class TestShadowToolCall:
    def test_to_dict(self):
        call = ShadowToolCall(
            action="Read",
            resource="/src/main.py",
            category="file_read",
            would_be_blocked=False,
            would_be_held=False,
        )
        d = call.to_dict()
        assert d["action"] == "Read"
        assert d["resource"] == "/src/main.py"
        assert d["category"] == "file_read"
        assert d["would_be_blocked"] is False
        assert "timestamp" in d

    def test_from_dict(self):
        data = {
            "action": "Edit",
            "resource": "/src/models.py",
            "category": "file_write",
            "timestamp": "2026-03-15T12:00:00+00:00",
            "would_be_blocked": True,
            "would_be_held": False,
            "reason": "blocked path",
        }
        call = ShadowToolCall.from_dict(data)
        assert call.action == "Edit"
        assert call.resource == "/src/models.py"
        assert call.category == "file_write"
        assert call.would_be_blocked is True
        assert call.reason == "blocked path"

    def test_from_dict_missing_action_raises(self):
        with pytest.raises(ValueError, match="action"):
            ShadowToolCall.from_dict({"resource": "x", "category": "other"})

    def test_from_dict_missing_resource_raises(self):
        with pytest.raises(ValueError, match="resource"):
            ShadowToolCall.from_dict({"action": "x", "category": "other"})

    def test_from_dict_missing_category_raises(self):
        with pytest.raises(ValueError, match="category"):
            ShadowToolCall.from_dict({"action": "x", "resource": "y"})

    def test_roundtrip(self):
        call = ShadowToolCall(
            action="Bash",
            resource="ls -la",
            category="shell_command",
            would_be_blocked=True,
            would_be_held=False,
            reason="Shell commands blocked",
        )
        restored = ShadowToolCall.from_dict(call.to_dict())
        assert restored.action == call.action
        assert restored.resource == call.resource
        assert restored.category == call.category
        assert restored.would_be_blocked == call.would_be_blocked
        assert restored.reason == call.reason


# ---------------------------------------------------------------------------
# ShadowSession dataclass
# ---------------------------------------------------------------------------


class TestShadowSession:
    def test_default_session(self):
        session = ShadowSession()
        assert session.session_id
        assert session.started_at is not None
        assert session.ended_at is None
        assert len(session.tool_calls) == 0

    def test_to_dict(self):
        session = ShadowSession(session_id="test-123")
        d = session.to_dict()
        assert d["session_id"] == "test-123"
        assert d["ended_at"] is None
        assert d["tool_calls"] == []

    def test_from_dict(self):
        data = {
            "session_id": "s-1",
            "started_at": "2026-03-15T10:00:00+00:00",
            "ended_at": "2026-03-15T11:00:00+00:00",
            "tool_calls": [
                {
                    "action": "Read",
                    "resource": "/foo.py",
                    "category": "file_read",
                    "timestamp": "2026-03-15T10:30:00+00:00",
                }
            ],
        }
        session = ShadowSession.from_dict(data)
        assert session.session_id == "s-1"
        assert session.ended_at is not None
        assert len(session.tool_calls) == 1

    def test_from_dict_missing_id_raises(self):
        with pytest.raises(ValueError, match="session_id"):
            ShadowSession.from_dict({"started_at": "2026-01-01T00:00:00+00:00"})

    def test_roundtrip(self):
        session = ShadowSession(session_id="rt-1")
        session.tool_calls.append(
            ShadowToolCall(action="Read", resource="/a.py", category="file_read")
        )
        restored = ShadowSession.from_dict(session.to_dict())
        assert restored.session_id == session.session_id
        assert len(restored.tool_calls) == 1
        assert restored.tool_calls[0].action == "Read"


# ---------------------------------------------------------------------------
# Category classification
# ---------------------------------------------------------------------------


class TestCategoryClassification:
    def test_read_action(self):
        assert _classify_category("Read", "/src/main.py") == "file_read"

    def test_read_file_action(self):
        assert _classify_category("read_file", "/foo.py") == "file_read"

    def test_write_action(self):
        assert _classify_category("Write", "/src/main.py") == "file_write"

    def test_edit_action(self):
        assert _classify_category("Edit", "/src/main.py") == "file_write"

    def test_bash_action(self):
        assert _classify_category("Bash", "ls -la") == "shell_command"

    def test_shell_action(self):
        assert _classify_category("shell", "echo hi") == "shell_command"

    def test_web_fetch_action(self):
        assert _classify_category("WebFetch", "https://example.com") == "web_request"

    def test_web_search_action(self):
        assert _classify_category("WebSearch", "query") == "web_request"

    def test_unknown_action(self):
        assert _classify_category("CustomTool", "data") == "other"

    def test_case_insensitive(self):
        assert _classify_category("BASH", "ls") == "shell_command"
        assert _classify_category("read", "/f.py") == "file_read"

    def test_resource_based_web(self):
        assert (
            _classify_category("unknown", "https://api.example.com/data")
            == "web_request"
        )


# ---------------------------------------------------------------------------
# ShadowObserver
# ---------------------------------------------------------------------------


class TestShadowObserver:
    def test_record_tool_call(self):
        observer = ShadowObserver()
        session = ShadowSession()
        call = observer.record(session, action="Read", resource="/src/main.py")
        assert call.category == "file_read"
        assert len(session.tool_calls) == 1

    def test_record_with_custom_category(self):
        observer = ShadowObserver()
        session = ShadowSession()
        call = observer.record(
            session, action="CustomTool", resource="data", category="special"
        )
        assert call.category == "special"

    def test_blocked_action_detected(self):
        envelope = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=["delete_file"]),
        )
        observer = ShadowObserver(envelope=envelope)
        session = ShadowSession()
        call = observer.record(session, action="delete_file", resource="/important.py")
        assert call.would_be_blocked is True
        assert call.reason is not None

    def test_blocked_path_detected(self):
        envelope = ConstraintEnvelope(
            data_access=DataAccessConstraints(blocked_paths=[".env"]),
        )
        observer = ShadowObserver(envelope=envelope)
        session = ShadowSession()
        call = observer.record(session, action="Read", resource=".env")
        assert call.would_be_blocked is True

    def test_blocked_pattern_detected(self):
        envelope = ConstraintEnvelope(
            data_access=DataAccessConstraints(blocked_patterns=["*.key"]),
        )
        observer = ShadowObserver(envelope=envelope)
        session = ShadowSession()
        call = observer.record(session, action="Read", resource="server.key")
        assert call.would_be_blocked is True

    def test_held_write_outside_allowed_paths(self):
        envelope = ConstraintEnvelope(
            data_access=DataAccessConstraints(write_paths=["src/", "tests/"]),
        )
        observer = ShadowObserver(envelope=envelope)
        session = ShadowSession()
        call = observer.record(session, action="Write", resource="production/deploy.sh")
        assert call.would_be_held is True
        assert "not in allowed write paths" in call.reason

    def test_allowed_action_passes(self):
        envelope = ConstraintEnvelope(
            operational=OperationalConstraints(
                allowed_actions=["read_file"], blocked_actions=[]
            ),
        )
        observer = ShadowObserver(envelope=envelope)
        session = ShadowSession()
        call = observer.record(session, action="Read", resource="/src/main.py")
        assert call.would_be_blocked is False
        assert call.would_be_held is False

    def test_default_template_is_software(self):
        observer = ShadowObserver()
        assert observer.envelope is not None
        # Software template blocks merge_to_main
        assert "merge_to_main" in observer.envelope.operational.blocked_actions

    def test_custom_template(self):
        observer = ShadowObserver(template_name="governance")
        assert "modify_constitution" in observer.envelope.operational.blocked_actions

    def test_unknown_template_falls_back(self):
        observer = ShadowObserver(template_name="nonexistent")
        assert observer.envelope is not None

    def test_multiple_calls_in_session(self):
        observer = ShadowObserver()
        session = ShadowSession()
        observer.record(session, action="Read", resource="/a.py")
        observer.record(session, action="Edit", resource="/b.py")
        observer.record(session, action="Bash", resource="pytest")
        assert len(session.tool_calls) == 3


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


class TestReportGeneration:
    def _make_session_with_calls(self) -> ShadowSession:
        envelope = ConstraintEnvelope(
            operational=OperationalConstraints(
                blocked_actions=["merge_to_main"],
            ),
            data_access=DataAccessConstraints(
                blocked_paths=[".env"],
                write_paths=["src/"],
            ),
        )
        observer = ShadowObserver(envelope=envelope)
        session = ShadowSession(session_id="test-report")
        observer.record(session, action="Read", resource="src/main.py")
        observer.record(session, action="Edit", resource="src/models.py")
        observer.record(session, action="merge_to_main", resource="main")
        observer.record(session, action="Read", resource=".env")
        observer.record(session, action="Bash", resource="pytest")
        session.ended_at = session.started_at + timedelta(hours=1)
        return session

    def test_markdown_report(self):
        session = self._make_session_with_calls()
        report = generate_report(session)
        assert "# Shadow Mode Report" in report
        assert "test-report" in report
        assert "Total tool calls" in report
        assert "BLOCKED" in report

    def test_markdown_report_contains_categories(self):
        session = self._make_session_with_calls()
        report = generate_report(session)
        assert "file_read" in report
        assert "file_write" in report
        assert "shell_command" in report

    def test_markdown_report_shows_flagged(self):
        session = self._make_session_with_calls()
        report = generate_report(session)
        assert "Flagged Actions" in report
        assert "merge_to_main" in report

    def test_json_report(self):
        session = self._make_session_with_calls()
        report = generate_report_json(session)
        assert report["session_id"] == "test-report"
        assert report["summary"]["total_calls"] == 5
        assert report["summary"]["blocked"] >= 2
        assert len(report["flagged_actions"]) >= 2
        assert len(report["tool_calls"]) == 5

    def test_json_report_serializable(self):
        session = self._make_session_with_calls()
        report = generate_report_json(session)
        # Must be JSON-serializable
        json_str = json.dumps(report, default=str)
        parsed = json.loads(json_str)
        assert parsed["session_id"] == "test-report"

    def test_empty_session_report(self):
        session = ShadowSession(session_id="empty")
        report = generate_report(session)
        assert "Total tool calls" in report
        assert "0" in report

    def test_empty_session_json(self):
        session = ShadowSession(session_id="empty")
        report = generate_report_json(session)
        assert report["summary"]["total_calls"] == 0
        assert report["summary"]["block_rate"] == 0.0


# ---------------------------------------------------------------------------
# Constraint inference
# ---------------------------------------------------------------------------


class TestConstraintInference:
    def test_infer_from_observed_actions(self):
        session = ShadowSession()
        session.tool_calls = [
            ShadowToolCall(action="Read", resource="src/main.py", category="file_read"),
            ShadowToolCall(
                action="Edit", resource="src/models.py", category="file_write"
            ),
            ShadowToolCall(action="Bash", resource="pytest", category="shell_command"),
        ]
        envelope = infer_constraints(session)
        assert "Read" in envelope.operational.allowed_actions
        assert "Edit" in envelope.operational.allowed_actions
        assert "Bash" in envelope.operational.allowed_actions

    def test_infer_read_paths(self):
        session = ShadowSession()
        session.tool_calls = [
            ShadowToolCall(action="Read", resource="src/main.py", category="file_read"),
            ShadowToolCall(
                action="Read", resource="tests/test_foo.py", category="file_read"
            ),
        ]
        envelope = infer_constraints(session)
        # DataAccessConstraints normalizes paths, stripping trailing slashes
        assert "src" in envelope.data_access.read_paths
        assert "tests" in envelope.data_access.read_paths

    def test_infer_write_paths(self):
        session = ShadowSession()
        session.tool_calls = [
            ShadowToolCall(
                action="Write", resource="src/new_module.py", category="file_write"
            ),
        ]
        envelope = infer_constraints(session)
        assert "src" in envelope.data_access.write_paths

    def test_infer_includes_default_blocked_patterns(self):
        session = ShadowSession()
        session.tool_calls = [
            ShadowToolCall(action="Read", resource="foo.py", category="file_read"),
        ]
        envelope = infer_constraints(session)
        assert "*.key" in envelope.data_access.blocked_patterns
        assert "*.env" in envelope.data_access.blocked_patterns

    def test_infer_signed_by_shadow(self):
        session = ShadowSession()
        envelope = infer_constraints(session)
        assert envelope.signed_by == "shadow-inferred"

    def test_infer_empty_session(self):
        session = ShadowSession()
        envelope = infer_constraints(session)
        assert envelope.operational.allowed_actions == []
        assert envelope.data_access.read_paths == []
        assert envelope.data_access.write_paths == []


# ---------------------------------------------------------------------------
# ShadowStore persistence
# ---------------------------------------------------------------------------


class TestShadowStore:
    @pytest.fixture
    def store(self, tmp_path):
        db_path = tmp_path / "shadow.db"
        s = ShadowStore(db_path)
        s.initialize()
        yield s
        s.close()

    def test_start_session(self, store):
        sid = store.start_session()
        assert sid is not None
        assert len(sid) > 0

    def test_get_session(self, store):
        sid = store.start_session()
        session = store.get_session(sid)
        assert session.session_id == sid
        assert session.started_at is not None
        assert session.ended_at is None
        assert len(session.tool_calls) == 0

    def test_get_session_not_found(self, store):
        with pytest.raises(KeyError, match="not found"):
            store.get_session("nonexistent-id")

    def test_record_call(self, store):
        sid = store.start_session()
        store.record_call(sid, "Read", "/src/main.py", "file_read")
        session = store.get_session(sid)
        assert len(session.tool_calls) == 1
        call = session.tool_calls[0]
        assert call.action == "Read"
        assert call.resource == "/src/main.py"
        assert call.category == "file_read"

    def test_record_call_with_blocking(self, store):
        sid = store.start_session()
        store.record_call(
            sid,
            "delete_file",
            "/important.py",
            "file_write",
            would_be_blocked=True,
            reason="Action blocked",
        )
        session = store.get_session(sid)
        assert session.tool_calls[0].would_be_blocked is True
        assert session.tool_calls[0].reason == "Action blocked"

    def test_record_call_with_hold(self, store):
        sid = store.start_session()
        store.record_call(
            sid,
            "Write",
            "/outside/path.py",
            "file_write",
            would_be_held=True,
            reason="Not in allowed paths",
        )
        session = store.get_session(sid)
        assert session.tool_calls[0].would_be_held is True

    def test_end_session(self, store):
        sid = store.start_session()
        store.end_session(sid)
        session = store.get_session(sid)
        assert session.ended_at is not None

    def test_list_sessions(self, store):
        store.start_session()
        store.start_session()
        store.start_session()
        sessions = store.list_sessions()
        assert len(sessions) == 3

    def test_list_sessions_limit(self, store):
        for _ in range(5):
            store.start_session()
        sessions = store.list_sessions(limit=2)
        assert len(sessions) == 2

    def test_list_sessions_since(self, store):
        store.start_session()
        since = datetime.now(timezone.utc) + timedelta(hours=1)
        sessions = store.list_sessions(since=since)
        assert len(sessions) == 0

    def test_list_sessions_since_includes_recent(self, store):
        store.start_session()
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        sessions = store.list_sessions(since=since)
        assert len(sessions) == 1

    def test_multiple_calls_order_preserved(self, store):
        sid = store.start_session()
        store.record_call(sid, "Read", "/a.py", "file_read")
        store.record_call(sid, "Edit", "/b.py", "file_write")
        store.record_call(sid, "Bash", "pytest", "shell_command")
        session = store.get_session(sid)
        assert len(session.tool_calls) == 3
        assert session.tool_calls[0].action == "Read"
        assert session.tool_calls[1].action == "Edit"
        assert session.tool_calls[2].action == "Bash"

    def test_initialize_idempotent(self, tmp_path):
        db_path = tmp_path / "shadow.db"
        store = ShadowStore(db_path)
        store.initialize()
        sid = store.start_session()
        store.record_call(sid, "Read", "/a.py", "file_read")
        # Re-initialize should not lose data
        store.initialize()
        session = store.get_session(sid)
        assert len(session.tool_calls) == 1
        store.close()

    def test_close_idempotent(self, tmp_path):
        db_path = tmp_path / "shadow.db"
        store = ShadowStore(db_path)
        store.initialize()
        store.close()
        store.close()  # Should not raise

    # -----------------------------------------------------------------------
    # validate_id enforcement (TODO-57)
    # -----------------------------------------------------------------------

    def test_get_session_rejects_path_traversal(self, store):
        """get_session must reject session_id with path traversal characters."""
        with pytest.raises(ValueError, match="unsafe characters"):
            store.get_session("../../etc/shadow")

    def test_get_session_rejects_slashes(self, store):
        """get_session must reject session_id containing slashes."""
        with pytest.raises(ValueError, match="unsafe characters"):
            store.get_session("abc/def")

    def test_get_session_rejects_dots(self, store):
        """get_session must reject session_id with dot sequences."""
        with pytest.raises(ValueError, match="unsafe characters"):
            store.get_session("..hidden")

    def test_get_session_accepts_valid_uuid(self, store):
        """get_session must accept a valid UUID-format session_id.

        Note: the session won't exist, but validation should pass and
        the KeyError for missing session should be raised (not ValueError).
        """
        with pytest.raises(KeyError, match="not found"):
            store.get_session("550e8400-e29b-41d4-a716-446655440000")

    def test_record_call_rejects_path_traversal(self, store):
        """record_call must reject session_id with path traversal."""
        with pytest.raises(ValueError, match="unsafe characters"):
            store.record_call("../../etc/passwd", "Read", "/src/main.py", "file_read")

    def test_record_call_rejects_spaces(self, store):
        """record_call must reject session_id with spaces."""
        with pytest.raises(ValueError, match="unsafe characters"):
            store.record_call(
                "session id with spaces", "Read", "/src/main.py", "file_read"
            )

    def test_record_call_accepts_valid_uuid(self, store):
        """record_call must accept a valid UUID session_id (validation passes)."""
        sid = store.start_session()
        # Should not raise ValueError — the session_id is a valid UUID
        store.record_call(sid, "Read", "/src/main.py", "file_read")
        session = store.get_session(sid)
        assert len(session.tool_calls) == 1

    def test_end_session_rejects_path_traversal(self, store):
        """end_session must reject session_id with path traversal."""
        with pytest.raises(ValueError, match="unsafe characters"):
            store.end_session("../../../etc/passwd")

    def test_end_session_rejects_null_bytes(self, store):
        """end_session must reject session_id with null bytes."""
        with pytest.raises(ValueError, match="unsafe characters"):
            store.end_session("session\x00id")

    def test_end_session_accepts_valid_uuid(self, store):
        """end_session must accept a valid UUID session_id."""
        sid = store.start_session()
        # Should not raise ValueError
        store.end_session(sid)
        session = store.get_session(sid)
        assert session.ended_at is not None

    def test_valid_uuid_passes_validation_roundtrip(self, store):
        """Full roundtrip: start, record, end, get — all with validated IDs."""
        sid = store.start_session()
        store.record_call(sid, "Read", "/a.py", "file_read")
        store.record_call(sid, "Edit", "/b.py", "file_write")
        store.end_session(sid)
        session = store.get_session(sid)
        assert session.session_id == sid
        assert len(session.tool_calls) == 2
        assert session.ended_at is not None


# ---------------------------------------------------------------------------
# Integration: Observer + Store
# ---------------------------------------------------------------------------


class TestShadowIntegration:
    def test_observer_record_then_persist(self, tmp_path):
        """Observer records calls, store persists them."""
        observer = ShadowObserver()
        session = ShadowSession()
        observer.record(session, action="Read", resource="src/main.py")
        observer.record(session, action="Edit", resource="src/models.py")
        observer.record(session, action="Bash", resource="pytest")

        # Persist to store
        store = ShadowStore(tmp_path / "shadow.db")
        store.initialize()
        sid = store.start_session()
        for call in session.tool_calls:
            store.record_call(
                sid,
                call.action,
                call.resource,
                call.category,
                would_be_blocked=call.would_be_blocked,
                would_be_held=call.would_be_held,
                reason=call.reason,
            )
        store.end_session(sid)

        # Load and verify
        loaded = store.get_session(sid)
        assert len(loaded.tool_calls) == 3
        assert loaded.ended_at is not None
        store.close()

    def test_generate_report_from_stored_session(self, tmp_path):
        """Generate report from a persisted session."""
        store = ShadowStore(tmp_path / "shadow.db")
        store.initialize()
        sid = store.start_session()
        store.record_call(sid, "Read", "/src/main.py", "file_read")
        store.record_call(
            sid,
            "delete_file",
            "/critical.py",
            "file_write",
            would_be_blocked=True,
            reason="Action blocked",
        )
        store.end_session(sid)

        session = store.get_session(sid)
        report = generate_report(session)
        assert "Shadow Mode Report" in report
        assert "BLOCKED" in report
        store.close()

    def test_infer_constraints_from_stored_session(self, tmp_path):
        """Infer constraints from a persisted session."""
        store = ShadowStore(tmp_path / "shadow.db")
        store.initialize()
        sid = store.start_session()
        store.record_call(sid, "Read", "src/main.py", "file_read")
        store.record_call(sid, "Write", "src/new.py", "file_write")
        store.end_session(sid)

        session = store.get_session(sid)
        envelope = infer_constraints(session)
        assert "Read" in envelope.operational.allowed_actions
        assert "Write" in envelope.operational.allowed_actions
        assert "src" in envelope.data_access.read_paths
        assert "src" in envelope.data_access.write_paths
        store.close()

    def test_shadow_store_busy_timeout_pragma(self, tmp_path):
        """ShadowStore must set PRAGMA busy_timeout=5000 on its connection."""
        store = ShadowStore(tmp_path / "shadow.db")
        store.initialize()
        conn = store._get_connection()
        result = conn.execute("PRAGMA busy_timeout").fetchone()
        assert result[0] == 5000, f"Expected busy_timeout=5000, got {result[0]}"
        store.close()

    def test_shadow_store_wal_mode(self, tmp_path):
        """ShadowStore must use WAL journal mode."""
        store = ShadowStore(tmp_path / "shadow.db")
        store.initialize()
        conn = store._get_connection()
        result = conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == "wal", f"Expected journal_mode=wal, got {result[0]}"
        store.close()


# ---------------------------------------------------------------------------
# ShadowStore.stats()
# ---------------------------------------------------------------------------


class TestShadowStoreStats:
    @pytest.fixture
    def store(self, tmp_path):
        db_path = tmp_path / "shadow.db"
        s = ShadowStore(db_path)
        s.initialize()
        yield s
        s.close()

    def test_stats_empty_store(self, store):
        info = store.stats()
        assert info["session_count"] == 0
        assert info["tool_call_count"] == 0
        assert info["oldest_session"] is None
        assert info["newest_session"] is None
        assert info["disk_usage_bytes"] > 0  # SQLite file exists

    def test_stats_with_sessions(self, store):
        sid1 = store.start_session()
        store.record_call(sid1, "Read", "/a.py", "file_read")
        store.record_call(sid1, "Edit", "/b.py", "file_write")
        sid2 = store.start_session()
        store.record_call(sid2, "Bash", "ls", "shell_command")

        info = store.stats()
        assert info["session_count"] == 2
        assert info["tool_call_count"] == 3
        assert info["oldest_session"] is not None
        assert info["newest_session"] is not None
        assert info["disk_usage_bytes"] > 0

    def test_stats_date_range(self, store):
        store.start_session()
        store.start_session()
        info = store.stats()
        # oldest <= newest
        assert info["oldest_session"] <= info["newest_session"]


# ---------------------------------------------------------------------------
# ShadowStore.cleanup()
# ---------------------------------------------------------------------------


class TestShadowStoreCleanup:
    @pytest.fixture
    def store(self, tmp_path):
        db_path = tmp_path / "shadow.db"
        s = ShadowStore(db_path)
        s.initialize()
        yield s
        s.close()

    def test_cleanup_no_sessions(self, store):
        removed = store.cleanup()
        assert removed == 0

    def test_cleanup_invalid_max_age(self, store):
        with pytest.raises(ValueError, match="max_age_days"):
            store.cleanup(max_age_days=0)

    def test_cleanup_invalid_max_sessions(self, store):
        with pytest.raises(ValueError, match="max_sessions"):
            store.cleanup(max_sessions=0)

    def test_cleanup_invalid_max_size(self, store):
        with pytest.raises(ValueError, match="max_size_mb"):
            store.cleanup(max_size_mb=0)

    def test_cleanup_by_max_sessions(self, store):
        # Create 5 sessions
        for _ in range(5):
            sid = store.start_session()
            store.record_call(sid, "Read", "/a.py", "file_read")

        removed = store.cleanup(max_sessions=3)
        assert removed == 2
        info = store.stats()
        assert info["session_count"] == 3

    def test_cleanup_by_max_sessions_removes_oldest(self, store):
        """Cleanup must remove the oldest sessions first."""
        sids = []
        for _ in range(5):
            sids.append(store.start_session())

        store.cleanup(max_sessions=2)
        info = store.stats()
        assert info["session_count"] == 2

        # The two newest sessions should survive
        conn = store._get_connection()
        remaining = [
            row[0]
            for row in conn.execute(
                "SELECT session_id FROM shadow_sessions ORDER BY started_at DESC"
            ).fetchall()
        ]
        # The last two created should remain (newest)
        assert sids[-1] in remaining
        assert sids[-2] in remaining

    def test_cleanup_by_age(self, store):
        """Sessions older than max_age_days should be removed."""
        conn = store._get_connection()
        # Insert a session with an old started_at timestamp
        old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        conn.execute(
            "INSERT INTO shadow_sessions (session_id, started_at) VALUES (?, ?)",
            ("old-session", old_ts),
        )
        conn.commit()

        # Insert a recent session via normal API
        store.start_session()

        removed = store.cleanup(max_age_days=90)
        assert removed == 1
        info = store.stats()
        assert info["session_count"] == 1

    def test_cleanup_age_does_not_remove_recent(self, store):
        """Recent sessions within max_age_days should not be removed."""
        store.start_session()
        store.start_session()
        removed = store.cleanup(max_age_days=1)
        assert removed == 0
        assert store.stats()["session_count"] == 2

    def test_cleanup_atomic_deletes_tool_calls(self, store):
        """When a session is cleaned up, its tool calls must also be removed."""
        conn = store._get_connection()
        old_ts = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        conn.execute(
            "INSERT INTO shadow_sessions (session_id, started_at) VALUES (?, ?)",
            ("old-sess", old_ts),
        )
        conn.execute(
            "INSERT INTO shadow_tool_calls "
            "(session_id, action, resource, category, timestamp, "
            "would_be_blocked, would_be_held) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("old-sess", "Read", "/x.py", "file_read", old_ts, 0, 0),
        )
        conn.commit()

        removed = store.cleanup(max_age_days=90)
        assert removed == 1

        # Verify tool calls are also gone
        orphan_calls = conn.execute(
            "SELECT COUNT(*) FROM shadow_tool_calls WHERE session_id = ?",
            ("old-sess",),
        ).fetchone()[0]
        assert orphan_calls == 0

    def test_cleanup_returns_total_removed(self, store):
        """cleanup() returns the total count of sessions removed across all phases."""
        conn = store._get_connection()
        # 3 old sessions + 5 recent sessions = 8 total
        for i in range(3):
            old_ts = (datetime.now(timezone.utc) - timedelta(days=200 + i)).isoformat()
            conn.execute(
                "INSERT INTO shadow_sessions (session_id, started_at) VALUES (?, ?)",
                (f"old-{i}", old_ts),
            )
        conn.commit()
        for _ in range(5):
            store.start_session()

        # max_age=90 removes 3, then max_sessions=3 removes 2 more
        removed = store.cleanup(max_age_days=90, max_sessions=3)
        assert removed == 5
        assert store.stats()["session_count"] == 3

    def test_cleanup_combined_policies(self, store):
        """All three policies are applied in order."""
        for _ in range(10):
            sid = store.start_session()
            store.record_call(sid, "Read", "/a.py", "file_read")

        # With max_sessions=5, should remove 5
        removed = store.cleanup(max_sessions=5)
        assert removed == 5
        assert store.stats()["session_count"] == 5


# ---------------------------------------------------------------------------
# CLI: shadow-manage cleanup / stats
# ---------------------------------------------------------------------------


class TestShadowManageCLI:
    """Tests for the 'attest shadow-manage' CLI group."""

    @pytest.fixture
    def cli_runner(self):
        from click.testing import CliRunner

        from trustplane.cli import main

        runner = CliRunner()
        return runner, main

    def test_shadow_stats_no_data(self, cli_runner, tmp_path):
        runner, main_cmd = cli_runner
        result = runner.invoke(
            main_cmd,
            ["--dir", str(tmp_path), "shadow-manage", "stats"],
        )
        assert result.exit_code == 0
        assert "No shadow data found" in result.output

    def test_shadow_stats_json_no_data(self, cli_runner, tmp_path):
        runner, main_cmd = cli_runner
        result = runner.invoke(
            main_cmd,
            ["--dir", str(tmp_path), "shadow-manage", "stats", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["session_count"] == 0

    def test_shadow_stats_with_data(self, cli_runner, tmp_path):
        # Seed some shadow data
        store = ShadowStore(tmp_path / "shadow.db")
        store.initialize()
        sid = store.start_session()
        store.record_call(sid, "Read", "/a.py", "file_read")
        store.close()

        runner, main_cmd = cli_runner
        result = runner.invoke(
            main_cmd,
            ["--dir", str(tmp_path), "shadow-manage", "stats"],
        )
        assert result.exit_code == 0
        assert "Sessions:    1" in result.output
        assert "Tool calls:  1" in result.output
        assert "Disk usage:" in result.output

    def test_shadow_stats_json_with_data(self, cli_runner, tmp_path):
        store = ShadowStore(tmp_path / "shadow.db")
        store.initialize()
        sid = store.start_session()
        store.record_call(sid, "Read", "/a.py", "file_read")
        store.close()

        runner, main_cmd = cli_runner
        result = runner.invoke(
            main_cmd,
            ["--dir", str(tmp_path), "shadow-manage", "stats", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["session_count"] == 1
        assert data["tool_call_count"] == 1

    def test_shadow_cleanup_no_data(self, cli_runner, tmp_path):
        runner, main_cmd = cli_runner
        result = runner.invoke(
            main_cmd,
            ["--dir", str(tmp_path), "shadow-manage", "cleanup"],
        )
        assert result.exit_code == 0
        assert "No shadow data found" in result.output

    def test_shadow_cleanup_nothing_to_remove(self, cli_runner, tmp_path):
        store = ShadowStore(tmp_path / "shadow.db")
        store.initialize()
        store.start_session()
        store.close()

        runner, main_cmd = cli_runner
        result = runner.invoke(
            main_cmd,
            ["--dir", str(tmp_path), "shadow-manage", "cleanup"],
        )
        assert result.exit_code == 0
        assert "No sessions needed cleanup" in result.output

    def test_shadow_cleanup_removes_sessions(self, cli_runner, tmp_path):
        store = ShadowStore(tmp_path / "shadow.db")
        store.initialize()
        for _ in range(5):
            sid = store.start_session()
            store.record_call(sid, "Read", "/a.py", "file_read")
        store.close()

        runner, main_cmd = cli_runner
        result = runner.invoke(
            main_cmd,
            [
                "--dir",
                str(tmp_path),
                "shadow-manage",
                "cleanup",
                "--max-sessions",
                "2",
            ],
        )
        assert result.exit_code == 0
        assert "Cleaned up 3 session(s)" in result.output

    def test_shadow_cleanup_with_max_age(self, cli_runner, tmp_path):
        import sqlite3

        # Seed an old session directly in the DB
        store = ShadowStore(tmp_path / "shadow.db")
        store.initialize()
        conn = store._get_connection()
        old_ts = (datetime.now(timezone.utc) - timedelta(days=50)).isoformat()
        conn.execute(
            "INSERT INTO shadow_sessions (session_id, started_at) VALUES (?, ?)",
            ("old-cli-test", old_ts),
        )
        conn.commit()
        # Also add a recent one
        store.start_session()
        store.close()

        runner, main_cmd = cli_runner
        result = runner.invoke(
            main_cmd,
            [
                "--dir",
                str(tmp_path),
                "shadow-manage",
                "cleanup",
                "--max-age",
                "30",
            ],
        )
        assert result.exit_code == 0
        assert "Cleaned up 1 session(s)" in result.output
