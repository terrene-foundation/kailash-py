"""
PlanComposer: Assembles a Plan DAG from subtasks and agent specifications.

Given the outputs of TaskDecomposer (subtasks with dependency indices) and
AgentDesigner (AgentSpec + SpawnDecision per subtask), the PlanComposer uses
an LLM to decide:
    - Which subtasks can run in parallel (no data dependencies)
    - What data flows between subtasks (input_mapping)
    - Edge types (DataDependency, CompletionDependency, CoStart)

The companion PlanValidator performs deterministic structural and envelope
checks (no LLM required) to promote the plan from Draft to Validated.

Both live in the orchestration layer (kaizen-agents) because plan composition
requires LLM judgment, while validation is deterministic.
"""

from __future__ import annotations

import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from kaizen_agents.llm import LLMClient
from kaizen_agents.orchestration.planner.decomposer import Subtask
from kaizen_agents.orchestration.planner.designer import SpawnDecision
from kaizen_agents.types import (
    AgentSpec,
    ConstraintEnvelope,
    EdgeType,
    Plan,
    PlanEdge,
    PlanNode,
    PlanNodeOutput,
    PlanState,
)


# ---------------------------------------------------------------------------
# Validation error type
# ---------------------------------------------------------------------------


@dataclass
class ValidationError:
    """A single validation error with a human-readable description.

    Attributes:
        code: Machine-readable error code (e.g., "CYCLE_DETECTED").
        message: Human-readable description of the problem.
        node_id: Optional node ID involved in the error.
    """

    code: str
    message: str
    node_id: str | None = None


# ---------------------------------------------------------------------------
# PlanValidator -- deterministic, no LLM
# ---------------------------------------------------------------------------


