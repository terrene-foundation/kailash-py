"""
Unit tests for kaizen_agents.protocols — DelegationProtocol, ClarificationProtocol,
EscalationProtocol.

Uses mocked LLM (Tier 1 — unit tests may mock external services).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from kaizen_agents.llm import LLMClient
from kaizen_agents.orchestration.protocols.clarification import (
    CLARIFICATION_INTERPRETATION_SCHEMA,
    CLARIFICATION_QUESTION_SCHEMA,
    ClarificationProtocol,
)
from kaizen_agents.orchestration.protocols.delegation import (
    COMPLETION_PROCESSING_SCHEMA,
    DELEGATION_COMPOSITION_SCHEMA,
    DelegationProtocol,
)
from kaizen_agents.orchestration.protocols.escalation import (
    ESCALATION_COMPOSITION_SCHEMA,
    ESCALATION_DECISION_SCHEMA,
    EscalationAction,
    EscalationProtocol,
)
from kaizen_agents.types import (
    CompletionPayload,
    ConstraintEnvelope,
    make_envelope,
    EscalationPayload,
    EscalationSeverity,
    Priority,
    ResourceSnapshot,
)


# ---------------------------------------------------------------------------
# Helpers — mock LLM client
# ---------------------------------------------------------------------------


def _make_mock_llm(structured_response: dict[str, Any]) -> LLMClient:
    """Create a mock LLMClient that returns the given structured response."""
    mock = MagicMock(spec=LLMClient)
    mock.complete_structured.return_value = structured_response
    return mock


# ---------------------------------------------------------------------------
# DelegationProtocol — compose_delegation
# ---------------------------------------------------------------------------


class TestDelegationComposition:
    """Tests for DelegationProtocol.compose_delegation."""

    def test_compose_basic_delegation(self) -> None:
        """A well-formed LLM response produces a valid DelegationPayload."""
        llm = _make_mock_llm(
            {
                "task_description": (
                    "Analyze the OAuth2 providers available for the FastAPI stack. "
                    "Compare Auth0, Keycloak, and Firebase Auth on cost, features, "
                    "and integration complexity. Produce a comparison table."
                ),
                "priority_suggestion": "normal",
                "required_context_keys": ["stack", "auth_provider"],
            }
        )

        protocol = DelegationProtocol(llm_client=llm)
        envelope = make_envelope(financial={"limit": 5.0})
        context = {
            "stack": "Python/FastAPI",
            "auth_provider": "Auth0",
            "project_name": "web-app",
            "unrelated_key": "noise",
        }

        payload = protocol.compose_delegation(
            subtask_description="Analyze authentication providers",
            context=context,
            envelope=envelope,
        )

        assert "OAuth2" in payload.task_description
        assert payload.priority == Priority.NORMAL
        # Context snapshot should only contain LLM-selected keys
        assert "stack" in payload.context_snapshot
        assert "auth_provider" in payload.context_snapshot
        assert "unrelated_key" not in payload.context_snapshot
        assert payload.envelope is envelope
        assert payload.deadline is None

    def test_compose_delegation_with_deadline(self) -> None:
        """Deadline is passed through to the payload."""
        llm = _make_mock_llm(
            {
                "task_description": "Do the task urgently.",
                "priority_suggestion": "high",
                "required_context_keys": [],
            }
        )

        protocol = DelegationProtocol(llm_client=llm)
        deadline = datetime.now(timezone.utc) + timedelta(hours=1)

        payload = protocol.compose_delegation(
            subtask_description="Urgent task",
            context={},
            envelope=make_envelope(),
            deadline=deadline,
        )

        assert payload.deadline == deadline
        assert payload.priority == Priority.HIGH

    def test_compose_delegation_critical_priority(self) -> None:
        """Critical priority is correctly mapped."""
        llm = _make_mock_llm(
            {
                "task_description": "Critical system repair needed.",
                "priority_suggestion": "critical",
                "required_context_keys": ["error_log"],
            }
        )

        protocol = DelegationProtocol(llm_client=llm)
        payload = protocol.compose_delegation(
            subtask_description="Fix critical error",
            context={"error_log": "StackOverflow at line 42"},
            envelope=make_envelope(),
        )

        assert payload.priority == Priority.CRITICAL
        assert "error_log" in payload.context_snapshot

    def test_compose_delegation_low_priority(self) -> None:
        """Low priority is correctly mapped."""
        llm = _make_mock_llm(
            {
                "task_description": "Background cleanup task.",
                "priority_suggestion": "low",
                "required_context_keys": [],
            }
        )

        protocol = DelegationProtocol(llm_client=llm)
        payload = protocol.compose_delegation(
            subtask_description="Clean up temp files",
            context={},
            envelope=make_envelope(),
        )

        assert payload.priority == Priority.LOW

    def test_compose_delegation_invalid_priority_defaults_normal(self) -> None:
        """Unknown priority string falls back to NORMAL."""
        llm = _make_mock_llm(
            {
                "task_description": "Some task.",
                "priority_suggestion": "ultra_mega_priority",
                "required_context_keys": [],
            }
        )

        protocol = DelegationProtocol(llm_client=llm)
        payload = protocol.compose_delegation(
            subtask_description="Task",
            context={},
            envelope=make_envelope(),
        )

        assert payload.priority == Priority.NORMAL

    def test_compose_delegation_empty_task_falls_back(self) -> None:
        """If LLM returns empty task_description, falls back to subtask_description."""
        llm = _make_mock_llm(
            {
                "task_description": "",
                "priority_suggestion": "normal",
                "required_context_keys": [],
            }
        )

        protocol = DelegationProtocol(llm_client=llm)
        payload = protocol.compose_delegation(
            subtask_description="Original description",
            context={},
            envelope=make_envelope(),
        )

        assert payload.task_description == "Original description"

    def test_compose_delegation_passes_schema(self) -> None:
        """Verify the correct schema is passed to the LLM client."""
        llm = _make_mock_llm(
            {
                "task_description": "Task.",
                "priority_suggestion": "normal",
                "required_context_keys": [],
            }
        )

        protocol = DelegationProtocol(llm_client=llm)
        protocol.compose_delegation(
            subtask_description="Test",
            context={},
            envelope=make_envelope(),
        )

        call_kwargs = llm.complete_structured.call_args
        assert call_kwargs.kwargs["schema"] == DELEGATION_COMPOSITION_SCHEMA
        assert call_kwargs.kwargs["schema_name"] == "delegation_composition"

    def test_compose_delegation_missing_context_keys_silently_omitted(self) -> None:
        """If LLM requests a key not in context, it is silently omitted."""
        llm = _make_mock_llm(
            {
                "task_description": "Task.",
                "priority_suggestion": "normal",
                "required_context_keys": ["exists", "does_not_exist"],
            }
        )

        protocol = DelegationProtocol(llm_client=llm)
        payload = protocol.compose_delegation(
            subtask_description="Test",
            context={"exists": "value"},
            envelope=make_envelope(),
        )

        assert payload.context_snapshot == {"exists": "value"}


# ---------------------------------------------------------------------------
# DelegationProtocol — handle_completion
# ---------------------------------------------------------------------------


class TestDelegationCompletion:
    """Tests for DelegationProtocol.handle_completion."""

    def test_handle_successful_completion(self) -> None:
        """Process a successful child completion."""
        llm = _make_mock_llm(
            {
                "summary": "Child successfully analyzed the auth providers.",
                "extracted_outputs": {
                    "recommended_provider": "Auth0",
                    "cost_per_month": 25,
                },
                "quality_assessment": "complete",
                "follow_up_needed": False,
                "follow_up_reason": "",
            }
        )

        protocol = DelegationProtocol(llm_client=llm)
        completion = CompletionPayload(
            result={"provider": "Auth0", "analysis": "detailed comparison..."},
            success=True,
            context_updates={"auth_decision": "Auth0"},
            resource_consumed=ResourceSnapshot(
                financial_spent=0.50,
                actions_executed=5,
                elapsed_seconds=12.3,
            ),
        )

        result = protocol.handle_completion(
            completion=completion,
            plan_context={"project": "web-app"},
        )

        assert result["summary"] == "Child successfully analyzed the auth providers."
        assert result["extracted_outputs"]["recommended_provider"] == "Auth0"
        assert result["quality_assessment"] == "complete"
        assert result["follow_up_needed"] is False
        assert result["success"] is True
        assert result["context_updates"] == {"auth_decision": "Auth0"}

    def test_handle_failed_completion(self) -> None:
        """Process a failed child completion with follow-up needed."""
        llm = _make_mock_llm(
            {
                "summary": "Child failed to access the auth provider API.",
                "extracted_outputs": {},
                "quality_assessment": "failed",
                "follow_up_needed": True,
                "follow_up_reason": "Need to retry with different credentials.",
            }
        )

        protocol = DelegationProtocol(llm_client=llm)
        completion = CompletionPayload(
            result=None,
            success=False,
            error_detail="401 Unauthorized: invalid API key",
            resource_consumed=ResourceSnapshot(financial_spent=0.10),
        )

        result = protocol.handle_completion(
            completion=completion,
            plan_context={},
        )

        assert result["quality_assessment"] == "failed"
        assert result["follow_up_needed"] is True
        assert "credentials" in result["follow_up_reason"]
        assert result["success"] is False

    def test_handle_partial_completion(self) -> None:
        """Process a partial completion."""
        llm = _make_mock_llm(
            {
                "summary": "Child analyzed 2 of 3 providers before running out of budget.",
                "extracted_outputs": {"partial_comparison": "Auth0 vs Keycloak"},
                "quality_assessment": "partial",
                "follow_up_needed": True,
                "follow_up_reason": "Firebase Auth analysis still pending.",
            }
        )

        protocol = DelegationProtocol(llm_client=llm)
        completion = CompletionPayload(
            result={"analyzed": ["Auth0", "Keycloak"]},
            success=True,
            context_updates={"partial_result": True},
        )

        result = protocol.handle_completion(
            completion=completion,
            plan_context={},
        )

        assert result["quality_assessment"] == "partial"
        assert result["follow_up_needed"] is True

    def test_handle_completion_invalid_quality_defaults_partial(self) -> None:
        """Invalid quality_assessment falls back to 'partial'."""
        llm = _make_mock_llm(
            {
                "summary": "Done.",
                "extracted_outputs": {},
                "quality_assessment": "superb",
                "follow_up_needed": False,
                "follow_up_reason": "",
            }
        )

        protocol = DelegationProtocol(llm_client=llm)
        completion = CompletionPayload(result="ok", success=True)

        result = protocol.handle_completion(completion=completion, plan_context={})
        assert result["quality_assessment"] == "partial"

    def test_handle_completion_passes_schema(self) -> None:
        """Verify the correct schema is passed to the LLM client."""
        llm = _make_mock_llm(
            {
                "summary": "Done.",
                "extracted_outputs": {},
                "quality_assessment": "complete",
                "follow_up_needed": False,
                "follow_up_reason": "",
            }
        )

        protocol = DelegationProtocol(llm_client=llm)
        protocol.handle_completion(
            completion=CompletionPayload(result="ok", success=True),
            plan_context={},
        )

        call_kwargs = llm.complete_structured.call_args
        assert call_kwargs.kwargs["schema"] == COMPLETION_PROCESSING_SCHEMA
        assert call_kwargs.kwargs["schema_name"] == "completion_processing"


# ---------------------------------------------------------------------------
# ClarificationProtocol — compose_question
# ---------------------------------------------------------------------------


class TestClarificationQuestion:
    """Tests for ClarificationProtocol.compose_question."""

    def test_compose_blocking_question_with_options(self) -> None:
        """Compose a blocking clarification question with multiple-choice options."""
        llm = _make_mock_llm(
            {
                "question": (
                    "The task specifies 'standard auth' but the project context lists "
                    "both OAuth2 and API key authentication. Which approach should be "
                    "used for user-facing endpoints?"
                ),
                "options": ["OAuth2", "API Keys", "Both (OAuth2 for users, API keys for services)"],
                "blocking": True,
            }
        )

        protocol = ClarificationProtocol(llm_client=llm)
        payload = protocol.compose_question(
            ambiguity="Task says 'standard auth' but context has both OAuth2 and API keys",
            context={"auth_options": ["oauth2", "api_key"], "stack": "FastAPI"},
            options=["OAuth2", "API Keys"],
        )

        assert "OAuth2" in payload.question
        assert payload.blocking is True
        assert payload.is_response is False
        assert payload.options is not None
        assert len(payload.options) == 3

    def test_compose_nonblocking_open_question(self) -> None:
        """Compose a non-blocking open-ended question."""
        llm = _make_mock_llm(
            {
                "question": "What error format should the API use for validation failures?",
                "options": [],
                "blocking": False,
            }
        )

        protocol = ClarificationProtocol(llm_client=llm)
        payload = protocol.compose_question(
            ambiguity="Error response format not specified in the task",
            context={"api_style": "REST"},
        )

        assert "error format" in payload.question.lower()
        assert payload.blocking is False
        assert payload.is_response is False
        assert payload.options is None  # empty list -> None

    def test_compose_question_falls_back_on_empty_question(self) -> None:
        """If LLM returns empty question, falls back to ambiguity description."""
        llm = _make_mock_llm(
            {
                "question": "",
                "options": [],
                "blocking": True,
            }
        )

        protocol = ClarificationProtocol(llm_client=llm)
        payload = protocol.compose_question(
            ambiguity="The original ambiguity",
            context={},
        )

        assert payload.question == "The original ambiguity"

    def test_compose_question_passes_schema(self) -> None:
        """Verify the correct schema is passed to the LLM."""
        llm = _make_mock_llm(
            {
                "question": "Q?",
                "options": [],
                "blocking": False,
            }
        )

        protocol = ClarificationProtocol(llm_client=llm)
        protocol.compose_question(ambiguity="Ambiguity", context={})

        call_kwargs = llm.complete_structured.call_args
        assert call_kwargs.kwargs["schema"] == CLARIFICATION_QUESTION_SCHEMA
        assert call_kwargs.kwargs["schema_name"] == "clarification_question"


# ---------------------------------------------------------------------------
# ClarificationProtocol — interpret_response
# ---------------------------------------------------------------------------


class TestClarificationInterpretation:
    """Tests for ClarificationProtocol.interpret_response."""

    def test_interpret_clear_response(self) -> None:
        """Interpret a clear, high-confidence response."""
        llm = _make_mock_llm(
            {
                "resolved_value": "OAuth2",
                "context_updates": {
                    "auth_method": "oauth2",
                    "auth_provider": "Auth0",
                },
                "confidence": "high",
                "needs_further_clarification": False,
            }
        )

        protocol = ClarificationProtocol(llm_client=llm)
        result = protocol.interpret_response(
            response="Use OAuth2 with Auth0 for all user-facing endpoints.",
            original_question="Which auth method should be used?",
            original_options=["OAuth2", "API Keys"],
        )

        assert result["resolved_value"] == "OAuth2"
        assert result["context_updates"]["auth_method"] == "oauth2"
        assert result["confidence"] == "high"
        assert result["needs_further_clarification"] is False

    def test_interpret_ambiguous_response(self) -> None:
        """Interpret a response that introduces new ambiguity."""
        llm = _make_mock_llm(
            {
                "resolved_value": "Depends on the endpoint type",
                "context_updates": {},
                "confidence": "low",
                "needs_further_clarification": True,
            }
        )

        protocol = ClarificationProtocol(llm_client=llm)
        result = protocol.interpret_response(
            response="It depends on whether the endpoint is internal or external.",
            original_question="Which auth method?",
        )

        assert result["confidence"] == "low"
        assert result["needs_further_clarification"] is True

    def test_interpret_medium_confidence(self) -> None:
        """Interpret a response with medium confidence."""
        llm = _make_mock_llm(
            {
                "resolved_value": "JWT tokens",
                "context_updates": {"token_type": "jwt"},
                "confidence": "medium",
                "needs_further_clarification": False,
            }
        )

        protocol = ClarificationProtocol(llm_client=llm)
        result = protocol.interpret_response(
            response="Probably JWT, but check with the security team.",
            original_question="Token format?",
        )

        assert result["confidence"] == "medium"
        assert result["context_updates"]["token_type"] == "jwt"

    def test_interpret_invalid_confidence_defaults_medium(self) -> None:
        """Invalid confidence string falls back to 'medium'."""
        llm = _make_mock_llm(
            {
                "resolved_value": "answer",
                "context_updates": {},
                "confidence": "absolutely_certain",
                "needs_further_clarification": False,
            }
        )

        protocol = ClarificationProtocol(llm_client=llm)
        result = protocol.interpret_response(
            response="The answer is clear.",
            original_question="Question?",
        )

        assert result["confidence"] == "medium"

    def test_interpret_passes_schema(self) -> None:
        """Verify the correct schema is passed to the LLM."""
        llm = _make_mock_llm(
            {
                "resolved_value": "v",
                "context_updates": {},
                "confidence": "high",
                "needs_further_clarification": False,
            }
        )

        protocol = ClarificationProtocol(llm_client=llm)
        protocol.interpret_response(
            response="Answer",
            original_question="Question?",
        )

        call_kwargs = llm.complete_structured.call_args
        assert call_kwargs.kwargs["schema"] == CLARIFICATION_INTERPRETATION_SCHEMA
        assert call_kwargs.kwargs["schema_name"] == "clarification_interpretation"


# ---------------------------------------------------------------------------
# EscalationProtocol — compose_escalation
# ---------------------------------------------------------------------------


class TestEscalationComposition:
    """Tests for EscalationProtocol.compose_escalation."""

    def test_compose_blocked_escalation(self) -> None:
        """Compose a blocked escalation with mitigations tried."""
        llm = _make_mock_llm(
            {
                "problem_description": (
                    "The code search API returns 429 Too Many Requests after 3 attempts "
                    "with exponential backoff. Cannot proceed with code analysis."
                ),
                "severity": "blocked",
                "suggested_action": "Increase rate limit or switch to local file search.",
                "violating_dimension": "operational",
            }
        )

        protocol = EscalationProtocol(llm_client=llm)
        payload = protocol.compose_escalation(
            problem="Rate limit exceeded on code search API",
            mitigations_tried=["Exponential backoff", "Reduced query scope"],
            severity="blocked",
        )

        assert "429" in payload.problem_description
        assert payload.severity == EscalationSeverity.BLOCKED
        assert payload.suggested_action is not None
        assert "rate limit" in payload.suggested_action.lower()
        assert payload.violating_dimension == "operational"
        assert len(payload.attempted_mitigations) == 2

    def test_compose_budget_alert(self) -> None:
        """Compose a budget_alert escalation."""
        llm = _make_mock_llm(
            {
                "problem_description": "Spent 85% of allocated budget with 40% of work remaining.",
                "severity": "budget_alert",
                "suggested_action": "Allocate additional $2.00 to complete the task.",
                "violating_dimension": "financial",
            }
        )

        protocol = EscalationProtocol(llm_client=llm)
        payload = protocol.compose_escalation(
            problem="Budget 85% consumed, 40% work remaining",
            mitigations_tried=[],
            severity="budget_alert",
        )

        assert payload.severity == EscalationSeverity.BUDGET_ALERT
        assert payload.violating_dimension == "financial"

    def test_compose_critical_escalation(self) -> None:
        """Compose a critical escalation."""
        llm = _make_mock_llm(
            {
                "problem_description": "Database credentials are expired. All queries fail.",
                "severity": "critical",
                "suggested_action": "Rotate database credentials immediately.",
                "violating_dimension": "none",
            }
        )

        protocol = EscalationProtocol(llm_client=llm)
        payload = protocol.compose_escalation(
            problem="DB credentials expired",
            mitigations_tried=["Retried with cached credentials"],
            severity="critical",
        )

        assert payload.severity == EscalationSeverity.CRITICAL
        assert payload.violating_dimension is None  # "none" maps to None

    def test_compose_warning_escalation(self) -> None:
        """Compose a warning escalation."""
        llm = _make_mock_llm(
            {
                "problem_description": "Test coverage is below threshold but tests pass.",
                "severity": "warning",
                "suggested_action": "Consider adding more edge case tests.",
                "violating_dimension": "none",
            }
        )

        protocol = EscalationProtocol(llm_client=llm)
        payload = protocol.compose_escalation(
            problem="Low test coverage",
            mitigations_tried=[],
            severity="warning",
        )

        assert payload.severity == EscalationSeverity.WARNING

    def test_compose_escalation_empty_description_falls_back(self) -> None:
        """Empty problem_description from LLM falls back to input problem."""
        llm = _make_mock_llm(
            {
                "problem_description": "",
                "severity": "blocked",
                "suggested_action": "",
                "violating_dimension": "none",
            }
        )

        protocol = EscalationProtocol(llm_client=llm)
        payload = protocol.compose_escalation(
            problem="The original problem",
            mitigations_tried=[],
            severity="blocked",
        )

        assert payload.problem_description == "The original problem"

    def test_compose_escalation_passes_schema(self) -> None:
        """Verify the correct schema is passed to the LLM."""
        llm = _make_mock_llm(
            {
                "problem_description": "p",
                "severity": "warning",
                "suggested_action": "s",
                "violating_dimension": "none",
            }
        )

        protocol = EscalationProtocol(llm_client=llm)
        protocol.compose_escalation(
            problem="p",
            mitigations_tried=[],
            severity="warning",
        )

        call_kwargs = llm.complete_structured.call_args
        assert call_kwargs.kwargs["schema"] == ESCALATION_COMPOSITION_SCHEMA
        assert call_kwargs.kwargs["schema_name"] == "escalation_composition"


# ---------------------------------------------------------------------------
# EscalationProtocol — decide_action
# ---------------------------------------------------------------------------


class TestEscalationDecision:
    """Tests for EscalationProtocol.decide_action."""

    def test_decide_retry(self) -> None:
        """LLM recommends retry with modifications."""
        llm = _make_mock_llm(
            {
                "action": "retry",
                "reasoning": "The failure was transient (rate limit). Backoff should resolve it.",
                "retry_modifications": "Increase backoff delay to 30 seconds.",
                "recompose_hints": "",
            }
        )

        protocol = EscalationProtocol(llm_client=llm)
        escalation = EscalationPayload(
            severity=EscalationSeverity.BLOCKED,
            problem_description="Rate limit exceeded",
            attempted_mitigations=["5s backoff"],
        )

        action, details = protocol.decide_action(
            escalation=escalation,
            parent_context={"retry_budget": 2},
        )

        assert action == EscalationAction.RETRY
        assert "transient" in details["reasoning"]
        assert "30 seconds" in details["retry_modifications"]

    def test_decide_recompose(self) -> None:
        """LLM recommends recomposing the approach."""
        llm = _make_mock_llm(
            {
                "action": "recompose",
                "reasoning": "The current approach requires an API that is unavailable.",
                "retry_modifications": "",
                "recompose_hints": "Use local file search instead of the cloud API.",
            }
        )

        protocol = EscalationProtocol(llm_client=llm)
        escalation = EscalationPayload(
            severity=EscalationSeverity.BLOCKED,
            problem_description="API unavailable",
            attempted_mitigations=["Retried 3 times", "Tried alternate endpoint"],
        )

        action, details = protocol.decide_action(
            escalation=escalation,
            parent_context={},
        )

        assert action == EscalationAction.RECOMPOSE
        assert "local file search" in details["recompose_hints"]

    def test_decide_escalate_further(self) -> None:
        """LLM recommends escalating further up the hierarchy."""
        llm = _make_mock_llm(
            {
                "action": "escalate_further",
                "reasoning": "Parent also lacks the budget to resolve this. Grandparent must decide.",
                "retry_modifications": "",
                "recompose_hints": "",
            }
        )

        protocol = EscalationProtocol(llm_client=llm)
        escalation = EscalationPayload(
            severity=EscalationSeverity.CRITICAL,
            problem_description="Budget exhausted at all levels",
            attempted_mitigations=["Reduced scope", "Requested more budget from parent"],
        )

        action, details = protocol.decide_action(
            escalation=escalation,
            parent_context={"budget_remaining": 0},
        )

        assert action == EscalationAction.ESCALATE_FURTHER

    def test_decide_abandon(self) -> None:
        """LLM recommends abandoning the subtask."""
        llm = _make_mock_llm(
            {
                "action": "abandon",
                "reasoning": "The subtask is optional and all mitigation attempts failed.",
                "retry_modifications": "",
                "recompose_hints": "",
            }
        )

        protocol = EscalationProtocol(llm_client=llm)
        escalation = EscalationPayload(
            severity=EscalationSeverity.BLOCKED,
            problem_description="Optional subtask cannot complete",
            attempted_mitigations=["Attempt 1", "Attempt 2", "Attempt 3"],
            suggested_action="Skip this subtask",
        )

        action, details = protocol.decide_action(
            escalation=escalation,
            parent_context={"subtask_optional": True},
        )

        assert action == EscalationAction.ABANDON
        assert "optional" in details["reasoning"].lower()

    def test_decide_unknown_action_defaults_escalate_further(self) -> None:
        """Unknown action string from LLM defaults to ESCALATE_FURTHER."""
        llm = _make_mock_llm(
            {
                "action": "do_magic",
                "reasoning": "Magic.",
                "retry_modifications": "",
                "recompose_hints": "",
            }
        )

        protocol = EscalationProtocol(llm_client=llm)
        escalation = EscalationPayload(
            severity=EscalationSeverity.WARNING,
            problem_description="Minor issue",
        )

        action, _ = protocol.decide_action(
            escalation=escalation,
            parent_context={},
        )

        assert action == EscalationAction.ESCALATE_FURTHER

    def test_decide_action_passes_schema(self) -> None:
        """Verify the correct schema is passed to the LLM."""
        llm = _make_mock_llm(
            {
                "action": "retry",
                "reasoning": "r",
                "retry_modifications": "m",
                "recompose_hints": "",
            }
        )

        protocol = EscalationProtocol(llm_client=llm)
        protocol.decide_action(
            escalation=EscalationPayload(
                severity=EscalationSeverity.BLOCKED,
                problem_description="p",
            ),
            parent_context={},
        )

        call_kwargs = llm.complete_structured.call_args
        assert call_kwargs.kwargs["schema"] == ESCALATION_DECISION_SCHEMA
        assert call_kwargs.kwargs["schema_name"] == "escalation_decision"


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestSchemas:
    """Verify that JSON schemas have the required structure for OpenAI structured outputs."""

    @pytest.mark.parametrize(
        "schema",
        [
            DELEGATION_COMPOSITION_SCHEMA,
            COMPLETION_PROCESSING_SCHEMA,
            CLARIFICATION_QUESTION_SCHEMA,
            CLARIFICATION_INTERPRETATION_SCHEMA,
            ESCALATION_COMPOSITION_SCHEMA,
            ESCALATION_DECISION_SCHEMA,
        ],
    )
    def test_schema_has_required_fields(self, schema: dict[str, Any]) -> None:
        """Each schema must have type=object, properties, required, and additionalProperties."""
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema
        assert schema.get("additionalProperties") is False or schema.get(
            "additionalProperties"
        ) == {"type": "string"}
        # All required fields must exist in properties
        for field_name in schema["required"]:
            assert (
                field_name in schema["properties"]
            ), f"Required field {field_name!r} not in properties"
