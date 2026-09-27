"""Real workflow/resource paths retain public values while bounding diagnostics."""

import io
import logging

import pytest

from kailash.nodes.base import Node, NodeParameter
from kailash.resources.factory import ResourceFactory
from kailash.resources.registry import ResourceRegistry
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.contracts import ConnectionContract
from kailash.workflow.graph import Workflow

LOGGERS = (
    "kailash.workflow.builder",
    "kailash.workflow.graph",
    "kailash.resources.registry",
)
VALUES = [
    "ordinary",
    "line\nFORGED",
    "line\rFORGED",
    "line\u2028FORGED",
    "line\u202eFORGED",
    "line\ud800FORGED",
    "long-" + "x" * 5000,
]
SECRET = "credential-value-must-not-appear"


@pytest.fixture
def diagnostics(caplog):
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    for name in LOGGERS:
        caplog.set_level(logging.DEBUG, logger=name)
        logging.getLogger(name).addHandler(handler)
    yield caplog, output
    for name in LOGGERS:
        logging.getLogger(name).removeHandler(handler)
    handler.close()


def assert_safe_diagnostics(diagnostics, *, secret=None):
    caplog, output = diagnostics
    records = [record for record in caplog.records if record.name in LOGGERS]
    assert records
    for record in records:
        text = record.getMessage()
        assert text.isprintable()
        assert len(text) < 4096
        assert secret is None or secret not in text
    # The real handler must emit exactly one UTF-8 physical line per record.
    emitted = output.getvalue()
    assert len(emitted.encode("utf-8").splitlines()) == len(records)


class ValueNode(Node):
    def get_parameters(self):
        return {"value": NodeParameter(name="value", type=str, required=False)}

    def run(self, **kwargs):
        return {"result": kwargs.get("value", SECRET)}


@pytest.mark.parametrize("value", VALUES)
def test_builder_graph_keep_identifiers_and_ports(diagnostics, value):
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", value, {"code": "result = 1"})
    builder.add_node("PythonCodeNode", "target", {"code": "result = 2"})
    builder.add_connection(value, value, "target", value)
    workflow = builder.build(workflow_id=value)
    assert workflow.workflow_id == value
    assert value in builder.nodes and value in workflow.nodes
    assert builder.connections[0]["from_output"] == value
    assert builder.connections[0]["to_input"] == value
    assert workflow.connections[0].source_node == value
    assert workflow.connections[0].source_output == value
    assert workflow.connections[0].target_input == value
    assert workflow.graph.get_edge_data(value, "target")["mapping"] == {value: value}
    workflow.validate()
    assert_safe_diagnostics(diagnostics)


@pytest.mark.parametrize("pattern", ["class", "instance", "dict", "list"])
def test_builder_sibling_creation_paths(diagnostics, pattern):
    value = "node\nFORGED"
    builder = WorkflowBuilder()
    if pattern == "class":
        with pytest.warns(UserWarning, match="CUSTOM NODE USAGE CORRECT"):
            builder.add_node(ValueNode, value, {})
    elif pattern == "instance":
        with pytest.warns(UserWarning, match="Instance-based API usage detected"):
            builder.add_node(ValueNode(), value)
    elif pattern == "dict":
        builder = WorkflowBuilder.from_dict(
            {"nodes": {value: {"type": "PythonCodeNode", "parameters": []}}}
        )
    else:
        builder = WorkflowBuilder.from_dict(
            {"nodes": [{"id": value, "type": "PythonCodeNode", "parameters": []}]}
        )
    assert value in builder.nodes
    assert_safe_diagnostics(diagnostics)


def test_graph_execution_retains_values_without_logging_configuration(diagnostics):
    value = "node\nFORGED"
    graph = Workflow("id\nFORGED", "name\nFORGED")
    graph.add_node(value, ValueNode(value=SECRET))
    graph.add_node("target", ValueNode())
    graph.connect(value, "target", {"result": "value"})
    assert graph.execute() == {value: {"result": SECRET}, "target": {"result": SECRET}}
    assert graph.nodes[value].config["value"] == SECRET
    assert_safe_diagnostics(diagnostics, secret=SECRET)


