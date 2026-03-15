# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for TrustPlane MCP Server tools."""

import asyncio
import threading

import pytest

import trustplane.mcp_server as mcp_mod
from trustplane.models import ConstraintEnvelope, OperationalConstraints
from trustplane.project import TrustProject


@pytest.fixture
def trust_dir(tmp_path):
    return tmp_path / "trust-plane"


@pytest.fixture
async def project(trust_dir):
    """Create a project and patch the MCP module to use it."""
    env = ConstraintEnvelope(
        operational=OperationalConstraints(
            blocked_actions=["fabricate", "delete_project"],
        ),
        signed_by="Test",
    )
    p = await TrustProject.create(
        trust_dir=trust_dir,
        project_name="MCP Test",
        author="Alice",
        constraint_envelope=env,
    )
    # Patch the cached project
    mcp_mod._set_project(p)
    yield p
    mcp_mod._reset_project()


class TestTrustCheck:
    async def test_allowed_action(self, project):
        result = await mcp_mod.trust_check(
            action="record_decision",
            decision_type="scope",
        )
        assert result["verdict"] == "auto_approved"

    async def test_blocked_action(self, project):
        result = await mcp_mod.trust_check(
            action="record_decision",
            decision_type="fabricate",
        )
        assert result["verdict"] == "blocked"

    async def test_includes_posture(self, project):
        result = await mcp_mod.trust_check(action="anything")
        assert result["posture"] == "supervised"


class TestTrustRecord:
    async def test_record_decision(self, project):
        result = await mcp_mod.trust_record(
            decision="Use CARE framework",
            rationale="Best fit for governance",
            decision_type="scope",
        )
        assert result["anchor_created"] is True
        assert result["decision_id"].startswith("dec-")

    async def test_record_blocked_decision(self, project):
        result = await mcp_mod.trust_record(
            decision="Made up data",
            rationale="Testing",
            decision_type="fabricate",
        )
        assert result["blocked"] is True
        assert "error" in result

    async def test_record_with_confidentiality(self, project):
        result = await mcp_mod.trust_record(
            decision="Sensitive decision",
            rationale="Testing confidentiality",
            confidentiality="restricted",
        )
        assert result["anchor_created"] is True


class TestTrustEnvelope:
    async def test_returns_envelope(self, project):
        result = await mcp_mod.trust_envelope()
        assert result["envelope"] is not None
        assert "fabricate" in result["envelope"]["operational"]["blocked_actions"]

    async def test_no_envelope(self, trust_dir):
        p = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="No Envelope",
            author="Bob",
        )
        mcp_mod._set_project(p)
        result = await mcp_mod.trust_envelope()
        assert result["envelope"] is None
        mcp_mod._reset_project()


class TestTrustStatus:
    async def test_returns_status(self, project):
        result = await mcp_mod.trust_status()
        assert result["project_name"] == "MCP Test"
        assert result["trust_posture"] == "supervised"
        assert result["total_decisions"] == 0
        assert result["blocked_actions"] == ["fabricate", "delete_project"]

    async def test_status_after_decision(self, project):
        await mcp_mod.trust_record(
            decision="Test", rationale="Testing", decision_type="scope"
        )
        result = await mcp_mod.trust_status()
        assert result["total_decisions"] == 1


class TestTrustVerify:
    async def test_verify_clean(self, project):
        result = await mcp_mod.trust_verify()
        assert result["chain_valid"] is True
        assert result["integrity_issues"] == []
        assert result["trust_posture"] == "supervised"
        assert result["verification_level"] == "FULL"


class TestGetProjectThreadSafety:
    """Verify _get_project() is thread-safe under concurrent access."""

    async def test_concurrent_get_project_returns_same_instance(self, trust_dir):
        """Multiple threads calling _get_project() concurrently all get the
        same TrustProject instance — no double-init race."""
        # Create a real project on disk so _get_project() has something to load
        env = ConstraintEnvelope(
            operational=OperationalConstraints(
                blocked_actions=["fabricate"],
            ),
            signed_by="Test",
        )
        await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Concurrency Test",
            author="Alice",
            constraint_envelope=env,
        )

        # Reset cached state so _get_project() must load from disk
        mcp_mod._reset_project()
        original_trust_dir = mcp_mod.TRUST_DIR
        mcp_mod.TRUST_DIR = trust_dir

        results: list[TrustProject] = []
        errors: list[Exception] = []
        barrier = threading.Barrier(8, timeout=5)

        def worker():
            """Each worker waits at a barrier then calls _get_project()."""
            try:
                barrier.wait()
                loop = asyncio.new_event_loop()
                try:
                    project = loop.run_until_complete(mcp_mod._get_project())
                    results.append(project)
                finally:
                    loop.close()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # Restore original state
        mcp_mod.TRUST_DIR = original_trust_dir
        mcp_mod._reset_project()

        # No errors should have occurred
        assert errors == [], f"Threads raised errors: {errors}"

        # All threads must have received a valid TrustProject
        assert len(results) == 8

        # All threads must have received the SAME instance (init-once)
        first = results[0]
        for i, r in enumerate(results[1:], start=1):
            assert r is first, (
                f"Thread {i} got a different TrustProject instance — "
                f"race condition in _get_project()"
            )

    async def test_manifest_mtime_atomic_with_project(self, trust_dir):
        """_manifest_mtime is updated atomically with _project — no partial
        state where one is updated but the other is not."""
        env = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=[]),
            signed_by="Test",
        )
        await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Atomic Test",
            author="Bob",
            constraint_envelope=env,
        )

        mcp_mod._reset_project()
        original_trust_dir = mcp_mod.TRUST_DIR
        mcp_mod.TRUST_DIR = trust_dir

        # Load the project
        project = await mcp_mod._get_project()
        assert project is not None

        # Read the mtime through the lock-protected accessor
        mtime = mcp_mod._get_manifest_mtime()
        assert mtime > 0.0, "_manifest_mtime should be set after _get_project() loads"

        # Restore
        mcp_mod.TRUST_DIR = original_trust_dir
        mcp_mod._reset_project()

    async def test_reset_clears_both_project_and_mtime(self):
        """_reset_project() clears both _project and _manifest_mtime atomically."""
        mcp_mod._reset_project()

        # After reset, both should be in initial state
        mtime = mcp_mod._get_manifest_mtime()
        assert mtime == 0.0, "_manifest_mtime should be 0.0 after reset"

    async def test_set_project_updates_atomically(self, trust_dir):
        """_set_project() updates _project under the lock, including
        manifest mtime so the cache is consistent with _get_project()."""
        env = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=[]),
            signed_by="Test",
        )
        p = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Set Test",
            author="Alice",
            constraint_envelope=env,
        )

        original_trust_dir = mcp_mod.TRUST_DIR
        # TRUST_DIR must be set BEFORE _set_project so it reads the
        # correct manifest mtime from the right directory.
        mcp_mod.TRUST_DIR = trust_dir
        mcp_mod._reset_project()
        mcp_mod._set_project(p)

        # Should be retrievable immediately without triggering a reload
        result = await mcp_mod._get_project()
        assert result is p

        # Cleanup
        mcp_mod.TRUST_DIR = original_trust_dir
        mcp_mod._reset_project()
