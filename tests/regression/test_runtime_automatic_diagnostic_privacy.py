"""Runtime diagnostics preserve errors and outputs without logging their values."""

import asyncio
import io
import json
import logging
from pathlib import Path

import pytest

from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.base_async import AsyncNode
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.local import ContentAwareExecutionError, LocalRuntime
from kailash.workflow.graph import Workflow

PRIVATE = "runtime-person@example.invalid"
pytestmark = pytest.mark.regression


class DiagnosticSource(Node):
    def __init__(self, mode="success", **kwargs):
        self.mode = mode
        super().__init__(**kwargs)

    def get_parameters(self):
        return {}

    def run(self, **kwargs):
        if self.mode == "content":
            return {"success": False, "error": PRIVATE}
        if self.mode == "raised":
            raise ValueError(PRIVATE)
        return {"payload": {"value": PRIVATE}}


class DiagnosticConsumer(Node):
    def get_parameters(self):
        return {"value": NodeParameter(name="value", type=str, required=True)}

    def run(self, **kwargs):
        return {"result": kwargs["value"]}


@pytest.fixture
def diagnostics():
    records = []
    stream = io.StringIO()

    class Capture(logging.StreamHandler):
        def emit(self, record):
            records.append(dict(record.__dict__))
            super().emit(record)

    logger = logging.getLogger("kailash")
    previous = logger.level
    handler = Capture(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        yield stream, records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)


def assert_private(diagnostics):
    stream, records = diagnostics
    assert records
    assert PRIVATE not in stream.getvalue()
    assert PRIVATE not in json.dumps(records, default=str)
    assert all(r["exc_info"] is None for r in records)


def workflow(mode, connected=False):
    graph = Workflow("diagnostic_privacy", name="diagnostic_privacy")
    graph.add_node("source", DiagnosticSource(mode=mode))
    if connected:
        graph.add_node("consumer", DiagnosticConsumer())
        graph.connect("source", "consumer", mapping={"payload.value": "value"})
    return graph


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["local", "async"])
@pytest.mark.parametrize("debug", [False, True])
@pytest.mark.parametrize("mode", ["content", "raised"])
async def test_public_failure_keeps_error_and_omits_automatic_payload(
    kind, debug, mode, diagnostics
):
    runtime = (
        LocalRuntime(debug=debug) if kind == "local" else AsyncLocalRuntime(debug=debug)
    )
    events = []
    runtime.on_node_complete(events.append)
    with runtime:
        try:
            with pytest.raises(Exception) as caught:
                if kind == "local":
                    runtime.execute(workflow(mode, connected=mode == "raised"))
                else:
                    await runtime.execute_async(
                        workflow(mode, connected=mode == "raised")
                    )
            assert PRIVATE in str(caught.value)
            if mode == "content":
                assert isinstance(caught.value, ContentAwareExecutionError)
                assert caught.value.failure_data == {"success": False, "error": PRIVATE}
            assert events == []
            assert_private(diagnostics)
            assert any(r["levelno"] >= logging.ERROR for r in diagnostics[1])
        finally:
            if kind == "async":
                await runtime.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["local", "async"])
async def test_debug_nested_mapping_keeps_outputs_without_logging_values(
    kind, diagnostics
):
    runtime = (
        LocalRuntime(debug=True) if kind == "local" else AsyncLocalRuntime(debug=True)
    )
    with runtime:
        try:
            graph = workflow("success", connected=True)
            results, run_id = (
                runtime.execute(graph)
                if kind == "local"
                else await runtime.execute_async(graph)
            )
            assert results["source"] == {"payload": {"value": PRIVATE}}
            assert results["consumer"] == {"result": PRIVATE}
            assert run_id
            assert_private(diagnostics)
        finally:
            if kind == "async":
                await runtime.cleanup()


