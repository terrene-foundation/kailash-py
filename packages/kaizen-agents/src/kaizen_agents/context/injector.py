"""
ContextInjector: Selects relevant context for child agent delegation.

When a parent delegates a subtask to a child, the child should not receive
the parent's entire context -- only the keys relevant to its task. The
ContextInjector handles this filtering with two modes:

1. Deterministic mode: When required_keys is fully specified, it simply
   filters the parent context to those keys. No LLM needed.

2. Semantic mode: When required_keys is incomplete or empty, the LLM
   evaluates each context key for relevance to the subtask description
   and selects the appropriate subset.

This is orchestration logic (kaizen-agents) because semantic relevance
matching requires LLM judgment. The ScopedContext primitive (SDK) handles
the projection enforcement after keys are selected here.
"""

from __future__ import annotations

from typing import Any

from kaizen_agents.llm import LLMClient


# JSON schema for LLM-based context selection
CONTEXT_SELECTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "selected_keys": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Context keys that are relevant to the subtask. "
                "Only include keys that the child agent actually needs."
            ),
        },
        "reasoning": {
            "type": "string",
            "description": (
                "Brief explanation of why these keys were selected " "and why others were excluded."
            ),
        },
    },
    "required": ["selected_keys", "reasoning"],
    "additionalProperties": False,
}


def _build_selection_system_prompt() -> str:
    """Build the system prompt for context key selection."""
    return """You are a context filter for a PACT-governed autonomous agent system.

When a parent agent delegates a subtask to a child, the child should only receive
the context keys it actually needs -- not the parent's entire context. Your job
is to select the relevant keys.

## Rules

1. Include keys that are directly relevant to the subtask description.
2. Include keys that provide necessary background (e.g., project name, tech stack)
   if the subtask depends on that information.
3. EXCLUDE keys that are:
   - Irrelevant to the subtask (e.g., a billing key for a code review task)
   - Internal to the parent's workflow (e.g., parent's retry counts, timing data)
   - Overly large context that can be summarized instead
4. When in doubt, include the key. Under-sharing is more harmful than over-sharing
   because the child cannot ask for keys it does not know exist.
5. Return ONLY keys that exist in the provided context. Do not invent keys."""


def _build_selection_user_prompt(
    parent_context: dict[str, Any],
    subtask_description: str,
) -> str:
    """Build the user prompt for context key selection."""
    context_lines = []
    for key, value in parent_context.items():
        value_preview = str(value)
        if len(value_preview) > 200:
            value_preview = value_preview[:200] + "..."
        context_lines.append(f"- **{key}**: {value_preview}")
    context_section = "\n".join(context_lines) if context_lines else "(empty context)"

    return f"""## Subtask

{subtask_description}

## Available Context Keys

{context_section}

Select which context keys the child agent needs for this subtask."""


class ContextInjector:
    """Selects relevant context keys for child agent delegation.

    Operates in two modes:
    - Deterministic: When required_keys covers all needed keys, uses simple
      dict filtering. Fast, no LLM call.
    - Semantic: When required_keys is empty or incomplete, uses the LLM to
      determine which parent context keys are relevant to the subtask.

    Usage:
        injector = ContextInjector(llm_client=my_client)

        # Deterministic -- required_keys fully specified
        filtered = injector.select_context(
            parent_context={"project": "web-app", "budget": 100, "auth": "oauth2"},
            subtask_description="Implement OAuth2 login",
            required_keys=["project", "auth"],
        )
        # Returns: {"project": "web-app", "auth": "oauth2"}

        # Semantic -- let the LLM decide
        filtered = injector.select_context(
            parent_context={"project": "web-app", "budget": 100, "auth": "oauth2"},
            subtask_description="Implement OAuth2 login",
        )
        # LLM selects relevant keys
    """

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        """Initialise the context injector.

        Args:
            llm_client: Optional LLM client for semantic selection mode.
                If not provided, only deterministic mode is available.
                Calling select_context with empty required_keys and no
                LLM client returns the full parent context.
        """
        self._llm = llm_client

    def select_context(
        self,
        parent_context: dict[str, Any],
        subtask_description: str,
        required_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        """Select relevant context for a child agent.

        When required_keys is provided and non-empty, uses deterministic
        filtering (no LLM call). When required_keys is None or empty, uses
        the LLM to determine relevance semantically.

        Args:
            parent_context: The parent's full context dict.
            subtask_description: What the child agent will be doing.
            required_keys: Explicit list of keys the child needs. When fully
                specified, the LLM is not called.

        Returns:
            A filtered dict containing only the context keys relevant to
            the child's subtask. Keys not present in parent_context are
            silently omitted.
        """
        if not parent_context:
            return {}

        # Deterministic path: required_keys fully specified
        if required_keys:
            return self._deterministic_select(parent_context, required_keys)

        # Semantic path: LLM decides relevance
        if self._llm is not None:
            return self._semantic_select(parent_context, subtask_description)

        # Fallback: no LLM and no required_keys -- return full context
        # (preserving the principle that under-sharing is worse than over-sharing)
        return dict(parent_context)

    def _deterministic_select(
        self,
        parent_context: dict[str, Any],
        required_keys: list[str],
    ) -> dict[str, Any]:
        """Filter parent context to only the specified keys.

        Args:
            parent_context: The full context dict.
            required_keys: Keys to include.

        Returns:
            Filtered dict with only the requested keys that exist in context.
        """
        return {k: parent_context[k] for k in required_keys if k in parent_context}

    def _semantic_select(
        self,
        parent_context: dict[str, Any],
        subtask_description: str,
    ) -> dict[str, Any]:
        """Use the LLM to select contextually relevant keys.

        Args:
            parent_context: The full context dict.
            subtask_description: The child's task description.

        Returns:
            Filtered dict with LLM-selected keys.
        """
        system_prompt = _build_selection_system_prompt()
        user_prompt = _build_selection_user_prompt(parent_context, subtask_description)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw_result = self._llm.complete_structured(
            messages=messages,
            schema=CONTEXT_SELECTION_SCHEMA,
            schema_name="context_selection",
        )

        selected_keys = raw_result.get("selected_keys", [])
        if not isinstance(selected_keys, list):
            # LLM returned unexpected format; fall back to full context
            return dict(parent_context)

        # Filter to only keys that actually exist in the parent context
        valid_keys = [str(k) for k in selected_keys if k and str(k) in parent_context]

        if not valid_keys:
            # LLM selected nothing valid; fall back to full context to avoid
            # starving the child of necessary information
            return dict(parent_context)

        return {k: parent_context[k] for k in valid_keys}
