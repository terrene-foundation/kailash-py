"""
ContextSummarizer: Compresses large context values while preserving key information.

When context values are too large to include in a delegation payload within
the token budget, the ContextSummarizer compresses them using the LLM. The
summarizer preserves the essential information content while reducing token
count to fit within the specified limit.

This is orchestration logic (kaizen-agents) because compression requires
LLM judgment about which information is essential.
"""

from __future__ import annotations

from typing import Any

from kaizen_agents.llm import LLMClient


# JSON schema for context value summarization
SUMMARIZATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": (
                "Compressed version of the context value. Must preserve "
                "all essential facts, decisions, and data points."
            ),
        },
        "preserved_items": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "List of key items that were preserved in the summary. "
                "Serves as a checklist for information retention."
            ),
        },
        "dropped_items": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "List of items that were dropped or simplified in the summary. "
                "Helps the consumer understand what detail was lost."
            ),
        },
    },
    "required": ["summary", "preserved_items", "dropped_items"],
    "additionalProperties": False,
}


def _build_summarization_system_prompt(max_tokens: int) -> str:
    """Build the system prompt for context value summarization.

    Args:
        max_tokens: Target maximum token count for the summary.
    """
    return f"""You are a context summarizer for a PACT-governed autonomous agent system.

A context value is too large to include in full when delegating a task to a
child agent. Your job is to compress it while preserving essential information.

## Rules

1. The summary MUST be significantly shorter than the original. Target approximately
   {max_tokens} tokens or fewer.
2. Preserve ALL key facts, decisions, numerical values, and identifiers.
3. Preserve structural relationships (e.g., "X depends on Y", "A causes B").
4. Drop verbose explanations, examples, and redundant restatements.
5. Drop formatting-only content (decorative separators, excessive whitespace).
6. Use concise language. Replace long phrases with shorter equivalents.
7. If the original is a list, keep all items but shorten each description.
8. If the original is a report, keep findings and conclusions, drop methodology
   details unless they affect interpretation.
9. The summary should be usable as a drop-in replacement for the original
   in the context of delegated tasks."""


def _build_summarization_user_prompt(
    context_value: str,
    context_key: str | None,
) -> str:
    """Build the user prompt for summarization.

    Args:
        context_value: The value to summarize.
        context_key: Optional key name for context about what this value represents.
    """
    key_section = ""
    if context_key:
        key_section = f"\n\nContext key name: **{context_key}**"

    return f"""## Context Value to Summarize{key_section}

{context_value}

Compress this value while preserving all essential information. List what
was preserved and what was dropped."""


def _estimate_token_count(text: str) -> int:
    """Estimate the token count of a text string.

    Uses a rough heuristic of 4 characters per token. This is imprecise but
    sufficient for deciding whether summarization is needed and for setting
    approximate targets.

    Args:
        text: The text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    return max(1, len(text) // 4)


class ContextSummarizer:
    """Compresses large context values while preserving essential information.

    Usage:
        summarizer = ContextSummarizer(llm_client=my_client)

        # Summarize a large context value
        result = summarizer.summarize(
            context_value="<very long analysis report...>",
            max_tokens=500,
            context_key="analysis_report",
        )
        compressed_value = result["summary"]

        # Check what was preserved/dropped
        print("Preserved:", result["preserved_items"])
        print("Dropped:", result["dropped_items"])
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """Initialise the summarizer.

        Args:
            llm_client: A configured LLMClient for summarization.
        """
        self._llm = llm_client

    def summarize(
        self,
        context_value: str,
        max_tokens: int = 500,
        context_key: str | None = None,
    ) -> dict[str, Any]:
        """Summarize a context value to fit within a token budget.

        If the value already fits within max_tokens, it is returned unchanged
        (no LLM call). Otherwise, the LLM compresses it.

        Args:
            context_value: The string value to summarize.
            max_tokens: Target maximum token count for the output. The actual
                output may be slightly over due to estimation imprecision.
            context_key: Optional key name to give the LLM context about
                what this value represents (e.g., "analysis_report").

        Returns:
            A dict with keys:
                - summary: The compressed value (or original if small enough)
                - preserved_items: Items preserved in the summary
                - dropped_items: Items dropped or simplified
                - was_summarized: Whether summarization was actually performed
        """
        estimated_tokens = _estimate_token_count(context_value)

        # If the value already fits, return it unchanged
        if estimated_tokens <= max_tokens:
            return {
                "summary": context_value,
                "preserved_items": ["(all content preserved -- no summarization needed)"],
                "dropped_items": [],
                "was_summarized": False,
            }

        system_prompt = _build_summarization_system_prompt(max_tokens)
        user_prompt = _build_summarization_user_prompt(context_value, context_key)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw_result = self._llm.complete_structured(
            messages=messages,
            schema=SUMMARIZATION_SCHEMA,
            schema_name="context_summarization",
        )

        summary = raw_result.get("summary", "")
        if not isinstance(summary, str) or not summary.strip():
            # LLM failed to produce a summary; return original with a warning
            return {
                "summary": context_value,
                "preserved_items": ["(summarization failed -- original preserved)"],
                "dropped_items": [],
                "was_summarized": False,
            }

        preserved = raw_result.get("preserved_items", [])
        if not isinstance(preserved, list):
            preserved = []
        preserved = [str(item) for item in preserved if item]

        dropped = raw_result.get("dropped_items", [])
        if not isinstance(dropped, list):
            dropped = []
        dropped = [str(item) for item in dropped if item]

        return {
            "summary": summary,
            "preserved_items": preserved,
            "dropped_items": dropped,
            "was_summarized": True,
        }
