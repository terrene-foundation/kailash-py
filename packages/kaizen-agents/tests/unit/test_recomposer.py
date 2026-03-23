"""
Unit tests for kaizen_agents.recovery.recomposer -- Recomposer.

Uses mocked LLM (Tier 1 -- unit tests may mock external services).
Tests each recovery strategy and validates that produced PlanModification
objects preserve DAG invariants.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from kaizen_agents.llm import LLMClient
from kaizen_agents.recovery.diagnoser import FailureCategory, FailureDiagnosis
from kaizen_agents.recovery.recomposer import (
    RECOVERY_SCHEMA,
    RecoveryPlan,
    RecoveryStrategy,
    Recomposer,
    _build_recovery_system_prompt,
    _build_recovery_user_prompt,
)
from kaizen_agents.types import (
    AgentSpec,
    ConstraintEnvelope,
    EdgeType,
    Plan,
    PlanEdge,
    PlanGradient,
    PlanModification,
    PlanModificationType,
    PlanNode,
    PlanNodeState,
)


# ---------------------------------------------------------------------------
# Helpers -- mock LLM and test fixtures
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


def _make_diagnosis(
    category: FailureCategory = FailureCategory.TRANSIENT,
    recoverable: bool = True,
    node_id: str = "failed-node",
) -> FailureDiagnosis:
    """Create a FailureDiagnosis with sensible defaults for testing."""
    return FailureDiagnosis(
        node_id=node_id,
        root_cause=f"Test root cause for {category.value} failure",
        category=category,
        recoverable=recoverable,
        suggested_actions=["Action 1", "Action 2"],
        confidence=0.8,
        raw_error="Test error message",
    )


def _make_three_node_plan(
    failed_node_optional: bool = False,
    failed_node_retry_count: int = 2,
) -> Plan:
    """Build a three-node linear plan: setup -> failed-node -> finalize.

    The failed-node has state=FAILED and sits between a completed upstream
    node and a pending downstream node.
    """
    setup_spec = _make_agent_spec(
        name="setup-agent",
        description="Gather initial data",
        capabilities=["data-collection"],
        tool_ids=["file_read"],
    )
    failed_spec = _make_agent_spec(
        name="analysis-agent",
        description="Analyze the gathered data",
        capabilities=["data-analysis", "web-search"],
        tool_ids=["web_browser", "data_tool"],
    )
    finalize_spec = _make_agent_spec(
        name="report-agent",
        description="Generate final report",
        capabilities=["report-generation"],
        tool_ids=["file_write"],
    )

    nodes = {
        "setup-node": PlanNode(
            node_id="setup-node",
            agent_spec=setup_spec,
            state=PlanNodeState.COMPLETED,
            output={"data": "collected data"},
        ),
        "failed-node": PlanNode(
            node_id="failed-node",
            agent_spec=failed_spec,
            state=PlanNodeState.FAILED,
            optional=failed_node_optional,
            retry_count=failed_node_retry_count,
            error="Test failure",
        ),
        "finalize-node": PlanNode(
            node_id="finalize-node",
            agent_spec=finalize_spec,
            state=PlanNodeState.PENDING,
        ),
    }

    edges = [
        PlanEdge(
            from_node="setup-node",
            to_node="failed-node",
            edge_type=EdgeType.DATA_DEPENDENCY,
        ),
        PlanEdge(
            from_node="failed-node",
            to_node="finalize-node",
            edge_type=EdgeType.DATA_DEPENDENCY,
        ),
    ]

    return Plan(
        plan_id="test-plan-001",
        name="Three Node Test Plan",
        nodes=nodes,
        edges=edges,
        gradient=PlanGradient(retry_budget=2),
    )


# ---------------------------------------------------------------------------
# LLM response fixtures for each strategy
# ---------------------------------------------------------------------------


def _retry_response() -> dict[str, Any]:
    """LLM response selecting the RETRY strategy."""
    return {
        "strategy": "retry",
        "rationale": "The failure is transient (rate limit). The executor's retry mechanism will handle it automatically.",
        "replacement_spec": None,
        "alternative_nodes": None,
        "skip_reason": None,
    }


def _replace_response() -> dict[str, Any]:
    """LLM response selecting the REPLACE strategy."""
    return {
        "strategy": "replace",
        "rationale": "The agent lacks web-search capability needed for this task. Replacing with an agent that has it.",
        "replacement_spec": {
            "name": "web-research-agent",
            "description": "Research agent with web search and API access",
            "capabilities": ["web-search", "api-access", "data-analysis"],
            "tool_ids": ["web_browser", "api_client", "data_tool"],
        },
        "alternative_nodes": None,
        "skip_reason": None,
    }


def _skip_response() -> dict[str, Any]:
    """LLM response selecting the SKIP strategy."""
    return {
        "strategy": "skip",
        "rationale": "The node is optional and its analysis output is not critical for the final report.",
        "replacement_spec": None,
        "alternative_nodes": None,
        "skip_reason": "Optional analysis step; downstream nodes can proceed without this data.",
    }


def _restructure_response() -> dict[str, Any]:
    """LLM response selecting the RESTRUCTURE strategy."""
    return {
        "strategy": "restructure",
        "rationale": "The original single-step analysis failed. Splitting into validation + focused analysis as an alternative path.",
        "replacement_spec": None,
        "alternative_nodes": [
            {
                "name": "data-validator",
                "description": "Validate and clean the input data before analysis",
                "capabilities": ["data-validation"],
                "tool_ids": ["data_tool"],
                "connect_from": ["setup-node"],
                "connect_to": [],
            },
            {
                "name": "focused-analyzer",
                "description": "Perform focused analysis on validated data",
                "capabilities": ["data-analysis"],
                "tool_ids": ["data_tool", "file_write"],
                "connect_from": [],
                "connect_to": ["finalize-node"],
            },
        ],
        "skip_reason": None,
    }


def _abort_response() -> dict[str, Any]:
    """LLM response selecting the ABORT strategy."""
    return {
        "strategy": "abort",
        "rationale": "The failure is permanent and unrecoverable. The required data source is permanently unavailable.",
        "replacement_spec": None,
        "alternative_nodes": None,
        "skip_reason": None,
    }


# ---------------------------------------------------------------------------
# RecoveryStrategy enum
# ---------------------------------------------------------------------------


class TestRecoveryStrategy:
    def test_all_strategies_exist(self) -> None:
        assert RecoveryStrategy.RETRY.value == "retry"
        assert RecoveryStrategy.REPLACE.value == "replace"
        assert RecoveryStrategy.SKIP.value == "skip"
        assert RecoveryStrategy.RESTRUCTURE.value == "restructure"
        assert RecoveryStrategy.ABORT.value == "abort"

    def test_five_strategies(self) -> None:
        assert len(RecoveryStrategy) == 5


# ---------------------------------------------------------------------------
# RecoveryPlan dataclass
# ---------------------------------------------------------------------------


class TestRecoveryPlan:
    def test_construction(self) -> None:
        rp = RecoveryPlan(
            strategy=RecoveryStrategy.RETRY,
            modifications=[],
            rationale="Transient failure, retry will fix it",
            failed_node_id="node-1",
        )
        assert rp.strategy == RecoveryStrategy.RETRY
        assert rp.modifications == []
        assert rp.failed_node_id == "node-1"

    def test_defaults(self) -> None:
        rp = RecoveryPlan(strategy=RecoveryStrategy.ABORT)
        assert rp.modifications == []
        assert rp.rationale == ""
        assert rp.failed_node_id == ""


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


class TestRecoveryPromptBuilding:
    def test_system_prompt_includes_all_strategies(self) -> None:
        prompt = _build_recovery_system_prompt()
        assert "retry" in prompt.lower()
        assert "replace" in prompt.lower()
        assert "skip" in prompt.lower()
        assert "restructure" in prompt.lower()
        assert "abort" in prompt.lower()

    def test_user_prompt_includes_diagnosis(self) -> None:
        plan = _make_three_node_plan()
        failed_node = plan.nodes["failed-node"]
        diagnosis = _make_diagnosis(category=FailureCategory.CONFIGURATION)

        prompt = _build_recovery_user_prompt(plan, failed_node, diagnosis)
        assert "configuration" in prompt.lower()
        assert "Test root cause" in prompt

    def test_user_prompt_includes_node_details(self) -> None:
        plan = _make_three_node_plan()
        failed_node = plan.nodes["failed-node"]
        diagnosis = _make_diagnosis()

        prompt = _build_recovery_user_prompt(plan, failed_node, diagnosis)
        assert "failed-node" in prompt
        assert "Analyze the gathered data" in prompt
        assert "data-analysis" in prompt

    def test_user_prompt_shows_plan_status(self) -> None:
        plan = _make_three_node_plan()
        failed_node = plan.nodes["failed-node"]
        diagnosis = _make_diagnosis()

        prompt = _build_recovery_user_prompt(plan, failed_node, diagnosis)
        assert "setup-node" in prompt  # completed node
        assert "finalize-node" in prompt  # pending node


# ---------------------------------------------------------------------------
# Recomposer.recompose -- RETRY strategy
# ---------------------------------------------------------------------------


class TestRecomposeRetry:
    def test_retry_produces_no_modifications(self) -> None:
        mock_llm = _make_mock_llm(_retry_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis(category=FailureCategory.TRANSIENT)

        recovery = recomposer.recompose(
            plan=plan, failed_node_id="failed-node", diagnosis=diagnosis
        )

        assert recovery.strategy == RecoveryStrategy.RETRY
        assert recovery.modifications == []
        assert recovery.failed_node_id == "failed-node"
        assert len(recovery.rationale) > 0

    def test_retry_preserves_plan_unchanged(self) -> None:
        mock_llm = _make_mock_llm(_retry_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        original_node_count = len(plan.nodes)
        diagnosis = _make_diagnosis(category=FailureCategory.TRANSIENT)

        recomposer.recompose(plan=plan, failed_node_id="failed-node", diagnosis=diagnosis)

        assert len(plan.nodes) == original_node_count


# ---------------------------------------------------------------------------
# Recomposer.recompose -- REPLACE strategy
# ---------------------------------------------------------------------------


class TestRecomposeReplace:
    def test_replace_produces_replace_node_modification(self) -> None:
        mock_llm = _make_mock_llm(_replace_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis(category=FailureCategory.CONFIGURATION)

        recovery = recomposer.recompose(
            plan=plan, failed_node_id="failed-node", diagnosis=diagnosis
        )

        assert recovery.strategy == RecoveryStrategy.REPLACE
        assert len(recovery.modifications) == 1

        mod = recovery.modifications[0]
        assert mod.modification_type == PlanModificationType.REPLACE_NODE
        assert mod.old_node_id == "failed-node"
        assert mod.new_node is not None

    def test_replace_new_node_has_correct_spec(self) -> None:
        mock_llm = _make_mock_llm(_replace_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis(category=FailureCategory.CONFIGURATION)

        recovery = recomposer.recompose(
            plan=plan, failed_node_id="failed-node", diagnosis=diagnosis
        )

        new_node = recovery.modifications[0].new_node
        assert new_node is not None
        assert new_node.agent_spec.name == "web-research-agent"
        assert "web-search" in new_node.agent_spec.capabilities
        assert "api-access" in new_node.agent_spec.capabilities
        assert "web_browser" in new_node.agent_spec.tool_ids

    def test_replace_preserves_input_mapping(self) -> None:
        mock_llm = _make_mock_llm(_replace_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis(category=FailureCategory.CONFIGURATION)

        recovery = recomposer.recompose(
            plan=plan, failed_node_id="failed-node", diagnosis=diagnosis
        )

        new_node = recovery.modifications[0].new_node
        assert new_node is not None
        # Input mapping should be preserved from the original failed node
        original_mapping = plan.nodes["failed-node"].input_mapping
        assert new_node.input_mapping == original_mapping

    def test_replace_preserves_optional_flag(self) -> None:
        mock_llm = _make_mock_llm(_replace_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan(failed_node_optional=True)
        diagnosis = _make_diagnosis(category=FailureCategory.CONFIGURATION)

        recovery = recomposer.recompose(
            plan=plan, failed_node_id="failed-node", diagnosis=diagnosis
        )

        new_node = recovery.modifications[0].new_node
        assert new_node is not None
        assert new_node.optional is True

    def test_replace_preserves_envelope(self) -> None:
        mock_llm = _make_mock_llm(_replace_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis(category=FailureCategory.CONFIGURATION)

        original_envelope = plan.nodes["failed-node"].agent_spec.envelope
        recovery = recomposer.recompose(
            plan=plan, failed_node_id="failed-node", diagnosis=diagnosis
        )

        new_node = recovery.modifications[0].new_node
        assert new_node is not None
        assert new_node.agent_spec.envelope == original_envelope

    def test_replace_missing_spec_raises(self) -> None:
        response = _replace_response()
        response["replacement_spec"] = None
        mock_llm = _make_mock_llm(response)
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis(category=FailureCategory.CONFIGURATION)

        with pytest.raises(ValueError, match="replacement_spec"):
            recomposer.recompose(plan=plan, failed_node_id="failed-node", diagnosis=diagnosis)

    def test_replace_empty_name_raises(self) -> None:
        response = _replace_response()
        response["replacement_spec"]["name"] = ""
        mock_llm = _make_mock_llm(response)
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis(category=FailureCategory.CONFIGURATION)

        with pytest.raises(ValueError, match="name.*description"):
            recomposer.recompose(plan=plan, failed_node_id="failed-node", diagnosis=diagnosis)


# ---------------------------------------------------------------------------
# Recomposer.recompose -- SKIP strategy
# ---------------------------------------------------------------------------


class TestRecomposeSkip:
    def test_skip_produces_skip_node_modification(self) -> None:
        mock_llm = _make_mock_llm(_skip_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan(failed_node_optional=True)
        diagnosis = _make_diagnosis(category=FailureCategory.PERMANENT, recoverable=False)

        recovery = recomposer.recompose(
            plan=plan, failed_node_id="failed-node", diagnosis=diagnosis
        )

        assert recovery.strategy == RecoveryStrategy.SKIP
        assert len(recovery.modifications) == 1

        mod = recovery.modifications[0]
        assert mod.modification_type == PlanModificationType.SKIP_NODE
        assert mod.node_id == "failed-node"

    def test_skip_has_reason(self) -> None:
        mock_llm = _make_mock_llm(_skip_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan(failed_node_optional=True)
        diagnosis = _make_diagnosis(category=FailureCategory.PERMANENT, recoverable=False)

        recovery = recomposer.recompose(
            plan=plan, failed_node_id="failed-node", diagnosis=diagnosis
        )

        mod = recovery.modifications[0]
        assert mod.reason is not None
        assert len(mod.reason) > 0

    def test_skip_uses_skip_reason_from_llm(self) -> None:
        mock_llm = _make_mock_llm(_skip_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan(failed_node_optional=True)
        diagnosis = _make_diagnosis(category=FailureCategory.PERMANENT, recoverable=False)

        recovery = recomposer.recompose(
            plan=plan, failed_node_id="failed-node", diagnosis=diagnosis
        )

        mod = recovery.modifications[0]
        assert "optional" in mod.reason.lower() or "downstream" in mod.reason.lower()

    def test_skip_falls_back_to_rationale_when_no_reason(self) -> None:
        response = _skip_response()
        response["skip_reason"] = None
        mock_llm = _make_mock_llm(response)
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan(failed_node_optional=True)
        diagnosis = _make_diagnosis(category=FailureCategory.PERMANENT, recoverable=False)

        recovery = recomposer.recompose(
            plan=plan, failed_node_id="failed-node", diagnosis=diagnosis
        )

        mod = recovery.modifications[0]
        # Falls back to rationale when skip_reason is None
        assert mod.reason == response["rationale"]


# ---------------------------------------------------------------------------
# Recomposer.recompose -- RESTRUCTURE strategy
# ---------------------------------------------------------------------------


class TestRecomposeRestructure:
    def test_restructure_produces_skip_plus_add_nodes(self) -> None:
        mock_llm = _make_mock_llm(_restructure_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis(category=FailureCategory.DEPENDENCY)

        recovery = recomposer.recompose(
            plan=plan, failed_node_id="failed-node", diagnosis=diagnosis
        )

        assert recovery.strategy == RecoveryStrategy.RESTRUCTURE
        # Skip the failed node + 2 AddNode modifications
        assert len(recovery.modifications) == 3

        # First modification should skip the failed node
        skip_mod = recovery.modifications[0]
        assert skip_mod.modification_type == PlanModificationType.SKIP_NODE
        assert skip_mod.node_id == "failed-node"

        # Second and third should be AddNode
        add_mods = recovery.modifications[1:]
        for mod in add_mods:
            assert mod.modification_type == PlanModificationType.ADD_NODE
            assert mod.node is not None

    def test_restructure_new_nodes_have_unique_ids(self) -> None:
        mock_llm = _make_mock_llm(_restructure_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis(category=FailureCategory.DEPENDENCY)

        recovery = recomposer.recompose(
            plan=plan, failed_node_id="failed-node", diagnosis=diagnosis
        )

        add_mods = [
            m
            for m in recovery.modifications
            if m.modification_type == PlanModificationType.ADD_NODE
        ]
        node_ids = [m.node.node_id for m in add_mods]
        assert len(node_ids) == len(set(node_ids))  # All unique

    def test_restructure_wires_edges_to_existing_nodes(self) -> None:
        mock_llm = _make_mock_llm(_restructure_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis(category=FailureCategory.DEPENDENCY)

        recovery = recomposer.recompose(
            plan=plan, failed_node_id="failed-node", diagnosis=diagnosis
        )

        # The first new node should connect from setup-node
        first_add = recovery.modifications[1]
        assert first_add.edges is not None
        from_edges = [e for e in first_add.edges if e.to_node == first_add.node.node_id]
        from_node_ids = [e.from_node for e in from_edges]
        assert "setup-node" in from_node_ids

        # The second new node should connect to finalize-node
        second_add = recovery.modifications[2]
        assert second_add.edges is not None
        to_edges = [e for e in second_add.edges if e.from_node == second_add.node.node_id]
        to_node_ids = [e.to_node for e in to_edges]
        assert "finalize-node" in to_node_ids

    def test_restructure_new_nodes_inherit_envelope(self) -> None:
        mock_llm = _make_mock_llm(_restructure_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis(category=FailureCategory.DEPENDENCY)

        original_envelope = plan.nodes["failed-node"].agent_spec.envelope
        recovery = recomposer.recompose(
            plan=plan, failed_node_id="failed-node", diagnosis=diagnosis
        )

        add_mods = [
            m
            for m in recovery.modifications
            if m.modification_type == PlanModificationType.ADD_NODE
        ]
        for mod in add_mods:
            assert mod.node.agent_spec.envelope == original_envelope

    def test_restructure_missing_nodes_raises(self) -> None:
        response = _restructure_response()
        response["alternative_nodes"] = None
        mock_llm = _make_mock_llm(response)
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis(category=FailureCategory.DEPENDENCY)

        with pytest.raises(ValueError, match="alternative_nodes"):
            recomposer.recompose(plan=plan, failed_node_id="failed-node", diagnosis=diagnosis)

    def test_restructure_empty_nodes_raises(self) -> None:
        response = _restructure_response()
        response["alternative_nodes"] = []
        mock_llm = _make_mock_llm(response)
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis(category=FailureCategory.DEPENDENCY)

        with pytest.raises(ValueError, match="at least one"):
            recomposer.recompose(plan=plan, failed_node_id="failed-node", diagnosis=diagnosis)

    def test_restructure_invalid_node_entry_raises(self) -> None:
        response = _restructure_response()
        response["alternative_nodes"] = ["not_a_dict"]
        mock_llm = _make_mock_llm(response)
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis(category=FailureCategory.DEPENDENCY)

        with pytest.raises(ValueError, match="not a dict"):
            recomposer.recompose(plan=plan, failed_node_id="failed-node", diagnosis=diagnosis)

    def test_restructure_node_missing_name_raises(self) -> None:
        response = _restructure_response()
        response["alternative_nodes"][0]["name"] = ""
        mock_llm = _make_mock_llm(response)
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis(category=FailureCategory.DEPENDENCY)

        with pytest.raises(ValueError, match="name.*description"):
            recomposer.recompose(plan=plan, failed_node_id="failed-node", diagnosis=diagnosis)

    def test_restructure_ignores_edges_to_nonexistent_nodes(self) -> None:
        response = _restructure_response()
        response["alternative_nodes"][0]["connect_from"] = ["nonexistent-node"]
        mock_llm = _make_mock_llm(response)
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis(category=FailureCategory.DEPENDENCY)

        recovery = recomposer.recompose(
            plan=plan, failed_node_id="failed-node", diagnosis=diagnosis
        )

        # The edge to a nonexistent node should be silently dropped
        first_add = recovery.modifications[1]
        from_edges = [e for e in (first_add.edges or []) if e.to_node == first_add.node.node_id]
        from_node_ids = [e.from_node for e in from_edges]
        assert "nonexistent-node" not in from_node_ids


# ---------------------------------------------------------------------------
# Recomposer.recompose -- ABORT strategy
# ---------------------------------------------------------------------------


class TestRecomposeAbort:
    def test_abort_produces_no_modifications(self) -> None:
        mock_llm = _make_mock_llm(_abort_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis(category=FailureCategory.PERMANENT, recoverable=False)

        recovery = recomposer.recompose(
            plan=plan, failed_node_id="failed-node", diagnosis=diagnosis
        )

        assert recovery.strategy == RecoveryStrategy.ABORT
        assert recovery.modifications == []

    def test_abort_has_rationale(self) -> None:
        mock_llm = _make_mock_llm(_abort_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis(category=FailureCategory.PERMANENT, recoverable=False)

        recovery = recomposer.recompose(
            plan=plan, failed_node_id="failed-node", diagnosis=diagnosis
        )

        assert len(recovery.rationale) > 0


# ---------------------------------------------------------------------------
# Recomposer -- LLM interaction
# ---------------------------------------------------------------------------


class TestRecomposerLLMInteraction:
    def test_calls_llm_with_structured_schema(self) -> None:
        mock_llm = _make_mock_llm(_retry_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis()

        recomposer.recompose(plan=plan, failed_node_id="failed-node", diagnosis=diagnosis)

        mock_llm.complete_structured.assert_called_once()
        call_args = mock_llm.complete_structured.call_args
        schema = call_args.kwargs.get("schema") or call_args[1].get("schema")
        assert schema == RECOVERY_SCHEMA

    def test_node_not_found_raises_key_error(self) -> None:
        mock_llm = _make_mock_llm(_retry_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis()

        with pytest.raises(KeyError):
            recomposer.recompose(plan=plan, failed_node_id="nonexistent", diagnosis=diagnosis)


# ---------------------------------------------------------------------------
# Recomposer -- validation of LLM response
# ---------------------------------------------------------------------------


class TestRecomposerValidation:
    def test_invalid_strategy_raises(self) -> None:
        response = _retry_response()
        response["strategy"] = "invalid_strategy"
        mock_llm = _make_mock_llm(response)
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis()

        with pytest.raises(ValueError, match="Invalid recovery strategy"):
            recomposer.recompose(plan=plan, failed_node_id="failed-node", diagnosis=diagnosis)

    def test_empty_rationale_raises(self) -> None:
        response = _retry_response()
        response["rationale"] = ""
        mock_llm = _make_mock_llm(response)
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis()

        with pytest.raises(ValueError, match="rationale"):
            recomposer.recompose(plan=plan, failed_node_id="failed-node", diagnosis=diagnosis)


# ---------------------------------------------------------------------------
# Recomposer -- DAG invariant validation
# ---------------------------------------------------------------------------


class TestRecomposerDAGValidation:
    def test_replace_with_valid_node_passes_validation(self) -> None:
        mock_llm = _make_mock_llm(_replace_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis(category=FailureCategory.CONFIGURATION)

        # Should not raise
        recovery = recomposer.recompose(
            plan=plan, failed_node_id="failed-node", diagnosis=diagnosis
        )
        assert len(recovery.modifications) == 1

    def test_skip_existing_node_passes_validation(self) -> None:
        mock_llm = _make_mock_llm(_skip_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan(failed_node_optional=True)
        diagnosis = _make_diagnosis(category=FailureCategory.PERMANENT, recoverable=False)

        # Should not raise
        recovery = recomposer.recompose(
            plan=plan, failed_node_id="failed-node", diagnosis=diagnosis
        )
        assert len(recovery.modifications) == 1

    def test_restructure_with_valid_edges_passes_validation(self) -> None:
        mock_llm = _make_mock_llm(_restructure_response())
        recomposer = Recomposer(llm_client=mock_llm)
        plan = _make_three_node_plan()
        diagnosis = _make_diagnosis(category=FailureCategory.DEPENDENCY)

        # Should not raise
        recovery = recomposer.recompose(
            plan=plan, failed_node_id="failed-node", diagnosis=diagnosis
        )
        assert len(recovery.modifications) == 3


# ---------------------------------------------------------------------------
# Recovery schema structure
# ---------------------------------------------------------------------------


class TestRecoverySchema:
    def test_schema_is_valid_json_schema(self) -> None:
        assert RECOVERY_SCHEMA["type"] == "object"
        assert "strategy" in RECOVERY_SCHEMA["properties"]
        assert "rationale" in RECOVERY_SCHEMA["properties"]
        assert "replacement_spec" in RECOVERY_SCHEMA["properties"]
        assert "alternative_nodes" in RECOVERY_SCHEMA["properties"]
        assert "skip_reason" in RECOVERY_SCHEMA["properties"]

    def test_schema_required_fields(self) -> None:
        required = RECOVERY_SCHEMA["required"]
        assert "strategy" in required
        assert "rationale" in required

    def test_strategy_enum_matches_recovery_strategy(self) -> None:
        schema_enum = RECOVERY_SCHEMA["properties"]["strategy"]["enum"]
        strategy_values = [s.value for s in RecoveryStrategy]
        assert sorted(schema_enum) == sorted(strategy_values)
