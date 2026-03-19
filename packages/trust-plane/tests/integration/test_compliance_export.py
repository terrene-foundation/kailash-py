# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for SOC2/ISO 27001 compliance evidence mapping and GRC export."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from click.testing import CliRunner

from trustplane.cli import main
from trustplane.compliance import (
    SECURITY_PATTERN_EVIDENCE,
    export_decisions_csv,
    export_violations_csv,
    generate_control_mapping_json,
    generate_evidence_summary_md,
    generate_iso27001_evidence,
    generate_soc2_evidence,
)
from trustplane.holds import HoldRecord
from trustplane.models import DecisionRecord, DecisionType, MilestoneRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def initialized_project(runner, tmp_path):
    """Create an initialized TrustPlane project with sample records."""
    trust_dir = str(tmp_path / "trust-plane")

    # Init project
    result = runner.invoke(
        main,
        [
            "--dir",
            trust_dir,
            "init",
            "--name",
            "Compliance Test",
            "--author",
            "Auditor",
        ],
    )
    assert result.exit_code == 0, result.output

    # Add decisions
    for i in range(3):
        result = runner.invoke(
            main,
            [
                "--dir",
                trust_dir,
                "decide",
                "--type",
                "scope",
                "--decision",
                f"Decision {i}",
                "--rationale",
                f"Rationale {i}",
                "--risk",
                f"Risk {i}",
                "--alternative",
                f"Alt {i}",
            ],
        )
        assert result.exit_code == 0, result.output

    # Add milestones
    result = runner.invoke(
        main,
        [
            "--dir",
            trust_dir,
            "milestone",
            "--version",
            "v0.1",
            "--description",
            "First milestone",
        ],
    )
    assert result.exit_code == 0, result.output

    return trust_dir


@pytest.fixture
def sample_decisions():
    """Create sample DecisionRecord instances for unit tests."""
    now = datetime.now(timezone.utc)
    return [
        DecisionRecord(
            decision_type=DecisionType.SCOPE,
            decision="Focus on core features",
            rationale="Resource constraints",
            alternatives=["Full feature set", "Phased rollout"],
            risks=["Missing features", "User complaints"],
            confidence=0.85,
            author="alice",
            timestamp=now - timedelta(days=5),
        ),
        DecisionRecord(
            decision_type=DecisionType.TECHNICAL,
            decision="Use PostgreSQL",
            rationale="Better scalability",
            alternatives=["MySQL", "SQLite"],
            risks=["Migration complexity"],
            confidence=0.9,
            author="bob",
            timestamp=now - timedelta(days=3),
        ),
        DecisionRecord(
            decision_type="compliance_ruling",
            decision="Accept residual risk",
            rationale="Within tolerance",
            confidence=0.7,
            author="carol",
            timestamp=now - timedelta(days=1),
        ),
    ]


@pytest.fixture
def sample_holds():
    """Create sample HoldRecord instances for unit tests."""
    now = datetime.now(timezone.utc)
    return [
        HoldRecord(
            hold_id="hold-abc123def456",
            action="write_file",
            resource="/etc/passwd",
            context={"dimension": "data_access"},
            reason="Blocked path violation",
            status="denied",
            created_at=now - timedelta(days=4),
            resolved_at=now - timedelta(days=3),
            resolved_by="security-admin",
            resolution_reason="Correctly blocked",
        ),
        HoldRecord(
            hold_id="hold-789ghi012jkl",
            action="execute_command",
            resource="rm -rf /",
            context={"dimension": "operational"},
            reason="Dangerous command",
            status="pending",
            created_at=now - timedelta(days=2),
        ),
    ]


# ---------------------------------------------------------------------------
# Unit tests: CSV export
# ---------------------------------------------------------------------------


