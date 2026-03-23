"""
Unit tests for kaizen_agents.planner.designer — AgentDesigner, CapabilityMatcher, SpawnPolicy.

Uses mocked LLM (Tier 1 — unit tests may mock external services).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from kaizen_agents.llm import LLMClient
from kaizen_agents.orchestration.planner.decomposer import Subtask
from kaizen_agents.orchestration.planner.designer import (
    AGENT_DESIGN_SCHEMA,
    AgentDesigner,
    CapabilityMatch,
    CapabilityMatcher,
    SpawnDecision,
    SpawnPolicy,
)
from kaizen_agents.types import AgentSpec, ConstraintEnvelope, MemoryConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_llm(structured_response: dict[str, Any]) -> LLMClient:
    """Create a mock LLMClient that returns a structured response."""
    mock = MagicMock(spec=LLMClient)
    mock.complete_structured.return_value = structured_response
    return mock


def _sample_subtask(
    description: str = "Review code for security issues",
    complexity: int = 3,
    capabilities: list[str] | None = None,
    tools: list[str] | None = None,
    depends_on: list[int] | None = None,
    output_keys: list[str] | None = None,
) -> Subtask:
    """Create a sample subtask for testing."""
    return Subtask(
        description=description,
        estimated_complexity=complexity,
        required_capabilities=(
            capabilities if capabilities is not None else ["code-review", "security-analysis"]
        ),
        suggested_tools=tools if tools is not None else ["code_search", "file_read"],
        depends_on=depends_on if depends_on is not None else [],
        output_keys=output_keys if output_keys is not None else ["review_result"],
    )


def _sample_spec(
    spec_id: str = "existing-001",
    name: str = "Code Reviewer",
    capabilities: list[str] | None = None,
    tool_ids: list[str] | None = None,
) -> AgentSpec:
    """Create a sample AgentSpec for the registry."""
    return AgentSpec(
        spec_id=spec_id,
        name=name,
        description="Reviews code for issues.",
        capabilities=capabilities or ["code-review", "security-analysis"],
        tool_ids=tool_ids or ["code_search", "file_read"],
        envelope=ConstraintEnvelope(financial={"limit": 5.0}),
        memory_config=MemoryConfig(session=True),
    )


def _sample_llm_design_response() -> dict[str, Any]:
    """LLM response for agent design."""
    return {
        "name": "Security Reviewer",
        "description": "Performs security-focused code review.",
        "capabilities": ["code-review", "security-analysis", "vulnerability-detection"],
        "selected_tools": ["code_search", "file_read"],
        "financial_ratio": 0.15,
        "needs_shared_memory": False,
        "needs_persistent_memory": True,
        "produced_context_keys": ["security_report"],
    }


# ---------------------------------------------------------------------------
# CapabilityMatcher — exact matching
# ---------------------------------------------------------------------------


class TestCapabilityMatcher:
    def test_empty_registry_returns_no_matches(self) -> None:
        matcher = CapabilityMatcher()
        matches = matcher.find_matches(["code-review"])
        assert matches == []

    def test_empty_requirements_returns_no_matches(self) -> None:
        matcher = CapabilityMatcher(known_specs=[_sample_spec()])
        matches = matcher.find_matches([])
        assert matches == []

    def test_exact_full_match(self) -> None:
        spec = _sample_spec(capabilities=["code-review", "security-analysis"])
        matcher = CapabilityMatcher(known_specs=[spec])

        matches = matcher.find_matches(["code-review", "security-analysis"])
        assert len(matches) == 1
        assert matches[0].match_score == 1.0
        assert matches[0].unmatched_capabilities == []

    def test_partial_match(self) -> None:
        spec = _sample_spec(capabilities=["code-review"])
        matcher = CapabilityMatcher(known_specs=[spec])

        matches = matcher.find_matches(
            ["code-review", "security-analysis"],
            min_score=0.4,
        )
        assert len(matches) == 1
        assert matches[0].match_score == 0.5
        assert "security-analysis" in matches[0].unmatched_capabilities

    def test_no_match_below_threshold(self) -> None:
        spec = _sample_spec(capabilities=["testing"])
        matcher = CapabilityMatcher(known_specs=[spec])

        matches = matcher.find_matches(
            ["code-review", "security-analysis"],
            min_score=0.5,
        )
        assert matches == []

    def test_multiple_specs_sorted_by_score(self) -> None:
        spec_full = _sample_spec(
            spec_id="full",
            capabilities=["code-review", "security-analysis"],
        )
        spec_partial = _sample_spec(
            spec_id="partial",
            capabilities=["code-review"],
        )
        matcher = CapabilityMatcher(known_specs=[spec_partial, spec_full])

        matches = matcher.find_matches(
            ["code-review", "security-analysis"],
            min_score=0.4,
        )
        assert len(matches) == 2
        assert matches[0].spec.spec_id == "full"
        assert matches[1].spec.spec_id == "partial"

    def test_register_adds_spec(self) -> None:
        matcher = CapabilityMatcher()
        spec = _sample_spec()
        matcher.register(spec)

        matches = matcher.find_matches(["code-review"])
        assert len(matches) == 1


# ---------------------------------------------------------------------------
# CapabilityMatcher — semantic matching
# ---------------------------------------------------------------------------


class TestCapabilityMatcherSemantic:
    def test_falls_back_to_exact_without_llm(self) -> None:
        spec = _sample_spec(capabilities=["code-review"])
        matcher = CapabilityMatcher(known_specs=[spec])

        matches = matcher.find_semantic_matches(
            ["code-review"],
            min_score=0.5,
        )
        assert len(matches) == 1

    def test_semantic_match_with_llm(self) -> None:
        llm_response = {
            "matches": [
                {
                    "required_capability": "static-analysis",
                    "is_covered": True,
                    "matched_by": "code-review",
                },
                {
                    "required_capability": "pen-testing",
                    "is_covered": False,
                    "matched_by": "",
                },
            ]
        }
        mock_llm = _make_mock_llm(llm_response)
        spec = _sample_spec(capabilities=["code-review", "security-analysis"])
        matcher = CapabilityMatcher(known_specs=[spec], llm_client=mock_llm)

        matches = matcher.find_semantic_matches(
            ["static-analysis", "pen-testing"],
            min_score=0.4,
        )
        assert len(matches) == 1
        assert "static-analysis" in matches[0].matched_capabilities
        assert "pen-testing" in matches[0].unmatched_capabilities
        assert matches[0].match_score == 0.5

    def test_semantic_empty_registry(self) -> None:
        mock_llm = _make_mock_llm({"matches": []})
        matcher = CapabilityMatcher(llm_client=mock_llm)
        matches = matcher.find_semantic_matches(["anything"])
        assert matches == []

    def test_semantic_empty_requirements(self) -> None:
        mock_llm = _make_mock_llm({"matches": []})
        matcher = CapabilityMatcher(known_specs=[_sample_spec()], llm_client=mock_llm)
        matches = matcher.find_semantic_matches([])
        assert matches == []

    def test_semantic_spec_with_no_capabilities_skipped(self) -> None:
        mock_llm = _make_mock_llm({"matches": []})
        spec_no_caps = _sample_spec(capabilities=[])
        matcher = CapabilityMatcher(known_specs=[spec_no_caps], llm_client=mock_llm)
        matches = matcher.find_semantic_matches(["code-review"])
        assert matches == []


# ---------------------------------------------------------------------------
# SpawnPolicy
# ---------------------------------------------------------------------------


class TestSpawnPolicy:
    def test_high_complexity_spawns(self) -> None:
        policy = SpawnPolicy(complexity_threshold=3)
        subtask = _sample_subtask(complexity=4)
        decision = policy.evaluate(subtask, ConstraintEnvelope())

        assert decision.should_spawn is True
        assert "Complexity 4" in decision.reason

    def test_low_complexity_inlines(self) -> None:
        policy = SpawnPolicy(complexity_threshold=3)
        subtask = _sample_subtask(complexity=1, tools=[])
        decision = policy.evaluate(subtask, ConstraintEnvelope())

        assert decision.should_spawn is False
        assert "below threshold" in decision.reason

    def test_many_tools_spawns(self) -> None:
        policy = SpawnPolicy(complexity_threshold=5, tool_count_threshold=2)
        subtask = _sample_subtask(complexity=2, tools=["a", "b", "c"])
        decision = policy.evaluate(subtask, ConstraintEnvelope())

        assert decision.should_spawn is True
        assert "tools" in decision.reason.lower()

    def test_tight_budget_inlines(self) -> None:
        policy = SpawnPolicy(budget_threshold=5.0)
        subtask = _sample_subtask(complexity=4)
        envelope = ConstraintEnvelope(financial={"limit": 1.0})
        decision = policy.evaluate(subtask, envelope)

        assert decision.should_spawn is False
        assert "budget" in decision.reason.lower()

    def test_matching_spec_spawns(self) -> None:
        policy = SpawnPolicy(complexity_threshold=5, tool_count_threshold=10)
        subtask = _sample_subtask(complexity=2, tools=["a"])
        decision = policy.evaluate(subtask, ConstraintEnvelope(), has_matching_spec=True)

        assert decision.should_spawn is True
        assert "reuse" in decision.reason.lower()

    def test_repr(self) -> None:
        decision = SpawnDecision(SpawnDecision.SPAWN, "test reason")
        assert "spawn" in repr(decision)
        assert "test reason" in repr(decision)


# ---------------------------------------------------------------------------
# AgentDesigner — LLM-driven spec generation
# ---------------------------------------------------------------------------


class TestAgentDesigner:
    def test_generates_new_spec_from_llm(self) -> None:
        mock_llm = _make_mock_llm(_sample_llm_design_response())
        designer = AgentDesigner(llm_client=mock_llm)

        subtask = _sample_subtask()
        envelope = ConstraintEnvelope(financial={"limit": 100.0})
        available_tools = ["code_search", "file_read", "file_write", "web_browser"]

        spec, decision = designer.design(subtask, envelope, available_tools)

        assert spec.name == "Security Reviewer"
        assert "code-review" in spec.capabilities
        assert "code_search" in spec.tool_ids
        assert "file_read" in spec.tool_ids
        assert spec.envelope.financial["limit"] <= 100.0
        assert spec.memory_config.persistent is True

    def test_filters_unavailable_tools(self) -> None:
        response = _sample_llm_design_response()
        response["selected_tools"] = ["code_search", "nonexistent_tool"]
        mock_llm = _make_mock_llm(response)
        designer = AgentDesigner(llm_client=mock_llm)

        subtask = _sample_subtask()
        envelope = ConstraintEnvelope(financial={"limit": 100.0})
        available_tools = ["code_search", "file_read"]

        spec, _ = designer.design(subtask, envelope, available_tools)
        assert "nonexistent_tool" not in spec.tool_ids
        assert "code_search" in spec.tool_ids

    def test_financial_ratio_clamped(self) -> None:
        response = _sample_llm_design_response()
        response["financial_ratio"] = 0.99  # Over the 0.5 max
        mock_llm = _make_mock_llm(response)
        designer = AgentDesigner(llm_client=mock_llm)

        subtask = _sample_subtask()
        envelope = ConstraintEnvelope(financial={"limit": 100.0})

        spec, _ = designer.design(subtask, envelope, [])
        # 0.5 * 100 = 50.0 max
        assert spec.envelope.financial["limit"] <= 50.0

    def test_child_envelope_is_tighter_than_parent(self) -> None:
        mock_llm = _make_mock_llm(_sample_llm_design_response())
        designer = AgentDesigner(llm_client=mock_llm)

        subtask = _sample_subtask()
        parent_envelope = ConstraintEnvelope(
            financial={"limit": 100.0},
            operational={"allowed": ["read", "write"], "blocked": ["delete"]},
        )

        spec, _ = designer.design(subtask, parent_envelope, ["code_search"])
        assert spec.envelope.financial["limit"] <= 100.0
        assert "delete" in spec.envelope.operational["blocked"]

    def test_uses_agent_design_schema(self) -> None:
        mock_llm = _make_mock_llm(_sample_llm_design_response())
        designer = AgentDesigner(llm_client=mock_llm)
        subtask = _sample_subtask()

        designer.design(subtask, ConstraintEnvelope(), [])

        call_args = mock_llm.complete_structured.call_args
        schema = call_args.kwargs.get("schema") or call_args[1].get("schema")
        assert schema == AGENT_DESIGN_SCHEMA

    def test_spec_has_metadata(self) -> None:
        mock_llm = _make_mock_llm(_sample_llm_design_response())
        designer = AgentDesigner(llm_client=mock_llm)

        subtask = _sample_subtask(complexity=4)
        spec, _ = designer.design(subtask, ConstraintEnvelope(), [])

        assert spec.metadata.get("generated_by") == "agent_designer"
        assert spec.metadata.get("subtask_complexity") == 4


# ---------------------------------------------------------------------------
# AgentDesigner — adapts existing specs
# ---------------------------------------------------------------------------


class TestAgentDesignerWithExistingSpecs:
    def test_reuses_existing_spec_on_full_match(self) -> None:
        """When an existing spec covers all required capabilities, it is adapted."""
        mock_llm = _make_mock_llm(_sample_llm_design_response())
        existing_spec = _sample_spec(
            capabilities=["code-review", "security-analysis"],
            tool_ids=["code_search", "file_read"],
        )
        matcher = CapabilityMatcher(known_specs=[existing_spec])
        designer = AgentDesigner(
            llm_client=mock_llm,
            capability_matcher=matcher,
        )

        subtask = _sample_subtask(capabilities=["code-review", "security-analysis"])
        envelope = ConstraintEnvelope(financial={"limit": 100.0})
        available_tools = ["code_search", "file_read", "file_write"]

        spec, decision = designer.design(subtask, envelope, available_tools)

        # Should adapt existing spec, not call LLM
        mock_llm.complete_structured.assert_not_called()
        assert spec.name == "Code Reviewer"  # From existing spec
        assert "code_search" in spec.tool_ids
        assert spec.metadata.get("adapted_from") == "existing-001"

    def test_adapted_spec_filters_unavailable_tools(self) -> None:
        mock_llm = _make_mock_llm(_sample_llm_design_response())
        existing_spec = _sample_spec(
            capabilities=["code-review", "security-analysis"],
            tool_ids=["code_search", "file_read", "missing_tool"],
        )
        matcher = CapabilityMatcher(known_specs=[existing_spec])
        designer = AgentDesigner(llm_client=mock_llm, capability_matcher=matcher)

        subtask = _sample_subtask(capabilities=["code-review", "security-analysis"])
        available_tools = ["code_search", "file_read"]

        spec, _ = designer.design(subtask, ConstraintEnvelope(), available_tools)
        assert "missing_tool" not in spec.tool_ids

    def test_adapted_spec_adds_suggested_tools(self) -> None:
        mock_llm = _make_mock_llm(_sample_llm_design_response())
        existing_spec = _sample_spec(
            capabilities=["code-review", "security-analysis"],
            tool_ids=["code_search"],
        )
        matcher = CapabilityMatcher(known_specs=[existing_spec])
        designer = AgentDesigner(llm_client=mock_llm, capability_matcher=matcher)

        subtask = _sample_subtask(
            capabilities=["code-review", "security-analysis"],
            tools=["code_search", "file_read"],
        )
        available_tools = ["code_search", "file_read", "file_write"]

        spec, _ = designer.design(subtask, ConstraintEnvelope(), available_tools)
        assert "file_read" in spec.tool_ids

    def test_falls_through_to_llm_on_partial_match(self) -> None:
        """When no spec covers all capabilities, the LLM generates a new one."""
        mock_llm = _make_mock_llm(_sample_llm_design_response())
        existing_spec = _sample_spec(capabilities=["testing"])  # Doesn't match
        matcher = CapabilityMatcher(known_specs=[existing_spec])
        designer = AgentDesigner(llm_client=mock_llm, capability_matcher=matcher)

        subtask = _sample_subtask(capabilities=["code-review", "security-analysis"])

        spec, _ = designer.design(subtask, ConstraintEnvelope(), ["code_search"])
        mock_llm.complete_structured.assert_called_once()
        assert spec.name == "Security Reviewer"  # From LLM


# ---------------------------------------------------------------------------
# Envelope tightening
# ---------------------------------------------------------------------------


class TestEnvelopeTightening:
    def test_child_financial_is_fraction_of_parent(self) -> None:
        mock_llm = _make_mock_llm(_sample_llm_design_response())
        designer = AgentDesigner(llm_client=mock_llm)

        subtask = _sample_subtask()
        parent = ConstraintEnvelope(financial={"limit": 200.0})

        spec, _ = designer.design(subtask, parent, [])
        # LLM says 0.15 ratio, so 200 * 0.15 = 30.0
        assert spec.envelope.financial["limit"] == pytest.approx(30.0)

    def test_child_cannot_exceed_parent_financial(self) -> None:
        response = _sample_llm_design_response()
        response["financial_ratio"] = 0.5  # Max allowed ratio
        mock_llm = _make_mock_llm(response)
        designer = AgentDesigner(llm_client=mock_llm)

        subtask = _sample_subtask()
        parent = ConstraintEnvelope(financial={"limit": 10.0})

        spec, _ = designer.design(subtask, parent, [])
        assert spec.envelope.financial["limit"] <= 10.0

    def test_child_inherits_parent_blocked_operations(self) -> None:
        mock_llm = _make_mock_llm(_sample_llm_design_response())
        designer = AgentDesigner(llm_client=mock_llm)

        subtask = _sample_subtask()
        parent = ConstraintEnvelope(
            operational={"allowed": [], "blocked": ["delete", "drop_table"]}
        )

        spec, _ = designer.design(subtask, parent, [])
        assert "delete" in spec.envelope.operational["blocked"]
        assert "drop_table" in spec.envelope.operational["blocked"]

    def test_child_allowed_ops_subset_of_parent(self) -> None:
        mock_llm = _make_mock_llm(_sample_llm_design_response())
        designer = AgentDesigner(llm_client=mock_llm)

        subtask = _sample_subtask()
        parent = ConstraintEnvelope(operational={"allowed": ["read", "write"], "blocked": []})

        spec, _ = designer.design(subtask, parent, [])
        # Child's allowed must be subset of parent's allowed
        for op in spec.envelope.operational.get("allowed", []):
            assert op in ["read", "write"]

    def test_child_inherits_data_access_ceiling(self) -> None:
        mock_llm = _make_mock_llm(_sample_llm_design_response())
        designer = AgentDesigner(llm_client=mock_llm)

        subtask = _sample_subtask()
        parent = ConstraintEnvelope(
            data_access={"ceiling": "confidential", "scopes": ["project-x"]}
        )

        spec, _ = designer.design(subtask, parent, [])
        assert spec.envelope.data_access["ceiling"] == "confidential"


# ---------------------------------------------------------------------------
# Designer properties
# ---------------------------------------------------------------------------


class TestAgentDesignerProperties:
    def test_exposes_capability_matcher(self) -> None:
        mock_llm = _make_mock_llm({})
        matcher = CapabilityMatcher()
        designer = AgentDesigner(llm_client=mock_llm, capability_matcher=matcher)
        assert designer.capability_matcher is matcher

    def test_exposes_spawn_policy(self) -> None:
        mock_llm = _make_mock_llm({})
        policy = SpawnPolicy(complexity_threshold=4)
        designer = AgentDesigner(llm_client=mock_llm, spawn_policy=policy)
        assert designer.spawn_policy is policy

    def test_default_matcher_and_policy(self) -> None:
        mock_llm = _make_mock_llm({})
        designer = AgentDesigner(llm_client=mock_llm)
        assert designer.capability_matcher is not None
        assert designer.spawn_policy is not None


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestAgentDesignSchema:
    def test_schema_structure(self) -> None:
        assert AGENT_DESIGN_SCHEMA["type"] == "object"
        props = AGENT_DESIGN_SCHEMA["properties"]
        assert "name" in props
        assert "description" in props
        assert "capabilities" in props
        assert "selected_tools" in props
        assert "financial_ratio" in props

    def test_all_required_fields_present(self) -> None:
        required = AGENT_DESIGN_SCHEMA["required"]
        assert "name" in required
        assert "description" in required
        assert "capabilities" in required
        assert "selected_tools" in required
        assert "financial_ratio" in required
        assert "needs_shared_memory" in required
        assert "needs_persistent_memory" in required
        assert "produced_context_keys" in required