def test_cycle_configuration_is_retained_but_not_logged(diagnostics):
    graph = Workflow("cycle", "cycle")
    graph.add_node("one", ValueNode())
    graph.add_node("two", ValueNode())
    graph.connect("one", "two", {"result": "value"})
    cycle_id = "cycle\nFORGED"
    graph.create_cycle(cycle_id).connect(
        "two", "one", mapping={"result": "value"}
    ).max_iterations(2).converge_when(SECRET).build()
    cycle = graph.connections[-1]
    assert cycle.cycle_id == cycle_id
    assert cycle.convergence_check == SECRET
    assert cycle.max_iterations == 2
    assert graph.get_cycle_groups()
    assert_safe_diagnostics(diagnostics, secret=SECRET)


class Resource:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class Factory(ResourceFactory):
    def __init__(self, error=None):
        self.error = error
        self.created = []

    async def create(self):
        if self.error is not None:
            raise self.error
        resource = Resource()
        self.created.append(resource)
        return resource

    def get_config(self):
        return {}


class PayloadError(ValueError):
    def __init__(self):
        super().__init__(SECRET + "\nFORGED_ERROR")
        self.render_calls = 0

    def __str__(self):
        self.render_calls += 1
        return SECRET + "\nFORGED_ERROR"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", VALUES)
async def test_registry_identity_and_lifetime_are_unchanged(diagnostics, name):
    registry = ResourceRegistry()
    factory = Factory()
    registry.register_factory(name, factory)
    registry.register_factory(name, factory)
    try:
        first = await registry.get_resource(name)
        assert await registry.get_resource(name) is first
        assert registry._resources[name] is first
        assert registry._metrics["resource_accesses"][name] == 2
    finally:
        await registry.cleanup()
    assert len(factory.created) == 1 and first.closed
    assert_safe_diagnostics(diagnostics)


@pytest.mark.asyncio
async def test_registry_creation_error_identity_and_circuit_breaker(diagnostics):
    registry = ResourceRegistry()
    error = PayloadError()
    name = "resource\nFORGED"
    registry.register_factory(
        name, Factory(error), metadata={"circuit_breaker_threshold": 1}
    )
    try:
        with pytest.raises(PayloadError) as caught:
            await registry.get_resource(name)
        assert caught.value is error
        assert registry._circuit_breakers[name]["state"] == "open"
        assert error.render_calls == 0
    finally:
        await registry.cleanup()
    assert_safe_diagnostics(diagnostics, secret=SECRET)


@pytest.mark.asyncio
async def test_registry_health_and_cleanup_failure_paths(diagnostics):
    registry = ResourceRegistry()
    error = PayloadError()
    factory = Factory()

    async def health(resource):
        raise error

    async def cleanup(resource):
        await resource.close()
        raise error

    name = "resource\nFORGED"
    registry.register_factory(
        name, factory, health_check=health, cleanup_handler=cleanup
    )
    try:
        first = await registry.get_resource(name)
        second = await registry.get_resource(name)
        assert first is not second and first.closed
        assert registry._resources[name] is second
        assert registry._metrics["health_check_failures"][name] == 1
        assert registry._metrics["resource_recreations"][name] == 1
    finally:
        await registry.cleanup()
    assert second.closed and error.render_calls == 0
    assert_safe_diagnostics(diagnostics, secret=SECRET)


def test_parameter_issue_details_remain_public_without_entering_logs(diagnostics):
    builder = WorkflowBuilder()
    with pytest.warns(UserWarning, match="CUSTOM NODE USAGE CORRECT"):
        builder.add_node(ValueNode, "node\nFORGED", {SECRET: "configuration"})
    issues = builder.validate_parameter_declarations()
    assert any(SECRET in issue.message for issue in issues)
    assert any(issue.code == "PAR002" for issue in issues)
    assert_safe_diagnostics(diagnostics, secret=SECRET)


def test_typed_connection_preserves_contract_identity(diagnostics):
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "source", {"code": "result = 'value'"})
    builder.add_node("PythonCodeNode", "target", {"code": "result = data"})
    contract = ConnectionContract(
        name="contract\nFORGED",
        source_schema={"type": "string"},
        target_schema={"type": "string"},
    )
    builder.add_typed_connection(
        "source", "result", "target", "data", contract=contract
    )
    assert next(iter(builder.connection_contracts.values())) is contract
    assert contract.name == "contract\nFORGED"
    assert_safe_diagnostics(diagnostics)


@pytest.mark.parametrize("phase", ["run", "task"])
def test_graph_tracking_callbacks_do_not_render_exception_payload(diagnostics, phase):
    error = PayloadError()

    class FailedTracking:
        def create_run(self, **kwargs):
            if phase == "run":
                raise error
            return "run-id"

        def create_task(self, **kwargs):
            raise error

    graph = Workflow("tracking", "tracking")
    graph.add_node("node\nFORGED", ValueNode())
    assert graph.execute(task_manager=FailedTracking()) == {
        "node\nFORGED": {"result": SECRET}
    }
    assert error.render_calls == 0
    assert_safe_diagnostics(diagnostics, secret=SECRET)