class TestExportDecisionsCSV:
    def test_empty_decisions(self):
        csv_text = export_decisions_csv([])
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 1  # header only
        assert "decision_id" in rows[0]

    def test_csv_header_fields(self, sample_decisions):
        csv_text = export_decisions_csv(sample_decisions)
        reader = csv.reader(io.StringIO(csv_text))
        header = next(reader)
        expected = [
            "decision_id",
            "decision_type",
            "decision",
            "rationale",
            "alternatives",
            "risks",
            "review_requirement",
            "confidence",
            "author",
            "timestamp",
        ]
        assert header == expected

    def test_csv_row_count(self, sample_decisions):
        csv_text = export_decisions_csv(sample_decisions)
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 4  # header + 3 decisions

    def test_csv_field_values(self, sample_decisions):
        csv_text = export_decisions_csv(sample_decisions)
        reader = csv.reader(io.StringIO(csv_text))
        next(reader)  # skip header
        first_row = next(reader)
        assert first_row[1] == "scope"  # decision_type
        assert first_row[2] == "Focus on core features"  # decision
        assert first_row[3] == "Resource constraints"  # rationale
        assert "Full feature set" in first_row[4]  # alternatives
        assert first_row[7] == "0.85"  # confidence
        assert first_row[8] == "alice"  # author

    def test_csv_custom_type(self, sample_decisions):
        csv_text = export_decisions_csv(sample_decisions)
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        # Third decision has custom type
        assert rows[3][1] == "compliance_ruling"


class TestExportViolationsCSV:
    def test_empty_violations(self):
        csv_text = export_violations_csv([])
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 1  # header only
        assert "hold_id" in rows[0]

    def test_csv_header_fields(self, sample_holds):
        csv_text = export_violations_csv(sample_holds)
        reader = csv.reader(io.StringIO(csv_text))
        header = next(reader)
        expected = [
            "hold_id",
            "action",
            "resource",
            "reason",
            "status",
            "created_at",
            "resolved_at",
            "resolved_by",
            "resolution_reason",
        ]
        assert header == expected

    def test_csv_row_count(self, sample_holds):
        csv_text = export_violations_csv(sample_holds)
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 3  # header + 2 holds

    def test_csv_resolved_hold(self, sample_holds):
        csv_text = export_violations_csv(sample_holds)
        reader = csv.reader(io.StringIO(csv_text))
        next(reader)  # skip header
        first_row = next(reader)
        assert first_row[0] == "hold-abc123def456"
        assert first_row[1] == "write_file"
        assert first_row[3] == "Blocked path violation"
        assert first_row[4] == "denied"
        assert first_row[7] == "security-admin"

    def test_csv_pending_hold(self, sample_holds):
        csv_text = export_violations_csv(sample_holds)
        reader = csv.reader(io.StringIO(csv_text))
        next(reader)  # skip header
        next(reader)  # skip first
        second_row = next(reader)
        assert second_row[4] == "pending"
        assert second_row[6] == ""  # resolved_at empty
        assert second_row[7] == ""  # resolved_by empty


# ---------------------------------------------------------------------------
# Unit tests: Control mapping JSON
# ---------------------------------------------------------------------------


class TestControlMappingJSON:
    def test_soc2_mapping(self):
        mapping = generate_control_mapping_json("soc2")
        assert mapping["framework"] == "SOC2"
        assert mapping["framework_version"] == "2017"
        assert len(mapping["mappings"]) == 11  # 11 SOC2 controls

        control_ids = {m["control_id"] for m in mapping["mappings"]}
        assert "CC6.1" in control_ids
        assert "CC6.2" in control_ids
        assert "CC6.3" in control_ids
        assert "CC6.6" in control_ids
        assert "CC6.7" in control_ids
        assert "CC6.8" in control_ids
        assert "CC7.1" in control_ids
        assert "CC7.2" in control_ids
        assert "CC7.3" in control_ids
        assert "CC7.4" in control_ids
        assert "CC8.1" in control_ids

    def test_iso27001_mapping(self):
        mapping = generate_control_mapping_json("iso27001")
        assert mapping["framework"] == "ISO27001"
        assert mapping["framework_version"] == "2022"
        assert len(mapping["mappings"]) == 9  # 9 ISO 27001 controls

        control_ids = {m["control_id"] for m in mapping["mappings"]}
        assert "A.6.1" in control_ids
        assert "A.9.2" in control_ids
        assert "A.9.4" in control_ids
        assert "A.10.1" in control_ids
        assert "A.12.3" in control_ids
        assert "A.12.4" in control_ids
        assert "A.14.2" in control_ids
        assert "A.16.1" in control_ids
        assert "A.18.1" in control_ids

    def test_unsupported_framework_raises(self):
        with pytest.raises(ValueError, match="Unsupported framework"):
            generate_control_mapping_json("hipaa")

    def test_mapping_entries_have_required_fields(self):
        for framework in ("soc2", "iso27001"):
            mapping = generate_control_mapping_json(framework)
            for entry in mapping["mappings"]:
                assert "control_id" in entry
                assert "title" in entry
                assert "description" in entry
                assert "record_type" in entry
                assert "trustplane_source" in entry