@pytest.mark.asyncio
async def test_caller_cancellation_remains_exact_and_owned_resources_close(diagnostics):
    error = asyncio.CancelledError(PRIVATE)

    class CancelNode(AsyncNode):
        def get_parameters(self):
            return {}

        async def execute_async(self, **kwargs):
            raise error

    graph = Workflow("cancel_privacy", name="cancel_privacy")
    graph.add_node("cancel", CancelNode())
    runtime = AsyncLocalRuntime(debug=True)
    with runtime:
        try:
            with pytest.raises(asyncio.CancelledError) as caught:
                await runtime.execute_async(graph)
            assert caught.value is error
            assert str(caught.value) == PRIVATE
            assert_private(diagnostics)
        finally:
            await runtime.cleanup()


def test_runtime_source_is_pinned():
    import kailash.runtime.local as module

    assert (
        Path(module.__file__).resolve()
        == Path(__file__).resolve().parents[2] / "src/kailash/runtime/local.py"
    )


@pytest.mark.asyncio
async def test_task_error_during_cancellation_keeps_cleanup_and_safe_diagnostic(
    diagnostics,
):
    from kailash.runtime.async_local import ExecutionContext

    started = asyncio.Event()
    finalized = []

    async def resource():
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            finalized.append(True)
            raise ValueError(PRIVATE)

    context = ExecutionContext()
    task = asyncio.create_task(resource())
    context.tasks.append(task)
    await started.wait()
    await context.cancel_all_tasks()
    assert task.done() and isinstance(task.exception(), ValueError)
    assert str(task.exception()) == PRIVATE
    assert finalized == [True]
    assert_private(diagnostics)
    assert any(
        "raised error during cancellation" in str(r["msg"]) for r in diagnostics[1]
    )
    await context.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["local", "async"])
async def test_content_opt_out_preserves_failure_output(kind, diagnostics):
    runtime = (LocalRuntime if kind == "local" else AsyncLocalRuntime)(
        debug=True, content_aware_success_detection=False
    )
    with runtime:
        try:
            graph = workflow("content")
            results, _ = (
                runtime.execute(graph)
                if kind == "local"
                else await runtime.execute_async(graph)
            )
            assert results["source"] == {"success": False, "error": PRIVATE}
            assert_private(diagnostics)
        finally:
            if kind == "async":
                await runtime.cleanup()


def test_local_continue_error_result_retains_original_payload(diagnostics):
    with LocalRuntime(debug=True) as runtime:
        results, _ = runtime.execute(workflow("raised"))
    assert results["source"]["failed"] is True
    assert PRIVATE in results["source"]["error"]
    assert PRIVATE in str(results["source"]["_exception"])
    assert_private(diagnostics)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["local", "async"])
async def test_context_exit_uses_safe_exception_type_and_preserves_error(
    kind, diagnostics
):
    error_type = type("Injected\nERROR " + PRIVATE, (ValueError,), {})
    error = error_type(PRIVATE)
    runtime = (LocalRuntime if kind == "local" else AsyncLocalRuntime)(debug=True)
    with pytest.raises(error_type) as caught:
        with runtime:
            try:
                raise error
            finally:
                if kind == "async":
                    await runtime.cleanup()
    assert caught.value is error
    assert runtime._ref_count == 0
    assert_private(diagnostics)
    assert "Injected\nERROR" not in diagnostics[0].getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["local", "async"])
