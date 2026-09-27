"""Parameter callers preserve mappings and public errors while logging safe text."""

import logging
from contextlib import AsyncExitStack

import pytest

from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime
from kailash.runtime.parameter_injector import WorkflowParameterInjector
from kailash.sdk_exceptions import NodeValidationError
from kailash.workflow.graph import Workflow

SECRET = "parameter-caller-canary-418275"
KEYS = [
    f"https://user:{SECRET}@example.invalid/?token={SECRET}",
    f'{{"password":"{SECRET}"}}',
    "unused\nFORGED\r\u2028\u202e\ud800",
    "unused-" + "x" * 5000,
]


class CallerNode(Node):
    def get_parameters(self):
        return {
            "value": NodeParameter(name="value", type=int, required=False, default=9)
        }

    def run(self, **kwargs):
        return {"value": kwargs.get("value")}


def graph(node_id="node"):
    workflow = Workflow("caller", "caller")
    workflow.add_node(node_id, CallerNode())
    return workflow


def assert_safe(caplog):
    records = [
        r
        for r in caplog.records
        if r.name in {"kailash.runtime.base", "kailash.nodes.base"}
    ]
    assert records
    for record in records:
        text = record.getMessage()
        assert SECRET not in text
        assert text.isprintable()
        assert len(text) < 1800
    return records


@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
@pytest.mark.parametrize("key", KEYS)
@pytest.mark.asyncio
async def test_shared_runtime_parameter_helpers_keep_raw_keys_and_values(
    caplog, runtime_type, key
):
    caplog.set_level(logging.DEBUG)
    node_id = "node-" + key
    workflow = graph(node_id)
    node_parameters = {"value": "7"}
    supplied = {node_id: node_parameters, "value": "5", key: "unused"}
    warnings = WorkflowParameterInjector(workflow).validate_parameters({key: "unused"})
    assert len(warnings) == 1 and repr(key) in warnings[0]
    caplog.clear()
    async with AsyncExitStack() as stack:
        runtime = runtime_type(debug=True)
        if isinstance(runtime, AsyncLocalRuntime):
            await stack.enter_async_context(runtime)
        else:
            stack.enter_context(runtime)
        node_specific, workflow_level = runtime._separate_parameter_formats(
            supplied, workflow
        )
        assert node_specific == {node_id: node_parameters}
        assert workflow_level == {"value": "5", key: "unused"}
        result = runtime._process_workflow_parameters(workflow, supplied)
    assert result == {node_id: {"value": "7"}}
    assert result[node_id] is node_parameters
    assert supplied == {node_id: {"value": "7"}, "value": "5", key: "unused"}
    records = assert_safe(caplog)
    assert any("Separated parameters" in r.getMessage() for r in records)
    assert any("Parameter validation" in r.getMessage() for r in records)


@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("strict", [False, True])
def test_node_warning_transform_does_not_change_public_validation_error(
    caplog, key, strict
):
    class StrictCallerNode(CallerNode):
        _strict_unknown_params = True

    node = StrictCallerNode() if strict else CallerNode()
    caplog.set_level(logging.WARNING, logger="kailash.nodes.base")
    if strict:
        with pytest.raises(NodeValidationError) as error:
            node.validate_inputs(value="7", **{key: "unused"})
        assert repr(key) in str(error.value)
        assert not [r for r in caplog.records if r.name == "kailash.nodes.base"]
    else:
        assert node.validate_inputs(value="7", **{key: "unused"}) == {"value": 7}
        assert_safe(caplog)


@pytest.mark.parametrize("key", KEYS[:2])
@pytest.mark.asyncio
async def test_real_native_async_execution_preserves_validated_parameters(caplog, key):
    workflow = graph()
    caplog.set_level(logging.WARNING)
    caplog.set_level(logging.WARNING, logger="kailash.nodes.base")
    async with AsyncLocalRuntime(debug=True) as runtime:
        results, _ = await runtime.execute_workflow_async(
            workflow, inputs={"node": {"value": "7", key: "unused"}}
        )
    assert results["node"]["value"] == 7
    assert_safe(caplog)


@pytest.mark.parametrize("key", KEYS[:2])
def test_real_local_execution_preserves_validated_parameters(caplog, key):
    workflow = graph()
    caplog.set_level(logging.WARNING)
    caplog.set_level(logging.WARNING, logger="kailash.nodes.base")
    with LocalRuntime(debug=True) as runtime:
        results, _ = runtime.execute(
            workflow, parameters={"node": {"value": "7", key: "unused"}}
        )
    assert results["node"]["value"] == 7
    assert_safe(caplog)


def test_declared_and_suggested_json_keys_are_sanitized_before_formatting(caplog):
    declared = '{"password":"' + SECRET + '"}'
    supplied = '{"password":"' + SECRET + '","typo":true}'

    class SuggestedNode(Node):
        def get_parameters(self):
            return {
                declared: NodeParameter(
                    name=declared, type=int, required=False, default=9
                )
            }

        def run(self, **kwargs):
            return kwargs

    node = SuggestedNode()
    assert declared in node._suggest_parameter_mapping(supplied, [declared])
    with caplog.at_level(logging.WARNING, logger="kailash.nodes.base"):
        assert node.validate_inputs(**{declared: "7", supplied: "unused"}) == {
            declared: 7
        }
    assert_safe(caplog)
    assert any("Suggestions:" in r.getMessage() for r in caplog.records)
