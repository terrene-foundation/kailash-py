# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for platform-specific key and database file protection (TODO-33)."""

import os
import stat
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only permissions")
class TestPOSIXKeyProtection:
    """Verify private key files are created with 0o600 on POSIX."""

    def test_private_key_permissions(self, tmp_path: Path) -> None:
        """Private key file must be owner read/write only (0o600)."""
        from trustplane.project import _save_keys

        _save_keys(tmp_path / "keys", "fake-private-key", "fake-public-key")

        priv_path = tmp_path / "keys" / "private.key"
        mode = stat.S_IMODE(priv_path.stat().st_mode)
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"

    def test_public_key_permissions(self, tmp_path: Path) -> None:
        """Public key file should be 0o644 (readable but not world-writable)."""
        from trustplane.project import _save_keys

        _save_keys(tmp_path / "keys", "fake-private-key", "fake-public-key")

        pub_path = tmp_path / "keys" / "public.key"
        mode = stat.S_IMODE(pub_path.stat().st_mode)
        assert mode == 0o644, f"Expected 0o644, got {oct(mode)}"

    def test_set_private_file_permissions(self, tmp_path: Path) -> None:
        """set_private_file_permissions() applies 0o600 on POSIX."""
        from trustplane.project import set_private_file_permissions

        test_file = tmp_path / "secret.txt"
        test_file.write_text("secret data")
        os.chmod(test_file, 0o644)  # Start with world-readable

        set_private_file_permissions(test_file)

        mode = stat.S_IMODE(test_file.stat().st_mode)
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only tests")
class TestWindowsKeyProtection:
    """Verify Windows key protection doesn't crash (actual ACL verification
    requires pywin32 which is optional)."""

    def test_key_write_does_not_raise(self, tmp_path: Path) -> None:
        """Key write must succeed on Windows regardless of pywin32 availability."""
        from trustplane.project import _save_keys

        _save_keys(tmp_path / "keys", "fake-private-key", "fake-public-key")

        priv_path = tmp_path / "keys" / "private.key"
        assert priv_path.exists()
        assert priv_path.read_text() == "fake-private-key"


class TestKeyProtectionCrossPlatform:
    """Tests that work on any platform."""

    def test_save_keys_creates_both_files(self, tmp_path: Path) -> None:
        """Both private and public key files must be created."""
        from trustplane.project import _save_keys

        keys_dir = tmp_path / "keys"
        _save_keys(keys_dir, "priv-data", "pub-data")

        assert (keys_dir / "private.key").exists()
        assert (keys_dir / "public.key").exists()
        assert (keys_dir / "private.key").read_text() == "priv-data"
        assert (keys_dir / "public.key").read_text() == "pub-data"

    def test_save_keys_creates_directory(self, tmp_path: Path) -> None:
        """Keys directory is created if it doesn't exist."""
        from trustplane.project import _save_keys

        keys_dir = tmp_path / "nested" / "keys"
        _save_keys(keys_dir, "priv", "pub")

        assert keys_dir.exists()
        assert (keys_dir / "private.key").exists()
