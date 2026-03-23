"""
Unit tests for kaizen_agents.recovery.diagnoser -- FailureDiagnoser.

Uses mocked LLM (Tier 1 -- unit tests may mock external services).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from kaizen_agents.llm import LLMClient
from kaizen_agents.orchestration.recovery.diagnoser import (
    DIAGNOSIS_SCHEMA,
    FailureCategory,
    FailureDiagnosis,
    FailureDiagnoser,
    _build_diagnosis_system_prompt,
    _build_diagnosis_user_prompt,
)
from kaizen_agents.types import (
    AgentSpec,
    ConstraintEnvelope,
    EdgeType,
    Plan,
    PlanEdge,
    PlanGradient,
    PlanNode,
    PlanNodeState,
)


# ---------------------------------------------------------------------------
# Helpers -- mock LLM client
# ---------------------------------------------------------------------------


def _make_mock_llm(structured_response: dict[str, Any]) -> LLMClient:
    """Create a mock LLMClient that returns the given structured response."""
    mock = MagicMock(spec=LLMClient)
    mock.complete_structured.return_value = structured_response
    return mock


def _make_agent_spec(
    name: str = "test-agent",
    description: str = "A test agent",
    capabilities: list[str] | None = None,
    tool_ids: list[str] | None = None,
) -> AgentSpec:
    """Create an AgentSpec with sensible defaults for testing."""
    return AgentSpec(
        spec_id=f"spec-{name}",
        name=name,
        description=description,
        capabilities=capabilities or [],
        tool_ids=tool_ids or [],
    )


def _make_plan_with_failed_node(
    node_id: str = "research-node",
    error: str = "Something went wrong",
    optional: bool = False,
    retry_count: int = 0,
    upstream_nodes: list[tuple[str, PlanNodeState]] | None = None,
    downstream_nodes: list[str] | None = None,
) -> Plan:
    """Build a minimal plan containing a failed node and optional up/downstream nodes."""
    nodes: dict[str, PlanNode] = {}
    edges: list[PlanEdge] = []

    # The failed node
    failed_spec = _make_agent_spec(
        name="research-agent",
        description="Research authentication providers",
        capabilities=["web-search", "documentation-review"],
        tool_ids=["web_browser", "file_read"],
    )
    nodes[node_id] = PlanNode(
        node_id=node_id,
        agent_spec=failed_spec,
        state=PlanNodeState.FAILED,
        optional=optional,
        retry_count=retry_count,
        error=error,
    )

    # Upstream nodes
    for up_id, up_state in upstream_nodes or []:
        up_spec = _make_agent_spec(name=f"agent-{up_id}", description=f"Upstream {up_id}")
        output = {"result": f"output from {up_id}"} if up_state == PlanNodeState.COMPLETED else None
        nodes[up_id] = PlanNode(
            node_id=up_id,
            agent_spec=up_spec,
            state=up_state,
            output=output,
        )
        edges.append(PlanEdge(from_node=up_id, to_node=node_id, edge_type=EdgeType.DATA_DEPENDENCY))

    # Downstream nodes
    for down_id in downstream_nodes or []:
        down_spec = _make_agent_spec(name=f"agent-{down_id}", description=f"Downstream {down_id}")
        nodes[down_id] = PlanNode(
            node_id=down_id,
            agent_spec=down_spec,
            state=PlanNodeState.PENDING,
        )
        edges.append(
            PlanEdge(from_node=node_id, to_node=down_id, edge_type=EdgeType.DATA_DEPENDENCY)
        )

    return Plan(
        plan_id="test-plan-001",
        name="Test Plan",
        nodes=nodes,
        edges=edges,
        gradient=PlanGradient(retry_budget=2),
    )


def _transient_diagnosis() -> dict[str, Any]:
    """LLM response for a transient (rate-limit) failure."""
    return {
        "root_cause": "OpenAI API returned 429 Too Many Requests due to rate limiting",
        "category": "transient",
        "recoverable": True,
        "suggested_actions": [
            "Retry with exponential backoff",
            "Reduce concurrent API calls",
        ],
        "confidence": 0.95,
    }


def _permanent_diagnosis() -> dict[str, Any]:
    """LLM response for a permanent failure."""
    return {
        "root_cause": "The agent attempted to access a private GitHub repository but lacks authentication credentials",
        "category": "permanent",
        "recoverable": False,
        "suggested_actions": [
            "Abort this task -- repository access requires credentials not available in the envelope",
        ],
        "confidence": 0.9,
    }


def _resource_diagnosis() -> dict[str, Any]:
    """LLM response for a resource exhaustion failure."""
    return {
        "root_cause": "Financial budget exhausted: $5.00 limit reached with $4.98 spent on API calls",
        "category": "resource",
        "recoverable": True,
        "suggested_actions": [
            "Request budget increase from supervisor",
            "Replace with a cheaper model (gpt-4o-mini instead of gpt-4o)",
            "Skip this optional analysis step",
        ],
        "confidence": 0.85,
    }


def _dependency_diagnosis() -> dict[str, Any]:
    """LLM response for a dependency failure."""
    return {
        "root_cause": "Upstream node 'data-collection' produced an empty dataset; this node requires at least 10 records to perform analysis",
        "category": "dependency",
        "recoverable": True,
        "suggested_actions": [
            "Add a data-validation node between the collector and analyzer",
            "Replace the data-collection node with a more thorough collector",
        ],
        "confidence": 0.7,
    }


def _configuration_diagnosis() -> dict[str, Any]:
    """LLM response for a configuration failure."""
    return {
        "root_cause": "Agent does not have web-search capability but the task requires fetching live data from the internet",
        "category": "configuration",
        "recoverable": True,
        "suggested_actions": [
            "Replace agent with one that has web-search capability",
            "Add web_browser tool to the agent's tool set",
        ],
        "confidence": 0.88,
    }


# ---------------------------------------------------------------------------
# FailureDiagnosis dataclass
# ---------------------------------------------------------------------------


class TestFailureDiagnosis:
    def test_construction(self) -> None:
        d = FailureDiagnosis(
            node_id="node-1",
            root_cause="Rate limit exceeded",
            category=FailureCategory.TRANSIENT,
            recoverable=True,
            suggested_actions=["Retry"],
            confidence=0.9,
            raw_error="429 error",
        )
        assert d.node_id == "node-1"
        assert d.category == FailureCategory.TRANSIENT
        assert d.recoverable is True
        assert d.confidence == 0.9
        assert d.raw_error == "429 error"

    def test_defaults(self) -> None:
        d = FailureDiagnosis(
            node_id="node-1",
            root_cause="Something broke",
            category=FailureCategory.PERMANENT,
            recoverable=False,
        )
        assert d.suggested_actions == []
        assert d.confidence == 0.5
        assert d.raw_error == ""


# ---------------------------------------------------------------------------
# FailureCategory enum
# ---------------------------------------------------------------------------


class TestFailureCategory:
    def test_all_categories_exist(self) -> None:
        assert FailureCategory.TRANSIENT.value == "transient"
        assert FailureCategory.PERMANENT.value == "permanent"
        assert FailureCategory.RESOURCE.value == "resource"
        assert FailureCategory.DEPENDENCY.value == "dependency"
        assert FailureCategory.CONFIGURATION.value == "configuration"

    def test_five_categories(self) -> None:
        assert len(FailureCategory) == 5


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


class TestDiagnosisPromptBuilding:
    def test_system_prompt_includes_category_descriptions(self) -> None:
        prompt = _build_diagnosis_system_prompt()
        assert "transient" in prompt.lower()
        assert "permanent" in prompt.lower()
        assert "resource" in prompt.lower()
        assert "dependency" in prompt.lower()
        assert "configuration" in prompt.lower()

    def test_user_prompt_includes_error(self) -> None:
        plan = _make_plan_with_failed_node(error="Connection timed out after 30s")
        node = plan.nodes["research-node"]
        prompt = _build_diagnosis_user_prompt(node, "Connection timed out after 30s", plan, {})
        assert "Connection timed out after 30s" in prompt

    def test_user_prompt_includes_node_details(self) -> None:
        plan = _make_plan_with_failed_node()
        node = plan.nodes["research-node"]
        prompt = _build_diagnosis_user_prompt(node, "error", plan, {})
        assert "research-node" in prompt
        assert "Research authentication providers" in prompt
        assert "web-search" in prompt
        assert "web_browser" in prompt

    def test_user_prompt_includes_upstream_info(self) -> None:
        plan = _make_plan_with_failed_node(
            upstream_nodes=[("data-collector", PlanNodeState.COMPLETED)]
        )
        node = plan.nodes["research-node"]
        prompt = _build_diagnosis_user_prompt(node, "error", plan, {})
        assert "data-collector" in prompt
        assert "completed" in prompt

    def test_user_prompt_includes_downstream_info(self) -> None:
        plan = _make_plan_with_failed_node(downstream_nodes=["implementation-node"])
        node = plan.nodes["research-node"]
        prompt = _build_diagnosis_user_prompt(node, "error", plan, {})
        assert "implementation-node" in prompt

    def test_user_prompt_includes_execution_context(self) -> None:
        plan = _make_plan_with_failed_node()
        node = plan.nodes["research-node"]
        prompt = _build_diagnosis_user_prompt(
            node, "error", plan, {"elapsed_seconds": 45.2, "attempts": 3}
        )
        assert "45.2" in prompt
        assert "attempts" in prompt

    def test_user_prompt_shows_retry_count(self) -> None:
        plan = _make_plan_with_failed_node(retry_count=2)
        node = plan.nodes["research-node"]
        prompt = _build_diagnosis_user_prompt(node, "error", plan, {})
        assert "2 / 2" in prompt  # retry_count / retry_budget

    def test_user_prompt_shows_optional_status(self) -> None:
        plan = _make_plan_with_failed_node(optional=True)
        node = plan.nodes["research-node"]
        prompt = _build_diagnosis_user_prompt(node, "error", plan, {})
        assert "True" in prompt  # optional=True


# ---------------------------------------------------------------------------
# FailureDiagnoser.diagnose -- transient failures
# ---------------------------------------------------------------------------


class TestDiagnoseTransient:
    def test_rate_limit_diagnosed_as_transient(self) -> None:
        mock_llm = _make_mock_llm(_transient_diagnosis())
        diagnoser = FailureDiagnoser(llm_client=mock_llm)
        plan = _make_plan_with_failed_node(error="429 Too Many Requests")

        diagnosis = diagnoser.diagnose(
            node_id="research-node",
            error="429 Too Many Requests",
            plan=plan,
        )

        assert diagnosis.category == FailureCategory.TRANSIENT
        assert diagnosis.recoverable is True
        assert diagnosis.confidence >= 0.9
        assert "429" in diagnosis.root_cause or "rate" in diagnosis.root_cause.lower()
        assert len(diagnosis.suggested_actions) >= 1
        assert diagnosis.raw_error == "429 Too Many Requests"
        assert diagnosis.node_id == "research-node"

    def test_transient_diagnosis_preserves_raw_error(self) -> None:
        mock_llm = _make_mock_llm(_transient_diagnosis())
        diagnoser = FailureDiagnoser(llm_client=mock_llm)
        plan = _make_plan_with_failed_node(error="Connection reset by peer")

        diagnosis = diagnoser.diagnose(
            node_id="research-node",
            error="Connection reset by peer",
            plan=plan,
        )

        assert diagnosis.raw_error == "Connection reset by peer"


# ---------------------------------------------------------------------------
# FailureDiagnoser.diagnose -- permanent failures
# ---------------------------------------------------------------------------


class TestDiagnosePermanent:
    def test_permanent_failure_not_recoverable(self) -> None:
        mock_llm = _make_mock_llm(_permanent_diagnosis())
        diagnoser = FailureDiagnoser(llm_client=mock_llm)
        plan = _make_plan_with_failed_node(
            error="PermissionError: access denied to private repository"
        )

        diagnosis = diagnoser.diagnose(
            node_id="research-node",
            error="PermissionError: access denied to private repository",
            plan=plan,
        )

        assert diagnosis.category == FailureCategory.PERMANENT
        assert diagnosis.recoverable is False

    def test_permanent_diagnosis_has_root_cause(self) -> None:
        mock_llm = _make_mock_llm(_permanent_diagnosis())
        diagnoser = FailureDiagnoser(llm_client=mock_llm)
        plan = _make_plan_with_failed_node(error="access denied")

        diagnosis = diagnoser.diagnose(
            node_id="research-node",
            error="access denied",
            plan=plan,
        )

        assert len(diagnosis.root_cause) > 10  # Substantive explanation


# ---------------------------------------------------------------------------
# FailureDiagnoser.diagnose -- resource failures
# ---------------------------------------------------------------------------


class TestDiagnoseResource:
    def test_budget_exhaustion_diagnosed_as_resource(self) -> None:
        mock_llm = _make_mock_llm(_resource_diagnosis())
        diagnoser = FailureDiagnoser(llm_client=mock_llm)
        plan = _make_plan_with_failed_node(error="Budget limit exceeded: $5.00")

        diagnosis = diagnoser.diagnose(
            node_id="research-node",
            error="Budget limit exceeded: $5.00",
            plan=plan,
        )

        assert diagnosis.category == FailureCategory.RESOURCE
        assert diagnosis.recoverable is True
        assert len(diagnosis.suggested_actions) >= 2


# ---------------------------------------------------------------------------
# FailureDiagnoser.diagnose -- dependency failures
# ---------------------------------------------------------------------------


class TestDiagnoseDependency:
    def test_upstream_data_issue_diagnosed_as_dependency(self) -> None:
        mock_llm = _make_mock_llm(_dependency_diagnosis())
        diagnoser = FailureDiagnoser(llm_client=mock_llm)
        plan = _make_plan_with_failed_node(
            error="ValueError: expected at least 10 records, got 0",
            upstream_nodes=[("data-collector", PlanNodeState.COMPLETED)],
        )

        diagnosis = diagnoser.diagnose(
            node_id="research-node",
            error="ValueError: expected at least 10 records, got 0",
            plan=plan,
        )

        assert diagnosis.category == FailureCategory.DEPENDENCY
        assert diagnosis.recoverable is True


# ---------------------------------------------------------------------------
# FailureDiagnoser.diagnose -- configuration failures
# ---------------------------------------------------------------------------


class TestDiagnoseConfiguration:
    def test_wrong_tools_diagnosed_as_configuration(self) -> None:
        mock_llm = _make_mock_llm(_configuration_diagnosis())
        diagnoser = FailureDiagnoser(llm_client=mock_llm)
        plan = _make_plan_with_failed_node(error="ToolNotFoundError: web_browser is not available")

        diagnosis = diagnoser.diagnose(
            node_id="research-node",
            error="ToolNotFoundError: web_browser is not available",
            plan=plan,
        )

        assert diagnosis.category == FailureCategory.CONFIGURATION
        assert diagnosis.recoverable is True


# ---------------------------------------------------------------------------
# FailureDiagnoser -- LLM interaction
# ---------------------------------------------------------------------------


class TestDiagnoserLLMInteraction:
    def test_calls_llm_with_structured_schema(self) -> None:
        mock_llm = _make_mock_llm(_transient_diagnosis())
        diagnoser = FailureDiagnoser(llm_client=mock_llm)
        plan = _make_plan_with_failed_node(error="timeout")

        diagnoser.diagnose(node_id="research-node", error="timeout", plan=plan)

        mock_llm.complete_structured.assert_called_once()
        call_args = mock_llm.complete_structured.call_args
        schema = call_args.kwargs.get("schema") or call_args[1].get("schema")
        assert schema == DIAGNOSIS_SCHEMA

    def test_passes_execution_context(self) -> None:
        mock_llm = _make_mock_llm(_transient_diagnosis())
        diagnoser = FailureDiagnoser(llm_client=mock_llm)
        plan = _make_plan_with_failed_node(error="timeout")

        diagnoser.diagnose(
            node_id="research-node",
            error="timeout",
            plan=plan,
            execution_context={"elapsed_seconds": 120.5},
        )

        call_args = mock_llm.complete_structured.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        user_msg = messages[1]["content"]
        assert "120.5" in user_msg

    def test_node_not_found_raises_key_error(self) -> None:
        mock_llm = _make_mock_llm(_transient_diagnosis())
        diagnoser = FailureDiagnoser(llm_client=mock_llm)
        plan = _make_plan_with_failed_node()

        with pytest.raises(KeyError):
            diagnoser.diagnose(
                node_id="nonexistent-node",
                error="error",
                plan=plan,
            )


# ---------------------------------------------------------------------------
# FailureDiagnoser -- validation of LLM response
# ---------------------------------------------------------------------------


class TestDiagnoserValidation:
    def test_empty_root_cause_raises(self) -> None:
        response = _transient_diagnosis()
        response["root_cause"] = ""
        mock_llm = _make_mock_llm(response)
        diagnoser = FailureDiagnoser(llm_client=mock_llm)
        plan = _make_plan_with_failed_node(error="error")

        with pytest.raises(ValueError, match="root_cause"):
            diagnoser.diagnose(node_id="research-node", error="error", plan=plan)

    def test_invalid_category_raises(self) -> None:
        response = _transient_diagnosis()
        response["category"] = "invalid_category"
        mock_llm = _make_mock_llm(response)
        diagnoser = FailureDiagnoser(llm_client=mock_llm)
        plan = _make_plan_with_failed_node(error="error")

        with pytest.raises(ValueError, match="Invalid failure category"):
            diagnoser.diagnose(node_id="research-node", error="error", plan=plan)

    def test_non_boolean_recoverable_raises(self) -> None:
        response = _transient_diagnosis()
        response["recoverable"] = "yes"
        mock_llm = _make_mock_llm(response)
        diagnoser = FailureDiagnoser(llm_client=mock_llm)
        plan = _make_plan_with_failed_node(error="error")

        with pytest.raises(ValueError, match="recoverable.*boolean"):
            diagnoser.diagnose(node_id="research-node", error="error", plan=plan)

    def test_confidence_clamped_to_range(self) -> None:
        response = _transient_diagnosis()
        response["confidence"] = 1.5
        mock_llm = _make_mock_llm(response)
        diagnoser = FailureDiagnoser(llm_client=mock_llm)
        plan = _make_plan_with_failed_node(error="error")

        diagnosis = diagnoser.diagnose(node_id="research-node", error="error", plan=plan)
        assert diagnosis.confidence == 1.0

    def test_negative_confidence_clamped(self) -> None:
        response = _transient_diagnosis()
        response["confidence"] = -0.5
        mock_llm = _make_mock_llm(response)
        diagnoser = FailureDiagnoser(llm_client=mock_llm)
        plan = _make_plan_with_failed_node(error="error")

        diagnosis = diagnoser.diagnose(node_id="research-node", error="error", plan=plan)
        assert diagnosis.confidence == 0.0

    def test_non_list_suggested_actions_treated_as_empty(self) -> None:
        response = _transient_diagnosis()
        response["suggested_actions"] = "not a list"
        mock_llm = _make_mock_llm(response)
        diagnoser = FailureDiagnoser(llm_client=mock_llm)
        plan = _make_plan_with_failed_node(error="error")

        diagnosis = diagnoser.diagnose(node_id="research-node", error="error", plan=plan)
        assert diagnosis.suggested_actions == []

    def test_non_numeric_confidence_defaults(self) -> None:
        response = _transient_diagnosis()
        response["confidence"] = "high"
        mock_llm = _make_mock_llm(response)
        diagnoser = FailureDiagnoser(llm_client=mock_llm)
        plan = _make_plan_with_failed_node(error="error")

        diagnosis = diagnoser.diagnose(node_id="research-node", error="error", plan=plan)
        assert diagnosis.confidence == 0.5


# ---------------------------------------------------------------------------
# Diagnosis schema structure
# ---------------------------------------------------------------------------


class TestDiagnosisSchema:
    def test_schema_is_valid_json_schema(self) -> None:
        assert DIAGNOSIS_SCHEMA["type"] == "object"
        assert "root_cause" in DIAGNOSIS_SCHEMA["properties"]
        assert "category" in DIAGNOSIS_SCHEMA["properties"]
        assert "recoverable" in DIAGNOSIS_SCHEMA["properties"]
        assert "suggested_actions" in DIAGNOSIS_SCHEMA["properties"]
        assert "confidence" in DIAGNOSIS_SCHEMA["properties"]

    def test_schema_required_fields(self) -> None:
        required = DIAGNOSIS_SCHEMA["required"]
        assert "root_cause" in required
        assert "category" in required
        assert "recoverable" in required
        assert "suggested_actions" in required
        assert "confidence" in required

    def test_category_enum_matches_failure_category(self) -> None:
        schema_enum = DIAGNOSIS_SCHEMA["properties"]["category"]["enum"]
        category_values = [c.value for c in FailureCategory]
        assert sorted(schema_enum) == sorted(category_values)
