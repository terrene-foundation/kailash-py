"""
Recomposer: Generates PlanModification objects to recover from node failures.

Given a Plan, a failed node, and a FailureDiagnosis (from FailureDiagnoser),
the Recomposer uses LLM judgment to select a recovery strategy and produce
the concrete PlanModification(s) needed to resume execution.

The Recomposer is part of the orchestration layer (kaizen-agents) because
strategy selection requires LLM judgment. The modifications it produces are
validated by the SDK's PlanExecutor (deterministic) before application.

See: specs/05-plan-dag.md (PlanModification semantics, Section 4)
See: 01-analysis/01-research/08-planexecutor-boundary-resolution.md
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from kaizen_agents.llm import LLMClient
from kaizen_agents.orchestration.recovery.diagnoser import FailureCategory, FailureDiagnosis
from kaizen_agents.types import (
    AgentSpec,
    ConstraintEnvelope,
    EdgeType,
    MemoryConfig,
    Plan,
    PlanEdge,
    PlanModification,
    PlanNode,
    PlanNodeState,
)


class RecoveryStrategy(Enum):
    """High-level recovery strategy selected by the Recomposer.

    Each strategy maps to a different set of PlanModification objects.
    """

    RETRY = "retry"
    """No modification needed. PlanExecutor handles retry via the gradient.
    Selected when the diagnosis says transient failure and retries remain."""

    REPLACE = "replace"
    """ReplaceNode with a new AgentSpec using different tools, model, or approach."""

    SKIP = "skip"
    """SkipNode if the node is optional and its output is not critical."""

    RESTRUCTURE = "restructure"
    """AddNode + AddEdge to create an alternative path around the failure."""

    ABORT = "abort"
    """No modifications. Signal that the plan branch should be terminated."""


@dataclass
class RecoveryPlan:
    """The output of the Recomposer: a strategy and its concrete modifications.

    Attributes:
        strategy: The high-level recovery strategy selected.
        modifications: Concrete PlanModification objects to apply.
            Empty for RETRY (executor handles) and ABORT (no recovery).
        rationale: LLM-generated explanation of why this strategy was chosen.
        failed_node_id: The node this recovery plan addresses.
    """

    strategy: RecoveryStrategy
    modifications: list[PlanModification] = field(default_factory=list)
    rationale: str = ""
    failed_node_id: str = ""


# JSON schema for the LLM structured output
RECOVERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "strategy": {
            "type": "string",
            "enum": ["retry", "replace", "skip", "restructure", "abort"],
            "description": (
                "Recovery strategy: retry (let executor retry), replace (swap agent spec), "
                "skip (mark optional node as skipped), restructure (add alternative path), "
                "abort (terminate this plan branch)."
            ),
        },
        "rationale": {
            "type": "string",
            "description": "Explanation of why this strategy was chosen.",
        },
        "replacement_spec": {
            "type": ["object", "null"],
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "capabilities": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "tool_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["name", "description", "capabilities", "tool_ids"],
            "additionalProperties": False,
            "description": ("New agent spec for REPLACE strategy. null for other strategies."),
        },
        "alternative_nodes": {
            "type": ["array", "null"],
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "capabilities": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "tool_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "connect_from": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": "Node IDs that should feed into this new node.",
                    },
                    "connect_to": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": "Node IDs this new node should feed into.",
                    },
                },
                "required": [
                    "name",
                    "description",
                    "capabilities",
                    "tool_ids",
                    "connect_from",
                    "connect_to",
                ],
                "additionalProperties": False,
            },
            "description": ("New nodes for RESTRUCTURE strategy. null for other strategies."),
        },
        "skip_reason": {
            "type": ["string", "null"],
            "description": "Reason for skipping, used with SKIP strategy. null otherwise.",
        },
    },
    "required": [
        "strategy",
        "rationale",
        "replacement_spec",
        "alternative_nodes",
        "skip_reason",
    ],
    "additionalProperties": False,
}


def _build_recovery_system_prompt() -> str:
    """Build the system prompt for the recomposer."""
    return """You are a plan recovery engine for an autonomous agent orchestration system.

A node in a plan DAG has failed and been diagnosed. Your job is to select the
best recovery strategy and provide the details needed to implement it.

## Recovery Strategies

- **retry**: The failure is transient and the executor's retry mechanism will handle it.
  Select this ONLY if the diagnosis category is 'transient' and retries remain.
  No modification is needed -- the executor handles retries via the verification gradient.

