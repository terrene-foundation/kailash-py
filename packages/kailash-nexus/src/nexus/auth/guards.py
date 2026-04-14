# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Per-handler authorization guards for Nexus.

AuthGuard provides a declarative way to attach RBAC constraints to
individual handlers rather than relying solely on route-scoped
middleware. When a handler is registered with ``guard=``, the guard's
``check()`` method is called before the handler function executes. If
the check fails, a ``PermissionError`` is raised and the handler never
runs.

Usage::

    from nexus.auth.guards import AuthGuard

    @app.handler("agent.create", guard=AuthGuard.RequirePermission("agents:create"))
    async def create_agent(name: str) -> dict:
        ...

    @app.handler("admin.reset", guard=AuthGuard.RequireRole("admin"))
    async def admin_reset() -> dict:
        ...

    # Combine guards (all must pass)
    @app.handler("org.delete",
        guard=AuthGuard.All(
            AuthGuard.RequireRole("admin"),
            AuthGuard.RequirePermission("orgs:delete"),
        ))
    async def delete_org(org_id: str) -> dict:
        ...

Note: Do NOT use ``from __future__ import annotations`` in this module.
FastAPI inspects parameter annotations at runtime to recognize special types
like Request. PEP 563 deferred annotations turn them into strings, which
prevents FastAPI from injecting the Request object.
"""

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "AuthGuard",
    "BaseGuard",
    "RequireRoleGuard",
    "RequirePermissionGuard",
    "AllGuard",
    "AnyGuard",
    "CustomGuard",
]


class BaseGuard:
    """Abstract base for authorization guards.

    Subclasses implement ``check(user, request_context)`` which returns
    ``(passed, reason)`` where ``reason`` is a server-side diagnostic
    (never leaked to the client).
    """

    def check(
        self,
        user: Any,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """Check whether the request is authorized.

        Args:
            user: The authenticated user object (``AuthenticatedUser``
                from ``request.state.user``). May be ``None`` if no
                auth middleware is installed.
            request_context: Optional dict with transport-specific
                context (e.g., ``{"path": "/api/...", "method": "POST"}``
                for HTTP, ``{"tool_name": "..."}`` for MCP).

        Returns:
            Tuple of ``(passed, reason)``. When ``passed`` is False,
            ``reason`` is a server-side diagnostic string that is logged
            but never sent to the client.
        """
        raise NotImplementedError("Subclasses must implement check()")

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"


class RequireRoleGuard(BaseGuard):
    """Guard that requires the user to have at least one of the given roles."""

    def __init__(self, *roles: str) -> None:
        if not roles:
            raise ValueError("RequireRoleGuard requires at least one role")
        self.roles = roles

    def check(
        self,
        user: Any,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        if user is None:
            return False, "No authenticated user"
        if hasattr(user, "has_any_role") and user.has_any_role(*self.roles):
            return True, ""
        # Fallback: check roles attribute directly
        user_roles = getattr(user, "roles", None) or []
        if any(r in user_roles for r in self.roles):
            return True, ""
        return False, f"User lacks required roles: {self.roles}"

    def __repr__(self) -> str:
        return f"RequireRoleGuard({', '.join(repr(r) for r in self.roles)})"


class RequirePermissionGuard(BaseGuard):
    """Guard that requires the user to have at least one of the given permissions."""

    def __init__(self, *permissions: str) -> None:
        if not permissions:
            raise ValueError("RequirePermissionGuard requires at least one permission")
        self.permissions = permissions

    def check(
        self,
        user: Any,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        if user is None:
            return False, "No authenticated user"

        # Check user's direct permissions
        if hasattr(user, "has_any_permission") and user.has_any_permission(
            *self.permissions
        ):
            return True, ""

        # Check RBAC-resolved permissions from request context
        rbac_permissions = (request_context or {}).get("rbac_permissions")
        if rbac_permissions:
            try:
                from kailash.trust.auth.rbac import matches_permission_set
            except ImportError:
                pass
            else:
                for perm in self.permissions:
                    if matches_permission_set(rbac_permissions, perm):
                        return True, ""

        # Fallback: check permissions attribute directly
        user_perms = getattr(user, "permissions", None) or []
        if any(p in user_perms for p in self.permissions):
            return True, ""

        return False, f"User lacks required permissions: {self.permissions}"

    def __repr__(self) -> str:
        return (
            f"RequirePermissionGuard"
            f"({', '.join(repr(p) for p in self.permissions)})"
        )


class AllGuard(BaseGuard):
    """Composite guard that requires ALL inner guards to pass."""

    def __init__(self, *guards: BaseGuard) -> None:
        if len(guards) < 2:
            raise ValueError("AllGuard requires at least 2 guards")
        self.guards = guards

    def check(
        self,
        user: Any,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        for guard in self.guards:
            passed, reason = guard.check(user, request_context)
            if not passed:
                return False, reason
        return True, ""

    def __repr__(self) -> str:
        inner = ", ".join(repr(g) for g in self.guards)
        return f"AllGuard({inner})"


class AnyGuard(BaseGuard):
    """Composite guard that requires at least one inner guard to pass."""

    def __init__(self, *guards: BaseGuard) -> None:
        if len(guards) < 2:
            raise ValueError("AnyGuard requires at least 2 guards")
        self.guards = guards

    def check(
        self,
        user: Any,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        reasons = []
        for guard in self.guards:
            passed, reason = guard.check(user, request_context)
            if passed:
                return True, ""
            reasons.append(reason)
        return False, " AND ".join(reasons)

    def __repr__(self) -> str:
        inner = ", ".join(repr(g) for g in self.guards)
        return f"AnyGuard({inner})"


class CustomGuard(BaseGuard):
    """Guard backed by a user-provided callable.

    The callable receives ``(user, request_context)`` and returns
    ``(passed: bool, reason: str)``.
    """

    def __init__(self, check_fn, description: str = "custom guard") -> None:
        if not callable(check_fn):
            raise TypeError("check_fn must be callable")
        self._check_fn = check_fn
        self._description = description

    def check(
        self,
        user: Any,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        return self._check_fn(user, request_context)

    def __repr__(self) -> str:
        return f"CustomGuard({self._description!r})"


class AuthGuard:
    """Factory namespace for creating authorization guards.

    Provides static factory methods that return ``BaseGuard`` instances.
    This is the primary public API for per-handler auth.

    Example::

        @app.handler("item.delete", guard=AuthGuard.RequirePermission("items:delete"))
        async def delete_item(item_id: str) -> dict:
            ...
    """

    @staticmethod
    def RequireRole(*roles: str) -> RequireRoleGuard:
        """Guard requiring at least one of the specified roles."""
        return RequireRoleGuard(*roles)

    @staticmethod
    def RequirePermission(*permissions: str) -> RequirePermissionGuard:
        """Guard requiring at least one of the specified permissions."""
        return RequirePermissionGuard(*permissions)

    @staticmethod
    def All(*guards: BaseGuard) -> AllGuard:
        """Composite guard: all inner guards must pass."""
        return AllGuard(*guards)

    @staticmethod
    def Any(*guards: BaseGuard) -> AnyGuard:
        """Composite guard: at least one inner guard must pass."""
        return AnyGuard(*guards)

    @staticmethod
    def Custom(check_fn, description: str = "custom guard") -> CustomGuard:
        """Guard backed by a user-provided callable."""
        return CustomGuard(check_fn, description=description)
