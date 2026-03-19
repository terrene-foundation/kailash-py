# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for TrustProject — EATP-backed project lifecycle."""

import json

import pytest

from trustplane.models import DecisionRecord, DecisionType, ReviewRequirement
from trustplane.project import TrustProject


@pytest.fixture
def trust_dir(tmp_path):
    return tmp_path / "trust-plane"


class TestTrustProjectCreate:
    async def test_create_project(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Test Project",
            author="Alice",
        )
        assert project.manifest.project_name == "Test Project"
        assert project.manifest.author == "Alice"
        assert project.manifest.genesis_id != ""
        assert project.manifest.chain_hash != ""

    async def test_create_persists_genesis(self, trust_dir):
        await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Test",
            author="Bob",
        )
        genesis_path = trust_dir / "genesis.json"
        assert genesis_path.exists()
        with open(genesis_path) as f:
            genesis = json.load(f)
        assert "genesis_id" in genesis
        assert "public_key" in genesis

    async def test_create_persists_manifest(self, trust_dir):
        await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Test",
            author="Carol",
        )
        manifest_path = trust_dir / "manifest.json"
        assert manifest_path.exists()
        with open(manifest_path) as f:
            manifest = json.load(f)
        assert manifest["project_name"] == "Test"
        assert manifest["author"] == "Carol"

    async def test_create_with_constraints(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Constrained",
            author="Dave",
            constraints=["no_fabrication", "honest_limitations"],
        )
        assert project.manifest.constraints == ["no_fabrication", "honest_limitations"]

    async def test_create_directory_structure(self, trust_dir):
        await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Test",
            author="Eve",
        )
        assert (trust_dir / "decisions").is_dir()
        assert (trust_dir / "milestones").is_dir()
        assert (trust_dir / "anchors").is_dir()


class TestTrustProjectLoad:
    async def test_load_existing(self, trust_dir):
        original = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Reload Test",
            author="Frank",
        )
        loaded = await TrustProject.load(trust_dir)
        assert loaded.manifest.project_name == original.manifest.project_name
        assert loaded.manifest.project_id == original.manifest.project_id

    async def test_load_nonexistent_raises(self, trust_dir):
        with pytest.raises(FileNotFoundError):
            await TrustProject.load(trust_dir)


class TestRecordDecision:
    async def test_record_decision(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Decision Test",
            author="Grace",
        )
        decision_id = await project.record_decision(
            DecisionRecord(
                decision_type=DecisionType.SCOPE,
                decision="Focus on philosophy",
                rationale="Clean separation",
            )
        )
        assert decision_id.startswith("dec-")
        assert project.manifest.total_decisions == 1
        assert project.manifest.total_audits == 1

    async def test_decision_persisted(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Persist Test",
            author="Heidi",
        )
        await project.record_decision(
            DecisionRecord(
                decision_type=DecisionType.ARGUMENT,
                decision="Mirror Thesis is central",
                rationale="Differentiates CARE",
            )
        )
        decision_files = list((trust_dir / "decisions").glob("*.json"))
        assert len(decision_files) == 1

        with open(decision_files[0]) as f:
            data = json.load(f)
        assert data["decision"] == "Mirror Thesis is central"
        assert "eatp_anchor_id" in data
        assert "content_hash" in data

    async def test_anchor_persisted(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Anchor Test",
            author="Ivan",
        )
        await project.record_decision(
            DecisionRecord(
                decision_type=DecisionType.LITERATURE,
                decision="Cite Ostrom",
                rationale="Commons governance",
            )
        )
        anchor_files = list((trust_dir / "anchors").glob("*.json"))
        assert len(anchor_files) == 1

        with open(anchor_files[0]) as f:
            data = json.load(f)
        assert data["action"] == "record_decision"
        assert "reasoning_trace" in data

    async def test_multiple_decisions(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Multi Test",
            author="Judy",
        )
        for i in range(3):
            await project.record_decision(
                DecisionRecord(
                    decision_type=DecisionType.SCOPE,
                    decision=f"Decision {i}",
                    rationale=f"Reason {i}",
                )
            )
        assert project.manifest.total_decisions == 3
        assert project.manifest.total_audits == 3
        assert len(project.get_decisions()) == 3