- **replace**: Replace the failed node with a new agent that has different tools,
  capabilities, or approach. Select this when the diagnosis category is 'configuration'
  or 'permanent' and a different agent setup could succeed.
  You must provide replacement_spec with the new agent's details.

- **skip**: Mark the node as skipped. Select this ONLY when the node is optional
  and its output is not critical to downstream nodes.
  You must provide skip_reason.

- **restructure**: Add new nodes and edges to create an alternative execution path.
  Select this when the original approach failed but an alternative multi-step
  approach could succeed (e.g., adding a data-validation node before retrying,
  or splitting a complex task into simpler subtasks).
  You must provide alternative_nodes.

- **abort**: No recovery is possible. The plan branch should be terminated.
  Select this when the failure is permanent and unrecoverable, the node is
  required, and no alternative approach exists.

## Rules

1. Prefer least-disruptive strategies: retry > replace > skip > restructure > abort.
2. Never select 'skip' for a required (non-optional) node.
3. Never select 'retry' if the diagnosis says the failure is permanent or configuration-based.
4. For 'replace', the new agent must have DIFFERENT capabilities or tools than the original.
5. For 'restructure', new nodes must connect properly to the existing DAG.
6. For 'abort', provide a clear rationale explaining why no recovery is possible.
7. Set replacement_spec to null unless strategy is 'replace'.
8. Set alternative_nodes to null unless strategy is 'restructure'.
9. Set skip_reason to null unless strategy is 'skip'."""


def _build_recovery_user_prompt(
    plan: Plan,
    failed_node: PlanNode,
    diagnosis: FailureDiagnosis,
) -> str:
    """Build the user prompt with the failure context and diagnosis."""
    downstream_info = []
    for edge in plan.edges:
        if edge.from_node == failed_node.node_id:
            downstream_node = plan.nodes.get(edge.to_node)
            if downstream_node:
                downstream_info.append(
                    f"  - {edge.to_node}: {downstream_node.agent_spec.description} "
                    f"(optional={downstream_node.optional})"
                )

    downstream_section = ""
    if downstream_info:
        downstream_section = "\n## Downstream Nodes (affected by this failure)\n\n" + "\n".join(
            downstream_info
        )

    # Summarize the plan structure
    completed_nodes = [nid for nid, n in plan.nodes.items() if n.state == PlanNodeState.COMPLETED]
    pending_nodes = [
        nid
        for nid, n in plan.nodes.items()
        if n.state in (PlanNodeState.PENDING, PlanNodeState.READY)
    ]

    actions_str = "\n".join(f"  {i + 1}. {a}" for i, a in enumerate(diagnosis.suggested_actions))

    tools_str = (
        ", ".join(failed_node.agent_spec.tool_ids) if failed_node.agent_spec.tool_ids else "(none)"
    )
    caps_str = (
        ", ".join(failed_node.agent_spec.capabilities)
        if failed_node.agent_spec.capabilities
        else "(none)"
    )

    return f"""## Failed Node

- **Node ID**: {failed_node.node_id}
- **Purpose**: {failed_node.agent_spec.description}
- **Capabilities**: {caps_str}
- **Tools**: {tools_str}
- **Optional**: {failed_node.optional}
- **Retry count**: {failed_node.retry_count} / {plan.gradient.retry_budget}

## Diagnosis

- **Root cause**: {diagnosis.root_cause}
- **Category**: {diagnosis.category.value}
- **Recoverable**: {diagnosis.recoverable}
- **Confidence**: {diagnosis.confidence}
- **Suggested actions**:
{actions_str}

## Original Error

{diagnosis.raw_error}
{downstream_section}

## Plan Status

- **Completed nodes**: {', '.join(completed_nodes) if completed_nodes else '(none)'}
- **Pending/ready nodes**: {', '.join(pending_nodes) if pending_nodes else '(none)'}
- **Total nodes**: {len(plan.nodes)}

