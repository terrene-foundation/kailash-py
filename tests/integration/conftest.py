"""Integration test-specific fixtures for Kailash SDK."""

import os
import warnings

# Import common fixtures from parent conftest
# The main conftest.py already provides:
# - temp_data_dir, sample_csv_file, sample_json_file
# - simple_workflow, complex_integration_workflow, error_workflow, parallel_workflow
# - task_manager, sample_manifest
# - mock_api_data, mock_llm_response, large_dataset, yaml_workflow_config

# This file is kept for potential future integration-specific fixtures
# All common fixtures have been moved to the main conftest.py

# Set environment variable to suppress WebSocket deprecation warnings
# This needs to be done before any imports that might trigger the warnings
existing_warnings = os.environ.get("PYTHONWARNINGS", "")
websocket_filters = "ignore::DeprecationWarning:websockets.legacy,ignore::DeprecationWarning:uvicorn.protocols.websockets.websockets_impl"
if existing_warnings:
    os.environ["PYTHONWARNINGS"] = f"{existing_warnings},{websocket_filters}"
else:
    os.environ["PYTHONWARNINGS"] = websocket_filters


# Suppress external library deprecation warnings that occur at import time
def pytest_configure(config):
    """Configure pytest for integration tests."""
    # Suppress WebSocket deprecation warnings from external libraries
    warnings.filterwarnings(
        "ignore",
        message="websockets.legacy is deprecated",
        category=DeprecationWarning,
        module="websockets.legacy",
    )
    warnings.filterwarnings(
        "ignore",
        message="websockets.server.WebSocketServerProtocol is deprecated",
        category=DeprecationWarning,
        module="uvicorn.protocols.websockets.websockets_impl",
    )
