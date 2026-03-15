# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Role-Based Access Control (RBAC) for TrustPlane.

Provides role assignment, permission checking, and persistence for
controlling who can perform which TrustPlane operations.

Roles:
    ADMIN    -- All operations.
    AUDITOR  -- Read-only: verify, status, decisions, export.
    DELEGATE -- Record within delegated constraints: decide, milestone,
                hold_approve, hold_deny.
    OBSERVER -- Shadow mode only: shadow, status.

Security:
    - User IDs are validated via ``validate_id()`` to prevent path
      traversal when IDs are used in file paths.
    - RBAC state is persisted atomically via ``atomic_write()``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from trustplane._locking import atomic_write, file_lock, safe_read_json, validate_id
from trustplane.exceptions import TrustPlaneError

logger = logging.getLogger(__name__)

__all__ = [
    "Role",
    "RolePermission",
    "RBACManager",
    "OPERATIONS",
    "ROLE_PERMISSIONS",
]


# ---------------------------------------------------------------------------
# All known TrustPlane operations
# ---------------------------------------------------------------------------

OPERATIONS: frozenset[str] = frozenset(
    {
        "decide",
        "milestone",
        "verify",
        "status",
        "export",
        "hold_approve",
        "hold_deny",
        "shadow",
        "init",
        "migrate",
        "rbac_assign",
        "decisions",
    }
)


# ---------------------------------------------------------------------------
# Role enum
# ---------------------------------------------------------------------------


class Role(str, Enum):
    """TrustPlane user roles."""

    ADMIN = "admin"
    AUDITOR = "auditor"
    DELEGATE = "delegate"
    OBSERVER = "observer"


