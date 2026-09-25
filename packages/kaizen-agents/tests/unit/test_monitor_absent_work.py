"""#2248: absent work must not become successful or applied work.

Malformed-modification cases deliberately inject a recovery collaborator at
the monitor boundary. The built-in Recomposer rejects malformed LLM payloads;
these tests do not claim that those payloads bypass its validation.
"""

from types import SimpleNamespace

import pytest

from kaizen_agents.orchestration.monitor import PlanMonitor
from kaizen_agents.orchestration.recovery.recomposer import (
    RecoveryPlan,
    RecoveryStrategy,
)
from kaizen_agents.types import (
    AgentSpec,
    GradientZone,
    Plan,
    PlanEdge,
    PlanEventType,
    PlanGradient,
    PlanModification,
    PlanModificationType,
    PlanNode,
    PlanNodeState,
    PlanState,
    make_envelope,
)


class NoExternalLLM:
    def complete_structured(self, **kwargs):
        raise AssertionError("This regression must not call an external LLM")


def _spec(name):
    return AgentSpec(spec_id=name, name=name, description=name)


def _monitor(modifications=None):
    monitor = PlanMonitor(
        llm=NoExternalLLM(),
        envelope=make_envelope(financial={"limit": 10.0}),
        gradient=PlanGradient(retry_budget=0, after_retry_exhaustion=GradientZone.HELD),
    )
    if modifications is not None:
        monitor._diagnoser = SimpleNamespace(diagnose=lambda **kwargs: object())
        monitor._recomposer = SimpleNamespace(
            recompose=lambda **kwargs: RecoveryPlan(
                strategy=RecoveryStrategy.RESTRUCTURE,
                modifications=modifications,
                rationale="deterministic recovery-boundary fixture",
            )
        )
    return monitor


def _plan():
    return Plan(nodes={"original": PlanNode("original", _spec("original"))})


@pytest.mark.asyncio
async def test_empty_plan_rejected_before_state_change_or_callback():
    plan = Plan()
    original_gradient = plan.gradient
    calls = []

    async def execute(spec, inputs):
        calls.append(spec)
        return {"result": "must not execute"}

    with pytest.raises(ValueError, match="EMPTY_PLAN.*at least one node"):
        await _monitor().run_plan(plan, execute)
    assert plan.state is PlanState.DRAFT
    assert plan.gradient is original_gradient
    assert calls == []


@pytest.mark.asyncio
async def test_required_node_completion_remains_successful():
    calls = []

    async def execute(spec, inputs):
        calls.append(spec.name)
        return {"result": "completed-output"}

    result = await _monitor().run_plan(_plan(), execute)
    assert result.success is True
    assert result.plan.state is PlanState.COMPLETED
    assert result.results == {"original": "completed-output"}
    assert calls == ["original"]
    assert result.events[-1].event_type is PlanEventType.PLAN_COMPLETED


@pytest.mark.parametrize(
    "modification",
    [
        PlanModification(PlanModificationType.ADD_NODE),
        PlanModification(PlanModificationType.REMOVE_NODE),
        PlanModification(PlanModificationType.REPLACE_NODE),
        PlanModification.replace_node("absent", PlanNode("new", _spec("new"))),
        PlanModification(PlanModificationType.SKIP_NODE),
        PlanModification.skip_node("absent", "not present"),
        PlanModification(PlanModificationType.ADD_EDGE),
        PlanModification(PlanModificationType.REMOVE_EDGE),
        PlanModification(PlanModificationType.UPDATE_SPEC),
        PlanModification.update_spec("absent", _spec("new")),
    ],
)
@pytest.mark.asyncio
async def test_malformed_boundary_recovery_is_not_recorded_applied(modification):
    plan = _plan()
    calls = []

    async def execute(spec, inputs):
        calls.append(spec.name)
        return {"error": "deterministic failure"}

    result = await _monitor([modification]).run_plan(plan, execute)
    assert result.success is False
    assert sorted(plan.nodes) == ["original"]
    assert plan.edges == []
    assert calls == ["original"]
    assert result.modifications_applied == []
    assert not any(
        event.event_type is PlanEventType.MODIFICATION_APPLIED
        for event in result.events
    )


