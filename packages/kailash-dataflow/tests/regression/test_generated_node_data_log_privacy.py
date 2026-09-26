"""Generated CRUD diagnostics must not publish arbitrary record values."""

import json
import logging
from pathlib import Path

import pytest

from dataflow import DataFlow
from dataflow.core import nodes
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

pytestmark = [pytest.mark.regression, pytest.mark.asyncio]


async def test_real_sqlite_crud_and_cache_logs_omit_record_values(tmp_path, caplog):
    root = Path(__file__).resolve().parents[4]
    assert Path(nodes.__file__).resolve() == (
        root / "packages/kailash-dataflow/src/dataflow/core/nodes.py"
    )
    identifier = "private_record_2026_09"
    email = "review.synthetic@example.invalid"
    note = "private_note_under_an_ordinary_key"
    db = DataFlow(
        f"sqlite:///{tmp_path / 'privacy.db'}", cache_enabled=True, test_mode=False
    )
    capture = logging.getLogger("dataflow.core.nodes")
    prior_level = capture.level
    results = {}
    try:

        @db.model
        class PrivacyLogRecord:
            id: str
            email: str
            note: str

        await db.initialize()
        capture.setLevel(logging.DEBUG)
        with LocalRuntime() as runtime:

            async def execute(label, operation, parameters):
                builder = WorkflowBuilder()
                builder.add_node(f"PrivacyLogRecord{operation}Node", "op", parameters)
                workflow = builder.build()
                node = workflow.get_node("op")
                level = node.logger.level
                node.logger.setLevel(logging.DEBUG)
                try:
                    output, _ = await runtime.execute_async(
                        workflow,
                        parameters={"workflow_context": {"dataflow_instance": db}},
                    )
                finally:
                    node.logger.setLevel(level)
                results[label] = output["op"]
                return output["op"]

            await execute(
                "create", "Create", {"id": identifier, "email": email, "note": note}
            )
            for label, cached in (("direct", False), ("cached", True), ("hit", True)):
                result = await execute(
                    label, "List", {"filter": {"email": email}, "enable_cache": cached}
                )
                assert result["records"][0]["email"] == email
                assert result["records"][0]["note"] == note
                assert result["records"][0]["id"] == identifier
            assert results["hit"]["_cache"]["hit"] is True
            count = await execute("count", "Count", {"filter": {"email": email}})
            assert count["count"] == 1
            await execute("delete", "Delete", {"id": identifier})
            remaining = await execute("remaining", "List", {"enable_cache": False})
            assert remaining["records"] == []

        records = [
            r
            for r in caplog.records
            if r.name == "dataflow.core.nodes" or r.getMessage().startswith("node.")
        ]
        events = [r.getMessage() for r in records]
        assert "nodes.inputs_received" in events
        assert "nodes.run" in events
        assert "nodes.list_operation_direct_result" in events
        assert "nodes.list_operation_cache_result" in events
        assert "nodes.count_operation_with_params" in events
        assert any(
            e in {"node.inputs_validated", "node.async_inputs_validated"}
            for e in events
        )
        # Check raw records as well as a downstream JSON handler's rendering:
        # a formatter that only prints getMessage() is blind to extra payloads.
        rendered = [json.dumps(r.__dict__, default=str) for r in records]
        for value in (identifier, email, note):
            assert not any(value in text for text in rendered), value
        assert not any(r.levelno >= logging.WARNING for r in records)
    finally:
        capture.setLevel(prior_level)
        await db.close_async()


@pytest.mark.parametrize("node_kind", ["sync", "async", "typed_async"])
async def test_core_input_diagnostics_omit_values_without_changing_execution(
    node_kind, caplog
):
    from kailash.nodes.base import AsyncTypedNode, Node, NodeParameter
    from kailash.nodes.base_async import AsyncNode

    class PayloadNode(Node):
        def get_parameters(self):
            return {"data": NodeParameter(name="data", type=dict, required=True)}

        def run(self, **kwargs):
            return {"data": kwargs["data"]}

    class PayloadAsyncNode(AsyncNode):
        def get_parameters(self):
            return {"data": NodeParameter(name="data", type=dict, required=True)}

        async def async_run(self, **kwargs):
            return {"data": kwargs["data"]}

    class PayloadTypedAsyncNode(AsyncTypedNode):
        def get_parameters(self):
            return {"data": NodeParameter(name="data", type=dict, required=True)}

        async def async_run(self, **kwargs):
            return {"data": kwargs["data"]}

    node = {
        "sync": PayloadNode,
        "async": PayloadAsyncNode,
        "typed_async": PayloadTypedAsyncNode,
    }[node_kind]()
    payload = {
        "ordinary_field": {
            "email": "input.synthetic@example.invalid",
            "nested": ["private_personal_note_2026"],
        }
    }
    with caplog.at_level(logging.DEBUG, logger=node.logger.name):
        if node_kind == "sync":
            result = node.execute(data=payload)
        else:
            result = await node.execute_async(data=payload)
    assert result == {"data": payload}
    records = [r for r in caplog.records if r.name == node.logger.name]
    validated = [
        r
        for r in records
        if r.getMessage() in {"node.inputs_validated", "node.async_inputs_validated"}
    ]
    assert len(validated) == 1
    assert validated[0].input_count == 1
    serialized = json.dumps([r.__dict__ for r in records], default=str)
    assert "input.synthetic@example.invalid" not in serialized
    assert "private_personal_note_2026" not in serialized
    assert not any(r.levelno >= logging.WARNING for r in records)


