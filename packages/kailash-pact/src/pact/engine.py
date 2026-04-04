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
import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pact.costs import CostTracker
from pact.enforcement import EnforcementMode, validate_enforcement_mode
from pact.events import EventBus
from pact.work import WorkResult, WorkSubmission

logger = logging.getLogger(__name__)

__all__ = [
    "GovernanceHeldError",
    "HeldActionCallback",
    "GovernanceCallback",
    "PactEngine",
]


class GovernanceHeldError(Exception):
    """Raised when a governance verdict is HELD and no on_held callback handles it."""

    def __init__(self, verdict: Any, role: str, action: str, context: dict[str, Any] | None = None) -> None:
        self.verdict = verdict
        self.role = role
        self.action = action
        self.context = context or {}
        super().__init__(f"Action held for human review: {role} attempting {action}")


@runtime_checkable
class HeldActionCallback(Protocol):
    """Protocol for handling HELD verdicts. Return True to proceed, False to block."""

    async def __call__(self, verdict: Any, role: str, action: str, context: dict[str, Any]) -> bool: ...


@runtime_checkable
class GovernanceCallback(Protocol):
    """Protocol for per-node governance verification."""

    async def __call__(self, role_address: str, action: str, context: dict[str, Any]) -> Any: ...


class _DefaultGovernanceCallback:
    """Default per-node governance callback calling verify_action() per node."""

    def __init__(self, governance: Any, on_held: HeldActionCallback | None = None) -> None:
        self._governance = governance
        self._on_held = on_held

    async def __call__(self, role_address: str, action: str, context: dict[str, Any]) -> Any:
        from kailash.trust.pact.exceptions import PactError

        verdict = self._governance.verify_action(role_address=role_address, action=action, context=context)

        if verdict.is_held:
            if self._on_held is not None:
                proceed = await self._on_held(verdict, role_address, action, context)
                if proceed:
                    return verdict
            raise GovernanceHeldError(verdict=verdict, role=role_address, action=action, context=context)

        if verdict.is_blocked:
            raise PactError(
                f"Governance BLOCKED: {verdict.reason}",
                details={"level": verdict.level, "reason": verdict.reason, "role_address": role_address, "action": action},
            )

        return verdict


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
        on_held: HeldActionCallback | None = None,
        enforcement_mode: EnforcementMode = EnforcementMode.ENFORCE,
    ) -> None:
        # Validate enforcement mode (DISABLED requires env var guard)
        validate_enforcement_mode(enforcement_mode)
        self._enforcement_mode = enforcement_mode
        self._on_held = on_held

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

        # Detect degenerate envelopes at init (#241)
        self._detect_degenerate_envelopes()

        # Create cost tracker (Execution Plane bridge)
        self._costs = CostTracker(budget_usd=budget_usd, cost_model=cost_model)

        # Create event bus (bounded history per trust-plane-security.md rule 4)
        self._events = EventBus(maxlen=10000)

        # Supervisor is lazy -- only created when kaizen-agents is installed
        self._supervisor: Any | None = None

        logger.info(
            "PactEngine initialized: org=%s model=%s budget=$%s clearance=%s mode=%s",
            self._governance.org_name,
            model or "(none)",
            f"{budget_usd:.2f}" if budget_usd is not None else "unlimited",
            clearance,
            enforcement_mode.value,
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
        governance_verdicts: list[dict[str, Any]] = []

        # Emit submission event
        self._events.emit(
            "work.submitted",
            {
                "objective": objective,
                "role": role,
                "context": ctx,
                "enforcement_mode": self._enforcement_mode.value,
            },
        )

        # --- DISABLED mode: skip governance entirely ---
        if self._enforcement_mode == EnforcementMode.DISABLED:
            logger.warning(
                "PactEngine.submit: governance DISABLED for role=%s objective='%s' -- "
                "all governance checks skipped",
                role,
                objective[:80],
            )
            self._events.emit(
                "work.governance_disabled",
                {
                    "objective": objective,
                    "role": role,
                    "enforcement_mode": "disabled",
                },
            )
            return await self._execute_supervised(
                objective,
                role,
                ctx,
                events_emitted,
                governance_verdicts,
                shadow=False,
            )

        # Step 1: Verify action via Trust Plane (GovernanceEngine)
        try:
            verdict = self._governance.verify_action(
                role_address=role,
                action="submit",
                context=ctx,
            )
        except Exception:
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

        verdict_dict = verdict.to_dict()
        governance_verdicts.append(verdict_dict)

        # --- SHADOW mode: log verdict but never block ---
        if self._enforcement_mode == EnforcementMode.SHADOW:
            shadow_verdict = {**verdict_dict, "shadow": True}
            logger.info(
                "PactEngine.submit [SHADOW]: role=%s action=submit level=%s reason='%s'",
                role,
                verdict.level,
                verdict.reason,
            )
            self._events.emit(
                "work.governance_shadow",
                {
                    "objective": objective,
                    "role": role,
                    "verdict_level": verdict.level,
                    "reason": verdict.reason,
                    "shadow": True,
                },
            )
            governance_verdicts[-1] = shadow_verdict
            events_emitted.append(shadow_verdict)
            return await self._execute_supervised(
                objective,
                role,
                ctx,
                events_emitted,
                governance_verdicts,
                shadow=True,
            )

        # --- ENFORCE mode: verdicts are binding ---
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
                events=[verdict_dict],
                governance_verdicts=governance_verdicts,
            )

        events_emitted.append(verdict_dict)

        # Step 2: Execute via Execution Plane
        return await self._execute_supervised(
            objective,
            role,
            ctx,
            events_emitted,
            governance_verdicts,
            shadow=False,
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

    @property
    def enforcement_mode(self) -> EnforcementMode:
        """The current enforcement mode."""
        return self._enforcement_mode

    # -------------------------------------------------------------------
    # Layer 3: Direct access to governance subsystems
    # -------------------------------------------------------------------

    @property
    def governance(self) -> Any:
        """Read-only governance view (Layer 3).

        Returns a _ReadOnlyGovernanceView that proxies read-only methods.
        Use ._admin_governance for mutable access (internal only).
        """
        return _ReadOnlyGovernanceView(self._governance)

    @property
    def _admin_governance(self) -> Any:
        """Mutable governance engine for internal PactEngine use only."""
        return self._governance

    @property
    def governance_callback(self) -> GovernanceCallback:
        """The per-node governance callback."""
        return _DefaultGovernanceCallback(governance=self._governance, on_held=self._on_held)

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

    async def _execute_supervised(
        self,
        objective: str,
        role: str,
        ctx: dict[str, Any],
        events_emitted: list[dict[str, Any]],
        governance_verdicts: list[dict[str, Any]],
        *,
        shadow: bool,
    ) -> WorkResult:
        """Execute work through the supervisor (Execution Plane).

        Shared by all enforcement modes after governance checks are handled.

        Args:
            objective: Natural-language description of the work.
            role: D/T/R address of the requesting role.
            ctx: Context dict for execution.
            events_emitted: Accumulated event dicts.
            governance_verdicts: Accumulated governance verdict dicts.
            shadow: True if running in shadow mode.

        Returns:
            A WorkResult with execution outcome.
        """
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
                governance_shadow=shadow,
                governance_verdicts=governance_verdicts,
            )

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
                governance_shadow=shadow,
                governance_verdicts=governance_verdicts,
            )

        except Exception:
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
                governance_shadow=shadow,
                governance_verdicts=governance_verdicts,
            )

    def _adapt_envelope(self, role_address: str) -> dict[str, Any]:
        """Resolve effective envelope and map all 5 PACT constraint dimensions
        to supervisor parameters.

        Maps the canonical PACT constraint dimensions:
        - Financial -> budget_usd
        - Operational -> tools, max_depth (max_delegation_depth)
        - Data Access -> data_clearance
        - Temporal -> timeout_seconds
        - Communication -> allowed_channels, notification_policy

        NaN guard: every numeric field is validated with math.isfinite().
        Missing envelope: maximally restrictive defaults are returned.

        Args:
            role_address: The D/T/R address to resolve the envelope for.

        Returns:
            A dict of supervisor kwargs mapped from the envelope.
        """
        envelope = self._governance.compute_envelope(role_address)
        if envelope is None:
            return self._maximally_restrictive_defaults()

        result: dict[str, Any] = {}

        # --- Financial ---
        if envelope.financial is not None:
            max_spend = envelope.financial.max_spend_usd
            if max_spend is not None and math.isfinite(max_spend):
                remaining = self._costs.remaining
                result["budget_usd"] = min(
                    max_spend, remaining if remaining is not None else max_spend
                )
            else:
                if max_spend is not None:
                    logger.error(
                        "_adapt_envelope: non-finite financial.max_spend_usd=%r for "
                        "role=%s -- using restrictive default",
                        max_spend,
                        role_address,
                    )
                remaining = self._costs.remaining
                result["budget_usd"] = remaining if remaining is not None else 0.0
        else:
            remaining = self._costs.remaining
            result["budget_usd"] = remaining if remaining is not None else 0.0

        # --- Operational ---
        if envelope.operational is not None:
            allowed = envelope.operational.allowed_actions
            if allowed is not None:
                result["tools"] = list(allowed)
            max_depth = envelope.max_delegation_depth
            if max_depth is not None:
                if math.isfinite(float(max_depth)):
                    result["max_depth"] = int(max_depth)
                else:
                    logger.error(
                        "_adapt_envelope: non-finite max_delegation_depth=%r for "
                        "role=%s -- using restrictive default",
                        max_depth,
                        role_address,
                    )
                    result["max_depth"] = 0
        else:
            result["tools"] = []
            result["max_depth"] = 0

        # --- Data Access ---
        # confidentiality_clearance lives at the envelope level, not data_access
        clearance = envelope.confidentiality_clearance
        if clearance is not None:
            result["data_clearance"] = (
                clearance.value if hasattr(clearance, "value") else str(clearance)
            )
        else:
            result["data_clearance"] = "none"

        # --- Temporal ---
        # ConstraintEnvelopeConfig.temporal has active_hours_start/end but
        # no max_duration_seconds. We map active hours window to a timeout
        # estimate, or use the restrictive default.
        result["timeout_seconds"] = 60  # Default restrictive timeout

        # --- Communication ---
        if envelope.communication is not None:
            channels = envelope.communication.allowed_channels
            if channels is not None:
                result["allowed_channels"] = list(channels)
            # Map external_requires_approval as notification policy
            if envelope.communication.external_requires_approval:
                result["notification_policy"] = "approval_required"

        return result

    @staticmethod
    def _maximally_restrictive_defaults() -> dict[str, Any]:
        """Return maximally restrictive supervisor defaults when no envelope exists.

        No spending, no actions, no data access, 1-minute timeout, no delegation.
        This is the fail-closed default per pact-governance.md rule 4.

        Returns:
            A dict of maximally restrictive supervisor kwargs.
        """
        return {
            "budget_usd": 0.0,
            "tools": [],
            "data_clearance": "none",
            "timeout_seconds": 60,
            "max_depth": 0,
        }

    def _detect_degenerate_envelopes(self) -> None:
        """Scan org Role nodes for degenerate envelopes and log warnings."""
        from kailash.trust.pact.addressing import NodeType
        from kailash.trust.pact.envelopes import check_degenerate_envelope

        compiled_org = self._governance.get_org()
        degenerate_count = 0
        for address, node in compiled_org.nodes.items():
            if node.node_type != NodeType.ROLE:
                continue
            try:
                envelope = self._governance.compute_envelope(address)
            except Exception:
                continue
            if envelope is None:
                continue
            degenerate_warnings = check_degenerate_envelope(envelope)
            if degenerate_warnings:
                if degenerate_count < 50:
                    logger.warning("Degenerate envelope at '%s': %s", address, "; ".join(degenerate_warnings))
                degenerate_count += 1
        if degenerate_count > 50:
            logger.warning("... and %d more degenerate envelopes (total: %d)", degenerate_count - 50, degenerate_count)
        elif degenerate_count > 0:
            logger.warning("Found %d degenerate envelope(s) in org '%s'", degenerate_count, compiled_org.org_id)

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