class PlanValidator:
    """Deterministic validator for Plan DAGs.

    Checks structural invariants (acyclicity, referential integrity,
    root/leaf existence) and envelope feasibility (budget summation,
    monotonic tightening) without any LLM calls.

    Invariants checked correspond to INV-PLAN-01 through INV-PLAN-08
    from the Plan DAG specification.
    """

    def validate_structure(self, plan: Plan) -> list[ValidationError]:
        """Check structural invariants on the plan DAG.

        Checks performed (spec references):
            - INV-PLAN-05: Non-empty (at least one node)
            - Unique node IDs (enforced by dict keys)
            - No self-edges
            - INV-PLAN-02: Referential integrity (edge endpoints exist)
            - INV-PLAN-02: Input mapping references exist
            - Input mapping consistency (backing edge exists)
            - INV-PLAN-01: Acyclicity (topological sort)
            - INV-PLAN-03: Root existence
            - INV-PLAN-04: Leaf existence

        Args:
            plan: The Plan to validate.

        Returns:
            A list of ValidationError objects. Empty list means the plan
            passes all structural checks.
        """
        errors: list[ValidationError] = []

        # INV-PLAN-05: Non-empty
        if not plan.nodes:
            errors.append(
                ValidationError(
                    code="EMPTY_PLAN",
                    message="Plan has no nodes. A valid plan requires at least one node.",
                )
            )
            return errors

        node_ids = set(plan.nodes.keys())

        # Self-edges
        for edge in plan.edges:
            if edge.from_node == edge.to_node:
                errors.append(
                    ValidationError(
                        code="SELF_EDGE",
                        message=f"Edge from '{edge.from_node}' to itself is not allowed.",
                        node_id=edge.from_node,
                    )
                )

        # INV-PLAN-02: Referential integrity -- edge endpoints
        for edge in plan.edges:
            if edge.from_node not in node_ids:
                errors.append(
                    ValidationError(
                        code="MISSING_EDGE_SOURCE",
                        message=(f"Edge references non-existent source node '{edge.from_node}'."),
                        node_id=edge.from_node,
                    )
                )
            if edge.to_node not in node_ids:
                errors.append(
                    ValidationError(
                        code="MISSING_EDGE_TARGET",
                        message=(f"Edge references non-existent target node '{edge.to_node}'."),
                        node_id=edge.to_node,
                    )
                )

        # INV-PLAN-02: Input mapping referential integrity
        for node_id, node in plan.nodes.items():
            for mapping_key, node_output in node.input_mapping.items():
                if node_output.source_node not in node_ids:
                    errors.append(
                        ValidationError(
                            code="MISSING_INPUT_SOURCE",
                            message=(
                                f"Node '{node_id}' input_mapping['{mapping_key}'] references "
                                f"non-existent source node '{node_output.source_node}'."
                            ),
                            node_id=node_id,
                        )
                    )

        # Input mapping consistency: backing edge must exist
        edge_set = {(e.from_node, e.to_node) for e in plan.edges}
        for node_id, node in plan.nodes.items():
            for mapping_key, node_output in node.input_mapping.items():
                if node_output.source_node in node_ids:
                    if (node_output.source_node, node_id) not in edge_set:
                        errors.append(
                            ValidationError(
                                code="INPUT_MAPPING_NO_EDGE",
                                message=(
                                    f"Node '{node_id}' input_mapping['{mapping_key}'] references "
                                    f"source '{node_output.source_node}' but no edge exists "
                                    f"from '{node_output.source_node}' to '{node_id}'."
                                ),
                                node_id=node_id,
                            )
                        )

        # INV-PLAN-01: Acyclicity via topological sort (Kahn's algorithm)
        # Only consider DataDependency and CompletionDependency edges for cycle detection
        # (CoStart edges are advisory and do not create ordering constraints)
        blocking_edges = [
            e
            for e in plan.edges
            if e.edge_type in (EdgeType.DATA_DEPENDENCY, EdgeType.COMPLETION_DEPENDENCY)
            and e.from_node in node_ids
            and e.to_node in node_ids
            and e.from_node != e.to_node
        ]

        in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
        adjacency: dict[str, list[str]] = {nid: [] for nid in node_ids}
        for edge in blocking_edges:
            in_degree[edge.to_node] += 1
            adjacency[edge.from_node].append(edge.to_node)

        queue: deque[str] = deque(nid for nid, deg in in_degree.items() if deg == 0)
        sorted_count = 0

        while queue:
            current = queue.popleft()
            sorted_count += 1
            for neighbour in adjacency[current]:
                in_degree[neighbour] -= 1
                if in_degree[neighbour] == 0:
                    queue.append(neighbour)

        if sorted_count != len(node_ids):
            remaining = [nid for nid, deg in in_degree.items() if deg > 0]
            errors.append(
                ValidationError(
                    code="CYCLE_DETECTED",
                    message=(
                        f"Plan contains a cycle involving node(s): "
                        f"{', '.join(sorted(remaining))}. "
                        "The plan must be a directed acyclic graph."
                    ),
                )
            )

        # INV-PLAN-03: Root existence (no incoming DataDependency/CompletionDependency)
        has_incoming: set[str] = set()
        for edge in plan.edges:
            if edge.edge_type in (EdgeType.DATA_DEPENDENCY, EdgeType.COMPLETION_DEPENDENCY):
                has_incoming.add(edge.to_node)

        root_nodes = node_ids - has_incoming
        if not root_nodes:
            errors.append(
                ValidationError(
                    code="NO_ROOT_NODE",
                    message=(
                        "Plan has no root node. At least one node must have no incoming "
                        "DataDependency or CompletionDependency edges."
                    ),
                )
            )

        # INV-PLAN-04: Leaf existence (no outgoing DataDependency/CompletionDependency)
        has_outgoing: set[str] = set()
        for edge in plan.edges:
            if edge.edge_type in (EdgeType.DATA_DEPENDENCY, EdgeType.COMPLETION_DEPENDENCY):
                has_outgoing.add(edge.from_node)

        leaf_nodes = node_ids - has_outgoing
        if not leaf_nodes:
            errors.append(
                ValidationError(
                    code="NO_LEAF_NODE",
                    message=(
                        "Plan has no leaf node. At least one node must have no outgoing "
                        "DataDependency or CompletionDependency edges."
                    ),
                )
            )

        return errors

    def validate_envelopes(self, plan: Plan) -> list[ValidationError]:
        """Check envelope feasibility invariants.

        Checks performed (spec references):
            - INV-PLAN-06: Budget summation (child budgets <= parent budget)
            - INV-PLAN-07: Monotonic tightening (per-dimension)

        Args:
            plan: The Plan to validate.

        Returns:
            A list of ValidationError objects. Empty list means envelope checks pass.
        """
        errors: list[ValidationError] = []

        if not plan.nodes:
            return errors

        parent_limit = (
            plan.envelope.financial.max_spend_usd if plan.envelope.financial else float("inf")
        )

        # INV-PLAN-06: Budget summation
        total_child_budget = 0.0
        for node_id, node in plan.nodes.items():
            child_limit = (
                node.agent_spec.envelope.financial.max_spend_usd
                if node.agent_spec.envelope.financial
                else 0.0
            )
            total_child_budget += child_limit

        if total_child_budget > parent_limit:
            errors.append(
                ValidationError(
                    code="BUDGET_OVERFLOW",
                    message=(
                        f"Sum of child budgets (${total_child_budget:.2f}) exceeds "
                        f"parent budget (${parent_limit:.2f}). "
                        "Child budget allocations must fit within the parent envelope."
                    ),
                )
            )

        # INV-PLAN-07: Monotonic tightening per node
        parent_blocked = set(plan.envelope.operational.blocked_actions)
        parent_allowed = plan.envelope.operational.allowed_actions

        for node_id, node in plan.nodes.items():
            child_env = node.agent_spec.envelope

            # Financial: child limit must not exceed parent limit
            child_limit = child_env.financial.max_spend_usd if child_env.financial else 0.0
            if child_limit > parent_limit:
                errors.append(
                    ValidationError(
                        code="FINANCIAL_EXCEEDS_PARENT",
                        message=(
                            f"Node '{node_id}' financial limit (${child_limit:.2f}) "
                            f"exceeds parent limit (${parent_limit:.2f})."
                        ),
                        node_id=node_id,
                    )
                )

            # Operational: child blocked must be superset of parent blocked
            child_blocked = set(child_env.operational.blocked_actions)
            missing_blocked = parent_blocked - child_blocked
            if missing_blocked:
                errors.append(
                    ValidationError(
                        code="BLOCKED_OPS_NOT_INHERITED",
                        message=(
                            f"Node '{node_id}' does not inherit parent's blocked operations: "
                            f"{', '.join(sorted(missing_blocked))}."
                        ),
                        node_id=node_id,
                    )
                )

            # Operational: child allowed must be subset of parent allowed (if parent restricts)
            if parent_allowed:
                child_allowed = set(child_env.operational.allowed_actions)
                excess_allowed = child_allowed - set(parent_allowed)
                if excess_allowed:
                    errors.append(
                        ValidationError(
                            code="ALLOWED_OPS_EXCEED_PARENT",
                            message=(
                                f"Node '{node_id}' has allowed operations not in parent: "
                                f"{', '.join(sorted(excess_allowed))}."
                            ),
                            node_id=node_id,
                        )
                    )

        return errors

    def validate(self, plan: Plan) -> list[ValidationError]:
        """Run all validators: structural + envelope.

        If no errors are found and the plan is in Draft state, transitions
        the plan to Validated state.

        Args:
            plan: The Plan to validate.

        Returns:
            A list of all ValidationError objects found. Empty list means
            the plan is fully valid.
        """
        errors: list[ValidationError] = []
        errors.extend(self.validate_structure(plan))
        errors.extend(self.validate_envelopes(plan))

        if not errors and plan.state == PlanState.DRAFT:
            plan.state = PlanState.VALIDATED

        return errors


