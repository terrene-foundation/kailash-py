"""
Integration Tests for Enhanced Registration Logging

Tests validate that workflow registration produces enhanced logging output
with full endpoint URLs, proper formatting, and multi-channel information.

These tests follow TDD: They will FAIL initially until enhanced logging is implemented.
This is expected behavior - we write tests FIRST, then implement.
"""

import logging
import re
from io import StringIO

from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus


def test_registration_logging_includes_full_urls(caplog):
    """Test that registration logs include complete endpoint URLs with host and port."""
    caplog.set_level(logging.INFO)

    # Create Nexus instance with specific port
    app = Nexus(api_port=8000)

    # Create simple workflow
    workflow = WorkflowBuilder()
    workflow.add_node(
        "PythonCodeNode", "test", {"code": "result = {'message': 'test'}"}
    )

    # Register workflow
    app.register("test_workflow", workflow)

    # Check logs contain full URLs
    log_output = caplog.text

    # Should contain host and port
    assert (
        "http://localhost:8000" in log_output
    ), "Logging should include full URL with host and port"

    # Should contain workflow name in path
    assert (
        "/workflows/test_workflow" in log_output
    ), "Logging should include workflow name in endpoint path"


def test_registration_logging_includes_all_endpoints(caplog):
    """Test that registration logs list all three standard endpoints."""
    caplog.set_level(logging.INFO)

    app = Nexus(api_port=8000)

    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "test", {"code": "result = {'status': 'ok'}"})

    app.register("data_processor", workflow)

    log_output = caplog.text

    # Should mention all three standard endpoints
    assert "/execute" in log_output, "Logging should mention /execute endpoint"
    assert (
        "/workflow/info" in log_output
    ), "Logging should mention /workflow/info endpoint"
    assert "/health" in log_output, "Logging should mention /health endpoint"


def test_registration_logging_shows_http_methods(caplog):
    """Test that registration logs show HTTP methods (POST, GET) for clarity."""
    caplog.set_level(logging.INFO)

    app = Nexus(api_port=8000)

    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "calc", {"code": "result = 42"})

    app.register("calculator", workflow)

    log_output = caplog.text

    # Should show HTTP methods for clarity
    # Looking for patterns like "POST" or "GET" near endpoint mentions
    has_post = "POST" in log_output or "post" in log_output.lower()
    has_get = "GET" in log_output or "get" in log_output.lower()

    assert (
        has_post or has_get
    ), "Logging should indicate HTTP methods (POST/GET) for endpoints"


def test_registration_logging_includes_multi_channel_info(caplog):
    """Test that registration logs mention multi-channel availability."""
    caplog.set_level(logging.INFO)

    app = Nexus(api_port=8000)

    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "greet", {"code": "result = 'Hello'"})

    app.register("greeter", workflow)

    log_output = caplog.text

    # Should mention multiple channels (API, CLI, MCP)
    # At least 2 of the 3 channels should be mentioned
    mentions_api = "API" in log_output or "api" in log_output.lower()
    mentions_cli = "CLI" in log_output or "cli" in log_output.lower()
    mentions_mcp = "MCP" in log_output or "mcp" in log_output.lower()

    channel_count = sum([mentions_api, mentions_cli, mentions_mcp])

    assert (
        channel_count >= 2
    ), "Logging should mention multiple channels (API, CLI, MCP)"


def test_registration_logging_is_human_readable(caplog):
    """Test that registration logs are formatted for human readability."""
    caplog.set_level(logging.INFO)

    app = Nexus(api_port=8000)

    workflow = WorkflowBuilder()
    workflow.add_node(
        "PythonCodeNode", "process", {"code": "result = {'data': 'processed'}"}
    )

    app.register("data_pipeline", workflow)

    log_output = caplog.text

    # Should have some structure (indentation, bullets, or clear separation)
    # Look for indicators of formatting: newlines, bullets (•, -, *), or indentation
    has_newlines = "\n" in log_output
    has_bullets = any(char in log_output for char in ["•", "→", "-", "*"])
    has_spacing = "  " in log_output  # Multiple spaces indicate indentation

    # At least one formatting indicator should be present
    assert (
        has_newlines or has_bullets or has_spacing
    ), "Logging should be formatted for readability (newlines, bullets, or indentation)"


def test_registration_logging_respects_different_ports(caplog):
    """Test that registration logs correctly show custom port numbers."""
    caplog.set_level(logging.INFO)

    # Use non-standard port
    app = Nexus(api_port=9999)

    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "test", {"code": "result = 'ok'"})

    app.register("port_test", workflow)

    log_output = caplog.text

    # Should show the custom port
    assert "9999" in log_output, "Logging should reflect custom port number"

    # Should show full URL with custom port
    assert (
        "localhost:9999" in log_output or "127.0.0.1:9999" in log_output
    ), "Logging should include full URL with custom port"
