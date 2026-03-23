"""
ClarificationProtocol: Composes and interprets clarification messages.

When a child agent encounters ambiguity it cannot resolve within its own
context, it uses ClarificationProtocol to compose a precise question for
its parent. When the parent responds, the child uses the same protocol to
interpret the answer and integrate it into its working context.

Both composition and interpretation use the LLM because they require
natural-language understanding -- determining what to ask and what the
answer means in context.
"""

from __future__ import annotations

from typing import Any

from kaizen_agents.llm import LLMClient
from kaizen_agents.types import ClarificationPayload


# JSON schema for composing a clarification question
CLARIFICATION_QUESTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "description": (
                "A precise, answerable question about the ambiguity. "
                "Should be self-contained so the parent can answer without "
                "needing additional context."
            ),
        },
        "options": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Suggested answer options if the question is multiple-choice. "
                "Empty array if the question is open-ended."
            ),
        },
        "blocking": {
            "type": "boolean",
            "description": (
                "Whether the agent must wait for the answer before continuing. "
                "True if the ambiguity prevents any further progress."
            ),
        },
    },
    "required": ["question", "options", "blocking"],
    "additionalProperties": False,
}


# JSON schema for interpreting a clarification response
CLARIFICATION_INTERPRETATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "resolved_value": {
            "type": "string",
            "description": (
                "The concrete value or decision extracted from the response. "
                "Should be a direct, usable answer."
            ),
        },
        "context_updates": {
            "type": "object",
            "description": (
                "Key-value pairs to merge into the agent's working context "
                "based on the clarification response."
            ),
            "additionalProperties": True,
        },
        "confidence": {
            "type": "string",
            "description": (
                "Confidence in the interpretation: 'high', 'medium', or 'low'. "
                "'low' means another clarification round may be needed."
            ),
        },
        "needs_further_clarification": {
            "type": "boolean",
            "description": "Whether the response introduces new ambiguity requiring another question.",
        },
    },
    "required": [
        "resolved_value",
        "context_updates",
        "confidence",
        "needs_further_clarification",
    ],
    "additionalProperties": False,
}


def _build_question_system_prompt() -> str:
    """Build the system prompt for composing clarification questions."""
    return """You are a clarification composer for a PACT-governed autonomous agent system.

A child agent has encountered an ambiguity it cannot resolve on its own. Your job
is to compose a precise, self-contained question that the parent agent can answer.

## Rules

1. The question must be specific and answerable. Avoid vague questions like
   "What should I do?" -- instead ask "Should the authentication middleware use
   JWT or session cookies?"
2. If the ambiguity has a small number of clear options, provide them as choices.
   Leave the options array empty for open-ended questions.
3. Set blocking to true ONLY if the agent genuinely cannot make any further
   progress without the answer. If the agent can continue with a reasonable
   default, set blocking to false.
4. Include enough context in the question itself so the parent does not need
   to look up background information."""


def _build_question_user_prompt(
    ambiguity_description: str,
    context: dict[str, Any],
    suggested_options: list[str] | None,
) -> str:
    """Build the user prompt for question composition."""
    context_lines = []
    for key, value in context.items():
        if isinstance(value, str):
            context_lines.append(f"- **{key}**: {value}")
        else:
            context_lines.append(f"- **{key}**: {value!r}")
    context_section = "\n".join(context_lines) if context_lines else "(no context available)"

    options_section = ""
    if suggested_options:
        options_section = "\n\n## Suggested Options\n\n" + "\n".join(
            f"- {opt}" for opt in suggested_options
        )

    return f"""## Ambiguity Encountered

{ambiguity_description}

## Current Working Context

{context_section}{options_section}

Compose a precise clarification question for the parent agent."""


def _build_interpretation_system_prompt() -> str:
    """Build the system prompt for interpreting clarification responses."""
    return """You are a response interpreter for a PACT-governed autonomous agent system.

A parent agent has responded to a clarification question from its child. Your job
is to extract the actionable answer and translate it into context updates the
child can use to continue its work.

## Rules

1. Extract a concrete resolved_value -- the direct answer to the question.
2. Produce context_updates as key-value pairs the child should merge into
   its working context. Use descriptive key names.
3. Assess confidence: 'high' if the answer is clear and complete, 'medium' if
   it answers the question but leaves some details to the child's judgment,
   'low' if the response is unclear or introduces new questions.
4. Set needs_further_clarification to true only if the response is genuinely
   ambiguous or contradictory and the child cannot proceed without asking again."""