# ---------------------------------------------------------------------------
# Integration tests: SOC2 evidence generation
# ---------------------------------------------------------------------------


class TestSOC2Evidence:
    def test_soc2_evidence_structure(self, initialized_project):
        import asyncio

        from trustplane.project import TrustProject

        project = asyncio.run(TrustProject.load(initialized_project))
        evidence = generate_soc2_evidence(project)

        assert evidence["framework"] == "SOC2"
        assert evidence["framework_version"] == "2017"
        assert "generated_at" in evidence
        assert "period" in evidence
        assert "project" in evidence
        assert "summary" in evidence
        assert "controls" in evidence

    def test_soc2_evidence_counts(self, initialized_project):
        import asyncio

        from trustplane.project import TrustProject

        project = asyncio.run(TrustProject.load(initialized_project))
        evidence = generate_soc2_evidence(project)

        assert evidence["summary"]["total_decisions"] == 3
        assert evidence["summary"]["total_milestones"] == 1

    def test_soc2_evidence_controls(self, initialized_project):
        import asyncio

        from trustplane.project import TrustProject

        project = asyncio.run(TrustProject.load(initialized_project))
        evidence = generate_soc2_evidence(project)

        controls = evidence["controls"]
        # Original record-based controls
        assert "CC6.2" in controls
        assert "CC6.3" in controls
        assert "CC6.7" in controls
        assert "CC6.8" in controls
        assert "CC7.2" in controls
        assert "CC7.3" in controls
        # New implementation controls
        assert "CC6.1" in controls
        assert "CC6.6" in controls
        assert "CC7.1" in controls
        assert "CC7.4" in controls
        assert "CC8.1" in controls

        # CC6.7 should have decision evidence
        assert controls["CC6.7"]["evidence_count"] == 3
        assert len(controls["CC6.7"]["evidence"]) == 3

        # CC7.2 should have milestone evidence
        assert controls["CC7.2"]["evidence_count"] == 1

        # New controls should have implementation evidence
        assert controls["CC6.1"]["evidence_count"] == 1
        assert controls["CC6.1"]["evidence"][0]["type"] == "implementation_control"
        assert controls["CC6.6"]["evidence_count"] == 1
        assert controls["CC7.1"]["evidence_count"] == 1
        assert controls["CC7.4"]["evidence_count"] == 1
        assert controls["CC8.1"]["evidence_count"] == 1

    def test_soc2_evidence_genesis(self, initialized_project):
        import asyncio

        from trustplane.project import TrustProject

        project = asyncio.run(TrustProject.load(initialized_project))
        evidence = generate_soc2_evidence(project)

        # CC6.2: Genesis record
        genesis = evidence["controls"]["CC6.2"]
        assert genesis["evidence_count"] == 1
        assert genesis["evidence"][0]["type"] == "genesis_record"
        assert genesis["evidence"][0]["project_name"] == "Compliance Test"


class TestISO27001Evidence:
    def test_iso27001_evidence_structure(self, initialized_project):
        import asyncio

        from trustplane.project import TrustProject

        project = asyncio.run(TrustProject.load(initialized_project))
        evidence = generate_iso27001_evidence(project)

        assert evidence["framework"] == "ISO27001"
        assert evidence["framework_version"] == "2022"
        assert "controls" in evidence

        controls = evidence["controls"]
        # Original record-based controls
        assert "A.9.2" in controls
        assert "A.12.4" in controls
        assert "A.16.1" in controls
        # New implementation controls
        assert "A.6.1" in controls
        assert "A.9.4" in controls
        assert "A.10.1" in controls
        assert "A.12.3" in controls
        assert "A.14.2" in controls
        assert "A.18.1" in controls

    def test_iso27001_decision_mapping(self, initialized_project):
        import asyncio

        from trustplane.project import TrustProject

        project = asyncio.run(TrustProject.load(initialized_project))
        evidence = generate_iso27001_evidence(project)

        # A.9.2: Decision records
        assert evidence["controls"]["A.9.2"]["evidence_count"] == 3