Select a recovery strategy and provide the necessary details."""


def _collect_descendants(plan: Plan, node_id: str) -> set[str]:
    """Collect all node IDs reachable downstream from node_id via any edge type."""
    descendants: set[str] = set()
    queue = [node_id]
    while queue:
        current = queue.pop()
        for edge in plan.edges:
            if edge.from_node == current and edge.to_node not in descendants:
                descendants.add(edge.to_node)
                queue.append(edge.to_node)
    return descendants


def _collect_ancestors(plan: Plan, node_id: str) -> set[str]:
    """Collect all node IDs reachable upstream from node_id via any edge type."""
    ancestors: set[str] = set()
    queue = [node_id]
    while queue:
        current = queue.pop()
        for edge in plan.edges:
            if edge.to_node == current and edge.from_node not in ancestors:
                ancestors.add(edge.from_node)
                queue.append(edge.from_node)
    return ancestors


def _would_create_cycle(plan: Plan, from_node: str, to_node: str) -> bool:
    """Check whether adding an edge from_node -> to_node would create a cycle.

    A cycle exists if to_node can already reach from_node via existing edges
    (meaning from_node is a descendant of to_node).
    """
    # If to_node can reach from_node, adding from_node -> to_node creates a cycle
    descendants_of_to = _collect_descendants(plan, to_node)
    return from_node in descendants_of_to


class Recomposer:
    """Generates PlanModification objects to recover from diagnosed node failures.

    The Recomposer sits after FailureDiagnoser in the recovery pipeline:
    PlanExecutor (NodeHeld) -> FailureDiagnoser (diagnosis) -> Recomposer (modifications).

    The modifications it produces are submitted back to PlanExecutor for
    deterministic validation against DAG invariants and envelope constraints.

    Usage:
        recomposer = Recomposer(llm_client=my_client)
        recovery = recomposer.recompose(
            plan=my_plan,
            failed_node_id="research-node",
            diagnosis=my_diagnosis,
        )
        for mod in recovery.modifications:
            plan_executor.apply_modification(plan, mod)
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """Initialise the recomposer with an LLM client.

        Args:
            llm_client: A configured LLMClient instance for making completions.
        """
        self._llm = llm_client

    def recompose(
        self,
        plan: Plan,
        failed_node_id: str,
        diagnosis: FailureDiagnosis,
    ) -> RecoveryPlan:
        """Generate a recovery plan for a diagnosed failure.

        Args:
            plan: The plan containing the failed node.
            failed_node_id: The ID of the failed node.
            diagnosis: The structured diagnosis from FailureDiagnoser.

        Returns:
            A RecoveryPlan with the selected strategy and concrete modifications.

        Raises:
            KeyError: If failed_node_id is not found in the plan.
            ValueError: If the LLM returns an unparseable response or the
                produced modifications would violate DAG invariants.
        """
        failed_node = plan.nodes[failed_node_id]

        system_prompt = _build_recovery_system_prompt()
        user_prompt = _build_recovery_user_prompt(plan, failed_node, diagnosis)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw_result = self._llm.complete_structured(
            messages=messages,
            schema=RECOVERY_SCHEMA,
            schema_name="recovery_plan",
        )

        recovery = self._parse_recovery(plan, failed_node, diagnosis, raw_result)
        self._validate_modifications(plan, recovery)
        return recovery

    def _parse_recovery(
        self,
        plan: Plan,
        failed_node: PlanNode,
        diagnosis: FailureDiagnosis,
        raw: dict[str, Any],
    ) -> RecoveryPlan:
        """Parse the LLM response into a RecoveryPlan with concrete modifications.

        Args:
            plan: The plan for context.
            failed_node: The failed PlanNode.
            diagnosis: The failure diagnosis for context.
            raw: The parsed JSON dict from the LLM.

        Returns:
            A RecoveryPlan with strategy and modifications.

        Raises:
            ValueError: If the response structure is invalid.
        """
        strategy_str = raw.get("strategy", "")
        try:
            strategy = RecoveryStrategy(strategy_str)
        except ValueError:
            raise ValueError(
                f"Invalid recovery strategy '{strategy_str}'. "
                f"Must be one of: {[s.value for s in RecoveryStrategy]}"
            )

        rationale = raw.get("rationale", "")
        if not rationale or not isinstance(rationale, str):
            raise ValueError(f"Recovery plan missing or empty 'rationale': {rationale!r}")

        modifications: list[PlanModification] = []

        if strategy == RecoveryStrategy.RETRY:
            # No modifications needed; PlanExecutor handles retry via gradient
            pass

        elif strategy == RecoveryStrategy.REPLACE:
            modifications = self._build_replace_modifications(
                plan, failed_node, raw.get("replacement_spec")
            )

        elif strategy == RecoveryStrategy.SKIP:
            skip_reason = raw.get("skip_reason") or rationale
            modifications = [PlanModification.skip_node(failed_node.node_id, skip_reason)]

        elif strategy == RecoveryStrategy.RESTRUCTURE:
            modifications = self._build_restructure_modifications(
                plan, failed_node, raw.get("alternative_nodes")
            )

        elif strategy == RecoveryStrategy.ABORT:
            # No modifications; the caller interprets ABORT as plan branch termination
            pass

        return RecoveryPlan(
            strategy=strategy,
            modifications=modifications,
            rationale=rationale,
            failed_node_id=failed_node.node_id,
        )

    def _build_replace_modifications(
        self,
        plan: Plan,
        failed_node: PlanNode,
        replacement_spec_raw: dict[str, Any] | None,
    ) -> list[PlanModification]:
        """Build a ReplaceNode modification from the LLM's replacement spec.

        Args:
            plan: The plan for envelope context.
            failed_node: The node being replaced.
            replacement_spec_raw: The LLM-provided spec dict.

        Returns:
            A list containing a single ReplaceNode modification.

        Raises:
            ValueError: If replacement_spec is missing or invalid.
        """
        if not replacement_spec_raw or not isinstance(replacement_spec_raw, dict):
            raise ValueError("REPLACE strategy requires a non-null 'replacement_spec' object")

        name = replacement_spec_raw.get("name", "")
        description = replacement_spec_raw.get("description", "")
        if not name or not description:
            raise ValueError("replacement_spec must include non-empty 'name' and 'description'")

        capabilities = replacement_spec_raw.get("capabilities", [])
        if not isinstance(capabilities, list):
            capabilities = []
        capabilities = [str(c) for c in capabilities if c]

        tool_ids = replacement_spec_raw.get("tool_ids", [])
        if not isinstance(tool_ids, list):
            tool_ids = []
        tool_ids = [str(t) for t in tool_ids if t]

        new_node_id = f"{failed_node.node_id}-replacement-{uuid.uuid4().hex[:8]}"

        new_spec = AgentSpec(
            spec_id=f"spec-{new_node_id}",
            name=name,
            description=description,
            capabilities=capabilities,
            tool_ids=tool_ids,
            envelope=failed_node.agent_spec.envelope,
            memory_config=failed_node.agent_spec.memory_config,
            max_lifetime=failed_node.agent_spec.max_lifetime,
            required_context_keys=failed_node.agent_spec.required_context_keys,
            produced_context_keys=failed_node.agent_spec.produced_context_keys,
        )

        new_node = PlanNode(
            node_id=new_node_id,
            agent_spec=new_spec,
            input_mapping=failed_node.input_mapping,
            optional=failed_node.optional,
        )

        return [PlanModification.replace_node(failed_node.node_id, new_node)]

    def _build_restructure_modifications(
        self,
        plan: Plan,
        failed_node: PlanNode,
        alternative_nodes_raw: list[dict[str, Any]] | None,
    ) -> list[PlanModification]:
        """Build AddNode + AddEdge modifications for the RESTRUCTURE strategy.

        Creates new nodes as an alternative execution path, skips the failed
        node, and wires the new nodes into the existing DAG.

        Args:
            plan: The plan to restructure.
            failed_node: The node being replaced by an alternative path.
            alternative_nodes_raw: The LLM-provided list of new node specs.

        Returns:
            A list of PlanModification objects (SkipNode + AddNode + AddEdge).

        Raises:
            ValueError: If alternative_nodes is missing, empty, or invalid.
        """
        if alternative_nodes_raw is None or not isinstance(alternative_nodes_raw, list):
            raise ValueError("RESTRUCTURE strategy requires a non-null 'alternative_nodes' list")

        if len(alternative_nodes_raw) == 0:
            raise ValueError("RESTRUCTURE strategy requires at least one alternative node")

        modifications: list[PlanModification] = []

        # Skip the failed node first
        modifications.append(
            PlanModification.skip_node(
                failed_node.node_id,
                f"Restructured: replaced by alternative path",
            )
        )

        # Track created node IDs for edge validation
        created_node_ids: set[str] = set()
        existing_node_ids = set(plan.nodes.keys())

        for idx, node_raw in enumerate(alternative_nodes_raw):
            if not isinstance(node_raw, dict):
                raise ValueError(f"Alternative node at index {idx} is not a dict")

            name = node_raw.get("name", "")
            description = node_raw.get("description", "")
            if not name or not description:
                raise ValueError(
                    f"Alternative node at index {idx} must include non-empty 'name' and 'description'"
                )

            capabilities = node_raw.get("capabilities", [])
            if not isinstance(capabilities, list):
                capabilities = []
            capabilities = [str(c) for c in capabilities if c]

            tool_ids = node_raw.get("tool_ids", [])
            if not isinstance(tool_ids, list):
                tool_ids = []
            tool_ids = [str(t) for t in tool_ids if t]

            node_id = f"alt-{failed_node.node_id}-{idx}-{uuid.uuid4().hex[:8]}"

            new_spec = AgentSpec(
                spec_id=f"spec-{node_id}",
                name=name,
                description=description,
                capabilities=capabilities,
                tool_ids=tool_ids,
                envelope=failed_node.agent_spec.envelope,
                memory_config=MemoryConfig(),
            )

            # Build edges for this new node
            edges: list[PlanEdge] = []

            connect_from = node_raw.get("connect_from") or []
            if not isinstance(connect_from, list):
                connect_from = []
            for source_id in connect_from:
                source_id = str(source_id)
                if source_id in existing_node_ids or source_id in created_node_ids:
                    edges.append(
                        PlanEdge(
                            from_node=source_id,
                            to_node=node_id,
                            edge_type=EdgeType.DATA_DEPENDENCY,
                        )
                    )

            connect_to = node_raw.get("connect_to") or []
            if not isinstance(connect_to, list):
                connect_to = []
            for target_id in connect_to:
                target_id = str(target_id)
                if target_id in existing_node_ids or target_id in created_node_ids:
                    edges.append(
                        PlanEdge(
                            from_node=node_id,
                            to_node=target_id,
                            edge_type=EdgeType.DATA_DEPENDENCY,
                        )
                    )

            new_node = PlanNode(
                node_id=node_id,
                agent_spec=new_spec,
                optional=failed_node.optional,
            )

            modifications.append(PlanModification.add_node(new_node, edges))
            created_node_ids.add(node_id)

        return modifications

    def _validate_modifications(
        self,
        plan: Plan,
        recovery: RecoveryPlan,
    ) -> None:
        """Validate that produced modifications preserve DAG invariants.

        Performs lightweight client-side validation before submitting to the
        SDK's PlanExecutor (which does authoritative validation). This catches
        obvious problems early and provides better error messages.

        Args:
            plan: The current plan state.
            recovery: The recovery plan with modifications to validate.

        Raises:
            ValueError: If any modification would violate a DAG invariant.
        """
        if not recovery.modifications:
            return

        # Build a working copy of node IDs to track additions/removals
        active_node_ids = set(plan.nodes.keys())

        for mod in recovery.modifications:
            if mod.modification_type.value == "add_node" and mod.node:
                if mod.node.node_id in active_node_ids:
                    raise ValueError(f"AddNode would create duplicate node ID: {mod.node.node_id}")
                active_node_ids.add(mod.node.node_id)

                # Check edges reference valid nodes
                if mod.edges:
                    for edge in mod.edges:
                        if edge.from_node not in active_node_ids:
                            raise ValueError(
                                f"AddNode edge references non-existent from_node: "
                                f"{edge.from_node}"
                            )
                        if edge.to_node not in active_node_ids:
                            raise ValueError(
                                f"AddNode edge references non-existent to_node: " f"{edge.to_node}"
                            )
                        if edge.from_node == edge.to_node:
                            raise ValueError(f"AddNode edge is a self-loop: {edge.from_node}")

            elif mod.modification_type.value == "remove_node" and mod.node_id:
                if mod.node_id not in active_node_ids:
                    raise ValueError(f"RemoveNode references non-existent node: {mod.node_id}")
                active_node_ids.discard(mod.node_id)

            elif mod.modification_type.value == "replace_node":
                if mod.old_node_id and mod.old_node_id not in active_node_ids:
                    raise ValueError(
                        f"ReplaceNode references non-existent old_node: {mod.old_node_id}"
                    )
                if mod.old_node_id:
                    active_node_ids.discard(mod.old_node_id)
                if mod.new_node:
                    active_node_ids.add(mod.new_node.node_id)

            elif mod.modification_type.value == "skip_node" and mod.node_id:
                if mod.node_id not in active_node_ids:
                    raise ValueError(f"SkipNode references non-existent node: {mod.node_id}")

            elif mod.modification_type.value == "add_edge" and mod.edge:
                if mod.edge.from_node not in active_node_ids:
                    raise ValueError(
                        f"AddEdge references non-existent from_node: {mod.edge.from_node}"
                    )
                if mod.edge.to_node not in active_node_ids:
                    raise ValueError(f"AddEdge references non-existent to_node: {mod.edge.to_node}")
                if mod.edge.from_node == mod.edge.to_node:
                    raise ValueError(f"AddEdge is a self-loop: {mod.edge.from_node}")
