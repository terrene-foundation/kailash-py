# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PactEngine -- Dual Plane bridge for governed agent execution.

PactEngine is the single facade that bridges the Trust Plane (GovernanceEngine)
with the Execution Plane (GovernedSupervisor). It provides a progressive
disclosure API:

    Layer 1: engine = PactEngine(org="org.yaml", model="claude-sonnet-4-6")
             result = await engine.submit("Analyze Q3 data", role="D1-R1")
    Layer 2: engine = PactEngine(org="org.yaml", model="...", budget_usd=50.0, clearance="confidential")
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
from pathlib import Path
from typing import Any

from pact.costs import CostTracker
from pact.events import EventBus
from pact.work import WorkResult, WorkSubmission

logger = logging.getLogger(__name__)

__all__ = ["PactEngine"]


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

        # Create cost tracker (Execution Plane bridge)
        self._costs = CostTracker(budget_usd=budget_usd, cost_model=cost_model)

        # Create event bus (bounded history per trust-plane-security.md rule 4)
        self._events = EventBus(maxlen=10000)

        # Supervisor is lazy -- only created when kaizen-agents is installed
        self._supervisor: Any | None = None

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
                    "error": str(exc),
                },
            )
            return WorkResult(
                success=False,
                error=f"Governance error: {exc}",
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
                    "error": str(exc),
                },
            )
            return WorkResult(
                success=False,
                error=f"Execution error: {exc}",
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
    def governance(self) -> Any:
        """The Trust Plane GovernanceEngine instance (Layer 3 administrative API).

        WARNING: This returns the mutable GovernanceEngine. Do NOT pass this
        reference to agent code — agents must receive GovernanceContext (frozen)
        only, per pact-governance.md Rule 1. This property is for administrative
        use: org compilation, envelope inspection, clearance queries.
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
        """Lazily create a GovernedSupervisor if kaizen-agents is installed.

        Returns:
            A GovernedSupervisor instance, or None if kaizen-agents
            is not importable.
        """
        if self._supervisor is not None:
            return self._supervisor

        try:
            from kaizen_agents.supervisor import GovernedSupervisor
        except ImportError:
            logger.info(
                "kaizen-agents not installed -- GovernedSupervisor unavailable. "
                "Install with: pip install kailash-kaizen"
            )
            return None

        supervisor = GovernedSupervisor(
            model=self._model or "claude-sonnet-4-6",
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
        self._supervisor = supervisor
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
