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

import logging
import math
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Awaitable, Callable

from kaizen_agents.audit.trail import AuditTrail
from kaizen_agents.governance.accountability import AccountabilityTracker
from kaizen_agents.governance.budget import BudgetTracker
from kaizen_agents.governance.bypass import BypassManager
from kaizen_agents.governance.cascade import CascadeManager
from kaizen_agents.governance.clearance import (
    ClassificationAssigner,
    ClearanceEnforcer,
    DataClassification,
)
from kaizen_agents.governance.dereliction import DerelictionDetector
from kaizen_agents.governance.vacancy import VacancyManager
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

__all__ = ["GovernedSupervisor", "SupervisorResult"]


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

# Map user-friendly clearance strings to DataClassification
_CLEARANCE_MAP: dict[str, DataClassification] = {
    "public": DataClassification.C0_PUBLIC,
    "internal": DataClassification.C1_INTERNAL,
    "restricted": DataClassification.C1_INTERNAL,
    "confidential": DataClassification.C2_CONFIDENTIAL,
    "secret": DataClassification.C3_SECRET,
    "top_secret": DataClassification.C4_TOP_SECRET,
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
        self._envelope = ConstraintEnvelope(
            financial={"limit": budget_usd},
            operational={"allowed": list(self._tools), "blocked": []},
            temporal={"limit_seconds": timeout_seconds},
            data_access={"ceiling": data_clearance, "scopes": []},
            communication={"recipients": [], "channels": []},
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

        budget_allocated = self._envelope.financial.get("limit", 0.0)

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

                    # Track cost
                    cost = output.get("cost", 0.0)
                    if isinstance(cost, (int, float)) and math.isfinite(cost) and cost >= 0:
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
        budget_allocated = self._envelope.financial.get("limit", 0.0)

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

                    cost = output.get("cost", 0.0)
                    if isinstance(cost, (int, float)) and math.isfinite(cost) and cost >= 0:
                        total_cost += cost
                        self._budget.record_consumption("root", cost)

                    events.append(
                        PlanEvent(
                            event_type=PlanEventType.NODE_COMPLETED,
                            node_id=node_id,
                            output=node.output,
                        )
                    )

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
    def clearance_level(self) -> DataClassification:
        """The data clearance level."""
        return self._clearance_level

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
    """Convert a ConstraintEnvelope to a plain dict."""
    return {
        "financial": env.financial,
        "operational": env.operational,
        "temporal": env.temporal,
        "data_access": env.data_access,
        "communication": env.communication,
    }


async def _default_executor(spec: AgentSpec, inputs: dict[str, Any]) -> dict[str, Any]:
    """Default no-op executor for dry runs."""
    return {"result": f"[dry-run] {spec.description}", "cost": 0.0}
