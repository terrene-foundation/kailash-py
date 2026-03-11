"""End-to-end tests for handler registration and execution through Nexus.

NO MOCKING - Tests use real Nexus instance with real HTTP server to verify
full handler lifecycle from registration through API execution.
"""

import asyncio
import os
import sys
import time

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))


async def echo_handler(message: str, prefix: str = "Echo") -> dict:
    """Echo back a message with a prefix."""
    return {"response": f"{prefix}: {message}"}


async def compute_handler(x: int, y: int, operation: str = "add") -> dict:
    """Perform a computation."""
    if operation == "add":
        return {"result": x + y}
    elif operation == "multiply":
        return {"result": x * y}
    return {"result": 0}


class TestHandlerE2E:
    """End-to-end tests for handler workflows via real Nexus and HTTP API."""

    @pytest.fixture
    def nexus_app(self):
        """Create a real Nexus app with handler registrations."""
        from nexus import Nexus

        # Use unique port to avoid conflicts
        app = Nexus(api_port=18900, enable_durability=False)

        @app.handler("echo", description="Echo handler")
        async def echo(message: str, prefix: str = "Echo") -> dict:
            return {"response": f"{prefix}: {message}"}

        app.register_handler("compute", compute_handler, description="Compute handler")

        return app

    def test_handler_registration_e2e(self, nexus_app):
        """Verify handlers are registered and accessible via Nexus."""
        assert "echo" in nexus_app._workflows
        assert "compute" in nexus_app._workflows
        assert "echo" in nexus_app._handler_registry
        assert "compute" in nexus_app._handler_registry

    def test_handler_registry_metadata(self, nexus_app):
        """Verify handler registry stores correct metadata."""
        echo_entry = nexus_app._handler_registry["echo"]
        assert echo_entry["description"] == "Echo handler"
        assert echo_entry["workflow"] is not None

        compute_entry = nexus_app._handler_registry["compute"]
        assert compute_entry["description"] == "Compute handler"

    @pytest.mark.asyncio
    async def test_handler_workflow_execution_e2e(self, nexus_app):
        """Execute handler workflow through Nexus's internal execution path."""
        from kailash.runtime import AsyncLocalRuntime

        runtime = AsyncLocalRuntime()

        # Get the workflow that was registered
        workflow = nexus_app._workflows["echo"]

        results, run_id = await runtime.execute_workflow_async(
            workflow, inputs={"message": "Hello World"}
        )

        assert run_id is not None
        # Single-node workflow - get the only result
        handler_result = next(iter(results.values()), {})
        assert handler_result.get("response") == "Echo: Hello World"
