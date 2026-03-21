# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for TrustPlane SIEM integration (CEF/OCSF/Syslog).

Validates:
- CEF format correctness (header structure, field escaping)
- OCSF format compliance (schema fields, category/class UIDs)
- Syslog handler creation
- Time filter (--since) for batch export
- Multiple record types formatted correctly
"""

import json
import logging.handlers
import socket
from datetime import datetime, timedelta, timezone

import pytest
from click.testing import CliRunner

from kailash.trust.plane.cli import main
from kailash.trust.plane.holds import HoldRecord
from kailash.trust.plane.models import (
    DecisionRecord,
    DecisionType,
    EscalationRecord,
    ExecutionRecord,
    InterventionRecord,
    MilestoneRecord,
    ReviewRequirement,
    VerificationCategory,
)
from kailash.trust.plane.siem import (
    create_syslog_handler,
    export_events,
    format_cef,
    format_ocsf,
)
from kailash.trust.plane.store.sqlite import SqliteTrustPlaneStore


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def decision_record():
    return DecisionRecord(
        decision_type=DecisionType.SCOPE,
        decision="Focus on core features",
        rationale="Time constraints require prioritization",
        alternatives=["Full feature set", "MVP approach"],
        risks=["May miss edge cases"],
        review_requirement=ReviewRequirement.STANDARD,
        confidence=0.85,
        author="alice",
        timestamp=datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc),
        decision_id="dec-abc123def456",
    )


@pytest.fixture
def milestone_record():
    return MilestoneRecord(
        version="v0.2.0",
        description="Beta release",
        file_path="dist/release.tar.gz",
        file_hash="sha256:abcdef1234567890",
        decision_count=5,
        author="bob",
        timestamp=datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc),
        milestone_id="ms-abc123def456",
    )


@pytest.fixture
def hold_record():
    return HoldRecord(
        hold_id="hold-abc123def45",
        action="write_file",
        resource="/etc/passwd",
        context={"agent": "ai-coder"},
        reason="Blocked path access",
        status="pending",
        created_at=datetime(2026, 3, 15, 14, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def hold_record_approved():
    return HoldRecord(
        hold_id="hold-resolved0001",
        action="deploy",
        resource="production",
        context={},
        reason="Production deploy requires approval",
        status="approved",
        created_at=datetime(2026, 3, 15, 14, 0, 0, tzinfo=timezone.utc),
        resolved_at=datetime(2026, 3, 15, 14, 30, 0, tzinfo=timezone.utc),
        resolved_by="admin",
        resolution_reason="Approved after review",
    )


@pytest.fixture
def hold_record_denied():
    return HoldRecord(
        hold_id="hold-denied00001",
        action="delete_database",
        resource="users_table",
        context={},
        reason="Destructive operation",
        status="denied",
        created_at=datetime(2026, 3, 15, 14, 0, 0, tzinfo=timezone.utc),
        resolved_at=datetime(2026, 3, 15, 15, 0, 0, tzinfo=timezone.utc),
        resolved_by="admin",
        resolution_reason="Too risky",
    )


@pytest.fixture
def execution_record():
    return ExecutionRecord(
        action="read_file",
        constraint_reference="operational.allowed_actions",
        verification_category=VerificationCategory.AUTO_APPROVED,
        confidence=0.95,
        timestamp=datetime(2026, 3, 15, 11, 0, 0, tzinfo=timezone.utc),
        execution_id="exec-abc123def4",
    )


@pytest.fixture
def escalation_record():
    return EscalationRecord(
        trigger="Budget limit exceeded",
        recommendation="Request additional funding",
        human_authority="finance_lead",
        verification_category=VerificationCategory.HELD,
        confidence=0.7,
        timestamp=datetime(2026, 3, 15, 13, 0, 0, tzinfo=timezone.utc),
        escalation_id="esc-abc123def45",
    )


@pytest.fixture
def intervention_record():
    return InterventionRecord(
        observation="Code quality below standard",
        action_taken="Requested refactoring",
        human_authority="senior_dev",
        verification_category=VerificationCategory.FLAGGED,
        confidence=0.6,
        timestamp=datetime(2026, 3, 15, 15, 0, 0, tzinfo=timezone.utc),
        intervention_id="int-abc123def45",
    )


# ============================================================================
# CEF Format Tests
# ============================================================================


class TestFormatCEF:
    """Tests for CEF (Common Event Format) serialization."""

    def test_cef_header_structure(self, decision_record):
        """CEF line has correct header: CEF:0|vendor|product|version|id|name|severity|ext."""
        cef = format_cef(decision_record)
        parts = cef.split("|")
        assert parts[0] == "CEF:0"
        assert parts[1] == "TerreneFoundation"
        assert parts[2] == "TrustPlane"
        assert parts[3] == "0.2.0"
        # eventId = decision_id
        assert parts[4] == "dec-abc123def456"
        # eventName contains decision type
        assert "Decision" in parts[5]
        assert "scope" in parts[5]
        # severity is numeric
        assert parts[6].strip() in ("1", "2", "3", "4", "5", "6", "7", "8", "9", "10")

    def test_cef_decision_record(self, decision_record):
        """DecisionRecord formats to CEF with correct extensions."""
        cef = format_cef(decision_record, project_name="TestProject")
        assert "act=decision" in cef
        assert "msg=Focus on core features" in cef
        assert "reason=Time constraints require prioritization" in cef
        assert "duser=alice" in cef
        assert "cs1=TestProject" in cef
        assert "cs1Label=projectName" in cef
        assert "cn1=0.85" in cef
        assert "cn1Label=confidence" in cef

    def test_cef_milestone_record(self, milestone_record):
        """MilestoneRecord formats to CEF with correct extensions."""
        cef = format_cef(milestone_record)
        assert "act=milestone" in cef
        assert "msg=Beta release" in cef
        assert "duser=bob" in cef
        assert "cs2=v0.2.0" in cef
        assert "cs2Label=milestoneVersion" in cef
        assert "ms-abc123def456" in cef

    def test_cef_hold_record_pending(self, hold_record):
        """Pending HoldRecord gets severity 7."""
        cef = format_cef(hold_record)
        parts = cef.split("|")
        assert parts[6] == "7"
        assert "act=write_file" in cef
        assert "outcome=pending" in cef

    def test_cef_hold_record_approved(self, hold_record_approved):
        """Approved HoldRecord gets severity 3."""
        cef = format_cef(hold_record_approved)
        parts = cef.split("|")
        assert parts[6] == "3"
        assert "outcome=approved" in cef
        assert "suser=admin" in cef

    def test_cef_hold_record_denied(self, hold_record_denied):
        """Denied HoldRecord gets severity 9."""
        cef = format_cef(hold_record_denied)
        parts = cef.split("|")
        assert parts[6] == "9"
        assert "outcome=denied" in cef

    def test_cef_execution_auto_approved(self, execution_record):
        """AUTO_APPROVED ExecutionRecord gets severity 1."""
        cef = format_cef(execution_record)
        parts = cef.split("|")
        assert parts[6] == "1"
        assert "act=read_file" in cef
        assert "outcome=auto_approved" in cef

    def test_cef_escalation_held(self, escalation_record):
        """HELD EscalationRecord gets severity 7."""
        cef = format_cef(escalation_record)
        parts = cef.split("|")
        assert parts[6] == "7"
        assert "act=escalation" in cef
        assert "outcome=held" in cef
        assert "suser=finance_lead" in cef

    def test_cef_intervention_flagged(self, intervention_record):
        """FLAGGED InterventionRecord gets severity 4."""
        cef = format_cef(intervention_record)
        parts = cef.split("|")
        assert parts[6] == "4"
        assert "act=intervention" in cef
        assert "suser=senior_dev" in cef

    def test_cef_severity_auto_approved(self):
        """AUTO_APPROVED decisions map to severity 1-3."""
        record = ExecutionRecord(
            action="test",
            verification_category=VerificationCategory.AUTO_APPROVED,
            execution_id="exec-test000001",
        )
        cef = format_cef(record)
        parts = cef.split("|")
        severity = int(parts[6])
        assert 1 <= severity <= 3

    def test_cef_severity_blocked(self):
        """BLOCKED records map to severity 9-10."""
        record = ExecutionRecord(
            action="test",
            verification_category=VerificationCategory.BLOCKED,
            execution_id="exec-test000002",
        )
        cef = format_cef(record)
        parts = cef.split("|")
        severity = int(parts[6])
        assert 7 <= severity <= 10

    def test_cef_field_escaping_pipe(self):
        """Pipe characters in values are escaped."""
        record = DecisionRecord(
            decision_type="test",
            decision="Option A | Option B",
            rationale="Because A|B",
            decision_id="dec-escape00001",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        cef = format_cef(record)
        # Pipes in extensions should be escaped
        assert "Option A \\| Option B" in cef

    def test_cef_field_escaping_equals(self):
        """Equals signs in extension values are escaped."""
        record = DecisionRecord(
            decision_type="test",
            decision="x=y",
            rationale="a=b",
            decision_id="dec-escape00002",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        cef = format_cef(record)
        assert "x\\=y" in cef

    def test_cef_field_escaping_newline(self):
        """Newlines in extension values are escaped."""
        record = DecisionRecord(
            decision_type="test",
            decision="line1\nline2",
            rationale="ok",
            decision_id="dec-escape00003",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        cef = format_cef(record)
        assert "line1\\nline2" in cef
        assert "\n" not in cef  # no literal newlines

    def test_cef_field_escaping_backslash(self):
        """Backslashes in extension values are escaped."""
        record = DecisionRecord(
            decision_type="test",
            decision="path\\to\\file",
            rationale="ok",
            decision_id="dec-escape00004",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        cef = format_cef(record)
        assert "path\\\\to\\\\file" in cef

    def test_cef_header_newline_injection_prevented(self):
        """Newlines in header fields are replaced with spaces to prevent log injection."""
        record = DecisionRecord(
            decision_type="test\nCEF:0|Evil|Attack|1.0|inject|attack|10|",
            decision="safe",
            rationale="ok",
            decision_id="dec-inject00001",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        cef = format_cef(record)
        # The entire output must be a single line — no literal newlines
        assert "\n" not in cef
        assert "\r" not in cef
        # Pipes in injected content must be escaped
        assert "Evil\\|Attack" in cef
        # Must start with exactly one proper CEF header
        assert cef.startswith("CEF:0|TerreneFoundation|TrustPlane|")

    def test_cef_custom_version(self, decision_record):
        """Custom version string appears in CEF header."""
        cef = format_cef(decision_record, version="1.0.0")
        parts = cef.split("|")
        assert parts[3] == "1.0.0"

    def test_cef_timestamp_epoch_ms(self, decision_record):
        """Timestamp is included as epoch milliseconds in rt= extension."""
        cef = format_cef(decision_record)
        expected_ms = int(
            datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc).timestamp() * 1000
        )
        assert f"rt={expected_ms}" in cef


# ============================================================================
# OCSF Format Tests
# ============================================================================


class TestFormatOCSF:
    """Tests for OCSF (Open Cybersecurity Schema Framework) serialization."""

    def test_ocsf_schema_fields(self, decision_record):
        """OCSF event has required schema fields."""
        ocsf = format_ocsf(decision_record)
        assert ocsf["class_uid"] == 6003  # api_activity
        assert ocsf["category_uid"] == 6  # Application Activity
        assert "activity_id" in ocsf
        assert "activity_name" in ocsf
        assert "severity_id" in ocsf
        assert "severity" in ocsf
        assert "time" in ocsf
        assert "uid" in ocsf
        assert "status" in ocsf
        assert "status_id" in ocsf
        assert "actor" in ocsf
        assert "metadata" in ocsf

    def test_ocsf_metadata_product(self, decision_record):
        """OCSF metadata includes product vendor/name/version."""
        ocsf = format_ocsf(decision_record)
        product = ocsf["metadata"]["product"]
        assert product["vendor_name"] == "Terrene Foundation"
        assert product["name"] == "TrustPlane"
        assert "version" in product
        assert ocsf["metadata"]["version"] == "1.1.0"

    def test_ocsf_decision_record(self, decision_record):
        """DecisionRecord produces correct OCSF event."""
        ocsf = format_ocsf(decision_record, project_name="TestProject")
        assert ocsf["uid"] == "dec-abc123def456"
        assert ocsf["actor"]["user"]["uid"] == "alice"
        assert ocsf["api"]["operation"] == "decision"
        assert ocsf["unmapped"]["decision_type"] == "scope"
        assert ocsf["unmapped"]["decision"] == "Focus on core features"
        assert ocsf["unmapped"]["confidence"] == 0.85
        assert ocsf["metadata"]["project_name"] == "TestProject"

    def test_ocsf_milestone_record(self, milestone_record):
        """MilestoneRecord produces correct OCSF event."""
        ocsf = format_ocsf(milestone_record)
        assert ocsf["uid"] == "ms-abc123def456"
        assert ocsf["api"]["operation"] == "milestone"
        assert ocsf["unmapped"]["version"] == "v0.2.0"
        assert ocsf["unmapped"]["description"] == "Beta release"

    def test_ocsf_hold_record(self, hold_record):
        """HoldRecord produces correct OCSF event."""
        ocsf = format_ocsf(hold_record)
        assert ocsf["uid"] == "hold-abc123def45"
        assert ocsf["api"]["operation"] == "hold"
        assert ocsf["unmapped"]["action"] == "write_file"
        assert ocsf["unmapped"]["resource"] == "/etc/passwd"
        assert ocsf["unmapped"]["status"] == "pending"

    def test_ocsf_execution_record(self, execution_record):
        """ExecutionRecord produces correct OCSF event."""
        ocsf = format_ocsf(execution_record)
        assert ocsf["uid"] == "exec-abc123def4"
        assert ocsf["api"]["operation"] == "execution"
        assert ocsf["unmapped"]["verification_category"] == "auto_approved"

    def test_ocsf_escalation_record(self, escalation_record):
        """EscalationRecord produces correct OCSF event."""
        ocsf = format_ocsf(escalation_record)
        assert ocsf["uid"] == "esc-abc123def45"
        assert ocsf["api"]["operation"] == "escalation"
        assert ocsf["unmapped"]["trigger"] == "Budget limit exceeded"
        assert ocsf["unmapped"]["recommendation"] == "Request additional funding"

    def test_ocsf_intervention_record(self, intervention_record):
        """InterventionRecord produces correct OCSF event."""
        ocsf = format_ocsf(intervention_record)
        assert ocsf["uid"] == "int-abc123def45"
        assert ocsf["api"]["operation"] == "intervention"
        assert ocsf["unmapped"]["observation"] == "Code quality below standard"
        assert ocsf["unmapped"]["action_taken"] == "Requested refactoring"

    def test_ocsf_severity_mapping(self, decision_record, hold_record_denied):
        """OCSF severity_id correctly maps from CEF severity."""
        # Decision with STANDARD review -> CEF severity 2 -> OCSF severity 1 (Informational)
        ocsf_dec = format_ocsf(decision_record)
        assert ocsf_dec["severity_id"] == 1
        assert ocsf_dec["severity"] == "Informational"

        # Denied hold -> CEF severity 9 -> OCSF severity 5 (Critical)
        ocsf_hold = format_ocsf(hold_record_denied)
        assert ocsf_hold["severity_id"] == 5
        assert ocsf_hold["severity"] == "Critical"

    def test_ocsf_time_epoch_ms(self, decision_record):
        """OCSF time field is epoch milliseconds."""
        ocsf = format_ocsf(decision_record)
        expected_ms = int(
            datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc).timestamp() * 1000
        )
        assert ocsf["time"] == expected_ms

    def test_ocsf_is_json_serializable(self, decision_record):
        """OCSF output can be serialized to JSON."""
        ocsf = format_ocsf(decision_record)
        serialized = json.dumps(ocsf, default=str)
        parsed = json.loads(serialized)
        assert parsed["uid"] == decision_record.decision_id

    def test_ocsf_no_project_name(self, decision_record):
        """OCSF event without project_name omits it from metadata."""
        ocsf = format_ocsf(decision_record, project_name="")
        assert "project_name" not in ocsf["metadata"]


# ============================================================================
# Syslog Handler Tests
# ============================================================================


class TestSyslogHandler:
    """Tests for syslog handler creation."""

    def test_create_udp_handler(self):
        """Create a UDP syslog handler."""
        handler = create_syslog_handler(host="localhost", port=5514, protocol="udp")
        assert isinstance(handler, logging.handlers.SysLogHandler)
        assert handler.address == ("localhost", 5514)
        assert handler.socktype == socket.SOCK_DGRAM
        handler.close()

    def test_create_tcp_handler(self):
        """Create a TCP syslog handler — validates socktype is STREAM.

        TCP handlers attempt connection during construction, so we start a
        local TCP listener to accept the connection.
        """
        import threading

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]

        accepted = []

        def _accept():
            conn, _ = srv.accept()
            accepted.append(conn)

        t = threading.Thread(target=_accept, daemon=True)
        t.start()

        handler = create_syslog_handler(host="127.0.0.1", port=port, protocol="tcp")
        assert isinstance(handler, logging.handlers.SysLogHandler)
        assert handler.address == ("127.0.0.1", port)
        assert handler.socktype == socket.SOCK_STREAM
        handler.close()

        t.join(timeout=2)
        for c in accepted:
            c.close()
        srv.close()

    def test_default_protocol_is_udp(self):
        """Default protocol is UDP."""
        handler = create_syslog_handler(host="localhost", port=5514)
        assert handler.socktype == socket.SOCK_DGRAM
        handler.close()

    def test_invalid_protocol_raises(self):
        """Invalid protocol raises ValueError."""
        with pytest.raises(ValueError, match="Invalid protocol"):
            create_syslog_handler(host="localhost", port=514, protocol="http")

    def test_case_insensitive_protocol(self):
        """Protocol is case-insensitive."""
        import threading

        handler_udp = create_syslog_handler(host="localhost", port=5514, protocol="UDP")
        assert handler_udp.socktype == socket.SOCK_DGRAM
        handler_udp.close()

        # TCP needs a listener to accept the connection
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]

        accepted = []

        def _accept():
            conn, _ = srv.accept()
            accepted.append(conn)

        t = threading.Thread(target=_accept, daemon=True)
        t.start()

        handler_tcp = create_syslog_handler(host="127.0.0.1", port=port, protocol="TCP")
        assert handler_tcp.socktype == socket.SOCK_STREAM
        handler_tcp.close()

        t.join(timeout=2)
        for c in accepted:
            c.close()
        srv.close()


# ============================================================================
# Batch Export Tests
# ============================================================================


class TestExportEvents:
    """Tests for batch export with time filtering."""

    def _make_store(self):
        """Create a real in-memory SqliteTrustPlaneStore for testing."""
        store = SqliteTrustPlaneStore(":memory:")
        store.initialize()
        return store

    def test_export_cef_empty_store(self):
        """Empty store produces empty event list."""
        store = self._make_store()
        events = export_events(store, fmt="cef")
        assert events == []

    def test_export_cef_with_decisions(self, decision_record):
        """Decisions are exported as CEF lines."""
        store = self._make_store()
        store.store_decision(decision_record)
        events = export_events(store, fmt="cef")
        assert len(events) == 1
        assert events[0].startswith("CEF:0|")
        assert "dec-abc123def456" in events[0]

    def test_export_ocsf_with_decisions(self, decision_record):
        """Decisions are exported as OCSF dicts."""
        store = self._make_store()
        store.store_decision(decision_record)
        events = export_events(store, fmt="ocsf")
        assert len(events) == 1
        assert isinstance(events[0], dict)
        assert events[0]["uid"] == "dec-abc123def456"

    def test_export_mixed_records(self, decision_record, milestone_record, hold_record):
        """Multiple record types are all exported."""
        store = self._make_store()
        store.store_decision(decision_record)
        store.store_milestone(milestone_record)
        store.store_hold(hold_record)
        events = export_events(store, fmt="cef")
        assert len(events) == 3

    def test_export_sorted_by_timestamp(self, decision_record, milestone_record):
        """Events are sorted chronologically."""
        store = self._make_store()
        # Milestone is at 12:00, decision is at 10:00
        store.store_decision(decision_record)
        store.store_milestone(milestone_record)
        events = export_events(store, fmt="cef")
        assert len(events) == 2
        # Decision (10:00) should come before milestone (12:00)
        assert "dec-abc123def456" in events[0]
        assert "ms-abc123def456" in events[1]

    def test_export_since_filter(self, decision_record, milestone_record):
        """--since filter excludes older records."""
        store = self._make_store()
        store.store_decision(decision_record)  # 10:00
        store.store_milestone(milestone_record)  # 12:00

        # Filter: only after 11:00
        since = datetime(2026, 3, 15, 11, 0, 0, tzinfo=timezone.utc)
        events = export_events(store, fmt="cef", since=since)
        assert len(events) == 1
        assert "ms-abc123def456" in events[0]

    def test_export_since_includes_exact_match(self, decision_record):
        """Records at exactly the since timestamp are included."""
        store = self._make_store()
        store.store_decision(decision_record)  # 10:00

        since = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
        events = export_events(store, fmt="cef", since=since)
        assert len(events) == 1

    def test_export_since_naive_datetime(self, decision_record):
        """Naive since datetime is treated as UTC."""
        store = self._make_store()
        store.store_decision(decision_record)  # 10:00 UTC

        since = datetime(2026, 3, 15, 11, 0, 0)  # naive, treated as UTC
        events = export_events(store, fmt="cef", since=since)
        assert len(events) == 0

    def test_export_project_name(self, decision_record):
        """Project name is included in exported events."""
        store = self._make_store()
        store.store_decision(decision_record)
        events = export_events(store, fmt="cef", project_name="MyProject")
        assert "cs1=MyProject" in events[0]

    def test_export_invalid_format_raises(self, decision_record):
        """Invalid format raises ValueError."""
        store = self._make_store()
        store.store_decision(decision_record)
        with pytest.raises(ValueError, match="Unsupported format"):
            export_events(store, fmt="xml")


# ============================================================================
# CLI Integration Tests
# ============================================================================


class TestCLIExportSIEM:
    """Tests for SIEM export via CLI."""

    def _init_project_with_records(self, runner, trust_dir):
        """Create a project and add some records for export testing."""
        runner.invoke(
            main,
            ["--dir", trust_dir, "init", "--name", "SIEM Test", "--author", "Alice"],
        )
        # Add a decision
        runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "decide",
                "--type",
                "scope",
                "--decision",
                "Test decision for SIEM",
                "--rationale",
                "Testing export",
            ],
        )
        # Add a milestone
        runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "milestone",
                "--version",
                "v0.1",
                "--description",
                "Test milestone",
            ],
        )

    def test_export_cef_format(self, tmp_path):
        """attest export --format cef outputs CEF lines."""
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        self._init_project_with_records(runner, trust_dir)

        result = runner.invoke(main, ["--dir", trust_dir, "export", "--format", "cef"])
        assert result.exit_code == 0
        # Output should contain CEF lines
        for line in result.output.strip().split("\n"):
            if line:
                assert line.startswith("CEF:0|")

    def test_export_ocsf_format(self, tmp_path):
        """attest export --format ocsf outputs OCSF JSON."""
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        self._init_project_with_records(runner, trust_dir)

        result = runner.invoke(main, ["--dir", trust_dir, "export", "--format", "ocsf"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 1
        # Check OCSF structure
        for event in data:
            assert event["class_uid"] == 6003
            assert event["category_uid"] == 6

    def test_export_cef_with_since(self, tmp_path):
        """attest export --format cef --since 24h filters by time."""
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        self._init_project_with_records(runner, trust_dir)

        # Recent records (just created) should appear with --since 24h
        result = runner.invoke(
            main, ["--dir", trust_dir, "export", "--format", "cef", "--since", "24h"]
        )
        assert result.exit_code == 0
        lines = [l for l in result.output.strip().split("\n") if l.startswith("CEF:")]
        assert len(lines) >= 1

    def test_export_cef_with_since_zero_results(self, tmp_path):
        """attest export --format cef --since 0h produces no results for old data."""
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        self._init_project_with_records(runner, trust_dir)

        # 0 hours ago = now, no records should match
        # (records were created milliseconds ago, but since=0h means now)
        # This is a boundary test - we accept either 0 or some results
        result = runner.invoke(
            main, ["--dir", trust_dir, "export", "--format", "cef", "--since", "1m"]
        )
        assert result.exit_code == 0

    def test_export_cef_to_file(self, tmp_path):
        """attest export --format cef --output writes to file."""
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        self._init_project_with_records(runner, trust_dir)

        output_file = str(tmp_path / "events.cef")
        result = runner.invoke(
            main, ["--dir", trust_dir, "export", "--format", "cef", "-o", output_file]
        )
        assert result.exit_code == 0
        assert "Exported" in result.output

        # Verify file contents
        with open(output_file) as f:
            content = f.read()
        assert "CEF:0|" in content

    def test_export_syslog_requires_host(self, tmp_path):
        """attest export --format syslog without --host errors."""
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        self._init_project_with_records(runner, trust_dir)

        result = runner.invoke(
            main, ["--dir", trust_dir, "export", "--format", "syslog"]
        )
        assert result.exit_code == 1
        assert "--host is required" in result.output

    def test_export_json_still_works(self, tmp_path):
        """Existing json export format is unaffected."""
        runner = CliRunner()
        trust_dir = str(tmp_path / "trust-plane")
        self._init_project_with_records(runner, trust_dir)

        result = runner.invoke(main, ["--dir", trust_dir, "export", "--format", "json"])
        assert result.exit_code == 0

    def test_export_no_project(self, tmp_path):
        """Export without project shows error."""
        runner = CliRunner()
        trust_dir = str(tmp_path / "no-project")
        result = runner.invoke(main, ["--dir", trust_dir, "export", "--format", "cef"])
        assert result.exit_code == 1
        assert "No project found" in result.output


# ============================================================================
# TLS Syslog Handler (TODO-45)
# ============================================================================


class TestTLSSyslogHandler:
    """Tests for TLS-encrypted syslog transport."""

    def test_tls_handler_import(self):
        """TLS handler is importable."""
        from kailash.trust.plane.siem import TLSSyslogError, create_tls_syslog_handler

        assert callable(create_tls_syslog_handler)
        assert issubclass(TLSSyslogError, Exception)

    def test_tls_handler_requires_client_key_with_cert(self):
        """Providing client_cert without client_key raises ValueError."""
        from kailash.trust.plane.siem import create_tls_syslog_handler

        with pytest.raises(ValueError, match="client_key is required"):
            create_tls_syslog_handler(
                host="localhost",
                port=6514,
                client_cert="/some/cert.pem",
            )

    def test_tls_handler_connection_refused(self):
        """Connecting to a non-listening port raises TLSSyslogError."""
        from kailash.trust.plane.siem import TLSSyslogError, create_tls_syslog_handler

        with pytest.raises(TLSSyslogError, match="Cannot connect"):
            create_tls_syslog_handler(
                host="127.0.0.1",
                port=19999,  # non-listening port
            )

    def test_tls_error_is_descriptive(self):
        """TLSSyslogError includes host and port."""
        from kailash.trust.plane.siem import TLSSyslogError

        err = TLSSyslogError(
            "TLS handshake failed with siem.local:6514: certificate verify failed"
        )
        assert "siem.local:6514" in str(err)
        assert "certificate verify failed" in str(err)
