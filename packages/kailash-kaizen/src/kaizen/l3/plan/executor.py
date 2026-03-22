# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PlanExecutor — DAG scheduling engine with PACT gradient rules.

Synchronous executor that schedules nodes according to DAG topology
and applies gradient rules (G1-G8) for failure handling. Agent execution
is delegated to a callback function (actual async agent spawning via
AgentFactory is an M6 integration concern).

Spec reference: workspaces/kaizen-l3/briefs/05-plan-dag.md Sections 4, 6.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

from kaizen.l3.plan.errors import ExecutionError
from kaizen.l3.plan.types import (
    EdgeType,
    Plan,
    PlanEvent,
    PlanNode,
    PlanNodeState,
    PlanState,
)

__all__ = ["PlanExecutor"]

logger = logging.getLogger(__name__)

# Type for the node execution callback
# (node_id, agent_spec_id) -> {"output": Any, "error": str|None, "retryable": bool}
NodeCallback = Callable[[str, str], dict[str, Any]]

# Default gradient configuration
_DEFAULT_GRADIENT = {
    "retry_budget": 2,
    "after_retry_exhaustion": "held",
    "optional_node_failure": "flagged",
    "resolution_timeout_seconds": 300,
    "budget_flag_pct": 0.80,
    "budget_hold_pct": 0.95,
}


