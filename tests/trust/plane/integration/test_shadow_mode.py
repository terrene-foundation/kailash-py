# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for shadow/strict enforcement mode switching."""

import json

import pytest

from kailash.trust.enforce.strict import Verdict
from kailash.trust.plane.models import (
    ConstraintEnvelope,
    DecisionRecord,
    DecisionType,
    OperationalConstraints,
)
from kailash.trust.plane.project import TrustProject


@pytest.fixture
def trust_dir(tmp_path):
    return tmp_path / "trust-plane"


class TestShadowMode:
    async def test_default_is_strict(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Default Mode",
            author="Alice",
        )
        assert project.enforcement_mode == "strict"

    async def test_switch_to_shadow(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Shadow Test",
            author="Bob",
        )
        mode = await project.switch_enforcement("shadow", "Calibrating constraints")
        assert mode == "shadow"
        assert project.enforcement_mode == "shadow"

    async def test_switch_creates_audit_anchor(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Anchor Test",
            author="Carol",
        )
        await project.switch_enforcement("shadow", "Testing")
        anchor_files = sorted((trust_dir / "anchors").glob("*.json"))
        assert len(anchor_files) == 1
        with open(anchor_files[0]) as f:
            data = json.load(f)
        assert data["action"] == "enforcement_mode_change"
        assert data["context"]["previous_mode"] == "strict"
        assert data["context"]["new_mode"] == "shadow"

    async def test_shadow_mode_never_blocks(self, trust_dir):
        """Shadow mode returns AUTO_APPROVED even for blocked actions."""
        env = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=["fabricate"]),
            signed_by="Dave",
        )
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Shadow Block",
            author="Dave",
            constraint_envelope=env,
        )
        await project.switch_enforcement("shadow", "Testing")

        # In shadow mode, check() should still block at the envelope level
        # (envelope checks happen before enforcer) for blocked_actions
        verdict = project.check("record_decision", {"decision_type": "fabricate"})
        assert verdict == Verdict.BLOCKED  # Envelope check catches it

        # But for non-blocked actions that would normally be checked by enforcer
        verdict = project.check("record_decision", {"decision_type": "scope"})
        assert verdict == Verdict.AUTO_APPROVED

    async def test_switch_back_to_strict(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Back to Strict",
            author="Eve",
        )
        await project.switch_enforcement("shadow", "Testing")
        await project.switch_enforcement("strict", "Done calibrating")
        assert project.enforcement_mode == "strict"

    async def test_mode_persists_across_load(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Persist Mode",
            author="Frank",
        )
        await project.switch_enforcement("shadow", "Testing")

        loaded = await TrustProject.load(trust_dir)
        assert loaded.enforcement_mode == "shadow"

    async def test_invalid_mode_raises(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Invalid",
            author="Grace",
        )
        with pytest.raises(ValueError, match="Invalid mode"):
            await project.switch_enforcement("turbo", "bad")

    async def test_same_mode_is_noop(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Noop",
            author="Heidi",
        )
        mode = await project.switch_enforcement("strict", "Already strict")
        assert mode == "strict"
        # No anchor created
        anchor_files = list((trust_dir / "anchors").glob("*.json"))
        assert len(anchor_files) == 0

    async def test_shadow_report(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Report Test",
            author="Ivan",
        )
        report = project.shadow_report()
        assert "Shadow Enforcement Report" in report

    async def test_verify_passes_with_mode_switch(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Verify Mode",
            author="Judy",
        )
        await project.switch_enforcement("shadow", "Test")
        await project.switch_enforcement("strict", "Done")
        report = await project.verify()
        assert report["chain_valid"] is True
