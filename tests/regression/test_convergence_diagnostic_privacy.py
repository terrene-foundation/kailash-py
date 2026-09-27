"""Convergence failures terminate safely without automatic payload diagnostics."""

import io
import logging
from contextlib import contextmanager

import pytest

from kailash.nodes.logic.operations import SwitchNode
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime
from kailash.workflow.convergence import create_convergence_condition
from kailash.workflow.cycle_state import CycleState
from kailash.workflow.graph import Workflow
from tests.regression.test_cycle_runtime_contract import Consume, Tick, close

PRIVATE = "convergence-person@example.invalid"
LOGGER = "kailash.workflow.convergence"


@contextmanager
def capture(caplog):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger(LOGGER)
    logger.addHandler(handler)
    try:
        with caplog.at_level(logging.DEBUG, logger=LOGGER):
            yield stream
    finally:
        logger.removeHandler(handler)
        handler.close()


def assert_private_failure(caplog, stream, event, error_type):
    records = [r for r in caplog.records if r.name == LOGGER]
    failures = [r for r in records if r.levelno >= logging.WARNING]
    assert len(failures) == 1
    record = failures[0]
    assert record.getMessage() == event
    assert record.error_type == error_type
    assert record.error_frames
    assert record.exc_info is None
    assert PRIVATE not in repr([vars(r) for r in records])
    assert PRIVATE not in stream.getvalue()
    assert stream.getvalue().splitlines()[-1] == event
    assert len(stream.getvalue().splitlines()) == len(records)
    assert "\n" not in record.error_type and "\r" not in record.error_type


@pytest.mark.parametrize("kind", ["expression", "callback"])
@pytest.mark.parametrize("hostile", [False, True])
def test_failed_conditions_keep_termination_and_descriptions_private_in_logs(
    caplog, kind, hostile
):
    state = CycleState("privacy")
    error_type = type(
        "Provider\nFailure" if hostile else "ProviderFailure", (ValueError,), {}
    )
    error = error_type(PRIVATE)
    error.__cause__ = ValueError(PRIVATE)
    calls = []

    def callback(results, actual_state):
        calls.append((results, actual_state))
        raise error

    spec = (
        {"type": "expression", "expression": f"results['{PRIVATE}']"}
        if kind == "expression"
        else {"type": "callback", "callback": callback, "name": PRIVATE}
    )
    condition = create_convergence_condition(spec)
    description = condition.describe()
    with capture(caplog) as stream:
        assert condition.evaluate({}, state) is True
    assert condition.describe() == description
    assert PRIVATE in description
    if kind == "callback":
        assert calls == [({}, state)]
        expected_type = "Provider?Failure" if hostile else "ProviderFailure"
    else:
        assert calls == []
        expected_type = "KeyError"
    assert_private_failure(
        caplog,
        stream,
        f"{kind.capitalize()} evaluation failed; terminating cycle",
        expected_type,
    )


@pytest.mark.parametrize("kind", ["expression", "callback"])
@pytest.mark.parametrize("result", [True, False])
def test_successful_conditions_preserve_true_false_and_emit_no_failure(
    caplog, kind, result
):
    spec = (
        "results['done']"
        if kind == "expression"
        else lambda results, state: results["done"]
    )
    condition = create_convergence_condition(spec)
    with capture(caplog) as stream:
        assert condition.evaluate({"done": result}, CycleState("success")) is result
    records = [r for r in caplog.records if r.name == LOGGER]
    assert not [r for r in records if r.levelno >= logging.WARNING]
    if kind == "expression":
        assert len(records) == 4 and records[-1].converged is result
    else:
        assert records == [] and stream.getvalue() == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
async def test_public_cycle_stops_after_failed_private_expression(runtime_type, caplog):
    workflow = Workflow("private_convergence", "Private convergence")
    tick, consumer = Tick(), Consume()
    workflow.add_node("tick", tick)
    workflow.add_node("gate", SwitchNode, condition_field="n", operator="<", value=2)
    workflow.add_node("consume", consumer)
    workflow.connect("tick", "gate", {"result": "input_data"})
    workflow.connect("gate", "consume", {"false_output": "input_data"})
    workflow.create_cycle("loop").connect(
        "gate", "tick", {"true_output": "input_data"}
    ).max_iterations(3).converge_when(f"results['{PRIVATE}']").build()
    runtime = runtime_type()
    try:
        with capture(caplog) as stream:
            results, run_id = await runtime.execute_async(workflow)
        assert isinstance(run_id, str)
        assert tick.calls == 1 and consumer.calls == 0
        assert results["tick"] == {"result": {"n": 1}}
        assert results["gate"]["true_output"] == {"n": 1}
        assert results["consume"] is None
        assert_private_failure(
            caplog,
            stream,
            "Expression evaluation failed; terminating cycle",
            "KeyError",
        )
    finally:
        await close(runtime)


def test_expression_debug_records_omit_private_values_and_keys(caplog):
    condition = create_convergence_condition(f"results['{PRIVATE}']")
    with capture(caplog) as stream:
        assert (
            condition.evaluate(
                {
                    PRIVATE: PRIVATE,
                    "private_context_key": PRIVATE,
                    "should_continue": PRIVATE,
                },
                CycleState("debug"),
            )
            is True
        )
    records = [r for r in caplog.records if r.name == LOGGER]
    assert len(records) == 4
    assert [r.getMessage() for r in records] == [
        "Evaluating convergence expression",
        "Convergence context prepared",
        "Convergence continuation input",
        "Convergence expression evaluated",
    ]
    assert records[1].variable_count == 13
    assert records[2].present is True and records[3].converged is True
    assert PRIVATE not in repr([vars(r) for r in records])
    assert "private_context_key" not in repr([vars(r) for r in records])
    assert (
        PRIVATE not in stream.getvalue()
        and "private_context_key" not in stream.getvalue()
    )
