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
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator, Protocol, runtime_checkable

from pact.costs import CostTracker
from pact.enforcement import EnforcementMode, validate_enforcement_mode
from pact.events import EventBus
from pact.work import WorkResult

if TYPE_CHECKING:  # imports for type-only forward references
    from pact.governance.results import ChainVerificationResult, EnvelopeSnapshot

logger = logging.getLogger(__name__)

__all__ = [
    "GovernanceHeldError",
    "HeldActionCallback",
    "GovernanceCallback",
    "PactEngine",
]


class GovernanceHeldError(Exception):
    """Raised when a governance verdict is HELD and no on_held callback handles it."""

    def __init__(
        self,
        verdict: Any,
        role: str,
        action: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.verdict = verdict
        self.role = role
        self.action = action
        self.context = context or {}
        super().__init__(f"Action held for human review: {role} attempting {action}")


@runtime_checkable
class HeldActionCallback(Protocol):
    """Protocol for handling HELD verdicts. Return True to proceed, False to block."""

    async def __call__(
        self, verdict: Any, role: str, action: str, context: dict[str, Any]
    ) -> bool: ...


@runtime_checkable
class GovernanceCallback(Protocol):
    """Protocol for per-node governance verification."""

    async def __call__(
        self, role_address: str, action: str, context: dict[str, Any]
    ) -> Any: ...


class _DefaultGovernanceCallback:
    """Default per-node governance callback calling verify_action() per node."""

    def __init__(
        self, governance: Any, on_held: HeldActionCallback | None = None
    ) -> None:
        self._governance = governance
        self._on_held = on_held

    async def __call__(
        self, role_address: str, action: str, context: dict[str, Any]
    ) -> Any:
        from kailash.trust.pact.exceptions import PactError

        verdict = self._governance.verify_action(
            role_address=role_address, action=action, context=context
        )

        if verdict.is_held:
            if self._on_held is not None:
                proceed = await self._on_held(verdict, role_address, action, context)
                if proceed:
                    return verdict
            raise GovernanceHeldError(
                verdict=verdict, role=role_address, action=action, context=context
            )

        if verdict.is_blocked:
            raise PactError(
                f"Governance BLOCKED: {verdict.reason}",
                details={
                    "level": verdict.level,
                    "reason": verdict.reason,
                    "role_address": role_address,
                    "action": action,
                },
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

        # Submit lock: makes check-remaining → execute → record-cost atomic (#292)
        self._submit_lock = asyncio.Lock()

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
        # Acquire submit lock to make check-remaining → execute → record-cost
        # atomic. Prevents concurrent submits from both seeing the same
        # remaining budget and overspending. (#292)
        async with self._submit_lock:
            return await self._submit_locked(objective, role, context)

    async def _submit_locked(
        self,
        objective: str,
        role: str,
        context: dict[str, Any] | None = None,
    ) -> WorkResult:
        """Inner submit logic, called under _submit_lock."""
        # Input validation (Tier 1): reject empty/invalid objective and role
        if not objective or not isinstance(objective, str) or not objective.strip():
            return WorkResult(
                success=False,
                error="objective must be a non-empty string",
            )
        if not role or not isinstance(role, str) or not role.strip():
            return WorkResult(
                success=False,
                error="role must be a non-empty D/T/R address",
            )

        ctx = context or {}
        events_emitted: list[dict[str, Any]] = []
        governance_verdicts: list[dict[str, Any]] = []
        audit_trail: list[dict[str, Any]] = []
        budget = self._costs._budget  # Budget allocated to this engine

        def _audit(event: str, details: dict[str, Any] | None = None) -> None:
            audit_trail.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event": event,
                    "role_address": role,
                    "details": details or {},
                }
            )

        _audit("submission_received", {"objective": objective[:200]})

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
            _audit("governance_skipped", {"enforcement_mode": "disabled"})
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
                budget_allocated=budget,
                audit_trail=audit_trail,
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
            _audit("governance_error", {"error": "verification raised"})
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
                budget_allocated=budget,
                audit_trail=audit_trail,
            )

        verdict_dict = verdict.to_dict()
        governance_verdicts.append(verdict_dict)
        _audit(
            "governance_verified", {"level": verdict.level, "allowed": verdict.allowed}
        )

        # Extract envelope_id for per-envelope cost rollups. The verdict's
        # effective_envelope_snapshot carries the resolved envelope at
        # verification time; its "id" field (when populated) is the
        # envelope identifier per ConstraintEnvelopeConfig.
        envelope_snapshot = verdict_dict.get("effective_envelope_snapshot") or {}
        submission_envelope_id = (
            envelope_snapshot.get("id") if isinstance(envelope_snapshot, dict) else None
        )

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
                budget_allocated=budget,
                audit_trail=audit_trail,
                envelope_id=submission_envelope_id,
            )

        # --- ENFORCE mode: verdicts are binding ---
        if not verdict.allowed:
            _audit("governance_blocked", {"reason": verdict.reason})
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
                budget_allocated=budget,
                audit_trail=audit_trail,
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
            budget_allocated=budget,
            audit_trail=audit_trail,
            envelope_id=submission_envelope_id,
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
        return _DefaultGovernanceCallback(
            governance=self._governance, on_held=self._on_held
        )

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
        budget_allocated: float | None = None,
        audit_trail: list[dict[str, Any]] | None = None,
        envelope_id: str | None = None,
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
            budget_allocated: Budget ceiling for this submission.
            audit_trail: Accumulated audit trail entries.
            envelope_id: Governance envelope resolved for this submission
                (from the verdict's ``effective_envelope_snapshot``). Passed
                to the cost tracker so per-envelope consumption rollups work
                out-of-box. DISABLED mode passes ``None`` (no verdict).

        Returns:
            A WorkResult with execution outcome.
        """
        trail = audit_trail if audit_trail is not None else []

        def _audit(event: str, details: dict[str, Any] | None = None) -> None:
            trail.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event": event,
                    "role_address": role,
                    "details": details or {},
                }
            )

        supervisor = self._get_or_create_supervisor()
        if supervisor is None:
            _audit("execution_unavailable", {"reason": "kaizen-agents not installed"})
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
                budget_allocated=budget_allocated,
                audit_trail=trail,
            )

        _audit("execution_started")
        try:
            supervisor_result = await supervisor.run(
                objective=objective,
                context=ctx,
            )
            cost_usd = supervisor_result.budget_consumed
            # NaN/Inf/negative guard on budget_consumed (#237)
            if not math.isfinite(cost_usd) or cost_usd < 0:
                logger.error(
                    "budget_consumed is invalid (%r) — recording as 0.0",
                    cost_usd,
                )
                cost_usd = 0.0
            if cost_usd > 0:
                self._costs.record(
                    cost_usd,
                    f"submit: {objective[:80]}",
                    envelope_id=envelope_id,
                    agent_id=role,
                )

            _audit(
                "execution_completed",
                {"success": supervisor_result.success, "cost_usd": cost_usd},
            )
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
                budget_allocated=budget_allocated,
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
                audit_trail=trail,
                governance_shadow=shadow,
                governance_verdicts=governance_verdicts,
            )

        except Exception:
            logger.exception(
                "PactEngine.submit: supervisor execution failed for role=%s -- fail-closed",
                role,
            )
            _audit("execution_failed", {"error": "supervisor raised"})
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
                budget_allocated=budget_allocated,
                audit_trail=trail,
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

    # -------------------------------------------------------------------
    # Absorbed governance capabilities (PR#7 of issue #567)
    #
    # These methods REPLACE the rejected MLFP `GovernanceDiagnostics`
    # parallel facade. They live as first-class methods on PactEngine so
    # they cannot bypass self._submit_lock (chain-race defense) and so
    # the result dataclasses are frozen (no envelope widening at runtime).
    # -------------------------------------------------------------------

    async def verify_audit_chain(
        self,
        *,
        tenant_id: str | None = None,
        start_sequence: int = 0,
        end_sequence: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> "ChainVerificationResult":
        """Verify audit chain integrity within optional filters.

        Acquires ``self._submit_lock`` before reading the chain so an
        in-flight submit's audit append cannot race the verification.
        Returns a frozen ``ChainVerificationResult``. On chain break the
        result carries ``is_valid=False`` + ``first_break_reason`` +
        ``first_break_sequence``. NEVER raises on chain break (PACT MUST
        Rule 4 fail-closed). Only raises on impossible states (engine
        disposed).

        Args:
            tenant_id: Restrict verification to anchors whose metadata
                carries this tenant identifier. Matching is exact.
            start_sequence: Skip anchors whose ``sequence`` < this value.
            end_sequence: Skip anchors whose ``sequence`` > this value.
            since: Skip anchors timestamped before this UTC datetime.
            until: Skip anchors timestamped after this UTC datetime.
        """
        from pact.governance.results import ChainVerificationResult

        async with self._submit_lock:
            return self._verify_audit_chain_locked(
                tenant_id=tenant_id,
                start_sequence=start_sequence,
                end_sequence=end_sequence,
                since=since,
                until=until,
            )

    def _verify_audit_chain_locked(
        self,
        *,
        tenant_id: str | None,
        start_sequence: int,
        end_sequence: int | None,
        since: datetime | None,
        until: datetime | None,
    ) -> "ChainVerificationResult":
        """Inner verification — caller MUST hold ``self._submit_lock``."""
        from pact.governance.results import ChainVerificationResult

        now = datetime.now(timezone.utc)
        chain = self._governance.audit_chain
        chain_id = getattr(chain, "chain_id", None) if chain is not None else None

        # Fail-closed on no chain: report zero verified, is_valid=True for
        # an empty chain window (nothing to verify), matches semantics of
        # AuditChain.verify_chain_integrity on an empty chain.
        if chain is None:
            return ChainVerificationResult(
                is_valid=True,
                verified_count=0,
                first_break_reason=None,
                first_break_sequence=None,
                tenant_id=tenant_id,
                chain_id=None,
                verified_at=now,
            )

        try:
            # Delegate to the underlying AuditChain's own verification,
            # which already uses hmac.compare_digest and a single forward
            # walk. We then filter the result to our requested window.
            raw_valid, raw_errors = chain.verify_chain_integrity()
        except Exception as exc:  # pragma: no cover - defense-in-depth
            logger.exception(
                "verify_audit_chain: AuditChain.verify_chain_integrity raised — fail-closed"
            )
            return ChainVerificationResult(
                is_valid=False,
                verified_count=0,
                first_break_reason=f"chain verification raised: {type(exc).__name__}",
                first_break_sequence=None,
                tenant_id=tenant_id,
                chain_id=chain_id,
                verified_at=now,
            )

        # Apply filters to count how many anchors we actually verified.
        verified_count = 0
        anchors_in_window: list[Any] = []
        for anchor in chain.anchors:
            if anchor.sequence < start_sequence:
                continue
            if end_sequence is not None and anchor.sequence > end_sequence:
                continue
            if since is not None and anchor.timestamp < since:
                continue
            if until is not None and anchor.timestamp > until:
                continue
            if tenant_id is not None:
                anchor_tenant = (anchor.metadata or {}).get("tenant_id")
                if anchor_tenant != tenant_id:
                    continue
            anchors_in_window.append(anchor)
            verified_count += 1

        if raw_valid:
            return ChainVerificationResult(
                is_valid=True,
                verified_count=verified_count,
                first_break_reason=None,
                first_break_sequence=None,
                tenant_id=tenant_id,
                chain_id=chain_id,
                verified_at=now,
            )

        # Chain has breaks. Identify the earliest break that intersects
        # our window. AuditChain error messages carry "Anchor {i}:" prefix.
        first_break_seq: int | None = None
        first_break_reason: str | None = None
        in_window_seqs = {a.sequence for a in anchors_in_window}
        for err in raw_errors:
            # Parse the "Anchor {i}:" prefix
            seq_candidate: int | None = None
            if err.startswith("Anchor ") and ":" in err:
                try:
                    seq_candidate = int(err.split("Anchor ", 1)[1].split(":", 1)[0])
                except (ValueError, IndexError):
                    seq_candidate = None
            # Only count breaks that fall inside the requested window
            if seq_candidate is not None and seq_candidate not in in_window_seqs:
                continue
            if first_break_seq is None or (
                seq_candidate is not None and seq_candidate < first_break_seq
            ):
                first_break_seq = seq_candidate
                first_break_reason = err

        if first_break_reason is None:
            # Breaks exist, but none fall inside our filter window —
            # treat our window as valid (the caller filtered them out).
            return ChainVerificationResult(
                is_valid=True,
                verified_count=verified_count,
                first_break_reason=None,
                first_break_sequence=None,
                tenant_id=tenant_id,
                chain_id=chain_id,
                verified_at=now,
            )

        return ChainVerificationResult(
            is_valid=False,
            verified_count=verified_count,
            first_break_reason=first_break_reason,
            first_break_sequence=first_break_seq,
            tenant_id=tenant_id,
            chain_id=chain_id,
            verified_at=now,
        )

    def envelope_snapshot(
        self,
        *,
        envelope_id: str | None = None,
        role_address: str | None = None,
        at_timestamp: datetime | None = None,  # noqa: ARG002 — reserved for future
        tenant_id: str | None = None,
    ) -> "EnvelopeSnapshot":
        """Return a frozen point-in-time snapshot of a resolved envelope.

        Exactly one of ``envelope_id`` or ``role_address`` MUST be
        provided. The underlying ``GovernanceEngine.compute_envelope``
        (called for the role form) already acquires the engine's thread
        lock (``self._lock`` per PACT MUST Rule 8). The ``envelope_id``
        form reads from the frozen compiled org which is immutable after
        compile — no additional lock needed beyond the engine's own.

        ``at_timestamp`` is accepted for forward-compatibility but the
        current store does not support point-in-time rewind. The returned
        ``resolved_at`` is always the actual resolution time.

        Args:
            envelope_id: Stable identifier of the envelope. When provided,
                ``role_address`` MUST be None.
            role_address: D/T/R address to resolve an envelope for. When
                provided, ``envelope_id`` MUST be None.
            at_timestamp: Reserved for future point-in-time rewind.
            tenant_id: Carried through into the snapshot for forensic
                correlation; not used for filtering here.

        Raises:
            ValueError: If both or neither of ``envelope_id`` and
                ``role_address`` are provided.
            LookupError: If ``envelope_id`` is supplied but no such
                envelope is defined, OR if ``role_address`` resolves to
                no envelope.
        """
        from pact.governance.results import EnvelopeSnapshot

        if (envelope_id is None) == (role_address is None):
            raise ValueError(
                "envelope_snapshot: exactly one of envelope_id or "
                "role_address must be provided"
            )

        now = datetime.now(timezone.utc)

        # --- by envelope_id ---
        if envelope_id is not None:
            # The envelope store is keyed by role_address, not envelope_id.
            # Walk every role node, ask the store for its envelope, and
            # match by id. This is O(roles) but bounded by
            # MAX_TOTAL_NODES (100_000) per PACT MUST Rule 7.
            from kailash.trust.pact.addressing import NodeType

            compiled = self._governance.get_org()
            matched_envelope: Any | None = None
            matched_role_address: str | None = None
            for addr, node in compiled.nodes.items():
                if node.node_type != NodeType.ROLE:
                    continue
                try:
                    env = self._governance.compute_envelope(addr)
                except Exception:  # pragma: no cover — defense-in-depth
                    continue
                if env is None:
                    continue
                if getattr(env, "id", None) == envelope_id:
                    matched_envelope = env
                    matched_role_address = addr
                    break
            if matched_envelope is None:
                raise LookupError(
                    f"envelope_snapshot: no envelope with id={envelope_id!r}"
                )
            return EnvelopeSnapshot(
                envelope_id=envelope_id,
                role_address=matched_role_address or "",
                resolved_at=now,
                clearance=_extract_clearance_dict(matched_envelope),
                constraints=_extract_constraints_dict(matched_envelope),
                tenant_id=tenant_id,
            )

        # --- by role_address (thread-safe: compute_envelope acquires lock) ---
        assert role_address is not None  # type-narrowing for mypy
        envelope = self._governance.compute_envelope(role_address)
        if envelope is None:
            raise LookupError(
                f"envelope_snapshot: no envelope resolved for role_address={role_address!r}"
            )
        return EnvelopeSnapshot(
            envelope_id=getattr(envelope, "id", "") or "",
            role_address=role_address,
            resolved_at=now,
            clearance=_extract_clearance_dict(envelope),
            constraints=_extract_constraints_dict(envelope),
            tenant_id=tenant_id,
        )

    def iter_audit_anchors(
        self,
        *,
        tenant_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 10_000,
    ) -> Iterator[Any]:
        """Yield persisted audit anchors within the requested filters.

        The underlying ``AuditChain.anchors`` list is protected by the
        chain's internal lock during append. We snapshot it under a
        quick read-copy so iteration is safe even if a concurrent
        ``submit()`` appends in parallel. The yielded anchors are the
        canonical ``kailash.trust.pact.audit.AuditAnchor`` instances —
        we do NOT re-define that type.

        Args:
            tenant_id: Filter to anchors whose metadata carries this
                tenant identifier.
            since: Skip anchors timestamped before this UTC datetime.
            until: Skip anchors timestamped after this UTC datetime.
            limit: Maximum number of anchors to yield. Must be a
                non-negative integer.

        Raises:
            ValueError: If ``limit`` is negative.
        """
        if limit < 0:
            raise ValueError(f"iter_audit_anchors: limit must be >= 0, got {limit}")

        chain = self._governance.audit_chain
        if chain is None or limit == 0:
            return iter(())

        # Snapshot under a quick list copy. The chain's own _chain_lock is
        # held by append; list(...) is O(n) and serializes with append.
        snapshot = list(chain.anchors)

        def _generator() -> Iterator[Any]:
            yielded = 0
            for anchor in snapshot:
                if yielded >= limit:
                    break
                if since is not None and anchor.timestamp < since:
                    continue
                if until is not None and anchor.timestamp > until:
                    continue
                if tenant_id is not None:
                    anchor_tenant = (anchor.metadata or {}).get("tenant_id")
                    if anchor_tenant != tenant_id:
                        continue
                yielded += 1
                yield anchor

        return _generator()

    def _get_or_create_supervisor(self) -> Any | None:
        """Lazily create a GovernedSupervisor if kaizen-agents is installed.

        Returns:
            A GovernedSupervisor instance, or None if kaizen-agents
            is not importable.
        """
        # Fresh supervisor per submit() — no caching (#235)
        # Budget must reflect self._costs.remaining at call time
        try:
            from kaizen_agents.supervisor import GovernedSupervisor
        except ImportError:
            logger.info(
                "kaizen-agents not installed -- GovernedSupervisor unavailable. "
                "Install with: pip install kailash-kaizen"
            )
            return None

        return GovernedSupervisor(
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


def _extract_clearance_dict(envelope: Any) -> dict[str, Any]:
    """Extract a JSON-safe clearance dict from a ConstraintEnvelopeConfig.

    Used by ``PactEngine.envelope_snapshot`` to freeze the clearance-side
    of an envelope into the snapshot result. Tolerates missing / None
    attributes — returns only the fields actually populated.
    """
    clearance: dict[str, Any] = {}
    level = getattr(envelope, "confidentiality_clearance", None)
    if level is not None:
        clearance["confidentiality_level"] = (
            level.value if hasattr(level, "value") else str(level)
        )
    compartments = getattr(envelope, "compartments", None)
    if compartments is not None:
        clearance["compartments"] = list(compartments)
    return clearance


def _extract_constraints_dict(envelope: Any) -> dict[str, Any]:
    """Extract a JSON-safe constraints dict from a ConstraintEnvelopeConfig.

    Returns a dict with keys for each of the 5 CARE dimensions whose
    constraint config is non-None on the envelope. Uses pydantic
    ``.model_dump()`` when available so nested configs serialize
    uniformly; falls back to an ``__dict__`` shallow copy otherwise.
    """
    constraints: dict[str, Any] = {}
    for name in (
        "financial",
        "operational",
        "data_access",
        "temporal",
        "communication",
    ):
        value = getattr(envelope, name, None)
        if value is None:
            continue
        dump = getattr(value, "model_dump", None)
        if callable(dump):
            constraints[name] = dump()
        else:
            constraints[name] = dict(getattr(value, "__dict__", {}))
    max_depth = getattr(envelope, "max_delegation_depth", None)
    if max_depth is not None:
        constraints["max_delegation_depth"] = max_depth
    expires_at = getattr(envelope, "expires_at", None)
    if expires_at is not None:
        constraints["expires_at"] = (
            expires_at.isoformat()
            if hasattr(expires_at, "isoformat")
            else str(expires_at)
        )
    return constraints


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
    from kailash.trust.pact.compilation import RoleDefinition
    from kailash.trust.pact.config import DepartmentConfig, OrgDefinition, TeamConfig

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
        # Every mutation method on GovernanceEngine MUST be listed here.
        # Verified against GovernanceEngine method inventory (2026-04-06).
        _BLOCKED = {
            "set_role_envelope",
            "set_task_envelope",
            "grant_clearance",
            "revoke_clearance",
            "transition_clearance",
            "compile_org",
            "create_bridge",
            "approve_bridge",
            "consent_bridge",
            "reject_bridge",
            "register_compliance_role",
            "create_ksp",
            "designate_acting_occupant",
        }
        if name in _BLOCKED:
            raise AttributeError(
                f"'{type(self).__name__}' does not expose '{name}'. "
                "Use PactEngine._admin_governance for mutable operations."
            )
        return getattr(self._engine, name)
