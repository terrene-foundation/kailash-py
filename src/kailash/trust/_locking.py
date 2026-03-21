# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-process file locking for TrustPlane.

Provides cross-platform locking for safe concurrent access to
trust plane state files. Used by project.py, delegation.py, and holds.py.

Design:
- filelock.FileLock: Cross-platform, cross-process exclusive locks
- Lock granularity: directory-level (one lock per subdirectory)
- Lock released automatically when context exits or process crashes

Security notes:
- filelock is ADVISORY — it only works if all processes cooperate
  by calling file_lock(). A process that bypasses the lock and writes
  directly to the file is NOT blocked. All TrustPlane code paths use
  file_lock(), so this is safe for our use case (CLI tool, not
  long-running server with untrusted clients).
- Symlink protection: Data file reads use safe_read_json() with
  O_NOFOLLOW for atomic symlink protection on POSIX, eliminating
  the TOCTOU window of separate check-then-open patterns.
  On Windows, O_NOFOLLOW is unavailable — this is a documented
  security degradation.
"""

import errno
import hashlib
import json
import logging
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

from filelock import FileLock, Timeout

from kailash.trust.exceptions import TrustError

logger = logging.getLogger(__name__)


class LockTimeoutError(TrustError, TimeoutError):
    """Raised when a file lock cannot be acquired within the timeout.

    Defined here (not in plane.exceptions) to avoid circular imports:
    _locking is shared by both protocol and plane layers, so it cannot
    import from plane.  plane.exceptions re-exports this class for
    backward compatibility.
    """


# Safe ID pattern: alphanumeric, hyphens, underscores only
_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

# Default lock timeout (seconds). 0 = no timeout (block forever).
DEFAULT_LOCK_TIMEOUT: float = 30.0


@contextmanager
def file_lock(
    lock_path: Path, timeout: float = DEFAULT_LOCK_TIMEOUT
) -> Generator[None, None, None]:
    """Acquire an exclusive file lock for safe concurrent writes.

    Uses filelock.FileLock which is cross-platform (Windows/Linux/macOS)
    and automatically released when the context exits.

    Note: filelock is advisory — it only prevents concurrent access
    when all writers cooperate by using this lock. All TrustPlane code
    paths use this function for writes.

    Args:
        lock_path: Path to the lock file (created if absent)
        timeout: Maximum seconds to wait for the lock. 0 means block
            forever. Raises LockTimeoutError if exceeded.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(lock_path), timeout=timeout if timeout > 0 else -1)
    try:
        lock.acquire()
    except Timeout:
        raise LockTimeoutError(
            f"Could not acquire lock on {lock_path} within {timeout}s"
        )
    try:
        yield
    finally:
        lock.release()


def atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically via temp file + rename.

    On POSIX, rename is atomic — if the process crashes mid-write,
    either the old file or the new file exists, never a corrupt partial.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.stem}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w") as f:
            fd = -1  # os.fdopen took ownership — don't double-close
            json.dump(data, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path))
    except BaseException:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def validate_id(identifier: str, prefix: str = "") -> None:
    """Validate that an identifier is safe for use in file paths.

    Prevents path traversal attacks (e.g., "../../etc/shadow").

    Args:
        identifier: The ID to validate
        prefix: Expected prefix (e.g., "del-", "hold-")

    Raises:
        ValueError: If the ID contains unsafe characters
    """
    if not _SAFE_ID_RE.match(identifier):
        raise ValueError(
            f"Invalid identifier: contains unsafe characters "
            f"(must match {_SAFE_ID_RE.pattern})"
        )
    if prefix and not identifier.startswith(prefix):
        raise ValueError(f"Invalid identifier: must start with '{prefix}'")


# Maximum length for tenant IDs
_MAX_TENANT_ID_LENGTH = 64


def validate_tenant_id(tenant_id: str) -> None:
    """Validate a tenant identifier for multi-tenancy.

    Tenant IDs must:
    - Match the safe ID pattern (alphanumeric, hyphens, underscores)
    - Be at most 64 characters long
    - Not contain path separators

    Args:
        tenant_id: The tenant ID to validate.

    Raises:
        ValueError: If the tenant ID is invalid.
    """
    if not tenant_id:
        raise ValueError("Tenant ID cannot be empty")
    if len(tenant_id) > _MAX_TENANT_ID_LENGTH:
        raise ValueError(
            f"Tenant ID too long: {len(tenant_id)} characters "
            f"(maximum {_MAX_TENANT_ID_LENGTH})"
        )
    if "/" in tenant_id or "\\" in tenant_id:
        raise ValueError("Tenant ID must not contain path separators")
    validate_id(tenant_id)


def safe_read_json(path: Path) -> dict[str, Any]:
    """Read a JSON file with O_NOFOLLOW to prevent symlink TOCTOU attacks.

    Uses a single atomic os.open() call with O_NOFOLLOW, eliminating
    the race window of separate check-then-open patterns.

    Raises:
        OSError: If the path is a symlink
        FileNotFoundError: If the path does not exist
    """
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(path), flags)
    except OSError as e:
        if e.errno == errno.ELOOP:
            raise OSError(f"Refusing to read symlink (possible attack): {path}") from e
        raise
    try:
        f = os.fdopen(fd, "r")
    except Exception:
        os.close(fd)  # fdopen failed — close fd to prevent leak
        raise
    with f:
        return json.load(f)


def safe_read_text(path: Path, encoding: str = "utf-8") -> str:
    """Read a text file with O_NOFOLLOW to prevent symlink TOCTOU attacks.

    Uses a single atomic os.open() call with O_NOFOLLOW, eliminating
    the race window of separate check-then-open patterns.

    Args:
        path: Path to the text file.
        encoding: Text encoding (default: utf-8).

    Raises:
        OSError: If the path is a symlink (ELOOP on POSIX).
        FileNotFoundError: If the path does not exist.
    """
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(path), flags)
    except OSError as e:
        if e.errno == errno.ELOOP:
            raise OSError(f"Refusing to read symlink (possible attack): {path}") from e
        raise
    try:
        f = os.fdopen(fd, "r", encoding=encoding)
    except Exception:
        os.close(fd)  # fdopen failed — close fd to prevent leak
        raise
    with f:
        return f.read()


def _safe_write_text(path: Path, content: str) -> None:
    """Write text to a file with O_NOFOLLOW to prevent symlink attacks.

    Uses atomic write pattern (temp file + rename) for crash safety.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.stem}.",
        suffix=".tmp",
    )
    try:
        os.write(fd, content.encode())
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(tmp_path, str(path))
    except BaseException:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def compute_wal_hash(wal_data: dict[str, Any]) -> str:
    """Compute a SHA-256 hash of WAL content for tamper detection.

    The hash covers the planned_revocations list and reason,
    allowing recovery to verify the WAL wasn't modified on disk.
    """
    payload = json.dumps(
        {
            "root_delegate_id": wal_data["root_delegate_id"],
            "planned_revocations": wal_data["planned_revocations"],
            "reason": wal_data["reason"],
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()
