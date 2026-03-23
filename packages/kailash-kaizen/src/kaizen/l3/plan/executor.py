# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PlanExecutor — DAG scheduling engine with PACT gradient rules.

Synchronous and asynchronous executors that schedule nodes according to DAG
topology and apply gradient rules (G1-G8) for failure handling. Agent
execution is delegated to a callback function (actual async agent spawning
via AgentFactory is an M6 integration concern).

The ``AsyncPlanExecutor`` adds concurrent execution of independent ready
nodes via ``asyncio.gather()``, an optional event callback for real-time
notification, and optional concurrency limiting via ``asyncio.Semaphore``.

Spec reference: workspaces/kaizen-l3/briefs/05-plan-dag.md Sections 4, 6.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Awaitable, Callable

from kaizen.l3.plan.errors import ExecutionError
from kaizen.l3.plan.types import (
    EdgeType,
    Plan,
    PlanEvent,
    PlanNode,
    PlanNodeState,
    PlanState,
)

__all__ = ["AsyncPlanExecutor", "PlanExecutor"]

logger = logging.getLogger(__name__)

# Type for the synchronous node execution callback
# (node_id, agent_spec_id) -> {"output": Any, "error": str|None, "retryable": bool}
NodeCallback = Callable[[str, str], dict[str, Any]]

# Type for the asynchronous node execution callback
AsyncNodeCallback = Callable[[str, str], Awaitable[dict[str, Any]]]