# ---------------------------------------------------------------------------
# Integration tests: Period filtering
# ---------------------------------------------------------------------------


class TestPeriodFiltering:
    def test_period_filters_decisions(self, initialized_project):
        import asyncio

        from trustplane.project import TrustProject

        project = asyncio.run(TrustProject.load(initialized_project))

        # All decisions were just created, so a future period should yield 0
        future = datetime.now(timezone.utc) + timedelta(days=30)
        far_future = future + timedelta(days=30)
        evidence = generate_soc2_evidence(
            project, period_start=future, period_end=far_future
        )
        assert evidence["summary"]["total_decisions"] == 0

    def test_period_includes_current(self, initialized_project):
        import asyncio

        from trustplane.project import TrustProject

        project = asyncio.run(TrustProject.load(initialized_project))

        # Period that includes now should yield all records
        past = datetime.now(timezone.utc) - timedelta(days=1)
        future = datetime.now(timezone.utc) + timedelta(days=1)
        evidence = generate_soc2_evidence(project, period_start=past, period_end=future)
        assert evidence["summary"]["total_decisions"] == 3
        assert evidence["summary"]["total_milestones"] == 1

    def test_no_period_returns_all(self, initialized_project):
        import asyncio

        from trustplane.project import TrustProject

        project = asyncio.run(TrustProject.load(initialized_project))
        evidence = generate_soc2_evidence(project)
        assert evidence["summary"]["total_decisions"] == 3


# ---------------------------------------------------------------------------
# Integration tests: Evidence summary markdown
# ---------------------------------------------------------------------------


class TestEvidenceSummaryMD:
    def test_summary_contains_framework(self, initialized_project):
        import asyncio

        from trustplane.project import TrustProject

        project = asyncio.run(TrustProject.load(initialized_project))
        evidence = generate_soc2_evidence(project)
        md = generate_evidence_summary_md(evidence)

        assert "# SOC2 Evidence Summary" in md
        assert "Compliance Test" in md

    def test_summary_with_verification(self, initialized_project):
        import asyncio

        from trustplane.project import TrustProject

        project = asyncio.run(TrustProject.load(initialized_project))
        evidence = generate_soc2_evidence(project)
        verification = asyncio.run(project.verify())
        md = generate_evidence_summary_md(evidence, verification=verification)

        assert "## Chain Verification" in md
        assert "Chain Valid" in md

    def test_summary_control_sections(self, initialized_project):
        import asyncio

        from trustplane.project import TrustProject

        project = asyncio.run(TrustProject.load(initialized_project))
        evidence = generate_soc2_evidence(project)
        md = generate_evidence_summary_md(evidence)

        assert "## Control Mappings" in md
        assert "CC6.7" in md
        assert "Restriction of Privileged Access" in md


# ---------------------------------------------------------------------------
# CLI integration tests: export --format soc2
# ---------------------------------------------------------------------------


