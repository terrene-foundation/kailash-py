"""The cycle-capable executor must also execute ordinary DAGs directly."""

import io
import logging
from uuid import UUID

import pytest

from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import WorkflowExecutionError
from kailash.tracking import TaskManager, TaskStatus
from kailash.tracking.storage.database import SQLiteStorage
from kailash.workflow.cyclic_runner import CyclicWorkflowExecutor
from kailash.workflow.graph import Workflow


class IncrementNode(Node):
    def get_parameters(self):
        return {
            "value": NodeParameter(name="value", type=int, required=False, default=0)
        }

    def run(self, **inputs):
        self.calls = getattr(self, "calls", 0) + 1
        if getattr(self, "fail", False):
            raise ValueError(getattr(self, "failure_message", "requested node failure"))
        return {"value": inputs["value"] + 1}


@pytest.mark.parametrize("use_runtime", [False, True])
@pytest.mark.parametrize("supplied_run_id", [None, "dag-dispatch-run"])
def test_acyclic_graph_uses_real_plan_and_forwards_inputs(
    use_runtime, supplied_run_id, caplog
):
    workflow = Workflow("acyclic_dispatch", "Acyclic dispatch")
    workflow.add_node("first", IncrementNode, value=1)
    workflow.add_node("second", IncrementNode, value=99)
    workflow.connect("first", "second", {"value": "value"})
    executor = CyclicWorkflowExecutor()
    runtime = LocalRuntime() if use_runtime else None
    try:
        with caplog.at_level(logging.WARNING):
            results, run_id = executor.execute(
                workflow,
                parameters={"first": {"value": 7}},
                run_id=supplied_run_id,
                runtime=runtime,
            )
        assert results == {"first": {"value": 8}, "second": {"value": 9}}
        assert workflow.get_node("first").calls == 1
        assert workflow.get_node("second").calls == 1
        if supplied_run_id:
            assert run_id == supplied_run_id
        else:
            assert str(UUID(run_id)) == run_id
        assert executor.cycle_state_manager.get_all_summaries() == {}
        assert not [
            record for record in caplog.records if record.levelno >= logging.WARNING
        ]
    finally:
        if runtime is not None:
            runtime.close()


def test_acyclic_executor_can_be_reused_with_new_parameters():
    workflow = Workflow("reusable_dag", "Reusable DAG")
    workflow.add_node("first", IncrementNode)
    executor = CyclicWorkflowExecutor()
    first, first_id = executor.execute(workflow, parameters={"first": {"value": 1}})
    second, second_id = executor.execute(workflow, parameters={"first": {"value": 9}})
    assert first == {"first": {"value": 2}}
    assert second == {"first": {"value": 10}}
    assert first_id != second_id
    assert workflow.get_node("first").calls == 2


def test_empty_acyclic_graph_returns_empty_results():
    result, run_id = CyclicWorkflowExecutor().execute(
        Workflow("empty_dag", "Empty DAG"), run_id="empty-run"
    )
    assert result == {}
    assert run_id == "empty-run"


def test_acyclic_plan_forwards_real_task_tracking(tmp_path, caplog):
    storage = SQLiteStorage(str(tmp_path / "tasks.sqlite"))
    manager = TaskManager(storage)
    workflow = Workflow("tracked_dag", "Tracked DAG")
    workflow.add_node("first", IncrementNode)
    run_id = manager.create_run(workflow.name)
    try:
        with caplog.at_level(logging.WARNING):
            results, returned_id = CyclicWorkflowExecutor().execute(
                workflow, task_manager=manager, run_id=run_id
            )
        assert returned_id == run_id
        assert results == {"first": {"value": 1}}
        tasks = manager.get_run_tasks(run_id)
        assert len(tasks) == 1
        assert tasks[0].node_id == "first"
        assert tasks[0].status == TaskStatus.COMPLETED
        assert tasks[0].result == {"value": 1}
        assert not [
            record for record in caplog.records if record.levelno >= logging.WARNING
        ]
    finally:
        storage.close()