def _build_interpretation_user_prompt(
    response_text: str,
    original_question: str,
    original_options: list[str] | None,
) -> str:
    """Build the user prompt for response interpretation."""
    options_section = ""
    if original_options:
        options_section = "\n\nOriginal options presented:\n" + "\n".join(
            f"- {opt}" for opt in original_options
        )

    return f"""## Original Question

{original_question}{options_section}

## Parent's Response

{response_text}

Extract the answer, produce context updates, assess confidence, and determine
if further clarification is needed."""


class ClarificationProtocol:
    """Composes clarification questions and interprets responses.

    Used by child agents when they encounter ambiguity they cannot resolve
    from their local context or task description alone.

    Usage:
        protocol = ClarificationProtocol(llm_client=my_client)

        # Child asks a question
        payload = protocol.compose_question(
            ambiguity="The task says 'use the standard auth approach' but "
                      "the context mentions both OAuth2 and API keys",
            context={"auth_providers": ["oauth2", "api_key"], "stack": "FastAPI"},
            options=["OAuth2", "API Keys", "Both"],
        )

        # ... send clarification, receive response ...

        # Child interprets the response
        resolved = protocol.interpret_response(
            response="Use OAuth2 for user-facing endpoints and API keys for service-to-service",
            original_question=payload.question,
            original_options=payload.options,
        )
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """Initialise the clarification protocol.

        Args:
            llm_client: A configured LLMClient for composing messages.
        """
        self._llm = llm_client

    def compose_question(
        self,
        ambiguity: str,
        context: dict[str, Any],
        options: list[str] | None = None,
    ) -> ClarificationPayload:
        """Compose a clarification question about an encountered ambiguity.

        Uses the LLM to refine the ambiguity description into a precise,
        answerable question with optional multiple-choice options.

        Args:
            ambiguity: Description of what is unclear or ambiguous.
            context: The agent's current working context.
            options: Optional suggested answer options from the agent's analysis.

        Returns:
            A ClarificationPayload ready to send to the parent.
        """
        system_prompt = _build_question_system_prompt()
        user_prompt = _build_question_user_prompt(ambiguity, context, options)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw_result = self._llm.complete_structured(
            messages=messages,
            schema=CLARIFICATION_QUESTION_SCHEMA,
            schema_name="clarification_question",
        )

        question = raw_result.get("question", ambiguity)
        if not isinstance(question, str) or not question.strip():
            question = ambiguity

        raw_options = raw_result.get("options", [])
        if not isinstance(raw_options, list):
            raw_options = []
        parsed_options = [str(o) for o in raw_options if o] or None

        blocking = raw_result.get("blocking", False)
        if not isinstance(blocking, bool):
            blocking = bool(blocking)

        return ClarificationPayload(
            question=question,
            blocking=blocking,
            is_response=False,
            options=parsed_options,
        )

    def interpret_response(
        self,
        response: str,
        original_question: str,
        original_options: list[str] | None = None,
    ) -> dict[str, Any]:
        """Interpret a parent's response to a clarification question.

        Uses the LLM to extract the concrete answer and translate it into
        context updates the child can integrate into its working state.

        Args:
            response: The parent's answer text.
            original_question: The question that was asked.
            original_options: The options that were presented (if any).

        Returns:
            A dict with keys:
                - resolved_value: The direct answer extracted from the response
                - context_updates: Key-value pairs to merge into context
                - confidence: 'high', 'medium', or 'low'
                - needs_further_clarification: Whether another round is needed
        """
        system_prompt = _build_interpretation_system_prompt()
        user_prompt = _build_interpretation_user_prompt(
            response, original_question, original_options
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw_result = self._llm.complete_structured(
            messages=messages,
            schema=CLARIFICATION_INTERPRETATION_SCHEMA,
            schema_name="clarification_interpretation",
        )

        resolved_value = raw_result.get("resolved_value", response)
        if not isinstance(resolved_value, str):
            resolved_value = str(resolved_value)

        context_updates = raw_result.get("context_updates", {})
        if not isinstance(context_updates, dict):
            context_updates = {}

        confidence = raw_result.get("confidence", "medium")
        if confidence not in ("high", "medium", "low"):
            confidence = "medium"

        needs_further = raw_result.get("needs_further_clarification", False)
        if not isinstance(needs_further, bool):
            needs_further = bool(needs_further)

        return {
            "resolved_value": resolved_value,
            "context_updates": context_updates,
            "confidence": confidence,
            "needs_further_clarification": needs_further,
        }
