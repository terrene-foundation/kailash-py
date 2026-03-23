"""
DelegationProtocol: Composes and processes delegation messages between agents.

A parent agent uses DelegationProtocol to craft clear, context-rich task
descriptions for child agents, and to process the results when children
complete their work. The LLM writes the natural-language task description
that goes into the DelegationPayload; the protocol handles envelope
packaging, deadline calculation, and result interpretation.

This belongs in kaizen-agents (not the SDK) because composing human-readable
task descriptions requires LLM judgment.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from kaizen_agents.llm import LLMClient
from kaizen_agents.types import (
    CompletionPayload,
    ConstraintEnvelope,
    DelegationPayload,
    Priority,
)


# JSON schema for the LLM-composed task description
DELEGATION_COMPOSITION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "task_description": {
            "type": "string",
            "description": (
                "A clear, actionable task description for the child agent. "
                "Includes the goal, relevant context, constraints, and expected output format."
            ),
        },
        "priority_suggestion": {
            "type": "string",
            "description": ("Suggested priority: 'low', 'normal', 'high', or 'critical'."),
        },
        "required_context_keys": {
            "type": "array",
            "items": {"type": "string"},
            "description": ("Context keys from the parent's context that the child needs to see."),
        },
    },
    "required": ["task_description", "priority_suggestion", "required_context_keys"],
    "additionalProperties": False,
}


# JSON schema for processing a completion payload
COMPLETION_PROCESSING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Brief summary of what the child accomplished.",
        },
        "extracted_outputs": {
            "type": "object",
            "description": (
                "Key-value pairs extracted from the child's result, "
                "normalized for the parent's context."
            ),
            "additionalProperties": True,
        },
        "quality_assessment": {
            "type": "string",
            "description": (
                "Assessment of the result quality: 'complete', 'partial', or 'failed'."
            ),
        },
        "follow_up_needed": {
            "type": "boolean",
            "description": "Whether the parent needs to take further action on this result.",
        },
        "follow_up_reason": {
            "type": "string",
            "description": "If follow_up_needed is true, why further action is required.",
        },
    },
    "required": [
        "summary",
        "extracted_outputs",
        "quality_assessment",
        "follow_up_needed",
        "follow_up_reason",
    ],
    "additionalProperties": False,
}


_PRIORITY_MAP: dict[str, Priority] = {
    "low": Priority.LOW,
    "normal": Priority.NORMAL,
    "high": Priority.HIGH,
    "critical": Priority.CRITICAL,
}


def _build_composition_system_prompt() -> str:
    """Build the system prompt for delegation task composition."""
    return """You are a delegation composer for a PACT-governed autonomous agent system.

Your job is to write clear, actionable task descriptions that a child agent can
execute independently. The task description must contain everything the child
needs to understand WHAT to do, WHY it matters, and WHAT constraints apply.

## Rules

1. The task description must be self-contained. The child agent has no memory of
   the parent's conversation history -- only the task description and the context
   snapshot you select.
2. Include specific success criteria so the child knows when it is done.
3. Mention any format requirements for the output.
4. Reference relevant constraints from the envelope (budget limits, blocked operations,
   data access ceilings) so the child respects them.
5. Suggest priority based on urgency and importance:
   - low: Background work, no time pressure
   - normal: Standard processing, default
   - high: Time-sensitive or blocking other work
   - critical: Immediate attention required, failure has cascading impact
6. List the context keys the child needs from the parent's context. Only include
   keys that are directly relevant -- do not over-share context."""


def _build_composition_user_prompt(
    subtask_description: str,
    context: dict[str, Any],
    envelope: ConstraintEnvelope,
    deadline: datetime | None,
) -> str:
    """Build the user prompt for delegation composition."""
    context_lines = []
    for key, value in context.items():
        if isinstance(value, str):
            context_lines.append(f"- **{key}**: {value}")
        else:
            context_lines.append(f"- **{key}**: {value!r}")
    context_section = "\n".join(context_lines) if context_lines else "(no context available)"

    budget_info = ""
    financial_limit = envelope.financial.get("limit")
    if financial_limit is not None:
        budget_info += f"\n- Financial budget: ${financial_limit}"

    blocked_ops = envelope.operational.get("blocked", [])
    if blocked_ops:
        budget_info += f"\n- Blocked operations: {', '.join(blocked_ops)}"

    data_ceiling = envelope.data_access.get("ceiling")
    if data_ceiling:
        budget_info += f"\n- Data access ceiling: {data_ceiling}"

    deadline_info = ""
    if deadline:
        deadline_info = f"\n- Deadline: {deadline.isoformat()}"

    return f"""## Subtask to Delegate

{subtask_description}

## Available Context

{context_section}

## Envelope Constraints{budget_info}{deadline_info}

Write a clear task description for the child agent, suggest a priority level,
and list which context keys the child needs."""


def _build_processing_system_prompt() -> str:
    """Build the system prompt for completion processing."""
    return """You are a result processor for a PACT-governed autonomous agent system.

A child agent has completed a delegated task and returned results. Your job is to:

