# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for AuditSession — session-scoped EATP audit context."""

import json

import pytest

from trustplane.models import DecisionRecord, DecisionType
from trustplane.project import TrustProject
from trustplane.session import AuditSession


@pytest.fixture
def trust_dir(tmp_path):
    return tmp_path / "trust-plane"


class TestAuditSessionModel:
    def test_create_session(self):
        session = AuditSession()
        assert session.session_id.startswith("sess-")
        assert session.is_active
        assert session.action_count == 0

    def test_end_session(self):
        session = AuditSession()
        session.end()
        assert not session.is_active
        assert session.ended_at is not None

    def test_record_action(self):
        session = AuditSession()
        session.record_action("record_decision")
        session.record_action("record_decision")
        session.record_action("create_milestone")
        assert session.action_count == 3
        assert session.decision_count == 2
        assert session.milestone_count == 1

    def test_roundtrip(self):
        session = AuditSession()
        session.record_action("record_decision")
        data = session.to_dict()
        restored = AuditSession.from_dict(data)
        assert restored.session_id == session.session_id
        assert restored.action_count == 1
        assert restored.is_active

    def test_context_data(self):
        session = AuditSession()
        session.record_action("record_decision")
        ctx = session.context_data()
        assert "session_id" in ctx
        assert ctx["session_action_count"] == 1

    def test_summary(self):
        session = AuditSession()
        session.record_action("record_decision")
        session.record_action("create_milestone")
        session.end()
        summary = session.summary()
        assert summary["decisions"] == 1
        assert summary["milestones"] == 1
        assert summary["total_actions"] == 2
        assert summary["ended_at"] is not None


class TestSessionInProject:
    async def test_start_session(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Session Test",
            author="Alice",
        )
        session = await project.start_session()
        assert session.is_active
        assert project.session is not None
        assert project.session.session_id == session.session_id

    async def test_end_session(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="End Session Test",
            author="Bob",
        )
        await project.start_session()
        summary = await project.end_session()
        assert summary["total_actions"] == 0
        assert project.session is None

    async def test_session_anchors_created(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Anchor Test",
            author="Carol",
        )
        await project.start_session()
        await project.end_session()

        # Should have session_start + session_complete anchors
        anchor_files = sorted((trust_dir / "anchors").glob("*.json"))
        assert len(anchor_files) == 2

        with open(anchor_files[0]) as f:
            start = json.load(f)
        assert start["action"] == "session_start"

        with open(anchor_files[1]) as f:
            end = json.load(f)
        assert end["action"] == "session_complete"

    async def test_decisions_within_session(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Decision Session",
            author="Dave",
        )
        session = await project.start_session()
        await project.record_decision(
            DecisionRecord(
                decision_type=DecisionType.SCOPE,
                decision="In session",
                rationale="Testing session context",
            )
        )
        summary = await project.end_session()

        assert summary["decisions"] == 1
        assert summary["total_actions"] == 1

        # Decision anchor should include session_id
        anchor_files = sorted((trust_dir / "anchors").glob("*.json"))
        # session_start + decision + session_complete = 3
        assert len(anchor_files) == 3

        with open(anchor_files[1]) as f:
            decision_anchor = json.load(f)
        assert decision_anchor["context"]["session_id"] == session.session_id

    async def test_verify_with_session(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Verify Session",
            author="Eve",
        )
        await project.start_session()
        await project.record_decision(
            DecisionRecord(
                decision_type=DecisionType.DESIGN,
                decision="Session decision",
                rationale="Testing verify",
            )
        )
        await project.end_session()

        report = await project.verify()
        assert report["chain_valid"] is True
        assert report["integrity_issues"] == []

    async def test_double_start_raises(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Double Start",
            author="Frank",
        )
        await project.start_session()
        with pytest.raises(RuntimeError, match="already active"):
            await project.start_session()

    async def test_end_without_start_raises(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="No Start",
            author="Grace",
        )
        with pytest.raises(RuntimeError, match="No active session"):
            await project.end_session()

    async def test_session_persists_across_load(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Persist Session",
            author="Heidi",
        )
        session = await project.start_session()
        session_id = session.session_id

        # Load from disk — session should be restored
        loaded = await TrustProject.load(trust_dir)
        assert loaded.session is not None
        assert loaded.session.session_id == session_id
        assert loaded.session.is_active

    async def test_session_file_removed_after_end(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Remove File",
            author="Ivan",
        )
        await project.start_session()
        assert (trust_dir / "session.json").exists()

        await project.end_session()
        assert not (trust_dir / "session.json").exists()

    async def test_decisions_work_without_session(self, trust_dir):
        """Decisions work fine without any session."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="No Session",
            author="Judy",
        )
        await project.record_decision(
            DecisionRecord(
                decision_type=DecisionType.SCOPE,
                decision="No session needed",
                rationale="Testing sessionless",
            )
        )
        assert project.manifest.total_decisions == 1
        assert project.session is None
