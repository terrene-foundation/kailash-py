"""
FailureDiagnoser: Analyzes node failures and produces structured diagnoses.

When PlanExecutor classifies a failure as HELD (gradient zone), the
orchestration layer uses FailureDiagnoser to understand what went wrong
before the Recomposer decides how to fix it.

The diagnoser is part of the orchestration layer (kaizen-agents) because
it requires LLM judgment. The SDK's PlanExecutor only classifies failures
into gradient zones deterministically -- it does not diagnose root causes.

See: specs/05-plan-dag.md (Section 6, Held zone resolution)
See: 01-analysis/01-research/08-planexecutor-boundary-resolution.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from kaizen_agents.llm import LLMClient
from kaizen_agents.types import Plan, PlanNode, PlanNodeState


class FailureCategory(Enum):
    """Classification of the root cause of a node failure.

    Used by the Recomposer to select an appropriate recovery strategy.
    """

    TRANSIENT = "transient"
    """Temporary issue likely fixed by retry (e.g., rate limit, network timeout)."""

    PERMANENT = "permanent"
    """Fundamental inability to complete the task with the current approach."""

    RESOURCE = "resource"
    """Budget, timeout, or other resource constraint exhausted."""

    DEPENDENCY = "dependency"
    """Upstream data is missing, malformed, or insufficient."""

    CONFIGURATION = "configuration"
    """Wrong tools, model, parameters, or capabilities for the task."""


@dataclass
class FailureDiagnosis:
    """Structured diagnosis of a node failure.

    Produced by FailureDiagnoser, consumed by Recomposer to select a
    recovery strategy and generate PlanModification objects.

    Attributes:
        node_id: The failed node that was diagnosed.
        root_cause: Human-readable explanation of the root cause.
        category: Classification of the failure type.
        recoverable: Whether the failure can potentially be recovered from.
            False means the Recomposer should consider SKIP or ABORT.
        suggested_actions: Ordered list of concrete recovery actions the
            Recomposer should consider (most preferred first).
        confidence: How confident the diagnoser is in this diagnosis (0.0-1.0).
        raw_error: The original error string for audit trail.
    """

    node_id: str
    root_cause: str
    category: FailureCategory
    recoverable: bool
    suggested_actions: list[str] = field(default_factory=list)
    confidence: float = 0.5
    raw_error: str = ""


# JSON schema for the LLM structured output
DIAGNOSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "root_cause": {
            "type": "string",
            "description": (
                "Clear explanation of why the node failed. Be specific: " "what went wrong and why."
            ),
        },
        "category": {
            "type": "string",
            "enum": ["transient", "permanent", "resource", "dependency", "configuration"],
            "description": (
                "Classification: transient (retry fixes it), permanent (need different approach), "
                "resource (budget/timeout), dependency (upstream data issue), "
                "configuration (wrong tools/params)."
            ),
        },
        "recoverable": {
            "type": "boolean",
            "description": "Whether the failure can potentially be recovered from.",
        },
        "suggested_actions": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Ordered list of concrete recovery actions (most preferred first). "
                "Examples: 'retry with exponential backoff', 'replace agent with web-search capability', "
                "'skip this optional analysis step', 'add a data-validation node upstream'."
            ),
        },
        "confidence": {
            "type": "number",
            "description": "Confidence in this diagnosis from 0.0 (guessing) to 1.0 (certain).",
        },
    },
    "required": ["root_cause", "category", "recoverable", "suggested_actions", "confidence"],
    "additionalProperties": False,
}


def _build_diagnosis_system_prompt() -> str:
    """Build the system prompt for the failure diagnoser."""
    return """You are a failure diagnosis engine for an autonomous agent orchestration system.

A node in a plan DAG has failed. Your job is to analyze the error in context
and produce a structured diagnosis that will be used to decide how to recover.

## Failure Categories

- **transient**: Temporary issue that retry will likely fix (rate limits, network timeouts,
  temporary service unavailability, connection resets).
- **permanent**: The current approach fundamentally cannot succeed. The agent lacks the
  ability to complete the task as specified (wrong model, impossible task, logical error
  in approach).
- **resource**: A resource constraint was hit -- budget exhausted, timeout exceeded,
  memory limit, token limit. The task might succeed with more resources.
- **dependency**: The node's inputs (from upstream nodes) are missing, malformed, or
  insufficient for the task. The upstream node completed but produced inadequate output.
- **configuration**: The agent has the wrong tools, wrong model, wrong parameters, or
  insufficient capabilities for this specific task. A differently configured agent could
  succeed.

## Rules