@pytest.mark.parametrize(
    "modifications", [[], [PlanModification.remove_node("absent")]]
)
@pytest.mark.asyncio
async def test_no_change_recovery_is_not_recorded_applied(modifications):
    async def execute(spec, inputs):
        return {"error": "deterministic failure"}

    monitor = _monitor(modifications)
    original_handle = monitor._handle_held_event
    recovery_outcomes = []

    async def observe_recovery(**kwargs):
        outcome = await original_handle(**kwargs)
        recovery_outcomes.append(outcome)
        return outcome

    monitor._handle_held_event = observe_recovery
    result = await monitor.run_plan(_plan(), execute)
    assert result.success is False
    assert recovery_outcomes == [False]
    assert result.modifications_applied == []
    assert not any(
        event.event_type is PlanEventType.MODIFICATION_APPLIED
        for event in result.events
    )


@pytest.mark.asyncio
async def test_removing_last_node_cannot_turn_failure_into_success():
    modification = PlanModification.remove_node("original")

    async def execute(spec, inputs):
        return {"error": "deterministic failure"}

    result = await _monitor([modification]).run_plan(_plan(), execute)
    assert result.plan.nodes == {}
    assert result.modifications_applied == [modification]
    assert result.success is False
    assert result.plan.state is PlanState.FAILED
    assert result.events[-1].event_type is PlanEventType.PLAN_FAILED


@pytest.mark.asyncio
async def test_real_replacement_records_exact_modification_and_completes():
    replacement = PlanNode("replacement", _spec("replacement"))
    modification = PlanModification.replace_node("original", replacement)
    calls = []

    async def execute(spec, inputs):
        calls.append(spec.name)
        if spec.name == "original":
            return {"error": "deterministic failure"}
        return {"result": "replacement-output"}

    result = await _monitor([modification]).run_plan(_plan(), execute)
    assert result.success is True
    assert result.plan.nodes == {"replacement": replacement}
    assert result.results == {"replacement": "replacement-output"}
    assert calls == ["original", "replacement"]
    assert result.modifications_applied == [modification]
    applied = [
        event
        for event in result.events
        if event.event_type is PlanEventType.MODIFICATION_APPLIED
    ]
    assert len(applied) == 1
    assert applied[0].modification is modification


def test_mutation_outcomes_distinguish_changes_from_idempotent_operations():
    monitor = _monitor()
    plan = _plan()
    assert (
        monitor._apply_modification(plan, PlanModification.remove_node("absent"))
        is False
    )
    original_spec = plan.nodes["original"].agent_spec
    assert (
        monitor._apply_modification(
            plan, PlanModification.update_spec("original", original_spec)
        )
        is False
    )
    changed_spec = _spec("changed")
    assert (
        monitor._apply_modification(
            plan, PlanModification.update_spec("original", changed_spec)
        )
        is True
    )
    assert plan.nodes["original"].agent_spec is changed_spec
    skip = PlanModification.skip_node("original", "fixture")
    assert monitor._apply_modification(plan, skip) is True
    assert plan.nodes["original"].state is PlanNodeState.SKIPPED
    assert monitor._apply_modification(plan, skip) is False
    new = PlanNode("new", _spec("new"))
    assert monitor._apply_modification(plan, PlanModification.add_node(new)) is True
    assert monitor._apply_modification(plan, PlanModification.add_node(new)) is False
    assert (
        monitor._apply_modification(plan, PlanModification.replace_node("new", new))
        is False
    )
    edge = PlanEdge("original", "new")
    assert monitor._apply_modification(plan, PlanModification.add_edge(edge)) is True
    assert monitor._apply_modification(plan, PlanModification.add_edge(edge)) is False
    remove_edge = PlanModification.remove_edge("original", "new")
    assert monitor._apply_modification(plan, remove_edge) is True
    assert monitor._apply_modification(plan, remove_edge) is False
    remove = PlanModification.remove_node("new")
    assert monitor._apply_modification(plan, remove) is True
    assert monitor._apply_modification(plan, remove) is False