class TestCLIExportSOC2:
    def test_soc2_export_creates_zip(self, runner, initialized_project, tmp_path):
        output_file = str(tmp_path / "evidence.zip")
        result = runner.invoke(
            main,
            [
                "--dir",
                initialized_project,
                "export",
                "--format",
                "soc2",
                "--output",
                output_file,
            ],
        )
        assert result.exit_code == 0, result.output
        assert "SOC2 evidence package" in result.output

        # Verify ZIP exists and is valid
        assert zipfile.is_zipfile(output_file)

    def test_soc2_zip_contains_all_files(self, runner, initialized_project, tmp_path):
        output_file = str(tmp_path / "evidence.zip")
        result = runner.invoke(
            main,
            [
                "--dir",
                initialized_project,
                "export",
                "--format",
                "soc2",
                "--output",
                output_file,
            ],
        )
        assert result.exit_code == 0, result.output

        with zipfile.ZipFile(output_file, "r") as zf:
            names = zf.namelist()
            assert "evidence-summary.md" in names
            assert "control-mapping.json" in names
            assert "decision-log.csv" in names
            assert "violation-log.csv" in names
            assert "chain-verification.json" in names

    def test_soc2_zip_evidence_summary_is_markdown(
        self, runner, initialized_project, tmp_path
    ):
        output_file = str(tmp_path / "evidence.zip")
        runner.invoke(
            main,
            [
                "--dir",
                initialized_project,
                "export",
                "--format",
                "soc2",
                "--output",
                output_file,
            ],
        )

        with zipfile.ZipFile(output_file, "r") as zf:
            md = zf.read("evidence-summary.md").decode("utf-8")
            assert "# SOC2 Evidence Summary" in md
            assert "Compliance Test" in md

    def test_soc2_zip_control_mapping_is_valid_json(
        self, runner, initialized_project, tmp_path
    ):
        output_file = str(tmp_path / "evidence.zip")
        runner.invoke(
            main,
            [
                "--dir",
                initialized_project,
                "export",
                "--format",
                "soc2",
                "--output",
                output_file,
            ],
        )

        with zipfile.ZipFile(output_file, "r") as zf:
            mapping = json.loads(zf.read("control-mapping.json"))
            assert mapping["framework"] == "SOC2"
            assert len(mapping["mappings"]) == 11

    def test_soc2_zip_decision_csv_valid(self, runner, initialized_project, tmp_path):
        output_file = str(tmp_path / "evidence.zip")
        runner.invoke(
            main,
            [
                "--dir",
                initialized_project,
                "export",
                "--format",
                "soc2",
                "--output",
                output_file,
            ],
        )

        with zipfile.ZipFile(output_file, "r") as zf:
            csv_text = zf.read("decision-log.csv").decode("utf-8")
            reader = csv.reader(io.StringIO(csv_text))
            rows = list(reader)
            assert len(rows) == 4  # header + 3 decisions
            assert rows[0][0] == "decision_id"

    def test_soc2_zip_chain_verification_valid(
        self, runner, initialized_project, tmp_path
    ):
        output_file = str(tmp_path / "evidence.zip")
        runner.invoke(
            main,
            [
                "--dir",
                initialized_project,
                "export",
                "--format",
                "soc2",
                "--output",
                output_file,
            ],
        )

        with zipfile.ZipFile(output_file, "r") as zf:
            verification = json.loads(zf.read("chain-verification.json"))
            assert "chain_valid" in verification
            assert "project_name" in verification


class TestCLIExportISO27001:
    def test_iso27001_export_creates_zip(self, runner, initialized_project, tmp_path):
        output_file = str(tmp_path / "iso-evidence.zip")
        result = runner.invoke(
            main,
            [
                "--dir",
                initialized_project,
                "export",
                "--format",
                "iso27001",
                "--output",
                output_file,
            ],
        )
        assert result.exit_code == 0, result.output
        assert "ISO27001 evidence package" in result.output

    def test_iso27001_zip_contents(self, runner, initialized_project, tmp_path):
        output_file = str(tmp_path / "iso-evidence.zip")
        runner.invoke(
            main,
            [
                "--dir",
                initialized_project,
                "export",
                "--format",
                "iso27001",
                "--output",
                output_file,
            ],
        )

        with zipfile.ZipFile(output_file, "r") as zf:
            names = zf.namelist()
            assert "evidence-summary.md" in names
            assert "control-mapping.json" in names

            mapping = json.loads(zf.read("control-mapping.json"))
            assert mapping["framework"] == "ISO27001"
            assert len(mapping["mappings"]) == 9


