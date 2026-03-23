"""
EscalationProtocol: Composes escalation messages and decides parent actions.

When a child agent encounters a problem it cannot resolve within its
envelope -- budget exhaustion, repeated failures, blocked operations,
or genuine uncertainty -- it uses EscalationProtocol to compose a
structured escalation message. When a parent receives an escalation,
the protocol helps decide the appropriate response action.

Composition uses the LLM to write clear problem descriptions with
context. Action decision uses the LLM to evaluate mitigation history
and determine the best course of action.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from kaizen_agents.llm import LLMClient
from kaizen_agents.types import EscalationPayload, EscalationSeverity


class EscalationAction(Enum):
    """Possible parent responses to a child's escalation."""

    RETRY = "retry"
    RECOMPOSE = "recompose"
    ESCALATE_FURTHER = "escalate_further"
    ABANDON = "abandon"


# JSON schema for composing an escalation message
ESCALATION_COMPOSITION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "problem_description": {
            "type": "string",
            "description": (
                "Clear description of the problem, what the agent was trying to do, "
                "and why it cannot proceed."
            ),
        },
        "severity": {
            "type": "string",
            "description": ("Severity level: 'warning', 'blocked', 'budget_alert', or 'critical'."),
        },
        "suggested_action": {
            "type": "string",
            "description": "What the child recommends the parent do about this problem.",
        },
        "violating_dimension": {
            "type": "string",
            "description": (
                "Which envelope dimension was violated, if applicable. "
                "One of: 'financial', 'operational', 'temporal', 'data_access', "
                "'communication', or 'none' if not an envelope issue."
            ),
        },
    },
    "required": [
        "problem_description",
        "severity",
        "suggested_action",
        "violating_dimension",
    ],
    "additionalProperties": False,
}


# JSON schema for deciding the parent's response action
ESCALATION_DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "description": (
                "The action to take: 'retry' (try the same task again), "
                "'recompose' (redesign the approach), 'escalate_further' "
                "(pass to grandparent), or 'abandon' (give up on this subtask)."
            ),
        },
        "reasoning": {
            "type": "string",
            "description": "Explanation of why this action was chosen.",
        },
        "retry_modifications": {
            "type": "string",
            "description": (
                "If action is 'retry', what should change on the retry attempt. "
                "Empty string if not applicable."
            ),
        },
        "recompose_hints": {
            "type": "string",
            "description": (
                "If action is 'recompose', hints for how to redesign the approach. "
                "Empty string if not applicable."
            ),
        },
    },
    "required": ["action", "reasoning", "retry_modifications", "recompose_hints"],
    "additionalProperties": False,
}


_SEVERITY_MAP: dict[str, EscalationSeverity] = {
    "warning": EscalationSeverity.WARNING,
    "blocked": EscalationSeverity.BLOCKED,
    "budget_alert": EscalationSeverity.BUDGET_ALERT,
    "critical": EscalationSeverity.CRITICAL,
}

_ACTION_MAP: dict[str, EscalationAction] = {
    "retry": EscalationAction.RETRY,
    "recompose": EscalationAction.RECOMPOSE,
    "escalate_further": EscalationAction.ESCALATE_FURTHER,
    "abandon": EscalationAction.ABANDON,
}


def _build_composition_system_prompt() -> str:
    """Build the system prompt for escalation composition."""
    return """You are an escalation composer for a PACT-governed autonomous agent system.

A child agent has encountered a problem it cannot resolve within its envelope.
Your job is to compose a clear, structured escalation message for the parent.

## Rules

1. Describe the problem specifically: what was attempted, what failed, and why
   the agent cannot proceed.
2. Choose severity carefully:
   - warning: Agent can continue with degraded quality. Informational.
   - blocked: Agent cannot proceed but the issue is not time-critical.
   - budget_alert: An envelope dimension is near exhaustion (80%+). Proactive warning.
   - critical: Hard failure requiring immediate intervention. Task cannot continue.
3. Suggest a concrete action the parent could take to resolve the issue.
4. Identify which envelope dimension is violated (if applicable). Use 'none'
   if the problem is not an envelope constraint issue."""


