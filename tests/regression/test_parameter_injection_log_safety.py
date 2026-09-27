"""Deferred injection keeps raw values out of diagnostics and delays acquisition."""

import logging

import pytest

from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.parameter_injection import ParameterInjectionMixin
from kailash.runtime.parameter_injector import (
    DeferredConfigNode,
    WorkflowParameterInjector,
)
from kailash.workflow.graph import Workflow

SECRET = "parameter-secret-canary-584791"
LOGGER_NAMES = (
    "kailash.runtime.parameter_injector",
    "kailash.runtime.parameter_injection",
)


class ValueNode(Node):
    def get_parameters(self):
        return {"value": NodeParameter(name="value", type=str, required=False)}

    def run(self, **kwargs):
        return {"value": kwargs.get("value")}


class DeferredValueNode(ParameterInjectionMixin, ValueNode):
    pass


@pytest.mark.parametrize("kind", ["config", "mixin"])
@pytest.mark.parametrize(
    "identifier",
    [
        "ordinary",
        "line\nFORGED",
        "line\rFORGED",
        "line\u2028FORGED",
        "line\u202eFORGED",
        "line\ud800FORGED",
        "long-" + "x" * 5000,
        f"https://user:{SECRET}@host/path?token={SECRET}",
        f'{{"api_key":"{SECRET}"}}',
    ],
)
def test_injection_applies_aliases_and_precedence_without_initialization(
    caplog, kind, identifier
):
    for name in LOGGER_NAMES:
        caplog.set_level(logging.DEBUG, logger=name)
    node = (
        DeferredConfigNode(ValueNode, value="initial")
        if kind == "config"
        else DeferredValueNode(value="initial")
    )
    graph = Workflow("injection", "injection")
    graph.add_node(identifier, node)
    graph.metadata["_workflow_inputs"] = {identifier: {identifier: "value"}}
    injector = WorkflowParameterInjector(graph, debug=True)
    parameters = {identifier: SECRET}
    assert injector.transform_workflow_parameters(parameters) == {
        identifier: {"value": SECRET}
    }
    injector.inject_parameters(parameters)
    assert node.get_effective_config()["value"] == SECRET
    assert node._is_initialized is False
    injector.inject_parameters({identifier: "replacement"})
    assert node.get_effective_config()["value"] == "replacement"
    assert node._is_initialized is False
    initial = node._initial_config if kind == "config" else node._deferred_config
    assert initial["value"] == "initial"
    assert parameters == {identifier: SECRET}
    records = [r for r in caplog.records if r.name in LOGGER_NAMES]
    assert records
    for record in records:
        message = record.getMessage()
        assert message.isprintable()
        assert len(message) < 2048
        assert SECRET not in message


def test_regular_nodes_are_not_reconfigured():
    graph = Workflow("regular", "regular")
    node = ValueNode(value="initial")
    graph.add_node("node", node)
    injector = WorkflowParameterInjector(graph)
    assert injector.transform_workflow_parameters({"value": "new"}) == {
        "node": {"value": "new"}
    }
    injector.inject_parameters({"value": "new"})
    assert node.config["value"] == "initial"


@pytest.mark.parametrize("kind", ["config", "mixin"])
def test_deferred_setter_bounds_dynamic_class_names(caplog, kind):
    for name in LOGGER_NAMES:
        caplog.set_level(logging.DEBUG, logger=name)
    base = ValueNode if kind == "config" else DeferredValueNode
    dynamic = type("Value\nFORGED", (base,), {})
    node = DeferredConfigNode(dynamic) if kind == "config" else dynamic()
    if kind == "config":
        node.set_runtime_config(value=SECRET)
    else:
        node.set_runtime_parameters(value=SECRET)
    assert node.get_effective_config()["value"] == SECRET
    records = [r for r in caplog.records if r.name in LOGGER_NAMES]
    assert records
    assert all(
        SECRET not in r.getMessage() and r.getMessage().isprintable() for r in records
    )


def test_deferred_constructor_failure_logs_frames_without_payload(caplog):
    class UnavailableNode(ValueNode):
        def __init__(self, **kwargs):
            raise ValueError(SECRET + "\nFORGED")

    caplog.set_level(logging.DEBUG, logger=LOGGER_NAMES[0])
    node = DeferredConfigNode(UnavailableNode)
    node._initialize_if_needed()
    assert node._actual_node is None and not node._is_initialized
    records = [r for r in caplog.records if r.name in LOGGER_NAMES]
    assert any(r.levelno == logging.WARNING for r in records)
    assert all(
        SECRET not in r.getMessage() and r.getMessage().isprintable() for r in records
    )
