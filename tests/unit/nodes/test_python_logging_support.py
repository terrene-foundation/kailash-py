"""
Unit tests for logging support in PythonCodeNode and AsyncPythonCodeNode (v0.9.30).

This test validates that both sync and async Python code nodes support
the logging module for structured logging in user code.

Feature: Added 'logging' and 'io' to ALLOWED_MODULES and ALLOWED_ASYNC_MODULES
"""

import pytest
from kailash.nodes.code.async_python import AsyncPythonCodeNode


@pytest.mark.asyncio
async def test_async_python_logging_basic():
    """Test AsyncPythonCodeNode allows logging module import and usage."""
    code = """
import logging

# Configure logging (use explicit logger name instead of __name__)
logger = logging.getLogger("async_test_logger")
logger.setLevel(logging.INFO)

# Log a message (goes to stderr by default)
logger.info("Processing data in async node")

result = {"status": "logged", "logger_configured": True}
"""

    node = AsyncPythonCodeNode(code=code)

    # Should not raise SafetyViolationError
    result = await node.execute_async()

    assert result["result"]["status"] == "logged"
    assert result["result"]["logger_configured"] is True


@pytest.mark.asyncio
async def test_async_python_logging_with_stringio():
    """Test AsyncPythonCodeNode can use logging with StringIO handler."""
    code = """
import logging
import asyncio
from io import StringIO

# Create string buffer
log_buffer = StringIO()

# Configure logger
logger = logging.getLogger("test_async")
logger.setLevel(logging.INFO)

# Add handler
handler = logging.StreamHandler(log_buffer)
handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
logger.addHandler(handler)

# Log messages
logger.info("Starting async operation")

# Simulate async work
await asyncio.sleep(0.001)

logger.info("Async operation completed")

# Get log output
log_output = log_buffer.getvalue()

result = {
    "log_output": log_output,
    "has_start_message": "Starting async operation" in log_output,
    "has_complete_message": "Async operation completed" in log_output
}
"""

    node = AsyncPythonCodeNode(code=code)
    result = await node.execute_async()

    assert result["result"]["has_start_message"] is True
    assert result["result"]["has_complete_message"] is True
    assert "INFO:" in result["result"]["log_output"]


def test_logging_and_io_modules_in_allowed_lists():
    """Test that logging and io are in the allowed modules lists."""
    from kailash.nodes.code.async_python import ALLOWED_ASYNC_MODULES
    from kailash.nodes.code.python import ALLOWED_MODULES

    assert "logging" in ALLOWED_MODULES, "logging should be in ALLOWED_MODULES"
    assert "io" in ALLOWED_MODULES, "io should be in ALLOWED_MODULES"

    assert (
        "logging" in ALLOWED_ASYNC_MODULES
    ), "logging should be in ALLOWED_ASYNC_MODULES"
    assert "io" in ALLOWED_ASYNC_MODULES, "io should be in ALLOWED_ASYNC_MODULES"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
