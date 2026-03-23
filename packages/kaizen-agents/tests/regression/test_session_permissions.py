# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for session file permissions (GitHub issue #68).

Session files contain conversation history that may include API keys and
sensitive data. They must be written with owner-only permissions (0o600)
and the sessions directory must be owner-only (0o700) on POSIX systems.
"""

from __future__ import annotations

import os
import stat
import sys

import pytest

from kaizen_agents.delegate.session import SessionManager


@pytest.mark.regression
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions only")
class TestSessionFilePermissions:
    """Verify session files and directories have restrictive permissions."""

    def test_sessions_directory_has_700_permissions(self, tmp_path: object) -> None:
        """Sessions directory must be owner-only (rwx------) on creation."""
        sessions_dir = tmp_path / "sessions"  # type: ignore[operator]
        SessionManager(sessions_dir)
        mode = stat.S_IMODE(os.stat(sessions_dir).st_mode)
        assert mode == 0o700, f"Expected 0o700, got {oct(mode)}"

    def test_save_session_creates_file_with_600_permissions(self, tmp_path: object) -> None:
        """Saved session files must be owner-only (rw-------)."""
        mgr = SessionManager(tmp_path / "sessions")  # type: ignore[operator]
        path = mgr.save_session("test")
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"

    def test_fork_session_creates_file_with_600_permissions(self, tmp_path: object) -> None:
        """Forked session files must also be owner-only (rw-------)."""
        mgr = SessionManager(tmp_path / "sessions")  # type: ignore[operator]
        mgr.save_session("original")
        result = mgr.fork_session("original", "forked")
        assert result is not None, "fork_session returned None — source should exist"
        mode = stat.S_IMODE(os.stat(result).st_mode)
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"

    def test_auto_save_creates_file_with_600_permissions(self, tmp_path: object) -> None:
        """Auto-saved session files must be owner-only (rw-------)."""
        mgr = SessionManager(tmp_path / "sessions")  # type: ignore[operator]
        path = mgr.auto_save()
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"

    def test_overwritten_session_retains_600_permissions(self, tmp_path: object) -> None:
        """Re-saving to same name must still enforce 0o600."""
        mgr = SessionManager(tmp_path / "sessions")  # type: ignore[operator]
        mgr.save_session("dup")
        path = mgr.save_session("dup")
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"

    def test_existing_directory_gets_permissions_fixed(self, tmp_path: object) -> None:
        """If the directory already exists, permissions are still tightened."""
        sessions_dir = tmp_path / "sessions"  # type: ignore[operator]
        sessions_dir.mkdir(mode=0o755)  # type: ignore[attr-defined]
        SessionManager(sessions_dir)
        mode = stat.S_IMODE(os.stat(sessions_dir).st_mode)
        assert mode == 0o700, f"Expected 0o700, got {oct(mode)}"
