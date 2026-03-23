"""
Unit tests for kaizen_agents.context — ContextInjector and ContextSummarizer.

Uses mocked LLM (Tier 1 — unit tests may mock external services).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from kaizen_agents.orchestration.context.injector import (
    CONTEXT_SELECTION_SCHEMA,
    ContextInjector,
)
from kaizen_agents.orchestration.context.summarizer import (
    SUMMARIZATION_SCHEMA,
    ContextSummarizer,
    _estimate_token_count,
)
from kaizen_agents.llm import LLMClient


# ---------------------------------------------------------------------------
# Helpers — mock LLM client
# ---------------------------------------------------------------------------


def _make_mock_llm(structured_response: dict[str, Any]) -> LLMClient:
    """Create a mock LLMClient that returns the given structured response."""
    mock = MagicMock(spec=LLMClient)
    mock.complete_structured.return_value = structured_response
    return mock


# ---------------------------------------------------------------------------
# ContextInjector — deterministic mode (no LLM)
# ---------------------------------------------------------------------------


class TestContextInjectorDeterministic:
    """Tests for ContextInjector with explicit required_keys (no LLM call)."""

    def test_select_with_all_keys_present(self) -> None:
        """All requested keys exist in parent context."""
        injector = ContextInjector()
        result = injector.select_context(
            parent_context={
                "project": "web-app",
                "stack": "FastAPI",
                "budget": 100,
                "auth": "oauth2",
            },
            subtask_description="Set up authentication",
            required_keys=["project", "auth"],
        )

        assert result == {"project": "web-app", "auth": "oauth2"}

    def test_select_with_missing_keys_silently_omitted(self) -> None:
        """Keys not in parent context are silently omitted."""
        injector = ContextInjector()
        result = injector.select_context(
            parent_context={"project": "web-app"},
            subtask_description="Anything",
            required_keys=["project", "nonexistent_key"],
        )

        assert result == {"project": "web-app"}

    def test_select_with_empty_context(self) -> None:
        """Empty parent context returns empty dict."""
        injector = ContextInjector()
        result = injector.select_context(
            parent_context={},
            subtask_description="Anything",
            required_keys=["project"],
        )

        assert result == {}

    def test_select_deterministic_does_not_call_llm(self) -> None:
        """When required_keys is provided, LLM is never called."""
        llm = _make_mock_llm({"selected_keys": ["project"], "reasoning": "r"})
        injector = ContextInjector(llm_client=llm)

        injector.select_context(
            parent_context={"project": "web-app", "budget": 100},
            subtask_description="Task",
            required_keys=["project"],
        )

        llm.complete_structured.assert_not_called()

    def test_select_preserves_complex_values(self) -> None:
        """Complex values (lists, dicts) are preserved as-is."""
        injector = ContextInjector()
        result = injector.select_context(
            parent_context={
                "files": ["a.py", "b.py", "c.py"],
                "config": {"debug": True, "port": 8080},
                "name": "test",
            },
            subtask_description="Review files",
            required_keys=["files", "config"],
        )

        assert result["files"] == ["a.py", "b.py", "c.py"]
        assert result["config"] == {"debug": True, "port": 8080}


# ---------------------------------------------------------------------------
# ContextInjector — semantic mode (with LLM)
# ---------------------------------------------------------------------------


class TestContextInjectorSemantic:
    """Tests for ContextInjector with LLM-based semantic selection."""

    def test_semantic_select_with_llm(self) -> None:
        """LLM selects relevant keys from parent context."""
        llm = _make_mock_llm(
            {
                "selected_keys": ["stack", "auth_provider"],
                "reasoning": "The task is about auth, so stack and auth_provider are relevant.",
            }
        )

        injector = ContextInjector(llm_client=llm)
        result = injector.select_context(
            parent_context={
                "stack": "FastAPI",
                "auth_provider": "Auth0",
                "billing_plan": "enterprise",
                "deploy_region": "us-east-1",
            },
            subtask_description="Implement OAuth2 authentication",
        )

        assert result == {"stack": "FastAPI", "auth_provider": "Auth0"}
        # Verify LLM was called
        llm.complete_structured.assert_called_once()

    def test_semantic_select_filters_invalid_keys(self) -> None:
        """LLM-returned keys not in parent context are filtered out."""
        llm = _make_mock_llm(
            {
                "selected_keys": ["stack", "hallucinated_key"],
                "reasoning": "Selected keys.",
            }
        )

        injector = ContextInjector(llm_client=llm)
        result = injector.select_context(
            parent_context={"stack": "FastAPI", "budget": 100},
            subtask_description="Task",
        )

        assert result == {"stack": "FastAPI"}

    def test_semantic_select_all_keys_invalid_falls_back_to_full(self) -> None:
        """If LLM returns only invalid keys, fall back to full context."""
        llm = _make_mock_llm(
            {
                "selected_keys": ["nonexistent_1", "nonexistent_2"],
                "reasoning": "Bad selection.",
            }
        )

        injector = ContextInjector(llm_client=llm)
        parent = {"stack": "FastAPI", "budget": 100}
        result = injector.select_context(
            parent_context=parent,
            subtask_description="Task",
        )

        assert result == parent

    def test_semantic_select_empty_keys_falls_back_to_full(self) -> None:
        """If LLM returns empty selected_keys, fall back to full context."""
        llm = _make_mock_llm(
            {
                "selected_keys": [],
                "reasoning": "Nothing relevant.",
            }
        )

        injector = ContextInjector(llm_client=llm)
        parent = {"stack": "FastAPI"}
        result = injector.select_context(
            parent_context=parent,
            subtask_description="Task",
        )

        assert result == parent

    def test_semantic_select_non_list_falls_back_to_full(self) -> None:
        """If LLM returns non-list for selected_keys, fall back to full context."""
        llm = _make_mock_llm(
            {
                "selected_keys": "stack",  # string, not list
                "reasoning": "oops.",
            }
        )

        injector = ContextInjector(llm_client=llm)
        parent = {"stack": "FastAPI", "budget": 100}
        result = injector.select_context(
            parent_context=parent,
            subtask_description="Task",
        )

        assert result == parent

    def test_semantic_select_passes_schema(self) -> None:
        """Verify the correct schema is passed to the LLM."""
        llm = _make_mock_llm(
            {
                "selected_keys": ["stack"],
                "reasoning": "r",
            }
        )

        injector = ContextInjector(llm_client=llm)
        injector.select_context(
            parent_context={"stack": "FastAPI"},
            subtask_description="Task",
        )

        call_kwargs = llm.complete_structured.call_args
        assert call_kwargs.kwargs["schema"] == CONTEXT_SELECTION_SCHEMA
        assert call_kwargs.kwargs["schema_name"] == "context_selection"


# ---------------------------------------------------------------------------
# ContextInjector — no LLM, no required_keys (fallback)
# ---------------------------------------------------------------------------


class TestContextInjectorFallback:
    """Tests for ContextInjector when neither LLM nor required_keys are provided."""

    def test_no_llm_no_keys_returns_full_context(self) -> None:
        """Without LLM and without required_keys, returns full parent context."""
        injector = ContextInjector()
        parent = {"a": 1, "b": 2, "c": 3}
        result = injector.select_context(
            parent_context=parent,
            subtask_description="Task",
        )

        assert result == parent

    def test_no_llm_no_keys_returns_copy(self) -> None:
        """The returned dict is a copy, not a reference to parent_context."""
        injector = ContextInjector()
        parent = {"a": 1}
        result = injector.select_context(
            parent_context=parent,
            subtask_description="Task",
        )

        assert result is not parent


# ---------------------------------------------------------------------------
# ContextSummarizer — short content (no summarization)
# ---------------------------------------------------------------------------


class TestContextSummarizerShortContent:
    """Tests for ContextSummarizer when content fits within max_tokens."""

    def test_short_content_not_summarized(self) -> None:
        """Short content is returned unchanged without calling the LLM."""
        llm = _make_mock_llm(
            {
                "summary": "should not be used",
                "preserved_items": [],
                "dropped_items": [],
            }
        )

        summarizer = ContextSummarizer(llm_client=llm)
        result = summarizer.summarize(
            context_value="Short value",
            max_tokens=500,
        )

        assert result["summary"] == "Short value"
        assert result["was_summarized"] is False
        llm.complete_structured.assert_not_called()

    def test_exact_boundary_not_summarized(self) -> None:
        """Content exactly at the token limit is not summarized."""
        llm = _make_mock_llm(
            {
                "summary": "should not be used",
                "preserved_items": [],
                "dropped_items": [],
            }
        )

        # ~500 tokens = ~2000 chars (at 4 chars/token)
        content = "x" * 2000
        summarizer = ContextSummarizer(llm_client=llm)
        result = summarizer.summarize(
            context_value=content,
            max_tokens=500,
        )

        assert result["summary"] == content
        assert result["was_summarized"] is False


# ---------------------------------------------------------------------------
# ContextSummarizer — long content (summarization needed)
# ---------------------------------------------------------------------------


class TestContextSummarizerLongContent:
    """Tests for ContextSummarizer when content exceeds max_tokens."""

    def test_long_content_is_summarized(self) -> None:
        """Long content is compressed by the LLM."""
        llm = _make_mock_llm(
            {
                "summary": "Auth analysis: Auth0 wins on cost and features.",
                "preserved_items": [
                    "Auth0 recommendation",
                    "Cost comparison: Auth0 $25/mo vs Keycloak $0 (self-hosted)",
                    "Feature matrix",
                ],
                "dropped_items": [
                    "Detailed methodology description",
                    "Interview quotes",
                ],
            }
        )

        # ~750 tokens = ~3000 chars, exceeds max_tokens=100
        long_content = "A" * 3000
        summarizer = ContextSummarizer(llm_client=llm)
        result = summarizer.summarize(
            context_value=long_content,
            max_tokens=100,
            context_key="auth_analysis",
        )

        assert result["summary"] == "Auth analysis: Auth0 wins on cost and features."
        assert result["was_summarized"] is True
        assert len(result["preserved_items"]) == 3
        assert len(result["dropped_items"]) == 2

    def test_long_content_with_context_key(self) -> None:
        """Context key is passed to the LLM for better summarization."""
        llm = _make_mock_llm(
            {
                "summary": "Compressed.",
                "preserved_items": ["item"],
                "dropped_items": [],
            }
        )

        long_content = "B" * 4000
        summarizer = ContextSummarizer(llm_client=llm)
        summarizer.summarize(
            context_value=long_content,
            max_tokens=50,
            context_key="detailed_report",
        )

        # Verify the LLM was called and the user prompt includes the key name
        call_args = llm.complete_structured.call_args
        messages = call_args.kwargs["messages"]
        user_msg = messages[1]["content"]
        assert "detailed_report" in user_msg

    def test_summarization_empty_result_falls_back(self) -> None:
        """If LLM returns empty summary, falls back to original content."""
        llm = _make_mock_llm(
            {
                "summary": "",
                "preserved_items": [],
                "dropped_items": [],
            }
        )

        long_content = "C" * 4000
        summarizer = ContextSummarizer(llm_client=llm)
        result = summarizer.summarize(
            context_value=long_content,
            max_tokens=50,
        )

        assert result["summary"] == long_content
        assert result["was_summarized"] is False

    def test_summarization_passes_schema(self) -> None:
        """Verify the correct schema is passed to the LLM."""
        llm = _make_mock_llm(
            {
                "summary": "S",
                "preserved_items": [],
                "dropped_items": [],
            }
        )

        long_content = "D" * 4000
        summarizer = ContextSummarizer(llm_client=llm)
        summarizer.summarize(context_value=long_content, max_tokens=50)

        call_kwargs = llm.complete_structured.call_args
        assert call_kwargs.kwargs["schema"] == SUMMARIZATION_SCHEMA
        assert call_kwargs.kwargs["schema_name"] == "context_summarization"

    def test_summarization_max_tokens_in_system_prompt(self) -> None:
        """The max_tokens target appears in the system prompt."""
        llm = _make_mock_llm(
            {
                "summary": "S",
                "preserved_items": [],
                "dropped_items": [],
            }
        )

        long_content = "E" * 4000
        summarizer = ContextSummarizer(llm_client=llm)
        summarizer.summarize(context_value=long_content, max_tokens=200)

        call_args = llm.complete_structured.call_args
        messages = call_args.kwargs["messages"]
        system_msg = messages[0]["content"]
        assert "200" in system_msg


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


class TestTokenEstimation:
    """Tests for the _estimate_token_count helper."""

    def test_empty_string(self) -> None:
        """Empty string returns 1 (minimum)."""
        assert _estimate_token_count("") == 1

    def test_short_string(self) -> None:
        """Short string estimates correctly."""
        # 12 chars / 4 = 3 tokens
        assert _estimate_token_count("Hello world!") == 3

    def test_long_string(self) -> None:
        """Long string estimates proportionally."""
        text = "a" * 4000
        assert _estimate_token_count(text) == 1000


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestContextSchemas:
    """Verify JSON schemas have required structure."""

    @pytest.mark.parametrize(
        "schema",
        [CONTEXT_SELECTION_SCHEMA, SUMMARIZATION_SCHEMA],
    )
    def test_schema_has_required_fields(self, schema: dict[str, Any]) -> None:
        """Each schema must have type=object, properties, required, and additionalProperties."""
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema
        assert schema["additionalProperties"] is False
        for field_name in schema["required"]:
            assert (
                field_name in schema["properties"]
            ), f"Required field {field_name!r} not in properties"
