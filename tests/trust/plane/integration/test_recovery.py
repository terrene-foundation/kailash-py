# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for error recovery and graceful degradation."""

import json

import pytest

from kailash.trust.plane.models import DecisionRecord, DecisionType
from kailash.trust.plane.project import TrustProject


@pytest.fixture
def trust_dir(tmp_path):
    return tmp_path / "trust-plane"


class TestAbandonedSession:
    async def test_abandon_session_creates_anchor(self, trust_dir):
        """Abandoning a session creates a session_abandoned anchor."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Abandon Test",
            author="Alice",
        )
        session = await project.start_session()
        summary = await project.abandon_session(reason="Process killed")

        assert summary["abandoned"] is True
        assert summary["abandon_reason"] == "Process killed"
        assert project.session is None

        # Check anchor was created
        anchor_files = sorted((trust_dir / "anchors").glob("*.json"))
        # session_start + session_abandoned
        assert len(anchor_files) == 2
        with open(anchor_files[1]) as f:
            data = json.load(f)
        assert data["action"] == "session_abandoned"

    async def test_abandon_without_session_raises(self, trust_dir):
        """Cannot abandon if no session is active."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="No Session",
            author="Bob",
        )
        with pytest.raises(RuntimeError, match="No active session"):
            await project.abandon_session()

    async def test_session_file_removed_on_abandon(self, trust_dir):
        """session.json is cleaned up on abandon."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Cleanup Test",
            author="Carol",
        )
        await project.start_session()
        assert (trust_dir / "session.json").exists()

        await project.abandon_session()
        assert not (trust_dir / "session.json").exists()

    async def test_verify_passes_after_abandon(self, trust_dir):
        """Chain remains valid after session abandonment."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Verify Abandon",
            author="Dave",
        )
        await project.start_session()
        await project.record_decision(
            DecisionRecord(
                decision_type=DecisionType.SCOPE,
                decision="Before abandon",
                rationale="Testing",
            )
        )
        await project.abandon_session(reason="Testing verify")

        report = await project.verify()
        assert report["chain_valid"] is True


class TestRepair:
    async def test_repair_no_issues(self, trust_dir):
        """Repair on clean project finds nothing."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Clean",
            author="Alice",
        )
        result = await project.repair()
        assert result["issues_found"] == []
        assert result["issues_fixed"] == []

    async def test_repair_finds_orphaned_session(self, trust_dir):
        """Repair detects orphaned session.json."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Orphan",
            author="Bob",
        )
        # Create orphaned session file manually
        (trust_dir / "session.json").write_text(
            json.dumps({"session_id": "orphan", "active": False})
        )

        result = await project.repair(dry_run=True)
        assert any("Orphaned" in i for i in result["issues_found"])
        # Dry run — file should still exist
        assert (trust_dir / "session.json").exists()

        # Now fix
        result = await project.repair(dry_run=False)
        assert any("Removed" in i for i in result["issues_fixed"])
        assert not (trust_dir / "session.json").exists()

    async def test_repair_fixes_audit_count_mismatch(self, trust_dir):
        """Repair fixes manifest audit count when it diverges from files."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Count Fix",
            author="Carol",
        )
        await project.record_decision(
            DecisionRecord(
                decision_type=DecisionType.SCOPE,
                decision="Decision one",
                rationale="Testing count",
            )
        )
        # Manually corrupt the manifest audit count
        manifest_path = trust_dir / "manifest.json"
        with open(manifest_path) as f:
            data = json.load(f)
        data["total_audits"] = 99
        with open(manifest_path, "w") as f:
            json.dump(data, f)

        # Reload to pick up corrupted count
        project = await TrustProject.load(trust_dir)
        result = await project.repair()
        assert any("audit count mismatch" in i for i in result["issues_found"])
        assert any("Updated manifest" in i for i in result["issues_fixed"])

    async def test_repair_dry_run_makes_no_changes(self, trust_dir):
        """Dry run reports issues but fixes nothing."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Dry Run",
            author="Dave",
        )
        # Create orphaned session
        (trust_dir / "session.json").write_text("{}")

        result = await project.repair(dry_run=True)
        assert len(result["issues_found"]) > 0
        assert result["issues_fixed"] == []
        assert result["dry_run"] is True
        # File still exists
        assert (trust_dir / "session.json").exists()


class TestEnforcerFallback:
    async def test_operations_work_without_enforcer(self, trust_dir):
        """If enforcer fails, operations degrade to AUTO_APPROVED."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Fallback Test",
            author="Eve",
        )
        # Sabotage the enforcer to make it throw
        project._enforcer = None  # type: ignore

        # check() should catch the AttributeError and return AUTO_APPROVED
        from kailash.trust.enforce.strict import Verdict

        verdict = project.check("anything", {})
        assert verdict == Verdict.AUTO_APPROVED