# Type for the event callback (optional, for real-time notification)
EventCallback = Callable[[PlanEvent], Awaitable[None]]

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

        # Transition all non-terminal nodes (including HELD) to Skipped
        for node in plan.nodes.values():
            if node.state in (
                PlanNodeState.PENDING,
                PlanNodeState.READY,
                PlanNodeState.RUNNING,
                PlanNodeState.HELD,
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
        """Handle retry budget exhaustion (G3).

        When gradient says "held", transition node to HELD state.
        When gradient says "blocked", leave in FAILED and cascade.
        """
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
            # Default: held — transition node from FAILED to HELD
            node.transition_to(PlanNodeState.HELD)
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
        """Handle non-retryable failure: G4 (optional) or G5 (required).

        For G5 (required) and G4 with held zone: transition FAILED -> HELD.
        """
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
                # Held — transition from FAILED to HELD
                node.transition_to(PlanNodeState.HELD)
                events.append(
                    PlanEvent.node_held(
                        node.node_id,
                        reason=f"Optional node failed: {error}",
                        zone="HELD",
                    )
                )
        else:
            # G5: Required node failure -> transition from FAILED to HELD
            node.transition_to(PlanNodeState.HELD)
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
        """Determine the final state of the plan after execution loop ends.

        - All required completed -> COMPLETED
        - Any node HELD (none FAILED/SKIPPED among required) -> SUSPENDED
        - Required nodes FAILED or SKIPPED -> FAILED
        - Otherwise (pending nodes, no running) -> SUSPENDED
        """
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
            # Check if any node is HELD — HELD nodes mean the plan
            # needs external resolution (SUSPENDED), not terminal failure
            held_nodes = [
                n for n in plan.nodes.values() if n.state == PlanNodeState.HELD
            ]
            # Check if any required node is in a failed/blocked terminal state
            failed_nodes = [
                n.node_id
                for n in required_nodes
                if n.state in (PlanNodeState.FAILED, PlanNodeState.SKIPPED)
            ]
            if held_nodes:
                # HELD nodes take precedence — plan is suspended awaiting resolution
                plan.state = PlanState.SUSPENDED
                events.append(PlanEvent.plan_suspended())
            elif failed_nodes:
                plan.state = PlanState.FAILED
                events.append(
                    PlanEvent.plan_failed(
                        failed_nodes=failed_nodes,
                        reason="Required nodes failed or were blocked",
                    )
                )
            else:
                # Some nodes still pending -- plan is suspended
                plan.state = PlanState.SUSPENDED
                events.append(PlanEvent.plan_suspended())

        return events


# ===================================================================
# AsyncPlanExecutor
# ===================================================================


class AsyncPlanExecutor:
    """Asynchronous DAG executor with PACT verification gradient.

    Executes a validated plan by scheduling nodes in topological order,
    running independent ready nodes concurrently via ``asyncio.gather()``,
    and applying gradient rules (G1-G8) for failure handling.

    Args:
        node_callback: Async function called to execute each node.
            Signature: async (node_id, agent_spec_id) -> result dict with keys:
            - output: Any (node output on success, None on failure)
            - error: str | None (error message on failure)
            - retryable: bool (whether the error is retryable)
            - envelope_violation: bool (optional, signals G8)
        event_callback: Optional async function called for each event
            as it is emitted, enabling real-time observation.
            Signature: async (PlanEvent) -> None
        max_concurrency: Optional maximum number of nodes to execute
            concurrently. If None, all ready nodes run in parallel.
    """

    def __init__(
        self,
        node_callback: AsyncNodeCallback,
        event_callback: EventCallback | None = None,
        max_concurrency: int | None = None,
    ) -> None:
        self._callback = node_callback
        self._event_callback = event_callback
        self._semaphore: asyncio.Semaphore | None = (
            asyncio.Semaphore(max_concurrency) if max_concurrency is not None else None
        )

    async def _emit(self, event: PlanEvent, events: list[PlanEvent]) -> None:
        """Append event to the list and dispatch to event_callback if set."""
        events.append(event)
        if self._event_callback is not None:
            await self._event_callback(event)

    async def _emit_many(
        self, new_events: list[PlanEvent], events: list[PlanEvent]
    ) -> None:
        """Append multiple events and dispatch each to event_callback."""
        for ev in new_events:
            await self._emit(ev, events)

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------

    async def execute(self, plan: Plan) -> list[PlanEvent]:
        """Execute the plan DAG asynchronously.

        Independent ready nodes are executed concurrently via
        ``asyncio.gather()``. Nodes with unsatisfied data dependencies
        wait until their predecessors complete.

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
            ready_nodes = self._find_ready_nodes(plan)

            if not ready_nodes:
                running = [
                    n for n in plan.nodes.values() if n.state == PlanNodeState.RUNNING
                ]
                if not running:
                    break
                break

            # Execute all ready nodes concurrently
            tasks = [
                self._execute_node_guarded(plan, node, gradient, events)
                for node in ready_nodes
            ]
            await asyncio.gather(*tasks)

        # Determine terminal state
        terminal_events = self._determine_terminal_state(plan)
        await self._emit_many(terminal_events, events)
        return events

    async def suspend(self, plan: Plan) -> list[PlanEvent]:
        """Suspend an executing plan.

        Precondition: plan.state must be EXECUTING.
        """
        if plan.state != PlanState.EXECUTING:
            raise ExecutionError(
                f"Can only suspend an Executing plan, got {plan.state.value}",
                details={"plan_id": plan.plan_id, "state": plan.state.value},
            )

        plan.state = PlanState.SUSPENDED
        events: list[PlanEvent] = []
        await self._emit(PlanEvent.plan_suspended(), events)
        return events

    async def resume(self, plan: Plan) -> list[PlanEvent]:
        """Resume a suspended plan.

        Precondition: plan.state must be SUSPENDED.
        """
        if plan.state != PlanState.SUSPENDED:
            raise ExecutionError(
                f"Can only resume a Suspended plan, got {plan.state.value}",
                details={"plan_id": plan.plan_id, "state": plan.state.value},
            )

        plan.state = PlanState.EXECUTING
        events: list[PlanEvent] = []
        await self._emit(PlanEvent.plan_resumed(), events)
        return events

    async def cancel(self, plan: Plan) -> list[PlanEvent]:
        """Cancel a plan (executing or suspended).

        Terminal states (Completed, Failed, Cancelled) raise error.
        """
        terminal_states = {
            PlanState.COMPLETED,
            PlanState.FAILED,
            PlanState.CANCELLED,
        }
        if plan.state in terminal_states:
            raise ExecutionError(
                f"Cannot cancel a plan in terminal state {plan.state.value}",
                details={"plan_id": plan.plan_id, "state": plan.state.value},
            )

        events: list[PlanEvent] = []

        for node in plan.nodes.values():
            if node.state in (
                PlanNodeState.PENDING,
                PlanNodeState.READY,
                PlanNodeState.RUNNING,
                PlanNodeState.HELD,
            ):
                if node.state == PlanNodeState.RUNNING:
                    node.state = PlanNodeState.FAILED
                node.state = PlanNodeState.SKIPPED
                node.error = "plan_cancelled"
                await self._emit(
                    PlanEvent.node_skipped(node.node_id, reason="plan_cancelled"),
                    events,
                )

        plan.state = PlanState.CANCELLED
        await self._emit(PlanEvent.plan_cancelled(), events)
        return events

    # -------------------------------------------------------------------
    # Internal methods
    # -------------------------------------------------------------------

    def _find_ready_nodes(self, plan: Plan) -> list[PlanNode]:
        """Find all nodes whose dependencies are satisfied."""
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
                # Advisory -- does not block.
                pass

        return True

    async def _execute_node_guarded(
        self,
        plan: Plan,
        node: PlanNode,
        gradient: dict[str, Any],
        events: list[PlanEvent],
    ) -> None:
        """Execute a node, optionally limited by semaphore."""
        if self._semaphore is not None:
            async with self._semaphore:
                await self._execute_node(plan, node, gradient, events)
        else:
            await self._execute_node(plan, node, gradient, events)

    async def _execute_node(
        self,
        plan: Plan,
        node: PlanNode,
        gradient: dict[str, Any],
        events: list[PlanEvent],
    ) -> None:
        """Execute a single node and apply gradient rules."""
        # Emit NodeReady
        await self._emit(PlanEvent.node_ready(node.node_id), events)

        # Transition to Running
        node.transition_to(PlanNodeState.RUNNING)
        instance_id = str(uuid.uuid4())
        node.instance_id = instance_id
        await self._emit(
            PlanEvent.node_started(node.node_id, instance_id=instance_id),
            events,
        )

        # Execute via async callback
        result = await self._callback(node.node_id, node.agent_spec_id)

        error = result.get("error")
        output = result.get("output")
        retryable = result.get("retryable", False)
        envelope_violation = result.get("envelope_violation", False)

        if error is None:
            # G1: Success -> AutoApproved
            node.transition_to(PlanNodeState.COMPLETED)
            node.output = output
            await self._emit(
                PlanEvent.node_completed(node.node_id, output=output), events
            )
        elif envelope_violation:
            # G8: Envelope violation -> ALWAYS Blocked
            node.transition_to(PlanNodeState.FAILED)
            node.error = error
            await self._emit(
                PlanEvent.node_blocked(
                    node.node_id, dimension="envelope", detail=error
                ),
                events,
            )
            cascade_events = self._cascade_block(plan, node.node_id)
            await self._emit_many(cascade_events, events)
        elif retryable:
            # G2/G3: Retryable failure
            await self._handle_retryable_failure(plan, node, error, gradient, events)
        else:
            # G4/G5: Non-retryable failure
            await self._handle_non_retryable_failure(
                plan, node, error, gradient, events
            )

    async def _handle_retryable_failure(
        self,
        plan: Plan,
        node: PlanNode,
        error: str,
        gradient: dict[str, Any],
        events: list[PlanEvent],
    ) -> None:
        """Handle a retryable failure: G2 (retry) or G3 (exhausted)."""
        retry_budget = int(gradient.get("retry_budget", 2))

        node.transition_to(PlanNodeState.FAILED)
        node.error = error
        await self._emit(
            PlanEvent.node_failed(node.node_id, error=error, retryable=True),
            events,
        )

        if node.retry_count < retry_budget:
            # G2: Retry within budget
            node.retry_count += 1
            await self._emit(
                PlanEvent.node_retrying(
                    node.node_id,
                    attempt=node.retry_count,
                    max_attempts=retry_budget,
                ),
                events,
            )
            # Re-execute (transition back to Running)
            node.transition_to(PlanNodeState.RUNNING)
            instance_id = str(uuid.uuid4())
            node.instance_id = instance_id
            await self._emit(
                PlanEvent.node_started(node.node_id, instance_id=instance_id),
                events,
            )

            result = await self._callback(node.node_id, node.agent_spec_id)
            retry_error = result.get("error")
            retry_output = result.get("output")
            retry_retryable = result.get("retryable", False)
            retry_envelope = result.get("envelope_violation", False)

            if retry_error is None:
                # Retry succeeded
                node.transition_to(PlanNodeState.COMPLETED)
                node.output = retry_output
                await self._emit(
                    PlanEvent.node_completed(node.node_id, output=retry_output),
                    events,
                )
            elif retry_envelope:
                node.transition_to(PlanNodeState.FAILED)
                node.error = retry_error
                await self._emit(
                    PlanEvent.node_blocked(
                        node.node_id,
                        dimension="envelope",
                        detail=retry_error or "",
                    ),
                    events,
                )
                cascade_events = self._cascade_block(plan, node.node_id)
                await self._emit_many(cascade_events, events)
            elif retry_retryable and node.retry_count < retry_budget:
                # Recurse for additional retries
                await self._handle_retryable_failure(
                    plan, node, retry_error or "", gradient, events
                )
            else:
                # G3 or non-retryable on retry: exhausted
                node.transition_to(PlanNodeState.FAILED)
                node.error = retry_error
                exhaustion_events = self._handle_exhaustion(plan, node, gradient)
                await self._emit_many(exhaustion_events, events)
        else:
            # G3: Retry budget exhausted
            exhaustion_events = self._handle_exhaustion(plan, node, gradient)
            await self._emit_many(exhaustion_events, events)

    def _handle_exhaustion(
        self,
        plan: Plan,
        node: PlanNode,
        gradient: dict[str, Any],
    ) -> list[PlanEvent]:
        """Handle retry budget exhaustion (G3).

        When gradient says "held", transition node to HELD state.
        When gradient says "blocked", leave in FAILED and cascade.
        """
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
            # Default: held — transition node from FAILED to HELD
            node.transition_to(PlanNodeState.HELD)
            events.append(
                PlanEvent.node_held(
                    node.node_id,
                    reason="Retry budget exhausted",
                    zone="HELD",
                )
            )

        return events

    async def _handle_non_retryable_failure(
        self,
        plan: Plan,
        node: PlanNode,
        error: str,
        gradient: dict[str, Any],
        events: list[PlanEvent],
    ) -> None:
        """Handle non-retryable failure: G4 (optional) or G5 (required).

        For G5 (required) and G4 with held zone: transition FAILED -> HELD.
        """
        node.transition_to(PlanNodeState.FAILED)
        node.error = error
        await self._emit(
            PlanEvent.node_failed(node.node_id, error=error, retryable=False),
            events,
        )

        if node.optional:
            # G4: Optional node failure
            optional_zone = gradient.get("optional_node_failure", "flagged")

            if optional_zone == "auto_approved":
                node.transition_to(PlanNodeState.SKIPPED)
                await self._emit(
                    PlanEvent.node_skipped(
                        node.node_id,
                        reason=f"Optional node failed: {error}",
                    ),
                    events,
                )
            elif optional_zone == "flagged":
                await self._emit(
                    PlanEvent.node_flagged(
                        node.node_id,
                        reason=f"Optional node failed: {error}",
                    ),
                    events,
                )
                node.transition_to(PlanNodeState.SKIPPED)
                await self._emit(
                    PlanEvent.node_skipped(
                        node.node_id,
                        reason=f"Optional node failed (flagged): {error}",
                    ),
                    events,
                )
            else:
                # Held — transition from FAILED to HELD
                node.transition_to(PlanNodeState.HELD)
                await self._emit(
                    PlanEvent.node_held(
                        node.node_id,
                        reason=f"Optional node failed: {error}",
                        zone="HELD",
                    ),
                    events,
                )
        else:
            # G5: Required node failure -> transition from FAILED to HELD
            node.transition_to(PlanNodeState.HELD)
            await self._emit(
                PlanEvent.node_held(
                    node.node_id,
                    reason=f"Required node failed (non-retryable): {error}",
                    zone="HELD",
                ),
                events,
            )

    def _cascade_block(self, plan: Plan, blocked_node_id: str) -> list[PlanEvent]:
        """Cascade block to downstream nodes via DATA_DEPENDENCY edges.

        Skips nodes reachable from the blocked node through DATA_DEPENDENCY.
        COMPLETION_DEPENDENCY edges do NOT cascade termination.
        """
        events: list[PlanEvent] = []

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
        """Determine the final state of the plan after execution loop ends.

        - All required completed -> COMPLETED
        - Any node HELD (none FAILED/SKIPPED among required) -> SUSPENDED
        - Required nodes FAILED or SKIPPED -> FAILED
        - Otherwise (pending nodes, no running) -> SUSPENDED
        """
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
            # Check if any node is HELD — HELD nodes mean the plan
            # needs external resolution (SUSPENDED), not terminal failure
            held_nodes = [
                n for n in plan.nodes.values() if n.state == PlanNodeState.HELD
            ]
            # Check if any required node is in a failed/blocked terminal state
            failed_nodes = [
                n.node_id
                for n in required_nodes
                if n.state in (PlanNodeState.FAILED, PlanNodeState.SKIPPED)
            ]
            if held_nodes:
                # HELD nodes take precedence — plan is suspended awaiting resolution
                plan.state = PlanState.SUSPENDED
                events.append(PlanEvent.plan_suspended())
            elif failed_nodes:
                plan.state = PlanState.FAILED
                events.append(
                    PlanEvent.plan_failed(
                        failed_nodes=failed_nodes,
                        reason="Required nodes failed or were blocked",
                    )
                )
            else:
                # Some nodes still pending -- plan is suspended
                plan.state = PlanState.SUSPENDED
                events.append(PlanEvent.plan_suspended())

        return events
