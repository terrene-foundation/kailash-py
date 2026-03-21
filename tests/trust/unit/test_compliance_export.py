# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for SOC 2 / ISO 27001 compliance evidence generation.

Tests the compliance evidence export module that maps EATP operations
to SOC 2 control objectives and generates audit-ready evidence reports.

TDD: These tests are written FIRST, before the implementation.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from kailash.trust.export.compliance import (
    SOC2_CONTROL_MAPPINGS,
    ComplianceEvidenceRecord,
    ComplianceEvidenceReport,
    generate_soc2_evidence,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def now():
    """Current UTC timestamp."""
    return datetime.now(timezone.utc)


@pytest.fixture
def period_start(now):
    """Report period start: 30 days ago."""
    return now - timedelta(days=30)


@pytest.fixture
def period_end(now):
    """Report period end: now."""
    return now


@pytest.fixture
def mock_audit_service(now):
    """Create a mock AuditQueryService that returns realistic compliance data.

    The mock returns a ComplianceReport-like object with audit data
    covering all four EATP operations: ESTABLISH, DELEGATE, VERIFY, AUDIT.
    """
    service = AsyncMock()

    # Build a realistic compliance report response
    report = MagicMock()
    report.start_time = now - timedelta(days=30)
    report.end_time = now
    report.total_actions = 150
    report.total_agents = 5
    report.success_count = 140
    report.failure_count = 5
    report.denied_count = 3
    report.partial_count = 2
    report.trust_established_count = 10
    report.trust_delegated_count = 8
    report.trust_revoked_count = 1
    report.any_violations = True
    report.violation_details = [
        {
            "anchor_id": "aud-denied-001",
            "agent_id": "agent-003",
            "action": "export_data",
            "timestamp": now.isoformat(),
            "reason": "Action denied",
        }
    ]

    # Action summaries covering all four EATP operations
    establish_summary = MagicMock()
    establish_summary.action = "trust_established"
    establish_summary.total_count = 10
    establish_summary.success_count = 10
    establish_summary.failure_count = 0
    establish_summary.denied_count = 0

    delegate_summary = MagicMock()
    delegate_summary.action = "trust_delegated"
    delegate_summary.total_count = 8
    delegate_summary.success_count = 7
    delegate_summary.failure_count = 1
    delegate_summary.denied_count = 0

    verify_summary = MagicMock()
    verify_summary.action = "verify_trust"
    verify_summary.total_count = 50
    verify_summary.success_count = 48
    verify_summary.failure_count = 2
    verify_summary.denied_count = 0

    audit_summary = MagicMock()
    audit_summary.action = "audit_action"
    audit_summary.total_count = 82
    audit_summary.success_count = 75
    audit_summary.failure_count = 2
    audit_summary.denied_count = 3

    report.action_summaries = {
        "trust_established": establish_summary,
        "trust_delegated": delegate_summary,
        "verify_trust": verify_summary,
        "audit_action": audit_summary,
    }

    # Agent summaries
    agent_summary = MagicMock()
    agent_summary.agent_id = "agent-001"
    agent_summary.total_actions = 50
    agent_summary.success_rate = 0.96
    report.agent_summaries = {"agent-001": agent_summary}

    service.generate_compliance_report = AsyncMock(return_value=report)
    return service


# ---------------------------------------------------------------------------
# SOC 2 Control Mapping Tests
# ---------------------------------------------------------------------------


class TestSOC2ControlMappings:
    """Tests for SOC 2 control mapping completeness and correctness."""

    def test_all_four_eatp_operations_have_mappings(self):
        """All four EATP operations must map to SOC 2 controls."""
        required_operations = {"ESTABLISH", "DELEGATE", "VERIFY", "AUDIT"}
        assert set(SOC2_CONTROL_MAPPINGS.keys()) == required_operations

    def test_establish_maps_to_access_control(self):
        """ESTABLISH operation maps to CC6.1 (access control) and CC6.2 (user provisioning)."""
        mappings = SOC2_CONTROL_MAPPINGS["ESTABLISH"]
        assert "CC6.1" in mappings, "ESTABLISH must map to CC6.1 (Logical and Physical Access Controls)"
        assert "CC6.2" in mappings, "ESTABLISH must map to CC6.2 (User Provisioning)"

    def test_delegate_maps_to_role_based_access(self):
        """DELEGATE operation maps to CC6.1 and CC6.3 (role-based access)."""
        mappings = SOC2_CONTROL_MAPPINGS["DELEGATE"]
        assert "CC6.1" in mappings, "DELEGATE must map to CC6.1 (Logical and Physical Access Controls)"
        assert "CC6.3" in mappings, "DELEGATE must map to CC6.3 (Role-Based Access)"

    def test_verify_maps_to_monitoring(self):
        """VERIFY operation maps to CC7.2 (system monitoring) and CC7.3 (anomaly detection)."""
        mappings = SOC2_CONTROL_MAPPINGS["VERIFY"]
        assert "CC7.2" in mappings, "VERIFY must map to CC7.2 (System Monitoring)"
        assert "CC7.3" in mappings, "VERIFY must map to CC7.3 (Anomaly Detection)"

    def test_audit_maps_to_change_management(self):
        """AUDIT operation maps to CC7.1 (monitoring) and CC8.1 (change management)."""
        mappings = SOC2_CONTROL_MAPPINGS["AUDIT"]
        assert "CC7.1" in mappings, "AUDIT must map to CC7.1 (Monitoring)"
        assert "CC8.1" in mappings, "AUDIT must map to CC8.1 (Change Management)"

    def test_all_control_mappings_are_lists_of_strings(self):
        """Every control mapping value must be a list of non-empty strings."""
        for operation, controls in SOC2_CONTROL_MAPPINGS.items():
            assert isinstance(controls, list), f"{operation} mapping must be a list"
            assert len(controls) > 0, f"{operation} must map to at least one control"
            for control in controls:
                assert isinstance(control, str), f"Control IDs must be strings, got {type(control)}"
                assert len(control) > 0, f"Control IDs must be non-empty"

    def test_control_ids_follow_soc2_naming_convention(self):
        """All control IDs must follow SOC 2 naming (CC prefix with number.number)."""
        import re

        pattern = re.compile(r"^CC\d+\.\d+$")
        for operation, controls in SOC2_CONTROL_MAPPINGS.items():
            for control in controls:
                assert pattern.match(control), (
                    f"Control ID '{control}' in {operation} does not follow "
                    f"SOC 2 naming convention (expected CCN.N format)"
                )


# ---------------------------------------------------------------------------
# ComplianceEvidenceRecord Tests
# ---------------------------------------------------------------------------


class TestComplianceEvidenceRecord:
    """Tests for individual evidence record structure."""

    def test_record_has_all_required_fields(self, now):
        """Evidence records must have all required fields populated."""
        record = ComplianceEvidenceRecord(
            record_id="rec-001",
            timestamp=now,
            operation="ESTABLISH",
            agent_id="agent-001",
            result="success",
            control_objectives=["CC6.1", "CC6.2"],
            evidence_data={"authority_id": "org-acme", "capabilities": ["read"]},
        )
        assert record.record_id == "rec-001"
        assert record.timestamp == now
        assert record.operation == "ESTABLISH"
        assert record.agent_id == "agent-001"
        assert record.result == "success"
        assert record.control_objectives == ["CC6.1", "CC6.2"]
        assert record.evidence_data == {
            "authority_id": "org-acme",
            "capabilities": ["read"],
        }

    def test_record_authority_id_is_optional(self, now):
        """authority_id on evidence records is optional (defaults to None)."""
        record = ComplianceEvidenceRecord(
            record_id="rec-002",
            timestamp=now,
            operation="VERIFY",
            agent_id="agent-002",
            result="success",
            control_objectives=["CC7.2"],
            evidence_data={},
        )
        assert record.authority_id is None

    def test_record_with_authority_id(self, now):
        """Evidence records can include an optional authority_id."""
        record = ComplianceEvidenceRecord(
            record_id="rec-003",
            timestamp=now,
            operation="DELEGATE",
            agent_id="agent-003",
            result="success",
            control_objectives=["CC6.1", "CC6.3"],
            evidence_data={"delegation_chain_length": 2},
            authority_id="org-acme",
        )
        assert record.authority_id == "org-acme"

    def test_record_for_each_operation_type(self, now):
        """Evidence records can be created for all four EATP operations."""
        for operation in ["ESTABLISH", "DELEGATE", "VERIFY", "AUDIT"]:
            record = ComplianceEvidenceRecord(
                record_id=f"rec-{operation.lower()}",
                timestamp=now,
                operation=operation,
                agent_id="agent-001",
                result="success",
                control_objectives=SOC2_CONTROL_MAPPINGS[operation],
                evidence_data={"test": True},
            )
            assert record.operation == operation
            assert record.control_objectives == SOC2_CONTROL_MAPPINGS[operation]


# ---------------------------------------------------------------------------
# ComplianceEvidenceReport Tests
# ---------------------------------------------------------------------------


class TestComplianceEvidenceReport:
    """Tests for full compliance evidence report structure."""

    def test_report_has_all_required_fields(self, now, period_start, period_end):
        """Evidence reports must contain all required structural fields."""
        report = ComplianceEvidenceReport(
            report_id="rpt-001",
            generated_at=now,
            period_start=period_start,
            period_end=period_end,
            framework="SOC2",
            records=[],
            control_coverage={},
            summary={},
        )
        assert report.report_id == "rpt-001"
        assert report.generated_at == now
        assert report.period_start == period_start
        assert report.period_end == period_end
        assert report.framework == "SOC2"
        assert report.records == []
        assert report.control_coverage == {}
        assert report.summary == {}

    def test_report_framework_must_be_specified(self, now, period_start, period_end):
        """Report framework field must be explicitly specified (SOC2 or ISO27001)."""
        for framework in ["SOC2", "ISO27001"]:
            report = ComplianceEvidenceReport(
                report_id=f"rpt-{framework}",
                generated_at=now,
                period_start=period_start,
                period_end=period_end,
                framework=framework,
                records=[],
                control_coverage={},
                summary={},
            )
            assert report.framework == framework

    def test_report_with_records_and_coverage(self, now, period_start, period_end):
        """Report must correctly store records and control coverage data."""
        record = ComplianceEvidenceRecord(
            record_id="rec-001",
            timestamp=now,
            operation="ESTABLISH",
            agent_id="agent-001",
            result="success",
            control_objectives=["CC6.1", "CC6.2"],
            evidence_data={},
        )
        report = ComplianceEvidenceReport(
            report_id="rpt-002",
            generated_at=now,
            period_start=period_start,
            period_end=period_end,
            framework="SOC2",
            records=[record],
            control_coverage={"CC6.1": 1, "CC6.2": 1},
            summary={"total_records": 1},
        )
        assert len(report.records) == 1
        assert report.records[0].record_id == "rec-001"
        assert report.control_coverage["CC6.1"] == 1
        assert report.summary["total_records"] == 1


# ---------------------------------------------------------------------------
# generate_soc2_evidence Tests
# ---------------------------------------------------------------------------


class TestGenerateSOC2Evidence:
    """Tests for the SOC 2 evidence generation function."""

    @pytest.mark.asyncio
    async def test_generates_report_with_valid_structure(self, mock_audit_service, period_start, period_end):
        """Generated report must have all required structural fields."""
        report = await generate_soc2_evidence(
            audit_service=mock_audit_service,
            start_time=period_start,
            end_time=period_end,
        )

        assert isinstance(report, ComplianceEvidenceReport)
        assert report.report_id is not None and len(report.report_id) > 0
        assert report.generated_at is not None
        assert report.period_start == period_start
        assert report.period_end == period_end
        assert report.framework == "SOC2"

    @pytest.mark.asyncio
    async def test_report_contains_evidence_records(self, mock_audit_service, period_start, period_end):
        """Generated report must contain evidence records derived from audit data."""
        report = await generate_soc2_evidence(
            audit_service=mock_audit_service,
            start_time=period_start,
            end_time=period_end,
        )

        assert len(report.records) > 0, "Report must contain at least one evidence record"

    @pytest.mark.asyncio
    async def test_evidence_records_map_to_soc2_controls(self, mock_audit_service, period_start, period_end):
        """Every evidence record must reference valid SOC 2 control objectives."""
        report = await generate_soc2_evidence(
            audit_service=mock_audit_service,
            start_time=period_start,
            end_time=period_end,
        )

        # Collect all valid SOC2 control IDs
        all_valid_controls = set()
        for controls in SOC2_CONTROL_MAPPINGS.values():
            all_valid_controls.update(controls)

        for record in report.records:
            assert len(record.control_objectives) > 0, (
                f"Record {record.record_id} must have at least one control objective"
            )
            for control in record.control_objectives:
                assert control in all_valid_controls, f"Record {record.record_id} references unknown control {control}"

    @pytest.mark.asyncio
    async def test_control_coverage_counts_records_per_control(self, mock_audit_service, period_start, period_end):
        """control_coverage must map each SOC 2 control ID to the count of evidence records."""
        report = await generate_soc2_evidence(
            audit_service=mock_audit_service,
            start_time=period_start,
            end_time=period_end,
        )

        assert len(report.control_coverage) > 0, "control_coverage must not be empty"
        for control_id, count in report.control_coverage.items():
            assert isinstance(count, int), f"Coverage count for {control_id} must be int"
            assert count > 0, f"Coverage count for {control_id} must be positive"

    @pytest.mark.asyncio
    async def test_summary_contains_aggregate_stats(self, mock_audit_service, period_start, period_end):
        """Report summary must include aggregate statistics."""
        report = await generate_soc2_evidence(
            audit_service=mock_audit_service,
            start_time=period_start,
            end_time=period_end,
        )

        assert "total_records" in report.summary, "Summary must include total_records"
        assert "total_agents" in report.summary, "Summary must include total_agents"
        assert "total_actions" in report.summary, "Summary must include total_actions"
        assert "violations_found" in report.summary, "Summary must include violations_found"

    @pytest.mark.asyncio
    async def test_passes_authority_id_filter_to_audit_service(self, mock_audit_service, period_start, period_end):
        """When authority_id is provided, it must be passed to the audit service."""
        await generate_soc2_evidence(
            audit_service=mock_audit_service,
            start_time=period_start,
            end_time=period_end,
            authority_id="org-acme",
        )

        mock_audit_service.generate_compliance_report.assert_called_once()
        call_kwargs = mock_audit_service.generate_compliance_report.call_args
        assert call_kwargs.kwargs.get("authority_id") == "org-acme" or (
            len(call_kwargs.args) >= 3 and call_kwargs.args[2] == "org-acme"
        )

    @pytest.mark.asyncio
    async def test_generates_establish_evidence_records(self, mock_audit_service, period_start, period_end):
        """Report must include evidence records for ESTABLISH operations."""
        report = await generate_soc2_evidence(
            audit_service=mock_audit_service,
            start_time=period_start,
            end_time=period_end,
        )

        establish_records = [r for r in report.records if r.operation == "ESTABLISH"]
        assert len(establish_records) > 0, "Must have evidence for ESTABLISH operations"
        for record in establish_records:
            assert "CC6.1" in record.control_objectives

    @pytest.mark.asyncio
    async def test_generates_delegate_evidence_records(self, mock_audit_service, period_start, period_end):
        """Report must include evidence records for DELEGATE operations."""
        report = await generate_soc2_evidence(
            audit_service=mock_audit_service,
            start_time=period_start,
            end_time=period_end,
        )

        delegate_records = [r for r in report.records if r.operation == "DELEGATE"]
        assert len(delegate_records) > 0, "Must have evidence for DELEGATE operations"
        for record in delegate_records:
            assert "CC6.3" in record.control_objectives

    @pytest.mark.asyncio
    async def test_generates_verify_evidence_records(self, mock_audit_service, period_start, period_end):
        """Report must include evidence records for VERIFY operations."""
        report = await generate_soc2_evidence(
            audit_service=mock_audit_service,
            start_time=period_start,
            end_time=period_end,
        )

        verify_records = [r for r in report.records if r.operation == "VERIFY"]
        assert len(verify_records) > 0, "Must have evidence for VERIFY operations"
        for record in verify_records:
            assert "CC7.2" in record.control_objectives

    @pytest.mark.asyncio
    async def test_generates_audit_evidence_records(self, mock_audit_service, period_start, period_end):
        """Report must include evidence records for AUDIT operations."""
        report = await generate_soc2_evidence(
            audit_service=mock_audit_service,
            start_time=period_start,
            end_time=period_end,
        )

        audit_records = [r for r in report.records if r.operation == "AUDIT"]
        assert len(audit_records) > 0, "Must have evidence for AUDIT operations"
        for record in audit_records:
            assert "CC8.1" in record.control_objectives

    @pytest.mark.asyncio
    async def test_calls_audit_service_with_correct_time_range(self, mock_audit_service, period_start, period_end):
        """Must pass exact start_time and end_time to audit service."""
        await generate_soc2_evidence(
            audit_service=mock_audit_service,
            start_time=period_start,
            end_time=period_end,
        )

        mock_audit_service.generate_compliance_report.assert_called_once()
        call_kwargs = mock_audit_service.generate_compliance_report.call_args
        # Check both positional and keyword argument styles
        if call_kwargs.kwargs:
            assert call_kwargs.kwargs.get("start_time") == period_start
            assert call_kwargs.kwargs.get("end_time") == period_end
        else:
            assert call_kwargs.args[0] == period_start
            assert call_kwargs.args[1] == period_end

    @pytest.mark.asyncio
    async def test_evidence_records_have_timestamps(self, mock_audit_service, period_start, period_end):
        """Every evidence record must have a valid timestamp."""
        report = await generate_soc2_evidence(
            audit_service=mock_audit_service,
            start_time=period_start,
            end_time=period_end,
        )

        for record in report.records:
            assert record.timestamp is not None, f"Record {record.record_id} must have a timestamp"
            assert isinstance(record.timestamp, datetime), f"Record {record.record_id} timestamp must be a datetime"

    @pytest.mark.asyncio
    async def test_evidence_records_have_unique_ids(self, mock_audit_service, period_start, period_end):
        """Every evidence record must have a unique record_id."""
        report = await generate_soc2_evidence(
            audit_service=mock_audit_service,
            start_time=period_start,
            end_time=period_end,
        )

        record_ids = [r.record_id for r in report.records]
        assert len(record_ids) == len(set(record_ids)), "All record IDs must be unique"

    @pytest.mark.asyncio
    async def test_violation_details_included_in_evidence(self, mock_audit_service, period_start, period_end):
        """When the compliance report has violations, they must appear in the summary."""
        report = await generate_soc2_evidence(
            audit_service=mock_audit_service,
            start_time=period_start,
            end_time=period_end,
        )

        assert report.summary["violations_found"] is True, "Summary must reflect that violations were found"
