# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for TrustPlane migration from pre-v0.2.1 to FilesystemStore."""

import json
import shutil

import pytest

from kailash.trust.plane.migrate import migrate_project
from kailash.trust.plane.project import TrustProject
from kailash.trust.plane.models import DecisionRecord, DecisionType


@pytest.fixture
def trust_dir(tmp_path):
    return tmp_path / "trust-plane"


class TestMigrate:
    async def test_migrate_fresh_project_is_noop(self, trust_dir):
        """A project created with v0.2.1+ already has FilesystemStore."""
        await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Fresh",
            author="Alice",
        )
        result = await migrate_project(trust_dir)
        # chains/ exists with data, so it should mark as migrated
        assert result["status"] == "marked"

    async def test_migrate_already_migrated(self, trust_dir):
        """Running migrate twice is a no-op."""
        await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Double",
            author="Bob",
        )
        await migrate_project(trust_dir)
        result = await migrate_project(trust_dir)
        assert result["status"] == "already_migrated"

    async def test_migrate_nonexistent_raises(self, trust_dir):
        """Migrating a nonexistent project raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            await migrate_project(trust_dir)

    async def test_migrate_pre_filesystem_project(self, trust_dir):
        """Simulate a pre-v0.2.1 project (no chains/ dir)."""
        # Create a project normally, then delete chains/ to simulate old format
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Legacy",
            author="Carol",
        )
        await project.record_decision(
            DecisionRecord(
                decision_type=DecisionType.SCOPE,
                decision="Old decision",
                rationale="Before migration",
            )
        )

        # Remove chains/ to simulate pre-FilesystemStore
        shutil.rmtree(trust_dir / "chains")
        assert not (trust_dir / "chains").exists()

        # Remove parent_anchor_id from anchors to simulate old format
        for af in sorted((trust_dir / "anchors").glob("*.json")):
            with open(af) as f:
                data = json.load(f)
            data.pop("parent_anchor_id", None)
            if "context" in data:
                data["context"].pop("parent_anchor_id", None)
            with open(af, "w") as f:
                json.dump(data, f, indent=2)

        result = await migrate_project(trust_dir)
        assert result["status"] == "migrated"
        assert result["anchors_updated"] == 1
        assert (trust_dir / "chains").exists()

    async def test_migrate_then_verify(self, trust_dir):
        """After migration, verify passes."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Verify After Migrate",
            author="Dave",
        )
        await project.record_decision(
            DecisionRecord(
                decision_type=DecisionType.SCOPE,
                decision="Pre-migration decision",
                rationale="Testing migration",
            )
        )

        # Simulate pre-v0.2.1 by removing chains/
        shutil.rmtree(trust_dir / "chains")

        await migrate_project(trust_dir)

        # Load and verify
        loaded = await TrustProject.load(trust_dir)
        report = await loaded.verify()
        assert report["chain_valid"] is True

    async def test_migrate_missing_keys_fails(self, trust_dir):
        """Migration without keys/ should fail gracefully."""
        await TrustProject.create(
            trust_dir=trust_dir,
            project_name="No Keys",
            author="Eve",
        )
        shutil.rmtree(trust_dir / "chains")
        shutil.rmtree(trust_dir / "keys")

        result = await migrate_project(trust_dir)
        assert result["status"] == "error"
        assert "keys" in result["message"].lower()

    async def test_migrate_missing_genesis_fails(self, trust_dir):
        """Migration without genesis.json should fail gracefully."""
        await TrustProject.create(
            trust_dir=trust_dir,
            project_name="No Genesis",
            author="Frank",
        )
        shutil.rmtree(trust_dir / "chains")
        (trust_dir / "genesis.json").unlink()

        result = await migrate_project(trust_dir)
        assert result["status"] == "error"
        assert "genesis" in result["message"].lower()

    async def test_migrate_preserves_decision_content(self, trust_dir):
        """Migration preserves all decision data."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Preserve Content",
            author="Grace",
        )
        await project.record_decision(
            DecisionRecord(
                decision_type=DecisionType.ARGUMENT,
                decision="Important argument",
                rationale="Must survive migration",
                alternatives=["Option A", "Option B"],
                confidence=0.95,
            )
        )

        shutil.rmtree(trust_dir / "chains")
        await migrate_project(trust_dir)

        loaded = await TrustProject.load(trust_dir)
        decisions = loaded.get_decisions()
        assert len(decisions) == 1
        assert decisions[0].decision == "Important argument"
        assert decisions[0].rationale == "Must survive migration"
        assert decisions[0].alternatives == ["Option A", "Option B"]
        assert decisions[0].confidence == 0.95
