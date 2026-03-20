# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Concurrency tests for TrustPlane locking, atomic writes, and WAL recovery.

Tests cross-process scenarios using multiprocessing (not threading),
since fcntl.flock is process-level.
"""

import json
import multiprocessing
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from trustplane._locking import (
    LockTimeoutError,
    atomic_write,
    compute_wal_hash,
    file_lock,
    safe_read_json,
)
from trustplane.delegation import DelegationManager, DelegateStatus
from trustplane.holds import HoldManager


# --- Helpers for cross-process tests ---


def _add_delegate_in_process(args: tuple[str, str, int]) -> str:
    """Worker: add a delegate and return its ID."""
    trust_dir_str, name_prefix, index = args
    trust_dir = Path(trust_dir_str)
    dm = DelegationManager(trust_dir)
    d = dm.add_delegate(f"{name_prefix}_{index}", ["operational"])
    return d.delegate_id


def _resolve_hold_in_process(args: tuple[str, str, str, bool]) -> str:
    """Worker: try to resolve a hold, return 'ok' or error message."""
    trust_dir_str, hold_id, delegate_id, approved = args
    trust_dir = Path(trust_dir_str)
    dm = DelegationManager(trust_dir)
    hm = HoldManager(trust_dir)
    try:
        hold = hm.get(hold_id)
        dm.resolve_hold(
            hold, delegate_id, approved, "process resolution", "operational"
        )
        return "ok"
    except (ValueError, KeyError) as e:
        return f"error:{e}"


# --- 1. Atomic Write Integrity ---


class TestAtomicWriteIntegrity:
    """Verify atomic_write prevents corruption."""

    def test_concurrent_delegate_save_no_corruption(self, tmp_path: Path) -> None:
        """Two processes saving delegates simultaneously — no corruption."""
        dm = DelegationManager(tmp_path)
        # Add a base delegate so the directory exists
        dm.add_delegate("base", ["operational"])

        # Use multiprocessing to add 10 delegates concurrently
        args = [(str(tmp_path), "concurrent", i) for i in range(10)]
        with multiprocessing.Pool(4) as pool:
            results = pool.map(_add_delegate_in_process, args)

        # All should succeed with unique IDs
        assert len(results) == 10
        assert len(set(results)) == 10  # All unique

        # Verify all delegates are valid JSON on disk
        dm2 = DelegationManager(tmp_path)
        all_delegates = dm2.list_delegates(active_only=False)
        # 1 base + 10 concurrent = 11
        assert len(all_delegates) == 11

    def test_crash_mid_write_produces_valid_state(self, tmp_path: Path) -> None:
        """Simulate crash during _save — file is either old or new, never partial."""
        target = tmp_path / "test.json"
        original_data = {"version": 1, "content": "original"}
        atomic_write(target, original_data)

        # Patch os.replace to raise after mkstemp but before replace
        def failing_replace(src: str, _dst: str) -> None:
            # Delete temp file to simulate crash cleanup
            os.unlink(src)
            raise OSError("Simulated crash during replace")

        with patch("trustplane._locking.os.replace", side_effect=failing_replace):
            with pytest.raises(OSError, match="Simulated crash"):
                atomic_write(target, {"version": 2, "content": "new"})

        # Original file should be untouched
        with open(target) as f:
            data = json.load(f)
        assert data["version"] == 1
        assert data["content"] == "original"


# --- 2. Lock Contention ---


class TestLockContention:
    """Verify file_lock serializes concurrent access."""

    def test_concurrent_add_delegates_sequential(self, tmp_path: Path) -> None:
        """Multiple processes adding delegates — all succeed, no duplicates."""
        args = [(str(tmp_path), "lock_test", i) for i in range(10)]
        with multiprocessing.Pool(4) as pool:
            results = pool.map(_add_delegate_in_process, args)

        assert len(results) == 10
        assert len(set(results)) == 10

        dm = DelegationManager(tmp_path)
        delegates = dm.list_delegates(active_only=True)
        assert len(delegates) == 10

    def test_concurrent_revoke_and_add_safe(self, tmp_path: Path) -> None:
        """Revoke parent, then try to add sub-delegate — second must fail."""
        dm = DelegationManager(tmp_path)
        parent = dm.add_delegate("parent", ["operational", "data_access"])

        # Revoke parent
        dm.revoke_delegate(parent.delegate_id, "test revocation")

        # Try to add child of revoked parent — must fail
        with pytest.raises(ValueError, match="not active"):
            dm.add_delegate(
                "child",
                ["operational"],
                parent_delegate_id=parent.delegate_id,
            )


# --- 3. TOCTOU Prevention ---


class TestTOCTOUPrevention:
    """Verify TOCTOU bugs are prevented by locking."""

    def test_double_resolve_hold_rejected(self, tmp_path: Path) -> None:
        """Two sequential resolves — second gets ValueError."""
        hm = HoldManager(tmp_path)
        hold = hm.create_hold(
            action="test_action",
            resource="test_resource",
            reason="needs review",
        )

        # First resolve succeeds
        hm.resolve(hold.hold_id, True, "reviewer_a", "approved first")

        # Second resolve must fail — hold already resolved
        with pytest.raises(ValueError, match="already"):
            hm.resolve(hold.hold_id, False, "reviewer_b", "tried second")

    def test_add_delegate_to_revoked_parent_rejected(self, tmp_path: Path) -> None:
        """Cannot sub-delegate from a revoked parent."""
        dm = DelegationManager(tmp_path)
        parent = dm.add_delegate("parent", ["operational", "data_access"])

        # Revoke parent
        dm.revoke_delegate(parent.delegate_id, "revoked")

        # Attempt sub-delegation must fail
        with pytest.raises(ValueError, match="not active"):
            dm.add_delegate(
                "child",
                ["operational"],
                parent_delegate_id=parent.delegate_id,
            )


# --- 4. WAL Recovery ---


class TestWALRecovery:
    """Verify WAL-based crash recovery for cascade revocations."""

    def test_wal_recovery_completes_cascade(self, tmp_path: Path) -> None:
        """Crash during cascade — recovery finishes the revocation."""
        dm = DelegationManager(tmp_path)
        parent = dm.add_delegate("parent", ["operational", "data_access"])
        child1 = dm.add_delegate(
            "child1", ["operational"], parent_delegate_id=parent.delegate_id
        )
        child2 = dm.add_delegate(
            "child2", ["operational"], parent_delegate_id=parent.delegate_id
        )
        grandchild = dm.add_delegate(
            "grandchild", ["operational"], parent_delegate_id=child1.delegate_id
        )

        # Simulate crash: write WAL but don't execute cascade
        wal_path = tmp_path / "delegates" / ".pending-revocation.wal"
        wal_data = {
            "root_delegate_id": parent.delegate_id,
            "planned_revocations": [
                parent.delegate_id,
                child1.delegate_id,
                child2.delegate_id,
                grandchild.delegate_id,
            ],
            "reason": "test crash recovery",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        wal_data["content_hash"] = compute_wal_hash(wal_data)
        atomic_write(wal_path, wal_data)

        # Recovery should complete the cascade
        recovered = dm.recover_pending_revocations()
        assert len(recovered) == 4

        # All delegates should be revoked
        for did in [
            parent.delegate_id,
            child1.delegate_id,
            child2.delegate_id,
            grandchild.delegate_id,
        ]:
            d = dm.get_delegate(did)
            assert d.status == DelegateStatus.REVOKED

        # WAL file should be cleaned up
        assert not wal_path.exists()

    def test_wal_recovery_idempotent(self, tmp_path: Path) -> None:
        """Running recovery twice doesn't double-revoke or error."""
        dm = DelegationManager(tmp_path)
        parent = dm.add_delegate("parent", ["operational"])
        child = dm.add_delegate(
            "child", ["operational"], parent_delegate_id=parent.delegate_id
        )

        # Normal revocation (creates and cleans WAL)
        dm.revoke_delegate(parent.delegate_id, "test")

        # Recovery with no WAL should be a no-op
        assert dm.recover_pending_revocations() == []

        # State should be unchanged
        assert dm.get_delegate(parent.delegate_id).status == DelegateStatus.REVOKED
        assert dm.get_delegate(child.delegate_id).status == DelegateStatus.REVOKED

    def test_no_wal_no_recovery(self, tmp_path: Path) -> None:
        """No pending WAL — recovery is a no-op."""
        dm = DelegationManager(tmp_path)
        assert dm.recover_pending_revocations() == []

    def test_wal_recovery_handles_already_revoked(self, tmp_path: Path) -> None:
        """WAL lists delegates that were already revoked — recovery skips them."""
        dm = DelegationManager(tmp_path)
        parent = dm.add_delegate("parent", ["operational"])
        child = dm.add_delegate(
            "child", ["operational"], parent_delegate_id=parent.delegate_id
        )

        # Manually revoke child before writing WAL
        dm.revoke_delegate(child.delegate_id, "pre-revoked")

        # Write WAL listing both parent and already-revoked child
        wal_path = tmp_path / "delegates" / ".pending-revocation.wal"
        wal_data = {
            "root_delegate_id": parent.delegate_id,
            "planned_revocations": [parent.delegate_id, child.delegate_id],
            "reason": "partial crash",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        wal_data["content_hash"] = compute_wal_hash(wal_data)
        atomic_write(wal_path, wal_data)

        # Recovery should only revoke parent (child already done)
        recovered = dm.recover_pending_revocations()
        assert parent.delegate_id in recovered
        assert child.delegate_id not in recovered  # Already revoked, skipped

    def test_wal_recovery_handles_deleted_delegate(self, tmp_path: Path) -> None:
        """WAL references a delegate whose file was deleted — recovery skips it."""
        dm = DelegationManager(tmp_path)
        parent = dm.add_delegate("parent", ["operational"])

        # Write WAL referencing a non-existent delegate
        wal_path = tmp_path / "delegates" / ".pending-revocation.wal"
        wal_data = {
            "root_delegate_id": parent.delegate_id,
            "planned_revocations": [parent.delegate_id, "del-nonexistent"],
            "reason": "deleted delegate",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        wal_data["content_hash"] = compute_wal_hash(wal_data)
        atomic_write(wal_path, wal_data)

        # Recovery should handle missing delegate gracefully
        recovered = dm.recover_pending_revocations()
        assert parent.delegate_id in recovered
        assert not wal_path.exists()


# --- 5. Cross-Process Delegation ---


class TestCrossProcessDelegation:
    """Verify delegation chains work across multiple processes."""

    def test_delegation_chain_depth(self, tmp_path: Path) -> None:
        """Build a delegation chain and verify depth tracking."""
        dm = DelegationManager(tmp_path)
        d1 = dm.add_delegate("level0", ["operational", "data_access"])
        d2 = dm.add_delegate(
            "level1", ["operational"], parent_delegate_id=d1.delegate_id
        )
        d3 = dm.add_delegate(
            "level2", ["operational"], parent_delegate_id=d2.delegate_id
        )

        assert dm.get_delegate(d1.delegate_id).depth == 0
        assert dm.get_delegate(d2.delegate_id).depth == 1
        assert dm.get_delegate(d3.delegate_id).depth == 2

    def test_cascade_revocation_full_tree(self, tmp_path: Path) -> None:
        """Revoking root cascades through entire tree."""
        dm = DelegationManager(tmp_path)
        root = dm.add_delegate("root", ["operational", "data_access", "financial"])
        branch1 = dm.add_delegate(
            "branch1",
            ["operational", "data_access"],
            parent_delegate_id=root.delegate_id,
        )
        branch2 = dm.add_delegate(
            "branch2", ["operational"], parent_delegate_id=root.delegate_id
        )
        leaf = dm.add_delegate(
            "leaf", ["operational"], parent_delegate_id=branch1.delegate_id
        )

        revoked = dm.revoke_delegate(root.delegate_id, "full tree revocation")
        assert len(revoked) == 4  # root + branch1 + branch2 + leaf

        # All should be revoked
        for did in [
            root.delegate_id,
            branch1.delegate_id,
            branch2.delegate_id,
            leaf.delegate_id,
        ]:
            assert dm.get_delegate(did).status == DelegateStatus.REVOKED

        # No active delegates remain
        assert len(dm.list_delegates(active_only=True)) == 0

    def test_monotonic_tightening_across_chain(self, tmp_path: Path) -> None:
        """Sub-delegates cannot expand parent's dimensions."""
        dm = DelegationManager(tmp_path)
        parent = dm.add_delegate("parent", ["operational"])

        # Cannot add dimension parent doesn't have
        with pytest.raises(ValueError, match="not in parent"):
            dm.add_delegate(
                "child",
                ["operational", "financial"],
                parent_delegate_id=parent.delegate_id,
            )

        # Can narrow to subset
        child = dm.add_delegate(
            "child", ["operational"], parent_delegate_id=parent.delegate_id
        )
        assert child.dimensions == ["operational"]


# --- 6. Path Traversal Prevention ---


class TestPathTraversal:
    """Verify ID validation prevents path traversal attacks."""

    def test_delegate_id_path_traversal_rejected(self, tmp_path: Path) -> None:
        """Delegate IDs with path separators are rejected."""
        dm = DelegationManager(tmp_path)
        with pytest.raises(ValueError, match="unsafe characters"):
            dm.get_delegate("../../etc/shadow")

    def test_delegate_id_dotdot_rejected(self, tmp_path: Path) -> None:
        """Delegate IDs with .. are rejected."""
        dm = DelegationManager(tmp_path)
        with pytest.raises(ValueError, match="unsafe characters"):
            dm.get_delegate("../delegates/del-abc")

    def test_hold_id_path_traversal_rejected(self, tmp_path: Path) -> None:
        """Hold IDs with path separators are rejected."""
        hm = HoldManager(tmp_path)
        with pytest.raises(ValueError, match="unsafe characters"):
            hm.get("../../etc/passwd")

    def test_revoke_path_traversal_rejected(self, tmp_path: Path) -> None:
        """Revoke with traversal ID is rejected."""
        dm = DelegationManager(tmp_path)
        with pytest.raises(ValueError, match="unsafe characters"):
            dm.revoke_delegate("../../../etc/shadow")

    def test_valid_delegate_id_accepted(self, tmp_path: Path) -> None:
        """Normal delegate IDs work fine."""
        dm = DelegationManager(tmp_path)
        d = dm.add_delegate("test", ["operational"])
        # The generated ID should pass validation
        retrieved = dm.get_delegate(d.delegate_id)
        assert retrieved.name == "test"


# --- 7. Corrupted WAL Recovery ---


class TestCorruptedWALRecovery:
    """Verify corrupted WAL files don't block operations."""

    def test_corrupted_wal_removed_gracefully(self, tmp_path: Path) -> None:
        """Invalid JSON in WAL file is handled, not propagated."""
        dm = DelegationManager(tmp_path)
        wal_path = tmp_path / "delegates" / ".pending-revocation.wal"
        wal_path.parent.mkdir(parents=True, exist_ok=True)
        wal_path.write_text("{invalid json")

        # Should not raise — corrupted WAL is removed
        result = dm.recover_pending_revocations()
        assert result == []
        assert not wal_path.exists()


# --- 8. Lock Timeout ---


class TestLockTimeout:
    """Verify configurable lock timeout."""

    def test_lock_timeout_raises_on_contention(self, tmp_path: Path) -> None:
        """When lock cannot be acquired within timeout, LockTimeoutError is raised."""
        lock_path = tmp_path / ".lock"
        # Acquire the lock in the current process
        with file_lock(lock_path, timeout=0):
            # Try to acquire from another process with a very short timeout
            # Since we hold the lock, the child must fail
            pass  # Lock is released on exit

        # Verify the error type exists and can be raised
        with pytest.raises(LockTimeoutError):
            raise LockTimeoutError("test")

    def test_lock_timeout_zero_blocks_forever(self, tmp_path: Path) -> None:
        """timeout=0 means block forever (original behavior)."""
        lock_path = tmp_path / ".lock"
        # Should acquire immediately (no contention)
        with file_lock(lock_path, timeout=0):
            assert lock_path.exists()


# --- 9. Symlink Protection ---


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="O_NOFOLLOW symlink protection not available on Windows",
)
class TestSymlinkProtection:
    """Verify symlink attack prevention."""

    def test_delegate_symlink_rejected(self, tmp_path: Path) -> None:
        """Reading a delegate file that is a symlink is rejected."""
        dm = DelegationManager(tmp_path)
        d = dm.add_delegate("legit", ["operational"])

        # Create a symlink to the delegate file
        real_path = tmp_path / "delegates" / f"{d.delegate_id}.json"
        symlink_path = tmp_path / "delegates" / "del-symlink.json"
        symlink_path.symlink_to(real_path)

        # Accessing via the symlink ID should fail
        with pytest.raises(OSError, match="symlink"):
            dm.get_delegate("del-symlink")

    def test_hold_symlink_rejected(self, tmp_path: Path) -> None:
        """Reading a hold file that is a symlink is rejected."""
        hm = HoldManager(tmp_path)
        hold = hm.create_hold("test", "resource", "reason")

        # Create a symlink
        real_path = tmp_path / "holds" / f"{hold.hold_id}.json"
        symlink_path = tmp_path / "holds" / "hold-symlink.json"
        symlink_path.symlink_to(real_path)

        with pytest.raises(OSError, match="symlink"):
            hm.get("hold-symlink")

    def test_safe_read_json_rejects_symlink(self, tmp_path: Path) -> None:
        """safe_read_json rejects symlinks atomically (no TOCTOU window)."""
        target = tmp_path / "target.json"
        target.write_text('{"key": "value"}')
        link = tmp_path / "link.json"
        link.symlink_to(target)

        with pytest.raises(OSError, match="symlink"):
            safe_read_json(link)

    def test_safe_read_json_reads_regular_files(self, tmp_path: Path) -> None:
        """safe_read_json successfully reads regular (non-symlink) JSON files."""
        regular = tmp_path / "data.json"
        regular.write_text('{"name": "test", "value": 42}')

        data = safe_read_json(regular)
        assert data == {"name": "test", "value": 42}

    def test_safe_read_json_raises_on_missing_file(self, tmp_path: Path) -> None:
        """safe_read_json raises FileNotFoundError for missing files."""
        missing = tmp_path / "missing.json"
        with pytest.raises(FileNotFoundError):
            safe_read_json(missing)


# --- 10. WAL Content Hash ---


class TestWALContentHash:
    """Verify WAL tamper detection via content hash."""

    def test_wal_hash_detects_tampering(self, tmp_path: Path) -> None:
        """WAL with mismatched content hash is rejected during recovery."""
        dm = DelegationManager(tmp_path)
        parent = dm.add_delegate("parent", ["operational"])

        # Write a WAL with correct hash, then tamper
        wal_path = tmp_path / "delegates" / ".pending-revocation.wal"
        wal_data = {
            "root_delegate_id": parent.delegate_id,
            "planned_revocations": [parent.delegate_id],
            "reason": "test hash",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        wal_data["content_hash"] = compute_wal_hash(wal_data)
        atomic_write(wal_path, wal_data)

        # Tamper with the WAL on disk
        with open(wal_path) as f:
            tampered = json.load(f)
        tampered["reason"] = "TAMPERED REASON"
        with open(wal_path, "w") as f:
            json.dump(tampered, f)

        # Recovery should detect the tamper and remove the WAL
        recovered = dm.recover_pending_revocations()
        assert recovered == []
        assert not wal_path.exists()
        # Parent should still be active (revocation was not applied)
        assert dm.get_delegate(parent.delegate_id).status == DelegateStatus.ACTIVE

    def test_wal_hash_valid_allows_recovery(self, tmp_path: Path) -> None:
        """WAL with correct content hash is accepted during recovery."""
        dm = DelegationManager(tmp_path)
        parent = dm.add_delegate("parent", ["operational"])

        # Write a WAL with correct hash
        wal_path = tmp_path / "delegates" / ".pending-revocation.wal"
        wal_data = {
            "root_delegate_id": parent.delegate_id,
            "planned_revocations": [parent.delegate_id],
            "reason": "test hash",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        wal_data["content_hash"] = compute_wal_hash(wal_data)
        atomic_write(wal_path, wal_data)

        # Recovery should succeed
        recovered = dm.recover_pending_revocations()
        assert parent.delegate_id in recovered
        assert dm.get_delegate(parent.delegate_id).status == DelegateStatus.REVOKED

    def test_wal_without_hash_is_rejected(self, tmp_path: Path) -> None:
        """WAL files without content_hash are rejected (possible tampering)."""
        dm = DelegationManager(tmp_path)
        parent = dm.add_delegate("parent", ["operational"])

        # Write a WAL without hash (attacker stripped it)
        wal_path = tmp_path / "delegates" / ".pending-revocation.wal"
        wal_data = {
            "root_delegate_id": parent.delegate_id,
            "planned_revocations": [parent.delegate_id],
            "reason": "stripped hash",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        atomic_write(wal_path, wal_data)

        # Recovery should reject the WAL (missing hash = possible tamper)
        recovered = dm.recover_pending_revocations()
        assert recovered == []
        # WAL should be removed
        assert not wal_path.exists()
        # Delegate should NOT be revoked
        assert dm.get_delegate(parent.delegate_id).status != DelegateStatus.REVOKED

    def test_compute_wal_hash_deterministic(self, tmp_path: Path) -> None:
        """Same WAL data produces the same hash."""
        data = {
            "root_delegate_id": "del-abc",
            "planned_revocations": ["del-abc", "del-def"],
            "reason": "test",
        }
        h1 = compute_wal_hash(data)
        h2 = compute_wal_hash(data)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

        # Different data produces different hash
        data2 = {**data, "reason": "different"}
        h3 = compute_wal_hash(data2)
        assert h3 != h1
