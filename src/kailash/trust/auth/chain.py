# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Auth middleware chain ordering enforcement.

Provides ``AuthMiddlewareChain`` that validates and enforces the correct
ordering of authentication/authorization middleware components.

The canonical request execution order (outermost to innermost):
    1. RateLimit (before auth, prevent abuse)
    2. JWT (core authentication)
    3. RBAC (needs JWT user for role -> permission resolution)
    4. Session (needs authenticated user)
    5. Audit (innermost — captures authenticated, authorized requests)

In Starlette, middleware added later wraps middleware added earlier,
so components must be added in reverse order (innermost first).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

__all__ = [
    "AuthMiddlewareChain",
    "MiddlewareSlot",
]


class MiddlewareSlot(str, Enum):
    """Canonical middleware ordering slots.

    Values represent execution priority (lower = runs first / outermost).
    """

    RATE_LIMIT = "rate_limit"  # 1 - outermost
    JWT = "jwt"  # 2
    RBAC = "rbac"  # 3
    SESSION = "session"  # 4
    AUDIT = "audit"  # 5 - innermost

    @property
    def priority(self) -> int:
        """Execution priority (1 = outermost)."""
        _priorities = {
            "rate_limit": 1,
            "jwt": 2,
            "rbac": 3,
            "session": 4,
            "audit": 5,
        }
        return _priorities[self.value]


@dataclass
class _ChainEntry:
    """Internal entry tracking a middleware component."""

    slot: MiddlewareSlot
    config: Any
    enabled: bool = True


class AuthMiddlewareChain:
    """Validates and enforces auth middleware ordering.

    Ensures middleware components are installed in the correct order
    to prevent dependency violations (e.g., RBAC running before JWT).

    Usage:
        >>> chain = AuthMiddlewareChain()
        >>> chain.add(MiddlewareSlot.JWT, jwt_config)
        >>> chain.add(MiddlewareSlot.RBAC, rbac_config)
        >>> chain.validate()  # Checks JWT is present since RBAC requires it
        >>> for slot, config in chain.ordered():
        ...     install_middleware(slot, config)
    """

    def __init__(self) -> None:
        self._entries: Dict[MiddlewareSlot, _ChainEntry] = {}

    def add(self, slot: MiddlewareSlot, config: Any) -> None:
        """Add a middleware component to the chain.

        Args:
            slot: Middleware slot
            config: Configuration for the middleware

        Raises:
            ValueError: If slot already occupied
        """
        if slot in self._entries:
            raise ValueError(
                f"Middleware slot '{slot.value}' is already occupied. "
                f"Remove it first with remove()."
            )
        self._entries[slot] = _ChainEntry(slot=slot, config=config)
        logger.debug("Added middleware to chain: %s", slot.value)

    def remove(self, slot: MiddlewareSlot) -> None:
        """Remove a middleware component.

        Args:
            slot: Middleware slot to remove
        """
        self._entries.pop(slot, None)

    def validate(self) -> List[str]:
        """Validate middleware chain dependencies.

        Returns:
            List of validation warnings (empty if valid)

        Raises:
            ValueError: If critical dependency violations are found
        """
        warnings: List[str] = []

        # RBAC requires JWT
        if (
            MiddlewareSlot.RBAC in self._entries
            and MiddlewareSlot.JWT not in self._entries
        ):
            raise ValueError(
                "RBAC middleware requires JWT middleware. "
                "Add JWT before RBAC in the chain."
            )

        # Session requires JWT
        if (
            MiddlewareSlot.SESSION in self._entries
            and MiddlewareSlot.JWT not in self._entries
        ):
            raise ValueError(
                "Session middleware requires JWT middleware. "
                "Add JWT before Session in the chain."
            )

        # Audit without JWT means no user_id in audit records
        if (
            MiddlewareSlot.AUDIT in self._entries
            and MiddlewareSlot.JWT not in self._entries
        ):
            warnings.append(
                "Audit middleware without JWT: audit records will not contain user_id"
            )

        return warnings

    def ordered(self) -> List[tuple]:
        """Get middleware entries in correct installation order.

        Returns entries in reverse priority order (innermost first)
        since Starlette wraps middleware added later around earlier ones.

        Returns:
            List of (MiddlewareSlot, config) tuples in installation order
        """
        entries = sorted(
            self._entries.values(),
            key=lambda e: e.slot.priority,
            reverse=True,  # Innermost (highest priority number) first
        )
        return [(e.slot, e.config) for e in entries if e.enabled]

    def __contains__(self, slot: MiddlewareSlot) -> bool:
        return slot in self._entries

    def __len__(self) -> int:
        return len(self._entries)
