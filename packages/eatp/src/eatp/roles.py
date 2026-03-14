# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP Trust Roles and Role-Based Access Control.

Defines the TrustRole enum and permission-checking utilities for controlling
which EATP operations each role may perform. Roles are a standalone access
control layer -- they do NOT modify TrustOperations internally. Callers use
``check_permission`` or ``require_permission`` as guards before invoking
TrustOperations methods.

Backward Compatibility:
    When no role is set (role is None), all operations are permitted. This
    preserves existing behavior for codebases that do not use role-based
    access control.

Roles:
    - ADMIN: Full access to all EATP operations (establish, delegate,
      verify, audit, read).
    - OPERATOR: Can delegate, verify, and read trust data but cannot
      establish new trust chains or perform audits.
    - OBSERVER: Read-only access to trust state.
    - AUDITOR: Can audit and read all evidence but cannot modify
      trust state.

Example::

    from eatp.roles import TrustRole, require_permission

    role = TrustRole.OPERATOR

    # Guard before calling ops.delegate(...)
    require_permission(role, "delegate")  # passes

    # Guard before calling ops.establish(...)
    require_permission(role, "establish")  # raises PermissionError
"""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import FrozenSet, Mapping, Optional


class TrustRole(str, Enum):
    """Trust role for EATP role-based access control.

    Each role defines a set of EATP operations it may perform.
    Roles are ``str`` enums so they serialize naturally to JSON.
    """

    ADMIN = "admin"
    OPERATOR = "operator"
    OBSERVER = "observer"
    AUDITOR = "auditor"


ROLE_PERMISSIONS: Mapping[TrustRole, FrozenSet[str]] = MappingProxyType(
    {
        TrustRole.ADMIN: frozenset(
            {"establish", "delegate", "verify", "audit", "read"}
        ),
        TrustRole.OPERATOR: frozenset({"delegate", "verify", "read"}),
        TrustRole.OBSERVER: frozenset({"read"}),
        TrustRole.AUDITOR: frozenset({"audit", "read"}),
    }
)
"""Mapping from each TrustRole to its permitted EATP operations.

Operations:
    - ``establish``: Create initial trust for an agent (genesis record + key binding)
    - ``delegate``: Transfer trust from one agent to another with constraints
    - ``verify``: Validate an agent's trust chain and produce a verification verdict
    - ``audit``: Record agent actions in an immutable, hash-linked audit trail
    - ``read``: Read trust state, chains, verification results, and evidence
"""


def check_permission(role: Optional[TrustRole], operation: str) -> bool:
    """Check whether a role is permitted to perform an operation.

    Args:
        role: The TrustRole to check. ``None`` means no RBAC enforcement
            (backward-compatible all-access).
        operation: The EATP operation name (e.g. ``"establish"``, ``"read"``).

    Returns:
        ``True`` if the operation is permitted, ``False`` otherwise.
    """
    if role is None:
        return True
    return operation in ROLE_PERMISSIONS.get(role, set())


def require_permission(role: Optional[TrustRole], operation: str) -> None:
    """Raise ``PermissionError`` if the role cannot perform the operation.

    This is the guard function callers should use before invoking
    TrustOperations methods.

    Args:
        role: The TrustRole to check. ``None`` means no RBAC enforcement
            (backward-compatible all-access).
        operation: The EATP operation name (e.g. ``"establish"``, ``"read"``).

    Raises:
        PermissionError: If the role is not permitted to perform the operation.
            The error message includes the role value and operation name for
            clear debugging.
    """
    if not check_permission(role, operation):
        role_name = role.value if role is not None else "None"
        raise PermissionError(f"Role '{role_name}' cannot perform '{operation}'")


__all__ = [
    "TrustRole",
    "ROLE_PERMISSIONS",
    "check_permission",
    "require_permission",
]
