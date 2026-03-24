"""
Unit tests for kaizen_agents.planner.decomposer — TaskDecomposer.

Uses mocked LLM (Tier 1 — unit tests may mock external services).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from kaizen_agents.llm import LLMClient
from kaizen_agents.orchestration.planner.decomposer import (
    DECOMPOSITION_SCHEMA,
    Subtask,
    TaskDecomposer,
    _build_system_prompt,
    _build_user_prompt,
)
from kaizen_agents.types import ConstraintEnvelope, make_envelope


# ---------------------------------------------------------------------------
# Helpers — mock LLM client
# ---------------------------------------------------------------------------


def _make_mock_llm(structured_response: dict[str, Any]) -> LLMClient:
    """Create a mock LLMClient that returns the given structured response."""
    mock = MagicMock(spec=LLMClient)
    mock.complete_structured.return_value = structured_response
    return mock


def _valid_decomposition() -> dict[str, Any]:
    """A well-formed decomposition response with three subtasks."""
    return {
        "subtasks": [
            {
                "description": "Research authentication providers (OAuth2, SAML, OIDC)",
                "estimated_complexity": 2,
                "required_capabilities": ["web-search", "documentation-review"],
                "suggested_tools": ["web_browser", "file_read"],
                "depends_on": [],
                "output_keys": ["provider_comparison"],
            },
            {
                "description": "Implement authentication middleware with chosen provider",
                "estimated_complexity": 4,
                "required_capabilities": ["code-writing", "security-review"],
                "suggested_tools": ["file_write", "code_search"],
                "depends_on": [0],
                "output_keys": ["auth_middleware", "auth_config"],
            },
            {
                "description": "Write integration tests for the authentication flow",
                "estimated_complexity": 3,
                "required_capabilities": ["testing", "code-writing"],
                "suggested_tools": ["file_write", "test_runner"],
                "depends_on": [1],
                "output_keys": ["test_results"],
            },
        ]
    }


# ---------------------------------------------------------------------------
# Subtask dataclass
# ---------------------------------------------------------------------------


class TestSubtask:
    def test_construction(self) -> None:
        s = Subtask(
            description="Do the thing",
            estimated_complexity=3,
            required_capabilities=["cap1"],
            suggested_tools=["tool1"],
            depends_on=[0],
            output_keys=["result"],
        )
        assert s.description == "Do the thing"
        assert s.estimated_complexity == 3
        assert s.required_capabilities == ["cap1"]
        assert s.depends_on == [0]

    def test_defaults(self) -> None:
        s = Subtask(description="Minimal", estimated_complexity=1)
        assert s.required_capabilities == []
        assert s.suggested_tools == []
        assert s.depends_on == []
        assert s.output_keys == []


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


class TestPromptBuilding:
    def test_system_prompt_includes_constraint_info(self) -> None:
        envelope = make_envelope(
            financial={"limit": 5.0},
            operational={"allowed": ["read"], "blocked": ["delete"]},
        )
        prompt = _build_system_prompt(envelope)
        assert "$5.0" in prompt
        assert "delete" in prompt
        assert "read" in prompt

    def test_system_prompt_default_envelope(self) -> None:
        prompt = _build_system_prompt(make_envelope())
        assert "task decomposition engine" in prompt.lower()

    def test_user_prompt_includes_objective(self) -> None:
        prompt = _build_user_prompt("Build a REST API", {})
        assert "Build a REST API" in prompt

    def test_user_prompt_includes_context(self) -> None:
        prompt = _build_user_prompt(
            "Build a REST API",
            {"stack": "FastAPI", "database": "PostgreSQL"},
        )
        assert "FastAPI" in prompt
        assert "PostgreSQL" in prompt

    def test_user_prompt_empty_context(self) -> None:
        prompt = _build_user_prompt("Do something", {})
        assert "Context" not in prompt

    def test_system_prompt_with_data_ceiling(self) -> None:
        from kailash.trust import ConfidentialityLevel
        from kailash.trust.pact.config import ConstraintEnvelopeConfig

        envelope = ConstraintEnvelopeConfig(
            id="test-ceiling",
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        )
        prompt = _build_system_prompt(envelope)
        assert "confidential" in prompt


# ---------------------------------------------------------------------------
# TaskDecomposer.decompose
# ---------------------------------------------------------------------------


class TestTaskDecomposer:
    def test_basic_decomposition(self) -> None:
        mock_llm = _make_mock_llm(_valid_decomposition())
        decomposer = TaskDecomposer(llm_client=mock_llm)

        subtasks = decomposer.decompose(
            objective="Implement user authentication",
            context={"stack": "Python/FastAPI"},
        )

        assert len(subtasks) == 3
        assert subtasks[0].description == "Research authentication providers (OAuth2, SAML, OIDC)"
        assert subtasks[0].estimated_complexity == 2
        assert subtasks[0].depends_on == []
        assert subtasks[1].depends_on == [0]
        assert subtasks[2].depends_on == [1]

    def test_passes_envelope_to_system_prompt(self) -> None:
        mock_llm = _make_mock_llm(_valid_decomposition())
        decomposer = TaskDecomposer(llm_client=mock_llm)
        envelope = make_envelope(financial={"limit": 50.0})

        decomposer.decompose(
            objective="Build something",
            envelope=envelope,
        )

        # Verify the LLM was called with structured output
        mock_llm.complete_structured.assert_called_once()
        call_args = mock_llm.complete_structured.call_args
        messages = (
            call_args.kwargs.get("messages") or call_args[1].get("messages") or call_args[0][0]
        )
        system_msg = messages[0]["content"]
        assert "$50.0" in system_msg

    def test_uses_correct_schema(self) -> None:
        mock_llm = _make_mock_llm(_valid_decomposition())
        decomposer = TaskDecomposer(llm_client=mock_llm)

        decomposer.decompose(objective="Do something")

        call_args = mock_llm.complete_structured.call_args
        schema = call_args.kwargs.get("schema") or call_args[1].get("schema")
        assert schema == DECOMPOSITION_SCHEMA

    def test_default_envelope_when_none_provided(self) -> None:
        mock_llm = _make_mock_llm(_valid_decomposition())
        decomposer = TaskDecomposer(llm_client=mock_llm)

        subtasks = decomposer.decompose(objective="Do something")
        assert len(subtasks) == 3  # Uses default envelope, still works

    def test_default_context_when_none_provided(self) -> None:
        mock_llm = _make_mock_llm(_valid_decomposition())
        decomposer = TaskDecomposer(llm_client=mock_llm)

        subtasks = decomposer.decompose(objective="Do something")
        assert len(subtasks) == 3


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestDecomposerValidation:
    def test_empty_subtasks_raises(self) -> None:
        mock_llm = _make_mock_llm({"subtasks": []})
        decomposer = TaskDecomposer(llm_client=mock_llm)

        with pytest.raises(ValueError, match="zero subtasks"):
            decomposer.decompose(objective="Do something")

    def test_subtasks_not_list_raises(self) -> None:
        mock_llm = _make_mock_llm({"subtasks": "not_a_list"})
        decomposer = TaskDecomposer(llm_client=mock_llm)

        with pytest.raises(ValueError, match="Expected 'subtasks' to be a list"):
            decomposer.decompose(objective="Do something")

    def test_subtask_not_dict_raises(self) -> None:
        mock_llm = _make_mock_llm({"subtasks": ["not_a_dict"]})
        decomposer = TaskDecomposer(llm_client=mock_llm)

        with pytest.raises(ValueError, match="not a dict"):
            decomposer.decompose(objective="Do something")

    def test_empty_description_raises(self) -> None:
        mock_llm = _make_mock_llm(
            {
                "subtasks": [
                    {
                        "description": "",
                        "estimated_complexity": 1,
                        "required_capabilities": [],
                        "suggested_tools": [],
                        "depends_on": [],
                        "output_keys": [],
                    }
                ]
            }
        )
        decomposer = TaskDecomposer(llm_client=mock_llm)

        with pytest.raises(ValueError, match="invalid or empty description"):
            decomposer.decompose(objective="Do something")

    def test_complexity_clamped_to_valid_range(self) -> None:
        mock_llm = _make_mock_llm(
            {
                "subtasks": [
                    {
                        "description": "Valid task",
                        "estimated_complexity": 10,  # Out of range, should be clamped to 5
                        "required_capabilities": [],
                        "suggested_tools": [],
                        "depends_on": [],
                        "output_keys": [],
                    }
                ]
            }
        )
        decomposer = TaskDecomposer(llm_client=mock_llm)
        subtasks = decomposer.decompose(objective="Do something")
        assert subtasks[0].estimated_complexity == 5

    def test_complexity_clamped_minimum(self) -> None:
        mock_llm = _make_mock_llm(
            {
                "subtasks": [
                    {
                        "description": "Valid task",
                        "estimated_complexity": -1,
                        "required_capabilities": [],
                        "suggested_tools": [],
                        "depends_on": [],
                        "output_keys": [],
                    }
                ]
            }
        )
        decomposer = TaskDecomposer(llm_client=mock_llm)
        subtasks = decomposer.decompose(objective="Do something")
        assert subtasks[0].estimated_complexity == 1

    def test_self_referencing_dependency_removed(self) -> None:
        mock_llm = _make_mock_llm(
            {
                "subtasks": [
                    {
                        "description": "Self-referencing task",
                        "estimated_complexity": 2,
                        "required_capabilities": [],
                        "suggested_tools": [],
                        "depends_on": [0],  # Self-reference
                        "output_keys": [],
                    }
                ]
            }
        )
        decomposer = TaskDecomposer(llm_client=mock_llm)
        subtasks = decomposer.decompose(objective="Do something")
        assert subtasks[0].depends_on == []  # Self-reference removed

    def test_out_of_range_dependency_removed(self) -> None:
        mock_llm = _make_mock_llm(
            {
                "subtasks": [
                    {
                        "description": "Task with bad dep",
                        "estimated_complexity": 2,
                        "required_capabilities": [],
                        "suggested_tools": [],
                        "depends_on": [99],  # Out of range
                        "output_keys": [],
                    }
                ]
            }
        )
        decomposer = TaskDecomposer(llm_client=mock_llm)
        subtasks = decomposer.decompose(objective="Do something")
        assert subtasks[0].depends_on == []

    def test_circular_dependency_raises(self) -> None:
        mock_llm = _make_mock_llm(
            {
                "subtasks": [
                    {
                        "description": "Task A",
                        "estimated_complexity": 2,
                        "required_capabilities": [],
                        "suggested_tools": [],
                        "depends_on": [1],
                        "output_keys": [],
                    },
                    {
                        "description": "Task B",
                        "estimated_complexity": 2,
                        "required_capabilities": [],
                        "suggested_tools": [],
                        "depends_on": [0],
                        "output_keys": [],
                    },
                ]
            }
        )
        decomposer = TaskDecomposer(llm_client=mock_llm)

        with pytest.raises(ValueError, match="Circular dependency"):
            decomposer.decompose(objective="Do something")

    def test_no_root_subtask_raises(self) -> None:
        # Three tasks forming a chain where every task has a dependency
        # but with a cycle removed by validation, there should be a root.
        # This test creates a valid DAG where everything depends on something.
        mock_llm = _make_mock_llm(
            {
                "subtasks": [
                    {
                        "description": "Task A depends on B",
                        "estimated_complexity": 2,
                        "required_capabilities": [],
                        "suggested_tools": [],
                        "depends_on": [1],
                        "output_keys": [],
                    },
                    {
                        "description": "Task B depends on A — but after cycle detection this is valid DAG",
                        "estimated_complexity": 2,
                        "required_capabilities": [],
                        "suggested_tools": [],
                        "depends_on": [2],
                        "output_keys": [],
                    },
                    {
                        "description": "Task C depends on A",
                        "estimated_complexity": 2,
                        "required_capabilities": [],
                        "suggested_tools": [],
                        "depends_on": [0],
                        "output_keys": [],
                    },
                ]
            }
        )
        decomposer = TaskDecomposer(llm_client=mock_llm)
        # This forms a cycle: 0->1->2->0, which should raise
        with pytest.raises(ValueError, match="Circular dependency"):
            decomposer.decompose(objective="Do something")

    def test_non_list_capabilities_treated_as_empty(self) -> None:
        mock_llm = _make_mock_llm(
            {
                "subtasks": [
                    {
                        "description": "Valid task",
                        "estimated_complexity": 1,
                        "required_capabilities": "not_a_list",
                        "suggested_tools": [],
                        "depends_on": [],
                        "output_keys": [],
                    }
                ]
            }
        )
        decomposer = TaskDecomposer(llm_client=mock_llm)
        subtasks = decomposer.decompose(objective="Do something")
        assert subtasks[0].required_capabilities == []

    def test_non_list_depends_on_treated_as_empty(self) -> None:
        mock_llm = _make_mock_llm(
            {
                "subtasks": [
                    {
                        "description": "Valid task",
                        "estimated_complexity": 1,
                        "required_capabilities": [],
                        "suggested_tools": [],
                        "depends_on": "not_a_list",
                        "output_keys": [],
                    }
                ]
            }
        )
        decomposer = TaskDecomposer(llm_client=mock_llm)
        subtasks = decomposer.decompose(objective="Do something")
        assert subtasks[0].depends_on == []


# ---------------------------------------------------------------------------
# Schema structure
# ---------------------------------------------------------------------------


class TestDecompositionSchema:
    def test_schema_is_valid_json_schema(self) -> None:
        assert DECOMPOSITION_SCHEMA["type"] == "object"
        assert "subtasks" in DECOMPOSITION_SCHEMA["properties"]
        assert DECOMPOSITION_SCHEMA["required"] == ["subtasks"]

    def test_subtask_schema_has_required_fields(self) -> None:
        subtask_schema = DECOMPOSITION_SCHEMA["properties"]["subtasks"]["items"]
        required = subtask_schema["required"]
        assert "description" in required
        assert "estimated_complexity" in required
        assert "required_capabilities" in required
        assert "suggested_tools" in required
        assert "depends_on" in required
        assert "output_keys" in required