# ---------------------------------------------------------------------------
# RolePermission
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RolePermission:
    """Maps a role to its allowed operations.

    Attributes:
        role: The role this permission set describes.
        allowed_operations: The set of operation names the role may perform.
    """

    role: Role
    allowed_operations: frozenset[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "allowed_operations": sorted(self.allowed_operations),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RolePermission:
        for field_name in ("role", "allowed_operations"):
            if field_name not in data:
                raise ValueError(
                    f"RolePermission.from_dict: missing required field '{field_name}'"
                )
        return cls(
            role=Role(data["role"]),
            allowed_operations=frozenset(data["allowed_operations"]),
        )


# ---------------------------------------------------------------------------
# Default permission matrix
# ---------------------------------------------------------------------------

ROLE_PERMISSIONS: dict[Role, RolePermission] = {
    Role.ADMIN: RolePermission(
        role=Role.ADMIN,
        allowed_operations=frozenset(OPERATIONS),
    ),
    Role.AUDITOR: RolePermission(
        role=Role.AUDITOR,
        allowed_operations=frozenset({"verify", "status", "decisions", "export"}),
    ),
    Role.DELEGATE: RolePermission(
        role=Role.DELEGATE,
        allowed_operations=frozenset(
            {"decide", "milestone", "hold_approve", "hold_deny"}
        ),
    ),
    Role.OBSERVER: RolePermission(
        role=Role.OBSERVER,
        allowed_operations=frozenset({"shadow", "status"}),
    ),
}


# ---------------------------------------------------------------------------
# RBACManager
# ---------------------------------------------------------------------------


class RBACError(TrustPlaneError):
    """Raised for RBAC-specific errors."""


class RBACManager:
    """Manages role assignments and permission checks.

    Persists role assignments in a JSON file at ``rbac_path``.

    Args:
        rbac_path: Path to the ``rbac.json`` file. The file and its parent
            directories are created on the first ``assign_role()`` call
            if they do not exist.
    """

    def __init__(self, rbac_path: Path) -> None:
        self._rbac_path = rbac_path
        self._assignments: dict[str, Role] = {}
        self._last_mtime: float = 0.0
        self._load()

    # -- Public API --------------------------------------------------------

    def assign_role(self, user_id: str, role: Role) -> None:
        """Assign *role* to *user_id*, persisting immediately.

        If the user already has a role, it is overwritten.

        Args:
            user_id: Safe identifier for the user (validated).
            role: The role to assign.

        Raises:
            ValueError: If *user_id* contains unsafe characters.
        """
        validate_id(user_id)
        logger.info("Assigning role %s to user %s", role.value, user_id)
        lock_path = self._rbac_path.with_suffix(".lock")
        with file_lock(lock_path):
            self._load()  # Re-read under lock to avoid lost updates
            self._assignments[user_id] = role
            self._save()

    def get_role(self, user_id: str) -> Role | None:
        """Return the role for *user_id*, or ``None`` if unassigned.

        Re-reads from disk if the file has been modified by another process,
        ensuring revocations are reflected immediately (fail-closed).

        Args:
            user_id: Safe identifier for the user (validated).

        Raises:
            ValueError: If *user_id* contains unsafe characters.
        """
        validate_id(user_id)
        self._refresh_if_stale()
        return self._assignments.get(user_id)

    def list_assignments(self) -> list[dict[str, str]]:
        """Return all role assignments as a list of dicts.

        Each dict has ``user_id`` and ``role`` keys.
        """
        return [
            {"user_id": uid, "role": role.value}
            for uid, role in sorted(self._assignments.items())
        ]

    def check_permission(self, user_id: str, operation: str) -> bool:
        """Check whether *user_id* is permitted to perform *operation*.

        Returns ``False`` if the user has no role or the operation is not
        in the user's allowed set. Never raises for unknown operations --
        unknown operations are simply denied.

        Re-reads from disk if the file has been modified by another process,
        ensuring revocations take effect immediately (fail-closed).

        Args:
            user_id: Safe identifier for the user (validated).
            operation: The operation name to check.

        Raises:
            ValueError: If *user_id* contains unsafe characters.
        """
        validate_id(user_id)
        self._refresh_if_stale()
        role = self._assignments.get(user_id)
        if role is None:
            logger.debug(
                "Permission denied for user %s (no role assigned): operation=%s",
                user_id,
                operation,
            )
            return False
        perm = ROLE_PERMISSIONS.get(role)
        if perm is None:
            logger.warning(
                "No permission definition found for role %s (user %s)",
                role.value,
                user_id,
            )
            return False
        allowed = operation in perm.allowed_operations
        if not allowed:
            logger.debug(
                "Permission denied for user %s (role=%s): operation=%s not in %s",
                user_id,
                role.value,
                operation,
                sorted(perm.allowed_operations),
            )
        return allowed

    def revoke_role(self, user_id: str) -> None:
        """Revoke the role for *user_id*.

        Args:
            user_id: Safe identifier for the user (validated).

        Raises:
            ValueError: If *user_id* contains unsafe characters.
            RBACError: If the user has no role assigned.
        """
        validate_id(user_id)
        lock_path = self._rbac_path.with_suffix(".lock")
        with file_lock(lock_path):
            self._load()  # Re-read under lock to avoid lost updates
            if user_id not in self._assignments:
                raise RBACError(
                    f"Cannot revoke role for user '{user_id}': no role assigned"
                )
            logger.info("Revoking role for user %s", user_id)
            del self._assignments[user_id]
            self._save()

    # -- Persistence -------------------------------------------------------

    def _refresh_if_stale(self) -> None:
        """Re-read from disk if the file has been modified since last load.

        Uses mtime-based cache invalidation so that role revocations from
        other processes take effect immediately (fail-closed). The ``stat()``
        call is lightweight relative to the full ``_load()`` parse.
        """
        try:
            if self._rbac_path.exists():
                current_mtime = self._rbac_path.stat().st_mtime
                if current_mtime != self._last_mtime:
                    self._load()
        except OSError:
            pass  # File temporarily unavailable — use cached assignments

    def _load(self) -> None:
        """Load assignments from disk if the file exists."""
        if not self._rbac_path.exists() or self._rbac_path.stat().st_size == 0:
            logger.debug(
                "No rbac.json at %s — starting with empty assignments", self._rbac_path
            )
            self._last_mtime = 0.0
            return
        try:
            self._last_mtime = self._rbac_path.stat().st_mtime
            data = safe_read_json(self._rbac_path)
        except json.JSONDecodeError as exc:
            raise RBACError(
                f"RBAC file contains invalid JSON: {self._rbac_path}: {exc}"
            ) from exc
        except OSError as exc:
            raise RBACError(
                f"Failed to read RBAC file: {self._rbac_path}: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise RBACError(
                f"RBAC file root must be a JSON object, got {type(data).__name__}: "
                f"{self._rbac_path}"
            )
        assignments_raw = data.get("assignments", {})
        if not isinstance(assignments_raw, dict):
            raise RBACError(
                f"'assignments' must be a JSON object, got {type(assignments_raw).__name__}"
            )
        self._assignments.clear()
        for uid, role_str in assignments_raw.items():
            try:
                self._assignments[uid] = Role(role_str)
            except ValueError:
                logger.warning(
                    "Skipping unknown role '%s' for user '%s' in %s",
                    role_str,
                    uid,
                    self._rbac_path,
                )

    def _save(self) -> None:
        """Persist assignments to disk atomically."""
        data = {
            "assignments": {uid: role.value for uid, role in self._assignments.items()}
        }
        atomic_write(self._rbac_path, data)
        logger.debug("Saved RBAC assignments to %s", self._rbac_path)
