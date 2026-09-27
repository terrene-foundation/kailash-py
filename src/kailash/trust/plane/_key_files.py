# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Descriptor-based local signing-key file access.

The final path component cannot be a symlink on O_NOFOLLOW platforms.
Parent-directory replacement and Windows ACL behavior are separate concerns.
"""

import base64
import os
import stat
from pathlib import Path

from kailash.utils.file_permissions import restrict_to_owner


def _open_regular(path: Path, flags: int, mode: int = 0o600) -> int:
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    fd = os.open(str(path), flags, mode)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("Signing key must be a regular file")
    except BaseException:
        os.close(fd)
        raise
    return fd


def _read_key_file(path: Path, *, private: bool) -> bytes:
    """Read only regular key files; private bytes require owner protection first."""
    fd = _open_regular(path, os.O_RDONLY)
    try:
        if private and not restrict_to_owner(path, fd=fd):
            raise PermissionError(
                "Cannot enforce owner-only private signing-key permissions; "
                "Windows requires pywin32"
            )
        stream = os.fdopen(fd, "rb")
        fd = -1
        with stream:
            return stream.read()
    finally:
        if fd >= 0:
            os.close(fd)


def read_private_key(path: Path) -> bytes:
    """Read the opened private inode only after restricting it to its owner."""
    return _read_key_file(path, private=True)


def read_public_key(path: Path) -> bytes:
    """Read a regular public key without requiring private-file protection."""
    return _read_key_file(path, private=False)


def write_key_file(
    path: Path, data: bytes, *, private: bool, exclusive: bool = False
) -> None:
    """Protect the opened inode before truncation or writing any private bytes.

    Exclusive creation prevents initialization from replacing a concurrently
    created identity. A failed public write leaves the private identity intact
    so the public half can be recovered on retry.
    """
    flags = os.O_WRONLY | os.O_CREAT
    if exclusive:
        flags |= os.O_EXCL
    fd = _open_regular(path, flags, 0o600 if private else 0o644)
    try:
        if private:
            if not restrict_to_owner(path, fd=fd):
                raise PermissionError(
                    "Cannot enforce owner-only private signing-key permissions; "
                    "Windows requires pywin32"
                )
        elif hasattr(os, "fchmod"):
            os.fchmod(fd, 0o644)
        os.ftruncate(fd, 0)
        remaining = memoryview(data)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("Signing key write made no progress")
            remaining = remaining[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def load_signing_keypair(keys_dir: Path) -> tuple[str, str]:
    """Load base64 Ed25519 keys, recovering only a missing public half.

    FileNotFoundError means both files are absent. Existing inconsistent key
    material fails without implicitly rotating the persisted signing identity.
    """
    priv_path = keys_dir / "private.key"
    pub_path = keys_dir / "public.key"
    try:
        private_key = read_private_key(priv_path).decode("utf-8")
    except FileNotFoundError:
        try:
            read_public_key(pub_path).decode("utf-8")
        except FileNotFoundError:
            raise FileNotFoundError(f"Keys not found at {keys_dir}") from None
        raise ValueError("Public signing key exists without its private key") from None

    from nacl.signing import SigningKey

    signing_key = SigningKey(base64.b64decode(private_key, validate=True))
    public_key = base64.b64encode(bytes(signing_key.verify_key)).decode("utf-8")
    try:
        stored_public = read_public_key(pub_path).decode("utf-8")
    except FileNotFoundError:
        write_key_file(pub_path, public_key.encode(), private=False, exclusive=True)
    else:
        if stored_public != public_key:
            raise ValueError("Stored public signing key does not match the private key")
    return private_key, public_key