async def test_datetime_failure_diagnostic_keeps_input_out_of_raw_record(caplog):
    from datetime import datetime

    value = "birth_date.private@example.invalid"
    logger = logging.getLogger("dataflow.core.nodes")
    with caplog.at_level(logging.DEBUG, logger=logger.name):
        result = nodes.convert_datetime_fields(
            {"birth_date": value}, {"birth_date": datetime}, logger
        )
    assert result == {"birth_date": value}
    records = [r for r in caplog.records if r.getMessage() == "nodes.datetime.invalid"]
    assert len(records) == 1
    assert records[0].error_type == "ValueError"
    assert value not in json.dumps(records[0].__dict__, default=str)


@pytest.mark.parametrize("node_kind", ["sync", "async", "typed_async"])
async def test_execution_error_logs_omit_exception_payload_and_preserve_cause(
    node_kind, caplog
):
    from kailash.nodes.base import AsyncTypedNode, Node, NodeParameter
    from kailash.nodes.base_async import AsyncNode
    from kailash.sdk_exceptions import NodeExecutionError

    class FailureNode(Node):
        def get_parameters(self):
            return {"data": NodeParameter(name="data", type=str, required=True)}

        def run(self, **kwargs):
            raise ValueError(kwargs["data"])

    class FailureAsyncNode(AsyncNode):
        def get_parameters(self):
            return {"data": NodeParameter(name="data", type=str, required=True)}

        async def async_run(self, **kwargs):
            raise ValueError(kwargs["data"])

    class FailureTypedNode(AsyncTypedNode):
        def get_parameters(self):
            return {"data": NodeParameter(name="data", type=str, required=True)}

        async def async_run(self, **kwargs):
            raise ValueError(kwargs["data"])

    node = {
        "sync": FailureNode,
        "async": FailureAsyncNode,
        "typed_async": FailureTypedNode,
    }[node_kind]()
    payload = "failure.synthetic@example.invalid"
    with caplog.at_level(logging.DEBUG, logger=node.logger.name):
        with pytest.raises(NodeExecutionError) as caught:
            if node_kind == "sync":
                node.execute(data=payload)
            else:
                await node.execute_async(data=payload)
    assert isinstance(caught.value.__cause__, ValueError)
    assert str(caught.value.__cause__) == payload
    assert payload in str(caught.value)
    records = [r for r in caplog.records if r.name == node.logger.name]
    failures = [r for r in records if r.levelno == logging.ERROR]
    assert len(failures) == 1
    assert "ValueError" in failures[0].getMessage()
    assert failures[0].exc_info is None
    assert payload not in json.dumps([r.__dict__ for r in records], default=str)
    assert all(payload not in logging.Formatter().format(r) for r in records)


async def test_constructor_failure_and_async_error_diagnostics_omit_payload(caplog):
    from kailash.nodes.base import Node
    from kailash.nodes.base_async import AsyncNode
    from kailash.security import SecurityConfig, SecurityError

    payload = "sibling.synthetic@example.invalid"

    class ParameterFailureNode(Node):
        calls = 0

        def get_parameters(self):
            self.calls += 1
            if self.calls == 1:
                raise ValueError(payload)
            return {}

        def run(self, **kwargs):
            return {}

    class ValidationNode(AsyncNode):
        def get_parameters(self):
            return {}

        async def async_run(self, **kwargs):
            return {}

    with caplog.at_level(logging.DEBUG, logger="kailash.nodes"):
        constructed = ParameterFailureNode()
        assert constructed.execute() == {}
        node = ValidationNode()
        node.security_config = SecurityConfig(
            allowed_directories=["/tmp/permitted-privacy-probe"],
            enable_audit_logging=True,
        )
        with pytest.raises(SecurityError) as caught:
            await node.validate_and_sanitize_inputs(
                {"file_path": "/tmp/" + payload + "/record.txt"}
            )
        assert payload in str(caught.value)
        await node.log_error("fixed diagnostic", ValueError(payload))
        try:
            raise ValueError(payload)
        except ValueError as error:
            await node.log_error_with_traceback(error, operation="fixed-operation")
    records = [
        r
        for r in caplog.records
        if r.name.startswith("kailash.nodes.") or r.name == node.logger.name
    ]
    assert any(
        r.getMessage().startswith("node.parameters_unavailable") for r in records
    )
    assert any(
        r.getMessage().startswith("node.security_validation_failed") for r in records
    )
    assert any(
        r.getMessage() == "fixed diagnostic" and r.error_type == "ValueError"
        for r in records
    )
    assert any(
        "Operation failed: fixed-operation" in r.getMessage()
        and "ValueError" in r.getMessage()
        for r in records
    )
    assert payload not in json.dumps([r.__dict__ for r in records], default=str)
    assert all(payload not in logging.Formatter().format(r) for r in records)