1. Summarize what the child accomplished.
2. Extract the key outputs into a structured form the parent can use.
3. Assess the quality: 'complete' (fully done), 'partial' (some gaps), or 'failed'.
4. Determine if the parent needs to take further action (e.g., retry, escalate,
   delegate additional subtasks)."""


def _build_processing_user_prompt(
    completion: CompletionPayload,
    plan_context: dict[str, Any],
) -> str:
    """Build the user prompt for completion processing."""
    result_str = str(completion.result) if completion.result is not None else "(no result)"
    context_updates_str = (
        str(completion.context_updates) if completion.context_updates else "(none)"
    )

    success_str = "SUCCESS" if completion.success else "FAILURE"
    error_str = ""
    if completion.error_detail:
        error_str = f"\nError detail: {completion.error_detail}"

    resource_str = ""
    consumed = completion.resource_consumed
    if consumed.financial_spent > 0 or consumed.actions_executed > 0:
        resource_str = (
            f"\nResources consumed: ${consumed.financial_spent:.4f} spent, "
            f"{consumed.actions_executed} actions, "
            f"{consumed.elapsed_seconds:.1f}s elapsed"
        )

    plan_context_lines = []
    for key, value in plan_context.items():
        if isinstance(value, str):
            plan_context_lines.append(f"- **{key}**: {value}")
        else:
            plan_context_lines.append(f"- **{key}**: {value!r}")
    plan_ctx_section = "\n".join(plan_context_lines) if plan_context_lines else "(no plan context)"

    return f"""## Child Completion Report

Status: {success_str}{error_str}

Result:
{result_str}

Context updates from child:
{context_updates_str}{resource_str}

## Parent's Plan Context

{plan_ctx_section}

Summarize the result, extract key outputs, assess quality, and determine
if the parent needs to take further action."""


class DelegationProtocol:
    """Composes delegation messages and processes completion results.

    The protocol uses an LLM to:
    - Write clear, self-contained task descriptions for child agents
    - Process completion results and extract structured outputs

    Usage:
        protocol = DelegationProtocol(llm_client=my_client)
        payload = protocol.compose_delegation(
            subtask_description="Analyze the authentication requirements",
            context={"project": "web-app", "stack": "Python/FastAPI"},
            envelope=my_envelope,
            deadline=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        # ... send delegation, wait for completion ...
        processed = protocol.handle_completion(completion_payload, plan_context)
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """Initialise the delegation protocol.

        Args:
            llm_client: A configured LLMClient for composing messages.
        """
        self._llm = llm_client

    def compose_delegation(
        self,
        subtask_description: str,
        context: dict[str, Any],
        envelope: ConstraintEnvelope,
        deadline: datetime | None = None,
    ) -> DelegationPayload:
        """Compose a DelegationPayload with an LLM-written task description.

        The LLM reads the subtask description, available context, and envelope
        constraints, then produces a clear, self-contained task description
        that the child agent can execute without additional context.

        Args:
            subtask_description: What the child should accomplish.
            context: Parent's context dict (all available keys).
            envelope: The constraint envelope allocated to the child.
            deadline: Optional absolute deadline for the task.

        Returns:
            A fully populated DelegationPayload ready to send.
        """
        system_prompt = _build_composition_system_prompt()
        user_prompt = _build_composition_user_prompt(
            subtask_description, context, envelope, deadline
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw_result = self._llm.complete_structured(
            messages=messages,
            schema=DELEGATION_COMPOSITION_SCHEMA,
            schema_name="delegation_composition",
        )

        task_description = raw_result.get("task_description", subtask_description)
        if not isinstance(task_description, str) or not task_description.strip():
            task_description = subtask_description

        priority_str = raw_result.get("priority_suggestion", "normal")
        if not isinstance(priority_str, str):
            priority_str = "normal"
        priority = _PRIORITY_MAP.get(priority_str.lower().strip(), Priority.NORMAL)

        required_keys = raw_result.get("required_context_keys", [])
        if not isinstance(required_keys, list):
            required_keys = []
        required_keys = [str(k) for k in required_keys if k]

        # Build the context snapshot: only include keys the LLM selected
        context_snapshot: dict[str, Any] = {}
        for key in required_keys:
            if key in context:
                context_snapshot[key] = context[key]

        return DelegationPayload(
            task_description=task_description,
            context_snapshot=context_snapshot,
            envelope=envelope,
            deadline=deadline,
            priority=priority,
        )

    def handle_completion(
        self,
        completion: CompletionPayload,
        plan_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Process a child's completion payload and extract structured results.

        Uses the LLM to summarize the result, extract key outputs, assess
        quality, and determine whether follow-up action is needed.

        Args:
            completion: The CompletionPayload from the child agent.
            plan_context: The parent's current plan context for reference.

        Returns:
            A dict with keys:
                - summary: Brief description of what was accomplished
                - extracted_outputs: Normalized key-value pairs from the result
                - quality_assessment: 'complete', 'partial', or 'failed'
                - follow_up_needed: Whether additional action is required
                - follow_up_reason: Why follow-up is needed (empty if not)
                - context_updates: The child's context_updates passed through
                - success: The child's success flag
        """
        system_prompt = _build_processing_system_prompt()
        user_prompt = _build_processing_user_prompt(completion, plan_context)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw_result = self._llm.complete_structured(
            messages=messages,
            schema=COMPLETION_PROCESSING_SCHEMA,
            schema_name="completion_processing",
        )

        summary = raw_result.get("summary", "")
        if not isinstance(summary, str):
            summary = str(summary)

        extracted = raw_result.get("extracted_outputs", {})
        if not isinstance(extracted, dict):
            extracted = {}

        quality = raw_result.get("quality_assessment", "partial")
        if quality not in ("complete", "partial", "failed"):
            quality = "partial"

        follow_up = raw_result.get("follow_up_needed", False)
        if not isinstance(follow_up, bool):
            follow_up = bool(follow_up)

        follow_up_reason = raw_result.get("follow_up_reason", "")
        if not isinstance(follow_up_reason, str):
            follow_up_reason = str(follow_up_reason)

        return {
            "summary": summary,
            "extracted_outputs": extracted,
            "quality_assessment": quality,
            "follow_up_needed": follow_up,
            "follow_up_reason": follow_up_reason,
            "context_updates": dict(completion.context_updates),
            "success": completion.success,
        }
