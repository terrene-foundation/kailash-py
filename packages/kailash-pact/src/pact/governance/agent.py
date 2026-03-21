# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""PactGovernedAgent -- wraps any agent with PACT governance enforcement.

Key security properties:
1. Agent receives GovernanceContext (frozen), NOT GovernanceEngine
2. All tool calls go through governance verification
3. BLOCKED -> GovernanceBlockedError
4. HELD -> GovernanceHeldError
5. FLAGGED -> warning + proceed
6. AUTO_APPROVED -> proceed silently
7. Unregistered tools are DEFAULT-DENY (GovernanceBlockedError)

Per governance.md MUST NOT Rule 2: agents operate within governance
constraints and must not be able to modify the constraints they are
subject to. The engine is private (_engine); only the frozen context
is exposed.

Per governance.md MUST NOT Rule 5: tool access is DEFAULT-DENY. Tools
must be explicitly registered. Unregistered tools are blocked.
"""

from __future__ import annotations

import logging
from typing import Any

from pact.build.config.schema import TrustPostureLevel
from pact.governance.context import GovernanceContext
from pact.governance.engine import GovernanceEngine
from pact.governance.verdict import GovernanceVerdict

logger = logging.getLogger(__name__)

__all__ = [
    "GovernanceBlockedError",
    "GovernanceHeldError",
    "PactGovernedAgent",
]


class GovernanceBlockedError(Exception):
    """Raised when governance blocks an agent action.

    Attributes:
        verdict: The GovernanceVerdict that caused the block.
    """

    def __init__(self, verdict: GovernanceVerdict) -> None:
        self.verdict = verdict
        super().__init__(f"Governance BLOCKED: {verdict.reason}")


class GovernanceHeldError(Exception):
    """Raised when governance holds an action for human approval.

    Attributes:
        verdict: The GovernanceVerdict that caused the hold.
    """

    def __init__(self, verdict: GovernanceVerdict) -> None:
        self.verdict = verdict
        super().__init__(f"Governance HELD: {verdict.reason}")


class PactGovernedAgent:
    """Wraps any agent with PACT governance enforcement.

    Key security properties:
    - Agent receives GovernanceContext (frozen), NOT GovernanceEngine
    - All tool calls go through governance verification
    - BLOCKED -> GovernanceBlockedError
    - HELD -> GovernanceHeldError
    - FLAGGED -> warning + proceed
    - AUTO_APPROVED -> proceed silently
    - Unregistered tools are DEFAULT-DENY

    Args:
        engine: The GovernanceEngine for verification. NOT exposed to agents.
        role_address: The D/T/R positional address for this agent's role.
        posture: The trust posture level for this agent.
            Defaults to SUPERVISED (safest).
    """

    def __init__(
        self,
        engine: GovernanceEngine,
        role_address: str,
        posture: TrustPostureLevel = TrustPostureLevel.SUPERVISED,
    ) -> None:
        self._engine = engine  # Private -- NOT exposed to agent code
        self._role_address = role_address
        self._posture = posture
        self._context = engine.get_context(role_address, posture=posture)
        self._registered_tools: dict[str, dict[str, Any]] = {}

    @property
    def context(self) -> GovernanceContext:
        """Read-only governance context for the agent.

        This is the ONLY governance state visible to the agent.
        It is frozen (immutable) -- agents cannot modify their constraints.
        """
        return self._context

    def register_tool(
        self,
        action_name: str,
        *,
        cost: float = 0.0,
        resource: str | None = None,
    ) -> None:
        """Register a tool as governance-aware.

        Only registered tools can be executed. Unregistered tools are
        blocked (default-deny per governance.md MUST NOT Rule 5).

        Args:
            action_name: The governance action name for this tool.
            cost: The cost of executing this tool (for financial checks).
            resource: Optional resource identifier (for knowledge checks).
        """
        self._registered_tools[action_name] = {
            "cost": cost,
            "resource": resource,
        }

    def execute_tool(self, action_name: str, **kwargs: Any) -> Any:
        """Execute a tool through governance. Default-deny for unregistered tools.

        The governance verification happens BEFORE the tool function is called.
        If governance blocks or holds, the tool function is NEVER called.

        Args:
            action_name: The governance action name to execute.
            **kwargs: Must include _tool_fn (callable) as the actual tool.

        Returns:
            The result of calling _tool_fn().

        Raises:
            GovernanceBlockedError: If the action is blocked (envelope violation
                or unregistered tool).
            GovernanceHeldError: If the action is held for human approval.
        """
        # Step 1: Default-deny for unregistered tools
        if action_name not in self._registered_tools:
            verdict = GovernanceVerdict(
                level="blocked",
                reason=f"Tool '{action_name}' is not governance-registered",
                role_address=self._role_address,
                action=action_name,
                audit_details={
                    "reason": "default_deny",
                    "action": action_name,
                    "role_address": self._role_address,
                },
            )
            raise GovernanceBlockedError(verdict)

        # Step 2: Build context for governance verification
        meta = self._registered_tools[action_name]
        verify_context: dict[str, Any] = {"cost": meta["cost"]}
        if meta["resource"] is not None:
            verify_context["resource"] = meta["resource"]

        # Step 3: Verify through the governance engine
        verdict = self._engine.verify_action(
            self._role_address,
            action_name,
            verify_context,
        )

        # Step 4: Handle verdict levels
        if verdict.level == "blocked":
            raise GovernanceBlockedError(verdict)
        elif verdict.level == "held":
            raise GovernanceHeldError(verdict)
        elif verdict.level == "flagged":
            logger.warning(
                "Governance FLAGGED for role=%s action=%s: %s",
                self._role_address,
                action_name,
                verdict.reason,
            )

        # Step 5: Execute the actual tool function
        tool_fn = kwargs.get("_tool_fn")
        if tool_fn is None:
            raise ValueError(
                f"execute_tool requires _tool_fn kwarg -- no callable provided "
                f"for action '{action_name}'"
            )
        return tool_fn()
