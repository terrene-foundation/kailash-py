"""Unit tests for error capture component.

Tests the ErrorCapture, CapturedError, and StackFrame classes to ensure
proper error capture with full context extraction.
"""

from datetime import datetime

import pytest
from dataflow.debug.error_capture import CapturedError, ErrorCapture, StackFrame


def test_capture_simple_exception():
    """Test capturing a simple exception."""
    capture = ErrorCapture()

    try:
        raise ValueError("Test error")
    except Exception as e:
        captured = capture.capture(e)

    assert captured.error_type == "ValueError"
    assert captured.message == "Test error"
    assert len(captured.stacktrace) > 0
    assert isinstance(captured.timestamp, datetime)
    assert isinstance(captured.exception, ValueError)


def test_capture_dataflow_exception():
    """Test capturing a DataFlow exception with context."""
    capture = ErrorCapture()

    try:
        exc = ValueError("Missing parameter 'id'")
        exc.context = {"node_id": "create_user", "operation": "CREATE"}
        exc.node_id = "create_user"
        exc.parameter_name = "id"
        exc.operation = "CREATE"
        raise exc
    except Exception as e:
        captured = capture.capture(e)

    # Verify context extracted
    assert captured.context["node_id"] == "create_user"
    assert captured.context["operation"] == "CREATE"
    assert captured.context["parameter_name"] == "id"


def test_extract_stacktrace():
    """Test stacktrace extraction with multiple frames."""
    capture = ErrorCapture()

    try:

        def inner_func():
            raise KeyError("test key")

        def outer_func():
            inner_func()

        outer_func()
    except Exception as e:
        captured = capture.capture(e)

    # Verify stacktrace has multiple frames
    assert len(captured.stacktrace) >= 2

    # Verify function names appear in stacktrace
    function_names = [frame.function_name for frame in captured.stacktrace]
    assert "inner_func" in function_names
    assert "outer_func" in function_names

    # Verify stack frame structure
    for frame in captured.stacktrace:
        assert isinstance(frame, StackFrame)
        assert isinstance(frame.filename, str)
        assert isinstance(frame.line_number, int)
        assert isinstance(frame.function_name, str)
        assert isinstance(frame.code_context, str)


def test_get_code_context():
    """Test code context extraction."""
    capture = ErrorCapture()

    try:
        x = 1 / 0  # This line will cause ZeroDivisionError
    except Exception as e:
        captured = capture.capture(e)

    # Code context should include the error line
    last_frame = captured.stacktrace[-1]

    # Context should contain the division line
    assert "1 / 0" in last_frame.code_context or "x = 1 / 0" in last_frame.code_context


def test_captured_error_structure():
    """Test CapturedError data structure completeness."""
    capture = ErrorCapture()

    try:
        raise RuntimeError("Test runtime error")
    except Exception as e:
        captured = capture.capture(e)

    # Verify all required fields are present
    assert hasattr(captured, "exception")
    assert hasattr(captured, "error_type")
    assert hasattr(captured, "message")
    assert hasattr(captured, "stacktrace")
    assert hasattr(captured, "context")
    assert hasattr(captured, "timestamp")

    # Verify field types
    assert isinstance(captured.exception, Exception)
    assert isinstance(captured.error_type, str)
    assert isinstance(captured.message, str)
    assert isinstance(captured.stacktrace, list)
    assert isinstance(captured.context, dict)
    assert isinstance(captured.timestamp, datetime)

    # Verify error was added to history
    assert len(capture.get_all_captured_errors()) == 1
    assert capture.get_all_captured_errors()[0] == captured

    # Test clear functionality
    capture.clear_captured_errors()
    assert len(capture.get_all_captured_errors()) == 0
