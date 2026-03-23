"""
PlanMonitor: The autonomous orchestration engine for L3 plan execution.

Wires all M2 components into a single execution loop:
    TaskDecomposer -> AgentDesigner -> PlanComposer -> execute -> monitor -> recover

The PlanMonitor does NOT directly call the SDK's PlanExecutor (it does not exist
yet in kailash-py). Instead, it implements a simplified execution loop that:
    - Tracks which nodes are ready (dependencies met)
    - "Executes" nodes by calling a provided execute_node callback
    - Applies the verification gradient for failure handling
    - Dispatches to recovery components on held events
    - Yields PlanEvents for the caller to consume

The execute_node callback is the integration point -- when the SDK's AgentFactory
and PlanExecutor exist, they replace this callback. For now, the kz CLI provides
the callback that actually runs agents.

See: 01-analysis/01-research/08-planexecutor-boundary-resolution.md
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from kaizen_agents.llm import LLMClient
from kaizen_agents.planner.composer import PlanComposer, PlanValidator
from kaizen_agents.planner.decomposer import TaskDecomposer
from kaizen_agents.planner.designer import AgentDesigner, SpawnDecision
from kaizen_agents.recovery.diagnoser import FailureCategory, FailureDiagnoser
from kaizen_agents.recovery.recomposer import Recomposer, RecoveryStrategy
from kaizen_agents.types import (
    AgentSpec,
    ConstraintEnvelope,
    EdgeType,
    GradientZone,
    Plan,
    PlanEdge,
    PlanEvent,
    PlanEventType,
    PlanGradient,
    PlanModification,
    PlanModificationType,
    PlanNode,
    PlanNodeState,
    PlanState,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PlanResult -- the outcome of a full plan execution
# ---------------------------------------------------------------------------


@dataclass
class PlanResult:
    """The outcome of a full plan execution through the PlanMonitor.

    Attributes:
        plan: The final plan state after execution (may have been modified
            by recovery operations).
        results: Mapping of node_id -> output for completed nodes.
        events: All PlanEvent objects emitted during execution, in order.
        modifications_applied: All PlanModification objects that were applied
            during recovery, in the order they were applied.
        total_cost: Cumulative cost tracked across all node executions.
            Populated from the execute_node callback's output if it includes
            a "cost" key; otherwise 0.0.
        success: True if all required nodes completed. False if any required
            node failed without recovery.
    """

    plan: Plan
    results: dict[str, Any] = field(default_factory=dict)
    events: list[PlanEvent] = field(default_factory=list)
    modifications_applied: list[PlanModification] = field(default_factory=list)
    total_cost: float = 0.0
    success: bool = False


# ---------------------------------------------------------------------------
# PlanMonitor -- the orchestration engine
# ---------------------------------------------------------------------------


class PlanMonitor:
    """The autonomous orchestration engine that turns SDK mechanisms into
    self-directed plan execution with failure recovery.

    Wires together:
        - TaskDecomposer: objective -> subtasks
        - AgentDesigner: subtask -> AgentSpec + SpawnDecision
        - PlanComposer: subtasks + specs -> validated Plan DAG
        - Execution loop: ready nodes -> execute_node callback
        - FailureDiagnoser: failed node -> root cause analysis
        - Recomposer: diagnosis -> PlanModification for recovery

    Two entry points:
        - run(): Full L3 loop from objective string to PlanResult
        - run_plan(): Execute an already-composed Plan

    The execute_node callback is the integration point. It receives an
    AgentSpec and an input dict (resolved from upstream node outputs),
    and returns a dict with at least a "result" key. Optional keys:
        - "cost": float, added to total_cost tracking
        - "error": str, if present the node is treated as failed

    Usage:
        monitor = PlanMonitor(llm=my_llm, envelope=my_envelope, gradient=my_gradient)

        async def my_executor(spec: AgentSpec, inputs: dict) -> dict:
            # Actually run the agent
            return {"result": "some output", "cost": 0.01}

        result = await monitor.run(
            objective="Analyze the codebase",
            context={"repo": "github.com/example/repo"},
            execute_node=my_executor,
        )
    """

    def __init__(
        self,
        llm: LLMClient,
        envelope: ConstraintEnvelope,
        gradient: PlanGradient,
    ) -> None:
        """Initialise the PlanMonitor with its component dependencies.

        Args:
            llm: LLM client shared across all sub-components. All LLM calls
                flow through this single client.
            envelope: The constraint envelope bounding the entire plan.
                Child nodes receive tightened sub-envelopes.
            gradient: The verification gradient configuration that determines
                how failures, retries, and budget consumption are classified
                into gradient zones.
        """
        self._llm = llm
        self._envelope = envelope
        self._gradient = gradient

        # Sub-components -- all share the same LLM client
        self._decomposer = TaskDecomposer(llm_client=llm)
        self._designer = AgentDesigner(llm_client=llm)
        self._composer = PlanComposer(llm_client=llm)
        self._validator = PlanValidator()
        self._diagnoser = FailureDiagnoser(llm_client=llm)
        self._recomposer = Recomposer(llm_client=llm)

    def validate_plan_with_sdk(self, plan: Plan) -> list[str]:
        """Validate a local Plan using the SDK PlanValidator.

        Converts the local Plan to an SDK Plan via the adapter layer,
        runs SDK structural and envelope validation, and returns a list
        of error strings. An empty list means the plan is valid.

        This method is synchronous (no LLM calls) and deterministic.
        It provides SDK-boundary validation without replacing the local
        PlanValidator.

        Args:
            plan: The local Plan to validate.

        Returns:
            A list of error strings. Empty means the plan passes all
            SDK validation checks.
        """
        from kaizen_agents._sdk_compat import plan_to_sdk
        from kaizen.l3.plan.validator import PlanValidator as SdkPlanValidator

        sdk_plan = plan_to_sdk(plan)
        errors: list[str] = []
        errors.extend(SdkPlanValidator.validate_structure(sdk_plan))
        errors.extend(SdkPlanValidator.validate_envelopes(sdk_plan))
        return [str(e) for e in errors]

    async def run(
        self,
        objective: str,
        context: dict[str, Any],
        execute_node: Callable[[AgentSpec, dict[str, Any]], Awaitable[dict[str, Any]]],
    ) -> PlanResult:
        """Full L3 loop: decompose -> design -> compose -> execute -> monitor -> recover.

        Takes a natural-language objective and drives it through the full
        planning and execution pipeline.

        Args:
            objective: Natural-language description of what to accomplish.
            context: Contextual information (tech stack, project state, etc.)
                passed to the decomposer and made available to nodes.
            execute_node: Callback that runs a single node. Receives the
                node's AgentSpec and a dict of resolved inputs from upstream
                nodes. Returns a dict with at least "result"; optionally
                "cost" and "error".

        Returns:
            A PlanResult with the final plan state, per-node results,
            all events, all modifications applied, total cost, and
            success/failure status.
        """
        # Phase 1: Decompose objective into subtasks
        subtasks = self._decomposer.decompose(
            objective=objective,
            context=context,
            envelope=self._envelope,
        )

        # Phase 2: Design AgentSpecs for each subtask
        specs: list[tuple[AgentSpec, SpawnDecision]] = []
        for subtask in subtasks:
            spec, decision = self._designer.design(
                subtask=subtask,
                parent_envelope=self._envelope,
                available_tools=subtask.suggested_tools,
            )
            specs.append((spec, decision))

        # Phase 3: Compose into a Plan DAG and validate
        plan, errors = self._composer.compose_and_validate(
            subtasks=subtasks,
            specs=specs,
            parent_envelope=self._envelope,
            plan_name=f"plan-for-{objective[:50]}",
        )

        if errors:
            error_msgs = "; ".join(f"{e.code}: {e.message}" for e in errors)
            logger.warning("Plan validation produced errors: %s", error_msgs)
            # Attach the gradient before execution even if there are warnings
            plan.gradient = self._gradient

        plan.gradient = self._gradient

        # Phase 4-7: Execute the plan
        return await self.run_plan(plan=plan, execute_node=execute_node)

    async def run_plan(
        self,
        plan: Plan,
        execute_node: Callable[[AgentSpec, dict[str, Any]], Awaitable[dict[str, Any]]],
    ) -> PlanResult:
        """Execute an already-composed plan through the monitoring loop.

        Iterates through the plan DAG, executing ready nodes, applying
        the verification gradient to failures, and dispatching to
        recovery components when held events occur.

        Args:
            plan: A Plan (ideally in Validated state). The gradient
                configuration on the plan is used for failure handling.
            execute_node: Callback that runs a single node.

        Returns:
            A PlanResult summarising the execution outcome.
        """
        plan.state = PlanState.EXECUTING
        plan.gradient = self._gradient

        result = PlanResult(plan=plan)
        node_outputs: dict[str, Any] = {}
        retry_counts: dict[str, int] = defaultdict(int)

        # Mark initial ready nodes
        self._update_ready_nodes(plan)

        while True:
            ready_nodes = [
                nid for nid, node in plan.nodes.items() if node.state == PlanNodeState.READY
            ]

            if not ready_nodes:
                # No more work to do -- check if we are done or stuck
                break

            for node_id in ready_nodes:
                node = plan.nodes[node_id]

                # Emit NODE_STARTED
                started_event = PlanEvent(
                    event_type=PlanEventType.NODE_STARTED,
                    node_id=node_id,
                )
                result.events.append(started_event)
                node.state = PlanNodeState.RUNNING

                # Resolve inputs from upstream node outputs
                resolved_inputs = self._resolve_inputs(node, node_outputs)

                # Check budget before execution
                budget_zone = self._check_budget(result.total_cost)
                if budget_zone == GradientZone.HELD:
                    held_event = PlanEvent(
                        event_type=PlanEventType.NODE_HELD,
                        node_id=node_id,
                        reason="Budget consumption at hold threshold",
                        zone=GradientZone.HELD,
                    )
                    result.events.append(held_event)
                    node.state = PlanNodeState.FAILED
                    node.error = "Budget hold threshold reached"

                    # Attempt recovery for budget hold
                    recovered = await self._handle_held_event(
                        plan=plan,
                        node_id=node_id,
                        error="Budget hold threshold reached",
                        result=result,
                    )
                    if not recovered:
                        continue
                    # If recovered, the node state may have changed via modification.
                    # Re-check on next iteration.
                    continue

                if budget_zone == GradientZone.BLOCKED:
                    blocked_event = PlanEvent(
                        event_type=PlanEventType.NODE_BLOCKED,
                        node_id=node_id,
                        reason="Budget exhausted",
                        zone=GradientZone.BLOCKED,
                    )
                    result.events.append(blocked_event)
                    node.state = PlanNodeState.FAILED
                    node.error = "Budget exhausted"
                    self._terminate_downstream(plan, node_id)
                    continue

                if budget_zone == GradientZone.FLAGGED:
                    warning_event = PlanEvent(
                        event_type=PlanEventType.ENVELOPE_WARNING,
                        node_id=node_id,
                        dimension="financial",
                        usage_pct=result.total_cost / self._get_budget_limit(),
                    )
                    result.events.append(warning_event)

                # Execute the node via the callback
                try:
                    output = await execute_node(node.agent_spec, resolved_inputs)
                except Exception as exc:
                    output = {"error": str(exc)}

                # Extract cost tracking (NaN/Inf/negative → fail-closed)
                node_cost = output.get("cost", 0.0)
                if isinstance(node_cost, (int, float)):
                    if not math.isfinite(node_cost) or node_cost < 0:
                        node.state = PlanNodeState.FAILED
                        node.error = (
                            f"Invalid cost value: {node_cost!r}. "
                            "Cost must be a finite non-negative number."
                        )
                        result.events.append(
                            PlanEvent(
                                event_type=PlanEventType.NODE_BLOCKED,
                                node_id=node_id,
                                dimension="financial",
                                reason=f"NaN/Inf/negative cost: {node_cost!r}",
                                zone=GradientZone.BLOCKED,
                            )
                        )
                        self._terminate_downstream(plan, node_id)
                        continue
                    result.total_cost += node_cost

                # Check for failure
                error = output.get("error")
                if error:
                    node.error = str(error)
                    node.retry_count = retry_counts[node_id]

                    # Apply gradient classification
                    zone = self._classify_failure(plan, node)

                    if zone == GradientZone.AUTO_APPROVED:
                        # Retry: auto-approved
                        if retry_counts[node_id] < plan.gradient.retry_budget:
                            retry_counts[node_id] += 1
                            node.retry_count = retry_counts[node_id]
                            retry_event = PlanEvent(
                                event_type=PlanEventType.NODE_RETRYING,
                                node_id=node_id,
                                error=str(error),
                                attempt=retry_counts[node_id],
                                max_attempts=plan.gradient.retry_budget,
                            )
                            result.events.append(retry_event)
                            # Reset to READY for retry
                            node.state = PlanNodeState.READY
                            continue
                        else:
                            # Retries exhausted -- escalate per gradient
                            zone = plan.gradient.after_retry_exhaustion

                    if zone == GradientZone.FLAGGED:
                        flagged_event = PlanEvent(
                            event_type=PlanEventType.NODE_FLAGGED,
                            node_id=node_id,
                            error=str(error),
                            zone=GradientZone.FLAGGED,
                        )
                        result.events.append(flagged_event)
                        # Skip this node but continue the plan
                        node.state = PlanNodeState.SKIPPED
                        self._update_ready_nodes(plan)
                        continue

                    if zone == GradientZone.HELD:
                        held_event = PlanEvent(
                            event_type=PlanEventType.NODE_HELD,
                            node_id=node_id,
                            error=str(error),
                            zone=GradientZone.HELD,
                        )
                        result.events.append(held_event)
                        node.state = PlanNodeState.FAILED

                        # Attempt LLM-driven recovery
                        recovered = await self._handle_held_event(
                            plan=plan,
                            node_id=node_id,
                            error=str(error),
                            result=result,
                        )
                        if not recovered:
                            self._terminate_downstream(plan, node_id)
                        else:
                            self._update_ready_nodes(plan)
                        continue

                    if zone == GradientZone.BLOCKED:
                        blocked_event = PlanEvent(
                            event_type=PlanEventType.NODE_BLOCKED,
                            node_id=node_id,
                            error=str(error),
                            zone=GradientZone.BLOCKED,
                        )
                        result.events.append(blocked_event)
                        node.state = PlanNodeState.FAILED
                        self._terminate_downstream(plan, node_id)
                        continue

                    # Fallback: treat unknown zone as held
                    node.state = PlanNodeState.FAILED
                    self._terminate_downstream(plan, node_id)
                    continue

                # Success path
                node_result = output.get("result")
                node.output = node_result
                node.state = PlanNodeState.COMPLETED
                node_outputs[node_id] = node_result

                completed_event = PlanEvent(
                    event_type=PlanEventType.NODE_COMPLETED,
                    node_id=node_id,
                    output=node_result,
                )
                result.events.append(completed_event)

                # Update downstream nodes that may now be ready
                self._update_ready_nodes(plan)

        # Determine overall success
        result.results = dict(node_outputs)
        result.success = self._evaluate_plan_success(plan)

        if result.success:
            plan.state = PlanState.COMPLETED
            result.events.append(
                PlanEvent(
                    event_type=PlanEventType.PLAN_COMPLETED,
                    results=dict(node_outputs),
                )
            )
        else:
            plan.state = PlanState.FAILED
            failed_nodes = [
                nid
                for nid, n in plan.nodes.items()
                if n.state == PlanNodeState.FAILED and not n.optional
            ]
            result.events.append(
                PlanEvent(
                    event_type=PlanEventType.PLAN_FAILED,
                    failed_nodes=failed_nodes,
                )
            )

        return result

    # ------------------------------------------------------------------
    # Internal: node readiness and dependency resolution
    # ------------------------------------------------------------------

    def _update_ready_nodes(self, plan: Plan) -> None:
        """Mark PENDING nodes as READY when all their dependencies are satisfied.

        A node is ready when every upstream node connected by a DATA_DEPENDENCY
        or COMPLETION_DEPENDENCY edge is in a terminal state (COMPLETED, SKIPPED,
        or FAILED for optional nodes).
        """
        # Build the set of upstream dependencies per node
        upstream: dict[str, set[str]] = defaultdict(set)
        for edge in plan.edges:
            if edge.edge_type in (EdgeType.DATA_DEPENDENCY, EdgeType.COMPLETION_DEPENDENCY):
                upstream[edge.to_node].add(edge.from_node)

        for node_id, node in plan.nodes.items():
            if node.state != PlanNodeState.PENDING:
                continue

            deps = upstream.get(node_id, set())
            all_deps_resolved = True
            for dep_id in deps:
                dep_node = plan.nodes.get(dep_id)
                if dep_node is None:
                    continue
                if dep_node.state == PlanNodeState.COMPLETED:
                    continue
                if dep_node.state == PlanNodeState.SKIPPED:
                    continue
                # A failed optional dependency does not block
                if dep_node.state == PlanNodeState.FAILED and dep_node.optional:
                    continue
                all_deps_resolved = False
                break

            if all_deps_resolved:
                node.state = PlanNodeState.READY

    def _resolve_inputs(self, node: PlanNode, node_outputs: dict[str, Any]) -> dict[str, Any]:
        """Resolve a node's input_mapping against completed upstream outputs.

        For each entry in input_mapping, looks up the source node's output
        in node_outputs and extracts the specified output_key. If the source
        output is a dict, extracts the key; otherwise uses the raw value.

        Args:
            node: The node whose inputs to resolve.
            node_outputs: Mapping of node_id -> output from completed nodes.

        Returns:
            A dict of input_key -> resolved_value for the node.
        """
        resolved: dict[str, Any] = {}
        for input_key, mapping in node.input_mapping.items():
            source_output = node_outputs.get(mapping.source_node)
            if source_output is None:
                resolved[input_key] = None
                continue
            if isinstance(source_output, dict):
                resolved[input_key] = source_output.get(mapping.output_key, source_output)
            else:
                resolved[input_key] = source_output
        return resolved

    # ------------------------------------------------------------------
    # Internal: verification gradient classification
    # ------------------------------------------------------------------

    def _classify_failure(self, plan: Plan, node: PlanNode) -> GradientZone:
        """Classify a node failure into a gradient zone.

        Uses the plan's PlanGradient configuration:
        - If retries remain: AUTO_APPROVED (will retry)
        - If optional and retries exhausted: uses optional_node_failure zone
        - If required and retries exhausted: uses after_retry_exhaustion zone

        Args:
            plan: The plan containing gradient configuration.
            node: The failed node.

        Returns:
            The GradientZone classification.
        """
        if node.retry_count < plan.gradient.retry_budget:
            return GradientZone.AUTO_APPROVED

        if node.optional:
            return plan.gradient.optional_node_failure

        return plan.gradient.after_retry_exhaustion

    def _check_budget(self, current_cost: float) -> GradientZone:
        """Check the current cost against budget gradient thresholds.

        Args:
            current_cost: The cumulative cost so far.

        Returns:
            The budget gradient zone. NaN/Inf/negative costs are BLOCKED
            (fail-closed per trust-plane-security.md Rule 3).
        """
        # Fail-closed: NaN/Inf/negative cost → BLOCKED
        if not math.isfinite(current_cost) or current_cost < 0:
            return GradientZone.BLOCKED

        budget_limit = self._get_budget_limit()

        # Fail-closed: NaN/Inf budget_limit → BLOCKED
        if not math.isfinite(budget_limit) or budget_limit <= 0:
            # inf budget means no limit → auto-approved (legitimate case)
            # But NaN budget → BLOCKED
            if budget_limit == float("inf"):
                return GradientZone.AUTO_APPROVED
            return GradientZone.BLOCKED

        usage_pct = current_cost / budget_limit

        if usage_pct >= 1.0:
            return GradientZone.BLOCKED
        if usage_pct >= self._gradient.budget_hold_threshold:
            return GradientZone.HELD
        if usage_pct >= self._gradient.budget_flag_threshold:
            return GradientZone.FLAGGED
        return GradientZone.AUTO_APPROVED

    def _get_budget_limit(self) -> float:
        """Get the financial budget limit from the envelope.

        Returns:
            The budget limit, or float('inf') if not set.
        """
        limit = float(self._envelope.financial.get("limit", float("inf")))
        return limit

    # ------------------------------------------------------------------
    # Internal: recovery via FailureDiagnoser + Recomposer
    # ------------------------------------------------------------------

    async def _handle_held_event(
        self,
        plan: Plan,
        node_id: str,
        error: str,
        result: PlanResult,
    ) -> bool:
        """Handle a held event by diagnosing the failure and attempting recovery.

        The recovery pipeline:
        1. FailureDiagnoser analyzes the error in plan context
        2. Recomposer selects a strategy and produces PlanModifications
        3. Modifications are applied to the plan
        4. Returns True if recovery was applied, False if plan should terminate

        Args:
            plan: The plan containing the failed node.
            node_id: The ID of the held node.
            error: The error string from the failed node.
            result: The PlanResult being built (for event and modification tracking).

        Returns:
            True if recovery modifications were applied and execution should
            continue. False if the failure is unrecoverable.
        """
        try:
            # Phase 1: Diagnose
            diagnosis = self._diagnoser.diagnose(
                node_id=node_id,
                error=error,
                plan=plan,
            )

            # Phase 2: Recompose
            recovery = self._recomposer.recompose(
                plan=plan,
                failed_node_id=node_id,
                diagnosis=diagnosis,
            )

            # Phase 3: Apply modifications
            if recovery.strategy == RecoveryStrategy.ABORT:
                logger.info(
                    "Recovery strategy is ABORT for node %s: %s",
                    node_id,
                    recovery.rationale,
                )
                return False

            if recovery.strategy == RecoveryStrategy.RETRY:
                # Reset the node to READY so it gets retried on next iteration
                plan.nodes[node_id].state = PlanNodeState.READY
                plan.nodes[node_id].error = None
                return True

            # Apply each modification
            for mod in recovery.modifications:
                self._apply_modification(plan, mod)
                result.modifications_applied.append(mod)
                mod_event = PlanEvent(
                    event_type=PlanEventType.MODIFICATION_APPLIED,
                    modification=mod,
                )
                result.events.append(mod_event)

            # After modifications, update readiness
            self._update_ready_nodes(plan)
            return True

        except (KeyError, ValueError) as exc:
            logger.warning(
                "Recovery failed for node %s: %s",
                node_id,
                str(exc),
            )
            return False

    def _apply_modification(self, plan: Plan, mod: PlanModification) -> None:
        """Apply a single PlanModification to the plan.

        This is the simplified version of what the SDK's PlanExecutor will do.
        Handles ADD_NODE, REMOVE_NODE, REPLACE_NODE, SKIP_NODE, ADD_EDGE,
        REMOVE_EDGE, and UPDATE_SPEC.

        Args:
            plan: The plan to modify in place.
            mod: The modification to apply.
        """
        mod_type = mod.modification_type

        if mod_type == PlanModificationType.ADD_NODE and mod.node:
            plan.nodes[mod.node.node_id] = mod.node
            if mod.edges:
                plan.edges.extend(mod.edges)

        elif mod_type == PlanModificationType.REMOVE_NODE and mod.node_id:
            plan.nodes.pop(mod.node_id, None)
            plan.edges = [
                e for e in plan.edges if e.from_node != mod.node_id and e.to_node != mod.node_id
            ]

        elif mod_type == PlanModificationType.REPLACE_NODE:
            old_id = mod.old_node_id
            new_node = mod.new_node
            if old_id and new_node:
                plan.nodes.pop(old_id, None)
                plan.nodes[new_node.node_id] = new_node
                # Rewire edges: replace references to old_id with new_node.node_id
                new_edges: list[PlanEdge] = []
                for edge in plan.edges:
                    from_n = new_node.node_id if edge.from_node == old_id else edge.from_node
                    to_n = new_node.node_id if edge.to_node == old_id else edge.to_node
                    new_edges.append(
                        PlanEdge(from_node=from_n, to_node=to_n, edge_type=edge.edge_type)
                    )
                plan.edges = new_edges

        elif mod_type == PlanModificationType.SKIP_NODE and mod.node_id:
            node = plan.nodes.get(mod.node_id)
            if node:
                node.state = PlanNodeState.SKIPPED

        elif mod_type == PlanModificationType.ADD_EDGE and mod.edge:
            plan.edges.append(mod.edge)

        elif mod_type == PlanModificationType.REMOVE_EDGE:
            if mod.from_node and mod.to_node:
                plan.edges = [
                    e
                    for e in plan.edges
                    if not (e.from_node == mod.from_node and e.to_node == mod.to_node)
                ]

        elif mod_type == PlanModificationType.UPDATE_SPEC:
            if mod.node_id and mod.new_spec:
                node = plan.nodes.get(mod.node_id)
                if node:
                    node.agent_spec = mod.new_spec

    # ------------------------------------------------------------------
    # Internal: downstream termination
    # ------------------------------------------------------------------

    def _terminate_downstream(self, plan: Plan, failed_node_id: str) -> None:
        """Cascade failure to all downstream nodes reachable from a failed node.

        Nodes reachable via DATA_DEPENDENCY or COMPLETION_DEPENDENCY edges
        from the failed node are marked as FAILED (if they are PENDING or READY).

        Args:
            plan: The plan to modify.
            failed_node_id: The node whose downstream should be terminated.
        """
        visited: set[str] = {failed_node_id}
        queue = [failed_node_id]

        while queue:
            current = queue.pop()
            for edge in plan.edges:
                if edge.from_node == current and edge.to_node not in visited:
                    if edge.edge_type in (
                        EdgeType.DATA_DEPENDENCY,
                        EdgeType.COMPLETION_DEPENDENCY,
                    ):
                        downstream_node = plan.nodes.get(edge.to_node)
                        if downstream_node and downstream_node.state in (
                            PlanNodeState.PENDING,
                            PlanNodeState.READY,
                        ):
                            downstream_node.state = PlanNodeState.FAILED
                            downstream_node.error = (
                                f"Cascaded failure from upstream node '{failed_node_id}'"
                            )
                        visited.add(edge.to_node)
                        queue.append(edge.to_node)

    # ------------------------------------------------------------------
    # Internal: plan success evaluation
    # ------------------------------------------------------------------

    def _evaluate_plan_success(self, plan: Plan) -> bool:
        """Determine whether the plan succeeded overall.

        A plan succeeds if all required (non-optional) nodes are in a
        terminal success state (COMPLETED or SKIPPED). If any required
        node is FAILED, the plan has failed.

        Args:
            plan: The plan to evaluate.

        Returns:
            True if all required nodes completed successfully.
        """
        for node in plan.nodes.values():
            if node.optional:
                continue
            if node.state not in (PlanNodeState.COMPLETED, PlanNodeState.SKIPPED):
                return False
        return True
