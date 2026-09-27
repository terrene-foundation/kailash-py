"""Parameter names are strings; nested containers remain valid values."""

import pytest

from kailash.runtime.local import LocalRuntime
from kailash.security import SecurityConfig, SecurityError, validate_node_parameters
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.parametrize("context", ["generic", "python_exec", "shell_exec"])
@pytest.mark.parametrize("key", [1, ("tuple",), None, True, b"bytes", 1.5])
def test_non_string_parameter_names_raise_security_error(context, key):
    with pytest.raises(SecurityError, match="Node parameter names must be strings"):
        validate_node_parameters(
            {key: {"nested": [1, {"count": 2}]}},
            config=SecurityConfig(enable_audit_logging=False),
            context=context,
        )


@pytest.mark.parametrize("context", ["generic", "python_exec", "shell_exec"])
def test_string_parameter_names_keep_nested_container_values(context):
    parameters = {"payload": {"nested": [1, {"count": 2}]}, "empty": []}
    assert (
        validate_node_parameters(
            parameters,
            config=SecurityConfig(enable_audit_logging=False),
            context=context,
        )
        == parameters
    )


@pytest.mark.parametrize("context", ["generic", "python_exec", "shell_exec"])
def test_string_parameter_names_keep_context_sanitization(context):
    expected_key = "<name>" if context == "python_exec" else "name"
    assert validate_node_parameters(
        {"<name>": [1, 2]},
        config=SecurityConfig(enable_audit_logging=False),
        context=context,
    ) == {expected_key: [1, 2]}


def test_python_workflow_keeps_nested_parameter_values():
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "echo", {"code": "result = payload"})
    payload = {"nested": [1, {"count": 2}]}
    with LocalRuntime(connection_validation="strict") as runtime:
        results, _ = runtime.execute(
            workflow.build(), parameters={"echo": {"payload": payload}}
        )
    assert results["echo"]["result"] == payload


def test_python_callable_keeps_nested_parameter_values():
    from kailash.nodes.code.python import CodeExecutor

    payload = {"nested": [1, {"count": 2}]}
    executor = CodeExecutor(security_config=SecurityConfig(enable_audit_logging=False))
    assert (
        executor.execute_function(lambda payload: payload, {"payload": payload})
        == payload
    )