def _build_composition_user_prompt(
    problem: str,
    mitigations_tried: list[str],
    severity_hint: str,
) -> str:
    """Build the user prompt for escalation composition."""
    mitigations_section = ""
    if mitigations_tried:
        mitigations_section = "\n\n## Mitigations Already Tried\n\n" + "\n".join(
            f"- {m}" for m in mitigations_tried
        )

    return f"""## Problem Encountered

{problem}

Severity hint from the agent: {severity_hint}{mitigations_section}

Compose a structured escalation message for the parent."""


def _build_decision_system_prompt() -> str:
    """Build the system prompt for escalation action decision."""
    return """You are an escalation decision engine for a PACT-governed autonomous agent system.

A child agent has escalated a problem. You must decide the best course of action
for the parent.

## Decision Framework

1. **retry**: Appropriate when the failure might be transient (network errors,
   rate limits, non-deterministic LLM outputs) and the child has not exhausted
   its retry budget. Specify what should change on the retry.

2. **recompose**: Appropriate when the approach itself is flawed -- the subtask
   needs to be broken down differently, a different tool/capability is needed,
   or the constraints need adjustment. Provide hints for the redesign.

3. **escalate_further**: Appropriate when the parent also cannot resolve the
   issue -- e.g., it requires additional budget, broader permissions, or
   human approval. This pushes the escalation up the delegation chain.

4. **abandon**: Appropriate when the subtask is optional and the cost of
   continued attempts exceeds the value, or when the problem is fundamentally
   unsolvable within the current envelope. Abandoning is a valid choice when
   the gradient zone permits it.

## Rules

- If the severity is 'warning', lean toward 'retry' or 'recompose' -- do not
  escalate or abandon for warnings unless mitigations are exhausted.
- If the severity is 'critical' and mitigations are exhausted, lean toward
  'escalate_further' or 'abandon'.
- If a budget dimension is violated, 'recompose' (with reduced scope) or
  'escalate_further' (request more budget) are the primary options.
- Consider the number of mitigations already tried. More attempts suggest
  the problem is structural (favoring recompose or escalate), not transient."""


def _build_decision_user_prompt(
    escalation: EscalationPayload,
    parent_context: dict[str, Any],
) -> str:
    """Build the user prompt for escalation action decision."""
    mitigations_str = ""
    if escalation.attempted_mitigations:
        mitigations_str = "\n\nMitigations already tried:\n" + "\n".join(
            f"- {m}" for m in escalation.attempted_mitigations
        )

    suggestion_str = ""
    if escalation.suggested_action:
        suggestion_str = f"\n\nChild's suggestion: {escalation.suggested_action}"

    dimension_str = ""
    if escalation.violating_dimension:
        dimension_str = f"\nViolating dimension: {escalation.violating_dimension}"

    context_lines = []
    for key, value in parent_context.items():
        if isinstance(value, str):
            context_lines.append(f"- **{key}**: {value}")
        else:
            context_lines.append(f"- **{key}**: {value!r}")
    context_section = "\n".join(context_lines) if context_lines else "(no context)"

    return f"""## Escalation

Severity: {escalation.severity.value}
Problem: {escalation.problem_description}{dimension_str}{mitigations_str}{suggestion_str}

## Parent's Context

{context_section}

Decide the best action: retry, recompose, escalate_further, or abandon."""


