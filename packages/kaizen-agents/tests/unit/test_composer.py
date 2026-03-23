"""
Unit tests for kaizen_agents.planner.composer — PlanComposer and PlanValidator.

Uses mocked LLM (Tier 1 -- unit tests may mock external services).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from kaizen_agents.llm import LLMClient
from kaizen_agents.planner.composer import (
    COMPOSITION_SCHEMA,
    PlanComposer,
    PlanValidator,
    ValidationError,
    _parse_edge_type,
)
from kaizen_agents.planner.decomposer import Subtask
from kaizen_agents.planner.designer import SpawnDecision
from kaizen_agents.types import (
    AgentSpec,
    ConstraintEnvelope,
    EdgeType,
    MemoryConfig,
    Plan,
    PlanEdge,
    PlanNode,
    PlanNodeOutput,
    PlanState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_llm(structured_response: dict[str, Any]) -> LLMClient:
    """Create a mock LLMClient that returns the given structured response."""
    mock = MagicMock(spec=LLMClient)
    mock.complete_structured.return_value = structured_response
    return mock


def _sample_subtask(
    description: str = "Do something",
    complexity: int = 2,
    capabilities: list[str] | None = None,
    tools: list[str] | None = None,
    depends_on: list[int] | None = None,
    output_keys: list[str] | None = None,
) -> Subtask:
    """Create a sample subtask for testing."""
    return Subtask(
        description=description,
        estimated_complexity=complexity,
        required_capabilities=capabilities or [],
        suggested_tools=tools or [],
        depends_on=depends_on or [],
        output_keys=output_keys or [],
    )


def _sample_spec(
    spec_id: str = "spec-001",
    name: str = "Test Agent",
    financial_limit: float = 5.0,
) -> AgentSpec:
    """Create a sample AgentSpec for testing."""
    return AgentSpec(
        spec_id=spec_id,
        name=name,
        description="A test agent.",
        capabilities=["test-cap"],
        tool_ids=["test_tool"],
        envelope=ConstraintEnvelope(
            financial={"limit": financial_limit},
            operational={"allowed": [], "blocked": ["delete"]},
        ),
        memory_config=MemoryConfig(session=True),
    )


def _sample_spawn_decision(should_spawn: bool = True) -> SpawnDecision:
    """Create a sample SpawnDecision."""
    if should_spawn:
        return SpawnDecision(SpawnDecision.SPAWN, "Complexity warrants spawning.")
    return SpawnDecision(SpawnDecision.INLINE, "Simple enough to handle inline.")


def _three_subtask_scenario() -> tuple[
    list[Subtask],
    list[tuple[AgentSpec, SpawnDecision]],
]:
    """Build a three-subtask scenario: research -> implement -> test.

    Subtask 0: no dependencies (root)
    Subtask 1: depends on 0
    Subtask 2: depends on 1
    """
    subtasks = [
        _sample_subtask(
            description="Research providers",
            complexity=2,
            depends_on=[],
            output_keys=["provider_comparison"],
        ),
        _sample_subtask(
            description="Implement middleware",
            complexity=4,
            depends_on=[0],
            output_keys=["auth_middleware"],
        ),
        _sample_subtask(
            description="Write integration tests",
            complexity=3,
            depends_on=[1],
            output_keys=["test_results"],
        ),
    ]

    specs = [
        (_sample_spec("spec-research", "Researcher", 3.0), _sample_spawn_decision()),
        (_sample_spec("spec-impl", "Implementer", 5.0), _sample_spawn_decision()),
        (_sample_spec("spec-test", "Tester", 2.0), _sample_spawn_decision()),
    ]

    return subtasks, specs


def _parallel_subtask_scenario() -> tuple[
    list[Subtask],
    list[tuple[AgentSpec, SpawnDecision]],
]:
    """Build a scenario with two independent root subtasks that can run in parallel.

    Subtask 0: no dependencies (root)
    Subtask 1: no dependencies (root)
    Subtask 2: depends on both 0 and 1 (aggregator)
    """
    subtasks = [
        _sample_subtask(
            description="Analyse frontend code",
            complexity=3,
            depends_on=[],
            output_keys=["frontend_report"],
        ),
        _sample_subtask(
            description="Analyse backend code",
            complexity=3,
            depends_on=[],
            output_keys=["backend_report"],
        ),
        _sample_subtask(
            description="Aggregate analysis results",
            complexity=2,
            depends_on=[0, 1],
            output_keys=["final_report"],
        ),
    ]

    specs = [
        (_sample_spec("spec-fe", "Frontend Analyser", 3.0), _sample_spawn_decision()),
        (_sample_spec("spec-be", "Backend Analyser", 3.0), _sample_spawn_decision()),
        (_sample_spec("spec-agg", "Aggregator", 2.0), _sample_spawn_decision()),
    ]

    return subtasks, specs


def _llm_response_sequential() -> dict[str, Any]:
    """LLM response for a sequential three-subtask plan (0 -> 1 -> 2)."""
    return {
        "edges": [
            {"from_index": 0, "to_index": 1, "edge_type": "data_dependency"},
            {"from_index": 1, "to_index": 2, "edge_type": "data_dependency"},
        ],
        "input_mappings": [
            {
                "target_index": 1,
                "input_key": "provider_data",
                "source_index": 0,
                "output_key": "provider_comparison",
            },
            {
                "target_index": 2,
                "input_key": "middleware_code",
                "source_index": 1,
                "output_key": "auth_middleware",
            },
        ],
    }


def _llm_response_parallel() -> dict[str, Any]:
    """LLM response for a parallel scenario: 0 and 1 are independent, both feed into 2."""
    return {
        "edges": [
            {"from_index": 0, "to_index": 2, "edge_type": "data_dependency"},
            {"from_index": 1, "to_index": 2, "edge_type": "data_dependency"},
        ],
        "input_mappings": [
            {
                "target_index": 2,
                "input_key": "frontend_data",
                "source_index": 0,
                "output_key": "frontend_report",
            },
            {
                "target_index": 2,
                "input_key": "backend_data",
                "source_index": 1,
                "output_key": "backend_report",
            },
        ],
    }


def _llm_response_with_cycle() -> dict[str, Any]:
    """LLM response that creates a cycle: 0 -> 1 -> 2 -> 0."""
    return {
        "edges": [
            {"from_index": 0, "to_index": 1, "edge_type": "data_dependency"},
            {"from_index": 1, "to_index": 2, "edge_type": "data_dependency"},
            {"from_index": 2, "to_index": 0, "edge_type": "data_dependency"},
        ],
        "input_mappings": [],
    }


# ---------------------------------------------------------------------------
# PlanValidator -- validate_structure
# ---------------------------------------------------------------------------


class TestPlanValidatorStructure:
    def test_empty_plan_rejected(self) -> None:
        plan = Plan(nodes={}, edges=[])
        validator = PlanValidator()

        errors = validator.validate_structure(plan)

        assert len(errors) == 1
        assert errors[0].code == "EMPTY_PLAN"

    def test_single_node_valid(self) -> None:
        node = PlanNode(node_id="a", agent_spec=_sample_spec())
        plan = Plan(nodes={"a": node}, edges=[])
        validator = PlanValidator()

        errors = validator.validate_structure(plan)
        assert errors == []

    def test_self_edge_detected(self) -> None:
        node = PlanNode(node_id="a", agent_spec=_sample_spec())
        plan = Plan(
            nodes={"a": node},
            edges=[PlanEdge(from_node="a", to_node="a", edge_type=EdgeType.DATA_DEPENDENCY)],
        )
        validator = PlanValidator()

        errors = validator.validate_structure(plan)
        codes = [e.code for e in errors]
        assert "SELF_EDGE" in codes

    def test_missing_edge_source_detected(self) -> None:
        node = PlanNode(node_id="a", agent_spec=_sample_spec())
        plan = Plan(
            nodes={"a": node},
            edges=[PlanEdge(from_node="ghost", to_node="a", edge_type=EdgeType.DATA_DEPENDENCY)],
        )
        validator = PlanValidator()

        errors = validator.validate_structure(plan)
        codes = [e.code for e in errors]
        assert "MISSING_EDGE_SOURCE" in codes

    def test_missing_edge_target_detected(self) -> None:
        node = PlanNode(node_id="a", agent_spec=_sample_spec())
        plan = Plan(
            nodes={"a": node},
            edges=[PlanEdge(from_node="a", to_node="ghost", edge_type=EdgeType.DATA_DEPENDENCY)],
        )
        validator = PlanValidator()

        errors = validator.validate_structure(plan)
        codes = [e.code for e in errors]
        assert "MISSING_EDGE_TARGET" in codes

    def test_missing_input_mapping_source_detected(self) -> None:
        node = PlanNode(
            node_id="a",
            agent_spec=_sample_spec(),
            input_mapping={
                "data": PlanNodeOutput(source_node="ghost", output_key="result"),
            },
        )
        plan = Plan(nodes={"a": node}, edges=[])
        validator = PlanValidator()

        errors = validator.validate_structure(plan)
        codes = [e.code for e in errors]
        assert "MISSING_INPUT_SOURCE" in codes

    def test_input_mapping_without_backing_edge_detected(self) -> None:
        node_a = PlanNode(node_id="a", agent_spec=_sample_spec())
        node_b = PlanNode(
            node_id="b",
            agent_spec=_sample_spec(),
            input_mapping={
                "data": PlanNodeOutput(source_node="a", output_key="result"),
            },
        )
        # No edge from a to b
        plan = Plan(nodes={"a": node_a, "b": node_b}, edges=[])
        validator = PlanValidator()

        errors = validator.validate_structure(plan)
        codes = [e.code for e in errors]
        assert "INPUT_MAPPING_NO_EDGE" in codes

    def test_cycle_detected(self) -> None:
        node_a = PlanNode(node_id="a", agent_spec=_sample_spec())
        node_b = PlanNode(node_id="b", agent_spec=_sample_spec())
        plan = Plan(
            nodes={"a": node_a, "b": node_b},
            edges=[
                PlanEdge(from_node="a", to_node="b", edge_type=EdgeType.DATA_DEPENDENCY),
                PlanEdge(from_node="b", to_node="a", edge_type=EdgeType.DATA_DEPENDENCY),
            ],
        )
        validator = PlanValidator()

        errors = validator.validate_structure(plan)
        codes = [e.code for e in errors]
        assert "CYCLE_DETECTED" in codes

    def test_three_node_cycle_detected(self) -> None:
        nodes = {f"n{i}": PlanNode(node_id=f"n{i}", agent_spec=_sample_spec()) for i in range(3)}
        plan = Plan(
            nodes=nodes,
            edges=[
                PlanEdge(from_node="n0", to_node="n1", edge_type=EdgeType.DATA_DEPENDENCY),
                PlanEdge(from_node="n1", to_node="n2", edge_type=EdgeType.DATA_DEPENDENCY),
                PlanEdge(from_node="n2", to_node="n0", edge_type=EdgeType.DATA_DEPENDENCY),
            ],
        )
        validator = PlanValidator()

        errors = validator.validate_structure(plan)
        codes = [e.code for e in errors]
        assert "CYCLE_DETECTED" in codes
        assert "NO_ROOT_NODE" in codes

    def test_valid_linear_chain(self) -> None:
        nodes = {f"n{i}": PlanNode(node_id=f"n{i}", agent_spec=_sample_spec()) for i in range(3)}
        plan = Plan(
            nodes=nodes,
            edges=[
                PlanEdge(from_node="n0", to_node="n1", edge_type=EdgeType.DATA_DEPENDENCY),
                PlanEdge(from_node="n1", to_node="n2", edge_type=EdgeType.DATA_DEPENDENCY),
            ],
        )
        validator = PlanValidator()

        errors = validator.validate_structure(plan)
        assert errors == []

    def test_valid_diamond_dag(self) -> None:
        """Diamond shape: a -> b, a -> c, b -> d, c -> d."""
        nodes = {
            nid: PlanNode(node_id=nid, agent_spec=_sample_spec()) for nid in ["a", "b", "c", "d"]
        }
        plan = Plan(
            nodes=nodes,
            edges=[
                PlanEdge(from_node="a", to_node="b", edge_type=EdgeType.DATA_DEPENDENCY),
                PlanEdge(from_node="a", to_node="c", edge_type=EdgeType.DATA_DEPENDENCY),
                PlanEdge(from_node="b", to_node="d", edge_type=EdgeType.DATA_DEPENDENCY),
                PlanEdge(from_node="c", to_node="d", edge_type=EdgeType.DATA_DEPENDENCY),
            ],
        )
        validator = PlanValidator()

        errors = validator.validate_structure(plan)
        assert errors == []

    def test_no_root_detected(self) -> None:
        """Two nodes with data dependency edges forming no root."""
        node_a = PlanNode(node_id="a", agent_spec=_sample_spec())
        node_b = PlanNode(node_id="b", agent_spec=_sample_spec())
        plan = Plan(
            nodes={"a": node_a, "b": node_b},
            edges=[
                PlanEdge(from_node="a", to_node="b", edge_type=EdgeType.DATA_DEPENDENCY),
                PlanEdge(from_node="b", to_node="a", edge_type=EdgeType.DATA_DEPENDENCY),
            ],
        )
        validator = PlanValidator()

        errors = validator.validate_structure(plan)
        codes = [e.code for e in errors]
        assert "NO_ROOT_NODE" in codes

    def test_co_start_edges_do_not_affect_root_leaf(self) -> None:
        """CoStart edges should not prevent nodes from being roots or leaves."""
        node_a = PlanNode(node_id="a", agent_spec=_sample_spec())
        node_b = PlanNode(node_id="b", agent_spec=_sample_spec())
        plan = Plan(
            nodes={"a": node_a, "b": node_b},
            edges=[PlanEdge(from_node="a", to_node="b", edge_type=EdgeType.CO_START)],
        )
        validator = PlanValidator()

        errors = validator.validate_structure(plan)
        assert errors == []

    def test_returns_all_errors_not_just_first(self) -> None:
        """Validator should collect all errors, not stop at the first."""
        node = PlanNode(node_id="a", agent_spec=_sample_spec())
        plan = Plan(
            nodes={"a": node},
            edges=[
                PlanEdge(from_node="a", to_node="a", edge_type=EdgeType.DATA_DEPENDENCY),
                PlanEdge(from_node="ghost1", to_node="a", edge_type=EdgeType.DATA_DEPENDENCY),
                PlanEdge(from_node="a", to_node="ghost2", edge_type=EdgeType.DATA_DEPENDENCY),
            ],
        )
        validator = PlanValidator()

        errors = validator.validate_structure(plan)
        # Should find self-edge + missing source + missing target (at least 3 errors)
        assert len(errors) >= 3


# ---------------------------------------------------------------------------
# PlanValidator -- validate_envelopes
# ---------------------------------------------------------------------------


class TestPlanValidatorEnvelopes:
    def test_budget_within_limits_passes(self) -> None:
        nodes = {
            "a": PlanNode(node_id="a", agent_spec=_sample_spec(financial_limit=3.0)),
            "b": PlanNode(node_id="b", agent_spec=_sample_spec(financial_limit=3.0)),
        }
        plan = Plan(
            nodes=nodes,
            edges=[],
            envelope=ConstraintEnvelope(financial={"limit": 10.0}),
        )
        validator = PlanValidator()

        errors = validator.validate_envelopes(plan)
        assert errors == []

    def test_budget_overflow_detected(self) -> None:
        nodes = {
            "a": PlanNode(node_id="a", agent_spec=_sample_spec(financial_limit=6.0)),
            "b": PlanNode(node_id="b", agent_spec=_sample_spec(financial_limit=6.0)),
        }
        plan = Plan(
            nodes=nodes,
            edges=[],
            envelope=ConstraintEnvelope(financial={"limit": 10.0}),
        )
        validator = PlanValidator()

        errors = validator.validate_envelopes(plan)
        codes = [e.code for e in errors]
        assert "BUDGET_OVERFLOW" in codes

    def test_exact_budget_passes(self) -> None:
        nodes = {
            "a": PlanNode(node_id="a", agent_spec=_sample_spec(financial_limit=5.0)),
            "b": PlanNode(node_id="b", agent_spec=_sample_spec(financial_limit=5.0)),
        }
        plan = Plan(
            nodes=nodes,
            edges=[],
            envelope=ConstraintEnvelope(financial={"limit": 10.0}),
        )
        validator = PlanValidator()

        errors = validator.validate_envelopes(plan)
        assert errors == []

    def test_child_exceeds_parent_financial(self) -> None:
        nodes = {
            "a": PlanNode(node_id="a", agent_spec=_sample_spec(financial_limit=15.0)),
        }
        plan = Plan(
            nodes=nodes,
            edges=[],
            envelope=ConstraintEnvelope(financial={"limit": 10.0}),
        )
        validator = PlanValidator()

        errors = validator.validate_envelopes(plan)
        codes = [e.code for e in errors]
        assert "FINANCIAL_EXCEEDS_PARENT" in codes

    def test_blocked_ops_not_inherited_detected(self) -> None:
        child_spec = AgentSpec(
            spec_id="child",
            name="Child",
            description="test",
            envelope=ConstraintEnvelope(
                financial={"limit": 3.0},
                operational={"allowed": [], "blocked": []},  # Missing parent's "delete"
            ),
        )
        nodes = {"a": PlanNode(node_id="a", agent_spec=child_spec)}
        plan = Plan(
            nodes=nodes,
            edges=[],
            envelope=ConstraintEnvelope(
                financial={"limit": 10.0},
                operational={"allowed": [], "blocked": ["delete"]},
            ),
        )
        validator = PlanValidator()

        errors = validator.validate_envelopes(plan)
        codes = [e.code for e in errors]
        assert "BLOCKED_OPS_NOT_INHERITED" in codes

    def test_allowed_ops_exceed_parent_detected(self) -> None:
        child_spec = AgentSpec(
            spec_id="child",
            name="Child",
            description="test",
            envelope=ConstraintEnvelope(
                financial={"limit": 3.0},
                operational={"allowed": ["read", "write", "admin"], "blocked": []},
            ),
        )
        nodes = {"a": PlanNode(node_id="a", agent_spec=child_spec)}
        plan = Plan(
            nodes=nodes,
            edges=[],
            envelope=ConstraintEnvelope(
                financial={"limit": 10.0},
                operational={"allowed": ["read", "write"], "blocked": []},
            ),
        )
        validator = PlanValidator()

        errors = validator.validate_envelopes(plan)
        codes = [e.code for e in errors]
        assert "ALLOWED_OPS_EXCEED_PARENT" in codes

    def test_empty_plan_passes_envelope_check(self) -> None:
        plan = Plan(nodes={}, edges=[])
        validator = PlanValidator()

        errors = validator.validate_envelopes(plan)
        assert errors == []


# ---------------------------------------------------------------------------
# PlanValidator -- validate (combined)
# ---------------------------------------------------------------------------


class TestPlanValidatorCombined:
    def test_valid_plan_transitions_to_validated(self) -> None:
        node = PlanNode(node_id="a", agent_spec=_sample_spec(financial_limit=3.0))
        plan = Plan(
            nodes={"a": node},
            edges=[],
            envelope=ConstraintEnvelope(financial={"limit": 10.0}),
            state=PlanState.DRAFT,
        )
        validator = PlanValidator()

        errors = validator.validate(plan)
        assert errors == []
        assert plan.state == PlanState.VALIDATED

    def test_invalid_plan_stays_draft(self) -> None:
        plan = Plan(nodes={}, edges=[], state=PlanState.DRAFT)
        validator = PlanValidator()

        errors = validator.validate(plan)
        assert len(errors) > 0
        assert plan.state == PlanState.DRAFT

    def test_already_validated_plan_not_reverted(self) -> None:
        """A plan already in VALIDATED state with errors should not change state."""
        plan = Plan(nodes={}, edges=[], state=PlanState.VALIDATED)
        validator = PlanValidator()

        errors = validator.validate(plan)
        assert len(errors) > 0
        # State is not DRAFT so the validator does not touch it
        assert plan.state == PlanState.VALIDATED

    def test_combined_finds_structural_and_envelope_errors(self) -> None:
        child_spec = AgentSpec(
            spec_id="child",
            name="Child",
            description="test",
            envelope=ConstraintEnvelope(financial={"limit": 15.0}),
        )
        node_a = PlanNode(node_id="a", agent_spec=child_spec)
        plan = Plan(
            nodes={"a": node_a},
            edges=[
                PlanEdge(from_node="a", to_node="a", edge_type=EdgeType.DATA_DEPENDENCY),
            ],
            envelope=ConstraintEnvelope(financial={"limit": 10.0}),
        )
        validator = PlanValidator()

        errors = validator.validate(plan)
        codes = [e.code for e in errors]
        # Should find both structural (self-edge) and envelope (exceeds parent) errors
        assert "SELF_EDGE" in codes
        assert "FINANCIAL_EXCEEDS_PARENT" in codes


# ---------------------------------------------------------------------------
# PlanComposer -- basic composition
# ---------------------------------------------------------------------------


class TestPlanComposer:
    def test_sequential_plan_composition(self) -> None:
        """Three sequential subtasks produce a linear chain."""
        subtasks, specs = _three_subtask_scenario()
        mock_llm = _make_mock_llm(_llm_response_sequential())
        composer = PlanComposer(llm_client=mock_llm)
        parent_envelope = ConstraintEnvelope(financial={"limit": 100.0})

        plan = composer.compose(
            subtasks=subtasks,
            specs=specs,
            parent_envelope=parent_envelope,
            plan_name="auth-plan",
        )

        assert plan.name == "auth-plan"
        assert plan.state == PlanState.DRAFT
        assert len(plan.nodes) == 3
        assert len(plan.edges) == 2

        # Verify edges: node-0 -> node-1 -> node-2
        edge_pairs = [(e.from_node, e.to_node) for e in plan.edges]
        assert ("node-0", "node-1") in edge_pairs
        assert ("node-1", "node-2") in edge_pairs

        # Verify all edges are DataDependency
        for edge in plan.edges:
            assert edge.edge_type == EdgeType.DATA_DEPENDENCY

    def test_parallel_plan_composition(self) -> None:
        """Two parallel roots feed into an aggregator with no edge between them."""
        subtasks, specs = _parallel_subtask_scenario()
        mock_llm = _make_mock_llm(_llm_response_parallel())
        composer = PlanComposer(llm_client=mock_llm)
        parent_envelope = ConstraintEnvelope(financial={"limit": 100.0})

        plan = composer.compose(
            subtasks=subtasks,
            specs=specs,
            parent_envelope=parent_envelope,
        )

        assert len(plan.nodes) == 3
        edge_pairs = [(e.from_node, e.to_node) for e in plan.edges]

        # No edge between node-0 and node-1 (they are parallel)
        assert ("node-0", "node-1") not in edge_pairs
        assert ("node-1", "node-0") not in edge_pairs

        # Both feed into node-2
        assert ("node-0", "node-2") in edge_pairs
        assert ("node-1", "node-2") in edge_pairs

    def test_input_mappings_wired(self) -> None:
        """Input mappings from the LLM response are applied to node input_mapping."""
        subtasks, specs = _three_subtask_scenario()
        mock_llm = _make_mock_llm(_llm_response_sequential())
        composer = PlanComposer(llm_client=mock_llm)
        parent_envelope = ConstraintEnvelope(financial={"limit": 100.0})

        plan = composer.compose(subtasks=subtasks, specs=specs, parent_envelope=parent_envelope)

        # node-1 should have input mapping from node-0
        node_1 = plan.nodes["node-1"]
        assert "provider_data" in node_1.input_mapping
        assert node_1.input_mapping["provider_data"].source_node == "node-0"
        assert node_1.input_mapping["provider_data"].output_key == "provider_comparison"

        # node-2 should have input mapping from node-1
        node_2 = plan.nodes["node-2"]
        assert "middleware_code" in node_2.input_mapping
        assert node_2.input_mapping["middleware_code"].source_node == "node-1"
        assert node_2.input_mapping["middleware_code"].output_key == "auth_middleware"

    def test_uses_composition_schema(self) -> None:
        subtasks, specs = _three_subtask_scenario()
        mock_llm = _make_mock_llm(_llm_response_sequential())
        composer = PlanComposer(llm_client=mock_llm)

        composer.compose(
            subtasks=subtasks,
            specs=specs,
            parent_envelope=ConstraintEnvelope(),
        )

        call_args = mock_llm.complete_structured.call_args
        schema = call_args.kwargs.get("schema") or call_args[1].get("schema")
        assert schema == COMPOSITION_SCHEMA

    def test_plan_envelope_matches_parent(self) -> None:
        subtasks, specs = _three_subtask_scenario()
        mock_llm = _make_mock_llm(_llm_response_sequential())
        composer = PlanComposer(llm_client=mock_llm)
        parent_envelope = ConstraintEnvelope(financial={"limit": 42.0})

        plan = composer.compose(subtasks=subtasks, specs=specs, parent_envelope=parent_envelope)

        assert plan.envelope is parent_envelope
        assert plan.envelope.financial["limit"] == 42.0


# ---------------------------------------------------------------------------
# PlanComposer -- edge cases
# ---------------------------------------------------------------------------


class TestPlanComposerEdgeCases:
    def test_mismatched_subtasks_and_specs_raises(self) -> None:
        subtasks = [_sample_subtask(), _sample_subtask()]
        specs = [(_sample_spec(), _sample_spawn_decision())]
        mock_llm = _make_mock_llm({"edges": [], "input_mappings": []})
        composer = PlanComposer(llm_client=mock_llm)

        with pytest.raises(ValueError, match="Mismatch"):
            composer.compose(subtasks=subtasks, specs=specs, parent_envelope=ConstraintEnvelope())

    def test_empty_subtasks_raises(self) -> None:
        mock_llm = _make_mock_llm({"edges": [], "input_mappings": []})
        composer = PlanComposer(llm_client=mock_llm)

        with pytest.raises(ValueError, match="zero subtasks"):
            composer.compose(subtasks=[], specs=[], parent_envelope=ConstraintEnvelope())

    def test_single_subtask_no_edges(self) -> None:
        subtasks = [_sample_subtask(output_keys=["result"])]
        specs = [(_sample_spec(), _sample_spawn_decision())]
        mock_llm = _make_mock_llm({"edges": [], "input_mappings": []})
        composer = PlanComposer(llm_client=mock_llm)

        plan = composer.compose(
            subtasks=subtasks, specs=specs, parent_envelope=ConstraintEnvelope()
        )

        assert len(plan.nodes) == 1
        assert len(plan.edges) == 0

    def test_declared_dependencies_added_as_edges(self) -> None:
        """Dependencies from subtask.depends_on are added even if LLM omits them."""
        subtasks = [
            _sample_subtask(description="Root", depends_on=[], output_keys=["a"]),
            _sample_subtask(description="Child", depends_on=[0], output_keys=["b"]),
        ]
        specs = [
            (_sample_spec("s0", "Root Agent"), _sample_spawn_decision()),
            (_sample_spec("s1", "Child Agent"), _sample_spawn_decision()),
        ]
        # LLM returns NO edges -- but depends_on declares 1 depends on 0
        mock_llm = _make_mock_llm({"edges": [], "input_mappings": []})
        composer = PlanComposer(llm_client=mock_llm)

        plan = composer.compose(
            subtasks=subtasks, specs=specs, parent_envelope=ConstraintEnvelope()
        )

        edge_pairs = [(e.from_node, e.to_node) for e in plan.edges]
        assert ("node-0", "node-1") in edge_pairs

    def test_duplicate_edges_deduplicated(self) -> None:
        """If LLM returns duplicate edges, only one is kept."""
        subtasks = [
            _sample_subtask(description="A", depends_on=[], output_keys=["x"]),
            _sample_subtask(description="B", depends_on=[0], output_keys=["y"]),
        ]
        specs = [
            (_sample_spec("s0"), _sample_spawn_decision()),
            (_sample_spec("s1"), _sample_spawn_decision()),
        ]
        llm_response = {
            "edges": [
                {"from_index": 0, "to_index": 1, "edge_type": "data_dependency"},
                {"from_index": 0, "to_index": 1, "edge_type": "data_dependency"},  # Duplicate
            ],
            "input_mappings": [],
        }
        mock_llm = _make_mock_llm(llm_response)
        composer = PlanComposer(llm_client=mock_llm)

        plan = composer.compose(
            subtasks=subtasks, specs=specs, parent_envelope=ConstraintEnvelope()
        )

        assert len(plan.edges) == 1

    def test_out_of_range_edge_indices_ignored(self) -> None:
        subtasks = [_sample_subtask()]
        specs = [(_sample_spec(), _sample_spawn_decision())]
        llm_response = {
            "edges": [
                {"from_index": 0, "to_index": 99, "edge_type": "data_dependency"},
                {"from_index": -1, "to_index": 0, "edge_type": "data_dependency"},
            ],
            "input_mappings": [],
        }
        mock_llm = _make_mock_llm(llm_response)
        composer = PlanComposer(llm_client=mock_llm)

        plan = composer.compose(
            subtasks=subtasks, specs=specs, parent_envelope=ConstraintEnvelope()
        )

        assert len(plan.edges) == 0

    def test_self_referencing_edges_ignored(self) -> None:
        subtasks = [_sample_subtask()]
        specs = [(_sample_spec(), _sample_spawn_decision())]
        llm_response = {
            "edges": [{"from_index": 0, "to_index": 0, "edge_type": "data_dependency"}],
            "input_mappings": [],
        }
        mock_llm = _make_mock_llm(llm_response)
        composer = PlanComposer(llm_client=mock_llm)

        plan = composer.compose(
            subtasks=subtasks, specs=specs, parent_envelope=ConstraintEnvelope()
        )

        assert len(plan.edges) == 0

    def test_invalid_input_mapping_indices_ignored(self) -> None:
        subtasks = [_sample_subtask()]
        specs = [(_sample_spec(), _sample_spawn_decision())]
        llm_response = {
            "edges": [],
            "input_mappings": [
                {
                    "target_index": 99,
                    "input_key": "x",
                    "source_index": 0,
                    "output_key": "y",
                },
                {
                    "target_index": 0,
                    "input_key": "x",
                    "source_index": 0,  # Self-reference
                    "output_key": "y",
                },
            ],
        }
        mock_llm = _make_mock_llm(llm_response)
        composer = PlanComposer(llm_client=mock_llm)

        plan = composer.compose(
            subtasks=subtasks, specs=specs, parent_envelope=ConstraintEnvelope()
        )

        # Both mappings should be ignored
        assert plan.nodes["node-0"].input_mapping == {}

    def test_empty_input_key_ignored(self) -> None:
        subtasks = [
            _sample_subtask(depends_on=[], output_keys=["x"]),
            _sample_subtask(depends_on=[0]),
        ]
        specs = [
            (_sample_spec("s0"), _sample_spawn_decision()),
            (_sample_spec("s1"), _sample_spawn_decision()),
        ]
        llm_response = {
            "edges": [{"from_index": 0, "to_index": 1, "edge_type": "data_dependency"}],
            "input_mappings": [
                {
                    "target_index": 1,
                    "input_key": "",  # Empty key
                    "source_index": 0,
                    "output_key": "x",
                },
            ],
        }
        mock_llm = _make_mock_llm(llm_response)
        composer = PlanComposer(llm_client=mock_llm)

        plan = composer.compose(
            subtasks=subtasks, specs=specs, parent_envelope=ConstraintEnvelope()
        )

        assert plan.nodes["node-1"].input_mapping == {}


# ---------------------------------------------------------------------------
# PlanComposer -- compose_and_validate
# ---------------------------------------------------------------------------


class TestPlanComposerComposeAndValidate:
    def test_valid_plan_passes_validation(self) -> None:
        subtasks, specs = _three_subtask_scenario()
        mock_llm = _make_mock_llm(_llm_response_sequential())
        composer = PlanComposer(llm_client=mock_llm)
        parent_envelope = ConstraintEnvelope(financial={"limit": 100.0})

        plan, errors = composer.compose_and_validate(
            subtasks=subtasks,
            specs=specs,
            parent_envelope=parent_envelope,
        )

        assert errors == []
        assert plan.state == PlanState.VALIDATED

    def test_cyclic_plan_fails_validation(self) -> None:
        """A plan with a cycle should fail structural validation."""
        subtasks = [
            _sample_subtask(description="A", depends_on=[], output_keys=["a"]),
            _sample_subtask(description="B", depends_on=[], output_keys=["b"]),
            _sample_subtask(description="C", depends_on=[], output_keys=["c"]),
        ]
        specs = [
            (_sample_spec("s0", financial_limit=3.0), _sample_spawn_decision()),
            (_sample_spec("s1", financial_limit=3.0), _sample_spawn_decision()),
            (_sample_spec("s2", financial_limit=3.0), _sample_spawn_decision()),
        ]
        mock_llm = _make_mock_llm(_llm_response_with_cycle())
        composer = PlanComposer(llm_client=mock_llm)
        parent_envelope = ConstraintEnvelope(financial={"limit": 100.0})

        plan, errors = composer.compose_and_validate(
            subtasks=subtasks,
            specs=specs,
            parent_envelope=parent_envelope,
        )

        codes = [e.code for e in errors]
        assert "CYCLE_DETECTED" in codes
        assert plan.state == PlanState.DRAFT

    def test_budget_overflow_fails_validation(self) -> None:
        subtasks, specs = _three_subtask_scenario()
        mock_llm = _make_mock_llm(_llm_response_sequential())
        composer = PlanComposer(llm_client=mock_llm)
        # Parent budget is only $5, but children sum to $10
        parent_envelope = ConstraintEnvelope(financial={"limit": 5.0})

        plan, errors = composer.compose_and_validate(
            subtasks=subtasks,
            specs=specs,
            parent_envelope=parent_envelope,
        )

        codes = [e.code for e in errors]
        assert "BUDGET_OVERFLOW" in codes
        assert plan.state == PlanState.DRAFT


# ---------------------------------------------------------------------------
# PlanComposer -- edge type handling
# ---------------------------------------------------------------------------


class TestPlanComposerEdgeTypes:
    def test_completion_dependency_edges(self) -> None:
        subtasks = [
            _sample_subtask(description="Main work", depends_on=[], output_keys=["result"]),
            _sample_subtask(description="Cleanup", depends_on=[0]),
        ]
        specs = [
            (_sample_spec("s0"), _sample_spawn_decision()),
            (_sample_spec("s1"), _sample_spawn_decision()),
        ]
        llm_response = {
            "edges": [
                {"from_index": 0, "to_index": 1, "edge_type": "completion_dependency"},
            ],
            "input_mappings": [],
        }
        mock_llm = _make_mock_llm(llm_response)
        composer = PlanComposer(llm_client=mock_llm)

        plan = composer.compose(
            subtasks=subtasks, specs=specs, parent_envelope=ConstraintEnvelope()
        )

        assert len(plan.edges) == 1
        assert plan.edges[0].edge_type == EdgeType.COMPLETION_DEPENDENCY

    def test_co_start_edges(self) -> None:
        subtasks = [
            _sample_subtask(description="Task A", depends_on=[]),
            _sample_subtask(description="Task B", depends_on=[]),
        ]
        specs = [
            (_sample_spec("s0"), _sample_spawn_decision()),
            (_sample_spec("s1"), _sample_spawn_decision()),
        ]
        llm_response = {
            "edges": [
                {"from_index": 0, "to_index": 1, "edge_type": "co_start"},
            ],
            "input_mappings": [],
        }
        mock_llm = _make_mock_llm(llm_response)
        composer = PlanComposer(llm_client=mock_llm)

        plan = composer.compose(
            subtasks=subtasks, specs=specs, parent_envelope=ConstraintEnvelope()
        )

        assert len(plan.edges) == 1
        assert plan.edges[0].edge_type == EdgeType.CO_START

    def test_unrecognised_edge_type_defaults_to_data_dependency(self) -> None:
        subtasks = [
            _sample_subtask(description="A", depends_on=[]),
            _sample_subtask(description="B", depends_on=[0]),
        ]
        specs = [
            (_sample_spec("s0"), _sample_spawn_decision()),
            (_sample_spec("s1"), _sample_spawn_decision()),
        ]
        llm_response = {
            "edges": [
                {"from_index": 0, "to_index": 1, "edge_type": "unknown_type"},
            ],
            "input_mappings": [],
        }
        mock_llm = _make_mock_llm(llm_response)
        composer = PlanComposer(llm_client=mock_llm)

        plan = composer.compose(
            subtasks=subtasks, specs=specs, parent_envelope=ConstraintEnvelope()
        )

        assert plan.edges[0].edge_type == EdgeType.DATA_DEPENDENCY


# ---------------------------------------------------------------------------
# PlanComposer -- properties
# ---------------------------------------------------------------------------


class TestPlanComposerProperties:
    def test_exposes_validator(self) -> None:
        mock_llm = _make_mock_llm({})
        validator = PlanValidator()
        composer = PlanComposer(llm_client=mock_llm, validator=validator)
        assert composer.validator is validator

    def test_default_validator_created(self) -> None:
        mock_llm = _make_mock_llm({})
        composer = PlanComposer(llm_client=mock_llm)
        assert composer.validator is not None
        assert isinstance(composer.validator, PlanValidator)


# ---------------------------------------------------------------------------
# _parse_edge_type helper
# ---------------------------------------------------------------------------


class TestParseEdgeType:
    def test_data_dependency(self) -> None:
        assert _parse_edge_type("data_dependency") == EdgeType.DATA_DEPENDENCY

    def test_completion_dependency(self) -> None:
        assert _parse_edge_type("completion_dependency") == EdgeType.COMPLETION_DEPENDENCY

    def test_co_start(self) -> None:
        assert _parse_edge_type("co_start") == EdgeType.CO_START

    def test_unknown_defaults_to_data_dependency(self) -> None:
        assert _parse_edge_type("something_else") == EdgeType.DATA_DEPENDENCY
        assert _parse_edge_type("") == EdgeType.DATA_DEPENDENCY


# ---------------------------------------------------------------------------
# COMPOSITION_SCHEMA
# ---------------------------------------------------------------------------


class TestCompositionSchema:
    def test_schema_is_valid_json_schema(self) -> None:
        assert COMPOSITION_SCHEMA["type"] == "object"
        assert "edges" in COMPOSITION_SCHEMA["properties"]
        assert "input_mappings" in COMPOSITION_SCHEMA["properties"]

    def test_schema_required_fields(self) -> None:
        assert "edges" in COMPOSITION_SCHEMA["required"]
        assert "input_mappings" in COMPOSITION_SCHEMA["required"]

    def test_edge_item_has_required_fields(self) -> None:
        edge_schema = COMPOSITION_SCHEMA["properties"]["edges"]["items"]
        assert "from_index" in edge_schema["required"]
        assert "to_index" in edge_schema["required"]
        assert "edge_type" in edge_schema["required"]

    def test_input_mapping_item_has_required_fields(self) -> None:
        mapping_schema = COMPOSITION_SCHEMA["properties"]["input_mappings"]["items"]
        assert "target_index" in mapping_schema["required"]
        assert "input_key" in mapping_schema["required"]
        assert "source_index" in mapping_schema["required"]
        assert "output_key" in mapping_schema["required"]


# ---------------------------------------------------------------------------
# ValidationError dataclass
# ---------------------------------------------------------------------------


class TestValidationError:
    def test_construction(self) -> None:
        err = ValidationError(code="TEST", message="A test error.")
        assert err.code == "TEST"
        assert err.message == "A test error."
        assert err.node_id is None

    def test_with_node_id(self) -> None:
        err = ValidationError(code="TEST", message="Error on node.", node_id="node-5")
        assert err.node_id == "node-5"