class PlanExecutor:
    """Synchronous DAG executor with PACT verification gradient.

    Executes a validated plan by scheduling nodes in topological order
    and applying gradient rules for failure handling.

    Args:
        node_callback: Function called to execute each node.
            Signature: (node_id, agent_spec_id) -> result dict with keys:
            - output: Any (node output on success, None on failure)
            - error: str | None (error message on failure)
            - retryable: bool (whether the error is retryable)
            - envelope_violation: bool (optional, signals G8)
    """

    def __init__(self, node_callback: NodeCallback) -> None:
        self._callback = node_callback

    def execute(self, plan: Plan) -> list[PlanEvent]:
        """Execute the plan DAG.

        Precondition: plan.state must be VALIDATED.

        Returns:
            List of all PlanEvents emitted during execution.
        """
        if plan.state != PlanState.VALIDATED:
            raise ExecutionError(
                f"Plan must be in Validated state to execute, "
                f"got {plan.state.value}",
                details={"plan_id": plan.plan_id, "state": plan.state.value},
            )

        plan.state = PlanState.EXECUTING
        events: list[PlanEvent] = []
        gradient = {**_DEFAULT_GRADIENT, **plan.gradient}

        # Execution loop
        while True:
            # Find ready nodes
            ready_nodes = self._find_ready_nodes(plan)

            if not ready_nodes:
                # No ready nodes — check if we're done
                running = [
                    n for n in plan.nodes.values() if n.state == PlanNodeState.RUNNING
                ]
                if not running:
                    break
                # If there are running nodes but no ready nodes, we'd normally
                # await completion. In synchronous mode, this shouldn't happen.
                break

            # Execute all ready nodes
            for node in ready_nodes:
                node_events = self._execute_node(plan, node, gradient)
                events.extend(node_events)

        # Determine terminal state
        events.extend(self._determine_terminal_state(plan))
        return events

    def suspend(self, plan: Plan) -> list[PlanEvent]:
        """Suspend an executing plan.

        Precondition: plan.state must be EXECUTING.
        """
        if plan.state != PlanState.EXECUTING:
            raise ExecutionError(
                f"Can only suspend an Executing plan, got {plan.state.value}",
                details={"plan_id": plan.plan_id, "state": plan.state.value},
            )

        plan.state = PlanState.SUSPENDED
        return [PlanEvent.plan_suspended()]

    def resume(self, plan: Plan) -> list[PlanEvent]:
        """Resume a suspended plan.

        Precondition: plan.state must be SUSPENDED.
        """
        if plan.state != PlanState.SUSPENDED:
            raise ExecutionError(
                f"Can only resume a Suspended plan, got {plan.state.value}",
                details={"plan_id": plan.plan_id, "state": plan.state.value},
            )

        plan.state = PlanState.EXECUTING
        return [PlanEvent.plan_resumed()]

    def cancel(self, plan: Plan) -> list[PlanEvent]:
        """Cancel a plan (executing or suspended).

        Terminal states (Completed, Failed, Cancelled) raise error.
        """
        terminal_states = {PlanState.COMPLETED, PlanState.FAILED, PlanState.CANCELLED}
        if plan.state in terminal_states:
            raise ExecutionError(
                f"Cannot cancel a plan in terminal state {plan.state.value}",
                details={"plan_id": plan.plan_id, "state": plan.state.value},
            )

        events: list[PlanEvent] = []

        # Transition all non-terminal nodes to Skipped
        for node in plan.nodes.values():
            if node.state in (
                PlanNodeState.PENDING,
                PlanNodeState.READY,
                PlanNodeState.RUNNING,
            ):
                # Force state to SKIPPED (bypass normal transition for cancel)
                if node.state == PlanNodeState.RUNNING:
                    node.state = PlanNodeState.FAILED
                node.state = PlanNodeState.SKIPPED
                node.error = "plan_cancelled"
                events.append(
                    PlanEvent.node_skipped(node.node_id, reason="plan_cancelled")
                )

        plan.state = PlanState.CANCELLED
        events.append(PlanEvent.plan_cancelled())
        return events

    # -----------------------------------------------------------------------
    # Internal methods
    # -----------------------------------------------------------------------

    def _find_ready_nodes(self, plan: Plan) -> list[PlanNode]:
        """Find all nodes whose dependencies are satisfied.

        Node readiness depends on edge type:
        - DATA_DEPENDENCY: source must be COMPLETED
        - COMPLETION_DEPENDENCY: source must be terminal (COMPLETED, FAILED, SKIPPED)
        - CO_START: source must be RUNNING or terminal (advisory)
        """
        ready: list[PlanNode] = []

        for node in plan.nodes.values():
            if node.state != PlanNodeState.PENDING:
                continue

            if self._is_node_ready(plan, node):
                node.transition_to(PlanNodeState.READY)
                ready.append(node)

        return ready

    def _is_node_ready(self, plan: Plan, node: PlanNode) -> bool:
        """Check if all dependencies for a node are satisfied."""
        for edge in plan.edges:
            if edge.to_node != node.node_id:
                continue

            source = plan.nodes.get(edge.from_node)
            if source is None:
                continue

            if edge.edge_type == EdgeType.DATA_DEPENDENCY:
                if source.state != PlanNodeState.COMPLETED:
                    return False
            elif edge.edge_type == EdgeType.COMPLETION_DEPENDENCY:
                if not source.is_terminal:
                    return False
            elif edge.edge_type == EdgeType.CO_START:
                # Advisory — does not block. If source hasn't started yet,
                # we still allow the node to proceed.
                pass

        return True

    def _execute_node(
        self,
        plan: Plan,
        node: PlanNode,
        gradient: dict[str, Any],
    ) -> list[PlanEvent]:
        """Execute a single node and apply gradient rules."""
        events: list[PlanEvent] = []

        # Emit NodeReady
        events.append(PlanEvent.node_ready(node.node_id))

        # Transition to Running
        node.transition_to(PlanNodeState.RUNNING)
        instance_id = str(uuid.uuid4())
        node.instance_id = instance_id
        events.append(PlanEvent.node_started(node.node_id, instance_id=instance_id))

        # Execute via callback
        result = self._callback(node.node_id, node.agent_spec_id)

        error = result.get("error")
        output = result.get("output")
        retryable = result.get("retryable", False)
        envelope_violation = result.get("envelope_violation", False)

        if error is None:
            # G1: Success -> AutoApproved
            node.transition_to(PlanNodeState.COMPLETED)
            node.output = output
            events.append(PlanEvent.node_completed(node.node_id, output=output))
        elif envelope_violation:
            # G8: Envelope violation -> ALWAYS Blocked
            node.transition_to(PlanNodeState.FAILED)
            node.error = error
            events.append(
                PlanEvent.node_blocked(node.node_id, dimension="envelope", detail=error)
            )
            # Cascade: skip downstream data-dependent nodes
            events.extend(self._cascade_block(plan, node.node_id))
        elif retryable:
            # G2/G3: Retryable failure
            events.extend(self._handle_retryable_failure(plan, node, error, gradient))
        else:
            # G4/G5: Non-retryable failure
            events.extend(
                self._handle_non_retryable_failure(plan, node, error, gradient)
            )

        return events

    def _handle_retryable_failure(
        self,
        plan: Plan,
        node: PlanNode,
        error: str,
        gradient: dict[str, Any],
    ) -> list[PlanEvent]:
        """Handle a retryable failure: G2 (retry) or G3 (exhausted)."""
        events: list[PlanEvent] = []
        retry_budget = int(gradient.get("retry_budget", 2))

        node.transition_to(PlanNodeState.FAILED)
        node.error = error
        events.append(PlanEvent.node_failed(node.node_id, error=error, retryable=True))

        if node.retry_count < retry_budget:
            # G2: Retry within budget
            node.retry_count += 1
            events.append(
                PlanEvent.node_retrying(
                    node.node_id,
                    attempt=node.retry_count,
                    max_attempts=retry_budget,
                )
            )
            # Re-execute (transition back to Running)
            node.transition_to(PlanNodeState.RUNNING)
            instance_id = str(uuid.uuid4())
            node.instance_id = instance_id
            events.append(PlanEvent.node_started(node.node_id, instance_id=instance_id))

            result = self._callback(node.node_id, node.agent_spec_id)
            retry_error = result.get("error")
            retry_output = result.get("output")
            retry_retryable = result.get("retryable", False)
            retry_envelope = result.get("envelope_violation", False)

            if retry_error is None:
                # Retry succeeded
                node.transition_to(PlanNodeState.COMPLETED)
                node.output = retry_output
                events.append(
                    PlanEvent.node_completed(node.node_id, output=retry_output)
                )
            elif retry_envelope:
                node.transition_to(PlanNodeState.FAILED)
                node.error = retry_error
                events.append(
                    PlanEvent.node_blocked(
                        node.node_id, dimension="envelope", detail=retry_error or ""
                    )
                )
                events.extend(self._cascade_block(plan, node.node_id))
            elif retry_retryable and node.retry_count < retry_budget:
                # Recurse for additional retries
                events.extend(
                    self._handle_retryable_failure(
                        plan, node, retry_error or "", gradient
                    )
                )
            else:
                # G3 or non-retryable on retry: exhausted
                node.transition_to(PlanNodeState.FAILED)
                node.error = retry_error
                events.extend(self._handle_exhaustion(plan, node, gradient))
        else:
            # G3: Retry budget exhausted
            events.extend(self._handle_exhaustion(plan, node, gradient))

        return events

    def _handle_exhaustion(
        self,
        plan: Plan,
        node: PlanNode,
        gradient: dict[str, Any],
    ) -> list[PlanEvent]:
        """Handle retry budget exhaustion (G3)."""
        events: list[PlanEvent] = []
        after_exhaustion = gradient.get("after_retry_exhaustion", "held")

        if after_exhaustion == "blocked":
            events.append(
                PlanEvent.node_blocked(
                    node.node_id,
                    dimension="retry",
                    detail="Retry budget exhausted",
                )
            )
            events.extend(self._cascade_block(plan, node.node_id))
        else:
            # Default: held
            events.append(
                PlanEvent.node_held(
                    node.node_id,
                    reason="Retry budget exhausted",
                    zone="HELD",
                )
            )

        return events

    def _handle_non_retryable_failure(
        self,
        plan: Plan,
        node: PlanNode,
        error: str,
        gradient: dict[str, Any],
    ) -> list[PlanEvent]:
        """Handle non-retryable failure: G4 (optional) or G5 (required)."""
        events: list[PlanEvent] = []

        node.transition_to(PlanNodeState.FAILED)
        node.error = error
        events.append(PlanEvent.node_failed(node.node_id, error=error, retryable=False))

        if node.optional:
            # G4: Optional node failure
            optional_zone = gradient.get("optional_node_failure", "flagged")

            if optional_zone == "auto_approved":
                node.transition_to(PlanNodeState.SKIPPED)
                events.append(
                    PlanEvent.node_skipped(
                        node.node_id, reason=f"Optional node failed: {error}"
                    )
                )
            elif optional_zone == "flagged":
                events.append(
                    PlanEvent.node_flagged(
                        node.node_id, reason=f"Optional node failed: {error}"
                    )
                )
                node.transition_to(PlanNodeState.SKIPPED)
                events.append(
                    PlanEvent.node_skipped(
                        node.node_id, reason=f"Optional node failed (flagged): {error}"
                    )
                )
            else:
                # Held
                events.append(
                    PlanEvent.node_held(
                        node.node_id,
                        reason=f"Optional node failed: {error}",
                        zone="HELD",
                    )
                )
        else:
            # G5: Required node failure -> Held
            events.append(
                PlanEvent.node_held(
                    node.node_id,
                    reason=f"Required node failed (non-retryable): {error}",
                    zone="HELD",
                )
            )

        return events

    def _cascade_block(self, plan: Plan, blocked_node_id: str) -> list[PlanEvent]:
        """Cascade block to downstream nodes via DATA_DEPENDENCY edges.

        Skips nodes reachable from the blocked node through DATA_DEPENDENCY.
        COMPLETION_DEPENDENCY edges do NOT cascade termination.
        """
        events: list[PlanEvent] = []

        # Find all nodes reachable via DATA_DEPENDENCY from blocked node (BFS)
        to_skip: set[str] = set()
        queue = [blocked_node_id]

        while queue:
            current = queue.pop(0)
            for edge in plan.edges:
                if (
                    edge.from_node == current
                    and edge.edge_type == EdgeType.DATA_DEPENDENCY
                    and edge.to_node not in to_skip
                    and edge.to_node != blocked_node_id
                ):
                    downstream = plan.nodes.get(edge.to_node)
                    if downstream and downstream.state in (
                        PlanNodeState.PENDING,
                        PlanNodeState.READY,
                    ):
                        to_skip.add(edge.to_node)
                        queue.append(edge.to_node)

        for node_id in to_skip:
            node = plan.nodes[node_id]
            node.state = PlanNodeState.SKIPPED
            node.error = f"upstream_blocked: {blocked_node_id}"
            events.append(
                PlanEvent.node_skipped(
                    node_id,
                    reason=f"upstream_blocked: {blocked_node_id}",
                )
            )

        return events

    def _determine_terminal_state(self, plan: Plan) -> list[PlanEvent]:
        """Determine the final state of the plan after execution loop ends."""
        events: list[PlanEvent] = []

        required_nodes = [n for n in plan.nodes.values() if not n.optional]
        all_required_completed = all(
            n.state == PlanNodeState.COMPLETED for n in required_nodes
        )

        if all_required_completed:
            plan.state = PlanState.COMPLETED
            results = {
                n.node_id: n.output
                for n in plan.nodes.values()
                if n.state == PlanNodeState.COMPLETED
            }
            events.append(PlanEvent.plan_completed(results=results))
        else:
            # Check if any required node is in a failed/blocked terminal state
            failed_nodes = [
                n.node_id
                for n in required_nodes
                if n.state in (PlanNodeState.FAILED, PlanNodeState.SKIPPED)
            ]
            if failed_nodes:
                plan.state = PlanState.FAILED
                events.append(
                    PlanEvent.plan_failed(
                        failed_nodes=failed_nodes,
                        reason="Required nodes failed or were blocked",
                    )
                )
            else:
                # Some nodes still pending/held -- plan is suspended
                plan.state = PlanState.SUSPENDED
                events.append(PlanEvent.plan_suspended())

        return events