@pytest.mark.parametrize("nested", [False, True])
async def test_missing_mapping_logs_counts_without_private_output_keys(
    kind, nested, diagnostics
):
    class PrivateKeys(Node):
        def get_parameters(self):
            return {}

        def run(self, **kwargs):
            return {"payload": {PRIVATE: 123}} if nested else {PRIVATE: 123}

    class OptionalConsumer(Node):
        def get_parameters(self):
            return {
                "value": NodeParameter(
                    name="value", type=str, required=False, default="nothing"
                )
            }

        def run(self, **kwargs):
            return {"result": kwargs.get("value", "nothing")}

    graph = Workflow("missing_private_key", name="missing_private_key")
    graph.add_node("source", PrivateKeys())
    graph.add_node("consumer", OptionalConsumer())
    graph.connect(
        "source",
        "consumer",
        mapping={"payload.missing" if nested else "missing": "value"},
    )
    runtime = (LocalRuntime if kind == "local" else AsyncLocalRuntime)(debug=True)
    with runtime:
        try:
            results, _ = (
                runtime.execute(graph)
                if kind == "local"
                else await runtime.execute_async(graph)
            )
            assert results["source"] == (
                {"payload": {PRIVATE: 123}} if nested else {PRIVATE: 123}
            )
            # Async simple-key mapping retains its whole-output fallback.
            expected = (
                str({PRIVATE: 123}) if kind == "async" and not nested else "nothing"
            )
            assert results["consumer"] == {"result": expected}
            assert_private(diagnostics)
            if kind == "local":
                assert "Available output count: 1" in diagnostics[0].getvalue()
        finally:
            if kind == "async":
                await runtime.cleanup()


def test_conditional_failure_preserves_real_fallback_and_private_error(
    monkeypatch, diagnostics
):
    from kailash.nodes.logic.operations import SwitchNode

    class Consumer(Node):
        def get_parameters(self):
            return {
                "input_data": NodeParameter(name="input_data", type=dict, required=True)
            }

        def run(self, **kwargs):
            return {"result": kwargs["input_data"]}

    graph = Workflow("conditional_privacy", name="conditional_privacy")
    graph.add_node(
        "switch", SwitchNode(condition_field="status", operator="==", value="active")
    )
    graph.add_node("consumer", Consumer())
    graph.connect("switch", "consumer", {"true_output": "input_data"})
    error = ValueError(PRIVATE)
    hits = []
    with LocalRuntime(conditional_execution="skip_branches", debug=True) as runtime:
        original = runtime._execute_switch_nodes

        async def fail_once(*args, **kwargs):
            if not hits:
                hits.append(error)
                raise error
            return await original(*args, **kwargs)

        monkeypatch.setattr(runtime, "_execute_switch_nodes", fail_once)
        results, run_id = runtime.execute(
            graph, parameters={"switch": {"input_data": {"status": "active"}}}
        )
    assert hits == [error]
    assert str(error) == PRIVATE
    assert results["consumer"] == {"result": {"status": "active"}}
    assert run_id
    assert_private(diagnostics)
    assert "Conditional execution failed" in diagnostics[0].getvalue()
    assert "Fallback used" in diagnostics[0].getvalue()


def test_conditional_failure_context_uses_metadata_only(diagnostics):
    error = type("Injected\nERROR " + PRIVATE, (ValueError,), {})(PRIVATE)
    graph = workflow("success")
    with LocalRuntime(debug=True) as runtime:
        runtime._log_conditional_execution_failure(
            graph, error, {"nodes_completed": 0, "private": PRIVATE}
        )
    assert str(error) == PRIVATE
    assert_private(diagnostics)
    assert "Execution context field count: 2" in diagnostics[0].getvalue()


@pytest.mark.parametrize("private_value", [None, "retained"])
def test_conditional_switch_output_keys_remain_private(private_value, diagnostics):
    from kailash.nodes.logic.operations import SwitchNode

    class PrivateKeySwitch(SwitchNode):
        def run(self, **kwargs):
            result = super().run(**kwargs)
            result[PRIVATE] = private_value
            return result

    graph = Workflow("conditional_keys", name="conditional_keys")
    graph.add_node(
        "switch",
        PrivateKeySwitch(condition_field="status", operator="==", value="active"),
    )
    with LocalRuntime(conditional_execution="skip_branches", debug=True) as runtime:
        result, _ = runtime.execute(
            graph, parameters={"switch": {"input_data": {"status": "active"}}}
        )
    assert result["switch"][PRIVATE] == private_value
    assert result["switch"]["true_output"] == {"status": "active"}
    assert_private(diagnostics)