class EscalationProtocol:
    """Composes escalation messages and decides parent response actions.

    Usage:
        protocol = EscalationProtocol(llm_client=my_client)

        # Child composes an escalation
        payload = protocol.compose_escalation(
            problem="Rate limit exceeded on the code search API after 3 attempts",
            mitigations_tried=["Added exponential backoff", "Reduced query scope"],
            severity="blocked",
        )

        # ... send escalation to parent ...

        # Parent decides what to do
        action, details = protocol.decide_action(
            escalation=payload,
            parent_context={"retry_budget_remaining": 1, "subtask_optional": False},
        )
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """Initialise the escalation protocol.

        Args:
            llm_client: A configured LLMClient for composing messages.
        """
        self._llm = llm_client

    def compose_escalation(
        self,
        problem: str,
        mitigations_tried: list[str],
        severity: str,
    ) -> EscalationPayload:
        """Compose an escalation message about a problem the child cannot resolve.

        Uses the LLM to write a clear problem description and determine the
        appropriate severity level and suggested action.

        Args:
            problem: Description of the problem encountered.
            mitigations_tried: List of actions the child already attempted.
            severity: Severity hint from the child ('warning', 'blocked',
                'budget_alert', or 'critical').

        Returns:
            A fully populated EscalationPayload ready to send to the parent.
        """
        system_prompt = _build_composition_system_prompt()
        user_prompt = _build_composition_user_prompt(problem, mitigations_tried, severity)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw_result = self._llm.complete_structured(
            messages=messages,
            schema=ESCALATION_COMPOSITION_SCHEMA,
            schema_name="escalation_composition",
        )

        problem_desc = raw_result.get("problem_description", problem)
        if not isinstance(problem_desc, str) or not problem_desc.strip():
            problem_desc = problem

        severity_str = raw_result.get("severity", severity)
        if not isinstance(severity_str, str):
            severity_str = severity
        resolved_severity = _SEVERITY_MAP.get(
            severity_str.lower().strip(), EscalationSeverity.BLOCKED
        )

        suggested_action = raw_result.get("suggested_action")
        if not isinstance(suggested_action, str) or not suggested_action.strip():
            suggested_action = None

        violating_dim = raw_result.get("violating_dimension")
        if not isinstance(violating_dim, str) or violating_dim.lower().strip() == "none":
            violating_dim = None

        return EscalationPayload(
            severity=resolved_severity,
            problem_description=problem_desc,
            attempted_mitigations=list(mitigations_tried),
            suggested_action=suggested_action,
            violating_dimension=violating_dim,
        )

    def decide_action(
        self,
        escalation: EscalationPayload,
        parent_context: dict[str, Any],
    ) -> tuple[EscalationAction, dict[str, Any]]:
        """Decide the best response action for an escalation.

        Uses the LLM to evaluate the escalation against the parent's context
        and determine whether to retry, recompose, escalate further, or abandon.

        Args:
            escalation: The escalation payload from the child.
            parent_context: The parent's current context for decision-making.

        Returns:
            A tuple of (EscalationAction, details_dict). The details dict contains:
                - reasoning: Why this action was chosen
                - retry_modifications: What to change on retry (if action is RETRY)
                - recompose_hints: Hints for redesign (if action is RECOMPOSE)
        """
        system_prompt = _build_decision_system_prompt()
        user_prompt = _build_decision_user_prompt(escalation, parent_context)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw_result = self._llm.complete_structured(
            messages=messages,
            schema=ESCALATION_DECISION_SCHEMA,
            schema_name="escalation_decision",
        )

        action_str = raw_result.get("action", "escalate_further")
        if not isinstance(action_str, str):
            action_str = "escalate_further"
        action = _ACTION_MAP.get(action_str.lower().strip(), EscalationAction.ESCALATE_FURTHER)

        reasoning = raw_result.get("reasoning", "")
        if not isinstance(reasoning, str):
            reasoning = str(reasoning)

        retry_mods = raw_result.get("retry_modifications", "")
        if not isinstance(retry_mods, str):
            retry_mods = str(retry_mods)

        recompose_hints = raw_result.get("recompose_hints", "")
        if not isinstance(recompose_hints, str):
            recompose_hints = str(recompose_hints)

        details: dict[str, Any] = {
            "reasoning": reasoning,
            "retry_modifications": retry_mods,
            "recompose_hints": recompose_hints,
        }

        return action, details