1. Be specific in root_cause. "Something went wrong" is not acceptable.
2. Match the category to the actual error pattern, not a guess.
3. Set recoverable=false only when no recovery strategy can reasonably succeed.
4. Order suggested_actions from most preferred (least disruptive) to least preferred.
5. Confidence should reflect how clearly the error maps to a category:
   - 0.9-1.0: Error message is unambiguous (e.g., "429 Too Many Requests" -> transient)
   - 0.6-0.8: Pattern strongly suggests a category but could be ambiguous
   - 0.3-0.5: Educated guess based on context
   - 0.0-0.2: Very uncertain, error is generic or unclear"""


def _build_diagnosis_user_prompt(
    node: PlanNode,
    error: str,
    plan: Plan,
    execution_context: dict[str, Any],
) -> str:
    """Build the user prompt with failure details and plan context."""
    # Collect upstream node info for context
    upstream_info = []
    for edge in plan.edges:
        if edge.to_node == node.node_id:
            upstream_node = plan.nodes.get(edge.from_node)
            if upstream_node:
                state_str = upstream_node.state.value
                output_summary = ""
                if upstream_node.output is not None:
                    output_str = str(upstream_node.output)
                    output_summary = f" (output: {output_str[:200]})"
                upstream_info.append(f"  - {edge.from_node}: state={state_str}{output_summary}")

    upstream_section = ""
    if upstream_info:
        upstream_section = "\n## Upstream Nodes\n\n" + "\n".join(upstream_info)

    downstream_info = []
    for edge in plan.edges:
        if edge.from_node == node.node_id:
            downstream_node = plan.nodes.get(edge.to_node)
            if downstream_node:
                downstream_info.append(
                    f"  - {edge.to_node}: {downstream_node.agent_spec.description}"
                )

    downstream_section = ""
    if downstream_info:
        downstream_section = "\n## Downstream Nodes (blocked by this failure)\n\n" + "\n".join(
            downstream_info
        )

    context_section = ""
    if execution_context:
        context_lines = [f"  - {k}: {v}" for k, v in execution_context.items()]
        context_section = "\n## Execution Context\n\n" + "\n".join(context_lines)

    tools_str = ", ".join(node.agent_spec.tool_ids) if node.agent_spec.tool_ids else "(none)"
    caps_str = ", ".join(node.agent_spec.capabilities) if node.agent_spec.capabilities else "(none)"

    return f"""## Failed Node

- **Node ID**: {node.node_id}
- **Purpose**: {node.agent_spec.description}
- **Capabilities**: {caps_str}
- **Tools**: {tools_str}
- **Optional**: {node.optional}
- **Retry count**: {node.retry_count} / {plan.gradient.retry_budget}

## Error

{error}
{upstream_section}{downstream_section}{context_section}

## Plan Context

- **Plan name**: {plan.name}
- **Total nodes**: {len(plan.nodes)}

Diagnose the failure. Return the result as a JSON object with: root_cause,
category (transient/permanent/resource/dependency/configuration),
recoverable (boolean), suggested_actions (list), and confidence (0.0-1.0)."""


class FailureDiagnoser:
    """Analyzes node failures and produces structured diagnoses using an LLM.

    The diagnoser sits between PlanExecutor's gradient classification (deterministic,
    SDK-level) and the Recomposer's recovery strategy selection (LLM-driven,
    orchestration-level). When PlanExecutor emits a NodeHeld event, the orchestration
    layer calls FailureDiagnoser to understand the root cause before attempting recovery.

    Usage:
        diagnoser = FailureDiagnoser(llm_client=my_client)
        diagnosis = diagnoser.diagnose(
            node_id="research-node",
            error="429 Too Many Requests: rate limit exceeded",
            plan=my_plan,
            execution_context={"elapsed_seconds": 45.2},
        )
        # diagnosis.category == FailureCategory.TRANSIENT
        # diagnosis.recoverable == True
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """Initialise the diagnoser with an LLM client.

        Args:
            llm_client: A configured LLMClient instance for making completions.
        """
        self._llm = llm_client

    def diagnose(
        self,
        node_id: str,
        error: str,
        plan: Plan,
        execution_context: dict[str, Any] | None = None,
    ) -> FailureDiagnosis:
        """Diagnose a node failure using LLM analysis.

        Args:
            node_id: The ID of the failed node.
            error: The error message or description from the failed node.
            plan: The plan containing the failed node and its context.
            execution_context: Optional dict of runtime context (elapsed time,
                resource consumption, attempt count, etc.).

        Returns:
            A FailureDiagnosis with structured root cause analysis.

        Raises:
            KeyError: If node_id is not found in the plan.
            ValueError: If the LLM returns an unparseable response.
        """
        node = plan.nodes[node_id]
        effective_context = execution_context or {}

        system_prompt = _build_diagnosis_system_prompt()
        user_prompt = _build_diagnosis_user_prompt(node, error, plan, effective_context)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw_result = self._llm.complete_structured(
            messages=messages,
            schema=DIAGNOSIS_SCHEMA,
            schema_name="failure_diagnosis",
        )

        return self._parse_diagnosis(node_id, error, raw_result)

    def _parse_diagnosis(
        self,
        node_id: str,
        error: str,
        raw: dict[str, Any],
    ) -> FailureDiagnosis:
        """Parse and validate the raw LLM diagnosis response.

        Args:
            node_id: The failed node ID (passed through to the diagnosis).
            error: The original error string (preserved for audit trail).
            raw: The parsed JSON dict from the LLM structured output.

        Returns:
            A validated FailureDiagnosis.

        Raises:
            ValueError: If required fields are missing or have invalid values.
        """
        root_cause = raw.get("root_cause", "")
        if not root_cause or not isinstance(root_cause, str):
            raise ValueError(f"Diagnosis missing or empty 'root_cause': {raw.get('root_cause')!r}")

        category_str = raw.get("category", "")
        try:
            category = FailureCategory(category_str)
        except ValueError:
            raise ValueError(
                f"Invalid failure category '{category_str}'. "
                f"Must be one of: {[c.value for c in FailureCategory]}"
            )

        recoverable = raw.get("recoverable")
        if not isinstance(recoverable, bool):
            raise ValueError(
                f"'recoverable' must be a boolean, got {type(recoverable).__name__}: "
                f"{recoverable!r}"
            )

        suggested_actions = raw.get("suggested_actions", [])
        if not isinstance(suggested_actions, list):
            suggested_actions = []
        suggested_actions = [str(a) for a in suggested_actions if a]

        confidence = raw.get("confidence", 0.5)
        if not isinstance(confidence, (int, float)):
            confidence = 0.5
        confidence = max(0.0, min(1.0, float(confidence)))

        return FailureDiagnosis(
            node_id=node_id,
            root_cause=root_cause,
            category=category,
            recoverable=recoverable,
            suggested_actions=suggested_actions,
            confidence=confidence,
            raw_error=error,
        )