class TestRecordMilestone:
    async def test_record_milestone(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Milestone Test",
            author="Karl",
        )
        ms_id = await project.record_milestone(
            version="v0.1",
            description="First draft",
        )
        assert ms_id.startswith("ms-")
        assert project.manifest.total_milestones == 1

    async def test_milestone_with_file_hash(self, trust_dir, tmp_path):
        # Create a file to hash
        test_file = tmp_path / "paper.md"
        test_file.write_text("# My Paper\n\nContent here.")

        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="File Hash Test",
            author="Laura",
        )
        await project.record_milestone(
            version="v0.1",
            description="Draft with hash",
            file_path=str(test_file),
        )
        milestone_files = list((trust_dir / "milestones").glob("*.json"))
        with open(milestone_files[0]) as f:
            data = json.load(f)
        assert data["file_hash"] != ""


class TestVerify:
    async def test_verify_clean_project(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Verify Test",
            author="Mallory",
        )
        report = await project.verify()
        assert report["chain_valid"] is True
        assert report["integrity_issues"] == []

    async def test_verify_with_decisions(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Verify Decisions",
            author="Nancy",
        )
        await project.record_decision(
            DecisionRecord(
                decision_type=DecisionType.SCOPE,
                decision="Test decision",
                rationale="Test rationale",
            )
        )
        report = await project.verify()
        assert report["chain_valid"] is True
        assert report["total_decisions"] == 1
        assert report["integrity_issues"] == []

    async def test_verify_detects_tamper(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Tamper Test",
            author="Oscar",
        )
        await project.record_decision(
            DecisionRecord(
                decision_type=DecisionType.SCOPE,
                decision="Original decision",
                rationale="Original rationale",
            )
        )

        # Tamper with the decision file
        decision_files = list((trust_dir / "decisions").glob("*.json"))
        with open(decision_files[0]) as f:
            data = json.load(f)
        data["decision"] = "TAMPERED DECISION"
        with open(decision_files[0], "w") as f:
            json.dump(data, f)

        report = await project.verify()
        assert len(report["integrity_issues"]) == 1
        assert "hash mismatch" in report["integrity_issues"][0]


class TestGetRecords:
    async def test_get_decisions_empty(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Empty Test",
            author="Pat",
        )
        assert project.get_decisions() == []

    async def test_get_milestones_empty(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Empty MS Test",
            author="Quinn",
        )
        assert project.get_milestones() == []


