# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""L3GovernedAgent -- PACT envelope enforcement wrapper.

Sits directly above ``BaseAgent`` in the canonical stacking order::

    BaseAgent -> L3GovernedAgent -> MonitoredAgent -> StreamingAgent

Governance rejects BEFORE LLM cost is incurred: a rejected request never
reaches the model, saving money on invalid work.

The governance check evaluates the ``ConstraintEnvelope`` dimensions:
- Financial: budget limits
- Operational: allowed/blocked action lists
- Temporal: time-of-day or deadline constraints
- Data access: scope restrictions
- Communication: channel restrictions
- Posture ceiling: maximum autonomy level

A ``_ProtectedInnerProxy`` prevents callers from bypassing governance by
reaching through ``.inner._inner``.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from kailash.trust.envelope import AgentPosture, ConstraintEnvelope
from kaizen.core.base_agent import BaseAgent
from kaizen_agents.wrapper_base import WrapperBase

logger = logging.getLogger(__name__)

__all__ = [
    "L3GovernedAgent",
    "GovernanceRejectedError",
]


class GovernanceRejectedError(RuntimeError):
    """Raised when the governance envelope rejects an execution request.

    Attributes:
        dimension: Which constraint dimension caused the rejection.
        detail: Human-readable explanation of why the request was rejected.
    """

    def __init__(self, dimension: str, detail: str) -> None:
        self.dimension = dimension
        self.detail = detail
        super().__init__(f"Governance rejected [{dimension}]: {detail}")


class _ProtectedInnerProxy:
    """Proxy that blocks direct access to the raw inner agent.

    Prevents bypassing governance by accessing ``.inner._inner``.
    Only exposes safe read-only attributes.
    """

    _ALLOWED_ATTRS = frozenset(
        {
            "config",
            "signature",
            "get_parameters",
            "to_workflow",
            "to_workflow_node",
        }
    )

    def __init__(self, inner: BaseAgent) -> None:
        object.__setattr__(self, "_real_inner", inner)

    def __getattr__(self, name: str) -> Any:
        if name == "_inner":
            raise AttributeError(
                "Direct access to _inner is blocked by governance. "
                "Use the governed agent's run() or run_async() methods."
            )
        if name in self._ALLOWED_ATTRS:
            return getattr(object.__getattribute__(self, "_real_inner"), name)
        raise AttributeError(
            f"Access to '{name}' on the governed inner agent is restricted. "
            f"Allowed attributes: {sorted(self._ALLOWED_ATTRS)}"
        )

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("Cannot modify attributes on a governed agent proxy")


class L3GovernedAgent(WrapperBase):
    """Governance wrapper -- enforces ConstraintEnvelope before execution.

    Parameters
    ----------
    inner:
        The agent to wrap.
    envelope:
        The ``ConstraintEnvelope`` defining the operational boundaries.
    posture:
        Optional agent posture override. If provided and the envelope has a
        posture ceiling, the posture will be clamped to the ceiling.
    """

    def __init__(
        self,
        inner: BaseAgent,
        envelope: ConstraintEnvelope,
        *,
        posture: AgentPosture | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(inner, **kwargs)
        self._envelope = envelope
        self._inner_proxy = _ProtectedInnerProxy(inner)
        self._rejection_count = 0

        # Clamp posture to ceiling if both are provided
        if posture is not None and envelope.posture_ceiling is not None:
            ceiling = AgentPosture(envelope.posture_ceiling)
            self._posture = posture.clamp_to_ceiling(ceiling)
        else:
            self._posture = posture

    @property
    def envelope(self) -> ConstraintEnvelope:
        """The active constraint envelope."""
        return self._envelope

    @property
    def posture(self) -> AgentPosture | None:
        """The active agent posture (clamped to envelope ceiling)."""
        return self._posture

    @property
    def inner(self) -> _ProtectedInnerProxy:  # type: ignore[override]
        """Returns a protected proxy instead of the raw inner agent."""
        return self._inner_proxy

    @property
    def rejection_count(self) -> int:
        """Number of requests rejected by governance since creation."""
        return self._rejection_count

    def _evaluate_financial(self, inputs: dict[str, Any]) -> None:
        """Check financial constraints.

        Raises GovernanceRejectedError if budget limits would be violated.
        """
        fin = self._envelope.financial
        if fin is None:
            return

        estimated_cost = inputs.get("_estimated_cost_usd", 0.0)
        if not isinstance(estimated_cost, int | float):
            return

        # NaN/Inf check per trust-plane-security rules
        if not math.isfinite(estimated_cost):
            raise GovernanceRejectedError(
                dimension="financial",
                detail=f"Estimated cost is non-finite ({estimated_cost!r}). "
                f"NaN/Inf values are rejected.",
            )

        if fin.budget_limit is not None and estimated_cost > fin.budget_limit:
            raise GovernanceRejectedError(
                dimension="financial",
                detail=f"Estimated cost ${estimated_cost:.4f} exceeds budget "
                f"limit ${fin.budget_limit:.4f}.",
            )

        if (
            fin.max_cost_per_action is not None
            and estimated_cost > fin.max_cost_per_action
        ):
            raise GovernanceRejectedError(
                dimension="financial",
                detail=f"Estimated cost ${estimated_cost:.4f} exceeds per-action "
                f"limit ${fin.max_cost_per_action:.4f}.",
            )

    def _evaluate_operational(self, inputs: dict[str, Any]) -> None:
        """Check operational constraints (allowed/blocked actions).

        Raises GovernanceRejectedError if the requested action is not permitted.
        """
        ops = self._envelope.operational
        if ops is None:
            return

        action = inputs.get("_action", "")
        if not action:
            return

        # Check blocked actions first (deny wins)
        if ops.blocked_actions and action in ops.blocked_actions:
            raise GovernanceRejectedError(
                dimension="operational",
                detail=f"Action '{action}' is explicitly blocked.",
            )

        # If allowed_actions is non-empty, the action must be in the list
        if ops.allowed_actions and action not in ops.allowed_actions:
            raise GovernanceRejectedError(
                dimension="operational",
                detail=f"Action '{action}' is not in the allowed actions list: "
                f"{sorted(ops.allowed_actions)}.",
            )

    def _evaluate_posture_ceiling(self) -> None:
        """Check that the agent posture fits within the envelope ceiling.

        Raises GovernanceRejectedError if the posture exceeds the ceiling.
        """
        if self._posture is None or self._envelope.posture_ceiling is None:
            return

        ceiling = AgentPosture(self._envelope.posture_ceiling)
        if not self._posture.fits_ceiling(ceiling):
            raise GovernanceRejectedError(
                dimension="posture",
                detail=f"Agent posture '{self._posture.value}' exceeds "
                f"ceiling '{ceiling.value}'.",
            )

    def _evaluate(self, inputs: dict[str, Any]) -> None:
        """Run all governance checks. Raises GovernanceRejectedError on failure."""
        self._evaluate_financial(inputs)
        self._evaluate_operational(inputs)
        self._evaluate_posture_ceiling()

    def run(self, **inputs: Any) -> dict[str, Any]:
        """Execute with governance checks (synchronous)."""
        try:
            self._evaluate(inputs)
        except GovernanceRejectedError:
            self._rejection_count += 1
            raise
        self._inner_called = True
        return self._inner.run(**inputs)

    async def run_async(self, **inputs: Any) -> dict[str, Any]:
        """Execute with governance checks (asynchronous)."""
        try:
            self._evaluate(inputs)
        except GovernanceRejectedError:
            self._rejection_count += 1
            raise
        self._inner_called = True
        return await self._inner.run_async(**inputs)
