# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PactGovernanceMiddleware -- Kaizen middleware for governance enforcement.

The middleware provides a pre-execution check for Kaizen agent tool calls
without requiring subclassing. It returns GovernanceVerdict objects that
the caller (Kaizen bridge, agent framework) can use to decide whether
to proceed, hold, or block.

Unlike PactGovernedAgent (which raises exceptions), the middleware is a
low-level building block that returns verdicts for the caller to handle.
This allows integration with different execution frameworks.

Thread-safe: delegates to GovernanceEngine which has its own lock.
"""

from __future__ import annotations

import logging
from typing import Any

from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.verdict import GovernanceVerdict

logger = logging.getLogger(__name__)

__all__ = ["PactGovernanceMiddleware"]


class PactGovernanceMiddleware:
    """Kaizen middleware for governance enforcement without subclassing.

    Returns GovernanceVerdict from pre_execute() for the caller to handle.
    Does NOT raise exceptions or block execution directly -- that is the
    caller's responsibility.

    Args:
        engine: The GovernanceEngine for verification decisions.
        role_address: The D/T/R positional address for the role this
            middleware is enforcing.
    """

    def __init__(
        self,
        engine: GovernanceEngine,
        role_address: str,
    ) -> None:
        self._engine = engine
        self._role_address = role_address

    @property
    def role_address(self) -> str:
        """The D/T/R address this middleware is enforcing."""
        return self._role_address

    def pre_execute(
        self,
        action_name: str,
        context: dict[str, Any] | None = None,
    ) -> GovernanceVerdict:
        """Check governance before tool execution.

        Called before each tool execution. Returns a GovernanceVerdict
        that the caller should inspect to decide whether to proceed.

        This method does NOT raise exceptions -- it returns verdicts.
        The PactGovernedAgent layer converts these into exceptions
        for the agent runtime.

        Args:
            action_name: The action being attempted.
            context: Optional context dict with additional info:
                - "cost": float -- for financial constraint checks
                - "resource": KnowledgeItem -- for knowledge access checks

        Returns:
            A GovernanceVerdict with level (auto_approved, flagged, held, blocked),
            reason, and audit details.
        """
        return self._engine.verify_action(
            self._role_address,
            action_name,
            context or {},
        )