class TestCLIExportPeriod:
    def test_period_flag_accepted(self, runner, initialized_project, tmp_path):
        output_file = str(tmp_path / "period.zip")
        result = runner.invoke(
            main,
            [
                "--dir",
                initialized_project,
                "export",
                "--format",
                "soc2",
                "--period",
                "2026-01-01:2026-12-31",
                "--output",
                output_file,
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Period:" in result.output

    def test_period_filters_records(self, runner, initialized_project, tmp_path):
        # Use a past period that won't include any records
        output_file = str(tmp_path / "old-period.zip")
        result = runner.invoke(
            main,
            [
                "--dir",
                initialized_project,
                "export",
                "--format",
                "soc2",
                "--period",
                "2020-01-01:2020-12-31",
                "--output",
                output_file,
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Decisions:  0" in result.output

    def test_auto_generated_filename(self, runner, initialized_project):
        """Export without --output should auto-generate filename."""
        import os

        # Change to tmp dir to not pollute workspace
        with runner.isolated_filesystem():
            result = runner.invoke(
                main,
                [
                    "--dir",
                    initialized_project,
                    "export",
                    "--format",
                    "soc2",
                ],
            )
            assert result.exit_code == 0, result.output
            assert "trust-plane-soc2-evidence-" in result.output

    def test_invalid_period_format(self, runner, initialized_project, tmp_path):
        output_file = str(tmp_path / "bad.zip")
        result = runner.invoke(
            main,
            [
                "--dir",
                initialized_project,
                "export",
                "--format",
                "soc2",
                "--period",
                "invalid-period",
                "--output",
                output_file,
            ],
        )
        assert result.exit_code != 0


class TestCLIExportExistingFormats:
    """Verify that existing json/html export formats still work."""

    def test_json_export_still_works(self, runner, initialized_project):
        result = runner.invoke(
            main,
            [
                "--dir",
                initialized_project,
                "export",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# Unit tests: Security pattern evidence mapping
# ---------------------------------------------------------------------------


class TestSecurityPatternEvidence:
    """Verify the SECURITY_PATTERN_EVIDENCE mapping is complete and well-formed."""

    def test_all_11_patterns_present(self):
        """All 11 hardened security patterns must be mapped."""
        assert len(SECURITY_PATTERN_EVIDENCE) == 11
        pattern_ids = {v["pattern_id"] for v in SECURITY_PATTERN_EVIDENCE.values()}
        assert pattern_ids == set(range(1, 12))

    def test_each_pattern_has_required_fields(self):
        """Each pattern entry must have title, description, tests, and controls."""
        required = {
            "pattern_id",
            "title",
            "description",
            "implementation",
            "soc2_controls",
            "iso27001_controls",
            "tests",
        }
        for key, entry in SECURITY_PATTERN_EVIDENCE.items():
            missing = required - set(entry.keys())
            assert not missing, f"Pattern {key} missing fields: {missing}"

    def test_each_pattern_has_nonempty_tests(self):
        """Each pattern must reference at least one test."""
        for key, entry in SECURITY_PATTERN_EVIDENCE.items():
            assert len(entry["tests"]) > 0, f"Pattern {key} has no test references"

    def test_each_pattern_maps_to_controls(self):
        """Each pattern must map to at least one SOC2 or ISO 27001 control."""
        for key, entry in SECURITY_PATTERN_EVIDENCE.items():
            total = len(entry["soc2_controls"]) + len(entry["iso27001_controls"])
            assert total > 0, f"Pattern {key} has no compliance control mappings"

    def test_soc2_control_references_valid(self):
        """All SOC2 control references in patterns must exist in SOC2_CONTROL_MAP."""
        from trustplane.compliance import SOC2_CONTROL_MAP

        for key, entry in SECURITY_PATTERN_EVIDENCE.items():
            for ctrl_id in entry["soc2_controls"]:
                assert ctrl_id in SOC2_CONTROL_MAP, (
                    f"Pattern {key} references unknown SOC2 control: {ctrl_id}"
                )

    def test_iso27001_control_references_valid(self):
        """All ISO 27001 references in patterns must exist in ISO27001_CONTROL_MAP."""
        from trustplane.compliance import ISO27001_CONTROL_MAP

        for key, entry in SECURITY_PATTERN_EVIDENCE.items():
            for ctrl_id in entry["iso27001_controls"]:
                assert ctrl_id in ISO27001_CONTROL_MAP, (
                    f"Pattern {key} references unknown ISO27001 control: {ctrl_id}"
                )


# ---------------------------------------------------------------------------
# Unit tests: Compliance matrix completeness
# ---------------------------------------------------------------------------


class TestComplianceMatrixCompleteness:
    """Verify the compliance matrix covers all implemented security features."""

    def test_soc2_has_11_controls(self):
        """SOC2 map should have 11 controls after red-team hardening."""
        from trustplane.compliance import SOC2_CONTROL_MAP

        assert len(SOC2_CONTROL_MAP) == 11

    def test_iso27001_has_9_controls(self):
        """ISO 27001 map should have 9 controls after enterprise features."""
        from trustplane.compliance import ISO27001_CONTROL_MAP

        assert len(ISO27001_CONTROL_MAP) == 9

    def test_soc2_controls_have_evidence_sources(self):
        """All SOC2 controls must reference evidence source files."""
        from trustplane.compliance import SOC2_CONTROL_MAP

        for ctrl_id, ctrl in SOC2_CONTROL_MAP.items():
            assert "evidence_sources" in ctrl, (
                f"SOC2 control {ctrl_id} missing evidence_sources"
            )
            assert len(ctrl["evidence_sources"]) > 0, (
                f"SOC2 control {ctrl_id} has empty evidence_sources"
            )

    def test_iso27001_controls_have_evidence_sources(self):
        """All ISO 27001 controls must reference evidence source files."""
        from trustplane.compliance import ISO27001_CONTROL_MAP

        for ctrl_id, ctrl in ISO27001_CONTROL_MAP.items():
            assert "evidence_sources" in ctrl, (
                f"ISO27001 control {ctrl_id} missing evidence_sources"
            )
            assert len(ctrl["evidence_sources"]) > 0, (
                f"ISO27001 control {ctrl_id} has empty evidence_sources"
            )

    def test_soc2_controls_have_test_sources(self):
        """All SOC2 controls must reference test files."""
        from trustplane.compliance import SOC2_CONTROL_MAP

        for ctrl_id, ctrl in SOC2_CONTROL_MAP.items():
            assert "test_sources" in ctrl, (
                f"SOC2 control {ctrl_id} missing test_sources"
            )
            assert len(ctrl["test_sources"]) > 0, (
                f"SOC2 control {ctrl_id} has empty test_sources"
            )

    def test_iso27001_controls_have_test_sources(self):
        """All ISO 27001 controls must reference test files."""
        from trustplane.compliance import ISO27001_CONTROL_MAP

        for ctrl_id, ctrl in ISO27001_CONTROL_MAP.items():
            assert "test_sources" in ctrl, (
                f"ISO27001 control {ctrl_id} missing test_sources"
            )
            assert len(ctrl["test_sources"]) > 0, (
                f"ISO27001 control {ctrl_id} has empty test_sources"
            )

    def test_evidence_source_files_exist(self):
        """All evidence_sources must point to real files in the codebase."""
        from pathlib import Path

        from trustplane.compliance import ISO27001_CONTROL_MAP, SOC2_CONTROL_MAP

        pkg_root = Path(__file__).resolve().parent.parent.parent

        all_sources: set[str] = set()
        for ctrl in SOC2_CONTROL_MAP.values():
            all_sources.update(ctrl.get("evidence_sources", []))
        for ctrl in ISO27001_CONTROL_MAP.values():
            all_sources.update(ctrl.get("evidence_sources", []))

        for source in sorted(all_sources):
            source_path = pkg_root / source
            assert source_path.exists(), (
                f"Evidence source file does not exist: {source} "
                f"(resolved to {source_path})"
            )

    def test_test_source_files_exist(self):
        """All test_sources must point to real test files in the codebase.

        Handles both plain paths (tests/test_foo.py) and pytest node IDs
        (tests/test_foo.py::TestBar).
        """
        from pathlib import Path

        from trustplane.compliance import ISO27001_CONTROL_MAP, SOC2_CONTROL_MAP

        pkg_root = Path(__file__).resolve().parent.parent.parent

        all_tests: set[str] = set()
        for ctrl in SOC2_CONTROL_MAP.values():
            all_tests.update(ctrl.get("test_sources", []))
        for ctrl in ISO27001_CONTROL_MAP.values():
            all_tests.update(ctrl.get("test_sources", []))

        for test_ref in sorted(all_tests):
            # Strip pytest node ID suffix (::TestClass::test_method)
            file_path = test_ref.split("::")[0]
            test_path = pkg_root / file_path
            assert test_path.exists(), (
                f"Test source file does not exist: {file_path} "
                f"(resolved to {test_path})"
            )

    def test_security_pattern_test_files_exist(self):
        """All test references in SECURITY_PATTERN_EVIDENCE must exist."""
        from pathlib import Path

        pkg_root = Path(__file__).resolve().parent.parent.parent

        for key, entry in SECURITY_PATTERN_EVIDENCE.items():
            for test_ref in entry["tests"]:
                file_path = test_ref.split("::")[0]
                test_path = pkg_root / file_path
                assert test_path.exists(), (
                    f"Pattern {key} references nonexistent test: {file_path} "
                    f"(resolved to {test_path})"
                )
