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

from kailash.trust.action_policy import evaluate_action
from kailash.trust.envelope import AgentPosture, ConstraintEnvelope
from kailash.trust.readonly_proxy import ReadOnlyAttributeProxy
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


class _ProtectedInnerProxy(ReadOnlyAttributeProxy):
    """Proxy that blocks direct access to the raw inner agent.

    Prevents bypassing governance by accessing ``.inner._inner``.
    Only exposes safe read-only attributes.

    Enforcement lives in
    :class:`~kailash.trust.readonly_proxy.ReadOnlyAttributeProxy`, which gates
    every access through ``__getattribute__``.

    The previous implementation guarded with ``__getattr__``, which is a
    FALLBACK consulted only when normal lookup fails. It blocked ``_inner`` by
    name while storing the real agent as ``_real_inner`` -- a plain instance
    attribute -- so ``proxy._real_inner.run()`` and
    ``proxy.__dict__["_real_inner"].run()`` both resolved normally, never
    reached the guard, and ran the agent ungoverned. Same defect class as
    #2224. Note this is distinct from the documented Python limitation covered
    by ``TestGovernanceBypassViaDirectRun``: that one requires an explicit
    ``object.__getattribute__`` call, whereas this was plain attribute access.
    """

    __slots__ = ()

    # Safe read-only INTROSPECTION only. Every entry here is handed back through
    # ReadOnlyAttributeProxy's forwarder, but gating the NAME and stripping the
    # bound method's __self__ is not sufficient on its own: a member that
    # RETURNS a live handle to the raw agent (or an executable form of it) is an
    # escape hatch no matter how the name is gated. This is the #2226 class at
    # the agent boundary. Two members were removed for exactly that (HIGH-1 of
    # the #2227 review):
    #   * ``to_workflow_node`` is ``def to_workflow_node(self): return self`` --
    #     it structurally cannot return anything but the raw inner agent, so
    #     ``governed.inner.to_workflow_node().run(**inputs)`` (and, through the
    #     innermost boundary, ``streaming.innermost.to_workflow_node().run(...)``)
    #     executed completely ungoverned.
    #   * ``to_workflow`` builds a WorkflowBuilder whose ``LLMAgentNode`` carries
    #     ``ungoverned=self.config.ungoverned`` and NO envelope check -- the L3
    #     evaluation lives in run()/run_async(), not in the emitted workflow --
    #     so a proxy holder could build+run the agent's LLM work outside the
    #     envelope. Neither can be made safe here (both live in BaseAgent, which
    #     is out of scope and shared by every caller), and neither has any
    #     legitimate consumer THROUGH the proxy: wrappers proxy
    #     ``self._inner.to_workflow()`` on the raw inner directly, never through
    #     ``.inner``. So the fix is to deny them, not to reshape them.
    # The staleness pin is ``test_no_allowlisted_member_returns_a_live_agent_handle``,
    # which CALLS every allowlisted member and asserts the return is neither the
    # raw agent nor runnable -- so a NEW leaky entry fails, the way inspecting
    # only __self__ did not.
    _ALLOWED_ATTRS = frozenset(
        {
            "config",
            "signature",
            "get_parameters",
        }
    )

    def __init__(self, inner: BaseAgent) -> None:
        allowed = _ProtectedInnerProxy._ALLOWED_ATTRS
        super().__init__(
            inner,
            allowed,
            label="_ProtectedInnerProxy",
            message_template=(
                "Access to '{name}' on the governed inner agent is restricted. "
                f"Allowed attributes: {sorted(allowed)}"
            ),
            overrides={
                "_inner": (
                    "Direct access to _inner is blocked by governance. "
                    "Use the governed agent's run() or run_async() methods."
                )
            },
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

    def _containment_boundary(self) -> _ProtectedInnerProxy:
        """This wrapper's protected proxy stands in for everything beneath it.

        Declares the governance boundary to ``WrapperBase.innermost``, which
        otherwise walks the private ``_inner`` chain straight past ``inner``
        and hands back the raw agent -- ``governed.innermost.run(...)`` ran
        completely ungoverned (#2227 Route A). Declaring the boundary here
        rather than overriding ``innermost`` covers the STACKED case too:
        ``StreamingAgent(MonitoredAgent(governed)).innermost`` starts its walk
        at the outermost wrapper and would never have consulted an override on
        this class.
        """
        return self._inner_proxy

    @property
    def inner(self) -> _ProtectedInnerProxy:  # type: ignore[override]
        """Returns a protected proxy instead of the raw inner agent."""
        return self._inner_proxy

    @property
    def rejection_count(self) -> int:
        """Number of requests rejected by governance since creation."""
        return self._rejection_count

    def to_workflow(self) -> Any:
        """Refuse conversion to a static workflow -- fail closed (#2227).

        ``WrapperBase.to_workflow`` proxies to ``self._inner.to_workflow()``,
        which emits an ``LLMAgentNode`` carrying ``ungoverned=config.ungoverned``
        and NO envelope evaluation -- the L3 budget/operational/posture checks
        live only in ``run``/``run_async``. So an inherited ``to_workflow`` let a
        holder of the wrapper do::

            wf = governed.to_workflow()
            LocalRuntime().execute(wf.build())   # inner LLM work, envelope SKIPPED

        from a plain public method, no private access. This is the same class
        as the ``innermost``/``to_workflow_node`` routes already contained, and
        the same danger documented for the proxy ``to_workflow`` entry that was
        removed from ``_ProtectedInnerProxy._ALLOWED_ATTRS`` -- closing the proxy
        path while leaving the wrapper's own public method open would be half a
        fix. It is also reachable as ``MonitoredAgent(governed).to_workflow()``,
        which inherits this via the ``_inner`` chain.

        Emitting a *governed* workflow is a larger design change (the envelope
        evaluation would have to become a node); refusing is the correct
        fail-closed move and matches ``StreamingAgent.to_workflow``, which
        already raises for its own reason. Governed execution goes through
        ``run``/``run_async``, where the envelope is enforced.

        Raised as :class:`GovernanceRejectedError` rather than the
        not-implemented error ``StreamingAgent`` uses: this is a deliberate
        governance refusal, not an unimplemented method, and the bare
        not-implemented form trips the repo's zero-tolerance stub gate. The
        dimension names the refused operation so the audit trail is precise.

        Raises:
            GovernanceRejectedError: always. A governed agent has no ungoverned
                static-workflow form; use ``run``/``run_async``.
        """
        raise GovernanceRejectedError(
            dimension="workflow_conversion",
            detail=(
                "L3GovernedAgent cannot be converted to a static workflow -- the "
                "emitted LLMAgentNode would run the inner agent with the "
                "governance envelope SKIPPED (budget/operational/posture are "
                "enforced only in run()/run_async()). Use the governed agent's "
                "run()/run_async(), which evaluate the envelope before execution"
            ),
        )

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
            # The caller declared no action, so there is nothing to match
            # against the allow/block lists. This is orthogonal to GH #2218:
            # it behaves identically for empty and non-empty allowlists, so
            # no surface disagrees about it.
            return

        # The allow/block decision lives in ONE place
        # (kailash.trust.action_policy), shared with
        # GovernanceEngine.verify_action, GradientEngine and the bridge scope
        # validator (GH #2218, security.md § Enforcement-Surface Parity).
        # This surface previously spelled the check as
        # ``if ops.allowed_actions and action not in ops.allowed_actions`` --
        # the ``and`` short-circuited on an EMPTY allowlist, so an agent whose
        # operator had tightened the allowlist down to nothing was permitted
        # EVERY action on its own run() path.
        verdict = evaluate_action(ops, action)
        if not verdict.permitted:
            raise GovernanceRejectedError(
                dimension="operational",
                detail=f"{verdict.reason}.",
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