class _ReadOnlyGovernanceView:
    """Read-only wrapper around GovernanceEngine per pact-governance.md Rule 1."""

    __slots__ = ("_engine",)

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    @property
    def org_name(self) -> str:
        return self._engine.org_name

    @property
    def compiled_org(self) -> Any:
        return self._engine.compiled_org

    def verify_action(self, *args: Any, **kwargs: Any) -> Any:
        return self._engine.verify_action(*args, **kwargs)

    def compute_envelope(self, *args: Any, **kwargs: Any) -> Any:
        return self._engine.compute_envelope(*args, **kwargs)

    def __repr__(self) -> str:
        return f"<_ReadOnlyGovernanceView org='{self._engine.org_name}'>"

    def __getattr__(self, name: str) -> Any:
        _BLOCKED = {
            "update_envelope", "modify_envelope", "set_role_envelope",
            "grant_clearance", "revoke_clearance", "register_vacancy",
            "register_tool", "compile_org", "set_compliance_role",
            "create_bridge", "approve_bridge", "consent_bridge",
            "register_compliance_role", "designate_interim", "revoke_interim",
            "register_ksp", "revoke_ksp",
        }
        if name in _BLOCKED:
            raise AttributeError(
                f"'{type(self).__name__}' does not expose '{name}'. "
                "Use PactEngine._admin_governance for mutable operations."
            )
        return getattr(self._engine, name)