# ---------------------------------------------------------------------------
# LLM schema for plan composition
# ---------------------------------------------------------------------------


COMPOSITION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "from_index": {
                        "type": "integer",
                        "description": "Zero-based index of the source subtask.",
                    },
                    "to_index": {
                        "type": "integer",
                        "description": "Zero-based index of the target subtask.",
                    },
                    "edge_type": {
                        "type": "string",
                        "enum": ["data_dependency", "completion_dependency", "co_start"],
                        "description": (
                            "Type of dependency: data_dependency (output needed), "
                            "completion_dependency (must finish first), "
                            "co_start (should start together)."
                        ),
                    },
                },
                "required": ["from_index", "to_index", "edge_type"],
                "additionalProperties": False,
            },
        },
        "input_mappings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "target_index": {
                        "type": "integer",
                        "description": "Zero-based index of the subtask receiving input.",
                    },
                    "input_key": {
                        "type": "string",
                        "description": "The key name for this input in the target node.",
                    },
                    "source_index": {
                        "type": "integer",
                        "description": "Zero-based index of the subtask providing output.",
                    },
                    "output_key": {
                        "type": "string",
                        "description": "The key name from the source node's output.",
                    },
                },
                "required": ["target_index", "input_key", "source_index", "output_key"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["edges", "input_mappings"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# PlanComposer -- LLM-driven DAG assembly
# ---------------------------------------------------------------------------


def _build_composer_system_prompt() -> str:
    """Build the system prompt for plan composition."""
    return """You are a plan composition engine for a PACT-governed autonomous agent system.

Given a list of subtasks (with their dependencies, output keys, and assigned agents),
your job is to produce:
1. A list of edges defining the execution DAG.
2. Input mappings that wire output keys from upstream subtasks to downstream inputs.

## Edge Types

- **data_dependency**: The target subtask needs data from the source's output.
  Use this when a subtask's output_keys are consumed by a downstream subtask.
- **completion_dependency**: The target just needs the source to finish first
  (regardless of success/failure). Use for cleanup or summary nodes.
- **co_start**: The target should start at the same time as the source.
  Use for subtasks that can run concurrently but benefit from coordination.

## Rules

1. Respect the declared depends_on relationships from the decomposition.
   Every depends_on reference MUST appear as an edge.
2. Subtasks with no depends_on entries and no data dependencies between them
   CAN run in parallel -- do NOT add unnecessary edges between them.
3. For each data dependency edge, provide input_mappings wiring the source's
   output_keys to the target's inputs.
4. Do NOT create cycles. The graph must be a DAG.
5. Do NOT create self-edges (from_index == to_index).
6. Every subtask that has depends_on entries should have at least one incoming edge.
7. Prefer data_dependency when output data is actually consumed.
   Use completion_dependency only when ordering matters but no data flows."""


def _build_composer_user_prompt(
    subtasks: list[Subtask],
    specs: list[tuple[AgentSpec, SpawnDecision]],
) -> str:
    """Build the user prompt describing the subtasks and their agents."""
    lines = ["## Subtasks\n"]

    for idx, subtask in enumerate(subtasks):
        spec, decision = specs[idx]
        lines.append(f"### Subtask {idx}: {subtask.description}")
        lines.append(f"  Agent: {spec.name}")
        lines.append(f"  Complexity: {subtask.estimated_complexity}/5")
        lines.append(f"  Spawn decision: {decision.decision}")
        lines.append(f"  Depends on: {subtask.depends_on or '(none)'}")
        lines.append(f"  Output keys: {subtask.output_keys or '(none)'}")
        lines.append(
            f"  Required capabilities: " f"{', '.join(subtask.required_capabilities) or '(none)'}"
        )
        lines.append("")

    lines.append(
        "Produce edges and input_mappings for this set of subtasks. "
        "Respect the depends_on relationships. Identify which subtasks "
        "can run in parallel and which need data from upstream."
    )

    return "\n".join(lines)


class PlanComposer:
    """Assembles a Plan DAG from subtasks and agent specifications using an LLM.

    Combines LLM-driven dependency analysis with deterministic validation
    to produce a fully wired Plan ready for execution.

    The composition pipeline:
        1. Build prompts describing subtasks and their agents.
        2. Use the LLM to decide edges and input mappings.
        3. Construct PlanNode and PlanEdge objects.
        4. Validate the result using PlanValidator.
        5. Return the Plan in Draft state (call PlanValidator.validate()
           to promote to Validated).

    Usage:
        composer = PlanComposer(llm_client=my_client)
        plan = composer.compose(
            subtasks=decomposed_subtasks,
            specs=[(spec1, decision1), (spec2, decision2), ...],
            parent_envelope=my_envelope,
        )
        # plan.state == PlanState.DRAFT
        errors = PlanValidator().validate(plan)
        # if no errors: plan.state == PlanState.VALIDATED
    """

    def __init__(
        self,
        llm_client: LLMClient,
        validator: PlanValidator | None = None,
    ) -> None:
        """Initialise the composer.

        Args:
            llm_client: LLM client for deciding edge types and input mappings.
            validator: Optional PlanValidator. If not provided, a default is created.
        """
        self._llm = llm_client
        self._validator = validator or PlanValidator()

    @property
    def validator(self) -> PlanValidator:
        """The PlanValidator used by this composer."""
        return self._validator

    def compose(
        self,
        subtasks: list[Subtask],
        specs: list[tuple[AgentSpec, SpawnDecision]],
        parent_envelope: ConstraintEnvelope,
        plan_name: str = "",
    ) -> Plan:
        """Compose a Plan DAG from subtasks and agent specifications.

        Args:
            subtasks: Ordered list of subtasks from TaskDecomposer.
            specs: List of (AgentSpec, SpawnDecision) tuples from AgentDesigner,
                one per subtask (same ordering).
            parent_envelope: The parent's constraint envelope bounding the plan.
            plan_name: Optional human-readable name for the plan.

        Returns:
            A Plan in Draft state with all nodes, edges, and input mappings wired.

        Raises:
            ValueError: If subtasks and specs have different lengths,
                or if the LLM returns an unparseable response.
        """
        if len(subtasks) != len(specs):
            raise ValueError(
                f"Mismatch: {len(subtasks)} subtasks but {len(specs)} specs. "
                "Each subtask must have exactly one (AgentSpec, SpawnDecision) pair."
            )

        if not subtasks:
            raise ValueError("Cannot compose a plan with zero subtasks.")

        # Step 1: Ask the LLM for edges and input mappings
        raw_composition = self._query_llm(subtasks, specs)

        # Step 2: Build the Plan from the LLM response
        plan = self._build_plan(
            subtasks=subtasks,
            specs=specs,
            raw_composition=raw_composition,
            parent_envelope=parent_envelope,
            plan_name=plan_name,
        )

        return plan

    def compose_and_validate(
        self,
        subtasks: list[Subtask],
        specs: list[tuple[AgentSpec, SpawnDecision]],
        parent_envelope: ConstraintEnvelope,
        plan_name: str = "",
    ) -> tuple[Plan, list[ValidationError]]:
        """Compose a plan and run validation in one call.

        Convenience method that composes the plan and immediately validates it.
        If validation passes, the plan is promoted to Validated state.

        Args:
            subtasks: Ordered list of subtasks from TaskDecomposer.
            specs: List of (AgentSpec, SpawnDecision) tuples from AgentDesigner.
            parent_envelope: The parent's constraint envelope.
            plan_name: Optional human-readable name for the plan.

        Returns:
            A tuple of (Plan, list[ValidationError]). If the error list is empty,
            the plan is in Validated state.
        """
        plan = self.compose(subtasks, specs, parent_envelope, plan_name)
        errors = self._validator.validate(plan)
        return plan, errors

    def _query_llm(
        self,
        subtasks: list[Subtask],
        specs: list[tuple[AgentSpec, SpawnDecision]],
    ) -> dict[str, Any]:
        """Query the LLM for edge and input mapping decisions.

        Args:
            subtasks: The subtasks to compose.
            specs: Agent specs paired with spawn decisions.

        Returns:
            Parsed JSON dict with "edges" and "input_mappings" arrays.
        """
        system_prompt = _build_composer_system_prompt()
        user_prompt = _build_composer_user_prompt(subtasks, specs)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        return self._llm.complete_structured(
            messages=messages,
            schema=COMPOSITION_SCHEMA,
            schema_name="plan_composition",
        )

    def _build_plan(
        self,
        subtasks: list[Subtask],
        specs: list[tuple[AgentSpec, SpawnDecision]],
        raw_composition: dict[str, Any],
        parent_envelope: ConstraintEnvelope,
        plan_name: str,
    ) -> Plan:
        """Build a Plan object from parsed LLM output.

        Args:
            subtasks: The original subtasks.
            specs: Agent specs paired with spawn decisions.
            raw_composition: The LLM's structured output with edges and input_mappings.
            parent_envelope: The parent envelope for the plan.
            plan_name: Human-readable plan name.

        Returns:
            A Plan in Draft state.
        """
        num_subtasks = len(subtasks)

        # Generate node IDs from subtask indices
        node_ids = [f"node-{i}" for i in range(num_subtasks)]

        # Build nodes
        nodes: dict[str, PlanNode] = {}
        for idx, subtask in enumerate(subtasks):
            spec, _ = specs[idx]
            nodes[node_ids[idx]] = PlanNode(
                node_id=node_ids[idx],
                agent_spec=spec,
                input_mapping={},
            )

        # Parse and build edges
        edges: list[PlanEdge] = []
        seen_edges: set[tuple[str, str]] = set()
        raw_edges = raw_composition.get("edges", [])

        for raw_edge in raw_edges:
            from_idx = raw_edge.get("from_index")
            to_idx = raw_edge.get("to_index")
            edge_type_str = raw_edge.get("edge_type", "data_dependency")

            # Validate indices
            if not isinstance(from_idx, int) or not isinstance(to_idx, int):
                continue
            if from_idx < 0 or from_idx >= num_subtasks:
                continue
            if to_idx < 0 or to_idx >= num_subtasks:
                continue
            if from_idx == to_idx:
                continue

            edge_key = (node_ids[from_idx], node_ids[to_idx])
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)

            edge_type = _parse_edge_type(edge_type_str)
            edges.append(
                PlanEdge(
                    from_node=node_ids[from_idx],
                    to_node=node_ids[to_idx],
                    edge_type=edge_type,
                )
            )

        # Ensure declared dependencies from subtasks are represented as edges
        for idx, subtask in enumerate(subtasks):
            for dep_idx in subtask.depends_on:
                if 0 <= dep_idx < num_subtasks and dep_idx != idx:
                    edge_key = (node_ids[dep_idx], node_ids[idx])
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        edges.append(
                            PlanEdge(
                                from_node=node_ids[dep_idx],
                                to_node=node_ids[idx],
                                edge_type=EdgeType.DATA_DEPENDENCY,
                            )
                        )

        # Parse and apply input mappings
        raw_mappings = raw_composition.get("input_mappings", [])
        for mapping in raw_mappings:
            target_idx = mapping.get("target_index")
            input_key = mapping.get("input_key", "")
            source_idx = mapping.get("source_index")
            output_key = mapping.get("output_key", "")

            if not isinstance(target_idx, int) or not isinstance(source_idx, int):
                continue
            if target_idx < 0 or target_idx >= num_subtasks:
                continue
            if source_idx < 0 or source_idx >= num_subtasks:
                continue
            if source_idx == target_idx:
                continue
            if not input_key or not output_key:
                continue

            target_node_id = node_ids[target_idx]
            source_node_id = node_ids[source_idx]

            nodes[target_node_id].input_mapping[input_key] = PlanNodeOutput(
                source_node=source_node_id,
                output_key=output_key,
            )

        plan = Plan(
            plan_id=str(uuid.uuid4()),
            name=plan_name or "composed-plan",
            envelope=parent_envelope,
            nodes=nodes,
            edges=edges,
            state=PlanState.DRAFT,
        )

        return plan


def _parse_edge_type(edge_type_str: str) -> EdgeType:
    """Parse an edge type string into an EdgeType enum.

    Args:
        edge_type_str: One of "data_dependency", "completion_dependency", "co_start".

    Returns:
        The corresponding EdgeType enum value.
        Defaults to DATA_DEPENDENCY for unrecognised strings.
    """
    mapping = {
        "data_dependency": EdgeType.DATA_DEPENDENCY,
        "completion_dependency": EdgeType.COMPLETION_DEPENDENCY,
        "co_start": EdgeType.CO_START,
    }
    return mapping.get(edge_type_str, EdgeType.DATA_DEPENDENCY)
