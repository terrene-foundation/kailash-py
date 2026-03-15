# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for cross-process file locking (PS1).

Verifies that file_lock() provides mutual exclusion for filesystem
operations, including lock lifecycle, shared vs exclusive modes,
and proper cleanup.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

from eatp.store.filesystem import file_lock, validate_id


class TestFileLockExclusiveMode:
    """PS1: Exclusive file locking semantics."""

    def test_exclusive_lock_creates_sidecar(self, tmp_path):
        """Exclusive lock must create a .lock sidecar file."""
        target = str(tmp_path / "data.json")
        with file_lock(target, exclusive=True):
            assert os.path.exists(f"{target}.lock")

    def test_exclusive_lock_releases_on_exit(self, tmp_path):
        """Lock file descriptor must be closed after context exit."""
        target = str(tmp_path / "data.json")
        with file_lock(target, exclusive=True):
            pass
        # After exit, we should be able to acquire another lock immediately
        with file_lock(target, exclusive=True):
            pass  # Would hang if the first lock wasn't released

    def test_exclusive_lock_allows_file_operations(self, tmp_path):
        """File operations inside the lock context must succeed."""
        target = tmp_path / "data.json"
        with file_lock(str(target), exclusive=True):
            target.write_text('{"key": "value"}')
        assert target.read_text() == '{"key": "value"}'

    def test_exclusive_lock_releases_on_exception(self, tmp_path):
        """Lock must be released even if an exception occurs inside."""
        target = str(tmp_path / "data.json")
        with pytest.raises(RuntimeError):
            with file_lock(target, exclusive=True):
                raise RuntimeError("deliberate failure")
        # Lock should be released — can re-acquire
        with file_lock(target, exclusive=True):
            pass


class TestFileLockSharedMode:
    """PS1: Shared (read) lock semantics."""

    def test_shared_lock_creates_sidecar(self, tmp_path):
        """Shared lock must also create a .lock sidecar file."""
        target = str(tmp_path / "data.json")
        with file_lock(target, exclusive=False):
            assert os.path.exists(f"{target}.lock")

    def test_shared_lock_default_is_exclusive(self, tmp_path):
        """Default mode should be exclusive=True."""
        target = str(tmp_path / "data.json")
        # Just verify no error with default
        with file_lock(target):
            pass


class TestFileLockCrossProcess:
    """PS1: Cross-process mutual exclusion via subprocess."""

    def test_exclusive_lock_blocks_second_process(self, tmp_path):
        """A second process trying to acquire an exclusive lock on the
        same file should block until the first releases it.

        We verify this by:
        1. Parent holds the lock and writes a marker file
        2. Child tries to acquire, then writes when it gets the lock
        3. Child's write must happen AFTER parent releases
        """
        target = str(tmp_path / "data.json")
        marker = str(tmp_path / "order.txt")

        child_script = textwrap.dedent(
            f"""\
            import sys
            sys.path.insert(0, {repr(str(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src')))})
            from eatp.store.filesystem import file_lock
            with file_lock({repr(target)}, exclusive=True):
                with open({repr(marker)}, "a") as f:
                    f.write("child\\n")
        """
        )

        # Parent acquires lock first
        with file_lock(target, exclusive=True):
            # Write parent marker while holding lock
            with open(marker, "w") as f:
                f.write("parent\n")

            # Launch child — it will block on the lock
            child = subprocess.Popen(
                [sys.executable, "-c", child_script],
                env={
                    **os.environ,
                    "PYTHONPATH": os.path.join(
                        os.path.dirname(__file__), "..", "..", "..", "src"
                    ),
                },
            )
            # Give child time to start and attempt lock
            import time

            time.sleep(0.3)

            # Child should still be running (blocked on lock)
            assert child.poll() is None, "Child should be blocked waiting for lock"

        # Parent released lock — child should now complete
        child.wait(timeout=10)
        assert child.returncode == 0

        # Verify ordering: parent wrote first, child appended
        with open(marker) as f:
            lines = f.read().strip().split("\n")
        assert lines == ["parent", "child"]

    def test_exclusive_parameter_accepted(self, tmp_path):
        """The exclusive parameter is accepted for backward compatibility.

        Note: filelock does not support shared locks. Both exclusive=True
        and exclusive=False acquire an exclusive lock. Read safety comes
        from the atomic write-then-replace pattern, not from shared locking.
        """
        target = str(tmp_path / "data.json")

        # Both modes should work without error
        with file_lock(target, exclusive=True):
            pass

        with file_lock(target, exclusive=False):
            pass


class TestFileLockPublicAPI:
    """PS2: file_lock and validate_id must be importable from public locations."""

    def test_file_lock_importable_from_filesystem(self):
        """file_lock must be importable from eatp.store.filesystem."""
        from eatp.store.filesystem import file_lock as fl

        assert callable(fl)

    def test_validate_id_importable_from_filesystem(self):
        """validate_id must be importable from eatp.store.filesystem."""
        from eatp.store.filesystem import validate_id as vi

        assert callable(vi)

    def test_file_lock_has_docstring(self):
        """Public utility must have documentation."""
        assert file_lock.__doc__ is not None
        assert "lock" in file_lock.__doc__.lower()

    def test_validate_id_has_docstring(self):
        """Public utility must have documentation."""
        assert validate_id.__doc__ is not None
        assert "traversal" in validate_id.__doc__.lower()
