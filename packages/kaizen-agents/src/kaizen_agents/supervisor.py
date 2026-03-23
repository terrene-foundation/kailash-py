# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""GovernedSupervisor — the progressive-disclosure entry point for L3 orchestration.

Hides the 20-concept L3 surface area behind three layers:

Layer 1 (simple):
    supervisor = GovernedSupervisor(model="claude-sonnet-4-6", budget_usd=10.0)
    result = await supervisor.run("Analyze this codebase")

Layer 2 (configured):
    supervisor = GovernedSupervisor(
        model="claude-sonnet-4-6",
        budget_usd=10.0,
        tools=["read_file", "grep", "write_report"],
        data_clearance="restricted",
        warning_threshold=0.70,
    )

Layer 3 (advanced):
    supervisor.accountability   # AccountabilityTracker
    supervisor.budget          # BudgetTracker
    supervisor.cascade         # CascadeManager
    supervisor.clearance       # ClearanceEnforcer
    supervisor.audit           # AuditTrail

Defaults follow PACT default-deny: empty tools, $1 budget, PUBLIC clearance.
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

try:
    from kailash.trust.pact.agent import GovernanceHeldError
except ImportError:

    class GovernanceHeldError(Exception):  # type: ignore[no-redef]
        """Fallback when kailash-pact is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args)


from kaizen_agents.audit.trail import AuditTrail
from kaizen_agents.governance.accountability import AccountabilityTracker
from kaizen_agents.governance.budget import BudgetTracker
from kaizen_agents.governance.bypass import BypassManager
from kaizen_agents.governance.cascade import CascadeManager
from kaizen_agents.governance.cost_model import CostModel
from kailash.trust import ConfidentialityLevel

from kaizen_agents.governance.clearance import (
    ClassificationAssigner,
    ClearanceEnforcer,
)
from kaizen_agents.governance.dereliction import DerelictionDetector
from kaizen_agents.governance.vacancy import VacancyManager
from kailash.trust.pact.config import (
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TemporalConstraintConfig,
)

from kaizen_agents.types import (
    AgentSpec,
    ConstraintEnvelope,
    GradientZone,
    Plan,
    PlanEvent,
    PlanEventType,
    PlanGradient,
    PlanModification,
    PlanNode,
    PlanNodeState,
    PlanState,
)

logger = logging.getLogger(__name__)

__all__ = ["GovernanceHeldError", "GovernedSupervisor", "HoldRecord", "SupervisorResult"]


@dataclass
class HoldRecord:
    """Record of a held node awaiting human resolution.

    Attributes:
        node_id: The plan node ID that was held.
        reason: Human-readable reason the node was held.
        details: Structured details from the governance verdict.
        held_at: UTC timestamp when the hold was created.
        event: Async event for signaling hold resolution.
        approved: True if approved, False if rejected, None if unresolved.
        modified_context: Optional modified context for resumed execution.
    """

    node_id: str
    reason: str
    details: dict[str, Any]
    held_at: datetime
    event: asyncio.Event = field(default_factory=asyncio.Event)
    approved: bool | None = None
    modified_context: dict[str, Any] | None = None


class _ReadOnlyView:
    """Read-only proxy that exposes only query methods, not mutation methods."""

    def __init__(self, target: Any, allowed_methods: frozenset[str]) -> None:
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_allowed", allowed_methods)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or name not in object.__getattribute__(self, "_allowed"):
            target = object.__getattribute__(self, "_target")
            raise AttributeError(
                f"'{type(target).__name__}' read-only view has no attribute '{name}'"
            )
        return getattr(object.__getattribute__(self, "_target"), name)


# Allowed query methods for each Layer 3 governance subsystem
_AUDIT_QUERY_METHODS = frozenset({"verify_chain", "query_by_agent", "to_list"})
_ACCOUNTABILITY_QUERY_METHODS = frozenset(
    {
        "get_address",
        "get_record",
        "get_siblings",
        "trace_accountability",
        "query_policy_source",
        "agent_count",
    }
)
_BUDGET_QUERY_METHODS = frozenset({"get_snapshot", "is_held", "get_events"})
_CASCADE_QUERY_METHODS = frozenset({"get_envelope", "get_children"})
_CLEARANCE_QUERY_METHODS = frozenset(
    {"filter_for_clearance", "get_classification", "is_visible", "value_count"}
)
_CLASSIFIER_QUERY_METHODS = frozenset({"classify", "classify_and_wrap"})
_DERELICTION_QUERY_METHODS = frozenset({"get_stats", "get_warnings", "threshold"})
_BYPASS_QUERY_METHODS = frozenset(
    {"is_bypassed", "get_history", "get_original_envelope", "active_count"}
)
_VACANCY_QUERY_METHODS = frozenset({"get_orphans", "is_orphaned"})

# Map user-friendly clearance strings to ConfidentialityLevel
_CLEARANCE_MAP: dict[str, ConfidentialityLevel] = {
    "public": ConfidentialityLevel.PUBLIC,
    "internal": ConfidentialityLevel.RESTRICTED,
    "restricted": ConfidentialityLevel.RESTRICTED,
    "confidential": ConfidentialityLevel.CONFIDENTIAL,
    "secret": ConfidentialityLevel.SECRET,
    "top_secret": ConfidentialityLevel.TOP_SECRET,
}


@dataclass(frozen=True)
class SupervisorResult:
    """The outcome of a GovernedSupervisor.run() execution.

    Frozen to prevent post-construction mutation (R1-02 security hardening).

    Attributes:
        success: True if all required plan nodes completed.
        results: Mapping of node_id -> output for completed nodes.
        plan: The final Plan state (may have been modified by recovery).
        events: All PlanEvents emitted during execution.
        audit_trail: List of EATP audit records (as dicts).
        budget_consumed: Total financial dimension consumed.
        budget_allocated: Total financial dimension allocated.
        modifications: Plan modifications applied during recovery.
    """

    success: bool = False
    results: dict[str, Any] = field(default_factory=dict)
    plan: Plan | None = None
    events: list[PlanEvent] = field(default_factory=list)
    audit_trail: list[dict[str, Any]] = field(default_factory=list)
    budget_consumed: float = 0.0
    budget_allocated: float = 0.0
    modifications: list[PlanModification] = field(default_factory=list)


# Type alias for the execute_node callback
ExecuteNodeFn = Callable[[AgentSpec, dict[str, Any]], Awaitable[dict[str, Any]]]


class GovernedSupervisor:
    """PACT-governed L3 autonomous agent supervisor.

    Progressive disclosure API:
    - Layer 1: model + budget_usd (everything else gets sensible defaults)
    - Layer 2: tools, data_clearance, warning_threshold, gradient config
    - Layer 3: direct access to governance subsystems via properties

    Args:
        model: Model identifier string (informational, passed to AgentSpecs).
        budget_usd: Maximum budget in USD. Default $1.00.
        tools: Allowed tool names. Default empty (default-deny per PACT Rule 5).
        data_clearance: Clearance level string. Default "public".
        timeout_seconds: Maximum execution time. Default 300s (5 min).
        warning_threshold: Budget warning threshold (0.0-1.0). Default 0.70.
        max_children: Max child agents per parent. Default 10.
        max_depth: Max delegation depth. Default 5.
        policy_source: Human identity that defined this supervisor's constraints.
        cost_model: Optional CostModel for computing LLM token costs. When provided,
            executor results that include ``prompt_tokens`` and ``completion_tokens``
            but no explicit ``cost`` will have their cost computed automatically.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        budget_usd: float = 1.0,
        tools: list[str] | None = None,
        data_clearance: str = "public",
        timeout_seconds: float = 300.0,
        warning_threshold: float = 0.70,
        max_children: int = 10,
        max_depth: int = 5,
        policy_source: str = "",
        cost_model: CostModel | None = None,
    ) -> None:
        # Validate inputs
        if not math.isfinite(budget_usd) or budget_usd < 0:
            raise ValueError(f"budget_usd must be finite and non-negative, got {budget_usd}")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be finite and positive, got {timeout_seconds}")
        if not math.isfinite(warning_threshold):
            raise ValueError(f"warning_threshold must be finite, got {warning_threshold}")
        if data_clearance not in _CLEARANCE_MAP:
            raise ValueError(
                f"data_clearance must be one of {sorted(_CLEARANCE_MAP.keys())}, "
                f"got {data_clearance!r}"
            )

        self._model = model
        self._tools = list(tools) if tools else []
        self._clearance_level = _CLEARANCE_MAP[data_clearance]
        self._policy_source = policy_source
        self._max_children = max_children
        self._max_depth = max_depth

        # Build the root envelope (Layer 1 defaults)
        self._envelope = ConstraintEnvelopeConfig(
            id="supervisor-root",
            financial=FinancialConstraintConfig(max_spend_usd=budget_usd),
            operational=OperationalConstraintConfig(
                allowed_actions=list(self._tools),
                blocked_actions=[],
            ),
            temporal=TemporalConstraintConfig(),
            confidentiality_clearance=self._clearance_level,
        )

        self._gradient = PlanGradient(
            retry_budget=2,
            after_retry_exhaustion=GradientZone.HELD,
            resolution_timeout=timedelta(seconds=min(timeout_seconds, 300)),
            budget_flag_threshold=warning_threshold,
            budget_hold_threshold=0.95,
        )

        # Layer 3: governance subsystems
        self._audit = AuditTrail()
        self._accountability = AccountabilityTracker()
        self._budget = BudgetTracker(
            warning_threshold=warning_threshold,
            hold_threshold=1.0,
        )
        self._cascade = CascadeManager()
        self._clearance = ClearanceEnforcer()
        self._classifier = ClassificationAssigner()
        self._dereliction = DerelictionDetector()
        self._bypass = BypassManager()
        self._vacancy = VacancyManager()

        # LLM token cost model (optional — auto-computes cost from token counts)
        self._cost_model = cost_model

        # External hold records: node_id -> HoldRecord (thread-safe, bounded)
        self._held_nodes: dict[str, HoldRecord] = {}
        self._held_lock = threading.Lock()
        self._max_held_nodes = 10_000

        # Budget tracking
        self._budget.allocate("root", budget_usd)

        logger.info(
            "GovernedSupervisor initialized: model=%s budget=$%.2f tools=%d clearance=%s",
            model,
            budget_usd,
            len(self._tools),
            data_clearance,
        )

    # -------------------------------------------------------------------
    # Layer 1: Simple API
    # -------------------------------------------------------------------

    async def run(
        self,
        objective: str,
        context: dict[str, Any] | None = None,
        execute_node: ExecuteNodeFn | None = None,
    ) -> SupervisorResult:
        """Execute an objective through the full L3 pipeline.

        Decomposes the objective into a plan, executes each node through
        the provided callback, tracks budget and audit, and returns results.

        If no execute_node callback is provided, nodes are "executed" with
        a no-op that returns their spec description (useful for dry runs).

        Args:
            objective: Natural-language objective to accomplish.
            context: Optional context dict passed to plan nodes.
            execute_node: Async callback(spec, inputs) -> {"result": ..., "cost": ...}.

        Returns:
            A SupervisorResult with outcomes, audit trail, and budget info.
        """
        ctx = context or {}
        executor = execute_node or _default_executor

        # Record genesis in audit trail (idempotent — safe to call run() multiple times)
        if self._accountability.get_address("root") is None:
            self._accountability.register_root(
                "root",
                envelope=_envelope_to_dict(self._envelope),
                policy_source=self._policy_source,
            )
            self._audit.record_genesis(
                agent_id="root",
                envelope=_envelope_to_dict(self._envelope),
            )
            self._cascade.register("root", None, _envelope_to_dict(self._envelope))

        budget_allocated = (
            self._envelope.financial.max_spend_usd if self._envelope.financial else 0.0
        )

        # Build a single-node plan if no decomposer is wired
        # (GovernedSupervisor is the entry point — decomposition happens
        # at the LLM layer above; here we accept a pre-built plan or
        # create a trivial one-node plan for the objective)
        plan = self._build_trivial_plan(objective, ctx)

        # Execute plan nodes in topological order
        plan.state = PlanState.EXECUTING
        events: list[PlanEvent] = []
        node_results: dict[str, Any] = {}
        total_cost = 0.0

        ready_nodes = self._find_ready_nodes(plan)

        plan_failed = False
        while ready_nodes and not plan_failed:
            for node_id in ready_nodes:
                node = plan.nodes[node_id]
                node.state = PlanNodeState.RUNNING

                events.append(
                    PlanEvent(
                        event_type=PlanEventType.NODE_STARTED,
                        node_id=node_id,
                    )
                )

                # Resolve inputs from upstream
                inputs = self._resolve_inputs(node, node_results, ctx)

                # Check budget before execution
                budget_snap = self._budget.get_snapshot("root")
                if budget_snap and budget_snap.utilization >= 1.0:
                    node.state = PlanNodeState.HELD
                    events.append(
                        PlanEvent(
                            event_type=PlanEventType.NODE_HELD,
                            node_id=node_id,
                            reason="budget_exhaustion",
                        )
                    )
                    self._audit.record_held("root", node_id, "budget_exhaustion")
                    continue

                # Execute the node
                try:
                    output = await executor(node.agent_spec, inputs)
                    node.output = output.get("result")
                    node.state = PlanNodeState.COMPLETED
                    node_results[node_id] = node.output

                    # Track cost (explicit or computed from tokens via cost_model)
                    cost = self._resolve_cost(output)
                    if cost > 0:
                        total_cost += cost
                        budget_events = self._budget.record_consumption("root", cost)
                        for be in budget_events:
                            if be.event_type == "warning":
                                events.append(
                                    PlanEvent(
                                        event_type=PlanEventType.ENVELOPE_WARNING,
                                        node_id=node_id,
                                        dimension="financial",
                                        usage_pct=be.details.get("utilization", 0.0),
                                    )
                                )

                    events.append(
                        PlanEvent(
                            event_type=PlanEventType.NODE_COMPLETED,
                            node_id=node_id,
                            output=node.output,
                        )
                    )

                    self._audit.record_action(
                        agent_id="root",
                        action=f"node_completed:{node_id}",
                        details={"cost": cost, "node_id": node_id},
                    )

                except GovernanceHeldError as held:
                    # External governance verdict: pause this node for human approval
                    node.state = PlanNodeState.HELD
                    hold_reason = (
                        str(getattr(held.verdict, "reason", held))
                        if hasattr(held, "verdict")
                        else str(held)
                    )
                    hold_record = HoldRecord(
                        node_id=node_id,
                        reason=hold_reason,
                        details=getattr(held, "details", {}) if hasattr(held, "details") else {},
                        held_at=datetime.now(timezone.utc),
                    )
                    with self._held_lock:
                        # Evict resolved holds if at capacity
                        if len(self._held_nodes) >= self._max_held_nodes:
                            resolved = [k for k, v in self._held_nodes.items() if v.event.is_set()]
                            for k in resolved:
                                del self._held_nodes[k]
                        self._held_nodes[node_id] = hold_record
                    events.append(
                        PlanEvent(
                            event_type=PlanEventType.NODE_HELD,
                            node_id=node_id,
                            reason=f"governance: {hold_reason}",
                        )
                    )
                    self._audit.record_held("root", node_id, f"governance: {hold_reason}")
                    continue

                except (KeyboardInterrupt, SystemExit):
                    raise

                except Exception as exc:
                    node.state = PlanNodeState.FAILED
                    node.error = str(exc)

                    events.append(
                        PlanEvent(
                            event_type=PlanEventType.NODE_FAILED,
                            node_id=node_id,
                            error=str(exc),
                        )
                    )

                    self._audit.record_action(
                        agent_id="root",
                        action=f"node_failed:{node_id}",
                        details={"error": str(exc), "node_id": node_id},
                    )

                    # R1-06: Non-optional node failure halts plan
                    if not node.optional:
                        plan_failed = True
                        break

            ready_nodes = self._find_ready_nodes(plan)

        # Determine success
        required_nodes = [n for n in plan.nodes.values() if not n.optional]
        all_completed = all(n.state == PlanNodeState.COMPLETED for n in required_nodes)
        plan.state = PlanState.COMPLETED if all_completed else PlanState.FAILED

        events.append(
            PlanEvent(
                event_type=(
                    PlanEventType.PLAN_COMPLETED if all_completed else PlanEventType.PLAN_FAILED
                ),
                results=node_results if all_completed else None,
            )
        )

        return SupervisorResult(
            success=all_completed,
            results=node_results,
            plan=plan,
            events=events,
            audit_trail=self._audit.to_list(),
            budget_consumed=total_cost,
            budget_allocated=budget_allocated,
        )

    async def run_plan(
        self,
        plan: Plan,
        execute_node: ExecuteNodeFn | None = None,
        context: dict[str, Any] | None = None,
    ) -> SupervisorResult:
        """Execute a pre-built plan (Layer 2+).

        Same as run() but accepts an already-composed Plan instead of
        an objective string.

        Args:
            plan: A pre-built Plan DAG.
            execute_node: Async callback for node execution.
            context: Optional context dict.

        Returns:
            A SupervisorResult.
        """
        # Register root if not already done
        if self._accountability.get_address("root") is None:
            self._accountability.register_root(
                "root",
                envelope=_envelope_to_dict(self._envelope),
                policy_source=self._policy_source,
            )
            self._audit.record_genesis(
                agent_id="root",
                envelope=_envelope_to_dict(self._envelope),
            )

        ctx = context or {}
        executor = execute_node or _default_executor
        budget_allocated = (
            self._envelope.financial.max_spend_usd if self._envelope.financial else 0.0
        )

        # R1-10 (L2): Validate plan limits
        if len(plan.nodes) > self._max_children * self._max_depth:
            raise ValueError(
                f"Plan has {len(plan.nodes)} nodes, exceeding limit of "
                f"{self._max_children * self._max_depth}"
            )

        plan.state = PlanState.EXECUTING
        events: list[PlanEvent] = []
        node_results: dict[str, Any] = {}
        total_cost = 0.0

        ready_nodes = self._find_ready_nodes(plan)

        plan_failed = False
        while ready_nodes and not plan_failed:
            for node_id in ready_nodes:
                node = plan.nodes[node_id]
                node.state = PlanNodeState.RUNNING
                inputs = self._resolve_inputs(node, node_results, ctx)

                try:
                    output = await executor(node.agent_spec, inputs)
                    node.output = output.get("result")
                    node.state = PlanNodeState.COMPLETED
                    node_results[node_id] = node.output

                    cost = self._resolve_cost(output)
                    if cost > 0:
                        total_cost += cost
                        self._budget.record_consumption("root", cost)

                    events.append(
                        PlanEvent(
                            event_type=PlanEventType.NODE_COMPLETED,
                            node_id=node_id,
                            output=node.output,
                        )
                    )

                except GovernanceHeldError as held:
                    # External governance verdict: pause this node for human approval
                    node.state = PlanNodeState.HELD
                    hold_reason = (
                        str(getattr(held.verdict, "reason", held))
                        if hasattr(held, "verdict")
                        else str(held)
                    )
                    hold_record = HoldRecord(
                        node_id=node_id,
                        reason=hold_reason,
                        details=getattr(held, "details", {}) if hasattr(held, "details") else {},
                        held_at=datetime.now(timezone.utc),
                    )
                    with self._held_lock:
                        # Evict resolved holds if at capacity
                        if len(self._held_nodes) >= self._max_held_nodes:
                            resolved = [k for k, v in self._held_nodes.items() if v.event.is_set()]
                            for k in resolved:
                                del self._held_nodes[k]
                        self._held_nodes[node_id] = hold_record
                    events.append(
                        PlanEvent(
                            event_type=PlanEventType.NODE_HELD,
                            node_id=node_id,
                            reason=f"governance: {hold_reason}",
                        )
                    )
                    self._audit.record_held("root", node_id, f"governance: {hold_reason}")
                    continue

                except (KeyboardInterrupt, SystemExit):
                    raise

                except Exception as exc:
                    node.state = PlanNodeState.FAILED
                    node.error = str(exc)
                    events.append(
                        PlanEvent(
                            event_type=PlanEventType.NODE_FAILED,
                            node_id=node_id,
                            error=str(exc),
                        )
                    )

                    # R1-06: Non-optional node failure halts plan
                    if not node.optional:
                        plan_failed = True
                        break

            ready_nodes = self._find_ready_nodes(plan)

        required = [n for n in plan.nodes.values() if not n.optional]
        all_ok = all(n.state == PlanNodeState.COMPLETED for n in required)
        plan.state = PlanState.COMPLETED if all_ok else PlanState.FAILED

        return SupervisorResult(
            success=all_ok,
            results=node_results,
            plan=plan,
            events=events,
            audit_trail=self._audit.to_list(),
            budget_consumed=total_cost,
            budget_allocated=budget_allocated,
        )

    # -------------------------------------------------------------------
    # Layer 2: Configuration accessors
    # -------------------------------------------------------------------

    @property
    def model(self) -> str:
        """The model identifier."""
        return self._model

    @property
    def envelope(self) -> ConstraintEnvelope:
        """The root constraint envelope (deep copy — mutations do not affect supervisor)."""
        import copy

        return copy.deepcopy(self._envelope)

    @property
    def gradient(self) -> PlanGradient:
        """The verification gradient configuration."""
        return self._gradient

    @property
    def tools(self) -> list[str]:
        """The allowed tool names."""
        return list(self._tools)

    @property
    def cost_model(self) -> CostModel | None:
        """The LLM token cost model, or None if not configured."""
        return self._cost_model

    @property
    def clearance_level(self) -> ConfidentialityLevel:
        """The data clearance level."""
        return self._clearance_level

    # -------------------------------------------------------------------
    # Hold management (external governance HELD mechanism)
    # -------------------------------------------------------------------

    @property
    def held_nodes(self) -> dict[str, HoldRecord]:
        """Currently held nodes awaiting resolution. Returns a thread-safe copy."""
        with self._held_lock:
            return dict(self._held_nodes)

    def resolve_hold(
        self,
        node_id: str,
        approved: bool,
        modified_context: dict[str, Any] | None = None,
    ) -> None:
        """Resume or reject a held node. Thread-safe.

        Args:
            node_id: The held node ID.
            approved: True to resume execution, False to fail the node.
            modified_context: Optional modified context for the resumed node.

        Raises:
            ValueError: If the node is not currently held.
        """
        with self._held_lock:
            record = self._held_nodes.get(node_id)
            if record is None:
                raise ValueError(f"Node '{node_id}' is not currently held")
            record.approved = approved
            record.modified_context = modified_context
        # Event.set() outside lock to avoid deadlock with event loop waiters
        record.event.set()

    # -------------------------------------------------------------------
    # Layer 3: Tool-level audit recording (for CLI/entrypoint use)
    # -------------------------------------------------------------------

    def record_tool_use(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        blocked: bool = False,
        reason: str = "",
    ) -> None:
        """Record a tool invocation in the audit trail.

        Called by CLI/entrypoint tool executors to record governance-relevant
        tool usage. This is the only write path exposed outside the supervisor's
        own workflow execution.

        Args:
            tool_name: Name of the tool invoked.
            arguments: Tool call arguments (keys only for security).
            blocked: Whether the tool was blocked by governance.
            reason: Reason for blocking (if blocked).
        """
        details: dict[str, Any] = {
            "tool": tool_name,
            "argument_keys": list((arguments or {}).keys()),
            "blocked": blocked,
        }
        if blocked and reason:
            details["reason"] = reason
        action = f"tool_blocked:{tool_name}" if blocked else f"tool_use:{tool_name}"
        self._audit.record_action("root", action, details)

    def record_cost(self, amount: float, *, source: str = "tool") -> None:
        """Record a cost against the session budget.

        This is the write path for budget consumption from CLI/entrypoint code.
        The ``budget`` property only exposes read-only queries.

        Args:
            amount: Cost in USD (must be finite and non-negative).
            source: What incurred the cost (e.g. "tool", "llm_tokens").
        """
        if not math.isfinite(amount) or amount < 0:
            logger.warning("Ignoring invalid cost: %s (source=%s)", amount, source)
            return
        try:
            self._budget.record_consumption("root", amount)
        except ValueError:
            pass  # Agent not allocated yet (should not happen)

    # -------------------------------------------------------------------
    # Layer 3: Direct access to governance subsystems
    # -------------------------------------------------------------------

    @property
    def audit(self) -> Any:
        """The EATP audit trail (read-only view)."""
        return _ReadOnlyView(self._audit, _AUDIT_QUERY_METHODS)

    @property
    def accountability(self) -> Any:
        """The D/T/R accountability tracker (read-only view)."""
        return _ReadOnlyView(self._accountability, _ACCOUNTABILITY_QUERY_METHODS)

    @property
    def budget(self) -> Any:
        """The budget tracker (read-only view)."""
        return _ReadOnlyView(self._budget, _BUDGET_QUERY_METHODS)

    @property
    def cascade(self) -> Any:
        """The cascade revocation manager (read-only view)."""
        return _ReadOnlyView(self._cascade, _CASCADE_QUERY_METHODS)

    @property
    def clearance(self) -> Any:
        """The clearance enforcer (read-only view)."""
        return _ReadOnlyView(self._clearance, _CLEARANCE_QUERY_METHODS)

    @property
    def classifier(self) -> Any:
        """The data classification assigner (read-only view)."""
        return _ReadOnlyView(self._classifier, _CLASSIFIER_QUERY_METHODS)

    @property
    def dereliction(self) -> Any:
        """The dereliction detector (read-only view)."""
        return _ReadOnlyView(self._dereliction, _DERELICTION_QUERY_METHODS)

    @property
    def bypass_manager(self) -> Any:
        """The emergency bypass manager (read-only view)."""
        return _ReadOnlyView(self._bypass, _BYPASS_QUERY_METHODS)

    @property
    def vacancy(self) -> Any:
        """The vacancy manager (read-only view)."""
        return _ReadOnlyView(self._vacancy, _VACANCY_QUERY_METHODS)

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _resolve_cost(self, output: dict[str, Any]) -> float:
        """Resolve cost from executor output.

        Resolution order:
        1. If ``cost`` is present and valid, use it directly.
        2. If ``cost`` is absent (or 0.0) but ``prompt_tokens`` and
           ``completion_tokens`` are present and a cost_model is configured,
           compute cost from token counts using the cost model.
        3. Otherwise return 0.0.

        Args:
            output: The executor result dict.

        Returns:
            Cost in USD (finite, non-negative).
        """
        explicit_cost = output.get("cost")
        if (
            explicit_cost is not None
            and isinstance(explicit_cost, (int, float))
            and math.isfinite(explicit_cost)
            and explicit_cost > 0
        ):
            return float(explicit_cost)

        # Auto-compute from tokens if cost_model is available
        if self._cost_model is not None:
            prompt_tokens = output.get("prompt_tokens")
            completion_tokens = output.get("completion_tokens")
            if (
                isinstance(prompt_tokens, int)
                and isinstance(completion_tokens, int)
                and prompt_tokens >= 0
                and completion_tokens >= 0
            ):
                model_name = output.get("model", self._model)
                computed = self._cost_model.compute(model_name, prompt_tokens, completion_tokens)
                if math.isfinite(computed) and computed >= 0:
                    return computed

        return 0.0

    def _build_trivial_plan(self, objective: str, _context: dict[str, Any]) -> Plan:
        """Build a single-node plan for an objective (no LLM decomposition)."""
        spec = AgentSpec(
            spec_id="root-task",
            name="root-task",
            description=objective,
            tool_ids=list(self._tools),
            envelope=self._envelope,
        )
        node = PlanNode(
            node_id="task-0",
            agent_spec=spec,
        )
        return Plan(
            name=objective[:80],
            envelope=self._envelope,
            gradient=self._gradient,
            nodes={"task-0": node},
            edges=[],
        )

    @staticmethod
    def _find_ready_nodes(plan: Plan) -> list[str]:
        """Find nodes whose dependencies are all completed."""
        # Build dependency map
        deps: dict[str, set[str]] = {nid: set() for nid in plan.nodes}
        for edge in plan.edges:
            if edge.to_node in deps:
                deps[edge.to_node].add(edge.from_node)

        ready = []
        for nid, node in plan.nodes.items():
            if node.state != PlanNodeState.PENDING:
                continue
            all_deps_met = all(
                plan.nodes[dep].state == PlanNodeState.COMPLETED
                for dep in deps[nid]
                if dep in plan.nodes
            )
            if all_deps_met:
                ready.append(nid)

        return ready

    @staticmethod
    def _resolve_inputs(
        node: PlanNode,
        node_results: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve input_mapping to actual values from upstream outputs."""
        inputs = dict(context)
        for key, pno in node.input_mapping.items():
            upstream_output = node_results.get(pno.source_node)
            if isinstance(upstream_output, dict):
                inputs[key] = upstream_output.get(pno.output_key)
            else:
                inputs[key] = upstream_output
        return inputs


def _envelope_to_dict(env: ConstraintEnvelope) -> dict[str, Any]:
    """Convert a ConstraintEnvelopeConfig to a plain dict for audit/cascade systems."""
    return {
        "financial": env.financial.model_dump() if env.financial else {},
        "operational": env.operational.model_dump(),
        "temporal": env.temporal.model_dump(),
        "data_access": env.data_access.model_dump(),
        "communication": env.communication.model_dump(),
    }


async def _default_executor(spec: AgentSpec, inputs: dict[str, Any]) -> dict[str, Any]:
    """Default no-op executor for dry runs."""
    return {"result": f"[dry-run] {spec.description}", "cost": 0.0}