class TestKeyPersistence:
    async def test_keys_persisted_on_create(self, trust_dir):
        await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Key Test",
            author="Rita",
        )
        keys_dir = trust_dir / "keys"
        assert (keys_dir / "private.key").exists()
        assert (keys_dir / "public.key").exists()

    async def test_private_key_permissions(self, trust_dir):
        import os
        import stat

        await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Perm Test",
            author="Sam",
        )
        priv_path = trust_dir / "keys" / "private.key"
        mode = os.stat(str(priv_path)).st_mode
        # Owner read+write only (600)
        assert mode & stat.S_IRWXU == stat.S_IRUSR | stat.S_IWUSR
        assert mode & stat.S_IRWXG == 0
        assert mode & stat.S_IRWXO == 0

    async def test_load_uses_persisted_keys(self, trust_dir):
        original = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Reload Key Test",
            author="Tina",
        )
        original_pub = original.manifest.authority_public_key

        # Read the persisted public key
        stored_pub = (trust_dir / "keys" / "public.key").read_text()
        assert stored_pub == original_pub

        # Load and verify same key is used
        loaded = await TrustProject.load(trust_dir)
        assert loaded.manifest.authority_public_key == original_pub

    async def test_load_survives_across_sessions(self, trust_dir):
        """Simulate cross-session: create, record decision, load, record another."""
        project1 = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Session Test",
            author="Uma",
        )
        await project1.record_decision(
            DecisionRecord(
                decision_type=DecisionType.SCOPE,
                decision="First session decision",
                rationale="Testing cross-session",
            )
        )

        # "New session" — load from disk
        project2 = await TrustProject.load(trust_dir)
        await project2.record_decision(
            DecisionRecord(
                decision_type=DecisionType.SCOPE,
                decision="Second session decision",
                rationale="Testing cross-session",
            )
        )

        assert project2.manifest.total_decisions == 2
        report = await project2.verify()
        assert report["chain_valid"] is True
        assert report["integrity_issues"] == []

    async def test_backward_compat_no_keys(self, trust_dir):
        """Projects created before key persistence get new keys on load."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Legacy Test",
            author="Victor",
        )
        # Simulate pre-key-persistence project by deleting keys
        import shutil

        shutil.rmtree(trust_dir / "keys")
        assert not (trust_dir / "keys").exists()

        # Load should succeed and create new keys
        loaded = await TrustProject.load(trust_dir)
        assert loaded.manifest.project_name == "Legacy Test"
        assert (trust_dir / "keys" / "private.key").exists()


class TestVerifyKeyIntegrity:
    async def test_verify_detects_missing_keys(self, trust_dir):
        import shutil

        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Missing Key Test",
            author="Wendy",
        )
        shutil.rmtree(trust_dir / "keys")

        report = await project.verify()
        assert any("keys missing" in i for i in report["integrity_issues"])

    async def test_verify_detects_swapped_public_key(self, trust_dir):
        from eatp.crypto import generate_keypair

        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Swap Key Test",
            author="Xander",
        )
        # Swap the public key with a different one
        _, fake_pub = generate_keypair()
        (trust_dir / "keys" / "public.key").write_text(fake_pub)

        report = await project.verify()
        assert any("public key mismatch" in i for i in report["integrity_issues"])


class TestCustomDecisionTypes:
    async def test_record_custom_type(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Custom Type Test",
            author="Yara",
        )
        decision_id = await project.record_decision(
            DecisionRecord(
                decision_type="compliance_ruling",
                decision="Accept residual risk",
                rationale="Within tolerance bands",
            )
        )
        assert decision_id.startswith("dec-")

        # Verify it persisted correctly
        decisions = project.get_decisions()
        assert len(decisions) == 1
        assert decisions[0].decision_type == "compliance_ruling"

    async def test_verify_with_custom_types(self, trust_dir):
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Custom Verify Test",
            author="Zara",
        )
        await project.record_decision(
            DecisionRecord(
                decision_type="financial_allocation",
                decision="Allocate budget",
                rationale="Approved",
            )
        )
        report = await project.verify()
        assert report["chain_valid"] is True
        assert report["integrity_issues"] == []


class TestChainContinuity:
    async def test_cross_session_chain(self, trust_dir):
        """create → decide → load → decide → verify — all in one chain."""
        project1 = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Chain Test",
            author="Alpha",
        )
        await project1.record_decision(
            DecisionRecord(
                decision_type=DecisionType.SCOPE,
                decision="Session 1 decision",
                rationale="First session",
            )
        )

        # Simulate new session
        project2 = await TrustProject.load(trust_dir)
        await project2.record_decision(
            DecisionRecord(
                decision_type=DecisionType.DESIGN,
                decision="Session 2 decision",
                rationale="Second session",
            )
        )

        report = await project2.verify()
        assert report["chain_valid"] is True
        assert report["total_decisions"] == 2
        assert report["total_anchors"] == 2
        assert report["integrity_issues"] == []

    async def test_parent_anchor_chain_unbroken(self, trust_dir):
        """5 decisions form an unbroken parent_anchor_id chain."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Parent Chain Test",
            author="Beta",
        )
        for i in range(5):
            await project.record_decision(
                DecisionRecord(
                    decision_type=DecisionType.SCOPE,
                    decision=f"Decision {i}",
                    rationale=f"Reason {i}",
                )
            )

        # Walk the anchor files and verify parent chain
        anchor_files = sorted((trust_dir / "anchors").glob("*.json"))
        assert len(anchor_files) == 5

        expected_parent = None
        for af in anchor_files:
            with open(af) as f:
                data = json.load(f)
            actual_parent = data.get("parent_anchor_id") or data.get("context", {}).get(
                "parent_anchor_id"
            )
            assert actual_parent == expected_parent, (
                f"Anchor {af.name}: expected parent {expected_parent}, got {actual_parent}"
            )
            expected_parent = data["anchor_id"]

    async def test_verify_detects_deleted_anchor(self, trust_dir):
        """Deleting a middle anchor breaks the parent chain."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Delete Anchor Test",
            author="Gamma",
        )
        for i in range(3):
            await project.record_decision(
                DecisionRecord(
                    decision_type=DecisionType.SCOPE,
                    decision=f"Decision {i}",
                    rationale=f"Reason {i}",
                )
            )

        # Delete the middle anchor
        anchor_files = sorted((trust_dir / "anchors").glob("*.json"))
        assert len(anchor_files) == 3
        anchor_files[1].unlink()

        report = await project.verify()
        assert report["chain_valid"] is False
        assert any("parent chain broken" in i for i in report["integrity_issues"])

    async def test_filesystem_store_persistence(self, trust_dir):
        """chains/ directory persists store data across load cycles."""
        await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Store Persist Test",
            author="Delta",
        )
        chains_dir = trust_dir / "chains"
        assert chains_dir.is_dir()
        # FilesystemStore should have at least one file
        chain_files = list(chains_dir.rglob("*"))
        assert len(chain_files) > 0

        # Load from fresh and verify store still works
        loaded = await TrustProject.load(trust_dir)
        report = await loaded.verify()
        assert report["chain_valid"] is True

    async def test_genesis_id_preserved_across_load(self, trust_dir):
        """Load must NOT create a new genesis — same genesis ID."""
        original = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Genesis Preserve",
            author="Epsilon",
        )
        genesis_id = original.manifest.genesis_id

        loaded = await TrustProject.load(trust_dir)
        assert loaded.manifest.genesis_id == genesis_id

        # Verify the chain in store also has the same genesis
        report = await loaded.verify()
        assert report["genesis_id"] == genesis_id

    async def test_chains_directory_created(self, trust_dir):
        """create() produces a chains/ subdirectory."""
        await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Chains Dir Test",
            author="Zeta",
        )
        assert (trust_dir / "chains").is_dir()

    async def test_mixed_decisions_and_milestones_chain(self, trust_dir):
        """Decisions and milestones share the same parent anchor chain."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Mixed Chain",
            author="Eta",
        )
        await project.record_decision(
            DecisionRecord(
                decision_type=DecisionType.SCOPE,
                decision="Decision 1",
                rationale="Reason 1",
            )
        )
        await project.record_milestone(
            version="v0.1",
            description="First milestone",
        )
        await project.record_decision(
            DecisionRecord(
                decision_type=DecisionType.DESIGN,
                decision="Decision 2",
                rationale="Reason 2",
            )
        )

        report = await project.verify()
        assert report["chain_valid"] is True
        assert report["total_decisions"] == 2
        assert report["total_milestones"] == 1
        assert report["total_anchors"] == 3


class TestFileLocking:
    async def test_concurrent_safety_sequential(self, trust_dir):
        """Verify that sequential operations maintain correct counters."""
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Lock Test",
            author="Alpha",
        )
        for i in range(10):
            await project.record_decision(
                DecisionRecord(
                    decision_type=DecisionType.SCOPE,
                    decision=f"Decision {i}",
                    rationale=f"Reason {i}",
                )
            )
        assert project.manifest.total_decisions == 10
        assert project.manifest.total_audits == 10

        # Verify all files have unique sequence numbers
        decision_files = sorted((trust_dir / "decisions").glob("*.json"))
        assert len(decision_files) == 10
        for i, df in enumerate(decision_files):
            assert df.name.startswith(f"{i:04d}-")