@pytest.mark.parametrize("shape", ["url", "query", "json"])
@pytest.mark.asyncio
async def test_recognized_credentials_in_metadata_are_log_only_transforms(
    diagnostics, shape
):
    import json

    payload = {
        "url": f"https://user:{SECRET}@example.invalid/path",
        "query": f"https://example.invalid/path?token={SECRET}",
        "json": json.dumps({"password": SECRET, "description": "node"}),
    }[shape]
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", payload, {"code": "result=1"})
    builder.add_node("PythonCodeNode", "target", {"code": "result=2"})
    builder.add_connection(payload, payload, "target", payload)
    workflow = builder.build(workflow_id=payload)
    assert workflow.workflow_id == payload
    assert payload in workflow.nodes
    assert workflow.connections[0].source_output == payload
    assert workflow.connections[0].target_input == payload
    assert workflow.graph.get_edge_data(payload, "target")["mapping"] == {
        payload: payload
    }
    registry = ResourceRegistry()
    factory = Factory()
    registry.register_factory(payload, factory)
    try:
        resource = await registry.get_resource(payload)
        assert registry._resources[payload] is resource
    finally:
        await registry.cleanup()
    assert resource.closed
    assert_safe_diagnostics(diagnostics, secret=SECRET)


def test_safe_log_field_normalizes_hostile_string_and_total_object_formatter():
    from kailash.utils.secure_logging import safe_log_field, sanitize_log_value

    class HostileText(str):
        def __str__(self):
            raise AssertionError("must not call custom string conversion")

        def __len__(self):
            return 0

    class HostileObject:
        def __str__(self):
            raise ValueError("private exception payload")

    value = HostileText(
        f"https://u:{SECRET}@example.invalid/" + "x" * 5000 + "\nFORGED"
    )
    rendered = safe_log_field(value)
    assert SECRET not in rendered
    assert rendered.isprintable() and len(rendered) <= 256
    assert safe_log_field(HostileObject()) == "<unrepresentable>"
    assert SECRET in sanitize_log_value(
        f"password={SECRET}"
    )  # Existing API remains structural-only.


def test_safe_log_field_masking_failure_is_total_and_omits_original(monkeypatch):
    from kailash.utils import secure_logging

    reached = []

    def failing_mask(value):
        reached.append(value)
        raise ValueError(SECRET)

    monkeypatch.setattr(secure_logging, "mask_error_text", failing_mask)
    assert secure_logging.safe_log_field(SECRET) == "<unrepresentable>"
    assert reached == [SECRET]


@pytest.mark.parametrize(
    "rendering",
    [
        f"https://user:{SECRET}@example.invalid/path",
        f"https://example.invalid/path?token={SECRET}",
        '{"password": "' + SECRET + '"}',
    ],
)
@pytest.mark.parametrize("kind", ["bytes", "object"])
def test_registry_nonstring_identifiers_mask_recognized_credentials(
    diagnostics, rendering, kind
):
    class RenderedIdentity:
        def __str__(self):
            return rendering

    identity = rendering.encode() if kind == "bytes" else RenderedIdentity()
    factory = object()
    registry = ResourceRegistry()
    registry.register_factory(identity, factory)
    assert list(registry._factories) == [identity]
    assert registry._factories[identity] is factory
    assert_safe_diagnostics(diagnostics, secret=SECRET)


def test_registry_nonstring_conversion_failure_does_not_expose_error(diagnostics):
    class BrokenIdentity:
        def __str__(self):
            raise ValueError(SECRET)

    identity = BrokenIdentity()
    registry = ResourceRegistry()
    registry.register_factory(identity, object())
    assert identity in registry._factories
    assert_safe_diagnostics(diagnostics, secret=SECRET)
    assert "<unrepresentable>" in diagnostics[1].getvalue()


def test_registry_opaque_tuple_and_invalid_utf8_never_render_payload(diagnostics):
    registry = ResourceRegistry()
    identities = (("password", SECRET), b"\xff" + SECRET.encode())
    for identity in identities:
        registry.register_factory(identity, object())
        assert identity in registry._factories
    assert_safe_diagnostics(diagnostics, secret=SECRET)
    assert diagnostics[1].getvalue().count("<unrepresentable>") == 2
