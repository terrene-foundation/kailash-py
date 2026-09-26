"""Automatic Python execution diagnostics omit private exception payloads."""

import io
import json
import logging
from pathlib import Path

import pytest

from kailash.nodes.code import python as python_nodes
from kailash.sdk_exceptions import NodeExecutionError
from kailash.security import SecurityConfig, get_security_config, set_security_config

pytestmark = pytest.mark.regression
PRIVATE = "review-person@example.invalid"


@pytest.fixture(autouse=True)
def execution_config():
    previous = get_security_config()
    # These tests exercise diagnostics, not the platform memory safeguard.
    set_security_config(SecurityConfig(memory_limit=None))
    try:
        yield
    finally:
        set_security_config(previous)


@pytest.fixture
def diagnostics():
    stream = io.StringIO()
    records = []

    class Capture(logging.StreamHandler):
        def emit(self, record):
            records.append(dict(record.__dict__))
            super().emit(record)

    handler = Capture(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    logger = logging.getLogger("kailash")
    prior = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        yield stream, records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prior)


def assert_private_diagnostic(diagnostics, event, exception_type):
    stream, records = diagnostics
    failures = [
        r
        for r in records
        if r["name"] == python_nodes.__name__ and r["levelno"] >= logging.ERROR
    ]
    assert len(failures) == 1
    record = failures[0]
    assert record["msg"].startswith(event)
    assert PRIVATE not in stream.getvalue()
    assert PRIVATE not in json.dumps(records, default=str)
    assert exception_type in record["args"]
    assert "@" in record["args"][-1]
    assert record["exc_info"] is None
    assert (
        len(
            [
                line
                for line in stream.getvalue().splitlines()
                if line.startswith("ERROR:")
            ]
        )
        == 1
    )


def test_source_is_pinned():
    root = Path(__file__).resolve().parents[2]
    assert (
        Path(python_nodes.__file__).resolve()
        == root / "src/kailash/nodes/code/python.py"
    )


@pytest.mark.parametrize("mode", ["code", "function"])
def test_public_execution_preserves_chained_error_without_logging_payload(
    mode, diagnostics
):
    def fail(value: str):
        try:
            raise ValueError("cause " + value)
        except ValueError as cause:
            raise RuntimeError("outer " + value) from cause

    if mode == "code":
        node = python_nodes.PythonCodeNode(
            name="privacy_probe",
            code="try:\n    raise ValueError('cause ' + value)\nexcept ValueError as cause:\n    raise RuntimeError('outer ' + value) from cause",
        )
    else:
        node = python_nodes.PythonCodeNode.from_function(fail)
    with pytest.raises(NodeExecutionError) as caught:
        node.execute(value=PRIVATE)
    error = caught.value
    prefix = "Code" if mode == "code" else "Function"
    assert str(error).startswith(
        prefix
        + " execution failed: outer "
        + PRIVATE
        + "\nTraceback (most recent call last):"
    )
    assert "ValueError: cause " + PRIVATE in str(error)
    assert "RuntimeError: outer " + PRIVATE in str(error)
    assert isinstance(error.__context__, RuntimeError)
    assert str(error.__context__) == "outer " + PRIVATE
    assert isinstance(error.__context__.__cause__, ValueError)
    assert str(error.__context__.__cause__) == "cause " + PRIVATE
    assert_private_diagnostic(diagnostics, prefix + " execution failed", "RuntimeError")
    record = [
        r
        for r in diagnostics[1]
        if r["name"] == python_nodes.__name__ and r["levelno"] >= logging.ERROR
    ][0]
    assert "ValueError@" in record["args"][-1]


def test_public_wrapper_rejection_preserves_error_without_logging_payload(diagnostics):
    private_type = type(PRIVATE, (), {})
    node = python_nodes.PythonCodeNode(name="privacy_probe", code="result = value")
    with pytest.raises(NodeExecutionError) as caught:
        node.execute(value=private_type())
    assert str(caught.value).startswith("Execution failed: Input type not allowed:")
    assert PRIVATE in str(caught.value)
    assert str(caught.value) == "Execution failed: " + str(caught.value.__context__)
    assert_private_diagnostic(
        diagnostics, "Python code execution failed", "SecurityError"
    )


def test_hostile_exception_type_is_inert_in_raw_record(diagnostics):
    hostile_type = type("Injected\nERROR counterfeit", (ValueError,), {})

    def fail():
        raise hostile_type(PRIVATE)

    node = python_nodes.PythonCodeNode.from_function(fail)
    with pytest.raises(NodeExecutionError) as caught:
        node.execute()
    assert PRIVATE in str(caught.value)
    assert_private_diagnostic(
        diagnostics, "Function execution failed", "Injected?ERROR?counterfeit"
    )
    records = [
        r
        for r in diagnostics[1]
        if r["name"] == python_nodes.__name__ and r["levelno"] >= logging.ERROR
    ]
    assert all("\n" not in str(arg) for arg in records[0]["args"])


@pytest.mark.parametrize("mode", ["code", "function"])
def test_successful_public_execution_retains_output(mode, diagnostics):
    def produce(value: str) -> dict:
        return {"retained": value}

    node = (
        python_nodes.PythonCodeNode(
            name="privacy_probe", code="result = {'retained': value}"
        )
        if mode == "code"
        else python_nodes.PythonCodeNode.from_function(produce)
    )
    assert node.execute(value=PRIVATE) == {"result": {"retained": PRIVATE}}
    assert not [r for r in diagnostics[1] if r["levelno"] >= logging.WARNING]


@pytest.mark.parametrize("hostile_type", [False, True])
def test_failed_optional_binding_keeps_debug_event_without_payload(
    monkeypatch, diagnostics, hostile_type
):
    executor = python_nodes.CodeExecutor(allowed_modules={"json"})
    original = python_nodes.importlib.import_module
    error_type = (
        type("Injected\nERROR counterfeit", (ImportError,), {})
        if hostile_type
        else ImportError
    )
    reached = []

    def unavailable(name, *args, **kwargs):
        if name == "json":
            reached.append(name)
            raise error_type(PRIVATE)
        return original(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(python_nodes.importlib, "import_module", unavailable)
        assert executor._build_module_bindings("json") == {}
    assert reached == ["json"]
    records = [r for r in diagnostics[1] if r["name"] == python_nodes.__name__]
    assert len(records) == 1
    assert records[0]["levelno"] == logging.DEBUG
    assert records[0]["args"][0] == "json"
    assert records[0]["args"][1] == (
        "Injected?ERROR?counterfeit" if hostile_type else "ImportError"
    )
    assert "@" in records[0]["args"][-1]
    assert records[0]["exc_info"] is None
    assert PRIVATE not in diagnostics[0].getvalue()
    assert PRIVATE not in json.dumps(records, default=str)
    assert len(diagnostics[0].getvalue().splitlines()) == 1


def test_explicit_caller_logging_and_print_remain_caller_owned(diagnostics, capsys):
    node = python_nodes.PythonCodeNode(
        name="explicit_logging",
        code="import logging\nlogging.getLogger('kailash.user').info(value)\nprint(value)\nresult = value",
    )
    assert node.execute(value=PRIVATE) == {"result": PRIVATE}
    assert capsys.readouterr().out == PRIVATE + "\n"
    records = [r for r in diagnostics[1] if r["name"] == "kailash.user"]
    assert len(records) == 1 and records[0]["msg"] == PRIVATE
