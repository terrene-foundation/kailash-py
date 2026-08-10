# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Owner-only file protection, across POSIX and Windows.

This module is the **single source of truth** for "make this file readable by
its owner and nobody else". Every site that writes secret material — API keys,
private keys, audit logs — MUST route through :func:`restrict_to_owner` rather
than calling ``os.fchmod`` / ``os.chmod`` directly.

Why a helper rather than a call-site ``chmod``:

* ``os.fchmod`` **does not exist on Windows**. A bare call raises
  ``AttributeError`` there, turning a permission-hardening fix into a hard
  crash — which is exactly what happened to the first version of this change.
* POSIX mode bits do not carry over. ``os.chmod`` exists on Windows but only
  toggles the read-only attribute; it does **not** restrict who may read the
  file. Confidentiality on Windows requires a DACL, which needs ``pywin32``.
* So "did the owner-only guarantee actually get applied?" has a genuinely
  different answer per platform, and callers deserve to be told rather than
  left believing a ``0o600`` they can see in the source is in force.

That last point is why :func:`restrict_to_owner` returns a ``bool`` instead of
``None``: a protection that silently does not apply is precisely the failure
mode this module exists to prevent (``rules/security.md`` § Secure-Default For
A New Security Feature).
"""

from __future__ import annotations

import logging
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

__all__ = [
    "restrict_to_owner",
    "restrict_dir_to_owner",
    "OWNER_ONLY_MODE",
    "OWNER_ONLY_DIR_MODE",
    "owner_only_is_enforceable",
]

# Owner read/write, no group, no other. Meaningful on POSIX only.
OWNER_ONLY_MODE = 0o600

# Directories additionally need the execute bit to be traversable by their
# owner; 0o600 on a directory locks the owner out of its own store.
OWNER_ONLY_DIR_MODE = 0o700


@lru_cache(maxsize=1)
def _warn_no_acl_mechanism() -> None:
    """Warn that this platform cannot restrict access, once per process.

    Once, not once per call: a per-write warning on a busy audit log would be
    its own denial of service on the operator's log stream. ``lru_cache`` is
    the one-shot latch -- tests reset it with ``cache_clear()``.

    The message deliberately does not call the file "secret": this helper is
    general-purpose and the caller may be protecting an audit log or a key.
    What matters is naming the mechanism that is missing and how to supply it.
    """
    logger.warning(
        "File permissions are NOT access-controlled on this platform. POSIX "
        "mode bits do not restrict readers on Windows, and pywin32 is not "
        "installed, so no DACL could be applied. Any user able to read the "
        "containing directory can read files this process intended to be "
        "owner-only. Install pywin32 (pip install pywin32), or place them in "
        "a directory whose ACL already restricts access."
    )


def owner_only_is_enforceable() -> bool:
    """Whether this platform can enforce owner-only access at all.

    True on POSIX always; on Windows only when ``pywin32`` is importable, since
    the DACL is the sole mechanism that restricts *readers* there.
    """
    if sys.platform != "win32":
        return True
    try:
        import win32security  # type: ignore[import-untyped]  # noqa: F401
    except ImportError:
        return False
    return True


def _restrict_via_dacl(path: Union[str, Path]) -> bool:
    """Windows: restrict the file's DACL to the current user's SID."""
    try:
        import ntsecuritycon as con  # type: ignore[import-untyped]
        import win32api  # type: ignore[import-untyped]
        import win32security  # type: ignore[import-untyped]
    except ImportError:
        # The path is deliberately NOT interpolated here. The warning is about
        # a missing platform mechanism, not about one file, and it fires once
        # per process -- naming a single arbitrary path would misleadingly
        # imply only that file is affected. Callers that need per-file
        # attribution have the False return value.
        _warn_no_acl_mechanism()
        return False

    username = win32api.GetUserName()
    user_sid = win32security.LookupAccountName(None, username)[0]
    dacl = win32security.ACL()
    dacl.AddAccessAllowedAce(
        win32security.ACL_REVISION,
        con.FILE_GENERIC_READ | con.FILE_GENERIC_WRITE,
        user_sid,
    )
    descriptor = win32security.GetFileSecurity(
        str(path), win32security.DACL_SECURITY_INFORMATION
    )
    descriptor.SetSecurityDescriptorDacl(True, dacl, False)
    win32security.SetFileSecurity(
        str(path), win32security.DACL_SECURITY_INFORMATION, descriptor
    )
    return True


def restrict_to_owner(
    path: Union[str, Path],
    *,
    fd: Optional[int] = None,
) -> bool:
    """Restrict ``path`` so only its owner can read or write it.

    Args:
        path: The file to protect. Used for the Windows DACL call and for
            diagnostics; on POSIX it is only needed when ``fd`` is omitted.
        fd: An OPEN descriptor for that file. Strongly preferred on POSIX: it
            makes the change apply to the object already opened, so a symlink
            swapped in between the open and the mode change cannot redirect it
            the way a second path lookup could. Windows has no ``fchmod``, so
            the descriptor is unused there.

    Returns:
        ``True`` if owner-only access was actually enforced. ``False`` on
        Windows without ``pywin32``, where no mechanism was available -- the
        file was still written, but it is NOT confidential. Callers handling
        secret material should treat ``False`` as a real finding, not noise.
    """
    if sys.platform == "win32":
        return _restrict_via_dacl(path)

    # POSIX. Prefer the descriptor-based call; fall back to the path only when
    # the caller has no fd (e.g. hardening a file created by an earlier run).
    if fd is not None and hasattr(os, "fchmod"):
        os.fchmod(fd, OWNER_ONLY_MODE)
    else:
        os.chmod(path, OWNER_ONLY_MODE)
    return True


def restrict_dir_to_owner(path: Union[str, Path]) -> bool:
    """Restrict a DIRECTORY so only its owner can list or traverse it.

    Same contract as :func:`restrict_to_owner`, with ``0o700`` instead of
    ``0o600`` because a directory without the owner's execute bit cannot be
    opened even by its owner. Kept here rather than as a call-site ``chmod``
    for the reason in the module docstring: the Windows answer is a DACL, not
    a mode, and only this module knows that.

    ``os.makedirs(..., mode=0o700)`` alone is not enough on POSIX: the mode is
    masked by the process umask, and it is ignored entirely for a directory
    that already exists — which is the common case for a long-lived store.

    Returns:
        ``True`` if owner-only access was actually enforced, ``False`` on
        Windows without ``pywin32`` (the directory exists, but is NOT private).
    """
    if sys.platform == "win32":
        return _restrict_via_dacl(path)
    os.chmod(path, OWNER_ONLY_DIR_MODE)
    return True
