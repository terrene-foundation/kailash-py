# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PactEngine -- Dual Plane bridge for governed agent execution.

PactEngine is the single facade that bridges the Trust Plane (GovernanceEngine)
with the Execution Plane (GovernedSupervisor). It provides a progressive
disclosure API:

    Layer 1: engine = PactEngine(org="org.yaml", model=os.environ.get("DEFAULT_LLM_MODEL"))
             result = await engine.submit("Analyze Q3 data", role="D1-R1")
    Layer 2: engine = PactEngine(org="org.yaml", model=..., budget_usd=50.0, clearance="confidential")
    Layer 3: engine.governance / engine.costs / engine.events

Design principles:
1. Fail-closed: any governance error -> BLOCKED WorkResult
2. NaN-safe: budget_usd validated with math.isfinite()
3. Lazy import: kaizen-agents is optional -- detected at submit() time
4. Bounded: event history uses maxlen=10000
5. Async-primary: submit() is async, submit_sync() is convenience wrapper
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
from pathlib import Path
from typing import Any

from pact.costs import CostTracker
from pact.events import EventBus
from pact.work import WorkResult, WorkSubmission

logger = logging.getLogger(__name__)

__all__ = ["PactEngine"]


class _ReadOnlyGovernanceView:
    """Read-only wrapper around GovernanceEngine.

    Proxies read-only methods and properties (org_name, compiled_org,
    verify_action, compute_envelope, check_access, get_org, get_node,
    list_roles, audit_chain) while raising AttributeError for mutating
    methods (set_role_envelope, grant_clearance, etc.).

    This ensures that external consumers of ``PactEngine.governance``
    cannot mutate the governance engine directly.
    """

    __slots__ = ("_engine",)

    # Methods that are safe to proxy (read-only / query)
    _PROXIED_METHODS: frozenset[str] = frozenset(
        {
            "org_name",
            "compiled_org",
            "verify_action",
            "compute_envelope",
            "check_access",
            "get_org",
            "get_node",
            "list_roles",
            "audit_chain",
            "get_clearance",
            "get_role_envelope",
            "get_effective_envelope",
            "describe_address",
            "explain_access",
            "explain_envelope",
        }
    )

    # Methods that MUST be blocked (mutating)
    _BLOCKED_METHODS: frozenset[str] = frozenset(
        {
            "set_role_envelope",
            "grant_clearance",
            "create_bridge",
            "approve_bridge",
            "consent_bridge",
            "register_compliance_role",
            "designate_interim",
            "revoke_interim",
            "register_ksp",
            "revoke_ksp",
        }
    )

    def __init__(self, engine: Any) -> None:
        object.__setattr__(self, "_engine", engine)

    def __getattr__(self, name: str) -> Any:
        if name in _ReadOnlyGovernanceView._BLOCKED_METHODS:
            raise AttributeError(
                f"'{name}' is a mutating method and is not available through "
                f"the read-only governance view. Use engine._admin_governance "
                f"for administrative operations."
            )
        return getattr(object.__getattribute__(self, "_engine"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("Cannot set attributes on the read-only governance view.")

    def __repr__(self) -> str:
        engine = object.__getattribute__(self, "_engine")
        return f"_ReadOnlyGovernanceView(org={engine.org_name!r})"


class PactEngine:
    """Dual Plane bridge -- governed agent execution facade.

    Progressive disclosure API:
    - Layer 1: PactEngine(org="org.yaml") + submit()
    - Layer 2: model, budget_usd, clearance, cost_model
    - Layer 3: governance, costs, events properties

    Args:
        org: Organization definition. Accepts:
            - str: Path to a YAML file
            - Path: Path object to a YAML file
            - dict: Raw org definition dict (passed to load_org_yaml-style parsing)
        model: LLM model identifier string (informational).
        budget_usd: Maximum budget in USD. None means unlimited.
        clearance: Clearance level string. Default "restricted".
        store_backend: Store backend for GovernanceEngine. Default "memory".
        cost_model: Optional CostModel for LLM token cost computation.

    Raises:
        ValueError: If budget_usd is NaN, Inf, or negative.
        ConfigurationError: If the org YAML is invalid.
        FileNotFoundError: If the org path does not exist.
    """

    def __init__(
        self,
        org: str | Path | dict[str, Any],
        *,
        model: str | None = None,
        budget_usd: float | None = None,
        clearance: str = "restricted",
        store_backend: str = "memory",
        cost_model: Any | None = None,
    ) -> None:
        # Validate budget_usd (NaN/Inf/negative per pact-governance.md rule 6)
        if budget_usd is not None:
            if not math.isfinite(budget_usd):
                raise ValueError(f"budget_usd must be finite, got {budget_usd!r}")
            if budget_usd < 0:
                raise ValueError(
                    f"budget_usd must be finite and non-negative, got {budget_usd}"
                )

        self._model = model
        self._clearance = clearance
        self._store_backend = store_backend

        # Load org and create GovernanceEngine (Trust Plane)
        self._governance = self._create_governance_engine(org, store_backend)

        # Degenerate envelope detection (#241) -- warn on envelopes so tight
        # that no meaningful action is possible. Cap at 50 warnings.
        self._detect_degenerate_envelopes()

        # Create cost tracker (Execution Plane bridge)
        self._costs = CostTracker(budget_usd=budget_usd, cost_model=cost_model)

        # Create event bus (bounded history per trust-plane-security.md rule 4)
        self._events = EventBus(maxlen=10000)

        logger.info(
            "PactEngine initialized: org=%s model=%s budget=$%s clearance=%s",
            self._governance.org_name,
            model or "(none)",
            f"{budget_usd:.2f}" if budget_usd is not None else "unlimited",
            clearance,
        )

    # -------------------------------------------------------------------
    # Layer 1: Simple API
    # -------------------------------------------------------------------

    async def submit(
        self,
        objective: str,
        role: str,
        context: dict[str, Any] | None = None,
    ) -> WorkResult:
        """Submit work for governed execution.

        Resolves the role's governance envelope, verifies the action is
        permitted, then executes via the supervisor (if kaizen-agents is
        installed).

        Fail-closed: any governance error returns a BLOCKED WorkResult
        instead of raising an exception.

        Args:
            objective: Natural-language description of the work.
            role: D/T/R address of the requesting role.
            context: Optional context dict for the execution.

        Returns:
            A WorkResult with the outcome. success=False if governance
            blocks the action or if kaizen-agents is not available.
        """
        ctx = context or {}
        events_emitted: list[dict[str, Any]] = []

        # Emit submission event
        self._events.emit(
            "work.submitted",
            {
                "objective": objective,
                "role": role,
                "context": ctx,
            },
        )

        # Step 1: Verify action via Trust Plane (GovernanceEngine)
        try:
            verdict = self._governance.verify_action(
                role_address=role,
                action="submit",
                context=ctx,
            )
        except Exception as exc:
            logger.exception(
                "PactEngine.submit: governance verify_action raised for role=%s -- fail-closed",
                role,
            )
            self._events.emit(
                "work.blocked",
                {
                    "objective": objective,
                    "role": role,
                    "error": "Governance verification failed",
                },
            )
            return WorkResult(
                success=False,
                error="Governance verification failed — see server logs for details",
                events=events_emitted,
            )

        # Check if governance blocks the action
        if not verdict.allowed:
            self._events.emit(
                "work.blocked",
                {
                    "objective": objective,
                    "role": role,
                    "verdict_level": verdict.level,
                    "reason": verdict.reason,
                },
            )
            return WorkResult(
                success=False,
                error=f"Governance {verdict.level}: {verdict.reason}",
                events=[verdict.to_dict()],
            )

        events_emitted.append(verdict.to_dict())

        # Step 2: Execute via Execution Plane (GovernedSupervisor)
        supervisor = self._get_or_create_supervisor()
        if supervisor is None:
            self._events.emit(
                "work.completed",
                {
                    "objective": objective,
                    "role": role,
                    "success": False,
                    "reason": "kaizen-agents not installed",
                },
            )
            return WorkResult(
                success=False,
                error=(
                    "Execution plane unavailable: kaizen-agents is not installed. "
                    "Install with: pip install kailash-kaizen"
                ),
                events=events_emitted,
            )

        # Execute through supervisor
        try:
            supervisor_result = await supervisor.run(
                objective=objective,
                context=ctx,
            )
            cost_usd = supervisor_result.budget_consumed
            if not math.isfinite(cost_usd) or cost_usd < 0:
                logger.error(
                    "budget_consumed is non-finite or negative (%r) — recording as 0.0",
                    cost_usd,
                )
                cost_usd = 0.0
            if cost_usd > 0:
                self._costs.record(cost_usd, f"submit: {objective[:80]}")

            self._events.emit(
                "work.completed",
                {
                    "objective": objective,
                    "role": role,
                    "success": supervisor_result.success,
                    "cost_usd": cost_usd,
                },
            )

            return WorkResult(
                success=supervisor_result.success,
                results=supervisor_result.results,
                cost_usd=cost_usd,
                events=[
                    {
                        "type": (
                            e.event_type.value
                            if hasattr(e.event_type, "value")
                            else str(e.event_type)
                        ),
                        "node_id": getattr(e, "node_id", None),
                    }
                    for e in supervisor_result.events
                ],
            )

        except Exception as exc:
            logger.exception(
                "PactEngine.submit: supervisor execution failed for role=%s -- fail-closed",
                role,
            )
            self._events.emit(
                "work.failed",
                {
                    "objective": objective,
                    "role": role,
                    "error": "Execution failed",
                },
            )
            return WorkResult(
                success=False,
                error="Execution failed — see server logs for details",
                events=events_emitted,
            )

    def submit_sync(
        self,
        objective: str,
        role: str,
        context: dict[str, Any] | None = None,
    ) -> WorkResult:
        """Synchronous convenience wrapper around submit().

        Creates or reuses an event loop to run the async submit().

        Args:
            objective: Natural-language description of the work.
            role: D/T/R address of the requesting role.
            context: Optional context dict for the execution.

        Returns:
            A WorkResult with the outcome.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            # We are inside an async context -- create a new thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run,
                    self.submit(objective, role, context),
                )
                return future.result()
        else:
            return asyncio.run(self.submit(objective, role, context))

    # -------------------------------------------------------------------
    # Layer 2: Configuration accessors
    # -------------------------------------------------------------------

    @property
    def model(self) -> str | None:
        """The LLM model identifier string, or None if not specified."""
        return self._model

    @property
    def clearance(self) -> str:
        """The clearance level string."""
        return self._clearance

    # -------------------------------------------------------------------
    # Layer 3: Direct access to governance subsystems
    # -------------------------------------------------------------------

    @property
    def governance(self) -> _ReadOnlyGovernanceView:
        """Read-only view of the Trust Plane GovernanceEngine (Layer 3 API).

        Returns a ``_ReadOnlyGovernanceView`` that proxies read-only methods
        (org_name, verify_action, compute_envelope, check_access, etc.) and
        raises ``AttributeError`` for mutating methods (set_role_envelope,
        grant_clearance, etc.).

        For internal administrative mutations use ``_admin_governance``.
        """
        return _ReadOnlyGovernanceView(self._governance)

    @property
    def _admin_governance(self) -> Any:
        """The mutable GovernanceEngine for internal PactEngine use only.

        This returns the raw GovernanceEngine without the read-only wrapper.
        It is private (underscore-prefixed) and MUST NOT be exposed to agent
        code. Use ``governance`` for external consumers.
        """
        return self._governance

    @property
    def costs(self) -> CostTracker:
        """The cost tracker for budget management."""
        return self._costs

    @property
    def events(self) -> EventBus:
        """The event bus for governance and execution events."""
        return self._events

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _detect_degenerate_envelopes(self) -> None:
        """Scan org Role nodes for degenerate envelopes and log warnings.

        Called once during __init__ after compile_org(). Iterates all Role
        nodes in the compiled org (only Roles have valid envelope addresses),
        computes each effective envelope, and runs
        ``check_degenerate_envelope()`` on it. Caps warnings at 50 to
        prevent log flooding for large organizations.
        """
        from kailash.trust.pact.addressing import NodeType
        from kailash.trust.pact.envelopes import check_degenerate_envelope

        compiled_org = self._governance.get_org()
        degenerate_count = 0

        for address, node in compiled_org.nodes.items():
            # Only Role nodes have valid D/T/R addresses for envelope computation
            if node.node_type != NodeType.ROLE:
                continue
            try:
                envelope = self._governance.compute_envelope(address)
            except Exception:
                # Fail-safe: if envelope computation fails, skip this node
                continue
            if envelope is None:
                continue
            degenerate_warnings = check_degenerate_envelope(envelope)
            if degenerate_warnings:
                if degenerate_count < 50:
                    logger.warning(
                        "Degenerate envelope at '%s': %s",
                        address,
                        "; ".join(degenerate_warnings),
                    )
                degenerate_count += 1

        if degenerate_count > 50:
            logger.warning(
                "... and %d more degenerate envelopes (total: %d)",
                degenerate_count - 50,
                degenerate_count,
            )
        elif degenerate_count > 0:
            logger.warning(
                "Found %d degenerate envelope(s) in org '%s'",
                degenerate_count,
                compiled_org.org_id,
            )

    @staticmethod
    def _create_governance_engine(
        org: str | Path | dict[str, Any],
        store_backend: str,
    ) -> Any:
        """Create a GovernanceEngine from an org source.

        Handles three input types:
        - str: Treated as a file path to YAML
        - Path: Treated as a file path to YAML
        - dict: Treated as a raw org definition dict

        Args:
            org: The org source (str path, Path, or dict).
            store_backend: The store backend type ("memory" or "sqlite").

        Returns:
            A GovernanceEngine instance.

        Raises:
            ConfigurationError: If the org definition is invalid.
            FileNotFoundError: If the YAML file does not exist.
        """
        from kailash.trust.pact.engine import GovernanceEngine
        from kailash.trust.pact.yaml_loader import load_org_yaml
        from kailash.trust.pact.config import OrgDefinition

        if isinstance(org, (str, Path)):
            # Load from YAML file
            loaded = load_org_yaml(org)
            org_def = loaded.org_definition
        elif isinstance(org, dict):
            # Build OrgDefinition from dict -- use the YAML loader's parsing
            # by writing to a temporary in-memory representation
            org_def = _org_def_from_dict(org)
        else:
            raise TypeError(
                f"org must be a str path, Path, or dict, got {type(org).__name__}"
            )

        return GovernanceEngine(org_def, store_backend=store_backend)

    def _get_or_create_supervisor(self) -> Any | None:
        """Create a fresh GovernedSupervisor if kaizen-agents is installed.

        A new supervisor is created on every call so that ``budget_usd``
        reflects ``self._costs.remaining`` at the time of each submit().

        Returns:
            A GovernedSupervisor instance, or None if kaizen-agents
            is not importable.
        """
        try:
            from kaizen_agents.supervisor import GovernedSupervisor
        except ImportError:
            logger.info(
                "kaizen-agents not installed -- GovernedSupervisor unavailable. "
                "Install with: pip install kailash-kaizen"
            )
            return None

        supervisor = GovernedSupervisor(
            model=self._model or os.environ.get("DEFAULT_LLM_MODEL"),
            budget_usd=(
                self._costs.remaining if self._costs.remaining is not None else 1.0
            ),
            data_clearance=(
                self._clearance
                if self._clearance
                in (
                    "public",
                    "internal",
                    "restricted",
                    "confidential",
                    "secret",
                    "top_secret",
                )
                else "public"
            ),
            cost_model=self._costs.cost_model,
        )
        return supervisor


def _org_def_from_dict(data: dict[str, Any]) -> Any:
    """Build an OrgDefinition from a raw dict.

    Mirrors the structure expected by the YAML loader but without
    needing a physical file.

    Args:
        data: Dict with org_id, name, departments, teams, roles.

    Returns:
        An OrgDefinition instance.

    Raises:
        ValueError: If required fields are missing.
    """
    from kailash.trust.pact.config import DepartmentConfig, OrgDefinition, TeamConfig
    from kailash.trust.pact.compilation import RoleDefinition

    if "org_id" not in data:
        raise ValueError("org dict must contain 'org_id'")
    if "name" not in data:
        raise ValueError("org dict must contain 'name'")

    departments = []
    for d in data.get("departments", []):
        departments.append(
            DepartmentConfig(
                department_id=d["id"],
                name=d.get("name", d["id"]),
            )
        )

    teams = []
    for t in data.get("teams", []):
        teams.append(
            TeamConfig(
                id=t["id"],
                name=t.get("name", t["id"]),
                workspace=f"ws-{t['id']}",
            )
        )

    roles = []
    for r in data.get("roles", []):
        roles.append(
            RoleDefinition(
                role_id=r["id"],
                name=r.get("name", r["id"]),
                reports_to_role_id=r.get("reports_to"),
                is_primary_for_unit=r.get("heads"),
                agent_id=r.get("agent"),
            )
        )

    return OrgDefinition(
        org_id=data["org_id"],
        name=data["name"],
        departments=departments,
        teams=teams,
        roles=roles,
    )