def test_acyclic_failure_stops_dependents_and_clears_state(caplog):
    workflow = Workflow("failed_dag", "Failed DAG")
    workflow.add_node("first", IncrementNode)
    workflow.add_node("second", IncrementNode)
    workflow.connect("first", "second", {"value": "value"})
    workflow.get_node("first").fail = True
    private_value = "cycle-person@example.invalid\nFORGED"
    workflow.get_node("first").failure_message = private_value
    executor = CyclicWorkflowExecutor()
    executor.cycle_state_manager.get_or_create_state("previous-run")
    with pytest.raises(WorkflowExecutionError) as error:
        executor.execute(workflow)
    assert private_value in str(error.value)
    records = [r for r in caplog.records if r.name == "kailash.workflow.cyclic_runner"]
    assert len(records) == 1
    assert "ValueError" in records[0].getMessage()
    assert "cycle-person" not in repr(records[0].__dict__)
    assert "FORGED" not in logging.Formatter().format(records[0])
    assert workflow.get_node("first").calls == 1
    assert getattr(workflow.get_node("second"), "calls", 0) == 0
    assert executor.cycle_state_manager.get_all_summaries() == {}


@pytest.mark.parametrize("private_source", ["value", "key", "condition"])
def test_real_cycle_returns_private_payload_without_automatic_log_disclosure(
    private_source, caplog
):
    marker = "cycle-row-person@example.invalid"

    class PayloadNode(IncrementNode):
        def run(self, **inputs):
            result = super().run(**inputs)
            result["payload"] = marker
            if private_source == "key":
                result[marker] = "private-key-value"
            return result

    workflow = Workflow("private_cycle", "Private cycle")
    workflow.add_node("increment", PayloadNode)
    cycle = (
        workflow.create_cycle("repeat")
        .connect("increment", "increment", {"value": "value"})
        .max_iterations(2)
    )
    if private_source == "condition":
        cycle.converge_when(f"payload == '{marker}'")
    cycle.build()
    logger = logging.getLogger("kailash.workflow.cyclic_runner")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)
    executor = CyclicWorkflowExecutor()
    try:
        with caplog.at_level(logging.DEBUG, logger=logger.name):
            results, run_id = executor.execute(workflow, run_id="private-cycle-run")
        iterations = 1 if private_source == "condition" else 2
        expected = {"value": iterations, "payload": marker}
        if private_source == "key":
            expected[marker] = "private-key-value"
        assert results == {"increment": expected}
        assert run_id == "private-cycle-run"
        assert workflow.get_node("increment").calls == iterations
        assert executor.cycle_state_manager.get_all_summaries() == {}
        records = [r for r in caplog.records if r.name == logger.name]
        assert (
            len([r for r in records if "(before update)" in r.getMessage()])
            == iterations
        )
        assert all(marker not in repr(r.__dict__) for r in records)
        assert marker not in stream.getvalue()
        assert not [r for r in records if r.levelno >= logging.WARNING]
    finally:
        logger.removeHandler(handler)
        handler.close()


@pytest.mark.parametrize(
    "method", ["create_task", "update_task_status", "update_task_metrics"]
)
def test_cycle_task_diagnostic_omits_observer_error_payload(
    method, tmp_path, monkeypatch, caplog
):
    marker = "cycle-task-person@example.invalid\nFORGED"
    storage = SQLiteStorage(str(tmp_path / "cycle-tasks.sqlite"))
    manager = TaskManager(storage)
    run_id = manager.create_run("cycle-task-failure")
    calls = []

    def fail(*args, **kwargs):
        calls.append(method)
        raise ValueError(marker)

    monkeypatch.setattr(manager, method, fail)
    workflow = Workflow("cycle_tasks", "Cycle task failure")
    workflow.add_node("increment", IncrementNode)
    workflow.create_cycle("repeat").connect(
        "increment", "increment", {"value": "value"}
    ).max_iterations(2).build()
    try:
        results, returned_id = CyclicWorkflowExecutor().execute(
            workflow, task_manager=manager, run_id=run_id
        )
        assert results == {"increment": {"value": 2}}
        assert returned_id == run_id
        assert calls
        records = [
            r
            for r in caplog.records
            if r.name == "kailash.workflow.cyclic_runner"
            and r.levelno >= logging.WARNING
        ]
        assert records
        assert all("ValueError" in r.getMessage() for r in records)
        assert all("cycle-task-person" not in repr(r.__dict__) for r in records)
        assert all("FORGED" not in logging.Formatter().format(r) for r in records)
    finally:
        storage.close()
