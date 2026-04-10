# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for trust posture tracking."""

import json

import pytest
from kailash.trust.plane.project import TrustProject
from kailash.trust.posture.postures import TrustPosture


@pytest.fixture
def trust_dir(tmp_path):
    return tmp_path / "trust-plane"


class TestPosture:
    async def test_default_posture_is_supervised(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Posture Test",
            author="Alice",
        )
        assert project.posture == TrustPosture.SUPERVISED

    async def test_transition_posture(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Transition Test",
            author="Bob",
        )
        new = await project.transition_posture(
            TrustPosture.SUPERVISED,
            reason="Trust established through session work",
        )
        assert new == TrustPosture.SUPERVISED
        assert project.posture == TrustPosture.SUPERVISED

    async def test_posture_transition_creates_anchor(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Anchor Test",
            author="Carol",
        )
        await project.transition_posture(
            TrustPosture.SUPERVISED,
            reason="Testing audit trail",
        )
        anchor_files = sorted((trust_dir / "anchors").glob("*.json"))
        assert len(anchor_files) == 1

        with open(anchor_files[0]) as f:
            data = json.load(f)
        assert data["action"] == "posture_transition"
        assert data["context"]["previous_posture"] == "supervised"
        assert data["context"]["new_posture"] == "supervised"
        assert data["context"]["reason"] == "Testing audit trail"

    async def test_posture_persists_across_load(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Persist Posture",
            author="Dave",
        )
        await project.transition_posture(
            TrustPosture.SUPERVISED,
            reason="Persisting",
        )
        loaded = await TrustProject.load(trust_dir)
        assert loaded.posture == TrustPosture.SUPERVISED

    async def test_downgrade_posture(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Downgrade Test",
            author="Eve",
        )
        await project.transition_posture(
            TrustPosture.SUPERVISED,
            reason="Upgrading first",
        )
        await project.transition_posture(
            TrustPosture.TOOL,
            reason="Downgrading back",
        )
        assert project.posture == TrustPosture.TOOL

    async def test_emergency_reset_to_pseudo_agent(self, trust_dir):
        """Emergency reset drops posture to PSEUDO_AGENT regardless of current level."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Emergency Test",
            author="Grace",
        )
        await project.transition_posture(
            TrustPosture.SUPERVISED,
            reason="Upgrading first",
        )
        await project.transition_posture(
            TrustPosture.PSEUDO,
            reason="Emergency: trust violation detected",
        )
        assert project.posture == TrustPosture.PSEUDO

        # Verify anchor trail records the emergency reset
        anchor_files = sorted((trust_dir / "anchors").glob("*.json"))
        # Two transitions = 2 anchors
        assert len(anchor_files) == 2

    async def test_verify_with_posture_transitions(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Verify Posture",
            author="Frank",
        )
        await project.transition_posture(
            TrustPosture.SUPERVISED,
            reason="Testing verify",
        )
        report = await project.verify()
        assert report["chain_valid"] is True
        assert report["integrity_issues"] == []
        assert report["trust_posture"] == "supervised"
        assert report["verification_level"] == "STANDARD"

    async def test_verify_reports_supervised_as_standard(self, trust_dir):
        """SUPERVISED posture (default) maps to STANDARD verification level."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Level Test",
            author="Gina",
        )
        report = await project.verify()
        assert report["trust_posture"] == "supervised"
        assert report["verification_level"] == "STANDARD"
